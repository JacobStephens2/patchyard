//! Durable PostgreSQL rows used by the supervisor and its recovery sweeps.

use std::time::Duration;

use factory_core::{
    state::{FactoryRepository as _, PostgresRepository, TriageRecorded, TriageSubmission},
    triage::{Rubric, TaskSpec},
};
use factory_verify::ledger::{self, ValidatedRunRecord};
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Postgres, Row, Transaction, postgres::PgPoolOptions};
use thiserror::Error;
use time::OffsetDateTime;
use uuid::Uuid;

use crate::artifacts::StoredArtifact;
use crate::contracts::InvocationUsage;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct DailyLimits {
    pub per_submitter: u32,
    pub global: u32,
}

impl DailyLimits {
    pub fn validate(self) -> Result<Self, StoreError> {
        if self.per_submitter == 0 || self.global == 0 || self.per_submitter > self.global {
            return Err(StoreError::InvalidDailyLimits);
        }
        Ok(self)
    }
}

#[derive(Clone, Debug)]
pub struct WorkClaim {
    pub request_id: Uuid,
    pub source: String,
    pub body: String,
    pub trace_id: String,
    pub fencing_token: i64,
    pub recovered: bool,
}

#[derive(Clone, Debug)]
pub struct RequestWork {
    pub request_id: Uuid,
    pub source: String,
    pub body: String,
    pub trace_id: String,
    pub status: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ControlKind {
    Pause,
    Resume,
    Kill,
    FullStop,
}

impl ControlKind {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Pause => "pause",
            Self::Resume => "resume",
            Self::Kill => "kill",
            Self::FullStop => "full_stop",
        }
    }

    fn parse(value: &str) -> Result<Self, StoreError> {
        match value {
            "pause" => Ok(Self::Pause),
            "resume" => Ok(Self::Resume),
            "kill" => Ok(Self::Kill),
            "full_stop" => Ok(Self::FullStop),
            _ => Err(StoreError::MalformedRow),
        }
    }
}

#[derive(Clone, Debug)]
pub struct ControlRow {
    pub id: Uuid,
    pub command: ControlKind,
    pub target_run_id: Option<Uuid>,
    pub requested_by: String,
    pub reason: String,
    pub status: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SideEffectDisposition {
    Start,
    Resume,
    Completed,
}

#[derive(Clone, Debug)]
pub struct ExistingRun {
    pub id: Uuid,
    pub base_sha: String,
    pub state: String,
    pub lane: String,
    pub skill: String,
}

/// Store contract used identically by the daemon and `factoryctl run`.
pub trait PipelineStore: Clone + Send + Sync + 'static {
    fn claim_next(
        &self,
        holder: &str,
        ttl: Duration,
        limits: DailyLimits,
    ) -> impl Future<Output = Result<Option<WorkClaim>, StoreError>> + Send;

    fn claim_specific(
        &self,
        request_id: Uuid,
        holder: &str,
        ttl: Duration,
        limits: DailyLimits,
    ) -> impl Future<Output = Result<WorkClaim, StoreError>> + Send;

    fn load_request(
        &self,
        request_id: Uuid,
    ) -> impl Future<Output = Result<RequestWork, StoreError>> + Send;

    fn authoritative_task_spec(
        &self,
        request_id: Uuid,
    ) -> impl Future<Output = Result<Option<TaskSpec>, StoreError>> + Send;

    fn record_triage(
        &self,
        request_id: Uuid,
        submission: &TriageSubmission,
        rubric: &Rubric,
    ) -> impl Future<Output = Result<TriageRecorded, StoreError>> + Send;

    fn existing_run(
        &self,
        request_id: Uuid,
    ) -> impl Future<Output = Result<Option<ExistingRun>, StoreError>> + Send;

    fn append_run(
        &self,
        run: &ValidatedRunRecord,
    ) -> impl Future<Output = Result<(), StoreError>> + Send;

    fn transition_run(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        event_type: &str,
        to_state: &str,
        idempotency_key: &str,
        payload: serde_json::Value,
    ) -> impl Future<Output = Result<bool, StoreError>> + Send;

    fn record_usage(
        &self,
        run_id: Uuid,
        model_id: &str,
        usage: InvocationUsage,
    ) -> impl Future<Output = Result<(), StoreError>> + Send;

    fn register_artifact(
        &self,
        request_id: Uuid,
        run_id: Option<Uuid>,
        stage: &str,
        artifact: &StoredArtifact,
    ) -> impl Future<Output = Result<(), StoreError>> + Send;

    fn stage_artifacts(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        stage: &str,
    ) -> impl Future<Output = Result<Vec<StoredArtifact>, StoreError>> + Send;

    fn begin_side_effect(
        &self,
        request_id: Uuid,
        run_id: Option<Uuid>,
        key: &str,
        effect_type: &str,
        attempt: u8,
    ) -> impl Future<Output = Result<SideEffectDisposition, StoreError>> + Send;

