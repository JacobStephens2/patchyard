use std::{
    error::Error, fs, io::Cursor, os::unix::fs::PermissionsExt as _, path::Path, time::Duration,
};

use axum::{
    Router,
    body::Body,
    http::{Method, Request, StatusCode, header},
};
use factory_core::auth::{AccountRole, hash_password};
use factory_web::{
    AppState,
    auth::{LOGIN_COOKIE, SESSION_COOKIE, csrf_for_secret, hash_secret, new_secret},
    router,
    store::{DashboardStore, LOGIN_PAIR_FAILURE_LIMIT},
    upload::MAX_MULTIPART_BYTES,
};
use http_body_util::BodyExt as _;
use image::{DynamicImage, ImageBuffer, ImageFormat, Rgb};
use sha2::{Digest as _, Sha256};
use sqlx::PgPool;
use tempfile::TempDir;
use tower::ServiceExt as _;
use uuid::Uuid;

struct Identity {
    id: Uuid,
    username: String,
    cookie: String,
    csrf: String,
}

struct Harness {
    app: Router,
    admin: PgPool,
    _checkout: TempDir,
    _artifacts: TempDir,
    request_id: Uuid,
    run_id: Uuid,
    evidence_name: String,
}

fn urls() -> Option<(String, String)> {
    Some((
        std::env::var("FACTORY_TEST_DASHBOARD_DATABASE_URL").ok()?,
        std::env::var("FACTORY_TEST_ADMIN_DATABASE_URL").ok()?,
    ))
}

async fn harness(hostile_body: &str) -> Result<Option<Harness>, Box<dyn Error>> {
    let Some((dashboard_url, admin_url)) = urls() else {
        eprintln!("skipped: disposable dashboard PostgreSQL URLs are not set");
        return Ok(None);
    };
    let admin = PgPool::connect(&admin_url).await?;
    let request_id = Uuid::new_v4();
    let run_id = Uuid::new_v4();
    let trace_id = hex::encode(request_id.as_bytes());
    let fingerprint: [u8; 32] = Sha256::digest(request_id.as_bytes()).into();
    sqlx::query(
        "INSERT INTO factory.requests (id,fingerprint,source,body,trace_id) VALUES ($1,$2,'dashboard-route-fixture',$3,$4)",
    )
    .bind(request_id)
    .bind(fingerprint.as_slice())
    .bind(hostile_body)
    .bind(&trace_id)
    .execute(&admin)
    .await?;
    sqlx::query(
        "INSERT INTO factory.events (request_id,event_type,trace_id,payload) VALUES ($1,'request.claimed',$2,'{\"run_class\":\"production\"}'::jsonb)",
    )
    .bind(request_id)
    .bind(&trace_id)
    .execute(&admin)
    .await?;
    sqlx::query(
        "INSERT INTO factory.runs (id,request_id,run_class,base_sha,branch,lane,skill) VALUES ($1,$2,'production',$3,$4,'A','fixture')",
    )
    .bind(run_id)
    .bind(request_id)
    .bind("a".repeat(40))
    .bind(format!("factory/{request_id}-route-fixture"))
    .execute(&admin)
    .await?;

    let checkout = fixture_checkout()?;
    let artifacts = tempfile::tempdir()?;
    let upload_root = artifacts.path().join("uploads");
    fs::create_dir(&upload_root)?;
    fs::set_permissions(&upload_root, fs::Permissions::from_mode(0o700))?;
    let evidence_name = "proof.txt".to_owned();
    let relative = format!("{run_id}/{evidence_name}");
    fs::create_dir_all(artifacts.path().join(run_id.to_string()))?;
    let evidence = b"bounded evidence\n";
    fs::write(artifacts.path().join(&relative), evidence)?;
    let evidence_sha: [u8; 32] = Sha256::digest(evidence).into();
    sqlx::query(
        "INSERT INTO factory.artifacts (id,request_id,run_id,path,sha256,kind) VALUES ($1,$2,$3,$4,$5,'fixture')",
    )
    .bind(Uuid::new_v4())
    .bind(request_id)
    .bind(run_id)
    .bind(relative)
    .bind(evidence_sha.as_slice())
    .execute(&admin)
    .await?;

    let store = DashboardStore::connect(&dashboard_url).await?;
    let state = AppState::load(
        store,
        checkout.path().to_path_buf(),
        artifacts.path().to_path_buf(),
        checkout.path().join("runtime-ideas.md"),
    )
    .await?;
    Ok(Some(Harness {
        app: router(state),
        admin,
        _checkout: checkout,
        _artifacts: artifacts,
        request_id,
        run_id,
        evidence_name,
    }))
}

async fn seed_identity(admin: &PgPool, role: AccountRole) -> Result<Identity, Box<dyn Error>> {
    let user_id = Uuid::new_v4();
    let username = format!("{user_id}@example.test");
    let password_hash = hash_password("fixture-password-long")?;
    sqlx::query(
        "INSERT INTO factory.users (id,username,display_name,password_hash,role) VALUES ($1,$2,$3,$4,$5::factory.account_role)",
    )
    .bind(user_id)
    .bind(&username)
    .bind(format!("Fixture {user_id}"))
    .bind(password_hash)
    .bind(role.as_str())
    .execute(admin)
    .await?;
    let secret = new_secret();
    let csrf = csrf_for_secret(&secret.value);
    sqlx::query(
        r#"
        INSERT INTO factory.sessions (
            token_hash,user_id,csrf_hash,session_version,
            idle_expires_at,absolute_expires_at
        ) VALUES (
            $1,$2,$3,1,clock_timestamp()+interval '30 minutes',
            clock_timestamp()+interval '8 hours'
        )
        "#,
    )
    .bind(secret.hash.as_slice())
    .bind(user_id)
    .bind(csrf.hash.as_slice())
    .execute(admin)
    .await?;
    Ok(Identity {
        id: user_id,
        username,
        cookie: format!("{SESSION_COOKIE}={}", secret.value),
        csrf: csrf.value,
    })
}

