//! Narrow PostgreSQL surface for the dashboard.
//!
//! This module intentionally has no transition, triage, cap, verifier, or
//! publisher operation. PostgreSQL grants enforce the same boundary if a
//! handler is bypassed and the role is used directly.

use std::{path::PathBuf, time::Duration};

use factory_core::{
    auth::AccountRole,
    schema::{SchemaCatalog, introspect},
    state::{NewRequest, RequestCreated},
};
use serde::Serialize;
use serde_json::Value;
use sqlx::{PgPool, Row, postgres::PgPoolOptions};
use thiserror::Error;
use time::OffsetDateTime;
use uuid::Uuid;

pub const LOGIN_WINDOW: Duration = Duration::from_secs(15 * 60);
pub const LOGIN_PAIR_FAILURE_LIMIT: i64 = 5;
pub const LOGIN_ACCOUNT_FAILURE_LIMIT: i64 = 10;
pub const SESSION_IDLE: Duration = Duration::from_secs(30 * 60);
pub const SESSION_ABSOLUTE: Duration = Duration::from_secs(8 * 60 * 60);
pub const LOGIN_CHALLENGE_LIFETIME: Duration = Duration::from_secs(10 * 60);
pub const EVENTS_BATCH_LIMIT: i64 = 1_000;

#[derive(Clone, Debug)]
pub struct DashboardStore {
    pool: PgPool,
}

#[derive(Clone, Debug)]
pub struct UserRecord {
    pub id: Uuid,
    pub username: String,
    pub display_name: String,
    pub password_hash: String,
    pub role: AccountRole,
    pub enabled: bool,
    pub password_reset_required: bool,
    pub session_version: i64,
}

#[derive(Clone, Debug)]
pub struct Principal {
    pub id: Uuid,
    pub username: String,
    pub display_name: String,
    pub role: AccountRole,
    pub csrf_hash: [u8; 32],
    pub idle_expires_at: OffsetDateTime,
    pub absolute_expires_at: OffsetDateTime,
}

#[derive(Clone, Debug, Serialize)]
pub struct RequestSummary {
    pub id: Uuid,
    pub source: String,
    pub status: String,
    pub received_at: OffsetDateTime,
    pub run_state: Option<String>,
    pub event_count: i64,
}

#[derive(Clone, Debug)]
pub struct RequestRecord {
    pub id: Uuid,
    pub source: String,
    pub body: String,
    pub status: String,
    pub received_at: OffsetDateTime,
}

#[derive(Clone, Debug, Serialize)]
pub struct RunRecord {
    pub id: Uuid,
    pub state: String,
    pub lane: String,
    pub skill: String,
    pub branch: String,
    pub queued_at: OffsetDateTime,
    pub started_at: Option<OffsetDateTime>,
    pub finished_at: Option<OffsetDateTime>,
}

#[derive(Clone, Debug, Serialize)]
pub struct EventRecord {
    pub id: i64,
    pub request_id: Uuid,
    pub run_id: Option<Uuid>,
    pub event_type: String,
    pub from_state: Option<String>,
    pub to_state: Option<String>,
    pub trace_id: String,
    pub payload: Value,
    pub occurred_at: OffsetDateTime,
}

#[derive(Clone, Debug, Serialize)]
pub struct PullRequestRecord {
    pub number: i32,
    pub state: Option<String>,
    pub is_draft: Option<bool>,
    pub html_url: Option<String>,
    pub ci_state: String,
    pub review_state: String,
}

#[derive(Clone, Debug)]
pub struct RequestDetail {
    pub request: RequestRecord,
    pub runs: Vec<RunRecord>,
    pub events: Vec<EventRecord>,
    pub pulls: Vec<PullRequestRecord>,
    pub artifacts: Vec<ArtifactSummary>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ActiveRun {
    pub request_id: Uuid,
    pub run_id: Uuid,
    pub state: String,
}

#[derive(Clone, Debug)]
pub struct ArtifactRecord {
    pub relative_path: PathBuf,
    pub sha256: [u8; 32],
}

#[derive(Clone, Debug)]
pub struct ArtifactSummary {
    pub run_id: Uuid,
    pub relative_path: PathBuf,
    pub kind: String,
    pub created_at: OffsetDateTime,
}

impl DashboardStore {
    pub async fn connect(database_url: &str) -> Result<Self, StoreError> {
        let pool = PgPoolOptions::new()
            .max_connections(10)
            .acquire_timeout(Duration::from_secs(10))
            .connect(database_url)
            .await?;
        Ok(Self { pool })
    }

