use std::{error::Error, fs, path::Path, time::Duration};

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
};
use http_body_util::BodyExt as _;
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
    let fingerprint: [u8; 32] = Sha256::digest(request_id.as_bytes()).into();
    sqlx::query(
        "INSERT INTO factory.requests (id,fingerprint,source,body,trace_id) VALUES ($1,$2,'dashboard-route-fixture',$3,$4)",
    )
    .bind(request_id)
    .bind(fingerprint.as_slice())
    .bind(hostile_body)
    .bind(hex::encode(request_id.as_bytes()))
    .execute(&admin)
    .await?;
    sqlx::query(
        "INSERT INTO factory.runs (id,request_id,base_sha,branch,lane,skill) VALUES ($1,$2,$3,$4,'A','fixture')",
    )
    .bind(run_id)
    .bind(request_id)
    .bind("a".repeat(40))
    .bind(format!("factory/{request_id}-route-fixture"))
    .execute(&admin)
    .await?;

    let checkout = fixture_checkout()?;
    let artifacts = tempfile::tempdir()?;
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
    assert!(csp.contains("default-src 'self'"));
    assert!(csp.contains("script-src 'self' 'nonce-"));
    assert!(!csp.contains("'unsafe-inline'"));
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
    let response = call(
        &harness.app,
        Method::GET,
        &format!("/request/{}/events", harness.request_id),
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
            builder = builder.header(header::CONTENT_TYPE, "application/x-www-form-urlencoded");
            Body::from(format!(
                "request_body=route-matrix-{}&csrf_token={}",
                Uuid::new_v4(),
                identity.map_or("missing", |value| &value.csrf)
            ))
        }
        FormKind::Login => {
            builder = builder.header(header::CONTENT_TYPE, "application/x-www-form-urlencoded");
            Body::from("username=fixture%40example.test&password=wrong&csrf_token=missing")
        }
    };
    Ok(app.clone().oneshot(builder.body(body)?).await?)
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
        root.path().join("docs/codebase-metrics.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
            "schema_version": 1,
            "generated_by": "tools/check-codebase.sh",
            "tokei_version": "fixture",
            "source_revision": "fixture",
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
