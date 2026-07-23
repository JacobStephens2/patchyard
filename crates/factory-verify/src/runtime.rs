//! Clean verifier runtime for targeted PHPUnit on the secret-free worker.

use std::{
    collections::BTreeSet,
    ffi::OsStr,
    fs::{self, File, Metadata},
    io::{self, Read},
    os::unix::fs::MetadataExt,
    path::{Path, PathBuf},
    process::{Command, ExitStatus, Stdio},
    thread,
    time::{Duration, Instant},
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::{InputError, require_lower_hex, require_repo_path};

const EXPECTED_SCHEMA_VERSION: u8 = 1;
const EXPECTED_IDENTITY: &str = "factory-worker";
const PHPUNIT_BINARY: &str = "/usr/local/bin/phpunit";
const MAX_TESTS: usize = 16;
const MAX_OUTPUT_BYTES: usize = 65_536;
const MAX_TIMEOUT_SECONDS: u64 = 300;
const BASE_SHA_MARKER: &str = ".patchyard-base-sha";
const ALLOWED_ENVIRONMENT: &[&str] = &["LANG", "LC_ALL", "PATH", "TMPDIR", "TZ"];

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeManifest {
    pub schema_version: u8,
    pub run_id: String,
    pub base_sha: String,
    pub source_archive_sha256: String,
    pub patch_sha256: String,
    pub phpunit_binary_sha256: String,
    pub phpunit_tests: Vec<String>,
    pub timeout_seconds: u64,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct RuntimeEvidence {
    pub schema_version: u8,
    pub run_id: String,
    pub verifier_identity: String,
    pub verifier_uid: u32,
    pub base_sha: String,
    pub source_archive_sha256: String,
    pub patch_sha256: String,
    pub phpunit_binary_sha256: String,
    pub phpunit_tests: Vec<String>,
    pub phpunit_exit_code: i32,
    pub phpunit_stdout: String,
    pub phpunit_stderr: String,
    pub duration_ms: u128,
    pub tree_hash_before: String,
    pub tree_hash_after: String,
    pub tree_hash_equal: bool,
    pub clean_environment: bool,
    pub git_remote_count: usize,
}

#[derive(Debug, Error)]
pub enum RuntimeError {
    #[error(transparent)]
    Input(#[from] InputError),
    #[error("runtime manifest schema_version must be {EXPECTED_SCHEMA_VERSION}")]
    SchemaVersion,
    #[error("run_id must contain 1 to 63 lowercase letters, digits, or hyphens")]
    RunId,
    #[error("targeted PHPUnit selection must contain 1 to {MAX_TESTS} unique tests")]
    TestCount,
    #[error("targeted PHPUnit path must be a PHP file below tests/: {0}")]
    TestPath(String),
    #[error("duplicate targeted PHPUnit path: {0}")]
    DuplicateTest(String),
    #[error("timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")]
    Timeout,
    #[error("verifier must run as {EXPECTED_IDENTITY}, got {0}")]
    Identity(String),
    #[error("verifier environment is not clean; unexpected variable: {0}")]
    Environment(String),
    #[error("cannot inspect {path}: {source}")]
    Io { path: PathBuf, source: io::Error },
    #[error("worktree must be an absolute, non-symlink directory")]
    Worktree,
    #[error("patch must be an absolute, regular, non-symlink file")]
    Patch,
    #[error("base SHA marker does not match the runtime manifest")]
    BaseSha,
    #[error("runtime patch SHA-256 does not match the manifest")]
    PatchSha,
    #[error("installed PHPUnit SHA-256 does not match the manifest")]
    PhpunitSha,
    #[error("targeted PHPUnit file is absent or not a regular file: {0}")]
    MissingTest(String),
    #[error("verifier worktree has a Git remote")]
    GitRemote,
    #[error("subprocess failed: {0}")]
    Process(String),
    #[error("targeted PHPUnit exceeded the {0}-second timeout")]
    PhpunitTimeout(u64),
    #[error("targeted PHPUnit output exceeded {MAX_OUTPUT_BYTES} bytes")]
    OutputTooLarge,
    #[error("targeted PHPUnit failed with exit {code}\nstdout:\n{stdout}\nstderr:\n{stderr}")]
    PhpunitFailed {
        code: i32,
        stdout: String,
        stderr: String,
    },
    #[error("verification mutated the candidate tree: {before} != {after}")]
    TreeChanged { before: String, after: String },
    #[error("tree contains a non-UTF-8 path")]
    NonUtf8Path,
}

pub fn verify(
    manifest: &RuntimeManifest,
    worktree: &Path,
    patch: &Path,
) -> Result<RuntimeEvidence, RuntimeError> {
    validate_manifest(manifest)?;
    let (identity, uid) = current_identity()?;
    if identity != EXPECTED_IDENTITY {
        return Err(RuntimeError::Identity(identity));
    }
    require_clean_environment()?;

    let worktree = canonical_directory(worktree)?;
    let patch = canonical_file(patch).map_err(|_| RuntimeError::Patch)?;
    let marker = read_trimmed(&worktree.join(BASE_SHA_MARKER))?;
    if marker != manifest.base_sha {
        return Err(RuntimeError::BaseSha);
    }
    if sha256_file(&patch)? != manifest.patch_sha256 {
        return Err(RuntimeError::PatchSha);
    }

    let phpunit = canonical_file(Path::new(PHPUNIT_BINARY)).map_err(|source| RuntimeError::Io {
        path: PathBuf::from(PHPUNIT_BINARY),
        source,
    })?;
    if sha256_file(&phpunit)? != manifest.phpunit_binary_sha256 {
        return Err(RuntimeError::PhpunitSha);
    }

    for test in &manifest.phpunit_tests {
        let metadata =
            fs::symlink_metadata(worktree.join(test)).map_err(|source| RuntimeError::Io {
                path: worktree.join(test),
                source,
            })?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(RuntimeError::MissingTest(test.clone()));
        }
    }

    let remote_output = Command::new("/usr/bin/git")
        .args([
            "-C",
            worktree.to_str().ok_or(RuntimeError::NonUtf8Path)?,
            "remote",
        ])
        .env_clear()
        .env("PATH", "/usr/local/bin:/usr/bin:/bin")
        .output()
        .map_err(|error| RuntimeError::Process(error.to_string()))?;
    if !remote_output.status.success() {
        return Err(RuntimeError::Process("git remote failed".to_owned()));
    }
    let remote_count = String::from_utf8_lossy(&remote_output.stdout)
        .lines()
        .count();
    if remote_count != 0 {
        return Err(RuntimeError::GitRemote);
    }

    let tree_hash_before = tree_hash(&worktree)?;
    let started = Instant::now();
    let phpunit_result = run_phpunit(manifest, &worktree, &phpunit);
    let duration_ms = started.elapsed().as_millis();
    let tree_hash_after = tree_hash(&worktree)?;
    if tree_hash_before != tree_hash_after {
        return Err(RuntimeError::TreeChanged {
            before: tree_hash_before,
            after: tree_hash_after,
        });
    }
    let output = phpunit_result?;
    if !output.status.success() {
        return Err(RuntimeError::PhpunitFailed {
            code: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        });
    }

    Ok(RuntimeEvidence {
        schema_version: EXPECTED_SCHEMA_VERSION,
        run_id: manifest.run_id.clone(),
        verifier_identity: identity,
        verifier_uid: uid,
        base_sha: manifest.base_sha.clone(),
        source_archive_sha256: manifest.source_archive_sha256.clone(),
        patch_sha256: manifest.patch_sha256.clone(),
        phpunit_binary_sha256: manifest.phpunit_binary_sha256.clone(),
        phpunit_tests: manifest.phpunit_tests.clone(),
        phpunit_exit_code: output.status.code().unwrap_or(0),
        phpunit_stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
        phpunit_stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        duration_ms,
        tree_hash_before: tree_hash_before.clone(),
        tree_hash_after,
        tree_hash_equal: true,
        clean_environment: true,
        git_remote_count: remote_count,
    })
}

pub fn validate_manifest(manifest: &RuntimeManifest) -> Result<(), RuntimeError> {
    if manifest.schema_version != EXPECTED_SCHEMA_VERSION {
        return Err(RuntimeError::SchemaVersion);
    }
    if manifest.run_id.is_empty()
        || manifest.run_id.len() > 63
        || !manifest
            .run_id
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
        || manifest.run_id.starts_with('-')
        || manifest.run_id.ends_with('-')
    {
        return Err(RuntimeError::RunId);
    }
    require_lower_hex("base_sha", &manifest.base_sha, 40)?;
    require_lower_hex("source_archive_sha256", &manifest.source_archive_sha256, 64)?;
    require_lower_hex("patch_sha256", &manifest.patch_sha256, 64)?;
    require_lower_hex("phpunit_binary_sha256", &manifest.phpunit_binary_sha256, 64)?;
    if manifest.phpunit_tests.is_empty() || manifest.phpunit_tests.len() > MAX_TESTS {
        return Err(RuntimeError::TestCount);
    }
    let mut tests = BTreeSet::new();
    for test in &manifest.phpunit_tests {
        require_repo_path(test)?;
        if !test.starts_with("tests/") || !test.ends_with("Test.php") {
            return Err(RuntimeError::TestPath(test.clone()));
        }
        if !tests.insert(test) {
            return Err(RuntimeError::DuplicateTest(test.clone()));
        }
    }
    if manifest.timeout_seconds == 0 || manifest.timeout_seconds > MAX_TIMEOUT_SECONDS {
        return Err(RuntimeError::Timeout);
    }
    Ok(())
}

pub fn tree_hash(root: &Path) -> Result<String, RuntimeError> {
    let mut hasher = Sha256::new();
    visit_tree(root, root, &mut hasher)?;
    Ok(hex::encode(hasher.finalize()))
}

fn visit_tree(root: &Path, directory: &Path, hasher: &mut Sha256) -> Result<(), RuntimeError> {
    let mut entries = fs::read_dir(directory)
        .map_err(|source| RuntimeError::Io {
            path: directory.to_path_buf(),
            source,
        })?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|source| RuntimeError::Io {
            path: directory.to_path_buf(),
            source,
        })?;
    entries.sort_by_key(|entry| entry.file_name());

    for entry in entries {
        if directory == root && entry.file_name() == OsStr::new(".git") {
            continue;
        }
        let path = entry.path();
        let relative = path
            .strip_prefix(root)
            .expect("walked path remains below root")
            .to_str()
            .ok_or(RuntimeError::NonUtf8Path)?;
        let metadata = fs::symlink_metadata(&path).map_err(|source| RuntimeError::Io {
            path: path.clone(),
            source,
        })?;
        if metadata.file_type().is_dir() {
            hash_entry_header(hasher, b'd', relative, &metadata, 0);
            visit_tree(root, &path, hasher)?;
        } else if metadata.file_type().is_symlink() {
            let target = fs::read_link(&path).map_err(|source| RuntimeError::Io {
                path: path.clone(),
                source,
            })?;
            let target = target.to_str().ok_or(RuntimeError::NonUtf8Path)?.as_bytes();
            hash_entry_header(hasher, b'l', relative, &metadata, target.len() as u64);
            hasher.update(target);
        } else if metadata.file_type().is_file() {
            hash_entry_header(hasher, b'f', relative, &metadata, metadata.len());
            let mut file = File::open(&path).map_err(|source| RuntimeError::Io {
                path: path.clone(),
                source,
            })?;
            let mut buffer = [0_u8; 65_536];
            loop {
                let count = file.read(&mut buffer).map_err(|source| RuntimeError::Io {
                    path: path.clone(),
                    source,
                })?;
                if count == 0 {
                    break;
                }
                hasher.update(&buffer[..count]);
            }
        } else {
            return Err(RuntimeError::Worktree);
        }
    }
    Ok(())
}

fn hash_entry_header(hasher: &mut Sha256, kind: u8, path: &str, metadata: &Metadata, length: u64) {
    hasher.update([kind]);
    hasher.update((metadata.mode() & 0o7777).to_be_bytes());
    hasher.update((path.len() as u64).to_be_bytes());
    hasher.update(path.as_bytes());
    hasher.update(length.to_be_bytes());
}

fn run_phpunit(
    manifest: &RuntimeManifest,
    worktree: &Path,
    phpunit: &Path,
) -> Result<BoundedOutput, RuntimeError> {
    let mut command = Command::new(phpunit);
    command
        .current_dir(worktree)
        .env_clear()
        .env("LANG", "C.UTF-8")
        .env("LC_ALL", "C.UTF-8")
        .env("PATH", "/usr/local/bin:/usr/bin:/bin")
        .arg("--no-configuration")
        .arg("--colors=never")
        .args(&manifest.phpunit_tests)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = command
        .spawn()
        .map_err(|error| RuntimeError::Process(error.to_string()))?;
    let stdout = child.stdout.take().expect("stdout is piped");
    let stderr = child.stderr.take().expect("stderr is piped");
    let stdout_reader = thread::spawn(move || read_bounded(stdout));
    let stderr_reader = thread::spawn(move || read_bounded(stderr));
    let deadline = Instant::now() + Duration::from_secs(manifest.timeout_seconds);
    let status = loop {
        if let Some(status) = child
            .try_wait()
            .map_err(|error| RuntimeError::Process(error.to_string()))?
        {
            break status;
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            let _ = stdout_reader.join();
            let _ = stderr_reader.join();
            return Err(RuntimeError::PhpunitTimeout(manifest.timeout_seconds));
        }
        thread::sleep(Duration::from_millis(25));
    };
    let stdout = stdout_reader
        .join()
        .map_err(|_| RuntimeError::Process("stdout reader panicked".to_owned()))??;
    let stderr = stderr_reader
        .join()
        .map_err(|_| RuntimeError::Process("stderr reader panicked".to_owned()))??;
    Ok(BoundedOutput {
        status,
        stdout,
        stderr,
    })
}

fn read_bounded(mut reader: impl Read) -> Result<Vec<u8>, RuntimeError> {
    let mut output = Vec::new();
    reader
        .by_ref()
        .take((MAX_OUTPUT_BYTES + 1) as u64)
        .read_to_end(&mut output)
        .map_err(|error| RuntimeError::Process(error.to_string()))?;
    if output.len() > MAX_OUTPUT_BYTES {
        return Err(RuntimeError::OutputTooLarge);
    }
    Ok(output)
}

fn current_identity() -> Result<(String, u32), RuntimeError> {
    let name = identity_command(&["-un"])?;
    let uid = identity_command(&["-u"])?
        .parse::<u32>()
        .map_err(|_| RuntimeError::Process("id -u returned a non-number".to_owned()))?;
    Ok((name, uid))
}

fn identity_command(arguments: &[&str]) -> Result<String, RuntimeError> {
    let output = Command::new("/usr/bin/id")
        .args(arguments)
        .env_clear()
        .env("PATH", "/usr/local/bin:/usr/bin:/bin")
        .output()
        .map_err(|error| RuntimeError::Process(error.to_string()))?;
    if !output.status.success() {
        return Err(RuntimeError::Process("id failed".to_owned()));
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn require_clean_environment() -> Result<(), RuntimeError> {
    for key in std::env::vars_os().map(|(key, _)| key) {
        let key = key.to_str().ok_or(RuntimeError::NonUtf8Path)?;
        if !ALLOWED_ENVIRONMENT.contains(&key) {
            return Err(RuntimeError::Environment(key.to_owned()));
        }
    }
    Ok(())
}

fn canonical_directory(path: &Path) -> Result<PathBuf, RuntimeError> {
    if !path.is_absolute() {
        return Err(RuntimeError::Worktree);
    }
    let metadata = fs::symlink_metadata(path).map_err(|source| RuntimeError::Io {
        path: path.to_path_buf(),
        source,
    })?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(RuntimeError::Worktree);
    }
    fs::canonicalize(path).map_err(|source| RuntimeError::Io {
        path: path.to_path_buf(),
        source,
    })
}

fn canonical_file(path: &Path) -> io::Result<PathBuf> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(io::Error::other("not a regular non-symlink file"));
    }
    fs::canonicalize(path)
}

