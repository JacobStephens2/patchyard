//! Versioned static seat routing resolved against the canonical bench.

use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use thiserror::Error;

use crate::{
    contracts::{AccountedUsage, InvocationUsage},
    pricing::{ModelRates, PricingError},
};

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
    /// False until a separate reviewed change activates provider execution.
    pub live_provider_execution: bool,
    pub rules: BTreeMap<String, RoutingRule>,
    #[serde(skip)]
    rates: ModelRates,
}

/// One serving host's provider-egress and credential eligibility record.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProviderEgress {
    pub display_name: String,
    pub hostnames: Vec<String>,
    pub credential_qualified: bool,
}

/// The fail-closed provider policy consulted before a live seat is created.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProviderEgressConfig {
    pub schema_version: u16,
    pub default: String,
    pub runtime_dns: String,
    pub qualification_rule: String,
    pub providers: BTreeMap<String, ProviderEgress>,
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
    pub fn load(
        routing_path: &Path,
        bench_path: &Path,
        rates_path: &Path,
    ) -> Result<Self, RoutingError> {
        let routing_bytes = std::fs::read(routing_path)?;
        let bench_bytes = std::fs::read(bench_path)?;
        let mut config: Self = serde_json::from_slice(&routing_bytes)?;
        let bench: Bench = serde_json::from_slice(&bench_bytes)?;
        config.rates = ModelRates::load(rates_path)?;
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
            "improvement_proposer",
            "improvement_proposer_review",
            "improvement_proposer_disposition",
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
            self.rates.require_current(&rule.seat)?;
        }
        for (author_name, rule) in &self.rules {
            for reviewer_name in &rule.reviewers {
                let reviewer = &self.resolve(reviewer_name)?.seat;
                if rule.seat.family() == reviewer.family() || rule.seat.harness == reviewer.harness
                {
                    return Err(RoutingError::ReviewerNotDiverse(format!(
                        "{author_name}->{reviewer_name}"
                    )));
                }
            }
        }
        let author = &self.resolve("implement")?.seat;
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

    /// Price one invocation from normalized token categories under the same
    /// policy that made its seat routable at daemon start.
    pub fn account_usage(
        &self,
        seat: &Seat,
        usage: InvocationUsage,
    ) -> Result<AccountedUsage, RoutingError> {
        Ok(self.rates.account(seat, usage)?)
    }
}

impl ProviderEgressConfig {
    /// Parse the provider policy and reject ambiguous serving-host names.
    pub fn load(path: &Path) -> Result<Self, ProviderEgressError> {
        let bytes = std::fs::read(path)?;
        let config: Self = serde_json::from_slice(&bytes)?;
        config.validate()?;
        Ok(config)
    }

    fn validate(&self) -> Result<(), ProviderEgressError> {
        if self.schema_version != 1
            || self.default != "deny"
            || self.runtime_dns != "deny"
            || self.qualification_rule.trim().is_empty()
            || self.providers.is_empty()
        {
            return Err(ProviderEgressError::InvalidEnvelope);
        }
        let mut display_names = BTreeSet::new();
        for (key, provider) in &self.providers {
            if key.is_empty()
                || provider.display_name.trim().is_empty()
                || provider.hostnames.is_empty()
                || !display_names.insert(provider.display_name.as_str())
            {
                return Err(ProviderEgressError::InvalidProvider(key.clone()));
            }
            let mut hostnames = BTreeSet::new();
            if provider.hostnames.iter().any(|hostname| {
                hostname.trim().is_empty()
                    || hostname.contains(['/', ':', '@'])
                    || !hostnames.insert(hostname.as_str())
            }) {
                return Err(ProviderEgressError::InvalidProvider(key.clone()));
            }
        }
        Ok(())
    }

    /// Resolve a canonical bench host through its human-facing provider name.
    #[must_use]
    pub fn by_display_name(&self, display_name: &str) -> Option<&ProviderEgress> {
        self.providers
            .values()
            .find(|provider| provider.display_name == display_name)
    }
}

