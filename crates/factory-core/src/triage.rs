//! Typed triage intent, executable rubric policy, and content-trust framing.
//!
//! Lane classification accepts only a validated [`TaskSpec`]. The free-text
//! request is deliberately absent from the classifier's function signature.

use std::{
    collections::{BTreeMap, BTreeSet},
    fmt,
};

use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use thiserror::Error;

/// The sole supported TaskSpec schema in Session 8.
pub const TASK_SPEC_SCHEMA_VERSION: u16 = 1;

const RUBRIC_BEGIN: &str = "<!-- FACTORY_RUBRIC_JSON_BEGIN -->";
const RUBRIC_END: &str = "<!-- FACTORY_RUBRIC_JSON_END -->";
const HARD_RULES_PLACEHOLDER: &str = "{{CONSTITUTION_HARD_RULES}}";
const UNTRUSTED_PLACEHOLDER: &str = "{{UNTRUSTED_CHANNELS_JSON}}";

/// The four ruled lanes.
#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize)]
pub enum Lane {
    A,
    B,
    C,
    D,
}

impl fmt::Display for Lane {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::A => "A",
            Self::B => "B",
            Self::C => "C",
            Self::D => "D",
        })
    }
}

impl Lane {
    /// Parse the stable single-letter ledger representation.
    pub fn parse(value: &str) -> Result<Self, TriageError> {
        match value {
            "A" => Ok(Self::A),
            "B" => Ok(Self::B),
            "C" => Ok(Self::C),
            "D" => Ok(Self::D),
            _ => Err(TriageError::InvalidLane(value.to_owned())),
        }
    }
}

/// Semantic intent selected by triage before deterministic lane policy runs.
#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum IntentClass {
    InternalDisplay,
    InternalReport,
    InternalWording,
    InternalOrdering,
    InternalValidation,
    Feature,
    SchemaOrDataModel,
    AuthPermissionsOrSecrets,
    PaymentsPricingOrAccounting,
    OutboundOrScheduledAutomation,
    CustomerFacing,
    DataCorrection,
    Operations,
    Unclear,
}

impl IntentClass {
    const ALL: [Self; 14] = [
        Self::InternalDisplay,
        Self::InternalReport,
        Self::InternalWording,
        Self::InternalOrdering,
        Self::InternalValidation,
        Self::Feature,
        Self::SchemaOrDataModel,
        Self::AuthPermissionsOrSecrets,
        Self::PaymentsPricingOrAccounting,
        Self::OutboundOrScheduledAutomation,
        Self::CustomerFacing,
        Self::DataCorrection,
        Self::Operations,
        Self::Unclear,
    ];

    fn policy_name(self) -> &'static str {
        match self {
            Self::InternalDisplay => "internal_display",
            Self::InternalReport => "internal_report",
            Self::InternalWording => "internal_wording",
            Self::InternalOrdering => "internal_ordering",
            Self::InternalValidation => "internal_validation",
            Self::Feature => "feature",
            Self::SchemaOrDataModel => "schema_or_data_model",
            Self::AuthPermissionsOrSecrets => "auth_permissions_or_secrets",
            Self::PaymentsPricingOrAccounting => "payments_pricing_or_accounting",
            Self::OutboundOrScheduledAutomation => "outbound_or_scheduled_automation",
            Self::CustomerFacing => "customer_facing",
            Self::DataCorrection => "data_correction",
            Self::Operations => "operations",
            Self::Unclear => "unclear",
        }
    }
}

/// One exact page/file target supported by repository evidence.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TaskTarget {
    pub page: String,
    pub path: String,
    pub evidence: String,
}

/// A deterministic acceptance assertion. It contains no command string.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AcceptanceTest {
    pub id: String,
    pub kind: AcceptanceKind,
    pub assertion: String,
}

/// Closed set of acceptance mechanisms accepted by the triage contract.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AcceptanceKind {
    ExactText,
    SortedPermutation,
    UnitTest,
    StaticAnalysis,
    BrowserEvidence,
    Invariant,
}

/// Explicit change-surface flags required even when false.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChangeFlags {
    pub dependency_changes: bool,
    pub test_changes: bool,
    pub ci_changes: bool,
}

/// Maximum effect budget and the human/policy source that authorized it.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChangeBudget {
    pub max_files: u16,
    pub max_changed_lines: u32,
    pub authority: BudgetAuthority,
}

