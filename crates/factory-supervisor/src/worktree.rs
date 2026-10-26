//! Exact-SHA bundles, patch re-derivation, and explicit worktree cleanup.

use std::{
    collections::BTreeMap,
    ffi::OsString,
    fs,
    io::{BufReader, Read as _},
    os::unix::fs::PermissionsExt as _,
    path::{Path, PathBuf},
    time::Duration,
};

use factory_verify::{
    caps::{ChangeKind, DiffFile, DiffManifest},
    runtime::tree_hash,
};
use sha2::{Digest as _, Sha256};
use thiserror::Error;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::{
    contracts::PatchHunk,
    process::{ProcessError, ProcessSpec, run_bounded},
};

/// Credential-free source bundle made from one exact commit.
pub struct ExactBundle {
    path: PathBuf,
    pub base_sha: String,
    pub sha256: String,
    closed: bool,
}

impl ExactBundle {
    pub async fn create(
        repository: &Path,
        base_sha: &str,
        scratch: &Path,
        cancellation: &CancellationToken,
    ) -> Result<Self, WorktreeError> {
        validate_git_sha(base_sha)?;
        create_private_dir(scratch.to_path_buf()).await?;
        let path = scratch.join(format!("source-{}.tar", Uuid::new_v4()));
        let mut spec = ProcessSpec::new("/usr/bin/git");
        spec.args = vec![
            OsString::from("-C"),
            repository.as_os_str().to_owned(),
            OsString::from("archive"),
            OsString::from("--format=tar"),
            OsString::from(format!("--output={}", path.display())),
            OsString::from(base_sha),
        ];
        spec.timeout = Duration::from_secs(120);
        spec.output_limit = 64 * 1024;
        let output = run_bounded(&spec, cancellation).await?;
        if output.code != 0 {
            return Err(WorktreeError::Git {
                operation: "archive",
                code: output.code,
            });
        }
        let hash_path = path.clone();
        let sha256 = tokio::task::spawn_blocking(move || hash_file(&hash_path))
            .await
            .map_err(WorktreeError::Join)??;
        Ok(Self {
            path,
            base_sha: base_sha.to_owned(),
            sha256,
            closed: false,
        })
    }

    #[must_use]
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Fallible cleanup is awaitable and checked; Drop never substitutes.
    pub async fn close(mut self) -> Result<(), WorktreeError> {
        let path = self.path.clone();
        tokio::task::spawn_blocking(move || match fs::remove_file(path) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error),
        })
        .await
        .map_err(WorktreeError::Join)??;
        self.closed = true;
        Ok(())
    }
}

impl Drop for ExactBundle {
    fn drop(&mut self) {
        if !self.closed {
            tracing::error!(path = %self.path.display(), "exact bundle dropped without close()");
        }
    }
}

/// A fresh detached worktree with an explicit checked teardown.
pub struct DetachedWorktree {
    repository: PathBuf,
    path: PathBuf,
    pub reviewed_sha: String,
    closed: bool,
}

