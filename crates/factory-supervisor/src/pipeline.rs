//! One state-derived pipeline shared by the daemon and foreground operator.

use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
    sync::Arc,
    time::Instant,
};

use factory_core::{
    state::TriageSubmission,
    triage::{Lane, Rubric, TaskSpec, TriageOutput},
};
use factory_verify::ledger::{self, Provenance, RunRecord};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest as _, Sha256};
use thiserror::Error;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    artifacts::{ArtifactError, ArtifactStore, StoredArtifact},
    automaton,
    config::{RoutingConfig, RoutingError},
    contracts::{
        DispositionArtifact, DispositionKind, DispositionPacket, DisputeRecord, OutContract,
        ResolvedInvocation, TriageInvocation, VerifyFailure, WorkerClaim, WorkerTaskPacket,
    },
    observability,
    publisher::{
        PublishInput, PublishService, PublishedPullRequest, PublisherError, build_pr_body,
    },
    review::{ReviewError, SandboxedReviewer},
    stages::{
        ProcessAgentBackend, ProcessVerifierBackend, ProcessWorkerBackend, StageError,
        read_bounded_file,
    },
    store::{ExistingRun, PipelineStore, SideEffectDisposition, StoreError, WorkClaim},
    worktree::{
        ExactBundle, WorktreeError, hash_commit_tree, inspect_patch, materialize_review_sha,
    },
};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RunMode {
    DryRun,
    PrePublish,
}

#[derive(Clone, Debug)]
pub struct PipelineConfig {
    pub repository: PathBuf,
    pub base_sha: String,
    pub scratch: PathBuf,
    pub holder: String,
    pub mode: RunMode,
    pub publish_branch_suffix: String,
    pub reviewer_count: usize,
    pub builder_cli_version: String,
    pub constitution: PathBuf,
    pub rubric_source: PathBuf,
    pub skill: PathBuf,
    pub implement_prompt: PathBuf,
    pub verifier_binary: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "outcome", rename_all = "snake_case")]
pub enum PipelineOutcome {
    PlanBin {
        lane: String,
        request_id: Uuid,
    },
    DryRunComplete {
        run_id: Uuid,
        attempts: u8,
    },
    PublishedDraft {
        run_id: Uuid,
        attempts: u8,
        pull_request: PublishedPullRequest,
    },
    Escalated {
        run_id: Uuid,
        reason: String,
    },
    AlreadyTerminal {
        run_id: Uuid,
        state: String,
    },
}

#[derive(Clone)]
pub struct Pipeline<S: PipelineStore> {
    store: S,
    config: PipelineConfig,
    routing: RoutingConfig,
    rubric: Rubric,
    artifacts: ArtifactStore,
    agents: ProcessAgentBackend,
    worker: ProcessWorkerBackend,
    verifier: ProcessVerifierBackend,
    reviewer: SandboxedReviewer,
    publisher: Option<Arc<dyn PublishService>>,
}

impl<S: PipelineStore> Pipeline<S> {
    #[allow(clippy::too_many_arguments)]
    #[must_use]
    pub fn new(
        store: S,
        config: PipelineConfig,
        routing: RoutingConfig,
        rubric: Rubric,
        artifacts: ArtifactStore,
        agents: ProcessAgentBackend,
        worker: ProcessWorkerBackend,
        verifier: ProcessVerifierBackend,
        reviewer: SandboxedReviewer,
        publisher: Option<Arc<dyn PublishService>>,
    ) -> Self {
        Self {
            store,
            config,
            routing,
            rubric,
            artifacts,
            agents,
            worker,
            verifier,
            reviewer,
            publisher,
        }
    }