/// Budget authority distinguishes estimates from actual authorization.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BudgetAuthority {
    LaneAPolicy,
    TriageEstimate,
    HumanApproved,
}

/// Guide injected before implementation.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TaskGuide {
    pub kind: GuideKind,
    pub reference: String,
}

/// A lane-A skill or a human-approved lane-B plan can be the Guide.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum GuideKind {
    SkillPlaybook,
    ApprovedPlan,
}

/// Schema-validated authoritative intent for all downstream gates.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TaskSpec {
    pub schema_version: u16,
    pub rubric_version: String,
    pub intent_class: IntentClass,
    pub objective: String,
    pub named_skill: Option<String>,
    pub targets: Vec<TaskTarget>,
    pub allowed_paths: Vec<String>,
    pub allowed_globs: Vec<String>,
    pub acceptance_tests: Vec<AcceptanceTest>,
    pub flags: ChangeFlags,
    pub budget: Option<ChangeBudget>,
    pub guide: Option<TaskGuide>,
}

impl TaskSpec {
    /// Deserialize and validate a TaskSpec without consulting request text.
    pub fn parse_json(input: &str) -> Result<Self, TriageError> {
        let task_spec: Self = serde_json::from_str(input)?;
        task_spec.validate()?;
        Ok(task_spec)
    }

    /// Validate schema and bounded, repo-relative effect fields.
    pub fn validate(&self) -> Result<(), TriageError> {
        if self.schema_version != TASK_SPEC_SCHEMA_VERSION {
            return Err(TriageError::UnsupportedTaskSpecSchema(self.schema_version));
        }
        bounded_nonblank("rubric_version", &self.rubric_version, 64)?;
        bounded_nonblank("objective", &self.objective, 2_000)?;
        if let Some(skill) = &self.named_skill {
            bounded_nonblank("named_skill", skill, 128)?;
        }
        if self.targets.len() > 100
            || self.allowed_paths.len() > 100
            || self.allowed_globs.len() > 100
            || self.acceptance_tests.len() > 100
        {
            return Err(TriageError::CollectionTooLarge);
        }

        let mut target_paths = BTreeSet::new();
        for target in &self.targets {
            bounded_nonblank("target.page", &target.page, 256)?;
            validate_repo_path(&target.path, false)?;
            bounded_nonblank("target.evidence", &target.evidence, 1_000)?;
            if !target_paths.insert(&target.path) {
                return Err(TriageError::DuplicateValue("targets.path"));
            }
        }
        validate_unique_paths("allowed_paths", &self.allowed_paths, false)?;
        validate_unique_paths("allowed_globs", &self.allowed_globs, true)?;

        let mut acceptance_ids = BTreeSet::new();
        for acceptance in &self.acceptance_tests {
            if acceptance.id.is_empty()
                || acceptance.id.len() > 64
                || !acceptance
                    .id
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"._-".contains(&byte))
            {
                return Err(TriageError::InvalidAcceptanceId(acceptance.id.clone()));
            }
            if !acceptance_ids.insert(&acceptance.id) {
                return Err(TriageError::DuplicateValue("acceptance_tests.id"));
            }
            bounded_nonblank("acceptance_tests.assertion", &acceptance.assertion, 2_000)?;
        }
        if let Some(budget) = self.budget
            && (budget.max_files == 0 || budget.max_changed_lines == 0)
        {
            return Err(TriageError::InvalidBudget);
        }
        if let Some(guide) = &self.guide {
            bounded_nonblank("guide.reference", &guide.reference, 512)?;
        }
        Ok(())
    }

    /// Validate the stronger contract required when a human-approved B plan
    /// replaces lane-A caps and becomes the implementation Guide.
    pub fn validate_human_approved(&self) -> Result<(), TriageError> {
        self.validate()?;
        if !matches!(
            self.budget,
            Some(ChangeBudget {
                authority: BudgetAuthority::HumanApproved,
                ..
            })
        ) {
            return Err(TriageError::HumanApprovalMissingBudget);
        }
        if !matches!(
            self.guide,
            Some(TaskGuide {
                kind: GuideKind::ApprovedPlan,
                ..
            })
        ) {
            return Err(TriageError::HumanApprovalMissingGuide);
        }
        if self.allowed_paths.is_empty() && self.allowed_globs.is_empty() {
            return Err(TriageError::HumanApprovalMissingScope);
        }
        if self.acceptance_tests.is_empty() {
            return Err(TriageError::HumanApprovalMissingAcceptance);
        }
        Ok(())
    }

    /// Stable digest recorded beside the JSON ledger payload.
    pub fn sha256(&self) -> Result<[u8; 32], TriageError> {
        self.validate()?;
        Ok(Sha256::digest(serde_json::to_vec(self)?).into())
    }
}

