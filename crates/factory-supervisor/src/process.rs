//! Bounded, cancellation-aware subprocess execution.

use std::{ffi::OsString, path::PathBuf, process::Stdio, time::Duration};

use thiserror::Error;
use tokio::{
    io::{AsyncRead, AsyncReadExt as _},
    process::Command,
    task::JoinHandle,
    time::{Instant, sleep_until},
};
use tokio_util::sync::CancellationToken;

/// One argument-vector invocation. Shell parsing is never involved.
#[derive(Clone, Debug)]
pub struct ProcessSpec {
    pub program: PathBuf,
    pub args: Vec<OsString>,
    pub current_dir: Option<PathBuf>,
    pub environment: Vec<(OsString, OsString)>,
    pub timeout: Duration,
    pub output_limit: usize,
}

impl ProcessSpec {
    #[must_use]
    pub fn new(program: impl Into<PathBuf>) -> Self {
        Self {
            program: program.into(),
            args: Vec::new(),
            current_dir: None,
            environment: Vec::new(),
            timeout: Duration::from_secs(300),
            output_limit: 4 * 1024 * 1024,
        }
    }
}

/// Complete bounded process result. Both streams are retained for A83.
#[derive(Clone, Debug)]
pub struct ProcessOutput {
    pub code: i32,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub duration: Duration,
}

impl ProcessOutput {
    /// Stable full-harness transcript representation. It is persisted as an
    /// artifact and never placed in another agent's packet.
    #[must_use]
    pub fn transcript(&self) -> Vec<u8> {
        let mut transcript = Vec::with_capacity(self.stdout.len() + self.stderr.len() + 80);
        transcript.extend_from_slice(b"--- stdout ---\n");
        transcript.extend_from_slice(&self.stdout);
        if !self.stdout.ends_with(b"\n") {
            transcript.push(b'\n');
        }
        transcript.extend_from_slice(b"--- stderr ---\n");
        transcript.extend_from_slice(&self.stderr);
        if !self.stderr.ends_with(b"\n") {
            transcript.push(b'\n');
        }
        transcript
    }
}

/// Run one child and explicitly kill/reap it on timeout or cancellation.
pub async fn run_bounded(
    spec: &ProcessSpec,
    cancellation: &CancellationToken,
) -> Result<ProcessOutput, ProcessError> {
    if spec.output_limit == 0 || spec.output_limit > 16 * 1024 * 1024 {
        return Err(ProcessError::InvalidOutputLimit);
    }
    if spec.timeout.is_zero() || spec.timeout > Duration::from_secs(3_600) {
        return Err(ProcessError::InvalidTimeout);
    }

    let started = Instant::now();
    let mut command = Command::new(&spec.program);
    command
        .args(&spec.args)
        .env_clear()
        .env("PATH", "/usr/local/bin:/usr/bin:/bin")
        .envs(spec.environment.iter().cloned())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    if let Some(directory) = &spec.current_dir {
        command.current_dir(directory);
    }
    let mut child = command.spawn().map_err(|source| ProcessError::Spawn {
        program: spec.program.clone(),
        source,
    })?;
    let stdout = child.stdout.take().ok_or(ProcessError::MissingPipe)?;
    let stderr = child.stderr.take().ok_or(ProcessError::MissingPipe)?;
    let stdout_task = tokio::spawn(read_bounded(stdout, spec.output_limit));
    let stderr_task = tokio::spawn(read_bounded(stderr, spec.output_limit));
    let deadline = sleep_until(started + spec.timeout);
    tokio::pin!(deadline);

    // Cancellation audit: Child::wait, Sleep, and CancellationToken::cancelled
    // are cancellation-safe. The losing wait future holds no data buffer or
    // queue position. Stream readers live in owned tasks and are not cancelled.
    let termination = tokio::select! {
        status = child.wait() => Termination::Exited(status?),
        () = cancellation.cancelled() => Termination::Cancelled,
        () = &mut deadline => Termination::TimedOut,
    };

    let (status, terminal_error) = match termination {
        Termination::Exited(status) => (status, None),
        Termination::Cancelled => {
            child.kill().await?;
            (child.wait().await?, Some(ProcessError::Cancelled))
        }
        Termination::TimedOut => {
            child.kill().await?;
            (
                child.wait().await?,
                Some(ProcessError::TimedOut(spec.timeout)),
            )
        }
    };
    let stdout = join_reader(stdout_task).await?;
    let stderr = join_reader(stderr_task).await?;
    if stdout.overflow || stderr.overflow {
        return Err(ProcessError::OutputLimit {
            stdout: stdout.bytes.len(),
            stderr: stderr.bytes.len(),
            limit: spec.output_limit,
        });
    }
    if let Some(error) = terminal_error {
        return Err(error);
    }
    Ok(ProcessOutput {
        code: status.code().unwrap_or(-1),
        stdout: stdout.bytes,
        stderr: stderr.bytes,
        duration: started.elapsed(),
    })
}

