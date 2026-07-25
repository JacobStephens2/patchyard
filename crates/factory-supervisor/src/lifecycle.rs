//! Draft-PR CI, preview evidence, and ready-for-review lifecycle.

use std::{
    collections::{BTreeMap, BTreeSet},
    future::Future,
    path::Path,
    pin::Pin,
    sync::Arc,
    time::{Duration, Instant},
};

use serde::Serialize;
use sha2::{Digest as _, Sha256};
use thiserror::Error;
use time::OffsetDateTime;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    artifacts::{ArtifactError, ArtifactStore, StoredArtifact},
    child::{ChildError, ChildTerminalState, EvidenceAction, EvidenceContract},
    evidence::{EvidenceCapture, EvidenceError, ValidatedEvidence},
    preview::{
        PreviewApi, PreviewError, PreviewLease, PreviewLogScan, PreviewRelease, PreviewVerification,
    },
    process::ProcessError,
    publisher::{
        CheckRuns, EvidenceLink, GitHubApi, GitHubError, InstallationToken, PublishInput,
        PublishedPullRequest, PullRequest, RepositoryScope, TokenPurpose, build_final_pr_body,
    },
    secret_scan::{SecretScan, SecretScanApi, SecretScanError},
    store::{LifecycleStore, PullRequestRecord, SideEffectDisposition, StoreError},
};

pub const FAIL_CLOSED_STATES: &[&str] = &[
    "ci_failed",
    "ci_cancelled",
    "ci_job_timed_out",
    "ci_action_required",
    "ci_neutral",
    "ci_skipped",
    "ci_stale",
    "ci_startup_failed",
    "ci_wait_timed_out",
    "ci_observation_failed",
    "preview_failed",
    "preview_timed_out",
    "preview_sha_changed",
    "evidence_failed",
    "secret_scan_failed",
    "lease_cleanup_failed",
    "pr_contract_failed",
];

const EVIDENCE_KINDS: &[&str] = &[
    "evidence-dom",
    "evidence-screenshot",
    "evidence-extract",
    "evidence-hashes",
    "evidence-execution",
    "evidence-lifecycle",
];

#[derive(Clone, Debug)]
pub struct LifecycleConfig {
    pub repository: RepositoryScope,
    pub ci_wait_timeout: Duration,
    pub ci_poll_interval: Duration,
    pub preview_path: String,
    pub selectors: Vec<String>,
}

