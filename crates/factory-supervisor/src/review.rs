//! A87 fresh-worktree reviewer isolation and submission barrier.

use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

use factory_core::{catalogue::CallSite, triage::TaskSpec};
use factory_verify::caps::DiffManifest;
use sha2::Digest as _;
use thiserror::Error;
use tokio::task::JoinSet;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    child::{ChildContract, ChildError, ChildSecret, ChildTerminalState, IsolatedChildSpawner},
    config::Seat,
    contracts::{PatchHunk, ResolvedInvocation, ReviewArtifact, ReviewPacket},
    proposer::{EvidenceCitation, PromptBundleManifest},
    stages::{CredentialCommand, StageError},
    worktree::{DetachedWorktree, WorktreeError},
};

/// Live-seat wiring for the isolated reviewer. Constructed only after
/// bootstrap has proven the seat's provider `credential_qualified` (A113);
/// its absence keeps the sealed `offline-review` network policy.
#[derive(Clone, Debug)]
pub struct LiveReviewSeat {
    pub credential: CredentialCommand,
    pub mint_root: PathBuf,
    pub egress_host: String,
}

#[derive(Clone, Debug)]
pub struct ReviewSandboxConfig {
    pub spawner: IsolatedChildSpawner,
    pub prompt: PathBuf,
    pub worktree_root: PathBuf,
    pub live: Option<LiveReviewSeat>,
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

struct IsolatedReviewInput {
    worktree: PathBuf,
    packet_bytes: Vec<u8>,
    prompt_bytes: Vec<u8>,
    review_id: Uuid,
    reviewed_sha: String,
    seat: Seat,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(deny_unknown_fields)]
pub struct PolicyReviewPacket {
    pub schema_version: u16,
    pub run_id: Uuid,
    pub review_id: Uuid,
    pub reviewed_sha: String,
    pub report_sha256: String,
    pub patch_sha256: String,
    /// Supervisor-derived, bounded unified diff. This lets the isolated
    /// reviewer inspect the exact change without exposing the shared Git ODB.
    pub patch: String,
    pub citations: Vec<EvidenceCitation>,
    pub manifest: DiffManifest,
    pub self_referential_paths: Vec<String>,
    pub author_prompt_bundle: PromptBundleManifest,
    pub reviewer_prompt_bundle: PromptBundleManifest,
    pub report: crate::lessons::LessonsReport,
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
        hunks: &[PatchHunk],
        call_sites: &[CallSite],
        invocations: Vec<ResolvedInvocation>,
        cancellation: &CancellationToken,
    ) -> Result<Vec<ReviewExecution>, ReviewError> {
        if invocations.is_empty() {
            return Ok(Vec::new());
        }
        // Git's worktree administration updates one repository-level registry.
        // Prepare and close those entries sequentially; the isolated reviewers
        // still execute concurrently and no lock is held across their awaits.
        let mut workspaces: Vec<(Uuid, ResolvedInvocation, DetachedWorktree)> =
            Vec::with_capacity(invocations.len());
        for invocation in invocations {
            let review_id = Uuid::new_v4();
            let workspace_name = format!("review-{}", review_id.simple());
            let workspace = match DetachedWorktree::create(
                repository,
                reviewed_sha,
                &self.config.worktree_root,
                &workspace_name,
                cancellation,
            )
            .await
            {
                Ok(workspace) => workspace,
                Err(error) => {
                    let mut cleanup_error = None;
                    for (_, _, workspace) in workspaces {
                        if let Err(cleanup) = workspace.close(&CancellationToken::new()).await {
                            cleanup_error.get_or_insert(cleanup);
                        }
                    }
                    if let Some(cleanup) = cleanup_error {
                        return Err(cleanup.into());
                    }
                    return Err(error.into());
                }
            };
            workspaces.push((review_id, invocation, workspace));
        }
        let mut completed = Vec::new();
        let mut first_error = None;
        if self.config.live.is_some() {
            // A live-egress child requires the host's non-router baseline
            // (ip_forward=0) and holds the shared network lock for its whole
            // run, so live reviewers execute one at a time. The A87 barrier
            // is unaffected: outputs stay supervisor-held either way, and no
            // reviewer's output is visible to another before all return.
            for (review_id, invocation, workspace) in &workspaces {
                match self
                    .review_prepared(
                        *review_id,
                        workspace.path(),
                        reviewed_sha,
                        task_spec.clone(),
                        patch_sha256.to_owned(),
                        manifest.clone(),
                        hunks.to_vec(),
                        call_sites.to_vec(),
                        invocation.clone(),
                        cancellation,
                    )
                    .await
                {
                    Ok(review) => completed.push(review),
                    Err(error) => {
                        first_error.get_or_insert(error);
                    }
                }
            }
        } else {
            let mut set = JoinSet::new();
            for (review_id, invocation, workspace) in &workspaces {
                let reviewer = self.clone();
                let reviewed_sha = reviewed_sha.to_owned();
                let task_spec = task_spec.clone();
                let patch_sha256 = patch_sha256.to_owned();
                let manifest = manifest.clone();
                let hunks = hunks.to_vec();
                let call_sites = call_sites.to_vec();
                let cancellation = cancellation.clone();
                let review_id = *review_id;
                let invocation = invocation.clone();
                let workspace = workspace.path().to_path_buf();
                set.spawn(async move {
                    reviewer
                        .review_prepared(
                            review_id,
                            &workspace,
                            &reviewed_sha,
                            task_spec,
                            patch_sha256,
                            manifest,
                            hunks,
                            call_sites,
                            invocation,
                            &cancellation,
                        )
                        .await
                });
            }
            while let Some(joined) = set.join_next().await {
                match joined {
                    Ok(Ok(review)) => completed.push(review),
                    Ok(Err(error)) if first_error.is_none() => first_error = Some(error),
                    Ok(Err(_)) => {}
                    Err(error) if first_error.is_none() => {
                        first_error = Some(ReviewError::Join(error));
                    }
                    Err(_) => {}
                }
            }
        }
        let mut cleanup_error = None;
        for (_, _, workspace) in workspaces {
            if let Err(error) = workspace.close(&CancellationToken::new()).await {
                cleanup_error = Some(error);
            }
        }
        if let Some(error) = cleanup_error {
            return Err(error.into());
        }
        if let Some(error) = first_error {
            return Err(error);
        }
        completed.sort_by_key(|review| review.artifact.review_id);
        Ok(completed)
    }

