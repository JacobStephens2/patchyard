use std::{
    error::Error, fs, os::unix::fs::PermissionsExt as _, path::Path, process::Stdio, time::Duration,
};

use axum::{
    body::Body,
    http::{Method, Request, StatusCode, header},
};
use factory_core::auth::{AccountRole, hash_password, verify_password};
use factory_supervisor::store::{DailyLimits, PgPipelineStore, PipelineStore as _, StoreError};
use factory_web::{
    AppState,
    auth::{SESSION_COOKIE, csrf_for_secret, new_secret},
    router,
    store::DashboardStore,
};
use sqlx::{PgPool, postgres::PgListener};
use tokio::{io::AsyncWriteExt as _, process::Command};
use tower::ServiceExt as _;
use uuid::Uuid;

fn urls() -> Option<(String, String, String)> {
    Some((
        std::env::var("FACTORY_TEST_DASHBOARD_DATABASE_URL").ok()?,
        std::env::var("FACTORY_TEST_DATABASE_URL").ok()?,
        std::env::var("FACTORY_TEST_ADMIN_DATABASE_URL").ok()?,
    ))
}

#[tokio::test]
async fn form_notify_claim_and_factoryctl_pause_are_one_durable_path() -> Result<(), Box<dyn Error>>
{
    let Some((dashboard_url, supervisor_url, admin_url)) = urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let admin = PgPool::connect(&admin_url).await?;
    let supervisor = PgPipelineStore::connect(&supervisor_url).await?;
    supervisor
        .set_claiming_state(false, false, "dashboard-e2e-start")
        .await?;
    let (user_id, cookie, csrf) = seed_submitter(&admin).await?;
    let checkout = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("workspace root")
        .to_path_buf();
    let artifact_root = tempfile::tempdir()?;
    let upload_root = artifact_root.path().join("uploads");
    fs::create_dir(&upload_root)?;
    fs::set_permissions(&upload_root, fs::Permissions::from_mode(0o700))?;
    let dashboard = DashboardStore::connect(&dashboard_url).await?;
    let app =
        router(AppState::load(dashboard, checkout, artifact_root.path().to_path_buf()).await?);
    let mut listener = PgListener::connect(&supervisor_url).await?;
    listener.listen("factory_intake").await?;
    listener.listen("factory_control").await?;

    let first_body = format!("dashboard listener fixture {}", Uuid::new_v4());
    let response = submit(&app, &cookie, &csrf, &first_body).await?;
    assert_eq!(response, StatusCode::OK);
    let notification = tokio::time::timeout(Duration::from_secs(1), listener.recv())
        .await
        .expect("intake notification deadline")?;
    assert_eq!(notification.channel(), "factory_intake");
    let first_id: Uuid =
        sqlx::query_scalar("SELECT id FROM factory.requests WHERE source=$1 AND body=$2")
            .bind(format!("dashboard:{user_id}"))
            .bind(&first_body)
            .fetch_one(&admin)
            .await?;
    let claim = supervisor
        .claim_specific(
            first_id,
            "dashboard-e2e-listener",
            Duration::from_secs(60),
            DailyLimits {
                per_submitter: 10_000,
                global: 10_000,
            },
        )
        .await?;
    assert_eq!(claim.request_id, first_id);
    assert_eq!(claim.body, first_body);
    supervisor
        .release_lease(first_id, "dashboard-e2e-listener")
        .await?;

    let actor = format!("factoryctl-e2e-{}", Uuid::new_v4());
    let output = Command::new(env!("CARGO_BIN_EXE_factoryctl"))
        .args([
            "--database-url",
            &supervisor_url,
            "pause",
            "--actor",
            &actor,
            "--reason",
            "integration pause",
        ])
        .output()
        .await?;
    assert!(output.status.success(), "{output:?}");
    let notification = tokio::time::timeout(Duration::from_secs(1), listener.recv())
        .await
        .expect("control notification deadline")?;
    assert_eq!(notification.channel(), "factory_control");
    let control = supervisor
        .pending_controls(1_000)
        .await?
        .into_iter()
        .find(|control| control.requested_by == actor)
        .expect("factoryctl pause control");
    assert!(supervisor.claim_control(control.id).await?);
    supervisor
        .set_claiming_state(true, false, &control.requested_by)
        .await?;
    supervisor
        .complete_control(
            control.id,
            true,
            serde_json::json!({"paused": true, "fixture": true}),
        )
        .await?;

    let second_body = format!("dashboard paused fixture {}", Uuid::new_v4());
    assert_eq!(
        submit(&app, &cookie, &csrf, &second_body).await?,
        StatusCode::OK
    );
    let second_id: Uuid =
        sqlx::query_scalar("SELECT id FROM factory.requests WHERE source=$1 AND body=$2")
            .bind(format!("dashboard:{user_id}"))
            .bind(second_body)
            .fetch_one(&admin)
            .await?;
    assert!(matches!(
        supervisor
            .claim_specific(
                second_id,
                "dashboard-e2e-paused",
                Duration::from_secs(60),
                DailyLimits {
                    per_submitter: 10_000,
                    global: 10_000,
                },
            )
            .await,
        Err(StoreError::ClaimingPaused)
    ));
    supervisor
        .set_claiming_state(false, false, "dashboard-e2e-cleanup")
        .await?;
    listener.unlisten_all().await?;
    supervisor.close().await;
    admin.close().await;
    Ok(())
}