struct RouteCase {
    method: Method,
    path: String,
    anonymous: StatusCode,
    submitter: StatusCode,
    admin: StatusCode,
    form: FormKind,
}

#[derive(Clone, Copy)]
enum FormKind {
    None,
    Csrf,
    Submission,
    Login,
}

#[tokio::test]
async fn exact_route_by_role_matrix() -> Result<(), Box<dyn Error>> {
    let Some(harness) = harness("role matrix fixture").await? else {
        return Ok(());
    };
    let submitter = seed_identity(&harness.admin, AccountRole::Submitter).await?;
    let admin = seed_identity(&harness.admin, AccountRole::Admin).await?;
    let request = harness.request_id;
    let run = harness.run_id;
    let evidence = &harness.evidence_name;
    let mut cases = vec![
        route(Method::GET, "/healthz", 200, 200, 200),
        route(Method::POST, "/csp-report", 204, 204, 204),
        route(Method::GET, "/login", 200, 302, 302),
        route(Method::POST, "/login", 403, 403, 403).form(FormKind::Login),
        route(Method::GET, "/", 302, 403, 200),
        route(Method::GET, "/new", 302, 200, 200),
        route(Method::POST, "/new", 302, 200, 200).form(FormKind::Submission),
        route(Method::GET, &format!("/request/{request}"), 302, 403, 200),
        route(
            Method::GET,
            &format!("/request/{request}/events"),
            302,
            403,
            200,
        ),
        route(
            Method::POST,
            &format!("/request/{request}/refresh"),
            302,
            403,
            302,
        )
        .form(FormKind::Csrf),
        route(Method::POST, &format!("/run/{run}/kill"), 302, 403, 302).form(FormKind::Csrf),
        route(Method::POST, "/controls/pause", 302, 403, 302).form(FormKind::Csrf),
        route(Method::POST, "/controls/resume", 302, 403, 302).form(FormKind::Csrf),
        route(Method::POST, "/controls/full-stop", 302, 403, 302).form(FormKind::Csrf),
        route(
            Method::GET,
            &format!("/evidence/{run}/{evidence}"),
            302,
            403,
            200,
        ),
        route(Method::GET, "/decisions", 302, 200, 200),
        route(Method::GET, "/ideas", 302, 403, 200),
        route(Method::GET, "/bench", 302, 403, 200),
        route(Method::GET, "/schema", 302, 403, 200),
        route(Method::GET, "/model", 302, 200, 200),
        route(Method::GET, "/codebase", 302, 200, 200),
        route(Method::GET, "/assets/terminal.css", 200, 200, 200),
        route(Method::GET, "/assets/patchyard-theme.css", 200, 200, 200),
        route(Method::GET, "/projection/factory-model.svg", 302, 200, 200),
        route(Method::GET, "/projection/factory-model.json", 302, 200, 200),
        route(Method::GET, "/projection/factory-model.mmd", 302, 200, 200),
        route(
            Method::GET,
            "/projection/factory-model.schema.json",
            302,
            200,
            200,
        ),
    ];
    // Logout is last because a successful call revokes the role's session.
    cases.push(route(Method::POST, "/logout", 302, 302, 302).form(FormKind::Csrf));

    for case in cases {
        for (label, identity, expected) in [
            ("anonymous", None, case.anonymous),
            ("submitter", Some(&submitter), case.submitter),
            ("admin", Some(&admin), case.admin),
        ] {
            let response = call(
                &harness.app,
                case.method.clone(),
                &case.path,
                identity,
                case.form,
            )
            .await?;
            assert_eq!(
                response.status(),
                expected,
                "{label} {} {}",
                case.method,
                case.path
            );
            drop(response);
        }
    }
    let dashboard_kill: bool = sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM factory.controls WHERE command='kill' AND target_run_id=$1 AND requested_by=$2)",
    )
    .bind(run)
    .bind(&admin.username)
    .fetch_one(&harness.admin)
    .await?;
    assert!(dashboard_kill);
    let audited_actions: Vec<String> = sqlx::query_scalar(
        "SELECT action FROM factory.audit_events WHERE user_id=$1 ORDER BY occurred_at,id",
    )
    .bind(admin.id)
    .fetch_all(&harness.admin)
    .await?;
    assert!(
        audited_actions
            .iter()
            .any(|action| action == "submission.created")
    );
    assert!(
        audited_actions
            .iter()
            .any(|action| action == "control.queued")
    );
    assert!(
        audited_actions
            .iter()
            .any(|action| action == "reconcile.queued")
    );
    Ok(())
}

