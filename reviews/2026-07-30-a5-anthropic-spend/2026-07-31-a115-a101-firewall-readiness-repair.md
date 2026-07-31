# A115 A101 firewall-readiness repair attempt

Status: **fresh A78 review returned six conceded findings; A9 stop pending a
new bounded authorization**

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

## Fresh A78 result

A78 reviewed exact record commit
`cdd931ec4545f426bf07bd53efd18673e140d346` and returned NOT A PASS with one
medium material finding. The repaired production helper resisted every source
attack, including four multi-value JSON orderings, empty and malformed bodies,
HTTP failures and non-200 statuses, state and provider shape variants, stale
response reuse, ordering bypasses, and a real bearer argv canary.

The remaining defect is test binding. A78 added three behavior-changing source
lines without removing any required fragment:

- `tail -n1` after jq accepts a rejected-then-ready multi-value stream;
- later 900-second curl timeout options override the required three-second
  options; and
- a later `POLL_SECONDS=600` overrides the required two-second assignment.

Each mutant passed all 7 focused tests and all 24 shipped mutations.

The build seat independently reproduced each mutant in a disposable worktree.
Each again passed 7 of 7 tests. Direct local experiments returned `true` from
the filtered multi-value stream, showed curl honoring the later timeout, and
showed Bash's effective poll value as 600. F1 is conceded under A77 with medium
severity sustained.

The exact review and adjudication are recorded in
`2026-07-31-a78-a101-firewall-readiness-repair-source-review.md` and
`2026-07-31-a77-a101-firewall-readiness-repair-source-review-adjudication.md`.

## A9 stop

No further repair was made. The authorized repair loop is exhausted. The
smallest next repair is test-only: add a multi-value provider fixture, assert
every sleep argument equals `2`, require the two curl timeout options to occur
exactly once, and add those three additive mutations.

That repair, full gates, and another A78 review require a new explicit bounded
authorization. It would not authorize a production-source change, replacement
plan, live worker or cloud action, provider request, Console action,
requirement-1 refresh, acceptance, requirement 3, rotation, or qualification
change.

## Additional test-only repair authorization

Jacob explicitly authorized the proposed repair after the A9 stop. The grant
is limited to the three A78 F1 test bindings, their mutations, the complete
repository gates, and a new A78 review. It authorizes no production helper or
operator change and no live action. The grant is recorded under A115 rather
than as a new numbered ruling.

## Additional test-only repair

Only `infra/ansible/tests/test_worker_firewall_readiness.py` changed:

1. the provider mock now emits two complete ready JSON objects in one response,
   and the exhaustive failure set requires 24-attempt refusal;
2. the pending-then-ready case and every exhausting failure assert the exact
   recorded sleep values rather than only the number of sleep calls;
3. the source validator requires the jq command-substitution close, poll
   assignment, connect-timeout option, and transfer-timeout option to be
   singular; and
4. the mutation dictionary adds last-value jq filtering, later 900-second curl
   timeout options, and a later 600-second poll assignment.

The first focused run passed all 7 tests, Python compilation, and
`git diff --check`. It rejects 27 mutations: 23 helper mutations and 4 operator
mutations. No repair loop was needed.

The production identities remain byte-identical:

| File | SHA-256 |
| --- | --- |
| `infra/wait-do-worker-firewall.sh` | `5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba` |
| `infra/replace-worker.sh` | `27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e` |
| `tools/check-ansible.sh` | `ead1c23f932f39ec423222f70775304be6453dcd1cd7c24a45b99699d001158e` |

The repaired test SHA-256 is
`425db4ebcb4b89636a114120c489086f589d1d6c9ee95df6f3f7be27a6f8c821`.

Full gates and fresh A78 review remain pending. No worker, DigitalOcean,
Anthropic, Console, requirement-1, acceptance, requirement-3, rotation, or
qualification-flag action occurred.

## Installed additive mutation checks

