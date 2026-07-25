//! Exact bearer-material scans over bounded control-plane log sources.

use std::{
    ffi::OsString,
    future::Future,
    os::unix::fs::{OpenOptionsExt as _, PermissionsExt as _},
    path::{Path, PathBuf},
    pin::Pin,
    time::Duration,
};

use serde::{Deserialize, Serialize};
use thiserror::Error;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use crate::process::{ProcessError, ProcessSpec, run_bounded};

const MAX_SCAN_OUTPUT: usize = 64 * 1024;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SecretScan {
    pub schema_version: u16,
    pub sources: u32,
    pub bytes_scanned: u64,
    pub matches: u32,
}

pub type SecretScanFuture<'a> =
    Pin<Box<dyn Future<Output = Result<SecretScan, SecretScanError>> + Send + 'a>>;

pub trait SecretScanApi: Send + Sync {
    fn scan<'a>(
        &'a self,
        secret: &'a str,
        capability_id: &'a str,
        since_unix: i64,
        cancellation: &'a CancellationToken,
    ) -> SecretScanFuture<'a>;
}

#[derive(Clone, Debug)]
pub struct ProcessSecretScanner {
    program: PathBuf,
    scratch: PathBuf,
    timeout: Duration,
}

impl ProcessSecretScanner {
    pub fn new(
        program: PathBuf,
        scratch: PathBuf,
        timeout: Duration,
    ) -> Result<Self, SecretScanError> {
        if timeout.is_zero() || timeout > Duration::from_secs(120) {
            return Err(SecretScanError::InvalidConfig);
        }
        Ok(Self {
            program,
            scratch,
            timeout,
        })
    }

    async fn scan_inner(
        &self,
        secret: &str,
        capability_id: &str,
        since_unix: i64,
        cancellation: &CancellationToken,
    ) -> Result<SecretScan, SecretScanError> {
        if secret.len() < 16
            || secret.len() > 8192
            || secret.contains(['\r', '\n'])
            || capability_id.len() < 8
            || capability_id.len() > 128
            || since_unix <= 0
        {
            return Err(SecretScanError::InvalidInput);
        }
        let needles = format!("{secret}\n{capability_id}\n");
        let file = PrivateNeedles::create(&self.scratch, needles.into_bytes()).await?;
        let mut spec = ProcessSpec::new(&self.program);
        spec.args = vec![
            OsString::from("--needles-file"),
            file.path().as_os_str().to_owned(),
            OsString::from("--since-unix"),
            OsString::from(since_unix.to_string()),
        ];
        spec.timeout = self.timeout;
        spec.output_limit = MAX_SCAN_OUTPUT;
        let process = run_bounded(&spec, cancellation).await;
        let cleanup = file.close().await;
        let process = match (process, cleanup) {
            (Ok(output), Ok(())) => output,
            (Err(error), Ok(())) => return Err(error.into()),
            (_, Err(error)) => return Err(error),
        };
        let scan: SecretScan = serde_json::from_slice(&process.stdout)?;
        if scan.schema_version != 1 || scan.sources == 0 {
            return Err(SecretScanError::MalformedResult);
        }
        if scan.matches != 0 {
            return Err(SecretScanError::SecretFound(scan.matches));
        }
        if process.code != 0 {
            return Err(SecretScanError::ScannerExit(process.code));
        }
        Ok(scan)
    }
}

impl SecretScanApi for ProcessSecretScanner {
    fn scan<'a>(
        &'a self,
        secret: &'a str,
        capability_id: &'a str,
        since_unix: i64,
        cancellation: &'a CancellationToken,
    ) -> SecretScanFuture<'a> {
        Box::pin(self.scan_inner(secret, capability_id, since_unix, cancellation))
    }
}

struct PrivateNeedles {
    path: PathBuf,
    closed: bool,
}

impl PrivateNeedles {
    async fn create(root: &Path, bytes: Vec<u8>) -> Result<Self, SecretScanError> {
        let root = root.to_path_buf();
        let path = tokio::task::spawn_blocking(move || {
            std::fs::create_dir_all(&root)?;
            let metadata = std::fs::symlink_metadata(&root)?;
            if !metadata.is_dir() || metadata.file_type().is_symlink() {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    "secret-scan root is unsafe",
                ));
            }
            std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o700))?;
            let path = root.join(format!("evidence-log-needles-{}", Uuid::new_v4()));
            let mut options = std::fs::OpenOptions::new();
            options.write(true).create_new(true).mode(0o600);
            use std::io::Write as _;
            let mut file = options.open(&path)?;
            file.write_all(&bytes)?;
            file.sync_all()?;
            Ok::<_, std::io::Error>(path)
        })
        .await
        .map_err(SecretScanError::Join)??;
        Ok(Self {
            path,
            closed: false,
        })
    }

    fn path(&self) -> &Path {
        &self.path
    }

    async fn close(mut self) -> Result<(), SecretScanError> {
        let path = self.path.clone();
        tokio::task::spawn_blocking(move || match std::fs::remove_file(path) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error),
        })
        .await
        .map_err(SecretScanError::Join)??;
        self.closed = true;
        Ok(())
    }
}

impl Drop for PrivateNeedles {
    fn drop(&mut self) {
        if !self.closed {
            tracing::error!(
                path = %self.path.display(),
                "evidence log needles dropped without explicit close"
            );
        }
    }
}

#[derive(Debug, Error)]
pub enum SecretScanError {
    #[error("secret scanner configuration is invalid")]
    InvalidConfig,
    #[error("secret scanner input is invalid")]
    InvalidInput,
    #[error("secret scanner returned a malformed result")]
    MalformedResult,
    #[error("secret scanner found {0} bearer-material matches")]
    SecretFound(u32),
    #[error("secret scanner exited with status {0}")]
    ScannerExit(i32),
    #[error("secret scanner JSON failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("secret scanner process failed: {0}")]
    Process(#[from] ProcessError),
    #[error("secret scanner filesystem failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("secret scanner blocking task failed: {0}")]
    Join(tokio::task::JoinError),
}
