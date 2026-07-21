//! Disposable-PostgreSQL acceptance for the Session 2 durability contract.

use std::{error::Error, time::Duration};

use factory_core::{
    RequestBody,
    state::{
        FactoryRepository, NewRequest, PostgresRepository, RepositoryError, Sha256Digest, TraceId,
        TransitionFault,
    },
};
use sqlx::{AssertSqlSafe, Connection as _, Executor as _, PgConnection, PgPool, Row};
use time::OffsetDateTime;
use uuid::Uuid;

fn test_urls() -> Option<(String, String)> {
    let runtime = std::env::var("FACTORY_TEST_DATABASE_URL").ok()?;
    let admin = std::env::var("FACTORY_TEST_ADMIN_DATABASE_URL").ok()?;
    Some((runtime, admin))
}

fn request(seed: u8) -> NewRequest {
    let id = Uuid::new_v4();
    let mut fingerprint = [seed; 32];
    fingerprint[..16].copy_from_slice(id.as_bytes());
    NewRequest::new(
        id,
        Sha256Digest::new(fingerprint),
        "integration-test",
        RequestBody::parse(format!("request fixture {seed} {}", Uuid::new_v4()))
            .expect("valid request body"),
        TraceId::random(),
    )
    .expect("valid request")
}

async fn scalar_i64(pool: &PgPool, sql: &'static str, id: Uuid) -> Result<i64, sqlx::Error> {
    sqlx::query_scalar(sql).bind(id).fetch_one(pool).await
}

#[tokio::test]
async fn queued_transition_faults_and_connection_drop_converge() -> Result<(), Box<dyn Error>> {
    let Some((runtime_url, admin_url)) = test_urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let repository = PostgresRepository::connect(&runtime_url).await?;

    for (seed, fault) in [
        (11, TransitionFault::BeforeStateWrite),
        (12, TransitionFault::AfterStateBeforeEvent),
        (13, TransitionFault::AfterEventBeforeCommit),
        (14, TransitionFault::AfterCommitAcknowledgement),
    ] {
        let fixture = request(seed);
        let failed = repository.create_request_with_fault(&fixture, fault).await;
        assert!(matches!(failed, Err(RepositoryError::InjectedFault(actual)) if actual == fault));

        let retried = repository.create_request(&fixture).await?;
        assert_eq!(retried.id, fixture.id);
        assert_eq!(
            retried.inserted,
            fault != TransitionFault::AfterCommitAcknowledgement,
            "only a killed acknowledgement leaves the first commit durable"
        );
        assert_eq!(
            scalar_i64(
                repository.pool(),
                "SELECT count(*) FROM factory.requests WHERE id = $1",
                fixture.id,
            )
            .await?,
            1
        );
        assert_eq!(
            scalar_i64(
                repository.pool(),
                "SELECT count(*) FROM factory.events WHERE request_id = $1 AND event_type = 'request.queued'",
                fixture.id,
            )
            .await?,
            1
        );
    }

    // Named boundary: terminate the backend after the state row write and
    // before its queue event. PostgreSQL must roll the whole transaction back.
    let dropped = request(15);
    let mut connection = repository.pool().acquire().await?;
    let mut transaction = connection.begin().await?;
    let backend_pid: i32 = sqlx::query_scalar("SELECT pg_backend_pid()")
        .fetch_one(&mut *transaction)
        .await?;
    sqlx::query(
        r#"
        INSERT INTO factory.requests (id, fingerprint, source, body, trace_id)
        VALUES ($1, $2, $3, $4, $5)
        "#,
    )
    .bind(dropped.id)
    .bind(dropped.fingerprint.as_bytes().as_slice())
    .bind(&dropped.source)
    .bind(dropped.body.as_str())
    .bind(dropped.trace_id.as_str())
    .execute(&mut *transaction)
    .await?;
    let mut admin = PgConnection::connect(&admin_url).await?;
    assert!(
        sqlx::query_scalar::<_, bool>("SELECT pg_terminate_backend($1)")
            .bind(backend_pid)
            .fetch_one(&mut admin)
            .await?
    );
    assert!(
        sqlx::query("SELECT 1")
            .execute(&mut *transaction)
            .await
            .is_err()
    );
    drop(transaction);
    drop(connection);

    let retry = repository.create_request(&dropped).await?;
    assert!(retry.inserted);
    assert_eq!(
        scalar_i64(
            repository.pool(),
            "SELECT count(*) FROM factory.events WHERE request_id = $1",
            dropped.id,
        )
        .await?,
        1
    );
    Ok(())
}