    fn finish_side_effect(
        &self,
        key: &str,
        status: &str,
        external_ref: Option<&str>,
        facts: serde_json::Value,
    ) -> impl Future<Output = Result<(), StoreError>> + Send;

    fn release_lease(
        &self,
        request_id: Uuid,
        holder: &str,
    ) -> impl Future<Output = Result<(), StoreError>> + Send;

    fn finish_run(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        state: &str,
        event_type: &str,
        outcome: serde_json::Value,
    ) -> impl Future<Output = Result<(), StoreError>> + Send;

    fn enqueue_control(
        &self,
        command: ControlKind,
        target_run_id: Option<Uuid>,
        requested_by: &str,
        reason: &str,
    ) -> impl Future<Output = Result<Uuid, StoreError>> + Send;

    fn pending_controls(
        &self,
        limit: i64,
    ) -> impl Future<Output = Result<Vec<ControlRow>, StoreError>> + Send;

    fn claim_control(&self, id: Uuid) -> impl Future<Output = Result<bool, StoreError>> + Send;

    fn set_claiming_state(
        &self,
        paused: bool,
        full_stop: bool,
        actor: &str,
    ) -> impl Future<Output = Result<(), StoreError>> + Send;

    fn complete_control(
        &self,
        id: Uuid,
        success: bool,
        outcome: serde_json::Value,
    ) -> impl Future<Output = Result<(), StoreError>> + Send;

    fn kill_run(
        &self,
        run_id: Uuid,
        control_id: Uuid,
        reason: &str,
    ) -> impl Future<Output = Result<Option<Uuid>, StoreError>> + Send;

    fn request_for_run(
        &self,
        run_id: Uuid,
    ) -> impl Future<Output = Result<Option<Uuid>, StoreError>> + Send;
}

#[derive(Clone, Debug)]
pub struct PgPipelineStore {
    pool: PgPool,
    repository: PostgresRepository,
}

impl PgPipelineStore {
    pub async fn connect(database_url: &str) -> Result<Self, StoreError> {
        let pool = PgPoolOptions::new()
            .max_connections(10)
            .acquire_timeout(Duration::from_secs(10))
            .connect(database_url)
            .await?;
        Ok(Self {
            repository: PostgresRepository::from_pool(pool.clone()),
            pool,
        })
    }

    #[must_use]
    pub fn pool(&self) -> &PgPool {
        &self.pool
    }

    pub async fn close(&self) {
        self.pool.close().await;
    }