#[tokio::test]
async fn account_disable_enable_and_reset_revoke_sessions_and_audit() -> Result<(), Box<dyn Error>>
{
    let Some((_, _, admin_url)) = urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let admin = PgPool::connect(&admin_url).await?;
    let username = format!("{}@example.test", Uuid::new_v4());
    let initial_password = "account-fixture-initial-password";
    let reset_password = "account-fixture-reset-password";

    let provision = account_command(
        &admin_url,
        [
            "provision",
            "--username",
            &username,
            "--display-name",
            "Account fixture",
            "--role",
            "factory-admin",
        ],
        Some(initial_password),
    )
    .await?;
    assert!(provision.status.success(), "{provision:?}");
    assert!(!String::from_utf8_lossy(&provision.stdout).contains(initial_password));

    let (user_id, password_hash, session_version): (Uuid, String, i64) = sqlx::query_as(
        "SELECT id,password_hash,session_version FROM factory.users WHERE username=$1",
    )
    .bind(&username)
    .fetch_one(&admin)
    .await?;
    assert!(verify_password(initial_password, &password_hash));
    let first_session = seed_account_session(&admin, user_id, session_version).await?;

    let disable = account_command(&admin_url, ["disable", "--username", &username], None).await?;
    assert!(disable.status.success(), "{disable:?}");
    let (enabled, disabled_version): (bool, i64) =
        sqlx::query_as("SELECT enabled,session_version FROM factory.users WHERE id=$1")
            .bind(user_id)
            .fetch_one(&admin)
            .await?;
    assert!(!enabled);
    assert_eq!(disabled_version, session_version + 1);
    assert_session_revoked(&admin, &first_session).await?;

    let enable = account_command(&admin_url, ["enable", "--username", &username], None).await?;
    assert!(enable.status.success(), "{enable:?}");
    let second_session = seed_account_session(&admin, user_id, disabled_version).await?;

    let reset = account_command(
        &admin_url,
        ["reset-password", "--username", &username],
        Some(reset_password),
    )
    .await?;
    assert!(reset.status.success(), "{reset:?}");
    assert!(!String::from_utf8_lossy(&reset.stdout).contains(reset_password));
    let (enabled, reset_hash, reset_version): (bool, String, i64) = sqlx::query_as(
        "SELECT enabled,password_hash,session_version FROM factory.users WHERE id=$1",
    )
    .bind(user_id)
    .fetch_one(&admin)
    .await?;
    assert!(enabled);
    assert_eq!(reset_version, disabled_version + 1);
    assert!(verify_password(reset_password, &reset_hash));
    assert!(!verify_password(initial_password, &reset_hash));
    assert_session_revoked(&admin, &second_session).await?;

    let actions: Vec<String> =
        sqlx::query_scalar("SELECT action FROM factory.audit_events WHERE user_id=$1 ORDER BY id")
            .bind(user_id)
            .fetch_all(&admin)
            .await?;
    assert_eq!(
        actions,
        [
            "account.provisioned",
            "account.disabled",
            "account.enabled",
            "account.password_reset"
        ]
    );
    admin.close().await;
    Ok(())
}