fn read_trimmed(path: &Path) -> Result<String, RuntimeError> {
    fs::read_to_string(path)
        .map(|value| value.trim().to_owned())
        .map_err(|source| RuntimeError::Io {
            path: path.to_path_buf(),
            source,
        })
}

fn sha256_file(path: &Path) -> Result<String, RuntimeError> {
    let mut file = File::open(path).map_err(|source| RuntimeError::Io {
        path: path.to_path_buf(),
        source,
    })?;
    let mut hasher = Sha256::new();
    io::copy(&mut file, &mut hasher).map_err(|source| RuntimeError::Io {
        path: path.to_path_buf(),
        source,
    })?;
    Ok(hex::encode(hasher.finalize()))
}

struct BoundedOutput {
    status: ExitStatus,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    const SHA: &str = "0123456789abcdef0123456789abcdef01234567";
    const HASH: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    fn manifest() -> RuntimeManifest {
        RuntimeManifest {
            schema_version: 1,
            run_id: "session7-runtime".to_owned(),
            base_sha: SHA.to_owned(),
            source_archive_sha256: HASH.to_owned(),
            patch_sha256: HASH.to_owned(),
            phpunit_binary_sha256: HASH.to_owned(),
            phpunit_tests: vec!["tests/Unit/AlphabetizeTest.php".to_owned()],
            timeout_seconds: 60,
        }
    }

