//! A87 fresh-worktree reviewer isolation and submission barrier.

use std::{
    collections::BTreeSet,
    ffi::OsString,
    path::{Path, PathBuf},
    time::Duration,
};

use factory_core::triage::TaskSpec;
use factory_verify::caps::DiffManifest;
use thiserror::Error;
use tokio::task::JoinSet;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    config::Seat,
    contracts::{ResolvedInvocation, ReviewArtifact, ReviewPacket},
    process::{ProcessError, ProcessSpec, run_bounded},
    stages::{
        StageError, create_private_dir, read_bounded_file, remove_private_dir, write_private,
    },
    worktree::{DetachedWorktree, WorktreeError},
};

#[derive(Clone, Debug)]
pub struct ReviewSandboxConfig {
    pub bubblewrap: PathBuf,
    pub harness_program: PathBuf,
    pub prompt: PathBuf,
    pub worktree_root: PathBuf,
    pub scratch_root: PathBuf,
    pub timeout: Duration,
    /// Must remain false until the provider-native isolation path is A-5 qualified.
    pub live_network: bool,
}

#[derive(Clone, Debug)]
pub struct ReviewExecution {
    pub invocation: ResolvedInvocation,
    pub artifact: ReviewArtifact,
    pub transcript: Vec<u8>,
    pub sibling_unreachable: bool,
    pub shared_scratch_unreachable: bool,
}

#[derive(Clone, Debug)]
pub struct SandboxedReviewer {
    config: ReviewSandboxConfig,
}

impl SandboxedReviewer {
    #[must_use]
    pub fn new(config: ReviewSandboxConfig) -> Self {
        Self { config }
    }

    /// Execute all reviewers concurrently, but return nothing until every
    /// reviewer has submitted. The caller cannot persist or reveal one output
    /// before the supervisor-held barrier opens.
    #[allow(clippy::too_many_arguments)]
    pub async fn review_many(
        &self,
        repository: &Path,
        reviewed_sha: &str,
        task_spec: &TaskSpec,
        patch_sha256: &str,
        manifest: &DiffManifest,
        invocations: Vec<ResolvedInvocation>,
        cancellation: &CancellationToken,
    ) -> Result<Vec<ReviewExecution>, ReviewError> {
        if invocations.is_empty() {
            return Ok(Vec::new());
        }
        let mut set = JoinSet::new();
        for invocation in invocations {
            let reviewer = self.clone();
            let repository = repository.to_path_buf();
            let reviewed_sha = reviewed_sha.to_owned();
            let task_spec = task_spec.clone();
            let patch_sha256 = patch_sha256.to_owned();
            let manifest = manifest.clone();
            let cancellation = cancellation.clone();
            set.spawn(async move {
                reviewer
                    .review_one(
                        &repository,
                        &reviewed_sha,
                        task_spec,
                        patch_sha256,
                        manifest,
                        invocation,
                        &cancellation,
                    )
                    .await
            });
        }
        let mut completed = Vec::new();
        let mut first_error = None;
        while let Some(joined) = set.join_next().await {
            match joined {
                Ok(Ok(review)) => completed.push(review),
                Ok(Err(error)) if first_error.is_none() => first_error = Some(error),
                Ok(Err(_)) => {}
                Err(error) if first_error.is_none() => first_error = Some(ReviewError::Join(error)),
                Err(_) => {}
            }
        }
        if let Some(error) = first_error {
            return Err(error);
        }
        completed.sort_by_key(|review| review.artifact.review_id);
        Ok(completed)
    }

    #[allow(clippy::too_many_arguments)]
    async fn review_one(
        &self,
        repository: &Path,
        reviewed_sha: &str,
        task_spec: TaskSpec,
        patch_sha256: String,
        manifest: DiffManifest,
        invocation: ResolvedInvocation,
        cancellation: &CancellationToken,
    ) -> Result<ReviewExecution, ReviewError> {
        if self.config.live_network {
            return Err(ReviewError::LiveProviderNotQualified);
        }
        let review_id = Uuid::new_v4();
        let workspace_name = format!("review-{}", review_id.simple());
        let workspace = DetachedWorktree::create(
            repository,
            reviewed_sha,
            &self.config.worktree_root,
            &workspace_name,
            cancellation,
        )
        .await?;
        let private = self.config.scratch_root.join(workspace_name);
        create_private_dir(private.clone()).await?;
        let input_path = private.join("packet.json");
        let output_path = private.join("review.json");
        let packet = ReviewPacket {
            schema_version: 1,
            review_id,
            reviewed_sha: reviewed_sha.to_owned(),
            task_spec,
            patch_sha256,
            manifest,
        };
        write_private(input_path.clone(), serde_json::to_vec(&packet)?).await?;

        let result = self
            .run_isolated(
                workspace.path(),
                &input_path,
                &output_path,
                &invocation.seat,
                cancellation,
            )
            .await;
        let workspace_cleanup = workspace.close(&CancellationToken::new()).await;
        let private_cleanup = remove_private_dir(private).await;
        match (result, workspace_cleanup, private_cleanup) {
            (Ok(value), Ok(()), Ok(())) => Ok(value),
            (Err(error), Ok(()), Ok(())) => Err(error),
            (_, Err(error), _) => Err(error.into()),
            (_, _, Err(error)) => Err(error.into()),
        }
        .map(|mut execution| {
            execution.invocation = invocation;
            execution
        })
    }

