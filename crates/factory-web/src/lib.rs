#![forbid(unsafe_code)]

pub mod auth;
pub mod projection;
pub mod store;
pub mod upload;

use std::{
    collections::BTreeMap,
    convert::Infallible,
    path::{Component, Path, PathBuf},
    sync::Arc,
    time::Duration,
};

use askama::Template;
use axum::{
    Form, Router,
    body::{Body, Bytes},
    extract::{
        DefaultBodyLimit, FromRequest, Multipart, Path as RoutePath, Query, Request, State,
        multipart::Field,
    },
    http::{
        HeaderMap, HeaderValue, StatusCode,
        header::{self, HeaderName},
    },
    middleware::{self, Next},
    response::{
        Html, IntoResponse, Response,
        sse::{Event as SseEvent, KeepAlive, Sse},
    },
    routing::{get, post},
};
use base64::{Engine as _, engine::general_purpose::URL_SAFE_NO_PAD};
use factory_core::{
    REQUEST_BODY_HTML_REQUIRED, REQUEST_BODY_MAX_UTF16_CODE_UNITS,
    auth::{PASSWORD_MAX_BYTES, USERNAME_MAX_BYTES, normalize_username, verify_password},
    schema::SchemaCatalog,
    state::{NewRequest, TraceId},
};
use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use sqlx::postgres::PgListener;
use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;
use tracing::Instrument as _;
use uuid::Uuid;

use crate::{
    auth::{
        Authenticated, LOGIN_COOKIE, SESSION_COOKIE, authenticate, clear_login_cookie,
        clear_session_cookie, client_key, cookie, csrf_for_secret, csrf_valid, hash_secret,
        login_challenge_valid, login_cookie, new_secret, session_cookie,
    },
    projection::{
        Bench, CodebaseMetrics, LanguageMetrics, ModelStage, decision_log_html,
        markdown_without_raw_html, read_bench, read_checkout_revision, read_codebase, read_model,
    },
    store::{
        ActiveRun, ArtifactSummary, DashboardStore, EVENTS_BATCH_LIMIT, EventRecord,
        LOGIN_CHALLENGE_LIFETIME, NewUploadArtifact, PullRequestRecord, RequestDetail,
        RequestRecord, RequestSummary, RunRecord, UploadAdmission, UploadSummary,
    },
    upload::{
        CleanFormat, MAX_CONCURRENT_DECODES, MAX_MULTIPART_BYTES, MAX_UPLOAD_BYTES, UPLOAD_ACCEPT,
        UploadError, UploadStorage, sanitize_image_timed,
    },
};

const TERMINAL_STATES: &[&str] = &[
    "ready_for_review",
    "dry_run_complete",
    "failed",
    "killed",
    "closed",
    "escalated",
];
const MAX_FORM_BYTES: usize = 64 * 1024;

#[derive(Clone)]
pub struct AppState {
    pub store: DashboardStore,
    pub checkout_root: PathBuf,
    pub artifact_root: PathBuf,
    upload_storage: UploadStorage,
    decode_slots: Arc<tokio::sync::Semaphore>,
    dummy_password_hash: String,
    actor_by_stage: BTreeMap<String, String>,
}

impl AppState {
    pub async fn load(
        store: DashboardStore,
        checkout_root: PathBuf,
        artifact_root: PathBuf,
    ) -> Result<Self, AppError> {
        let model = read_model(&checkout_root).await?;
        let dummy_password_hash = tokio::task::spawn_blocking(auth::dummy_password_hash).await??;
        let storage_root = artifact_root.clone();
        let upload_storage =
            tokio::task::spawn_blocking(move || UploadStorage::open(&storage_root)).await??;
        Ok(Self {
            store,
            checkout_root,
            artifact_root,
            upload_storage,
            decode_slots: Arc::new(tokio::sync::Semaphore::new(MAX_CONCURRENT_DECODES)),
            dummy_password_hash,
            actor_by_stage: model.actors(),
        })
    }

    #[cfg(test)]
    fn with_dummy_hash(
        store: DashboardStore,
        checkout_root: PathBuf,
        artifact_root: PathBuf,
        dummy_password_hash: String,
        actor_by_stage: BTreeMap<String, String>,
    ) -> Self {
        let upload_storage =
            UploadStorage::open(&artifact_root).expect("test upload root should be private");
        Self {
            store,
            checkout_root,
            artifact_root,
            upload_storage,
            decode_slots: Arc::new(tokio::sync::Semaphore::new(MAX_CONCURRENT_DECODES)),
            dummy_password_hash,
            actor_by_stage,
        }
    }
}

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/healthz", get(health))
        .route("/csp-report", post(csp_report))
        .route("/login", get(login_form).post(login))
        .route("/logout", post(logout))
        .route("/", get(index))
        .route("/new", get(new_form).post(submit))
        .route("/request/{id}", get(request_detail))
        .route("/request/{id}/events", get(request_events))
        .route("/request/{id}/refresh", post(refresh))
        .route("/run/{id}/kill", post(kill))
        .route("/controls/pause", post(pause))
        .route("/controls/resume", post(resume))
        .route("/controls/full-stop", post(full_stop))
        .route("/upload/{id}", get(upload))
        .route("/evidence/{run_id}/{name}", get(evidence))
        .route("/decisions", get(decisions))
        .route("/bench", get(bench))
        .route("/schema", get(schema))
        .route("/model", get(model))
        .route("/codebase", get(codebase))
        .route("/assets/terminal.css", get(terminal_css))
        .route("/assets/patchyard-theme.css", get(eta_theme_css))
        .route("/projection/{name}", get(projection_asset))
        .fallback(not_found)
        .layer(DefaultBodyLimit::max(MAX_MULTIPART_BYTES))
        .layer(middleware::from_fn(security_headers))
        .with_state(state)
}

async fn health(State(state): State<AppState>) -> Response {
    match sqlx::query_scalar::<_, i32>("SELECT 1")
        .fetch_one(state.store.pool())
        .await
    {
        Ok(1) => (StatusCode::OK, "ok\n").into_response(),
        Ok(_) | Err(_) => (StatusCode::SERVICE_UNAVAILABLE, "unavailable\n").into_response(),
    }
}

async fn csp_report(body: Bytes) -> StatusCode {
    let digest = Sha256::digest(&body);
    tracing::warn!(
        report_bytes = body.len(),
        report_sha256 = %format!("{digest:x}"),
        "browser reported a content security policy violation"
    );
    StatusCode::NO_CONTENT
}

async fn login_form(State(state): State<AppState>, headers: HeaderMap) -> Response {
    match authenticate(&state.store, &headers).await {
        Ok(Some(_)) => redirect_found("/"),
        Ok(None) => render_login(&state, "").await,
        Err(error) => internal_error(error).await,
    }
}

#[derive(Debug, Deserialize)]
struct LoginForm {
    username: String,
    password: String,
    csrf_token: String,
}

