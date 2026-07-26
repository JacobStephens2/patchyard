//! Fail-closed GitHub/deployment reconciliation for one durable factory run.

use std::{ffi::OsString, path::PathBuf, sync::Arc, time::Duration};

use serde::{Deserialize, Serialize};
use thiserror::Error;
use time::{OffsetDateTime, format_description::well_known::Rfc3339};
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    process::{ProcessError, ProcessSpec, run_bounded},
    publisher::{
        GitHubApi, GitHubError, PullRequest, RepositoryScope, TokenPurpose, has_head_approval,
    },
    store::{PullRequestRecord, ReconcileStore, StoreError},
};

#[derive(Clone, Debug)]
pub struct DeployedVersionConfig {
    pub program: PathBuf,
    pub arguments: Vec<OsString>,
    pub timeout: Duration,
    pub output_limit: usize,
}

impl DeployedVersionConfig {
    pub fn validate(&self) -> Result<(), ReconcileError> {
        if self.program.as_os_str().is_empty() {
            return Err(ReconcileError::InvalidConfig("deployed-version program"));
        }
        if self.timeout.is_zero() || self.timeout > Duration::from_secs(120) {
            return Err(ReconcileError::InvalidConfig("deployed-version timeout"));
        }
        if self.output_limit == 0 || self.output_limit > 1024 * 1024 {
            return Err(ReconcileError::InvalidConfig(
                "deployed-version output limit",
            ));
        }
        if self.arguments.len() > 64 {
            return Err(ReconcileError::InvalidConfig(
                "deployed-version argument count",
            ));
        }
        Ok(())
    }

