//! PostgreSQL-backed state repository and domain operations.
//!
//! Callers depend on [`FactoryRepository`], not SQL. PostgreSQL is the only
//! phase-1 implementation; this boundary is about domain ownership, not
//! engine portability.

use std::{
    path::{Component, Path, PathBuf},
    time::Duration,
};

use sqlx::{PgPool, Postgres, Row, Transaction, postgres::PgPoolOptions};
use thiserror::Error;
use time::OffsetDateTime;
use uuid::Uuid;

use crate::RequestBody;

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
    /// Canonical ID; on a duplicate fingerprint this is the original ID.
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
                sqlx::query_scalar::<_, Uuid>(
                    "SELECT id FROM factory.requests WHERE fingerprint = $1",
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
                None,
                "request.queued",
                None,
                Some("queued"),
                request.trace_id.as_str(),
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
                None,
                "request.claimed",
                Some(&status),
                Some("claimed"),
                &trace_id,
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
            None,
            "request.claimed",
            Some(&status),
            Some("claimed"),
            &trace_id,
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
            None,
            "request.closed",
            Some(&status),
            Some("closed"),
            &trace_id,
        )
        .await?;
        transaction.commit().await?;
        Ok(true)
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

async fn append_event(
    transaction: &mut Transaction<'_, Postgres>,
    request_id: Uuid,
    run_id: Option<Uuid>,
    event_type: &str,
    from_state: Option<&str>,
    to_state: Option<&str>,
    trace_id: &str,
) -> Result<(), RepositoryError> {
    sqlx::query(
        r#"
        INSERT INTO factory.events (
            request_id, run_id, event_type, from_state, to_state, trace_id
        ) VALUES ($1, $2, $3, $4, $5, $6)
        "#,
    )
    .bind(request_id)
    .bind(run_id)
    .bind(event_type)
    .bind(from_state)
    .bind(to_state)
    .bind(trace_id)
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
    #[error("invalid domain input: {0}")]
    InvalidInput(#[from] DomainInputError),
    #[error("request {0} does not exist")]
    RequestNotFound(Uuid),
    #[error("request {request_id} is terminal ({status})")]
    TerminalRequest { request_id: Uuid, status: String },
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
