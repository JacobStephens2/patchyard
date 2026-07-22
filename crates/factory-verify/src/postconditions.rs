//! Sort-skill postconditions over normalized, canned DOM evidence.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use thiserror::Error;
use unicode_normalization::UnicodeNormalization;

/// Evidence extracted from the same select elements before and after a patch.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SortEvidence {
    pub baseline: SortSnapshot,
    pub candidate: SortSnapshot,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SortSnapshot {
    pub source: SourceContract,
    pub callers: Vec<String>,
    pub selects: Vec<SelectSnapshot>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SourceContract {
    /// Exact normalized WHERE clause. Any byte change is a membership change.
    pub where_clause: String,
    pub order_by: String,
    pub sort_key: String,
    pub list_order_role: ListOrderRole,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ListOrderRole {
    Presentation,
    Priority,
    NotUsed,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SelectSnapshot {
    pub id: String,
    pub options: Vec<OptionSnapshot>,
}

#[derive(Clone, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(deny_unknown_fields)]
pub struct OptionSnapshot {
    pub label: String,
    pub value: String,
    pub selected: bool,
    #[serde(default)]
    pub blank_sentinel: bool,
}

#[derive(Debug, Error, Eq, PartialEq)]
pub enum PostconditionError {
    #[error("WHERE clause changed")]
    WhereClauseChanged,
    #[error("candidate sort key must be first_name_casefolded, got {0}")]
    SortKey(String),
    #[error("ORDER BY change is not the ruled presentation-only listOrder replacement")]
    UnsafeOrderByChange,
    #[error("shared-getter caller membership changed")]
    CallerMembership,
    #[error("duplicate caller evidence: {0}")]
    DuplicateCaller(String),
    #[error("select membership changed")]
    SelectMembership,
    #[error("sort evidence must enumerate at least one shared-getter caller")]
    NoCallers,
    #[error("sort evidence must contain at least one select")]
    NoSelects,
    #[error("duplicate select evidence: {0}")]
    DuplicateSelect(String),
    #[error("select {0} contains no options")]
    NoOptions(String),
    #[error("select {select} has an invalid blank sentinel at option {index}")]
    InvalidSentinel { select: String, index: usize },
    #[error("select {0} changed option membership, values, counts, or selection")]
    OptionMembership(String),
    #[error("select {0} does not preserve sentinel positions and stable first-name order")]
    WrongOrder(String),
}

/// Verify the ruled sort transformation as a stable permutation.
pub fn verify(evidence: &SortEvidence) -> Result<(), PostconditionError> {
    let baseline = &evidence.baseline;
    let candidate = &evidence.candidate;
    if baseline.source.where_clause != candidate.source.where_clause {
        return Err(PostconditionError::WhereClauseChanged);
    }
    if candidate.source.sort_key != "first_name_casefolded" {
        return Err(PostconditionError::SortKey(
            candidate.source.sort_key.clone(),
        ));
    }
    if baseline.source.order_by != candidate.source.order_by
        && !(baseline.source.order_by == "listOrder"
            && baseline.source.list_order_role == ListOrderRole::Presentation
            && candidate.source.order_by == "first_name_casefolded"
            && candidate.source.list_order_role == ListOrderRole::Presentation)
    {
        return Err(PostconditionError::UnsafeOrderByChange);
    }
    if baseline.callers.is_empty() || candidate.callers.is_empty() {
        return Err(PostconditionError::NoCallers);
    }
    if baseline.selects.is_empty() || candidate.selects.is_empty() {
        return Err(PostconditionError::NoSelects);
    }

    let baseline_callers = unique_set(&baseline.callers)?;
    let candidate_callers = unique_set(&candidate.callers)?;
    if baseline_callers != candidate_callers {
        return Err(PostconditionError::CallerMembership);
    }

    let baseline_selects = select_map(&baseline.selects)?;
    let candidate_selects = select_map(&candidate.selects)?;
    if baseline_selects.keys().collect::<Vec<_>>() != candidate_selects.keys().collect::<Vec<_>>() {
        return Err(PostconditionError::SelectMembership);
    }

    for (id, before) in baseline_selects {
        let after = candidate_selects[id];
        validate_options(id, &before.options)?;
        validate_options(id, &after.options)?;

        let before_members: BTreeMap<_, usize> = multiset(&before.options);
        let after_members: BTreeMap<_, usize> = multiset(&after.options);
        if before_members != after_members {
            return Err(PostconditionError::OptionMembership(id.clone()));
        }

        let mut sortable = before
            .options
            .iter()
            .filter(|option| !option.blank_sentinel)
            .cloned()
            .collect::<Vec<_>>();
        sortable.sort_by_key(|option| first_name_key(&option.label));
        let mut sorted = sortable.into_iter();
        let expected = before
            .options
            .iter()
            .map(|option| {
                if option.blank_sentinel {
                    option.clone()
                } else {
                    sorted.next().expect("sortable option count is unchanged")
                }
            })
            .collect::<Vec<_>>();
        if expected != after.options {
            return Err(PostconditionError::WrongOrder(id.clone()));
        }
    }
    Ok(())
}

fn unique_set(values: &[String]) -> Result<BTreeSet<&String>, PostconditionError> {
    let mut set = BTreeSet::new();
    for value in values {
        if !set.insert(value) {
            return Err(PostconditionError::DuplicateCaller(value.clone()));
        }
    }
    Ok(set)
}

fn select_map(
    selects: &[SelectSnapshot],
) -> Result<BTreeMap<&String, &SelectSnapshot>, PostconditionError> {
    let mut map = BTreeMap::new();
    for select in selects {
        if map.insert(&select.id, select).is_some() {
            return Err(PostconditionError::DuplicateSelect(select.id.clone()));
        }
    }
    Ok(map)
}

fn validate_options(id: &str, options: &[OptionSnapshot]) -> Result<(), PostconditionError> {
    if options.is_empty() {
        return Err(PostconditionError::NoOptions(id.to_owned()));
    }
    for (index, option) in options.iter().enumerate() {
        if option.blank_sentinel && (!option.label.is_empty() || !option.value.is_empty()) {
            return Err(PostconditionError::InvalidSentinel {
                select: id.to_owned(),
                index,
            });
        }
    }
    Ok(())
}

fn multiset(options: &[OptionSnapshot]) -> BTreeMap<&OptionSnapshot, usize> {
    let mut counts = BTreeMap::new();
    for option in options {
        *counts.entry(option).or_default() += 1;
    }
    counts
}

fn first_name_key(label: &str) -> String {
    label
        .split_whitespace()
        .next()
        .unwrap_or_default()
        .chars()
        .flat_map(stringprep::tables::case_fold_for_nfkc)
        .nfkc()
        .collect()
}