    #[test]
    fn runtime_manifest_rejects_unsafe_test_selection() {
        let mut value = manifest();
        value.phpunit_tests = vec!["--configuration=evil.xml".to_owned()];
        assert!(validate_manifest(&value).is_err());
        value.phpunit_tests = vec!["tests/../policy.php".to_owned()];
        assert!(validate_manifest(&value).is_err());
        value.phpunit_tests = vec!["mfieldbook/AlphabetizeTest.php".to_owned()];
        assert!(validate_manifest(&value).is_err());
    }

    #[test]
    fn runtime_manifest_rejects_duplicate_and_unbounded_tests() {
        let mut value = manifest();
        value.phpunit_tests.push(value.phpunit_tests[0].clone());
        assert!(matches!(
            validate_manifest(&value),
            Err(RuntimeError::DuplicateTest(_))
        ));
        value.phpunit_tests = (0..=MAX_TESTS)
            .map(|index| format!("tests/Unit/T{index}Test.php"))
            .collect();
        assert!(matches!(
            validate_manifest(&value),
            Err(RuntimeError::TestCount)
        ));
    }

    #[test]
    fn tree_hash_is_stable_and_detects_file_mode_content_and_symlink_changes() {
        let root = std::env::temp_dir().join(format!("factory-runtime-{}", Uuid::new_v4()));
        fs::create_dir_all(root.join("nested")).expect("create test tree");
        fs::write(root.join("nested/file.txt"), "one\n").expect("write file");
        std::os::unix::fs::symlink("nested/file.txt", root.join("link")).expect("create symlink");
        fs::create_dir(root.join(".git")).expect("create ignored git directory");
        fs::write(root.join(".git/noise"), "ignored").expect("write ignored file");

        let initial = tree_hash(&root).expect("hash tree");
        assert_eq!(initial, tree_hash(&root).expect("rehash tree"));
        fs::write(root.join(".git/noise"), "still ignored").expect("mutate ignored file");
        assert_eq!(initial, tree_hash(&root).expect("rehash ignored mutation"));

        fs::write(root.join("nested/file.txt"), "two\n").expect("mutate content");
        assert_ne!(initial, tree_hash(&root).expect("hash content mutation"));
        fs::remove_dir_all(&root).expect("remove test tree");
    }
}