#[tokio::test]
async fn ideas_is_runtime_backed_and_uses_the_governance_content_filter()
-> Result<(), Box<dyn Error>> {
    let Some(harness) = harness("ideas projection fixture").await? else {
        return Ok(());
    };
    let admin = seed_identity(&harness.admin, AccountRole::Admin).await?;
    let response = call(
        &harness.app,
        Method::GET,
        "/ideas",
        Some(&admin),
        FormKind::None,
    )
    .await?;
    assert_eq!(response.status(), StatusCode::OK);
    let html = String::from_utf8(response.into_body().collect().await?.to_bytes().to_vec())?;
    assert!(html.contains("Runtime ideas"));
    assert!(html.contains("href=\"https://example.test\""));
    assert!(html.contains("pixel"));
    assert!(!html.contains("<script>"));
    assert!(!html.contains("data:image"));
    assert!(!html.contains("<img"));
    Ok(())
}

#[tokio::test]
async fn upload_adversarial_fixtures_fail_closed_and_clean_bytes_serve_inactive()
-> Result<(), Box<dyn Error>> {
    let Some(harness) = harness("upload adversarial harness").await? else {
        return Ok(());
    };
    let valid_png = png_fixture(1, 1);
    let csrf_identity = seed_identity(&harness.admin, AccountRole::Submitter).await?;
    let invalid_csrf = submit_screenshot_with_token(
        &harness.app,
        &csrf_identity,
        "invalid",
        "invalid CSRF upload",
        "screen.png",
        "image/png",
        &valid_png,
    )
    .await?;
    assert_eq!(invalid_csrf.status(), StatusCode::FORBIDDEN);
    let admission_reason: String =
        sqlx::query_scalar("SELECT reason FROM factory.upload_admissions WHERE user_id=$1")
            .bind(csrf_identity.id)
            .fetch_one(&harness.admin)
            .await?;
    assert_eq!(
        admission_reason, "invalid-csrf",
        "quota reservation must close after invalid CSRF"
    );

    let boundary = format!("patchyard-{}", Uuid::new_v4());
    let reordered = format!(
        "--{boundary}\r\nContent-Disposition: form-data; name=\"request_body\"\r\n\r\nrequest first\r\n\
         --{boundary}\r\nContent-Disposition: form-data; name=\"csrf_token\"\r\n\r\n{}\r\n\
         --{boundary}--\r\n",
        csrf_identity.csrf
    );
    let reordered_response = harness
        .app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/new")
                .header(header::COOKIE, &csrf_identity.cookie)
                .header(
                    header::CONTENT_TYPE,
                    format!("multipart/form-data; boundary={boundary}"),
                )
                .header(header::CONTENT_LENGTH, reordered.len().to_string())
                .body(Body::from(reordered))?,
        )
        .await?;
    assert_eq!(
        reordered_response.status(),
        StatusCode::UNPROCESSABLE_ENTITY
    );
    let oversize_response = harness
        .app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/new")
                .header(header::COOKIE, &csrf_identity.cookie)
                .header(
                    header::CONTENT_TYPE,
                    format!("multipart/form-data; boundary={boundary}"),
                )
                .header(
                    header::CONTENT_LENGTH,
                    (MAX_MULTIPART_BYTES + 1).to_string(),
                )
                .body(Body::empty())?,
        )
        .await?;
    assert_eq!(oversize_response.status(), StatusCode::PAYLOAD_TOO_LARGE);

    let oversized_dimensions = png_fixture(4_097, 1);
    let cases: Vec<(&str, &str, &str, Vec<u8>, StatusCode)> = vec![
        (
            "traversal",
            "../../escape.png",
            "image/png",
            valid_png.clone(),
            StatusCode::UNPROCESSABLE_ENTITY,
        ),
        (
            "double-extension",
            "screen.png.php",
            "image/png",
            valid_png.clone(),
            StatusCode::UNPROCESSABLE_ENTITY,
        ),
        (
            "mime-spoof",
            "screen.png",
            "image/png",
            b"PK\x03\x04not-an-image".to_vec(),
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
        ),
        (
            "active-svg",
            "screen.svg",
            "image/svg+xml",
            b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>".to_vec(),
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
        ),
        (
            "executable",
            "screen.bin",
            "application/octet-stream",
            b"\x7fELFnot-an-image".to_vec(),
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
        ),
        (
            "malformed",
            "screen.png",
            "image/png",
            b"\x89PNG\r\n\x1a\nmalformed".to_vec(),
            StatusCode::UNPROCESSABLE_ENTITY,
        ),
        (
            "dimension-bomb",
            "screen.png",
            "image/png",
            oversized_dimensions,
            StatusCode::UNPROCESSABLE_ENTITY,
        ),
    ];
    for (label, filename, content_type, bytes, expected) in cases {
        let identity = seed_identity(&harness.admin, AccountRole::Submitter).await?;
        let response = submit_screenshot(
            &harness.app,
            &identity,
            &format!("upload fixture {label} {}", Uuid::new_v4()),
            filename,
            content_type,
            &bytes,
        )
        .await?;
        assert_eq!(response.status(), expected, "{label}");
    }

    let submitter = seed_identity(&harness.admin, AccountRole::Submitter).await?;
    let admin = seed_identity(&harness.admin, AccountRole::Admin).await?;
    let clean_request = format!("clean upload fixture {}", Uuid::new_v4());
    let mut polyglot = valid_png.clone();
    polyglot.extend_from_slice(b"<script>original bytes must not survive</script>");
    let accepted = submit_screenshot(
        &harness.app,
        &submitter,
        &clean_request,
        "screen.png",
        "text/html",
        &polyglot,
    )
    .await?;
    assert_eq!(accepted.status(), StatusCode::OK);
    let upload_row = sqlx::query(
        r#"
        SELECT artifact.id,artifact.path
        FROM factory.artifacts artifact
        JOIN factory.requests request ON request.id=artifact.request_id
        WHERE request.body=$1 AND artifact.run_id IS NULL
        "#,
    )
    .bind(&clean_request)
    .fetch_one(&harness.admin)
    .await?;
    let upload_id: Uuid = sqlx::Row::try_get(&upload_row, "id")?;
    let stored_path: String = sqlx::Row::try_get(&upload_row, "path")?;
    assert!(!stored_path.contains("screen.png"));
    let stored = fs::read(harness._artifacts.path().join(&stored_path))?;
    assert!(
        !stored
            .windows(b"<script>".len())
            .any(|window| window == b"<script>")
    );
    assert_ne!(stored, polyglot);

    let served = call(
        &harness.app,
        Method::GET,
        &format!("/upload/{upload_id}"),
        Some(&admin),
        FormKind::None,
    )
    .await?;
    assert_eq!(served.status(), StatusCode::OK);
    assert_eq!(
        served
            .headers()
            .get(header::CONTENT_TYPE)
            .and_then(|value| value.to_str().ok()),
        Some("image/png")
    );
    assert_eq!(
        served
            .headers()
            .get(header::X_CONTENT_TYPE_OPTIONS)
            .and_then(|value| value.to_str().ok()),
        Some("nosniff")
    );
    assert_eq!(
        served
            .headers()
            .get(header::CONTENT_SECURITY_POLICY)
            .and_then(|value| value.to_str().ok()),
        Some("sandbox; default-src 'none'")
    );
    assert_eq!(
        served
            .headers()
            .get("cross-origin-resource-policy")
            .and_then(|value| value.to_str().ok()),
        Some("same-site")
    );
    assert!(
        served
            .headers()
            .get(header::CONTENT_DISPOSITION)
            .and_then(|value| value.to_str().ok())
            .is_some_and(|value| value == format!("attachment; filename=\"{upload_id}.png\""))
    );
    let served_bytes = served.into_body().collect().await?.to_bytes();
    assert_eq!(served_bytes.as_ref(), stored.as_slice());
    assert_eq!(
        call(
            &harness.app,
            Method::GET,
            &format!("/upload/{upload_id}"),
            Some(&submitter),
            FormKind::None,
        )
        .await?
        .status(),
        StatusCode::FORBIDDEN
    );

    let duplicate_body = format!("concurrent duplicate fixture {}", Uuid::new_v4());
    let first = submit_screenshot(
        &harness.app,
        &submitter,
        &duplicate_body,
        "screen.png",
        "image/png",
        &valid_png,
    );
    let second = submit_screenshot(
        &harness.app,
        &submitter,
        &duplicate_body,
        "screen.png",
        "image/png",
        &valid_png,
    );
    let (first, second) = tokio::join!(first, second);
    let mut statuses = [first?.status(), second?.status()];
    statuses.sort();
    assert_eq!(statuses, [StatusCode::OK, StatusCode::CONFLICT]);
    let request_count: i64 =
        sqlx::query_scalar("SELECT count(*) FROM factory.requests WHERE source=$1 AND body=$2")
            .bind(format!("dashboard:{}", submitter.id))
            .bind(&duplicate_body)
            .fetch_one(&harness.admin)
            .await?;
    let artifact_count: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM factory.artifacts artifact JOIN factory.requests request ON request.id=artifact.request_id WHERE request.source=$1 AND request.body=$2 AND artifact.run_id IS NULL",
    )
    .bind(format!("dashboard:{}", submitter.id))
    .bind(&duplicate_body)
    .fetch_one(&harness.admin)
    .await?;
    assert_eq!((request_count, artifact_count), (1, 1));

    sqlx::query("UPDATE factory.requests SET status='failed' WHERE source=$1 AND body=$2")
        .bind(format!("dashboard:{}", submitter.id))
        .bind(&duplicate_body)
        .execute(&harness.admin)
        .await?;
    let retry_after_terminal = submit_screenshot(
        &harness.app,
        &submitter,
        &duplicate_body,
        "screen.png",
        "image/png",
        &valid_png,
    )
    .await?;
    assert_eq!(retry_after_terminal.status(), StatusCode::OK);
    let recovered_request_count: i64 =
        sqlx::query_scalar("SELECT count(*) FROM factory.requests WHERE source=$1 AND body=$2")
            .bind(format!("dashboard:{}", submitter.id))
            .bind(&duplicate_body)
            .fetch_one(&harness.admin)
            .await?;
    let recovered_artifact_count: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM factory.artifacts artifact JOIN factory.requests request ON request.id=artifact.request_id WHERE request.source=$1 AND request.body=$2 AND artifact.run_id IS NULL",
    )
    .bind(format!("dashboard:{}", submitter.id))
    .bind(&duplicate_body)
    .fetch_one(&harness.admin)
    .await?;
    assert_eq!((recovered_request_count, recovered_artifact_count), (2, 2));
    Ok(())
}

