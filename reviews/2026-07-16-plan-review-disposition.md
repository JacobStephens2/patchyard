# Disposition: adversarial review of PLAN.md

*2026-07-16. Review: `2026-07-16-plan-adversarial-review.md` (GPT
5.6-Sol xhigh, via codex). Disposition author: the orchestration agent.
Applied in PLAN.md v2 (same day). Summary: **all findings conceded** -
five blocking sequencing errors, the weak-exit table, the overrun
analysis, all twelve unowned SPEC requirements, and the unit-name
ambiguity. Nothing rejected. Where the review offered alternative
remedies, the choice made is recorded below.*

## Blocking findings

| # | Finding | Disposition | Where applied |
| :-- | :-- | :-- | :-- |
| 1 | Verification depends on a preview mechanism built in session 9 | **Conceded.** Remedy chosen: land a minimal preview slice early (the review's re-plan point 4), not a temporary path the evidence session would replace | Session 7 owns the preview lease/SHA/baseline-DOM slice; session 6 tests postconditions against canned DOM only and says so; nothing claims end-to-end before session 15 |
| 2 | Session 8 claimed full-run dashboard acceptance before the run can finish | **Conceded** | Session 11 exits on a seeded-state route-by-role matrix; the full-run stage-transition display is explicitly deferred to session 15 |
| 3 | Final acceptance preceded material cutover | **Conceded.** Remedy chosen: cutover before the matrix (the review's first option), so the accepted artifact is the installed topology | Session 14 = cutover, session 15 = acceptance against it |
| 4 | Service identities used before any task creates them | **Conceded** | Session 1 provisions `factory-worker`, `factory-web`, the `factory` group, and the `/var/lib/patchyard/` skeleton with ownership assertions as tests |
| 5 | GitHub App surfaced early, activated late; PAT fallback under-specified | **Conceded** | App dependency opens at session 1 with a token-mint smoke test; fallback named as a dedicated machine-user fine-grained PAT (A45), never the human PAT; "PR author is the machine identity" is part of session 10's exit |

## Weak exit criteria (table, sessions 2-11)

**Conceded in full.** The "objective evidence needed" column was folded
into the corresponding session exits: named crash boundaries +
`integrity_check` + idempotent retry (session 2); predeclared probe
manifest with must-pass criteria (3); enumerated hostile-test manifest
(5); two-build reproducibility + exercised install/rollback (6); lease
cleanup on both paths + PHPUnit-as-`factory-worker` (7); replay manifest
with expected lanes + every plan-bin transition (8); ordering/provenance
/repair-exhaustion assertions (9); per-transition and per-crash-point
publisher tests (10); route-by-role matrix with exact status codes (11);
named upload fixtures + declared fuzz budget (12); failure-path states
(13); migration counts/hashes + rollback drill (14); frozen versioned
manifest with per-case expected state (15).

## Overrun analysis

**Conceded.** v1's ~10+1 was optimistic by roughly half: isolation was
allocated 2 sessions against a 2-2.5 component estimate *including*
adversarial qualification; the dashboard got 1 against 1.5-2; acceptance
got 1 for dozens of k=3 executions plus fuzzing. v2 re-baselines to ~15
sessions (splits: worker build-out vs adversarial qualification; skill
triage vs orchestration; dashboard routes/auth vs upload hardening;
cutover vs acceptance) and removes the fictional buffer - an overrun now
surfaces in its build PR instead of compressing security testing.
SPEC's component-estimate section gains a re-baseline note; the
component estimates themselves were right, the session cutting wasn't.

## Unowned SPEC requirements

All twelve **conceded** and assigned owners: clean verifier runtime +
ordering (session 7); targeted PHPUnit as `factory-worker` (7); plan-bin
return paths (8); full worktree lifecycle (10); deployed-SHA
reconciliation (10); provenance population (9) and completeness
validation in `ledger-append` (6, schema in 2); ruling/request namespace
separation with old-path rejection tests (14); storage trait boundary
(2); dashboard-triggered reconcile (11); admin-bypassed-merge outcome
recording (10, acceptance case in 15); deterministic supervisor boundary
test (9); dashboard scribe-only constructor + rejection tests (11).

Manifest ambiguity resolved: the systemd **unit** is
`factory-dashboard.service` (SPEC's name); **`factory-web`** is the user
it runs as. PLAN v2 states both explicitly.
