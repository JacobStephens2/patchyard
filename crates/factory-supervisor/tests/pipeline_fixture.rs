use std::{
    collections::BTreeMap,
    fs,
    os::unix::fs::PermissionsExt as _,
    path::{Path, PathBuf},
    process::Command,
    sync::{Arc, Mutex},
    time::Duration,
};

use factory_core::{
    state::{TriageRecorded, TriageSubmission},
    triage::{Rubric, TaskSpec},
};
use factory_supervisor::{
    artifacts::{ArtifactStore, StoredArtifact},
    child::{ChildSpawnConfig, IsolatedChildSpawner},
    config::RoutingConfig,
    contracts::AccountedUsage,
    lifecycle::{LifecycleFuture, LifecycleResult, LifecycleService},
    pipeline::{Pipeline, PipelineConfig, PipelineOutcome, RunMode},
    publisher::{PublishInput, PublishService, PublishedPullRequest, PublisherFuture},
    review::{ReviewSandboxConfig, SandboxedReviewer},
    stages::{
        ProcessAgentBackend, ProcessVerifierBackend, ProcessWorkerBackend, StageCommand,
        VerifierCommand, WorkerCommand,
    },
    store::{
        ClaimLimits, ControlKind, ControlRow, ExistingRun, KillReport, LeaseDisposition,
        PipelineStore, RequestWork, SideEffectDisposition, StoreError, WorkClaim,
    },
};
use factory_verify::ledger::{RunRecord, ValidatedRunRecord};
use serde_json::Value;
use tempfile::TempDir;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

#[derive(Clone, Debug)]
struct Event {
    event_type: String,
    payload: Value,
}

#[derive(Clone)]
struct MemoryStore {
    state: Arc<Mutex<MemoryState>>,
}

#[derive(Default)]
struct MemoryState {
    request_id: Option<Uuid>,
    task: Option<TaskSpec>,
    run: Option<RunRecord>,
    run_state: Option<String>,
    events: Vec<Event>,
    artifacts: Vec<StoredArtifact>,
    usage: Vec<(String, AccountedUsage)>,
    released: bool,
    controls: Vec<ControlRow>,
}

impl MemoryStore {
    fn new(request_id: Uuid) -> Self {
        let state = MemoryState {
            request_id: Some(request_id),
            ..MemoryState::default()
        };
        Self {
            state: Arc::new(Mutex::new(state)),
        }
    }

    fn snapshot(&self) -> MemorySnapshot {
        let state = self.state.lock().expect("memory store");
        MemorySnapshot {
            run: state.run.clone().expect("run persisted"),
            run_state: state.run_state.clone().expect("run state"),
            events: state.events.clone(),
            artifacts: state.artifacts.clone(),
            usage: state.usage.clone(),
            released: state.released,
        }
    }

    fn prepare_recovery(&self) {
        let mut state = self.state.lock().expect("memory store");
        state.run_state = Some("implementing".to_owned());
        state.released = false;
    }
}

struct MemorySnapshot {
    run: RunRecord,
    run_state: String,
    events: Vec<Event>,
    artifacts: Vec<StoredArtifact>,
    usage: Vec<(String, AccountedUsage)>,
    released: bool,
}

impl PipelineStore for MemoryStore {
    async fn claim_next(
        &self,
        _holder: &str,
        _ttl: Duration,
        _limits: ClaimLimits,
    ) -> Result<Option<WorkClaim>, StoreError> {
        Ok(None)
    }

    async fn claim_specific(
        &self,
        request_id: Uuid,
        _holder: &str,
        _ttl: Duration,
        _limits: ClaimLimits,
    ) -> Result<WorkClaim, StoreError> {
        Ok(fixture_claim(request_id))
    }

    async fn load_request(&self, request_id: Uuid) -> Result<RequestWork, StoreError> {
        Ok(RequestWork {
            request_id,
            source: "fixture".to_owned(),
            body: "ALPHABETIZE the two named salesperson selectors".to_owned(),
            trace_id: "0123456789abcdef0123456789abcdef".to_owned(),
            status: "claimed".to_owned(),
        })
    }

    async fn authoritative_task_spec(
        &self,
        _request_id: Uuid,
    ) -> Result<Option<TaskSpec>, StoreError> {
        Ok(self.state.lock().expect("memory store").task.clone())
    }

    async fn record_triage(
        &self,
        _request_id: Uuid,
        submission: &TriageSubmission,
        rubric: &Rubric,
    ) -> Result<TriageRecorded, StoreError> {
        let classification = rubric
            .classify(&submission.output.task_spec)
            .map_err(|_| StoreError::MalformedRow)?;
        self.state.lock().expect("memory store").task = Some(submission.output.task_spec.clone());
        Ok(TriageRecorded {
            classification,
            plan_id: submission.plan_id,
            inserted: true,
        })
    }

