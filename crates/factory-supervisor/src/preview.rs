//! Exact-SHA preview leases through the credential-free forced SSH bridge.

use std::{ffi::OsString, future::Future, path::PathBuf, pin::Pin, time::Duration};

use serde::{Deserialize, Serialize};
use thiserror::Error;
use tokio_util::sync::CancellationToken;

use crate::{
    child::PreviewBearer,
    process::{ProcessError, ProcessSpec, run_bounded},
};

const MAX_PREVIEW_OUTPUT: usize = 256 * 1024;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreviewLease {
    pub ok: bool,
    pub slot: u8,
    pub url: String,
    pub lease_id: String,
    pub owner: String,
    pub request_id: String,
    pub expected_sha: String,
    pub host_head: String,
    pub preview_head: String,
    pub expires_at: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreviewVerification {
    pub ok: bool,
    pub slot: u8,
    pub lease_id: String,
    pub expected_sha: String,
    pub host_head: String,
    pub preview_head: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreviewAuthorization {
    pub ok: bool,
    pub slot: u8,
    pub lease_id: String,
    pub expected_sha: String,
    pub bearer: PreviewBearer,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreviewLogScan {
    pub ok: bool,
    pub slot: u8,
    pub lease_id: String,
    pub sources: u32,
    pub bytes_scanned: u64,
    pub matches: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreviewRelease {
    pub ok: bool,
    pub slot: u8,
    pub lease_id: String,
    pub cleanup_complete: bool,
    pub cleanup_errors: Vec<String>,
    #[serde(default)]
    pub already_absent: bool,
}

pub type PreviewFuture<'a, T> = Pin<Box<dyn Future<Output = Result<T, PreviewError>> + Send + 'a>>;

pub trait PreviewApi: Send + Sync {
    fn acquire<'a>(
        &'a self,
        request_id: &'a str,
        branch: &'a str,
        expected_sha: &'a str,
        lease_id: &'a str,
        cancellation: &'a CancellationToken,
    ) -> PreviewFuture<'a, PreviewLease>;

    fn verify<'a>(
        &'a self,
        lease: &'a PreviewLease,
        cancellation: &'a CancellationToken,
    ) -> PreviewFuture<'a, PreviewVerification>;

    fn authorize<'a>(
        &'a self,
        lease: &'a PreviewLease,
        expected_sha: &'a str,
        capability_id: &'a str,
        cancellation: &'a CancellationToken,
    ) -> PreviewFuture<'a, PreviewAuthorization>;

    fn scan_logs<'a>(
        &'a self,
        lease: &'a PreviewLease,
        cancellation: &'a CancellationToken,
    ) -> PreviewFuture<'a, PreviewLogScan>;

    fn release<'a>(
        &'a self,
        lease: &'a PreviewLease,
        cancellation: &'a CancellationToken,
    ) -> PreviewFuture<'a, PreviewRelease>;
}

#[derive(Clone, Debug)]
pub struct ProcessPreviewConfig {
    pub ssh_program: PathBuf,
    pub ssh_config: PathBuf,
    pub ssh_host: String,
    pub home: PathBuf,
    pub owner: String,
    pub lease_ttl: Duration,
    pub capability_ttl: Duration,
    pub command_timeout: Duration,
}

#[derive(Clone, Debug)]
pub struct ProcessPreview {
    config: ProcessPreviewConfig,
}

impl ProcessPreview {
    pub fn new(config: ProcessPreviewConfig) -> Result<Self, PreviewError> {
        if !valid_name(&config.ssh_host)
            || !valid_name(&config.owner)
            || config.lease_ttl < Duration::from_secs(60)
            || config.lease_ttl > Duration::from_secs(3_600)
            || config.capability_ttl < Duration::from_secs(30)
            || config.capability_ttl > Duration::from_secs(300)
            || config.command_timeout.is_zero()
            || config.command_timeout > Duration::from_secs(3_600)
        {
            return Err(PreviewError::InvalidConfig);
        }
        Ok(Self { config })
    }

