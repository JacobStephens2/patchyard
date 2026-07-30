# A77 adjudication and A9 escalation - A116 source re-review

Candidate reviewed by A78:
`f182df72a84b140223e84fad8a2e01a95d09c7b2`.

A116 authorized one additional consolidated pre-attempt source repair limited
to A115-3R and A115-5R. Commit `f182df7` is that repair. A78 returned six
findings after executed mutations. The build seat independently replayed the
decisive experiments before adjudication. No implementation repair, worker
action, cap change, or provider request follows this record.

## A116-1 - Concede

The build seat independently reran M1 and M2. Both mutated copies pass
`tools/check-anthropic-spend.py`, `tools/check-worker-runtime.py`, and all 21
focused tests. Their counting harnesses each report
`PROVIDER_STATUS=200 requests=2`.

This settles the core claim. The new whole-guest literal scan closes the prior
helper reproduction but does not bind invocation count. A function containing
the one byte-exact block can be called twice, and the block's `runuser`
executor can be shadowed to invoke twice. The authored
`request_attempts: 1` output is consequently not truthful proof.

## A116-2 - Concede

The build seat independently replayed A78's branch harness. HTTP 403 with an
HTML body, HTTP 400 with an empty body, and HTTP 200 with a valid message all
exit as `anthropic-spend-provider-call-not-completed` when the response omits a
request-ID header. The calls completed, but status and shape are lost before
the response-stage failure is set. This is a bounded-diagnostic defect and a
record-truth defect under A114.

## A116-3 - Concede

The build seat independently ran the C1 copy after replacing the checker's
compiled command regex with a never-matching expression. The spend checker and
all 21 focused tests pass. The finding's core is therefore correct: the test
duplicates the regex rather than behaviorally binding the checker CI executes.

The individually removable required-source strings are not each independent
safety defects because executed guest tests cover their behavior. They do not
change the conceded disposition: the material C1 mutation is sufficient.

## A116-4 - Concede

The exact loopback command text is mechanically required in both checker and
test. This is not a false qualification path, but it is an unnecessary coupling
that causes an Anthropic spend gate to reject ordinary reviewed local-probe
changes. The checkable claim is correct.

## A116-5 - Concede

The documentation's absolute statement is false under the reproduced M1, M2,
M4, and M5b constructions. It also omits the two loopback block exemptions.

## A116-6 - Refute with evidence

The review environment did not expose `tokei`, but the build environment does:

```text
tokei 14.0.0 compiled with serialization support: json
codebase metrics projection: pass
```

The build seat ran `tools/check-codebase.sh --write`, then reran the byte-exact
check successfully. The application gate independently reached the same
projection after formatting, clippy, workspace tests, reproducible-release,
audit, deny, vet, machete, and model checks passed. Accumulating the branch's
prior changes is the projection's intended A106 behavior, not an A116 scope
defect. No corrective action is required for this finding.

## Gate and mutation record

- A116 focused suite: 21 passed.
- Full Ansible discovery: 125 tests with only the two disclosed stale
  requirement-1 digest failures.
- Infrastructure validation passed through stack, independence, worker
  runtime, and worker qualification, then stopped on exactly the four disclosed
  stale issuance-evidence errors.
- Ansible lint and all four playbook syntax checks passed.
- Application checks passed through the complete Rust, release, dependency,
  model, and final regenerated codebase-projection checks. State integration
  was not enabled in this source-only host run.
- Preview, seats, and constitution checks passed; seats retained ten
  pre-existing warnings.
- ShellCheck and Python/Bash syntax checks passed.
- Author mutations: reverting the checker to branch-only scope failed the
  suite; replacing the single-object predicate with jq's empty-input behavior
  failed two executed cases.
- A78 mutations: M1 and M2 were independently confirmed as two-call green-gate
  bypasses; C1 independently confirmed that the checker's regex can be neutered
  while its tests pass.
- All 13 `credential_qualified` flags remain false. No bare credential,
  requirement 3 work, or behavioral acceptance case was introduced.

## A9 disposition - Escalate

A116's authorization is explicit: one additional consolidated pre-attempt
source repair. Commit `f182df7` consumed it and did not satisfy A115-3R. A9
therefore forbids another unruled repair loop. The build seat stops before a
second A116 patch, clean-worker replacement, or provider request.

Jacob must decide whether to authorize another bounded source redesign or leave
Anthropic requirement 2 unqualified. Any further authorization should address
the structural result rather than add command names to the denylist: request
count needs a one-shot construction and independent readback across the whole
installed image, and the missing-request-ID path needs a truthful bounded
response-stage record. A new authorization would still require A78 source
review and a separately reviewed clean-worker replacement before a live A115
attempt.

## Scope at escalation

- Requirement 2 remains unqualified.
- Worker `588590370` remains quarantined; no replacement was applied.
- No Anthropic request was sent and no cap was changed.
- The organization limit remains outside the mutation scope.
- Requirement 3 and behavioral acceptance remain unopened.
- All 13 qualification flags remain false.
- No bare `ANTHROPIC_API_KEY` was introduced.