/// The complete model output. Confidence is intentionally outside TaskSpec.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TriageOutput {
    pub task_spec: TaskSpec,
    pub confidence_basis_points: u16,
}

impl TriageOutput {
    /// Parse the exact no-prose triage output contract.
    pub fn parse_json(input: &str) -> Result<Self, TriageError> {
        let output: Self = serde_json::from_str(input)?;
        output.validate()?;
        Ok(output)
    }

    /// Validate telemetry bounds and the authoritative TaskSpec.
    pub fn validate(&self) -> Result<(), TriageError> {
        if self.confidence_basis_points > 10_000 {
            return Err(TriageError::InvalidConfidence);
        }
        self.task_spec.validate()
    }
}

/// Deterministic classification, including stable policy reason codes.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Classification {
    pub lane: Lane,
    pub reasons: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RubricDocument {
    version: String,
    task_spec_schema_version: u16,
    lane_a: LaneAPolicy,
    intent_routes: Vec<IntentRoute>,
    deny_paths: Vec<DenyPathRule>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct LaneAPolicy {
    max_files: u16,
    max_changed_lines: u32,
    allowed_path_prefixes: Vec<String>,
    require_exact_paths: bool,
    require_named_targets: bool,
    require_deterministic_acceptance: bool,
    supported_skills: Vec<String>,
}

#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct IntentRoute {
    intent: IntentClass,
    lane: Lane,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct DenyPathRule {
    #[serde(rename = "match")]
    match_kind: PathMatch,
    value: String,
    lane: Lane,
    reason: String,
}

#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(rename_all = "snake_case")]
enum PathMatch {
    Exact,
    Prefix,
    Suffix,
    Component,
    FileName,
}

/// Parsed executable block from `policy/rubric.md`.
#[derive(Clone, Debug)]
pub struct Rubric {
    document: RubricDocument,
    source_sha256: [u8; 32],
}

impl Rubric {
    /// Parse and validate the one machine-readable JSON block in rubric.md.
    pub fn parse_markdown(markdown: &str) -> Result<Self, TriageError> {
        let begin = markdown
            .find(RUBRIC_BEGIN)
            .ok_or(TriageError::RubricMarkerMissing)?;
        let after_begin = begin + RUBRIC_BEGIN.len();
        let relative_end = markdown[after_begin..]
            .find(RUBRIC_END)
            .ok_or(TriageError::RubricMarkerMissing)?;
        let end = after_begin + relative_end;
        if markdown[end + RUBRIC_END.len()..].contains(RUBRIC_END)
            || markdown[after_begin..end].contains(RUBRIC_BEGIN)
        {
            return Err(TriageError::RubricMarkerRepeated);
        }
        let document: RubricDocument = serde_json::from_str(markdown[after_begin..end].trim())?;
        validate_rubric(&document)?;
        Ok(Self {
            document,
            source_sha256: Sha256::digest(markdown.as_bytes()).into(),
        })
    }

    /// Version carried into every TaskSpec and ledger row.
    #[must_use]
    pub fn version(&self) -> &str {
        &self.document.version
    }

    /// SHA-256 of the complete human-ruled rubric markdown.
    #[must_use]
    pub fn source_sha256(&self) -> &[u8; 32] {
        &self.source_sha256
    }

    /// Classify solely from typed intent. Model confidence is not accepted by
    /// this function, so it cannot promote a lane by construction.
    pub fn classify(&self, task_spec: &TaskSpec) -> Result<Classification, TriageError> {
        task_spec.validate()?;
        if task_spec.rubric_version != self.document.version {
            return Err(TriageError::RubricVersionMismatch {
                task: task_spec.rubric_version.clone(),
                loaded: self.document.version.clone(),
            });
        }
        let route = self
            .document
            .intent_routes
            .iter()
            .find(|route| route.intent == task_spec.intent_class)
            .ok_or(TriageError::IntentRouteMissing(task_spec.intent_class))?;
        if route.lane != Lane::A {
            return Ok(Classification {
                lane: route.lane,
                reasons: vec![format!("intent.{}", task_spec.intent_class.policy_name())],
            });
        }

        let mut lane_b_reasons = BTreeSet::new();
        let mut lane_d_reasons = BTreeSet::new();
        if task_spec.flags.dependency_changes {
            lane_b_reasons.insert("flag.dependency_changes".to_owned());
        }
        if task_spec.flags.ci_changes {
            lane_b_reasons.insert("flag.ci_changes".to_owned());
        }
        for path in task_spec
            .allowed_paths
            .iter()
            .chain(task_spec.allowed_globs.iter())
            .chain(task_spec.targets.iter().map(|target| &target.path))
        {
            for deny in &self.document.deny_paths {
                if deny.matches(path) && deny.lane == Lane::B {
                    lane_b_reasons.insert(deny.reason.clone());
                }
            }
            if !self
                .document
                .lane_a
                .allowed_path_prefixes
                .iter()
                .any(|prefix| path.starts_with(prefix))
            {
                lane_b_reasons.insert("lane_a.path_outside_internal_mfieldbook".to_owned());
            }
        }
        if self.document.lane_a.require_exact_paths && !task_spec.allowed_globs.is_empty() {
            lane_b_reasons.insert("lane_a.effect_glob_not_exact".to_owned());
        }
        let budget = task_spec.budget;
        if !matches!(
            budget,
            Some(ChangeBudget {
                authority: BudgetAuthority::LaneAPolicy,
                ..
            })
        ) {
            lane_b_reasons.insert("lane_a.budget_not_policy_authorized".to_owned());
        }
        if budget.is_some_and(|budget| {
            budget.max_files > self.document.lane_a.max_files
                || budget.max_changed_lines > self.document.lane_a.max_changed_lines
        }) || task_spec.allowed_paths.len() > usize::from(self.document.lane_a.max_files)
        {
            lane_b_reasons.insert("lane_a.over_cap".to_owned());
        }
        match &task_spec.named_skill {
            Some(skill) if self.document.lane_a.supported_skills.contains(skill) => {}
            _ => {
                lane_b_reasons.insert("lane_a.named_skill_missing_or_unsupported".to_owned());
            }
        }
        match (&task_spec.named_skill, &task_spec.guide) {
            (
                Some(skill),
                Some(TaskGuide {
                    kind: GuideKind::SkillPlaybook,
                    reference,
                }),
            ) if skill == reference => {}
            _ => {
                lane_b_reasons.insert("lane_a.skill_guide_missing_or_mismatched".to_owned());
            }
        }
        if self.document.lane_a.require_deterministic_acceptance
            && task_spec.acceptance_tests.is_empty()
        {
            lane_b_reasons.insert("lane_a.acceptance_missing".to_owned());
        }
        if self.document.lane_a.require_named_targets {
            let targets: BTreeSet<&str> = task_spec
                .targets
                .iter()
                .map(|target| target.path.as_str())
                .collect();
            let allowed: BTreeSet<&str> =
                task_spec.allowed_paths.iter().map(String::as_str).collect();
            if allowed.is_empty() || targets != allowed {
                lane_d_reasons.insert("lane_a.exact_target_not_evidenced".to_owned());
            }
        }

        if !lane_b_reasons.is_empty() {
            return Ok(Classification {
                lane: Lane::B,
                reasons: lane_b_reasons.into_iter().collect(),
            });
        }
        if !lane_d_reasons.is_empty() {
            return Ok(Classification {
                lane: Lane::D,
                reasons: lane_d_reasons.into_iter().collect(),
            });
        }
        Ok(Classification {
            lane: Lane::A,
            reasons: vec!["lane_a.all_requirements_met".to_owned()],
        })
    }
}

impl DenyPathRule {
    fn matches(&self, path: &str) -> bool {
        match self.match_kind {
            PathMatch::Exact => path == self.value,
            PathMatch::Prefix => path.starts_with(&self.value),
            PathMatch::Suffix => path.ends_with(&self.value),
            PathMatch::Component => path.split('/').any(|component| component == self.value),
            PathMatch::FileName => path.rsplit('/').next() == Some(self.value.as_str()),
        }
    }
}

/// One explicitly labeled channel inserted into the triage prompt as JSON.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct UntrustedChannel<'a> {
    pub channel: &'a str,
    pub authority: &'static str,
    pub content: &'a str,
}

