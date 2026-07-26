//! Evidence-gated improvement proposals with a policy-only effect boundary.
//!
//! Model output is always untrusted. This module re-derives evidence from a
//! [`LessonsReport`], re-derives the candidate diff in a detached worktree,
//! and keeps the prompt bundle pinned to the trusted base commit.

use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, OpenOptions},
    io::Write as _,
    os::unix::fs::OpenOptionsExt as _,
    path::{Path, PathBuf},
    pin::Pin,
    process::Command,
    sync::Arc,
    time::Duration,
};

use factory_verify::caps::{self, DiffManifest};
use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use sqlx::{PgPool, Row};
use thiserror::Error;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    artifacts::{ArtifactError, ArtifactStore, StoredArtifact},
    child::{ChildContract, ChildError, ChildTerminalState, IsolatedChildSpawner},
    config::{RoutingConfig, Seat},
    contracts::ResolvedInvocation,
    lessons::{LessonsError, LessonsReport},
    process::{ProcessSpec, run_bounded},
    publisher::{
        CreatePullRequest, GitHubApi, InstallationToken, PublishedPullRequest, RepositoryScope,
        TokenPurpose,
    },
    review::{PolicyReviewPacket, ReviewExecution, SandboxedReviewer},
    worktree::{DetachedWorktree, InspectedPatch, WorktreeError, inspect_patch},
};

pub const PROPOSER_SCHEMA_VERSION: u16 = 1;
pub const MAX_POLICY_FILES: usize = 8;
pub const MAX_POLICY_CHANGED_LINES: u64 = 1_000;
pub const MAX_LESSONS_REPORT_BYTES: usize = 2 * 1024 * 1024;
const MAX_AGENT_TRANSCRIPT_BYTES: usize = 8 * 1024 * 1024;
const PROPOSER_BRANCH_PREFIX: &str = "factory/proposer/";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ProposerState {
    Queued,
    Reporting,
    Proposing,
    Reviewing,
    Publishing,
    IdeaAppended,
    ReadyForReview,
    OpenPrCapReached,
    ReportFailed,
    ReportTooLarge,
    ProposerContractFailed,
    EvidenceCitationFailed,
    AuthoritySurfaceFailed,
    AdversarialReviewFailed,
    PublicationFailed,
    CleanupFailed,
    Killed,
}

impl ProposerState {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Queued => "queued",
            Self::Reporting => "reporting",
            Self::Proposing => "proposing",
            Self::Reviewing => "reviewing",
            Self::Publishing => "publishing",
            Self::IdeaAppended => "idea_appended",
            Self::ReadyForReview => "ready_for_review",
            Self::OpenPrCapReached => "open_pr_cap_reached",
            Self::ReportFailed => "report_failed",
            Self::ReportTooLarge => "report_too_large",
            Self::ProposerContractFailed => "proposer_contract_failed",
            Self::EvidenceCitationFailed => "evidence_citation_failed",
            Self::AuthoritySurfaceFailed => "authority_surface_failed",
            Self::AdversarialReviewFailed => "adversarial_review_failed",
            Self::PublicationFailed => "publication_failed",
            Self::CleanupFailed => "cleanup_failed",
            Self::Killed => "killed",
        }
    }

    #[must_use]
    pub const fn terminal(self) -> bool {
        !matches!(
            self,
            Self::Queued | Self::Reporting | Self::Proposing | Self::Reviewing | Self::Publishing
        )
    }
}

#[derive(Clone, Debug)]
pub struct ProposerRunStore {
    pool: PgPool,
}

#[derive(Clone, Debug)]
pub struct ProposerLease {
    pub holder: String,
    pub fencing_token: i64,
}

impl ProposerRunStore {
    #[must_use]
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn begin(&self, base_sha: &str) -> Result<Uuid, ProposerError> {
        let id = Uuid::new_v4();
        let mut transaction = self.pool.begin().await?;
        sqlx::query(
            r#"
            INSERT INTO factory.proposer_runs (
                id, base_sha, report_sha256, report_max_event_id,
                prompt_bundle_sha256
            ) VALUES ($1,$2,$3,$4,$5)
            "#,
        )
        .bind(id)
        .bind(base_sha)
        .bind(vec![0_u8; 32])
        .bind(0_i64)
        .bind(vec![0_u8; 32])
        .execute(&mut *transaction)
        .await?;
        sqlx::query(
            r#"
            INSERT INTO factory.proposer_events (
                proposer_run_id,event_type,from_state,to_state,reason_code,facts
            ) VALUES ($1,'proposer.queued',NULL,'queued','scheduled',$2)
            "#,
        )
        .bind(id)
        .bind(serde_json::json!({"base_sha": base_sha}))
        .execute(&mut *transaction)
        .await?;
        transaction.commit().await?;
        Ok(id)
    }

    pub async fn bind_packet(
        &self,
        run_id: Uuid,
        packet: &ProposerPacket,
    ) -> Result<(), ProposerError> {
        let report_sha = hex::decode(&packet.report_sha256)
            .map_err(|_| ProposerError::InvalidIdentifier("report SHA-256"))?;
        let prompt_sha = hex::decode(&packet.prompt_bundle.bundle_sha256)
            .map_err(|_| ProposerError::InvalidIdentifier("prompt bundle SHA-256"))?;
        let updated = sqlx::query(
            r#"
            UPDATE factory.proposer_runs
            SET report_sha256=$2,report_max_event_id=$3,prompt_bundle_sha256=$4
            WHERE id=$1 AND state='reporting'
            "#,
        )
        .bind(run_id)
        .bind(report_sha)
        .bind(packet.report.snapshot_max_event_id)
        .bind(prompt_sha)
        .execute(&self.pool)
        .await?;
        if updated.rows_affected() != 1 {
            return Err(ProposerError::LostProposerState {
                expected: ProposerState::Reporting.as_str(),
                actual: "missing_or_not_reporting".to_owned(),
            });
        }
        Ok(())
    }

    pub async fn record_transcript(
        &self,
        run_id: Uuid,
        expected: ProposerState,
        stage: &str,
        artifact: &StoredArtifact,
    ) -> Result<(), ProposerError> {
        let digest = hex::decode(&artifact.sha256)
            .map_err(|_| ProposerError::InvalidIdentifier("transcript SHA-256"))?;
        let mut transaction = self.pool.begin().await?;
        let state: String = sqlx::query_scalar(
            "SELECT state::text FROM factory.proposer_runs WHERE id=$1 FOR UPDATE",
        )
        .bind(run_id)
        .fetch_optional(&mut *transaction)
        .await?
        .ok_or(ProposerError::MissingProposerRun(run_id))?;
        if state != expected.as_str() {
            return Err(ProposerError::LostProposerState {
                expected: expected.as_str(),
                actual: state,
            });
        }
        sqlx::query(
            r#"
            INSERT INTO factory.proposer_artifacts (
                id,proposer_run_id,stage,path,sha256,kind,bytes
            ) VALUES ($1,$2,$3,$4,$5,$6,$7)
            "#,
        )
        .bind(artifact.id)
        .bind(run_id)
        .bind(stage)
        .bind(&artifact.relative_path)
        .bind(digest)
        .bind(&artifact.kind)
        .bind(i64::try_from(artifact.bytes).map_err(|_| ProposerError::TranscriptTooLarge)?)
        .execute(&mut *transaction)
        .await?;
        sqlx::query(
            r#"
            INSERT INTO factory.proposer_events (
                proposer_run_id,event_type,from_state,to_state,reason_code,facts
            ) VALUES ($1,'agent.transcript.persisted',$2::factory.proposer_state,
                      $2::factory.proposer_state,'private_artifact_registered',$3)
            "#,
        )
        .bind(run_id)
        .bind(expected.as_str())
        .bind(serde_json::json!({
            "stage": stage,
            "path": artifact.relative_path,
            "sha256": artifact.sha256,
            "bytes": artifact.bytes,
        }))
        .execute(&mut *transaction)
        .await?;
        transaction.commit().await?;
        Ok(())
    }

    pub async fn transition(
        &self,
        run_id: Uuid,
        expected: ProposerState,
        next: ProposerState,
        reason_code: &str,
        facts: serde_json::Value,
    ) -> Result<(), ProposerError> {
        if !allowed_transition(expected, next)
            || reason_code.is_empty()
            || reason_code.len() > 128
            || reason_code.chars().any(char::is_control)
        {
            return Err(ProposerError::InvalidTransition);
        }
        let mut transaction = self.pool.begin().await?;
        let row = sqlx::query(
            "SELECT state::text AS state FROM factory.proposer_runs WHERE id=$1 FOR UPDATE",
        )
        .bind(run_id)
        .fetch_optional(&mut *transaction)
        .await?
        .ok_or(ProposerError::MissingProposerRun(run_id))?;
        let actual: String = row.try_get("state")?;
        if actual != expected.as_str() {
            return Err(ProposerError::LostProposerState {
                expected: expected.as_str(),
                actual,
            });
        }
        sqlx::query(
            r#"
            UPDATE factory.proposer_runs
            SET state=$2::factory.proposer_state,
                started_at=COALESCE(started_at, clock_timestamp()),
                finished_at=CASE WHEN $3 THEN clock_timestamp() ELSE NULL END,
                failure_code=CASE WHEN $3 AND $2 NOT IN
                    ('idea_appended','ready_for_review','open_pr_cap_reached')
                    THEN $4 ELSE NULL END
            WHERE id=$1
            "#,
        )
        .bind(run_id)
        .bind(next.as_str())
        .bind(next.terminal())
        .bind(reason_code)
        .execute(&mut *transaction)
        .await?;
        sqlx::query(
            r#"
            INSERT INTO factory.proposer_events (
                proposer_run_id,event_type,from_state,to_state,reason_code,facts
            ) VALUES ($1,$2,$3::factory.proposer_state,$4::factory.proposer_state,$5,$6)
            "#,
        )
        .bind(run_id)
        .bind(format!("proposer.{}", next.as_str()))
        .bind(expected.as_str())
        .bind(next.as_str())
        .bind(reason_code)
        .bind(facts)
        .execute(&mut *transaction)
        .await?;
        transaction.commit().await?;
        Ok(())
    }