async fn login(
    State(state): State<AppState>,
    headers: HeaderMap,
    Form(form): Form<LoginForm>,
) -> Response {
    let Some(raw_login_cookie) = cookie(&headers, LOGIN_COOKIE) else {
        return forbidden("login CSRF challenge missing").await;
    };
    let Some((challenge_hash, challenge_csrf_hash)) =
        login_challenge_valid(&raw_login_cookie, &form.csrf_token)
    else {
        return forbidden("login CSRF challenge invalid").await;
    };
    match state
        .store
        .consume_login_challenge(&challenge_hash, &challenge_csrf_hash)
        .await
    {
        Ok(true) => {}
        Ok(false) => return forbidden("login CSRF challenge expired").await,
        Err(error) => return internal_error(error).await,
    }

    let client = client_key(&headers);
    let username = normalize_username(&form.username).unwrap_or_else(|_| "invalid".to_owned());
    let throttled = match state.store.login_is_throttled(&username, &client).await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    let user = match state.store.user_for_login(&username).await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    let encoded = user.as_ref().map_or_else(
        || state.dummy_password_hash.clone(),
        |record| record.password_hash.clone(),
    );
    let password = form.password;
    let password_valid =
        match tokio::task::spawn_blocking(move || verify_password(&password, &encoded)).await {
            Ok(value) => value,
            Err(error) => return internal_error(error).await,
        };
    let eligible = user
        .as_ref()
        .is_some_and(|record| record.enabled && !record.password_reset_required);
    if throttled || !password_valid || !eligible {
        if let Err(error) = state
            .store
            .record_login_failure(
                user.as_ref().map(|record| record.id),
                &username,
                &client,
                throttled,
            )
            .await
        {
            return internal_error(error).await;
        }
        return if throttled {
            render_login_status(
                &state,
                "Sign-in temporarily throttled. Wait 15 minutes.",
                StatusCode::TOO_MANY_REQUESTS,
            )
            .await
        } else {
            render_login(&state, "Invalid username or password.").await
        };
    }
    let user = user.expect("eligible login has an account");
    let session = new_secret();
    let csrf = csrf_for_secret(&session.value);
    let prior = cookie(&headers, SESSION_COOKIE)
        .filter(|value| value.len() == 43)
        .map(|value| hash_secret(&value));
    let expires = match state
        .store
        .create_session(&user, &session.hash, &csrf.hash, prior.as_ref(), &client)
        .await
    {
        Ok(expires) => expires,
        Err(error) => return internal_error(error).await,
    };
    let mut response = redirect_found("/");
    append_set_cookie(&mut response, session_cookie(&session.value, expires));
    append_set_cookie(&mut response, clear_login_cookie());
    response
}

#[derive(Debug, Deserialize)]
struct CsrfForm {
    csrf_token: String,
}

async fn logout(
    State(state): State<AppState>,
    headers: HeaderMap,
    Form(form): Form<CsrfForm>,
) -> Response {
    let authenticated = match require_auth(&state, &headers, Access::Authenticated).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    if !csrf_valid(&authenticated, &form.csrf_token) {
        return forbidden("CSRF token invalid").await;
    }
    if let Err(error) = state
        .store
        .revoke_session(
            &authenticated.token_hash,
            &authenticated.principal,
            &client_key(&headers),
        )
        .await
    {
        return internal_error(error).await;
    }
    let mut response = redirect_found("/login");
    append_set_cookie(&mut response, clear_session_cookie());
    response
}

async fn index(State(state): State<AppState>, headers: HeaderMap) -> Response {
    let authenticated = match require_auth(&state, &headers, Access::Admin).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let requests = match state.store.requests().await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    let chrome = chrome(&authenticated);
    render_page(IndexTemplate { chrome, requests }, None).await
}

async fn new_form(State(state): State<AppState>, headers: HeaderMap) -> Response {
    let authenticated = match require_auth(&state, &headers, Access::Submit).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    render_page(
        NewTemplate {
            chrome: chrome(&authenticated),
            request_max: REQUEST_BODY_MAX_UTF16_CODE_UNITS,
            request_required: REQUEST_BODY_HTML_REQUIRED,
            upload_accept: UPLOAD_ACCEPT,
            request_body: String::new(),
            error: String::new(),
        },
        None,
    )
    .await
}

async fn submit(State(state): State<AppState>, request: Request) -> Response {
    let headers = request.headers().clone();
    let authenticated = match require_auth(&state, &headers, Access::Submit).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let content_length = match upload_content_length(&headers) {
        Ok(value) => value,
        Err(error) => return error.into_response(),
    };
    let client = client_key(&headers);
    let admission_id = match state
        .store
        .reserve_upload(&authenticated.principal, content_length, &client)
        .await
    {
        Ok(UploadAdmission::Admitted(value)) => value,
        Ok(UploadAdmission::RateLimited) => {
            return error_page(
                StatusCode::TOO_MANY_REQUESTS,
                "Upload rate limit reached. Wait before trying again.",
            )
            .await;
        }
        Ok(UploadAdmission::QuotaExceeded) => {
            return error_page(
                StatusCode::TOO_MANY_REQUESTS,
                "Daily screenshot quota reached.",
            )
            .await;
        }
        Err(error) => return internal_error(error).await,
    };
    let mut multipart = match Multipart::from_request(request, &state).await {
        Ok(value) => value,
        Err(_) => {
            reject_admission(
                &state,
                &authenticated,
                admission_id,
                "malformed-multipart",
                &client,
            )
            .await;
            return upload_form_error(UploadFormError::Multipart).await;
        }
    };
    let csrf = match first_csrf_field(&mut multipart).await {
        Ok(value) => value,
        Err(error) => {
            reject_admission(
                &state,
                &authenticated,
                admission_id,
                error.reason(),
                &client,
            )
            .await;
            return upload_form_error(error).await;
        }
    };
    if !csrf_valid(&authenticated, &csrf) {
        reject_admission(
            &state,
            &authenticated,
            admission_id,
            "invalid-csrf",
            &client,
        )
        .await;
        return forbidden("CSRF token invalid").await;
    }
    let parsed = match remaining_upload_fields(&mut multipart).await {
        Ok(value) => value,
        Err(error) => {
            reject_admission(
                &state,
                &authenticated,
                admission_id,
                error.reason(),
                &client,
            )
            .await;
            return upload_form_error(error).await;
        }
    };
    let source = format!("dashboard:{}", authenticated.principal.id);
    let request = match NewRequest::from_intake(
        Uuid::new_v4(),
        source,
        parsed.request_body.clone(),
        TraceId::random(),
    ) {
        Ok(value) => value,
        Err(error) => {
            reject_admission(
                &state,
                &authenticated,
                admission_id,
                "invalid-request",
                &client,
            )
            .await;
            return render_page_status(
                NewTemplate {
                    chrome: chrome(&authenticated),
                    request_max: REQUEST_BODY_MAX_UTF16_CODE_UNITS,
                    request_required: REQUEST_BODY_HTML_REQUIRED,
                    upload_accept: UPLOAD_ACCEPT,
                    request_body: parsed.request_body,
                    error: error.to_string(),
                },
                None,
                StatusCode::UNPROCESSABLE_ENTITY,
            )
            .await;
        }
    };
    let Some(original) = parsed.screenshot else {
        reject_admission(
            &state,
            &authenticated,
            admission_id,
            "no-screenshot",
            &client,
        )
        .await;
        let created = match state
            .store
            .submit_request(&request, &authenticated.principal, &client)
            .await
        {
            Ok(value) => value,
            Err(error) => return internal_error(error).await,
        };
        return receipt(&state, &authenticated, created).await;
    };

    let clean = match sanitize_image_timed(original, Arc::clone(&state.decode_slots)).await {
        Ok(value) => value,
        Err(error) => {
            let reason = upload_error_reason(&error);
            reject_admission(&state, &authenticated, admission_id, reason, &client).await;
            return upload_pipeline_error(error).await;
        }
    };
    let upload_id = Uuid::new_v4();
    let format = clean.format;
    let sha256 = clean.sha256;
    let clean_bytes = match i64::try_from(clean.bytes.len()) {
        Ok(value) => value,
        Err(_) => {
            reject_admission(
                &state,
                &authenticated,
                admission_id,
                "clean-size-overflow",
                &client,
            )
            .await;
            return upload_pipeline_error(UploadError::CleanImageTooLarge).await;
        }
    };
    let storage = state.upload_storage.clone();
    let relative_path =
        match tokio::task::spawn_blocking(move || storage.store(upload_id, &clean)).await {
            Ok(Ok(value)) => value,
            Ok(Err(error)) => {
                reject_admission(
                    &state,
                    &authenticated,
                    admission_id,
                    upload_error_reason(&error),
                    &client,
                )
                .await;
                return upload_pipeline_error(error).await;
            }
            Err(error) => {
                reject_admission(
                    &state,
                    &authenticated,
                    admission_id,
                    "storage-task",
                    &client,
                )
                .await;
                return internal_error(error).await;
            }
        };
    let upload = NewUploadArtifact {
        id: upload_id,
        relative_path: relative_path.clone(),
        sha256,
        kind: match format {
            CleanFormat::Png => "request-screenshot-png",
            CleanFormat::Jpeg => "request-screenshot-jpeg",
        },
        clean_bytes,
    };
    let created = match state
        .store
        .submit_request_with_upload(
            &request,
            &authenticated.principal,
            admission_id,
            &upload,
            &client,
        )
        .await
    {
        Ok(value) => value,
        Err(error) => {
            cleanup_stored_upload(&state, upload_id, relative_path).await;
            reject_admission(
                &state,
                &authenticated,
                admission_id,
                "database-registration",
                &client,
            )
            .await;
            return internal_error(error).await;
        }
    };
    if !created.inserted {
        cleanup_stored_upload(&state, upload_id, relative_path).await;
        return error_page(
            StatusCode::CONFLICT,
            "Duplicate request rejected; the existing intake was left unchanged.",
        )
        .await;
    }
    receipt(&state, &authenticated, created).await
}

