//! Fixed live qualification entry point for A89/A104.
//!
//! This binary has no database or GitHub configuration. It invokes the same
//! `EvidenceCapture` and `IsolatedChildSpawner` used by the supervisor, under a
//! fixed systemd unit with the supervisor's hardening.

use std::{
    fs,
    io::{self, Read as _, Write as _},
    os::unix::fs::{OpenOptionsExt as _, PermissionsExt as _},
    path::{Path, PathBuf},
    time::Duration,
};

use factory_supervisor::{
    artifacts::{ArtifactStore, StoredArtifact},
    child::{
        ChildSpawnConfig, ChildTerminal, EvidenceContract, IsolatedChildSpawner, PreviewBearer,
    },
    evidence::EvidenceCapture,
};
use serde::{Deserialize, Serialize};
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

const INPUT: &str = "/run/patchyard-evidence-qualification/input.json";
const RESULT: &str = "/run/patchyard-evidence-qualification/result.json";
const ARTIFACT_ROOT: &str = "/var/lib/patchyard/artifacts";
const MAX_INPUT_BYTES: u64 = 64 * 1024;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct QualificationInput {
    schema_version: u16,
    request_id: Uuid,
    run_id: Uuid,
    contract: EvidenceContract,
    bearer: PreviewBearer,
}

#[derive(Debug, Serialize)]
struct QualificationResult {
    schema_version: u16,
    ok: bool,
    request_id: Uuid,
    run_id: Uuid,
    artifacts: Vec<StoredArtifact>,
    terminal: ChildTerminal,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let input = consume_input(Path::new(INPUT))?;
    if input.schema_version != 1 {
        return Err("unsupported qualification input schema".into());
    }
    remove_existing_result(Path::new(RESULT))?;
    let spawner = IsolatedChildSpawner::new(ChildSpawnConfig {
        spawn_program: PathBuf::from("/usr/local/libexec/patchyard-spawn-child"),
        cancel_program: PathBuf::from("/usr/local/libexec/patchyard-cancel-child"),
        staging_root: PathBuf::from("/run/patchyard-children"),
        timeout: Duration::from_secs(90),
    });
    let artifacts = ArtifactStore::open(ARTIFACT_ROOT)?;
    let capture = EvidenceCapture::new(spawner, artifacts);
    let cancellation = CancellationToken::new();
    let signal_cancellation = cancellation.clone();
    let signal = tokio::spawn(async move {
        wait_for_shutdown().await;
        signal_cancellation.cancel();
    });
    let outcome = capture
        .capture_with_execution(
            input.request_id,
            input.run_id,
            input.contract,
            input.bearer,
            &cancellation,
        )
        .await;
    signal.abort();
    let _signal_result = signal.await;
    let outcome = outcome?;
    write_result(
        Path::new(RESULT),
        &QualificationResult {
            schema_version: 1,
            ok: true,
            request_id: input.request_id,
            run_id: input.run_id,
            artifacts: outcome.artifacts,
            terminal: outcome.terminal,
        },
    )?;
    Ok(())
}

fn consume_input(path: &Path) -> Result<QualificationInput, Box<dyn std::error::Error>> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file()
        || metadata.file_type().is_symlink()
        || metadata.permissions().mode() & 0o7777 != 0o600
        || metadata.len() == 0
        || metadata.len() > MAX_INPUT_BYTES
    {
        let _remove_result = fs::remove_file(path);
        return Err("unsafe qualification input".into());
    }
    let mut bytes = Vec::with_capacity(usize::try_from(metadata.len())?);
    let read_result = fs::File::open(path).and_then(|file| {
        file.take(MAX_INPUT_BYTES + 1)
            .read_to_end(&mut bytes)
            .map(|_| ())
    });
    let remove_result = fs::remove_file(path);
    read_result?;
    remove_result?;
    if u64::try_from(bytes.len())? > MAX_INPUT_BYTES {
        return Err("qualification input exceeds fixed bound".into());
    }
    Ok(serde_json::from_slice(&bytes)?)
}

fn remove_existing_result(path: &Path) -> io::Result<()> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error),
    }
}

fn write_result(
    path: &Path,
    value: &QualificationResult,
) -> Result<(), Box<dyn std::error::Error>> {
    let bytes = serde_json::to_vec(value)?;
    let temporary = path.with_extension(format!("{}.tmp", Uuid::new_v4().simple()));
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true).mode(0o600);
    let result = (|| -> io::Result<()> {
        let mut file = options.open(&temporary)?;
        file.write_all(&bytes)?;
        file.write_all(b"\n")?;
        file.sync_all()?;
        fs::rename(&temporary, path)?;
        fs::File::open(path.parent().ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidInput, "result parent is missing")
        })?)?
        .sync_all()
    })();
    if result.is_err() {
        let _remove_result = fs::remove_file(&temporary);
    }
    result?;
    Ok(())
}

#[cfg(unix)]
async fn wait_for_shutdown() {
    use tokio::signal::unix::{SignalKind, signal};

    let terminate = signal(SignalKind::terminate());
    let interrupt = signal(SignalKind::interrupt());
    match (terminate, interrupt) {
        (Ok(mut terminate), Ok(mut interrupt)) => {
            tokio::select! {
                _ = terminate.recv() => {}
                _ = interrupt.recv() => {}
            }
        }
        _ => std::future::pending::<()>().await,
    }
}