    async fn claim(
        &self,
        requested: Option<Uuid>,
        holder: &str,
        ttl: Duration,
        limits: DailyLimits,
    ) -> Result<Option<WorkClaim>, StoreError> {
        validate_label("holder", holder, 128)?;
        let limits = limits.validate()?;
        let ttl_seconds = i64::try_from(ttl.as_secs()).map_err(|_| StoreError::InvalidLeaseTtl)?;
        if !(1..=86_400).contains(&ttl_seconds) {
            return Err(StoreError::InvalidLeaseTtl);
        }
        let mut transaction = self.pool.begin().await?;
        let state = sqlx::query(
            "SELECT paused, full_stop FROM factory.supervisor_state WHERE singleton FOR UPDATE",
        )
        .fetch_one(&mut *transaction)
        .await?;
        if state.try_get::<bool, _>("paused")? || state.try_get::<bool, _>("full_stop")? {
            transaction.commit().await?;
            return if requested.is_some() {
                Err(StoreError::ClaimingPaused)
            } else {
                Ok(None)
            };
        }
        let global_count: i64 = sqlx::query_scalar(
            r#"
            SELECT count(DISTINCT request_id)
            FROM factory.events
            WHERE event_type = 'request.claimed'
              AND occurred_at >= date_trunc('day', clock_timestamp())
            "#,
        )
        .fetch_one(&mut *transaction)
        .await?;
        let rows = if let Some(request_id) = requested {
            sqlx::query(
                r#"
                SELECT id, source, body, trace_id, status::text AS status
                FROM factory.requests
                WHERE id = $1 AND status IN ('queued', 'claimed')
                FOR UPDATE
                "#,
            )
            .bind(request_id)
            .fetch_all(&mut *transaction)
            .await?
        } else {
            // There are two genuine consumers: the resident daemon and the
            // foreground operator path, so SKIP LOCKED is intentional here.
            // Application-level foreign leases and submitters already at
            // their admission limit are excluded before ordering; otherwise
            // one old row could starve every eligible row behind it.
            sqlx::query(
                r#"
                SELECT candidate.id, candidate.source, candidate.body,
                       candidate.trace_id, candidate.status::text AS status
                FROM factory.requests AS candidate
                WHERE candidate.status IN ('queued', 'claimed')
                  AND NOT EXISTS (
                    SELECT 1
                    FROM factory.leases
                    WHERE leases.request_id = candidate.id
                      AND leases.released_at IS NULL
                      AND leases.expires_at > clock_timestamp()
                      AND leases.holder <> $1
                  )
                  AND (
                    candidate.status = 'claimed'
                    OR (
                      SELECT count(DISTINCT events.request_id)
                      FROM factory.events
                      JOIN factory.requests AS claimed_request
                        ON claimed_request.id = events.request_id
                      WHERE events.event_type = 'request.claimed'
                        AND events.occurred_at >= date_trunc('day', clock_timestamp())
                        AND claimed_request.source = candidate.source
                    ) < $2
                  )
                ORDER BY (candidate.status = 'claimed') DESC,
                         candidate.received_at, candidate.id
                LIMIT 1
                FOR UPDATE OF candidate SKIP LOCKED
                "#,
            )
            .bind(holder)
            .bind(i64::from(limits.per_submitter))
            .fetch_all(&mut *transaction)
            .await?
        };
        if rows.is_empty() {
            transaction.commit().await?;
            return if let Some(request_id) = requested {
                Err(StoreError::RequestNotClaimable(request_id))
            } else {
                Ok(None)
            };
        }

        let mut chosen = None;
        for row in rows {
            let source: String = row.try_get("source")?;
            let status: String = row.try_get("status")?;
            // Limits gate new claims. Recovery of an already-claimed durable
            // row must not be stranded after a restart or date boundary.
            if status == "claimed" {
                chosen = Some((row, source));
                break;
            }
            let submitter_count: i64 = sqlx::query_scalar(
                r#"
                SELECT count(DISTINCT events.request_id)
                FROM factory.events
                JOIN factory.requests ON requests.id = events.request_id
                WHERE events.event_type = 'request.claimed'
                  AND events.occurred_at >= date_trunc('day', clock_timestamp())
                  AND requests.source = $1
                "#,
            )
            .bind(&source)
            .fetch_one(&mut *transaction)
            .await?;
            if submitter_count >= i64::from(limits.per_submitter) {
                if requested.is_some() {
                    return Err(StoreError::SubmitterDailyLimit(source));
                }
                continue;
            }
            chosen = Some((row, source));
            break;
        }
        let Some((row, source)) = chosen else {
            transaction.commit().await?;
            return Ok(None);
        };
        let request_id: Uuid = row.try_get("id")?;
        let status: String = row.try_get("status")?;
        let trace_id: String = row.try_get("trace_id")?;
        if status != "claimed" && global_count >= i64::from(limits.global) {
            transaction.commit().await?;
            return if requested.is_some() {
                Err(StoreError::GlobalDailyLimit)
            } else {
                Ok(None)
            };
        }
        let resource = format!("request:{request_id}");
        let now: OffsetDateTime = sqlx::query_scalar("SELECT clock_timestamp()")
            .fetch_one(&mut *transaction)
            .await?;
        let expires_at = now + time::Duration::seconds(ttl_seconds);
        let lease = sqlx::query(
            "SELECT holder, fencing_token, expires_at, released_at FROM factory.leases WHERE resource = $1 FOR UPDATE",
        )
        .bind(&resource)
        .fetch_optional(&mut *transaction)
        .await?;
        let (fencing_token, recovered, append_claim) = if let Some(lease) = lease {
            let current_holder: String = lease.try_get("holder")?;
            let token: i64 = lease.try_get("fencing_token")?;
            let expiry: OffsetDateTime = lease.try_get("expires_at")?;
            let released: Option<OffsetDateTime> = lease.try_get("released_at")?;
            if released.is_none() && expiry > now && current_holder != holder {
                transaction.commit().await?;
                return if requested.is_some() {
                    Err(StoreError::LeaseHeld(request_id))
                } else {
                    Ok(None)
                };
            }
            if released.is_none() && expiry > now {
                (token, true, false)
            } else {
                let next = token.checked_add(1).ok_or(StoreError::FencingExhausted)?;
                sqlx::query(
                    "UPDATE factory.leases SET holder=$2, fencing_token=$3, acquired_at=$4, expires_at=$5, released_at=NULL WHERE resource=$1",
                )
                .bind(&resource)
                .bind(holder)
                .bind(next)
                .bind(now)
                .bind(expires_at)
                .execute(&mut *transaction)
                .await?;
                (next, status == "claimed", true)
            }
        } else {
            sqlx::query(
                "INSERT INTO factory.leases (resource, request_id, holder, fencing_token, acquired_at, expires_at) VALUES ($1,$2,$3,1,$4,$5)",
            )
            .bind(&resource)
            .bind(request_id)
            .bind(holder)
            .bind(now)
            .bind(expires_at)
            .execute(&mut *transaction)
            .await?;
            (1, status == "claimed", true)
        };
        if status != "claimed" {
            sqlx::query("UPDATE factory.requests SET status='claimed' WHERE id=$1")
                .bind(request_id)
                .execute(&mut *transaction)
                .await?;
        }
        if append_claim {
            append_event(
                &mut transaction,
                request_id,
                None,
                "request.claimed",
                Some(&status),
                Some("claimed"),
                &trace_id,
                serde_json::json!({"holder": holder, "fencing_token": fencing_token}),
            )
            .await?;
        }
        let claim = WorkClaim {
            request_id,
            source,
            body: row.try_get("body")?,
            trace_id,
            fencing_token,
            recovered,
        };
        transaction.commit().await?;
        Ok(Some(claim))
    }
}