async fn account_command<const N: usize>(
    database_url: &str,
    arguments: [&str; N],
    password: Option<&str>,
) -> Result<std::process::Output, Box<dyn Error>> {
    let mut command = Command::new(env!("CARGO_BIN_EXE_factoryctl"));
    command
        .arg("--database-url")
        .arg(database_url)
        .arg("account")
        .args(arguments)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if password.is_some() {
        command.stdin(Stdio::piped());
    } else {
        command.stdin(Stdio::null());
    }
    let mut child = command.spawn()?;
    if let Some(password) = password {
        let mut stdin = child.stdin.take().expect("password stdin");
        stdin.write_all(password.as_bytes()).await?;
        stdin.shutdown().await?;
    }
    Ok(child.wait_with_output().await?)
}

async fn seed_account_session(
    admin: &PgPool,
    user_id: Uuid,
    session_version: i64,
) -> Result<[u8; 32], Box<dyn Error>> {
    let secret = new_secret();
    let csrf = csrf_for_secret(&secret.value);
    sqlx::query(
        r#"
        INSERT INTO factory.sessions (
            token_hash,user_id,csrf_hash,session_version,
            idle_expires_at,absolute_expires_at
        ) VALUES (
            $1,$2,$3,$4,clock_timestamp()+interval '30 minutes',
            clock_timestamp()+interval '8 hours'
        )
        "#,
    )
    .bind(secret.hash.as_slice())
    .bind(user_id)
    .bind(csrf.hash.as_slice())
    .bind(session_version)
    .execute(admin)
    .await?;
    Ok(secret.hash)
}

async fn assert_session_revoked(
    admin: &PgPool,
    token_hash: &[u8; 32],
) -> Result<(), Box<dyn Error>> {
    let revoked: bool = sqlx::query_scalar(
        "SELECT revoked_at IS NOT NULL FROM factory.sessions WHERE token_hash=$1",
    )
    .bind(token_hash.as_slice())
    .fetch_one(admin)
    .await?;
    assert!(revoked);
    Ok(())
}

async fn seed_submitter(admin: &PgPool) -> Result<(Uuid, String, String), Box<dyn Error>> {
    let user_id = Uuid::new_v4();
    let username = format!("{user_id}@example.test");
    sqlx::query(
        "INSERT INTO factory.users (id,username,display_name,password_hash,role) VALUES ($1,$2,'Queue fixture',$3,$4::factory.account_role)",
    )
    .bind(user_id)
    .bind(username)
    .bind(hash_password("queue-fixture-password")?)
    .bind(AccountRole::Submitter.as_str())
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
    Ok((
        user_id,
        format!("{SESSION_COOKIE}={}", secret.value),
        csrf.value,
    ))
}

async fn submit(
    app: &axum::Router,
    cookie: &str,
    csrf: &str,
    body: &str,
) -> Result<StatusCode, Box<dyn Error>> {
    let boundary = format!("patchyard-{}", Uuid::new_v4());
    let multipart = format!(
        "--{boundary}\r\nContent-Disposition: form-data; name=\"csrf_token\"\r\n\r\n{csrf}\r\n\
         --{boundary}\r\nContent-Disposition: form-data; name=\"request_body\"\r\n\r\n{body}\r\n\
         --{boundary}--\r\n"
    );
    let request = Request::builder()
        .method(Method::POST)
        .uri("/new")
        .header(header::COOKIE, cookie)
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={boundary}"),
        )
        .header(header::CONTENT_LENGTH, multipart.len().to_string())
        .body(Body::from(multipart))?;
    Ok(app.clone().oneshot(request).await?.status())
}