impl LifecycleConfig {
    fn validate(&self) -> Result<(), LifecycleError> {
        if self.ci_wait_timeout.is_zero()
            || self.ci_wait_timeout > Duration::from_secs(3_600)
            || self.ci_poll_interval.is_zero()
            || self.ci_poll_interval > Duration::from_secs(60)
            || self.ci_poll_interval >= self.ci_wait_timeout
            || !self.preview_path.starts_with('/')
            || self.preview_path.starts_with("//")
            || self.preview_path.contains(['#', '\\'])
            || self.selectors.is_empty()
            || self.selectors.len() > 8
        {
            return Err(LifecycleError::InvalidConfig);
        }
        for selector in &self.selectors {
            let bytes = selector.as_bytes();
            if bytes.len() < 2
                || bytes.len() > 65
                || bytes[0] != b'#'
                || !bytes[1].is_ascii_alphabetic()
                || !bytes[2..]
                    .iter()
                    .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-'))
            {
                return Err(LifecycleError::InvalidConfig);
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct LifecycleResult {
    pub pull_request: PublishedPullRequest,
    pub evidence: Vec<StoredArtifact>,
}

pub type LifecycleFuture<'a> =
    Pin<Box<dyn Future<Output = Result<LifecycleResult, LifecycleError>> + Send + 'a>>;

pub trait LifecycleService: Send + Sync {
    fn complete<'a>(
        &'a self,
        input: &'a PublishInput,
        cancellation: &'a CancellationToken,
    ) -> LifecycleFuture<'a>;
}

#[derive(Clone)]
pub struct EvidenceLifecycle<S: LifecycleStore> {
    store: S,
    github: Arc<dyn GitHubApi>,
    preview: Arc<dyn PreviewApi>,
    secret_scan: Arc<dyn SecretScanApi>,
    evidence: EvidenceCapture,
    artifacts: ArtifactStore,
    config: LifecycleConfig,
}

impl<S: LifecycleStore> EvidenceLifecycle<S> {
    pub fn new(
        store: S,
        github: Arc<dyn GitHubApi>,
        preview: Arc<dyn PreviewApi>,
        secret_scan: Arc<dyn SecretScanApi>,
        evidence: EvidenceCapture,
        artifacts: ArtifactStore,
        config: LifecycleConfig,
    ) -> Result<Self, LifecycleError> {
        config.validate()?;
        Ok(Self {
            store,
            github,
            preview,
            secret_scan,
            evidence,
            artifacts,
            config,
        })
    }

    async fn complete_checked(
        &self,
        input: &PublishInput,
        cancellation: &CancellationToken,
    ) -> Result<LifecycleResult, LifecycleError> {
        input
            .validate()
            .map_err(|error| failed("pr_contract_failed", "invalid_publish_input", error))?;
        let durable = self
            .store
            .pull_request_for_run(input.run_id)
            .await?
            .ok_or_else(|| {
                failed_message(
                    "pr_contract_failed",
                    "missing_pull_request",
                    "draft PR row is absent",
                )
            })?;
        validate_durable_pull(input, &durable)?;

        let token = match self
            .github
            .mint_token(
                &self.config.repository,
                TokenPurpose::Lifecycle,
                cancellation,
            )
            .await
        {
            Ok(token) => token,
            Err(error) if github_cancelled(&error) => return Err(LifecycleError::Cancelled),
            Err(error) => {
                return Err(failed(
                    "ci_observation_failed",
                    "lifecycle_token_unavailable",
                    error,
                ));
            }
        };
        let pull = self
            .load_pull(input, &durable, &token, cancellation)
            .await?;
        self.wait_for_ci(input, &durable, &pull, &token, cancellation)
            .await?;

        self.store
            .transition_lifecycle(
                input.request_id,
                input.run_id,
                "evidence.capture_started",
                "capturing_evidence",
                &format!("lifecycle:{}:capture-started", input.run_id),
                serde_json::json!({
                    "baseline_sha": input.base_sha,
                    "candidate_sha": durable.head_sha,
                }),
            )
            .await?;
        let baseline = self
            .capture_pack("baseline", input, &durable, &input.base_sha, cancellation)
            .await?;
        let candidate = self
            .capture_pack(
                "candidate",
                input,
                &durable,
                &durable.head_sha,
                cancellation,
            )
            .await?;

        self.store
            .transition_lifecycle(
                input.request_id,
                input.run_id,
                "pull_request.finalization_started",
                "finalizing_pr",
                &format!("lifecycle:{}:finalization-started", input.run_id),
                serde_json::json!({
                    "pull_request": durable.number,
                    "evidence_artifacts": baseline.len() + candidate.len(),
                }),
            )
            .await?;
        let mut all_artifacts = baseline;
        all_artifacts.extend(candidate);
        let links = evidence_links(input.run_id, &all_artifacts)?;
        let body = build_final_pr_body(
            input.request_id,
            &input.review_contract,
            &input.base_sha,
            &durable.head_sha,
            &input.expected_tree_hash,
            &input.patch_sha256,
            &links,
        )
        .map_err(|error| failed("pr_contract_failed", "final_body_invalid", error))?;
        let final_pull = self
            .finalize_pull(input, &durable, &token, &body, cancellation)
            .await?;
        self.store
            .update_pull_lifecycle(
                input.run_id,
                durable.number,
                &durable.head_sha,
                "success",
                "ready_for_review",
                false,
                final_pull.updated_at().map_err(|error| {
                    failed("pr_contract_failed", "github_timestamp_invalid", error)
                })?,
            )
            .await?;
        self.store
            .finish_lifecycle_run(
                input.request_id,
                input.run_id,
                "ready_for_review",
                "run.ready_for_review",
                serde_json::json!({
                    "dry_run": false,
                    "publish_invoked": true,
                    "pull_request": durable.number,
                    "head_sha": durable.head_sha,
                    "ci_state": "success",
                    "evidence_count": all_artifacts.len(),
                    "draft_reply_sent": false,
                }),
            )
            .await?;
        Ok(LifecycleResult {
            pull_request: PublishedPullRequest {
                number: durable.number,
                url: durable.html_url,
                branch: durable.branch,
                head_sha: durable.head_sha,
                author_login: durable.author_login,
            },
            evidence: all_artifacts,
        })
    }

    async fn load_pull(
        &self,
        input: &PublishInput,
        durable: &PullRequestRecord,
        token: &InstallationToken,
        cancellation: &CancellationToken,
    ) -> Result<PullRequest, LifecycleError> {
        let pulls = match self
            .github
            .pull_requests_for_branch(token, &self.config.repository, &input.branch, cancellation)
            .await
        {
            Ok(pulls) => pulls,
            Err(error) if github_cancelled(&error) => return Err(LifecycleError::Cancelled),
            Err(error) => {
                return Err(failed(
                    "ci_observation_failed",
                    "pull_request_unavailable",
                    error,
                ));
            }
        };
        if pulls.len() != 1 {
            return Err(failed_message(
                "pr_contract_failed",
                "pull_request_cardinality",
                "expected exactly one PR for the durable branch",
            ));
        }
        let pull = pulls.into_iter().next().expect("cardinality checked");
        validate_live_pull(input, durable, token, &pull, None)?;
        Ok(pull)
    }

    async fn wait_for_ci(
        &self,
        input: &PublishInput,
        durable: &PullRequestRecord,
        pull: &PullRequest,
        token: &InstallationToken,
        cancellation: &CancellationToken,
    ) -> Result<(), LifecycleError> {
        let key = format!("lifecycle:{}:ci-wait", input.run_id);
        if self
            .store
            .begin_lifecycle_effect(input.request_id, input.run_id, &key, "github-ci-wait")
            .await?
            == SideEffectDisposition::Completed
        {
            return Ok(());
        }
        self.store
            .update_pull_lifecycle(
                input.run_id,
                durable.number,
                &durable.head_sha,
                "waiting",
                "draft",
                true,
                pull.updated_at().map_err(|error| {
                    failed("ci_observation_failed", "github_timestamp_invalid", error)
                })?,
            )
            .await?;
        let started = Instant::now();
        loop {
            let checks = match self
                .github
                .check_runs(
                    token,
                    &self.config.repository,
                    &durable.head_sha,
                    cancellation,
                )
                .await
            {
                Ok(checks) => checks,
                Err(error) if github_cancelled(&error) => {
                    return Err(LifecycleError::Cancelled);
                }
                Err(error) => {
                    return Err(failed(
                        "ci_observation_failed",
                        "check_runs_unavailable",
                        error,
                    ));
                }
            };
            match evaluate_checks(&checks, &durable.head_sha)? {
                CiEvaluation::Passed => {
                    self.store
                        .finish_lifecycle_effect(
                            &key,
                            "completed",
                            Some(&durable.head_sha),
                            serde_json::json!({
                                "head_sha": durable.head_sha,
                                "checks": checks,
                            }),
                        )
                        .await?;
                    self.store
                        .update_pull_lifecycle(
                            input.run_id,
                            durable.number,
                            &durable.head_sha,
                            "success",
                            "draft",
                            true,
                            OffsetDateTime::now_utc(),
                        )
                        .await?;
                    self.store
                        .transition_lifecycle(
                            input.request_id,
                            input.run_id,
                            "ci.passed",
                            "awaiting_ci",
                            &format!("lifecycle:{}:ci-passed", input.run_id),
                            serde_json::json!({
                                "head_sha": durable.head_sha,
                                "checks": checks.check_runs.len(),
                            }),
                        )
                        .await?;
                    return Ok(());
                }
                CiEvaluation::Failed(state) => {
                    return Err(failed_message(
                        state,
                        "github_ci_terminal",
                        "GitHub CI reached a non-success terminal conclusion",
                    ));
                }
                CiEvaluation::Waiting(wait_state) => {
                    let digest = hex::encode(Sha256::digest(
                        serde_json::to_vec(&checks).map_err(LifecycleError::Json)?,
                    ));
                    self.store
                        .transition_lifecycle(
                            input.request_id,
                            input.run_id,
                            "ci.waiting",
                            "awaiting_ci",
                            &format!("lifecycle:{}:ci-waiting:{digest}", input.run_id),
                            serde_json::json!({
                                "head_sha": durable.head_sha,
                                "wait_state": wait_state,
                                "checks": checks.check_runs.len(),
                            }),
                        )
                        .await?;
                }
            }
            if started.elapsed() >= self.config.ci_wait_timeout {
                return Err(failed_message(
                    "ci_wait_timed_out",
                    "github_ci_deadline",
                    "GitHub CI did not reach success before the lifecycle deadline",
                ));
            }
            tokio::select! {
                () = cancellation.cancelled() => return Err(LifecycleError::Cancelled),
                () = tokio::time::sleep(self.config.ci_poll_interval) => {}
            }
        }
    }

    async fn capture_pack(
        &self,
        label: &'static str,
        input: &PublishInput,
        durable: &PullRequestRecord,
        expected_sha: &str,
        cancellation: &CancellationToken,
    ) -> Result<Vec<StoredArtifact>, LifecycleError> {
        let stage = format!("evidence-{label}");
        let existing = self
            .store
            .lifecycle_artifacts(input.request_id, input.run_id, &stage)
            .await?;
        if !existing.is_empty() {
            validate_recovered_pack(&self.artifacts, &existing).await?;
            return Ok(existing);
        }
        let effect_key = format!("lifecycle:{}:evidence-{label}", input.run_id);
        if self
            .store
            .begin_lifecycle_effect(
                input.request_id,
                input.run_id,
                &effect_key,
                "preview-evidence-capture",
            )
            .await?
            == SideEffectDisposition::Completed
        {
            return Err(failed_message(
                "evidence_failed",
                "completed_evidence_missing",
                "completed evidence side effect has no durable artifact pack",
            ));
        }
        let lease_id = deterministic_id(&format!("preview-lease:{}:{label}", input.run_id));
        let request_label = input.request_id.to_string();
        let lease = match self
            .preview
            .acquire(
                &request_label,
                &durable.branch,
                expected_sha,
                &lease_id,
                cancellation,
            )
            .await
        {
            Ok(lease) => lease,
            Err(error) => return Err(map_preview_error(error, "preview_acquire")),
        };
        let operation = self
            .capture_under_lease(label, input, expected_sha, &lease, cancellation)
            .await;
        let cleanup = self
            .preview
            .release(&lease, &CancellationToken::new())
            .await;
        let release = match cleanup {
            Ok(release) => release,
            Err(error) => {
                return Err(failed("lease_cleanup_failed", "preview_release", error));
            }
        };
        let completed = match operation {
            Ok(completed) => {
                let evidence_outcome = if completed.validated.is_ok() {
                    "validated"
                } else {
                    "failed_closed"
                };
                self.store
                    .transition_lifecycle(
                        input.request_id,
                        input.run_id,
                        "evidence.security_checks_completed",
                        "capturing_evidence",
                        &format!("lifecycle:{}:evidence-{label}-security", input.run_id),
                        serde_json::json!({
                            "label": label,
                            "expected_sha": expected_sha,
                            "before": completed.before,
                            "after": completed.after,
                            "local_log_scan": completed.local_log_scan,
                            "preview_log_scan": completed.preview_log_scan,
                            "evidence_outcome": evidence_outcome,
                            "release": release,
                        }),
                    )
                    .await?;
                completed
            }
            Err(error) => {
                self.store
                    .transition_lifecycle(
                        input.request_id,
                        input.run_id,
                        "evidence.lease_released",
                        "capturing_evidence",
                        &format!("lifecycle:{}:evidence-{label}-release", input.run_id),
                        serde_json::json!({
                            "label": label,
                            "expected_sha": expected_sha,
                            "security_checks_complete": false,
                            "release": release,
                        }),
                    )
                    .await?;
                return Err(error);
            }
        };
        let validated = completed.validated?;
        let imported = self
            .evidence
            .import(
                input.request_id,
                input.run_id,
                &stage,
                Some(label),
                validated,
            )
            .await
            .map_err(|error| failed("evidence_failed", "artifact_import", error))?;
        let mut artifacts = imported.artifacts;
        for artifact in &artifacts {
            self.store
                .register_lifecycle_artifact(input.request_id, input.run_id, &stage, artifact)
                .await?;
        }
        let manifest = CaptureLifecycleManifest {
            schema_version: 1,
            label: label.to_owned(),
            expected_sha: expected_sha.to_owned(),
            lease_slot: lease.slot,
            lease_id: lease.lease_id,
            before: completed.before,
            after: completed.after,
            child_job_id: imported.terminal.job_id,
            child_network_policy_sha256: imported.terminal.network_policy_sha256,
            child_teardown: imported.terminal.teardown,
            local_log_scan: completed.local_log_scan,
            preview_log_scan: completed.preview_log_scan,
            release,
            artifacts: artifacts.clone(),
        };
        let manifest_artifact = self
            .artifacts
            .put(
                input.request_id,
                Some(input.run_id),
                &stage,
                "lifecycle.json",
                "evidence-lifecycle",
                serde_json::to_vec_pretty(&manifest)?,
                256 * 1024,
            )
            .await?;
        self.store
            .register_lifecycle_artifact(input.request_id, input.run_id, &stage, &manifest_artifact)
            .await?;
        artifacts.push(manifest_artifact);
        self.store
            .finish_lifecycle_effect(
                &effect_key,
                "completed",
                Some(&lease_id),
                serde_json::json!({
                    "label": label,
                    "expected_sha": expected_sha,
                    "slot": lease.slot,
                    "lease_cleanup": "complete",
                    "artifact_sha256": artifacts.iter().map(|item| item.sha256.clone()).collect::<Vec<_>>(),
                    "log_secret_matches": 0,
                }),
            )
            .await?;
        self.store
            .transition_lifecycle(
                input.request_id,
                input.run_id,
                "evidence.capture_completed",
                "capturing_evidence",
                &format!("lifecycle:{}:evidence-{label}-completed", input.run_id),
                serde_json::json!({
                    "label": label,
                    "expected_sha": expected_sha,
                    "artifacts": artifacts.len(),
                    "lease_cleanup": "complete",
                    "log_secret_matches": 0,
                }),
            )
            .await?;
        Ok(artifacts)
    }

    async fn capture_under_lease(
        &self,
        _label: &str,
        _input: &PublishInput,
        expected_sha: &str,
        lease: &PreviewLease,
        cancellation: &CancellationToken,
    ) -> Result<CaptureAttempt, LifecycleError> {
        let before = self
            .preview
            .verify(lease, cancellation)
            .await
            .map_err(|error| map_preview_error(error, "preview_before_capture"))?;
        let scan_started = OffsetDateTime::now_utc().unix_timestamp();
        let capability_id = Uuid::new_v4().simple().to_string();
        let authorization = self
            .preview
            .authorize(lease, expected_sha, &capability_id, cancellation)
            .await
            .map_err(|error| map_preview_error(error, "preview_authorize"))?;
        let mut actions = Vec::with_capacity(self.config.selectors.len() * 2 + 1);
        for selector in &self.config.selectors {
            actions.push(EvidenceAction::WaitFor {
                selector: selector.clone(),
            });
            actions.push(EvidenceAction::ExtractSelect {
                selector: selector.clone(),
            });
        }
        actions.push(EvidenceAction::Screenshot);
        let contract = EvidenceContract {
            allowed_url: format!("{}{}", lease.url, self.config.preview_path),
            expected_sha: expected_sha.to_owned(),
            actions,
            navigation_timeout_ms: 30_000,
            action_timeout_ms: 10_000,
            total_timeout_ms: 60_000,
            maximum_dom_bytes: 2_000_000,
            maximum_screenshot_bytes: 5_000_000,
            maximum_extract_bytes: 1024 * 1024,
        };
        let evidence_result = self
            .evidence
            .execute(contract, authorization.bearer.clone(), cancellation)
            .await;
        // Once a capability exists, exact log scans and SHA verification are
        // teardown duties. They use a fresh cancellation token so caller
        // cancellation cannot skip the security proof before lease release.
        let teardown_cancellation = CancellationToken::new();
        let after_result = self.preview.verify(lease, &teardown_cancellation).await;
        let local_log_scan_result = self
            .secret_scan
            .scan(
                &authorization.bearer.secret,
                &authorization.bearer.capability_id,
                scan_started,
                &teardown_cancellation,
            )
            .await;
        let preview_log_scan_result = self.preview.scan_logs(lease, &teardown_cancellation).await;
        let local_log_scan = local_log_scan_result.map_err(map_secret_scan_error)?;
        let preview_log_scan = preview_log_scan_result
            .map_err(|error| map_preview_error(error, "preview_log_scan"))?;
        let after =
            after_result.map_err(|error| map_preview_error(error, "preview_after_capture"))?;
        let validated = evidence_result.map_err(map_evidence_error);
        Ok(CaptureAttempt {
            validated,
            before,
            after,
            local_log_scan,
            preview_log_scan,
        })
    }

    async fn finalize_pull(
        &self,
        input: &PublishInput,
        durable: &PullRequestRecord,
        token: &InstallationToken,
        body: &str,
        cancellation: &CancellationToken,
    ) -> Result<PullRequest, LifecycleError> {
        let body_key = format!("lifecycle:{}:pr-body", input.run_id);
        let body_disposition = self
            .store
            .begin_lifecycle_effect(
                input.request_id,
                input.run_id,
                &body_key,
                "github-pr-body-update",
            )
            .await?;
        if body_disposition != SideEffectDisposition::Completed {
            let updated = match self
                .github
                .update_pull_request_body(
                    token,
                    &self.config.repository,
                    durable.number,
                    body,
                    cancellation,
                )
                .await
            {
                Ok(pull) => pull,
                Err(error) if github_cancelled(&error) => {
                    return Err(LifecycleError::Cancelled);
                }
                Err(error) => {
                    return Err(failed("pr_contract_failed", "pr_body_update", error));
                }
            };
            validate_live_pull(input, durable, token, &updated, Some(body))?;
            self.store
                .finish_lifecycle_effect(
                    &body_key,
                    "completed",
                    Some(&durable.number.to_string()),
                    serde_json::json!({
                        "body_sha256": hex::encode(Sha256::digest(body.as_bytes())),
                        "head_sha": durable.head_sha,
                    }),
                )
                .await?;
        }
        self.store
            .update_pull_lifecycle(
                input.run_id,
                durable.number,
                &durable.head_sha,
                "success",
                "finalizing",
                true,
                OffsetDateTime::now_utc(),
            )
            .await?;

        let ready_key = format!("lifecycle:{}:ready-for-review", input.run_id);
        let ready_disposition = self
            .store
            .begin_lifecycle_effect(
                input.request_id,
                input.run_id,
                &ready_key,
                "github-ready-for-review",
            )
            .await?;
        let current = self.load_pull(input, durable, token, cancellation).await?;
        validate_live_pull(input, durable, token, &current, Some(body))?;
        if current.draft {
            if ready_disposition == SideEffectDisposition::Completed {
                return Err(failed_message(
                    "pr_contract_failed",
                    "ready_effect_regressed",
                    "completed ready effect points to a draft PR",
                ));
            }
            match self
                .github
                .mark_pull_request_ready(token, &current.node_id, cancellation)
                .await
            {
                Ok(()) => {}
                Err(error) if github_cancelled(&error) => {
                    return Err(LifecycleError::Cancelled);
                }
                Err(error) => {
                    return Err(failed(
                        "pr_contract_failed",
                        "ready_for_review_update",
                        error,
                    ));
                }
            }
        } else if ready_disposition == SideEffectDisposition::Start {
            return Err(failed_message(
                "pr_contract_failed",
                "premature_ready_for_review",
                "PR became ready before the lifecycle's durable ready effect",
            ));
        }
        self.store
            .finish_lifecycle_effect(
                &ready_key,
                "completed",
                Some(&durable.number.to_string()),
                serde_json::json!({
                    "head_sha": durable.head_sha,
                    "body_sha256": hex::encode(Sha256::digest(body.as_bytes())),
                }),
            )
            .await?;
        let final_pull = self.load_pull(input, durable, token, cancellation).await?;
        validate_live_pull(input, durable, token, &final_pull, Some(body))?;
        if final_pull.draft {
            return Err(failed_message(
                "pr_contract_failed",
                "ready_for_review_not_observed",
                "GitHub still reports the finalized PR as draft",
            ));
        }
        Ok(final_pull)
    }
}

impl<S: LifecycleStore> LifecycleService for EvidenceLifecycle<S> {
    fn complete<'a>(
        &'a self,
        input: &'a PublishInput,
        cancellation: &'a CancellationToken,
    ) -> LifecycleFuture<'a> {
        Box::pin(async move {
            let result = self.complete_checked(input, cancellation).await;
            if let Err(LifecycleError::Failed(failure)) = &result {
                self.store
                    .finish_lifecycle_run(
                        input.request_id,
                        input.run_id,
                        failure.state,
                        &format!("run.{}", failure.state),
                        serde_json::json!({
                            "reason_code": failure.reason_code,
                            "detail": failure.detail,
                            "fail_closed": true,
                            "draft_reply_sent": false,
                        }),
                    )
                    .await?;
            }
            result
        })
    }
}

struct CaptureAttempt {
    validated: Result<ValidatedEvidence, LifecycleError>,
    before: PreviewVerification,
    after: PreviewVerification,
    local_log_scan: SecretScan,
    preview_log_scan: PreviewLogScan,
}

#[derive(Serialize)]
struct CaptureLifecycleManifest {
    schema_version: u16,
    label: String,
    expected_sha: String,
    lease_slot: u8,
    lease_id: String,
    before: PreviewVerification,
    after: PreviewVerification,
    child_job_id: Uuid,
    child_network_policy_sha256: String,
    child_teardown: crate::child::TeardownFacts,
    local_log_scan: SecretScan,
    preview_log_scan: PreviewLogScan,
    release: PreviewRelease,
    artifacts: Vec<StoredArtifact>,
}

enum CiEvaluation {
    Waiting(&'static str),
    Passed,
    Failed(&'static str),
}

fn evaluate_checks(checks: &CheckRuns, expected_sha: &str) -> Result<CiEvaluation, LifecycleError> {
    if checks.total_count != checks.check_runs.len()
        || checks.total_count >= 100
        || checks.check_runs.iter().any(|check| {
            check.id == 0
                || check.name.trim().is_empty()
                || check.head_sha != expected_sha
                || check.details_url.trim().is_empty()
        })
    {
        return Err(failed_message(
            "ci_observation_failed",
            "check_runs_malformed",
            "GitHub check-run snapshot is incomplete or inconsistent",
        ));
    }
    if checks.check_runs.is_empty() {
        return Ok(CiEvaluation::Waiting("checks_not_started"));
    }
    let mut waiting = false;
    let mut failures = BTreeSet::new();
    for check in &checks.check_runs {
        match check.status.as_str() {
            "queued" | "in_progress" | "requested" | "waiting" | "pending" => {
                if check.conclusion.is_some() {
                    return Err(failed_message(
                        "ci_observation_failed",
                        "pending_check_has_conclusion",
                        "non-terminal check unexpectedly has a conclusion",
                    ));
                }
                waiting = true;
            }
            "completed" => match check.conclusion.as_deref() {
                Some("success") => {}
                Some("failure") => {
                    failures.insert("ci_failed");
                }
                Some("cancelled") => {
                    failures.insert("ci_cancelled");
                }
                Some("timed_out") => {
                    failures.insert("ci_job_timed_out");
                }
                Some("action_required") => {
                    failures.insert("ci_action_required");
                }
                Some("neutral") => {
                    failures.insert("ci_neutral");
                }
                Some("skipped") => {
                    failures.insert("ci_skipped");
                }
                Some("stale") => {
                    failures.insert("ci_stale");
                }
                Some("startup_failure") => {
                    failures.insert("ci_startup_failed");
                }
                _ => {
                    return Err(failed_message(
                        "ci_observation_failed",
                        "unknown_ci_conclusion",
                        "completed check has an unknown or absent conclusion",
                    ));
                }
            },
            _ => {
                return Err(failed_message(
                    "ci_observation_failed",
                    "unknown_ci_status",
                    "check has an unknown status",
                ));
            }
        }
    }
    for state in [
        "ci_startup_failed",
        "ci_job_timed_out",
        "ci_action_required",
        "ci_failed",
        "ci_cancelled",
        "ci_stale",
        "ci_neutral",
        "ci_skipped",
    ] {
        if failures.contains(state) {
            return Ok(CiEvaluation::Failed(state));
        }
    }
    if waiting {
        Ok(CiEvaluation::Waiting("checks_running"))
    } else {
        Ok(CiEvaluation::Passed)
    }
}

fn validate_durable_pull(
    input: &PublishInput,
    pull: &PullRequestRecord,
) -> Result<(), LifecycleError> {
    if pull.request_id != input.request_id
        || pull.run_id != input.run_id
        || pull.branch != input.branch
        || pull.state != "open"
        || pull.head_sha.len() != 40
        || !lower_hex(&pull.head_sha)
        || !pull
            .html_url
            .starts_with("https://github.com/example-org/fieldbook/pull/")
    {
        return Err(failed_message(
            "pr_contract_failed",
            "durable_pull_mismatch",
            "durable PR row differs from the verified publish input",
        ));
    }
    Ok(())
}

fn validate_live_pull(
    input: &PublishInput,
    durable: &PullRequestRecord,
    token: &InstallationToken,
    pull: &PullRequest,
    expected_body: Option<&str>,
) -> Result<(), LifecycleError> {
    if pull.number != durable.number
        || pull.state != "open"
        || pull.head.branch != input.branch
        || pull.head.sha != durable.head_sha
        || pull.base.branch != "master"
        || pull.user.login != token.bot.login
        || pull.user.login != durable.author_login
        || pull.node_id.trim().is_empty()
        || expected_body.is_some_and(|body| pull.body.as_deref() != Some(body))
    {
        return Err(failed_message(
            "pr_contract_failed",
            "live_pull_mismatch",
            "live PR differs from its durable exact-head contract",
        ));
    }
    Ok(())
}

async fn validate_recovered_pack(
    artifacts: &ArtifactStore,
    pack: &[StoredArtifact],
) -> Result<(), LifecycleError> {
    if pack.len() != EVIDENCE_KINDS.len() {
        return Err(failed_message(
            "evidence_failed",
            "partial_evidence_pack",
            "recovered evidence pack has the wrong artifact count",
        ));
    }
    let kinds: BTreeSet<&str> = pack.iter().map(|item| item.kind.as_str()).collect();
    if kinds != EVIDENCE_KINDS.iter().copied().collect() {
        return Err(failed_message(
            "evidence_failed",
            "partial_evidence_pack",
            "recovered evidence pack has missing or duplicate kinds",
        ));
    }
    for item in pack {
        let path = artifacts.root().join(&item.relative_path);
        let bytes = read_artifact(&path, 5 * 1024 * 1024).await?;
        if hex::encode(Sha256::digest(&bytes)) != item.sha256 {
            return Err(failed_message(
                "evidence_failed",
                "recovered_evidence_digest",
                "recovered evidence bytes differ from the artifact ledger",
            ));
        }
    }
    Ok(())
}

async fn read_artifact(path: &Path, maximum: usize) -> Result<Vec<u8>, LifecycleError> {
    let metadata = tokio::fs::symlink_metadata(path).await?;
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > maximum as u64 {
        return Err(failed_message(
            "evidence_failed",
            "unsafe_recovered_evidence",
            "recovered evidence path is not a bounded regular file",
        ));
    }
    Ok(tokio::fs::read(path).await?)
}

fn evidence_links(
    run_id: Uuid,
    artifacts: &[StoredArtifact],
) -> Result<Vec<EvidenceLink>, LifecycleError> {
    let mut labels_by_path = BTreeMap::new();
    for artifact in artifacts {
        if !matches!(
            artifact.kind.as_str(),
            "evidence-dom"
                | "evidence-screenshot"
                | "evidence-extract"
                | "evidence-hashes"
                | "evidence-execution"
        ) {
            continue;
        }
        let stage = if artifact.relative_path.contains("/evidence-baseline/") {
            "Baseline"
        } else if artifact.relative_path.contains("/evidence-candidate/") {
            "Candidate"
        } else {
            return Err(failed_message(
                "pr_contract_failed",
                "evidence_stage_unknown",
                "evidence artifact is outside the baseline and candidate stages",
            ));
        };
        let kind = match artifact.kind.as_str() {
            "evidence-dom" => "DOM",
            "evidence-screenshot" => "screenshot",
            "evidence-extract" => "extracted DOM order",
            "evidence-hashes" => "child hash manifest",
            "evidence-execution" => "execution manifest",
            _ => unreachable!(),
        };
        let name = Path::new(&artifact.relative_path)
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or_else(|| {
                failed_message(
                    "pr_contract_failed",
                    "evidence_name_invalid",
                    "evidence artifact name is not UTF-8",
                )
            })?
            .to_owned();
        if labels_by_path
            .insert(
                artifact.relative_path.clone(),
                EvidenceLink {
                    label: format!("{stage} {kind}"),
                    run_id,
                    name,
                    sha256: artifact.sha256.clone(),
                },
            )
            .is_some()
        {
            return Err(failed_message(
                "pr_contract_failed",
                "evidence_path_duplicate",
                "evidence artifact path is duplicated",
            ));
        }
    }
    Ok(labels_by_path.into_values().collect())
}

fn deterministic_id(value: &str) -> String {
    hex::encode(Sha256::digest(value.as_bytes()))[..32].to_owned()
}

fn map_preview_error(error: PreviewError, reason_code: &'static str) -> LifecycleError {
    match error {
        PreviewError::Process(ProcessError::Cancelled) => LifecycleError::Cancelled,
        PreviewError::Process(ProcessError::TimedOut(_)) => {
            failed("preview_timed_out", reason_code, error)
        }
        PreviewError::ShaChanged => failed("preview_sha_changed", reason_code, error),
        PreviewError::SecretInLogs(_) => failed("secret_scan_failed", reason_code, error),
        PreviewError::CleanupFailed => failed("lease_cleanup_failed", reason_code, error),
        _ => failed("preview_failed", reason_code, error),
    }
}

fn map_evidence_error(error: EvidenceError) -> LifecycleError {
    match &error {
        EvidenceError::Child(ChildError::Process(ProcessError::Cancelled)) => {
            LifecycleError::Cancelled
        }
        EvidenceError::FailClosed(ChildTerminalState::ChildTimedOut)
        | EvidenceError::Child(ChildError::Process(ProcessError::TimedOut(_))) => {
            failed("preview_timed_out", "isolated_browser_timeout", error)
        }
        EvidenceError::FailClosed(ChildTerminalState::TeardownFailed)
        | EvidenceError::Child(ChildError::TeardownIncomplete)
        | EvidenceError::Child(ChildError::SecretResidue)
        | EvidenceError::Child(ChildError::Cleanup { .. }) => {
            failed("lease_cleanup_failed", "isolated_child_teardown", error)
        }
        EvidenceError::BearerDisclosure(_) => {
            failed("secret_scan_failed", "child_output_secret_scan", error)
        }
        _ => failed("evidence_failed", "isolated_evidence_capture", error),
    }
}

fn map_secret_scan_error(error: SecretScanError) -> LifecycleError {
    match error {
        SecretScanError::Process(ProcessError::Cancelled) => LifecycleError::Cancelled,
        _ => failed("secret_scan_failed", "control_plane_log_scan", error),
    }
}

fn github_cancelled(error: &GitHubError) -> bool {
    matches!(error, GitHubError::Process(ProcessError::Cancelled))
}

fn lower_hex(value: &str) -> bool {
    value
        .bytes()
        .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn failed(
    state: &'static str,
    reason_code: &'static str,
    error: impl std::fmt::Display,
) -> LifecycleError {
    failed_message(state, reason_code, error.to_string())
}

fn failed_message(
    state: &'static str,
    reason_code: &'static str,
    detail: impl Into<String>,
) -> LifecycleError {
    debug_assert!(FAIL_CLOSED_STATES.contains(&state));
    LifecycleError::Failed(LifecycleFailure {
        state,
        reason_code,
        detail: detail.into(),
    })
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LifecycleFailure {
    pub state: &'static str,
    pub reason_code: &'static str,
    pub detail: String,
}

#[derive(Debug, Error)]
pub enum LifecycleError {
    #[error("evidence lifecycle configuration is invalid")]
    InvalidConfig,
    #[error("evidence lifecycle was cancelled and remains resumable")]
    Cancelled,
    #[error("evidence lifecycle failed closed as {0:?}")]
    Failed(LifecycleFailure),
    #[error("evidence lifecycle store failed: {0}")]
    Store(#[from] StoreError),
    #[error("evidence lifecycle artifact store failed: {0}")]
    Artifact(#[from] ArtifactError),
    #[error("evidence lifecycle JSON failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("evidence lifecycle filesystem failed: {0}")]
    Io(#[from] std::io::Error),
}

#[cfg(test)]
mod tests {
    use std::{
        collections::{BTreeSet, HashSet},
        fs,
        os::unix::fs::PermissionsExt as _,
        path::{Path, PathBuf},
        sync::{Arc, Mutex},
        time::{Duration, SystemTime, UNIX_EPOCH},
    };

    use tempfile::TempDir;
    use time::OffsetDateTime;
    use tokio_util::sync::CancellationToken;
    use uuid::Uuid;

    use super::{
        CiEvaluation, EvidenceLifecycle, LifecycleConfig, LifecycleError, LifecycleService,
        evaluate_checks,
    };
    use crate::{
        artifacts::{ArtifactStore, StoredArtifact},
        child::{ChildSpawnConfig, IsolatedChildSpawner, PreviewBearer},
        evidence::EvidenceCapture,
        preview::{
            PreviewApi, PreviewAuthorization, PreviewError, PreviewFuture, PreviewLease,
            PreviewLogScan, PreviewRelease, PreviewVerification,
        },
        publisher::{
            BotIdentity, CheckRun, CheckRuns, CreatePullRequest, GitHubApi, GitHubFuture,
            GitHubUser, InstallationToken, OpenPullRequestSnapshot, PublishInput, PullRequest,
            PullRequestRef, RepositoryScope, Review, ReviewContract, RootCause, TokenPurpose,
            build_initial_pr_body,
        },
        secret_scan::{SecretScan, SecretScanApi, SecretScanError, SecretScanFuture},
        store::{LifecycleStore, PullRequestRecord, SideEffectDisposition, StoreError},
    };

    fn checks(status: &str, conclusion: Option<&str>) -> CheckRuns {
        let head = "a".repeat(40);
        CheckRuns {
            total_count: 1,
            check_runs: vec![CheckRun {
                id: 1,
                name: "PHPUnit Tests".to_owned(),
                head_sha: head,
                status: status.to_owned(),
                conclusion: conclusion.map(str::to_owned),
                details_url: "https://github.com/check".to_owned(),
            }],
        }
    }

    #[test]
    fn every_github_terminal_conclusion_has_an_explicit_state() {
        for (conclusion, expected) in [
            ("failure", "ci_failed"),
            ("cancelled", "ci_cancelled"),
            ("timed_out", "ci_job_timed_out"),
            ("action_required", "ci_action_required"),
            ("neutral", "ci_neutral"),
            ("skipped", "ci_skipped"),
            ("stale", "ci_stale"),
            ("startup_failure", "ci_startup_failed"),
        ] {
            assert!(matches!(
                evaluate_checks(
                    &checks("completed", Some(conclusion)),
                    &"a".repeat(40)
                )
                .expect("known conclusion"),
                CiEvaluation::Failed(actual) if actual == expected
            ));
        }
        assert!(matches!(
            evaluate_checks(&checks("completed", Some("success")), &"a".repeat(40))
                .expect("success"),
            CiEvaluation::Passed
        ));
        assert!(matches!(
            evaluate_checks(&checks("in_progress", None), &"a".repeat(40)).expect("pending"),
            CiEvaluation::Waiting("checks_running")
        ));
    }

    #[tokio::test]
    async fn complete_lifecycle_releases_before_import_and_finalizes_full_contract() {
        let fixture = LifecycleFixture::new(
            "/completed",
            false,
            false,
            checks("completed", Some("success")),
        );

        let result = fixture
            .lifecycle
            .complete(&fixture.input, &CancellationToken::new())
            .await
            .expect("complete lifecycle");

        assert_eq!(result.evidence.len(), 12);
        assert_eq!(
            result
                .evidence
                .iter()
                .map(|item| item.relative_path.as_str())
                .filter(|path| path.ends_with(".png"))
                .count(),
            2
        );
        let names: BTreeSet<_> = result
            .evidence
            .iter()
            .filter_map(|item| Path::new(&item.relative_path).file_name())
            .collect();
        assert_eq!(names.len(), 12, "baseline and candidate names must differ");
        assert_eq!(
            fixture.store.terminal_state(),
            Some("ready_for_review".to_owned())
        );
        assert_eq!(fixture.preview.release_count(), 2);
        assert_eq!(fixture.secret_scan.scan_count(), 2);

        let calls = fixture.calls.lock().expect("call log");
        for label in ["baseline", "candidate"] {
            let release = calls
                .iter()
                .position(|item| item == &format!("release:{label}"))
                .expect("release call");
            let register = calls
                .iter()
                .position(|item| item == &format!("register:{label}"))
                .expect("artifact registration");
            assert!(release < register, "{label} imported before lease release");
        }
        let github = fixture.github.state.lock().expect("GitHub state");
        assert!(!github.pull.draft);
        let body = github.pull.body.as_deref().expect("final body");
        assert!(body.contains("### Reviewer quiz"));
        assert!(body.contains("### Explain diff for shared function"));
        assert!(body.contains("### Draft requester reply - written, never sent"));
        assert!(body.contains("https://factory.example.com/evidence/"));
        assert!(body.contains("Baseline screenshot"));
        assert!(body.contains("Candidate extracted DOM order"));
        for artifact in &result.evidence {
            if artifact.kind != "evidence-lifecycle" {
                assert!(body.contains(&artifact.sha256));
            }
        }
        assert!(github.ready_called);
    }

    #[tokio::test]
    async fn failed_browser_still_scans_and_releases_without_import() {
        let fixture = LifecycleFixture::new(
            "/browser_crashed",
            false,
            false,
            checks("completed", Some("success")),
        );

        let error = fixture
            .lifecycle
            .complete(&fixture.input, &CancellationToken::new())
            .await
            .expect_err("browser failure");

        assert!(matches!(
            error,
            LifecycleError::Failed(ref failure) if failure.state == "evidence_failed"
        ));
        assert_eq!(
            fixture.store.terminal_state(),
            Some("evidence_failed".to_owned())
        );
        assert_eq!(fixture.store.artifact_count(), 0);
        assert_eq!(fixture.secret_scan.scan_count(), 1);
        assert_eq!(fixture.preview.log_scan_count(), 1);
        assert_eq!(fixture.preview.release_count(), 1);
        let proof = fixture
            .store
            .event_payload("evidence.security_checks_completed")
            .expect("durable failure cleanup proof");
        assert_eq!(proof["evidence_outcome"], "failed_closed");
        assert_eq!(proof["local_log_scan"]["matches"], 0);
        assert_eq!(proof["preview_log_scan"]["matches"], 0);
        assert_eq!(proof["release"]["cleanup_complete"], true);
    }

    #[tokio::test]
    async fn cleanup_failure_overrides_success_and_imports_nothing() {
        let fixture = LifecycleFixture::new(
            "/completed",
            true,
            false,
            checks("completed", Some("success")),
        );

        let error = fixture
            .lifecycle
            .complete(&fixture.input, &CancellationToken::new())
            .await
            .expect_err("cleanup failure");

        assert!(matches!(
            error,
            LifecycleError::Failed(ref failure) if failure.state == "lease_cleanup_failed"
        ));
        assert_eq!(
            fixture.store.terminal_state(),
            Some("lease_cleanup_failed".to_owned())
        );
        assert_eq!(fixture.store.artifact_count(), 0);
        assert_eq!(fixture.preview.release_count(), 1);
    }

    #[tokio::test]
    async fn secret_scan_failure_releases_and_lands_in_named_state() {
        let fixture = LifecycleFixture::new(
            "/completed",
            false,
            true,
            checks("completed", Some("success")),
        );

        let error = fixture
            .lifecycle
            .complete(&fixture.input, &CancellationToken::new())
            .await
            .expect_err("secret scan failure");

        assert!(matches!(
            error,
            LifecycleError::Failed(ref failure) if failure.state == "secret_scan_failed"
        ));
        assert_eq!(
            fixture.store.terminal_state(),
            Some("secret_scan_failed".to_owned())
        );
        assert_eq!(fixture.store.artifact_count(), 0);
        assert_eq!(fixture.preview.release_count(), 1);
    }

    #[tokio::test]
    async fn empty_ci_snapshot_times_out_fail_closed_before_preview() {
        let mut empty = checks("completed", Some("success"));
        empty.total_count = 0;
        empty.check_runs.clear();
        let mut fixture = LifecycleFixture::new("/completed", false, false, empty);
        fixture.lifecycle.config.ci_wait_timeout = Duration::from_millis(3);
        fixture.lifecycle.config.ci_poll_interval = Duration::from_millis(1);

        let error = fixture
            .lifecycle
            .complete(&fixture.input, &CancellationToken::new())
            .await
            .expect_err("CI timeout");

        assert!(matches!(
            error,
            LifecycleError::Failed(ref failure) if failure.state == "ci_wait_timed_out"
        ));
        assert_eq!(
            fixture.store.terminal_state(),
            Some("ci_wait_timed_out".to_owned())
        );
        assert_eq!(fixture.preview.release_count(), 0);
    }

    struct LifecycleFixture {
        _temp: TempDir,
        lifecycle: EvidenceLifecycle<MemoryLifecycleStore>,
        input: PublishInput,
        store: MemoryLifecycleStore,
        github: FakeGitHub,
        preview: FakePreview,
        secret_scan: FakeSecretScan,
        calls: Arc<Mutex<Vec<String>>>,
    }

    impl LifecycleFixture {
        fn new(
            preview_path: &str,
            release_failure: bool,
            secret_failure: bool,
            checks: CheckRuns,
        ) -> Self {
            let temp = tempfile::tempdir().expect("temp");
            let artifact_root = temp.path().join("artifacts");
            let staging_root = temp.path().join("children");
            fs::create_dir(&artifact_root).expect("artifact root");
            fs::set_permissions(&artifact_root, fs::Permissions::from_mode(0o2750))
                .expect("artifact permissions");
            fs::create_dir(&staging_root).expect("staging root");
            fs::set_permissions(&staging_root, fs::Permissions::from_mode(0o700))
                .expect("staging permissions");
            let artifacts = ArtifactStore::open(&artifact_root).expect("artifact store");
            let spawner = IsolatedChildSpawner::new(ChildSpawnConfig {
                spawn_program: project_root().join("fixtures/pipeline/bin/child-evidence-fixture"),
                cancel_program: project_root().join("fixtures/pipeline/bin/child-cancel-stub"),
                staging_root,
                timeout: Duration::from_secs(10),
            });
            let evidence = EvidenceCapture::new(spawner, artifacts.clone());
            let request_id = Uuid::new_v4();
            let run_id = Uuid::new_v4();
            let base_sha = "b".repeat(40);
            let head_sha = "a".repeat(40);
            let branch = format!("factory/{request_id}-session-14-fixture");
            let contract = review_contract();
            let body = build_initial_pr_body(
                request_id,
                &contract,
                &base_sha,
                &"c".repeat(64),
                &"d".repeat(64),
            )
            .expect("initial body");
            let input = PublishInput {
                schema_version: 2,
                request_id,
                run_id,
                attempts: 1,
                branch: branch.clone(),
                base_sha: base_sha.clone(),
                patch_relative_path: "attempt-0/patch.diff".to_owned(),
                patch_sha256: "d".repeat(64),
                expected_tree_hash: "c".repeat(64),
                title: format!("Factory request {request_id}"),
                body: body.clone(),
                review_contract: contract,
            };
            let calls = Arc::new(Mutex::new(Vec::new()));
            let pull_record = pull_record(request_id, run_id, &branch, &head_sha);
            let store = MemoryLifecycleStore::new(pull_record);
            let github = FakeGitHub::new(live_pull(&branch, &head_sha, &body), checks);
            let preview = FakePreview::new(release_failure, calls.clone());
            let secret_scan = FakeSecretScan::new(secret_failure, calls.clone());
            let lifecycle = EvidenceLifecycle::new(
                store.clone(),
                Arc::new(github.clone()),
                Arc::new(preview.clone()),
                Arc::new(secret_scan.clone()),
                evidence,
                artifacts,
                LifecycleConfig {
                    repository: repository(),
                    ci_wait_timeout: Duration::from_secs(2),
                    ci_poll_interval: Duration::from_millis(10),
                    preview_path: preview_path.to_owned(),
                    selectors: vec!["#sales_person_id".to_owned()],
                },
            )
            .expect("lifecycle");
            store.set_calls(calls.clone());
            Self {
                _temp: temp,
                lifecycle,
                input,
                store,
                github,
                preview,
                secret_scan,
                calls,
            }
        }
    }

    #[derive(Clone)]
    struct MemoryLifecycleStore {
        state: Arc<Mutex<MemoryLifecycleState>>,
    }

    struct MemoryLifecycleState {
        pull: PullRequestRecord,
        terminal: Option<String>,
        artifacts: Vec<StoredArtifact>,
        completed_effects: HashSet<String>,
        calls: Option<Arc<Mutex<Vec<String>>>>,
        lifecycle_events: Vec<(String, serde_json::Value)>,
    }

    impl MemoryLifecycleStore {
        fn new(pull: PullRequestRecord) -> Self {
            Self {
                state: Arc::new(Mutex::new(MemoryLifecycleState {
                    pull,
                    terminal: None,
                    artifacts: Vec::new(),
                    completed_effects: HashSet::new(),
                    calls: None,
                    lifecycle_events: Vec::new(),
                })),
            }
        }

        fn set_calls(&self, calls: Arc<Mutex<Vec<String>>>) {
            self.state.lock().expect("store").calls = Some(calls);
        }

        fn terminal_state(&self) -> Option<String> {
            self.state.lock().expect("store").terminal.clone()
        }

        fn artifact_count(&self) -> usize {
            self.state.lock().expect("store").artifacts.len()
        }

        fn event_payload(&self, event_type: &str) -> Option<serde_json::Value> {
            self.state
                .lock()
                .expect("store")
                .lifecycle_events
                .iter()
                .find(|(kind, _)| kind == event_type)
                .map(|(_, payload)| payload.clone())
        }
    }

    impl LifecycleStore for MemoryLifecycleStore {
        async fn pull_request_for_run(
            &self,
            run_id: Uuid,
        ) -> Result<Option<PullRequestRecord>, StoreError> {
            let state = self.state.lock().expect("store");
            Ok((state.pull.run_id == run_id).then(|| state.pull.clone()))
        }

        async fn update_pull_lifecycle(
            &self,
            run_id: Uuid,
            number: i32,
            head_sha: &str,
            ci_state: &str,
            review_state: &str,
            is_draft: bool,
            github_updated_at: OffsetDateTime,
        ) -> Result<(), StoreError> {
            let mut state = self.state.lock().expect("store");
            assert_eq!(state.pull.run_id, run_id);
            assert_eq!(state.pull.number, number);
            assert_eq!(state.pull.head_sha, head_sha);
            state.pull.ci_state = ci_state.to_owned();
            state.pull.review_state = review_state.to_owned();
            state.pull.is_draft = is_draft;
            state.pull.github_updated_at = github_updated_at;
            Ok(())
        }

        async fn transition_lifecycle(
            &self,
            _request_id: Uuid,
            _run_id: Uuid,
            event_type: &str,
            to_state: &str,
            _idempotency_key: &str,
            payload: serde_json::Value,
        ) -> Result<bool, StoreError> {
            let mut state = self.state.lock().expect("store");
            state.terminal = Some(to_state.to_owned());
            state
                .lifecycle_events
                .push((event_type.to_owned(), payload));
            Ok(true)
        }

        async fn register_lifecycle_artifact(
            &self,
            _request_id: Uuid,
            _run_id: Uuid,
            stage: &str,
            artifact: &StoredArtifact,
        ) -> Result<(), StoreError> {
            let label = stage.strip_prefix("evidence-").unwrap_or(stage);
            let mut state = self.state.lock().expect("store");
            if state
                .artifacts
                .iter()
                .all(|item| item.relative_path != artifact.relative_path)
            {
                state.artifacts.push(artifact.clone());
                if let Some(calls) = &state.calls {
                    calls
                        .lock()
                        .expect("call log")
                        .push(format!("register:{label}"));
                }
            }
            Ok(())
        }

        async fn lifecycle_artifacts(
            &self,
            _request_id: Uuid,
            _run_id: Uuid,
            stage: &str,
        ) -> Result<Vec<StoredArtifact>, StoreError> {
            let marker = format!("/{stage}/");
            Ok(self
                .state
                .lock()
                .expect("store")
                .artifacts
                .iter()
                .filter(|artifact| artifact.relative_path.contains(&marker))
                .cloned()
                .collect())
        }

        async fn begin_lifecycle_effect(
            &self,
            _request_id: Uuid,
            _run_id: Uuid,
            key: &str,
            _effect_type: &str,
        ) -> Result<SideEffectDisposition, StoreError> {
            Ok(
                if self
                    .state
                    .lock()
                    .expect("store")
                    .completed_effects
                    .contains(key)
                {
                    SideEffectDisposition::Completed
                } else {
                    SideEffectDisposition::Start
                },
            )
        }

        async fn finish_lifecycle_effect(
            &self,
            key: &str,
            status: &str,
            _external_ref: Option<&str>,
            _facts: serde_json::Value,
        ) -> Result<(), StoreError> {
            assert_eq!(status, "completed");
            self.state
                .lock()
                .expect("store")
                .completed_effects
                .insert(key.to_owned());
            Ok(())
        }

        async fn finish_lifecycle_run(
            &self,
            _request_id: Uuid,
            _run_id: Uuid,
            state_name: &str,
            _event_type: &str,
            _outcome: serde_json::Value,
        ) -> Result<(), StoreError> {
            self.state.lock().expect("store").terminal = Some(state_name.to_owned());
            Ok(())
        }
    }

    #[derive(Clone)]
    struct FakeGitHub {
        state: Arc<Mutex<FakeGitHubState>>,
    }

    struct FakeGitHubState {
        pull: PullRequest,
        checks: CheckRuns,
        ready_called: bool,
    }

    impl FakeGitHub {
        fn new(pull: PullRequest, checks: CheckRuns) -> Self {
            Self {
                state: Arc::new(Mutex::new(FakeGitHubState {
                    pull,
                    checks,
                    ready_called: false,
                })),
            }
        }
    }

    impl GitHubApi for FakeGitHub {
        fn mint_token<'a>(
            &'a self,
            _repository: &'a RepositoryScope,
            purpose: TokenPurpose,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, InstallationToken> {
            Box::pin(async move {
                assert_eq!(purpose, TokenPurpose::Lifecycle);
                Ok(InstallationToken {
                    value: "fixture-token".to_owned(),
                    bot: BotIdentity {
                        id: 1,
                        login: "patchyard[bot]".to_owned(),
                    },
                })
            })
        }

        fn open_pull_requests<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            _limit: usize,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, OpenPullRequestSnapshot> {
            Box::pin(async { unreachable!("publisher-only API") })
        }

        fn pull_requests_for_branch<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            _branch: &'a str,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, Vec<PullRequest>> {
            Box::pin(async move { Ok(vec![self.state.lock().expect("GitHub").pull.clone()]) })
        }

        fn create_draft_pull_request<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            _request: &'a CreatePullRequest,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, PullRequest> {
            Box::pin(async { unreachable!("publisher-only API") })
        }

        fn check_runs<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            _head_sha: &'a str,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, CheckRuns> {
            Box::pin(async move { Ok(self.state.lock().expect("GitHub").checks.clone()) })
        }

        fn update_pull_request_body<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            number: i32,
            body: &'a str,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, PullRequest> {
            Box::pin(async move {
                let mut state = self.state.lock().expect("GitHub");
                assert_eq!(state.pull.number, number);
                state.pull.body = Some(body.to_owned());
                Ok(state.pull.clone())
            })
        }

        fn mark_pull_request_ready<'a>(
            &'a self,
            _token: &'a InstallationToken,
            pull_request_node_id: &'a str,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, ()> {
            Box::pin(async move {
                let mut state = self.state.lock().expect("GitHub");
                assert_eq!(state.pull.node_id, pull_request_node_id);
                state.pull.draft = false;
                state.ready_called = true;
                Ok(())
            })
        }

        fn reviews<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            _number: i32,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, Vec<Review>> {
            Box::pin(async { Ok(Vec::new()) })
        }

        fn delete_branch<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            _branch: &'a str,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, ()> {
            Box::pin(async { unreachable!("publisher-only API") })
        }
    }

    #[derive(Clone)]
    struct FakePreview {
        state: Arc<Mutex<FakePreviewState>>,
    }

    struct FakePreviewState {
        release_failure: bool,
        releases: usize,
        log_scans: usize,
        calls: Arc<Mutex<Vec<String>>>,
    }

    impl FakePreview {
        fn new(release_failure: bool, calls: Arc<Mutex<Vec<String>>>) -> Self {
            Self {
                state: Arc::new(Mutex::new(FakePreviewState {
                    release_failure,
                    releases: 0,
                    log_scans: 0,
                    calls,
                })),
            }
        }

        fn release_count(&self) -> usize {
            self.state.lock().expect("preview").releases
        }

        fn log_scan_count(&self) -> usize {
            self.state.lock().expect("preview").log_scans
        }
    }

    impl PreviewApi for FakePreview {
        fn acquire<'a>(
            &'a self,
            request_id: &'a str,
            branch: &'a str,
            expected_sha: &'a str,
            lease_id: &'a str,
            _cancellation: &'a CancellationToken,
        ) -> PreviewFuture<'a, PreviewLease> {
            Box::pin(async move {
                Ok(PreviewLease {
                    ok: true,
                    slot: 1,
                    url: "https://1.preview.example.dev".to_owned(),
                    lease_id: lease_id.to_owned(),
                    owner: "factory-supervisor".to_owned(),
                    request_id: request_id.to_owned(),
                    expected_sha: expected_sha.to_owned(),
                    host_head: expected_sha.to_owned(),
                    preview_head: expected_sha.to_owned(),
                    expires_at: branch.to_owned(),
                })
            })
        }

