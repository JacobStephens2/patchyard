# A115 A101 firewall-readiness repair attempt

Status: **first A78 review returned three conceded findings; bounded source
repair and full gates complete; pending fresh A78 source review**

## Authorization and boundary

After A78 passed the quarantined-successor operational record, Jacob
authorized the proposed bounded source-only repair: add a fail-closed
DigitalOcean firewall desired-state precondition before A101, bind it with
tests and source mutations, run the full gates, and return it to A78. The grant
authorizes no worker or firewall mutation, replacement plan, host access,
Anthropic credential or request, Console action, requirement-1 refresh,
behavioral acceptance, requirement-3 work, credential rotation, or provider
qualification-flag change.

This operational grant is recorded under A115. It does not mint a new numbered
ruling, and A119 remains taken.

## Source candidate

The uncommitted candidate adds
`infra/wait-do-worker-firewall.sh` immediately after the replacement wrapper's
second convergence and before its first `infra/ansible/qualify.sh` call.
Because A101 remains inside that qualifier, the new precondition is ordered
before A101 and does not retry it.

The helper derives the exact worker and firewall identities from current
post-apply OpenTofu state. It refuses unless state contains exactly one
`digitalocean_droplet.worker`, exactly one
`digitalocean_firewall.worker`, and the firewall's sole droplet attachment
matches that worker. It then polls only
`/v2/firewalls/<state-bound-firewall-id>` and accepts only one provider shape:

- the returned firewall ID matches the state-bound ID;
- the name is exactly `patchyard-worker`;
- `status` is exactly `succeeded`;
- `pending_changes` is an array of length zero;
- `droplet_ids` is an array containing only the state-bound worker ID; and
- `tags` is an array of length zero.

The loop has 24 fixed attempts, two seconds between attempts, and three-second
connect and transfer timeouts. Exhaustion, HTTP failure, malformed provider
JSON, a state mismatch, or any provider-field mismatch stops nonzero. It does
not claim that provider control-plane readiness proves data-plane propagation;
A101 remains the independent terminal management-transport check.

Candidate SHA-256 values at the A9 stop:

| File | SHA-256 |
| --- | --- |
| `infra/wait-do-worker-firewall.sh` | `eaad6d53ad12bd795cf640a227bc345467d8717beecd470a2ef7aa4693a58915` |
| `infra/replace-worker.sh` | `27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e` |
| `infra/ansible/tests/test_worker_firewall_readiness.py` | `c267ffa33330748038757717d2b5f301271dac05c768f044bb5e048c134a9971` |
| `tools/check-ansible.sh` | `ead1c23f932f39ec423222f70775304be6453dcd1cd7c24a45b99699d001158e` |

These are local candidate bytes, not reviewed or accepted source.

## First focused failure and authorized repair

The first focused test invocation failed before executing a case because the
new test used Python 3.10 union annotation syntax under the repository's
Python 3.9 runtime:

```text
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
```

The one authorized repair loop added postponed annotation evaluation to the
test module. Bash parsing and ShellCheck already passed. No production helper
predicate or operator ordering changed in this repair.

## Second focused failure

At `2026-07-31T02:38:25Z`, the repeated focused boundary still failed:

```text
Ran 6 tests in 5.476s
FAILED (failures=9, errors=1)
```

The exact provider-ready case passed, and the source/operator contract passed.
Python compilation, Bash parsing, and ShellCheck also passed. The remaining
failures are in the new test harness:

1. the mock curl counter overwrites one numeric value, while assertions count
   file lines and therefore report 1 after every multi-poll case;
2. the invalid-worker-ID state fixture tries to convert its intentionally
   invalid string to an integer while constructing the fixture; and
3. the `MAX_ATTEMPTS=24` mutation becomes `MAX_ATTEMPTS=240`, which still
   contains the shorter text as a prefix, so the exact-binding validator does
   not reject that one mutation.

The other provider-binding mismatch cases reached the helper's refusal path,
and every other recorded source-only weakening mutation was rejected. Those
partial observations do not turn the focused suite into a pass.

## A9 stop

No second repair was made. The candidate and this failure record are preserved
on draft PR #79 only as a stopped A9 artifact; they are not accepted or fit to
apply while the focused suite is red. The full application, infrastructure,
and Ansible gates were not started, and no A78 review was requested.

Further work requires a new explicit bounded repair authorization for only the
three checkable test-harness defects above, followed by the same focused tests,
source mutations, full repository gates, and A78 source review. No new
numbered ruling should record that operational grant.

No live Factory, DigitalOcean, Anthropic, Console, acceptance, requirement-1,
requirement-3, rotation, or qualification-flag action occurred.