    async fn json<T: for<'de> Deserialize<'de>>(
        &self,
        arguments: Vec<OsString>,
        cancellation: &CancellationToken,
    ) -> Result<T, PreviewError> {
        let mut spec = ProcessSpec::new(&self.config.ssh_program);
        spec.args = vec![
            OsString::from("-F"),
            self.config.ssh_config.as_os_str().to_owned(),
            OsString::from(&self.config.ssh_host),
        ];
        spec.args.extend(arguments);
        spec.environment = vec![
            (
                OsString::from("HOME"),
                self.config.home.as_os_str().to_owned(),
            ),
            (OsString::from("LANG"), OsString::from("C.UTF-8")),
        ];
        spec.timeout = self.config.command_timeout;
        spec.output_limit = MAX_PREVIEW_OUTPUT;
        let output = run_bounded(&spec, cancellation).await?;
        if output.code != 0 {
            let message = serde_json::from_slice::<FailureEnvelope>(&output.stdout)
                .ok()
                .map(|value| value.error)
                .unwrap_or_else(|| "preview bridge rejected the operation".to_owned());
            return Err(PreviewError::Bridge(message));
        }
        Ok(serde_json::from_slice(&output.stdout)?)
    }
}

impl PreviewApi for ProcessPreview {
    fn acquire<'a>(
        &'a self,
        request_id: &'a str,
        branch: &'a str,
        expected_sha: &'a str,
        lease_id: &'a str,
        cancellation: &'a CancellationToken,
    ) -> PreviewFuture<'a, PreviewLease> {
        Box::pin(async move {
            validate_request(request_id, branch, expected_sha, lease_id)?;
            let lease: PreviewLease = self
                .json(
                    vec![
                        OsString::from("acquire"),
                        OsString::from("--owner"),
                        OsString::from(&self.config.owner),
                        OsString::from("--request-id"),
                        OsString::from(request_id),
                        OsString::from("--branch"),
                        OsString::from(branch),
                        OsString::from("--expected-sha"),
                        OsString::from(expected_sha),
                        OsString::from("--lease-id"),
                        OsString::from(lease_id),
                        OsString::from("--ttl-seconds"),
                        OsString::from(self.config.lease_ttl.as_secs().to_string()),
                    ],
                    cancellation,
                )
                .await?;
            if !lease.ok
                || lease.owner != self.config.owner
                || lease.request_id != request_id
                || lease.expected_sha != expected_sha
                || lease.lease_id != lease_id
                || lease.host_head != expected_sha
                || lease.preview_head != expected_sha
                || lease.url != format!("https://{}.preview.example.dev", lease.slot)
                || !(1..=30).contains(&lease.slot)
            {
                return Err(PreviewError::MalformedResponse);
            }
            Ok(lease)
        })
    }

    fn verify<'a>(
        &'a self,
        lease: &'a PreviewLease,
        cancellation: &'a CancellationToken,
    ) -> PreviewFuture<'a, PreviewVerification> {
        Box::pin(async move {
            let proof: PreviewVerification = self
                .json(
                    vec![
                        OsString::from("verify"),
                        OsString::from("--slot"),
                        OsString::from(lease.slot.to_string()),
                        OsString::from("--lease-id"),
                        OsString::from(&lease.lease_id),
                    ],
                    cancellation,
                )
                .await?;
            if !proof.ok
                || proof.slot != lease.slot
                || proof.lease_id != lease.lease_id
                || proof.expected_sha != lease.expected_sha
                || proof.host_head != lease.expected_sha
                || proof.preview_head != lease.expected_sha
            {
                return Err(PreviewError::ShaChanged);
            }
            Ok(proof)
        })
    }

    fn authorize<'a>(
        &'a self,
        lease: &'a PreviewLease,
        expected_sha: &'a str,
        capability_id: &'a str,
        cancellation: &'a CancellationToken,
    ) -> PreviewFuture<'a, PreviewAuthorization> {
        Box::pin(async move {
            if expected_sha != lease.expected_sha
                || capability_id.len() != 32
                || !lower_hex(capability_id)
            {
                return Err(PreviewError::InvalidInput);
            }
            let authorization: PreviewAuthorization = self
                .json(
                    vec![
                        OsString::from("authorize"),
                        OsString::from("--slot"),
                        OsString::from(lease.slot.to_string()),
                        OsString::from("--lease-id"),
                        OsString::from(&lease.lease_id),
                        OsString::from("--expected-sha"),
                        OsString::from(expected_sha),
                        OsString::from("--capability-id"),
                        OsString::from(capability_id),
                        OsString::from("--ttl-seconds"),
                        OsString::from(self.config.capability_ttl.as_secs().to_string()),
                    ],
                    cancellation,
                )
                .await?;
            if !authorization.ok
                || authorization.slot != lease.slot
                || authorization.lease_id != lease.lease_id
                || authorization.expected_sha != expected_sha
                || authorization.bearer.capability_id != capability_id
                || authorization.bearer.lease_id != lease.lease_id
            {
                return Err(PreviewError::MalformedResponse);
            }
            Ok(authorization)
        })
    }

    fn scan_logs<'a>(
        &'a self,
        lease: &'a PreviewLease,
        cancellation: &'a CancellationToken,
    ) -> PreviewFuture<'a, PreviewLogScan> {
        Box::pin(async move {
            let scan: PreviewLogScan = self
                .json(
                    vec![
                        OsString::from("scan-logs"),
                        OsString::from("--slot"),
                        OsString::from(lease.slot.to_string()),
                        OsString::from("--lease-id"),
                        OsString::from(&lease.lease_id),
                    ],
                    cancellation,
                )
                .await?;
            if !scan.ok
                || scan.slot != lease.slot
                || scan.lease_id != lease.lease_id
                || scan.sources == 0
            {
                return Err(PreviewError::MalformedResponse);
            }
            if scan.matches != 0 {
                return Err(PreviewError::SecretInLogs(scan.matches));
            }
            Ok(scan)
        })
    }

    fn release<'a>(
        &'a self,
        lease: &'a PreviewLease,
        cancellation: &'a CancellationToken,
    ) -> PreviewFuture<'a, PreviewRelease> {
        Box::pin(async move {
            let release: PreviewRelease = self
                .json(
                    vec![
                        OsString::from("release"),
                        OsString::from("--slot"),
                        OsString::from(lease.slot.to_string()),
                        OsString::from("--lease-id"),
                        OsString::from(&lease.lease_id),
                    ],
                    cancellation,
                )
                .await?;
            if !release.ok
                || release.slot != lease.slot
                || release.lease_id != lease.lease_id
                || !release.cleanup_complete
                || !release.cleanup_errors.is_empty()
            {
                return Err(PreviewError::CleanupFailed);
            }
            Ok(release)
        })
    }
}

