//! PostgreSQL-backed state repository and domain operations.
//!
//! Callers depend on [`FactoryRepository`], not SQL. PostgreSQL is the only
//! phase-1 implementation; this boundary is about domain ownership, not
//! engine portability.

use std::{
    path::{Component, Path, PathBuf},
    time::Duration,
};

use sha2::{Digest as _, Sha256};
use sqlx::{PgPool, Postgres, Row, Transaction, postgres::PgPoolOptions};
use thiserror::Error;
use time::OffsetDateTime;
use uuid::Uuid;

use crate::{
    RequestBody, RequestBodyError,
    plan::{
        PlanAction, PlanDecision, PlanError, PlanTransition, PlanTransitionKind, transition_for,
    },
    triage::{Classification, Lane, Rubric, TaskSpec, TriageError, TriageOutput},
};

const PLAN_CLOSE_RETENTION: Duration = Duration::from_secs(90 * 86_400);

/// A validated W3C trace identifier carried by every queued row and event.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TraceId(String);

impl TraceId {
    /// Construct a non-zero, lower-hex, 16-byte W3C trace identifier.
    #[must_use]
    pub fn random() -> Self {
        Self(Uuid::new_v4().simple().to_string())
    }

    /// Validate a trace identifier supplied by a caller.
    pub fn parse(value: impl Into<String>) -> Result<Self, DomainInputError> {
        let value = value.into();
        if value.len() != 32
            || !value
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
            || value.bytes().all(|byte| byte == b'0')
        {
            return Err(DomainInputError::InvalidTraceId);
        }
        Ok(Self(value))
    }

    /// Borrow the canonical lower-hex representation.
    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// A SHA-256 value in its canonical 32-byte database representation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Sha256Digest([u8; 32]);

impl Sha256Digest {
    /// Wrap an already computed SHA-256 digest.
    #[must_use]
    pub const fn new(bytes: [u8; 32]) -> Self {
        Self(bytes)
    }

    /// Parse a 64-character hexadecimal SHA-256 value.
    pub fn from_hex(value: &str) -> Result<Self, DomainInputError> {
        let bytes = hex::decode(value).map_err(|_| DomainInputError::InvalidSha256)?;
        let bytes: [u8; 32] = bytes
            .try_into()
            .map_err(|_| DomainInputError::InvalidSha256)?;
        Ok(Self(bytes))
    }

    /// Borrow the database byte representation.
    #[must_use]
    pub fn as_bytes(&self) -> &[u8; 32] {
        &self.0
    }
}

/// One request accepted by the shared intake parser and ready for persistence.
#[derive(Clone, Debug)]
pub struct NewRequest {
    /// Stable request identifier chosen before the transaction begins.
    pub id: Uuid,
    /// Idempotency fingerprint.
    pub fingerprint: Sha256Digest,
    /// Bounded origin label such as `factoryctl` or `dashboard`.
    pub source: String,
    /// Verbatim body accepted by [`RequestBody::parse`].
    pub body: RequestBody,
    /// Trace identifier propagated to the queue event.
    pub trace_id: TraceId,
}

impl NewRequest {
    /// Construct a request from raw intake through the one canonical parser
    /// and fingerprint algorithm used by `factoryctl` and the dashboard.
    pub fn from_intake(
        id: Uuid,
        source: impl Into<String>,
        raw_body: impl Into<String>,
        trace_id: TraceId,
    ) -> Result<Self, NewRequestError> {
        let source = source.into();
        let body = RequestBody::parse(raw_body.into())?;
        let mut hasher = Sha256::new();
        hasher.update(source.as_bytes());
        hasher.update([0]);
        hasher.update(body.as_str().as_bytes());
        let fingerprint = Sha256Digest::new(hasher.finalize().into());
        Ok(Self::new(id, fingerprint, source, body, trace_id)?)
    }

    /// Construct a request while enforcing domain-level source invariants.
    pub fn new(
        id: Uuid,
        fingerprint: Sha256Digest,
        source: impl Into<String>,
        body: RequestBody,
        trace_id: TraceId,
    ) -> Result<Self, DomainInputError> {
        let source = source.into();
        if source.trim().is_empty() || source.len() > 64 {
            return Err(DomainInputError::InvalidSource);
        }
        Ok(Self {
            id,
            fingerprint,
            source,
            body,
            trace_id,
        })
    }
}

/// Result of an idempotent intake transaction.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RequestCreated {
    /// Canonical ID; on a duplicate live fingerprint this is the original ID.
    pub id: Uuid,
    /// Whether this call inserted the row.
    pub inserted: bool,
}

/// Read model used by the operator status command.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RequestSnapshot {
    pub id: Uuid,
    pub source: String,
    pub trace_id: String,
    pub received_at: OffsetDateTime,
    pub status: String,
    pub closed_at: Option<OffsetDateTime>,
    pub run_count: i64,
    pub event_count: i64,
    pub active_lease_holder: Option<String>,
    pub lease_expires_at: Option<OffsetDateTime>,
}

/// Result of acquiring or renewing a request lease.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LeaseClaim {
    pub request_id: Uuid,
    pub holder: String,
    pub fencing_token: i64,
    pub expires_at: OffsetDateTime,
    pub idempotent_retry: bool,
}

