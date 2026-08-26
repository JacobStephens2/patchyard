use std::{error::Error, time::Duration};

use factory_core::{
    RequestBody,
    auth::hash_password,
    state::{FactoryRepository as _, NewRequest, PostgresRepository, Sha256Digest, TraceId},
};
use factory_supervisor::store::{
    ClaimLimits, ControlKind, PgPipelineStore, PipelineStore, PublisherStore, StoreError,
};
use factory_verify::ledger::{self, Provenance, RunClass, RunRecord};
use uuid::Uuid;

fn urls() -> Option<(String, String)> {
    Some((
        std::env::var("FACTORY_TEST_DATABASE_URL").ok()?,
        std::env::var("FACTORY_TEST_ADMIN_DATABASE_URL").ok()?,
    ))
}

fn request(source: &str) -> NewRequest {
    let id = Uuid::new_v4();
    let mut fingerprint = [0_u8; 32];
    fingerprint[..16].copy_from_slice(id.as_bytes());
    NewRequest::new(
        id,
        Sha256Digest::new(fingerprint),
        source,
        RequestBody::parse(format!("supervisor fixture {id}")).expect("request body"),
        TraceId::random(),
    )
    .expect("request")
}

#[tokio::test]
async fn a_request_that_never_progresses_is_retired_instead_of_reclaimed_forever()
-> Result<(), Box<dyn Error>> {
    let Some((runtime_url, admin_url)) = urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let admin = PostgresRepository::connect(&admin_url).await?;
    let store = PgPipelineStore::connect(&runtime_url).await?;
    store
        .set_claiming_state(false, false, "integration-test")
        .await?;
    let stuck = request(&format!("ceiling-{}", Uuid::new_v4()));
    admin.create_request(&stuck).await?;
    let limits = ClaimLimits {
        per_submitter: 10,
        global: 10_000,
        max_claim_attempts: 3,
    };
    let holder = "ceiling-holder";

    // A stage that fails before it writes anything else leaves the claim event
    // as the request's only progress. Each sweep is a billed provider call.
    for attempt in 1..=3 {
        let claim = store
            .claim_specific(stuck.id, holder, Duration::from_secs(60), limits)
            .await?;
        assert_eq!(claim.request_id, stuck.id, "attempt {attempt}");
        store.release_lease(stuck.id, holder).await?;
    }

    // The fourth sweep retires it rather than spending a fourth call. Drive it
    // through the daemon's own path: this row must no longer be a candidate.
    let retired = store
        .claim_next(holder, Duration::from_secs(60), limits)
        .await?;
    assert_ne!(
        retired.map(|claim| claim.request_id),
        Some(stuck.id),
        "an exhausted request must not be claimed"
    );

    let status: String =
        sqlx::query_scalar("SELECT status::text FROM factory.requests WHERE id=$1")
            .bind(stuck.id)
            .fetch_one(admin.pool())
            .await?;
    assert_eq!(status, "failed");
    let abandoned: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM factory.events WHERE request_id=$1 AND event_type='request.abandoned'",
    )
    .bind(stuck.id)
    .fetch_one(admin.pool())
    .await?;
    assert_eq!(abandoned, 1, "the retirement must be on the stream");
    let claims: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM factory.events WHERE request_id=$1 AND event_type='request.claimed'",
    )
    .bind(stuck.id)
    .fetch_one(admin.pool())
    .await?;
    assert_eq!(
        claims, 3,
        "the ceiling bounds attempts, it does not add one"
    );
    Ok(())
}

