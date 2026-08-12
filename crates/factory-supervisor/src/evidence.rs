//! A89 evidence capture over the shared A104 child-spawn boundary.

use std::{
    collections::BTreeSet,
    time::{SystemTime, UNIX_EPOCH},
};

use serde::Deserialize;
use sha2::{Digest as _, Sha256};
use thiserror::Error;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    artifacts::{ArtifactError, ArtifactStore, StoredArtifact},
    child::{
        ChildContract, ChildError, ChildTerminal, ChildTerminalState, EvidenceAction,
        EvidenceContract, IsolatedChildSpawner, PreviewBearer,
    },
};

const MAX_DOM_BYTES: usize = 2_000_000;
const MAX_SCREENSHOT_BYTES: usize = 5_000_000;
const MAX_EXTRACT_BYTES: usize = 1024 * 1024;
const MAX_MANIFEST_BYTES: usize = 128 * 1024;

#[derive(Clone, Debug)]
pub struct EvidenceCapture {
    spawner: IsolatedChildSpawner,
    artifacts: ArtifactStore,
}

#[derive(Clone, Debug)]
pub struct EvidenceCaptureResult {
    pub artifacts: Vec<StoredArtifact>,
    pub terminal: ChildTerminal,
}

/// Validated child output retained outside the artifact tree until the
/// lifecycle has independently re-verified the preview and closed its lease.
#[derive(Clone, Debug)]
pub struct ValidatedEvidence {
    pub terminal: ChildTerminal,
    page: Vec<u8>,
    screenshot: Vec<u8>,
    extract: Vec<u8>,
    hashes: Vec<u8>,
    execution: Vec<u8>,
}

impl EvidenceCapture {
    #[must_use]
    pub fn new(spawner: IsolatedChildSpawner, artifacts: ArtifactStore) -> Self {
        Self { spawner, artifacts }
    }

    /// Spawn, await checked teardown, validate all untrusted returned bytes,
    /// and only then copy the bounded files into the artifact store.
    pub async fn capture(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        contract: EvidenceContract,
        bearer: PreviewBearer,
        cancellation: &CancellationToken,
    ) -> Result<Vec<StoredArtifact>, EvidenceError> {
        Ok(self
            .capture_with_execution(request_id, run_id, contract, bearer, cancellation)
            .await?
            .artifacts)
    }

    /// Qualification and the Session 14 lifecycle both need the checked
    /// terminal facts alongside the imported artifacts. Keep that proof on the
    /// same production path instead of reconstructing it from helper logs.
    pub async fn capture_with_execution(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        contract: EvidenceContract,
        bearer: PreviewBearer,
        cancellation: &CancellationToken,
    ) -> Result<EvidenceCaptureResult, EvidenceError> {
        let validated = self.execute(contract, bearer, cancellation).await?;
        self.import(request_id, run_id, "evidence-capture", None, validated)
            .await
    }

    /// Run and completely tear down the isolated child, validate every
    /// returned byte, and retain the bounded result in memory. Nothing has
    /// reached the durable artifact tree when this method returns.
    pub async fn execute(
        &self,
        contract: EvidenceContract,
        bearer: PreviewBearer,
        cancellation: &CancellationToken,
    ) -> Result<ValidatedEvidence, EvidenceError> {
        validate_contract(&contract)?;
        validate_bearer(&bearer)?;
        let capture_bytes = serde_json::to_vec(&contract)?;
        let bearer_sha256 = hex::encode(Sha256::digest(bearer.secret.as_bytes()));
        let capability_id_sha256 = hex::encode(Sha256::digest(bearer.capability_id.as_bytes()));
        let child = self
            .spawner
            .spawn(
                ChildContract::Evidence {
                    capture: contract.clone(),
                    bearer_sha256,
                    capability_id_sha256,
                },
                vec![("capture.json".to_owned(), capture_bytes)],
                Some(crate::child::ChildSecret::Preview(bearer.clone())),
                cancellation,
            )
            .await?;
        if child.terminal.state != ChildTerminalState::Completed {
            return Err(EvidenceError::FailClosed(child.terminal.state));
        }
        let isolation = &child.terminal.isolation;
        if !isolation.sibling_unreachable
            || !isolation.shared_scratch_unreachable
            || !isolation.credential_paths_unreachable
            || !isolation.postgres_socket_unreachable
            || !isolation.artifact_tree_unreachable
        {
            return Err(EvidenceError::FailClosed(
                ChildTerminalState::AuthorityProbeFailed,
            ));
        }
        if !isolation.metadata_unreachable || !isolation.private_fleet_unreachable {
            return Err(EvidenceError::FailClosed(
                ChildTerminalState::EgressProbeFailed,
            ));
        }
        let page = child.output("page.html")?;
        let screenshot = child.output("page.png")?;
        let extract = child.output("extract.json")?;
        let hashes = child.output("hashes.json")?;
        let execution = child.output("execution.json")?;
        for (name, bytes) in [
            ("page.html", page),
            ("page.png", screenshot),
            ("extract.json", extract),
            ("hashes.json", hashes),
            ("execution.json", execution),
            ("child-transcript.log", child.transcript.as_slice()),
        ] {
            if contains(bytes, bearer.secret.as_bytes())
                || contains(bytes, bearer.capability_id.as_bytes())
            {
                return Err(EvidenceError::BearerDisclosure(name.to_owned()));
            }
        }
        validate_execution_attestation(execution, &contract)?;
        validate_hashes(
            hashes,
            &contract,
            [
                ("page.html", page),
                ("page.png", screenshot),
                ("extract.json", extract),
                ("execution.json", execution),
            ],
        )?;

        Ok(ValidatedEvidence {
            terminal: child.terminal.clone(),
            page: page.to_vec(),
            screenshot: screenshot.to_vec(),
            extract: extract.to_vec(),
            hashes: hashes.to_vec(),
            execution: execution.to_vec(),
        })
    }