/// One expired artifact selected for safe removal.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ExpiredArtifact {
    pub id: Uuid,
    pub relative_path: PathBuf,
}

/// One idempotent triage result ready for the append-only ledger.
#[derive(Clone, Debug)]
pub struct TriageSubmission {
    pub id: Uuid,
    /// Required for B/C/D and forbidden for A.
    pub plan_id: Option<Uuid>,
    pub output: TriageOutput,
}

/// Durable result of recording one schema-validated triage output.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TriageRecorded {
    pub classification: Classification,
    pub plan_id: Option<Uuid>,
    pub inserted: bool,
}

/// Durable result of a plan-bin decision.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PlanTransitionRecorded {
    pub transition: PlanTransition,
    pub inserted: bool,
}

/// Named transaction boundaries used by the crash-convergence suite.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TransitionFault {
    None,
    BeforeStateWrite,
    AfterStateBeforeEvent,
    AfterEventBeforeCommit,
    AfterCommitAcknowledgement,
}

/// Domain-owned state operations.
pub trait FactoryRepository {
    fn create_request(
        &self,
        request: &NewRequest,
    ) -> impl Future<Output = Result<RequestCreated, RepositoryError>> + Send;

    fn request_status(
        &self,
        request_id: Uuid,
    ) -> impl Future<Output = Result<RequestSnapshot, RepositoryError>> + Send;

    fn claim_request(
        &self,
        request_id: Uuid,
        holder: &str,
        ttl: Duration,
    ) -> impl Future<Output = Result<LeaseClaim, RepositoryError>> + Send;

    fn close_request(
        &self,
        request_id: Uuid,
        retention: Duration,
    ) -> impl Future<Output = Result<bool, RepositoryError>> + Send;

    fn record_triage(
        &self,
        request_id: Uuid,
        submission: &TriageSubmission,
        rubric: &Rubric,
    ) -> impl Future<Output = Result<TriageRecorded, RepositoryError>> + Send;

    fn transition_plan(
        &self,
        request_id: Uuid,
        plan_id: Uuid,
        decision: &PlanDecision,
    ) -> impl Future<Output = Result<PlanTransitionRecorded, RepositoryError>> + Send;

    fn authoritative_implementation_task_spec(
        &self,
        request_id: Uuid,
    ) -> impl Future<Output = Result<Option<TaskSpec>, RepositoryError>> + Send;

    fn expired_artifacts(
        &self,
        now: OffsetDateTime,
        limit: i64,
    ) -> impl Future<Output = Result<Vec<ExpiredArtifact>, RepositoryError>> + Send;

    fn mark_artifact_deleted(
        &self,
        artifact_id: Uuid,
        deleted_at: OffsetDateTime,
    ) -> impl Future<Output = Result<(), RepositoryError>> + Send;
}

/// The supported PostgreSQL implementation of the state repository.
#[derive(Clone, Debug)]
pub struct PostgresRepository {
    pool: PgPool,
}

impl PostgresRepository {
    /// Connect with a small, bounded pool suitable for operator commands.
    pub async fn connect(database_url: &str) -> Result<Self, RepositoryError> {
        let pool = PgPoolOptions::new()
            .max_connections(5)
            .acquire_timeout(Duration::from_secs(10))
            .connect(database_url)
            .await?;
        Ok(Self { pool })
    }

    /// Wrap a pool supplied by a daemon or integration test.
    #[must_use]
    pub fn from_pool(pool: PgPool) -> Self {
        Self { pool }
    }

    /// Borrow the PostgreSQL pool for shared introspection and migration code.
    #[must_use]
    pub fn pool(&self) -> &PgPool {
        &self.pool
    }

    /// Intake with deterministic failure injection at named durability boundaries.
    pub async fn create_request_with_fault(
        &self,
        request: &NewRequest,
        fault: TransitionFault,
    ) -> Result<RequestCreated, RepositoryError> {
        if fault == TransitionFault::BeforeStateWrite {
            return Err(RepositoryError::InjectedFault(fault));
        }

        let mut transaction = self.pool.begin().await?;
        let inserted_id = sqlx::query_scalar::<_, Uuid>(
            r#"
            INSERT INTO factory.requests (id, fingerprint, source, body, trace_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (fingerprint)
                WHERE status IN ('queued', 'claimed', 'plan_bin')
                DO NOTHING
            RETURNING id
            "#,
        )
        .bind(request.id)
        .bind(request.fingerprint.as_bytes().as_slice())
        .bind(&request.source)
        .bind(request.body.as_str())
        .bind(request.trace_id.as_str())
        .fetch_optional(&mut *transaction)
        .await?;

        let inserted = inserted_id.is_some();
        let id = match inserted_id {
            Some(id) => id,
            None => {
                sqlx::query_scalar::<_, Uuid>(
                    "SELECT id FROM factory.requests \
                     WHERE fingerprint = $1 \
                       AND status IN ('queued', 'claimed', 'plan_bin')",
                )
                .bind(request.fingerprint.as_bytes().as_slice())
                .fetch_one(&mut *transaction)
                .await?
            }
        };

        if inserted && fault == TransitionFault::AfterStateBeforeEvent {
            return Err(RepositoryError::InjectedFault(fault));
        }

        if inserted {
            append_event(
                &mut transaction,
                id,
                EventAppend {
                    run_id: None,
                    event_type: "request.queued",
                    from_state: None,
                    to_state: Some("queued"),
                    trace_id: request.trace_id.as_str(),
                    payload: &serde_json::json!({}),
                },
            )
            .await?;
        }

        if inserted && fault == TransitionFault::AfterEventBeforeCommit {
            return Err(RepositoryError::InjectedFault(fault));
        }

        transaction.commit().await?;
        if inserted && fault == TransitionFault::AfterCommitAcknowledgement {
            return Err(RepositoryError::InjectedFault(fault));
        }

        Ok(RequestCreated { id, inserted })
    }

    async fn require_request_for_update(
        transaction: &mut Transaction<'_, Postgres>,
        request_id: Uuid,
    ) -> Result<(String, String), RepositoryError> {
        let row = sqlx::query(
            "SELECT status::text AS status, trace_id FROM factory.requests WHERE id = $1 FOR UPDATE",
        )
        .bind(request_id)
        .fetch_optional(&mut **transaction)
        .await?
        .ok_or(RepositoryError::RequestNotFound(request_id))?;
        Ok((row.try_get("status")?, row.try_get("trace_id")?))
    }
}

impl FactoryRepository for PostgresRepository {
    async fn create_request(
        &self,
        request: &NewRequest,
    ) -> Result<RequestCreated, RepositoryError> {
        self.create_request_with_fault(request, TransitionFault::None)
            .await
    }