The build seat installed each A78 F1 mutation independently in a disposable
detached worktree at exact technical commit
`bb91d7ecd14d3284be5ee73b20c052f75f5e3fe7`. Each source-only weakening made
the real seven-test suite fail:

| Mutation | Observed failure |
| --- | --- |
| pipe jq output through `tail -n1` | the multi-value provider case passed open and the exact jq close binding failed |
| append 900-second curl timeout options | the timeout singularity binding failed |
| append `POLL_SECONDS=600` | the pending and exhaustive cases recorded `600` instead of `2`, and the poll singularity binding failed |

The three mutation-suite exit statuses were all 1. The disposable worktree was
restored byte-clean and removed.

## Additional repair full gates

The complete application wrapper passed at exact clean commit `bb91d7e`:

- 39 browser-control tests passed with the one documented Linux Docker
  integration skip;
- formatting, Clippy, every Rust unit/integration/property/documentation test,
  and triage replay passed;
- two release builds reproduced `factory-verify` SHA-256
  `2eae220106314f3c40626f8c39361987e64e8a7b30f72e117d6ccf615175082f`;
- checksum install and rollback, audit, deny, vet, dependency, model, and
  byte-exact codebase-projection gates passed.

The infrastructure wrapper initialized and validated all three OpenTofu roots
and passed stack, independence, worker-runtime, and worker-qualification
checks. It stopped only on the deliberately stale requirement-1 live
host-contract fixture:

```text
live    bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f
current eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977
```

Complete Ansible discovery passed 146 of 147 tests and failed only that same
assertion. ShellCheck, all four production Ansible lint profiles, and all four
playbook syntax checks passed.

All 13 provider qualification flags remain false. The requirement-1 fixture
was not refreshed.

## Additional-repair A78 handoff

A78 must review the exact final record commit in a new detached worktree,
confirm the production helper and operator are byte-identical, reproduce all
three former green mutants against the repaired test, run all 7 focused tests
and 27 shipped mutations, add independent additive mutations, and return PASS
or material findings. Review authorizes no live or provider action.

## Effective-argv A78 result

A78 reviewed exact record commit
`96d5d0cc61e98b08193f8d3f34b7aac629fc28f3` and returned NOT A PASS:

- M1 medium: short curl options, aliases, shell-function wrappers, a second
  config, and retry options change the effective curl bound while preserving
  every literal source assertion;
- M2 low: `MAX_ATTEMPTS=` is not required to be singular; and
- M3 low: an absolute extra sleep bypasses the PATH mock and passes all tests.

The production helper and operator remained byte-identical, all 7 tests and 27
shipped mutations passed on the unmodified source, and the prior three additive
findings were closed.

The build seat independently reproduced:

- `-m 900` passing all 7 tests and curl honoring a later short-form timeout;
- a duplicate `MAX_ATTEMPTS` assignment passing the structural validator; and
- an extra absolute sleep passing all 7 tests.

All three findings are conceded under A77 with A78's severities sustained. The
exact review and adjudication are
`2026-07-31-a78-a101-firewall-readiness-effective-argv-review.md` and
`2026-07-31-a77-a101-firewall-readiness-effective-argv-adjudication.md`.

## Effective-argv A9 stop

No further repair was made. The smallest next repair remains test-only:
validate the complete ordered curl argv in the mock, require singular
`MAX_ATTEMPTS=`, require one sleep command, and add representative mutations
for every class.

That repair, full gates, and another A78 review require a new explicit bounded
authorization. No production source or live action is included.

## Effective-argv repair authorization and boundary

Jacob authorized the proposed bounded test-only repair in the agent chat on
2026-07-31. The grant covers exact ordered curl argv, singular
`MAX_ATTEMPTS=`, one sleep command, representative source mutations, full
gates, and a new A78 review. It does not authorize a production helper or
operator change, worker or firewall action, provider request, Console action,
requirement-1 refresh, behavioral acceptance, requirement 3, rotation work, or
qualification-flag change.

