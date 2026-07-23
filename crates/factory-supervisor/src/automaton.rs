//! Pure deterministic acceptance gates over the worker OutContract.

use std::{collections::BTreeSet, path::Path};

use factory_core::triage::{Lane, TaskSpec};
use factory_verify::{
    caps::{self, CapSummary},
    deny_paths,
};
use globset::{Glob, GlobSet, GlobSetBuilder};
use serde::Serialize;
use thiserror::Error;

use crate::contracts::OutContract;

/// Successful deterministic acceptance evidence.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct AcceptReport {
    pub files: usize,
    pub changed_lines: u64,
    pub allowed_paths: Vec<String>,
    pub allowed_globs: Vec<String>,
}

/// Apply only deterministic gates. No confidence value is accepted by this
/// function or by [`OutContract`].
pub fn accept(
    task: &TaskSpec,
    lane: Lane,
    contract: &OutContract,
    patch: &str,
) -> Result<AcceptReport, AcceptError> {
    task.validate()?;
    if contract.schema_version != 1 || contract.attempt > 1 {
        return Err(AcceptError::ContractEnvelope);
    }
    let scope = Scope::new(&task.allowed_paths, &task.allowed_globs)?;
    for file in &contract.manifest.files {
        if !scope.allows(&file.path) {
            return Err(AcceptError::PathOutsideTaskSpec(file.path.clone()));
        }
        if let Some(old_path) = &file.old_path
            && !scope.allows(old_path)
        {
            return Err(AcceptError::PathOutsideTaskSpec(old_path.clone()));
        }
    }

    let budget = task.budget.ok_or(AcceptError::MissingBudget)?;
    let cap = caps::verify(
        &contract.manifest,
        &contract.base_sha,
        usize::from(budget.max_files),
        u64::from(budget.max_changed_lines),
    )?;
    if lane == Lane::A {
        deny_paths::verify(&contract.manifest)?;
    }
    dependency_gate(task, contract)?;
    patch_sink_gate(patch)?;
    secret_gate(patch)?;

    Ok(report(cap, task))
}

fn report(cap: CapSummary, task: &TaskSpec) -> AcceptReport {
    AcceptReport {
        files: cap.files,
        changed_lines: cap.changed_lines,
        allowed_paths: task.allowed_paths.clone(),
        allowed_globs: task.allowed_globs.clone(),
    }
}

struct Scope {
    exact: BTreeSet<String>,
    globs: GlobSet,
}

impl Scope {
    fn new(exact: &[String], patterns: &[String]) -> Result<Self, AcceptError> {
        if exact.is_empty() && patterns.is_empty() {
            return Err(AcceptError::EmptyScope);
        }
        let mut builder = GlobSetBuilder::new();
        for pattern in patterns {
            builder.add(
                Glob::new(pattern).map_err(|error| AcceptError::InvalidGlob {
                    pattern: pattern.clone(),
                    error: error.to_string(),
                })?,
            );
        }
        Ok(Self {
            exact: exact.iter().cloned().collect(),
            globs: builder
                .build()
                .map_err(|error| AcceptError::GlobSet(error.to_string()))?,
        })
    }

    fn allows(&self, path: &str) -> bool {
        self.exact.contains(path) || self.globs.is_match(path)
    }
}

fn dependency_gate(task: &TaskSpec, contract: &OutContract) -> Result<(), AcceptError> {
    let dependency_delta = contract
        .manifest
        .files
        .iter()
        .any(|file| is_dependency_path(&file.path));
    if dependency_delta && !task.flags.dependency_changes {
        return Err(AcceptError::DependencyFlagRequired);
    }
    Ok(())
}

fn is_dependency_path(path: &str) -> bool {
    let name = Path::new(path)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    matches!(
        name.as_str(),
        "composer.json" | "composer.lock" | "package.json" | "package-lock.json"
    ) || name.ends_with(".lock")
}

fn added_lines(patch: &str) -> impl Iterator<Item = &str> {
    patch
        .lines()
        .filter(|line| line.starts_with('+') && !line.starts_with("+++"))
        .map(|line| &line[1..])
}

fn patch_sink_gate(patch: &str) -> Result<(), AcceptError> {
    for line in added_lines(patch) {
        let lower = line.to_ascii_lowercase();
        let dynamic_include = (lower.contains("include") || lower.contains("require"))
            && (lower.contains("include $")
                || lower.contains("require $")
                || lower.contains("include($")
                || lower.contains("require($"));
        let raw_sql_concat = (lower.contains("query(") || lower.contains("execute("))
            && (lower.contains(" . $") || lower.contains("{$"));
        let outbound_http = lower.contains("curl_init(")
            || lower.contains("file_get_contents('http")
            || lower.contains("file_get_contents(\"http")
            || lower.contains("new client(") && lower.contains("http");
        if lower.contains("eval(")
            || lower.contains("shell_exec(")
            || lower.contains("passthru(")
            || lower.contains("system(")
            || dynamic_include
            || raw_sql_concat
            || outbound_http
        {
            return Err(AcceptError::ForbiddenSink(line.to_owned()));
        }
    }
    Ok(())
}