    pub async fn acquire_publish_lease(
        &self,
        holder: &str,
        ttl: Duration,
    ) -> Result<ProposerLease, ProposerError> {
        if holder.trim().is_empty()
            || holder.len() > 128
            || ttl.is_zero()
            || ttl > Duration::from_secs(3_600)
        {
            return Err(ProposerError::InvalidPublisherConfig);
        }
        let seconds =
            i64::try_from(ttl.as_secs()).map_err(|_| ProposerError::InvalidPublisherConfig)?;
        let mut transaction = self.pool.begin().await?;
        let row = sqlx::query(
            r#"
            SELECT holder,fencing_token,expires_at,released_at,
                   clock_timestamp() AS now
            FROM factory.proposer_publisher_lease
            WHERE singleton FOR UPDATE
            "#,
        )
        .fetch_one(&mut *transaction)
        .await?;
        let current_holder: Option<String> = row.try_get("holder")?;
        let token: i64 = row.try_get("fencing_token")?;
        let expires_at: Option<time::OffsetDateTime> = row.try_get("expires_at")?;
        let released_at: Option<time::OffsetDateTime> = row.try_get("released_at")?;
        let now: time::OffsetDateTime = row.try_get("now")?;
        if current_holder.is_some()
            && released_at.is_none()
            && expires_at.is_some_and(|expiry| expiry > now)
        {
            return Err(ProposerError::PublisherLeaseHeld(
                current_holder.unwrap_or_default(),
            ));
        }
        let fencing_token = token
            .checked_add(1)
            .ok_or(ProposerError::PublisherFenceExhausted)?;
        sqlx::query(
            r#"
            UPDATE factory.proposer_publisher_lease
            SET holder=$1,fencing_token=$2,acquired_at=$3,
                expires_at=$3 + make_interval(secs => $4),released_at=NULL
            WHERE singleton
            "#,
        )
        .bind(holder)
        .bind(fencing_token)
        .bind(now)
        .bind(seconds)
        .execute(&mut *transaction)
        .await?;
        transaction.commit().await?;
        Ok(ProposerLease {
            holder: holder.to_owned(),
            fencing_token,
        })
    }

    pub async fn release_publish_lease(&self, lease: &ProposerLease) -> Result<(), ProposerError> {
        let updated = sqlx::query(
            r#"
            UPDATE factory.proposer_publisher_lease
            SET released_at=clock_timestamp()
            WHERE singleton AND holder=$1 AND fencing_token=$2
              AND released_at IS NULL
            "#,
        )
        .bind(&lease.holder)
        .bind(lease.fencing_token)
        .execute(&self.pool)
        .await?;
        if updated.rows_affected() != 1 {
            return Err(ProposerError::PublisherLeaseLost);
        }
        Ok(())
    }

    pub async fn record_pull_request(
        &self,
        run_id: Uuid,
        branch: &str,
        patch_sha256: &str,
        pull: &PublishedPullRequest,
    ) -> Result<(), ProposerError> {
        let patch = hex::decode(patch_sha256)
            .map_err(|_| ProposerError::InvalidIdentifier("patch SHA-256"))?;
        let updated = sqlx::query(
            r#"
            UPDATE factory.proposer_runs
            SET branch=$2,patch_sha256=$3,pr_number=$4,pr_url=$5
            WHERE id=$1
            "#,
        )
        .bind(run_id)
        .bind(branch)
        .bind(patch)
        .bind(pull.number)
        .bind(&pull.url)
        .execute(&self.pool)
        .await?;
        if updated.rows_affected() != 1 {
            return Err(ProposerError::MissingProposerRun(run_id));
        }
        Ok(())
    }
}

fn allowed_transition(from: ProposerState, to: ProposerState) -> bool {
    use ProposerState::{
        AdversarialReviewFailed, AuthoritySurfaceFailed, CleanupFailed, EvidenceCitationFailed,
        IdeaAppended, Killed, OpenPrCapReached, ProposerContractFailed, Proposing,
        PublicationFailed, Publishing, Queued, ReadyForReview, ReportFailed, ReportTooLarge,
        Reporting, Reviewing,
    };
    matches!(
        (from, to),
        (Queued, Reporting)
            | (
                Reporting,
                Proposing | ReportFailed | ReportTooLarge | ProposerContractFailed | Killed
            )
            | (
                Proposing,
                Reviewing
                    | IdeaAppended
                    | OpenPrCapReached
                    | ProposerContractFailed
                    | EvidenceCitationFailed
                    | AuthoritySurfaceFailed
                    | PublicationFailed
                    | CleanupFailed
                    | Killed
            )
            | (
                Reviewing,
                Publishing | AdversarialReviewFailed | CleanupFailed | Killed
            )
            | (
                Publishing,
                ReadyForReview | OpenPrCapReached | PublicationFailed | CleanupFailed | Killed
            )
    )
}

fn cancelled_or(cancellation: &CancellationToken, otherwise: ProposerState) -> ProposerState {
    if cancellation.is_cancelled() {
        ProposerState::Killed
    } else {
        otherwise
    }
}

pub type PolicyPublisherFuture<'a, T> =
    Pin<Box<dyn std::future::Future<Output = Result<T, ProposerError>> + Send + 'a>>;

pub trait PolicyPublicationService: Send + Sync {
    fn has_open_proposer_pr<'a>(
        &'a self,
        cancellation: &'a CancellationToken,
    ) -> PolicyPublisherFuture<'a, bool>;

    fn publish<'a>(
        &'a self,
        run_id: Uuid,
        packet: &'a ProposerPacket,
        intent: &'a ProposalIntent,
        validated: &'a ValidatedPolicyPatch,
        body: &'a str,
        cancellation: &'a CancellationToken,
    ) -> PolicyPublisherFuture<'a, PublishedPullRequest>;
}

#[derive(Clone, Debug)]
pub struct ImprovementProposerConfig {
    pub repository: PathBuf,
    pub ideas_path: PathBuf,
    pub scratch: PathBuf,
    pub base_sha: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ProposerOutcome {
    IdeaAppended {
        run_id: Uuid,
    },
    ReadyForReview {
        run_id: Uuid,
        pull_request: PublishedPullRequest,
    },
    OpenPrCapReached {
        run_id: Uuid,
    },
}

pub struct ImprovementProposer {
    store: ProposerRunStore,
    artifacts: ArtifactStore,
    agent: Arc<dyn ProposerAgentService>,
    reviewer: Arc<dyn PolicyAdversarialReviewService>,
    publisher: Arc<dyn PolicyPublicationService>,
    routing: RoutingConfig,
    config: ImprovementProposerConfig,
}

struct PatchTermination<'a> {
    run_id: Uuid,
    current: ProposerState,
    intended: ProposerState,
    reason: &'static str,
    patch_path: &'a Path,
    primary: ProposerError,
    facts: serde_json::Value,
}

impl ImprovementProposer {
    pub fn new(
        store: ProposerRunStore,
        artifacts: ArtifactStore,
        agent: Arc<dyn ProposerAgentService>,
        reviewer: Arc<dyn PolicyAdversarialReviewService>,
        publisher: Arc<dyn PolicyPublicationService>,
        routing: RoutingConfig,
        config: ImprovementProposerConfig,
    ) -> Result<Self, ProposerError> {
        require_lower_hex(&config.base_sha, 40, "proposer base SHA")?;
        let author = routing
            .resolve("improvement_proposer")
            .map_err(|_| ProposerError::InvalidRouting)?;
        let reviewer_rule = routing
            .resolve("improvement_proposer_review")
            .map_err(|_| ProposerError::InvalidRouting)?;
        if author.reviewers != ["improvement_proposer_review"]
            || author.seat.family() == reviewer_rule.seat.family()
            || author.seat.harness == reviewer_rule.seat.harness
        {
            return Err(ProposerError::InvalidRouting);
        }
        Ok(Self {
            store,
            artifacts,
            agent,
            reviewer,
            publisher,
            routing,
            config,
        })
    }

    pub async fn run(
        &self,
        report: LessonsReport,
        cancellation: &CancellationToken,
    ) -> Result<ProposerOutcome, ProposerError> {
        let run_id = self.start_reporting().await?;
        self.run_report(run_id, report, cancellation).await
    }

    pub async fn run_from_ledger(
        &self,
        pool: &PgPool,
        cancellation: &CancellationToken,
    ) -> Result<ProposerOutcome, ProposerError> {
        let run_id = self.start_reporting().await?;
        let generated = tokio::select! {
            () = cancellation.cancelled() => {
                self.store
                    .transition(
                        run_id,
                        ProposerState::Reporting,
                        ProposerState::Killed,
                        "cancelled_during_report",
                        serde_json::json!({}),
                    )
                    .await?;
                return Err(ProposerError::Cancelled);
            }
            result = crate::lessons::generate(pool) => result,
        };
        let report = match generated {
            Ok(report) => report,
            Err(error) => {
                self.store
                    .transition(
                        run_id,
                        ProposerState::Reporting,
                        ProposerState::ReportFailed,
                        "lessons_report_failed",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error.into());
            }
        };
        self.run_report(run_id, report, cancellation).await
    }

    async fn start_reporting(&self) -> Result<Uuid, ProposerError> {
        let run_id = self.store.begin(&self.config.base_sha).await?;
        self.store
            .transition(
                run_id,
                ProposerState::Queued,
                ProposerState::Reporting,
                "report_started",
                serde_json::json!({}),
            )
            .await?;
        Ok(run_id)
    }