struct ParsedUploadForm {
    request_body: String,
    screenshot: Option<Vec<u8>>,
}

#[derive(Debug)]
enum UploadFormError {
    MissingCsrf,
    CsrfShape,
    MissingRequest,
    RequestShape,
    InvalidUtf8,
    SuspiciousFilename,
    TooLarge,
    ExtraField,
    Multipart,
}

impl UploadFormError {
    const fn reason(&self) -> &'static str {
        match self {
            Self::MissingCsrf => "missing-csrf",
            Self::CsrfShape => "csrf-shape",
            Self::MissingRequest => "missing-request",
            Self::RequestShape => "request-shape",
            Self::InvalidUtf8 => "invalid-utf8",
            Self::SuspiciousFilename => "unsafe-filename",
            Self::TooLarge => "field-too-large",
            Self::ExtraField => "extra-field",
            Self::Multipart => "malformed-multipart",
        }
    }
}

fn upload_content_length(headers: &HeaderMap) -> Result<i64, (StatusCode, &'static str)> {
    let Some(value) = headers.get(header::CONTENT_LENGTH) else {
        return Err((
            StatusCode::LENGTH_REQUIRED,
            "Content-Length is required for uploads.\n",
        ));
    };
    let length = value
        .to_str()
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0)
        .ok_or((StatusCode::BAD_REQUEST, "Content-Length is invalid.\n"))?;
    if length > MAX_MULTIPART_BYTES {
        return Err((
            StatusCode::PAYLOAD_TOO_LARGE,
            "Multipart request exceeds the upload limit.\n",
        ));
    }
    i64::try_from(length).map_err(|_| {
        (
            StatusCode::PAYLOAD_TOO_LARGE,
            "Multipart request exceeds the upload limit.\n",
        )
    })
}

async fn first_csrf_field(multipart: &mut Multipart) -> Result<String, UploadFormError> {
    let field = multipart
        .next_field()
        .await
        .map_err(|_| UploadFormError::Multipart)?
        .ok_or(UploadFormError::MissingCsrf)?;
    if field.name() != Some("csrf_token") || field.file_name().is_some() {
        return Err(UploadFormError::CsrfShape);
    }
    let bytes = read_field_limited(field, 256).await?;
    String::from_utf8(bytes).map_err(|_| UploadFormError::InvalidUtf8)
}

async fn remaining_upload_fields(
    multipart: &mut Multipart,
) -> Result<ParsedUploadForm, UploadFormError> {
    let request = multipart
        .next_field()
        .await
        .map_err(|_| UploadFormError::Multipart)?
        .ok_or(UploadFormError::MissingRequest)?;
    if request.name() != Some("request_body") || request.file_name().is_some() {
        return Err(UploadFormError::RequestShape);
    }
    let request_body = String::from_utf8(read_field_limited(request, MAX_FORM_BYTES).await?)
        .map_err(|_| UploadFormError::InvalidUtf8)?;

    let screenshot = match multipart
        .next_field()
        .await
        .map_err(|_| UploadFormError::Multipart)?
    {
        None => None,
        Some(field) => {
            if field.name() != Some("screenshot") {
                return Err(UploadFormError::ExtraField);
            }
            let filename = field.file_name().unwrap_or_default();
            if !filename.is_empty() && suspicious_filename(filename) {
                return Err(UploadFormError::SuspiciousFilename);
            }
            let bytes = read_field_limited(field, MAX_UPLOAD_BYTES).await?;
            (!bytes.is_empty()).then_some(bytes)
        }
    };
    if multipart
        .next_field()
        .await
        .map_err(|_| UploadFormError::Multipart)?
        .is_some()
    {
        return Err(UploadFormError::ExtraField);
    }
    Ok(ParsedUploadForm {
        request_body,
        screenshot,
    })
}

async fn read_field_limited(
    mut field: Field<'_>,
    maximum: usize,
) -> Result<Vec<u8>, UploadFormError> {
    let mut bytes = Vec::new();
    while let Some(chunk) = field
        .chunk()
        .await
        .map_err(|_| UploadFormError::Multipart)?
    {
        if chunk.len() > maximum.saturating_sub(bytes.len()) {
            return Err(UploadFormError::TooLarge);
        }
        bytes.extend_from_slice(&chunk);
    }
    Ok(bytes)
}

fn suspicious_filename(value: &str) -> bool {
    value.len() > 128
        || value.is_empty()
        || value.starts_with('.')
        || value
            .bytes()
            .any(|byte| byte.is_ascii_control() || matches!(byte, b'/' | b'\\' | b':' | b'\0'))
        || value.bytes().filter(|byte| *byte == b'.').count() > 1
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-' | b' '))
}

async fn upload_form_error(error: UploadFormError) -> Response {
    let status = if matches!(error, UploadFormError::TooLarge) {
        StatusCode::PAYLOAD_TOO_LARGE
    } else {
        StatusCode::UNPROCESSABLE_ENTITY
    };
    error_page(status, "Malformed or disallowed upload form.").await
}

fn upload_error_reason(error: &UploadError) -> &'static str {
    match error {
        UploadError::UnsupportedType => "unsupported-type",
        UploadError::Dimensions => "dimension-limit",
        UploadError::InvalidImage => "invalid-image",
        UploadError::CleanImageTooLarge => "clean-image-too-large",
        UploadError::DecodeTimeout => "decode-timeout",
        UploadError::DecodeBusy => "decode-busy",
        UploadError::BlockingTask => "decode-task",
        UploadError::InvalidPath => "invalid-path",
        UploadError::UnsafeFilesystemObject => "unsafe-filesystem",
        UploadError::DiskFull => "disk-full",
        UploadError::Io(_) => "storage-io",
    }
}

async fn upload_pipeline_error(error: UploadError) -> Response {
    match error {
        UploadError::UnsupportedType => {
            error_page(
                StatusCode::UNSUPPORTED_MEDIA_TYPE,
                "Only valid PNG and JPEG screenshots are accepted.",
            )
            .await
        }
        UploadError::Dimensions | UploadError::InvalidImage | UploadError::CleanImageTooLarge => {
            error_page(
                StatusCode::UNPROCESSABLE_ENTITY,
                "Screenshot failed the image safety limits.",
            )
            .await
        }
        UploadError::DecodeTimeout => {
            error_page(
                StatusCode::REQUEST_TIMEOUT,
                "Screenshot decode exceeded the safety timeout.",
            )
            .await
        }
        UploadError::DecodeBusy => {
            error_page(
                StatusCode::SERVICE_UNAVAILABLE,
                "Screenshot decoder is temporarily at capacity.",
            )
            .await
        }
        UploadError::DiskFull => {
            tracing::error!("upload storage exhausted; intake failed closed");
            error_page(
                StatusCode::from_u16(507).expect("507 is a valid HTTP status"),
                "Screenshot storage is full; nothing was accepted.",
            )
            .await
        }
        error => internal_error(error).await,
    }
}

