# A118 findings bounded source repair

## Authorization and scope

Jacob authorized one additional bounded source-only repair after the A118
adjudication. Under the subsequent governance-hygiene direction, this
operational authorization is recorded in the requirement-2 work record rather
than minted as another numbered policy ruling. It is limited to the conceded
A118-1 and A118-2 findings.

The authorization covers no clean-worker plan or mutation, provider request,
credential issuance, cap action, requirement 3 work, behavioral acceptance, or
qualification-flag change. It adds no live attempt or further repair loop.

## Complete transport-setup binding

The A118 digest covered only the namespace nftables lines between two markers.
The repair removes those nested markers. The checker now extracts one singular
transport-control section from the `setup_provider_transport` declaration
through the complete `assert_provider_transport_preflight` closing brace and
verifies one hard-coded SHA-256.

That section includes:

- namespace IPv6 writes before link creation;
- veth creation, addressing, link-up, and default route;
- host IP forwarding;
- the host forward and postrouting chains, exact provider destination and
  port, return path, terminal rejection, and masquerade;
- namespace tables, chains, drop policies, sets, and named counters;
- loopback and established-connection handling;
- exact namespace interface, source, destination, port, and new-state admit
  rule;
- used-source, later-new-connection, and terminal rejection; and
- the complete IPv6 preflight readback and failure path.

An added rule, an early preflight bypass, or a weakening anywhere in that
section changes the verified digest.

## Exact IPv6 preflight

The checker separately requires exactly one byte-identical comparison:

```bash
if [[ "$ipv6_all" != 1 || "$ipv6_default" != 1 || "$ipv6_eth0" != 1 ]]; then
```

This keeps the independently readable intent visible in addition to the
complete transport-control digest.

## Mutation set

The real spend checker now runs against fifteen disposable source weakenings.
The five additions for this repair are:

1. add the formerly green unqualified namespace rule immediately before the
   complete setup function's closing brace;
2. replace the host-forward provider destination with `0.0.0.0/0`;
3. change the host-forward terminal rejection to acceptance;
4. replace the exact IPv6 OR comparison with the ineffective AND comparison
   reproduced during A77 adjudication; and
5. return successfully before evaluating the exact comparison.

All five fail, as do the ten A118 mutations. The focused spend suite remains 24
tests because the mutations are subcases of its real-checker behavioral test.

## Boundary

No provider or external-network action occurred. No worker, credential, cap,
acceptance, requirement-3, or qualification-flag state changed. A78 review of
the exact repaired source SHA remains the next gate before any clean-worker
replacement plan.

## Post-repair review result

A78 reviewed exact commit `4a1fb52` with Opus 5 at effort `max`. The review
found four further material gaps in the source binding: executable replacement
definitions, a preflight call hidden in dead code, fabricated counter/set
readbacks, and a transport-changing command inserted at the call site. The
build seat independently reproduced and conceded all four under A77.

The authorized repair loop is exhausted. No further repair, clean-worker
replacement, provider action, or live attempt follows without a new bounded
authorization. Consistent with the governance-hygiene direction, any such
grant will be appended here with its authorizer, scope, reason, and loop count;
it will not create a new numbered decision-log ruling.

## Second post-A118 operational repair authorization

On 2026-07-30, after the post-repair A78 review and A77 adjudication, Jacob
authorized another bounded source repair. This is the second operational
post-A118 repair grant recorded in this work record:

1. A118 was the policy authorization for the bounded repair of the six A117
   findings.
2. The first post-A118 operational grant repaired conceded A118-1 and A118-2.
3. This second post-A118 operational grant covers only the four conceded
   findings in `2026-07-30-a78-post-a118-source-review.md`.

The reason for the grant is that the first post-A118 repair bound only the
first textual setup/preflight region. It did not bind the executed definition,
the direct preflight call, the readback helpers, or intervening commands at the
paid-transfer call site.

Consistent with the governance-hygiene direction, this authorization is not a
numbered decision-log ruling. It authorizes no worker plan or mutation,
provider request, credential issuance, cap action, behavioral acceptance,
requirement-3 work, or qualification-flag change.

## Complete launcher binding repair

The repair replaces the partial transport-region digest with one hard-coded
SHA-256 of the complete `patchyard-firecracker-run` source. The reviewed
source digest is
`c2b4275704ab0447a08e157be994a0bd18e505a843f1a017ce496220f3e83928`.
The complete-file boundary includes all equivalent function-definition forms,
both nftables readback helpers, teardown, and every command before and after
the paid transfer. The existing exact IPv6 comparison remains independently
readable. A new exact multiline binding requires setup, preflight, and the
one-shot transfer to be adjacent and singular.

The test independently recomputes the launcher SHA-256, requires the same
literal in the checker, pins the reviewed checker source itself, and runs the
real checker in a fresh disposable copy for every weakening. A mutation now
succeeds only when the checker emits its normal controlled failure header and
the exact diagnostic for the mutated source; a Python crash no longer satisfies
the test.

## Added post-review mutations

