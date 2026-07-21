//! Generated operation sequences against disposable PostgreSQL.

use std::{error::Error, time::Duration};

use factory_core::{
    RequestBody,
    state::{
        FactoryRepository, NewRequest, PostgresRepository, RepositoryError, Sha256Digest, TraceId,
    },
};
use proptest::{
    collection::vec,
    prelude::Just,
    test_runner::{Config, TestCaseError, TestRunner},
};
use sqlx::{PgPool, Row as _};
use uuid::Uuid;

#[derive(Clone, Copy, Debug)]
enum Operation {
    RetryIntake,
    ClaimA,
    ClaimB,
    ExpireLease,
    Close,
}

#[derive(Clone, Debug, Default)]
struct Model {
    claimed_once: bool,
    closed: bool,
    active_holder: Option<&'static str>,
    fencing_token: i64,
    event_count: i64,
}

#[test]
fn generated_sequences_preserve_state_machine_invariants() -> Result<(), Box<dyn Error>> {
    let (Ok(runtime_url), Ok(admin_url)) = (
        std::env::var("FACTORY_TEST_DATABASE_URL"),
        std::env::var("FACTORY_TEST_ADMIN_DATABASE_URL"),
    ) else {
        eprintln!("skipped: disposable PostgreSQL URLs are not set");
        return Ok(());
    };

    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    let operation = proptest::prop_oneof![
        Just(Operation::RetryIntake),
        Just(Operation::ClaimA),
        Just(Operation::ClaimB),
        Just(Operation::ExpireLease),
        Just(Operation::Close),
    ];
    let strategy = vec(operation, 1..40);
    let mut runner = TestRunner::new(Config {
        cases: 64,
        max_shrink_iters: 512,
        ..Config::default()
    });

    runner.run(&strategy, |operations| {
        runtime
            .block_on(run_sequence(&runtime_url, &admin_url, &operations))
            .map_err(|error| TestCaseError::fail(error.to_string()))
    })?;
    Ok(())
}

async fn run_sequence(
    runtime_url: &str,
    admin_url: &str,
    operations: &[Operation],
) -> Result<(), Box<dyn Error>> {
    let repository = PostgresRepository::connect(runtime_url).await?;
    let admin = PgPool::connect(admin_url).await?;
    let id = Uuid::new_v4();
    let mut fingerprint = [0x91; 32];
    fingerprint[..16].copy_from_slice(id.as_bytes());
    let request = NewRequest::new(
        id,
        Sha256Digest::new(fingerprint),
        "proptest",
        RequestBody::parse(format!("generated state sequence {id}"))?,
        TraceId::random(),
    )?;
    assert!(repository.create_request(&request).await?.inserted);
    let mut model = Model {
        event_count: 1,
        ..Model::default()
    };

    for operation in operations {
        match operation {
            Operation::RetryIntake => {
                let retry = repository.create_request(&request).await?;
                assert_eq!(retry.id, request.id);
                assert!(!retry.inserted);
            }
            Operation::ClaimA => {
                apply_claim(&repository, request.id, "seat-a", &mut model).await?;
            }
            Operation::ClaimB => {
                apply_claim(&repository, request.id, "seat-b", &mut model).await?;
            }
            Operation::ExpireLease => {
                sqlx::query(
                    r#"
                    UPDATE factory.leases
                    SET acquired_at = clock_timestamp() - interval '10 minutes',
                        expires_at = clock_timestamp() - interval '1 second'
                    WHERE request_id = $1
                    "#,
                )
                .bind(request.id)
                .execute(&admin)
                .await?;
                model.active_holder = None;
            }
            Operation::Close => {
                let result = repository
                    .close_request(request.id, Duration::from_secs(90 * 86_400))
                    .await?;
                assert_eq!(result, !model.closed);
                if !model.closed {
                    model.closed = true;
                    model.active_holder = None;
                    model.event_count += 1;
                }
            }
        }
        assert_model(&repository, &admin, request.id, &model).await?;
    }
    Ok(())
}

async fn apply_claim(
    repository: &PostgresRepository,
    request_id: Uuid,
    holder: &'static str,
    model: &mut Model,
) -> Result<(), Box<dyn Error>> {
    let result = repository
        .claim_request(request_id, holder, Duration::from_secs(300))
        .await;
    if model.closed {
        assert!(matches!(
            result,
            Err(RepositoryError::TerminalRequest { .. })
        ));
    } else if let Some(active_holder) = model.active_holder {
        if active_holder == holder {
            let claim = result?;
            assert!(claim.idempotent_retry);
            assert_eq!(claim.fencing_token, model.fencing_token);
        } else {
            assert!(matches!(result, Err(RepositoryError::LeaseHeld { .. })));
        }
    } else {
        let claim = result?;
        assert!(!claim.idempotent_retry);
        model.fencing_token += 1;
        assert_eq!(claim.fencing_token, model.fencing_token);
        model.claimed_once = true;
        model.active_holder = Some(holder);
        model.event_count += 1;
    }
    Ok(())
}

async fn assert_model(
    repository: &PostgresRepository,
    admin: &PgPool,
    request_id: Uuid,
    model: &Model,
) -> Result<(), Box<dyn Error>> {
    let snapshot = repository.request_status(request_id).await?;
    let expected_status = if model.closed {
        "closed"
    } else if model.claimed_once {
        "claimed"
    } else {
        "queued"
    };
    assert_eq!(snapshot.status, expected_status);
    assert_eq!(snapshot.event_count, model.event_count);
    assert_eq!(snapshot.active_lease_holder.as_deref(), model.active_holder);
    assert_eq!(
        sqlx::query_scalar::<_, i64>("SELECT count(*) FROM factory.requests WHERE id = $1")
            .bind(request_id)
            .fetch_one(admin)
            .await?,
        1
    );

    let lease = sqlx::query(
        r#"
        SELECT holder, fencing_token,
               released_at IS NULL AND expires_at > clock_timestamp() AS active
        FROM factory.leases WHERE request_id = $1
        "#,
    )
    .bind(request_id)
    .fetch_optional(admin)
    .await?;
    if model.fencing_token == 0 {
        assert!(lease.is_none());
    } else {
        let lease = lease.expect("model expects one durable lease row");
        assert_eq!(
            lease.try_get::<i64, _>("fencing_token")?,
            model.fencing_token
        );
        assert_eq!(
            lease.try_get::<bool, _>("active")?,
            model.active_holder.is_some()
        );
        if let Some(holder) = model.active_holder {
            assert_eq!(lease.try_get::<String, _>("holder")?, holder);
        }
    }
    Ok(())
}