impl<'a> UntrustedChannel<'a> {
    /// Construct a channel whose authority cannot be caller-controlled.
    #[must_use]
    pub const fn new(channel: &'a str, content: &'a str) -> Self {
        Self {
            channel,
            authority: "none",
            content,
        }
    }
}

/// Render the no-shell triage prompt with exact constitution rules and JSON
/// datamarking. Untrusted content is substituted last, so it cannot expand a
/// template token that it contains.
pub fn render_triage_prompt(
    template: &str,
    constitution: &str,
    channels: &[UntrustedChannel<'_>],
) -> Result<String, TriageError> {
    validate_triage_frontmatter(template)?;
    let hard_rules = extract_hard_rules(constitution)?;
    require_one_placeholder(template, HARD_RULES_PLACEHOLDER)?;
    require_one_placeholder(template, UNTRUSTED_PLACEHOLDER)?;
    for channel in channels {
        bounded_nonblank("untrusted channel label", channel.channel, 128)?;
    }
    let datamarked = serde_json::to_string_pretty(&serde_json::json!({
        "authority": "none",
        "channels": channels,
    }))?
    .replace('<', "\\u003c")
    .replace('>', "\\u003e")
    .replace('&', "\\u0026");
    let with_constitution = template.replace(HARD_RULES_PLACEHOLDER, hard_rules);
    Ok(with_constitution.replace(UNTRUSTED_PLACEHOLDER, &datamarked))
}

/// Assert that the prompt frontmatter exactly matches its declared harness.
pub fn validate_triage_frontmatter(template: &str) -> Result<(), TriageError> {
    let mut lines = template.lines();
    if lines.next() != Some("---") {
        return Err(TriageError::InvalidTriageFrontmatter);
    }
    let mut harness = None;
    let mut tools = None;
    let mut closed = false;
    for line in &mut lines {
        if line == "---" {
            closed = true;
            break;
        }
        if line.trim().is_empty() {
            continue;
        }
        let (key, value) = line
            .split_once(':')
            .ok_or(TriageError::InvalidTriageFrontmatter)?;
        match key.trim() {
            "harness" => {
                if harness.is_some() {
                    return Err(TriageError::InvalidTriageFrontmatter);
                }
                harness = Some(value.trim());
            }
            "tools" => {
                if tools.is_some() {
                    return Err(TriageError::InvalidTriageFrontmatter);
                }
                tools = Some(
                    value
                        .split(',')
                        .map(str::trim)
                        .filter(|value| !value.is_empty())
                        .collect::<Vec<_>>(),
                );
            }
            _ => {}
        }
    }
    if !closed {
        return Err(TriageError::InvalidTriageFrontmatter);
    }
    match (harness, tools.as_deref()) {
        (Some("api"), None) | (Some("claude-code"), Some(["Read", "Grep", "Glob"])) => Ok(()),
        (Some("api" | "claude-code"), _) => Err(TriageError::InvalidTriageToolAllowlist),
        _ => Err(TriageError::InvalidTriageHarness),
    }
}

fn validate_rubric(document: &RubricDocument) -> Result<(), TriageError> {
    bounded_nonblank("rubric.version", &document.version, 64)?;
    if document.task_spec_schema_version != TASK_SPEC_SCHEMA_VERSION {
        return Err(TriageError::UnsupportedTaskSpecSchema(
            document.task_spec_schema_version,
        ));
    }
    if document.lane_a.max_files == 0 || document.lane_a.max_changed_lines == 0 {
        return Err(TriageError::InvalidRubric("lane-A caps must be positive"));
    }
    if document.lane_a.allowed_path_prefixes.is_empty()
        || document.lane_a.supported_skills.is_empty()
    {
        return Err(TriageError::InvalidRubric(
            "lane-A paths and skills must be explicit",
        ));
    }
    let mut routes = BTreeMap::new();
    for route in &document.intent_routes {
        if routes.insert(route.intent, route.lane).is_some() {
            return Err(TriageError::InvalidRubric("duplicate intent route"));
        }
    }
    if IntentClass::ALL
        .iter()
        .any(|intent| !routes.contains_key(intent))
    {
        return Err(TriageError::InvalidRubric("incomplete intent routes"));
    }
    for rule in &document.deny_paths {
        bounded_nonblank("deny_paths.value", &rule.value, 512)?;
        bounded_nonblank("deny_paths.reason", &rule.reason, 128)?;
        if rule.lane != Lane::B {
            return Err(TriageError::InvalidRubric(
                "path deny rules must demote lane-A candidates to B",
            ));
        }
    }
    Ok(())
}

fn validate_unique_paths(
    field: &'static str,
    paths: &[String],
    allow_glob: bool,
) -> Result<(), TriageError> {
    let mut unique = BTreeSet::new();
    for path in paths {
        validate_repo_path(path, allow_glob)?;
        if !unique.insert(path) {
            return Err(TriageError::DuplicateValue(field));
        }
    }
    Ok(())
}

fn validate_repo_path(path: &str, allow_glob: bool) -> Result<(), TriageError> {
    bounded_nonblank("repository path", path, 512)?;
    if path.starts_with('/')
        || path.starts_with('~')
        || path.contains('\\')
        || path.chars().any(char::is_control)
        || path
            .split('/')
            .any(|component| component.is_empty() || component == "." || component == "..")
        || (!allow_glob && path.bytes().any(|byte| b"*?[]{}".contains(&byte)))
    {
        return Err(TriageError::UnsafeRepositoryPath(path.to_owned()));
    }
    Ok(())
}

fn bounded_nonblank(field: &'static str, value: &str, maximum: usize) -> Result<(), TriageError> {
    if value.trim().is_empty() || value.chars().count() > maximum {
        return Err(TriageError::InvalidText { field, maximum });
    }
    Ok(())
}

fn extract_hard_rules(constitution: &str) -> Result<&str, TriageError> {
    let start = constitution
        .find("## Hard rules")
        .ok_or(TriageError::ConstitutionHardRulesMissing)?;
    let rest = &constitution[start..];
    let end = rest.find("\n## ").unwrap_or(rest.len());
    Ok(rest[..end].trim_end())
}

fn require_one_placeholder(template: &str, placeholder: &'static str) -> Result<(), TriageError> {
    if template.match_indices(placeholder).count() != 1 {
        return Err(TriageError::PromptPlaceholderInvalid(placeholder));
    }
    Ok(())
}

/// Fail-closed errors for TaskSpec parsing, rubric policy, and prompt framing.
#[derive(Debug, Error)]
pub enum TriageError {
    #[error("triage JSON failed schema deserialization: {0}")]
    Json(#[from] serde_json::Error),
    #[error("unsupported TaskSpec schema version {0}")]
    UnsupportedTaskSpecSchema(u16),
    #[error("field {field} must contain 1 to {maximum} characters")]
    InvalidText { field: &'static str, maximum: usize },
    #[error("TaskSpec collection exceeds 100 entries")]
    CollectionTooLarge,
    #[error("duplicate value in {0}")]
    DuplicateValue(&'static str),
    #[error("unsafe repository path or glob: {0}")]
    UnsafeRepositoryPath(String),
    #[error("invalid acceptance-test id: {0}")]
    InvalidAcceptanceId(String),
    #[error("budget values must be positive")]
    InvalidBudget,
    #[error("confidence must be between 0 and 10000 basis points")]
    InvalidConfidence,
    #[error("rubric machine-readable markers are missing")]
    RubricMarkerMissing,
    #[error("rubric machine-readable markers are repeated")]
    RubricMarkerRepeated,
    #[error("invalid rubric: {0}")]
    InvalidRubric(&'static str),
    #[error("TaskSpec rubric version {task} does not match loaded rubric {loaded}")]
    RubricVersionMismatch { task: String, loaded: String },
    #[error("rubric has no route for {0:?}")]
    IntentRouteMissing(IntentClass),
    #[error("invalid lane value {0}")]
    InvalidLane(String),
    #[error("human-approved TaskSpec lacks a human-approved budget")]
    HumanApprovalMissingBudget,
    #[error("human-approved TaskSpec lacks an approved-plan Guide")]
    HumanApprovalMissingGuide,
    #[error("human-approved TaskSpec lacks allowed paths or globs")]
    HumanApprovalMissingScope,
    #[error("human-approved TaskSpec lacks deterministic acceptance")]
    HumanApprovalMissingAcceptance,
    #[error("triage frontmatter is missing or malformed")]
    InvalidTriageFrontmatter,
    #[error("triage harness must be exactly api or claude-code")]
    InvalidTriageHarness,
    #[error("triage tools do not exactly match the declared harness")]
    InvalidTriageToolAllowlist,
    #[error("constitution hard-rules section is missing")]
    ConstitutionHardRulesMissing,
    #[error("prompt placeholder must appear exactly once: {0}")]
    PromptPlaceholderInvalid(&'static str),
}