Five disposable mutations cover the four conceded findings, splitting the two
readback helpers so each is independently bound:

1. append later setup and preflight definitions, including the two-line brace
   spelling that evaded the old declaration count;
2. move the preflight call into `if false; then`;
3. make the counter helper return fabricated values before querying nftables;
4. make the set helper return fabricated values before querying nftables; and
5. insert an unqualified host forwarding accept rule between setup and
   preflight.

Together with the existing fifteen cases, the real-checker harness now carries
twenty source mutations. A78 review of the exact repair commit remains required
before any clean-worker replacement plan.

The build seat also mutation-checked the binding implementation itself in a
disposable repository copy. Changing the launcher comparison from
`if digest(...)` to `if False and digest(...)` changed the checker SHA-256 from
the pinned
`6b49386cd63cb73d4aca399ac7d3b4d4bdace93c6f66bddf7ec61190c1630048`
to
`3c7f374501448bb8df328b1822f51491fdc71de65dd113a5f44697a2e03b4879`.
The focused contract test failed on that exact mismatch. The mutation was not
retained.

## Complete-launcher A78 result and stop

A78 reviewed exact repair commit `36590dc` with Opus 5 at effort `max`. The
complete-launcher digest closed all four findings in scope, including novel
variants, and the controlled-diagnostic mutation behavior held. A78 found two
adjacent material gaps outside that file boundary:

1. the unbound issuance runner can skip its installed launcher and one-shot
   comparisons, and Ansible permits a later writer to the executed path; and
2. the spend guest's credential-absence and receipt assertions remain
   substring-bound and can be moved into dead code or short-circuited.

The build seat independently reproduced and conceded both under A77. This
second operational post-A118 repair grant is exhausted. No further repair,
clean-worker replacement, provider action, or live attempt follows without a
new bounded authorization recorded in this work record. No new numbered ruling
is to be created.

## Third post-A118 operational repair authorization

On 2026-07-30, after receiving the complete-launcher review and A77
adjudication, Jacob answered `Yes` to authorize another bounded source-only
repair. This is the third operational post-A118 repair grant. It is limited to
the two conceded findings in
`2026-07-30-a78-complete-launcher-binding-review.md`: the unbound runner and
non-singular installed-path writers, and the substring-bound spend-guest
assertions.

The reason for the grant is that the complete launcher binding does not itself
prove that the runner enforces the installed-source comparisons before bearer
issuance, that no later Ansible task overwrites either executed path, or that
the guest actually executes its credential-absence and receipt-cardinality
assertions.

Consistent with the governance-hygiene direction, this authorization is
recorded here and is not a numbered decision-log ruling. It authorizes no
worker plan or mutation, provider request, credential issuance, cap action,
behavioral acceptance, requirement-3 work, or qualification-flag change.

## Runner, installed-path, and guest binding repair

The checker now binds the complete issuance-runner source at SHA-256
`45ff683fdd9c9226e6fa07c5ea1de52bb7581f77eb231c42ea6c05c256feaa87`.
That boundary includes the runner's independently measured installed launcher
and one-shot hashes, their comparisons against checkout sources, and the order
of those checks before capability issuance. The tests independently recompute
the runner digest and require the same literal in the checker.

The complete worker install-task source is bound at SHA-256
`110cbffc6db188aafa1364e88901249290653134b7f0adc559152abf3f35df40`,
and it must contain exactly one writer for each executed path:
`/usr/local/sbin/patchyard-firecracker-run` and
`/usr/local/libexec/patchyard-anthropic-one-shot`. This rejects a later task,
including an alternate destination spelling inside the bound task source, that
overwrites a reviewed executable after its normal install task. The tests
independently recompute the task-source digest and require the same literal in
the checker.

The checker also binds the complete spend-guest source at SHA-256
`229346fb350297b298c1b752188c0f7762ef9d5de77572156843070fecfcc654`.
That boundary includes the credential-drive and provider-hosts absence checks
and the full host-owned transport-receipt validation. The tests independently
recompute this digest and require the same literal in the checker.

## Added complete-boundary mutations

Six new disposable source weakenings exercise the repair:

1. move the installed-launcher comparison into dead code;
2. make the expected launcher digest self-referential;
3. remove the installed one-shot comparison;
4. add a later Ansible writer that overwrites the launcher destination;
5. move the guest credential-drive and provider-hosts assertions into dead
   code; and
6. short-circuit the guest's transport-receipt assertions with `true or`.

Each mutation must make the real checker exit nonzero with its controlled
failure header and the exact complete-source or singular-writer diagnostic.
Together with the existing twenty cases, the harness now covers twenty-six
source mutations without increasing the focused suite's 24-test count.

The checker source remains independently pinned by the contract test. A78
review of the exact repaired source SHA is required before any clean-worker
replacement plan. This third operational grant is exhausted after that review
and A77 adjudication; no live or provider action is authorized by it.

## Third-repair verification

The focused spend suite passed 24 tests. Its real-checker mutation subtest
rejected all twenty-six disposable source weakenings, including the six added
for this repair. The unmutated spend checker passed.

