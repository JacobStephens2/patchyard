//! Deterministic, fail-closed verification gates for Patchyard Factory patches.

pub mod caps;
pub mod deny_paths;
pub mod ledger;
pub mod postconditions;
pub mod runtime;

use std::path::{Component, Path};

use thiserror::Error;

/// Errors shared by verifier inputs.
#[derive(Debug, Error, Eq, PartialEq)]
pub enum InputError {
    #[error("{field} must be canonical lowercase {length}-character hexadecimal")]
    InvalidHex { field: &'static str, length: usize },
    #[error("path must be repository-relative and normalized: {0}")]
    InvalidPath(String),
}

pub(crate) fn require_lower_hex(
    field: &'static str,
    value: &str,
    length: usize,
) -> Result<(), InputError> {
    if value.len() != length
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(InputError::InvalidHex { field, length });
    }
    Ok(())
}

pub(crate) fn require_repo_path(value: &str) -> Result<(), InputError> {
    let path = Path::new(value);
    if value.is_empty()
        || value.starts_with('/')
        || value.ends_with('/')
        || value.contains("//")
        || value.contains('\\')
        || value.chars().any(char::is_control)
        || value.split('/').any(|part| matches!(part, "" | "." | ".."))
        || path.is_absolute()
        || path.components().any(|component| {
            matches!(
                component,
                Component::ParentDir
                    | Component::CurDir
                    | Component::RootDir
                    | Component::Prefix(_)
            )
        })
    {
        return Err(InputError::InvalidPath(value.to_owned()));
    }
    Ok(())
}