#[tokio::test]
async fn lease_expiry_double_claim_and_close_are_idempotent() -> Result<(), Box<dyn Error>> {
    let Some((runtime_url, admin_url)) = test_urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let repository = PostgresRepository::connect(&runtime_url).await?;
    let fixture = request(21);
    repository.create_request(&fixture).await?;

    let first = repository
        .claim_request(fixture.id, "seat-a", Duration::from_secs(300))
        .await?;
    assert_eq!(first.fencing_token, 1);
    assert!(!first.idempotent_retry);

    let same_holder = repository
        .claim_request(fixture.id, "seat-a", Duration::from_secs(300))
        .await?;
    assert!(same_holder.idempotent_retry);
    assert_eq!(same_holder.fencing_token, 1);

    let double_claim = repository
        .claim_request(fixture.id, "seat-b", Duration::from_secs(300))
        .await;
    assert!(matches!(
        double_claim,
        Err(RepositoryError::LeaseHeld { .. })
    ));

    let admin = PgPool::connect(&admin_url).await?;
    sqlx::query(
        "UPDATE factory.leases SET acquired_at = clock_timestamp() - interval '10 minutes', expires_at = clock_timestamp() - interval '1 second' WHERE request_id = $1",
    )
    .bind(fixture.id)
    .execute(&admin)
    .await?;
    let takeover = repository
        .claim_request(fixture.id, "seat-b", Duration::from_secs(300))
        .await?;
    assert_eq!(takeover.fencing_token, 2);
    assert!(!takeover.idempotent_retry);

    assert!(
        repository
            .close_request(fixture.id, Duration::from_secs(90 * 86_400))
            .await?
    );
    assert!(
        !repository
            .close_request(fixture.id, Duration::from_secs(90 * 86_400))
            .await?
    );
    let snapshot = repository.request_status(fixture.id).await?;
    assert_eq!(snapshot.status, "closed");
    assert!(snapshot.active_lease_holder.is_none());
    assert_eq!(snapshot.event_count, 4); // queued, claim, expired takeover, close
    Ok(())
}