    async fn request_status(&self, request_id: Uuid) -> Result<RequestSnapshot, RepositoryError> {
        let row = sqlx::query(
            r#"
            SELECT
                requests.id,
                requests.source,
                requests.trace_id,
                requests.received_at,
                requests.status::text AS status,
                requests.closed_at,
                count(DISTINCT runs.id)::bigint AS run_count,
                count(DISTINCT events.id)::bigint AS event_count,
                max(leases.holder) FILTER (
                    WHERE leases.released_at IS NULL AND leases.expires_at > clock_timestamp()
                ) AS active_lease_holder,
                max(leases.expires_at) FILTER (
                    WHERE leases.released_at IS NULL AND leases.expires_at > clock_timestamp()
                ) AS lease_expires_at
            FROM factory.requests
            LEFT JOIN factory.runs ON runs.request_id = requests.id
            LEFT JOIN factory.events ON events.request_id = requests.id
            LEFT JOIN factory.leases ON leases.request_id = requests.id
            WHERE requests.id = $1
            GROUP BY requests.id
            "#,
        )
        .bind(request_id)
        .fetch_optional(&self.pool)
        .await?
        .ok_or(RepositoryError::RequestNotFound(request_id))?;

        Ok(RequestSnapshot {
            id: row.try_get("id")?,
            source: row.try_get("source")?,
            trace_id: row.try_get("trace_id")?,
            received_at: row.try_get("received_at")?,
            status: row.try_get("status")?,
            closed_at: row.try_get("closed_at")?,
            run_count: row.try_get("run_count")?,
            event_count: row.try_get("event_count")?,
            active_lease_holder: row.try_get("active_lease_holder")?,
            lease_expires_at: row.try_get("lease_expires_at")?,
        })
    }