#[tokio::test]
async fn a_request_under_the_ceiling_is_left_alone_by_the_retire_sweep()
-> Result<(), Box<dyn Error>> {
    let Some((runtime_url, admin_url)) = urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let admin = PostgresRepository::connect(&admin_url).await?;
    let store = PgPipelineStore::connect(&runtime_url).await?;
    store
        .set_claiming_state(false, false, "integration-test")
        .await?;
    let under = request(&format!("under-{}", Uuid::new_v4()));
    admin.create_request(&under).await?;
    let limits = ClaimLimits {
        per_submitter: 10,
        global: 10_000,
        max_claim_attempts: 5,
    };
    let holder = "under-holder";

    // The retire pass runs on every claim and must touch only exhausted rows:
    // a request one short of the ceiling stays claimable and unmarked.
    for _ in 0..4 {
        store
            .claim_specific(under.id, holder, Duration::from_secs(60), limits)
            .await?;
        store.release_lease(under.id, holder).await?;
    }
    let status: String =
        sqlx::query_scalar("SELECT status::text FROM factory.requests WHERE id=$1")
            .bind(under.id)
            .fetch_one(admin.pool())
            .await?;
    assert_eq!(status, "claimed", "four of five attempts is not exhausted");
    let abandoned: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM factory.events WHERE request_id=$1 AND event_type='request.abandoned'",
    )
    .bind(under.id)
    .fetch_one(admin.pool())
    .await?;
    assert_eq!(abandoned, 0);
    Ok(())
}

#[tokio::test]
async fn progress_on_a_request_resets_its_claim_attempts() -> Result<(), Box<dyn Error>> {
    let Some((runtime_url, admin_url)) = urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let admin = PostgresRepository::connect(&admin_url).await?;
    let store = PgPipelineStore::connect(&runtime_url).await?;
    store
        .set_claiming_state(false, false, "integration-test")
        .await?;
    let progressing = request(&format!("reset-{}", Uuid::new_v4()));
    admin.create_request(&progressing).await?;
    let limits = ClaimLimits {
        per_submitter: 10,
        global: 10_000,
        max_claim_attempts: 2,
    };
    let holder = "reset-holder";

    for _ in 0..2 {
        store
            .claim_specific(progressing.id, holder, Duration::from_secs(60), limits)
            .await?;
        store.release_lease(progressing.id, holder).await?;
    }
    // A restart mid-run is not a failing request: any event other than the
    // claim itself is progress, and the count starts again from there.
    sqlx::query(
        "INSERT INTO factory.events (request_id,event_type,trace_id) VALUES ($1,'request.triaged',$2)",
    )
    .bind(progressing.id)
    .bind(progressing.trace_id.as_str())
    .execute(admin.pool())
    .await?;

    store
        .claim_specific(progressing.id, holder, Duration::from_secs(60), limits)
        .await
        .expect("progress must clear the ceiling");
    store.release_lease(progressing.id, holder).await?;
    Ok(())
}

