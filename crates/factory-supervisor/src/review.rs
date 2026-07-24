//! A87 fresh-worktree reviewer isolation and submission barrier.

use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

use factory_core::triage::TaskSpec;
use factory_verify::caps::DiffManifest;
use sha2::Digest as _;
use thiserror::Error;
use tokio::task::JoinSet;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    child::{ChildContract, ChildError, ChildTerminalState, IsolatedChildSpawner},
    config::Seat,
    contracts::{ResolvedInvocation, ReviewArtifact, ReviewPacket},
    stages::StageError,
    worktree::{DetachedWorktree, WorktreeError},
};

#[derive(Clone, Debug)]
pub struct ReviewSandboxConfig {
    pub spawner: IsolatedChildSpawner,
    pub prompt: PathBuf,
    pub worktree_root: PathBuf,
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
        let packet = ReviewPacket {
            schema_version: 1,
            review_id,
            reviewed_sha: reviewed_sha.to_owned(),
            task_spec,
            patch_sha256,
            manifest,
        };
        let packet_bytes = serde_json::to_vec(&packet)?;
        let prompt_bytes = tokio::fs::read(&self.config.prompt).await?;

        let result = self
            .run_isolated(
                workspace.path(),
                packet_bytes,
                prompt_bytes,
                &packet,
                &invocation.seat,
                cancellation,
            )
            .await;
        let workspace_cleanup = workspace.close(&CancellationToken::new()).await;
        match (result, workspace_cleanup) {
            (Ok(value), Ok(())) => Ok(value),
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error.into()),
        }
        .map(|mut execution| {
            execution.invocation = invocation;
            execution
        })
    }

    async fn run_isolated(
        &self,
        worktree: &Path,
        packet_bytes: Vec<u8>,
        prompt_bytes: Vec<u8>,
        packet: &ReviewPacket,
        seat: &Seat,
        cancellation: &CancellationToken,
    ) -> Result<ReviewExecution, ReviewError> {
        let workspace = worktree
            .to_str()
            .ok_or(ReviewError::NonUtf8Workspace)?
            .to_owned();
        let packet_sha256 = hex::encode(sha2::Sha256::digest(&packet_bytes));
        let prompt_sha256 = hex::encode(sha2::Sha256::digest(&prompt_bytes));
        let child = self
            .config
            .spawner
            .spawn(
                ChildContract::Review {
                    workspace,
                    reviewed_sha: packet.reviewed_sha.clone(),
                    packet_sha256,
                    prompt_sha256,
                    model: seat.model.clone(),
                    effort: seat.effort.clone(),
                    harness: seat.harness.clone(),
                    provider: seat.provider.clone(),
                },
                vec![
                    ("packet.json".to_owned(), packet_bytes),
                    ("prompt.md".to_owned(), prompt_bytes),
                ],
                None,
                cancellation,
            )
            .await?;
        if child.terminal.state != ChildTerminalState::Completed {
            return Err(ReviewError::ChildState(child.terminal.state));
        }
        let isolation = &child.terminal.isolation;
        if !isolation.sibling_unreachable
            || !isolation.shared_scratch_unreachable
            || !isolation.credential_paths_unreachable
            || !isolation.postgres_socket_unreachable
            || !isolation.artifact_tree_unreachable
            || !isolation.metadata_unreachable
            || !isolation.private_fleet_unreachable
        {
            return Err(ReviewError::IsolationProbe);
        }
        let artifact: ReviewArtifact = serde_json::from_slice(child.output("review.json")?)?;
        validate_artifact(&artifact, packet)?;
        Ok(ReviewExecution {
            invocation: ResolvedInvocation {
                task_class: String::new(),
                routing_version: String::new(),
                seat: seat.clone(),
            },
            artifact,
            transcript: child.output("transcript.log")?.to_vec(),
            sibling_unreachable: isolation.sibling_unreachable,
            shared_scratch_unreachable: isolation.shared_scratch_unreachable,
        })
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
    #[error("reviewer child returned fail-closed state {0:?}")]
    ChildState(ChildTerminalState),
    #[error("review workspace path is not UTF-8")]
    NonUtf8Workspace,
    #[error("review artifact is malformed")]
    MalformedArtifact,
    #[error("review JSON failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("review filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("review child spawn failed: {0}")]
    Child(#[from] ChildError),
    #[error("review stage failed: {0}")]
    Stage(#[from] StageError),
    #[error("review worktree failed: {0}")]
    Worktree(#[from] WorktreeError),
    #[error("review task failed: {0}")]
    Join(tokio::task::JoinError),
}

#[cfg(test)]
mod tests {
    // A87 isolation facts are validated at the shared A104 child boundary.
}