    async fn claim_request(
        &self,
        request_id: Uuid,
        holder: &str,
        ttl: Duration,
    ) -> Result<LeaseClaim, RepositoryError> {
        if holder.trim().is_empty() || holder.len() > 128 {
            return Err(DomainInputError::InvalidHolder.into());
        }
        let ttl_seconds =
            i64::try_from(ttl.as_secs()).map_err(|_| DomainInputError::InvalidLeaseTtl)?;
        if ttl_seconds <= 0 || ttl_seconds > 86_400 {
            return Err(DomainInputError::InvalidLeaseTtl.into());
        }

        let mut transaction = self.pool.begin().await?;
        let (status, trace_id) =
            Self::require_request_for_update(&mut transaction, request_id).await?;
        if matches!(status.as_str(), "closed" | "failed" | "killed") {
            return Err(RepositoryError::TerminalRequest { request_id, status });
        }
        if status == "plan_bin" {
            return Err(RepositoryError::RequestInPlanBin(request_id));
        }

        let now: OffsetDateTime = sqlx::query_scalar("SELECT clock_timestamp()")
            .fetch_one(&mut *transaction)
            .await?;
        let expires_at = now + time::Duration::seconds(ttl_seconds);
        let resource = format!("request:{request_id}");
        let lease = sqlx::query(
            r#"
            SELECT holder, fencing_token, expires_at, released_at
            FROM factory.leases
            WHERE resource = $1
            FOR UPDATE
            "#,
        )
        .bind(&resource)
        .fetch_optional(&mut *transaction)
        .await?;

        if let Some(lease) = lease {
            let current_holder: String = lease.try_get("holder")?;
            let current_token: i64 = lease.try_get("fencing_token")?;
            let current_expiry: OffsetDateTime = lease.try_get("expires_at")?;
            let released_at: Option<OffsetDateTime> = lease.try_get("released_at")?;
            if released_at.is_none() && current_expiry > now {
                if current_holder != holder {
                    return Err(RepositoryError::LeaseHeld {
                        request_id,
                        holder: current_holder,
                        expires_at: current_expiry,
                    });
                }
                transaction.commit().await?;
                return Ok(LeaseClaim {
                    request_id,
                    holder: holder.to_owned(),
                    fencing_token: current_token,
                    expires_at: current_expiry,
                    idempotent_retry: true,
                });
            }

            let next_token = current_token
                .checked_add(1)
                .ok_or(RepositoryError::FencingTokenExhausted(request_id))?;
            sqlx::query(
                r#"
                UPDATE factory.leases
                SET holder = $2,
                    fencing_token = $3,
                    acquired_at = $4,
                    expires_at = $5,
                    released_at = NULL
                WHERE resource = $1
                "#,
            )
            .bind(&resource)
            .bind(holder)
            .bind(next_token)
            .bind(now)
            .bind(expires_at)
            .execute(&mut *transaction)
            .await?;

            if status != "claimed" {
                sqlx::query("UPDATE factory.requests SET status = 'claimed' WHERE id = $1")
                    .bind(request_id)
                    .execute(&mut *transaction)
                    .await?;
            }
            append_event(
                &mut transaction,
                request_id,
                EventAppend {
                    run_id: None,
                    event_type: "request.claimed",
                    from_state: Some(&status),
                    to_state: Some("claimed"),
                    trace_id: &trace_id,
                    payload: &serde_json::json!({}),
                },
            )
            .await?;
            transaction.commit().await?;
            return Ok(LeaseClaim {
                request_id,
                holder: holder.to_owned(),
                fencing_token: next_token,
                expires_at,
                idempotent_retry: false,
            });
        }

        sqlx::query(
            r#"
            INSERT INTO factory.leases (
                resource, request_id, holder, fencing_token, acquired_at, expires_at
            ) VALUES ($1, $2, $3, 1, $4, $5)
            "#,
        )
        .bind(&resource)
        .bind(request_id)
        .bind(holder)
        .bind(now)
        .bind(expires_at)
        .execute(&mut *transaction)
        .await?;
        if status != "claimed" {
            sqlx::query("UPDATE factory.requests SET status = 'claimed' WHERE id = $1")
                .bind(request_id)
                .execute(&mut *transaction)
                .await?;
        }
        append_event(
            &mut transaction,
            request_id,
            EventAppend {
                run_id: None,
                event_type: "request.claimed",
                from_state: Some(&status),
                to_state: Some("claimed"),
                trace_id: &trace_id,
                payload: &serde_json::json!({}),
            },
        )
        .await?;
        transaction.commit().await?;
        Ok(LeaseClaim {
            request_id,
            holder: holder.to_owned(),
            fencing_token: 1,
            expires_at,
            idempotent_retry: false,
        })
    }

    async fn close_request(
        &self,
        request_id: Uuid,
        retention: Duration,
    ) -> Result<bool, RepositoryError> {
        let retention_seconds =
            i64::try_from(retention.as_secs()).map_err(|_| DomainInputError::InvalidRetention)?;
        if retention_seconds <= 0 {
            return Err(DomainInputError::InvalidRetention.into());
        }

        let mut transaction = self.pool.begin().await?;
        let (status, trace_id) =
            Self::require_request_for_update(&mut transaction, request_id).await?;
        if status == "closed" {
            transaction.commit().await?;
            return Ok(false);
        }
        if status == "plan_bin" {
            return Err(RepositoryError::RequestInPlanBin(request_id));
        }
        if matches!(status.as_str(), "failed" | "killed") {
            return Err(RepositoryError::TerminalRequest { request_id, status });
        }

        let now: OffsetDateTime = sqlx::query_scalar("SELECT clock_timestamp()")
            .fetch_one(&mut *transaction)
            .await?;
        let expires_at = now + time::Duration::seconds(retention_seconds);
        sqlx::query("UPDATE factory.requests SET status = 'closed', closed_at = $2 WHERE id = $1")
            .bind(request_id)
            .bind(now)
            .execute(&mut *transaction)
            .await?;
        sqlx::query(
            "UPDATE factory.leases SET released_at = $2 WHERE request_id = $1 AND released_at IS NULL",
        )
        .bind(request_id)
        .bind(now)
        .execute(&mut *transaction)
        .await?;
        sqlx::query(
            "UPDATE factory.artifacts SET expires_at = COALESCE(expires_at, $2) WHERE request_id = $1",
        )
        .bind(request_id)
        .bind(expires_at)
        .execute(&mut *transaction)
        .await?;
        append_event(
            &mut transaction,
            request_id,
            EventAppend {
                run_id: None,
                event_type: "request.closed",
                from_state: Some(&status),
                to_state: Some("closed"),
                trace_id: &trace_id,
                payload: &serde_json::json!({}),
            },
        )
        .await?;
        transaction.commit().await?;
        Ok(true)
    }

