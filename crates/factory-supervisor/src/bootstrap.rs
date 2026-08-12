//! Environment-to-runtime wiring shared by both executables.

use std::{
    collections::BTreeMap,
    env,
    ffi::OsString,
    path::{Path, PathBuf},
    sync::Arc,
    time::Duration,
};

use factory_core::triage::Rubric;
use thiserror::Error;

use crate::{
    artifacts::ArtifactStore,
    child::{ChildSpawnConfig, IsolatedChildSpawner},
    config::{ProviderEgressConfig, RoutingConfig},
    daemon::DaemonConfig,
    evidence::EvidenceCapture,
    lifecycle::{EvidenceLifecycle, LifecycleConfig, LifecycleService},
    pipeline::{Pipeline, PipelineConfig, RunMode},
    preview::{ProcessPreview, ProcessPreviewConfig},
    proposer::{
        ImprovementProposer, ImprovementProposerConfig, IsolatedProposer, PolicyPublisher,
        PolicyPublisherConfig, ProposerRunStore,
    },
    publisher::{
        GhGitHub, GhGitHubConfig, PublishService, Publisher, PublisherConfig, RepositoryScope,
    },
    reconcile::{DeployedVersionConfig, Reconciler},
    review::{LiveReviewSeat, ReviewSandboxConfig, SandboxedReviewer},
    secret_scan::ProcessSecretScanner,
    stages::{
        CredentialCommand, ProcessAgentBackend, ProcessVerifierBackend, ProcessWorkerBackend,
        StageCommand, VerifierCommand, WorkerCommand,
    },
    store::{DailyLimits, PgPipelineStore},
};

pub struct RuntimeComponents {
    pub store: PgPipelineStore,
    pub pipeline: Pipeline<PgPipelineStore>,
    pub reconciler: Reconciler<PgPipelineStore>,
    pub proposer: Arc<ImprovementProposer>,
    pub daemon: DaemonConfig,
}

pub struct ReconcileComponents {
    pub store: PgPipelineStore,
    pub reconciler: Reconciler<PgPipelineStore>,
}

type PublicationComponents = (
    PathBuf,
    Option<Arc<dyn PublishService>>,
    Option<Arc<dyn LifecycleService>>,
);

impl ReconcileComponents {
    pub async fn close(self) {
        self.store.close().await;
    }
}

impl RuntimeComponents {
    /// Explicitly close the SQLx pool. Pool Drop is best effort only.
    pub async fn close(self) {
        self.store.close().await;
    }
}