#[tokio::test]
async fn durable_sweep_claims_recovery_limits_and_control_rows() -> Result<(), Box<dyn Error>> {
    let Some((runtime_url, admin_url)) = urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let admin = PostgresRepository::connect(&admin_url).await?;
    let store = PgPipelineStore::connect(&runtime_url).await?;
    store
        .set_claiming_state(false, false, "integration-test")
        .await?;
    let source = format!("daily-limit-{}", Uuid::new_v4());
    let first = request(&source);
    let second = request(&source);
    admin.create_request(&first).await?;
    admin.create_request(&second).await?;
    let limits = ClaimLimits {
        per_submitter: 1,
        global: 10_000,
        max_claim_attempts: 3,
    };
    let claimed = store
        .claim_specific(
            first.id,
            "fixture-holder-a",
            Duration::from_secs(60),
            limits,
        )
        .await?;
    assert!(!claimed.recovered);
    store.release_lease(first.id, "fixture-holder-a").await?;

    // Recovery is row-derived and bypasses new-run admission limits.
    let recovered = store
        .claim_specific(
            first.id,
            "fixture-holder-b",
            Duration::from_secs(60),
            limits,
        )
        .await?;
    assert!(recovered.recovered);
    assert!(recovered.fencing_token > claimed.fencing_token);
    store.release_lease(first.id, "fixture-holder-b").await?;
    assert!(matches!(
        store
            .claim_specific(second.id, "fixture-holder-c", Duration::from_secs(60), limits)
            .await,
        Err(StoreError::SubmitterDailyLimit(actual)) if actual == source
    ));

    let paused_id = store
        .enqueue_control(
            ControlKind::Pause,
            None,
            "integration-test",
            "pause fixture",
        )
        .await?;
    let pending = store.pending_controls(100).await?;
    assert!(pending.iter().any(|control| control.id == paused_id));
    assert!(store.claim_control(paused_id).await?);
    store
        .set_claiming_state(true, false, "integration-test")
        .await?;
    store
        .complete_control(paused_id, true, serde_json::json!({"paused": true}))
        .await?;
    let third = request(&format!("paused-{}", Uuid::new_v4()));
    admin.create_request(&third).await?;
    assert!(matches!(
        store
            .claim_specific(
                third.id,
                "fixture-holder-d",
                Duration::from_secs(60),
                limits
            )
            .await,
        Err(StoreError::ClaimingPaused)
    ));
    let qualification = request(&format!("qualification-{}", Uuid::new_v4()));
    admin.create_request(&qualification).await?;
    assert!(matches!(
        store
            .claim_session14_qualification(
                qualification.id,
                "not-the-session14-holder",
                Duration::from_secs(60),
                limits,
            )
            .await,
        Err(StoreError::InvalidLabel("session 14 qualification holder"))
    ));
    let qualification_claim = store
        .claim_session14_qualification(
            qualification.id,
            "factory-session14-qualification",
            Duration::from_secs(60),
            limits,
        )
        .await?;
    assert_eq!(qualification_claim.request_id, qualification.id);
    store
        .release_lease(qualification.id, "factory-session14-qualification")
        .await?;
    store
        .set_claiming_state(true, true, "integration-test")
        .await?;
    let full_stop = request(&format!("full-stop-{}", Uuid::new_v4()));
    admin.create_request(&full_stop).await?;
    assert!(matches!(
        store
            .claim_session14_qualification(
                full_stop.id,
                "factory-session14-qualification",
                Duration::from_secs(60),
                limits,
            )
            .await,
        Err(StoreError::ClaimingPaused)
    ));
    store
        .set_claiming_state(false, false, "integration-test")
        .await?;

    let resume_id = store
        .enqueue_control(
            ControlKind::Resume,
            None,
            "integration-test",
            "resume fixture",
        )
        .await?;
    assert!(store.claim_control(resume_id).await?);
    store
        .set_claiming_state(false, false, "integration-test")
        .await?;
    store
        .complete_control(resume_id, true, serde_json::json!({"paused": false}))
        .await?;
    let swept = store
        .claim_next("fixture-holder-e", Duration::from_secs(60), limits)
        .await?
        .expect("startup/timer sweep finds a durable queued row without a notification");
    assert_eq!(
        store.load_request(swept.request_id).await?.status,
        "claimed"
    );

    let run_id = Uuid::new_v4();
    let run = ledger::validate(RunRecord {
        id: run_id,
        request_id: swept.request_id,
        run_class: swept.run_class,
        base_sha: "a".repeat(40),
        branch: format!("factory/kill-fixture/{}", run_id.simple()),
        lane: "A".to_owned(),
        skill: "ui.sort-dropdown".to_owned(),
        provenance: fixture_provenance(),
    })?;
    store.append_run(&run).await?;
    let kill_id = store
        .enqueue_control(
            ControlKind::Kill,
            Some(run_id),
            "integration-test",
            "kill fixture",
        )
        .await?;
    assert!(store.claim_control(kill_id).await?);
    // The daemon calls this only after checked worker teardown; this store
    // assertion covers the remaining atomic terminal-event and lease effects.
    assert_eq!(
        store.kill_run(run_id, kill_id, "kill fixture").await?,
        Some(swept.request_id)
    );
    store
        .complete_control(
            kill_id,
            true,
            serde_json::json!({"worker_teardown": "complete"}),
        )
        .await?;
    assert_eq!(store.load_request(swept.request_id).await?.status, "killed");
    let run_state: String = sqlx::query_scalar("SELECT state::text FROM factory.runs WHERE id=$1")
        .bind(run_id)
        .fetch_one(store.pool())
        .await?;
    assert_eq!(run_state, "killed");
    let killed_event: bool = sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM factory.events WHERE run_id=$1 AND event_type='run.killed')",
    )
    .bind(run_id)
    .fetch_one(store.pool())
    .await?;
    assert!(killed_event);
    let lease_released: bool = sqlx::query_scalar(
        "SELECT bool_and(released_at IS NOT NULL) FROM factory.leases WHERE request_id=$1",
    )
    .bind(swept.request_id)
    .fetch_one(store.pool())
    .await?;
    assert!(lease_released);
    store.close().await;
    Ok(())
}