#[tokio::test]
async fn upload_rate_and_daily_user_quotas_are_transactional() -> Result<(), Box<dyn Error>> {
    let Some(harness) = harness("upload quota harness").await? else {
        return Ok(());
    };
    let rate_identity = seed_identity(&harness.admin, AccountRole::Submitter).await?;
    for attempt in 0..5 {
        let response = call(
            &harness.app,
            Method::POST,
            "/new",
            Some(&rate_identity),
            FormKind::Submission,
        )
        .await?;
        assert_eq!(response.status(), StatusCode::OK, "attempt {attempt}");
    }
    let limited = call(
        &harness.app,
        Method::POST,
        "/new",
        Some(&rate_identity),
        FormKind::Submission,
    )
    .await?;
    assert_eq!(limited.status(), StatusCode::TOO_MANY_REQUESTS);
    let rate_reason: String = sqlx::query_scalar(
        "SELECT reason FROM factory.upload_admissions WHERE user_id=$1 ORDER BY admitted_at DESC,id DESC LIMIT 1",
    )
    .bind(rate_identity.id)
    .fetch_one(&harness.admin)
    .await?;
    assert_eq!(rate_reason, "rate-limit");

    let quota_identity = seed_identity(&harness.admin, AccountRole::Submitter).await?;
    for _ in 0..20 {
        sqlx::query(
            r#"
            INSERT INTO factory.upload_admissions (
                id,user_id,state,content_length,reserved_bytes,
                admitted_at,expires_at
            ) VALUES (
                $1,$2,'admitted',1,1,
                date_trunc('day',clock_timestamp() AT TIME ZONE 'UTC')
                    AT TIME ZONE 'UTC',
                clock_timestamp()+interval '1 hour'
            )
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(quota_identity.id)
        .execute(&harness.admin)
        .await?;
    }
    let quota_limited = call(
        &harness.app,
        Method::POST,
        "/new",
        Some(&quota_identity),
        FormKind::Submission,
    )
    .await?;
    assert_eq!(quota_limited.status(), StatusCode::TOO_MANY_REQUESTS);
    let quota_reason: String = sqlx::query_scalar(
        "SELECT reason FROM factory.upload_admissions WHERE user_id=$1 AND state='rejected' ORDER BY admitted_at DESC,id DESC LIMIT 1",
    )
    .bind(quota_identity.id)
    .fetch_one(&harness.admin)
    .await?;
    assert_eq!(quota_reason, "daily-quota");
    Ok(())
}

#[tokio::test]
async fn hostile_ledger_text_is_inert_and_nonterminal_has_refresh_fallback()
-> Result<(), Box<dyn Error>> {
    let hostile = r#"<script>alert(1)</script><a href="https://phish.invalid">sign in</a>"#;
    let Some(harness) = harness(hostile).await? else {
        return Ok(());
    };
    let admin = seed_identity(&harness.admin, AccountRole::Admin).await?;
    sqlx::query(
        "INSERT INTO factory.events (request_id,run_id,event_type,to_state,trace_id,payload) VALUES ($1,$2,'fixture.event','implementing',$3,$4)",
    )
    .bind(harness.request_id)
    .bind(harness.run_id)
    .bind(hex::encode(Uuid::new_v4().as_bytes()))
    .bind(serde_json::json!({"message": hostile}))
    .execute(&harness.admin)
    .await?;

    let response = call(
        &harness.app,
        Method::GET,
        &format!("/request/{}", harness.request_id),
        Some(&admin),
        FormKind::None,
    )
    .await?;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        response
            .headers()
            .get("refresh")
            .and_then(|v| v.to_str().ok()),
        Some("15")
    );
    let csp = response
        .headers()
        .get(header::CONTENT_SECURITY_POLICY)
        .and_then(|value| value.to_str().ok())
        .expect("CSP");
    assert!(csp.contains("default-src 'none'"));
    assert!(csp.contains("script-src 'nonce-"));
    assert!(!csp.contains("script-src 'self'"));
    assert!(!csp.contains("'unsafe-inline'"));
    assert!(csp.contains("report-uri /csp-report"));
    let html = String::from_utf8(response.into_body().collect().await?.to_bytes().to_vec())?;
    assert!(html.contains("&#60;script&#62;alert(1)&#60;/script&#62;"));
    assert!(html.contains("&#60;a href=&#34;https://phish.invalid&#34;&#62;"));
    assert!(!html.contains("<script>alert(1)</script>"));
    assert!(!html.contains("<a href=\"https://phish.invalid\">sign in</a>"));
    Ok(())
}