    async fn existing_run(&self, _request_id: Uuid) -> Result<Option<ExistingRun>, StoreError> {
        let state = self.state.lock().expect("memory store");
        Ok(state.run.as_ref().map(|run| ExistingRun {
            run_class: factory_verify::ledger::RunClass::Production,
            id: run.id,
            base_sha: run.base_sha.clone(),
            branch: run.branch.clone(),
            state: state
                .run_state
                .clone()
                .unwrap_or_else(|| "queued".to_owned()),
            lane: run.lane.clone(),
            skill: run.skill.clone(),
        }))
    }

    async fn append_run(&self, run: &ValidatedRunRecord) -> Result<(), StoreError> {
        let mut state = self.state.lock().expect("memory store");
        state.run = Some(run.record().clone());
        state.run_state = Some("queued".to_owned());
        state.events.push(Event {
            event_type: "run.queued".to_owned(),
            payload: Value::Null,
        });
        Ok(())
    }

    async fn transition_run(
        &self,
        _request_id: Uuid,
        _run_id: Uuid,
        event_type: &str,
        to_state: &str,
        idempotency_key: &str,
        payload: Value,
    ) -> Result<bool, StoreError> {
        let mut state = self.state.lock().expect("memory store");
        if state.events.iter().any(|event| {
            event.payload.get("idempotency_key").and_then(Value::as_str) == Some(idempotency_key)
        }) {
            return Ok(false);
        }
        state.run_state = Some(to_state.to_owned());
        let mut payload = payload;
        payload["idempotency_key"] = Value::String(idempotency_key.to_owned());
        state.events.push(Event {
            event_type: event_type.to_owned(),
            payload,
        });
        Ok(true)
    }

    async fn record_usage(
        &self,
        _run_id: Uuid,
        model_id: &str,
        usage: AccountedUsage,
    ) -> Result<(), StoreError> {
        self.state
            .lock()
            .expect("memory store")
            .usage
            .push((model_id.to_owned(), usage));
        Ok(())
    }

    async fn register_artifact(
        &self,
        _request_id: Uuid,
        _run_id: Option<Uuid>,
        _stage: &str,
        artifact: &StoredArtifact,
    ) -> Result<(), StoreError> {
        self.state
            .lock()
            .expect("memory store")
            .artifacts
            .push(artifact.clone());
        Ok(())
    }

    async fn stage_artifacts(
        &self,
        request_id: Uuid,
        run_id: Uuid,
        stage: &str,
    ) -> Result<Vec<StoredArtifact>, StoreError> {
        let prefix = format!("{request_id}/{run_id}/{stage}/");
        Ok(self
            .state
            .lock()
            .expect("memory store")
            .artifacts
            .iter()
            .filter(|artifact| artifact.relative_path.starts_with(&prefix))
            .cloned()
            .collect())
    }

    async fn begin_side_effect(
        &self,
        _request_id: Uuid,
        _run_id: Option<Uuid>,
        _key: &str,
        _effect_type: &str,
        _attempt: u8,
    ) -> Result<SideEffectDisposition, StoreError> {
        Ok(SideEffectDisposition::Start)
    }

    async fn finish_side_effect(
        &self,
        _key: &str,
        _status: &str,
        _external_ref: Option<&str>,
        _facts: Value,
    ) -> Result<(), StoreError> {
        Ok(())
    }

    async fn release_lease(&self, _request_id: Uuid, _holder: &str) -> Result<(), StoreError> {
        self.state.lock().expect("memory store").released = true;
        Ok(())
    }

    async fn finish_run(
        &self,
        _request_id: Uuid,
        _run_id: Uuid,
        state_name: &str,
        event_type: &str,
        outcome: Value,
    ) -> Result<(), StoreError> {
        let mut state = self.state.lock().expect("memory store");
        state.run_state = Some(state_name.to_owned());
        state.events.push(Event {
            event_type: event_type.to_owned(),
            payload: outcome,
        });
        Ok(())
    }

    async fn enqueue_control(
        &self,
        command: ControlKind,
        target_run_id: Option<Uuid>,
        requested_by: &str,
        reason: &str,
    ) -> Result<Uuid, StoreError> {
        let id = Uuid::new_v4();
        self.state
            .lock()
            .expect("memory store")
            .controls
            .push(ControlRow {
                id,
                command,
                target_run_id,
                requested_by: requested_by.to_owned(),
                reason: reason.to_owned(),
                status: "pending".to_owned(),
            });
        Ok(id)
    }

    async fn pending_controls(&self, _limit: i64) -> Result<Vec<ControlRow>, StoreError> {
        Ok(self.state.lock().expect("memory store").controls.clone())
    }