#[tokio::test]
async fn claim_and_close_crash_boundaries_roll_back_or_retry() -> Result<(), Box<dyn Error>> {
    let Some((runtime_url, _admin_url)) = test_urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let repository = PostgresRepository::connect(&runtime_url).await?;

    // Named claim boundaries: before write is a no-op; state-before-event and
    // event-before-commit are killed by dropping their transactions.
    for (seed, include_event) in [(31, false), (32, true)] {
        let fixture = request(seed);
        repository.create_request(&fixture).await?;
        let mut transaction = repository.pool().begin().await?;
        let now: OffsetDateTime = sqlx::query_scalar("SELECT clock_timestamp()")
            .fetch_one(&mut *transaction)
            .await?;
        sqlx::query("UPDATE factory.requests SET status = 'claimed' WHERE id = $1")
            .bind(fixture.id)
            .execute(&mut *transaction)
            .await?;
        sqlx::query(
            r#"
            INSERT INTO factory.leases (
                resource, request_id, holder, fencing_token, acquired_at, expires_at
            ) VALUES ($1, $2, 'crashed-seat', 1, $3, $4)
            "#,
        )
        .bind(format!("request:{}", fixture.id))
        .bind(fixture.id)
        .bind(now)
        .bind(now + time::Duration::minutes(5))
        .execute(&mut *transaction)
        .await?;
        if include_event {
            sqlx::query(
                r#"
                INSERT INTO factory.events (
                    request_id, event_type, from_state, to_state, trace_id
                ) VALUES ($1, 'request.claimed', 'queued', 'claimed', $2)
                "#,
            )
            .bind(fixture.id)
            .bind(fixture.trace_id.as_str())
            .execute(&mut *transaction)
            .await?;
        }
        drop(transaction); // simulated kill before commit

        assert_eq!(
            repository.request_status(fixture.id).await?.status,
            "queued"
        );
        repository
            .claim_request(fixture.id, "retry-seat", Duration::from_secs(300))
            .await?;
        assert_eq!(repository.request_status(fixture.id).await?.event_count, 2);
    }

    // Named acknowledgement boundary: a committed claim retried by the same
    // holder is recognized without a second event.
    let acknowledged_claim = request(33);
    repository.create_request(&acknowledged_claim).await?;
    repository
        .claim_request(
            acknowledged_claim.id,
            "retry-seat",
            Duration::from_secs(300),
        )
        .await?;
    let retry = repository
        .claim_request(
            acknowledged_claim.id,
            "retry-seat",
            Duration::from_secs(300),
        )
        .await?;
    assert!(retry.idempotent_retry);
    assert_eq!(
        repository
            .request_status(acknowledged_claim.id)
            .await?
            .event_count,
        2
    );

    // Repeat the state/event/commit boundary proof for close. Each fixture is
    // already claimed before the simulated close begins.
    for (seed, include_event) in [(34, false), (35, true)] {
        let fixture = request(seed);
        repository.create_request(&fixture).await?;
        repository
            .claim_request(fixture.id, "closing-seat", Duration::from_secs(300))
            .await?;
        let mut transaction = repository.pool().begin().await?;
        let now: OffsetDateTime = sqlx::query_scalar("SELECT clock_timestamp()")
            .fetch_one(&mut *transaction)
            .await?;
        sqlx::query("UPDATE factory.requests SET status = 'closed', closed_at = $2 WHERE id = $1")
            .bind(fixture.id)
            .bind(now)
            .execute(&mut *transaction)
            .await?;
        sqlx::query("UPDATE factory.leases SET released_at = $2 WHERE request_id = $1")
            .bind(fixture.id)
            .bind(now)
            .execute(&mut *transaction)
            .await?;
        if include_event {
            sqlx::query(
                r#"
                INSERT INTO factory.events (
                    request_id, event_type, from_state, to_state, trace_id
                ) VALUES ($1, 'request.closed', 'claimed', 'closed', $2)
                "#,
            )
            .bind(fixture.id)
            .bind(fixture.trace_id.as_str())
            .execute(&mut *transaction)
            .await?;
        }
        drop(transaction);

        assert_eq!(
            repository.request_status(fixture.id).await?.status,
            "claimed"
        );
        assert!(
            repository
                .close_request(fixture.id, Duration::from_secs(90 * 86_400))
                .await?
        );
        assert_eq!(repository.request_status(fixture.id).await?.event_count, 3);
    }

    let acknowledged_close = request(36);
    repository.create_request(&acknowledged_close).await?;
    repository
        .claim_request(
            acknowledged_close.id,
            "closing-seat",
            Duration::from_secs(300),
        )
        .await?;
    assert!(
        repository
            .close_request(acknowledged_close.id, Duration::from_secs(90 * 86_400))
            .await?
    );
    assert!(
        !repository
            .close_request(acknowledged_close.id, Duration::from_secs(90 * 86_400))
            .await?
    );
    assert_eq!(
        repository
            .request_status(acknowledged_close.id)
            .await?
            .event_count,
        3
    );
    Ok(())
}

