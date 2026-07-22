//! Validated, transactional run-record append.

use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Row};
use thiserror::Error;
use uuid::Uuid;

use crate::{InputError, require_lower_hex};

/// The eight provenance fields required on every run.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Provenance {
    pub model_id_hash: String,
    pub cli_version_hash: String,
    pub constitution_hash: String,
    pub rubric_hash: String,
    pub skill_hash: String,
    pub prompt_template_hash: String,
    pub verifier_binary_hash: String,
    pub base_tree_hash: String,
}

/// Minimum complete record appended when a run enters the queue.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RunRecord {
    pub id: Uuid,
    pub request_id: Uuid,
    pub base_sha: String,
    pub branch: String,
    pub lane: String,
    pub skill: String,
    pub provenance: Provenance,
}

/// A record whose identifiers and complete provenance have passed validation.
#[derive(Clone, Debug)]
pub struct ValidatedRunRecord {
    record: RunRecord,
    provenance_bytes: [[u8; 32]; 8],
}

impl ValidatedRunRecord {
    #[must_use]
    pub fn record(&self) -> &RunRecord {
        &self.record
    }
}

#[derive(Debug, Error)]
pub enum LedgerError {
    #[error(transparent)]
    Input(#[from] InputError),
    #[error("{0} must not be blank")]
    Blank(&'static str),
    #[error("database append failed")]
    Database(#[from] sqlx::Error),
    #[error("request does not exist: {0}")]
    RequestNotFound(Uuid),
}

/// Validate all fields before a caller can attempt persistence.
pub fn validate(record: RunRecord) -> Result<ValidatedRunRecord, LedgerError> {
    require_lower_hex("base_sha", &record.base_sha, 40)?;
    for (field, value) in [
        ("branch", record.branch.as_str()),
        ("lane", record.lane.as_str()),
        ("skill", record.skill.as_str()),
    ] {
        if value.trim().is_empty() {
            return Err(LedgerError::Blank(field));
        }
    }

    let values = [
        ("model_id_hash", &record.provenance.model_id_hash),
        ("cli_version_hash", &record.provenance.cli_version_hash),
        ("constitution_hash", &record.provenance.constitution_hash),
        ("rubric_hash", &record.provenance.rubric_hash),
        ("skill_hash", &record.provenance.skill_hash),
        (
            "prompt_template_hash",
            &record.provenance.prompt_template_hash,
        ),
        (
            "verifier_binary_hash",
            &record.provenance.verifier_binary_hash,
        ),
        ("base_tree_hash", &record.provenance.base_tree_hash),
    ];
    let mut provenance_bytes = [[0_u8; 32]; 8];
    for (index, (field, value)) in values.into_iter().enumerate() {
        require_lower_hex(field, value, 64)?;
        hex::decode_to_slice(value, &mut provenance_bytes[index])
            .expect("canonical SHA-256 hex has a fixed decoded length");
    }
    Ok(ValidatedRunRecord {
        record,
        provenance_bytes,
    })
}

/// Append the run and its first event atomically. Validation is deliberately
/// a separate constructor so malformed provenance cannot reach a connection.
pub async fn append(pool: &PgPool, run: &ValidatedRunRecord) -> Result<(), LedgerError> {
    let mut transaction = pool.begin().await?;
    let trace_id = sqlx::query("SELECT trace_id FROM factory.requests WHERE id = $1 FOR UPDATE")
        .bind(run.record.request_id)
        .fetch_optional(&mut *transaction)
        .await?
        .ok_or(LedgerError::RequestNotFound(run.record.request_id))?
        .try_get::<String, _>("trace_id")?;

    sqlx::query(
        r#"
        INSERT INTO factory.runs (
            id, request_id, base_sha, branch, lane, skill,
            model_id_hash, cli_version_hash, constitution_hash, rubric_hash,
            skill_hash, prompt_template_hash, verifier_binary_hash, base_tree_hash
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11, $12, $13, $14
        )
        "#,
    )
    .bind(run.record.id)
    .bind(run.record.request_id)
    .bind(&run.record.base_sha)
    .bind(&run.record.branch)
    .bind(&run.record.lane)
    .bind(&run.record.skill)
    .bind(run.provenance_bytes[0].as_slice())
    .bind(run.provenance_bytes[1].as_slice())
    .bind(run.provenance_bytes[2].as_slice())
    .bind(run.provenance_bytes[3].as_slice())
    .bind(run.provenance_bytes[4].as_slice())
    .bind(run.provenance_bytes[5].as_slice())
    .bind(run.provenance_bytes[6].as_slice())
    .bind(run.provenance_bytes[7].as_slice())
    .execute(&mut *transaction)
    .await?;

    sqlx::query(
        r#"
        INSERT INTO factory.events (
            request_id, run_id, event_type, from_state, to_state, trace_id
        ) VALUES ($1, $2, 'run.queued', NULL, 'queued', $3)
        "#,
    )
    .bind(run.record.request_id)
    .bind(run.record.id)
    .bind(trace_id)
    .execute(&mut *transaction)
    .await?;
    transaction.commit().await?;
    Ok(())
}