pub async fn from_environment(database_url: String) -> Result<RuntimeComponents, BootstrapError> {
    let root = path_env("FACTORY_INSTALL_ROOT", "/opt/patchyard");
    let base_sha = required("FACTORY_BASE_SHA")?;
    let scratch = path_env("FACTORY_SCRATCH_ROOT", "/var/lib/patchyard/supervisor");
    let artifact_root = path_env("FACTORY_ARTIFACT_ROOT", "/var/lib/patchyard/artifacts");
    let holder = env::var("FACTORY_HOLDER").unwrap_or_else(|_| "factory-supervisor".to_owned());
    let mode = match required_or("FACTORY_RUN_MODE", "dry_run").as_str() {
        "dry_run" => RunMode::DryRun,
        "pre_publish" => RunMode::PrePublish,
        _ => return Err(BootstrapError::InvalidEnvironment("FACTORY_RUN_MODE")),
    };
    let publish_branch_suffix = required_or("FACTORY_PUBLISH_BRANCH_SUFFIX", "change");
    if publish_branch_suffix.is_empty()
        || publish_branch_suffix.len() > 64
        || !publish_branch_suffix
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
    {
        return Err(BootstrapError::InvalidEnvironment(
            "FACTORY_PUBLISH_BRANCH_SUFFIX",
        ));
    }

    let routing_path = root.join("policy/routing.json");
    let bench_path = root.join("docs/bench.json");
    let rubric_path = root.join("policy/rubric.md");
    let routing = blocking({
        let routing_path = routing_path.clone();
        let bench_path = bench_path.clone();
        move || RoutingConfig::load(&routing_path, &bench_path)
    })
    .await??;
    let provider_egress = if routing.live_provider_execution {
        let provider_egress_path = root.join("policy/provider-egress.json");
        let provider_egress =
            blocking(move || ProviderEgressConfig::load(&provider_egress_path)).await??;
        // Every live seat fails closed at startup unless its provider is
        // credential_qualified (A113); a routing edit cannot outrun policy.
        for rule in [
            routing.resolve("triage")?,
            routing.resolve("author_disposition")?,
            routing.resolve("implementation_review")?,
        ] {
            require_qualified_seat(rule, &provider_egress)?;
        }
        Some(provider_egress)
    } else {
        None
    };
    let rubric_source = tokio::fs::read_to_string(&rubric_path).await?;
    let rubric = Rubric::parse_markdown(&rubric_source)?;
    ensure_private_roots(&scratch, &artifact_root).await?;
    let artifacts = blocking({
        let artifact_root = artifact_root.clone();
        move || ArtifactStore::open(artifact_root)
    })
    .await??;

    let seat_credential = if routing.live_provider_execution {
        Some(CredentialCommand {
            program: PathBuf::from("/usr/local/libexec/patchyard-request-seat-bearer"),
            arguments: Vec::new(),
            timeout: duration_env("FACTORY_SEAT_CREDENTIAL_TIMEOUT_SECONDS", 45)?,
        })
    } else {
        None
    };
    let mut commands = BTreeMap::new();
    commands.insert(
        "triage".to_owned(),
        StageCommand {
            program: path_env(
                "FACTORY_TRIAGE_HARNESS",
                "/usr/local/libexec/patchyard-triage-stub",
            ),
            prompt: root.join("policy/triage.md"),
            timeout: duration_env("FACTORY_TRIAGE_TIMEOUT_SECONDS", 120)?,
            cli_version: required_or("FACTORY_TRIAGE_CLI_VERSION", "fixture-stub/1"),
            credential: seat_credential.clone(),
        },
    );
    commands.insert(
        "author_disposition".to_owned(),
        StageCommand {
            program: path_env(
                "FACTORY_DISPOSITION_HARNESS",
                "/usr/local/libexec/patchyard-disposition-stub",
            ),
            prompt: root.join("policy/disposition.md"),
            timeout: duration_env("FACTORY_DISPOSITION_TIMEOUT_SECONDS", 180)?,
            cli_version: required_or("FACTORY_DISPOSITION_CLI_VERSION", "fixture-stub/1"),
            credential: seat_credential.clone(),
        },
    );
    let agent_scratch = if routing.live_provider_execution {
        path_env("FACTORY_SEAT_SCRATCH_ROOT", "/run/patchyard-seats")
    } else {
        scratch.join("agents")
    };
    let agents = ProcessAgentBackend::new(commands, agent_scratch.clone());
    let worker = ProcessWorkerBackend::new(
        WorkerCommand {
            program: path_env(
                "FACTORY_WORKER_PROGRAM",
                "/usr/local/sbin/patchyard-invoke-worker",
            ),
            cleanup_program: path_env(
                "FACTORY_WORKER_CLEANUP",
                "/usr/local/sbin/patchyard-cleanup-worker",
            ),
            snapshot: required_path("FACTORY_SNAPSHOT")?,
            timeout: duration_env("FACTORY_WORKER_TIMEOUT_SECONDS", 1800)?,
        },
        scratch.join("worker-results"),
    );
    let verifier_binary = path_env(
        "FACTORY_VERIFIER_PROGRAM",
        "/usr/local/sbin/patchyard-run-verifier",
    );
    let verifier = ProcessVerifierBackend::new(
        VerifierCommand {
            program: verifier_binary.clone(),
            timeout: duration_env("FACTORY_VERIFY_TIMEOUT_SECONDS", 1800)?,
            tests: split_env("FACTORY_VERIFY_TESTS"),
        },
        scratch.join("verify"),
    );
    let child_spawner = IsolatedChildSpawner::new(ChildSpawnConfig {
        spawn_program: path_env(
            "FACTORY_CHILD_SPAWN_PROGRAM",
            "/usr/local/libexec/patchyard-spawn-child",
        ),
        cancel_program: path_env(
            "FACTORY_CHILD_CANCEL_PROGRAM",
            "/usr/local/libexec/patchyard-cancel-child",
        ),
        staging_root: path_env("FACTORY_CHILD_STAGING_ROOT", "/run/patchyard-children"),
        timeout: duration_env("FACTORY_CHILD_TIMEOUT_SECONDS", 300)?,
    });
    child_spawner.recover_orphans().await?;
    let reviewer_live = match &provider_egress {
        Some(egress) => {
            let provider = &routing.resolve("implementation_review")?.seat.provider;
            let entry = egress
                .by_display_name(provider)
                .expect("qualified seat gate ran before reviewer wiring");
            Some(LiveReviewSeat {
                credential: seat_credential
                    .clone()
                    .expect("live execution carries a seat credential"),
                mint_root: agent_scratch.clone(),
                egress_host: entry
                    .hostnames
                    .first()
                    .cloned()
                    .expect("provider-egress validation requires a hostname"),
            })
        }
        None => None,
    };
    let reviewer = SandboxedReviewer::new(ReviewSandboxConfig {
        spawner: child_spawner.clone(),
        prompt: root.join("policy/review.md"),
        worktree_root: scratch.join("review-worktrees"),
        live: reviewer_live,
    });
    let store = PgPipelineStore::connect(&database_url).await?;
    let reconciler = Reconciler::new(
        store.clone(),
        github_from_environment(scratch.join("github-private"))?,
        repository_scope(),
        deployed_version_config()?,
    )?;
    let (repository, publisher, lifecycle): PublicationComponents = match mode {
        RunMode::DryRun => (required_path("FACTORY_TARGET_REPOSITORY")?, None, None),
        RunMode::PrePublish => {
            let github = github_from_environment(scratch.join("github-private"))?;
            let publisher = Publisher::new(
                store.clone(),
                github.clone(),
                PublisherConfig {
                    repository: repository_scope(),
                    base_branch: required_or("FACTORY_GITHUB_BASE_BRANCH", "master"),
                    worktree_root: path_env(
                        "FACTORY_PUBLISHER_WORKTREE_ROOT",
                        "/var/lib/patchyard/worktrees",
                    ),
                    git_program: path_env("FACTORY_GIT_PROGRAM", "/bin/git"),
                    git_askpass: path_env(
                        "FACTORY_GIT_ASKPASS",
                        "/usr/local/libexec/patchyard-git-askpass",
                    ),
                    holder: holder.clone(),
                    max_open_prs: 2,
                    github_freshness: duration_env("FACTORY_GITHUB_FRESHNESS_SECONDS", 30)?,
                    lease_ttl: duration_env("FACTORY_PUBLISHER_LEASE_SECONDS", 3_600)?,
                    fault_after: None,
                    #[cfg(test)]
                    test_remote: None,
                },
            )?;
            publisher
                .prepare_base(&base_sha, &tokio_util::sync::CancellationToken::new())
                .await?;
            let repository = publisher.repository_path();
            let preview = Arc::new(ProcessPreview::new(ProcessPreviewConfig {
                ssh_program: path_env("FACTORY_PREVIEW_SSH_PROGRAM", "/bin/ssh"),
                ssh_config: path_env(
                    "FACTORY_PREVIEW_SSH_CONFIG",
                    "/etc/patchyard/preview-ssh.conf",
                ),
                ssh_host: required_or("FACTORY_PREVIEW_SSH_HOST", "patchyard-preview"),
                home: path_env("FACTORY_PREVIEW_SSH_HOME", "/var/lib/patchyard-manager"),
                owner: required_or("FACTORY_PREVIEW_OWNER", "factory-supervisor"),
                lease_ttl: duration_env("FACTORY_PREVIEW_LEASE_SECONDS", 1_800)?,
                capability_ttl: duration_env("FACTORY_PREVIEW_CAPABILITY_SECONDS", 300)?,
                command_timeout: duration_env("FACTORY_PREVIEW_COMMAND_TIMEOUT_SECONDS", 1_300)?,
            })?);
            let secret_scan = Arc::new(ProcessSecretScanner::new(
                path_env(
                    "FACTORY_LOG_SECRET_SCAN_PROGRAM",
                    "/usr/local/libexec/patchyard-log-secret-scan",
                ),
                scratch.join("evidence-log-scan"),
                duration_env("FACTORY_LOG_SECRET_SCAN_TIMEOUT_SECONDS", 60)?,
            )?);
            let selectors = {
                let configured = required_or("FACTORY_EVIDENCE_SELECTORS", "#sales_person_id");
                configured
                    .split(',')
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .map(str::to_owned)
                    .collect()
            };
            let lifecycle = EvidenceLifecycle::new(
                store.clone(),
                github,
                preview,
                secret_scan,
                EvidenceCapture::new(child_spawner.clone(), artifacts.clone()),
                artifacts.clone(),
                LifecycleConfig {
                    repository: repository_scope(),
                    ci_wait_timeout: duration_env("FACTORY_CI_WAIT_TIMEOUT_SECONDS", 1_800)?,
                    ci_poll_interval: duration_env("FACTORY_CI_POLL_SECONDS", 10)?,
                    preview_path: required_or(
                        "FACTORY_EVIDENCE_PREVIEW_PATH",
                        "/mfieldbook/leads/assign?rqst_id=96429",
                    ),
                    selectors,
                },
            )?;
            (
                repository,
                Some(Arc::new(publisher)),
                Some(Arc::new(lifecycle)),
            )
        }
    };
    let proposer_scheduling_enabled = bool_env("FACTORY_PROPOSER_SCHEDULING_ENABLED", false)?;
    let proposer_routing = routing.clone();
    let proposer_github = github_from_environment(scratch.join("proposer-github-private"))?;
    let proposer_store = ProposerRunStore::new(store.pool().clone());
    let policy_publisher = Arc::new(PolicyPublisher::new(
        proposer_store.clone(),
        proposer_github,
        PolicyPublisherConfig {
            installed_repository: root.clone(),
            scratch: scratch.join("policy-publisher"),
            git_program: path_env("FACTORY_GIT_PROGRAM", "/bin/git"),
            git_askpass: path_env(
                "FACTORY_GIT_ASKPASS",
                "/usr/local/libexec/patchyard-git-askpass",
            ),
            repository: RepositoryScope {
                owner: required_or(
                    "FACTORY_PROPOSER_GITHUB_OWNER",
                    "example-org",
                ),
                name: required_or("FACTORY_PROPOSER_GITHUB_REPOSITORY", "factory"),
            },
            base_branch: required_or("FACTORY_PROPOSER_BASE_BRANCH", "master"),
            holder: format!("{holder}:policy"),
            lease_ttl: duration_env("FACTORY_PROPOSER_PUBLISHER_LEASE_SECONDS", 3_600)?,
            github_freshness: duration_env("FACTORY_GITHUB_FRESHNESS_SECONDS", 30)?,
            test_remote: None,
        },
    )?);
    let proposer = Arc::new(ImprovementProposer::new(
        proposer_store,
        artifacts.clone(),
        Arc::new(IsolatedProposer::new(child_spawner.clone(), false)),
        Arc::new(SandboxedReviewer::new(ReviewSandboxConfig {
            spawner: child_spawner.clone(),
            prompt: root.join("policy/proposer-review.md"),
            worktree_root: scratch.join("proposer-review-worktrees"),
            live: None,
        })),
        policy_publisher,
        proposer_routing,
        ImprovementProposerConfig {
            repository: root.clone(),
            ideas_path: path_env(
                "FACTORY_PROPOSER_IDEAS_PATH",
                "/var/lib/patchyard/proposer-inbox/docs/ideas.md",
            ),
            scratch: scratch.join("proposer"),
            review_worktree_root: scratch.join("proposer-review-worktrees"),
            review_repository: scratch.join("policy-publisher/factory-policy.git"),
            base_sha: required("FACTORY_PROPOSER_BASE_SHA")?,
        },
    )?);
    let config = PipelineConfig {
        repository,
        base_sha,
        scratch,
        holder: holder.clone(),
        mode,
        publish_branch_suffix,
        reviewer_count: usize_env("FACTORY_REVIEWER_COUNT", 1)?,
        builder_cli_version: required_or("FACTORY_BUILDER_CLI_VERSION", "fixture-worker/1"),
        constitution: root.join("AGENTS.md"),
        rubric_source: rubric_path,
        skill: root.join("policy/skills/ui-sort-dropdown.md"),
        implement_prompt: root.join("policy/implement.md"),
        verifier_binary,
    };
    let pipeline = Pipeline::new(
        store.clone(),
        config,
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
    let daemon = DaemonConfig {
        database_url,
        holder,
        sweep_interval: duration_env("FACTORY_SWEEP_SECONDS", 30)?,
        lease_ttl: duration_env("FACTORY_LEASE_TTL_SECONDS", 3600)?,
        limits: DailyLimits {
            per_submitter: u32_env("FACTORY_DAILY_PER_SUBMITTER", 5)?,
            global: u32_env("FACTORY_DAILY_GLOBAL", 25)?,
        }
        .validate()?,
        max_active: usize_env("FACTORY_MAX_ACTIVE", 2)?,
        reconcile_abandoned_after: duration_env("FACTORY_RECONCILE_ABANDONED_SECONDS", 300)?,
        reconcile_sweep_limit: usize_env("FACTORY_RECONCILE_SWEEP_LIMIT", 10)?,
        proposer_scheduling_enabled,
        proposer_interval: duration_env("FACTORY_PROPOSER_INTERVAL_SECONDS", 86_400)?,
    };
    Ok(RuntimeComponents {
        store,
        pipeline,
        reconciler,
        proposer,
        daemon,
    })
}

pub async fn reconciler_from_environment(
    database_url: String,
) -> Result<ReconcileComponents, BootstrapError> {
    let scratch = path_env("FACTORY_SCRATCH_ROOT", "/var/lib/patchyard/supervisor");
    let store = PgPipelineStore::connect(&database_url).await?;
    let reconciler = Reconciler::new(
        store.clone(),
        github_from_environment(scratch.join("github-private"))?,
        repository_scope(),
        deployed_version_config()?,
    )?;
    Ok(ReconcileComponents { store, reconciler })
}

fn deployed_version_config() -> Result<DeployedVersionConfig, BootstrapError> {
    Ok(DeployedVersionConfig {
        program: required_path("FACTORY_DEPLOYED_VERSION_PROGRAM")?,
        arguments: os_args_json("FACTORY_DEPLOYED_VERSION_ARGUMENTS_JSON")?,
        environment: [
            "GH_PATCHYARD_APP_ID",
            "GH_PATCHYARD_APP_INSTALLATION_ID",
            "GH_PATCHYARD_APP_PRIVATE_KEY_FILE",
        ]
        .into_iter()
        .map(|name| Ok((OsString::from(name), OsString::from(required(name)?))))
        .collect::<Result<Vec<_>, BootstrapError>>()?,
        timeout: duration_env("FACTORY_DEPLOYED_VERSION_TIMEOUT_SECONDS", 30)?,
        output_limit: usize_env("FACTORY_DEPLOYED_VERSION_OUTPUT_BYTES", 64 * 1024)?,
    })
}

fn github_from_environment(scratch: PathBuf) -> Result<Arc<GhGitHub>, BootstrapError> {
    Ok(Arc::new(GhGitHub::new(GhGitHubConfig {
        gh_program: path_env("FACTORY_GH_PROGRAM", "/bin/gh"),
        xdg_state_home: path_env(
            "XDG_STATE_HOME",
            "/var/lib/patchyard/supervisor/xdg-state",
        ),
        gh_config_dir: path_env("GH_CONFIG_DIR", "/var/lib/patchyard/supervisor/gh-config"),
        curl_program: path_env("FACTORY_CURL_PROGRAM", "/bin/curl"),
        openssl_program: path_env("FACTORY_OPENSSL_PROGRAM", "/bin/openssl"),
        app_id: u64_env("GH_PATCHYARD_APP_ID")?,
        installation_id: u64_env("GH_PATCHYARD_APP_INSTALLATION_ID")?,
        app_slug: required_or("GH_PATCHYARD_APP_SLUG", "patchyard"),
        private_key: required_path("GH_PATCHYARD_APP_PRIVATE_KEY_FILE")?,
        scratch,
        timeout: duration_env("FACTORY_GITHUB_TIMEOUT_SECONDS", 60)?,
    })?))
}

fn repository_scope() -> RepositoryScope {
    RepositoryScope {
        owner: required_or(
            "FACTORY_GITHUB_REPOSITORY_OWNER",
            "example-org",
        ),
        name: required_or("FACTORY_GITHUB_REPOSITORY_NAME", "fieldbook"),
    }
}

fn require_qualified_seat(
    rule: &crate::config::RoutingRule,
    provider_egress: &ProviderEgressConfig,
) -> Result<(), BootstrapError> {
    let provider = &rule.seat.provider;
    let Some(entry) = provider_egress.by_display_name(provider) else {
        return Err(BootstrapError::LiveProviderForbidden {
            provider: provider.clone(),
            reason: "provider is absent from policy/provider-egress.json",
        });
    };
    if !entry.credential_qualified {
        return Err(BootstrapError::LiveProviderForbidden {
            provider: provider.clone(),
            reason: "credential_qualified is false in policy/provider-egress.json",
        });
    }
    Ok(())
}

async fn ensure_private_roots(scratch: &Path, artifacts: &Path) -> Result<(), BootstrapError> {
    for (path, mode) in [(scratch, 0o700), (artifacts, 0o2750)] {
        let path = path.to_path_buf();
        blocking(move || {
            use std::os::unix::fs::PermissionsExt as _;
            std::fs::create_dir_all(&path)?;
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(mode))
        })
        .await??;
    }
    Ok(())
}