#[tokio::test]
async fn complete_role_matrix_and_grafana_canary_hold() -> Result<(), Box<dyn Error>> {
    let Some((_runtime_url, admin_url)) = test_urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };

    for role in [
        "patchyard_owner",
        "patchyard_migrator",
        "patchyard_supervisor",
        "patchyard_dashboard",
        "patchyard_exporter",
        "grafana_ro",
    ] {
        let row = sqlx::query(
            r#"
            SELECT rolpassword IS NULL AS passwordless,
                   NOT rolsuper AS not_superuser,
                   NOT rolcreatedb AS no_createdb,
                   NOT rolcreaterole AS no_createrole
            FROM pg_catalog.pg_authid WHERE rolname = $1
            "#,
        )
        .bind(role)
        .fetch_one(&PgPool::connect(&admin_url).await?)
        .await?;
        assert!(row.try_get::<bool, _>("passwordless")?, "{role} password");
        assert!(row.try_get::<bool, _>("not_superuser")?, "{role} superuser");
        assert!(row.try_get::<bool, _>("no_createdb")?, "{role} createdb");
        assert!(
            row.try_get::<bool, _>("no_createrole")?,
            "{role} createrole"
        );
    }
    let worker_roles: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM pg_roles WHERE rolname IN ('patchyard_worker', 'factory_worker')",
    )
    .fetch_one(&PgPool::connect(&admin_url).await?)
    .await?;
    assert_eq!(worker_roles, 0);

    let admin = PgPool::connect(&admin_url).await?;
    for role in ["patchyard_dashboard", "patchyard_supervisor"] {
        for table in [
            "requests",
            "runs",
            "events",
            "artifacts",
            "pr_state",
            "leases",
        ] {
            assert!(
                has_table_privilege(&admin, role, table, "SELECT").await?,
                "{role} must read {table}"
            );
            assert!(
                !has_table_privilege(&admin, role, table, "DELETE").await?,
                "{role} must not delete {table}"
            );
            assert!(
                !has_table_privilege(&admin, role, table, "TRUNCATE").await?,
                "{role} must not truncate {table}"
            );
        }
        assert!(
            !has_schema_privilege(&admin, role, "CREATE").await?,
            "{role} must not own DDL"
        );
    }
    for table in ["runs", "events", "artifacts", "pr_state", "leases"] {
        assert!(!has_table_privilege(&admin, "patchyard_dashboard", table, "INSERT").await?);
        assert!(!has_table_privilege(&admin, "patchyard_dashboard", table, "UPDATE").await?);
    }
    let dashboard_insert_columns: Vec<String> = sqlx::query_scalar(
        r#"
        SELECT column_name
        FROM information_schema.column_privileges
        WHERE table_schema = 'factory'
          AND table_name = 'requests'
          AND grantee = 'patchyard_dashboard'
          AND privilege_type = 'INSERT'
        ORDER BY column_name
        "#,
    )
    .fetch_all(&admin)
    .await?;
    assert_eq!(
        dashboard_insert_columns,
        ["body", "fingerprint", "id", "source", "trace_id"]
    );
    let dashboard_updates: i64 = sqlx::query_scalar(
        r#"
        SELECT count(*) FROM information_schema.column_privileges
        WHERE table_schema = 'factory'
          AND grantee = 'patchyard_dashboard'
          AND privilege_type = 'UPDATE'
        "#,
    )
    .fetch_one(&admin)
    .await?;
    assert_eq!(dashboard_updates, 0);

    for table in ["runs", "events", "artifacts", "pr_state", "leases"] {
        assert!(
            has_table_privilege(&admin, "patchyard_supervisor", table, "INSERT").await?,
            "supervisor must insert {table}"
        );
    }
    assert!(!has_table_privilege(&admin, "patchyard_supervisor", "requests", "INSERT").await?);
    assert!(!has_table_privilege(&admin, "patchyard_supervisor", "events", "UPDATE").await?);
    let supervisor_request_insert_columns: Vec<String> = sqlx::query_scalar(
        r#"
        SELECT column_name
        FROM information_schema.column_privileges
        WHERE table_schema = 'factory'
          AND table_name = 'requests'
          AND grantee = 'patchyard_supervisor'
          AND privilege_type = 'INSERT'
        ORDER BY column_name
        "#,
    )
    .fetch_all(&admin)
    .await?;
    assert_eq!(
        supervisor_request_insert_columns,
        ["body", "fingerprint", "id", "source", "trace_id"]
    );

    for statement in [
        "SELECT 1 FROM factory.requests LIMIT 1",
        "SELECT 1 FROM factory.runs LIMIT 1",
        "SELECT 1 FROM factory.events LIMIT 1",
        "SELECT 1 FROM factory.artifacts LIMIT 1",
        "SELECT 1 FROM factory.pr_state LIMIT 1",
        "SELECT 1 FROM factory.leases LIMIT 1",
        "INSERT INTO factory.requests (id, fingerprint, source, body, trace_id) VALUES ('10000000-0000-4000-8000-000000000001', decode(repeat('11', 32), 'hex'), 'dashboard-test', 'dashboard intake', '10000000000000000000000000000001')",
    ] {
        assert!(
            role_statement(&admin_url, "patchyard_dashboard", statement)
                .await
                .is_ok(),
            "dashboard should allow: {statement}"
        );
    }
    for statement in [
        "UPDATE factory.requests SET status = 'claimed' WHERE false",
        "DELETE FROM factory.requests WHERE false",
        "TRUNCATE factory.requests",
        "INSERT INTO factory.events (request_id, event_type, trace_id) SELECT id, 'forbidden', trace_id FROM factory.requests LIMIT 1",
        "UPDATE factory.events SET event_type = event_type WHERE false",
        "DELETE FROM factory.events WHERE false",
        "CREATE TABLE factory.dashboard_escape(id integer)",
    ] {
        assert!(
            role_statement(&admin_url, "patchyard_dashboard", statement)
                .await
                .is_err(),
            "dashboard should reject: {statement}"
        );
    }

    for statement in [
        "SELECT 1 FROM factory.requests LIMIT 1",
        "INSERT INTO factory.requests (id, fingerprint, source, body, trace_id) VALUES ('20000000-0000-4000-8000-000000000001', decode(repeat('e2', 32), 'hex'), 'supervisor-test', 'supervisor intake', '20000000000000000000000000000001')",
        "UPDATE factory.requests SET status = status WHERE false",
        "INSERT INTO factory.events (request_id, event_type, trace_id) SELECT id, 'supervisor.test', trace_id FROM factory.requests LIMIT 1",
    ] {
        assert!(
            role_statement(&admin_url, "patchyard_supervisor", statement)
                .await
                .is_ok(),
            "supervisor should allow: {statement}"
        );
    }
    for statement in [
        "UPDATE factory.events SET event_type = event_type WHERE false",
        "DELETE FROM factory.events WHERE false",
        "TRUNCATE factory.events",
        "CREATE TABLE factory.supervisor_escape(id integer)",
    ] {
        assert!(
            role_statement(&admin_url, "patchyard_supervisor", statement)
                .await
                .is_err(),
            "supervisor should reject: {statement}"
        );
    }

    let canary_id = Uuid::new_v4();
    let run_id = Uuid::new_v4();
    let request_canary = format!("GRAFANA_REQUEST_CANARY_{canary_id}");
    let artifact_canary = format!("GRAFANA_ARTIFACT_CANARY_{canary_id}");
    let mut canary_fingerprint = [41_u8; 32];
    canary_fingerprint[..16].copy_from_slice(canary_id.as_bytes());
    sqlx::query(
        r#"
        INSERT INTO factory.requests (id, fingerprint, source, body, trace_id)
        VALUES ($1, $2, 'canary', $3, '30000000000000000000000000000001')
        "#,
    )
    .bind(canary_id)
    .bind(canary_fingerprint.as_slice())
    .bind(&request_canary)
    .execute(&admin)
    .await?;
    sqlx::query(
        r#"
        INSERT INTO factory.runs (id, request_id, base_sha, branch, lane, skill)
        VALUES ($1, $2, repeat('a', 40), $3, 'A', 'canary-skill')
        "#,
    )
    .bind(run_id)
    .bind(canary_id)
    .bind(format!("canary/{canary_id}"))
    .execute(&admin)
    .await?;
    sqlx::query(
        r#"
        INSERT INTO factory.artifacts (id, request_id, run_id, path, sha256, kind)
        VALUES ($1, $2, $3, $4, $5, 'canary')
        "#,
    )
    .bind(Uuid::new_v4())
    .bind(canary_id)
    .bind(run_id)
    .bind(&artifact_canary)
    .bind([42_u8; 32].as_slice())
    .execute(&admin)
    .await?;

    let view_json = role_query_text(
        &admin_url,
        "grafana_ro",
        r#"
        SELECT jsonb_build_object(
            'requests', COALESCE((SELECT jsonb_agg(to_jsonb(summary)) FROM factory.grafana_request_summary summary), '[]'::jsonb),
            'runs', COALESCE((SELECT jsonb_agg(to_jsonb(metrics)) FROM factory.grafana_run_metrics metrics), '[]'::jsonb)
        )::text
        "#,
    )
    .await?;
    assert!(!view_json.contains(&request_canary));
    assert!(!view_json.contains(&artifact_canary));
    assert!(
        role_statement(
            &admin_url,
            "grafana_ro",
            "SELECT body FROM factory.requests LIMIT 1"
        )
        .await
        .is_err()
    );
    assert!(
        role_statement(
            &admin_url,
            "grafana_ro",
            "SELECT path FROM factory.artifacts LIMIT 1"
        )
        .await
        .is_err()
    );
    let grafana_table_grants: i64 = sqlx::query_scalar(
        r#"
        SELECT count(*)
        FROM information_schema.role_table_grants
        WHERE table_schema = 'factory' AND grantee = 'grafana_ro'
        "#,
    )
    .fetch_one(&admin)
    .await?;
    assert_eq!(
        grafana_table_grants, 0,
        "grafana_ro must have no table grant"
    );

    let provenance: Vec<String> = sqlx::query_scalar(
        r#"
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'factory'
          AND table_name = 'runs'
          AND column_name IN (
              'model_id_hash', 'cli_version_hash', 'constitution_hash', 'rubric_hash',
              'skill_hash', 'prompt_template_hash', 'verifier_binary_hash', 'base_tree_hash'
          )
        ORDER BY column_name
        "#,
    )
    .fetch_all(&admin)
    .await?;
    assert_eq!(provenance.len(), 8);

    assert!(
        sqlx::query(
            "UPDATE factory.events SET event_type = 'mutated' WHERE id = (SELECT min(id) FROM factory.events)",
        )
            .execute(&admin)
            .await
            .is_err(),
        "append-only trigger must reject even an owner/admin mutation"
    );
    Ok(())
}