#[tokio::test]
async fn kill_preserves_an_existing_terminal_request_outcome() -> Result<(), Box<dyn Error>> {
    let Some((runtime_url, admin_url)) = urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let admin = PostgresRepository::connect(&admin_url).await?;
    let store = PgPipelineStore::connect(&runtime_url).await?;
    let fixture = request(&format!("closed-request-kill-{}", Uuid::new_v4()));
    admin.create_request(&fixture).await?;
    admin
        .claim_request(
            fixture.id,
            "closed-request-kill-fixture",
            Duration::from_secs(60),
        )
        .await?;
    let run = fixture_run(fixture.id);
    let run_id = run.record().id;
    store.append_run(&run).await?;
    sqlx::query("UPDATE factory.runs SET state='reviewing' WHERE id=$1")
        .bind(run_id)
        .execute(admin.pool())
        .await?;
    assert!(
        admin
            .close_request(fixture.id, Duration::from_secs(90 * 86_400))
            .await?
    );
    let closed_at: time::OffsetDateTime =
        sqlx::query_scalar("SELECT closed_at FROM factory.requests WHERE id=$1")
            .bind(fixture.id)
            .fetch_one(admin.pool())
            .await?;

    let kill_id = store
        .enqueue_control(
            ControlKind::Kill,
            Some(run_id),
            "integration-test",
            "close orphan run",
        )
        .await?;
    assert!(store.claim_control(kill_id).await?);
    assert_eq!(
        store.kill_run(run_id, kill_id, "close orphan run").await?,
        Some(fixture.id)
    );
    store
        .complete_control(kill_id, true, serde_json::json!({"closed_orphan": true}))
        .await?;

    let (request_state, preserved_closed_at): (String, time::OffsetDateTime) =
        sqlx::query_as("SELECT status::text,closed_at FROM factory.requests WHERE id=$1")
            .bind(fixture.id)
            .fetch_one(admin.pool())
            .await?;
    assert_eq!(request_state, "closed");
    assert_eq!(preserved_closed_at, closed_at);
    let run_state: String = sqlx::query_scalar("SELECT state::text FROM factory.runs WHERE id=$1")
        .bind(run_id)
        .fetch_one(store.pool())
        .await?;
    assert_eq!(run_state, "killed");
    store.close().await;
    Ok(())
}