    async fn claim_control(&self, _id: Uuid) -> Result<bool, StoreError> {
        Ok(true)
    }

    async fn set_claiming_state(
        &self,
        _paused: bool,
        _full_stop: bool,
        _actor: &str,
    ) -> Result<(), StoreError> {
        Ok(())
    }

    async fn complete_control(
        &self,
        _id: Uuid,
        _success: bool,
        _outcome: Value,
    ) -> Result<(), StoreError> {
        Ok(())
    }

    async fn kill_run(
        &self,
        _run_id: Uuid,
        _control_id: Uuid,
        _reason: &str,
    ) -> Result<KillReport, StoreError> {
        Ok(KillReport {
            request_id: self.state.lock().expect("memory store").request_id,
            lease_release: LeaseDisposition::Released,
        })
    }

    async fn request_for_run(&self, _run_id: Uuid) -> Result<Option<Uuid>, StoreError> {
        Ok(self.state.lock().expect("memory store").request_id)
    }
}

struct Fixture {
    _temp: TempDir,
    pipeline: Pipeline<MemoryStore>,
    store: MemoryStore,
    request_id: Uuid,
    artifact_root: PathBuf,
    worker_fixture_root: PathBuf,
    worker_program: PathBuf,
    worker_cleanup_log: PathBuf,
}

impl Fixture {
    async fn build(review_harness: &str, verifier_harness: &str, reviewers: usize) -> Self {
        Self::build_mode(
            review_harness,
            verifier_harness,
            reviewers,
            RunMode::DryRun,
            None,
        )
        .await
    }