#[tokio::test]
async fn close_starts_the_artifact_retention_lifecycle() -> Result<(), Box<dyn Error>> {
    let Some((runtime_url, admin_url)) = test_urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let repository = PostgresRepository::connect(&runtime_url).await?;
    let admin = PgPool::connect(&admin_url).await?;
    let fixture = request(71);
    repository.create_request(&fixture).await?;
    let artifact_id = Uuid::new_v4();
    sqlx::query(
        r#"
        INSERT INTO factory.artifacts (id, request_id, path, sha256, kind)
        VALUES ($1, $2, $3, $4, 'retention-test')
        "#,
    )
    .bind(artifact_id)
    .bind(fixture.id)
    .bind(format!("{}/evidence.json", fixture.id))
    .bind([71_u8; 32].as_slice())
    .execute(&admin)
    .await?;

    repository
        .close_request(fixture.id, Duration::from_secs(1))
        .await?;
    let expires_at: Option<OffsetDateTime> =
        sqlx::query_scalar("SELECT expires_at FROM factory.artifacts WHERE id = $1")
            .bind(artifact_id)
            .fetch_one(&admin)
            .await?;
    assert!(expires_at.is_some());
    tokio::time::sleep(Duration::from_millis(1100)).await;
    let now = OffsetDateTime::now_utc();
    let expired = repository.expired_artifacts(now, 100).await?;
    assert!(expired.iter().any(|artifact| artifact.id == artifact_id));
    repository.mark_artifact_deleted(artifact_id, now).await?;
    let deleted_at: Option<OffsetDateTime> =
        sqlx::query_scalar("SELECT deleted_at FROM factory.artifacts WHERE id = $1")
            .bind(artifact_id)
            .fetch_one(&admin)
            .await?;
    assert!(deleted_at.is_some());
    Ok(())
}