impl PipelineStore for PgPipelineStore {
    async fn claim_next(
        &self,
        holder: &str,
        ttl: Duration,
        limits: DailyLimits,
    ) -> Result<Option<WorkClaim>, StoreError> {
        self.claim(None, holder, ttl, limits).await
    }

    async fn claim_specific(
        &self,
        request_id: Uuid,
        holder: &str,
        ttl: Duration,
        limits: DailyLimits,
    ) -> Result<WorkClaim, StoreError> {
        self.claim(Some(request_id), holder, ttl, limits)
            .await?
            .ok_or(StoreError::RequestNotClaimable(request_id))
    }

    async fn load_request(&self, request_id: Uuid) -> Result<RequestWork, StoreError> {
        let row = sqlx::query(
            "SELECT id, source, body, trace_id, status::text AS status FROM factory.requests WHERE id=$1",
        )
        .bind(request_id)
        .fetch_optional(&self.pool)
        .await?
        .ok_or(StoreError::RequestNotFound(request_id))?;
        Ok(RequestWork {
            request_id: row.try_get("id")?,
            source: row.try_get("source")?,
            body: row.try_get("body")?,
            trace_id: row.try_get("trace_id")?,
            status: row.try_get("status")?,
        })
    }

    async fn authoritative_task_spec(
        &self,
        request_id: Uuid,
    ) -> Result<Option<TaskSpec>, StoreError> {
        Ok(self
            .repository
            .authoritative_implementation_task_spec(request_id)
            .await?)
    }

    async fn record_triage(
        &self,
        request_id: Uuid,
        submission: &TriageSubmission,
        rubric: &Rubric,
    ) -> Result<TriageRecorded, StoreError> {
        Ok(self
            .repository
            .record_triage(request_id, submission, rubric)
            .await?)
    }

    async fn existing_run(&self, request_id: Uuid) -> Result<Option<ExistingRun>, StoreError> {
        let row = sqlx::query(
            "SELECT id, base_sha, state::text AS state, lane, skill FROM factory.runs WHERE request_id=$1 ORDER BY queued_at DESC LIMIT 1",
        )
        .bind(request_id)
        .fetch_optional(&self.pool)
        .await?;
        row.map(|row| {
            Ok(ExistingRun {
                id: row.try_get("id")?,
                base_sha: row.try_get("base_sha")?,
                state: row.try_get("state")?,
                lane: row.try_get("lane")?,
                skill: row.try_get("skill")?,
            })
        })
        .transpose()
    }

    async fn append_run(&self, run: &ValidatedRunRecord) -> Result<(), StoreError> {
        match ledger::append(&self.pool, run).await {
            Ok(()) => Ok(()),
            Err(ledger::LedgerError::Database(sqlx::Error::Database(error)))
                if error.is_unique_violation() =>
            {
                let existing: Option<Uuid> = sqlx::query_scalar(
                    "SELECT id FROM factory.runs WHERE id=$1 AND request_id=$2 AND base_sha=$3 AND branch=$4",
                )
                .bind(run.record().id)
                .bind(run.record().request_id)
                .bind(&run.record().base_sha)
                .bind(&run.record().branch)
                .fetch_optional(&self.pool)
                .await?;
                if existing == Some(run.record().id) {
                    Ok(())
                } else {
                    Err(StoreError::RunConflict(run.record().id))
                }
            }
            Err(error) => Err(error.into()),
        }
    }

    async fn transition_run(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        event_type: &str,
        to_state: &str,
        idempotency_key: &str,
        mut payload: serde_json::Value,
    ) -> Result<bool, StoreError> {
        validate_label("event type", event_type, 128)?;
        validate_label("state", to_state, 64)?;
        validate_label("idempotency key", idempotency_key, 256)?;
        payload["idempotency_key"] = serde_json::Value::String(idempotency_key.to_owned());
        let mut transaction = self.pool.begin().await?;
        let row = sqlx::query(
            "SELECT runs.state::text AS state, requests.trace_id FROM factory.runs JOIN factory.requests ON requests.id=runs.request_id WHERE runs.id=$1 AND runs.request_id=$2 FOR UPDATE OF runs",
        )
        .bind(run_id)
        .bind(request_id)
        .fetch_optional(&mut *transaction)
        .await?
        .ok_or(StoreError::RunNotFound(run_id))?;
        let exists: bool = sqlx::query_scalar(
            "SELECT EXISTS(SELECT 1 FROM factory.events WHERE run_id=$1 AND payload->>'idempotency_key'=$2)",
        )
        .bind(run_id)
        .bind(idempotency_key)
        .fetch_one(&mut *transaction)
        .await?;
        if exists {
            transaction.commit().await?;
            return Ok(false);
        }
        let from_state: String = row.try_get("state")?;
        sqlx::query(
            "UPDATE factory.runs SET state=$2::factory.run_state, started_at=COALESCE(started_at, clock_timestamp()) WHERE id=$1",
        )
        .bind(run_id)
        .bind(to_state)
        .execute(&mut *transaction)
        .await?;
        append_event(
            &mut transaction,
            request_id,
            Some(run_id),
            event_type,
            Some(&from_state),
            Some(to_state),
            row.try_get("trace_id")?,
            payload,
        )
        .await?;
        transaction.commit().await?;
        Ok(true)
    }