No new numbered ruling was minted. The authorization is recorded here under
A115 as required by the governance-hygiene instruction.

## Effective-argv test repair

Exact technical commit
`0339826785a5202d6aba8097e71dfc3d382e4df6` changes only
`infra/ansible/tests/test_worker_firewall_readiness.py`:

- the curl mock now accepts exactly 17 ordered arguments and no extras;
- the sole dynamic argument is constrained to the generated private response
  path;
- the terminal URL must use the state-bound firewall ID;
- the validator requires exactly one `MAX_ATTEMPTS=` assignment;
- the validator requires the exact poll sleep and one total `sleep` lexeme;
  and
- the permanent mutation set adds short-form timeout, alias wrapper,
  shell-function wrapper, second config, retry expansion, duplicate maximum
  attempts, and absolute extra sleep.

All 7 focused tests pass. The suite rejects 34 source mutations: 30 helper
mutations and 4 operator mutations. The repaired test SHA-256 is
`b233c67f77b7fb8aca1e67b6dbbff640f225374e5d74213f81736092c6af41be`.

The production identities remain byte-identical:

| File | SHA-256 |
| --- | --- |
| `infra/wait-do-worker-firewall.sh` | `5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba` |
| `infra/replace-worker.sh` | `27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e` |
| `tools/check-ansible.sh` | `ead1c23f932f39ec423222f70775304be6453dcd1cd7c24a45b99699d001158e` |

## Effective-argv installed mutation checks

The build seat installed seven independent helper mutations in disposable
detached worktrees at the technical commit. Every real seven-test suite
failed:

| Mutation | Observed binding |
| --- | --- |
| append `-m 900` | exact curl argv refused the call before counting it |
| alias curl to prepend `-m 900` | exact curl argv refused the wrapper argument |
| wrap curl in a shell function that prepends `-m 900` | exact curl argv refused the wrapper argument |
| append a second curl config | exact curl argv refused the extra config and value |
| append retry controls | exact curl argv refused all extra retry arguments |
| append `MAX_ATTEMPTS=25` | assignment singularity and exact 24-call behavior failed |
| append `/bin/sleep 0.02` | sleep lexical singularity failed |

All seven completed runs exited 1. A preliminary 240-attempt duplicate run
had already emitted its structural failure but was interrupted rather than
waiting through the deliberately enlarged loop; the completed 25-attempt
duplicate proves the same assignment class. All disposable worktrees were
removed.

## Effective-argv full gates

With the technical source and regenerated codebase projection, the complete
application wrapper passed:

- all 39 browser-control tests passed with the one documented Docker-only
  skip;
- formatting, Clippy, every Rust unit/integration/property/documentation test,
  and triage replay passed;
- the release builds reproduced `factory-verify` SHA-256
  `2eae220106314f3c40626f8c39361987e64e8a7b30f72e117d6ccf615175082f`;
  and
- checksum, audit, deny, vet, dependency, model, and codebase-projection gates
  passed.

The infrastructure wrapper initialized and validated all three OpenTofu roots
and passed stack, independence, worker-runtime, and worker-qualification
checks. It stopped only on the deliberately stale requirement-1 host-contract
fixture:

```text
live    bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f
current eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977
```

Complete Ansible discovery passed 146 of 147 tests and failed only the same
fixture assertion. ShellCheck, all four production Ansible lint profiles, and
all four playbook syntax checks passed.

All 13 provider qualification flags remain false. No live or provider action
occurred.

## Effective-argv A78 handoff

A78 must review the final record commit in a new detached worktree, verify the
production helper and operator remain byte-identical, run all 7 focused tests
and all 34 shipped mutations, reproduce the seven installed mutation classes,
add independent additive mutations, and return PASS or material findings. The
review authorizes no real curl, network, provider, worker, or Console action.

## Invocation-singularity A78 result