impl DetachedWorktree {
    pub async fn create(
        repository: &Path,
        reviewed_sha: &str,
        root: &Path,
        name: &str,
        cancellation: &CancellationToken,
    ) -> Result<Self, WorktreeError> {
        validate_git_sha(reviewed_sha)?;
        validate_name(name)?;
        create_private_dir(root.to_path_buf()).await?;
        let path = root.join(name);
        if tokio::fs::try_exists(&path).await? {
            return Err(WorktreeError::AlreadyExists(path));
        }
        let mut spec = ProcessSpec::new("/usr/bin/git");
        spec.args = vec![
            OsString::from("-C"),
            repository.as_os_str().to_owned(),
            OsString::from("worktree"),
            OsString::from("add"),
            OsString::from("--detach"),
            path.as_os_str().to_owned(),
            OsString::from(reviewed_sha),
        ];
        spec.timeout = Duration::from_secs(60);
        spec.output_limit = 128 * 1024;
        let output = match run_bounded(&spec, cancellation).await {
            Ok(output) => output,
            Err(error) => {
                cleanup_partial_worktree(repository, &path).await?;
                return Err(error.into());
            }
        };
        if output.code != 0 {
            cleanup_partial_worktree(repository, &path).await?;
            return Err(WorktreeError::Git {
                operation: "worktree-add",
                code: output.code,
            });
        }
        let worktree = Self {
            repository: repository.to_path_buf(),
            path,
            reviewed_sha: reviewed_sha.to_owned(),
            closed: false,
        };
        let validation = async {
            let permission_path = worktree.path.clone();
            tokio::task::spawn_blocking(move || {
                fs::set_permissions(permission_path, fs::Permissions::from_mode(0o700))
            })
            .await
            .map_err(WorktreeError::Join)??;
            let actual = git_stdout(
                repository,
                &[
                    "-C",
                    worktree.path.to_str().ok_or(WorktreeError::NonUtf8)?,
                    "rev-parse",
                    "HEAD",
                ],
                cancellation,
            )
            .await?;
            if actual.trim() != reviewed_sha {
                return Err(WorktreeError::WrongSha {
                    expected: reviewed_sha.to_owned(),
                    actual: actual.trim().to_owned(),
                });
            }
            Ok(())
        }
        .await;
        match validation {
            Ok(()) => Ok(worktree),
            Err(error) => {
                worktree.close(&CancellationToken::new()).await?;
                Err(error)
            }
        }
    }

    #[must_use]
    pub fn path(&self) -> &Path {
        &self.path
    }

    pub async fn close(mut self, cancellation: &CancellationToken) -> Result<(), WorktreeError> {
        let mut spec = ProcessSpec::new("/usr/bin/git");
        spec.args = vec![
            OsString::from("-C"),
            self.repository.as_os_str().to_owned(),
            OsString::from("worktree"),
            OsString::from("remove"),
            OsString::from("--force"),
            // `git worktree add` locks a tree while it initializes it.  If
            // initialization itself fails, one force is deliberately not
            // enough to remove that locked, partial tree.  The second force
            // is narrowly paired with this exact generated worktree path.
            OsString::from("--force"),
            self.path.as_os_str().to_owned(),
        ];
        spec.timeout = Duration::from_secs(60);
        spec.output_limit = 128 * 1024;
        let output = run_bounded(&spec, cancellation).await?;
        if output.code != 0 && tokio::fs::try_exists(&self.path).await? {
            return Err(WorktreeError::Git {
                operation: "worktree-remove",
                code: output.code,
            });
        }
        self.closed = true;
        Ok(())
    }
}

async fn cleanup_partial_worktree(repository: &Path, path: &Path) -> Result<(), WorktreeError> {
    let mut spec = ProcessSpec::new("/usr/bin/git");
    spec.args = vec![
        OsString::from("-C"),
        repository.as_os_str().to_owned(),
        OsString::from("worktree"),
        OsString::from("remove"),
        OsString::from("--force"),
        OsString::from("--force"),
        path.as_os_str().to_owned(),
    ];
    spec.timeout = Duration::from_secs(60);
    spec.output_limit = 128 * 1024;
    let output = run_bounded(&spec, &CancellationToken::new()).await?;
    if output.code != 0 && tokio::fs::try_exists(path).await? {
        return Err(WorktreeError::Git {
            operation: "partial-worktree-remove",
            code: output.code,
        });
    }
    Ok(())
}

impl Drop for DetachedWorktree {
    fn drop(&mut self) {
        if !self.closed {
            tracing::error!(path = %self.path.display(), "worktree dropped without close()");
        }
    }
}

/// Ceiling on the hunk ranges one recomputation may yield. Lane A is capped at
/// 2 files and 50 changed lines, so a diff that reaches this is malformed
/// rather than large, and inspection must fail closed instead of growing.
///
/// The review seat validates the same ceiling on the receiving side, as
/// `MAX_PACKET_HUNKS` in
/// `infra/ansible/roles/control_plane/files/patchyard-review-seat`. The two
/// cannot share a constant across the process boundary; raising one without
/// the other only makes the seat, not the supervisor, the refusing side.
const MAX_PATCH_HUNKS: usize = 256;