## Further bounded repair authorization

Jacob explicitly authorized the requested repair after the A9 stop. The grant
is limited to the three recorded test-harness defects: numeric mock-call
counter interpretation, invalid worker-ID fixture construction, and exact
attempt-count mutation matching. It also authorizes the already-declared
focused tests, mutation checks, full gates, and A78 source review.

The grant authorizes no change to the production readiness predicates, no
replacement plan or apply, no host or cloud mutation, no provider credential
or request, and none of the other excluded A-5 or acceptance work. It is
recorded under A115 rather than as a new numbered ruling.

## Further bounded repair

The repair made exactly three test-only changes:

1. curl mock calls are read as the numeric value stored in the counter file,
   while sleep calls remain line-counted;
2. the invalid worker-ID fixture uses a separate valid attachment value so the
   helper, rather than fixture construction, rejects the invalid state; and
3. fixed numeric bounds are compared as complete source lines, so changing
   `MAX_ATTEMPTS=24` to `MAX_ATTEMPTS=240` cannot retain a prefix match.

The production helper and operator did not change. Their SHA-256 values remain
`eaad6d53ad12bd795cf640a227bc345467d8717beecd470a2ef7aa4693a58915`
and
`27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e`.
The repaired test SHA-256 is
`99ad3e964b078edc5f79240749e13758b3b2d8ced30a8f0d130e5d82b7b7cdda`.

## Focused tests and source mutations

All 6 readiness tests pass. They prove immediate exact-state success,
pending-then-ready polling, 24-attempt fail-closed exhaustion for seven
provider failure shapes, pre-provider refusal of three invalid OpenTofu state
shapes, and exact operator ordering after two converges and before A101.

The permanent source mutation harness rejects all 11 authored weakenings:

1. expand the fixed attempt count from 24 to 240;
2. remove curl's transfer timeout;
3. weaken the exact provider firewall ID;
4. weaken the exact provider firewall name;
5. weaken `status=succeeded`;
6. permit nonzero pending changes;
7. weaken the provider worker attachment;
8. permit a tag attachment;
9. weaken the OpenTofu worker/firewall attachment equality;
10. remove the readiness call from the replacement operator; and
11. move readiness after the qualifier and therefore after A101.

The combined replacement/readiness suite passes 13 of 13. All 47 Session 16
cutover contract tests and all 25 Anthropic spend tests pass, including the
spend checker's existing 36 structural mutations. The unmodified spend checker,
Python compilation, Bash parsing, ShellCheck, and `git diff --check` pass.

## Full repository gates

Exact clean technical commit
`ec8f2c33b332a0fbc85c9b3709e81b4e903838df` passed the complete application
wrapper: 39 browser-control tests with the one Docker-only integration skip,
all Rust unit, integration, property, fixture, database, and documentation
tests, triage replay, reproducible `factory-verify` release SHA-256
`2eae220106314f3c40626f8c39361987e64e8a7b30f72e117d6ccf615175082f`,
checksum install/rollback, advisory, license, source, vet, dependency, model,
and byte-exact codebase-projection checks.

The infrastructure wrapper initialized and validated all three OpenTofu roots,
then passed stack, independence, worker-runtime, and worker-qualification
checks. It stopped only at the deliberately stale requirement-1 live
host-contract fixture:

```text
live    bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f
current eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977
```

The complete Ansible unit discovery passed 145 of 146 tests and stopped only
on the same exact fixture mismatch. ShellCheck includes the new helper. All
four production Ansible lint profiles and all four playbook syntax checks pass.
Refreshing requirement 1 after a failed replacement would falsely claim a live
rerun, so the red live-evidence dependency remains intentional.

All 13 `credential_qualified` flags remain false.

## A78 review boundary

A78 must review the exact final record commit in a fresh detached worktree and:

1. verify that the helper binds one current OpenTofu firewall to one current
   worker before reading provider state;
2. verify all six provider desired-state predicates and the fixed polling/time
   bounds;
3. verify readiness is after both converges and before A101, with A101 still
   one-shot and terminal;
4. rerun the focused behavior and mutation checks, adding adversarial
   source-only mutations where useful; and
5. return PASS or material findings without accessing a host, applying a plan,
   changing DigitalOcean state, or performing any Anthropic or Console action.

The current worker remains quarantined. This repair does not authorize a fresh
worker plan or live sequence.

## First A78 review and A77 disposition

A78 reviewed exact commit
`097a5b4acdf68fb27b173445f0df0ff6fb3b7e74` in a clean detached worktree and
returned NOT A PASS:

