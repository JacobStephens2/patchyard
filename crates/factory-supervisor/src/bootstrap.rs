//! Environment-to-runtime wiring shared by both executables.

use std::{
    collections::BTreeMap,
    env,
    path::{Path, PathBuf},
    sync::Arc,
    time::Duration,
};

use factory_core::triage::Rubric;
use thiserror::Error;

use crate::{
    artifacts::ArtifactStore,
    config::RoutingConfig,
    daemon::DaemonConfig,
    pipeline::{Pipeline, PipelineConfig, RunMode},
    publisher::{
        GhGitHub, GhGitHubConfig, PublishService, Publisher, PublisherConfig, RepositoryScope,
    },
    reconcile::{DeployedVersionConfig, Reconciler},
    review::{ReviewSandboxConfig, SandboxedReviewer},
    stages::{
        ProcessAgentBackend, ProcessVerifierBackend, ProcessWorkerBackend, StageCommand,
        VerifierCommand, WorkerCommand,
    },
    store::{DailyLimits, PgPipelineStore},
};

pub struct RuntimeComponents {
    pub store: PgPipelineStore,
    pub pipeline: Pipeline<PgPipelineStore>,
    pub daemon: DaemonConfig,
}

pub struct ReconcileComponents {
    pub store: PgPipelineStore,
    pub reconciler: Reconciler<PgPipelineStore>,
}

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
    if routing.live_provider_execution {
        return Err(BootstrapError::LiveProviderForbidden);
    }
    let rubric_source = tokio::fs::read_to_string(&rubric_path).await?;
    let rubric = Rubric::parse_markdown(&rubric_source)?;
    ensure_private_roots(&scratch, &artifact_root).await?;
    let artifacts = blocking({
        let artifact_root = artifact_root.clone();
        move || ArtifactStore::open(artifact_root)
    })
    .await??;

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
            timeout: duration_env("FACTORY_DISPOSITION_TIMEOUT_SECONDS", 120)?,
            cli_version: required_or("FACTORY_DISPOSITION_CLI_VERSION", "fixture-stub/1"),
        },
    );
    let agents = ProcessAgentBackend::new(commands, scratch.join("agents"));
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
    let reviewer = SandboxedReviewer::new(ReviewSandboxConfig {
        bubblewrap: path_env("FACTORY_BUBBLEWRAP", "/usr/bin/bwrap"),
        harness_program: path_env(
            "FACTORY_REVIEW_HARNESS",
            "/usr/local/libexec/patchyard-review-stub",
        ),
        prompt: root.join("policy/review.md"),
        worktree_root: scratch.join("review-worktrees"),
        scratch_root: scratch.join("review-scratch"),
        timeout: duration_env("FACTORY_REVIEW_TIMEOUT_SECONDS", 300)?,
        live_network: false,
    });
    let store = PgPipelineStore::connect(&database_url).await?;
    let (repository, publisher): (PathBuf, Option<Arc<dyn PublishService>>) = match mode {
        RunMode::DryRun => (required_path("FACTORY_TARGET_REPOSITORY")?, None),
        RunMode::PrePublish => {
            let github = github_from_environment(scratch.join("github-private"))?;
            let publisher = Publisher::new(
                store.clone(),
                github,
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
            (repository, Some(Arc::new(publisher)))
        }
    };
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
    };
    Ok(RuntimeComponents {
        store,
        pipeline,
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
        DeployedVersionConfig {
            program: required_path("FACTORY_DEPLOYED_VERSION_PROGRAM")?,
            arguments: os_args_json("FACTORY_DEPLOYED_VERSION_ARGUMENTS_JSON")?,
            timeout: duration_env("FACTORY_DEPLOYED_VERSION_TIMEOUT_SECONDS", 30)?,
            output_limit: usize_env("FACTORY_DEPLOYED_VERSION_OUTPUT_BYTES", 64 * 1024)?,
        },
    )?;
    Ok(ReconcileComponents { store, reconciler })
}

fn github_from_environment(scratch: PathBuf) -> Result<Arc<GhGitHub>, BootstrapError> {
    Ok(Arc::new(GhGitHub::new(GhGitHubConfig {
        gh_program: path_env("FACTORY_GH_PROGRAM", "/bin/gh"),
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

async fn ensure_private_roots(scratch: &Path, artifacts: &Path) -> Result<(), BootstrapError> {
    for path in [scratch, artifacts] {
        let path = path.to_path_buf();
        blocking(move || {
            use std::os::unix::fs::PermissionsExt as _;
            std::fs::create_dir_all(&path)?;
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700))
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
    #[error("live provider execution is forbidden before provider qualification")]
    LiveProviderForbidden,
    #[error("runtime filesystem failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("runtime blocking task failed: {0}")]
    Join(#[from] tokio::task::JoinError),
    #[error("routing config failed: {0}")]
    Routing(#[from] crate::config::RoutingError),
    #[error("rubric failed: {0}")]
    Rubric(#[from] factory_core::triage::TriageError),
    #[error("artifact store failed: {0}")]
    Artifact(#[from] crate::artifacts::ArtifactError),
    #[error("PostgreSQL store failed: {0}")]
    Store(#[from] crate::store::StoreError),
    #[error("GitHub API setup failed: {0}")]
    GitHub(#[from] crate::publisher::GitHubError),
    #[error("publisher setup failed: {0}")]
    Publisher(#[from] crate::publisher::PublisherError),
    #[error("reconcile setup failed: {0}")]
    Reconcile(#[from] crate::reconcile::ReconcileError),
}
