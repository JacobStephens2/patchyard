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
