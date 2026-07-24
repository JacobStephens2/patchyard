//! A104's single typed spawn boundary for no-authority child jobs.

use std::{
    collections::BTreeSet,
    fs,
    os::unix::fs::{MetadataExt as _, OpenOptionsExt as _, PermissionsExt as _},
    path::{Path, PathBuf},
    time::Duration,
};

use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use thiserror::Error;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::process::{ProcessError, ProcessSpec, run_bounded};

pub const MAX_CHILD_OUTPUT_BYTES: usize = 8 * 1024 * 1024;
const MAX_TERMINAL_BYTES: usize = 128 * 1024;
const MAX_CONTROL_OUTPUT_BYTES: usize = 64 * 1024;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ChildKind {
    Review,
    Evidence,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ChildTerminalState {
    Completed,
    RedirectBlocked,
    DnsBindingChanged,
    CrossOriginBlocked,
    PopupBlocked,
    DownloadBlocked,
    OutputLimitExceeded,
    BearerDisclosureBlocked,
    BrowserCrashed,
    AuthorityProbeFailed,
    EgressProbeFailed,
    ChildTimedOut,
    TeardownFailed,
    ContractRejected,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceAction {
    WaitFor { selector: String },
    ExtractSelect { selector: String },
    Screenshot,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EvidenceContract {
    pub allowed_url: String,
    pub expected_sha: String,
    pub actions: Vec<EvidenceAction>,
    pub navigation_timeout_ms: u64,
    pub action_timeout_ms: u64,
    pub total_timeout_ms: u64,
    pub maximum_dom_bytes: u64,
    pub maximum_screenshot_bytes: u64,
    pub maximum_extract_bytes: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreviewBearer {
    pub capability_id: String,
    pub lease_id: String,
    pub expires_at_unix: i64,
    pub secret: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum ChildContract {
    Review {
        workspace: String,
        reviewed_sha: String,
        packet_sha256: String,
        prompt_sha256: String,
        model: String,
        effort: String,
        harness: String,
        provider: String,
    },
    Evidence {
        capture: EvidenceContract,
        bearer_sha256: String,
        capability_id_sha256: String,
    },
}

impl ChildContract {
    #[must_use]
    pub fn kind(&self) -> ChildKind {
        match self {
            Self::Review { .. } => ChildKind::Review,
            Self::Evidence { .. } => ChildKind::Evidence,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChildRequest {
    pub schema_version: u16,
    pub job_id: Uuid,
    pub contract: ChildContract,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChildOutputClaim {
    pub name: String,
    pub sha256: String,
    pub bytes: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct IsolationFacts {
    pub sibling_unreachable: bool,
    pub shared_scratch_unreachable: bool,
    pub credential_paths_unreachable: bool,
    pub postgres_socket_unreachable: bool,
    pub artifact_tree_unreachable: bool,
    pub metadata_unreachable: bool,
    pub private_fleet_unreachable: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TeardownFacts {
    pub complete: bool,
    pub processes: u32,
    pub mounts: u32,
    pub namespaces: u32,
    pub secret_files: u32,
    pub staging_paths: u32,
    pub firewall_rules: u32,
    pub preview_capabilities: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChildTerminal {
    pub schema_version: u16,
    pub job_id: Uuid,
    pub kind: ChildKind,
    pub state: ChildTerminalState,
    pub request_sha256: String,
    pub network_policy_sha256: String,
    pub outputs: Vec<ChildOutputClaim>,
    pub isolation: IsolationFacts,
    pub teardown: TeardownFacts,
}

#[derive(Clone, Debug)]
pub struct ChildOutput {
    pub name: String,
    pub sha256: String,
    pub bytes: Vec<u8>,
}

#[derive(Clone, Debug)]
pub struct ChildExecution {
    pub terminal: ChildTerminal,
    pub outputs: Vec<ChildOutput>,
    pub transcript: Vec<u8>,
}

impl ChildExecution {
    pub fn output(&self, name: &str) -> Result<&[u8], ChildError> {
        self.outputs
            .iter()
            .find(|output| output.name == name)
            .map(|output| output.bytes.as_slice())
            .ok_or_else(|| ChildError::MissingOutput(name.to_owned()))
    }
}

#[derive(Clone, Debug)]
pub struct ChildSpawnConfig {
    pub spawn_program: PathBuf,
    pub cancel_program: PathBuf,
    pub staging_root: PathBuf,
    pub timeout: Duration,
}

#[derive(Clone, Debug)]
pub struct IsolatedChildSpawner {
    config: ChildSpawnConfig,
}

impl IsolatedChildSpawner {
    #[must_use]
    pub fn new(config: ChildSpawnConfig) -> Self {
        Self { config }
    }

    /// Cancel and remove every valid staging entry left by a previous daemon.
    ///
    /// Recovery runs before the daemon accepts work, so there cannot be a
    /// legitimate concurrent child. An unexpected entry fails startup closed
    /// instead of broadening cleanup beyond the UUID-only contract.
    pub async fn recover_orphans(&self) -> Result<usize, ChildError> {
        let mut entries = tokio::fs::read_dir(&self.config.staging_root).await?;
        let mut jobs = Vec::new();
        while let Some(entry) = entries.next_entry().await? {
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| ChildError::InvalidStagingEntry)?;
            let file_type = entry.file_type().await?;
            if !file_type.is_dir()
                || file_type.is_symlink()
                || name.len() != 32
                || !name
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
            {
                return Err(ChildError::InvalidStagingEntry);
            }
            jobs.push(entry.path());
        }
        drop(entries);
        for job in &jobs {
            self.cancel_and_remove(job).await?;
        }
        Ok(jobs.len())
    }

    pub async fn spawn(
        &self,
        contract: ChildContract,
        inputs: Vec<(String, Vec<u8>)>,
        bearer: Option<PreviewBearer>,
        cancellation: &CancellationToken,
    ) -> Result<ChildExecution, ChildError> {
        let job_id = Uuid::new_v4();
        let request = ChildRequest {
            schema_version: 1,
            job_id,
            contract,
        };
        let job_directory = self.config.staging_root.join(job_id.simple().to_string());
        let request_bytes = serde_json::to_vec(&request)?;
        let request_sha256 = hex::encode(Sha256::digest(&request_bytes));
        create_job(job_directory.clone(), request_bytes, inputs, bearer).await?;

        let mut spec = ProcessSpec::new(&self.config.spawn_program);
        spec.args = vec![job_directory.clone().into_os_string()];
        spec.timeout = self.config.timeout;
        spec.output_limit = MAX_CONTROL_OUTPUT_BYTES;
        let process_result = run_bounded(&spec, cancellation).await;
        if let Err(process_error) = process_result {
            let cleanup_result = self.cancel_and_remove(&job_directory).await;
            return match cleanup_result {
                Ok(()) => Err(process_error.into()),
                Err(cleanup_error) => Err(ChildError::Cleanup {
                    operation: "cancel after failed child spawn",
                    source: Box::new(cleanup_error),
                }),
            };
        }
        let process = process_result.expect("checked above");
        let result = self
            .read_execution(&job_directory, job_id, &request, &request_sha256)
            .await;
        let cleanup = remove_job(job_directory).await;
        match (result, cleanup) {
            (Ok(mut execution), Ok(())) => {
                execution.transcript = process.transcript();
                Ok(execution)
            }
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(ChildError::Cleanup {
                operation: "remove completed child staging",
                source: Box::new(error),
            }),
        }
    }

    async fn read_execution(
        &self,
        job_directory: &Path,
        job_id: Uuid,
        request: &ChildRequest,
        request_sha256: &str,
    ) -> Result<ChildExecution, ChildError> {
        let terminal_bytes =
            read_regular_bounded(job_directory.join("terminal.json"), MAX_TERMINAL_BYTES).await?;
        let terminal: ChildTerminal = serde_json::from_slice(&terminal_bytes)?;
        validate_terminal(&terminal, job_id, request.contract.kind(), request_sha256)?;
        if job_directory.join("secret").exists() {
            return Err(ChildError::SecretResidue);
        }
        let mut outputs = Vec::with_capacity(terminal.outputs.len());
        for claim in &terminal.outputs {
            validate_output_name(request.contract.kind(), &claim.name)?;
            let maximum = output_maximum(request.contract.kind(), &claim.name)?;
            let bytes =
                read_regular_bounded(job_directory.join("output").join(&claim.name), maximum)
                    .await?;
            let actual_sha256 = hex::encode(Sha256::digest(&bytes));
            if actual_sha256 != claim.sha256
                || u64::try_from(bytes.len()).map_err(|_| ChildError::LengthOverflow)?
                    != claim.bytes
            {
                return Err(ChildError::OutputDigest(claim.name.clone()));
            }
            outputs.push(ChildOutput {
                name: claim.name.clone(),
                sha256: actual_sha256,
                bytes,
            });
        }
        Ok(ChildExecution {
            terminal,
            outputs,
            transcript: Vec::new(),
        })
    }

    async fn cancel_and_remove(&self, job_directory: &Path) -> Result<(), ChildError> {
        let mut spec = ProcessSpec::new(&self.config.cancel_program);
        spec.args = vec![job_directory.as_os_str().to_owned()];
        spec.timeout = Duration::from_secs(30);
        spec.output_limit = MAX_CONTROL_OUTPUT_BYTES;
        let cleanup_token = CancellationToken::new();
        let output = run_bounded(&spec, &cleanup_token).await?;
        if output.code != 0 {
            return Err(ChildError::CancelExit(output.code));
        }
        remove_job(job_directory.to_path_buf()).await
    }
}

fn validate_terminal(
    terminal: &ChildTerminal,
    job_id: Uuid,
    kind: ChildKind,
    request_sha256: &str,
) -> Result<(), ChildError> {
    if terminal.schema_version != 1
        || terminal.job_id != job_id
        || terminal.kind != kind
        || terminal.request_sha256 != request_sha256
        || terminal.network_policy_sha256.len() != 64
        || !terminal
            .network_policy_sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        || terminal.outputs.len() > 8
    {
        return Err(ChildError::MalformedTerminal);
    }
    let mut names = BTreeSet::new();
    if terminal
        .outputs
        .iter()
        .any(|output| !names.insert(&output.name))
    {
        return Err(ChildError::MalformedTerminal);
    }
    let clean = &terminal.teardown;
    let zero_residue = clean.processes == 0
        && clean.mounts == 0
        && clean.namespaces == 0
        && clean.secret_files == 0
        && clean.staging_paths == 0
        && clean.firewall_rules == 0
        && clean.preview_capabilities == 0;
    if terminal.state == ChildTerminalState::TeardownFailed {
        if clean.complete && zero_residue {
            return Err(ChildError::MalformedTerminal);
        }
    } else if !clean.complete || !zero_residue {
        return Err(ChildError::TeardownIncomplete);
    }
    Ok(())
}

fn validate_output_name(kind: ChildKind, name: &str) -> Result<(), ChildError> {
    let allowed: &[&str] = match kind {
        ChildKind::Review => &["review.json", "transcript.log"],
        ChildKind::Evidence => &[
            "page.html",
            "page.png",
            "extract.json",
            "hashes.json",
            "execution.json",
        ],
    };
    if allowed.contains(&name) {
        Ok(())
    } else {
        Err(ChildError::UnexpectedOutput(name.to_owned()))
    }
}

fn output_maximum(kind: ChildKind, name: &str) -> Result<usize, ChildError> {
    match (kind, name) {
        (ChildKind::Review, "review.json") => Ok(1024 * 1024),
        (ChildKind::Review, "transcript.log") => Ok(MAX_CHILD_OUTPUT_BYTES),
        (ChildKind::Evidence, "page.html") => Ok(2_000_000),
        (ChildKind::Evidence, "page.png") => Ok(5_000_000),
        (ChildKind::Evidence, "extract.json") => Ok(1024 * 1024),
        (ChildKind::Evidence, "hashes.json" | "execution.json") => Ok(128 * 1024),
        _ => Err(ChildError::UnexpectedOutput(name.to_owned())),
    }
}

async fn create_job(
    job_directory: PathBuf,
    request: Vec<u8>,
    inputs: Vec<(String, Vec<u8>)>,
    bearer: Option<PreviewBearer>,
) -> Result<(), ChildError> {
    tokio::task::spawn_blocking(move || {
        let root = job_directory
            .parent()
            .ok_or_else(|| ChildIoError::UnsafeRoot(job_directory.clone()))?;
        let root_metadata = fs::symlink_metadata(root)?;
        if !root_metadata.is_dir()
            || root_metadata.file_type().is_symlink()
            || root_metadata.permissions().mode() & 0o7777 != 0o700
        {
            return Err(ChildIoError::UnsafeRoot(root.to_path_buf()));
        }
        fs::create_dir(&job_directory)?;
        fs::set_permissions(&job_directory, fs::Permissions::from_mode(0o700))?;
        let input_directory = job_directory.join("input");
        let output_directory = job_directory.join("output");
        fs::create_dir(&input_directory)?;
        fs::create_dir(&output_directory)?;
        fs::set_permissions(&input_directory, fs::Permissions::from_mode(0o700))?;
        fs::set_permissions(&output_directory, fs::Permissions::from_mode(0o700))?;
        write_new(&job_directory.join("request.json"), &request)?;
        let mut names = BTreeSet::new();
        for (name, bytes) in inputs {
            if !valid_input_name(&name) || !names.insert(name.clone()) {
                return Err(ChildIoError::UnsafeInputName(name));
            }
            write_new(&input_directory.join(&name), &bytes)?;
        }
        if let Some(bearer) = bearer {
            let secret_directory = job_directory.join("secret");
            fs::create_dir(&secret_directory)?;
            fs::set_permissions(&secret_directory, fs::Permissions::from_mode(0o700))?;
            write_new(
                &secret_directory.join("bearer.json"),
                &serde_json::to_vec(&bearer)?,
            )?;
        }
        let directory = fs::File::open(&job_directory)?;
        directory.sync_all()?;
        Ok::<(), ChildIoError>(())
    })
    .await
    .map_err(ChildError::Join)??;
    Ok(())
}

fn valid_input_name(name: &str) -> bool {
    matches!(name, "packet.json" | "prompt.md" | "capture.json")
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<(), ChildIoError> {
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true).mode(0o600);
    use std::io::Write as _;
    let mut file = options.open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}

async fn read_regular_bounded(path: PathBuf, maximum: usize) -> Result<Vec<u8>, ChildError> {
    tokio::task::spawn_blocking(move || {
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.is_file()
            || metadata.file_type().is_symlink()
            || metadata.nlink() != 1
            || metadata.permissions().mode() & 0o077 != 0
        {
            return Err(ChildIoError::UnsafeFile(path));
        }
        if metadata.len() > u64::try_from(maximum).unwrap_or(u64::MAX) {
            return Err(ChildIoError::TooLarge(path));
        }
        fs::read(path).map_err(ChildIoError::Io)
    })
    .await
    .map_err(ChildError::Join)?
    .map_err(ChildError::ChildIo)
}

async fn remove_job(path: PathBuf) -> Result<(), ChildError> {
    tokio::task::spawn_blocking(move || match fs::remove_dir_all(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error),
    })
    .await
    .map_err(ChildError::Join)??;
    Ok(())
}

#[derive(Debug, Error)]
pub enum ChildIoError {
    #[error("unsafe child input name: {0}")]
    UnsafeInputName(String),
    #[error("child staging root is not a private non-symlink directory: {0}")]
    UnsafeRoot(PathBuf),
    #[error("child file is not a private, single-link regular file: {0}")]
    UnsafeFile(PathBuf),
    #[error("child file exceeds its byte ceiling: {0}")]
    TooLarge(PathBuf),
    #[error("child JSON staging failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("child filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
}

#[derive(Debug, Error)]
pub enum ChildError {
    #[error("child JSON contract failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("child filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("child file contract failed: {0}")]
    ChildIo(#[from] ChildIoError),
    #[error("child subprocess failed: {0}")]
    Process(#[from] ProcessError),
    #[error("child blocking task failed: {0}")]
    Join(tokio::task::JoinError),
    #[error("child terminal manifest is malformed")]
    MalformedTerminal,
    #[error("child teardown is incomplete")]
    TeardownIncomplete,
    #[error("child left its tmpfs secret path behind")]
    SecretResidue,
    #[error("child output is not declared for this job kind: {0}")]
    UnexpectedOutput(String),
    #[error("child output is missing: {0}")]
    MissingOutput(String),
    #[error("child output digest or length differs: {0}")]
    OutputDigest(String),
    #[error("child output length cannot be represented")]
    LengthOverflow,
    #[error("isolated-child staging contains an invalid entry")]
    InvalidStagingEntry,
    #[error("child cancellation helper exited with status {0}")]
    CancelExit(i32),
    #[error("checked cleanup failed while trying to {operation}: {source}")]
    Cleanup {
        operation: &'static str,
        source: Box<ChildError>,
    },
}

#[cfg(test)]
mod tests {
    use super::{
        ChildKind, ChildOutputClaim, ChildTerminal, ChildTerminalState, IsolationFacts,
        TeardownFacts, validate_terminal,
    };
    use uuid::Uuid;

    fn terminal(state: ChildTerminalState) -> ChildTerminal {
        ChildTerminal {
            schema_version: 1,
            job_id: Uuid::new_v4(),
            kind: ChildKind::Evidence,
            state,
            request_sha256: "a".repeat(64),
            network_policy_sha256: "b".repeat(64),
            outputs: Vec::<ChildOutputClaim>::new(),
            isolation: IsolationFacts {
                sibling_unreachable: true,
                shared_scratch_unreachable: true,
                credential_paths_unreachable: true,
                postgres_socket_unreachable: true,
                artifact_tree_unreachable: true,
                metadata_unreachable: true,
                private_fleet_unreachable: true,
            },
            teardown: TeardownFacts {
                complete: true,
                processes: 0,
                mounts: 0,
                namespaces: 0,
                secret_files: 0,
                staging_paths: 0,
                firewall_rules: 0,
                preview_capabilities: 0,
            },
        }
    }

    #[test]
    fn success_and_negative_states_require_zero_residue() {
        for state in [
            ChildTerminalState::Completed,
            ChildTerminalState::RedirectBlocked,
            ChildTerminalState::BrowserCrashed,
            ChildTerminalState::ChildTimedOut,
        ] {
            let value = terminal(state);
            validate_terminal(&value, value.job_id, value.kind, &value.request_sha256)
                .expect("clean terminal");
        }
        let mut residue = terminal(ChildTerminalState::BrowserCrashed);
        residue.teardown.processes = 1;
        assert!(
            validate_terminal(
                &residue,
                residue.job_id,
                residue.kind,
                &residue.request_sha256,
            )
            .is_err()
        );
    }

    #[test]
    fn teardown_failed_cannot_claim_clean_teardown() {
        let value = terminal(ChildTerminalState::TeardownFailed);
        assert!(
            validate_terminal(&value, value.job_id, value.kind, &value.request_sha256,).is_err()
        );
    }
}