    async fn run_report(
        &self,
        run_id: Uuid,
        report: LessonsReport,
        cancellation: &CancellationToken,
    ) -> Result<ProposerOutcome, ProposerError> {
        if let Err(error) = report.validate() {
            self.store
                .transition(
                    run_id,
                    ProposerState::Reporting,
                    ProposerState::ReportFailed,
                    "lessons_report_invalid",
                    serde_json::json!({"error": error.to_string()}),
                )
                .await?;
            return Err(error.into());
        }
        let repository = self.config.repository.clone();
        let base_sha = self.config.base_sha.clone();
        let bundles = tokio::task::spawn_blocking(move || {
            Ok::<_, ProposerError>((
                load_prompt_bundle(&repository, &base_sha, BundleRole::Author)?,
                load_prompt_bundle(&repository, &base_sha, BundleRole::Reviewer)?,
            ))
        })
        .await;
        let (author_bundle, reviewer_bundle) = match bundles {
            Ok(Ok(bundles)) => bundles,
            Ok(Err(error)) => {
                self.store
                    .transition(
                        run_id,
                        ProposerState::Reporting,
                        ProposerState::ProposerContractFailed,
                        "prompt_bundle_failed",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error);
            }
            Err(error) => {
                let error = ProposerError::Join(error);
                self.store
                    .transition(
                        run_id,
                        ProposerState::Reporting,
                        ProposerState::ProposerContractFailed,
                        "prompt_bundle_task_failed",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error);
            }
        };
        let packet = match build_packet(&self.config.base_sha, report, &author_bundle) {
            Ok(packet) => packet,
            Err(error) => {
                let terminal = if matches!(error, ProposerError::ReportTooLarge { .. }) {
                    ProposerState::ReportTooLarge
                } else {
                    ProposerState::ReportFailed
                };
                self.store
                    .transition(
                        run_id,
                        ProposerState::Reporting,
                        terminal,
                        "lessons_report_packet_failed",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error);
            }
        };
        self.store.bind_packet(run_id, &packet).await?;
        self.store
            .transition(
                run_id,
                ProposerState::Reporting,
                ProposerState::Proposing,
                "prompt_bundle_pinned",
                serde_json::json!({
                    "report_sha256": packet.report_sha256,
                    "snapshot_max_event_id": packet.report.snapshot_max_event_id,
                    "author_bundle_sha256": author_bundle.manifest.bundle_sha256,
                    "reviewer_bundle_sha256": reviewer_bundle.manifest.bundle_sha256,
                }),
            )
            .await?;

        let threshold_reached = packet
            .report
            .cohorts
            .iter()
            .any(|cohort| cohort.eligible_for_policy_pr);
        if threshold_reached {
            match self.publisher.has_open_proposer_pr(cancellation).await {
                Ok(true) => {
                    self.store
                        .transition(
                            run_id,
                            ProposerState::Proposing,
                            ProposerState::OpenPrCapReached,
                            "fresh_github_open_cap",
                            serde_json::json!({}),
                        )
                        .await?;
                    return Ok(ProposerOutcome::OpenPrCapReached { run_id });
                }
                Ok(false) => {}
                Err(error) => {
                    let terminal = cancelled_or(cancellation, ProposerState::PublicationFailed);
                    self.store
                        .transition(
                            run_id,
                            ProposerState::Proposing,
                            terminal,
                            "open_pr_observation_failed",
                            serde_json::json!({"error": error.to_string()}),
                        )
                        .await?;
                    return Err(error);
                }
            }
        }

        let prompt = match render_effective_prompt(&author_bundle, &packet) {
            Ok(prompt) => prompt,
            Err(error) => {
                self.store
                    .transition(
                        run_id,
                        ProposerState::Proposing,
                        ProposerState::ProposerContractFailed,
                        "effective_prompt_failed",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error);
            }
        };
        let author_rule = match self.routing.resolve("improvement_proposer") {
            Ok(rule) => rule,
            Err(_) => {
                let error = ProposerError::InvalidRouting;
                self.store
                    .transition(
                        run_id,
                        ProposerState::Proposing,
                        ProposerState::ProposerContractFailed,
                        "author_routing_failed",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error);
            }
        };
        let execution = match self
            .agent
            .invoke(&packet, prompt, &author_rule.seat, cancellation)
            .await
        {
            Ok(execution) => execution,
            Err(error) => {
                self.store
                    .transition(
                        run_id,
                        ProposerState::Proposing,
                        cancelled_or(cancellation, ProposerState::ProposerContractFailed),
                        "agent_contract_or_execution",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error);
            }
        };
        let author_transcript = match self
            .persist_transcript(run_id, "proposer-author", execution.transcript.clone())
            .await
        {
            Ok(artifact) => artifact,
            Err(error) => {
                self.store
                    .transition(
                        run_id,
                        ProposerState::Proposing,
                        ProposerState::ProposerContractFailed,
                        "author_transcript_persist_failed",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error);
            }
        };
        if let Err(error) = validate_intent(&packet.report, &execution.intent) {
            let terminal = if matches!(error, ProposerError::EvidenceCitation) {
                ProposerState::EvidenceCitationFailed
            } else {
                ProposerState::ProposerContractFailed
            };
            self.store
                .transition(
                    run_id,
                    ProposerState::Proposing,
                    terminal,
                    "supervisor_rederivation",
                    serde_json::json!({"error": error.to_string()}),
                )
                .await?;
            return Err(error);
        }

        if !threshold_reached {
            let append = match render_idea_append(
                &packet.report,
                &packet.report_sha256,
                &execution.intent,
            ) {
                Ok(append) => append,
                Err(error) => {
                    self.store
                        .transition(
                            run_id,
                            ProposerState::Proposing,
                            ProposerState::ProposerContractFailed,
                            "idea_render_failed",
                            serde_json::json!({"error": error.to_string()}),
                        )
                        .await?;
                    return Err(error);
                }
            };
            let ideas_path = self.config.ideas_path.clone();
            let append_result =
                tokio::task::spawn_blocking(move || append_idea(&ideas_path, &append)).await;
            if let Err(error) = match append_result {
                Ok(result) => result,
                Err(error) => Err(ProposerError::Join(error)),
            } {
                self.store
                    .transition(
                        run_id,
                        ProposerState::Proposing,
                        ProposerState::CleanupFailed,
                        "idea_append_failed",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error);
            }
            self.store
                .transition(
                    run_id,
                    ProposerState::Proposing,
                    ProposerState::IdeaAppended,
                    "below_threshold_append_only",
                    serde_json::json!({
                        "report_sha256": packet.report_sha256,
                        "production_run_count": packet.report.production_run_count,
                        "transcript_sha256": author_transcript.sha256,
                    }),
                )
                .await?;
            return Ok(ProposerOutcome::IdeaAppended { run_id });
        }

        let validated = match inspect_policy_intent(
            &self.config.repository,
            &self.config.base_sha,
            &self.config.scratch.join("inspect"),
            &author_bundle.manifest,
            &reviewer_bundle.manifest,
            &execution.intent,
            cancellation,
        )
        .await
        {
            Ok(validated) => validated,
            Err(error) => {
                let terminal = cancelled_or(cancellation, ProposerState::AuthoritySurfaceFailed);
                self.store
                    .transition(
                        run_id,
                        ProposerState::Proposing,
                        terminal,
                        "diff_authority_gate",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error);
            }
        };
        self.store
            .transition(
                run_id,
                ProposerState::Proposing,
                ProposerState::Reviewing,
                "authority_surface_passed",
                serde_json::json!({
                    "patch_sha256": validated.inspected.patch_sha256,
                    "paths": validated.inspected.manifest.files.iter()
                        .map(|file| file.path.as_str()).collect::<Vec<_>>(),
                    "self_referential_paths": validated.self_referential_paths,
                    "author_transcript_sha256": author_transcript.sha256,
                }),
            )
            .await?;
        let reviewed_sha = match crate::worktree::materialize_review_sha(
            &self.config.repository,
            &self.config.base_sha,
            &validated.patch_path,
            &self.config.scratch.join("review-materialize"),
            cancellation,
        )
        .await
        {
            Ok(reviewed_sha) => reviewed_sha,
            Err(error) => {
                let error = self
                    .terminate_after_patch_cleanup(PatchTermination {
                        run_id,
                        current: ProposerState::Reviewing,
                        intended: cancelled_or(
                            cancellation,
                            ProposerState::AdversarialReviewFailed,
                        ),
                        reason: "review_candidate_materialization_failed",
                        patch_path: &validated.patch_path,
                        primary: error.into(),
                        facts: serde_json::json!({}),
                    })
                    .await?;
                return Err(error);
            }
        };
        let review_packet = PolicyReviewPacket {
            schema_version: 1,
            review_id: Uuid::new_v4(),
            reviewed_sha,
            report_sha256: packet.report_sha256.clone(),
            patch_sha256: validated.inspected.patch_sha256.clone(),
            citations: execution.intent.citations().to_vec(),
            manifest: validated.inspected.manifest.clone(),
            self_referential_paths: validated.self_referential_paths.clone(),
            author_prompt_bundle: author_bundle.manifest.clone(),
            reviewer_prompt_bundle: reviewer_bundle.manifest.clone(),
            report: packet.report.clone(),
        };
        let reviewer_rule = match self.routing.resolve("improvement_proposer_review") {
            Ok(rule) => rule,
            Err(_) => {
                let error = self
                    .terminate_after_patch_cleanup(PatchTermination {
                        run_id,
                        current: ProposerState::Reviewing,
                        intended: ProposerState::AdversarialReviewFailed,
                        reason: "reviewer_routing_failed",
                        patch_path: &validated.patch_path,
                        primary: ProposerError::InvalidRouting,
                        facts: serde_json::json!({}),
                    })
                    .await?;
                return Err(error);
            }
        };
        let reviewer_prompt = match reviewer_bundle.file("policy/proposer-review.md") {
            Ok(prompt) => prompt.to_vec(),
            Err(error) => {
                let error = self
                    .terminate_after_patch_cleanup(PatchTermination {
                        run_id,
                        current: ProposerState::Reviewing,
                        intended: ProposerState::AdversarialReviewFailed,
                        reason: "reviewer_prompt_failed",
                        patch_path: &validated.patch_path,
                        primary: error,
                        facts: serde_json::json!({}),
                    })
                    .await?;
                return Err(error);
            }
        };
        let review = match self
            .reviewer
            .review(
                &self.config.repository,
                &review_packet,
                reviewer_prompt,
                ResolvedInvocation {
                    task_class: "improvement_proposer_review".to_owned(),
                    routing_version: self.routing.version.clone(),
                    seat: reviewer_rule.seat.clone(),
                },
                cancellation,
            )
            .await
        {
            Ok(review) => review,
            Err(error) => {
                let error = self
                    .terminate_after_patch_cleanup(PatchTermination {
                        run_id,
                        current: ProposerState::Reviewing,
                        intended: cancelled_or(
                            cancellation,
                            ProposerState::AdversarialReviewFailed,
                        ),
                        reason: "review_execution_failed",
                        patch_path: &validated.patch_path,
                        primary: error,
                        facts: serde_json::json!({}),
                    })
                    .await?;
                return Err(error);
            }
        };
        let reviewer_transcript = match self
            .persist_transcript(run_id, "proposer-reviewer", review.transcript.clone())
            .await
        {
            Ok(artifact) => artifact,
            Err(error) => {
                let error = self
                    .terminate_after_patch_cleanup(PatchTermination {
                        run_id,
                        current: ProposerState::Reviewing,
                        intended: ProposerState::AdversarialReviewFailed,
                        reason: "review_transcript_persist_failed",
                        patch_path: &validated.patch_path,
                        primary: error,
                        facts: serde_json::json!({}),
                    })
                    .await?;
                return Err(error);
            }
        };
        if !review.artifact.findings.is_empty() {
            let error = self
                .terminate_after_patch_cleanup(PatchTermination {
                    run_id,
                    current: ProposerState::Reviewing,
                    intended: ProposerState::AdversarialReviewFailed,
                    reason: "review_findings_require_new_attempt",
                    patch_path: &validated.patch_path,
                    primary: ProposerError::AdversarialReviewFindings,
                    facts: serde_json::json!({
                        "review_id": review.artifact.review_id,
                        "reviewer_transcript_sha256": reviewer_transcript.sha256,
                        "finding_ids": review.artifact.findings.iter()
                            .map(|finding| finding.id.as_str()).collect::<Vec<_>>(),
                    }),
                })
                .await?;
            return Err(error);
        }
        self.store
            .transition(
                run_id,
                ProposerState::Reviewing,
                ProposerState::Publishing,
                "cross_family_review_clean",
                serde_json::json!({
                    "review_id": review.artifact.review_id,
                    "reviewer": review.invocation,
                    "reviewer_transcript_sha256": reviewer_transcript.sha256,
                }),
            )
            .await?;
        let body = match build_policy_pr_body(&packet, &execution.intent, &validated) {
            Ok(body) => body,
            Err(error) => {
                let error = self
                    .terminate_after_patch_cleanup(PatchTermination {
                        run_id,
                        current: ProposerState::Publishing,
                        intended: ProposerState::PublicationFailed,
                        reason: "pull_request_body_failed",
                        patch_path: &validated.patch_path,
                        primary: error,
                        facts: serde_json::json!({}),
                    })
                    .await?;
                return Err(error);
            }
        };
        let published = self
            .publisher
            .publish(
                run_id,
                &packet,
                &execution.intent,
                &validated,
                &body,
                cancellation,
            )
            .await;
        let cleanup = cleanup_patch(&validated.patch_path).await;
        let published = match (published, cleanup) {
            (Ok(pull), Ok(())) => pull,
            (Err(ProposerError::OpenProposerPrCap), Ok(())) => {
                self.store
                    .transition(
                        run_id,
                        ProposerState::Publishing,
                        ProposerState::OpenPrCapReached,
                        "fresh_github_open_cap",
                        serde_json::json!({}),
                    )
                    .await?;
                return Ok(ProposerOutcome::OpenPrCapReached { run_id });
            }
            (Err(error), Ok(())) => {
                let terminal = cancelled_or(cancellation, ProposerState::PublicationFailed);
                self.store
                    .transition(
                        run_id,
                        ProposerState::Publishing,
                        terminal,
                        "publisher_failed",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error);
            }
            (_, Err(error)) => {
                self.store
                    .transition(
                        run_id,
                        ProposerState::Publishing,
                        ProposerState::CleanupFailed,
                        "patch_cleanup_failed",
                        serde_json::json!({"error": error.to_string()}),
                    )
                    .await?;
                return Err(error);
            }
        };
        self.store
            .transition(
                run_id,
                ProposerState::Publishing,
                ProposerState::ReadyForReview,
                "draft_pr_opened",
                serde_json::json!({
                    "number": published.number,
                    "url": published.url,
                    "branch": published.branch,
                    "head_sha": published.head_sha,
                    "author_login": published.author_login,
                }),
            )
            .await?;
        Ok(ProposerOutcome::ReadyForReview {
            run_id,
            pull_request: published,
        })
    }