async fn blocking<T, E>(
    job: impl FnOnce() -> Result<T, E> + Send + 'static,
) -> Result<Result<T, E>, BootstrapError>
where
    T: Send + 'static,
    E: Send + 'static,
{
    Ok(tokio::task::spawn_blocking(job).await?)
}

fn required(name: &'static str) -> Result<String, BootstrapError> {
    env::var(name)
        .ok()
        .filter(|value| !value.trim().is_empty())
        .ok_or(BootstrapError::MissingEnvironment(name))
}

fn required_path(name: &'static str) -> Result<PathBuf, BootstrapError> {
    required(name).map(PathBuf::from)
}

fn required_or(name: &'static str, default: &str) -> String {
    env::var(name).unwrap_or_else(|_| default.to_owned())
}

fn path_env(name: &'static str, default: &str) -> PathBuf {
    PathBuf::from(required_or(name, default))
}

fn duration_env(name: &'static str, default: u64) -> Result<Duration, BootstrapError> {
    let value = required_or(name, &default.to_string())
        .parse::<u64>()
        .map_err(|_| BootstrapError::InvalidEnvironment(name))?;
    if value == 0 {
        return Err(BootstrapError::InvalidEnvironment(name));
    }
    Ok(Duration::from_secs(value))
}

fn usize_env(name: &'static str, default: usize) -> Result<usize, BootstrapError> {
    let value = required_or(name, &default.to_string())
        .parse::<usize>()
        .map_err(|_| BootstrapError::InvalidEnvironment(name))?;
    if value == 0 {
        return Err(BootstrapError::InvalidEnvironment(name));
    }
    Ok(value)
}