/// Independently recomputed patch facts used to construct OutContract.
#[derive(Clone, Debug)]
pub struct InspectedPatch {
    pub manifest: DiffManifest,
    /// Where the change landed, in reviewed-SHA line numbers. Read from the
    /// same recomputed diff as `manifest`, so the reviewer's window is aimed
    /// by the supervisor's own reading of the applied result rather than by
    /// hunk headers the worker wrote.
    pub hunks: Vec<PatchHunk>,
    pub patch_sha256: String,
    pub base_tree_hash: String,
    pub result_tree_hash: String,
}

pub async fn inspect_patch(
    repository: &Path,
    base_sha: &str,
    patch_path: &Path,
    scratch: &Path,
    cancellation: &CancellationToken,
) -> Result<InspectedPatch, WorktreeError> {
    let name = format!("inspect-{}", Uuid::new_v4());
    let worktree =
        DetachedWorktree::create(repository, base_sha, scratch, &name, cancellation).await?;
    let result = inspect_in_worktree(&worktree, patch_path, cancellation).await;
    // Cleanup is a correctness path and must not inherit run cancellation.
    let cleanup = worktree.close(&CancellationToken::new()).await;
    match (result, cleanup) {
        (Ok(value), Ok(())) => Ok(value),
        (Err(error), Ok(())) => Err(error),
        (_, Err(error)) => Err(error),
    }
}

/// Hash an exact commit's filesystem projection in a disposable worktree.
pub async fn hash_commit_tree(
    repository: &Path,
    base_sha: &str,
    scratch: &Path,
    cancellation: &CancellationToken,
) -> Result<String, WorktreeError> {
    let name = format!("hash-{}", Uuid::new_v4());
    let worktree =
        DetachedWorktree::create(repository, base_sha, scratch, &name, cancellation).await?;
    let root = worktree.path().to_path_buf();
    let result = tokio::task::spawn_blocking(move || tree_hash(&root))
        .await
        .map_err(WorktreeError::Join)?
        .map_err(WorktreeError::TreeHash);
    // Cleanup is a correctness path and must not inherit run cancellation.
    let cleanup = worktree.close(&CancellationToken::new()).await;
    match (result, cleanup) {
        (Ok(hash), Ok(())) => Ok(hash),
        (Err(error), Ok(())) => Err(error),
        (_, Err(error)) => Err(error),
    }
}

/// Materialize a patch as an exact local commit for isolated reviewers. The
/// temporary worktree is always explicitly removed before the SHA is returned.
pub async fn materialize_review_sha(
    repository: &Path,
    base_sha: &str,
    patch_path: &Path,
    scratch: &Path,
    cancellation: &CancellationToken,
) -> Result<String, WorktreeError> {
    let name = format!("materialize-{}", Uuid::new_v4());
    let worktree =
        DetachedWorktree::create(repository, base_sha, scratch, &name, cancellation).await?;
    let result = async {
        let mut apply = ProcessSpec::new("/usr/bin/git");
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
        if output.code != 0 {
            return Err(WorktreeError::Git {
                operation: "materialize-apply",
                code: output.code,
            });
        }
        let mut commit = ProcessSpec::new("/usr/bin/git");
        commit.args = vec![
            OsString::from("-C"),
            worktree.path().as_os_str().to_owned(),
            OsString::from("-c"),
            OsString::from("user.name=Patchyard Factory"),
            OsString::from("-c"),
            OsString::from("user.email=factory@invalid.example"),
            OsString::from("commit"),
            OsString::from("--no-gpg-sign"),
            OsString::from("-m"),
            OsString::from("factory review materialization"),
        ];
        commit.timeout = Duration::from_secs(60);
        commit.output_limit = 256 * 1024;
        let output = run_bounded(&commit, cancellation).await?;
        if output.code != 0 {
            return Err(WorktreeError::Git {
                operation: "materialize-commit",
                code: output.code,
            });
        }
        Ok(
            git_stdout_path(worktree.path(), &["rev-parse", "HEAD"], cancellation)
                .await?
                .trim()
                .to_owned(),
        )
    }
    .await;
    let cleanup = worktree.close(&CancellationToken::new()).await;
    match (result, cleanup) {
        (Ok(sha), Ok(())) => Ok(sha),
        (Err(error), Ok(())) => Err(error),
        (_, Err(error)) => Err(error),
    }
}