    async fn build_mode(
        review_harness: &str,
        verifier_harness: &str,
        reviewers: usize,
        mode: RunMode,
        publisher: Option<Arc<dyn PublishService>>,
    ) -> Self {
        let project = project_root();
        let temp = tempfile::tempdir().expect("fixture tempdir");
        let repository = temp.path().join("repository");
        let artifact_root = temp.path().join("artifacts");
        let scratch = temp.path().join("scratch");
        let snapshot = temp.path().join("snapshot.img");
        let worker_fixture_root = temp.path().join("worker-fixture");
        let worker_program = worker_fixture_root.join("bin/worker-stub");
        let worker_cleanup_program = temp.path().join("worker-cleanup-stub");
        let worker_cleanup_log = temp.path().join("worker-cleanup.log");
        let repository_source = project.join("fixtures/pipeline/alphabetize-repo");
        let setup_repository = repository.clone();
        let setup_artifacts = artifact_root.clone();
        let setup_scratch = scratch.clone();
        let setup_snapshot = snapshot.clone();
        let setup_worker_fixture_root = worker_fixture_root.clone();
        let setup_worker_program = worker_program.clone();
        let setup_worker_cleanup_program = worker_cleanup_program.clone();
        let setup_worker_cleanup_log = worker_cleanup_log.clone();
        tokio::task::spawn_blocking(move || {
            copy_tree(&repository_source, &setup_repository);
            fs::create_dir_all(&setup_artifacts).expect("fixture artifact directory");
            fs::set_permissions(&setup_artifacts, fs::Permissions::from_mode(0o2750))
                .expect("artifact chmod");
            fs::create_dir_all(&setup_scratch).expect("fixture scratch directory");
            fs::set_permissions(&setup_scratch, fs::Permissions::from_mode(0o700))
                .expect("scratch chmod");
            fs::create_dir(setup_scratch.join("children")).expect("fixture child staging");
            fs::set_permissions(
                setup_scratch.join("children"),
                fs::Permissions::from_mode(0o700),
            )
            .expect("child staging chmod");
            fs::write(setup_snapshot, b"fixture snapshot").expect("snapshot");
            fs::create_dir_all(setup_worker_fixture_root.join("bin"))
                .expect("worker fixture directory");
            fs::copy(
                project_root().join("fixtures/pipeline/bin/worker-stub"),
                &setup_worker_program,
            )
            .expect("worker fixture copy");
            fs::copy(
                project_root().join("fixtures/pipeline/alphabetize.patch"),
                setup_worker_fixture_root.join("alphabetize.patch"),
            )
            .expect("worker patch fixture copy");
            fs::set_permissions(setup_worker_program, fs::Permissions::from_mode(0o755))
                .expect("worker fixture chmod");
            fs::write(
                &setup_worker_cleanup_program,
                format!(
                    "#!/usr/bin/bash\nset -euo pipefail\nprintf '%s\\n' \"$1\" >> \"{}\"\n",
                    setup_worker_cleanup_log.display()
                ),
            )
            .expect("worker cleanup fixture");
            fs::set_permissions(
                setup_worker_cleanup_program,
                fs::Permissions::from_mode(0o755),
            )
            .expect("worker cleanup chmod");
            git(&setup_repository, &["init", "--quiet"]);
            git(&setup_repository, &["add", "."]);
            git(
                &setup_repository,
                &[
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@invalid.example",
                    "commit",
                    "--quiet",
                    "-m",
                    "fixture base",
                ],
            );
        })
        .await
        .expect("fixture setup task");
        let base_sha = git_output(repository.clone(), vec!["rev-parse", "HEAD"]).await;
        let routing = tokio::task::spawn_blocking({
            let project = project.clone();
            move || {
                RoutingConfig::load(
                    &project.join("policy/routing.json"),
                    &project.join("docs/bench.json"),
                    &project.join("policy/model-rates.json"),
                )
            }
        })
        .await
        .expect("routing task")
        .expect("routing");
        let rubric = Rubric::parse_markdown(
            &tokio::fs::read_to_string(project.join("policy/rubric.md"))
                .await
                .expect("rubric source"),
        )
        .expect("rubric");
        let request_id = Uuid::new_v4();
        let store = MemoryStore::new(request_id);
        let mut commands = BTreeMap::new();
        commands.insert(
            "triage".to_owned(),
            StageCommand {
                program: project.join("fixtures/pipeline/bin/triage-stub"),
                prompt: project.join("policy/triage.md"),
                timeout: Duration::from_secs(10),
                cli_version: "fixture-triage/1".to_owned(),
                credential: None,
            },
        );
        commands.insert(
            "author_disposition".to_owned(),
            StageCommand {
                program: project.join("fixtures/pipeline/bin/disposition-stub"),
                prompt: project.join("policy/disposition.md"),
                timeout: Duration::from_secs(10),
                cli_version: "fixture-disposition/1".to_owned(),
                credential: None,
            },
        );
        let agents = ProcessAgentBackend::new(commands, scratch.join("agents"));
        let worker = ProcessWorkerBackend::new(
            WorkerCommand {
                program: worker_program.clone(),
                cleanup_program: worker_cleanup_program,
                snapshot,
                timeout: Duration::from_secs(10),
            },
            scratch.join("worker"),
        );
        let verifier_program = project.join("fixtures/pipeline/bin").join(verifier_harness);
        let verifier = ProcessVerifierBackend::new(
            VerifierCommand {
                program: verifier_program.clone(),
                timeout: Duration::from_secs(10),
                tests: Vec::new(),
            },
            scratch.join("verify"),
        );
        let reviewer = SandboxedReviewer::new(ReviewSandboxConfig {
            spawner: IsolatedChildSpawner::new(ChildSpawnConfig {
                spawn_program: project
                    .join("fixtures/pipeline/bin")
                    .join(format!("child-{review_harness}")),
                cancel_program: project.join("fixtures/pipeline/bin/child-cancel-stub"),
                staging_root: scratch.join("children"),
                timeout: Duration::from_secs(10),
            }),
            prompt: project.join("policy/review.md"),
            worktree_root: scratch.join("review-worktrees"),
            live: None,
        });
        let artifacts = ArtifactStore::open(&artifact_root).expect("artifact store");
        let lifecycle = publisher.as_ref().map(|_| {
            Arc::new(RecordingLifecycle {
                store: store.clone(),
            }) as Arc<dyn LifecycleService>
        });
        let pipeline = Pipeline::new(
            store.clone(),
            PipelineConfig {
                repository,
                base_sha,
                scratch,
                holder: "fixture-supervisor".to_owned(),
                mode,
                publish_branch_suffix: "session-10-publisher-demo".to_owned(),
                reviewer_count: reviewers,
                builder_cli_version: "fixture-worker/1".to_owned(),
                constitution: project.join("AGENTS.md"),
                rubric_source: project.join("policy/rubric.md"),
                skill: project.join("policy/skills/ui-sort-dropdown.md"),
                implement_prompt: project.join("policy/implement.md"),
                verifier_binary: verifier_program,
            },
            routing,
            rubric,
            artifacts,
            agents,
            worker,
            verifier,
            reviewer,
            publisher,
            lifecycle,
        );
        Self {
            _temp: temp,
            pipeline,
            store,
            request_id,
            artifact_root,
            worker_fixture_root,
            worker_program,
            worker_cleanup_log,
        }
    }

    /// The verdict persisted by the first verify attempt, parsed.
    async fn first_verify_verdict(&self) -> Value {
        let snapshot = self.store.snapshot();
        let evidence = snapshot
            .artifacts
            .iter()
            .find(|artifact| {
                artifact.kind == "verify-evidence" && artifact.relative_path.contains("/verify-0/")
            })
            .expect("first verify evidence artifact");
        let bytes = tokio::fs::read(self.artifact_root.join(&evidence.relative_path))
            .await
            .expect("persisted verify evidence");
        serde_json::from_slice(&bytes).expect("the verdict is JSON")
    }

