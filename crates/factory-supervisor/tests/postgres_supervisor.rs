use std::{error::Error, time::Duration};

use factory_core::{
    RequestBody,
    state::{FactoryRepository as _, NewRequest, PostgresRepository, Sha256Digest, TraceId},
};
use factory_supervisor::store::{
    ControlKind, DailyLimits, PgPipelineStore, PipelineStore, PublisherStore, StoreError,
};
use factory_verify::ledger::{self, Provenance, RunRecord};
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
    let limits = DailyLimits {
        per_submitter: 1,
        global: 10_000,
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
    let limits = DailyLimits {
        per_submitter: 100,
        global: 10_000,
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

    // The request remains claimed for the later evidence lifecycle, but it is
    // terminal for this pipeline and must not starve genuinely queued work.
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