async fn inspect_in_worktree(
    worktree: &DetachedWorktree,
    patch_path: &Path,
    cancellation: &CancellationToken,
) -> Result<InspectedPatch, WorktreeError> {
    let base_root = worktree.path().to_path_buf();
    let base_tree_hash = tokio::task::spawn_blocking(move || tree_hash(&base_root))
        .await
        .map_err(WorktreeError::Join)??;
    let mut apply = ProcessSpec::new("/usr/bin/git");
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
    if output.code != 0 {
        return Err(WorktreeError::Git {
            operation: "apply",
            code: output.code,
        });
    }
    let numstat = git_stdout_path(
        worktree.path(),
        &[
            "diff",
            "--cached",
            "--numstat",
            "--find-renames",
            "HEAD",
            "--",
        ],
        cancellation,
    )
    .await?;
    let raw = git_stdout_path(
        worktree.path(),
        &["diff", "--cached", "--raw", "--find-renames", "HEAD", "--"],
        cancellation,
    )
    .await?;
    let manifest = parse_manifest(&worktree.reviewed_sha, &numstat, &raw)?;
    // Zero context lines: the hunk headers then state the changed ranges
    // exactly, and the seat supplies the reading context itself. Rename
    // detection is deliberately off here - a rename's `b/` side is the only
    // path a window can be taken against, and `parse_manifest` above is what
    // records the rename itself.
    let unified = git_stdout_path(
        worktree.path(),
        &["diff", "--cached", "-U0", "--no-renames", "HEAD", "--"],
        cancellation,
    )
    .await?;
    let hunks = parse_hunks(&unified)?;
    let result_root = worktree.path().to_path_buf();
    let result_tree_hash = tokio::task::spawn_blocking(move || tree_hash(&result_root))
        .await
        .map_err(WorktreeError::Join)??;
    let hash_path = patch_path.to_path_buf();
    let patch_sha256 = tokio::task::spawn_blocking(move || hash_file(&hash_path))
        .await
        .map_err(WorktreeError::Join)??;
    Ok(InspectedPatch {
        manifest,
        hunks,
        patch_sha256,
        base_tree_hash,
        result_tree_hash,
    })
}

/// Read every hunk's new-file line range out of the recomputed unified diff.
///
/// The manifest counts a file's changed lines but never says where they are,
/// so without this the reviewer's projection can only offer whole file bodies,
/// and a file over its per-file cap has no body it can offer.
///
/// The path comes from each `+++ b/` line rather than from `diff --git`,
/// because `+++` names the side the ranges are in. A `+++ /dev/null` file was
/// deleted, so it has no reviewed-SHA line to window and its hunks are
/// dropped.
///
/// A pure-deletion hunk (`+n,0`) has no new line of its own; it is recorded as
/// the single line the deletion sits against, which is the line a window must
/// show for the removal to be visible.
///
/// An empty result is a valid answer, not a fault: a diff that only changes
/// modes or only touches binary files has no textual hunk to window. The seat
/// falls back to its omission markers for those paths.
fn parse_hunks(unified: &str) -> Result<Vec<PatchHunk>, WorktreeError> {
    let mut hunks = Vec::new();
    let mut current_path: Option<&str> = None;
    let mut named_a_side = false;
    // Remaining old/new lines the hunk body must still account for. While
    // these are live, a `@@` or `+++` at column 0 is diff content, not a
    // header: every body line carries a one-character prefix.
    let mut remaining: Option<(u32, u32)> = None;
    for line in unified.lines() {
        if remaining == Some((0, 0)) {
            remaining = None;
        }
        if let Some((old_span, new_span)) = remaining.as_mut() {
            match line.as_bytes().first() {
                Some(b'-') => {
                    *old_span = old_span
                        .checked_sub(1)
                        .ok_or(WorktreeError::MalformedGitOutput)?;
                }
                Some(b'+') => {
                    *new_span = new_span
                        .checked_sub(1)
                        .ok_or(WorktreeError::MalformedGitOutput)?;
                }
                // `\ No newline at end of file` belongs to the line before it.
                Some(b'\\') => {}
                Some(_) | None => return Err(WorktreeError::MalformedGitOutput),
            }
            continue;
        }
        if let Some(path) = line.strip_prefix("+++ b/") {
            current_path = Some(path);
            named_a_side = true;
            continue;
        }
        if line == "+++ /dev/null" {
            current_path = None;
            named_a_side = true;
            continue;
        }
        let Some(header) = line.strip_prefix("@@ -") else {
            continue;
        };
        if !named_a_side {
            return Err(WorktreeError::MalformedGitOutput);
        }
        let (old_span, rest) = split_hunk_span(header)?;
        let (new_span, _) = split_hunk_span(
            rest.strip_prefix('+')
                .ok_or(WorktreeError::MalformedGitOutput)?,
        )?;
        remaining = Some((old_span.1, new_span.1));
        let Some(path) = current_path else {
            continue;
        };
        if hunks.len() >= MAX_PATCH_HUNKS {
            return Err(WorktreeError::TooManyPatchHunks(MAX_PATCH_HUNKS));
        }
        hunks.push(PatchHunk {
            path: path.to_owned(),
            start_line: new_span.0.max(1),
            line_count: new_span.1.max(1),
        });
    }
    Ok(hunks)
}