#[tokio::test]
async fn reconcile_queue_recovers_with_a_fenced_claim() -> Result<(), Box<dyn Error>> {
    let Some((runtime_url, admin_url)) = urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let admin = PostgresRepository::connect(&admin_url).await?;
    let store = PgPipelineStore::connect(&runtime_url).await?;
    let request = request(&format!("reconcile-queue-{}", Uuid::new_v4()));
    admin.create_request(&request).await?;
    let user_id = Uuid::new_v4();
    sqlx::query(
        "INSERT INTO factory.users (id,username,display_name,password_hash,role) VALUES ($1,$2,'Reconcile fixture',$3,'factory_admin')",
    )
    .bind(user_id)
    .bind(format!("{user_id}@example.test"))
    .bind(hash_password("reconcile-fixture-password")?)
    .execute(admin.pool())
    .await?;
    let reconcile_id = Uuid::new_v4();
    sqlx::query(
        "INSERT INTO factory.reconcile_requests (id,request_id,requested_by) VALUES ($1,$2,$3)",
    )
    .bind(reconcile_id)
    .bind(request.id)
    .bind(user_id)
    .execute(admin.pool())
    .await?;

    let first = store
        .claim_next_reconcile(Duration::from_secs(30))
        .await?
        .expect("pending refresh claim");
    assert_eq!(first.id, reconcile_id);
    sqlx::query(
        "UPDATE factory.reconcile_requests SET claimed_at=clock_timestamp()-interval '31 seconds' WHERE id=$1",
    )
    .bind(reconcile_id)
    .execute(admin.pool())
    .await?;
    let recovered = store
        .claim_next_reconcile(Duration::from_secs(30))
        .await?
        .expect("abandoned refresh recovery");
    assert_eq!(recovered.id, reconcile_id);
    assert_ne!(recovered.claim_token, first.claim_token);
    assert!(matches!(
        store
            .complete_reconcile(&first, true, serde_json::json!({"stale": true}))
            .await,
        Err(StoreError::ReconcileClaimLost(id)) if id == reconcile_id
    ));
    store
        .complete_reconcile(&recovered, true, serde_json::json!({"bounded": true}))
        .await?;
    let (status, bounded): (String, bool) = sqlx::query_as(
        "SELECT status,(outcome->>'bounded')::boolean FROM factory.reconcile_requests WHERE id=$1",
    )
    .bind(reconcile_id)
    .fetch_one(admin.pool())
    .await?;
    assert_eq!(status, "completed");
    assert!(bounded);
    store.close().await;
    Ok(())
}

#[tokio::test]
async fn publisher_lease_serializes_cap_check_and_creation() -> Result<(), Box<dyn Error>> {
    let Some((runtime_url, admin_url)) = urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let admin = PostgresRepository::connect(&admin_url).await?;
    let store = PgPipelineStore::connect(&runtime_url).await?;
    let first_request = request(&format!("publisher-lease-{}", Uuid::new_v4()));
    let second_request = request(&format!("publisher-lease-{}", Uuid::new_v4()));
    admin.create_request(&first_request).await?;
    admin.create_request(&second_request).await?;
    admin
        .claim_request(
            first_request.id,
            "publisher-fixture-a",
            Duration::from_secs(60),
        )
        .await?;
    admin
        .claim_request(
            second_request.id,
            "publisher-fixture-b",
            Duration::from_secs(60),
        )
        .await?;
    let first_run = fixture_run(first_request.id);
    let second_run = fixture_run(second_request.id);
    store.append_run(&first_run).await?;
    store.append_run(&second_run).await?;
    let resource = "publisher:example-org/fieldbook";
    let first = store
        .acquire_publisher_lease(
            resource,
            first_request.id,
            first_run.record().id,
            "publisher-one",
            Duration::from_secs(60),
        )
        .await?;
    assert!(matches!(
        store
            .acquire_publisher_lease(
                resource,
                second_request.id,
                second_run.record().id,
                "publisher-two",
                Duration::from_secs(60),
            )
            .await,
        Err(StoreError::PublisherLeaseHeld { .. })
    ));
    store.release_publisher_lease(&first).await?;
    let second = store
        .acquire_publisher_lease(
            resource,
            second_request.id,
            second_run.record().id,
            "publisher-two",
            Duration::from_secs(60),
        )
        .await?;
    assert!(second.fencing_token > first.fencing_token);
    store.release_publisher_lease(&second).await?;
    store.close().await;
    Ok(())
}