    async fn record_triage(
        &self,
        request_id: Uuid,
        submission: &TriageSubmission,
        rubric: &Rubric,
    ) -> Result<TriageRecorded, RepositoryError> {
        submission.output.validate()?;
        let classification = rubric.classify(&submission.output.task_spec)?;
        match (classification.lane, submission.plan_id) {
            (Lane::A, None) => {}
            (Lane::A, Some(_)) => return Err(RepositoryError::LaneAPlanId),
            (Lane::B | Lane::C | Lane::D, None) => {
                return Err(RepositoryError::PlanIdRequired(classification.lane));
            }
            (Lane::B | Lane::C | Lane::D, Some(_)) => {}
        }

        let task_spec_sha256 = hex::encode(submission.output.task_spec.sha256()?);
        let rubric_sha256 = hex::encode(rubric.source_sha256());
        let triage_payload = serde_json::json!({
            "triage_id": submission.id,
            "plan_id": submission.plan_id,
            "lane": classification.lane,
            "reasons": classification.reasons,
            "confidence_basis_points": submission.output.confidence_basis_points,
            "task_spec_sha256": task_spec_sha256,
            "rubric_sha256": rubric_sha256,
            "task_spec": submission.output.task_spec,
        });

        let mut transaction = self.pool.begin().await?;
        let (status, trace_id) =
            Self::require_request_for_update(&mut transaction, request_id).await?;
        let existing: Option<serde_json::Value> = sqlx::query_scalar(
            r#"
            SELECT payload
            FROM factory.events
            WHERE request_id = $1
              AND event_type = 'triage.classified'
              AND payload->>'triage_id' = $2
            ORDER BY id DESC
            LIMIT 1
            "#,
        )
        .bind(request_id)
        .bind(submission.id.to_string())
        .fetch_optional(&mut *transaction)
        .await?;
        if let Some(existing) = existing {
            if existing != triage_payload {
                return Err(RepositoryError::TriageIdConflict(submission.id));
            }
            transaction.commit().await?;
            return Ok(TriageRecorded {
                classification,
                plan_id: submission.plan_id,
                inserted: false,
            });
        }
        if status != "claimed" {
            return Err(RepositoryError::UnexpectedRequestStatus {
                request_id,
                expected: "claimed",
                actual: status,
            });
        }

        let triage_target = if classification.lane == Lane::A {
            "implement"
        } else {
            "plan_bin"
        };
        append_event(
            &mut transaction,
            request_id,
            EventAppend {
                run_id: None,
                event_type: "triage.classified",
                from_state: Some("triaging"),
                to_state: Some(triage_target),
                trace_id: &trace_id,
                payload: &triage_payload,
            },
        )
        .await?;

        if let Some(plan_id) = submission.plan_id {
            let now: OffsetDateTime = sqlx::query_scalar("SELECT clock_timestamp()")
                .fetch_one(&mut *transaction)
                .await?;
            sqlx::query("UPDATE factory.requests SET status = 'plan_bin' WHERE id = $1")
                .bind(request_id)
                .execute(&mut *transaction)
                .await?;
            sqlx::query(
                "UPDATE factory.leases SET released_at = $2 WHERE request_id = $1 AND released_at IS NULL",
            )
            .bind(request_id)
            .bind(now)
            .execute(&mut *transaction)
            .await?;
            let plan_payload = serde_json::json!({
                "plan_id": plan_id,
                "triage_id": submission.id,
                "lane": classification.lane,
                "task_spec_sha256": task_spec_sha256,
                "rubric_version": submission.output.task_spec.rubric_version,
            });
            append_event(
                &mut transaction,
                request_id,
                EventAppend {
                    run_id: None,
                    event_type: "plan.entered",
                    from_state: Some("triaging"),
                    to_state: Some("plan_bin"),
                    trace_id: &trace_id,
                    payload: &plan_payload,
                },
            )
            .await?;
        }

        transaction.commit().await?;
        Ok(TriageRecorded {
            classification,
            plan_id: submission.plan_id,
            inserted: true,
        })
    }