/// Split one `start[,count]` hunk span off the front of a hunk header,
/// returning it and the remainder after the following space.
fn split_hunk_span(header: &str) -> Result<((u32, u32), &str), WorktreeError> {
    let (span, rest) = header
        .split_once(' ')
        .ok_or(WorktreeError::MalformedGitOutput)?;
    let (start, count) = match span.split_once(',') {
        Some((start, count)) => (start, count),
        None => (span, "1"),
    };
    Ok((
        (
            start
                .parse::<u32>()
                .map_err(|_| WorktreeError::MalformedGitOutput)?,
            count
                .parse::<u32>()
                .map_err(|_| WorktreeError::MalformedGitOutput)?,
        ),
        rest,
    ))
}

fn parse_manifest(base_sha: &str, numstat: &str, raw: &str) -> Result<DiffManifest, WorktreeError> {
    let mut raw_by_path = BTreeMap::new();
    for line in raw.lines().filter(|line| !line.is_empty()) {
        let mut fields = line.split('\t');
        let header = fields.next().ok_or(WorktreeError::MalformedGitOutput)?;
        let path = fields.next().ok_or(WorktreeError::MalformedGitOutput)?;
        let header_fields: Vec<_> = header.split_whitespace().collect();
        if header_fields.len() != 5 {
            return Err(WorktreeError::MalformedGitOutput);
        }
        let old_mode = header_fields[0].trim_start_matches(':').to_owned();
        let new_mode = header_fields[1].to_owned();
        let status = header_fields[4];
        let old_path = if status.starts_with('R') {
            Some(path.to_owned())
        } else {
            None
        };
        let final_path = if old_path.is_some() {
            fields.next().ok_or(WorktreeError::MalformedGitOutput)?
        } else {
            path
        };
        raw_by_path.insert(
            final_path.to_owned(),
            (status.to_owned(), old_mode, new_mode, old_path),
        );
    }
    let mut files = Vec::new();
    for line in numstat.lines().filter(|line| !line.is_empty()) {
        let mut fields = line.split('\t');
        let additions = fields.next().ok_or(WorktreeError::MalformedGitOutput)?;
        let deletions = fields.next().ok_or(WorktreeError::MalformedGitOutput)?;
        let path = fields.next().ok_or(WorktreeError::MalformedGitOutput)?;
        let (status, old_mode, new_mode, old_path) = raw_by_path
            .remove(path)
            .ok_or(WorktreeError::MalformedGitOutput)?;
        let binary = additions == "-" || deletions == "-";
        let (additions, deletions) = if binary {
            (0, 0)
        } else {
            (
                additions
                    .parse()
                    .map_err(|_| WorktreeError::MalformedGitOutput)?,
                deletions
                    .parse()
                    .map_err(|_| WorktreeError::MalformedGitOutput)?,
            )
        };
        let change = match status.as_bytes().first().copied() {
            Some(b'A') => ChangeKind::Added,
            Some(b'D') => ChangeKind::Deleted,
            Some(b'M') => ChangeKind::Modified,
            Some(b'R') => ChangeKind::Renamed,
            _ => return Err(WorktreeError::MalformedGitOutput),
        };
        files.push(DiffFile {
            path: path.to_owned(),
            old_path,
            change,
            additions,
            deletions,
            binary,
            generated: false,
            old_mode: Some(old_mode),
            new_mode: Some(new_mode),
        });
    }
    if !raw_by_path.is_empty() {
        return Err(WorktreeError::MalformedGitOutput);
    }
    files.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(DiffManifest {
        base_sha: base_sha.to_owned(),
        files,
    })
}