    async fn read(
        &self,
        cancellation: &CancellationToken,
    ) -> Result<DeployedVersion, ReconcileError> {
        self.validate()?;
        let mut spec = ProcessSpec::new(&self.program);
        spec.args = self.arguments.clone();
        spec.timeout = self.timeout;
        spec.output_limit = self.output_limit;
        let output = run_bounded(&spec, cancellation).await?;
        if output.code != 0 {
            return Err(ReconcileError::DeployedVersionExit(output.code));
        }
        let version: DeployedVersion = serde_json::from_slice(&output.stdout)?;
        version.validate()?;
        Ok(version)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct DeployedVersion {
    pub schema_version: u16,
    pub repository: String,
    pub deployed_sha: String,
    pub observed_at: String,
    pub source: String,
}

impl DeployedVersion {
    fn validate(&self) -> Result<(), ReconcileError> {
        if self.schema_version != 1 {
            return Err(ReconcileError::InvalidDeployedVersion("schema version"));
        }
        validate_git_sha(&self.deployed_sha)?;
        if self.repository.trim().is_empty()
            || self.repository.len() > 256
            || self.repository.chars().any(char::is_control)
            || self.source.trim().is_empty()
            || self.source.len() > 256
            || self.source.chars().any(char::is_control)
        {
            return Err(ReconcileError::InvalidDeployedVersion(
                "repository or source",
            ));
        }
        OffsetDateTime::parse(&self.observed_at, &Rfc3339)
            .map_err(|_| ReconcileError::InvalidDeployedVersion("observed_at"))?;
        Ok(())
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ReconcileOutcome {
    pub request_id: Uuid,
    pub run_id: Uuid,
    pub pull_request: i32,
    pub state: String,
    pub merged: bool,
    pub merge_commit_sha: Option<String>,
    pub deployed_sha: Option<String>,
    pub approved_at_head: bool,
    pub admin_bypassed: bool,
    pub passing_run: bool,
    pub branch_deleted: bool,
}

#[derive(Clone)]
pub struct Reconciler<S: ReconcileStore> {
    store: S,
    github: Arc<dyn GitHubApi>,
    repository: RepositoryScope,
    deployed: DeployedVersionConfig,
}

impl<S: ReconcileStore> Reconciler<S> {
    pub fn new(
        store: S,
        github: Arc<dyn GitHubApi>,
        repository: RepositoryScope,
        deployed: DeployedVersionConfig,
    ) -> Result<Self, ReconcileError> {
        deployed.validate()?;
        if repository.owner.trim().is_empty() || repository.name.trim().is_empty() {
            return Err(ReconcileError::InvalidConfig("repository"));
        }
        Ok(Self {
            store,
            github,
            repository,
            deployed,
        })
    }

    pub async fn reconcile(
        &self,
        request_id: Uuid,
        cancellation: &CancellationToken,
    ) -> Result<ReconcileOutcome, ReconcileError> {
        let run = self
            .store
            .reconcile_run(request_id)
            .await?
            .ok_or(ReconcileError::RunNotFound(request_id))?;
        let token = match self
            .github
            .mint_token(&self.repository, TokenPurpose::Reconcile, cancellation)
            .await
        {
            Ok(token) => token,
            Err(error) => {
                self.record_github_failure(&error).await?;
                return Err(error.into());
            }
        };
        let pulls = match self
            .github
            .pull_requests_for_branch(&token, &self.repository, &run.branch, cancellation)
            .await
        {
            Ok(pulls) => pulls,
            Err(error) => {
                self.record_github_failure(&error).await?;
                return Err(error.into());
            }
        };
        if pulls.len() != 1 {
            return Err(ReconcileError::PullRequestCount {
                branch: run.branch,
                count: pulls.len(),
            });
        }
        let pull = &pulls[0];
        self.validate_pull(&run.branch, &token.bot.login, pull)?;

        let merged = pull.merged_at()?.is_some();
        let reviews = if merged {
            match self
                .github
                .reviews(&token, &self.repository, pull.number, cancellation)
                .await
            {
                Ok(reviews) => reviews,
                Err(error) => {
                    self.record_github_failure(&error).await?;
                    return Err(error.into());
                }
            }
        } else {
            Vec::new()
        };
        let approved_at_head = merged && has_head_approval(&reviews, &pull.head.sha);
        let admin_bypassed = merged && !approved_at_head;
        let mut deployed_sha = None;
        let mut reconcile_error = None;
        let passing_run = if merged {
            let merge_sha = pull
                .merge_commit_sha
                .as_deref()
                .ok_or(ReconcileError::MissingMergeCommit)?;
            validate_git_sha(merge_sha)?;
            match self.deployed.read(cancellation).await {
                Ok(version) if version.repository == self.repository.full_name() => {
                    deployed_sha = Some(version.deployed_sha);
                    approved_at_head && deployed_sha.as_deref() == Some(merge_sha)
                }
                Ok(_) => {
                    reconcile_error =
                        Some("deployed-version repository differs from factory target".to_owned());
                    false
                }
                Err(error) => {
                    reconcile_error = Some(error.to_string());
                    false
                }
            }
        } else {
            false
        };

        let review_state = if approved_at_head {
            "approved"
        } else if merged {
            "admin_bypassed"
        } else {
            "pending"
        };
        self.store
            .record_reconciled_pull_request(&PullRequestRecord {
                number: pull.number,
                request_id,
                run_id: run.id,
                branch: pull.head.branch.clone(),
                head_sha: pull.head.sha.clone(),
                ci_state: if passing_run {
                    "deployed"
                } else {
                    "not_passing"
                }
                .to_owned(),
                review_state: review_state.to_owned(),
                state: pull.state.clone(),
                is_draft: pull.draft,
                author_login: pull.user.login.clone(),
                html_url: pull.html_url.clone(),
                github_updated_at: pull.updated_at()?,
                merged_at: pull.merged_at()?,
                merge_commit_sha: pull.merge_commit_sha.clone(),
                merged_by: pull.merged_by.as_ref().map(|user| user.login.clone()),
                deployed_sha: deployed_sha.clone(),
                admin_bypassed,
                passing_run,
                reconcile_error: reconcile_error.clone(),
            })
            .await?;

        if let Some(error) = reconcile_error {
            return Err(ReconcileError::FailClosed(error));
        }
        Ok(ReconcileOutcome {
            request_id,
            run_id: run.id,
            pull_request: pull.number,
            state: pull.state.clone(),
            merged,
            merge_commit_sha: pull.merge_commit_sha.clone(),
            deployed_sha,
            approved_at_head,
            admin_bypassed,
            passing_run,
            branch_deleted: false,
        })
    }

    async fn record_github_failure(&self, error: &GitHubError) -> Result<(), ReconcileError> {
        self.store
            .record_reconcile_github_failure(&self.repository.full_name(), &error.to_string())
            .await?;
        Ok(())
    }

    fn validate_pull(
        &self,
        branch: &str,
        bot_login: &str,
        pull: &PullRequest,
    ) -> Result<(), ReconcileError> {
        if pull.head.branch != branch {
            return Err(ReconcileError::PullRequestMismatch("branch"));
        }
        if pull.user.login != bot_login {
            return Err(ReconcileError::PullRequestMismatch("author"));
        }
        if !matches!(pull.state.as_str(), "open" | "closed") {
            return Err(ReconcileError::PullRequestMismatch("state"));
        }
        validate_git_sha(&pull.head.sha)?;
        Ok(())
    }
}

fn validate_git_sha(value: &str) -> Result<(), ReconcileError> {
    if value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        Ok(())
    } else {
        Err(ReconcileError::InvalidDeployedVersion("Git SHA"))
    }
}

#[derive(Debug, Error)]
pub enum ReconcileError {
    #[error("invalid reconcile configuration: {0}")]
    InvalidConfig(&'static str),
    #[error("invalid deployed-version response: {0}")]
    InvalidDeployedVersion(&'static str),
    #[error("deployed-version source exited with status {0}")]
    DeployedVersionExit(i32),
    #[error("deployed-version JSON failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("bounded deployed-version process failed: {0}")]
    Process(#[from] ProcessError),
    #[error("factory store failed: {0}")]
    Store(#[from] StoreError),
    #[error("GitHub operation failed: {0}")]
    GitHub(#[from] GitHubError),
    #[error("no run exists for request {0}")]
    RunNotFound(Uuid),
    #[error("expected one PR for {branch}, found {count}")]
    PullRequestCount { branch: String, count: usize },
    #[error("pull request differs from durable factory identity: {0}")]
    PullRequestMismatch(&'static str),
    #[error("merged pull request has no merge commit SHA")]
    MissingMergeCommit,
    #[error("reconciliation failed closed: {0}")]
    FailClosed(String),
}

#[cfg(test)]
mod tests {
    use std::{
        fs,
        os::unix::fs::PermissionsExt as _,
        path::PathBuf,
        sync::{Arc, Mutex},
        time::Duration,
    };

    use time::{OffsetDateTime, format_description::well_known::Rfc3339};
    use tokio_util::sync::CancellationToken;
    use uuid::Uuid;

    use crate::{
        publisher::{
            BotIdentity, CreatePullRequest, GitHubApi, GitHubFuture, GitHubUser, InstallationToken,
            OpenPullRequestSnapshot, PullRequest, PullRequestRef, RepositoryScope, Review,
            TokenPurpose,
        },
        store::{ExistingRun, PullRequestRecord, ReconcileStore, StoreError},
    };

    use super::{DeployedVersion, DeployedVersionConfig, ReconcileError, Reconciler};

    #[test]
    fn deployed_version_is_strict_and_sha_bounded() {
        let valid: DeployedVersion = serde_json::from_str(&format!(
            r#"{{"schema_version":1,"repository":"example-org/fieldbook","deployed_sha":"{}","observed_at":"2026-07-23T00:00:00Z","source":"github-deploy-marker:fixture"}}"#,
            "a".repeat(40)
        ))
        .expect("strict JSON");
        valid.validate().expect("valid");
        assert!(
            serde_json::from_str::<DeployedVersion>(
                r#"{"schema_version":1,"repository":"x/y","deployed_sha":"bad","observed_at":"x","source":"x","extra":true}"#
            )
            .is_err()
        );
    }

    #[derive(Clone)]
    struct MemoryReconcileStore {
        run: ExistingRun,
        record: Arc<Mutex<Option<PullRequestRecord>>>,
    }

    impl ReconcileStore for MemoryReconcileStore {
        async fn reconcile_run(
            &self,
            _request_id: Uuid,
        ) -> Result<Option<ExistingRun>, StoreError> {
            Ok(Some(self.run.clone()))
        }

        async fn record_reconcile_github_failure(
            &self,
            _repository: &str,
            _error: &str,
        ) -> Result<(), StoreError> {
            Ok(())
        }

        async fn record_reconciled_pull_request(
            &self,
            record: &PullRequestRecord,
        ) -> Result<(), StoreError> {
            *self.record.lock().expect("record") = Some(record.clone());
            Ok(())
        }
    }

    #[derive(Clone)]
    struct MergedGitHub {
        pull: PullRequest,
        reviews: Vec<Review>,
    }

    impl GitHubApi for MergedGitHub {
        fn mint_token<'a>(
            &'a self,
            _repository: &'a RepositoryScope,
            _purpose: TokenPurpose,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, InstallationToken> {
            Box::pin(async {
                Ok(InstallationToken {
                    value: "fixture".to_owned(),
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
            Box::pin(async {
                Ok(OpenPullRequestSnapshot {
                    observed_at: OffsetDateTime::now_utc(),
                    pull_requests: Vec::new(),
                })
            })
        }

        fn pull_requests_for_branch<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            _branch: &'a str,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, Vec<PullRequest>> {
            Box::pin(async { Ok(vec![self.pull.clone()]) })
        }

        fn create_draft_pull_request<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            _request: &'a CreatePullRequest,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, PullRequest> {
            Box::pin(async { panic!("reconcile cannot create a PR") })
        }

        fn reviews<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            _number: i32,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, Vec<Review>> {
            Box::pin(async { Ok(self.reviews.clone()) })
        }

        fn delete_branch<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            _branch: &'a str,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, ()> {
            Box::pin(async { panic!("reconcile is read-only") })
        }
    }

    #[tokio::test]
    async fn admin_bypassed_merge_is_durably_not_passing() {
        let request_id = Uuid::new_v4();
        let run_id = Uuid::new_v4();
        let branch = format!("factory/{request_id}-session-10-publisher-demo");
        let head = "a".repeat(40);
        let merge = "b".repeat(40);
        let store = MemoryReconcileStore {
            run: ExistingRun {
                run_class: factory_verify::ledger::RunClass::Production,
                id: run_id,
                base_sha: "c".repeat(40),
                branch: branch.clone(),
                state: "ready_for_review".to_owned(),
                lane: "A".to_owned(),
                skill: "fixture".to_owned(),
            },
            record: Arc::new(Mutex::new(None)),
        };
        let github = MergedGitHub {
            pull: merged_pull(&branch, &head, &merge),
            reviews: Vec::new(),
        };
        let temp = tempfile::tempdir().expect("temp");
        let program = deployed_program(temp.path(), &merge);
        let reconciler = Reconciler::new(
            store.clone(),
            Arc::new(github),
            RepositoryScope {
                owner: "example-org".to_owned(),
                name: "fieldbook".to_owned(),
            },
            DeployedVersionConfig {
                program,
                arguments: Vec::new(),
                timeout: Duration::from_secs(2),
                output_limit: 4096,
            },
        )
        .expect("reconciler");
        let outcome = reconciler
            .reconcile(request_id, &CancellationToken::new())
            .await
            .expect("reconcile");
        assert!(outcome.admin_bypassed);
        assert!(!outcome.passing_run);
        let record = store
            .record
            .lock()
            .expect("record")
            .clone()
            .expect("durable record");
        assert!(record.admin_bypassed);
        assert!(!record.passing_run);
        assert_eq!(record.deployed_sha.as_deref(), Some(merge.as_str()));
    }

    #[tokio::test]
    async fn control_plane_local_source_drives_persisted_deployed_sha() {
        let request_id = Uuid::new_v4();
        let run_id = Uuid::new_v4();
        let branch = format!("factory/{request_id}-reconcile-source-fixture");
        let head = "a".repeat(40);
        let merge = "b".repeat(40);
        let store = MemoryReconcileStore {
            run: ExistingRun {
                run_class: factory_verify::ledger::RunClass::Production,
                id: run_id,
                base_sha: "c".repeat(40),
                branch: branch.clone(),
                state: "ready_for_review".to_owned(),
                lane: "A".to_owned(),
                skill: "fixture".to_owned(),
            },
            record: Arc::new(Mutex::new(None)),
        };
        let github = MergedGitHub {
            pull: merged_pull(&branch, &head, &merge),
            reviews: vec![approved_review(&head)],
        };
        let temp = tempfile::tempdir().expect("temp");
        let reconciler = Reconciler::new(
            store.clone(),
            Arc::new(github),
            RepositoryScope {
                owner: "example-org".to_owned(),
                name: "fieldbook".to_owned(),
            },
            DeployedVersionConfig {
                program: deployed_program(temp.path(), &merge),
                arguments: Vec::new(),
                timeout: Duration::from_secs(2),
                output_limit: 4096,
            },
        )
        .expect("reconciler");

        let outcome = reconciler
            .reconcile(request_id, &CancellationToken::new())
            .await
            .expect("reconcile");
        assert!(outcome.approved_at_head);
        assert!(outcome.passing_run);
        assert_eq!(outcome.deployed_sha.as_deref(), Some(merge.as_str()));
        let record = store
            .record
            .lock()
            .expect("record")
            .clone()
            .expect("durable record");
        assert!(record.passing_run);
        assert_eq!(record.deployed_sha.as_deref(), Some(merge.as_str()));
        assert_eq!(record.reconcile_error, None);
    }

    #[tokio::test]
    async fn control_plane_local_source_failure_is_persisted_fail_closed() {
        let request_id = Uuid::new_v4();
        let run_id = Uuid::new_v4();
        let branch = format!("factory/{request_id}-reconcile-source-failure");
        let head = "a".repeat(40);
        let merge = "b".repeat(40);
        let store = MemoryReconcileStore {
            run: ExistingRun {
                run_class: factory_verify::ledger::RunClass::Production,
                id: run_id,
                base_sha: "c".repeat(40),
                branch: branch.clone(),
                state: "ready_for_review".to_owned(),
                lane: "A".to_owned(),
                skill: "fixture".to_owned(),
            },
            record: Arc::new(Mutex::new(None)),
        };
        let github = MergedGitHub {
            pull: merged_pull(&branch, &head, &merge),
            reviews: vec![approved_review(&head)],
        };
        let temp = tempfile::tempdir().expect("temp");
        let source = temp.path().join("failed-deployed-version");
        fs::write(&source, "#!/bin/sh\nexit 23\n").expect("program");
        fs::set_permissions(&source, fs::Permissions::from_mode(0o700)).expect("chmod");
        let reconciler = Reconciler::new(
            store.clone(),
            Arc::new(github),
            RepositoryScope {
                owner: "example-org".to_owned(),
                name: "fieldbook".to_owned(),
            },
            DeployedVersionConfig {
                program: source,
                arguments: Vec::new(),
                timeout: Duration::from_secs(2),
                output_limit: 4096,
            },
        )
        .expect("reconciler");

        let error = reconciler
            .reconcile(request_id, &CancellationToken::new())
            .await
            .expect_err("source failure must fail closed");
        assert!(matches!(
            error,
            ReconcileError::FailClosed(ref message)
                if message == "deployed-version source exited with status 23"
        ));
        let record = store
            .record
            .lock()
            .expect("record")
            .clone()
            .expect("durable failure record");
        assert!(!record.passing_run);
        assert_eq!(record.deployed_sha, None);
        assert_eq!(
            record.reconcile_error.as_deref(),
            Some("deployed-version source exited with status 23")
        );
    }

    fn merged_pull(branch: &str, head: &str, merge: &str) -> PullRequest {
        let now = OffsetDateTime::now_utc()
            .format(&Rfc3339)
            .expect("timestamp");
        PullRequest {
            number: 42,
            node_id: "PR_42".to_owned(),
            draft: false,
            state: "closed".to_owned(),
            body: None,
            html_url: "https://github.invalid/pull/42".to_owned(),
            head: PullRequestRef {
                branch: branch.to_owned(),
                sha: head.to_owned(),
            },
            base: PullRequestRef {
                branch: "master".to_owned(),
                sha: "d".repeat(40),
            },
            user: GitHubUser {
                login: "patchyard[bot]".to_owned(),
            },
            updated_at: now.clone(),
            merged_at: Some(now),
            merge_commit_sha: Some(merge.to_owned()),
            merged_by: Some(GitHubUser {
                login: "admin".to_owned(),
            }),
        }
    }

    fn approved_review(head: &str) -> Review {
        Review {
            state: "APPROVED".to_owned(),
            commit_id: head.to_owned(),
            submitted_at: Some("2026-07-23T00:00:00Z".to_owned()),
            user: GitHubUser {
                login: "reviewer".to_owned(),
            },
        }
    }

    fn deployed_program(root: &std::path::Path, sha: &str) -> PathBuf {
        let program = root.join("deployed-version");
        fs::write(
            &program,
            format!(
                "#!/bin/sh\nprintf '%s\\n' '{}'\n",
                serde_json::json!({
                    "schema_version": 1,
                    "repository": "example-org/fieldbook",
                    "deployed_sha": sha,
                    "observed_at": "2026-07-23T00:00:00Z",
                    "source": "github-deploy-marker:fixture",
                })
            ),
        )
        .expect("program");
        fs::set_permissions(&program, fs::Permissions::from_mode(0o700)).expect("chmod");
        program
    }
}