async fn reject_admission(
    state: &AppState,
    authenticated: &Authenticated,
    admission_id: Uuid,
    reason: &'static str,
    client: &str,
) {
    if let Err(error) = state
        .store
        .reject_upload(admission_id, &authenticated.principal, reason, client)
        .await
    {
        tracing::error!(%admission_id, %error, "failed to close upload admission");
    }
}

async fn cleanup_stored_upload(state: &AppState, id: Uuid, relative_path: PathBuf) {
    let storage = state.upload_storage.clone();
    match tokio::task::spawn_blocking(move || storage.remove(id, &relative_path)).await {
        Ok(Ok(())) => {}
        Ok(Err(error)) => {
            tracing::error!(%id, %error, "stored upload cleanup failed");
        }
        Err(error) => {
            tracing::error!(%id, %error, "stored upload cleanup task failed");
        }
    }
}

async fn receipt(
    state: &AppState,
    authenticated: &Authenticated,
    created: factory_core::state::RequestCreated,
) -> Response {
    let status = match state.store.request_status(created.id).await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    render_page(
        ReceiptTemplate {
            chrome: chrome(authenticated),
            request_id: created.id,
            inserted: created.inserted,
            status,
        },
        None,
    )
    .await
}

async fn request_detail(
    State(state): State<AppState>,
    RoutePath(request_id): RoutePath<Uuid>,
    headers: HeaderMap,
) -> Response {
    let authenticated = match require_auth(&state, &headers, Access::Admin).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let detail = match state.store.request_detail(request_id).await {
        Ok(Some(value)) => value,
        Ok(None) => return not_found_response().await,
        Err(error) => return internal_error(error).await,
    };
    let terminal = detail_is_terminal(&detail);
    let last_event_id = detail.events.last().map_or(0, |event| event.id);
    let artifacts = artifact_views(&detail.artifacts);
    let uploads = upload_views(&detail.uploads);
    let template = DetailTemplate {
        chrome: chrome(&authenticated),
        request: detail.request,
        runs: detail.runs,
        events: event_views(&detail.events, &state.actor_by_stage, terminal),
        pulls: pull_views(&detail.pulls),
        artifacts,
        uploads,
        terminal,
        last_event_id,
    };
    render_page(template, (!terminal).then_some("15")).await
}

#[derive(Debug, Deserialize)]
struct EventsQuery {
    after: Option<i64>,
}

async fn request_events(
    State(state): State<AppState>,
    RoutePath(request_id): RoutePath<Uuid>,
    Query(query): Query<EventsQuery>,
    headers: HeaderMap,
) -> Response {
    let authenticated = match require_auth(&state, &headers, Access::Admin).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    match state.store.request_exists(request_id).await {
        Ok(true) => {}
        Ok(false) => return not_found_response().await,
        Err(error) => return internal_error(error).await,
    }
    let last_id = headers
        .get("last-event-id")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.parse::<i64>().ok())
        .filter(|value| *value >= 0)
        .or_else(|| query.after.filter(|value| *value >= 0))
        .unwrap_or(0);
    let mut listener = match PgListener::connect_with(state.store.pool()).await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    if let Err(error) = listener.listen("factory_events").await {
        return internal_error(error).await;
    }
    if let Err(error) = listener.listen("factory_auth").await {
        return internal_error(error).await;
    }
    // Close the revocation race between initial auth and LISTEN setup: changes
    // before LISTEN are visible in this durable recheck; later changes wake the
    // listener.
    let authenticated = match state.store.authenticate(&authenticated.token_hash).await {
        Ok(Some(value)) if value.id == authenticated.principal.id => Authenticated {
            principal: value,
            ..authenticated
        },
        Ok(Some(_)) | Ok(None) => return redirect_found("/login"),
        Err(error) => return internal_error(error).await,
    };
    let (sender, receiver) = mpsc::channel::<Result<SseEvent, Infallible>>(32);
    let store = state.store.clone();
    let actor_by_stage = state.actor_by_stage.clone();
    let user_id = authenticated.principal.id;
    let expires_at = authenticated
        .principal
        .idle_expires_at
        .min(authenticated.principal.absolute_expires_at);
    tokio::spawn(
        async move {
            let mut cursor = last_id;
            let expires_in = (expires_at - time::OffsetDateTime::now_utc())
                .try_into()
                .unwrap_or(Duration::ZERO);
            let session_expiry = tokio::time::sleep(expires_in);
            tokio::pin!(session_expiry);
            loop {
                let events = match store.events_after(request_id, cursor).await {
                    Ok(value) => value,
                    Err(error) => {
                        tracing::warn!(%request_id, %error, "SSE ledger query failed");
                        break;
                    }
                };
                let caught_up = events.len()
                    < usize::try_from(EVENTS_BATCH_LIMIT).expect("event batch limit fits usize");
                let mut terminal = false;
                for event in events {
                    cursor = event.id;
                    let frame = EventFrame::from_record(&event, &actor_by_stage);
                    terminal |= frame.terminal;
                    let data = match serde_json::to_string(&frame) {
                        Ok(value) => value,
                        Err(error) => {
                            tracing::warn!(%request_id, %error, "SSE frame serialization failed");
                            break;
                        }
                    };
                    if sender
                        .send(Ok(SseEvent::default()
                            .event("ledger")
                            .id(event.id.to_string())
                            .data(data)))
                        .await
                        .is_err()
                    {
                        terminal = true;
                        break;
                    }
                }
                if terminal {
                    break;
                }
                if !caught_up {
                    continue;
                }
                // Cancellation audit: `Sender::closed` and PgListener::recv are
                // cancellation-safe. A notification is only a wake; after every
                // wake the durable ledger is selected by monotonically increasing
                // event id, so cancelling recv loses no state.
                tokio::select! {
                    () = sender.closed() => break,
                    () = &mut session_expiry => break,
                    notification = listener.recv() => match notification {
                        Ok(notification)
                            if notification.channel() == "factory_events"
                                && notification.payload() == request_id.to_string() => {}
                        Ok(notification)
                            if notification.channel() == "factory_auth"
                                && notification.payload() == user_id.to_string() => break,
                        Ok(_) => continue,
                        Err(error) => {
                            tracing::warn!(%request_id, %error, "SSE LISTEN connection failed");
                            break;
                        }
                    }
                }
            }
            // PgListener has no close method. UNLISTEN is its fallible async
            // shutdown operation; dropping then returns the connection to the pool.
            if let Err(error) = listener.unlisten_all().await {
                tracing::warn!(%request_id, %error, "SSE listener shutdown failed");
            }
        }
        .instrument(tracing::info_span!("dashboard_sse", %request_id)),
    );
    let mut response = Sse::new(ReceiverStream::new(receiver))
        .keep_alive(
            KeepAlive::new()
                .interval(Duration::from_secs(20))
                .text("keep-alive"),
        )
        .into_response();
    response
        .headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache"));
    response.headers_mut().insert(
        HeaderName::from_static("x-accel-buffering"),
        HeaderValue::from_static("no"),
    );
    response
}

async fn refresh(
    State(state): State<AppState>,
    RoutePath(request_id): RoutePath<Uuid>,
    headers: HeaderMap,
    Form(form): Form<CsrfForm>,
) -> Response {
    let authenticated = match require_auth(&state, &headers, Access::Admin).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    if !csrf_valid(&authenticated, &form.csrf_token) {
        return forbidden("CSRF token invalid").await;
    }
    if let Err(error) = state
        .store
        .enqueue_reconcile(request_id, &authenticated.principal, &client_key(&headers))
        .await
    {
        return internal_error(error).await;
    }
    see_other(&format!("/request/{request_id}"))
}