A78 reviewed exact record commit
`6e9e9821e17c8d0e3a47169e829e060a3a51eec7` and returned NOT A PASS with one
High finding. All 7 tests and all 34 shipped mutations passed on the unmodified
source, and the three authorized binding classes were individually verified.
However, an extra non-conforming curl call remains invisible because the mock
increments its counter only after argv validation.

A78 made both a discarded timeout-and-retry call and a discarded response-file
overwrite call pass all 7 tests. The build seat independently reproduced both
green suites, then showed that an additive absolute-path stand-in also passes
while bypassing the PATH mock.

The exact records are
`2026-07-31-a78-a101-firewall-readiness-invocation-singularity-review.md` and
`2026-07-31-a77-a101-firewall-readiness-invocation-singularity-adjudication.md`.
M1 is conceded at High severity under A77.

## Invocation-singularity A9 stop

No further repair was made. A9 requires a new bounded test-only authorization
before attempted and accepted curl counts, a source-level curl singularity
binding, and representative extra-invocation mutations can be added and
returned through full gates and A78.

No production source, live system, worker, provider state, Console limit,
requirement-1 fixture, acceptance case, requirement-3 artifact, rotation state,
or qualification flag changed.

## Invocation-singularity repair authorization

Jacob explicitly authorized the bounded repair in the agent chat on
2026-07-31. The grant covers attempted and accepted curl counters, a
source-level curl-executor singularity binding, representative extra-invocation
mutations, the full repository gates, and a new A78 review. It authorizes no
production helper or operator change and no live, worker, firewall, provider,
Console, requirement-1, acceptance, requirement-3, rotation, or
qualification-flag action.

The authorization is recorded under A115. It does not mint a new numbered
ruling, and A119 remains taken.

## Invocation-singularity test repair

Exact technical commit
`3ec94b419fe6fc50ba0bfc5609437a1c8f0afb07` changes only
`infra/ansible/tests/test_worker_firewall_readiness.py`:

- the curl mock increments `MOCK_CURL_TOTAL` before validating any argument,
  so rejected attempts cannot disappear;
- `MOCK_CURL_CALLS` remains the independently observed accepted-call counter;
- every behavior case asserts exact accepted and attempted totals, including
  1/1 for immediate readiness, 2/2 for pending then ready, 24/24 for every
  exhausting refusal, and 0/0 before provider polling;
- the source validator normalizes empty quotes and simple backslash escapes,
  then requires one standalone raw `curl` executor; and
- the permanent mutation harness adds two discarded calls, an absolute-path
  call, an empty-quote assembled call, and a rejected wrapper call whose
  accepted count remains one while its attempted count becomes two.

All 7 focused tests pass. The suite exercises 39 source mutations: 29 static
helper mutations, 5 effective-curl-argv mutations, 1 attempted-call mutation,
and 4 operator mutations. The repaired test SHA-256 is
`e558b7b0ceb0f041359470f8518c718bba9b5b6a1f48648c3783771b345465ee`.

The production identities remain byte-identical:

| File | SHA-256 |
| --- | --- |
| `infra/wait-do-worker-firewall.sh` | `5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba` |
| `infra/replace-worker.sh` | `27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e` |
| `tools/check-ansible.sh` | `ead1c23f932f39ec423222f70775304be6453dcd1cd7c24a45b99699d001158e` |

## Invocation-singularity installed mutation checks

The build seat installed five independent source weakenings into disposable
detached worktrees at the technical commit and ran the real seven-test suite
against each one:

| Installed mutation | Observed binding |
| --- | --- |
| discarded direct provider curl with a 900-second timeout and retries | attempted-call totals doubled and the source executor/endpoint contract also rejected the addition |
| discarded curl overwriting the response file | attempted-call totals doubled and the structural contract rejected the additional executor |
| absolute `/nonexistent/curl` provider call | the source-level executor and provider-endpoint singularity contract rejected it |
| empty-quote assembled `cu""rl` call | normalization exposed the second executor and the singularity contract rejected it |
| extra rejected `curl_with_bearer` call to `https://example.invalid/` | accepted calls remained 1 while attempted calls became 2, so the exact total assertion failed independently |