    /// Copy a previously validated and fully torn-down child result into the
    /// private artifact store. The caller chooses a fixed lifecycle stage so
    /// baseline and candidate packs remain independently recoverable.
    pub async fn import(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        stage: &str,
        name_prefix: Option<&str>,
        validated: ValidatedEvidence,
    ) -> Result<EvidenceCaptureResult, EvidenceError> {
        if name_prefix.is_some_and(|prefix| {
            prefix.is_empty()
                || prefix.len() > 32
                || !prefix
                    .bytes()
                    .all(|byte| byte.is_ascii_lowercase() || byte == b'-')
        }) {
            return Err(EvidenceError::InvalidContract);
        }
        let mut stored = Vec::with_capacity(5);
        let terminal = validated.terminal;
        for (name, kind, bytes, maximum) in [
            ("page.html", "evidence-dom", validated.page, MAX_DOM_BYTES),
            (
                "page.png",
                "evidence-screenshot",
                validated.screenshot,
                MAX_SCREENSHOT_BYTES,
            ),
            (
                "extract.json",
                "evidence-extract",
                validated.extract,
                MAX_EXTRACT_BYTES,
            ),
            (
                "hashes.json",
                "evidence-hashes",
                validated.hashes,
                MAX_MANIFEST_BYTES,
            ),
            (
                "execution.json",
                "evidence-execution",
                validated.execution,
                MAX_MANIFEST_BYTES,
            ),
        ] {
            let name =
                name_prefix.map_or_else(|| name.to_owned(), |prefix| format!("{prefix}-{name}"));
            stored.push(
                self.artifacts
                    .put(request_id, Some(run_id), stage, &name, kind, bytes, maximum)
                    .await?,
            );
        }
        Ok(EvidenceCaptureResult {
            artifacts: stored,
            terminal,
        })
    }
}

fn validate_contract(contract: &EvidenceContract) -> Result<(), EvidenceError> {
    if !valid_preview_url(&contract.allowed_url)
        || contract.expected_sha.len() != 40
        || !lower_hex(&contract.expected_sha)
        || contract.actions.is_empty()
        || contract.actions.len() > 16
        || contract.navigation_timeout_ms == 0
        || contract.navigation_timeout_ms > 30_000
        || contract.action_timeout_ms == 0
        || contract.action_timeout_ms > 10_000
        || contract.total_timeout_ms == 0
        || contract.total_timeout_ms > 60_000
        || contract.maximum_dom_bytes == 0
        || contract.maximum_dom_bytes > MAX_DOM_BYTES as u64
        || contract.maximum_screenshot_bytes == 0
        || contract.maximum_screenshot_bytes > MAX_SCREENSHOT_BYTES as u64
        || contract.maximum_extract_bytes == 0
        || contract.maximum_extract_bytes > MAX_EXTRACT_BYTES as u64
    {
        return Err(EvidenceError::InvalidContract);
    }
    let mut selectors = BTreeSet::new();
    for action in &contract.actions {
        match action {
            EvidenceAction::WaitFor { selector } | EvidenceAction::ExtractSelect { selector } => {
                if !valid_selector(selector) {
                    return Err(EvidenceError::InvalidContract);
                }
                selectors.insert(selector.clone());
            }
            EvidenceAction::Screenshot => {}
        }
    }
    if selectors.len() > 8 {
        return Err(EvidenceError::InvalidContract);
    }
    Ok(())
}

fn valid_preview_url(value: &str) -> bool {
    let Some(remainder) = value.strip_prefix("https://") else {
        return false;
    };
    let authority = remainder.split('/').next().unwrap_or_default();
    if authority.is_empty()
        || authority.contains(['@', ':', '#', '?'])
        || !remainder.contains('/')
        || remainder.contains('\\')
    {
        return false;
    }
    let Some(slot) = authority.strip_suffix(".preview.example.dev") else {
        return false;
    };
    matches!(slot.parse::<u8>(), Ok(1..=30))
}

fn valid_selector(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() >= 2
        && bytes.len() <= 65
        && bytes[0] == b'#'
        && bytes[1].is_ascii_alphabetic()
        && bytes[2..]
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-'))
}