#[derive(Debug, Error)]
pub enum RoutingError {
    #[error("routing policy or canonical bench could not be read: {0}")]
    Io(#[from] std::io::Error),
    #[error("routing policy or canonical bench JSON is invalid: {0}")]
    Json(#[from] serde_json::Error),
    #[error("model-rate policy failed: {0}")]
    Pricing(#[from] PricingError),
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

#[derive(Debug, Error)]
pub enum ProviderEgressError {
    #[error("provider-egress policy could not be read: {0}")]
    Io(#[from] std::io::Error),
    #[error("provider-egress policy JSON is invalid: {0}")]
    Json(#[from] serde_json::Error),
    #[error("provider-egress policy envelope is invalid")]
    InvalidEnvelope,
    #[error("provider-egress entry is invalid or ambiguous: {0}")]
    InvalidProvider(String),
}

#[cfg(test)]
mod tests {
    use std::{fs, path::Path};

    use super::{ProviderEgressConfig, RoutingConfig, RoutingError};
    use crate::contracts::InvocationUsage;
    use crate::pricing::PricingError;

    fn canonical_routing() -> RoutingConfig {
        RoutingConfig::load(
            Path::new("../../policy/routing.json"),
            Path::new("../../docs/bench.json"),
            Path::new("../../policy/model-rates.json"),
        )
        .expect("canonical routing and rates")
    }

    #[test]
    fn canonical_routing_resolves_against_bench() {
        let config = canonical_routing();
        // Live execution is on for the triage seat. What must stay true is not
        // that the flag is off, but that it is never on for a seat whose
        // provider is unqualified - the condition bootstrap enforces.
        if config.live_provider_execution {
            let egress = ProviderEgressConfig::load(Path::new("../../policy/provider-egress.json"))
                .expect("canonical provider egress");
            let provider = &config.resolve("triage").expect("triage").seat.provider;
            assert!(
                egress
                    .by_display_name(provider)
                    .is_some_and(|entry| entry.credential_qualified),
                "live execution is on but the triage provider is not qualified"
            );
        }
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

    #[test]
    fn supervisor_accounts_for_the_banked_live_implement_usage() {
        let config = canonical_routing();
        let seat = &config.resolve("implement").expect("implement").seat;

        let accounted = config
            .account_usage(
                seat,
                InvocationUsage {
                    input_tokens: 97_018,
                    cached_input_tokens: 80_078,
                    cache_write_input_tokens: 16_919,
                    output_tokens: 4_538,
                    cost_microusd: None,
                },
            )
            .expect("published rate covers every reported token category");

        assert_eq!(accounted.cost_microusd, 207_470);
    }

    #[test]
    fn supervisor_refuses_a_nonzero_category_without_a_published_rate() {
        let config = canonical_routing();
        let seat = &config.resolve("triage").expect("triage").seat;

        let error = config
            .account_usage(
                seat,
                InvocationUsage {
                    input_tokens: 10,
                    cached_input_tokens: 1,
                    cache_write_input_tokens: 0,
                    output_tokens: 1,
                    cost_microusd: None,
                },
            )
            .expect_err("Anthropic cache reads have no ruled rate");

        assert!(matches!(
            error,
            RoutingError::Pricing(PricingError::UnpricedCategory("cached_input_tokens"))
        ));
    }

    #[test]
    fn supervisor_names_an_unpriced_cache_write_category() {
        let config = canonical_routing();
        let seat = &config.resolve("dispute_arbitration").expect("arbiter").seat;

        let error = config
            .account_usage(
                seat,
                InvocationUsage {
                    input_tokens: 10,
                    cached_input_tokens: 0,
                    cache_write_input_tokens: 1,
                    output_tokens: 1,
                    cost_microusd: None,
                },
            )
            .expect_err("xAI publishes no cache-write rate");

        assert!(matches!(
            error,
            RoutingError::Pricing(PricingError::UnpricedCategory("cache_write_input_tokens"))
        ));
    }

    #[test]
    fn routing_refuses_a_model_without_a_rate_before_daemon_start() {
        let temporary = tempfile::tempdir().expect("rate fixture");
        let mut rates: serde_json::Value = serde_json::from_slice(
            &fs::read("../../policy/model-rates.json").expect("canonical rates"),
        )
        .expect("rate JSON");
        rates["rates"]
            .as_array_mut()
            .expect("rate rows")
            .retain(|rate| rate["model"] != "GPT-5.6 Sol");
        let rates_path = temporary.path().join("model-rates.json");
        fs::write(
            &rates_path,
            serde_json::to_vec(&rates).expect("rate fixture JSON"),
        )
        .expect("rate fixture write");

        let error = RoutingConfig::load(
            Path::new("../../policy/routing.json"),
            Path::new("../../docs/bench.json"),
            &rates_path,
        )
        .expect_err("an unpriced routed model must make startup fail");

        assert!(matches!(
            error,
            RoutingError::Pricing(PricingError::MissingRate(ref key))
                if key == "OpenAI/GPT-5.6 Sol"
        ));
    }

    #[test]
    fn routing_refuses_an_expired_rate_before_daemon_start() {
        let temporary = tempfile::tempdir().expect("rate fixture");
        let mut rates: serde_json::Value = serde_json::from_slice(
            &fs::read("../../policy/model-rates.json").expect("canonical rates"),
        )
        .expect("rate JSON");
        let openai = rates["rates"]
            .as_array_mut()
            .expect("rate rows")
            .iter_mut()
            .find(|rate| rate["model"] == "GPT-5.6 Sol")
            .expect("OpenAI rate");
        openai["valid_through"] = serde_json::json!("2026-08-27");
        let rates_path = temporary.path().join("model-rates.json");
        fs::write(
            &rates_path,
            serde_json::to_vec(&rates).expect("rate fixture JSON"),
        )
        .expect("rate fixture write");

        let error = RoutingConfig::load(
            Path::new("../../policy/routing.json"),
            Path::new("../../docs/bench.json"),
            &rates_path,
        )
        .expect_err("a stale routed rate must make startup fail");

        assert!(matches!(
            error,
            RoutingError::Pricing(PricingError::ExpiredRate(ref key))
                if key == "OpenAI/GPT-5.6 Sol"
        ));
    }

    #[test]
    fn openai_long_context_pricing_starts_strictly_above_272k_input_tokens() {
        let config = canonical_routing();
        let seat = &config.resolve("implement").expect("implement").seat;
        let usage = |input_tokens| InvocationUsage {
            input_tokens,
            cached_input_tokens: 0,
            cache_write_input_tokens: 0,
            output_tokens: 1,
            cost_microusd: None,
        };

        assert_eq!(
            config
                .account_usage(seat, usage(272_000))
                .expect("standard tier")
                .cost_microusd,
            1_088_020
        );
        assert_eq!(
            config
                .account_usage(seat, usage(272_001))
                .expect("long-context tier")
                .cost_microusd,
            2_176_038
        );
    }

    #[test]
    fn supervisor_rejects_a_seat_reported_cost_that_disagrees() {
        let config = canonical_routing();
        let seat = &config
            .resolve("implementation_review")
            .expect("review")
            .seat;

        let error = config
            .account_usage(
                seat,
                InvocationUsage {
                    input_tokens: 100,
                    cached_input_tokens: 0,
                    cache_write_input_tokens: 0,
                    output_tokens: 50,
                    cost_microusd: Some(0),
                },
            )
            .expect_err("the legacy zero must not override trusted pricing");

        assert!(matches!(
            error,
            RoutingError::Pricing(PricingError::ReportedCostMismatch {
                reported: 0,
                computed: 1_750
            })
        ));
    }

    #[test]
    fn supervisor_rejects_cache_counts_larger_than_total_input() {
        let config = canonical_routing();
        let seat = &config.resolve("implement").expect("implement").seat;

        let error = config
            .account_usage(
                seat,
                InvocationUsage {
                    input_tokens: 10,
                    cached_input_tokens: 8,
                    cache_write_input_tokens: 3,
                    output_tokens: 1,
                    cost_microusd: None,
                },
            )
            .expect_err("categories cannot exceed the reported total");

        assert!(matches!(
            error,
            RoutingError::Pricing(PricingError::InvalidUsage)
        ));
    }

    #[test]
    fn canonical_provider_policy_qualifies_anthropic_and_openai() {
        let config = ProviderEgressConfig::load(Path::new("../../policy/provider-egress.json"))
            .expect("canonical provider policy");
        assert!(
            config
                .by_display_name("Anthropic")
                .expect("Anthropic")
                .credential_qualified
        );
        assert!(
            config
                .by_display_name("OpenAI")
                .expect("OpenAI")
                .credential_qualified
        );
        assert!(
            !config
                .by_display_name("xAI")
                .expect("xAI")
                .credential_qualified
        );
        assert!(config.by_display_name("missing-provider").is_none());
    }
}
