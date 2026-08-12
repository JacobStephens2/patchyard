//! Process-backed agent, worker, and verifier stage adapters.

use std::{
    collections::BTreeMap,
    ffi::OsString,
    fs,
    os::unix::fs::{MetadataExt as _, OpenOptionsExt as _, PermissionsExt as _},
    path::{Path, PathBuf},
    time::Duration,
};

use serde::de::DeserializeOwned;
use thiserror::Error;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    config::Seat,
    contracts::{InvocationUsage, ResolvedInvocation},
    process::{ProcessError, ProcessOutput, ProcessSpec, run_bounded},
    worktree::ExactBundle,
};

#[derive(Clone, Debug)]
pub struct StageCommand {
    pub program: PathBuf,
    pub prompt: PathBuf,
    pub timeout: Duration,
    pub cli_version: String,
    pub credential: Option<CredentialCommand>,
}

#[derive(Clone, Debug)]
pub struct CredentialCommand {
    pub program: PathBuf,
    pub arguments: Vec<OsString>,
    pub timeout: Duration,
}

#[derive(Clone, Debug)]
pub struct AgentResult<T> {
    pub value: T,
    pub transcript: Vec<u8>,
    pub usage: InvocationUsage,
    pub cli_version: String,
}

#[derive(Clone, Debug)]
pub struct ProcessAgentBackend {
    commands: BTreeMap<String, StageCommand>,
    scratch: PathBuf,
}

impl ProcessAgentBackend {
    #[must_use]
    pub fn new(commands: BTreeMap<String, StageCommand>, scratch: PathBuf) -> Self {
        Self { commands, scratch }
    }

    /// The harness convention is: `PROGRAM PROMPT INPUT_JSON OUTPUT_JSON`.
    /// Raw content exists only in INPUT_JSON, never argv or the static prompt.
    pub async fn invoke<I: serde::Serialize, O: DeserializeOwned>(
        &self,
        invocation: &ResolvedInvocation,
        input: &I,
        cancellation: &CancellationToken,
    ) -> Result<AgentResult<O>, StageError> {
        let command = self
            .commands
            .get(&invocation.task_class)
            .ok_or_else(|| StageError::MissingCommand(invocation.task_class.clone()))?;
        let directory = self.scratch.join(format!("agent-{}", Uuid::new_v4()));
        create_private_dir(directory.clone()).await?;
        let input_path = directory.join("input.json");
        let output_path = directory.join("output.json");
        let result = async {
            let input_bytes = serde_json::to_vec(input)?;
            write_private(input_path.clone(), input_bytes).await?;
            let bearer_path = if let Some(credential) = &command.credential {
                let path = directory.join("bearer");
                mint_bearer(
                    credential,
                    &invocation.seat.provider,
                    path.clone(),
                    cancellation,
                )
                .await?;
                Some(path)
            } else {
                None
            };
            let mut spec = ProcessSpec::new(&command.program);
            spec.args = vec![
                command.prompt.as_os_str().to_owned(),
                input_path.as_os_str().to_owned(),
                output_path.as_os_str().to_owned(),
            ];
            spec.environment = seat_environment(&invocation.seat, bearer_path.as_deref());
            spec.timeout = command.timeout;
            spec.output_limit = 8 * 1024 * 1024;
            let process = run_bounded(&spec, cancellation).await?;
            if process.code != 0 {
                return Err(StageError::Exit {
                    stage: invocation.task_class.clone(),
                    code: process.code,
                });
            }
            let output = read_bounded_file(output_path, 1024 * 1024).await?;
            let value: O = serde_json::from_slice(&output)?;
            Ok(AgentResult {
                value,
                transcript: process.transcript(),
                usage: parse_usage(&process),
                cli_version: command.cli_version.clone(),
            })
        }
        .await;
        let cleanup = remove_private_dir(directory).await;
        match (result, cleanup) {
            (Ok(value), Ok(())) => Ok(value),
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error),
        }
    }
}

fn parse_usage(process: &ProcessOutput) -> InvocationUsage {
    // Harnesses may include one exact typed usage line on stderr. Missing or
    // malformed telemetry is zero; it never changes authorization.
    process
        .stderr
        .split(|byte| *byte == b'\n')
        .find_map(|line| line.strip_prefix(b"PATCHYARD_USAGE="))
        .and_then(|line| serde_json::from_slice(line).ok())
        .unwrap_or_default()
}