Every installed mutation suite exited 1. All disposable mutation worktrees
were removed and pruned. The wrapper case demonstrates that the attempted
counter is independently load-bearing even when the lexical executor and
provider-endpoint bindings remain unchanged.

## Invocation-singularity full gates

The complete application wrapper passed with the technical source and
regenerated codebase projection:

- 39 browser-control tests passed with the one documented Linux Docker
  integration skip;
- formatting, Clippy, every Rust unit/integration/property/documentation test,
  and triage replay passed;
- two release builds reproduced `factory-verify` SHA-256
  `2eae220106314f3c40626f8c39361987e64e8a7b30f72e117d6ccf615175082f`;
  and
- checksum install/rollback, audit, deny, vet, dependency, model, and
  byte-exact codebase-projection checks passed.

The infrastructure wrapper initialized and validated the DigitalOcean, AWS,
and GitHub OpenTofu roots and passed stack, independence, worker-runtime, and
worker-qualification checks. It stopped only on the deliberately stale
requirement-1 host-contract fixture:

```text
live    bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f
current eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977
```

Complete Ansible discovery passed 146 of 147 tests and failed only the same
exact assertion. All four production Ansible lint profiles and all four
playbook syntax checks passed. Refreshing the live requirement-1 fixture
remains outside authorization and would falsely claim a live rerun.

All 13 provider qualification flags remain false. No credential, provider
request, worker, firewall, Console limit, acceptance case, requirement-1
evidence, requirement-3 artifact, or rotation state changed.

## Invocation-singularity A78 handoff

A78 must review the exact final record commit in a fresh detached worktree,
verify the three production identities remain byte-identical, run all 7
focused tests and all 39 shipped mutations, reproduce the five installed
mutation classes, invent additional additive executor or counter bypasses, and
return PASS or material findings. Review authorizes no real curl, network,
provider, worker, firewall, or Console action.

## Invocation-singularity repair A78 result

A78 reviewed exact record commit
`b66e6dcd77b9b32dca95b279beaa30039f9f6535` in a clean detached worktree and
returned NOT A PASS with six material findings. The authorized changes
themselves work: all 7 tests, all 39 shipped mutation paths, both exact mock
counters, the five installed mutation classes, and all three production
source identities were verified.

The remaining gaps are broader than literal curl singularity:

1. an alternate network client can bypass curl-only source and runtime gates;
2. quote or parameter assembly can produce an absolute client path without a
   literal curl token;
3. a sourced sibling or Bash `/dev/tcp` builtin is outside the helper contract;
4. the operator is unbound outside the narrow readiness interval;
5. open-ended Ansible discovery and ShellCheck membership have no independent
   census binding; and
6. code under test can redirect the attempted-counter destination.

The build seat independently reproduced every finding. Alternate and
parameter-assembled local stubs each executed 436 times while all 7 tests
passed. Guarded source, guarded `/dev/tcp`, and operator mutants also kept all
7 tests green. A redirected hidden counter recorded 436 extra rejected mock
attempts while the asserted counters remained exact. Empty unittest discovery
returned 0 after running zero tests.

F1 and F2 are conceded at High; F3, F4, and F5 at Medium; and F6 at Low. The
exact review and adjudication are
`2026-07-31-a78-a101-firewall-readiness-invocation-singularity-repair-review.md`
and
`2026-07-31-a77-a101-firewall-readiness-invocation-singularity-repair-adjudication.md`.

## Invocation-singularity repair A9 stop

No further repair was made. A new explicit bounded authorization is required
for a test-and-gate structural redesign, installed F1-F6 mutations, the full
repository gates, and another fresh A78 review. The operational grant must be
recorded under A115 without a new numbered ruling.

No production source, live system, worker, firewall, provider state, Console
limit, requirement-1 fixture, acceptance case, requirement-3 artifact,
rotation state, or qualification flag changed.
