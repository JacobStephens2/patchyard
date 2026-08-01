# A77 adjudication - quarantined-successor replacement plan

## Scope and verdict

The build seat adjudicated A78's review of exact plan-record commit
`9c40b086a3c59a5955ebd484f942319e02786c68`, binary plan
`62adfcaac371203a5c9127ed307f29fdbd1593e2f2a466ae22836551e9fd91c3`,
rendered plan
`b77a32f12f3480e08496d6b8ff83fb38dc6c2b300999649ff0b9ad94169cafae`,
and operational plan source
`d8b2955c4de050a67d932d763fd58f2509f34df5`.

A78 returned **PASS with no material findings** after closing its initially
permission-blocked test and wrapper-mutation scope. The build seat sustains the
PASS. No repair, plan regeneration, or apply follows this adjudication.

## Withdrawn A119 observation - refute with evidence

A78's initial branch-local inference was invalid and the reviewer withdrew it.
Jacob's pre-review coordination explicitly allocated A119 to PR #80 and said it
must not be minted or repurposed. A read-only GitHub query at
`2026-07-30T23:12:50Z` returned PR #80 titled
`Rule A119: reassign the A78 adversarial-reviewer seat to Opus 5 [max]`.
GitHub reported the PR `OPEN`, with null `mergedAt` and `mergeCommit`, rather
than corroborating the coordination note's word "merged." That state discrepancy
does not make A119 available: both the explicit coordination and the live PR's
title allocate the number. The reviewed phrase "A119 is already taken" is
therefore correct for this work, no new ruling is minted, and no edit follows.

## Observation 2 - concede with exact-plan clarification

The successor has no volume configured, and no volume resource or attachment
edge exists. A78 is also correct that the provider computes the after-side
`volume_ids` field, so the plan alone does not state a final empty list. The
saved plan and configuration still contain no mechanism that restores or
attaches quarantined-worker state. The observation is nonblocking; this
adjudication supplies the more exact wording without changing the reviewed
record or plan.

## Observation 3 - concede and bound to owner-only local custody

Two adjacent digest checks and apply are not an atomic open of one file. A
local actor with access to the plan directory could theoretically replace the
path after digest #2 and before OpenTofu reopens it. The artifact resides in a
mode-0700 owner-only directory as a mode-0600 file; the operator sequence
rechecks custody and modes, and the apply remains a single controlled process.
This is a defense-in-depth limit rather than a defect in the exact reviewed
bytes. No source weakening is authorized.

## Observation 4 - concede and preserve the operator preflight

Source inspection confirms the wrapper validates an absolute existing path and
digest but does not enforce owner/mode or outside-repository placement. The
proposed apply bracket explicitly requires both mode readbacks before wrapper
invocation. Since apply is not authorized, omission of that later readback
remains fail-closed: do not invoke the wrapper.

## Observation 5 - concede as an inherent evidence ordering

Plan source `d8b2955` cannot contain the later record of the plan generated from
it. A78 proved the plan's embedded configuration byte-identical to that source,
and the later plan-record commit changes no technical tree. Applying from the
generation source is therefore the stronger binding, not a stale-source gap.

## Observation 6 - concede the affirmative privacy property

The encrypted plan contains the names of the three ephemeral inputs but not
their values. This corroborates, rather than weakens, the no-credential record.
No action is needed.

## Observation 7 - concede the reviewer-process violation

A78's intermediate private tool output printed the management SSH public key
despite an explicit prompt prohibition. The value is a public key, not a bearer,
private key, provider credential, or Anthropic credential. It was not included
in the review record, repository, PR, or this adjudication and need not be
rotated. The disclosure is retained as a process observation; the build seat
does not repeat the value.

## Observation 8 - concede as a mutation-authoring hazard

`verify_worker_plan` is called in both the plan and apply branches. A text-only
mutation can target the wrong occurrence if it lacks surrounding context. A78
caught and discarded that miscalibration, then reran the intended apply-branch
case. The production source is unambiguous at runtime; this is not an apply
defect.

## Observation 9 - concede the invalid intermediate harness and accept only the corrected experiment

The first disposable mutation repos were dirty because their mutations were
not committed, so `require_clean_revision` stopped them before the intended
guard. A78 explicitly excluded that run, committed each mutation in fresh mock
repos, recalibrated the prefix and action-shape cases, and reported only the
corrected 31-case matrix. The final controls and plan-swap pair demonstrate the
corrected harness reached the intended boundaries. The invalid run contributes
no positive evidence and creates no source finding.

## Independent build-seat checks

Before A78, the build seat independently passed the exact seven replacement
tests, all 25 spend tests, the spend checker, codebase projection, and seven
plan-projection mutations. The complete application gate passed. The complete
infrastructure and Ansible gates stopped only at the already disclosed
requirement-1 mismatch, with Ansible 139 of 140. After A78, the build seat
re-read both artifact hashes and all three owner-only modes and found them
unchanged. The author worktree, detached review worktree, and shared master
checkout remained clean.

## Final disposition

A78 PASS is sustained. The exact saved plan is fit only for a separately
authorized worker-only apply using the recorded preconditions. Current worker
`588826948` remains operationally quarantined and ineligible for repair or
reuse until that replacement occurs. No provider action, Console action,
requirement-1 refresh, behavioral acceptance, requirement-3 work, or
qualification-flag change occurred.