pub(crate) async fn mint_bearer(
    command: &CredentialCommand,
    provider: &str,
    path: PathBuf,
    cancellation: &CancellationToken,
) -> Result<(), StageError> {
    let mut spec = ProcessSpec::new(&command.program);
    spec.args = command.arguments.clone();
    spec.args.push(OsString::from(provider));
    spec.args.push(path.clone().into_os_string());
    spec.timeout = command.timeout;
    spec.output_limit = 16 * 1024;
    let output = run_bounded(&spec, cancellation).await?;
    if output.code != 0 {
        return Err(StageError::CredentialExit {
            provider: provider.to_owned(),
            code: output.code,
        });
    }
    if !output.stdout.is_empty() || !output.stderr.is_empty() {
        return Err(StageError::CredentialOutput(provider.to_owned()));
    }
    validate_bearer_file(path).await
}

async fn validate_bearer_file(path: PathBuf) -> Result<(), StageError> {
    tokio::task::spawn_blocking(move || {
        let metadata = fs::symlink_metadata(&path).map_err(StageIoError::Io)?;
        let parent = path
            .parent()
            .ok_or_else(|| StageIoError::UnsafeCredential(path.clone()))?;
        let parent_metadata = fs::symlink_metadata(parent).map_err(StageIoError::Io)?;
        if !metadata.is_file()
            || metadata.file_type().is_symlink()
            || metadata.permissions().mode() & 0o7777 != 0o600
            || metadata.uid() != parent_metadata.uid()
            || metadata.gid() != parent_metadata.gid()
            || !(1..=8192).contains(&metadata.len())
        {
            return Err(StageIoError::UnsafeCredential(path));
        }
        Ok(())
    })
    .await
    .map_err(StageError::Join)??;
    Ok(())
}

fn seat_environment(seat: &Seat, bearer_path: Option<&Path>) -> Vec<(OsString, OsString)> {
    let mut environment = vec![
        (
            OsString::from("PATCHYARD_MODEL"),
            OsString::from(&seat.model),
        ),
        (
            OsString::from("PATCHYARD_EFFORT"),
            OsString::from(&seat.effort),
        ),
        (
            OsString::from("PATCHYARD_HARNESS"),
            OsString::from(&seat.harness),
        ),
        (
            OsString::from("PATCHYARD_PROVIDER"),
            OsString::from(&seat.provider),
        ),
    ];
    if let Some(path) = bearer_path {
        environment.push((
            OsString::from("PATCHYARD_BEARER_FILE"),
            path.as_os_str().to_owned(),
        ));
    }
    environment
}

#[derive(Clone, Debug)]
pub struct WorkerCommand {
    pub program: PathBuf,
    pub cleanup_program: PathBuf,
    pub snapshot: PathBuf,
    pub timeout: Duration,
}

#[derive(Clone, Debug)]
pub struct WorkerResult {
    pub run_key: String,
    pub patch: Vec<u8>,
    pub rationale: Vec<u8>,
    pub evidence: Vec<u8>,
    pub transcript: Vec<u8>,
}

#[derive(Clone, Debug)]
pub struct ProcessWorkerBackend {
    command: WorkerCommand,
    scratch: PathBuf,
}

impl ProcessWorkerBackend {
    #[must_use]
    pub fn new(command: WorkerCommand, scratch: PathBuf) -> Self {
        Self { command, scratch }
    }