async fn pause(
    State(state): State<AppState>,
    headers: HeaderMap,
    Form(form): Form<CsrfForm>,
) -> Response {
    control(&state, &headers, &form, "pause", None).await
}

async fn resume(
    State(state): State<AppState>,
    headers: HeaderMap,
    Form(form): Form<CsrfForm>,
) -> Response {
    control(&state, &headers, &form, "resume", None).await
}

async fn full_stop(
    State(state): State<AppState>,
    headers: HeaderMap,
    Form(form): Form<CsrfForm>,
) -> Response {
    control(&state, &headers, &form, "full_stop", None).await
}

async fn kill(
    State(state): State<AppState>,
    RoutePath(run_id): RoutePath<Uuid>,
    headers: HeaderMap,
    Form(form): Form<CsrfForm>,
) -> Response {
    control(&state, &headers, &form, "kill", Some(run_id)).await
}

async fn control(
    state: &AppState,
    headers: &HeaderMap,
    form: &CsrfForm,
    command: &str,
    target: Option<Uuid>,
) -> Response {
    let authenticated = match require_auth(state, headers, Access::Admin).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    if !csrf_valid(&authenticated, &form.csrf_token) {
        return forbidden("CSRF token invalid").await;
    }
    if let Err(error) = state
        .store
        .enqueue_control(
            command,
            target,
            &authenticated.principal,
            &client_key(headers),
        )
        .await
    {
        return internal_error(error).await;
    }
    see_other("/")
}

async fn upload(
    State(state): State<AppState>,
    RoutePath(upload_id): RoutePath<Uuid>,
    headers: HeaderMap,
) -> Response {
    if let Err(response) = require_auth(&state, &headers, Access::Admin).await {
        return response;
    }
    let artifact = match state.store.upload(upload_id).await {
        Ok(Some(value)) => value,
        Ok(None) => return not_found_response().await,
        Err(error) => return internal_error(error).await,
    };
    let expected = artifact.sha256;
    let expected_kind = artifact.kind;
    let relative_path = artifact.relative_path;
    let storage = state.upload_storage.clone();
    let loaded = tokio::task::spawn_blocking(move || {
        let (bytes, format) = storage.read(upload_id, &relative_path)?;
        let actual: [u8; 32] = Sha256::digest(&bytes).into();
        Ok::<_, UploadError>((bytes, format, actual))
    })
    .await;
    let (bytes, format, actual) = match loaded {
        Ok(Ok(value)) => value,
        Ok(Err(UploadError::Io(error))) if error.kind() == std::io::ErrorKind::NotFound => {
            return not_found_response().await;
        }
        Ok(Err(error)) => return internal_error(error).await,
        Err(error) => return internal_error(error).await,
    };
    let kind_matches = matches!(
        (format, expected_kind.as_str()),
        (CleanFormat::Png, "request-screenshot-png")
            | (CleanFormat::Jpeg, "request-screenshot-jpeg")
    );
    if actual != expected || !kind_matches {
        tracing::error!(%upload_id, "clean upload integrity or media-type mismatch");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            "upload integrity failure\n",
        )
            .into_response();
    }

    let filename = format!("{upload_id}.{}", format.extension());
    let mut response = Response::new(Body::from(bytes));
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static(format.content_type()),
    );
    response.headers_mut().insert(
        header::CONTENT_DISPOSITION,
        HeaderValue::from_str(&format!("attachment; filename=\"{filename}\""))
            .expect("UUID upload filename is a valid header value"),
    );
    response.headers_mut().insert(
        header::CONTENT_SECURITY_POLICY,
        HeaderValue::from_static("sandbox; default-src 'none'"),
    );
    response.headers_mut().insert(
        HeaderName::from_static("cross-origin-resource-policy"),
        HeaderValue::from_static("same-site"),
    );
    response.headers_mut().insert(
        header::X_CONTENT_TYPE_OPTIONS,
        HeaderValue::from_static("nosniff"),
    );
    response
}

async fn evidence(
    State(state): State<AppState>,
    RoutePath((run_id, name)): RoutePath<(Uuid, String)>,
    headers: HeaderMap,
) -> Response {
    if let Err(response) = require_auth(&state, &headers, Access::Admin).await {
        return response;
    }
    if !safe_evidence_name(&name) {
        return not_found_response().await;
    }
    let artifact = match state.store.artifact(run_id, &name).await {
        Ok(Some(value)) => value,
        Ok(None) => return not_found_response().await,
        Err(error) => return internal_error(error).await,
    };
    let root = match tokio::fs::canonicalize(&state.artifact_root).await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    let path = match safe_artifact_path(&root, &artifact.relative_path).await {
        Ok(Some(value)) => value,
        Ok(None) => return not_found_response().await,
        Err(error) => return internal_error(error).await,
    };
    let bytes = match tokio::fs::read(path).await {
        Ok(value) => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return not_found_response().await;
        }
        Err(error) => return internal_error(error).await,
    };
    let expected = artifact.sha256;
    let (bytes, actual): (Vec<u8>, [u8; 32]) = match tokio::task::spawn_blocking(move || {
        let digest = Sha256::digest(&bytes).into();
        (bytes, digest)
    })
    .await
    {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    if actual != expected {
        tracing::error!(%run_id, %name, "artifact SHA-256 mismatch");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            "artifact integrity failure\n",
        )
            .into_response();
    }
    let mut response = Response::new(Body::from(bytes));
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/octet-stream"),
    );
    response.headers_mut().insert(
        header::CONTENT_DISPOSITION,
        HeaderValue::from_str(&format!("attachment; filename=\"{name}\""))
            .unwrap_or_else(|_| HeaderValue::from_static("attachment")),
    );
    response
}

async fn decisions(State(state): State<AppState>, headers: HeaderMap) -> Response {
    let authenticated = match require_auth(&state, &headers, Access::Authenticated).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let source =
        match tokio::fs::read_to_string(state.checkout_root.join("docs/decision-log.md")).await {
            Ok(value) => value,
            Err(error) => return internal_error(error).await,
        };
    let html = match tokio::task::spawn_blocking(move || decision_log_html(&source)).await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    render_page(
        DecisionsTemplate {
            chrome: chrome(&authenticated),
            decision_html: html,
        },
        None,
    )
    .await
}

async fn bench(State(state): State<AppState>, headers: HeaderMap) -> Response {
    let authenticated = match require_auth(&state, &headers, Access::Admin).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let bench = match read_bench(&state.checkout_root).await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    render_page(
        BenchTemplate {
            chrome: chrome(&authenticated),
            bench,
        },
        None,
    )
    .await
}

async fn schema(State(state): State<AppState>, headers: HeaderMap) -> Response {
    let authenticated = match require_auth(&state, &headers, Access::Admin).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let catalog = match state.store.schema().await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    render_page(
        SchemaTemplate {
            chrome: chrome(&authenticated),
            catalog,
        },
        None,
    )
    .await
}

async fn model(State(state): State<AppState>, headers: HeaderMap) -> Response {
    let authenticated = match require_auth(&state, &headers, Access::Authenticated).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let model = match read_model(&state.checkout_root).await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    let runs = match state.store.active_runs().await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    let has_runs = !runs.is_empty();
    render_page(
        ModelTemplate {
            chrome: chrome(&authenticated),
            model_version: model.model_version.to_string(),
            stages: model.stages,
            runs,
            has_runs,
        },
        None,
    )
    .await
}

async fn codebase(State(state): State<AppState>, headers: HeaderMap) -> Response {
    let authenticated = match require_auth(&state, &headers, Access::Authenticated).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let metrics = match read_codebase(&state.checkout_root).await {
        Ok(value) => value,
        Err(error) => return internal_error(error).await,
    };
    let roles = metrics
        .roles
        .iter()
        .map(|role| CodebaseRoleView {
            role: role.role.clone(),
            description_html: markdown_without_raw_html(&role.description),
            code: role.code,
            comments: role.comments,
            blanks: role.blanks,
            files: role.files,
            languages: role.languages.clone(),
        })
        .collect();
    let revision = read_checkout_revision(&state.checkout_root)
        .await
        .unwrap_or_else(|| "an unreported revision".to_owned());
    render_page(
        CodebaseTemplate {
            chrome: chrome(&authenticated),
            metrics,
            revision,
            roles,
        },
        None,
    )
    .await
}