    /// The task packet an attempt was actually handed, as the worker saw it.
    async fn task_packet(&self, attempt: u8) -> Option<Value> {
        let bytes = tokio::fs::read(
            self.worker_fixture_root
                .join(format!("task-a{attempt}.json")),
        )
        .await
        .ok()?;
        Some(serde_json::from_slice(&bytes).expect("the packet is JSON"))
    }

    async fn run(&self) -> PipelineOutcome {
        self.pipeline
            .run_claim(fixture_claim(self.request_id), &CancellationToken::new())
            .await
            .expect("fixture pipeline")
    }

    async fn run_recovered(&self) -> PipelineOutcome {
        let mut claim = fixture_claim(self.request_id);
        claim.recovered = true;
        self.pipeline
            .run_claim(claim, &CancellationToken::new())
            .await
            .expect("recovered fixture pipeline")
    }
}

#[derive(Clone, Default)]
struct RecordingPublisher {
    inputs: Arc<Mutex<Vec<PublishInput>>>,
}

impl PublishService for RecordingPublisher {
    fn publish<'a>(
        &'a self,
        input: &'a PublishInput,
        _patch_path: &'a Path,
        _cancellation: &'a CancellationToken,
    ) -> PublisherFuture<'a> {
        Box::pin(async move {
            self.inputs
                .lock()
                .expect("publisher inputs")
                .push(input.clone());
            Ok(PublishedPullRequest {
                number: 42,
                url: "https://github.invalid/pull/42".to_owned(),
                branch: input.branch.clone(),
                head_sha: "d".repeat(40),
                author_login: "patchyard[bot]".to_owned(),
            })
        })
    }
}

#[derive(Clone)]
struct RecordingLifecycle {
    store: MemoryStore,
}

impl LifecycleService for RecordingLifecycle {
    fn complete<'a>(
        &'a self,
        input: &'a PublishInput,
        _cancellation: &'a CancellationToken,
    ) -> LifecycleFuture<'a> {
        Box::pin(async move {
            let pull_request = PublishedPullRequest {
                number: 42,
                url: "https://github.invalid/pull/42".to_owned(),
                branch: input.branch.clone(),
                head_sha: "d".repeat(40),
                author_login: "patchyard[bot]".to_owned(),
            };
            let mut state = self.store.state.lock().expect("memory store");
            state.run_state = Some("ready_for_review".to_owned());
            state.events.push(Event {
                event_type: "run.ready_for_review".to_owned(),
                payload: serde_json::json!({"pull_request": pull_request}),
            });
            Ok(LifecycleResult {
                pull_request,
                evidence: Vec::new(),
            })
        })
    }
}

#[tokio::test]
async fn alphabetize_dry_run_asserts_lane_targets_patch_barrier_and_stop_boundary() {
    let fixture = Fixture::build("review-stub", "verifier-stub", 2).await;
    let outcome = fixture.run().await;
    assert!(
        matches!(
            &outcome,
            PipelineOutcome::DryRunComplete { attempts: 1, .. }
        ),
        "unexpected outcome: {outcome:?}"
    );
    let snapshot = fixture.store.snapshot();
    assert_eq!(snapshot.run.lane, "A");
    assert_eq!(snapshot.run.skill, "ui.sort-dropdown");
    assert_eq!(snapshot.run_state, "dry_run_complete");
    assert!(snapshot.released);
    assert_eq!(
        snapshot.run.provenance.model_id,
        "GPT-5.6 Sol|xhigh|Codex|OpenAI"
    );
    assert_eq!(
        snapshot.run.provenance.routing_config_version,
        "2026-08-23.1"
    );
    for digest in [
        &snapshot.run.provenance.model_id_hash,
        &snapshot.run.provenance.cli_version_hash,
        &snapshot.run.provenance.constitution_hash,
        &snapshot.run.provenance.rubric_hash,
        &snapshot.run.provenance.skill_hash,
        &snapshot.run.provenance.prompt_template_hash,
        &snapshot.run.provenance.verifier_binary_hash,
        &snapshot.run.provenance.base_tree_hash,
    ] {
        assert_eq!(digest.len(), 64, "complete ledger-accepted provenance");
    }
    let worker_terminated = event_position(&snapshot.events, "worker.terminated");
    let verify_started = event_position(&snapshot.events, "verify.started");
    assert!(worker_terminated < verify_started);
    assert_eq!(
        snapshot
            .events
            .iter()
            .filter(|event| event.event_type == "review.submitted")
            .count(),
        2,
        "two reviewers crossed the supervisor-held submission barrier"
    );
    for event in snapshot
        .events
        .iter()
        .filter(|event| event.event_type == "review.submitted")
    {
        assert_eq!(event.payload["sibling_unreachable"], true);
        assert_eq!(event.payload["shared_scratch_unreachable"], true);
    }
    let final_event = snapshot.events.last().expect("terminal event");
    assert_eq!(final_event.event_type, "run.dry_run_complete");
    assert_eq!(final_event.payload["dry_run"], true);
    assert_eq!(final_event.payload["publish_invoked"], false);
    assert_eq!(
        final_event.payload["accept"]["allowed_paths"],
        serde_json::json!(["mfieldbook/common_functions.php", "mfieldbook/leads/assign.php"])
    );
    assert_eq!(final_event.payload["accept"]["files"], 2);
    let transcript_count = snapshot
        .artifacts
        .iter()
        .filter(|artifact| artifact.kind == "agent-transcript")
        .count();
    assert_eq!(
        transcript_count, 4,
        "triage, worker, and two full review transcripts"
    );
    let patch = snapshot
        .artifacts
        .iter()
        .find(|artifact| artifact.kind == "patch")
        .expect("patch artifact");
    let patch_bytes = tokio::fs::read(fixture.artifact_root.join(&patch.relative_path))
        .await
        .expect("persisted patch");
    let patch_text = String::from_utf8(patch_bytes).expect("patch utf8");
    assert!(patch_text.contains("mfieldbook/common_functions.php"));
    assert!(patch_text.contains("mfieldbook/leads/assign.php"));
    assert_eq!(
        patch_text.matches("+        'zoe' => 'Zoe Adams'").count(),
        1
    );
    let (_, implement_usage) = snapshot
        .usage
        .iter()
        .find(|(model, _)| model.starts_with("GPT-5.6 Sol|"))
        .expect("implement usage reaches the durable rollup");
    assert_eq!(implement_usage.input_tokens, 29);
    assert_eq!(implement_usage.output_tokens, 31);
    assert_eq!(implement_usage.cost_microusd, 736);
}