#[tokio::test]
async fn notified_event_reaches_sse_frame_within_one_second() -> Result<(), Box<dyn Error>> {
    let Some(harness) = harness("SSE fixture").await? else {
        return Ok(());
    };
    let admin = seed_identity(&harness.admin, AccountRole::Admin).await?;
    let initial_event_id: i64 =
        sqlx::query_scalar("SELECT max(id) FROM factory.events WHERE request_id=$1")
            .bind(harness.request_id)
            .fetch_one(&harness.admin)
            .await?;
    let response = call(
        &harness.app,
        Method::GET,
        &format!(
            "/request/{}/events?after={initial_event_id}",
            harness.request_id
        ),
        Some(&admin),
        FormKind::None,
    )
    .await?;
    assert_eq!(response.status(), StatusCode::OK);
    let mut body = response.into_body();
    let event_id: i64 = sqlx::query_scalar(
        "INSERT INTO factory.events (request_id,run_id,event_type,to_state,trace_id,payload) VALUES ($1,$2,'sse.fixture','implementing',$3,$4) RETURNING id",
    )
    .bind(harness.request_id)
    .bind(harness.run_id)
    .bind(hex::encode(Uuid::new_v4().as_bytes()))
    .bind(serde_json::json!({"message": "<script>inert</script>"}))
    .fetch_one(&harness.admin)
    .await?;
    let frame = tokio::time::timeout(Duration::from_secs(1), body.frame())
        .await
        .expect("SSE frame deadline")
        .expect("SSE response remains open")?;
    let bytes = frame.into_data().expect("SSE data frame");
    let text = String::from_utf8(bytes.to_vec())?;
    assert!(text.contains("event: ledger"));
    assert!(text.contains(&format!("id: {event_id}")));
    assert!(text.contains("\"event_type\":\"sse.fixture\""));
    Ok(())
}