    async fn persist_transcript(
        &self,
        run_id: Uuid,
        stage: &str,
        bytes: Vec<u8>,
    ) -> Result<StoredArtifact, ProposerError> {
        let artifact = self
            .artifacts
            .put(
                run_id,
                None,
                stage,
                "transcript.log",
                "agent-transcript",
                bytes,
                MAX_AGENT_TRANSCRIPT_BYTES,
            )
            .await?;
        let expected = if stage == "proposer-author" {
            ProposerState::Proposing
        } else {
            ProposerState::Reviewing
        };
        self.store
            .record_transcript(run_id, expected, stage, &artifact)
            .await?;
        Ok(artifact)
    }

    async fn terminate_after_patch_cleanup(
        &self,
        failure: PatchTermination<'_>,
    ) -> Result<ProposerError, ProposerError> {
        let PatchTermination {
            run_id,
            current,
            intended,
            reason,
            patch_path,
            primary,
            mut facts,
        } = failure;
        match cleanup_patch(patch_path).await {
            Ok(()) => {
                if let Some(object) = facts.as_object_mut() {
                    object.insert(
                        "error".to_owned(),
                        serde_json::Value::String(primary.to_string()),
                    );
                }
                self.store
                    .transition(run_id, current, intended, reason, facts)
                    .await?;
                Ok(primary)
            }
            Err(cleanup) => {
                self.store
                    .transition(
                        run_id,
                        current,
                        ProposerState::CleanupFailed,
                        "patch_cleanup_failed",
                        serde_json::json!({
                            "primary_error": primary.to_string(),
                            "cleanup_error": cleanup.to_string(),
                        }),
                    )
                    .await?;
                Ok(cleanup)
            }
        }
    }
}

async fn cleanup_patch(path: &Path) -> Result<(), ProposerError> {
    match tokio::fs::remove_file(path).await {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
    }
}

#[derive(Clone, Debug)]
pub struct PolicyPublisherConfig {
    pub installed_repository: PathBuf,
    pub scratch: PathBuf,
    pub git_program: PathBuf,
    pub git_askpass: PathBuf,
    pub repository: RepositoryScope,
    pub base_branch: String,
    pub holder: String,
    pub lease_ttl: Duration,
    pub github_freshness: Duration,
}

#[derive(Clone)]
pub struct PolicyPublisher {
    store: ProposerRunStore,
    github: Arc<dyn GitHubApi>,
    config: PolicyPublisherConfig,
}

impl PolicyPublisher {
    pub fn new(
        store: ProposerRunStore,
        github: Arc<dyn GitHubApi>,
        config: PolicyPublisherConfig,
    ) -> Result<Self, ProposerError> {
        config
            .repository
            .validate()
            .map_err(|_| ProposerError::InvalidPublisherConfig)?;
        if config.holder.trim().is_empty()
            || config.base_branch != "master"
            || config.lease_ttl != Duration::from_secs(3_600)
            || config.github_freshness.is_zero()
            || config.github_freshness > Duration::from_secs(300)
        {
            return Err(ProposerError::InvalidPublisherConfig);
        }
        Ok(Self {
            store,
            github,
            config,
        })
    }

    async fn fresh_open_count(
        &self,
        token: &InstallationToken,
        cancellation: &CancellationToken,
    ) -> Result<usize, ProposerError> {
        let snapshot = self
            .github
            .open_pull_requests(token, &self.config.repository, 100, cancellation)
            .await?;
        let age = time::OffsetDateTime::now_utc() - snapshot.observed_at;
        if age.is_negative()
            || age
                > time::Duration::try_from(self.config.github_freshness)
                    .map_err(|_| ProposerError::InvalidPublisherConfig)?
        {
            return Err(ProposerError::StaleGitHubSnapshot);
        }
        Ok(snapshot
            .pull_requests
            .iter()
            .filter(|pull| pull.head.branch.starts_with(PROPOSER_BRANCH_PREFIX))
            .count())
    }

