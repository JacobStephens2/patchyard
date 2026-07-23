//! Typed plan-bin decisions and deterministic re-entry/close transitions.

use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use thiserror::Error;
use uuid::Uuid;

use crate::triage::{Lane, TaskSpec, TriageError};

/// One human decision, keyed for idempotent ledger application.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PlanDecision {
    pub id: Uuid,
    pub action: PlanAction,
}

impl PlanDecision {
    /// Stable digest used to recognize a retried decision ID.
    pub fn sha256(&self) -> Result<[u8; 32], PlanError> {
        Ok(Sha256::digest(serde_json::to_vec(self)?).into())
    }
}

/// Complete set of actions accepted while a request is in the plan bin.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "action", rename_all = "kebab-case", deny_unknown_fields)]
pub enum PlanAction {
    /// Human approval replaces the lane-A cap with this authoritative TaskSpec.
    ApproveB { task_spec: TaskSpec },
    /// Clarification remains untrusted request data and returns to triage.
    AnswerD { answer: String },
    /// A human executed the routed operations/data runbook.
    MarkCExecuted { runbook_reference: String },
    /// Any B/C/D plan can be declined or abandoned.
    Reject { reason: String },
}

/// Terminal plan-bin edge selected by deterministic lane/action policy.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum PlanTransitionKind {
    ReenterImplement,
    Retriage,
    CloseExecuted,
    CloseRejected,
}

/// Stable request outcome for plan-bin closes.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum PlanOutcome {
    #[serde(rename = "executed-not-code")]
    ExecutedNotCode,
    #[serde(rename = "rejected-at-plan")]
    RejectedAtPlan,
}

/// Validated transition result consumed by state and, later, the supervisor.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PlanTransition {
    pub kind: PlanTransitionKind,
    pub next_stage: Option<NextStage>,
    pub outcome: Option<PlanOutcome>,
    pub authoritative_task_spec: Option<TaskSpec>,
}

/// The only two re-entry targets ruled for the plan bin.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NextStage {
    Implement,
    Triage,
}

/// Apply lane/action compatibility without consulting request text.
pub fn transition_for(lane: Lane, decision: &PlanDecision) -> Result<PlanTransition, PlanError> {
    match (&decision.action, lane) {
        (PlanAction::ApproveB { task_spec }, Lane::B) => {
            task_spec.validate_human_approved()?;
            Ok(PlanTransition {
                kind: PlanTransitionKind::ReenterImplement,
                next_stage: Some(NextStage::Implement),
                outcome: None,
                authoritative_task_spec: Some(task_spec.clone()),
            })
        }
        (PlanAction::AnswerD { answer }, Lane::D) => {
            bounded_nonblank("clarification answer", answer, 20_000)?;
            Ok(PlanTransition {
                kind: PlanTransitionKind::Retriage,
                next_stage: Some(NextStage::Triage),
                outcome: None,
                authoritative_task_spec: None,
            })
        }
        (PlanAction::MarkCExecuted { runbook_reference }, Lane::C) => {
            bounded_nonblank("runbook reference", runbook_reference, 512)?;
            Ok(PlanTransition {
                kind: PlanTransitionKind::CloseExecuted,
                next_stage: None,
                outcome: Some(PlanOutcome::ExecutedNotCode),
                authoritative_task_spec: None,
            })
        }
        (PlanAction::Reject { reason }, Lane::B | Lane::C | Lane::D) => {
            bounded_nonblank("plan rejection reason", reason, 2_000)?;
            Ok(PlanTransition {
                kind: PlanTransitionKind::CloseRejected,
                next_stage: None,
                outcome: Some(PlanOutcome::RejectedAtPlan),
                authoritative_task_spec: None,
            })
        }
        (_, Lane::A) => Err(PlanError::LaneANeverEntersPlanBin),
        _ => Err(PlanError::ActionLaneMismatch { lane }),
    }
}

fn bounded_nonblank(field: &'static str, value: &str, maximum: usize) -> Result<(), PlanError> {
    if value.trim().is_empty() || value.chars().count() > maximum {
        return Err(PlanError::InvalidText { field, maximum });
    }
    Ok(())
}

/// Fail-closed plan decision errors.
#[derive(Debug, Error)]
pub enum PlanError {
    #[error("plan decision JSON failed serialization: {0}")]
    Json(#[from] serde_json::Error),
    #[error("approved plan TaskSpec is invalid: {0}")]
    TaskSpec(#[from] TriageError),
    #[error("lane A never enters the plan bin")]
    LaneANeverEntersPlanBin,
    #[error("plan action is incompatible with lane {lane}")]
    ActionLaneMismatch { lane: Lane },
    #[error("field {field} must contain 1 to {maximum} characters")]
    InvalidText { field: &'static str, maximum: usize },
}

#[cfg(test)]
mod tests {
    use super::{PlanAction, PlanDecision, PlanError, transition_for};
    use crate::triage::Lane;

    #[test]
    fn lane_and_action_compatibility_is_fail_closed() {
        let decision = PlanDecision {
            id: uuid::Uuid::new_v4(),
            action: PlanAction::AnswerD {
                answer: "The Simple Sales Report page.".to_owned(),
            },
        };
        assert!(transition_for(Lane::D, &decision).is_ok());
        assert!(matches!(
            transition_for(Lane::B, &decision),
            Err(PlanError::ActionLaneMismatch { lane: Lane::B })
        ));
        assert!(matches!(
            transition_for(Lane::A, &decision),
            Err(PlanError::LaneANeverEntersPlanBin)
        ));
    }
}