fn secret_gate(patch: &str) -> Result<(), AcceptError> {
    const MARKERS: [&str; 9] = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "OP_SERVICE_ACCOUNT_TOKEN",
        "MYSQL_PWD",
        "BEGIN OPENSSH PRIVATE KEY",
        "BEGIN PRIVATE KEY",
    ];
    for line in added_lines(patch) {
        if MARKERS.iter().any(|marker| line.contains(marker)) {
            return Err(AcceptError::SecretMarker);
        }
    }
    Ok(())
}

#[derive(Debug, Error)]
pub enum AcceptError {
    #[error("TaskSpec validation failed: {0}")]
    TaskSpec(#[from] factory_core::triage::TriageError),
    #[error("OutContract envelope is invalid")]
    ContractEnvelope,
    #[error("TaskSpec has no declared allowed path or glob")]
    EmptyScope,
    #[error("TaskSpec has no change budget")]
    MissingBudget,
    #[error("invalid TaskSpec glob {pattern}: {error}")]
    InvalidGlob { pattern: String, error: String },
    #[error("TaskSpec glob set is invalid: {0}")]
    GlobSet(String),
    #[error("diff path is outside the TaskSpec authority: {0}")]
    PathOutsideTaskSpec(String),
    #[error("patch caps rejected the OutContract: {0}")]
    Caps(#[from] caps::CapsError),
    #[error("lane-A deny paths rejected the OutContract: {0}")]
    DenyPaths(#[from] deny_paths::DenyPathsError),
    #[error("dependency delta requires TaskSpec.flags.dependency_changes")]
    DependencyFlagRequired,
    #[error("forbidden added-code sink: {0}")]
    ForbiddenSink(String),
    #[error("secret marker found in added patch content")]
    SecretMarker,
}

#[cfg(test)]
mod tests {
    use factory_core::triage::{Lane, TriageOutput};
    use factory_verify::caps::{ChangeKind, DiffFile, DiffManifest};
    use uuid::Uuid;

    use crate::contracts::OutContract;

    use super::{AcceptError, accept};

    fn fixture() -> (factory_core::triage::TaskSpec, OutContract) {
        let output =
            TriageOutput::parse_json(include_str!("../../../fixtures/triage/alphabetize.json"))
                .expect("fixture");
        let manifest = DiffManifest {
            base_sha: "a".repeat(40),
            files: vec![DiffFile {
                path: "mfieldbook/common_functions.php".to_owned(),
                old_path: None,
                change: ChangeKind::Modified,
                additions: 1,
                deletions: 0,
                binary: false,
                generated: false,
                old_mode: Some("100644".to_owned()),
                new_mode: Some("100644".to_owned()),
            }],
        };
        let contract = OutContract {
            schema_version: 1,
            run_id: Uuid::new_v4(),
            attempt: 0,
            base_sha: manifest.base_sha.clone(),
            patch_sha256: "b".repeat(64),
            base_tree_hash: "c".repeat(64),
            result_tree_hash: "d".repeat(64),
            manifest,
            claims: Vec::new(),
        };
        (output.task_spec, contract)
    }

    #[test]
    fn task_spec_scope_has_teeth() {
        let (task, mut contract) = fixture();
        accept(&task, Lane::A, &contract, "+ORDER BY firstName\n").expect("allowed path");
        contract.manifest.files[0].path = "mfieldbook/helpful-adjacent.php".to_owned();
        assert!(matches!(
            accept(&task, Lane::A, &contract, "+ORDER BY firstName\n"),
            Err(AcceptError::PathOutsideTaskSpec(_))
        ));
    }

    #[test]
    fn confidence_cannot_enter_the_out_contract() {
        let (_, contract) = fixture();
        let mut value = serde_json::to_value(contract).expect("serialize");
        value["confidence_basis_points"] = serde_json::json!(10_000);
        assert!(serde_json::from_value::<OutContract>(value).is_err());
    }

    #[test]
    fn forbidden_sinks_and_secret_markers_fail_closed() {
        let (task, contract) = fixture();
        assert!(matches!(
            accept(&task, Lane::A, &contract, "+eval($request);\n"),
            Err(AcceptError::ForbiddenSink(_))
        ));
        assert!(matches!(
            accept(&task, Lane::A, &contract, "+OPENAI_API_KEY=hostile\n"),
            Err(AcceptError::SecretMarker)
        ));
    }
}