#[tokio::test]
async fn verified_pre_publish_contract_opens_draft_before_ready_for_review() {
    let publisher = RecordingPublisher::default();
    let fixture = Fixture::build_mode(
        "review-stub",
        "verifier-stub",
        1,
        RunMode::PrePublish,
        Some(Arc::new(publisher.clone())),
    )
    .await;
    let outcome = fixture.run().await;
    assert!(matches!(
        outcome,
        PipelineOutcome::PublishedDraft {
            attempts: 1,
            ref pull_request,
            ..
        } if pull_request.author_login == "patchyard[bot]"
    ));
    let snapshot = fixture.store.snapshot();
    assert_eq!(snapshot.run_state, "ready_for_review");
    assert_eq!(
        snapshot
            .artifacts
            .iter()
            .filter(|artifact| artifact.kind == "publish-input")
            .count(),
        1
    );
    assert!(
        event_position(&snapshot.events, "run.verified")
            < event_position(&snapshot.events, "run.ready_for_review")
    );
    let inputs = publisher.inputs.lock().expect("publisher inputs");
    assert_eq!(inputs.len(), 1);
    assert_eq!(inputs[0].branch, snapshot.run.branch);
}

#[tokio::test]
async fn review_disposition_escalation_reaches_typed_third_family_stub() {
    let fixture = Fixture::build("review-escalate-stub", "verifier-stub", 1).await;
    let outcome = fixture.run().await;
    assert!(matches!(
        outcome,
        PipelineOutcome::Escalated { ref reason, .. }
            if reason == "review_dispute_requires_third_family"
    ));
    let snapshot = fixture.store.snapshot();
    assert!(
        snapshot
            .events
            .iter()
            .any(|event| event.event_type == "review.finding_disposition")
    );
    let dispute = snapshot
        .events
        .iter()
        .find(|event| event.event_type == "review.dispute_escalated")
        .expect("dispute escalation");
    assert_eq!(dispute.payload["stubbed"], true);
    assert_eq!(dispute.payload["arbiter"]["seat"]["model"], "Grok 4.5");
    assert!(
        !snapshot
            .events
            .iter()
            .any(|event| event.event_type == "verify.started")
    );
}

#[tokio::test]
async fn one_repair_loop_exhaustion_escalates_after_two_verifier_attempts() {
    let fixture = Fixture::build("review-stub", "verifier-fail-stub", 1).await;
    let outcome = fixture.run().await;
    assert!(matches!(
        outcome,
        PipelineOutcome::Escalated { ref reason, .. } if reason == "repair_exhausted"
    ));
    let snapshot = fixture.store.snapshot();
    assert_eq!(
        snapshot
            .events
            .iter()
            .filter(|event| event.event_type == "verify.started")
            .count(),
        2
    );
    assert_eq!(
        snapshot.events.last().expect("terminal").event_type,
        "repair.exhausted"
    );
    assert_eq!(
        snapshot.events.last().expect("terminal").payload["attempts"],
        2
    );
    assert_eq!(
        snapshot.events.last().expect("terminal").payload["reason_code"],
        "deterministic_verifier_failed",
        "an exhausted run says it ran out of attempts on a repairable failure"
    );
    assert!(snapshot.released);
}

