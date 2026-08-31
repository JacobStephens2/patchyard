//! A77 clause-3 third-family dispute arbitration, isolated per A87.
//!
//! The arbiter acts on one disputed finding only, never as a standing
//! adjudicator. It reads the typed dispute record by design - both positions
//! and their evidence - but works from its own fresh worktree at the reviewed
//! SHA, with no author or reviewer transcript reachable (F5).

use std::path::{Path, PathBuf};

use sha2::Digest as _;
use thiserror::Error;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    child::{ChildContract, ChildError, ChildSecret, ChildTerminalState, IsolatedChildSpawner},
    contracts::{ArbitrationArtifact, ArbitrationPacket, ResolvedInvocation},
    stages::{CredentialCommand, StageError},
    worktree::{DetachedWorktree, WorktreeError},
};

/// Cap on the arbiter's stated evidence. A decision that needs more than this
/// to justify itself is not a bounded artifact any more.
const MAX_EVIDENCE_BYTES: usize = 64 * 1024;

/// Live-seat wiring for the isolated arbiter. Constructed only after
/// bootstrap has proven the seat's provider `credential_qualified` (A113);
/// while it is absent the pipeline keeps its stubbed escalation path, so an
/// unqualified provider can never receive a real dispute.
#[derive(Clone, Debug)]
pub struct LiveArbiterSeat {
    pub credential: CredentialCommand,
    pub mint_root: PathBuf,
    pub egress_host: String,
}

#[derive(Clone, Debug)]
pub struct ArbiterSandboxConfig {
    pub spawner: IsolatedChildSpawner,
    pub prompt: PathBuf,
    pub worktree_root: PathBuf,
    pub live: Option<LiveArbiterSeat>,
}

#[derive(Clone, Debug)]
pub struct ArbitrationExecution {
    pub invocation: ResolvedInvocation,
    pub artifact: ArbitrationArtifact,
    pub transcript: Vec<u8>,
}

#[derive(Clone, Debug)]
pub struct SandboxedArbiter {
    config: ArbiterSandboxConfig,
}

impl SandboxedArbiter {
    #[must_use]
    pub fn new(config: ArbiterSandboxConfig) -> Self {
        Self { config }
    }

    /// Arbitrate one disputed finding from a fresh worktree at the reviewed
    /// SHA. The worktree is closed on every return path.
    pub async fn arbitrate(
        &self,
        repository: &Path,
        packet: &ArbitrationPacket,
        invocation: ResolvedInvocation,
        cancellation: &CancellationToken,
    ) -> Result<ArbitrationExecution, ArbiterError> {
        if packet.schema_version != 1 {
            return Err(ArbiterError::MalformedArtifact);
        }
        let workspace_name = format!("arbiter-{}", packet.dispute.dispute_id.simple());
        let workspace = DetachedWorktree::create(
            repository,
            &packet.dispute.reviewed_sha,
            &self.config.worktree_root,
            &workspace_name,
            cancellation,
        )
        .await?;
        let result = self
            .run_isolated(workspace.path(), packet, invocation, cancellation)
            .await;
        let cleanup = workspace.close(&CancellationToken::new()).await;
        match (result, cleanup) {
            (Ok(execution), Ok(())) => Ok(execution),
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error.into()),
        }
    }

    /// Mint one short-lived seat bearer through the same hardened requester
    /// the review seat uses, holding it only in memory: the mint stage is
    /// removed before the child spawns, and the only durable copy is the
    /// `secret/` staging file the launcher deletes on teardown.
    async fn mint_seat_bearer(
        &self,
        live: &LiveArbiterSeat,
        provider: &str,
        cancellation: &CancellationToken,
    ) -> Result<String, ArbiterError> {
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
            String::from_utf8(bytes).map_err(|_| ArbiterError::MalformedBearer)
        }
        .await;
        let cleanup = crate::stages::remove_private_dir(stage).await;
        match (result, cleanup) {
            (Ok(bearer), Ok(())) if !bearer.is_empty() => Ok(bearer),
            (Ok(_), Ok(())) => Err(ArbiterError::MalformedBearer),
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error.into()),
        }
    }

    async fn run_isolated(
        &self,
        worktree: &Path,
        packet: &ArbitrationPacket,
        invocation: ResolvedInvocation,
        cancellation: &CancellationToken,
    ) -> Result<ArbitrationExecution, ArbiterError> {
        let workspace = worktree
            .to_str()
            .ok_or(ArbiterError::NonUtf8Workspace)?
            .to_owned();
        let packet_bytes = serde_json::to_vec(packet)?;
        let prompt_bytes = tokio::fs::read(&self.config.prompt).await?;
        let packet_sha256 = hex::encode(sha2::Sha256::digest(&packet_bytes));
        let prompt_sha256 = hex::encode(sha2::Sha256::digest(&prompt_bytes));
        let seat = invocation.seat.clone();
        let (egress_host, secret) = match &self.config.live {
            Some(live) => (
                Some(live.egress_host.clone()),
                Some(ChildSecret::SeatBearer(
                    self.mint_seat_bearer(live, &seat.provider, cancellation)
                        .await?,
                )),
            ),
            None => (None, None),
        };
        let child = self
            .config
            .spawner
            .spawn(
                ChildContract::Arbitration {
                    workspace,
                    reviewed_sha: packet.dispute.reviewed_sha.clone(),
                    packet_sha256,
                    prompt_sha256,
                    model: seat.model.clone(),
                    effort: seat.effort.clone(),
                    harness: seat.harness.clone(),
                    provider: seat.provider.clone(),
                    egress_host,
                },
                vec![
                    ("packet.json".to_owned(), packet_bytes),
                    ("prompt.md".to_owned(), prompt_bytes),
                ],
                secret,
                cancellation,
            )
            .await?;
        if child.terminal.state != ChildTerminalState::Completed {
            return Err(ArbiterError::ChildState(child.terminal.state));
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
            return Err(ArbiterError::IsolationProbe);
        }
        let artifact: ArbitrationArtifact =
            serde_json::from_slice(child.output("arbitration.json")?)?;
        validate_artifact(&artifact, packet.dispute.dispute_id)?;
        Ok(ArbitrationExecution {
            invocation,
            artifact,
            transcript: child.output("transcript.log")?.to_vec(),
        })
    }
}

