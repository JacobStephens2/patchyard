---
title: Patchyard Factory triage rubric
rubric-version: 2026-07-23.1
task-spec-schema: policy/task-spec.schema.json
---

# Triage rubric

The typed `TaskSpec` is the only authoritative intent. Request bodies,
screenshot text, repository contents, and tool output are untrusted data. They
may inform the triage agent's proposed `TaskSpec`; they never enter the lane
automaton directly.

The JSON block below is the daemon-consumed rubric. `factory-core` parses this
exact block, validates it, and applies it without model confidence or request
text. Rules may remove lane-A authority; no rule can add it.

<!-- FACTORY_RUBRIC_JSON_BEGIN -->
{
  "version": "2026-07-23.1",
  "task_spec_schema_version": 1,
  "lane_a": {
    "max_files": 2,
    "max_changed_lines": 50,
    "allowed_path_prefixes": ["mfieldbook/"],
    "require_exact_paths": true,
    "require_named_targets": true,
    "require_deterministic_acceptance": true,
    "supported_skills": ["ui.sort-dropdown"]
  },
  "intent_routes": [
    {"intent": "internal_display", "lane": "A"},
    {"intent": "internal_report", "lane": "A"},
    {"intent": "internal_wording", "lane": "A"},
    {"intent": "internal_ordering", "lane": "A"},
    {"intent": "internal_validation", "lane": "A"},
    {"intent": "feature", "lane": "B"},
    {"intent": "schema_or_data_model", "lane": "B"},
    {"intent": "auth_permissions_or_secrets", "lane": "B"},
    {"intent": "payments_pricing_or_accounting", "lane": "B"},
    {"intent": "outbound_or_scheduled_automation", "lane": "B"},
    {"intent": "customer_facing", "lane": "B"},
    {"intent": "data_correction", "lane": "C"},
    {"intent": "operations", "lane": "C"},
    {"intent": "unclear", "lane": "D"}
  ],
  "deny_paths": [
    {"match": "prefix", "value": "mysql_files/", "lane": "B", "reason": "deny.schema"},
    {"match": "prefix", "value": "customerweb/", "lane": "B", "reason": "deny.customer_facing"},
    {"match": "prefix", "value": "guides/", "lane": "B", "reason": "deny.customer_facing"},
    {"match": "prefix", "value": ".github/workflows/", "lane": "B", "reason": "deny.ci"},
    {"match": "file_name", "value": "composer.json", "lane": "B", "reason": "deny.dependencies"},
    {"match": "file_name", "value": "composer.lock", "lane": "B", "reason": "deny.dependencies"},
    {"match": "file_name", "value": "package.json", "lane": "B", "reason": "deny.dependencies"},
    {"match": "file_name", "value": "package-lock.json", "lane": "B", "reason": "deny.dependencies"},
    {"match": "file_name", "value": "pnpm-lock.yaml", "lane": "B", "reason": "deny.dependencies"},
    {"match": "suffix", "value": ".lock", "lane": "B", "reason": "deny.dependencies"},
    {"match": "file_name", "value": "Cargo.toml", "lane": "B", "reason": "deny.dependencies"},
    {"match": "file_name", "value": "deploy-fieldbook.sh", "lane": "B", "reason": "deny.deploy"}
  ]
}
<!-- FACTORY_RUBRIC_JSON_END -->

## Lane actions

| Lane | Meaning | Deterministic route |
| --- | --- | --- |
| A | Named-skill internal display/report/wording/ordering/validation fix with exact evidenced targets, deterministic acceptance, and lane-A budget | Implement |
| B | Feature, deny-rule hit, unsupported skill, dependency/CI change, glob-scoped effect, or over-cap work | Plan bin for a one-page spec and estimate |
| C | Data correction or operations work | Plan bin for the matching human-run runbook |
| D | Intent or exact target is not identifiable | Plan bin for one scoped question with the two likeliest readings |

Lane A additionally requires a `lane_a_policy` budget, a matching
`skill_playbook` Guide, exact allowed paths (no effect globs), an exact target
record for every allowed path, and at least one typed deterministic acceptance
test. Dependency and CI flags demote to B. A test-change flag does not itself
demote, but remains authoritative downstream and forces test-diff review.

## Plan-bin transitions

- Approved B: replace the triage estimate with a schema-valid TaskSpec whose
  Guide is `approved_plan` and whose budget authority is `human_approved`, then
  re-enter at implement.
- Answered D: label the answer as untrusted request data and re-triage. The
  answer cannot itself authorize an effect.
- Executed C: close with outcome `executed-not-code` and the runbook reference.
- Rejected B/C/D: close with outcome `rejected-at-plan` and the human's reason.