    async fn publish_inner(
        &self,
        run_id: Uuid,
        packet: &ProposerPacket,
        intent: &ProposalIntent,
        validated: &ValidatedPolicyPatch,
        body: &str,
        cancellation: &CancellationToken,
    ) -> Result<PublishedPullRequest, ProposerError> {
        validate_intent(&packet.report, intent)?;
        let branch = format!("{PROPOSER_BRANCH_PREFIX}{}", &packet.report_sha256[..16]);
        let lease = self
            .store
            .acquire_publish_lease(
                &format!("{}:{run_id}", self.config.holder),
                self.config.lease_ttl,
            )
            .await?;
        let result = async {
            let token = self
                .github
                .mint_token(&self.config.repository, TokenPurpose::Publish, cancellation)
                .await?;
            let existing = self
                .github
                .pull_requests_for_branch(&token, &self.config.repository, &branch, cancellation)
                .await?;
            if existing.len() > 1 {
                return Err(ProposerError::MultiplePullRequests);
            }
            if let Some(pull) = existing.first() {
                return validate_policy_pull(pull, &token, &branch, &self.config.base_branch);
            }
            if self.fresh_open_count(&token, cancellation).await? >= 1 {
                return Err(ProposerError::OpenProposerPrCap);
            }
            let head_sha = self
                .prepare_and_push(
                    &token,
                    run_id,
                    packet,
                    intent,
                    validated,
                    &branch,
                    cancellation,
                )
                .await?;
            // Re-observe immediately before PR creation. The singleton lease
            // serializes this publisher; fresh GitHub truth catches external
            // bot-authored proposer branches/PRs.
            if self.fresh_open_count(&token, cancellation).await? >= 1 {
                return Err(ProposerError::OpenProposerPrCap);
            }
            let pull = self
                .github
                .create_draft_pull_request(
                    &token,
                    &self.config.repository,
                    &CreatePullRequest {
                        title: format!("Policy: {}", intent.title()),
                        head: branch.clone(),
                        base: self.config.base_branch.clone(),
                        body: body.to_owned(),
                        draft: true,
                    },
                    cancellation,
                )
                .await?;
            let published = validate_policy_pull(&pull, &token, &branch, &self.config.base_branch)?;
            if published.head_sha != head_sha {
                return Err(ProposerError::PublishedHeadMismatch);
            }
            self.store
                .record_pull_request(
                    run_id,
                    &branch,
                    &validated.inspected.patch_sha256,
                    &published,
                )
                .await?;
            Ok(published)
        }
        .await;
        let release = self.store.release_publish_lease(&lease).await;
        match (result, release) {
            (Ok(pull), Ok(())) => Ok(pull),
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error),
        }
    }

    #[allow(clippy::too_many_arguments)]
    async fn prepare_and_push(
        &self,
        token: &InstallationToken,
        run_id: Uuid,
        packet: &ProposerPacket,
        _intent: &ProposalIntent,
        validated: &ValidatedPolicyPatch,
        branch: &str,
        cancellation: &CancellationToken,
    ) -> Result<String, ProposerError> {
        tokio::fs::create_dir_all(&self.config.scratch).await?;
        let mirror = self.config.scratch.join("factory-policy.git");
        if !tokio::fs::try_exists(&mirror).await? {
            let output = self
                .git(
                    token,
                    vec![
                        "clone".into(),
                        "--bare".into(),
                        self.config.installed_repository.as_os_str().to_owned(),
                        mirror.as_os_str().to_owned(),
                    ],
                    cancellation,
                )
                .await?;
            require_process_success("clone policy mirror", output.code)?;
        }
        let remote_url = format!(
            "https://github.com/{}/{}.git",
            self.config.repository.owner, self.config.repository.name
        );
        let output = self
            .git(
                token,
                vec![
                    "-C".into(),
                    mirror.as_os_str().to_owned(),
                    "remote".into(),
                    "set-url".into(),
                    "origin".into(),
                    remote_url.into(),
                ],
                cancellation,
            )
            .await?;
        require_process_success("set policy mirror remote", output.code)?;
        let worktree = DetachedWorktree::create(
            &mirror,
            &packet.base_sha,
            &self.config.scratch.join("worktrees"),
            &format!("proposer-{}", run_id.simple()),
            cancellation,
        )
        .await?;
        let result = async {
            let output = self
                .git(
                    token,
                    vec![
                        "-C".into(),
                        worktree.path().as_os_str().to_owned(),
                        "apply".into(),
                        "--index".into(),
                        validated.patch_path.as_os_str().to_owned(),
                    ],
                    cancellation,
                )
                .await?;
            require_process_success("apply policy patch", output.code)?;
            let output = self
                .git(
                    token,
                    vec![
                        "-C".into(),
                        worktree.path().as_os_str().to_owned(),
                        "-c".into(),
                        format!("user.name={}", token.bot.login).into(),
                        "-c".into(),
                        format!("user.email={}", token.bot.email()).into(),
                        "commit".into(),
                        "--no-gpg-sign".into(),
                        "-m".into(),
                        format!(
                            "Propose policy improvement from {}",
                            &packet.report_sha256[..12]
                        )
                        .into(),
                    ],
                    cancellation,
                )
                .await?;
            require_process_success("commit policy patch", output.code)?;
            let output = self
                .git(
                    token,
                    vec![
                        "-C".into(),
                        worktree.path().as_os_str().to_owned(),
                        "rev-parse".into(),
                        "HEAD".into(),
                    ],
                    cancellation,
                )
                .await?;
            require_process_success("read policy head", output.code)?;
            let head = String::from_utf8(output.stdout)
                .map_err(|_| ProposerError::MalformedGitOutput)?
                .trim()
                .to_owned();
            require_lower_hex(&head, 40, "policy head SHA")?;
            let output = self
                .git(
                    token,
                    vec![
                        "-C".into(),
                        mirror.as_os_str().to_owned(),
                        "push".into(),
                        "origin".into(),
                        format!("{head}:refs/heads/{branch}").into(),
                    ],
                    cancellation,
                )
                .await?;
            require_process_success("push policy branch", output.code)?;
            Ok(head)
        }
        .await;
        let cleanup = worktree.close(&CancellationToken::new()).await;
        match (result, cleanup) {
            (Ok(head), Ok(())) => Ok(head),
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error.into()),
        }
    }

    async fn git(
        &self,
        token: &InstallationToken,
        arguments: Vec<std::ffi::OsString>,
        cancellation: &CancellationToken,
    ) -> Result<crate::process::ProcessOutput, ProposerError> {
        let mut spec = ProcessSpec::new(&self.config.git_program);
        spec.args = arguments;
        spec.environment = vec![
            ("PATCHYARD_GITHUB_TOKEN".into(), token.expose().into()),
            (
                "GIT_ASKPASS".into(),
                self.config.git_askpass.as_os_str().to_owned(),
            ),
            ("GIT_TERMINAL_PROMPT".into(), "0".into()),
        ];
        spec.timeout = Duration::from_secs(120);
        spec.output_limit = 2 * 1024 * 1024;
        Ok(run_bounded(&spec, cancellation).await?)
    }
}

impl PolicyPublicationService for PolicyPublisher {
    fn has_open_proposer_pr<'a>(
        &'a self,
        cancellation: &'a CancellationToken,
    ) -> PolicyPublisherFuture<'a, bool> {
        Box::pin(async move {
            let token = self
                .github
                .mint_token(
                    &self.config.repository,
                    TokenPurpose::Reconcile,
                    cancellation,
                )
                .await?;
            Ok(self.fresh_open_count(&token, cancellation).await? >= 1)
        })
    }

    fn publish<'a>(
        &'a self,
        run_id: Uuid,
        packet: &'a ProposerPacket,
        intent: &'a ProposalIntent,
        validated: &'a ValidatedPolicyPatch,
        body: &'a str,
        cancellation: &'a CancellationToken,
    ) -> PolicyPublisherFuture<'a, PublishedPullRequest> {
        Box::pin(async move {
            self.publish_inner(run_id, packet, intent, validated, body, cancellation)
                .await
        })
    }
}

fn validate_policy_pull(
    pull: &crate::publisher::PullRequest,
    token: &InstallationToken,
    branch: &str,
    base: &str,
) -> Result<PublishedPullRequest, ProposerError> {
    if pull.state != "open"
        || !pull.draft
        || pull.user.login != token.bot.login
        || pull.head.branch != branch
        || pull.base.branch != base
    {
        return Err(ProposerError::PullRequestContract);
    }
    Ok(PublishedPullRequest {
        number: pull.number,
        url: pull.html_url.clone(),
        branch: pull.head.branch.clone(),
        head_sha: pull.head.sha.clone(),
        author_login: pull.user.login.clone(),
    })
}