#[tokio::test]
async fn dashboard_database_role_cannot_mutate_state_or_events() -> Result<(), Box<dyn Error>> {
    let Some((dashboard_url, admin_url)) = urls() else {
        eprintln!("skipped: disposable dashboard PostgreSQL URLs are not set");
        return Ok(());
    };
    let dashboard = PgPool::connect(&dashboard_url).await?;
    let admin = PgPool::connect(&admin_url).await?;
    let request_id = Uuid::new_v4();
    let fingerprint: [u8; 32] = Sha256::digest(request_id.as_bytes()).into();
    sqlx::query(
        "INSERT INTO factory.requests (id,fingerprint,source,body,trace_id) VALUES ($1,$2,'dashboard-grant-fixture','grant fixture',$3)",
    )
    .bind(request_id)
    .bind(fingerprint.as_slice())
    .bind(hex::encode(request_id.as_bytes()))
    .execute(&admin)
    .await?;

    for statement in [
        "UPDATE factory.requests SET status='claimed' WHERE false",
        "DELETE FROM factory.requests WHERE false",
        "TRUNCATE factory.requests",
        "INSERT INTO factory.events (request_id,event_type,trace_id) SELECT id,'forbidden',trace_id FROM factory.requests LIMIT 1",
        "UPDATE factory.events SET event_type=event_type WHERE false",
        "DELETE FROM factory.events WHERE false",
        "TRUNCATE factory.events",
        "INSERT INTO factory.runs (id,request_id,base_sha,branch,lane,skill) SELECT gen_random_uuid(),id,repeat('a',40),'forbidden','A','forbidden' FROM factory.requests LIMIT 1",
        "UPDATE factory.runs SET state=state WHERE false",
        "UPDATE factory.artifacts SET kind=kind WHERE false",
        "UPDATE factory.pr_state SET ci_state=ci_state WHERE false",
        "UPDATE factory.leases SET holder=holder WHERE false",
        "UPDATE factory.supervisor_state SET paused=paused WHERE false",
        "UPDATE factory.controls SET status=status WHERE false",
        "DELETE FROM factory.controls WHERE false",
        "UPDATE factory.reconcile_requests SET status=status WHERE false",
        "DELETE FROM factory.reconcile_requests WHERE false",
    ] {
        assert!(
            sqlx::query(statement).execute(&dashboard).await.is_err(),
            "dashboard role unexpectedly allowed {statement}"
        );
    }
    Ok(())
}