    /// Invoke the remote boundary with an already-produced exact-SHA bundle.
    /// The command convention is fixed and argument-vector only.
    pub async fn invoke(
        &self,
        run_id: Uuid,
        attempt: u8,
        bundle: &ExactBundle,
        task_packet: &Path,
        invocation: &ResolvedInvocation,
        cancellation: &CancellationToken,
    ) -> Result<WorkerResult, StageError> {
        let run_key = format!("{}-a{attempt}", run_id.simple());
        create_private_dir(self.scratch.clone()).await?;
        let output_dir = self.scratch.join(format!("worker-{run_key}"));
        if tokio::fs::try_exists(&output_dir).await? {
            let recovered = self.read_result(&run_key, &output_dir).await;
            if let Ok(value) = recovered {
                self.teardown(&run_key).await?;
                remove_private_dir(output_dir).await?;
                return Ok(value);
            }
            self.teardown(&run_key).await?;
            remove_private_dir(output_dir.clone()).await?;
        }
        let mut spec = ProcessSpec::new(&self.command.program);
        spec.args = vec![
            OsString::from("--run-id"),
            OsString::from(&run_key),
            OsString::from("--base-sha"),
            OsString::from(&bundle.base_sha),
            OsString::from("--bundle"),
            bundle.path().as_os_str().to_owned(),
            OsString::from("--bundle-sha256"),
            OsString::from(&bundle.sha256),
            OsString::from("--task"),
            task_packet.as_os_str().to_owned(),
            OsString::from("--snapshot"),
            self.command.snapshot.as_os_str().to_owned(),
            OsString::from("--output"),
            output_dir.as_os_str().to_owned(),
        ];
        spec.environment = seat_environment(&invocation.seat, None);
        spec.timeout = self.command.timeout;
        spec.output_limit = 1024 * 1024;
        let process = run_bounded(&spec, cancellation).await;
        let result = match process {
            Ok(output) if output.code == 0 => self.read_result(&run_key, &output_dir).await,
            Ok(output) => Err(StageError::Exit {
                stage: "worker".to_owned(),
                code: output.code,
            }),
            Err(error) => Err(error.into()),
        };
        let teardown = self.teardown(&run_key).await;
        let local_cleanup = remove_private_dir(output_dir).await;
        match (result, teardown, local_cleanup) {
            (Ok(value), Ok(()), Ok(())) => Ok(value),
            (Err(error), Ok(()), Ok(())) => Err(error),
            (_, Err(error), _) => Err(error),
            (_, _, Err(error)) => Err(error),
        }
    }

    async fn read_result(
        &self,
        run_key: &str,
        output_dir: &Path,
    ) -> Result<WorkerResult, StageError> {
        Ok(WorkerResult {
            run_key: run_key.to_owned(),
            patch: read_bounded_file(output_dir.join("change.patch"), 1024 * 1024).await?,
            rationale: read_bounded_file(output_dir.join("rationale.txt"), 64 * 1024).await?,
            evidence: read_bounded_file(output_dir.join("evidence.json"), 128 * 1024).await?,
            transcript: read_bounded_file(output_dir.join("transcript.jsonl"), 8 * 1024 * 1024)
                .await?,
        })
    }

