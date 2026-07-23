//! Versioned static seat routing resolved against the canonical bench.

use std::{collections::BTreeMap, path::Path};

use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use thiserror::Error;

/// An exact model × harness × provider × effort seat.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Seat {
    pub model: String,
    pub effort: String,
    pub harness: String,
    pub provider: String,
}

impl Seat {
    /// Stable model identity carried by provenance and metrics.
    #[must_use]
    pub fn model_id(&self) -> String {
        format!(
            "{}|{}|{}|{}",
            self.model, self.effort, self.harness, self.provider
        )
    }

    /// A conservative family name used only for routing-policy validation.
    #[must_use]
    pub fn family(&self) -> &str {
        self.model.split_whitespace().next().unwrap_or(&self.model)
    }
}

/// One phase-1 static routing rule.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RoutingRule {
    pub selection_rule: String,
    pub seat: Seat,
    #[serde(default)]
    pub reviewers: Vec<String>,
}

/// The complete routing policy consumed by the daemon.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RoutingConfig {
    pub schema_version: u16,
    pub version: String,
    pub bench_sha256: String,
    /// False until a provider completes its later A-5 credential gate.
    pub live_provider_execution: bool,
    pub rules: BTreeMap<String, RoutingRule>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Bench {
    #[serde(rename = "$schema")]
    schema: Option<String>,
    last_updated: String,
    update_note: Option<String>,
    aa_index_version: String,
    aa_snapshot_date: String,
    pairs: Vec<BenchPair>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct BenchPair {
    model: String,
    effort: String,
    harness: String,
    preferred_harness: bool,
    host: String,
    floor: BenchFloor,
    image_input: serde_json::Value,
    provenance: String,
    standing: String,
    visible_tps: String,
    long_spec_wall: String,
    aa_intelligence: Option<f64>,
    aa_cost_per_task_usd: Option<f64>,
    aa_coding_index: Option<f64>,
    aa_agentic_index: Option<f64>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct BenchFloor {
    status: String,
    detail: String,
}

impl RoutingConfig {
    /// Parse routing and prove every selected pair exists, is preferred, and
    /// has passed the canonical bench floor. No daemon seat is hard-coded.
    pub fn load(routing_path: &Path, bench_path: &Path) -> Result<Self, RoutingError> {
        let routing_bytes = std::fs::read(routing_path)?;
        let bench_bytes = std::fs::read(bench_path)?;
        let config: Self = serde_json::from_slice(&routing_bytes)?;
        let bench: Bench = serde_json::from_slice(&bench_bytes)?;
        config.validate(&bench_bytes, &bench)?;
        Ok(config)
    }

    fn validate(&self, bench_bytes: &[u8], bench: &Bench) -> Result<(), RoutingError> {
        if self.schema_version != 1 || self.version.trim().is_empty() {
            return Err(RoutingError::InvalidEnvelope);
        }
        let bench_sha256 = hex::encode(Sha256::digest(bench_bytes));
        if bench_sha256 != self.bench_sha256 {
            return Err(RoutingError::BenchDigest {
                expected: self.bench_sha256.clone(),
                actual: bench_sha256,
            });
        }
        for required in [
            "triage",
            "implement",
            "implementation_review",
            "author_disposition",
            "dispute_arbitration",
            "repair",
        ] {
            if !self.rules.contains_key(required) {
                return Err(RoutingError::MissingRule(required.to_owned()));
            }
        }
        for (name, rule) in &self.rules {
            if rule.selection_rule.trim().is_empty() {
                return Err(RoutingError::InvalidRule(name.clone()));
            }
            let pair = bench.pairs.iter().find(|pair| {
                pair.model == rule.seat.model
                    && pair.effort == rule.seat.effort
                    && pair.harness == rule.seat.harness
                    && pair.host == rule.seat.provider
            });
            let Some(pair) = pair else {
                return Err(RoutingError::SeatAbsent(name.clone()));
            };
            if pair.floor.status != "pass" || !pair.preferred_harness {
                return Err(RoutingError::SeatIneligible(name.clone()));
            }
        }
        let author = &self.resolve("implement")?.seat;
        for reviewer_name in &self.resolve("implement")?.reviewers {
            let reviewer = &self.resolve(reviewer_name)?.seat;
            if author.family() == reviewer.family() || author.harness == reviewer.harness {
                return Err(RoutingError::ReviewerNotDiverse(reviewer_name.clone()));
            }
        }
        let reviewer = &self.resolve("implementation_review")?.seat;
        let arbiter = &self.resolve("dispute_arbitration")?.seat;
        if arbiter.family() == author.family() || arbiter.family() == reviewer.family() {
            return Err(RoutingError::ArbiterNotThirdFamily);
        }
        // Read every bench field under deny_unknown_fields so a format change
        // cannot silently bypass routing validation.
        let _bench_metadata = (
            &bench.schema,
            &bench.last_updated,
            &bench.update_note,
            &bench.aa_index_version,
            &bench.aa_snapshot_date,
        );
        for pair in &bench.pairs {
            let _pair_metadata = (
                &pair.floor.detail,
                &pair.image_input,
                &pair.provenance,
                &pair.standing,
                &pair.visible_tps,
                &pair.long_spec_wall,
                pair.aa_intelligence,
                pair.aa_cost_per_task_usd,
                pair.aa_coding_index,
                pair.aa_agentic_index,
            );
        }
        Ok(())
    }

    /// Resolve one static task class.
    pub fn resolve(&self, task_class: &str) -> Result<&RoutingRule, RoutingError> {
        self.rules
            .get(task_class)
            .ok_or_else(|| RoutingError::MissingRule(task_class.to_owned()))
    }
}

#[derive(Debug, Error)]
pub enum RoutingError {
    #[error("routing policy or canonical bench could not be read: {0}")]
    Io(#[from] std::io::Error),
    #[error("routing policy or canonical bench JSON is invalid: {0}")]
    Json(#[from] serde_json::Error),
    #[error("routing policy envelope is invalid")]
    InvalidEnvelope,
    #[error("routing rule is missing: {0}")]
    MissingRule(String),
    #[error("routing rule has no selection rule: {0}")]
    InvalidRule(String),
    #[error("routing rule does not resolve to an exact canonical bench pair: {0}")]
    SeatAbsent(String),
    #[error("routing seat is not a preferred floor-passing pair: {0}")]
    SeatIneligible(String),
    #[error("canonical bench digest differs: expected {expected}, got {actual}")]
    BenchDigest { expected: String, actual: String },
    #[error("reviewer is not cross-family and cross-harness: {0}")]
    ReviewerNotDiverse(String),
    #[error("arbiter is not from a third family")]
    ArbiterNotThirdFamily,
}

#[cfg(test)]
mod tests {
    use std::path::Path;

    use super::RoutingConfig;

    #[test]
    fn canonical_routing_resolves_against_bench() {
        let config = RoutingConfig::load(
            Path::new("../../policy/routing.json"),
            Path::new("../../docs/bench.json"),
        )
        .expect("canonical routing");
        assert!(!config.live_provider_execution);
        assert_eq!(
            config
                .resolve("implement")
                .expect("implement")
                .seat
                .provider,
            "OpenAI"
        );
        assert_eq!(
            config
                .resolve("dispute_arbitration")
                .expect("arbiter")
                .seat
                .provider,
            "xAI"
        );
    }
}