#[tokio::test]
async fn login_rotates_sessions_throttles_and_enforces_expiry() -> Result<(), Box<dyn Error>> {
    let Some(harness) = harness("auth hardening fixture").await? else {
        return Ok(());
    };
    let target_id = Uuid::new_v4();
    let username = format!("{target_id}@example.test");
    let password = "auth-fixture-password";
    sqlx::query(
        "INSERT INTO factory.users (id,username,display_name,password_hash,role) VALUES ($1,$2,'Auth fixture',$3,'factory_admin')",
    )
    .bind(target_id)
    .bind(&username)
    .bind(hash_password(password)?)
    .execute(&harness.admin)
    .await?;

    let prior_user = Uuid::new_v4();
    sqlx::query(
        "INSERT INTO factory.users (id,username,display_name,password_hash,role,enabled,disabled_at) VALUES ($1,$2,'Disabled fixture',$3,'factory_submit',false,clock_timestamp())",
    )
    .bind(prior_user)
    .bind(format!("{prior_user}@example.test"))
    .bind(hash_password("disabled-fixture-password")?)
    .execute(&harness.admin)
    .await?;
    let prior = new_secret();
    let prior_csrf = csrf_for_secret(&prior.value);
    sqlx::query(
        r#"
        INSERT INTO factory.sessions (
            token_hash,user_id,csrf_hash,session_version,
            idle_expires_at,absolute_expires_at
        ) VALUES (
            $1,$2,$3,1,clock_timestamp()+interval '30 minutes',
            clock_timestamp()+interval '8 hours'
        )
        "#,
    )
    .bind(prior.hash.as_slice())
    .bind(prior_user)
    .bind(prior_csrf.hash.as_slice())
    .execute(&harness.admin)
    .await?;

    let login_page = harness
        .app
        .clone()
        .oneshot(
            Request::builder()
                .uri("/login")
                .header(header::COOKIE, format!("{SESSION_COOKIE}={}", prior.value))
                .body(Body::empty())?,
        )
        .await?;
    assert_eq!(login_page.status(), StatusCode::OK);
    let challenge_cookie = login_page
        .headers()
        .get_all(header::SET_COOKIE)
        .iter()
        .filter_map(|value| value.to_str().ok())
        .find(|value| value.starts_with(&format!("{LOGIN_COOKIE}=")))
        .expect("login challenge cookie")
        .split(';')
        .next()
        .expect("cookie pair")
        .to_owned();
    let login_html =
        String::from_utf8(login_page.into_body().collect().await?.to_bytes().to_vec())?;
    let csrf_marker = "name=\"csrf_token\" value=\"";
    let csrf_start = login_html.find(csrf_marker).expect("login CSRF") + csrf_marker.len();
    let login_csrf = login_html[csrf_start..]
        .split('"')
        .next()
        .expect("login CSRF value");
    let login = harness
        .app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/login")
                .header(
                    header::COOKIE,
                    format!("{SESSION_COOKIE}={}; {challenge_cookie}", prior.value),
                )
                .header(header::CONTENT_TYPE, "application/x-www-form-urlencoded")
                .body(Body::from(format!(
                    "username={}&password={password}&csrf_token={login_csrf}",
                    username.replace('@', "%40")
                )))?,
        )
        .await?;
    assert_eq!(login.status(), StatusCode::FOUND);
    let session_set_cookie = login
        .headers()
        .get_all(header::SET_COOKIE)
        .iter()
        .filter_map(|value| value.to_str().ok())
        .find(|value| value.starts_with(&format!("{SESSION_COOKIE}=")))
        .expect("rotated session cookie");
    assert!(session_set_cookie.contains("; Secure; HttpOnly; SameSite=Strict"));
    assert!(!session_set_cookie.contains("Domain="));
    let new_session = session_set_cookie
        .split(';')
        .next()
        .and_then(|pair| pair.split_once('='))
        .map(|(_, value)| value)
        .expect("new session value");
    assert_ne!(new_session, prior.value);
    let prior_revoked: bool = sqlx::query_scalar(
        "SELECT revoked_at IS NOT NULL FROM factory.sessions WHERE token_hash=$1",
    )
    .bind(prior.hash.as_slice())
    .fetch_one(&harness.admin)
    .await?;
    assert!(
        prior_revoked,
        "login rotates and revokes a prior session id"
    );
    let login_audited: bool = sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM factory.audit_events WHERE user_id=$1 AND action='login.succeeded')",
    )
    .bind(target_id)
    .fetch_one(&harness.admin)
    .await?;
    assert!(login_audited);

    let dashboard_url = std::env::var("FACTORY_TEST_DASHBOARD_DATABASE_URL")?;
    let store = DashboardStore::connect(&dashboard_url).await?;
    let throttled_username = format!("throttle-{}@example.test", Uuid::new_v4());
    for _ in 0..LOGIN_PAIR_FAILURE_LIMIT {
        store
            .record_login_failure(None, &throttled_username, "192.0.2.44", false)
            .await?;
    }
    assert!(
        store
            .login_is_throttled(&throttled_username, "192.0.2.44")
            .await?
    );
    store.close().await;

    let new_hash = hash_secret(new_session);
    sqlx::query(
        r#"
        UPDATE factory.sessions SET
            created_at=clock_timestamp()-interval '10 hours',
            last_seen_at=clock_timestamp()-interval '9 hours',
            idle_expires_at=clock_timestamp()-interval '8 hours',
            absolute_expires_at=clock_timestamp()-interval '1 hour'
        WHERE token_hash=$1
        "#,
    )
    .bind(new_hash.as_slice())
    .execute(&harness.admin)
    .await?;
    let expired = harness
        .app
        .clone()
        .oneshot(
            Request::builder()
                .uri("/")
                .header(header::COOKIE, format!("{SESSION_COOKIE}={new_session}"))
                .body(Body::empty())?,
        )
        .await?;
    assert_eq!(expired.status(), StatusCode::FOUND);
    assert_eq!(
        expired
            .headers()
            .get(header::LOCATION)
            .and_then(|value| value.to_str().ok()),
        Some("/login")
    );
    Ok(())
}

fn route(method: Method, path: &str, anonymous: u16, submitter: u16, admin: u16) -> RouteCase {
    RouteCase {
        method,
        path: path.to_owned(),
        anonymous: StatusCode::from_u16(anonymous).expect("status"),
        submitter: StatusCode::from_u16(submitter).expect("status"),
        admin: StatusCode::from_u16(admin).expect("status"),
        form: FormKind::None,
    }
}

impl RouteCase {
    fn form(mut self, form: FormKind) -> Self {
        self.form = form;
        self
    }
}

