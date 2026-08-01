# A78 adversarial review - A116 consolidated source repair

Candidate: `f182df72a84b140223e84fad8a2e01a95d09c7b2` on the detached
A78 worktree.

Previous candidate: `d41504d`.

A115 series base: `e31ea705ab9c3418c6b49c77a23f015c5045ce52`.

Reviewer: Claude Code 2.1.220, `claude-opus-5`, effort xhigh. Session
`d8a9e3de-cb9e-4ba2-9f4b-cc6291b89dd3` ran first in plan/read-only mode,
then with only Bash, Read, Glob, and Grep available for approved throwaway
experiments under `/tmp/a78`. Edit, Write, and web tools remained disabled.
The session used no provider credential and made no provider request, web
request, repository edit, commit, push, infrastructure mutation, or worker
change. Four Bash probes were denied during an intermediate `dontAsk` attempt;
the experiment phase then completed without permission denials. The detached
worktree was clean at the reviewed SHA after every experiment.

## Verdict

**FINDINGS, not PASS:** one high, one medium, three low, and one
informational. A115-5R is repaired for jq's empty-document defect. A115-3R is
only narrowed: five new source constructions still make two Anthropic requests
per A115 phase while every applicable gate retains its baseline result.

No clean-worker replacement application and no provider request is authorized
by this review.

## Checks run

| Check | Result |
| :-- | :-- |
| Anthropic spend checker | Pass - A115 successor preflight; historical failures retained |
| Worker runtime checker and independent recipe computation | Pass - `4561735af68d44a88949bb3dd9dfd790180d9db458e105673f3abd181ab6003b` |
| Anthropic issuance checker | Four expected stale-live-evidence errors: shape/phase, image recipe, and host contract |
| Ansible unit discovery | 125 tests; exactly two expected stale issuance-digest failures |
| Worker qualification, stack, independence, and preview-runtime checkers | Pass |
| Seats, bench, and constitution checks | Pass; seats retained ten pre-existing warnings |
| ShellCheck on guest and issuance runner | Pass |
| Guest predicate matrix | 18 raw bodies executed; all non-single-object bodies rejected with a bounded class |
| Spend-branch trace | 18 HTTP paths executed; 15 bounded and three unbounded |
| Provider-request constructions | One rejected; five passed all applicable gates |
| Source/evidence mutations | Nine caught; six accepted, including one material checker weakening |
| Credential, history, scope, and flag scans | Clean; 13 flags false and historical records unchanged |

The review host did not expose `tokei` on its PATH, so A78 recorded the
codebase projection check as environmental rather than a pass. The build-seat
adjudication resolves that check independently.

The known requirement-1 red remained exact and is not recommended for
weakening:

```text
Anthropic issuance check: failed
  live result has an unexpected top-level evidence shape
  live result is stale for the current worker image recipe; rerun the Anthropic issuance fixture
  live result is stale for the current Anthropic host contract; rerun the Anthropic issuance fixture
  live issuance result has an unexpected qualification phase
```

## A116-1 - More than one Anthropic request still passes every gate

Severity: High. A115-3R is not repaired.

The A116 checker rejects the exact A115-3R reproduction: a helper outside the
spend branch containing a literal curl. It does not bind how often the one
exact block executes, shadowed executors, provider destinations added to curl's
configuration, or provider calls placed in another image file or made through
a non-denylisted executable.

A78 built six source-only constructions. The original helper reproduction was
rejected. These five retained a passing spend checker, runtime checker,
ShellCheck, and focused unit suite, with only the disclosed issuance baseline
red:

| Mutation | Construction | Result |
| :-- | :-- | :-- |
| M1 | Put the byte-exact request block in a function inside the branch and invoke the function twice | Two requests; all applicable gates pass |
| M2 | Shadow `runuser` with a wrapper that invokes the real executor twice | Two requests; all applicable gates pass |
| M3 | Add a second Messages URL to the curl authorization config | One curl invocation performs two transfers; gates pass |
| M4 | Install a sibling provider-call program from `worker/image` and invoke it by path | Two requests; gates pass |
| M5b | Make a second request through the installed PHP interpreter | Denylist does not match; gates pass |

M1 and M2 were executed with counting stubs and each returned
`PROVIDER_STATUS=200 requests=2`. M3's two-transfer behavior was separately
executed against two local `file://` URLs: curl emitted one result for each
configured URL. M1, M2, and M4 do not depend on PHP transport availability.

