//! Constitution deny-list checks against every path in the final diff.

use std::path::Path;

use serde::Serialize;
use thiserror::Error;

use crate::{InputError, caps::DiffManifest, require_repo_path};

/// The stable, machine-readable reason a path cannot remain in lane A.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DenyRule {
    SchemaOrMigration,
    AuthSessionPermissionOrSecret,
    Financial,
    OutboundOrScheduled,
    CustomerFacing,
    DependencyOrLockfile,
    Ci,
    Deploy,
}

#[derive(Debug, Error, Eq, PartialEq)]
pub enum DenyPathsError {
    #[error(transparent)]
    Input(#[from] InputError),
    #[error("constitution deny rule {rule:?} matched {path}")]
    Denied { path: String, rule: DenyRule },
}

/// Check both sides of every final-diff path so a rename cannot conceal a
/// forbidden source or destination.
pub fn verify(manifest: &DiffManifest) -> Result<(), DenyPathsError> {
    for file in &manifest.files {
        check_path(&file.path)?;
        if let Some(old_path) = &file.old_path {
            check_path(old_path)?;
        }
    }
    Ok(())
}

fn check_path(path: &str) -> Result<(), DenyPathsError> {
    require_repo_path(path)?;
    if let Some(rule) = classify(path) {
        return Err(DenyPathsError::Denied {
            path: path.to_owned(),
            rule,
        });
    }
    Ok(())
}

fn classify(path: &str) -> Option<DenyRule> {
    let normalized = path.to_ascii_lowercase();
    let components: Vec<_> = Path::new(&normalized)
        .components()
        .map(|component| component.as_os_str().to_string_lossy())
        .collect();
    let filename = components.last().map_or("", |value| value.as_ref());

    if has_any(
        &components,
        &[
            "mysql_files",
            "schema",
            "schemas",
            "migration",
            "migrations",
        ],
    ) {
        return Some(DenyRule::SchemaOrMigration);
    }
    if has_fragment(
        &components,
        &["auth", "session", "permission", "secret", "credential"],
    ) {
        return Some(DenyRule::AuthSessionPermissionOrSecret);
    }
    if has_fragment(
        &components,
        &[
            "payment",
            "pricing",
            "nacha",
            "accounting",
            "invoice",
            "payroll",
        ],
    ) || components.iter().any(|part| part.as_ref() == "ach")
    {
        return Some(DenyRule::Financial);
    }
    if has_fragment(&components, &["email", "sms", "webhook", "cron", "daemon"]) {
        return Some(DenyRule::OutboundOrScheduled);
    }
    if has_any(&components, &["customerweb", "guides"])
        || has_fragment(&components, &["customer-facing", "customer_facing"])
    {
        return Some(DenyRule::CustomerFacing);
    }
    if filename == "composer.json"
        || filename == "composer.lock"
        || filename == "package.json"
        || filename == "package-lock.json"
        || filename == "cargo.toml"
        || filename == "cargo.lock"
        || filename.ends_with(".lock")
    {
        return Some(DenyRule::DependencyOrLockfile);
    }
    if normalized.starts_with(".github/")
        || has_any(&components, &["ci", "workflows"])
        || filename == ".gitlab-ci.yml"
    {
        return Some(DenyRule::Ci);
    }
    if has_fragment(&components, &["deploy", "deployment"]) || filename == "apply-migration.sh" {
        return Some(DenyRule::Deploy);
    }
    None
}

fn has_any(components: &[std::borrow::Cow<'_, str>], terms: &[&str]) -> bool {
    components
        .iter()
        .any(|component| terms.contains(&component.as_ref()))
}

fn has_fragment(components: &[std::borrow::Cow<'_, str>], terms: &[&str]) -> bool {
    components
        .iter()
        .any(|component| terms.iter().any(|term| component.contains(term)))
}