async fn terminal_css() -> Response {
    static_asset(
        include_str!("../../../assets/dashboard/terminal.css"),
        "text/css; charset=utf-8",
    )
}

async fn eta_theme_css() -> Response {
    static_asset(
        include_str!("../../../assets/dashboard/patchyard-theme.css"),
        "text/css; charset=utf-8",
    )
}

async fn projection_asset(
    State(state): State<AppState>,
    RoutePath(name): RoutePath<String>,
    headers: HeaderMap,
) -> Response {
    if let Err(response) = require_auth(&state, &headers, Access::Authenticated).await {
        return response;
    }
    let (relative, content_type) = match name.as_str() {
        "factory-model.svg" => ("model/factory-model.svg", "image/svg+xml"),
        "factory-model.json" => ("model/factory-model.json", "application/json"),
        "factory-model.mmd" => ("model/factory-model.mmd", "text/plain; charset=utf-8"),
        "factory-model.schema.json" => {
            ("model/factory-model.schema.json", "application/schema+json")
        }
        _ => return not_found_response().await,
    };
    match tokio::fs::read(state.checkout_root.join(relative)).await {
        Ok(bytes) => binary_asset(bytes, content_type),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => not_found_response().await,
        Err(error) => internal_error(error).await,
    }
}

async fn render_login(state: &AppState, error: &str) -> Response {
    render_login_status(state, error, StatusCode::OK).await
}

async fn render_login_status(state: &AppState, error: &str, status: StatusCode) -> Response {
    let challenge = new_secret();
    let csrf = csrf_for_secret(&challenge.value);
    if let Err(store_error) = state
        .store
        .create_login_challenge(&challenge.hash, &csrf.hash)
        .await
    {
        return internal_error(store_error).await;
    }
    let nonce = nonce();
    let template = LoginTemplate {
        chrome: PageChrome::anonymous(nonce.clone()),
        login_csrf: csrf.value,
        username_max: USERNAME_MAX_BYTES,
        password_max: PASSWORD_MAX_BYTES,
        error: error.to_owned(),
    };
    let mut response = render_page_status(template, None, status).await;
    append_set_cookie(
        &mut response,
        login_cookie(&challenge.value, LOGIN_CHALLENGE_LIFETIME),
    );
    response
}

#[derive(Clone, Copy)]
enum Access {
    Authenticated,
    Submit,
    Admin,
}

async fn require_auth(
    state: &AppState,
    headers: &HeaderMap,
    access: Access,
) -> Result<Authenticated, Response> {
    let authenticated = match authenticate(&state.store, headers).await {
        Ok(Some(value)) => value,
        Ok(None) => return Err(redirect_found("/login")),
        Err(error) => return Err(internal_error(error).await),
    };
    let allowed = match access {
        Access::Authenticated => true,
        Access::Submit => authenticated.principal.role.can_submit(),
        Access::Admin => authenticated.principal.role.can_admin(),
    };
    if allowed {
        Ok(authenticated)
    } else {
        Err(forbidden("role does not authorize this route").await)
    }
}

fn detail_is_terminal(detail: &RequestDetail) -> bool {
    if matches!(
        detail.request.status.as_str(),
        "closed" | "failed" | "killed"
    ) {
        return true;
    }
    detail
        .runs
        .last()
        .is_some_and(|run| TERMINAL_STATES.contains(&run.state.as_str()))
}

fn actor_for_event(event: &EventRecord, actors: &BTreeMap<String, String>) -> String {
    let state = event
        .to_state
        .as_deref()
        .or(event.from_state.as_deref())
        .unwrap_or("intake");
    let stage = match state {
        "queued" | "claimed" => "intake",
        "triaging" | "plan_bin" => "triage",
        "implementing" | "reviewing" | "repairing" => "implement",
        "verifying" | "verified" => "verify",
        "publishing" | "ready_for_review" => "approve",
        "closed" | "dry_run_complete" | "failed" | "killed" | "escalated" => "close",
        _ => "intake",
    };
    actors
        .get(stage)
        .cloned()
        .unwrap_or_else(|| "deterministic".to_owned())
}

fn event_views(
    events: &[EventRecord],
    actors: &BTreeMap<String, String>,
    terminal: bool,
) -> Vec<EventView> {
    let now = time::OffsetDateTime::now_utc();
    let last = events.len().saturating_sub(1);
    events
        .iter()
        .enumerate()
        .map(|(index, event)| EventView {
            id: event.id,
            event_type: event.event_type.clone(),
            to_state: event.to_state.clone().unwrap_or_default(),
            payload: serde_json::to_string(&event.payload).unwrap_or_else(|_| "{}".to_owned()),
            occurred_at: event.occurred_at.to_string(),
            actor: actor_for_event(event, actors),
            duration: index
                .checked_sub(1)
                .map(|previous| duration_label(event.occurred_at - events[previous].occurred_at))
                .unwrap_or_default(),
            elapsed: if index == last && !terminal {
                duration_label(now - event.occurred_at)
            } else {
                String::new()
            },
            current: index == last,
        })
        .collect()
}

fn duration_label(duration: time::Duration) -> String {
    let milliseconds = duration.whole_milliseconds().max(0);
    format!("{}.{:03}s", milliseconds / 1_000, milliseconds % 1_000)
}

fn pull_views(pulls: &[PullRequestRecord]) -> Vec<PullView> {
    pulls
        .iter()
        .map(|pull| PullView {
            number: pull.number,
            state_text: pull.state.clone().unwrap_or_else(|| "unknown".to_owned()),
            ci_state: pull.ci_state.clone(),
            review_state: pull.review_state.clone(),
            safe_url: pull
                .html_url
                .as_deref()
                .filter(|url| url.starts_with("https://github.com/example-org/"))
                .unwrap_or_default()
                .to_owned(),
        })
        .collect()
}

fn artifact_views(artifacts: &[ArtifactSummary]) -> Vec<ArtifactView> {
    artifacts
        .iter()
        .filter_map(|artifact| {
            let name = artifact.relative_path.file_name()?.to_str()?;
            safe_evidence_name(name).then(|| ArtifactView {
                run_id: artifact.run_id,
                name: name.to_owned(),
                kind: artifact.kind.clone(),
                created_at: artifact.created_at.to_string(),
            })
        })
        .collect()
}

fn upload_views(uploads: &[UploadSummary]) -> Vec<UploadView> {
    uploads
        .iter()
        .map(|upload| UploadView {
            id: upload.id,
            kind: upload.kind.clone(),
            created_at: upload.created_at.to_string(),
        })
        .collect()
}

async fn safe_artifact_path(
    canonical_root: &Path,
    relative: &Path,
) -> Result<Option<PathBuf>, std::io::Error> {
    if relative.as_os_str().is_empty()
        || relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Ok(None);
    }
    let candidate = canonical_root.join(relative);
    let canonical = match tokio::fs::canonicalize(candidate).await {
        Ok(value) => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    Ok(canonical.starts_with(canonical_root).then_some(canonical))
}

fn safe_evidence_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && !matches!(value, "." | "..")
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
}

fn see_other(location: &str) -> Response {
    redirect_found(location)
}

fn redirect_found(location: &str) -> Response {
    let mut response = StatusCode::FOUND.into_response();
    if let Ok(location) = HeaderValue::from_str(location) {
        response.headers_mut().insert(header::LOCATION, location);
    }
    response
}

fn append_set_cookie(response: &mut Response, value: String) {
    if let Ok(value) = HeaderValue::from_str(&value) {
        response.headers_mut().append(header::SET_COOKIE, value);
    }
}

