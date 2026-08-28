//! Trusted model-rate policy and exact invocation cost accounting.

use std::{collections::BTreeSet, path::Path};

use serde::Deserialize;
use thiserror::Error;
use time::{Date, Month, OffsetDateTime};

use crate::{
    config::Seat,
    contracts::{AccountedUsage, InvocationUsage},
};

const TOKENS_PER_MILLION: u128 = 1_000_000;
const ROUND_HALF_UP: u128 = TOKENS_PER_MILLION / 2;

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ModelRates {
    schema_version: u16,
    version: String,
    currency: String,
    unit: String,
    rounding: String,
    rates: Vec<ModelRate>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ModelRate {
    provider: String,
    model: String,
    source: String,
    read_date: String,
    #[serde(default)]
    valid_through: Option<String>,
    #[serde(default)]
    tier_input_basis: Option<String>,
    #[serde(default)]
    tier_input_basis_source: Option<String>,
    tiers: Vec<RateTier>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct RateTier {
    minimum_input_tokens: u64,
    #[serde(rename = "input")]
    input_rate: u64,
    #[serde(default, rename = "cached_input")]
    cached_input_rate: Option<u64>,
    #[serde(default, rename = "cache_write_input")]
    cache_write_input_rate: Option<u64>,
    #[serde(rename = "output")]
    output_rate: u64,
}

impl ModelRates {
    pub(crate) fn load(path: &Path) -> Result<Self, PricingError> {
        let bytes = std::fs::read(path)?;
        let rates: Self = serde_json::from_slice(&bytes)?;
        rates.validate()?;
        Ok(rates)
    }

    fn validate(&self) -> Result<(), PricingError> {
        if self.schema_version != 1
            || self.version.trim().is_empty()
            || self.currency != "USD"
            || self.unit != "microusd_per_million_tokens"
            || self.rounding != "nearest_microusd_half_up"
            || self.rates.is_empty()
        {
            return Err(PricingError::InvalidEnvelope);
        }
        let mut keys = BTreeSet::new();
        for rate in &self.rates {
            if rate.provider.trim().is_empty()
                || rate.model.trim().is_empty()
                || rate.source.trim().is_empty()
                || !keys.insert((rate.provider.as_str(), rate.model.as_str()))
                || rate.tiers.is_empty()
                || rate.tiers[0].minimum_input_tokens != 0
                || (rate.tiers.len() > 1
                    && (rate.tier_input_basis.as_deref() != Some("total_input_tokens")
                        || rate
                            .tier_input_basis_source
                            .as_deref()
                            .is_none_or(str::is_empty)))
                || (rate.tiers.len() == 1
                    && (rate.tier_input_basis.is_some() || rate.tier_input_basis_source.is_some()))
            {
                return Err(PricingError::InvalidRate(rate.key()));
            }
            let read_date =
                parse_date(&rate.read_date).ok_or_else(|| PricingError::InvalidRate(rate.key()))?;
            if let Some(valid_through) = &rate.valid_through {
                let valid_through = parse_date(valid_through)
                    .ok_or_else(|| PricingError::InvalidRate(rate.key()))?;
                if valid_through < read_date {
                    return Err(PricingError::InvalidRate(rate.key()));
                }
            }
            let mut previous = None;
            for tier in &rate.tiers {
                if tier.input_rate == 0
                    || tier.output_rate == 0
                    || tier.cached_input_rate == Some(0)
                    || tier.cache_write_input_rate == Some(0)
                    || previous.is_some_and(|value| tier.minimum_input_tokens <= value)
                {
                    return Err(PricingError::InvalidRate(rate.key()));
                }
                previous = Some(tier.minimum_input_tokens);
            }
        }
        Ok(())
    }

    pub(crate) fn require_current(&self, seat: &Seat) -> Result<(), PricingError> {
        let rate = self.find(seat)?;
        if let Some(valid_through) = &rate.valid_through {
            let valid_through =
                parse_date(valid_through).ok_or_else(|| PricingError::InvalidRate(rate.key()))?;
            if OffsetDateTime::now_utc().date() > valid_through {
                return Err(PricingError::ExpiredRate(rate.key()));
            }
        }
        Ok(())
    }

    pub(crate) fn account(
        &self,
        seat: &Seat,
        usage: InvocationUsage,
    ) -> Result<AccountedUsage, PricingError> {
        self.require_current(seat)?;
        let rate = self.find(seat)?;
        let tier = rate
            .tiers
            .iter()
            .rev()
            .find(|tier| usage.input_tokens >= tier.minimum_input_tokens)
            .expect("validated rates start at zero");
        let uncached_input_tokens = usage
            .input_tokens
            .checked_sub(usage.cached_input_tokens)
            .and_then(|tokens| tokens.checked_sub(usage.cache_write_input_tokens))
            .ok_or(PricingError::InvalidUsage)?;
        let cached_input_cost = category_cost(
            usage.cached_input_tokens,
            tier.cached_input_rate,
            "cached_input_tokens",
        )?;
        let cache_write_input_cost = category_cost(
            usage.cache_write_input_tokens,
            tier.cache_write_input_rate,
            "cache_write_input_tokens",
        )?;
        let numerator = (u128::from(uncached_input_tokens) * u128::from(tier.input_rate))
            .checked_add(cached_input_cost)
            .and_then(|value| value.checked_add(cache_write_input_cost))
            .and_then(|value| {
                value.checked_add(u128::from(usage.output_tokens) * u128::from(tier.output_rate))
            })
            .ok_or(PricingError::UsageOverflow)?;
        let rounded = numerator
            .checked_add(ROUND_HALF_UP)
            .ok_or(PricingError::UsageOverflow)?
            / TOKENS_PER_MILLION;
        let cost_microusd = u64::try_from(rounded).map_err(|_| PricingError::UsageOverflow)?;
        if usage
            .cost_microusd
            .is_some_and(|reported| reported != cost_microusd)
        {
            return Err(PricingError::ReportedCostMismatch {
                reported: usage.cost_microusd.expect("checked as some"),
                computed: cost_microusd,
            });
        }
        Ok(AccountedUsage {
            input_tokens: usage.input_tokens,
            output_tokens: usage.output_tokens,
            cost_microusd,
        })
    }

    fn find(&self, seat: &Seat) -> Result<&ModelRate, PricingError> {
        self.rates
            .iter()
            .find(|rate| rate.provider == seat.provider && rate.model == seat.model)
            .ok_or_else(|| PricingError::MissingRate(format!("{}/{}", seat.provider, seat.model)))
    }
}

impl ModelRate {
    fn key(&self) -> String {
        format!("{}/{}", self.provider, self.model)
    }
}

fn category_cost(
    tokens: u64,
    rate: Option<u64>,
    category: &'static str,
) -> Result<u128, PricingError> {
    match (tokens, rate) {
        (0, _) => Ok(0),
        (_, Some(rate)) => Ok(u128::from(tokens) * u128::from(rate)),
        (_, None) => Err(PricingError::UnpricedCategory(category)),
    }
}

fn parse_date(value: &str) -> Option<Date> {
    let mut parts = value.split('-');
    let year = parts.next()?.parse().ok()?;
    let month = Month::try_from(parts.next()?.parse::<u8>().ok()?).ok()?;
    let day = parts.next()?.parse().ok()?;
    if parts.next().is_some() {
        return None;
    }
    Date::from_calendar_date(year, month, day).ok()
}

#[derive(Debug, Error)]
pub enum PricingError {
    #[error("model-rate policy could not be read: {0}")]
    Io(#[from] std::io::Error),
    #[error("model-rate policy JSON is invalid: {0}")]
    Json(#[from] serde_json::Error),
    #[error("model-rate policy envelope is invalid")]
    InvalidEnvelope,
    #[error("model-rate entry is invalid: {0}")]
    InvalidRate(String),
    #[error("routed model has no rate: {0}")]
    MissingRate(String),
    #[error("routed model rate is expired: {0}")]
    ExpiredRate(String),
    #[error("usage token categories exceed total input tokens")]
    InvalidUsage,
    #[error("usage category is non-zero but has no published rate: {0}")]
    UnpricedCategory(&'static str),
    #[error("usage cost exceeds supported integer bounds")]
    UsageOverflow,
    #[error("seat-reported cost {reported} differs from supervisor cost {computed}")]
    ReportedCostMismatch { reported: u64, computed: u64 },
}