The current gate scans command-name literals in one file. It does not bind the
reachable call graph or invocation count. The whole-image recipe digest is a
consistency binding that moves with these mutations, not an independent request
counter. The Usage Report refutation remains correct, so no independent
provider request counter repairs that gap. Nevertheless the guest still emits
the authored constant `request_attempts: 1` after two calls.

Criterion: prove one execution by construction and independent readback rather
than a finite command-name scan. Bind the whole installed image's provider
surface, exact authorization-config bytes, the executor, and a one-shot call
state. A denylist of four command names is not sufficient.

## A116-2 - Missing request ID loses the bounded response diagnostic

Severity: Medium. The response fails closed, but the failure record is false
and undiagnostic.

The guest validates `PROVIDER_REQUEST_ID` with a bare `[[ =~ ]]` under
`set -e` while `FAILURE` still says
`anthropic-spend-provider-call-not-completed`. A78 executed the exact branch
with only its provider block stubbed:

```text
403 html edge page, no request-id  -> anthropic-spend-provider-call-not-completed
400 empty body, no request-id      -> anthropic-spend-provider-call-not-completed
200 valid message, no request-id   -> anthropic-spend-provider-call-not-completed
```

The call did complete in every case, but the record contains neither status nor
shape. The other 15 executed paths, including empty/whitespace/malformed bodies,
produce bounded response-stage diagnostics.

Criterion: set the sanitized response-stage failure before parsing headers,
give absent and malformed request IDs distinct bounded suffixes, and execute
200, 400, and 403 cases without the header.

## A116-3 - The checker's denylist is not behaviorally bound by tests

Severity: Low.

Replacing `PROVIDER_CAPABLE_COMMAND` with a never-matching regex leaves the
spend checker and all 21 focused tests green. The test asserts that the checker
contains the global-scan source strings but reimplements the regex instead of
executing the checker's compiled pattern. Removing individual
`required_sources` entries for the single-object helper and two suffix strings
also leaves the suite green, although the executed guest behavior remains
covered separately.

Criterion: expose or import the checker binding and exercise it against a fixed
positive/negative command corpus; bind the repair's required-source entries
without duplicating their enforcement logic.

## A116-4 - The spend gate byte-binds unrelated loopback probes

Severity: Low.

The checker exempts the guest's local web-health and parity curls only by their
complete byte-exact command text. An ordinary reviewed flag, line-break, or
second loopback-probe change therefore fails the Anthropic spend gate until two
files are updated, even though the destination remains loopback.

Criterion: recognize literal loopback destinations as local rather than binding
both unrelated fixture commands byte-for-byte. Retain exact blocks for the two
credentialed Anthropic calls.

## A116-5 - Documentation overstates the executable contract

Severity: Low.

The documentation says the checker removes two blocks, rejects any remaining
provider-capable command, and prevents a helper from hiding another request.
The checker removes four blocks, uses a four-command denylist, and M1, M2, M4,
and M5b demonstrate helpers or alternate executors that remain invisible.

Criterion: document the actual exemptions and finite scan, or earn the stronger
claim with an executable one-shot construction.

## A116-6 - Metrics projection not verified in the review environment

Severity: Informational.

The regenerated projection incorporates the accumulated branch changes rather
than A116 alone. A78 could not byte-verify it because `tokei` was absent from
its PATH and requested that it be checked on a suitably equipped host before
merge.

## Authorized-target disposition

| Target | Disposition |
| :-- | :-- |
| A115-3R - one request per phase | **Not repaired.** The prior literal-helper reproduction is closed, but five new two-request constructions pass. |
| A115-5R - empty/non-single-object response | **Repaired for its chartered jq defect.** Empty, whitespace, truncated, multi-document, arrays, scalars, trailing garbage, and NUL inputs are rejected. The adjacent missing-request-ID path remains undiagnostic. |

Both author-declared negative mutations hold: changing the checker back to
spend-branch scope fails the suite, and replacing the single-object predicate
with ordinary jq behavior fails the non-single-object test.

## Scope and authorization

All 13 qualification flags remain false. The historical July records are
unchanged. No live A115 result exists. Requirement 3 and behavioral acceptance
remain unopened. No cap, worker, or provider state changed.

Clean-worker replacement planning may continue only to its separate review;
application at this candidate is not authorized because any A116-1 repair would
change the image digest. The provider qualification attempt is not authorized.