    /// Execute one claimed row. Lease release is an explicit checked operation
    /// on every return path; Drop is never used as a correctness mechanism.
    #[tracing::instrument(skip_all, fields(request_id = %claim.request_id, recovered = claim.recovered))]
    pub async fn run_claim(
        &self,
        claim: WorkClaim,
        cancellation: &CancellationToken,
    ) -> Result<PipelineOutcome, PipelineError> {
        let result = self.run_inner(&claim, cancellation).await;
        let release = self
            .store
            .release_lease(claim.request_id, &self.config.holder)
            .await;
        match (result, release) {
            (Ok(outcome), Ok(())) => Ok(outcome),
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error.into()),
        }
    }

    /// Idempotent teardown used by a control-row kill, including after daemon
    /// restart when no in-memory task remains.
    pub async fn kill_cleanup(&self, run_id: Uuid) -> Result<(), PipelineError> {
        let first = self
            .worker
            .teardown(&format!("{}-a0", run_id.simple()))
            .await;
        let second = self
            .worker
            .teardown(&format!("{}-a1", run_id.simple()))
            .await;
        first?;
        second?;
        Ok(())
    }

    async fn run_inner(
        &self,
        claim: &WorkClaim,
        cancellation: &CancellationToken,
    ) -> Result<PipelineOutcome, PipelineError> {
        let task_spec = self.task_spec(claim, cancellation).await?;
        let classification = self.rubric.classify(&task_spec)?;
        if classification.lane != Lane::A && task_spec.validate_human_approved().is_err() {
            return Ok(PipelineOutcome::PlanBin {
                lane: classification.lane.to_string(),
                request_id: claim.request_id,
            });
        }
        let lane = if classification.lane == Lane::A {
            Lane::A
        } else {
            Lane::B
        };
        let run = self
            .ensure_run(claim.request_id, &task_spec, lane, cancellation)
            .await?;
        if matches!(
            run.state.as_str(),
            "dry_run_complete" | "closed" | "ready_for_review" | "killed" | "failed" | "escalated"
        ) {
            return Ok(PipelineOutcome::AlreadyTerminal {
                run_id: run.id,
                state: run.state,
            });
        }
        if matches!(run.state.as_str(), "verified" | "publishing") {
            return self.resume_publication(claim, &run, cancellation).await;
        }

        let bundle = ExactBundle::create(
            &self.config.repository,
            &run.base_sha,
            &self.config.scratch.join("bundles"),
            cancellation,
        )
        .await?;
        let result = self
            .attempts(claim, &task_spec, lane, &run, &bundle, cancellation)
            .await;
        let cleanup = bundle.close().await;
        match (result, cleanup) {
            (Ok(outcome), Ok(())) => Ok(outcome),
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error.into()),
        }
    }

    async fn task_spec(
        &self,
        claim: &WorkClaim,
        cancellation: &CancellationToken,
    ) -> Result<TaskSpec, PipelineError> {
        if let Some(task) = self.store.authoritative_task_spec(claim.request_id).await? {
            return Ok(task);
        }
        let invocation = self.invocation("triage")?;
        let input = TriageInvocation {
            schema_version: 1,
            request_id: claim.request_id,
            untrusted_request: claim.body.clone(),
            authority: "none_untrusted_data_only".to_owned(),
        };
        let started = Instant::now();
        let result = self
            .agents
            .invoke::<_, TriageOutput>(&invocation, &input, cancellation)
            .await;
        let output = match result {
            Ok(output) => {
                observability::record_stage("triage", "success", started.elapsed());
                output
            }
            Err(error) => {
                observability::record_stage("triage", "error", started.elapsed());
                return Err(error.into());
            }
        };
        output.value.validate()?;
        self.persist(
            claim.request_id,
            None,
            "triage",
            "transcript.log",
            "agent-transcript",
            output.transcript,
            8 * 1024 * 1024,
        )
        .await?;
        observability::record_usage(invocation.seat.model_id(), output.usage);
        let classification = self.rubric.classify(&output.value.task_spec)?;
        let submission = TriageSubmission {
            id: Uuid::new_v4(),
            plan_id: (classification.lane != Lane::A).then(Uuid::new_v4),
            output: output.value,
        };
        let _recorded = self
            .store
            .record_triage(claim.request_id, &submission, &self.rubric)
            .await?;
        Ok(submission.output.task_spec)
    }

    async fn ensure_run(
        &self,
        request_id: Uuid,
        task: &TaskSpec,
        lane: Lane,
        cancellation: &CancellationToken,
    ) -> Result<ExistingRun, PipelineError> {
        if let Some(run) = self.store.existing_run(request_id).await? {
            if run.base_sha != self.config.base_sha {
                return Err(PipelineError::RecoveryBaseSha {
                    durable: run.base_sha,
                    configured: self.config.base_sha.clone(),
                });
            }
            return Ok(run);
        }
        let invocation = self.invocation("implement")?;
        let run_id = Uuid::new_v4();
        let provenance = Provenance {
            model_id: invocation.seat.model_id(),
            cli_version: self.config.builder_cli_version.clone(),
            harness: invocation.seat.harness.clone(),
            provider: invocation.seat.provider.clone(),
            effort: invocation.seat.effort.clone(),
            routing_config_version: invocation.routing_version.clone(),
            model_id_hash: hash_bytes(invocation.seat.model_id().as_bytes()),
            cli_version_hash: hash_bytes(self.config.builder_cli_version.as_bytes()),
            constitution_hash: hash_path(&self.config.constitution).await?,
            rubric_hash: hash_path(&self.config.rubric_source).await?,
            skill_hash: hash_path(&self.config.skill).await?,
            prompt_template_hash: hash_path(&self.config.implement_prompt).await?,
            verifier_binary_hash: hash_path(&self.config.verifier_binary).await?,
            base_tree_hash: hash_commit_tree(
                &self.config.repository,
                &self.config.base_sha,
                &self.config.scratch.join("provenance"),
                cancellation,
            )
            .await?,
        };
        let skill = task
            .named_skill
            .clone()
            .unwrap_or_else(|| "approved-plan".to_owned());
        let record = ledger::validate(RunRecord {
            id: run_id,
            request_id,
            base_sha: self.config.base_sha.clone(),
            branch: match self.config.mode {
                RunMode::DryRun => format!("factory/dry-run/{}", run_id.simple()),
                RunMode::PrePublish => {
                    format!("factory/{request_id}-{}", self.config.publish_branch_suffix)
                }
            },
            lane: lane.to_string(),
            skill: skill.clone(),
            provenance,
        })?;
        self.store.append_run(&record).await?;
        Ok(ExistingRun {
            id: run_id,
            base_sha: self.config.base_sha.clone(),
            branch: record.record().branch.clone(),
            state: "queued".to_owned(),
            lane: lane.to_string(),
            skill,
        })
    }

    #[allow(clippy::too_many_arguments)]
    async fn attempts(
        &self,
        claim: &WorkClaim,
        task: &TaskSpec,
        lane: Lane,
        run: &ExistingRun,
        bundle: &ExactBundle,
        cancellation: &CancellationToken,
    ) -> Result<PipelineOutcome, PipelineError> {
        let mut failure = None;
        for attempt in 0..=1 {
            let task_packet = WorkerTaskPacket {
                schema_version: 1,
                run_id: run.id,
                attempt,
                dry_run: self.config.mode == RunMode::DryRun,
                task_spec: task.clone(),
                invocation: self.invocation(if attempt == 0 { "implement" } else { "repair" })?,
                verify_failure: failure.clone(),
            };
            let packet_path = self
                .config
                .scratch
                .join(format!("task-{}-a{attempt}.json", run.id.simple()));
            remove_if_present(&packet_path).await?;
            crate::stages::write_private(packet_path.clone(), serde_json::to_vec(&task_packet)?)
                .await?;
            let stage_result = self
                .run_worker(
                    claim.request_id,
                    run.id,
                    attempt,
                    bundle,
                    &packet_path,
                    &task_packet,
                    cancellation,
                )
                .await;
            let packet_cleanup = remove_file_checked(packet_path).await;
            let outputs = match (stage_result, packet_cleanup) {
                (Ok(outputs), Ok(())) => outputs,
                (Err(error), Ok(())) => return Err(error),
                (_, Err(error)) => return Err(error),
            };

            let patch_path = self.artifacts.root().join(&outputs.patch.relative_path);
            let inspected = inspect_patch(
                &self.config.repository,
                &run.base_sha,
                &patch_path,
                &self.config.scratch.join("inspect"),
                cancellation,
            )
            .await?;
            let evidence: WorkerEvidence = serde_json::from_slice(&outputs.evidence_bytes)?;
            evidence.validate()?;
            self.record_usage(run.id, &task_packet.invocation, evidence.usage)
                .await?;
            let contract = OutContract {
                schema_version: 1,
                run_id: run.id,
                attempt,
                base_sha: run.base_sha.clone(),
                patch_sha256: inspected.patch_sha256.clone(),
                base_tree_hash: inspected.base_tree_hash,
                result_tree_hash: inspected.result_tree_hash,
                manifest: inspected.manifest,
                claims: evidence.claims,
            };
            let patch_text = std::str::from_utf8(&outputs.patch_bytes)
                .map_err(|_| PipelineError::PatchNotUtf8)?;
            let acceptance = automaton::accept(task, lane, &contract, patch_text)?;
            self.persist(
                claim.request_id,
                Some(run.id),
                &format!("attempt-{attempt}"),
                "out-contract.json",
                "out-contract",
                serde_json::to_vec(&contract)?,
                1024 * 1024,
            )
            .await?;

            if self
                .adversarial_review(
                    claim.request_id,
                    run.id,
                    task,
                    &contract,
                    &patch_path,
                    cancellation,
                )
                .await?
            {
                let reason = "review_dispute_requires_third_family".to_owned();
                self.store
                    .finish_run(
                        claim.request_id,
                        run.id,
                        "escalated",
                        "run.escalated",
                        serde_json::json!({"reason": reason, "dry_run": true, "publish_invoked": false}),
                    )
                    .await?;
                return Ok(PipelineOutcome::Escalated {
                    run_id: run.id,
                    reason,
                });
            }

            let verify = self
                .run_verify(
                    claim.request_id,
                    run.id,
                    attempt,
                    &patch_path,
                    &outputs.evidence,
                    cancellation,
                )
                .await?;
            if verify.passed {
                if self.config.mode == RunMode::DryRun {
                    self.store
                        .finish_run(
                            claim.request_id,
                            run.id,
                            "dry_run_complete",
                            "run.dry_run_complete",
                            serde_json::json!({
                                "dry_run": true,
                                "publish_invoked": false,
                                "attempt": attempt,
                                "accept": acceptance,
                            }),
                        )
                        .await?;
                    return Ok(PipelineOutcome::DryRunComplete {
                        run_id: run.id,
                        attempts: attempt + 1,
                    });
                }
                let input = PublishInput {
                    schema_version: 1,
                    request_id: claim.request_id,
                    run_id: run.id,
                    attempts: attempt + 1,
                    branch: run.branch.clone(),
                    base_sha: run.base_sha.clone(),
                    patch_relative_path: outputs.patch.relative_path.clone(),
                    patch_sha256: inspected.patch_sha256,
                    expected_tree_hash: contract.result_tree_hash.clone(),
                    title: format!("Factory request {}", claim.request_id),
                    body: build_pr_body(
                        claim.request_id,
                        &claim.source,
                        &claim.body,
                        &run.base_sha,
                        &contract.result_tree_hash,
                        &contract.patch_sha256,
                    )?,
                };
                let input = self.persist_publish_input(&input).await?;
                self.store
                    .transition_run(
                        claim.request_id,
                        run.id,
                        "run.verified",
                        "verified",
                        &format!("publisher:{}:verified", run.id),
                        serde_json::json!({
                            "attempt": attempt,
                            "patch_sha256": input.patch_sha256,
                            "result_tree_hash": input.expected_tree_hash,
                            "publish_input": true,
                        }),
                    )
                    .await?;
                return self
                    .publish_durable(&input, attempt + 1, cancellation)
                    .await;
            }
            if attempt == 0 {
                failure = Some(VerifyFailure {
                    schema_version: 1,
                    attempt,
                    gate: "deterministic_verifier".to_owned(),
                    reason_code: verify.reason_code,
                    evidence_artifact: verify.evidence.relative_path,
                });
                self.store
                    .transition_run(
                        claim.request_id,
                        run.id,
                        "repair.queued",
                        "repairing",
                        &format!("repair:{}:1", run.id),
                        serde_json::json!({"attempt": 1}),
                    )
                    .await?;
            }
        }
        let reason = "repair_exhausted".to_owned();
        self.store
            .finish_run(
                claim.request_id,
                run.id,
                "escalated",
                "repair.exhausted",
                serde_json::json!({"reason": reason, "attempts": 2, "publish_invoked": false}),
            )
            .await?;
        Ok(PipelineOutcome::Escalated {
            run_id: run.id,
            reason,
        })
    }

    #[allow(clippy::too_many_arguments)]
    async fn run_worker(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        attempt: u8,
        bundle: &ExactBundle,
        packet: &Path,
        task_packet: &WorkerTaskPacket,
        cancellation: &CancellationToken,
    ) -> Result<PersistedWorker, PipelineError> {
        let key = format!("worker:{run_id}:{attempt}");
        let disposition = self
            .store
            .begin_side_effect(request_id, Some(run_id), &key, "remote-worker", attempt)
            .await?;
        let stage = format!("attempt-{attempt}");
        self.store
            .transition_run(
                request_id,
                run_id,
                if attempt == 0 {
                    "worker.started"
                } else {
                    "repair.started"
                },
                if attempt == 0 {
                    "implementing"
                } else {
                    "repairing"
                },
                &format!("{key}:started"),
                serde_json::json!({"attempt": attempt, "seat": task_packet.invocation}),
            )
            .await?;
        if let Some(outputs) = self
            .recover_worker_outputs(request_id, run_id, &stage)
            .await?
        {
            if disposition != SideEffectDisposition::Completed {
                self.store
                    .finish_side_effect(
                        &key,
                        "completed",
                        Some(&format!("{}-a{attempt}", run_id.simple())),
                        serde_json::json!({
                            "bundle_sha256": bundle.sha256,
                            "teardown_complete": true,
                            "recovered_artifacts": true,
                        }),
                    )
                    .await?;
            }
            self.store
                .transition_run(
                    request_id,
                    run_id,
                    "worker.terminated",
                    "reviewing",
                    &format!("{key}:terminated"),
                    serde_json::json!({"attempt": attempt, "recovered_artifacts": true}),
                )
                .await?;
            return Ok(outputs);
        }
        if disposition == SideEffectDisposition::Completed {
            return Err(PipelineError::RecoveredArtifactSet {
                stage,
                reason: "completed worker side effect has no durable result artifacts".to_owned(),
            });
        }
        let started = Instant::now();
        let result = self
            .worker
            .invoke(
                run_id,
                attempt,
                bundle,
                packet,
                &task_packet.invocation,
                cancellation,
            )
            .await;
        let worker = match result {
            Ok(worker) => {
                observability::record_stage("implement", "success", started.elapsed());
                worker
            }
            Err(error) => {
                observability::record_stage("implement", "error", started.elapsed());
                self.store
                    .finish_side_effect(
                        &key,
                        "failed",
                        None,
                        serde_json::json!({"attempt": attempt}),
                    )
                    .await?;
                return Err(error.into());
            }
        };
        let patch_bytes = worker.patch;
        let evidence_bytes = worker.evidence;
        let patch = self
            .persist(
                request_id,
                Some(run_id),
                &stage,
                "change.patch",
                "patch",
                patch_bytes.clone(),
                1024 * 1024,
            )
            .await?;
        let evidence = self
            .persist(
                request_id,
                Some(run_id),
                &stage,
                "evidence.json",
                "worker-evidence",
                evidence_bytes.clone(),
                128 * 1024,
            )
            .await?;
        self.persist(
            request_id,
            Some(run_id),
            &stage,
            "rationale.txt",
            "rationale",
            worker.rationale,
            64 * 1024,
        )
        .await?;
        self.persist(
            request_id,
            Some(run_id),
            &stage,
            "transcript.jsonl",
            "agent-transcript",
            worker.transcript,
            8 * 1024 * 1024,
        )
        .await?;
        // `invoke` returns only after awaited worker teardown. Persist every
        // bounded result before marking the external effect complete, so a
        // restart can recover by durable rows rather than invoke it twice.
        self.store
            .finish_side_effect(
                &key,
                "completed",
                Some(&worker.run_key),
                serde_json::json!({
                    "bundle_sha256": bundle.sha256,
                    "teardown_complete": true,
                    "patch_artifact": patch.relative_path,
                    "evidence_artifact": evidence.relative_path,
                }),
            )
            .await?;
        self.store
            .transition_run(
                request_id,
                run_id,
                "worker.terminated",
                "reviewing",
                &format!("{key}:terminated"),
                serde_json::json!({"attempt": attempt, "run_key": worker.run_key}),
            )
            .await?;
        Ok(PersistedWorker {
            patch,
            evidence,
            patch_bytes,
            evidence_bytes,
        })
    }

    async fn recover_worker_outputs(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        stage: &str,
    ) -> Result<Option<PersistedWorker>, PipelineError> {
        let artifacts = self
            .store
            .stage_artifacts(request_id, run_id, stage)
            .await?;
        let required = BTreeMap::from([
            ("patch", 1024 * 1024),
            ("worker-evidence", 128 * 1024),
            ("rationale", 64 * 1024),
            ("agent-transcript", 8 * 1024 * 1024),
        ]);
        let mut matches: BTreeMap<String, Vec<StoredArtifact>> = BTreeMap::new();
        for artifact in artifacts {
            if required.contains_key(artifact.kind.as_str()) {
                matches
                    .entry(artifact.kind.clone())
                    .or_default()
                    .push(artifact);
            }
        }
        if matches.is_empty() {
            return Ok(None);
        }
        let mut recovered = BTreeMap::new();
        for (kind, maximum) in required {
            let Some(mut candidates) = matches.remove(kind) else {
                return Err(PipelineError::RecoveredArtifactSet {
                    stage: stage.to_owned(),
                    reason: format!("missing {kind}"),
                });
            };
            if candidates.len() != 1 {
                return Err(PipelineError::RecoveredArtifactSet {
                    stage: stage.to_owned(),
                    reason: format!("expected one {kind}, found {}", candidates.len()),
                });
            }
            let mut artifact = candidates.pop().expect("length checked");
            let bytes =
                read_bounded_file(self.artifacts.root().join(&artifact.relative_path), maximum)
                    .await?;
            let actual = hash_bytes(&bytes);
            if actual != artifact.sha256 {
                return Err(PipelineError::RecoveredArtifactDigest {
                    path: artifact.relative_path,
                });
            }
            artifact.bytes =
                u64::try_from(bytes.len()).map_err(|_| PipelineError::RecoveredArtifactSet {
                    stage: stage.to_owned(),
                    reason: "artifact length overflow".to_owned(),
                })?;
            recovered.insert(kind, (artifact, bytes));
        }
        let (patch, patch_bytes) = recovered.remove("patch").expect("required artifact");
        let (evidence, evidence_bytes) = recovered
            .remove("worker-evidence")
            .expect("required artifact");
        Ok(Some(PersistedWorker {
            patch,
            evidence,
            patch_bytes,
            evidence_bytes,
        }))
    }

    async fn adversarial_review(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        task: &TaskSpec,
        contract: &OutContract,
        patch: &Path,
        cancellation: &CancellationToken,
    ) -> Result<bool, PipelineError> {
        let reviewed_sha = materialize_review_sha(
            &self.config.repository,
            &contract.base_sha,
            patch,
            &self.config.scratch.join("review-materialize"),
            cancellation,
        )
        .await?;
        let invocation = self.invocation("implementation_review")?;
        let invocations = (0..self.config.reviewer_count)
            .map(|_| invocation.clone())
            .collect();
        let started = Instant::now();
        let reviews = self
            .reviewer
            .review_many(
                &self.config.repository,
                &reviewed_sha,
                task,
                &contract.patch_sha256,
                &contract.manifest,
                invocations,
                cancellation,
            )
            .await?;
        observability::record_stage("review", "success", started.elapsed());
        let mut escalate = false;
        for (index, review) in reviews.into_iter().enumerate() {
            let stage = format!("review-{index}");
            self.persist(
                request_id,
                Some(run_id),
                &stage,
                "review.json",
                "review-artifact",
                serde_json::to_vec(&review.artifact)?,
                1024 * 1024,
            )
            .await?;
            self.persist(
                request_id,
                Some(run_id),
                &stage,
                "transcript.log",
                "agent-transcript",
                review.transcript,
                8 * 1024 * 1024,
            )
            .await?;
            self.record_usage(run_id, &review.invocation, review.artifact.usage)
                .await?;
            self.store
                .transition_run(
                    request_id,
                    run_id,
                    "review.submitted",
                    "reviewing",
                    &format!("review:{}", review.artifact.review_id),
                    serde_json::json!({
                        "review_id": review.artifact.review_id,
                        "reviewed_sha": review.artifact.reviewed_sha,
                        "sibling_unreachable": review.sibling_unreachable,
                        "shared_scratch_unreachable": review.shared_scratch_unreachable,
                        "seat": review.invocation,
                    }),
                )
                .await?;
            if review.artifact.findings.is_empty() {
                continue;
            }
            let disposition_invocation = self.invocation("author_disposition")?;
            let packet = DispositionPacket {
                schema_version: 1,
                review: review.artifact.clone(),
                task_spec: task.clone(),
                patch_sha256: contract.patch_sha256.clone(),
            };
            let disposition = self
                .agents
                .invoke::<_, DispositionArtifact>(&disposition_invocation, &packet, cancellation)
                .await?;
            validate_dispositions(&review.artifact, &disposition.value)?;
            self.persist(
                request_id,
                Some(run_id),
                &stage,
                "disposition.json",
                "disposition-artifact",
                serde_json::to_vec(&disposition.value)?,
                1024 * 1024,
            )
            .await?;
            self.persist(
                request_id,
                Some(run_id),
                &format!("disposition-{index}"),
                "transcript.log",
                "agent-transcript",
                disposition.transcript,
                8 * 1024 * 1024,
            )
            .await?;
            self.record_usage(run_id, &disposition_invocation, disposition.usage)
                .await?;
            for item in &disposition.value.dispositions {
                self.store
                    .transition_run(
                        request_id,
                        run_id,
                        "review.finding_disposition",
                        "reviewing",
                        &format!(
                            "disposition:{}:{}",
                            review.artifact.review_id, item.finding_id
                        ),
                        serde_json::to_value(item)?,
                    )
                    .await?;
                if matches!(
                    item.disposition,
                    DispositionKind::Refute | DispositionKind::Escalate
                ) {
                    let finding = review
                        .artifact
                        .findings
                        .iter()
                        .find(|finding| finding.id == item.finding_id)
                        .expect("validated disposition references a finding");
                    let dispute = DisputeRecord {
                        schema_version: 1,
                        dispute_id: Uuid::new_v4(),
                        reviewed_sha: reviewed_sha.clone(),
                        task_spec_sha256: hex::encode(task.sha256()?),
                        patch_sha256: contract.patch_sha256.clone(),
                        finding: finding.clone(),
                        author_disposition: item.clone(),
                    };
                    self.persist(
                        request_id,
                        Some(run_id),
                        &stage,
                        "dispute.json",
                        "dispute-record",
                        serde_json::to_vec(&dispute)?,
                        1024 * 1024,
                    )
                    .await?;
                    self.store
                        .transition_run(
                            request_id,
                            run_id,
                            "review.dispute_escalated",
                            "reviewing",
                            &format!("dispute:{}", dispute.dispute_id),
                            serde_json::json!({
                                "dispute_id": dispute.dispute_id,
                                "arbiter": self.invocation("dispute_arbitration")?,
                                "stubbed": true,
                            }),
                        )
                        .await?;
                    escalate = true;
                }
            }
        }
        Ok(escalate)
    }

    async fn run_verify(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        attempt: u8,
        patch: &Path,
        implement_evidence: &StoredArtifact,
        cancellation: &CancellationToken,
    ) -> Result<PersistedVerify, PipelineError> {
        self.store
            .transition_run(
                request_id,
                run_id,
                "verify.started",
                "verifying",
                &format!("verify:{run_id}:{attempt}:started"),
                serde_json::json!({"attempt": attempt}),
            )
            .await?;
        let started = Instant::now();
        let result = self
            .verifier
            .verify(
                &self.config.repository,
                &self.config.base_sha,
                patch,
                &self
                    .artifacts
                    .root()
                    .join(&implement_evidence.relative_path),
                run_id,
                attempt,
                cancellation,
            )
            .await?;
        observability::record_stage(
            "verify",
            if result.passed { "success" } else { "failed" },
            started.elapsed(),
        );
        let evidence = self
            .persist(
                request_id,
                Some(run_id),
                &format!("verify-{attempt}"),
                "evidence.json",
                "verify-evidence",
                result.evidence,
                512 * 1024,
            )
            .await?;
        self.persist(
            request_id,
            Some(run_id),
            &format!("verify-{attempt}"),
            "transcript.log",
            "verifier-transcript",
            result.transcript,
            2 * 1024 * 1024,
        )
        .await?;
        self.store.transition_run(
            request_id,
            run_id,
            if result.passed { "verify.passed" } else { "verify.failed" },
            "verifying",
            &format!("verify:{run_id}:{attempt}:complete"),
            serde_json::json!({"attempt": attempt, "passed": result.passed, "evidence": evidence.relative_path}),
        ).await?;
        Ok(PersistedVerify {
            passed: result.passed,
            reason_code: result.reason_code,
            evidence,
        })
    }

    async fn persist_publish_input(
        &self,
        intended: &PublishInput,
    ) -> Result<PublishInput, PipelineError> {
        if let Some(existing) = self
            .load_publish_input(intended.request_id, intended.run_id)
            .await?
        {
            if existing != *intended {
                return Err(PipelineError::PublishInputConflict);
            }
            return Ok(existing);
        }
        intended.validate()?;
        self.persist(
            intended.request_id,
            Some(intended.run_id),
            "publisher",
            "publish-input.json",
            "publish-input",
            serde_json::to_vec(intended)?,
            128 * 1024,
        )
        .await?;
        Ok(intended.clone())
    }

    async fn load_publish_input(
        &self,
        request_id: Uuid,
        run_id: Uuid,
    ) -> Result<Option<PublishInput>, PipelineError> {
        let mut inputs: Vec<_> = self
            .store
            .stage_artifacts(request_id, run_id, "publisher")
            .await?
            .into_iter()
            .filter(|artifact| artifact.kind == "publish-input")
            .collect();
        if inputs.is_empty() {
            return Ok(None);
        }
        if inputs.len() != 1 {
            return Err(PipelineError::RecoveredArtifactSet {
                stage: "publisher".to_owned(),
                reason: format!("expected one publish-input, found {}", inputs.len()),
            });
        }
        let artifact = inputs.pop().expect("length checked");
        let bytes = read_bounded_file(
            self.artifacts.root().join(&artifact.relative_path),
            128 * 1024,
        )
        .await?;
        if hash_bytes(&bytes) != artifact.sha256 {
            return Err(PipelineError::RecoveredArtifactDigest {
                path: artifact.relative_path,
            });
        }
        let input: PublishInput = serde_json::from_slice(&bytes)?;
        input.validate()?;
        if input.request_id != request_id || input.run_id != run_id {
            return Err(PipelineError::PublishInputIdentity);
        }
        Ok(Some(input))
    }

    async fn resume_publication(
        &self,
        claim: &WorkClaim,
        run: &ExistingRun,
        cancellation: &CancellationToken,
    ) -> Result<PipelineOutcome, PipelineError> {
        let input = self
            .load_publish_input(claim.request_id, run.id)
            .await?
            .ok_or(PipelineError::MissingPublishInput)?;
        if input.base_sha != run.base_sha || input.branch != run.branch {
            return Err(PipelineError::PublishInputConflict);
        }
        self.publish_durable(&input, input.attempts, cancellation)
            .await
    }

    async fn publish_durable(
        &self,
        input: &PublishInput,
        attempts: u8,
        cancellation: &CancellationToken,
    ) -> Result<PipelineOutcome, PipelineError> {
        let publisher = self
            .publisher
            .as_ref()
            .ok_or(PipelineError::PublisherUnavailable)?;
        let patch_path = self.artifacts.root().join(&input.patch_relative_path);
        let patch = read_bounded_file(patch_path.clone(), 1024 * 1024).await?;
        if hash_bytes(&patch) != input.patch_sha256 {
            return Err(PipelineError::RecoveredArtifactDigest {
                path: input.patch_relative_path.clone(),
            });
        }
        let pull_request = publisher.publish(input, &patch_path, cancellation).await?;
        self.store
            .finish_run(
                input.request_id,
                input.run_id,
                "ready_for_review",
                "run.ready_for_review",
                serde_json::json!({
                    "dry_run": false,
                    "publish_invoked": true,
                    "attempts": attempts,
                    "pull_request": pull_request,
                }),
            )
            .await?;
        Ok(PipelineOutcome::PublishedDraft {
            run_id: input.run_id,
            attempts,
            pull_request,
        })
    }

    fn invocation(&self, task_class: &str) -> Result<ResolvedInvocation, PipelineError> {
        let rule = self.routing.resolve(task_class)?;
        Ok(ResolvedInvocation {
            task_class: task_class.to_owned(),
            routing_version: self.routing.version.clone(),
            seat: rule.seat.clone(),
        })
    }

    async fn record_usage(
        &self,
        run_id: Uuid,
        invocation: &ResolvedInvocation,
        usage: crate::contracts::InvocationUsage,
    ) -> Result<(), PipelineError> {
        observability::record_usage(invocation.seat.model_id(), usage);
        self.store
            .record_usage(run_id, &invocation.seat.model_id(), usage)
            .await?;
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    async fn persist(
        &self,
        request_id: Uuid,
        run_id: Option<Uuid>,
        stage: &str,
        name: &str,
        kind: &str,
        bytes: Vec<u8>,
        maximum: usize,
    ) -> Result<StoredArtifact, PipelineError> {
        let artifact = self
            .artifacts
            .put(request_id, run_id, stage, name, kind, bytes, maximum)
            .await?;
        self.store
            .register_artifact(request_id, run_id, stage, &artifact)
            .await?;
        Ok(artifact)
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkerEvidence {
    schema_version: u16,
    #[serde(default)]
    claims: Vec<WorkerClaim>,
    #[serde(default)]
    usage: crate::contracts::InvocationUsage,
    #[serde(flatten)]
    runtime_facts: BTreeMap<String, Value>,
}

impl WorkerEvidence {
    fn validate(&self) -> Result<(), PipelineError> {
        if self.schema_version != 1 || self.claims.len() > 100 || self.runtime_facts.len() > 100 {
            return Err(PipelineError::MalformedWorkerEvidence);
        }
        let mut ids = BTreeSet::new();
        if self.claims.iter().any(|claim| {
            claim.id.trim().is_empty()
                || claim.assertion.trim().is_empty()
                || claim.evidence_ref.trim().is_empty()
                || !ids.insert(&claim.id)
        }) {
            return Err(PipelineError::MalformedWorkerEvidence);
        }
        Ok(())
    }
}

struct PersistedWorker {
    patch: StoredArtifact,
    evidence: StoredArtifact,
    patch_bytes: Vec<u8>,
    evidence_bytes: Vec<u8>,
}

struct PersistedVerify {
    passed: bool,
    reason_code: String,
    evidence: StoredArtifact,
}

fn validate_dispositions(
    review: &crate::contracts::ReviewArtifact,
    disposition: &DispositionArtifact,
) -> Result<(), PipelineError> {
    if disposition.schema_version != 1 || disposition.review_id != review.review_id {
        return Err(PipelineError::MalformedDisposition);
    }
    let expected: BTreeSet<&str> = review
        .findings
        .iter()
        .map(|finding| finding.id.as_str())
        .collect();
    let actual: BTreeSet<&str> = disposition
        .dispositions
        .iter()
        .map(|item| item.finding_id.as_str())
        .collect();
    if expected != actual || disposition.dispositions.len() != review.findings.len() {
        return Err(PipelineError::MalformedDisposition);
    }
    Ok(())
}

fn hash_bytes(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

async fn hash_path(path: &Path) -> Result<String, PipelineError> {
    let path = path.to_path_buf();
    tokio::task::spawn_blocking(move || std::fs::read(path).map(|bytes| hash_bytes(&bytes)))
        .await
        .map_err(PipelineError::Join)?
        .map_err(PipelineError::Io)
}

async fn remove_if_present(path: &Path) -> Result<(), PipelineError> {
    match tokio::fs::remove_file(path).await {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
    }
}

async fn remove_file_checked(path: PathBuf) -> Result<(), PipelineError> {
    remove_if_present(&path).await
}

#[derive(Debug, Error)]
pub enum PipelineError {
    #[error("pipeline store failed: {0}")]
    Store(#[from] StoreError),
    #[error("stage failed: {0}")]
    Stage(#[from] StageError),
    #[error("review failed: {0}")]
    Review(#[from] ReviewError),
    #[error("artifact persistence failed: {0}")]
    Artifact(#[from] ArtifactError),
    #[error("exact worktree operation failed: {0}")]
    Worktree(#[from] WorktreeError),
    #[error("deterministic accept gate failed: {0}")]
    Accept(#[from] automaton::AcceptError),
    #[error("routing failed: {0}")]
    Routing(#[from] RoutingError),
    #[error("triage policy failed: {0}")]
    Triage(#[from] factory_core::triage::TriageError),
    #[error("run provenance failed: {0}")]
    Ledger(#[from] ledger::LedgerError),
    #[error("typed artifact JSON failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("pipeline filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("blocking pipeline task failed: {0}")]
    Join(tokio::task::JoinError),
    #[error("durable base SHA {durable} differs from configured SHA {configured}")]
    RecoveryBaseSha { durable: String, configured: String },
    #[error("worker patch is not UTF-8")]
    PatchNotUtf8,
    #[error("worker evidence is malformed")]
    MalformedWorkerEvidence,
    #[error("recovered artifact set for {stage} is unsafe: {reason}")]
    RecoveredArtifactSet { stage: String, reason: String },
    #[error("recovered artifact digest does not match the ledger: {path}")]
    RecoveredArtifactDigest { path: String },
    #[error("author disposition does not cover each finding exactly once")]
    MalformedDisposition,
    #[error("publisher is unavailable for a pre-publish run")]
    PublisherUnavailable,
    #[error("durable publish input is missing")]
    MissingPublishInput,
    #[error("durable publish input conflicts with the verified run")]
    PublishInputConflict,
    #[error("durable publish input identifies a different request or run")]
    PublishInputIdentity,
    #[error("publisher failed: {0}")]
    Publisher(#[from] PublisherError),
}