async fn call(
    app: &Router,
    method: Method,
    path: &str,
    identity: Option<&Identity>,
    form: FormKind,
) -> Result<axum::response::Response, Box<dyn Error>> {
    let mut builder = Request::builder().method(method).uri(path);
    if let Some(identity) = identity {
        builder = builder.header(header::COOKIE, &identity.cookie);
    }
    let body = match form {
        FormKind::None => Body::empty(),
        FormKind::Csrf => {
            builder = builder.header(header::CONTENT_TYPE, "application/x-www-form-urlencoded");
            Body::from(format!(
                "csrf_token={}",
                identity.map_or("missing", |value| &value.csrf)
            ))
        }
        FormKind::Submission => {
            let boundary = format!("patchyard-{}", Uuid::new_v4());
            let bytes = multipart_submission(
                &boundary,
                identity.map_or("missing", |value| &value.csrf),
                &format!("route-matrix-{}", Uuid::new_v4()),
                None,
            );
            builder = builder
                .header(
                    header::CONTENT_TYPE,
                    format!("multipart/form-data; boundary={boundary}"),
                )
                .header(header::CONTENT_LENGTH, bytes.len().to_string());
            Body::from(bytes)
        }
        FormKind::Login => {
            builder = builder.header(header::CONTENT_TYPE, "application/x-www-form-urlencoded");
            Body::from("username=fixture%40example.test&password=wrong&csrf_token=missing")
        }
    };
    Ok(app.clone().oneshot(builder.body(body)?).await?)
}

fn multipart_submission(
    boundary: &str,
    csrf: &str,
    request_body: &str,
    screenshot: Option<(&str, &str, &[u8])>,
) -> Vec<u8> {
    let mut body = format!(
        "--{boundary}\r\nContent-Disposition: form-data; name=\"csrf_token\"\r\n\r\n{csrf}\r\n\
         --{boundary}\r\nContent-Disposition: form-data; name=\"request_body\"\r\n\r\n{request_body}\r\n"
    )
    .into_bytes();
    if let Some((filename, content_type, bytes)) = screenshot {
        body.extend_from_slice(
            format!(
                "--{boundary}\r\nContent-Disposition: form-data; name=\"screenshot\"; filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n"
            )
            .as_bytes(),
        );
        body.extend_from_slice(bytes);
        body.extend_from_slice(b"\r\n");
    }
    body.extend_from_slice(format!("--{boundary}--\r\n").as_bytes());
    body
}

async fn submit_screenshot(
    app: &Router,
    identity: &Identity,
    request_body: &str,
    filename: &str,
    content_type: &str,
    screenshot: &[u8],
) -> Result<axum::response::Response, Box<dyn Error>> {
    submit_screenshot_with_token(
        app,
        identity,
        &identity.csrf,
        request_body,
        filename,
        content_type,
        screenshot,
    )
    .await
}

#[allow(clippy::too_many_arguments)]
async fn submit_screenshot_with_token(
    app: &Router,
    identity: &Identity,
    csrf: &str,
    request_body: &str,
    filename: &str,
    content_type: &str,
    screenshot: &[u8],
) -> Result<axum::response::Response, Box<dyn Error>> {
    let boundary = format!("patchyard-{}", Uuid::new_v4());
    let bytes = multipart_submission(
        &boundary,
        csrf,
        request_body,
        Some((filename, content_type, screenshot)),
    );
    let request = Request::builder()
        .method(Method::POST)
        .uri("/new")
        .header(header::COOKIE, &identity.cookie)
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={boundary}"),
        )
        .header(header::CONTENT_LENGTH, bytes.len().to_string())
        .body(Body::from(bytes))?;
    Ok(app.clone().oneshot(request).await?)
}

fn png_fixture(width: u32, height: u32) -> Vec<u8> {
    let image = DynamicImage::ImageRgb8(ImageBuffer::from_pixel(
        width,
        height,
        Rgb([1_u8, 2_u8, 3_u8]),
    ));
    let mut output = Cursor::new(Vec::new());
    image
        .write_to(&mut output, ImageFormat::Png)
        .expect("PNG fixture should encode");
    output.into_inner()
}

fn fixture_checkout() -> Result<TempDir, Box<dyn Error>> {
    let root = tempfile::tempdir()?;
    fs::create_dir_all(root.path().join("docs"))?;
    fs::create_dir_all(root.path().join("model"))?;
    copy_fixture("docs/bench.json", root.path())?;
    copy_fixture("model/factory-model.json", root.path())?;
    copy_fixture("model/factory-model.svg", root.path())?;
    copy_fixture("model/factory-model.mmd", root.path())?;
    copy_fixture("model/factory-model.schema.json", root.path())?;
    fs::write(
        root.path().join("docs/decision-log.md"),
        "| ID | Decision |\n| --- | --- |\n| A53 | scribe |\n",
    )?;
    fs::write(
        root.path().join("runtime-ideas.md"),
        "# Runtime ideas\n\n[safe](https://example.test)\n\n<script>bad()</script>\n\n![pixel](data:image/png;base64,AA==)\n",
    )?;
    fs::write(
        root.path().join("docs/codebase-metrics.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
            "schema_version": 1,
            "generated_by": "tools/check-codebase.sh",
            "tokei_version": "fixture",
            "roles": [
                {
                    "role": "product",
                    "description": "<script>inert</script>",
                    "code": 1,
                    "comments": 0,
                    "blanks": 0,
                    "files": 1,
                    "languages": [
                        {"language": "Rust", "code": 1, "comments": 0, "blanks": 0, "files": 1}
                    ]
                }
            ]
        }))?,
    )?;
    Ok(root)
}

fn copy_fixture(relative: &str, destination: &Path) -> Result<(), Box<dyn Error>> {
    let source = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("workspace root")
        .join(relative);
    let target = destination.join(relative);
    fs::copy(source, target)?;
    Ok(())
}