fn require_process_success(operation: &'static str, code: i32) -> Result<(), ProposerError> {
    if code == 0 {
        Ok(())
    } else {
        Err(ProposerError::Git { operation, code })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BundleRole {
    Author,
    Reviewer,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RuntimeGraph {
    schema_version: u16,
    author_roots: Vec<String>,
    reviewer_roots: Vec<String>,
    includes: BTreeMap<String, Vec<String>>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PromptBundleFile {
    pub path: String,
    pub git_blob: String,
    pub sha256: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PromptBundleManifest {
    pub schema_version: u16,
    pub role: String,
    pub base_sha: String,
    pub files: Vec<PromptBundleFile>,
    pub bundle_sha256: String,
}

#[derive(Clone, Debug)]
pub struct PromptBundle {
    pub manifest: PromptBundleManifest,
    files: BTreeMap<String, Vec<u8>>,
}

impl PromptBundle {
    pub fn file(&self, path: &str) -> Result<&[u8], ProposerError> {
        self.files
            .get(path)
            .map(Vec::as_slice)
            .ok_or_else(|| ProposerError::MissingBundlePath(path.to_owned()))
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProposerPacket {
    pub schema_version: u16,
    pub base_sha: String,
    pub report_sha256: String,
    pub prompt_bundle: PromptBundleManifest,
    pub report: LessonsReport,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EvidenceCitation {
    pub cohort_key: String,
    pub run_ids: Vec<Uuid>,
    pub terminal_state: String,
    pub numerator: usize,
    pub denominator: usize,
    pub rate_basis_points: u16,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum ProposalIntent {
    IdeaAppend {
        schema_version: u16,
        title: String,
        summary: String,
        markdown: String,
        citations: Vec<EvidenceCitation>,
    },
    PolicyPatch {
        schema_version: u16,
        title: String,
        summary: String,
        patch: String,
        citations: Vec<EvidenceCitation>,
    },
}

impl ProposalIntent {
    #[must_use]
    pub fn title(&self) -> &str {
        match self {
            Self::IdeaAppend { title, .. } | Self::PolicyPatch { title, .. } => title,
        }
    }

    #[must_use]
    pub fn summary(&self) -> &str {
        match self {
            Self::IdeaAppend { summary, .. } | Self::PolicyPatch { summary, .. } => summary,
        }
    }

    #[must_use]
    pub fn citations(&self) -> &[EvidenceCitation] {
        match self {
            Self::IdeaAppend { citations, .. } | Self::PolicyPatch { citations, .. } => citations,
        }
    }
}

#[derive(Clone, Debug)]
pub struct ValidatedPolicyPatch {
    pub patch_path: PathBuf,
    pub inspected: InspectedPatch,
    pub self_referential_paths: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct ProposerExecution {
    pub intent: ProposalIntent,
    pub transcript: Vec<u8>,
}

pub type ProposerAgentFuture<'a> = Pin<
    Box<dyn std::future::Future<Output = Result<ProposerExecution, ProposerError>> + Send + 'a>,
>;

pub trait ProposerAgentService: Send + Sync {
    fn invoke<'a>(
        &'a self,
        packet: &'a ProposerPacket,
        prompt: Vec<u8>,
        seat: &'a Seat,
        cancellation: &'a CancellationToken,
    ) -> ProposerAgentFuture<'a>;
}

pub type PolicyReviewFuture<'a> =
    Pin<Box<dyn std::future::Future<Output = Result<ReviewExecution, ProposerError>> + Send + 'a>>;

pub trait PolicyAdversarialReviewService: Send + Sync {
    fn review<'a>(
        &'a self,
        repository: &'a Path,
        packet: &'a PolicyReviewPacket,
        prompt: Vec<u8>,
        invocation: ResolvedInvocation,
        cancellation: &'a CancellationToken,
    ) -> PolicyReviewFuture<'a>;
}

#[derive(Clone, Debug)]
pub struct IsolatedProposer {
    spawner: IsolatedChildSpawner,
    /// Must remain false until provider egress passes A5 qualification.
    live_network: bool,
}

impl IsolatedProposer {
    #[must_use]
    pub fn new(spawner: IsolatedChildSpawner, live_network: bool) -> Self {
        Self {
            spawner,
            live_network,
        }
    }

    pub async fn invoke(
        &self,
        packet: &ProposerPacket,
        prompt: Vec<u8>,
        seat: &Seat,
        cancellation: &CancellationToken,
    ) -> Result<ProposerExecution, ProposerError> {
        if self.live_network {
            return Err(ProposerError::LiveProviderNotQualified);
        }
        let packet_bytes = serde_json::to_vec(packet)?;
        let child = self
            .spawner
            .spawn(
                ChildContract::Proposer {
                    packet_sha256: hex::encode(Sha256::digest(&packet_bytes)),
                    prompt_sha256: hex::encode(Sha256::digest(&prompt)),
                    model: seat.model.clone(),
                    effort: seat.effort.clone(),
                    harness: seat.harness.clone(),
                    provider: seat.provider.clone(),
                },
                vec![
                    ("packet.json".to_owned(), packet_bytes),
                    ("prompt.md".to_owned(), prompt),
                ],
                None,
                cancellation,
            )
            .await?;
        if child.terminal.state != ChildTerminalState::Completed {
            return Err(ProposerError::ChildState(child.terminal.state));
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
            return Err(ProposerError::IsolationProbe);
        }
        let intent: ProposalIntent = serde_json::from_slice(child.output("proposal.json")?)?;
        validate_intent(&packet.report, &intent)?;
        Ok(ProposerExecution {
            intent,
            transcript: child.output("transcript.log")?.to_vec(),
        })
    }
}

impl ProposerAgentService for IsolatedProposer {
    fn invoke<'a>(
        &'a self,
        packet: &'a ProposerPacket,
        prompt: Vec<u8>,
        seat: &'a Seat,
        cancellation: &'a CancellationToken,
    ) -> ProposerAgentFuture<'a> {
        Box::pin(
            async move { IsolatedProposer::invoke(self, packet, prompt, seat, cancellation).await },
        )
    }
}

impl PolicyAdversarialReviewService for SandboxedReviewer {
    fn review<'a>(
        &'a self,
        repository: &'a Path,
        packet: &'a PolicyReviewPacket,
        prompt: Vec<u8>,
        invocation: ResolvedInvocation,
        cancellation: &'a CancellationToken,
    ) -> PolicyReviewFuture<'a> {
        Box::pin(async move {
            self.review_policy(repository, packet, prompt, invocation, cancellation)
                .await
                .map_err(ProposerError::Review)
        })
    }
}

pub fn load_prompt_bundle(
    repository: &Path,
    base_sha: &str,
    role: BundleRole,
) -> Result<PromptBundle, ProposerError> {
    require_lower_hex(base_sha, 40, "base SHA")?;
    let graph_bytes = git_object(repository, base_sha, "policy/proposer-runtime.json")?;
    let graph: RuntimeGraph = serde_json::from_slice(&graph_bytes)?;
    if graph.schema_version != 1 {
        return Err(ProposerError::RuntimeGraph("schema version"));
    }
    for (node, children) in &graph.includes {
        require_repo_path(node)?;
        for child in children {
            require_repo_path(child)?;
            if !graph.includes.contains_key(child) {
                return Err(ProposerError::RuntimeGraph("unmapped include"));
            }
        }
    }
    let roots = match role {
        BundleRole::Author => &graph.author_roots,
        BundleRole::Reviewer => &graph.reviewer_roots,
    };
    if roots.is_empty() {
        return Err(ProposerError::RuntimeGraph("empty roots"));
    }
    let mut visiting = BTreeSet::new();
    let mut closure = BTreeSet::new();
    for root in roots {
        require_repo_path(root)?;
        visit_graph(root, &graph.includes, &mut visiting, &mut closure)?;
    }
    let mut files = BTreeMap::new();
    let mut manifest_files = Vec::with_capacity(closure.len());
    let mut bundle_hasher = Sha256::new();
    for path in closure {
        let bytes = if path == "policy/proposer-runtime.json" {
            graph_bytes.clone()
        } else {
            git_object(repository, base_sha, &path)?
        };
        let git_blob = git_blob(repository, base_sha, &path)?;
        let sha256 = hex::encode(Sha256::digest(&bytes));
        bundle_hasher.update(path.as_bytes());
        bundle_hasher.update([0]);
        bundle_hasher.update(sha256.as_bytes());
        bundle_hasher.update([0]);
        manifest_files.push(PromptBundleFile {
            path: path.clone(),
            git_blob,
            sha256,
        });
        files.insert(path, bytes);
    }
    Ok(PromptBundle {
        manifest: PromptBundleManifest {
            schema_version: 1,
            role: match role {
                BundleRole::Author => "author",
                BundleRole::Reviewer => "reviewer",
            }
            .to_owned(),
            base_sha: base_sha.to_owned(),
            files: manifest_files,
            bundle_sha256: hex::encode(bundle_hasher.finalize()),
        },
        files,
    })
}

fn visit_graph(
    node: &str,
    includes: &BTreeMap<String, Vec<String>>,
    visiting: &mut BTreeSet<String>,
    closure: &mut BTreeSet<String>,
) -> Result<(), ProposerError> {
    if closure.contains(node) {
        return Ok(());
    }
    if !visiting.insert(node.to_owned()) {
        return Err(ProposerError::RuntimeGraph("include cycle"));
    }
    let children = includes.get(node).ok_or(ProposerError::RuntimeGraph(
        "root absent from include graph",
    ))?;
    for child in children {
        visit_graph(child, includes, visiting, closure)?;
    }
    visiting.remove(node);
    closure.insert(node.to_owned());
    Ok(())
}

pub fn build_packet(
    base_sha: &str,
    report: LessonsReport,
    bundle: &PromptBundle,
) -> Result<ProposerPacket, ProposerError> {
    report.validate()?;
    if bundle.manifest.role != "author" || bundle.manifest.base_sha != base_sha {
        return Err(ProposerError::PromptBundleMismatch);
    }
    let report_json = serde_json::to_vec(&report)?;
    if report_json.len() > MAX_LESSONS_REPORT_BYTES {
        return Err(ProposerError::ReportTooLarge {
            actual: report_json.len(),
            maximum: MAX_LESSONS_REPORT_BYTES,
        });
    }
    let report_sha256 = hex::encode(Sha256::digest(&report_json));
    Ok(ProposerPacket {
        schema_version: PROPOSER_SCHEMA_VERSION,
        base_sha: base_sha.to_owned(),
        report_sha256,
        prompt_bundle: bundle.manifest.clone(),
        report,
    })
}

pub fn render_effective_prompt(
    bundle: &PromptBundle,
    packet: &ProposerPacket,
) -> Result<Vec<u8>, ProposerError> {
    if bundle.manifest != packet.prompt_bundle || packet.schema_version != PROPOSER_SCHEMA_VERSION {
        return Err(ProposerError::PromptBundleMismatch);
    }
    let static_prompt = bundle.file("policy/proposer.md")?;
    let mut prompt = Vec::with_capacity(static_prompt.len() + 4096);
    prompt.extend_from_slice(static_prompt);
    if !prompt.ends_with(b"\n") {
        prompt.push(b'\n');
    }
    prompt.extend_from_slice(b"\n<UNTRUSTED_LESSONS_REPORT>\n");
    prompt.extend_from_slice(packet.report.to_pretty_json()?.as_bytes());
    prompt.extend_from_slice(b"</UNTRUSTED_LESSONS_REPORT>\n");
    Ok(prompt)
}

pub fn validate_intent(
    report: &LessonsReport,
    intent: &ProposalIntent,
) -> Result<(), ProposerError> {
    report.validate()?;
    let (schema_version, is_policy) = match intent {
        ProposalIntent::IdeaAppend { schema_version, .. } => (*schema_version, false),
        ProposalIntent::PolicyPatch { schema_version, .. } => (*schema_version, true),
    };
    if schema_version != PROPOSER_SCHEMA_VERSION
        || !safe_prose(intent.title(), 120)
        || !safe_prose(intent.summary(), 2_000)
        || intent.citations().len() > 4
    {
        return Err(ProposerError::MalformedIntent);
    }
    let threshold_reached = report
        .cohorts
        .iter()
        .any(|cohort| cohort.eligible_for_policy_pr);
    if threshold_reached != is_policy {
        return Err(ProposerError::WrongThresholdAction);
    }
    if is_policy && intent.citations().is_empty() {
        return Err(ProposerError::EvidenceCitation);
    }
    let mut cited = BTreeSet::new();
    for citation in intent.citations() {
        if !cited.insert((&citation.cohort_key, &citation.terminal_state)) {
            return Err(ProposerError::EvidenceCitation);
        }
        validate_citation(report, citation, is_policy)?;
    }
    match intent {
        ProposalIntent::IdeaAppend { markdown, .. } => {
            if !safe_prose(markdown, 8_000) {
                return Err(ProposerError::MalformedIntent);
            }
        }
        ProposalIntent::PolicyPatch { patch, .. } => {
            if patch.is_empty() || patch.len() > 1024 * 1024 || patch.contains('\0') {
                return Err(ProposerError::MalformedIntent);
            }
        }
    }
    Ok(())
}

fn validate_citation(
    report: &LessonsReport,
    citation: &EvidenceCitation,
    require_eligible: bool,
) -> Result<(), ProposerError> {
    let cohort = report
        .cohorts
        .iter()
        .find(|cohort| cohort.cohort_key == citation.cohort_key)
        .ok_or(ProposerError::EvidenceCitation)?;
    let outcome = cohort
        .outcomes
        .iter()
        .find(|outcome| outcome.terminal_state == citation.terminal_state)
        .ok_or(ProposerError::EvidenceCitation)?;
    if (require_eligible && !cohort.eligible_for_policy_pr)
        || citation.run_ids != cohort.run_ids
        || citation.numerator != outcome.count
        || citation.denominator != cohort.production_run_count
        || citation.rate_basis_points != outcome.rate_basis_points
    {
        return Err(ProposerError::EvidenceCitation);
    }
    Ok(())
}

pub async fn inspect_policy_intent(
    repository: &Path,
    base_sha: &str,
    scratch: &Path,
    author_bundle: &PromptBundleManifest,
    reviewer_bundle: &PromptBundleManifest,
    intent: &ProposalIntent,
    cancellation: &CancellationToken,
) -> Result<ValidatedPolicyPatch, ProposerError> {
    let ProposalIntent::PolicyPatch { patch, .. } = intent else {
        return Err(ProposerError::WrongThresholdAction);
    };
    tokio::fs::create_dir_all(scratch).await?;
    let patch_path = scratch.join(format!("proposer-{}.patch", Uuid::new_v4()));
    tokio::fs::write(&patch_path, patch.as_bytes()).await?;
    let result = async {
        let inspected =
            inspect_patch(repository, base_sha, &patch_path, scratch, cancellation).await?;
        caps::verify(
            &inspected.manifest,
            base_sha,
            MAX_POLICY_FILES,
            MAX_POLICY_CHANGED_LINES,
        )?;
        validate_authority_surface(&inspected.manifest)?;
        let protected: BTreeSet<_> = author_bundle
            .files
            .iter()
            .chain(&reviewer_bundle.files)
            .map(|file| file.path.as_str())
            .collect();
        let self_referential_paths = inspected
            .manifest
            .files
            .iter()
            .filter(|file| protected.contains(file.path.as_str()))
            .map(|file| file.path.clone())
            .collect();
        Ok(ValidatedPolicyPatch {
            patch_path: patch_path.clone(),
            inspected,
            self_referential_paths,
        })
    }
    .await;
    if result.is_err() {
        let _ = tokio::fs::remove_file(&patch_path).await;
    }
    result
}

pub fn validate_authority_surface(manifest: &DiffManifest) -> Result<(), ProposerError> {
    let mut policy_change = false;
    for file in &manifest.files {
        if file.path.starts_with("policy/") {
            policy_change = true;
        } else if file.path != "docs/ideas.md" {
            return Err(ProposerError::AuthoritySurface(file.path.clone()));
        }
    }
    if !policy_change {
        return Err(ProposerError::MissingPolicyChange);
    }
    Ok(())
}

pub fn render_idea_append(
    report: &LessonsReport,
    report_sha256: &str,
    intent: &ProposalIntent,
) -> Result<String, ProposerError> {
    validate_intent(report, intent)?;
    let ProposalIntent::IdeaAppend {
        title,
        summary,
        markdown,
        citations,
        ..
    } = intent
    else {
        return Err(ProposerError::WrongThresholdAction);
    };
    require_lower_hex(report_sha256, 64, "report SHA-256")?;
    let mut evidence = String::new();
    for citation in citations {
        use std::fmt::Write as _;
        writeln!(
            evidence,
            "- `{}` `{}`: {}/{} ({} bp), runs: {}",
            citation.cohort_key,
            citation.terminal_state,
            citation.numerator,
            citation.denominator,
            citation.rate_basis_points,
            citation
                .run_ids
                .iter()
                .map(Uuid::to_string)
                .collect::<Vec<_>>()
                .join(", ")
        )
        .expect("write to String");
    }
    Ok(format!(
        "\n## Proposer inbox - {title}\n\n{summary}\n\n{markdown}\n\nDeterministic report SHA-256: `{report_sha256}`. Production runs: {}. This entry carries no authority under rule 1.\n\n{}",
        report.production_run_count, evidence
    ))
}

pub fn append_idea(path: &Path, append: &str) -> Result<(), ProposerError> {
    if append.is_empty() || append.contains('\0') {
        return Err(ProposerError::MalformedIntent);
    }
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err(ProposerError::UnsafeIdeasPath);
    }
    let mut file = OpenOptions::new()
        .append(true)
        .custom_flags(rustix::fs::OFlags::NOFOLLOW.bits() as i32)
        .open(path)?;
    file.write_all(append.as_bytes())?;
    file.sync_all()?;
    Ok(())
}

pub fn build_policy_pr_body(
    packet: &ProposerPacket,
    intent: &ProposalIntent,
    validated: &ValidatedPolicyPatch,
) -> Result<String, ProposerError> {
    validate_intent(&packet.report, intent)?;
    let ProposalIntent::PolicyPatch { citations, .. } = intent else {
        return Err(ProposerError::WrongThresholdAction);
    };
    let mut evidence = String::new();
    for citation in citations {
        use std::fmt::Write as _;
        writeln!(
            evidence,
            "- Cohort `{}` outcome `{}`: {}/{} ({} basis points); run IDs: {}",
            citation.cohort_key,
            citation.terminal_state,
            citation.numerator,
            citation.denominator,
            citation.rate_basis_points,
            citation
                .run_ids
                .iter()
                .map(Uuid::to_string)
                .collect::<Vec<_>>()
                .join(", ")
        )
        .expect("write to String");
    }
    let self_reference = if validated.self_referential_paths.is_empty() {
        "None".to_owned()
    } else {
        validated.self_referential_paths.join(", ")
    };
    Ok(format!(
        "## Improvement proposer evidence\n\nThis draft is bot-authored. It cannot merge itself; human merge is the sole authority gate.\n\n- Base SHA: `{}`\n- Lessons report SHA-256: `{}`\n- Snapshot maximum event ID: `{}`\n- Patch SHA-256: `{}`\n- Current-execution prompt bundle SHA-256: `{}`\n- R19 closure paths touched (candidate diff only; never loaded this execution): `{self_reference}`\n\n### Ledger evidence\n\n{evidence}\n### Independent review\n\nThe exact candidate commit is routed to the configured cross-family, cross-harness proposer reviewer before publication. Raw transcripts and proposer rationale are absent from its packet.\n",
        packet.base_sha,
        packet.report_sha256,
        packet.report.snapshot_max_event_id,
        validated.inspected.patch_sha256,
        packet.prompt_bundle.bundle_sha256,
    ))
}

fn safe_prose(value: &str, maximum: usize) -> bool {
    !value.trim().is_empty()
        && value.len() <= maximum
        && !value.contains('\0')
        && !value.contains("\r")
}

fn require_lower_hex(value: &str, length: usize, field: &'static str) -> Result<(), ProposerError> {
    if value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        Ok(())
    } else {
        Err(ProposerError::InvalidIdentifier(field))
    }
}

fn require_repo_path(path: &str) -> Result<(), ProposerError> {
    if path.is_empty()
        || path.starts_with('/')
        || path.contains('\0')
        || path
            .split('/')
            .any(|part| part.is_empty() || matches!(part, "." | ".."))
    {
        Err(ProposerError::RuntimeGraph("invalid repository path"))
    } else {
        Ok(())
    }
}

fn git_object(repository: &Path, sha: &str, path: &str) -> Result<Vec<u8>, ProposerError> {
    let output = Command::new("/usr/bin/git")
        .args(["-C"])
        .arg(repository)
        .args(["show", &format!("{sha}:{path}")])
        .output()?;
    if !output.status.success() || !output.stderr.is_empty() {
        return Err(ProposerError::GitObject(path.to_owned()));
    }
    Ok(output.stdout)
}

fn git_blob(repository: &Path, sha: &str, path: &str) -> Result<String, ProposerError> {
    let output = Command::new("/usr/bin/git")
        .args(["-C"])
        .arg(repository)
        .args(["rev-parse", &format!("{sha}:{path}")])
        .output()?;
    let value =
        String::from_utf8(output.stdout).map_err(|_| ProposerError::GitObject(path.to_owned()))?;
    let value = value.trim().to_owned();
    if !output.status.success()
        || !output.stderr.is_empty()
        || !matches!(value.len(), 40 | 64)
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(ProposerError::GitObject(path.to_owned()));
    }
    Ok(value)
}

#[derive(Debug, Error)]
pub enum ProposerError {
    #[error("proposer database operation failed: {0}")]
    Database(#[from] sqlx::Error),
    #[error("proposer attempt was cancelled")]
    Cancelled,
    #[error("lessons report is invalid: {0}")]
    Lessons(#[from] LessonsError),
    #[error("proposer artifact persistence failed: {0}")]
    Artifact(#[from] ArtifactError),
    #[error("proposer JSON is invalid: {0}")]
    Json(#[from] serde_json::Error),
    #[error("proposer filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("candidate worktree failed: {0}")]
    Worktree(#[from] WorktreeError),
    #[error("proposer subprocess failed: {0}")]
    Process(#[from] crate::process::ProcessError),
    #[error("proposer GitHub operation failed: {0}")]
    GitHub(#[from] crate::publisher::GitHubError),
    #[error("candidate cap failed: {0}")]
    Caps(#[from] caps::CapsError),
    #[error("invalid proposer runtime graph: {0}")]
    RuntimeGraph(&'static str),
    #[error("prompt bundle is missing {0}")]
    MissingBundlePath(String),
    #[error("prompt bundle is not pinned to the packet base")]
    PromptBundleMismatch,
    #[error("proposer intent is malformed")]
    MalformedIntent,
    #[error("lessons report has {actual} bytes, above {maximum}")]
    ReportTooLarge { actual: usize, maximum: usize },
    #[error("agent transcript length cannot be represented")]
    TranscriptTooLarge,
    #[error("proposer intent does not match the deterministic evidence threshold")]
    WrongThresholdAction,
    #[error("proposer evidence citation does not exactly match the report")]
    EvidenceCitation,
    #[error("proposer patch is outside the authority surface: {0}")]
    AuthoritySurface(String),
    #[error("at-threshold proposer patch must change at least one policy file")]
    MissingPolicyChange,
    #[error("ideas path is not a regular non-symlink file")]
    UnsafeIdeasPath,
    #[error("invalid {0}")]
    InvalidIdentifier(&'static str),
    #[error("Git object is unavailable or malformed: {0}")]
    GitObject(String),
    #[error("live proposer provider isolation is not A5-qualified")]
    LiveProviderNotQualified,
    #[error("proposer isolation probe did not prove the no-authority boundary")]
    IsolationProbe,
    #[error("proposer child returned fail-closed state {0:?}")]
    ChildState(ChildTerminalState),
    #[error("proposer child failed: {0}")]
    Child(#[from] ChildError),
    #[error("proposer blocking task failed: {0}")]
    Join(#[from] tokio::task::JoinError),
    #[error("proposer adversarial review failed: {0}")]
    Review(#[from] crate::review::ReviewError),
    #[error("proposer routing topology is invalid")]
    InvalidRouting,
    #[error("cross-family adversarial review returned findings")]
    AdversarialReviewFindings,
    #[error("invalid proposer state transition")]
    InvalidTransition,
    #[error("proposer run does not exist: {0}")]
    MissingProposerRun(Uuid),
    #[error("proposer state was lost: expected {expected}, found {actual}")]
    LostProposerState {
        expected: &'static str,
        actual: String,
    },
    #[error("proposer publisher configuration is invalid")]
    InvalidPublisherConfig,
    #[error("proposer publisher lease is held by {0}")]
    PublisherLeaseHeld(String),
    #[error("proposer publisher fencing token is exhausted")]
    PublisherFenceExhausted,
    #[error("proposer publisher lease was lost")]
    PublisherLeaseLost,
    #[error("GitHub open-PR snapshot is stale")]
    StaleGitHubSnapshot,
    #[error("one proposer PR is already open")]
    OpenProposerPrCap,
    #[error("more than one pull request exists for the proposer branch")]
    MultiplePullRequests,
    #[error("published proposer PR violates the draft/bot/head/base contract")]
    PullRequestContract,
    #[error("published proposer head differs from the committed head")]
    PublishedHeadMismatch,
    #[error("proposer Git output is malformed")]
    MalformedGitOutput,
    #[error("proposer Git operation {operation} exited {code}")]
    Git { operation: &'static str, code: i32 },
}

#[cfg(test)]
mod tests {
    use std::{fs, os::unix::fs::symlink, path::Path, process::Command};

    use factory_verify::caps::{ChangeKind, DiffFile, DiffManifest};
    use sha2::{Digest as _, Sha256};
    use uuid::Uuid;

    use crate::lessons::{
        LedgerQuote, LessonCohort, LessonsReport, OutcomeFact, OutcomeRate, QuoteSource,
        ReportSelection,
    };

    use super::{
        BundleRole, EvidenceCitation, ProposalIntent, ProposerError, append_idea, build_packet,
        load_prompt_bundle, render_effective_prompt, validate_authority_surface, validate_intent,
    };

    fn report(count: usize) -> LessonsReport {
        let run_ids: Vec<_> = (0..count).map(|_| Uuid::new_v4()).collect();
        let mut sorted_ids = run_ids.clone();
        sorted_ids.sort_unstable();
        let mut cohort_hasher = Sha256::new();
        cohort_hasher.update(b"A\0fixture\0");
        cohort_hasher.update("1".repeat(64).as_bytes());
        cohort_hasher.update(b"\0");
        cohort_hasher.update("2".repeat(64).as_bytes());
        cohort_hasher.update(b"\0fixture-v1");
        let cohort = LessonCohort {
            cohort_key: format!("cohort:{}", hex::encode(cohort_hasher.finalize())),
            lane: "A".to_owned(),
            skill: "fixture".to_owned(),
            rubric_sha256: "1".repeat(64),
            prompt_template_sha256: "2".repeat(64),
            routing_config_version: "fixture-v1".to_owned(),
            production_run_count: count,
            eligible_for_policy_pr: count >= 10,
            run_ids: sorted_ids,
            outcomes: vec![OutcomeRate {
                terminal_state: "dry_run_complete".to_owned(),
                count,
                rate_basis_points: 10_000,
            }],
        };
        let runs = run_ids
            .into_iter()
            .enumerate()
            .map(|(index, run_id)| OutcomeFact {
                run_id,
                request_id: Uuid::new_v4(),
                run_class: "production".to_owned(),
                lane: "A".to_owned(),
                skill: "fixture".to_owned(),
                rubric_sha256: "1".repeat(64),
                prompt_template_sha256: "2".repeat(64),
                routing_config_version: "fixture-v1".to_owned(),
                terminal_state: "dry_run_complete".to_owned(),
                queued_at: format!("2026-01-01T00:00:{index:02}Z"),
                started_at: Some(format!("2026-01-01T00:00:{index:02}Z")),
                finished_at: format!("2026-01-01T00:00:{index:02}Z"),
                duration_ms: Some(0),
                quotes: (index == 0)
                    .then(|| LedgerQuote {
                        event_id: 1,
                        event_type: "run.killed".to_owned(),
                        json_pointer: "/reason".to_owned(),
                        trust: "untrusted_operator_quote".to_owned(),
                        source_sha256: hex::encode(Sha256::digest(b"bounded operator quote")),
                        start_char: 0,
                        end_char: 22,
                        text: "bounded operator quote".to_owned(),
                        truncated: false,
                    })
                    .into_iter()
                    .collect(),
            })
            .collect();
        LessonsReport {
            schema_version: 1,
            snapshot_max_event_id: 1,
            selection: ReportSelection {
                run_class: "production".to_owned(),
                terminal_runs_only: true,
                quote_sources: vec![QuoteSource {
                    event_type: "run.killed".to_owned(),
                    json_pointer: "/reason".to_owned(),
                    trust: "untrusted_operator_quote".to_owned(),
                }],
                max_quotes_per_run: 1,
                max_quotes_per_report: 32,
                max_quote_chars: 240,
            },
            policy_pr_threshold: 10,
            production_run_count: count,
            cohorts: vec![cohort],
            runs,
        }
    }

    fn citation(report: &LessonsReport) -> EvidenceCitation {
        let cohort = &report.cohorts[0];
        EvidenceCitation {
            cohort_key: cohort.cohort_key.clone(),
            run_ids: cohort.run_ids.clone(),
            terminal_state: "dry_run_complete".to_owned(),
            numerator: cohort.production_run_count,
            denominator: cohort.production_run_count,
            rate_basis_points: 10_000,
        }
    }

    #[test]
    fn threshold_and_evidence_are_supervisor_derived() {
        let below = report(9);
        below.validate().expect("below report");
        let idea = ProposalIntent::IdeaAppend {
            schema_version: 1,
            title: "Observe".to_owned(),
            summary: "Collect evidence".to_owned(),
            markdown: "No authority.".to_owned(),
            citations: vec![citation(&below)],
        };
        validate_intent(&below, &idea).expect("below threshold idea");

        let at = report(10);
        at.validate().expect("threshold report");
        assert!(matches!(
            validate_intent(&at, &idea),
            Err(ProposerError::WrongThresholdAction)
        ));
        let mut evidence = citation(&at);
        let policy = ProposalIntent::PolicyPatch {
            schema_version: 1,
            title: "Tighten policy".to_owned(),
            summary: "Evidence backed".to_owned(),
            patch: "fixture patch".to_owned(),
            citations: vec![evidence.clone()],
        };
        validate_intent(&at, &policy).expect("exact evidence");
        evidence.denominator = 11;
        let forged = ProposalIntent::PolicyPatch {
            schema_version: 1,
            title: "Tighten policy".to_owned(),
            summary: "Evidence backed".to_owned(),
            patch: "fixture patch".to_owned(),
            citations: vec![evidence],
        };
        assert!(matches!(
            validate_intent(&at, &forged),
            Err(ProposerError::EvidenceCitation)
        ));
    }

    #[test]
    fn authority_surface_rejects_every_outside_path() {
        let manifest = DiffManifest {
            base_sha: "a".repeat(40),
            files: vec![DiffFile {
                path: "crates/factory-supervisor/src/lib.rs".to_owned(),
                old_path: None,
                change: ChangeKind::Modified,
                additions: 1,
                deletions: 0,
                binary: false,
                generated: false,
                old_mode: Some("100644".to_owned()),
                new_mode: Some("100644".to_owned()),
            }],
        };
        assert!(matches!(
            validate_authority_surface(&manifest),
            Err(ProposerError::AuthoritySurface(_))
        ));
    }

    #[test]
    fn ideas_append_is_literal_eof_only_and_rejects_symlinks() {
        let temporary = tempfile::tempdir().expect("tempdir");
        let ideas = temporary.path().join("ideas.md");
        fs::write(&ideas, b"prefix\n").expect("seed ideas");
        append_idea(&ideas, "append\n").expect("append");
        assert_eq!(fs::read(&ideas).expect("ideas"), b"prefix\nappend\n");
        let link = temporary.path().join("ideas-link.md");
        symlink(&ideas, &link).expect("symlink");
        assert!(matches!(
            append_idea(&link, "hostile"),
            Err(ProposerError::UnsafeIdeasPath)
        ));
    }

    #[test]
    fn r19_bundle_is_base_pinned_when_candidate_changes_own_prompt() {
        let temporary = tempfile::tempdir().expect("tempdir");
        let repository = temporary.path();
        git(repository, &["init", "--quiet"]);
        let source_root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        for path in [
            "AGENTS.md",
            "docs/bench.json",
            "policy/lessons-report.schema.json",
            "policy/proposer-review.md",
            "policy/proposer-runtime.json",
            "policy/proposer.md",
            "policy/provider-egress.json",
            "policy/routing.json",
        ] {
            let destination = repository.join(path);
            fs::create_dir_all(destination.parent().expect("parent")).expect("mkdir");
            fs::copy(source_root.join(path), destination).expect("copy bundle file");
        }
        git(repository, &["add", "."]);
        git(
            repository,
            &[
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "base",
            ],
        );
        let base = git(repository, &["rev-parse", "HEAD"]);
        let bundle =
            load_prompt_bundle(repository, &base, BundleRole::Author).expect("base bundle");
        let reviewer_bundle =
            load_prompt_bundle(repository, &base, BundleRole::Reviewer).expect("reviewer bundle");
        let packet = build_packet(&base, report(9), &bundle).expect("packet");
        let prompt = render_effective_prompt(&bundle, &packet).expect("prompt");
        let prompt_text = String::from_utf8(prompt).expect("UTF-8 prompt");
        assert!(prompt_text.contains("bounded operator quote"));
        assert!(!prompt_text.contains("RAW_TRANSCRIPT_NEVER_ALLOWED"));

        fs::write(
            repository.join("policy/proposer.md"),
            b"candidate tries to replace current instructions\n",
        )
        .expect("candidate prompt");
        fs::write(
            repository.join("policy/proposer-review.md"),
            b"candidate tries to replace current review instructions\n",
        )
        .expect("candidate reviewer prompt");
        git(
            repository,
            &["add", "policy/proposer.md", "policy/proposer-review.md"],
        );
        git(
            repository,
            &[
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "candidate",
            ],
        );
        let candidate = git(repository, &["rev-parse", "HEAD"]);
        let base_again =
            load_prompt_bundle(repository, &base, BundleRole::Author).expect("base again");
        let candidate_bundle = load_prompt_bundle(repository, &candidate, BundleRole::Author)
            .expect("candidate bundle");
        let base_reviewer_again = load_prompt_bundle(repository, &base, BundleRole::Reviewer)
            .expect("base reviewer again");
        let candidate_reviewer = load_prompt_bundle(repository, &candidate, BundleRole::Reviewer)
            .expect("candidate reviewer bundle");
        assert_eq!(bundle.manifest, base_again.manifest);
        assert_eq!(reviewer_bundle.manifest, base_reviewer_again.manifest);
        assert_ne!(
            bundle.manifest.bundle_sha256,
            candidate_bundle.manifest.bundle_sha256
        );
        assert_ne!(
            reviewer_bundle.manifest.bundle_sha256,
            candidate_reviewer.manifest.bundle_sha256
        );
    }

    fn git(repository: &Path, arguments: &[&str]) -> String {
        let output = Command::new("/usr/bin/git")
            .arg("-C")
            .arg(repository)
            .args(arguments)
            .output()
            .expect("git");
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
}