    async fn transition_plan(
        &self,
        request_id: Uuid,
        plan_id: Uuid,
        decision: &PlanDecision,
    ) -> Result<PlanTransitionRecorded, RepositoryError> {
        let decision_sha256 = hex::encode(decision.sha256()?);
        let mut transaction = self.pool.begin().await?;
        let (status, trace_id) =
            Self::require_request_for_update(&mut transaction, request_id).await?;

        let existing: Option<serde_json::Value> = sqlx::query_scalar(
            r#"
            SELECT payload
            FROM factory.events
            WHERE request_id = $1
              AND event_type IN ('plan.reenter.implement', 'plan.reenter.triage', 'plan.closed')
              AND payload->>'decision_id' = $2
            ORDER BY id DESC
            LIMIT 1
            "#,
        )
        .bind(request_id)
        .bind(decision.id.to_string())
        .fetch_optional(&mut *transaction)
        .await?;
        if let Some(existing) = existing {
            if existing.get("plan_id").and_then(serde_json::Value::as_str)
                != Some(plan_id.to_string().as_str())
                || existing
                    .get("decision_sha256")
                    .and_then(serde_json::Value::as_str)
                    != Some(decision_sha256.as_str())
            {
                return Err(RepositoryError::PlanDecisionIdConflict(decision.id));
            }
            let transition: PlanTransition = serde_json::from_value(
                existing
                    .get("transition")
                    .cloned()
                    .ok_or(RepositoryError::MalformedLedgerEvent)?,
            )?;
            transaction.commit().await?;
            return Ok(PlanTransitionRecorded {
                transition,
                inserted: false,
            });
        }

        if status != "plan_bin" {
            return Err(RepositoryError::UnexpectedRequestStatus {
                request_id,
                expected: "plan_bin",
                actual: status,
            });
        }
        let plan_event = sqlx::query(
            r#"
            SELECT event_type, payload
            FROM factory.events
            WHERE request_id = $1
              AND event_type LIKE 'plan.%'
              AND payload->>'plan_id' = $2
            ORDER BY id DESC
            LIMIT 1
            "#,
        )
        .bind(request_id)
        .bind(plan_id.to_string())
        .fetch_optional(&mut *transaction)
        .await?
        .ok_or(RepositoryError::PlanNotFound(plan_id))?;
        let event_type: String = plan_event.try_get("event_type")?;
        if event_type != "plan.entered" {
            return Err(RepositoryError::PlanAlreadyTransitioned(plan_id));
        }
        let entered_payload: serde_json::Value = plan_event.try_get("payload")?;
        let lane = Lane::parse(
            entered_payload
                .get("lane")
                .and_then(serde_json::Value::as_str)
                .ok_or(RepositoryError::MalformedLedgerEvent)?,
        )?;
        if let PlanAction::ApproveB { task_spec } = &decision.action {
            let plan_rubric_version = entered_payload
                .get("rubric_version")
                .and_then(serde_json::Value::as_str)
                .ok_or(RepositoryError::MalformedLedgerEvent)?;
            if task_spec.rubric_version != plan_rubric_version {
                return Err(RepositoryError::ApprovedPlanRubricMismatch {
                    plan: plan_rubric_version.to_owned(),
                    task: task_spec.rubric_version.clone(),
                });
            }
        }
        let transition = transition_for(lane, decision)?;
        let decision_data = match &decision.action {
            PlanAction::ApproveB { task_spec } => serde_json::json!({
                "task_spec_sha256": hex::encode(task_spec.sha256()?),
            }),
            PlanAction::AnswerD { answer } => serde_json::json!({
                "channel": "clarification_answer",
                "authority": "none",
                "content": answer,
            }),
            PlanAction::MarkCExecuted { runbook_reference } => serde_json::json!({
                "runbook_reference": runbook_reference,
            }),
            PlanAction::Reject { reason } => serde_json::json!({
                "reason": reason,
            }),
        };
        let payload = serde_json::json!({
            "plan_id": plan_id,
            "decision_id": decision.id,
            "decision_sha256": decision_sha256,
            "lane": lane,
            "transition": transition,
            "decision_data": decision_data,
        });
        let (event_type, to_state) = match transition.kind {
            PlanTransitionKind::ReenterImplement => ("plan.reenter.implement", "implement"),
            PlanTransitionKind::Retriage => ("plan.reenter.triage", "triage"),
            PlanTransitionKind::CloseExecuted | PlanTransitionKind::CloseRejected => {
                ("plan.closed", "closed")
            }
        };

        if transition.outcome.is_some() {
            close_request_state(
                &mut transaction,
                request_id,
                duration_seconds(PLAN_CLOSE_RETENTION)?,
            )
            .await?;
        } else {
            sqlx::query("UPDATE factory.requests SET status = 'queued' WHERE id = $1")
                .bind(request_id)
                .execute(&mut *transaction)
                .await?;
        }
        append_event(
            &mut transaction,
            request_id,
            EventAppend {
                run_id: None,
                event_type,
                from_state: Some("plan_bin"),
                to_state: Some(to_state),
                trace_id: &trace_id,
                payload: &payload,
            },
        )
        .await?;
        transaction.commit().await?;
        Ok(PlanTransitionRecorded {
            transition,
            inserted: true,
        })
    }

    async fn authoritative_implementation_task_spec(
        &self,
        request_id: Uuid,
    ) -> Result<Option<TaskSpec>, RepositoryError> {
        let status: Option<String> =
            sqlx::query_scalar("SELECT status::text FROM factory.requests WHERE id = $1")
                .bind(request_id)
                .fetch_optional(&self.pool)
                .await?;
        let status = status.ok_or(RepositoryError::RequestNotFound(request_id))?;
        if matches!(status.as_str(), "closed" | "failed" | "killed" | "plan_bin") {
            return Ok(None);
        }
        let row = sqlx::query(
            r#"
            SELECT event_type, payload
            FROM factory.events
            WHERE request_id = $1
              AND (
                  event_type = 'plan.reenter.implement'
                  OR (event_type = 'triage.classified' AND payload->>'lane' = 'A')
              )
            ORDER BY id DESC
            LIMIT 1
            "#,
        )
        .bind(request_id)
        .fetch_optional(&self.pool)
        .await?;
        let Some(row) = row else {
            return Ok(None);
        };
        let event_type: String = row.try_get("event_type")?;
        let payload: serde_json::Value = row.try_get("payload")?;
        let task_spec_value = if event_type == "triage.classified" {
            payload.get("task_spec")
        } else {
            payload
                .get("transition")
                .and_then(|transition| transition.get("authoritative_task_spec"))
        };
        let Some(task_spec_value) = task_spec_value else {
            return Err(RepositoryError::MalformedLedgerEvent);
        };
        let task_spec: TaskSpec = serde_json::from_value(task_spec_value.clone())?;
        task_spec.validate()?;
        Ok(Some(task_spec))
    }

