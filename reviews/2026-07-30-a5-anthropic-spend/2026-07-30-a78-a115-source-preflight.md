# A78 adversarial review - A115 Anthropic spend successor source preflight

Candidate: `c04e6c602136c4dc2718dabba0e19aefcce951a3` on
`a5-anthropic-spend-a115-successor`  
Base: `e31ea705ab9c3418c6b49c77a23f015c5045ce52`  
Diff: 13 files, +1434 / -956

Reviewer: Claude Code 2.1.220, `claude-opus-5`, effort xhigh,
plan/read-only permission mode. Session
`2926ad3a-a694-4a00-a4bb-bd2a75a14867` completed in 1,127,125 API ms with no
permission denials, repository edits, provider requests, infrastructure
mutations, worker changes, pushes, or web searches. Experiments used throwaway
copies under `/tmp`.

## Verdict

Findings, not PASS: two high, three medium, and six low. No surface falsely
claims requirement 2 is qualified. The A115 three-phase causal contract is
substantially implemented, but the reviewed source is not yet eligible for a
worker converge or provider request.

## Checks run

| Check | Result |
| :-- | :-- |
| Anthropic spend checker | Pass - A115 preflight with historical failures retained |
| Anthropic issuance checker | Four expected stale-live-evidence errors: shape/phase, image recipe, and host contract |
| Ansible unit discovery | 115 tests; two expected stale issuance digest failures |
| Worker runtime checker | **Fail** - desired image-recipe pin stale |
| Worker qualification, independence, stack, preview, bench, and seats checkers | Pass |
| ShellCheck on gated runner | Pass |
| Synthetic finalized A115 result | Pass beside both historical failure records |
| 12 synthetic-result mutations | All rejected |
| Six spend-source mutations | Five rejected; URL hoist plus second sequential curl passed |
| Four record/flag mutations | All rejected |
| Five child-launcher mutations | Three rejected; removing chown or file-chmod teardown guards passed |
| Credential and scope scans | Clean; 13 flags false, no requirement 3, no bare key |

The disclosed requirement-1 staleness was confirmed exactly. The old evidence
lacks only `qualification_phase`, and its image-recipe and host-contract hashes
differ from the reviewed source. A78 did not recommend weakening those gates.

## Findings

### A115-1 - Stale desired-state image pin

Severity: High. `infra/ansible/group_vars/all.yml` retained the prior
`worker_image_recipe_sha256` while the changed guest recomputed differently.
`tools/check-worker-runtime.py` passed at the base and failed at the candidate.
A fresh worker would refuse to build the reviewed image.

Criterion: update the pin to the final source hash and make the worker-runtime
gate pass before applying a replacement.

### A115-2 - Month-scoped eligibility was undocumented

Severity: High. Cost and the workspace cap reset monthly. After the August 1
rollover, the fixed one-token request cannot create a baseline above $1.00
without an unauthorized ramp. A sequence that straddles the boundary also
causes month-to-date spend to move backward.

Criterion: make one-billing-month execution and an already-settled $1-$50
baseline explicit; missing the window must escalate to Jacob, not trigger
engineered spend.

### A115-3 - One request per phase was defeatable

Severity: Medium. The checker counted endpoint literals. Hoisting the URL and
adding a second sequential curl retained one literal and passed. The
`request_attempts: 1` evidence field was a guest-authored constant.

Criterion: bind the exact invocation rather than its URL literal, reject any
provider-capable invocation outside that block, and do not rely on the constant
alone. A78 suggested Usage Report corroboration where the API can supply it.

### A115-4 - A114 tests did not bind every teardown guard

Severity: Medium. Removing `|| mark_teardown_failed` from chown or file chmod
left the child-launcher tests green, although the implementation itself was
correct. Ordering, unlock-before-terminal, and terminal-write guards were
already bound.

Criterion: assert the guarded source form for every fallible post-child
operation.

### A115-5 - Rejected response shapes remained undiagnosed

Severity: Medium. Compatible envelopes exported a safe shape, but an envelope
rejected by the predicate left only its HTTP status before credential cleanup
destroyed the body. No test executed the guest predicate.

Criterion: publish a bounded credential-free rejection class in the failure
status and execute exact-predicate synthetic cases for compatible extras,
oversize, malformed request ID, and rate-limit exclusion.

### A115-6 - Organization cap was not pinned to $500

Severity: Low. Both tools required only an unchanged value above $50, while the
reviewed live value and attended procedure say $500.

Criterion: bind 50,000 cents in policy and both evidence tools.

### A115-7 - Repair record omitted the quarantined worker ID

Severity: Low. The repair marker did not say that worker `588590370` is the
quarantined replacement target.

Criterion: name that worker and bind its pending-reviewed-replacement state.

### A115-8 - Missing provider Date silently used guest time

Severity: Low. GNU `date -d ""` succeeds as now, allowing absent provider Date
to masquerade as a provider observation.

Criterion: require a nonempty parseable Date and use distinct failure classes.

### A115-9 - Incremental spend could include late phase-1 cost

Severity: Low. The pre-activation snapshot merely had to contain some settled
spend. Late positive-control cost could land in the after snapshot, making the
difference a conservative upper bound.

Criterion: add a full pre-activation settlement window or explicitly label the
figure as an upper bound.

### A115-10 - The $50 condition needed a no-ceiling explanation

Severity: Low. Rejecting total settled spend at or above $50 protects the
positive-control interpretation, but could be mistaken for A113's forbidden
overshoot ceiling.

Criterion: explain that pre-activation eligibility is not a relabelling or
ceiling on the recorded incremental figure.

### A115-11 - Distinct WIF exchanges were not bound

Severity: Low. Each phase validated one five-minute issuance but the finalizer
did not require distinct exchange IDs or non-overlapping bearer lifetimes.

Criterion: require three distinct exchange request IDs and disjoint windows in
the finalizer and checker.

## Prior A78 findings

| Finding | Source-preflight disposition |
| :-- | :-- |
| A78-1, A78-2, A78-3, A78-5, A78-6, A78-7 | Repaired |
| A78-4 | Partially repaired - required-key containment works; A115-5 remains |
| A78-8 | A77 refutation stands; A115 now admits success beside retained history |
| A78-9 | Partially repaired - loops/retries and teardown ordering caught; A115-3 remains |
| A78-10 | Implementation repaired; A115-4 test gap remains |
| A78-11 | A77 refutation stands; not reopened |

A78 additionally verified same principal/model/endpoint, byte-identical request
hashes, ordered five-minute cap readbacks, 429/rate-limit/overload exclusion,
the 10,260-second post-refusal settlement floor, separated cost figures with no
overshoot ceiling, credential-free bounded shapes, credential deletion before
every result, retained historical failures, and unchanged scope.

## Authorization

Clean-worker replacement planning may proceed to separate review, but the plan
must not be applied at this candidate because A115-1 prevents a correct
converge. No provider request is authorized by this review.