/// The repair attempt is only worth its live implement run if the model is told
/// what failed. On request bb995b19 it was told nothing and returned the
/// byte-identical patch.
#[tokio::test]
async fn the_repair_attempt_is_handed_the_assertions_that_failed() {
    let fixture = Fixture::build("review-stub", "verifier-fail-stub", 1).await;
    assert!(matches!(
        fixture.run().await,
        PipelineOutcome::Escalated { .. }
    ));

    let repair = fixture.task_packet(1).await.expect("a repair attempt ran");
    let failure = &repair["verify_failure"];
    assert_eq!(failure["reason_code"], "deterministic_verifier_failed");
    assert_eq!(failure["gate"], "fixture-repair-exhaustion");
    assert_eq!(failure["attempt"], 0);
    assert_eq!(
        failure["failures"][0]["assertion"], "fixture_always_rejects",
        "the repair attempt is told which assertion rejected its patch"
    );
    assert_eq!(
        failure["failures"][0]["observed"],
        "this fixture accepts none"
    );
    assert_eq!(failure["failures_truncated"], false);
    assert!(
        failure["evidence_artifact"].is_string(),
        "the full verdict remains reachable as an artifact"
    );
}

#[tokio::test]
async fn a_conforming_rejection_records_the_assertion_that_failed() {
    let fixture = Fixture::build("review-stub", "verifier-fail-stub", 1).await;
    assert!(matches!(
        fixture.run().await,
        PipelineOutcome::Escalated { .. }
    ));

    let verdict = fixture.first_verify_verdict().await;
    assert_eq!(verdict["status"], "failed");
    assert_eq!(
        verdict["failures"][0]["assertion"], "fixture_always_rejects",
        "a rejection names the assertion that failed"
    );
    assert!(
        verdict.get("synthesized").is_none(),
        "the verifier wrote its own verdict, so nothing is synthesized"
    );
}

/// Request bb995b19's rejection preserved nothing but `exit_code: 1`. A verifier
/// that breaches the contract this way still has its account preserved, and the
/// breach itself is named rather than passed off as an ordinary failure.
#[tokio::test]
async fn a_reason_less_rejection_preserves_what_the_verifier_emitted() {
    let fixture = Fixture::build("review-stub", "verifier-silent-fail-stub", 1).await;
    assert!(matches!(
        fixture.run().await,
        PipelineOutcome::Escalated { .. }
    ));

    let verdict = fixture.first_verify_verdict().await;
    assert_eq!(verdict["status"], "failed");
    assert_eq!(verdict["exit_code"], 1);
    assert_eq!(verdict["synthesized"], true);
    assert!(verdict["reason_unavailable"].is_string());
    assert!(
        verdict["captured"]["stderr"]
            .as_str()
            .expect("captured stderr")
            .contains("no match for mfieldbook/leads/assign.php"),
        "the only account of the rejection is carried, not discarded"
    );
}

/// The second live implement run request bb995b19 spent. A failure the model
/// cannot see is a failure it cannot fix, so the run escalates on one attempt.
#[tokio::test]
async fn a_reason_less_rejection_costs_one_implement_run_rather_than_two() {
    let fixture = Fixture::build("review-stub", "verifier-silent-fail-stub", 1).await;
    let outcome = fixture.run().await;
    assert!(
        matches!(
            &outcome,
            PipelineOutcome::Escalated { reason, .. } if reason == "verify_not_repairable"
        ),
        "unexpected outcome: {outcome:?}"
    );

    let snapshot = fixture.store.snapshot();
    assert_eq!(
        snapshot
            .events
            .iter()
            .filter(|event| event.event_type == "verify.started")
            .count(),
        1
    );
    assert!(
        !snapshot
            .events
            .iter()
            .any(|event| event.event_type == "repair.queued"),
        "no repair is queued against a failure that states nothing"
    );
    assert!(
        fixture.task_packet(1).await.is_none(),
        "no second worker run"
    );
    let terminal = snapshot.events.last().expect("terminal");
    assert_eq!(terminal.event_type, "repair.not_attempted");
    assert_eq!(terminal.payload["attempts"], 1);
    assert_eq!(terminal.payload["reason_code"], "verifier_reason_missing");
    assert!(snapshot.released);
}