fn validate_request(
    request_id: &str,
    branch: &str,
    expected_sha: &str,
    lease_id: &str,
) -> Result<(), PreviewError> {
    if !valid_name(request_id)
        || branch.is_empty()
        || branch.len() > 200
        || branch.contains("..")
        || !branch
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'/' | b'-'))
        || expected_sha.len() != 40
        || !lower_hex(expected_sha)
        || lease_id.len() != 32
        || !lower_hex(lease_id)
    {
        return Err(PreviewError::InvalidInput);
    }
    Ok(())
}

fn valid_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 63
        && value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
        && value.as_bytes()[0].is_ascii_alphanumeric()
}

fn lower_hex(value: &str) -> bool {
    value
        .bytes()
        .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

#[derive(Debug, Deserialize)]
struct FailureEnvelope {
    error: String,
}

#[derive(Debug, Error)]
pub enum PreviewError {
    #[error("preview client configuration is invalid")]
    InvalidConfig,
    #[error("preview request is invalid")]
    InvalidInput,
    #[error("preview bridge returned a malformed response")]
    MalformedResponse,
    #[error("preview exact-SHA verification changed")]
    ShaChanged,
    #[error("preview logs contain {0} bearer-material matches")]
    SecretInLogs(u32),
    #[error("preview lease cleanup failed")]
    CleanupFailed,
    #[error("preview bridge failed: {0}")]
    Bridge(String),
    #[error("preview bridge JSON failed: {0}")]
    Json(#[from] serde_json::Error),
    #[error("preview bridge process failed: {0}")]
    Process(#[from] ProcessError),
}