    async fn run_isolated(
        &self,
        worktree: &Path,
        packet: &Path,
        output: &Path,
        seat: &Seat,
        cancellation: &CancellationToken,
    ) -> Result<ReviewExecution, ReviewError> {
        let sibling_unreachable = self
            .probe_absent(worktree, packet, output, "/review-siblings", cancellation)
            .await?;
        let shared_scratch_unreachable = self
            .probe_absent(worktree, packet, output, "/shared-scratch", cancellation)
            .await?;
        if !sibling_unreachable || !shared_scratch_unreachable {
            return Err(ReviewError::IsolationProbe);
        }
        let mut spec = self.sandbox_spec(worktree, packet, output);
        spec.args.extend([
            OsString::from("/harness"),
            OsString::from("/input/PROMPT.md"),
            OsString::from("/input/PACKET.json"),
            OsString::from("/output/review.json"),
        ]);
        spec.environment.extend([
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
        ]);
        let process = run_bounded(&spec, cancellation).await?;
        if process.code != 0 {
            return Err(ReviewError::HarnessExit(process.code));
        }
        let bytes = read_bounded_file(output.to_path_buf(), 1024 * 1024).await?;
        let artifact: ReviewArtifact = serde_json::from_slice(&bytes)?;
        let packet_bytes = read_bounded_file(packet.to_path_buf(), 1024 * 1024).await?;
        let expected: ReviewPacket = serde_json::from_slice(&packet_bytes)?;
        validate_artifact(&artifact, &expected)?;
        Ok(ReviewExecution {
            invocation: ResolvedInvocation {
                task_class: String::new(),
                routing_version: String::new(),
                seat: seat.clone(),
            },
            artifact,
            transcript: process.transcript(),
            sibling_unreachable,
            shared_scratch_unreachable,
        })
    }

    async fn probe_absent(
        &self,
        worktree: &Path,
        packet: &Path,
        output: &Path,
        target: &str,
        cancellation: &CancellationToken,
    ) -> Result<bool, ReviewError> {
        let mut spec = self.sandbox_spec(worktree, packet, output);
        spec.args.extend([
            OsString::from("/usr/bin/stat"),
            OsString::from("--"),
            OsString::from(target),
        ]);
        spec.output_limit = 64 * 1024;
        let result = run_bounded(&spec, cancellation).await?;
        Ok(result.code != 0)
    }

    fn sandbox_spec(&self, worktree: &Path, packet: &Path, output: &Path) -> ProcessSpec {
        let output_directory = output.parent().expect("review output always has a parent");
        let mut spec = ProcessSpec::new(&self.config.bubblewrap);
        spec.args = vec![
            OsString::from("--unshare-all"),
            OsString::from("--die-with-parent"),
            OsString::from("--new-session"),
            OsString::from("--ro-bind"),
            OsString::from("/usr"),
            OsString::from("/usr"),
            OsString::from("--symlink"),
            OsString::from("usr/bin"),
            OsString::from("/bin"),
            OsString::from("--symlink"),
            OsString::from("usr/lib"),
            OsString::from("/lib"),
            OsString::from("--symlink"),
            OsString::from("usr/lib64"),
            OsString::from("/lib64"),
            OsString::from("--proc"),
            OsString::from("/proc"),
            OsString::from("--dev"),
            OsString::from("/dev"),
            OsString::from("--tmpfs"),
            OsString::from("/tmp"),
            OsString::from("--dir"),
            OsString::from("/input"),
            OsString::from("--dir"),
            OsString::from("/output"),
            OsString::from("--dir"),
            OsString::from("/workspace"),
            OsString::from("--ro-bind"),
            worktree.as_os_str().to_owned(),
            OsString::from("/workspace"),
            OsString::from("--ro-bind"),
            packet.as_os_str().to_owned(),
            OsString::from("/input/PACKET.json"),
            OsString::from("--ro-bind"),
            self.config.prompt.as_os_str().to_owned(),
            OsString::from("/input/PROMPT.md"),
            OsString::from("--ro-bind"),
            self.config.harness_program.as_os_str().to_owned(),
            OsString::from("/harness"),
            OsString::from("--bind"),
            output_directory.as_os_str().to_owned(),
            OsString::from("/output"),
            OsString::from("--chdir"),
            OsString::from("/workspace"),
            OsString::from("--setenv"),
            OsString::from("HOME"),
            OsString::from("/tmp"),
        ];
        spec.timeout = self.config.timeout;
        spec.output_limit = 8 * 1024 * 1024;
        spec
    }
}

fn validate_artifact(artifact: &ReviewArtifact, packet: &ReviewPacket) -> Result<(), ReviewError> {
    if artifact.schema_version != 1 || artifact.findings.len() > 100 {
        return Err(ReviewError::MalformedArtifact);
    }
    if artifact.review_id != packet.review_id || artifact.reviewed_sha != packet.reviewed_sha {
        return Err(ReviewError::MalformedArtifact);
    }
    let mut ids = BTreeSet::new();
    for finding in &artifact.findings {
        if finding.id.is_empty()
            || finding.id.len() > 64
            || !ids.insert(&finding.id)
            || finding.claim.trim().is_empty()
            || finding.evidence.trim().is_empty()
        {
            return Err(ReviewError::MalformedArtifact);
        }
    }
    Ok(())
}

#[derive(Debug, Error)]
pub enum ReviewError {
    #[error("live reviewer provider isolation is not A-5 qualified")]
    LiveProviderNotQualified,
    #[error("reviewer sandbox exposed sibling or shared scratch")]
    IsolationProbe,
    #[error("reviewer harness exited with status {0}")]
    HarnessExit(i32),
    #[error("review artifact is malformed")]
    MalformedArtifact,
    #[error("review JSON failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("review filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("review process failed: {0}")]
    Process(#[from] ProcessError),
    #[error("review stage failed: {0}")]
    Stage(#[from] StageError),
    #[error("review worktree failed: {0}")]
    Worktree(#[from] WorktreeError),
    #[error("review task failed: {0}")]
    Join(tokio::task::JoinError),
}