async fn has_table_privilege(
    pool: &PgPool,
    role: &str,
    table: &str,
    privilege: &str,
) -> Result<bool, sqlx::Error> {
    sqlx::query_scalar("SELECT has_table_privilege($1, 'factory.' || $2, $3)")
        .bind(role)
        .bind(table)
        .bind(privilege)
        .fetch_one(pool)
        .await
}

async fn has_schema_privilege(
    pool: &PgPool,
    role: &str,
    privilege: &str,
) -> Result<bool, sqlx::Error> {
    sqlx::query_scalar("SELECT has_schema_privilege($1, 'factory', $2)")
        .bind(role)
        .bind(privilege)
        .fetch_one(pool)
        .await
}

async fn role_statement(
    admin_url: &str,
    role: &'static str,
    statement: &'static str,
) -> Result<(), sqlx::Error> {
    let mut connection = PgConnection::connect(admin_url).await?;
    let mut transaction = connection.begin().await?;
    let set_role = match role {
        "patchyard_dashboard" => "SET LOCAL ROLE patchyard_dashboard",
        "patchyard_supervisor" => "SET LOCAL ROLE patchyard_supervisor",
        "grafana_ro" => "SET LOCAL ROLE grafana_ro",
        _ => panic!("test role is not allowlisted"),
    };
    transaction.execute(set_role).await?;
    // Statements are fixed test literals above, not external input.
    let result = transaction.execute(AssertSqlSafe(statement)).await;
    let _ = transaction.rollback().await;
    result.map(|_| ())
}

async fn role_query_text(
    admin_url: &str,
    role: &'static str,
    statement: &'static str,
) -> Result<String, sqlx::Error> {
    let mut connection = PgConnection::connect(admin_url).await?;
    let mut transaction = connection.begin().await?;
    match role {
        "grafana_ro" => transaction.execute("SET LOCAL ROLE grafana_ro").await?,
        _ => panic!("test role is not allowlisted"),
    };
    let value: String = sqlx::query_scalar(AssertSqlSafe(statement))
        .fetch_one(&mut *transaction)
        .await?;
    transaction.rollback().await?;
    Ok(value)
}