    /// Review one proposer candidate through the same isolated, sibling-blind
    /// A87 boundary used for code. The packet carries deterministic evidence,
    /// never proposer rationale or a model transcript.
    pub async fn review_policy(
        &self,
        repository: &Path,
        packet: &PolicyReviewPacket,
        prompt_bytes: Vec<u8>,
        invocation: ResolvedInvocation,
        cancellation: &CancellationToken,
    ) -> Result<ReviewExecution, ReviewError> {
        if packet.schema_version != 1 {
            return Err(ReviewError::MalformedArtifact);
        }
        let workspace_name = format!("review-{}", packet.review_id.simple());
        let worktree_root = self.config.worktree_root.join(packet.run_id.to_string());
        let workspace = DetachedWorktree::create(
            repository,
            &packet.reviewed_sha,
            &worktree_root,
            &workspace_name,
            cancellation,
        )
        .await?;
        let packet_bytes = serde_json::to_vec(packet)?;
        let result = self
            .run_isolated(
                IsolatedReviewInput {
                    worktree: workspace.path().to_path_buf(),
                    packet_bytes,
                    prompt_bytes,
                    review_id: packet.review_id,
                    reviewed_sha: packet.reviewed_sha.clone(),
                    seat: invocation.seat.clone(),
                },
                cancellation,
            )
            .await;
        let cleanup = workspace.close(&CancellationToken::new()).await;
        match (result, cleanup) {
            (Ok(mut review), Ok(())) => {
                review.invocation = invocation;
                Ok(review)
            }
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error.into()),
        }
    }

    #[allow(clippy::too_many_arguments)]
    async fn review_prepared(
        &self,
        review_id: Uuid,
        workspace: &Path,
        reviewed_sha: &str,
        task_spec: TaskSpec,
        patch_sha256: String,
        manifest: DiffManifest,
        hunks: Vec<PatchHunk>,
        call_sites: Vec<CallSite>,
        invocation: ResolvedInvocation,
        cancellation: &CancellationToken,
    ) -> Result<ReviewExecution, ReviewError> {
        let packet = ReviewPacket {
            schema_version: 1,
            review_id,
            reviewed_sha: reviewed_sha.to_owned(),
            task_spec,
            patch_sha256,
            manifest,
            hunks,
            call_sites,
        };
        let packet_bytes = serde_json::to_vec(&packet)?;
        let prompt_bytes = tokio::fs::read(&self.config.prompt).await?;
        self.run_isolated(
            IsolatedReviewInput {
                worktree: workspace.to_path_buf(),
                packet_bytes,
                prompt_bytes,
                review_id: packet.review_id,
                reviewed_sha: packet.reviewed_sha.clone(),
                seat: invocation.seat.clone(),
            },
            cancellation,
        )
        .await
        .map(|mut execution| {
            execution.invocation = invocation;
            execution
        })
    }

    /// Mint one short-lived seat bearer through the same hardened requester
    /// the process-backed agent stages use, holding it only in memory: the
    /// mint stage is removed before the child spawns, and the only durable
    /// copy is the `secret/` staging file the launcher deletes on teardown.
    async fn mint_seat_bearer(
        &self,
        live: &LiveReviewSeat,
        provider: &str,
        cancellation: &CancellationToken,
    ) -> Result<String, ReviewError> {
        let stage = live.mint_root.join(format!("agent-{}", Uuid::new_v4()));
        crate::stages::create_private_dir(stage.clone()).await?;
        let result = async {
            let bearer_path = stage.join("bearer");
            crate::stages::mint_bearer(
                &live.credential,
                provider,
                bearer_path.clone(),
                cancellation,
            )
            .await?;
            let bytes = crate::stages::read_bounded_file(bearer_path, 8192).await?;
            String::from_utf8(bytes).map_err(|_| ReviewError::MalformedBearer)
        }
        .await;
        let cleanup = crate::stages::remove_private_dir(stage).await;
        match (result, cleanup) {
            (Ok(bearer), Ok(())) if !bearer.is_empty() => Ok(bearer),
            (Ok(_), Ok(())) => Err(ReviewError::MalformedBearer),
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error.into()),
        }
    }

    async fn run_isolated(
        &self,
        input: IsolatedReviewInput,
        cancellation: &CancellationToken,
    ) -> Result<ReviewExecution, ReviewError> {
        let workspace = input
            .worktree
            .to_str()
            .ok_or(ReviewError::NonUtf8Workspace)?
            .to_owned();
        let packet_sha256 = hex::encode(sha2::Sha256::digest(&input.packet_bytes));
        let prompt_sha256 = hex::encode(sha2::Sha256::digest(&input.prompt_bytes));
        let (egress_host, secret) = match &self.config.live {
            Some(live) => (
                Some(live.egress_host.clone()),
                Some(ChildSecret::SeatBearer(
                    self.mint_seat_bearer(live, &input.seat.provider, cancellation)
                        .await?,
                )),
            ),
            None => (None, None),
        };
        let child = self
            .config
            .spawner
            .spawn(
                ChildContract::Review {
                    workspace,
                    reviewed_sha: input.reviewed_sha.clone(),
                    packet_sha256,
                    prompt_sha256,
                    model: input.seat.model.clone(),
                    effort: input.seat.effort.clone(),
                    harness: input.seat.harness.clone(),
                    provider: input.seat.provider.clone(),
                    egress_host,
                },
                vec![
                    ("packet.json".to_owned(), input.packet_bytes),
                    ("prompt.md".to_owned(), input.prompt_bytes),
                ],
                secret,
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
        validate_artifact(&artifact, input.review_id, &input.reviewed_sha)?;
        Ok(ReviewExecution {
            invocation: ResolvedInvocation {
                task_class: String::new(),
                routing_version: String::new(),
                seat: input.seat,
            },
            artifact,
            transcript: child.output("transcript.log")?.to_vec(),
            sibling_unreachable: isolation.sibling_unreachable,
            shared_scratch_unreachable: isolation.shared_scratch_unreachable,
        })
    }
}