        fn verify<'a>(
            &'a self,
            lease: &'a PreviewLease,
            _cancellation: &'a CancellationToken,
        ) -> PreviewFuture<'a, PreviewVerification> {
            Box::pin(async move {
                Ok(PreviewVerification {
                    ok: true,
                    slot: lease.slot,
                    lease_id: lease.lease_id.clone(),
                    expected_sha: lease.expected_sha.clone(),
                    host_head: lease.expected_sha.clone(),
                    preview_head: lease.expected_sha.clone(),
                })
            })
        }

        fn authorize<'a>(
            &'a self,
            lease: &'a PreviewLease,
            expected_sha: &'a str,
            capability_id: &'a str,
            _cancellation: &'a CancellationToken,
        ) -> PreviewFuture<'a, PreviewAuthorization> {
            Box::pin(async move {
                let now = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .expect("clock")
                    .as_secs();
                Ok(PreviewAuthorization {
                    ok: true,
                    slot: lease.slot,
                    lease_id: lease.lease_id.clone(),
                    expected_sha: expected_sha.to_owned(),
                    bearer: PreviewBearer {
                        capability_id: capability_id.to_owned(),
                        lease_id: lease.lease_id.clone(),
                        expires_at_unix: i64::try_from(now).expect("clock range") + 60,
                        secret: format!("efc1.{capability_id}.fixture-secret"),
                    },
                })
            })
        }

        fn scan_logs<'a>(
            &'a self,
            lease: &'a PreviewLease,
            _cancellation: &'a CancellationToken,
        ) -> PreviewFuture<'a, PreviewLogScan> {
            Box::pin(async move {
                self.state.lock().expect("preview").log_scans += 1;
                Ok(PreviewLogScan {
                    ok: true,
                    slot: lease.slot,
                    lease_id: lease.lease_id.clone(),
                    sources: 2,
                    bytes_scanned: 200,
                    matches: 0,
                })
            })
        }

        fn release<'a>(
            &'a self,
            lease: &'a PreviewLease,
            _cancellation: &'a CancellationToken,
        ) -> PreviewFuture<'a, PreviewRelease> {
            Box::pin(async move {
                let mut state = self.state.lock().expect("preview");
                state.releases += 1;
                let label = if lease.expected_sha.starts_with('b') {
                    "baseline"
                } else {
                    "candidate"
                };
                state
                    .calls
                    .lock()
                    .expect("call log")
                    .push(format!("release:{label}"));
                if state.release_failure {
                    return Err(PreviewError::CleanupFailed);
                }
                Ok(PreviewRelease {
                    ok: true,
                    slot: lease.slot,
                    lease_id: lease.lease_id.clone(),
                    cleanup_complete: true,
                    cleanup_errors: Vec::new(),
                    already_absent: false,
                })
            })
        }
    }

    #[derive(Clone)]
    struct FakeSecretScan {
        state: Arc<Mutex<FakeSecretScanState>>,
    }

    struct FakeSecretScanState {
        fail: bool,
        scans: usize,
        calls: Arc<Mutex<Vec<String>>>,
    }

    impl FakeSecretScan {
        fn new(fail: bool, calls: Arc<Mutex<Vec<String>>>) -> Self {
            Self {
                state: Arc::new(Mutex::new(FakeSecretScanState {
                    fail,
                    scans: 0,
                    calls,
                })),
            }
        }

        fn scan_count(&self) -> usize {
            self.state.lock().expect("secret scan").scans
        }
    }

    impl SecretScanApi for FakeSecretScan {
        fn scan<'a>(
            &'a self,
            _secret: &'a str,
            _capability_id: &'a str,
            _since_unix: i64,
            _cancellation: &'a CancellationToken,
        ) -> SecretScanFuture<'a> {
            Box::pin(async move {
                let mut state = self.state.lock().expect("secret scan");
                state.scans += 1;
                state
                    .calls
                    .lock()
                    .expect("call log")
                    .push("local-log-scan".to_owned());
                if state.fail {
                    return Err(SecretScanError::SecretFound(1));
                }
                Ok(SecretScan {
                    schema_version: 1,
                    sources: 1,
                    bytes_scanned: 100,
                    matches: 0,
                })
            })
        }
    }

    fn review_contract() -> ReviewContract {
        ReviewContract {
            request_source: "authenticated form".to_owned(),
            verbatim_request: "ALPHABETIZE the salesperson selectors.".to_owned(),
            lane: "A".to_owned(),
            rubric_version: "2026-07-21.1".to_owned(),
            root_causes: vec![RootCause {
                path: "mfieldbook/common_functions.php".to_owned(),
                line: 10,
                cause: "The shared helper emits source order.".to_owned(),
            }],
            named_assumptions: vec!["Option values and membership do not change.".to_owned()],
            risk: "A caller could depend on presentation order.".to_owned(),
            rollback: "Revert the single factory commit.".to_owned(),
            draft_reply: "The selectors are alphabetized and ready for review.".to_owned(),
            reviewer_quiz: vec![
                "Do both extracted orders preserve option membership?".to_owned(),
                "Does the shared helper retain caller semantics?".to_owned(),
            ],
            shared_function_touched: true,
            explain_diff: Some(
                "The shared helper changes presentation order for its authorized callers."
                    .to_owned(),
            ),
        }
    }

    fn pull_record(
        request_id: Uuid,
        run_id: Uuid,
        branch: &str,
        head_sha: &str,
    ) -> PullRequestRecord {
        PullRequestRecord {
            number: 42,
            request_id,
            run_id,
            branch: branch.to_owned(),
            head_sha: head_sha.to_owned(),
            ci_state: "pending".to_owned(),
            review_state: "draft".to_owned(),
            state: "open".to_owned(),
            is_draft: true,
            author_login: "patchyard[bot]".to_owned(),
            html_url: "https://github.com/example-org/fieldbook/pull/42".to_owned(),
            github_updated_at: OffsetDateTime::now_utc(),
            merged_at: None,
            merge_commit_sha: None,
            merged_by: None,
            deployed_sha: None,
            admin_bypassed: false,
            passing_run: false,
            reconcile_error: None,
        }
    }

    fn live_pull(branch: &str, head_sha: &str, body: &str) -> PullRequest {
        PullRequest {
            number: 42,
            node_id: "PR_fixture".to_owned(),
            draft: true,
            state: "open".to_owned(),
            body: Some(body.to_owned()),
            html_url: "https://github.com/example-org/fieldbook/pull/42".to_owned(),
            head: PullRequestRef {
                branch: branch.to_owned(),
                sha: head_sha.to_owned(),
            },
            base: PullRequestRef {
                branch: "master".to_owned(),
                sha: "b".repeat(40),
            },
            user: GitHubUser {
                login: "patchyard[bot]".to_owned(),
            },
            updated_at: "2026-07-25T00:00:00Z".to_owned(),
            merged_at: None,
            merge_commit_sha: None,
            merged_by: None,
        }
    }

    fn repository() -> RepositoryScope {
        RepositoryScope {
            owner: "example-org".to_owned(),
            name: "fieldbook".to_owned(),
        }
    }

    fn project_root() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .expect("project root")
    }
}
