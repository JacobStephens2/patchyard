# A77 adjudication - A115 M1/M2 clean-worker replacement plan

## Scope and verdict

The build seat adjudicated A78's review of exact binary plan
`a87568c6707f7d1e5bf581072d70584be117d01e785d1e12ff64ee3665415a59`,
rendered-plan digest
`d5c222e7b353e67eead2ff391fad1800e2537fe2e8bfedadd471cf3202649891`,
operational source `bc496e47bfeb703876495e80b011d88e10c7c232`, and
plan-record commit `5a5ba96f7030214e0fe022369a3361e496b3b738`.

A78 returned **PASS with no material findings**. The build seat sustains that
verdict. The plan remains unapplied and no live action followed review.

## N1 - concede and bound to the exact bytes

The action-shape gate does not inspect `.change.before.id`, every desired
attribute, or `output_changes`. The authored happy-path mock contains no
`before` object at all and still reaches mocked apply; the seven-test focused
suite passed, independently confirming that the target is not a durable gate
field. A78's target, attribute, and output mutations reproduce the same limit.

This is nonblocking only for the saved binary A78 decoded in full: its digest
is required twice, and a changed encrypted artifact either differs in SHA-256
or fails authenticated decode. A re-plan is a different artifact and receives
no authority from this PASS.

## N2 - concede the possible reading; clarify the claim

The recorded sentence says an **independent source projection** rejected a
different target. It is factually true and does not name the wrapper gate, but
could be read as claiming a persistent semantic guard. This adjudication makes
the boundary explicit: the old ID was checked during build-seat and A78 review;
the durable apply binding is the exact plan digest, not a target-ID predicate
inside `verify_worker_plan`.

## N3 - concede and reproduce

The build seat independently ran `converge.sh --check-inputs` with dummy valid
inputs. A mode-0644 GitHub App key plus a mode-0600 account roster returned
`converge_inputs_valid`; changing the roster itself to 0644 returned nonzero
with the expected group/world-access diagnostic. The asymmetry is real.

It does not admit this apply under the current authorization. Both real inputs
are absent, and the plan expressly requires a later authorized operator to
materialize both as mode 0600 inside a mode-0700 directory before invoking the
wrapper. A future general operator hardening can enforce the key mode in
source; it is not a repair prerequisite for review of these plan bytes.

## N4 - concede and preserve as a pre-apply readback

Source inspection finds the tag-firewall guard only in the plan arm. The
focused happy-path apply test reaches mocked apply in a fixture that does not
even provide `check-do-tag-firewalls.sh`, independently proving the apply arm
does not call it. A new tag-targeted firewall after generation is therefore a
real time-of-check risk.

The proposed apply sequence requires the production-tag guard to be rerun
inside the later authorization bracket before invoking the wrapper. Because no
apply is presently authorized, this manual prerequisite remains fail-closed:
its absence means do not invoke apply.

## N5 - concede and verify

The build seat independently projected the plan's `resource_drift`. It contains
exactly one entry for `digitalocean_firewall.worker`, moving from `waiting` with
two pending changes to `succeeded` with zero. This is benign settled-state
refresh, not an additional planned action, and it corroborates the subsequent
read-only firewall observation. Recording it here closes the disclosure gap.

## Numbering clarification

A78 correctly observed that this detached review checkout's decision log ends
at A118. Fleet coordination separately establishes that A119 is already taken
by the merged reviewer-seat reassignment. The plan record's phrase "A119
remains reserved" means unavailable for this operational grant, not unissued.
No decision-log ruling was added or renumbered.

## Final disposition

A78 PASS is sustained. No repair, plan regeneration, or second review follows.
The exact plan is fit only for a separately authorized apply using the recorded
preconditions. Worker `588778422` remains boundary-tainted and ineligible. No
credential, provider request, cap action, behavioral acceptance, requirement-3
work, or qualification-flag change occurred.