enum Termination {
    Exited(std::process::ExitStatus),
    Cancelled,
    TimedOut,
}

struct BoundedBytes {
    bytes: Vec<u8>,
    overflow: bool,
}

async fn read_bounded(
    mut reader: impl AsyncRead + Unpin,
    limit: usize,
) -> Result<BoundedBytes, std::io::Error> {
    let mut bytes = Vec::with_capacity(limit.min(64 * 1024));
    let mut buffer = [0_u8; 8192];
    let mut overflow = false;
    loop {
        let read = reader.read(&mut buffer).await?;
        if read == 0 {
            break;
        }
        let remaining = limit.saturating_sub(bytes.len());
        let retained = remaining.min(read);
        bytes.extend_from_slice(&buffer[..retained]);
        overflow |= retained < read;
        // Keep draining after the cap so a child cannot deadlock on a full pipe.
    }
    Ok(BoundedBytes { bytes, overflow })
}

async fn join_reader(
    task: JoinHandle<Result<BoundedBytes, std::io::Error>>,
) -> Result<BoundedBytes, ProcessError> {
    task.await
        .map_err(ProcessError::ReaderJoin)?
        .map_err(ProcessError::Io)
}

#[derive(Debug, Error)]
pub enum ProcessError {
    #[error("subprocess output limit is invalid")]
    InvalidOutputLimit,
    #[error("subprocess timeout is invalid")]
    InvalidTimeout,
    #[error("could not spawn {program}: {source}")]
    Spawn {
        program: PathBuf,
        source: std::io::Error,
    },
    #[error("subprocess pipe was not created")]
    MissingPipe,
    #[error("subprocess I/O failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("subprocess reader task failed: {0}")]
    ReaderJoin(tokio::task::JoinError),
    #[error("subprocess timed out after {0:?}")]
    TimedOut(Duration),
    #[error("subprocess was cancelled")]
    Cancelled,
    #[error("subprocess exceeded output cap {limit}: stdout={stdout}, stderr={stderr}")]
    OutputLimit {
        stdout: usize,
        stderr: usize,
        limit: usize,
    },
}

#[cfg(test)]
mod tests {
    use std::{ffi::OsString, path::PathBuf, time::Duration};

    use tokio_util::sync::CancellationToken;

    use super::{ProcessError, ProcessSpec, run_bounded};

    #[tokio::test]
    async fn cancellation_kills_and_reaps_child() {
        let marker = std::env::temp_dir().join(format!("factory-child-{}", uuid::Uuid::new_v4()));
        let mut spec = ProcessSpec::new("/bin/sh");
        spec.args = vec![
            OsString::from("-c"),
            OsString::from("printf '%s' \"$$\" > \"$1\"; exec sleep 30"),
            OsString::from("factory-process-test"),
            marker.clone().into_os_string(),
        ];
        spec.timeout = Duration::from_secs(5);
        let token = CancellationToken::new();
        let cancelling = token.clone();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(100)).await;
            cancelling.cancel();
        });
        let result = run_bounded(&spec, &token).await;
        assert!(matches!(result, Err(ProcessError::Cancelled)));
        let pid = std::fs::read_to_string(&marker).expect("child wrote pid");
        assert!(!PathBuf::from(format!("/proc/{}", pid.trim())).exists());
        std::fs::remove_file(marker).expect("remove marker");
    }
}