fn static_asset(content: &'static str, content_type: &'static str) -> Response {
    binary_asset(content.as_bytes().to_vec(), content_type)
}

fn binary_asset(content: Vec<u8>, content_type: &'static str) -> Response {
    let mut response = Response::new(Body::from(content));
    response
        .headers_mut()
        .insert(header::CONTENT_TYPE, HeaderValue::from_static(content_type));
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("public, max-age=3600"),
    );
    response
}

async fn security_headers(request: axum::extract::Request, next: Next) -> Response {
    let mut response = next.run(request).await;
    apply_security_baseline(response.headers_mut());
    response
}

/// Response-header floor applied to every route. Each header is inserted only
/// when the handler has not already set its own value, so route-specific
/// hardening (e.g. the upload route's stricter `sandbox` CSP) is preserved while
/// every other response still inherits the baseline. Cross-Origin-Resource-Policy
/// is part of the baseline so untrusted-derived bytes cannot be embedded
/// cross-site from any byte-serving route, not just the upload endpoint.
fn apply_security_baseline(headers: &mut HeaderMap) {
    headers
        .entry(header::X_CONTENT_TYPE_OPTIONS)
        .or_insert(HeaderValue::from_static("nosniff"));
    headers
        .entry(header::REFERRER_POLICY)
        .or_insert(HeaderValue::from_static("no-referrer"));
    headers
        .entry(header::X_FRAME_OPTIONS)
        .or_insert(HeaderValue::from_static("DENY"));
    headers
        .entry(HeaderName::from_static("cross-origin-resource-policy"))
        .or_insert(HeaderValue::from_static("same-site"));
    headers
        .entry(HeaderName::from_static("permissions-policy"))
        .or_insert(HeaderValue::from_static(
            "camera=(), microphone=(), geolocation=()",
        ));
    headers
        .entry(header::STRICT_TRANSPORT_SECURITY)
        .or_insert(HeaderValue::from_static(
            "max-age=31536000; includeSubDomains",
        ));
    headers
        .entry(header::CACHE_CONTROL)
        .or_insert(HeaderValue::from_static("no-store"));
    headers
        .entry(header::CONTENT_SECURITY_POLICY)
        .or_insert(HeaderValue::from_static(
            "default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; report-uri /csp-report",
        ));
}

async fn render_page<T: Template + HasNonce + Send + 'static>(
    template: T,
    refresh: Option<&str>,
) -> Response {
    render_page_status(template, refresh, StatusCode::OK).await
}

async fn render_page_status<T: Template + HasNonce + Send + 'static>(
    template: T,
    refresh: Option<&str>,
    status: StatusCode,
) -> Response {
    let nonce = template_nonce(&template);
    let rendered = match tokio::task::spawn_blocking(move || template.render()).await {
        Ok(Ok(value)) => value,
        Ok(Err(error)) => {
            tracing::error!(error = %error, "dashboard template render failed");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Html("The dashboard could not complete this request."),
            )
                .into_response();
        }
        Err(error) => {
            tracing::error!(error = %error, "dashboard template task failed");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Html("The dashboard could not complete this request."),
            )
                .into_response();
        }
    };
    let mut response = (status, Html(rendered)).into_response();
    if let Some(refresh) = refresh
        && let Ok(value) = HeaderValue::from_str(refresh)
    {
        response
            .headers_mut()
            .insert(HeaderName::from_static("refresh"), value);
    }
    let policy = format!(
        "default-src 'none'; script-src 'nonce-{nonce}'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; object-src 'none'; form-action 'self'; frame-ancestors 'none'; report-uri /csp-report"
    );
    if let Ok(value) = HeaderValue::from_str(&policy) {
        response
            .headers_mut()
            .insert(header::CONTENT_SECURITY_POLICY, value);
    }
    response
}

trait HasNonce {
    fn page_nonce(&self) -> &str;
}

fn template_nonce<T: HasNonce>(template: &T) -> String {
    template.page_nonce().to_owned()
}

async fn forbidden(message: &str) -> Response {
    error_page(StatusCode::FORBIDDEN, message).await
}

async fn not_found_response() -> Response {
    error_page(StatusCode::NOT_FOUND, "route or record not found").await
}

async fn not_found() -> Response {
    not_found_response().await
}

async fn error_page(status: StatusCode, message: &str) -> Response {
    let template = ErrorTemplate {
        chrome: PageChrome::anonymous(nonce()),
        status: status.as_u16(),
        message: message.to_owned(),
    };
    render_page_status(template, None, status).await
}

async fn internal_error(error: impl std::fmt::Display) -> Response {
    tracing::error!(error = %error, "dashboard request failed");
    error_page(
        StatusCode::INTERNAL_SERVER_ERROR,
        "The dashboard could not complete this request.",
    )
    .await
}

fn chrome(authenticated: &Authenticated) -> PageChrome {
    PageChrome {
        authenticated: true,
        admin: authenticated.principal.role.can_admin(),
        submit: authenticated.principal.role.can_submit(),
        display_name: authenticated.principal.display_name.clone(),
        csrf_token: authenticated.csrf_token.clone(),
        nonce: nonce(),
    }
}

fn nonce() -> String {
    let mut bytes = [0_u8; 32];
    bytes[..16].copy_from_slice(Uuid::new_v4().as_bytes());
    bytes[16..].copy_from_slice(Uuid::new_v4().as_bytes());
    URL_SAFE_NO_PAD.encode(bytes)
}

#[derive(Clone)]
struct PageChrome {
    authenticated: bool,
    admin: bool,
    submit: bool,
    display_name: String,
    csrf_token: String,
    nonce: String,
}

impl PageChrome {
    fn anonymous(nonce: String) -> Self {
        Self {
            authenticated: false,
            admin: false,
            submit: false,
            display_name: String::new(),
            csrf_token: String::new(),
            nonce,
        }
    }
}

macro_rules! impl_nonce {
    ($($name:ty),+ $(,)?) => {$(
        impl HasNonce for $name {
            fn page_nonce(&self) -> &str {
                &self.chrome.nonce
            }
        }
    )+};
}

#[derive(Template)]
#[template(path = "login.html")]
struct LoginTemplate {
    chrome: PageChrome,
    login_csrf: String,
    username_max: usize,
    password_max: usize,
    error: String,
}

#[derive(Template)]
#[template(path = "index.html")]
struct IndexTemplate {
    chrome: PageChrome,
    requests: Vec<RequestSummary>,
}

#[derive(Template)]
#[template(path = "new.html")]
struct NewTemplate {
    chrome: PageChrome,
    request_max: usize,
    request_required: bool,
    upload_accept: &'static str,
    request_body: String,
    error: String,
}

#[derive(Template)]
#[template(path = "receipt.html")]
struct ReceiptTemplate {
    chrome: PageChrome,
    request_id: Uuid,
    inserted: bool,
    status: String,
}

#[derive(Clone)]
struct EventView {
    id: i64,
    event_type: String,
    to_state: String,
    payload: String,
    occurred_at: String,
    actor: String,
    duration: String,
    elapsed: String,
    current: bool,
}

#[derive(Clone)]
struct PullView {
    number: i32,
    state_text: String,
    ci_state: String,
    review_state: String,
    safe_url: String,
}

#[derive(Clone)]
struct ArtifactView {
    run_id: Uuid,
    name: String,
    kind: String,
    created_at: String,
}

#[derive(Clone)]
struct UploadView {
    id: Uuid,
    kind: String,
    created_at: String,
}

#[derive(Template)]
#[template(path = "detail.html")]
struct DetailTemplate {
    chrome: PageChrome,
    request: RequestRecord,
    runs: Vec<RunRecord>,
    events: Vec<EventView>,
    pulls: Vec<PullView>,
    artifacts: Vec<ArtifactView>,
    uploads: Vec<UploadView>,
    terminal: bool,
    last_event_id: i64,
}