/// A verifier that rejected the task's shape rejected something no better patch
/// can answer, so the escalation says it was never repairable rather than that
/// it ran out of attempts.
#[tokio::test]
async fn a_task_shape_rejection_escalates_without_a_repair_attempt() {
    let fixture = Fixture::build("review-stub", "verifier-task-reject-stub", 1).await;
    let outcome = fixture.run().await;
    assert!(
        matches!(
            &outcome,
            PipelineOutcome::Escalated { reason, .. } if reason == "verify_not_repairable"
        ),
        "unexpected outcome: {outcome:?}"
    );

    let snapshot = fixture.store.snapshot();
    assert!(
        fixture.task_packet(1).await.is_none(),
        "no second worker run"
    );
    let terminal = snapshot.events.last().expect("terminal");
    assert_eq!(terminal.event_type, "repair.not_attempted");
    assert_eq!(terminal.payload["reason_code"], "verifier_rejected_task");
    assert_eq!(
        terminal.payload["gate"], "lane-a-eligibility",
        "the escalation names the gate that rejected the task"
    );
    assert_eq!(
        fixture.first_verify_verdict().await["rejects"],
        "task",
        "the verdict that decided it stays on the run"
    );
    assert!(snapshot.released);
}

#[tokio::test]
async fn restart_recovers_durable_worker_artifacts_without_reinvocation() {
    let fixture = Fixture::build("review-stub", "verifier-stub", 1).await;
    assert!(matches!(
        fixture.run().await,
        PipelineOutcome::DryRunComplete { .. }
    ));
    let original = fixture.store.snapshot();
    assert_eq!(
        original
            .artifacts
            .iter()
            .filter(|artifact| artifact.kind == "patch")
            .count(),
        1
    );

    fixture.store.prepare_recovery();
    tokio::fs::remove_file(&fixture.worker_program)
        .await
        .expect("disable worker executable");
    assert!(matches!(
        fixture.run_recovered().await,
        PipelineOutcome::DryRunComplete { .. }
    ));
    let recovered = fixture.store.snapshot();
    assert!(recovered.released);
    assert_eq!(
        recovered
            .artifacts
            .iter()
            .filter(|artifact| artifact.kind == "patch")
            .count(),
        1,
        "the missing worker executable proves replay used the original artifact"
    );
}

#[tokio::test]
async fn kill_cleanup_awaits_both_permitted_worker_attempts() {
    let fixture = Fixture::build("review-stub", "verifier-stub", 1).await;
    let run_id = Uuid::new_v4();
    fixture
        .pipeline
        .kill_cleanup(run_id)
        .await
        .expect("checked kill cleanup");
    let cleanup_log = tokio::fs::read_to_string(&fixture.worker_cleanup_log)
        .await
        .expect("cleanup log");
    assert_eq!(
        cleanup_log.lines().collect::<Vec<_>>(),
        vec![
            format!("{}-a0", run_id.simple()),
            format!("{}-a1", run_id.simple()),
        ]
    );
}

fn fixture_claim(request_id: Uuid) -> WorkClaim {
    WorkClaim {
        request_id,
        run_class: factory_verify::ledger::RunClass::Production,
        source: "fixture".to_owned(),
        body: "ALPHABETIZE the two named salesperson selectors".to_owned(),
        trace_id: "0123456789abcdef0123456789abcdef".to_owned(),
        fencing_token: 1,
        recovered: false,
    }
}

fn event_position(events: &[Event], event_type: &str) -> usize {
    events
        .iter()
        .position(|event| event.event_type == event_type)
        .unwrap_or_else(|| panic!("missing event {event_type}"))
}

fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .expect("project root")
}

fn copy_tree(source: &Path, destination: &Path) {
    fs::create_dir_all(destination).expect("copy destination");
    for entry in fs::read_dir(source).expect("source directory") {
        let entry = entry.expect("source entry");
        let target = destination.join(entry.file_name());
        if entry.file_type().expect("source type").is_dir() {
            copy_tree(&entry.path(), &target);
        } else {
            fs::copy(entry.path(), target).expect("copy fixture file");
        }
    }
}

fn git(repository: &Path, arguments: &[&str]) {
    let status = Command::new("/usr/bin/git")
        .arg("-C")
        .arg(repository)
        .args(arguments)
        .status()
        .expect("git command");
    assert!(status.success(), "git {:?}", arguments);
}

async fn git_output(repository: PathBuf, arguments: Vec<&'static str>) -> String {
    tokio::task::spawn_blocking(move || {
        let output = Command::new("/usr/bin/git")
            .arg("-C")
            .arg(repository)
            .args(arguments)
            .output()
            .expect("git output");
        assert!(output.status.success());
        String::from_utf8(output.stdout)
            .expect("git utf8")
            .trim()
            .to_owned()
    })
    .await
    .expect("git task")
}