    /// Idempotent, awaitable remote teardown. This is never delegated to Drop.
    pub async fn teardown(&self, run_key: &str) -> Result<(), StageError> {
        let mut spec = ProcessSpec::new(&self.command.cleanup_program);
        spec.args = vec![OsString::from(run_key)];
        spec.timeout = Duration::from_secs(60);
        spec.output_limit = 128 * 1024;
        // Cleanup must finish even when the run cancellation token is set.
        let cleanup_token = CancellationToken::new();
        let output = run_bounded(&spec, &cleanup_token).await?;
        if output.code != 0 {
            return Err(StageError::Exit {
                stage: "worker-teardown".to_owned(),
                code: output.code,
            });
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct VerifierCommand {
    pub program: PathBuf,
    pub timeout: Duration,
    pub tests: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct VerifyResult {
    pub passed: bool,
    pub evidence: Vec<u8>,
    pub transcript: Vec<u8>,
    pub reason_code: String,
}

#[derive(Clone, Debug)]
pub struct ProcessVerifierBackend {
    command: VerifierCommand,
    scratch: PathBuf,
}

impl ProcessVerifierBackend {
    #[must_use]
    pub fn new(command: VerifierCommand, scratch: PathBuf) -> Self {
        Self { command, scratch }
    }

    #[allow(clippy::too_many_arguments)]
    pub async fn verify(
        &self,
        repository: &Path,
        base_sha: &str,
        patch_path: &Path,
        implement_evidence: &Path,
        run_id: Uuid,
        attempt: u8,
        cancellation: &CancellationToken,
    ) -> Result<VerifyResult, StageError> {
        create_private_dir(self.scratch.clone()).await?;
        let output_dir = self
            .scratch
            .join(format!("verify-{}-a{attempt}", run_id.simple()));
        if tokio::fs::try_exists(&output_dir).await? {
            remove_private_dir(output_dir.clone()).await?;
        }
        let mut spec = ProcessSpec::new(&self.command.program);
        spec.args = vec![
            repository.as_os_str().to_owned(),
            OsString::from(base_sha),
            patch_path.as_os_str().to_owned(),
            implement_evidence.as_os_str().to_owned(),
            output_dir.as_os_str().to_owned(),
        ];
        spec.args
            .extend(self.command.tests.iter().map(OsString::from));
        spec.timeout = self.command.timeout;
        spec.output_limit = 2 * 1024 * 1024;
        let process = run_bounded(&spec, cancellation).await?;
        let transcript = process.transcript();
        let evidence_path = output_dir.join("evidence.json");
        let evidence = if evidence_path.is_file() {
            read_bounded_file(evidence_path, 512 * 1024).await?
        } else {
            serde_json::to_vec(&serde_json::json!({
                "schema_version": 1,
                "status": "failed",
                "exit_code": process.code,
            }))?
        };
        let reason_code = if process.code == 0 {
            "pass"
        } else {
            "deterministic_verifier_failed"
        };
        Ok(VerifyResult {
            passed: process.code == 0,
            evidence,
            transcript,
            reason_code: reason_code.to_owned(),
        })
    }
}

pub async fn write_private(path: PathBuf, bytes: Vec<u8>) -> Result<(), StageError> {
    tokio::task::spawn_blocking(move || {
        let mut options = fs::OpenOptions::new();
        options.write(true).create_new(true).mode(0o600);
        use std::io::Write as _;
        let mut file = options.open(path)?;
        file.write_all(&bytes)?;
        file.sync_all()
    })
    .await
    .map_err(StageError::Join)??;
    Ok(())
}

pub async fn read_bounded_file(path: PathBuf, maximum: usize) -> Result<Vec<u8>, StageError> {
    tokio::task::spawn_blocking(move || {
        let metadata = fs::symlink_metadata(&path).map_err(StageIoError::Io)?;
        if !metadata.is_file() || metadata.file_type().is_symlink() {
            return Err(StageIoError::UnsafeFile(path));
        }
        if metadata.len() > u64::try_from(maximum).unwrap_or(u64::MAX) {
            return Err(StageIoError::TooLarge(path));
        }
        fs::read(path).map_err(StageIoError::Io)
    })
    .await
    .map_err(StageError::Join)?
    .map_err(StageError::StageIo)
}

pub async fn create_private_dir(path: PathBuf) -> Result<(), StageError> {
    tokio::task::spawn_blocking(move || {
        fs::create_dir_all(&path)?;
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))
    })
    .await
    .map_err(StageError::Join)??;
    Ok(())
}

pub async fn remove_private_dir(path: PathBuf) -> Result<(), StageError> {
    tokio::task::spawn_blocking(move || match fs::remove_dir_all(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error),
    })
    .await
    .map_err(StageError::Join)??;
    Ok(())
}

#[derive(Debug, Error)]
pub enum StageIoError {
    #[error("stage output is not a regular non-symlink file: {0}")]
    UnsafeFile(PathBuf),
    #[error("stage output exceeds its byte cap: {0}")]
    TooLarge(PathBuf),
    #[error("seat bearer is not a private, bounded, same-owner regular file: {0}")]
    UnsafeCredential(PathBuf),
    #[error("stage output read failed: {0}")]
    Io(std::io::Error),
}

#[derive(Debug, Error)]
pub enum StageError {
    #[error("no bounded command is configured for task class {0}")]
    MissingCommand(String),
    #[error("stage {stage} exited with status {code}")]
    Exit { stage: String, code: i32 },
    #[error("credential mint for provider {provider} exited with status {code}")]
    CredentialExit { provider: String, code: i32 },
    #[error("credential mint for provider {0} wrote unexpected process output")]
    CredentialOutput(String),
    #[error("stage output path already exists: {0}")]
    OutputExists(PathBuf),
    #[error("bounded subprocess failed: {0}")]
    Process(#[from] ProcessError),
    #[error("stage JSON contract failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("stage filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("stage file contract failed: {0}")]
    StageIo(#[from] StageIoError),
    #[error("blocking stage task failed: {0}")]
    Join(tokio::task::JoinError),
}