#[tokio::test]
async fn sweep_skips_ready_for_review_request_and_claims_queued_work() -> Result<(), Box<dyn Error>>
{
    let Some((runtime_url, admin_url)) = urls() else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };
    let admin = PostgresRepository::connect(&admin_url).await?;
    let store = PgPipelineStore::connect(&runtime_url).await?;
    store
        .set_claiming_state(false, false, "integration-test")
        .await?;
    let ready_request = request(&format!("ready-sweep-{}", Uuid::new_v4()));
    let queued_request = request(&format!("queued-sweep-{}", Uuid::new_v4()));
    admin.create_request(&ready_request).await?;
    admin.create_request(&queued_request).await?;
    let limits = ClaimLimits {
        per_submitter: 100,
        global: 10_000,
        max_claim_attempts: 3,
    };
    store
        .claim_specific(
            ready_request.id,
            "ready-holder",
            Duration::from_secs(60),
            limits,
        )
        .await?;
    let ready_run = fixture_run(ready_request.id);
    store.append_run(&ready_run).await?;
    store
        .finish_run(
            ready_request.id,
            ready_run.record().id,
            "ready_for_review",
            "run.ready_for_review",
            serde_json::json!({"pull_request": 244}),
        )
        .await?;
    store
        .release_lease(ready_request.id, "ready-holder")
        .await?;
    store
        .claim_specific(
            queued_request.id,
            "queued-holder",
            Duration::from_secs(60),
            limits,
        )
        .await?;
    store
        .release_lease(queued_request.id, "queued-holder")
        .await?;
    sqlx::query(
        "UPDATE factory.requests SET received_at = CASE id WHEN $1 THEN '1970-01-01 00:00:00+00'::timestamptz ELSE '1970-01-01 00:00:01+00'::timestamptz END WHERE id IN ($1, $2)",
    )
    .bind(ready_request.id)
    .bind(queued_request.id)
    .execute(admin.pool())
    .await?;

    // The request remains claimed for the later evidence lifecycle, but it is
    // terminal for this pipeline and must not starve the next recoverable row.
    // Fixed old timestamps isolate this global sweep from parallel test rows:
    // without the terminal filter the ready request deterministically wins.
    assert_eq!(
        store.load_request(ready_request.id).await?.status,
        "claimed"
    );
    let next = store
        .claim_next("sweep-holder", Duration::from_secs(60), limits)
        .await?
        .expect("queued work remains claimable behind a ready-for-review run");
    assert_eq!(next.request_id, queued_request.id);
    store
        .release_lease(queued_request.id, "sweep-holder")
        .await?;
    store.close().await;
    Ok(())
}

fn fixture_run(request_id: Uuid) -> ledger::ValidatedRunRecord {
    let run_id = Uuid::new_v4();
    ledger::validate(RunRecord {
        id: run_id,
        request_id,
        run_class: RunClass::Production,
        base_sha: "a".repeat(40),
        branch: format!("factory/{request_id}-publisher-lease-{}", run_id.simple()),
        lane: "A".to_owned(),
        skill: "ui.sort-dropdown".to_owned(),
        provenance: fixture_provenance(),
    })
    .expect("valid run")
}

fn fixture_provenance() -> Provenance {
    Provenance {
        model_id: "fixture|high|fixture|none".to_owned(),
        cli_version: "fixture/1".to_owned(),
        harness: "fixture".to_owned(),
        provider: "none".to_owned(),
        effort: "high".to_owned(),
        routing_config_version: "fixture-1".to_owned(),
        model_id_hash: "b".repeat(64),
        cli_version_hash: "c".repeat(64),
        constitution_hash: "d".repeat(64),
        rubric_hash: "e".repeat(64),
        skill_hash: "f".repeat(64),
        prompt_template_hash: "1".repeat(64),
        verifier_binary_hash: "2".repeat(64),
        base_tree_hash: "3".repeat(64),
    }
}