    #[must_use]
    pub fn from_pool(pool: PgPool) -> Self {
        Self { pool }
    }

    #[must_use]
    pub fn pool(&self) -> &PgPool {
        &self.pool
    }

    pub async fn close(self) {
        self.pool.close().await;
    }

    pub async fn create_login_challenge(
        &self,
        token_hash: &[u8; 32],
        csrf_hash: &[u8; 32],
    ) -> Result<(), StoreError> {
        sqlx::query(
            r#"
            INSERT INTO factory.login_challenges (
                token_hash, csrf_hash, expires_at
            ) VALUES (
                $1, $2, clock_timestamp() + make_interval(secs => $3)
            )
            "#,
        )
        .bind(token_hash.as_slice())
        .bind(csrf_hash.as_slice())
        .bind(duration_seconds(LOGIN_CHALLENGE_LIFETIME)?)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn consume_login_challenge(
        &self,
        token_hash: &[u8; 32],
        csrf_hash: &[u8; 32],
    ) -> Result<bool, StoreError> {
        let affected = sqlx::query(
            r#"
            UPDATE factory.login_challenges
            SET used_at=clock_timestamp()
            WHERE token_hash=$1
              AND csrf_hash=$2
              AND used_at IS NULL
              AND expires_at > clock_timestamp()
            "#,
        )
        .bind(token_hash.as_slice())
        .bind(csrf_hash.as_slice())
        .execute(&self.pool)
        .await?
        .rows_affected();
        Ok(affected == 1)
    }

    pub async fn login_is_throttled(
        &self,
        username: &str,
        client_key: &str,
    ) -> Result<bool, StoreError> {
        let row = sqlx::query(
            r#"
            WITH recent AS (
                SELECT succeeded, client_key
                FROM factory.login_attempts
                WHERE username=$1
                  AND occurred_at >
                      clock_timestamp() - make_interval(secs => $3)
            )
            SELECT
                count(*) FILTER (
                    WHERE NOT succeeded AND client_key=$2
                )::bigint AS pair_failures,
                count(*) FILTER (
                    WHERE NOT succeeded
                )::bigint AS account_failures
            FROM recent
            "#,
        )
        .bind(username)
        .bind(client_key)
        .bind(duration_seconds(LOGIN_WINDOW)?)
        .fetch_one(&self.pool)
        .await?;
        Ok(
            row.try_get::<i64, _>("pair_failures")? >= LOGIN_PAIR_FAILURE_LIMIT
                || row.try_get::<i64, _>("account_failures")? >= LOGIN_ACCOUNT_FAILURE_LIMIT,
        )
    }

    pub async fn user_for_login(&self, username: &str) -> Result<Option<UserRecord>, StoreError> {
        let row = sqlx::query(
            r#"
            SELECT
                id, username, display_name, password_hash, role::text AS role,
                enabled, password_reset_required, session_version
            FROM factory.users
            WHERE username=$1
            "#,
        )
        .bind(username)
        .fetch_optional(&self.pool)
        .await?;
        row.map(user_from_row).transpose()
    }

    pub async fn record_login_failure(
        &self,
        user_id: Option<Uuid>,
        username: &str,
        client_key: &str,
        throttled: bool,
    ) -> Result<(), StoreError> {
        let mut transaction = self.pool.begin().await?;
        sqlx::query(
            "INSERT INTO factory.login_attempts (username,client_key,succeeded) VALUES ($1,$2,false)",
        )
        .bind(username)
        .bind(client_key)
        .execute(&mut *transaction)
        .await?;
        sqlx::query(
            "INSERT INTO factory.audit_events (user_id,action,subject,client_key,metadata) VALUES ($1,$2,$3,$4,$5)",
        )
        .bind(user_id)
        .bind(if throttled {
            "login.throttled"
        } else {
            "login.failed"
        })
        .bind(username)
        .bind(client_key)
        .bind(serde_json::json!({"throttled": throttled}))
        .execute(&mut *transaction)
        .await?;
        transaction.commit().await?;
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    pub async fn create_session(
        &self,
        user: &UserRecord,
        token_hash: &[u8; 32],
        csrf_hash: &[u8; 32],
        prior_token_hash: Option<&[u8; 32]>,
        client_key: &str,
    ) -> Result<OffsetDateTime, StoreError> {
        let idle_seconds = duration_seconds(SESSION_IDLE)?;
        let absolute_seconds = duration_seconds(SESSION_ABSOLUTE)?;
        let mut transaction = self.pool.begin().await?;
        if let Some(prior) = prior_token_hash {
            sqlx::query(
                "UPDATE factory.sessions SET revoked_at=COALESCE(revoked_at,clock_timestamp()) WHERE token_hash=$1",
            )
            .bind(prior.as_slice())
            .execute(&mut *transaction)
            .await?;
        }
        let absolute_expires_at: OffsetDateTime = sqlx::query_scalar(
            r#"
            INSERT INTO factory.sessions (
                token_hash, user_id, csrf_hash, session_version,
                idle_expires_at, absolute_expires_at
            ) VALUES (
                $1, $2, $3, $4,
                clock_timestamp() + make_interval(secs => $5),
                clock_timestamp() + make_interval(secs => $6)
            )
            RETURNING absolute_expires_at
            "#,
        )
        .bind(token_hash.as_slice())
        .bind(user.id)
        .bind(csrf_hash.as_slice())
        .bind(user.session_version)
        .bind(idle_seconds)
        .bind(absolute_seconds)
        .fetch_one(&mut *transaction)
        .await?;
        sqlx::query(
            "INSERT INTO factory.login_attempts (username,client_key,succeeded) VALUES ($1,$2,true)",
        )
        .bind(&user.username)
        .bind(client_key)
        .execute(&mut *transaction)
        .await?;
        sqlx::query(
            "INSERT INTO factory.audit_events (user_id,action,subject,client_key) VALUES ($1,'login.succeeded',$2,$3)",
        )
        .bind(user.id)
        .bind(&user.username)
        .bind(client_key)
        .execute(&mut *transaction)
        .await?;
        transaction.commit().await?;
        Ok(absolute_expires_at)
    }

    pub async fn authenticate(
        &self,
        token_hash: &[u8; 32],
    ) -> Result<Option<Principal>, StoreError> {
        let row = sqlx::query(
            r#"
            UPDATE factory.sessions AS session
            SET
                last_seen_at=clock_timestamp(),
                idle_expires_at=LEAST(
                    session.absolute_expires_at,
                    clock_timestamp() + make_interval(secs => $2)
                )
            FROM factory.users AS account
            WHERE session.token_hash=$1
              AND session.user_id=account.id
              AND session.revoked_at IS NULL
              AND session.idle_expires_at > clock_timestamp()
              AND session.absolute_expires_at > clock_timestamp()
              AND account.enabled
              AND NOT account.password_reset_required
              AND session.session_version=account.session_version
            RETURNING
                account.id, account.username, account.display_name,
                account.role::text AS role, session.csrf_hash,
                session.idle_expires_at, session.absolute_expires_at
            "#,
        )
        .bind(token_hash.as_slice())
        .bind(duration_seconds(SESSION_IDLE)?)
        .fetch_optional(&self.pool)
        .await?;
        row.map(principal_from_row).transpose()
    }

    pub async fn revoke_session(
        &self,
        token_hash: &[u8; 32],
        principal: &Principal,
        client_key: &str,
    ) -> Result<(), StoreError> {
        let mut transaction = self.pool.begin().await?;
        sqlx::query(
            "UPDATE factory.sessions SET revoked_at=COALESCE(revoked_at,clock_timestamp()) WHERE token_hash=$1",
        )
        .bind(token_hash.as_slice())
        .execute(&mut *transaction)
        .await?;
        append_audit(
            &mut transaction,
            principal.id,
            "logout",
            &principal.username,
            client_key,
            serde_json::json!({}),
        )
        .await?;
        transaction.commit().await?;
        Ok(())
    }

    pub async fn submit_request(
        &self,
        request: &NewRequest,
        principal: &Principal,
        client_key: &str,
    ) -> Result<RequestCreated, StoreError> {
        let mut transaction = self.pool.begin().await?;
        let inserted_id = sqlx::query_scalar::<_, Uuid>(
            r#"
            INSERT INTO factory.requests (id, fingerprint, source, body, trace_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (fingerprint) DO NOTHING
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
                sqlx::query_scalar("SELECT id FROM factory.requests WHERE fingerprint=$1")
                    .bind(request.fingerprint.as_bytes().as_slice())
                    .fetch_one(&mut *transaction)
                    .await?
            }
        };
        append_audit(
            &mut transaction,
            principal.id,
            if inserted {
                "submission.created"
            } else {
                "submission.deduplicated"
            },
            &id.to_string(),
            client_key,
            serde_json::json!({"source": request.source}),
        )
        .await?;
        transaction.commit().await?;
        Ok(RequestCreated { id, inserted })
    }

    pub async fn enqueue_control(
        &self,
        command: &str,
        target_run_id: Option<Uuid>,
        principal: &Principal,
        client_key: &str,
    ) -> Result<Uuid, StoreError> {
        if !matches!(command, "pause" | "resume" | "kill" | "full_stop")
            || ((command == "kill") != target_run_id.is_some())
        {
            return Err(StoreError::InvalidControl);
        }
        let id = Uuid::new_v4();
        let mut transaction = self.pool.begin().await?;
        sqlx::query(
            "INSERT INTO factory.controls (id,command,target_run_id,requested_by,reason) VALUES ($1,$2,$3,$4,$5)",
        )
        .bind(id)
        .bind(command)
        .bind(target_run_id)
        .bind(&principal.username)
        .bind(format!("factory dashboard {command}"))
        .execute(&mut *transaction)
        .await?;
        append_audit(
            &mut transaction,
            principal.id,
            "control.queued",
            &id.to_string(),
            client_key,
            serde_json::json!({
                "command": command,
                "target_run_id": target_run_id,
            }),
        )
        .await?;
        transaction.commit().await?;
        Ok(id)
    }

    pub async fn enqueue_reconcile(
        &self,
        request_id: Uuid,
        principal: &Principal,
        client_key: &str,
    ) -> Result<Uuid, StoreError> {
        let id = Uuid::new_v4();
        let mut transaction = self.pool.begin().await?;
        sqlx::query(
            "INSERT INTO factory.reconcile_requests (id,request_id,requested_by) VALUES ($1,$2,$3)",
        )
        .bind(id)
        .bind(request_id)
        .bind(principal.id)
        .execute(&mut *transaction)
        .await?;
        append_audit(
            &mut transaction,
            principal.id,
            "reconcile.queued",
            &request_id.to_string(),
            client_key,
            serde_json::json!({"reconcile_id": id}),
        )
        .await?;
        transaction.commit().await?;
        Ok(id)
    }

    pub async fn requests(&self) -> Result<Vec<RequestSummary>, StoreError> {
        Ok(sqlx::query(
            r#"
            SELECT
                request.id, request.source, request.status::text AS status,
                request.received_at,
                latest_run.state::text AS run_state,
                (SELECT count(*) FROM factory.events event
                 WHERE event.request_id=request.id)::bigint AS event_count
            FROM factory.requests request
            LEFT JOIN LATERAL (
                SELECT state
                FROM factory.runs
                WHERE request_id=request.id
                ORDER BY queued_at DESC
                LIMIT 1
            ) latest_run ON true
            ORDER BY request.received_at DESC, request.id
            LIMIT 250
            "#,
        )
        .fetch_all(&self.pool)
        .await?
        .into_iter()
        .map(|row| {
            Ok(RequestSummary {
                id: row.try_get("id")?,
                source: row.try_get("source")?,
                status: row.try_get("status")?,
                received_at: row.try_get("received_at")?,
                run_state: row.try_get("run_state")?,
                event_count: row.try_get("event_count")?,
            })
        })
        .collect::<Result<Vec<_>, sqlx::Error>>()?)
    }

    pub async fn request_status(&self, request_id: Uuid) -> Result<String, StoreError> {
        Ok(
            sqlx::query_scalar("SELECT status::text FROM factory.requests WHERE id=$1")
                .bind(request_id)
                .fetch_one(&self.pool)
                .await?,
        )
    }

    pub async fn request_exists(&self, request_id: Uuid) -> Result<bool, StoreError> {
        Ok(
            sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM factory.requests WHERE id=$1)")
                .bind(request_id)
                .fetch_one(&self.pool)
                .await?,
        )
    }

    pub async fn request_detail(
        &self,
        request_id: Uuid,
    ) -> Result<Option<RequestDetail>, StoreError> {
        let request = sqlx::query(
            "SELECT id,source,body,status::text AS status,received_at FROM factory.requests WHERE id=$1",
        )
        .bind(request_id)
        .fetch_optional(&self.pool)
        .await?
        .map(|row| {
            Ok::<_, sqlx::Error>(RequestRecord {
                id: row.try_get("id")?,
                source: row.try_get("source")?,
                body: row.try_get("body")?,
                status: row.try_get("status")?,
                received_at: row.try_get("received_at")?,
            })
        })
        .transpose()?;
        let Some(request) = request else {
            return Ok(None);
        };
        let runs = self.runs_for_request(request_id).await?;
        let events = self.events_after(request_id, 0).await?;
        let pulls = sqlx::query(
            "SELECT number,state,is_draft,html_url,ci_state,review_state FROM factory.pr_state WHERE request_id=$1 ORDER BY number",
        )
        .bind(request_id)
        .fetch_all(&self.pool)
        .await?
        .into_iter()
        .map(|row| {
            Ok(PullRequestRecord {
                number: row.try_get("number")?,
                state: row.try_get("state")?,
                is_draft: row.try_get("is_draft")?,
                html_url: row.try_get("html_url")?,
                ci_state: row.try_get("ci_state")?,
                review_state: row.try_get("review_state")?,
            })
        })
        .collect::<Result<Vec<_>, sqlx::Error>>()?;
        let artifacts = sqlx::query(
            r#"
            SELECT run_id,path,kind,created_at
            FROM factory.artifacts
            WHERE request_id=$1
              AND run_id IS NOT NULL
              AND deleted_at IS NULL
              AND (expires_at IS NULL OR expires_at > clock_timestamp())
            ORDER BY created_at,id
            "#,
        )
        .bind(request_id)
        .fetch_all(&self.pool)
        .await?
        .into_iter()
        .map(|row| {
            Ok(ArtifactSummary {
                run_id: row.try_get("run_id")?,
                relative_path: PathBuf::from(row.try_get::<String, _>("path")?),
                kind: row.try_get("kind")?,
                created_at: row.try_get("created_at")?,
            })
        })
        .collect::<Result<Vec<_>, sqlx::Error>>()?;
        Ok(Some(RequestDetail {
            request,
            runs,
            events,
            pulls,
            artifacts,
        }))
    }

    pub async fn events_after(
        &self,
        request_id: Uuid,
        last_id: i64,
    ) -> Result<Vec<EventRecord>, StoreError> {
        Ok(sqlx::query(
            r#"
            SELECT
                id, request_id, run_id, event_type, from_state, to_state,
                trace_id, payload, occurred_at
            FROM factory.events
            WHERE request_id=$1 AND id>$2
            ORDER BY id
            LIMIT $3
            "#,
        )
        .bind(request_id)
        .bind(last_id)
        .bind(EVENTS_BATCH_LIMIT)
        .fetch_all(&self.pool)
        .await?
        .into_iter()
        .map(event_from_row)
        .collect::<Result<Vec<_>, sqlx::Error>>()?)
    }

    pub async fn active_runs(&self) -> Result<Vec<ActiveRun>, StoreError> {
        Ok(sqlx::query(
            r#"
            SELECT request_id,id AS run_id,state::text AS state
            FROM factory.runs
            WHERE state NOT IN (
                'ready_for_review', 'dry_run_complete', 'failed', 'killed',
                'closed', 'escalated'
            )
            ORDER BY queued_at,id
            "#,
        )
        .fetch_all(&self.pool)
        .await?
        .into_iter()
        .map(|row| {
            Ok(ActiveRun {
                request_id: row.try_get("request_id")?,
                run_id: row.try_get("run_id")?,
                state: row.try_get("state")?,
            })
        })
        .collect::<Result<Vec<_>, sqlx::Error>>()?)
    }

    pub async fn schema(&self) -> Result<SchemaCatalog, StoreError> {
        Ok(introspect(&self.pool).await?)
    }

    pub async fn artifact(
        &self,
        run_id: Uuid,
        requested_name: &str,
    ) -> Result<Option<ArtifactRecord>, StoreError> {
        let rows = sqlx::query(
            r#"
            SELECT path,sha256
            FROM factory.artifacts
            WHERE run_id=$1
              AND deleted_at IS NULL
              AND (expires_at IS NULL OR expires_at > clock_timestamp())
            "#,
        )
        .bind(run_id)
        .fetch_all(&self.pool)
        .await?;
        for row in rows {
            let relative_path = PathBuf::from(row.try_get::<String, _>("path")?);
            if relative_path.file_name().and_then(|name| name.to_str()) == Some(requested_name) {
                let sha256: Vec<u8> = row.try_get("sha256")?;
                return Ok(Some(ArtifactRecord {
                    relative_path,
                    sha256: digest_array(sha256)?,
                }));
            }
        }
        Ok(None)
    }

    async fn runs_for_request(&self, request_id: Uuid) -> Result<Vec<RunRecord>, StoreError> {
        Ok(sqlx::query(
            "SELECT id,state::text AS state,lane,skill,branch,queued_at,started_at,finished_at FROM factory.runs WHERE request_id=$1 ORDER BY queued_at,id",
        )
        .bind(request_id)
        .fetch_all(&self.pool)
        .await?
        .into_iter()
        .map(|row| {
            Ok(RunRecord {
                id: row.try_get("id")?,
                state: row.try_get("state")?,
                lane: row.try_get("lane")?,
                skill: row.try_get("skill")?,
                branch: row.try_get("branch")?,
                queued_at: row.try_get("queued_at")?,
                started_at: row.try_get("started_at")?,
                finished_at: row.try_get("finished_at")?,
            })
        })
        .collect::<Result<Vec<_>, sqlx::Error>>()?)
    }
}

fn user_from_row(row: sqlx::postgres::PgRow) -> Result<UserRecord, StoreError> {
    Ok(UserRecord {
        id: row.try_get("id")?,
        username: row.try_get("username")?,
        display_name: row.try_get("display_name")?,
        password_hash: row.try_get("password_hash")?,
        role: AccountRole::parse(&row.try_get::<String, _>("role")?)?,
        enabled: row.try_get("enabled")?,
        password_reset_required: row.try_get("password_reset_required")?,
        session_version: row.try_get("session_version")?,
    })
}

fn principal_from_row(row: sqlx::postgres::PgRow) -> Result<Principal, StoreError> {
    Ok(Principal {
        id: row.try_get("id")?,
        username: row.try_get("username")?,
        display_name: row.try_get("display_name")?,
        role: AccountRole::parse(&row.try_get::<String, _>("role")?)?,
        csrf_hash: digest_array(row.try_get("csrf_hash")?)?,
        idle_expires_at: row.try_get("idle_expires_at")?,
        absolute_expires_at: row.try_get("absolute_expires_at")?,
    })
}

fn event_from_row(row: sqlx::postgres::PgRow) -> Result<EventRecord, sqlx::Error> {
    Ok(EventRecord {
        id: row.try_get("id")?,
        request_id: row.try_get("request_id")?,
        run_id: row.try_get("run_id")?,
        event_type: row.try_get("event_type")?,
        from_state: row.try_get("from_state")?,
        to_state: row.try_get("to_state")?,
        trace_id: row.try_get("trace_id")?,
        payload: row.try_get("payload")?,
        occurred_at: row.try_get("occurred_at")?,
    })
}

async fn append_audit(
    transaction: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    user_id: Uuid,
    action: &str,
    subject: &str,
    client_key: &str,
    metadata: Value,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "INSERT INTO factory.audit_events (user_id,action,subject,client_key,metadata) VALUES ($1,$2,$3,$4,$5)",
    )
    .bind(user_id)
    .bind(action)
    .bind(subject)
    .bind(client_key)
    .bind(metadata)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

fn digest_array(value: Vec<u8>) -> Result<[u8; 32], StoreError> {
    value.try_into().map_err(|_| StoreError::MalformedDigest)
}

fn duration_seconds(duration: Duration) -> Result<i32, StoreError> {
    i32::try_from(duration.as_secs()).map_err(|_| StoreError::DurationOverflow)
}

#[derive(Debug, Error)]
pub enum StoreError {
    #[error("dashboard PostgreSQL operation failed: {0}")]
    Database(#[from] sqlx::Error),
    #[error("schema introspection failed: {0}")]
    Schema(#[from] factory_core::schema::SchemaError),
    #[error("factory account row has an invalid role: {0}")]
    Account(#[from] factory_core::auth::AuthError),
    #[error("database digest is not SHA-256")]
    MalformedDigest,
    #[error("configured duration exceeds PostgreSQL interval input")]
    DurationOverflow,
    #[error("dashboard control shape is invalid")]
    InvalidControl,
}