fn validate_artifact(
    artifact: &ReviewArtifact,
    review_id: Uuid,
    reviewed_sha: &str,
) -> Result<(), ReviewError> {
    if artifact.schema_version != 1 || artifact.findings.len() > 100 {
        return Err(ReviewError::MalformedArtifact);
    }
    if artifact.review_id != review_id || artifact.reviewed_sha != reviewed_sha {
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
    #[error("minted seat bearer is empty or not UTF-8")]
    MalformedBearer,
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
    use std::{fs, path::Path, process::Command, time::Duration};

    use factory_core::triage::TaskSpec;
    use factory_verify::caps::DiffManifest;
    use serde_json::Value;
    use tempfile::TempDir;
    use tokio_util::sync::CancellationToken;

    use super::{ReviewError, ReviewSandboxConfig, SandboxedReviewer};
    use crate::{
        child::{ChildSpawnConfig, IsolatedChildSpawner},
        config::Seat,
        contracts::ResolvedInvocation,
    };

    fn git(repository: &Path, arguments: &[&str]) -> String {
        let output = Command::new("/usr/bin/git")
            .arg("-C")
            .arg(repository)
            .args(arguments)
            .output()
            .expect("git command");
        assert!(
            output.status.success(),
            "git failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        String::from_utf8(output.stdout)
            .expect("git UTF-8")
            .trim()
            .to_owned()
    }

    fn repository() -> (TempDir, String) {
        let temporary = tempfile::tempdir().expect("repository tempdir");
        git(temporary.path(), &["init", "--quiet"]);
        git(
            temporary.path(),
            &["config", "user.email", "fixture@example.invalid"],
        );
        git(temporary.path(), &["config", "user.name", "Fixture"]);
        fs::write(temporary.path().join("fixture.txt"), b"fixture\n").expect("fixture file");
        git(temporary.path(), &["add", "fixture.txt"]);
        git(temporary.path(), &["commit", "--quiet", "-m", "fixture"]);
        let sha = git(temporary.path(), &["rev-parse", "HEAD"]);
        (temporary, sha)
    }

    fn task_spec() -> TaskSpec {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let value: Value = serde_json::from_slice(
            &fs::read(root.join("fixtures/triage/alphabetize.json")).expect("triage fixture"),
        )
        .expect("triage JSON");
        serde_json::from_value(value["task_spec"].clone()).expect("task spec")
    }

    #[tokio::test]
    async fn prompt_read_failure_still_explicitly_closes_the_worktree() {
        let (repository, reviewed_sha) = repository();
        let scratch = tempfile::tempdir().expect("scratch");
        let worktree_root = scratch.path().join("review-worktrees");
        let reviewer = SandboxedReviewer::new(ReviewSandboxConfig {
            spawner: IsolatedChildSpawner::new(ChildSpawnConfig {
                spawn_program: scratch.path().join("unused-spawn"),
                cancel_program: scratch.path().join("unused-cancel"),
                staging_root: scratch.path().join("children"),
                timeout: Duration::from_secs(1),
            }),
            prompt: scratch.path().join("missing-review-prompt"),
            worktree_root: worktree_root.clone(),
            live: None,
        });
        let error = reviewer
            .review_many(
                repository.path(),
                &reviewed_sha,
                &task_spec(),
                &"a".repeat(64),
                &DiffManifest {
                    base_sha: reviewed_sha.clone(),
                    files: Vec::new(),
                },
                &[],
                &[],
                vec![ResolvedInvocation {
                    task_class: "review".to_owned(),
                    routing_version: "fixture".to_owned(),
                    seat: Seat {
                        model: "Fixture".to_owned(),
                        effort: "test".to_owned(),
                        harness: "fixture".to_owned(),
                        provider: "fixture".to_owned(),
                    },
                }],
                &CancellationToken::new(),
            )
            .await
            .expect_err("missing prompt must fail");
        assert!(matches!(error, ReviewError::Io(_)));
        assert!(
            fs::read_dir(&worktree_root)
                .expect("worktree root")
                .next()
                .is_none(),
            "failed setup left a detached worktree"
        );
    }
}