fn u32_env(name: &'static str, default: u32) -> Result<u32, BootstrapError> {
    required_or(name, &default.to_string())
        .parse::<u32>()
        .map_err(|_| BootstrapError::InvalidEnvironment(name))
}

fn u64_env(name: &'static str) -> Result<u64, BootstrapError> {
    required(name)?
        .parse::<u64>()
        .map_err(|_| BootstrapError::InvalidEnvironment(name))
}

fn bool_env(name: &'static str, default: bool) -> Result<bool, BootstrapError> {
    match required_or(name, if default { "true" } else { "false" }).as_str() {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err(BootstrapError::InvalidEnvironment(name)),
    }
}

fn split_env(name: &'static str) -> Vec<String> {
    env::var(name)
        .ok()
        .into_iter()
        .flat_map(|value| {
            value
                .split(',')
                .map(str::trim)
                .filter(|item| !item.is_empty())
                .map(str::to_owned)
                .collect::<Vec<_>>()
        })
        .collect()
}

fn os_args_json(name: &'static str) -> Result<Vec<std::ffi::OsString>, BootstrapError> {
    let values: Vec<String> = serde_json::from_str(&required_or(name, "[]"))
        .map_err(|_| BootstrapError::InvalidEnvironment(name))?;
    if values.len() > 64 || values.iter().any(|value| value.contains('\0')) {
        return Err(BootstrapError::InvalidEnvironment(name));
    }
    Ok(values.into_iter().map(std::ffi::OsString::from).collect())
}