- F1 high: jq 1.6 exits zero for empty or whitespace-only input, so a
  successful zero-byte response bypassed every provider predicate;
- F2 medium: four independent source weakenings survived the current contract,
  and combined fixtures masked individual pending and cardinality predicates;
  and
- F3 low: the new helper placed the DigitalOcean bearer in curl's process
  argument vector.

The build seat reproduced and conceded all three findings under A77. The exact
review and adjudication are recorded in
`2026-07-31-a78-a101-firewall-readiness-source-review.md` and
`2026-07-31-a77-a101-firewall-readiness-source-review-adjudication.md`.

Jacob then authorized the bounded repair, its tests and source mutations, the
full gates, and a fresh A78 review. This operational grant is recorded under
A115, not as a new numbered ruling.

## Authorized source repair

The helper now rejects empty and whitespace-only bodies, captures jq output,
and accepts only the exact single value `true`. It requires an exact HTTP 200
in addition to curl's `--fail`, uses a private temporary response file, and
passes a validated bearer through `curl --config -` on standard input rather
than argv.

The repaired suite independently exercises:

- empty and whitespace bodies;
- a redirect carrying an otherwise ready body;
- `status=succeeded` with nonempty pending changes;
- a provider firewall with an extra worker;
- two workers in OpenTofu state;
- a state firewall with two worker attachments; and
- a malformed bearer before the provider mock can run.

It also requires the operator interval between the second converge and A101 to
contain only one direct fatal readiness call.

The first focused repair run found one expected-block formatting error in the
test validator and one standalone ShellCheck unused-trap-helper warning. The
authorized repair loop replaced the helper function with a direct EXIT trap
and corrected the exact indentation-aware operator interval. The repeated
focused run passed all 7 tests, Bash parsing, Python compilation, standalone
ShellCheck, and `git diff --check`.

The permanent source mutation set now rejects 24 weakenings: 20 helper
mutations and 4 operator mutations. New cases cover empty-body acceptance,
jq-status-only acceptance, non-200 acceptance, curl failure acceptance,
provider object type, state worker/firewall/attachment cardinality, provider
attachment cardinality, bearer argv exposure, bearer-alphabet weakening,
conditional readiness, and a nonfatal readiness call.

No live or provider action occurred.

## Repaired source identity

Exact repaired record commit:
`69b38764a47c9de7d3e9941700d7d8bb8d06baec`.

| File | SHA-256 |
| --- | --- |
| `infra/wait-do-worker-firewall.sh` | `5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba` |
| `infra/replace-worker.sh` | `27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e` |
| `infra/ansible/tests/test_worker_firewall_readiness.py` | `39aab86e37321c896a80f0c182644abf2f37d124ffa62ae5039d1da5d11e00b2` |
| `tools/check-ansible.sh` | `ead1c23f932f39ec423222f70775304be6453dcd1cd7c24a45b99699d001158e` |

The operator and Ansible wrapper remain byte-identical to the first A78
revision. Only the readiness helper, its tests, generated codebase projection,
and review/work records changed.

## Full repaired gate set

The complete application wrapper passed at exact clean commit `69b3876`:

- constitution and 39 browser-control tests passed, with the one documented
  Linux Docker integration skip;
- formatting, Clippy, all Rust unit/integration/property/documentation tests,
  and triage replay passed;
- two independent release builds reproduced
  `factory-verify` SHA-256
  `2eae220106314f3c40626f8c39361987e64e8a7b30f72e117d6ccf615175082f`;
- checksum install and rollback, audit, deny, vet, dependency, model, and
  byte-exact codebase-projection checks passed.

The infrastructure wrapper initialized and validated the DigitalOcean, AWS,
and GitHub OpenTofu roots and passed stack, independence, worker-runtime, and
worker-qualification checks. It stopped only when the requirement-1 checker
honestly reported the preexisting stale live host-contract binding:

```text
live    bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f
current eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977
```

Complete Ansible discovery passed 146 of 147 tests and failed only the same
exact assertion. ShellCheck, all four production Ansible lint profiles, and
all four playbook syntax checks passed. Refreshing the live requirement-1
fixture remains outside authorization and would falsely claim a live rerun.

All 13 provider `credential_qualified` values remain false. No namespaced or
bare Anthropic credential, worker, cloud resource, provider request, Console
limit, acceptance case, requirement-1 evidence, requirement-3 artifact, or
rotation state changed.

## Fresh A78 handoff

A78 must review the final record commit in a new detached worktree, reproduce
the former empty-body bypass against the parent, verify it is closed in the
repair, run all 7 focused tests and all 24 source mutations, add independent
mutations, and return PASS or material findings. Review authorizes no live
action.