async fn git_stdout_path(
    repository: &Path,
    arguments: &[&str],
    cancellation: &CancellationToken,
) -> Result<String, WorktreeError> {
    let mut owned = vec![OsString::from("-C"), repository.as_os_str().to_owned()];
    owned.extend(arguments.iter().map(OsString::from));
    git_output(owned, cancellation).await
}

async fn git_stdout(
    _repository: &Path,
    arguments: &[&str],
    cancellation: &CancellationToken,
) -> Result<String, WorktreeError> {
    git_output(arguments.iter().map(OsString::from).collect(), cancellation).await
}

async fn git_output(
    arguments: Vec<OsString>,
    cancellation: &CancellationToken,
) -> Result<String, WorktreeError> {
    let mut spec = ProcessSpec::new("/usr/bin/git");
    spec.args = arguments;
    spec.timeout = Duration::from_secs(60);
    spec.output_limit = 2 * 1024 * 1024;
    let output = run_bounded(&spec, cancellation).await?;
    if output.code != 0 {
        return Err(WorktreeError::Git {
            operation: "inspect",
            code: output.code,
        });
    }
    String::from_utf8(output.stdout).map_err(|_| WorktreeError::NonUtf8)
}

async fn create_private_dir(path: PathBuf) -> Result<(), WorktreeError> {
    tokio::task::spawn_blocking(move || {
        fs::create_dir_all(&path)?;
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "worktree root is not a regular directory",
            ));
        }
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))
    })
    .await
    .map_err(WorktreeError::Join)??;
    Ok(())
}

fn hash_file(path: &Path) -> Result<String, WorktreeError> {
    let file = fs::File::open(path)?;
    let mut reader = BufReader::with_capacity(64 * 1024, file);
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = reader.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(hex::encode(hasher.finalize()))
}

fn validate_git_sha(value: &str) -> Result<(), WorktreeError> {
    if value.len() != 40
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(WorktreeError::InvalidSha);
    }
    Ok(())
}

fn validate_name(value: &str) -> Result<(), WorktreeError> {
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
    {
        return Err(WorktreeError::InvalidName);
    }
    Ok(())
}