fn validate_artifact(artifact: &ArbitrationArtifact, dispute_id: Uuid) -> Result<(), ArbiterError> {
    if artifact.schema_version != 1
        || artifact.dispute_id != dispute_id
        || artifact.evidence.trim().is_empty()
        || artifact.evidence.len() > MAX_EVIDENCE_BYTES
    {
        return Err(ArbiterError::MalformedArtifact);
    }
    Ok(())
}

#[derive(Debug, Error)]
pub enum ArbiterError {
    #[error("minted seat bearer is empty or not UTF-8")]
    MalformedBearer,
    #[error("arbiter sandbox exposed sibling or shared scratch")]
    IsolationProbe,
    #[error("arbiter child returned fail-closed state {0:?}")]
    ChildState(ChildTerminalState),
    #[error("arbiter workspace path is not UTF-8")]
    NonUtf8Workspace,
    #[error("arbitration artifact is malformed")]
    MalformedArtifact,
    #[error("arbitration JSON failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("arbitration filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("arbiter child spawn failed: {0}")]
    Child(#[from] ChildError),
    #[error("arbiter stage failed: {0}")]
    Stage(#[from] StageError),
    #[error("arbiter worktree failed: {0}")]
    Worktree(#[from] WorktreeError),
}

#[cfg(test)]
mod tests {
    use uuid::Uuid;

    use crate::contracts::{ArbitrationArtifact, ArbitrationDecision, InvocationUsage};

    use super::{ArbiterError, validate_artifact};

    fn artifact(dispute_id: Uuid) -> ArbitrationArtifact {
        ArbitrationArtifact {
            schema_version: 1,
            dispute_id,
            decision: ArbitrationDecision::Author,
            evidence: "the refutation matches the worktree bytes".to_owned(),
            usage: InvocationUsage::default(),
        }
    }

    #[test]
    fn a_conforming_artifact_validates_against_its_dispute() {
        let dispute_id = Uuid::new_v4();
        validate_artifact(&artifact(dispute_id), dispute_id).expect("conforming artifact");
    }

    #[test]
    fn a_wrong_dispute_echo_or_empty_evidence_fails_closed() {
        let dispute_id = Uuid::new_v4();
        assert!(matches!(
            validate_artifact(&artifact(dispute_id), Uuid::new_v4()),
            Err(ArbiterError::MalformedArtifact)
        ));
        let mut empty = artifact(dispute_id);
        empty.evidence = "   ".to_owned();
        assert!(matches!(
            validate_artifact(&empty, dispute_id),
            Err(ArbiterError::MalformedArtifact)
        ));
        let mut oversized = artifact(dispute_id);
        oversized.evidence = "e".repeat(super::MAX_EVIDENCE_BYTES + 1);
        assert!(matches!(
            validate_artifact(&oversized, dispute_id),
            Err(ArbiterError::MalformedArtifact)
        ));
    }
}