#[derive(Template)]
#[template(path = "decisions.html")]
struct DecisionsTemplate {
    chrome: PageChrome,
    decision_html: String,
}

#[derive(Template)]
#[template(path = "bench.html")]
struct BenchTemplate {
    chrome: PageChrome,
    bench: Bench,
}

#[derive(Template)]
#[template(path = "schema.html")]
struct SchemaTemplate {
    chrome: PageChrome,
    catalog: SchemaCatalog,
}

#[derive(Template)]
#[template(path = "model.html")]
struct ModelTemplate {
    chrome: PageChrome,
    model_version: String,
    stages: Vec<ModelStage>,
    runs: Vec<ActiveRun>,
    has_runs: bool,
}

#[derive(Clone)]
struct CodebaseRoleView {
    role: String,
    description_html: String,
    code: u64,
    comments: u64,
    blanks: u64,
    files: u64,
    languages: Vec<LanguageMetrics>,
}

#[derive(Template)]
#[template(path = "codebase.html")]
struct CodebaseTemplate {
    chrome: PageChrome,
    metrics: CodebaseMetrics,
    revision: String,
    roles: Vec<CodebaseRoleView>,
}

#[derive(Template)]
#[template(path = "error.html")]
struct ErrorTemplate {
    chrome: PageChrome,
    status: u16,
    message: String,
}

impl_nonce!(
    LoginTemplate,
    IndexTemplate,
    NewTemplate,
    ReceiptTemplate,
    DetailTemplate,
    DecisionsTemplate,
    BenchTemplate,
    SchemaTemplate,
    ModelTemplate,
    CodebaseTemplate,
    ErrorTemplate,
);

#[derive(Debug, Serialize)]
struct EventFrame {
    id: i64,
    request_id: Uuid,
    run_id: Option<Uuid>,
    event_type: String,
    to_state: Option<String>,
    payload: serde_json::Value,
    occurred_at: String,
    actor: String,
    terminal: bool,
}

impl EventFrame {
    fn from_record(event: &EventRecord, actors: &BTreeMap<String, String>) -> Self {
        Self {
            id: event.id,
            request_id: event.request_id,
            run_id: event.run_id,
            event_type: event.event_type.clone(),
            to_state: event.to_state.clone(),
            payload: event.payload.clone(),
            occurred_at: event.occurred_at.to_string(),
            actor: actor_for_event(event, actors),
            terminal: event
                .to_state
                .as_deref()
                .is_some_and(|state| TERMINAL_STATES.contains(&state)),
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("dashboard projection failed: {0}")]
    Projection(#[from] projection::ProjectionError),
    #[error("dashboard auth setup failed: {0}")]
    Auth(#[from] factory_core::auth::AuthError),
    #[error("dashboard startup task failed: {0}")]
    Join(#[from] tokio::task::JoinError),
    #[error("dashboard upload storage failed: {0}")]
    Upload(#[from] UploadError),
}

#[cfg(test)]
mod tests {
    use std::{collections::BTreeMap, path::PathBuf};

    use factory_core::{REQUEST_BODY_MAX_UTF16_CODE_UNITS, auth::hash_password};

    use super::{AppState, DashboardStore, NewTemplate, PageChrome, Template, UPLOAD_ACCEPT};

    #[test]
    fn security_baseline_sets_corp_and_never_overrides_route_headers() {
        use axum::http::{
            HeaderMap, HeaderValue,
            header::{self, HeaderName},
        };

        // A response that sets none of its own headers inherits the full
        // baseline, including Cross-Origin-Resource-Policy: same-site.
        let mut headers = HeaderMap::new();
        super::apply_security_baseline(&mut headers);
        assert_eq!(
            headers
                .get("cross-origin-resource-policy")
                .and_then(|value| value.to_str().ok()),
            Some("same-site")
        );
        assert_eq!(
            headers
                .get(header::X_CONTENT_TYPE_OPTIONS)
                .and_then(|value| value.to_str().ok()),
            Some("nosniff")
        );

        // A route that sets its own value keeps it: the baseline uses or_insert
        // and never overrides, which is what lets the upload route ship a
        // stricter sandbox CSP and its own CORP value.
        let mut explicit = HeaderMap::new();
        explicit.insert(
            HeaderName::from_static("cross-origin-resource-policy"),
            HeaderValue::from_static("same-origin"),
        );
        explicit.insert(
            header::CONTENT_SECURITY_POLICY,
            HeaderValue::from_static("sandbox; default-src 'none'"),
        );
        super::apply_security_baseline(&mut explicit);
        assert_eq!(
            explicit
                .get("cross-origin-resource-policy")
                .and_then(|value| value.to_str().ok()),
            Some("same-origin")
        );
        assert_eq!(
            explicit
                .get(header::CONTENT_SECURITY_POLICY)
                .and_then(|value| value.to_str().ok()),
            Some("sandbox; default-src 'none'")
        );
    }

    #[test]
    fn form_constraints_are_projected_from_factory_core() {
        let rendered = NewTemplate {
            chrome: PageChrome::anonymous("nonce".to_owned()),
            request_max: REQUEST_BODY_MAX_UTF16_CODE_UNITS,
            request_required: true,
            upload_accept: UPLOAD_ACCEPT,
            request_body: String::new(),
            error: String::new(),
        }
        .render()
        .expect("template");
        assert!(rendered.contains(&format!(
            "maxlength=\"{REQUEST_BODY_MAX_UTF16_CODE_UNITS}\" required"
        )));
    }

    #[test]
    fn askama_escapes_hostile_request_text() {
        let rendered = NewTemplate {
            chrome: PageChrome::anonymous("nonce".to_owned()),
            request_max: REQUEST_BODY_MAX_UTF16_CODE_UNITS,
            request_required: true,
            upload_accept: UPLOAD_ACCEPT,
            request_body: "<script>alert(1)</script><a href=\"https://evil.invalid\">review</a>"
                .to_owned(),
            error: String::new(),
        }
        .render()
        .expect("template");
        assert!(rendered.contains("&#60;script&#62;"));
        assert!(rendered.contains("&#60;a href=&#34;https://evil.invalid&#34;&#62;"));
        assert!(!rendered.contains("<script>alert"));
        assert!(!rendered.contains("<a href=\"https://evil.invalid\""));
    }

    #[test]
    fn dashboard_has_no_pipeline_or_verifier_dependency() {
        let manifest = include_str!("../Cargo.toml");
        assert!(!manifest.contains("factory-supervisor"));
        assert!(!manifest.contains("factory-verify"));
        let source = include_str!("lib.rs")
            .rsplit_once("#[cfg(test)]\nmod tests")
            .expect("production/test boundary")
            .0;
        for forbidden in [
            "transition_run(",
            "record_triage(",
            "factory_verify",
            "DailyLimits",
            "claim_request(",
        ] {
            assert!(
                !source.contains(forbidden),
                "found forbidden path {forbidden}"
            );
        }
        let store = include_str!("store.rs");
        for forbidden in [
            "UPDATE factory.requests",
            "DELETE FROM factory.requests",
            "INSERT INTO factory.events",
            "UPDATE factory.events",
            "INSERT INTO factory.runs",
            "record_triage",
            "DailyLimits",
        ] {
            assert!(
                !store.contains(forbidden),
                "dashboard store contains forbidden authority {forbidden}"
            );
        }
        assert!(store.contains("INSERT INTO factory.requests"));
        assert!(store.contains("INSERT INTO factory.controls"));
        assert!(store.contains("INSERT INTO factory.reconcile_requests"));
        assert!(source.contains("NewRequest::from_intake"));
    }

    #[allow(dead_code)]
    fn test_state_shape(store: DashboardStore) -> AppState {
        AppState::with_dummy_hash(
            store,
            PathBuf::from("../.."),
            PathBuf::from("/tmp/patchyard-test-artifacts"),
            hash_password("test-dummy-password-long-enough").expect("hash"),
            BTreeMap::new(),
        )
    }
}
