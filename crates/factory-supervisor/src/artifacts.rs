//! Private artifact persistence with atomic, bounded writes.

use std::{
    fs,
    os::unix::fs::{OpenOptionsExt as _, PermissionsExt as _},
    path::{Component, Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use thiserror::Error;
use uuid::Uuid;

/// One artifact ready to register in the ledger.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct StoredArtifact {
    pub id: Uuid,
    pub relative_path: String,
    pub sha256: String,
    pub kind: String,
    pub bytes: u64,
}

#[derive(Clone, Debug)]
pub struct ArtifactStore {
    root: PathBuf,
}

impl ArtifactStore {
    pub fn open(root: impl Into<PathBuf>) -> Result<Self, ArtifactError> {
        let root = root.into();
        let metadata = fs::symlink_metadata(&root)?;
        if !metadata.is_dir()
            || metadata.file_type().is_symlink()
            || metadata.permissions().mode() & 0o7777 != 0o2750
        {
            return Err(ArtifactError::UnsafeRoot(root));
        }
        Ok(Self { root })
    }

    /// Persist bytes outside the executor. Hashing, mkdir, fsync, and rename
    /// exceed the 10-100µs async floor on realistic artifacts.
    #[allow(clippy::too_many_arguments)]
    pub async fn put(
        &self,
        request_id: Uuid,
        run_id: Option<Uuid>,
        stage: &str,
        name: &str,
        kind: &str,
        bytes: Vec<u8>,
        maximum: usize,
    ) -> Result<StoredArtifact, ArtifactError> {
        validate_component(stage)?;
        validate_component(name)?;
        validate_component(kind)?;
        if bytes.len() > maximum {
            return Err(ArtifactError::TooLarge {
                actual: bytes.len(),
                maximum,
            });
        }
        let root = self.root.clone();
        let stage = stage.to_owned();
        let name = name.to_owned();
        let kind = kind.to_owned();
        tokio::task::spawn_blocking(move || {
            write_atomic(root, request_id, run_id, stage, name, kind, bytes)
        })
        .await
        .map_err(ArtifactError::Join)?
    }

    #[must_use]
    pub fn root(&self) -> &Path {
        &self.root
    }
}

fn write_atomic(
    root: PathBuf,
    request_id: Uuid,
    run_id: Option<Uuid>,
    stage: String,
    name: String,
    kind: String,
    bytes: Vec<u8>,
) -> Result<StoredArtifact, ArtifactError> {
    let id = Uuid::new_v4();
    let mut relative = PathBuf::from(request_id.to_string());
    if let Some(run_id) = run_id {
        relative.push(run_id.to_string());
    }
    relative.push(stage);
    let directory = root.join(&relative);
    fs::create_dir_all(&directory)?;
    fs::set_permissions(&directory, fs::Permissions::from_mode(0o2750))?;
    let final_name = format!("{id}-{name}");
    let final_path = directory.join(&final_name);
    let temporary = directory.join(format!(".{id}.tmp"));
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true).mode(0o640);
    let mut file = options.open(&temporary)?;
    use std::io::Write as _;
    file.write_all(&bytes)?;
    file.sync_all()?;
    fs::rename(&temporary, &final_path)?;
    let directory_file = fs::File::open(&directory)?;
    directory_file.sync_all()?;
    relative.push(final_name);
    let relative_path = relative
        .to_str()
        .ok_or(ArtifactError::NonUtf8Path)?
        .to_owned();
    Ok(StoredArtifact {
        id,
        relative_path,
        sha256: hex::encode(Sha256::digest(&bytes)),
        kind,
        bytes: u64::try_from(bytes.len()).map_err(|_| ArtifactError::LengthOverflow)?,
    })
}

fn validate_component(value: &str) -> Result<(), ArtifactError> {
    if value.is_empty()
        || value.len() > 128
        || Path::new(value)
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
        || value.chars().any(char::is_control)
    {
        return Err(ArtifactError::UnsafeComponent(value.to_owned()));
    }
    Ok(())
}

#[derive(Debug, Error)]
pub enum ArtifactError {
    #[error("artifact root is not a non-symlink setgid 2750 directory: {0}")]
    UnsafeRoot(PathBuf),
    #[error("unsafe artifact path component: {0}")]
    UnsafeComponent(String),
    #[error("artifact path is not UTF-8")]
    NonUtf8Path,
    #[error("artifact length cannot be represented")]
    LengthOverflow,
    #[error("artifact has {actual} bytes, above {maximum}")]
    TooLarge { actual: usize, maximum: usize },
    #[error("artifact filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("artifact blocking task failed: {0}")]
    Join(tokio::task::JoinError),
}

#[cfg(test)]
mod tests {
    use std::{fs, os::unix::fs::PermissionsExt as _};

    use uuid::Uuid;

    use super::ArtifactStore;

    #[tokio::test]
    async fn transcript_write_is_private_atomic_and_hashed() {
        let root = std::env::temp_dir().join(format!("factory-artifacts-{}", Uuid::new_v4()));
        fs::create_dir(&root).expect("root");
        fs::set_permissions(&root, fs::Permissions::from_mode(0o2750)).expect("chmod");
        let store = ArtifactStore::open(&root).expect("store");
        let artifact = store
            .put(
                Uuid::new_v4(),
                Some(Uuid::new_v4()),
                "triage-0",
                "transcript.log",
                "agent-transcript",
                b"full transcript".to_vec(),
                1024,
            )
            .await
            .expect("write");
        assert_eq!(artifact.bytes, 15);
        assert_eq!(
            fs::read(root.join(&artifact.relative_path)).expect("read"),
            b"full transcript"
        );
        assert_eq!(
            fs::metadata(root.join(&artifact.relative_path))
                .expect("metadata")
                .permissions()
                .mode()
                & 0o777,
            0o640
        );
        fs::remove_dir_all(root).expect("cleanup");
    }
}