fn validate_bearer(bearer: &PreviewBearer) -> Result<(), EvidenceError> {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| EvidenceError::Clock)?
        .as_secs();
    let now = i64::try_from(now).map_err(|_| EvidenceError::Clock)?;
    if bearer.capability_id.len() < 8
        || bearer.capability_id.len() > 128
        || !bearer
            .capability_id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-'))
        || bearer.secret.len() < 16
        || bearer.secret.len() > 8192
        || bearer.secret.contains(['\n', '\r'])
        || bearer.lease_id.len() != 32
        || !lower_hex(&bearer.lease_id)
        || bearer.expires_at_unix <= now
        || bearer.expires_at_unix > now + 300
    {
        return Err(EvidenceError::InvalidBearer);
    }
    Ok(())
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ExecutionManifest {
    schema_version: u16,
    allowed_url: String,
    expected_sha: String,
    final_url: String,
    redirects: u16,
    cross_origin_requests: u16,
    popup_attempts: u16,
    download_attempts: u16,
    bearer_disclosures: u16,
}

// These are observations by the fixed, reviewed controller. This validates
// their typed attestation; independent supervisor checks cover returned bytes,
// policy identity, authority probes, teardown, and capability-bound SHA.
fn validate_execution_attestation(
    bytes: &[u8],
    contract: &EvidenceContract,
) -> Result<(), EvidenceError> {
    let manifest: ExecutionManifest = serde_json::from_slice(bytes)?;
    if manifest.schema_version != 1
        || manifest.allowed_url != contract.allowed_url
        || manifest.expected_sha != contract.expected_sha
        || manifest.final_url != contract.allowed_url
        || manifest.redirects != 0
        || manifest.cross_origin_requests != 0
        || manifest.popup_attempts != 0
        || manifest.download_attempts != 0
        || manifest.bearer_disclosures != 0
    {
        return Err(EvidenceError::InvalidExecution);
    }
    Ok(())
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct HashManifest {
    schema_version: u16,
    expected_sha: String,
    artifacts: Vec<HashClaim>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct HashClaim {
    name: String,
    sha256: String,
    bytes: u64,
}

fn validate_hashes<'a>(
    bytes: &[u8],
    contract: &EvidenceContract,
    actual: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<(), EvidenceError> {
    let manifest: HashManifest = serde_json::from_slice(bytes)?;
    let actual = actual.into_iter().collect::<Vec<_>>();
    if manifest.schema_version != 1
        || manifest.expected_sha != contract.expected_sha
        || manifest.artifacts.len() != actual.len()
    {
        return Err(EvidenceError::InvalidHashes);
    }
    for (name, artifact) in actual {
        let Some(claim) = manifest.artifacts.iter().find(|claim| claim.name == name) else {
            return Err(EvidenceError::InvalidHashes);
        };
        if claim.sha256 != hex::encode(Sha256::digest(artifact))
            || claim.bytes != u64::try_from(artifact.len()).map_err(|_| EvidenceError::Length)?
        {
            return Err(EvidenceError::InvalidHashes);
        }
    }
    Ok(())
}

fn contains(haystack: &[u8], needle: &[u8]) -> bool {
    !needle.is_empty()
        && haystack
            .windows(needle.len())
            .any(|window| window == needle)
}

fn lower_hex(value: &str) -> bool {
    value
        .bytes()
        .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

#[derive(Debug, Error)]
pub enum EvidenceError {
    #[error("evidence contract is outside the fixed helper grammar")]
    InvalidContract,
    #[error("preview bearer is malformed, expired, or not short-lived")]
    InvalidBearer,
    #[error("system clock cannot represent the preview bearer window")]
    Clock,
    #[error("isolated evidence child failed closed as {0:?}")]
    FailClosed(ChildTerminalState),
    #[error("evidence child disclosed the bearer through {0}")]
    BearerDisclosure(String),
    #[error("evidence execution manifest is inconsistent")]
    InvalidExecution,
    #[error("evidence hash manifest is inconsistent")]
    InvalidHashes,
    #[error("evidence length cannot be represented")]
    Length,
    #[error("evidence child failed: {0}")]
    Child(#[from] ChildError),
    #[error("evidence JSON failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("evidence artifact import failed: {0}")]
    Artifact(#[from] ArtifactError),
}

#[cfg(test)]
mod tests {
    use super::{valid_preview_url, valid_selector};

    #[test]
    fn evidence_url_is_one_numbered_https_preview_origin() {
        assert!(valid_preview_url(
            "https://1.preview.example.dev/mfieldbook/leads/assign"
        ));
        assert!(valid_preview_url("https://30.preview.example.dev/"));
        for rejected in [
            "http://1.preview.example.dev/",
            "https://0.preview.example.dev/",
            "https://31.preview.example.dev/",
            "https://user@1.preview.example.dev/",
            "https://1.preview.example.dev:443/",
            "https://1.preview.example.dev.evil.example/",
        ] {
            assert!(!valid_preview_url(rejected), "{rejected}");
        }
    }

    #[test]
    fn selector_grammar_has_no_css_expression_surface() {
        assert!(valid_selector("#sales_person_id"));
        for rejected in ["sales_person_id", "#", "#1id", "#id img", "#id[href]"] {
            assert!(!valid_selector(rejected), "{rejected}");
        }
    }
}