#[derive(Debug, Error)]
pub enum BootstrapError {
    #[error("required environment variable is missing: {0}")]
    MissingEnvironment(&'static str),
    #[error("environment variable is invalid: {0}")]
    InvalidEnvironment(&'static str),
    #[error("live seat provider {provider} is forbidden: {reason}")]
    LiveProviderForbidden {
        provider: String,
        reason: &'static str,
    },
    #[error("runtime filesystem failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("runtime blocking task failed: {0}")]
    Join(#[from] tokio::task::JoinError),
    #[error("routing config failed: {0}")]
    Routing(#[from] crate::config::RoutingError),
    #[error("provider-egress config failed: {0}")]
    ProviderEgress(#[from] crate::config::ProviderEgressError),
    #[error("rubric failed: {0}")]
    Rubric(#[from] factory_core::triage::TriageError),
    #[error("artifact store failed: {0}")]
    Artifact(#[from] crate::artifacts::ArtifactError),
    #[error("isolated-child recovery failed: {0}")]
    Child(#[from] crate::child::ChildError),
    #[error("PostgreSQL store failed: {0}")]
    Store(#[from] crate::store::StoreError),
    #[error("GitHub API setup failed: {0}")]
    GitHub(#[from] crate::publisher::GitHubError),
    #[error("publisher setup failed: {0}")]
    Publisher(#[from] crate::publisher::PublisherError),
    #[error("preview lifecycle setup failed: {0}")]
    Lifecycle(#[from] crate::lifecycle::LifecycleError),
    #[error("preview client setup failed: {0}")]
    Preview(#[from] crate::preview::PreviewError),
    #[error("log secret scanner setup failed: {0}")]
    SecretScan(#[from] crate::secret_scan::SecretScanError),
    #[error("reconcile setup failed: {0}")]
    Reconcile(#[from] crate::reconcile::ReconcileError),
    #[error("improvement proposer setup failed: {0}")]
    Proposer(#[from] crate::proposer::ProposerError),
}

#[cfg(test)]
mod tests {
    use std::path::Path;

    use crate::config::{ProviderEgressConfig, RoutingConfig};

    use super::{BootstrapError, require_qualified_seat};

    fn canonical_configs() -> (RoutingConfig, ProviderEgressConfig) {
        (
            RoutingConfig::load(
                Path::new("../../policy/routing.json"),
                Path::new("../../docs/bench.json"),
            )
            .expect("routing"),
            ProviderEgressConfig::load(Path::new("../../policy/provider-egress.json"))
                .expect("provider egress"),
        )
    }

    #[test]
    fn qualified_seats_lift_the_live_gate_for_each_live_task_class() {
        let (routing, provider_egress) = canonical_configs();
        for task_class in ["triage", "author_disposition", "implementation_review"] {
            require_qualified_seat(
                routing.resolve(task_class).expect(task_class),
                &provider_egress,
            )
            .expect("each live seat resolves to a qualified provider");
        }
    }

    #[test]
    fn unqualified_seat_provider_is_named_with_the_policy_reason() {
        let (mut routing, provider_egress) = canonical_configs();
        routing
            .rules
            .get_mut("triage")
            .expect("triage")
            .seat
            .provider = "OpenAI".to_owned();
        let error =
            require_qualified_seat(routing.resolve("triage").expect("triage"), &provider_egress)
                .expect_err("OpenAI remains unqualified");
        assert!(matches!(
            error,
            BootstrapError::LiveProviderForbidden {
                ref provider,
                reason: "credential_qualified is false in policy/provider-egress.json",
            } if provider == "OpenAI"
        ));
        assert_eq!(
            error.to_string(),
            "live seat provider OpenAI is forbidden: credential_qualified is false in policy/provider-egress.json"
        );
    }
}