#[derive(Debug, Error)]
pub enum WorktreeError {
    #[error("Git SHA must be 40 lower-case hexadecimal characters")]
    InvalidSha,
    #[error("worktree name is invalid")]
    InvalidName,
    #[error("worktree already exists: {0}")]
    AlreadyExists(PathBuf),
    #[error("Git {operation} failed with status {code}")]
    Git { operation: &'static str, code: i32 },
    #[error("Git output did not match the bounded manifest grammar")]
    MalformedGitOutput,
    #[error("recomputed diff carries more than {0} hunks")]
    TooManyPatchHunks(usize),
    #[error("worktree is not UTF-8")]
    NonUtf8,
    #[error("worktree has {actual}, expected {expected}")]
    WrongSha { expected: String, actual: String },
    #[error("bounded subprocess failed: {0}")]
    Process(#[from] ProcessError),
    #[error("filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("blocking filesystem/hash task failed: {0}")]
    Join(tokio::task::JoinError),
    #[error("tree hashing failed: {0}")]
    TreeHash(#[from] factory_verify::runtime::RuntimeError),
}

#[cfg(test)]
mod tests {
    use std::{fs, process::Command};

    use tempfile::tempdir;
    use tokio_util::sync::CancellationToken;

    use factory_verify::caps::ChangeKind;

    use super::{DetachedWorktree, WorktreeError, inspect_patch, parse_hunks, parse_manifest};

    /// factory#325: the reviewer's projection can only window a large file if
    /// the packet says where the change is, and the manifest never does.
    #[test]
    fn hunk_ranges_are_read_in_reviewed_sha_line_numbers_for_every_hunk() {
        let unified = "\
diff --git a/mfieldbook/common_functions.php b/mfieldbook/common_functions.php
index 1111111..2222222 100644
--- a/mfieldbook/common_functions.php
+++ b/mfieldbook/common_functions.php
@@ -901 +901,2 @@ function first() {
-old behavior
+new behavior
+added behavior
@@ -41001 +41002 @@ function second() {
-old
+new
";

        let hunks = parse_hunks(unified).expect("recomputed diff");

        assert_eq!(hunks.len(), 2);
        assert_eq!(hunks[0].path, "mfieldbook/common_functions.php");
        assert_eq!((hunks[0].start_line, hunks[0].line_count), (901, 2));
        assert_eq!((hunks[1].start_line, hunks[1].line_count), (41002, 1));
    }

    /// A hunk body line that reads like a header must not be counted as one,
    /// or every range after it points at the wrong part of the file.
    #[test]
    fn a_hunk_body_line_shaped_like_a_header_is_content_not_a_new_range() {
        let unified = "\
--- a/notes.md
+++ b/notes.md
@@ -1,2 +1,2 @@
-@@ -9999,9 +9999,9 @@ not a header
-+++ b/also-not-a-header
+@@ -8888,8 +8888,8 @@ still not a header
++++ b/still-not-a-header
";

        let hunks = parse_hunks(unified).expect("recomputed diff");

        assert_eq!(hunks.len(), 1);
        assert_eq!(hunks[0].path, "notes.md");
        assert_eq!((hunks[0].start_line, hunks[0].line_count), (1, 2));
    }

    /// A pure deletion adds no line of its own, so `+n,0` has to become the
    /// one line a window shows for the removal to be visible at all.
    #[test]
    fn a_pure_deletion_hunk_still_names_a_line_a_window_can_show() {
        let unified = "\
--- a/notes.md
+++ b/notes.md
@@ -5 +4,0 @@
-removed
";

        let hunks = parse_hunks(unified).expect("recomputed diff");

        assert_eq!(hunks.len(), 1);
        assert_eq!((hunks[0].start_line, hunks[0].line_count), (4, 1));
    }

    /// A deleted file has no reviewed-SHA line to show, so it contributes no
    /// range - and the file after it must still be read correctly.
    #[test]
    fn a_deleted_files_hunks_are_dropped_without_losing_the_next_file() {
        let unified = "\
--- a/gone.php
+++ /dev/null
@@ -1,2 +0,0 @@
-first
-second
--- a/kept.php
+++ b/kept.php
@@ -7 +7 @@
-old
+new
";

        let hunks = parse_hunks(unified).expect("recomputed diff");

        assert_eq!(hunks.len(), 1);
        assert_eq!(hunks[0].path, "kept.php");
        assert_eq!((hunks[0].start_line, hunks[0].line_count), (7, 1));
    }

    #[test]
    fn a_hunk_header_before_any_file_header_fails_closed() {
        let error = parse_hunks("@@ -1 +1 @@\n-old\n+new\n").expect_err("no file named");

        assert!(matches!(error, WorktreeError::MalformedGitOutput));
    }

    fn git(repository: &std::path::Path, arguments: &[&str]) {
        let output = Command::new("git")
            .arg("-C")
            .arg(repository)
            .args(arguments)
            .output()
            .expect("git must run in the worktree regression test");
        assert!(
            output.status.success(),
            "git {:?} failed: {}",
            arguments,
            String::from_utf8_lossy(&output.stderr)
        );
    }

    #[test]
    fn added_symlink_mode_survives_manifest_parsing() {
        let raw = format!(
            ":000000 120000 {} {} A\tpolicy/escape.md\n",
            "0".repeat(40),
            "1".repeat(40)
        );
        let manifest =
            parse_manifest(&"a".repeat(40), "1\t0\tpolicy/escape.md\n", &raw).expect("manifest");
        assert_eq!(manifest.files[0].change, ChangeKind::Added);
        assert_eq!(manifest.files[0].old_mode.as_deref(), Some("000000"));
        assert_eq!(manifest.files[0].new_mode.as_deref(), Some("120000"));
    }

    /// The `-U0 --no-renames` flags and `parse_hunks` have to agree about what
    /// Git actually emits, so this runs the real recomputation end to end: two
    /// files changed in one patch, one of them past line 40,000.
    #[tokio::test]
    async fn inspection_recomputes_hunk_ranges_from_the_applied_result() {
        let temporary = tempdir().expect("temporary repository");
        let repository = temporary.path().join("repository");
        fs::create_dir(&repository).expect("repository directory");
        git(&repository, &["init"]);
        git(
            &repository,
            &["config", "user.name", "Patchyard Factory test"],
        );
        git(
            &repository,
            &["config", "user.email", "factory-test@invalid.example"],
        );
        let mut wide: Vec<String> = (1..=41_000).map(|line| format!("line {line}")).collect();
        fs::write(repository.join("wide.php"), wide.join("\n") + "\n").expect("wide fixture");
        fs::write(repository.join("small.php"), "alpha\nbeta\n").expect("small fixture");
        git(&repository, &["add", "wide.php", "small.php"]);
        git(&repository, &["commit", "-m", "fixture"]);
        let base_sha = String::from_utf8(
            Command::new("git")
                .arg("-C")
                .arg(&repository)
                .args(["rev-parse", "HEAD"])
                .output()
                .expect("rev-parse")
                .stdout,
        )
        .expect("UTF-8 SHA")
        .trim()
        .to_owned();

        wide[39_999] = "line 40000 changed".to_owned();
        fs::write(repository.join("wide.php"), wide.join("\n") + "\n").expect("wide edit");
        fs::write(repository.join("small.php"), "alpha\ngamma\n").expect("small edit");
        let patch = String::from_utf8(
            Command::new("git")
                .arg("-C")
                .arg(&repository)
                .args(["diff"])
                .output()
                .expect("diff")
                .stdout,
        )
        .expect("UTF-8 patch");
        git(&repository, &["checkout", "--", "."]);
        let patch_path = temporary.path().join("worker.patch");
        fs::write(&patch_path, patch).expect("patch file");

        let inspected = inspect_patch(
            &repository,
            &base_sha,
            &patch_path,
            &temporary.path().join("inspect"),
            &CancellationToken::new(),
        )
        .await
        .expect("inspection recomputes the applied result");

        let mut ranges: Vec<(String, u32, u32)> = inspected
            .hunks
            .into_iter()
            .map(|hunk| (hunk.path, hunk.start_line, hunk.line_count))
            .collect();
        ranges.sort();
        assert_eq!(
            ranges,
            vec![
                ("small.php".to_owned(), 2, 1),
                ("wide.php".to_owned(), 40_000, 1),
            ]
        );
    }

    #[tokio::test]
    async fn close_removes_a_git_initialization_locked_worktree() {
        let temporary = tempdir().expect("temporary repository");
        let repository = temporary.path().join("repository");
        fs::create_dir(&repository).expect("repository directory");
        git(&repository, &["init"]);
        git(
            &repository,
            &["config", "user.name", "Patchyard Factory test"],
        );
        git(
            &repository,
            &["config", "user.email", "factory-test@invalid.example"],
        );
        fs::write(repository.join("README"), "fixture\n").expect("fixture file");
        git(&repository, &["add", "README"]);
        git(&repository, &["commit", "-m", "fixture"]);

        let path = temporary.path().join("initializing");
        git(
            &repository,
            &[
                "worktree",
                "add",
                "--detach",
                "--lock",
                "--reason",
                "initializing",
                path.to_str().expect("UTF-8 temporary path"),
                "HEAD",
            ],
        );
        let worktree = DetachedWorktree {
            repository: repository.clone(),
            path: path.clone(),
            reviewed_sha: "0".repeat(40),
            closed: false,
        };

        worktree
            .close(&CancellationToken::new())
            .await
            .expect("two --force flags remove Git's initializing lock");
        assert!(!path.exists());
    }
}