    async fn record_usage(
        &self,
        run_id: Uuid,
        model_id: &str,
        usage: InvocationUsage,
    ) -> Result<(), StoreError> {
        validate_label("model id", model_id, 256)?;
        let input = i64::try_from(usage.input_tokens).map_err(|_| StoreError::UsageOverflow)?;
        let output = i64::try_from(usage.output_tokens).map_err(|_| StoreError::UsageOverflow)?;
        let cost = i64::try_from(usage.cost_microusd).map_err(|_| StoreError::UsageOverflow)?;
        sqlx::query(
            r#"
            UPDATE factory.runs
            SET input_tokens = input_tokens + $2,
                output_tokens = output_tokens + $3,
                turns = turns + 1,
                eval_scores = jsonb_set(
                    eval_scores,
                    ARRAY['cost_microusd_by_model', $4],
                    to_jsonb(COALESCE((eval_scores #>> ARRAY['cost_microusd_by_model', $4])::bigint, 0) + $5),
                    true
                )
            WHERE id=$1
            "#,
        )
        .bind(run_id)
        .bind(input)
        .bind(output)
        .bind(model_id)
        .bind(cost)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    async fn register_artifact(
        &self,
        request_id: Uuid,
        run_id: Option<Uuid>,
        stage: &str,
        artifact: &StoredArtifact,
    ) -> Result<(), StoreError> {
        validate_label("artifact stage", stage, 128)?;
        let mut transaction = self.pool.begin().await?;
        let trace_id: String =
            sqlx::query_scalar("SELECT trace_id FROM factory.requests WHERE id=$1 FOR UPDATE")
                .bind(request_id)
                .fetch_optional(&mut *transaction)
                .await?
                .ok_or(StoreError::RequestNotFound(request_id))?;
        let digest = hex::decode(&artifact.sha256).map_err(|_| StoreError::MalformedArtifact)?;
        let inserted = sqlx::query(
            "INSERT INTO factory.artifacts (id,request_id,run_id,path,sha256,kind) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (path) DO NOTHING",
        )
        .bind(artifact.id)
        .bind(request_id)
        .bind(run_id)
        .bind(&artifact.relative_path)
        .bind(digest)
        .bind(&artifact.kind)
        .execute(&mut *transaction)
        .await?
        .rows_affected();
        if inserted == 1 {
            let event_type = if artifact.kind == "agent-transcript" {
                "agent.transcript.persisted"
            } else {
                "artifact.persisted"
            };
            append_event(
                &mut transaction,
                request_id,
                run_id,
                event_type,
                Some(stage),
                Some(stage),
                &trace_id,
                serde_json::json!({
                    "artifact_id": artifact.id,
                    "path": artifact.relative_path,
                    "sha256": artifact.sha256,
                    "kind": artifact.kind,
                    "stage": stage,
                }),
            )
            .await?;
        }
        transaction.commit().await?;
        Ok(())
    }

    async fn stage_artifacts(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        stage: &str,
    ) -> Result<Vec<StoredArtifact>, StoreError> {
        validate_label("artifact stage", stage, 128)?;
        let prefix = format!("{request_id}/{run_id}/{stage}/");
        let rows = sqlx::query(
            r#"
            SELECT id, path, encode(sha256, 'hex') AS sha256, kind
            FROM factory.artifacts
            WHERE request_id=$1 AND run_id=$2 AND path LIKE $3 || '%'
              AND deleted_at IS NULL
            ORDER BY created_at, id
            "#,
        )
        .bind(request_id)
        .bind(run_id)
        .bind(prefix)
        .fetch_all(&self.pool)
        .await?;
        rows.into_iter()
            .map(|row| {
                Ok(StoredArtifact {
                    id: row.try_get("id")?,
                    relative_path: row.try_get("path")?,
                    sha256: row.try_get("sha256")?,
                    kind: row.try_get("kind")?,
                    // The initial artifact ledger intentionally stores the
                    // digest rather than a redundant byte count. Recovery
                    // checks the file and derives its actual length.
                    bytes: 0,
                })
            })
            .collect()
    }

    async fn begin_side_effect(
        &self,
        request_id: Uuid,
        run_id: Option<Uuid>,
        key: &str,
        effect_type: &str,
        attempt: u8,
    ) -> Result<SideEffectDisposition, StoreError> {
        validate_label("side-effect key", key, 256)?;
        validate_label("side-effect type", effect_type, 128)?;
        if attempt > 1 {
            return Err(StoreError::InvalidAttempt);
        }
        let mut transaction = self.pool.begin().await?;
        let inserted = sqlx::query(
            "INSERT INTO factory.side_effects (idempotency_key,request_id,run_id,effect_type,attempt,status,started_at) VALUES ($1,$2,$3,$4,$5,'running',clock_timestamp()) ON CONFLICT DO NOTHING",
        )
        .bind(key)
        .bind(request_id)
        .bind(run_id)
        .bind(effect_type)
        .bind(i16::from(attempt))
        .execute(&mut *transaction)
        .await?
        .rows_affected();
        if inserted == 1 {
            transaction.commit().await?;
            return Ok(SideEffectDisposition::Start);
        }
        let row = sqlx::query(
            "SELECT request_id,run_id,effect_type,attempt,status FROM factory.side_effects WHERE idempotency_key=$1 FOR UPDATE",
        )
        .bind(key)
        .fetch_one(&mut *transaction)
        .await?;
        if row.try_get::<Uuid, _>("request_id")? != request_id
            || row.try_get::<Option<Uuid>, _>("run_id")? != run_id
            || row.try_get::<String, _>("effect_type")? != effect_type
            || row.try_get::<i16, _>("attempt")? != i16::from(attempt)
        {
            return Err(StoreError::SideEffectConflict(key.to_owned()));
        }
        let status: String = row.try_get("status")?;
        let disposition = if status == "completed" {
            SideEffectDisposition::Completed
        } else {
            sqlx::query(
                "UPDATE factory.side_effects SET status='running', started_at=COALESCE(started_at,clock_timestamp()), finished_at=NULL WHERE idempotency_key=$1",
            )
            .bind(key)
            .execute(&mut *transaction)
            .await?;
            SideEffectDisposition::Resume
        };
        transaction.commit().await?;
        Ok(disposition)
    }

    async fn finish_side_effect(
        &self,
        key: &str,
        status: &str,
        external_ref: Option<&str>,
        facts: serde_json::Value,
    ) -> Result<(), StoreError> {
        if !matches!(status, "completed" | "compensated" | "failed") {
            return Err(StoreError::InvalidSideEffectStatus);
        }
        let affected = sqlx::query(
            "UPDATE factory.side_effects SET status=$2,external_ref=$3,facts=$4,finished_at=clock_timestamp() WHERE idempotency_key=$1 AND status='running'",
        )
        .bind(key)
        .bind(status)
        .bind(external_ref)
        .bind(facts)
        .execute(&self.pool)
        .await?
        .rows_affected();
        if affected == 1 {
            Ok(())
        } else {
            let existing: Option<String> = sqlx::query_scalar(
                "SELECT status FROM factory.side_effects WHERE idempotency_key=$1",
            )
            .bind(key)
            .fetch_optional(&self.pool)
            .await?;
            if existing.as_deref() == Some(status) {
                Ok(())
            } else {
                Err(StoreError::SideEffectNotRunning(key.to_owned()))
            }
        }
    }

    async fn release_lease(&self, request_id: Uuid, holder: &str) -> Result<(), StoreError> {
        let affected = sqlx::query(
            "UPDATE factory.leases SET released_at=clock_timestamp() WHERE request_id=$1 AND holder=$2 AND released_at IS NULL",
        )
        .bind(request_id)
        .bind(holder)
        .execute(&self.pool)
        .await?
        .rows_affected();
        if affected == 1 {
            return Ok(());
        }
        let already_released: bool = sqlx::query_scalar(
            "SELECT EXISTS(SELECT 1 FROM factory.leases WHERE request_id=$1 AND holder=$2 AND released_at IS NOT NULL)",
        )
        .bind(request_id)
        .bind(holder)
        .fetch_one(&self.pool)
        .await?;
        if already_released {
            Ok(())
        } else {
            Err(StoreError::LeaseReleaseFailed(request_id))
        }
    }

    async fn finish_run(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        state: &str,
        event_type: &str,
        outcome: serde_json::Value,
    ) -> Result<(), StoreError> {
        validate_label("terminal state", state, 64)?;
        let mut transaction = self.pool.begin().await?;
        let row = sqlx::query(
            "SELECT runs.state::text AS state,requests.trace_id,requests.status::text AS request_status FROM factory.runs JOIN factory.requests ON requests.id=runs.request_id WHERE runs.id=$1 AND runs.request_id=$2 FOR UPDATE OF runs,requests",
        )
        .bind(run_id)
        .bind(request_id)
        .fetch_optional(&mut *transaction)
        .await?
        .ok_or(StoreError::RunNotFound(run_id))?;
        let from_state: String = row.try_get("state")?;
        if from_state == state {
            transaction.commit().await?;
            return Ok(());
        }
        if matches!(
            from_state.as_str(),
            "dry_run_complete" | "closed" | "failed" | "killed" | "escalated"
        ) {
            return Err(StoreError::TerminalRunTransition {
                run_id,
                from: from_state,
                to: state.to_owned(),
            });
        }
        sqlx::query(
            r#"
            UPDATE factory.runs
            SET state=$2::factory.run_state,
                started_at=COALESCE(started_at, stamp.now),
                finished_at=stamp.now,
                eval_scores=eval_scores || $3
            FROM (SELECT clock_timestamp() AS now) AS stamp
            WHERE id=$1
            "#,
        )
        .bind(run_id)
        .bind(state)
        .bind(&outcome)
        .execute(&mut *transaction)
        .await?;
        let request_state = match state {
            "dry_run_complete" => "closed",
            "killed" => "killed",
            "escalated" | "failed" => "failed",
            _ => "claimed",
        };
        if request_state == "closed" {
            sqlx::query("UPDATE factory.requests SET status='closed',closed_at=clock_timestamp() WHERE id=$1")
                .bind(request_id)
                .execute(&mut *transaction)
                .await?;
        } else if request_state != "claimed" {
            sqlx::query(
                "UPDATE factory.requests SET status=$2::factory.request_status WHERE id=$1",
            )
            .bind(request_id)
            .bind(request_state)
            .execute(&mut *transaction)
            .await?;
        }
        append_event(
            &mut transaction,
            request_id,
            Some(run_id),
            event_type,
            Some(&from_state),
            Some(state),
            row.try_get("trace_id")?,
            outcome,
        )
        .await?;
        transaction.commit().await?;
        Ok(())
    }

    async fn enqueue_control(
        &self,
        command: ControlKind,
        target_run_id: Option<Uuid>,
        requested_by: &str,
        reason: &str,
    ) -> Result<Uuid, StoreError> {
        validate_label("control actor", requested_by, 128)?;
        validate_label("control reason", reason, 1_000)?;
        if (command == ControlKind::Kill) != target_run_id.is_some() {
            return Err(StoreError::InvalidControlTarget);
        }
        let id = Uuid::new_v4();
        sqlx::query(
            "INSERT INTO factory.controls (id,command,target_run_id,requested_by,reason) VALUES ($1,$2,$3,$4,$5)",
        )
        .bind(id)
        .bind(command.as_str())
        .bind(target_run_id)
        .bind(requested_by)
        .bind(reason)
        .execute(&self.pool)
        .await?;
        Ok(id)
    }

    async fn pending_controls(&self, limit: i64) -> Result<Vec<ControlRow>, StoreError> {
        if !(1..=1_000).contains(&limit) {
            return Err(StoreError::InvalidControlLimit);
        }
        let rows = sqlx::query(
            "SELECT id,command,target_run_id,requested_by,reason,status FROM factory.controls WHERE status IN ('pending','executing') ORDER BY requested_at,id LIMIT $1",
        )
        .bind(limit)
        .fetch_all(&self.pool)
        .await?;
        rows.into_iter()
            .map(|row| {
                Ok(ControlRow {
                    id: row.try_get("id")?,
                    command: ControlKind::parse(&row.try_get::<String, _>("command")?)?,
                    target_run_id: row.try_get("target_run_id")?,
                    requested_by: row.try_get("requested_by")?,
                    reason: row.try_get("reason")?,
                    status: row.try_get("status")?,
                })
            })
            .collect()
    }

    async fn claim_control(&self, id: Uuid) -> Result<bool, StoreError> {
        let affected = sqlx::query(
            "UPDATE factory.controls SET status='executing' WHERE id=$1 AND status='pending'",
        )
        .bind(id)
        .execute(&self.pool)
        .await?
        .rows_affected();
        if affected == 1 {
            return Ok(true);
        }
        let status: Option<String> =
            sqlx::query_scalar("SELECT status FROM factory.controls WHERE id=$1")
                .bind(id)
                .fetch_optional(&self.pool)
                .await?;
        Ok(status.as_deref() == Some("executing"))
    }

    async fn set_claiming_state(
        &self,
        paused: bool,
        full_stop: bool,
        actor: &str,
    ) -> Result<(), StoreError> {
        validate_label("control actor", actor, 128)?;
        sqlx::query(
            "UPDATE factory.supervisor_state SET paused=$1,full_stop=$2,updated_at=clock_timestamp(),updated_by=$3 WHERE singleton",
        )
        .bind(paused)
        .bind(full_stop)
        .bind(actor)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    async fn complete_control(
        &self,
        id: Uuid,
        success: bool,
        outcome: serde_json::Value,
    ) -> Result<(), StoreError> {
        let status = if success { "completed" } else { "failed" };
        let affected = sqlx::query(
            "UPDATE factory.controls SET status=$2,executed_at=clock_timestamp(),outcome=$3 WHERE id=$1 AND status='executing'",
        )
        .bind(id)
        .bind(status)
        .bind(outcome)
        .execute(&self.pool)
        .await?
        .rows_affected();
        if affected == 1 {
            Ok(())
        } else {
            Err(StoreError::ControlNotExecuting(id))
        }
    }

    async fn kill_run(
        &self,
        run_id: Uuid,
        control_id: Uuid,
        reason: &str,
    ) -> Result<Option<Uuid>, StoreError> {
        let request_id: Option<Uuid> =
            sqlx::query_scalar("SELECT request_id FROM factory.runs WHERE id=$1")
                .bind(run_id)
                .fetch_optional(&self.pool)
                .await?;
        let Some(request_id) = request_id else {
            return Ok(None);
        };
        self.finish_run(
            request_id,
            run_id,
            "killed",
            "run.killed",
            serde_json::json!({"control_id": control_id, "reason": reason}),
        )
        .await?;
        sqlx::query(
            "UPDATE factory.leases SET released_at=COALESCE(released_at,clock_timestamp()) WHERE request_id=$1",
        )
        .bind(request_id)
        .execute(&self.pool)
        .await?;
        Ok(Some(request_id))
    }

    async fn request_for_run(&self, run_id: Uuid) -> Result<Option<Uuid>, StoreError> {
        Ok(
            sqlx::query_scalar("SELECT request_id FROM factory.runs WHERE id=$1")
                .bind(run_id)
                .fetch_optional(&self.pool)
                .await?,
        )
    }
}

#[allow(clippy::too_many_arguments)]
async fn append_event(
    transaction: &mut Transaction<'_, Postgres>,
    request_id: Uuid,
    run_id: Option<Uuid>,
    event_type: &str,
    from_state: Option<&str>,
    to_state: Option<&str>,
    trace_id: &str,
    payload: serde_json::Value,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "INSERT INTO factory.events (request_id,run_id,event_type,from_state,to_state,trace_id,payload) VALUES ($1,$2,$3,$4,$5,$6,$7)",
    )
    .bind(request_id)
    .bind(run_id)
    .bind(event_type)
    .bind(from_state)
    .bind(to_state)
    .bind(trace_id)
    .bind(payload)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

fn validate_label(field: &'static str, value: &str, maximum: usize) -> Result<(), StoreError> {
    if value.trim().is_empty() || value.len() > maximum || value.chars().any(char::is_control) {
        return Err(StoreError::InvalidLabel(field));
    }
    Ok(())
}

#[derive(Debug, Error)]
pub enum StoreError {
    #[error("PostgreSQL supervisor operation failed: {0}")]
    Database(#[from] sqlx::Error),
    #[error("core state operation failed: {0}")]
    Core(#[from] factory_core::state::RepositoryError),
    #[error("ledger append failed: {0}")]
    Ledger(#[from] ledger::LedgerError),
    #[error("daily limits must be positive and per-submitter cannot exceed global")]
    InvalidDailyLimits,
    #[error("lease TTL must be 1..=86400 seconds")]
    InvalidLeaseTtl,
    #[error("claiming is paused")]
    ClaimingPaused,
    #[error("global daily run limit reached")]
    GlobalDailyLimit,
    #[error("daily run limit reached for submitter {0}")]
    SubmitterDailyLimit(String),
    #[error("request is not claimable: {0}")]
    RequestNotClaimable(Uuid),
    #[error("request does not exist: {0}")]
    RequestNotFound(Uuid),
    #[error("request lease is held by another supervisor: {0}")]
    LeaseHeld(Uuid),
    #[error("lease fencing token exhausted")]
    FencingExhausted,
    #[error("run does not exist: {0}")]
    RunNotFound(Uuid),
    #[error("run id conflicts with another durable record: {0}")]
    RunConflict(Uuid),
    #[error("invalid {0}")]
    InvalidLabel(&'static str),
    #[error("artifact digest is malformed")]
    MalformedArtifact,
    #[error("usage telemetry exceeds ledger integer bounds")]
    UsageOverflow,
    #[error("side-effect attempt must be zero or one")]
    InvalidAttempt,
    #[error("side-effect idempotency key conflicts with another effect: {0}")]
    SideEffectConflict(String),
    #[error("invalid side-effect terminal status")]
    InvalidSideEffectStatus,
    #[error("side effect is not running: {0}")]
    SideEffectNotRunning(String),
    #[error("lease release did not match the held lease: {0}")]
    LeaseReleaseFailed(Uuid),
    #[error("control target does not match command")]
    InvalidControlTarget,
    #[error("control sweep limit is invalid")]
    InvalidControlLimit,
    #[error("control is not executing: {0}")]
    ControlNotExecuting(Uuid),
    #[error("awaited worker teardown failed for killed run: {0}")]
    KillCleanupFailed(Uuid),
    #[error("terminal run {run_id} cannot transition from {from} to {to}")]
    TerminalRunTransition {
        run_id: Uuid,
        from: String,
        to: String,
    },
    #[error("durable row does not match its typed contract")]
    MalformedRow,
}