Four additional disposable checker-source mutations weakened each new binding
directly:

| Mutated checker binding | Mutated checker SHA-256 | Result |
| --- | --- | --- |
| runner digest comparison guarded by `False and` | `be6d8b18ebb5702c5ea534029658b072afafe743c887c8c6797bf131a673640c` | pinned-checker test failed |
| guest digest comparison guarded by `False and` | `80904f54467e0df6b67bfe7c054950ca02cbe0db50c11bf0b568cc9ef2cfa64a` | pinned-checker test failed |
| worker-task digest comparison guarded by `False and` | `014604c82f86a358b8a23e1d8f393f7196ce3c0cee55500483d4dfcf1f0aa758` | pinned-checker test failed |
| singular-writer comparison guarded by `False and` | `92d3cb91b16db0ba641a804fc1f085ad6338a06abb7eb0a3255ffc71b3e438cb` | pinned-checker test failed |

None of those mutations was retained. The reviewed checker source remains
SHA-256
`231676da8fb3ca579556b9b78e63374ae206003e7cfdaa150668297aaf8a5815`.

The complete application gate passed after regenerating its deterministic
codebase-metrics projection. OpenTofu formatting, initialization, and
validation passed for all three roots; stack, independence, worker-runtime,
worker-qualification, spend, and preview checks passed. ShellCheck passed. All
four Ansible lint profiles and all four playbook syntax checks passed. The full
Ansible unit suite retained its known requirement-1 evidence boundary: 127 of
129 tests passed, with only stale live guest-image-recipe and host-contract
digests failing. The infrastructure wrapper likewise reached only the four
already documented requirement-1 live-evidence shape, image-recipe,
host-contract, and phase diagnostics before stopping. No requirement-1 fixture
was rerun because this source-only repair authorizes no worker or provider
action.

## Third-repair A78 result and A77 close

A78 reviewed exact technical commit `62d2502` with Opus 5 at requested effort
`max`. Claude Code exposed no actual-effort value, so the record claims the
request rather than an unobservable realized setting. A78 rejected eleven novel
in-bound mutations and returned **PASS**: both the runner/install-writer target
and the guest-assertion target are closed, with no material finding.

A78 also reported six defense-in-depth observations: an unpinned guest
installation path, literal-only singular-writer syntax after coordinated
re-pinning, later Ansible writers outside the task file, the terminal unpinned
test, unbound gate wiring, and complete-file change friction. The build seat
independently reproduced every checkable observation and conceded all six under
A77. None defeats the reviewed runner's installed-vs-checkout comparisons
before bearer minting. The retained sentence claiming that the image recipe is
a complete guest-surface binding is conceded as inaccurate; it is not relied on
as qualification evidence.

The review and adjudication are recorded in
`2026-07-30-a78-runner-guest-binding-review.md` and
`2026-07-30-a77-runner-guest-binding-adjudication.md`. The third post-A118
operational source-repair grant is exhausted. No further source repair, worker
plan or mutation, provider request, credential issuance, cap action,
behavioral acceptance, requirement-3 work, or qualification-flag change is
authorized by this grant.

## Subsequent clean-worker authorization and A9 stop

Jacob later explicitly authorized the separately reviewed plan and worker
replacement, and allowed a provider request only if the prerequisites made one
useful. This operational grant is recorded here rather than minted as a new
decision-log ruling; A119 remains reserved.

A78 first rejected the correct replacement plan because its apply wrapper did
not bind the reviewed bytes or source revision and validated converge inputs
too late. Exact commit `6c161e9` repaired those three findings and tightened
the plan action shape. Seven source-only weakening mutations failed. A78 then
returned PASS after independently reproducing all seven.

The exact saved plan created worker `588761785`, attached the reviewed worker
firewall, and destroyed quarantined worker `588590370`. First converge stopped
nonzero because Rocky's live BaseOS/AppStream projection offered incompatible
Python package releases during cloud-init, leaving `firewalld` uninstalled.
The worker never received Factory state or credentials. The second converge,
qualification, isolation probe, and provider phases did not run. The full
record and failure log are in
`2026-07-30-a115-clean-worker-replacement-attempt.md`.

No retry or manual host repair followed. A9 now requires escalation before any
bootstrap source repair, new replacement plan, worker replacement, cap action,
or provider request.

## Immutable-bootstrap repair authorization

After that escalation, Jacob answered: "I authorize the repair, its review,
and a new sequence." This is the next operational grant under A115 and is
recorded here rather than minted as a new numbered decision-log ruling.

The grant covers one bounded repair of the Rocky bootstrap package transaction,
its tests and source-weakening mutations, A78 review, and a fresh worker
replacement sequence only after that review passes. Failed worker `588761785`
remains ineligible for reuse. Cap and provider actions remain gated behind a
cleanly converged and qualified replacement worker. Requirement 3, behavioral
acceptance, and all provider qualification flags remain out of scope.

The implementation and read-only solver experiment are recorded in
`2026-07-30-a115-bootstrap-repair.md`.