    async fn expired_artifacts(
        &self,
        now: OffsetDateTime,
        limit: i64,
    ) -> Result<Vec<ExpiredArtifact>, RepositoryError> {
        if !(1..=10_000).contains(&limit) {
            return Err(DomainInputError::InvalidSweepLimit.into());
        }
        let rows = sqlx::query(
            r#"
            SELECT id, path
            FROM factory.artifacts
            WHERE expires_at <= $1 AND deleted_at IS NULL
            ORDER BY expires_at, id
            LIMIT $2
            "#,
        )
        .bind(now)
        .bind(limit)
        .fetch_all(&self.pool)
        .await?;

        rows.into_iter()
            .map(|row| {
                let id = row.try_get("id")?;
                let path: String = row.try_get("path")?;
                let relative_path = validate_relative_artifact_path(Path::new(&path))?;
                Ok(ExpiredArtifact { id, relative_path })
            })
            .collect()
    }

    async fn mark_artifact_deleted(
        &self,
        artifact_id: Uuid,
        deleted_at: OffsetDateTime,
    ) -> Result<(), RepositoryError> {
        let affected = sqlx::query(
            r#"
            UPDATE factory.artifacts
            SET deleted_at = $2
            WHERE id = $1 AND expires_at <= $2 AND deleted_at IS NULL
            "#,
        )
        .bind(artifact_id)
        .bind(deleted_at)
        .execute(&self.pool)
        .await?
        .rows_affected();
        if affected != 1 {
            return Err(RepositoryError::ArtifactNotExpired(artifact_id));
        }
        Ok(())
    }
}

fn duration_seconds(duration: Duration) -> Result<i64, RepositoryError> {
    i64::try_from(duration.as_secs()).map_err(|_| DomainInputError::InvalidRetention.into())
}

async fn close_request_state(
    transaction: &mut Transaction<'_, Postgres>,
    request_id: Uuid,
    retention_seconds: i64,
) -> Result<(), RepositoryError> {
    if retention_seconds <= 0 {
        return Err(DomainInputError::InvalidRetention.into());
    }
    let now: OffsetDateTime = sqlx::query_scalar("SELECT clock_timestamp()")
        .fetch_one(&mut **transaction)
        .await?;
    let expires_at = now + time::Duration::seconds(retention_seconds);
    sqlx::query("UPDATE factory.requests SET status = 'closed', closed_at = $2 WHERE id = $1")
        .bind(request_id)
        .bind(now)
        .execute(&mut **transaction)
        .await?;
    sqlx::query(
        "UPDATE factory.leases SET released_at = $2 WHERE request_id = $1 AND released_at IS NULL",
    )
    .bind(request_id)
    .bind(now)
    .execute(&mut **transaction)
    .await?;
    sqlx::query(
        "UPDATE factory.artifacts SET expires_at = COALESCE(expires_at, $2) WHERE request_id = $1",
    )
    .bind(request_id)
    .bind(expires_at)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

struct EventAppend<'a> {
    run_id: Option<Uuid>,
    event_type: &'a str,
    from_state: Option<&'a str>,
    to_state: Option<&'a str>,
    trace_id: &'a str,
    payload: &'a serde_json::Value,
}

async fn append_event(
    transaction: &mut Transaction<'_, Postgres>,
    request_id: Uuid,
    event: EventAppend<'_>,
) -> Result<(), RepositoryError> {
    sqlx::query(
        r#"
        INSERT INTO factory.events (
            request_id, run_id, event_type, from_state, to_state, trace_id, payload
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        "#,
    )
    .bind(request_id)
    .bind(event.run_id)
    .bind(event.event_type)
    .bind(event.from_state)
    .bind(event.to_state)
    .bind(event.trace_id)
    .bind(event.payload)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

/// Remove an expired artifact path without following symlinks out of the 0700 root.
pub fn remove_artifact(root: &Path, relative_path: &Path) -> Result<bool, RepositoryError> {
    use std::os::unix::fs::PermissionsExt;

    let root_metadata = std::fs::symlink_metadata(root)?;
    if root_metadata.file_type().is_symlink() || !root_metadata.is_dir() {
        return Err(RepositoryError::UnsafeArtifactRoot(root.to_path_buf()));
    }
    if root_metadata.permissions().mode() & 0o777 != 0o700 {
        return Err(RepositoryError::UnsafeArtifactRoot(root.to_path_buf()));
    }

    let relative_path = validate_relative_artifact_path(relative_path)?;
    let mut current = root.to_path_buf();
    for component in relative_path.components() {
        let Component::Normal(part) = component else {
            return Err(RepositoryError::UnsafeArtifactPath(relative_path));
        };
        current.push(part);
        match std::fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(RepositoryError::UnsafeArtifactPath(relative_path));
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
            Err(error) => return Err(error.into()),
        }
    }

    let metadata = std::fs::symlink_metadata(&current)?;
    if metadata.is_dir() {
        std::fs::remove_dir_all(&current)?;
    } else {
        std::fs::remove_file(&current)?;
    }
    Ok(true)
}

fn validate_relative_artifact_path(path: &Path) -> Result<PathBuf, RepositoryError> {
    if path.as_os_str().is_empty()
        || path.is_absolute()
        || path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(RepositoryError::UnsafeArtifactPath(path.to_path_buf()));
    }
    Ok(path.to_path_buf())
}

/// Invalid caller input rejected before reaching PostgreSQL.
#[derive(Clone, Debug, Error, Eq, PartialEq)]
pub enum NewRequestError {
    #[error("request body is invalid: {0}")]
    Body(#[from] RequestBodyError),
    #[error("request metadata is invalid: {0}")]
    Metadata(#[from] DomainInputError),
}

/// Invalid caller input rejected before reaching PostgreSQL.
#[derive(Clone, Copy, Debug, Error, Eq, PartialEq)]
pub enum DomainInputError {
    #[error("trace id must be 32 non-zero lower-case hexadecimal characters")]
    InvalidTraceId,
    #[error("SHA-256 value must be 64 hexadecimal characters")]
    InvalidSha256,
    #[error("request source must contain 1 to 64 characters")]
    InvalidSource,
    #[error("lease holder must contain 1 to 128 characters")]
    InvalidHolder,
    #[error("lease TTL must be between 1 second and 24 hours")]
    InvalidLeaseTtl,
    #[error("retention must be positive")]
    InvalidRetention,
    #[error("retention sweep limit must be between 1 and 10000")]
    InvalidSweepLimit,
}

/// Repository failure with lease and durability errors kept explicit.
#[derive(Debug, Error)]
pub enum RepositoryError {
    #[error("PostgreSQL state operation failed: {0}")]
    Database(#[from] sqlx::Error),
    #[error("triage contract failed: {0}")]
    Triage(#[from] TriageError),
    #[error("plan-bin contract failed: {0}")]
    Plan(#[from] PlanError),
    #[error("ledger JSON failed validation: {0}")]
    LedgerJson(#[from] serde_json::Error),
    #[error("invalid domain input: {0}")]
    InvalidInput(#[from] DomainInputError),
    #[error("request {0} does not exist")]
    RequestNotFound(Uuid),
    #[error("request {request_id} is terminal ({status})")]
    TerminalRequest { request_id: Uuid, status: String },
    #[error("request {0} is waiting in the plan bin")]
    RequestInPlanBin(Uuid),
    #[error("request {request_id} must be {expected}, not {actual}")]
    UnexpectedRequestStatus {
        request_id: Uuid,
        expected: &'static str,
        actual: String,
    },
    #[error("lane A triage must not create a plan id")]
    LaneAPlanId,
    #[error("lane {0} triage requires a plan id")]
    PlanIdRequired(Lane),
    #[error("triage id {0} was reused with different content")]
    TriageIdConflict(Uuid),
    #[error("plan {0} does not exist for this request")]
    PlanNotFound(Uuid),
    #[error("plan {0} already left the plan bin")]
    PlanAlreadyTransitioned(Uuid),
    #[error("plan decision id {0} was reused with different content")]
    PlanDecisionIdConflict(Uuid),
    #[error("approved TaskSpec rubric {task} does not match plan rubric {plan}")]
    ApprovedPlanRubricMismatch { plan: String, task: String },
    #[error("ledger event does not match its typed contract")]
    MalformedLedgerEvent,
    #[error("request {request_id} is held by {holder} until {expires_at}")]
    LeaseHeld {
        request_id: Uuid,
        holder: String,
        expires_at: OffsetDateTime,
    },
    #[error("fencing token exhausted for request {0}")]
    FencingTokenExhausted(Uuid),
    #[error("artifact {0} is not currently expired")]
    ArtifactNotExpired(Uuid),
    #[error("unsafe artifact root: {0}")]
    UnsafeArtifactRoot(PathBuf),
    #[error("unsafe artifact path: {0}")]
    UnsafeArtifactPath(PathBuf),
    #[error("artifact filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("injected crash at {0:?}")]
    InjectedFault(TransitionFault),
}

#[cfg(test)]
mod tests {
    use std::{fs, os::unix::fs::PermissionsExt};

    use super::{RepositoryError, TraceId, remove_artifact};

    #[test]
    fn trace_ids_follow_w3c_shape() {
        let generated = TraceId::random();
        assert_eq!(generated.as_str().len(), 32);
        assert!(TraceId::parse(generated.as_str()).is_ok());
        assert!(TraceId::parse("00000000000000000000000000000000").is_err());
        assert!(TraceId::parse("ABCDEF00000000000000000000000001").is_err());
    }

    #[test]
    fn retention_rejects_traversal_and_symlinks() {
        let root = std::env::temp_dir().join(format!("factory-retention-{}", uuid::Uuid::new_v4()));
        fs::create_dir(&root).expect("create root");
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).expect("chmod root");
        fs::write(root.join("evidence.txt"), b"evidence").expect("write fixture");
        assert!(remove_artifact(&root, std::path::Path::new("evidence.txt")).expect("remove"));

        let traversal = remove_artifact(&root, std::path::Path::new("../outside"));
        assert!(matches!(
            traversal,
            Err(RepositoryError::UnsafeArtifactPath(_))
        ));

        std::os::unix::fs::symlink("/tmp", root.join("escape")).expect("create symlink");
        let escape = remove_artifact(&root, std::path::Path::new("escape/file"));
        assert!(matches!(
            escape,
            Err(RepositoryError::UnsafeArtifactPath(_))
        ));
        fs::remove_file(root.join("escape")).expect("remove symlink");
        fs::remove_dir(root).expect("remove root");
    }
}
