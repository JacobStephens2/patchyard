//! Patch size accounting against a recorded base SHA.

use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::{InputError, require_lower_hex, require_repo_path};

/// Default constitution cap for a lane-A patch.
pub const DEFAULT_MAX_FILES: usize = 2;
/// Additions plus deletions, including tests and whitespace-only lines.
pub const DEFAULT_MAX_LINES: u64 = 50;

/// A normalized final diff produced against the recorded base SHA.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DiffManifest {
    pub base_sha: String,
    pub files: Vec<DiffFile>,
}

/// One changed path and its explicit diff accounting.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DiffFile {
    pub path: String,
    #[serde(default)]
    pub old_path: Option<String>,
    pub change: ChangeKind,
    pub additions: u64,
    pub deletions: u64,
    #[serde(default)]
    pub binary: bool,
    #[serde(default)]
    pub generated: bool,
    #[serde(default)]
    pub old_mode: Option<String>,
    #[serde(default)]
    pub new_mode: Option<String>,
}

/// Git change kinds that must be enumerated rather than inferred.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ChangeKind {
    Added,
    Deleted,
    Modified,
    Renamed,
}

/// Successful cap accounting, suitable for run evidence.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub struct CapSummary {
    pub files: usize,
    pub changed_lines: u64,
}

#[derive(Debug, Error, Eq, PartialEq)]
pub enum CapsError {
    #[error(transparent)]
    Input(#[from] InputError),
    #[error("diff base {actual} does not match recorded base {expected}")]
    WrongBase { expected: String, actual: String },
    #[error("diff contains no changed files")]
    EmptyDiff,
    #[error("duplicate final path in diff: {0}")]
    DuplicatePath(String),
    #[error("lane-A caps reject rename: {old} -> {new}")]
    Rename { old: String, new: String },
    #[error("lane-A caps reject mode change on {path}: {old:?} -> {new:?}")]
    ModeChange {
        path: String,
        old: Option<String>,
        new: Option<String>,
    },
    #[error("lane-A caps reject binary change: {0}")]
    Binary(String),
    #[error("lane-A caps reject generated change: {0}")]
    Generated(String),
    #[error("file cap exceeded: {actual} > {limit}")]
    FileLimit { actual: usize, limit: usize },
    #[error("changed-line cap exceeded: {actual} > {limit}")]
    LineLimit { actual: u64, limit: u64 },
    #[error("changed-line count overflow")]
    CountOverflow,
}

/// Count every addition and deletion in the final diff, including tests and
/// whitespace-only changes. Ambiguous changes fail closed.
pub fn verify(
    manifest: &DiffManifest,
    expected_base_sha: &str,
    max_files: usize,
    max_lines: u64,
) -> Result<CapSummary, CapsError> {
    require_lower_hex("manifest.base_sha", &manifest.base_sha, 40)?;
    require_lower_hex("expected_base_sha", expected_base_sha, 40)?;
    if manifest.base_sha != expected_base_sha {
        return Err(CapsError::WrongBase {
            expected: expected_base_sha.to_owned(),
            actual: manifest.base_sha.clone(),
        });
    }
    if manifest.files.is_empty() {
        return Err(CapsError::EmptyDiff);
    }

    let mut paths = BTreeSet::new();
    let mut changed_lines = 0_u64;
    for file in &manifest.files {
        require_repo_path(&file.path)?;
        if !paths.insert(file.path.clone()) {
            return Err(CapsError::DuplicatePath(file.path.clone()));
        }
        if let Some(old_path) = &file.old_path {
            require_repo_path(old_path)?;
        }
        if file.change == ChangeKind::Renamed || file.old_path.is_some() {
            return Err(CapsError::Rename {
                old: file.old_path.clone().unwrap_or_else(|| file.path.clone()),
                new: file.path.clone(),
            });
        }
        if file.change == ChangeKind::Modified && file.old_mode != file.new_mode {
            return Err(CapsError::ModeChange {
                path: file.path.clone(),
                old: file.old_mode.clone(),
                new: file.new_mode.clone(),
            });
        }
        if file.binary {
            return Err(CapsError::Binary(file.path.clone()));
        }
        if file.generated {
            return Err(CapsError::Generated(file.path.clone()));
        }
        changed_lines = changed_lines
            .checked_add(file.additions)
            .and_then(|count| count.checked_add(file.deletions))
            .ok_or(CapsError::CountOverflow)?;
    }

    if manifest.files.len() > max_files {
        return Err(CapsError::FileLimit {
            actual: manifest.files.len(),
            limit: max_files,
        });
    }
    if changed_lines > max_lines {
        return Err(CapsError::LineLimit {
            actual: changed_lines,
            limit: max_lines,
        });
    }
    Ok(CapSummary {
        files: manifest.files.len(),
        changed_lines,
    })
}
