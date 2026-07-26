//! Deterministic, production-only learning facts from the durable ledger.
//!
//! This module has no model or artifact-store dependency. It reads typed run
//! and event columns only; request bodies and transcript artifacts are absent
//! from both its query and its public output contract.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use sqlx::{PgPool, Row};
use thiserror::Error;
use time::{OffsetDateTime, format_description::well_known::Rfc3339};
use uuid::Uuid;

pub const LESSONS_REPORT_SCHEMA_VERSION: u16 = 1;
pub const POLICY_PR_THRESHOLD: usize = 10;
pub const MAX_QUOTES_PER_RUN: usize = 1;
pub const MAX_QUOTES_PER_REPORT: usize = 32;
pub const MAX_QUOTE_CHARS: usize = 240;

type CohortDimensions = (String, String, String, String, String);
type CohortAggregate = (Vec<Uuid>, BTreeMap<String, usize>);

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LessonsReport {
    pub schema_version: u16,
    pub snapshot_max_event_id: i64,
    pub selection: ReportSelection,
    pub policy_pr_threshold: usize,
    pub production_run_count: usize,
    pub cohorts: Vec<LessonCohort>,
    pub runs: Vec<OutcomeFact>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ReportSelection {
    pub run_class: String,
    pub terminal_runs_only: bool,
    pub quote_sources: Vec<QuoteSource>,
    pub max_quotes_per_run: usize,
    pub max_quotes_per_report: usize,
    pub max_quote_chars: usize,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QuoteSource {
    pub event_type: String,
    pub json_pointer: String,
    pub trust: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LessonCohort {
    pub cohort_key: String,
    pub lane: String,
    pub skill: String,
    pub rubric_sha256: String,
    pub prompt_template_sha256: String,
    pub routing_config_version: String,
    pub production_run_count: usize,
    pub eligible_for_policy_pr: bool,
    pub run_ids: Vec<Uuid>,
    pub outcomes: Vec<OutcomeRate>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct OutcomeRate {
    pub terminal_state: String,
    pub count: usize,
    pub rate_basis_points: u16,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct OutcomeFact {
    pub run_id: Uuid,
    pub request_id: Uuid,
    pub run_class: String,
    pub lane: String,
    pub skill: String,
    pub rubric_sha256: String,
    pub prompt_template_sha256: String,
    pub routing_config_version: String,
    pub terminal_state: String,
    pub queued_at: String,
    pub started_at: Option<String>,
    pub finished_at: String,
    pub duration_ms: Option<i64>,
    pub quotes: Vec<LedgerQuote>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerQuote {
    pub event_id: i64,
    pub event_type: String,
    pub json_pointer: String,
    pub trust: String,
    pub source_sha256: String,
    pub start_char: usize,
    pub end_char: usize,
    pub text: String,
    pub truncated: bool,
}

#[derive(Debug, Error)]
pub enum LessonsError {
    #[error("lessons-report database read failed")]
    Database(#[from] sqlx::Error),
    #[error("lessons-report timestamp is not representable as RFC 3339")]
    Timestamp(#[from] time::error::Format),
    #[error("lessons-report ledger row is malformed: {0}")]
    Malformed(&'static str),
    #[error("lessons-report JSON serialization failed")]
    Json(#[from] serde_json::Error),
}

impl LessonsReport {
    pub fn validate(&self) -> Result<(), LessonsError> {
        if self.schema_version != LESSONS_REPORT_SCHEMA_VERSION
            || self.policy_pr_threshold != POLICY_PR_THRESHOLD
            || self.selection.run_class != "production"
            || !self.selection.terminal_runs_only
            || self.selection.quote_sources
                != [QuoteSource {
                    event_type: "run.killed".to_owned(),
                    json_pointer: "/reason".to_owned(),
                    trust: "untrusted_operator_quote".to_owned(),
                }]
            || self.selection.max_quotes_per_run != MAX_QUOTES_PER_RUN
            || self.selection.max_quotes_per_report != MAX_QUOTES_PER_REPORT
            || self.selection.max_quote_chars != MAX_QUOTE_CHARS
            || self.snapshot_max_event_id < 0
            || self.production_run_count != self.runs.len()
        {
            return Err(LessonsError::Malformed("report envelope"));
        }
        let mut run_ids = BTreeSet::new();
        let mut quote_count = 0_usize;
        for run in &self.runs {
            if run.run_class != "production"
                || !run_ids.insert(run.run_id)
                || run.lane.trim().is_empty()
                || run.skill.trim().is_empty()
                || run.rubric_sha256.len() != 64
                || !run
                    .rubric_sha256
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
                || run.prompt_template_sha256.len() != 64
                || !run
                    .prompt_template_sha256
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
                || run.routing_config_version.trim().is_empty()
                || run.terminal_state.trim().is_empty()
                || run.duration_ms.is_some_and(|duration| duration < 0)
                || run.quotes.len() > MAX_QUOTES_PER_RUN
            {
                return Err(LessonsError::Malformed("outcome fact"));
            }
            quote_count += run.quotes.len();
            for quote in &run.quotes {
                if quote.event_id <= 0
                    || quote.event_id > self.snapshot_max_event_id
                    || quote.event_type != "run.killed"
                    || quote.json_pointer != "/reason"
                    || quote.trust != "untrusted_operator_quote"
                    || quote.source_sha256.len() != 64
                    || !quote
                        .source_sha256
                        .bytes()
                        .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
                    || quote.start_char != 0
                    || quote.end_char != quote.text.chars().count()
                    || quote.text.chars().count() > MAX_QUOTE_CHARS
                {
                    return Err(LessonsError::Malformed("ledger quote"));
                }
            }
        }
        if quote_count > MAX_QUOTES_PER_REPORT {
            return Err(LessonsError::Malformed("report quote count"));
        }
        let mut expected = BTreeMap::<CohortDimensions, CohortAggregate>::new();
        for run in &self.runs {
            let aggregate = expected
                .entry((
                    run.lane.clone(),
                    run.skill.clone(),
                    run.rubric_sha256.clone(),
                    run.prompt_template_sha256.clone(),
                    run.routing_config_version.clone(),
                ))
                .or_default();
            aggregate.0.push(run.run_id);
            *aggregate.1.entry(run.terminal_state.clone()).or_default() += 1;
        }
        for (run_ids, _) in expected.values_mut() {
            run_ids.sort_unstable();
        }
        let mut actual_keys = BTreeSet::new();
        let cohort_total = self.cohorts.iter().try_fold(0_usize, |total, cohort| {
            let dimensions = (
                cohort.lane.clone(),
                cohort.skill.clone(),
                cohort.rubric_sha256.clone(),
                cohort.prompt_template_sha256.clone(),
                cohort.routing_config_version.clone(),
            );
            if !actual_keys.insert(dimensions.clone()) {
                return Err(LessonsError::Malformed("duplicate cohort"));
            }
            let outcome_total = cohort
                .outcomes
                .iter()
                .try_fold(0_usize, |subtotal, outcome| {
                    if outcome.terminal_state.trim().is_empty()
                        || outcome.rate_basis_points > 10_000
                        || outcome.rate_basis_points
                            != rate_basis_points(outcome.count, cohort.production_run_count)
                    {
                        return Err(LessonsError::Malformed("cohort outcome"));
                    }
                    subtotal
                        .checked_add(outcome.count)
                        .ok_or(LessonsError::Malformed("cohort count"))
                })?;
            if cohort.cohort_key
                != cohort_key(
                    &cohort.lane,
                    &cohort.skill,
                    &cohort.rubric_sha256,
                    &cohort.prompt_template_sha256,
                    &cohort.routing_config_version,
                )
                || cohort.production_run_count != outcome_total
                || cohort.run_ids.len() != cohort.production_run_count
                || cohort.run_ids.windows(2).any(|pair| pair[0] >= pair[1])
                || cohort.eligible_for_policy_pr
                    != (cohort.production_run_count >= POLICY_PR_THRESHOLD)
                || expected.get(&dimensions)
                    != Some(&(
                        cohort.run_ids.clone(),
                        cohort
                            .outcomes
                            .iter()
                            .map(|outcome| (outcome.terminal_state.clone(), outcome.count))
                            .collect(),
                    ))
            {
                return Err(LessonsError::Malformed("cohort"));
            }
            total
                .checked_add(cohort.production_run_count)
                .ok_or(LessonsError::Malformed("cohort total"))
        })?;
        if cohort_total != self.production_run_count || actual_keys.len() != expected.len() {
            return Err(LessonsError::Malformed("cohort coverage"));
        }
        Ok(())
    }

    pub fn to_pretty_json(&self) -> Result<String, LessonsError> {
        self.validate()?;
        Ok(format!("{}\n", serde_json::to_string_pretty(self)?))
    }

    pub fn sha256(&self) -> Result<String, LessonsError> {
        Ok(hex::encode(Sha256::digest(
            self.to_pretty_json()?.as_bytes(),
        )))
    }
}

pub async fn generate(pool: &PgPool) -> Result<LessonsReport, LessonsError> {
    let mut transaction = pool.begin().await?;
    sqlx::query("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        .execute(&mut *transaction)
        .await?;
    let snapshot_max_event_id: i64 =
        sqlx::query_scalar("SELECT COALESCE(max(id), 0) FROM factory.events")
            .fetch_one(&mut *transaction)
            .await?;
    let run_rows = sqlx::query(
        r#"
        SELECT
            id,
            request_id,
            run_class::text AS run_class,
            lane,
            skill,
            encode(rubric_hash, 'hex') AS rubric_sha256,
            encode(prompt_template_hash, 'hex') AS prompt_template_sha256,
            routing_config_version,
            state::text AS terminal_state,
            queued_at,
            started_at,
            finished_at
        FROM factory.runs
        WHERE run_class = 'production'
          AND finished_at IS NOT NULL
          AND rubric_hash IS NOT NULL
          AND prompt_template_hash IS NOT NULL
          AND routing_config_version IS NOT NULL
        ORDER BY lane, skill, rubric_hash, prompt_template_hash,
                 routing_config_version, queued_at, id
        "#,
    )
    .fetch_all(&mut *transaction)
    .await?;
    let quote_rows = sqlx::query(
        r#"
        SELECT
            event.id AS event_id,
            event.run_id,
            event.event_type,
            event.payload
        FROM factory.events AS event
        JOIN factory.runs AS run ON run.id = event.run_id
        WHERE run.run_class = 'production'
          AND run.finished_at IS NOT NULL
          AND run.rubric_hash IS NOT NULL
          AND run.prompt_template_hash IS NOT NULL
          AND run.routing_config_version IS NOT NULL
          AND event.event_type = 'run.killed'
          AND event.id <= $1
        ORDER BY event.run_id, event.id
        "#,
    )
    .bind(snapshot_max_event_id)
    .fetch_all(&mut *transaction)
    .await?;
    let report = build_report(snapshot_max_event_id, &run_rows, &quote_rows)?;
    transaction.commit().await?;
    report.validate()?;
    Ok(report)
}

fn build_report(
    snapshot_max_event_id: i64,
    run_rows: &[sqlx::postgres::PgRow],
    quote_rows: &[sqlx::postgres::PgRow],
) -> Result<LessonsReport, LessonsError> {
    let mut quotes_by_run: BTreeMap<Uuid, Vec<LedgerQuote>> = BTreeMap::new();
    let mut report_quote_count = 0_usize;
    for row in quote_rows {
        if report_quote_count == MAX_QUOTES_PER_REPORT {
            break;
        }
        let run_id: Uuid = row.try_get("run_id")?;
        let quotes = quotes_by_run.entry(run_id).or_default();
        if quotes.len() == MAX_QUOTES_PER_RUN {
            continue;
        }
        let event_type: String = row.try_get("event_type")?;
        if event_type != "run.killed" {
            continue;
        }
        let payload: serde_json::Value = row.try_get("payload")?;
        let Some(source) = payload
            .pointer("/reason")
            .and_then(serde_json::Value::as_str)
        else {
            continue;
        };
        let (text, truncated) = truncate_quote(source);
        let end_char = text.chars().count();
        quotes.push(LedgerQuote {
            event_id: row.try_get("event_id")?,
            event_type,
            json_pointer: "/reason".to_owned(),
            trust: "untrusted_operator_quote".to_owned(),
            source_sha256: hex::encode(Sha256::digest(source.as_bytes())),
            start_char: 0,
            end_char,
            text,
            truncated,
        });
        report_quote_count += 1;
    }

    let mut cohorts = BTreeMap::<CohortDimensions, CohortAggregate>::new();
    let mut runs = Vec::with_capacity(run_rows.len());
    for row in run_rows {
        let run_id: Uuid = row.try_get("id")?;
        let run_class: String = row.try_get("run_class")?;
        if run_class != "production" {
            return Err(LessonsError::Malformed("non-production query row"));
        }
        let skill: String = row.try_get("skill")?;
        let rubric_sha256: String = row.try_get("rubric_sha256")?;
        let prompt_template_sha256: String = row.try_get("prompt_template_sha256")?;
        let routing_config_version: String = row.try_get("routing_config_version")?;
        let terminal_state: String = row.try_get("terminal_state")?;
        let queued_at: OffsetDateTime = row.try_get("queued_at")?;
        let started_at: Option<OffsetDateTime> = row.try_get("started_at")?;
        let finished_at: OffsetDateTime = row.try_get("finished_at")?;
        let duration_ms = started_at
            .map(|started| (finished_at - started).whole_milliseconds())
            .map(|milliseconds| {
                i64::try_from(milliseconds).map_err(|_| LessonsError::Malformed("duration"))
            })
            .transpose()?;
        let lane: String = row.try_get("lane")?;
        let cohort = cohorts
            .entry((
                lane.clone(),
                skill.clone(),
                rubric_sha256.clone(),
                prompt_template_sha256.clone(),
                routing_config_version.clone(),
            ))
            .or_default();
        cohort.0.push(run_id);
        *cohort.1.entry(terminal_state.clone()).or_default() += 1;
        runs.push(OutcomeFact {
            run_id,
            request_id: row.try_get("request_id")?,
            run_class,
            lane,
            skill,
            rubric_sha256,
            prompt_template_sha256,
            routing_config_version,
            terminal_state,
            queued_at: queued_at.format(&Rfc3339)?,
            started_at: started_at.map(|value| value.format(&Rfc3339)).transpose()?,
            finished_at: finished_at.format(&Rfc3339)?,
            duration_ms,
            quotes: quotes_by_run.remove(&run_id).unwrap_or_default(),
        });
    }
    let cohorts = cohorts
        .into_iter()
        .map(
            |(
                (lane, skill, rubric_sha256, prompt_template_sha256, routing_config_version),
                (mut run_ids, outcomes),
            )| {
                run_ids.sort_unstable();
                let production_run_count = outcomes.values().sum::<usize>();
                let outcomes = outcomes
                    .into_iter()
                    .map(|(terminal_state, count)| OutcomeRate {
                        terminal_state,
                        count,
                        rate_basis_points: rate_basis_points(count, production_run_count),
                    })
                    .collect();
                LessonCohort {
                    cohort_key: cohort_key(
                        &lane,
                        &skill,
                        &rubric_sha256,
                        &prompt_template_sha256,
                        &routing_config_version,
                    ),
                    lane,
                    skill,
                    rubric_sha256,
                    prompt_template_sha256,
                    routing_config_version,
                    production_run_count,
                    eligible_for_policy_pr: production_run_count >= POLICY_PR_THRESHOLD,
                    run_ids,
                    outcomes,
                }
            },
        )
        .collect();
    Ok(LessonsReport {
        schema_version: LESSONS_REPORT_SCHEMA_VERSION,
        snapshot_max_event_id,
        selection: ReportSelection {
            run_class: "production".to_owned(),
            terminal_runs_only: true,
            quote_sources: vec![QuoteSource {
                event_type: "run.killed".to_owned(),
                json_pointer: "/reason".to_owned(),
                trust: "untrusted_operator_quote".to_owned(),
            }],
            max_quotes_per_run: MAX_QUOTES_PER_RUN,
            max_quotes_per_report: MAX_QUOTES_PER_REPORT,
            max_quote_chars: MAX_QUOTE_CHARS,
        },
        policy_pr_threshold: POLICY_PR_THRESHOLD,
        production_run_count: runs.len(),
        cohorts,
        runs,
    })
}

fn truncate_quote(value: &str) -> (String, bool) {
    let mut characters = value.chars();
    let text: String = characters.by_ref().take(MAX_QUOTE_CHARS).collect();
    (text, characters.next().is_some())
}

fn rate_basis_points(count: usize, total: usize) -> u16 {
    if total == 0 {
        return 0;
    }
    u16::try_from(count.saturating_mul(10_000) / total).unwrap_or(10_000)
}

fn cohort_key(
    lane: &str,
    skill: &str,
    rubric_sha256: &str,
    prompt_template_sha256: &str,
    routing_config_version: &str,
) -> String {
    let mut hasher = Sha256::new();
    hasher.update(lane.as_bytes());
    hasher.update([0]);
    hasher.update(skill.as_bytes());
    hasher.update([0]);
    hasher.update(rubric_sha256.as_bytes());
    hasher.update([0]);
    hasher.update(prompt_template_sha256.as_bytes());
    hasher.update([0]);
    hasher.update(routing_config_version.as_bytes());
    format!("cohort:{}", hex::encode(hasher.finalize()))
}

#[cfg(test)]
mod tests {
    use super::{MAX_QUOTE_CHARS, rate_basis_points, truncate_quote};

    #[test]
    fn quote_bound_is_unicode_scalar_safe() {
        let value = format!("{}tail", "🚀".repeat(MAX_QUOTE_CHARS));
        let (quote, truncated) = truncate_quote(&value);
        assert_eq!(quote.chars().count(), MAX_QUOTE_CHARS);
        assert!(truncated);
    }

    #[test]
    fn rates_are_integer_and_deterministic() {
        assert_eq!(rate_basis_points(1, 3), 3_333);
        assert_eq!(rate_basis_points(0, 0), 0);
        assert_eq!(rate_basis_points(10, 10), 10_000);
    }
}
