# A78 adversarial re-review - A115 Anthropic spend source preflight

Candidate: `88f8441f2a23b86db36881e22e35e9719b80eb4b` on
`a5-anthropic-spend-a115-successor`.

Previously reviewed: `c04e6c602136c4dc2718dabba0e19aefcce951a3`.

Base: `e31ea705ab9c3418c6b49c77a23f015c5045ce52`

Reviewer: Claude Code 2.1.220, `claude-opus-5`, effort xhigh,
plan/read-only permission mode. Session
`dbd28024-c04e-4fda-89a6-db4c5e6875dd` completed in 772,252 API ms with no
permission denials, repository edits, provider requests, infrastructure
mutations, worker changes, pushes, or web searches. Experiments used throwaway
copies under `/tmp`. The executed host had jq 1.6, ShellCheck 0.11.0, and Python
3.9.25; jq 1.6 matches the el9 package installed by the worker image recipe.

## Verdict

Findings, not PASS: one high and one medium. Nine of the eleven first-review
findings are repaired and held under mutation. A115-3 and A115-5 are only
partially repaired. No worker replacement or provider request is authorized by
this review.

## Checks run

| Check | Result |
| :-- | :-- |
| Anthropic spend checker | Pass - A115 preflight with historical failures retained |
| Worker runtime checker | Pass - recipe `efd0dbd97d2e16b67572c5630fd9227dbaab8252a19983ba2d4e69fff2e10225` |
| Anthropic issuance checker | Four expected stale-live-evidence errors: shape/phase, image recipe, and host contract |
| Ansible unit discovery | 123 tests; two expected stale issuance digest failures |
| Worker qualification, independence, stack, preview, seats, and constitution checkers | Pass |
| ShellCheck on gated runner | Pass |
| Synthetic finalized A115 result | Pass beside both historical failure records |
| 16 synthetic-result mutations | All rejected |
| Post-refusal `$55.00` positive control | Accepted - no overshoot ceiling |
| 12 source mutations | Ten rejected; two defects reproduced |
| Five A114 teardown-guard removals | All rejected |
| Six finalizer and guest-predicate mutations | All rejected |
| Credential and scope scans | Clean; 13 flags false, no requirement 3, no bare key |

`check-codebase.sh` could not run because `tokei` is absent on this host. No
other gate was red beyond the disclosed requirement-1 live-evidence staleness.

## A115-3R - one request per phase remains defeatable by name indirection

Severity: High.

The checker applies its provider-capable-command exclusion only to the literal
spend-branch text. A provider-call helper defined elsewhere in the guest is
therefore invisible when the spend branch invokes it by name.

A78 reproduced the defect by defining an `extra_provider_attempt` helper before
`finish()`, outside the spend branch, with a second authenticated curl to
`https://api.anthropic.com/v1/messages`. It then invoked only the helper name
after `# A115_PROVIDER_REQUEST_END` and updated the image-recipe pin. The spend
checker passed, the worker-runtime checker passed, all 123 tests retained only
the two disclosed stale-evidence failures, and ShellCheck was clean. The mutated
guest would make two provider requests in each phase.

The Usage Report prescription remains refuted: the committed report schema
aggregates tokens, does not count requests, and cannot distinguish one refused
request from two. The source gate is consequently the applicable request-count
proof and must cover guest-wide provider-call literals or the reachable call
graph. A naive guest-wide count of the messages URL is not sufficient because
the mutually exclusive requirement-1 branch legitimately contains its own
`/v1/models?limit=1` provider call.

## A115-5R - jq 1.6 accepts an empty response document

Severity: Medium. The implementation fails closed, but loses the bounded
diagnostic that A115-5 was chartered to preserve.

A78 verified that jq 1.6 exits zero and emits no value when an expression is
run over an empty file. Both the success and error-envelope predicates therefore
return success for an empty provider body, and the classifier labels an empty
body `compatible-error-envelope`.

An executed end-to-end trace of the refusal branch with HTTP 400 and an empty
body passed the compatibility predicate, skipped the empty request-ID check,
and classified the message as `spend_attributable`. A later `jq -nc --argjson`
failed, so the guest exited with only the generic
`anthropic-spend-provider-response-rejected` status. An empty HTTP 200 follows
the same pattern. Qualification does not occur, but an authorized attempt could
end with the same uninterpretable status as the July 29-30 failure.

The exact predicates and classifier need explicit nonempty, single-object JSON
preconditions and executed empty and whitespace-only cases. The current tests
cover extra fields, oversize content, malformed request IDs, and missing fields,
but not these inputs.

## Prior-finding disposition

| Finding | Re-review disposition |
| :-- | :-- |
| A115-1 stale desired-state image pin | Repaired; runtime checker passes |
| A115-2 month-scoped eligibility | Repaired; boundary and settlement mutations fail |
| A115-3 one request per phase | Partially repaired; direct in-branch mutations fail, helper indirection passes |
| A115-4 A114 teardown tests | Repaired; all five guard removals fail |
| A115-5 rejected-shape diagnosis | Partially repaired; ordinary malformed cases hold, empty document passes |
| A115-6 exact $500 organization cap | Repaired; altered-cap mutations fail |
| A115-7 quarantined worker identity | Repaired; identity and disposition mutations fail |
| A115-8 provider Date | Repaired; missing and invalid values are distinct failures |
| A115-9 late phase-1 settlement | Repaired; pre-activation settlement floor is bound |
| A115-10 no overshoot ceiling | Repaired; `$55.00` post-refusal evidence is admitted |
| A115-11 distinct WIF exchanges | Repaired; duplicate and overlap mutations fail |

## Repair-budget divergence

The committed A77 adjudication calls `c04e6c6..88f8441` the single A9 repair
loop authorized by A115. Read literally, the repair budget is exhausted. A78
also observed that A115 can be read as placing the A9 loop beside the live
qualification attempt while requiring all source defects to be repaired before
that attempt. A78 did not choose between those readings and referred the
conflict to Jacob.

Clean-worker planning is mechanically possible, but applying it before any
authorized source repair would immediately stale the replacement image because
either repair changes the guest recipe digest. Requirement 2 remains
unqualified; no provider request or worker action occurred.
