# A115 A101 firewall-readiness repair attempt

Status: **isolated execution-closure repair ready for exact-head A78 review;
no live action**

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

## F1-F6 structural-redesign authorization

Jacob explicitly authorized the bounded redesign addressing F1 through F6 in
the agent chat on 2026-07-31. The grant covers test-and-gate source changes,
installed source mutations for all six findings, the full repository gates,
and another clean A78 review. It does not authorize a production helper,
replacement operator, or Ansible-wrapper change, and it authorizes no live
worker, DigitalOcean, Anthropic, Console, requirement-1 refresh, acceptance,
requirement-3, rotation, or qualification-flag action.

The authorization is recorded under A115. It does not mint a new numbered
ruling, and A119 remains taken.

## F1-F6 structural redesign

Technical commits `340728d5eb0f49109e77f1055896e019ab5ef0c5` and
`2a1b3dd546f8747f44740ba8a74d400d2adfa75d` change only the readiness test,
the independently executed Anthropic spend checker, and the spend checker's
contract test.

The redesign uses the existing independent gate chain rather than extending
the production scripts:

- `tools/check-infra.sh` independently executes
  `tools/check-anthropic-spend.py`;
- the spend checker exact-digest binds the complete helper, operator, Ansible
  wrapper, and readiness test;
- the spend contract test independently exact-digest binds the complete spend
  checker and the same four readiness sources;
- the readiness test independently exact-digest binds the complete production
  helper, operator, and Ansible wrapper;
- the readiness test requires the wrapper to contain the exact helper and
  operator ShellCheck members and to discover the readiness test; and
- the spend checker independently requires the same wrapper census, so a
  renamed `TestCase` that makes discovery execute zero cases still fails.

The helper contract now rejects undeclared sourcing, `/dev/tcp`, and
`/dev/udp`. The operator contract rejects added network executors anywhere in
the complete operator, not only inside the readiness interval. Mock
measurement destinations are literal private paths embedded in the generated
mock scripts, so code under test cannot redirect them through
`MOCK_CURL_TOTAL`, `MOCK_CURL_CALLS`, or `MOCK_SLEEP_CALLS` environment
variables. Complete-source identities make alternate clients, quote or
parameter assembly, absolute executors, and later bypass definitions change a
reviewed binding instead of relying on an incomplete shell normalizer.

Exact final source identities before the A78 handoff are:

| File | SHA-256 |
| --- | --- |
| `infra/wait-do-worker-firewall.sh` | `5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba` |
| `infra/replace-worker.sh` | `27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e` |
| `tools/check-ansible.sh` | `ead1c23f932f39ec423222f70775304be6453dcd1cd7c24a45b99699d001158e` |
| `infra/ansible/tests/test_worker_firewall_readiness.py` | `2976bb4e5fbc7f1434aaac3fa84b0ddc4f0b78aaf27eb7139571b2e903619b4c` |
| `tools/check-anthropic-spend.py` | `83332667d754f44a0692db7d13cf000215fd2aca4971e9b7cdeb1ded51284c08` |
| `infra/ansible/tests/test_anthropic_spend.py` | `94b5d53c7b19c846322b843d3596e9a32b11294796aef97d60b698f8433397a2` |

The production helper, replacement operator, and Ansible wrapper are
byte-identical to the six-finding review. No production behavior changed.

## F1-F6 focused and installed mutation checks

All 7 readiness tests pass, including 47 permanent readiness mutation paths.
All 27 Anthropic spend contract tests pass, and the independently executed
spend checker passes. Python compilation, Bash parsing, ShellCheck, and
`git diff --check` pass.

The build seat then installed ten independent mutations into disposable
detached worktrees with the final redesign source and ran the real gates:

| Finding or binding | Installed mutation | Observed failure |
| --- | --- | --- |
| F1 | add an alternate `/nonexistent/wget` client | independent spend checker rejected the changed helper identity |
| F2 | assemble `/nonexistent/cur` plus `l` as an absolute client | independent spend checker rejected the changed helper identity |
| F3 | add a guarded sourced sibling | readiness source contract and independent checker rejected it |
| F3 | add guarded Bash `/dev/tcp` with the guard unset | readiness source contract and independent checker rejected it without opening a socket |
| F4 | add an unexecuted operator-wide curl | readiness operator identity and independent checker rejected it |
| F5 | remove helper ShellCheck membership from the wrapper | readiness wrapper contract and independent checker census rejected it |
| F5 | change the readiness class superclass from `TestCase` to `object` | direct discovery ran zero tests and exited zero, while the independent checker rejected the zero-test census |
| F6 | prepend `MOCK_CURL_TOTAL=/dev/null` to a quote-split curl | the private counter still recorded the extra call, focused behavior failed, and the identity binding failed |
| checker identity | make the checker's source comparison unreachable with `False and` | the direct weakened checker passed, while the spend contract suite failed six independent binding and mutation assertions |
| test identity | re-expose a private counter path through the helper environment | readiness behavior stayed green, while the independent checker and spend contract test rejected the changed test identity |

Every installed source-only weakening made at least one independently invoked
suite exit nonzero. The two deliberately self-weakening identity mutations
also prove that neither the checker nor its test can weaken its own new
binding without another gate failing. All ten disposable worktrees were
removed and pruned. No stub opened a socket and no real network client ran.

## Newly published RustSec repair

The first complete application-gate attempt reached and passed both
reproducible release builds, then downloaded a new RustSec record and failed
on `RUSTSEC-2026-0221`. The advisory database had advanced to commit
`29b6c63d8edcc354b75d0c8895ea188208eb0e17` at
`2026-07-31T12:06:56Z`, adding the `event-listener` unsoundness advisory.
Both the branch and its reviewed base still contained vulnerable version
5.4.1; the failure was independent of F1-F6.

A disposable worktree proved that updating `event-listener` to patched 5.4.2
changes only `Cargo.lock`, removes the now-unused `concurrent-queue` entry,
passes `cargo audit --deny warnings`, and passes all workspace Rust tests.
Jacob then explicitly authorized that lockfile-only security repair.

The complete application gate next reached `cargo vet` and correctly refused
5.4.2 because its exact bootstrap exemption still named 5.4.1. Jacob
separately authorized the minimal companion change: move the exact
`event-listener` exemption from 5.4.1 to 5.4.2, remove the unused
`concurrent-queue` exemption, regenerate the mechanical metrics projection,
and repeat the gates. The exemption remains the exact-version bootstrap record
described in `supply-chain/README.md`; it is not an Patchyard audit claim. A
disposable trial returned `Vetting Succeeded (321 exempted)` before the source
was changed.

Exact dependency repair commit:
`ba22d91bca6e123bfa776c9b3127e690a9e2f909`.

## F1-F6 final repository gates

The complete hosted-CI application wrapper passes at the dependency-repaired
source:

- all 39 browser-control tests pass with the one documented Docker-only skip;
- formatting, Clippy, all Rust unit, integration, property, fixture,
  database-contract, and documentation tests, and triage replay pass;
- both release builds reproduce `factory-verify` SHA-256
  `99e3d1da120848b5cb4198788504404bea2e2c178316f301c603a987e8795bae`;
- checksum install and rollback pass;
- the 1,175-record RustSec scan, cargo-deny advisory, ban, license and source
  checks, cargo-vet, cargo-machete, model, and byte-identical codebase metrics
  gates pass; and
- `cargo vet --locked` reports `Vetting Succeeded (321 exempted)`.

The infrastructure wrapper initializes and validates the DigitalOcean, AWS,
and GitHub OpenTofu roots, then passes stack, independence, worker-runtime,
and worker-qualification checks. It stops only at the deliberately stale
requirement-1 live host-contract fixture:

```text
live    bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f
current eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977
```

Complete Ansible discovery runs 149 tests: 148 pass and only that exact
requirement-1 assertion fails. ShellCheck includes the helper and operator.
All four production Ansible lint profiles pass with zero warnings, and all
four playbook syntax checks pass. The independently executed Anthropic spend
and preview-runtime checks pass. Refreshing the live requirement-1 fixture is
outside this source-only authorization and would falsely claim a live rerun.

All 13 `credential_qualified` flags remain false. No host, worker,
DigitalOcean resource, credential, provider request, Console setting,
requirement-1 evidence, acceptance case, requirement-3 artifact, rotation
state, or qualification flag changed.

## F1-F6 A78 handoff

A78 must review the exact final record commit in a new detached worktree,
confirm all six findings are closed by independent and load-bearing bindings,
run all 7 readiness tests and all 27 spend contract tests, reproduce the ten
installed mutation classes, and add new source-only attacks where useful.
A78 must also confirm that the dependency repair is limited to patched
`event-listener` 5.4.2, removal of its unused transitive dependency and exact
exemption, and the generated metrics projection.

Review authorizes no real network client, host, worker, DigitalOcean,
Anthropic, Console, requirement-1 refresh, acceptance, requirement-3,
rotation, or qualification-flag action.

## F1-F6 redesign A78 result

A78 reviewed exact record commit
`2a325357810837ee384a2ca22633dee8900029d2` in a fresh detached worktree and
returned NOT A PASS. A78 verified the three production identities, all 7
readiness tests, all 27 spend tests, the independent checker, all ten installed
mutation classes, both F5/F6 repairs, and the limited RustSec update. It then
reported five further findings:

1. High: `infra/tofu.sh`, `converge.sh`, and `qualify.sh` remained outside the
   complete readiness execution binding;
2. High as reported: a preceding module in shared unittest discovery could
   monkeypatch `hashlib.sha256` for later modules;
3. Medium-High as reported: the repository-internal digest graph lacked an
   external reviewed root;
4. Medium inherited: the stale requirement-1 fixture stopped the wrapper
   before lint and syntax checks; and
5. Medium as reported: executable `source` of the unbound tool-version file
   could replace every gate command with a shell function.

The exact review is recorded in
`2026-07-31-a78-a101-firewall-readiness-f1-f6-redesign-review.md`.

## F1-F6 redesign A77 adjudication

The build seat independently conceded the unpinned transitive oracle at High,
conceded shared-process discovery with a Medium-High scope correction,
conceded the need for a repository-external trust root while refuting the
claimed all-green semantic weakening, sustained the stale requirement-1
fixture as an inherited honest-red boundary, and conceded executable pin
loading while raising it to High.

The checkable experiments were:

- a modified `tofu.sh` with inert alternate clients and substituted state
  passed the old checker and added no discovery failure;
- a modified issuance module forged helper hashes inside discovery, but the
  separately launched spend checker still rejected the helper mutation;
- rolling every old digest for alternate-client, assembled-client, and sourced
  sibling mutations did not make the readiness contract pass - it failed on
  curl-executor singularity; and
- shell functions in `infra/tool-versions.env` made the old Ansible wrapper
  exit zero without executing its tests, lints, or syntax checks.

The exact dispositions and outputs are recorded in
`2026-07-31-a77-a101-firewall-readiness-f1-f6-redesign-adjudication.md`.

## Root-of-trust repair authorization

Jacob explicitly authorized the bounded repair after adjudication. The grant
covers a workflow-rooted source census, isolated and explicit test execution,
inert tool-version parsing, aggregate Ansible gates, source mutations, the full
repository gates, and another A78 review. It is recorded under A115 without a
new numbered ruling.

The grant authorizes no worker or firewall plan or apply, host access,
DigitalOcean or Anthropic request, Console action, requirement-1 refresh,
acceptance case, requirement-3 work, rotation, or qualification-flag change.

## Workflow-rooted repair

Technical commit `30615e8` establishes `.github/workflows/infrastructure.yml`
as the review root. Before any executable tool setup, the workflow checks the
literal SHA-256 of `tools/check-a101-readiness-root.py` and then executes it.
The checker exact-digest binds:

- the helper, replacement operator, `tofu.sh`, `converge.sh`, `qualify.sh`,
  and the inventory wrapper;
- the inert tool-version parser, the tool-version data, and the ShellCheck
  installer;
- the infrastructure and Ansible wrappers and the independent spend checker;
  and
- the root, readiness, and spend test modules.

It also requires the exact set of all 14 Ansible test modules, the wrapper's
same ordered module census, a separately launched spend checker, no open-ended
discovery, spend-before-issuance ordering, and the workflow's literal pin of
the checker's own current bytes.

The Ansible wrapper runs every module in a fresh Python process. It runs the
root, readiness, and spend security modules first, continues through every
remaining module after a failure, runs all four lint and four syntax gates,
rechecks the trust root, and returns the aggregate nonzero status. The stale
issuance fixture therefore stays red without hiding independent results.

`tools/check-infra.sh` now runs the root checker first and the independent
spend checker before the stale issuance checker. `tools/check-ansible.sh`,
`tools/check-infra.sh`, and `tools/install-shellcheck.sh` no longer source
`infra/tool-versions.env`. They query `tools/read-infra-tool-version.py`, which
accepts only the complete known key set, one inert `KEY=VALUE` assignment per
line, exact value shapes, and a ShellCheck URL derived from the selected
version.

Exact root identities are:

| File | SHA-256 |
| --- | --- |
| `tools/check-a101-readiness-root.py` | `2914d771d38fcdeb8434045ecb86d7a56c6c4e7804c91058cd5f2965a582f921` |
| `tools/check-ansible.sh` | `db391e029f876269f85b0276d20ca7370f8be6179f94285b516c31d32bca128b` |
| `tools/check-infra.sh` | `24e28cc6830725f89b889f4b1116eb019acd65208785ee6eb61e9b72f14c7d16` |
| `tools/read-infra-tool-version.py` | `d94d97d605736d0201d0fc0517e0e780d6c346ab79ddc3bd84de7b472edeccd8` |
| `infra/ansible/tests/test_a101_readiness_root.py` | `5d55c30b8d3b92de9bad435de8348318fad2d4d0b7c029dab88bee87f1350eb7` |

The production helper and replacement operator remain byte-identical at
`5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba`
and
`27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e`.

## Root focused tests and installed mutations

All 3 root tests, all 7 readiness tests, all 27 spend tests, and the independent
spend checker pass. The root tests mutate each of the 15 bound sources one at a
time and require each mutation to fail, inject executable shell content into
the version-data file and prove no command runs, and demonstrate that a
preceding module's `hashlib` replacement does not survive into the fresh
readiness process.

Four additional installed mutation worktrees at exact technical commit
`30615e8` produced these results:

| Finding | Installed mutation | Observed binding |
| --- | --- | --- |
| A1 | state-oracle override in `infra/tofu.sh` | root checker exited 1 on the exact `tofu.sh` identity |
| A2 | issuance-module `hashlib` poison plus alternate helper client | root checker exited 1 before discovery on the helper identity |
| A3 | altered a root-checker digest constant | workflow literal SHA-256 failed before execution; direct execution also rejected its missing workflow pin |
| A5 | shell functions for Python, ShellCheck, lint, and syntax tools in the version file | inert parser exited 1, the marker remained absent, and the root checker rejected the data identity |

All mutation worktrees were removed and pruned. No mutation invoked a real
network client or opened a socket.

## Root repair infrastructure and Ansible gates

The infrastructure wrapper passes the workflow-root checker first, initializes
and validates all three OpenTofu roots, and passes stack, independence,
worker-runtime, worker-qualification, and the independently launched spend
checker. It then stops on only the disclosed stale issuance host contract:

```text
live    bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f
current eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977
```

The redesigned Ansible wrapper runs 152 tests across 14 isolated modules. The
3 root, 7 readiness, 27 spend, and 95 other non-issuance tests pass. Nineteen
of twenty issuance tests pass; only the same stale host-contract assertion
fails. Despite that failure, all four production lint profiles pass with zero
failures and zero warnings, all four syntax checks pass, and the terminal root
recheck passes. The wrapper returns nonzero for the retained stale failure.

All 13 `credential_qualified` flags remain false. No credential, provider
request, host, worker, firewall, Console setting, requirement-1 evidence,
acceptance case, requirement-3 artifact, rotation state, or qualification flag
changed.

## Root repair application gate

The first application-wrapper invocation passed all 39 browser-control tests
with the one Docker-only skip, then exited 127 because the invoking shell did
not include `/var/lib/conductor/.cargo/bin` in `PATH`. No source test failed and
no repair followed. Repeating the same clean record commit with the established
repository gate path passed the complete wrapper:

- all browser-control, Rust formatting, Clippy, unit, integration, property,
  fixture, database-contract, documentation, and triage-replay tests pass;
- both clean release builds reproduce `factory-verify` SHA-256
  `99e3d1da120848b5cb4198788504404bea2e2c178316f301c603a987e8795bae`;
- checksum install and rollback pass;
- the 1,175-record RustSec scan, cargo-deny advisory, ban, license and source
  checks, cargo-vet, and cargo-machete pass;
- cargo-vet reports `Vetting Succeeded (321 exempted)`; and
- model schema, Mermaid projection, model tests, and the byte-identical
  codebase-metrics projection pass.

## Root repair A78 handoff

A78 must review the exact final record commit identified in the PR handoff in a
new detached worktree. It must verify the workflow literal matches the root
checker, the bound execution closure is complete for the reported findings,
all 14 modules run in fresh processes, the independent spend checker precedes
the stale issuance boundary, and tool-version content cannot execute. It must
run all 3 root, 7 readiness, and 27 spend tests and reproduce at least the four
installed A1/A2/A3/A5 mutation classes.

A78 should attempt source-only attacks against the workflow pin, root checker,
test census and ordering, transitive state oracle, aggregate gate status, and
inert pin parser. Review authorizes no network, host, worker, DigitalOcean,
Anthropic, Console, requirement-1 refresh, acceptance, requirement-3,
rotation, or qualification-flag action.

## Root repair A78 result

A78 reviewed exact final record commit
`ba109ee433956bf81070ae787f43fb0159795f3f` in a fresh detached worktree and
returned NOT A PASS:

1. Critical: an uncensused `tools/hashlib.py` shadows the standard library for
   both checker scripts, allowing an exact helper mutation to appear pinned
   while the workflow checker checksum remains valid;
2. High: uncensused package initializers execute inside every nominally
   isolated test process, and eleven module sources are bound by filename but
   not content;
3. High: the stale `check-infra.sh` step fails before GitHub reaches the newly
   aggregating Ansible step, so CI skips the repaired wrapper;
4. Medium: six checker scripts executed by the wrappers remain outside the
   root source identities; and
5. Medium as reported: `tofu.sh` has only the workflow-rooted binder, while
   the helper and operator retain three.

A78 also verified that isolated Python mode exposes the forged helper, inert
tool-version parsing is repaired, the Ansible wrapper aggregates honestly when
invoked, spend precedes issuance there, census add/remove cases fail, and the
three production identities remain unchanged. The exact review is
`2026-07-31-a78-a101-firewall-readiness-root-review.md`.

## Root repair A77 disposition

The build seat independently conceded F1 at Critical, F2 and F3 at High, and
F4 at Medium. A77 conceded F5's factual one-binder count but refuted separate
materiality: the sole externally rooted binder rejects a normal `tofu.sh`
mutation, and F1 is the attack that collapses it.

Independent experiments reproduced:

- an actual guarded alternate-client helper mutation that both checker scripts
  accepted through a `tools/hashlib.py` shim, while `python3 -I` rejected its
  real digest;
- an uncensused package initializer that executed in a censused test process;
- a trivial one-case issuance module that kept the filename census green;
- the workflow's skipped next step after the real stale infrastructure result;
- an unbound passing issuance checker accepted by both bound checkers; and
- a `tofu.sh` mutation rejected by the root checker while the spend and
  readiness suites stayed green.

The exact adjudication is
`2026-07-31-a77-a101-firewall-readiness-root-review-adjudication.md`.

## Root repair A9 stop

No further source repair was made. The new A78 review completed the authorized
loop and failed, so A9 requires this stop. Further work requires a new explicit
bounded authorization under A115 for isolated Python execution and provenance,
complete test/checker content binding, import-path census, workflow continuation
with final failure preservation, focused mutation checks, full gates, and a
new clean A78 review.

No new numbered ruling should record that operational grant. No live system,
worker, provider, credential, Console limit, requirement-1 evidence,
acceptance case, requirement-3 artifact, rotation state, or qualification flag
changed.

## Isolated Python and workflow-continuation authorization

Jacob explicitly authorized the next bounded repair after the A77 stop. The
grant covers isolated Python execution and standard-library provenance, a
pinned isolated test runner, exact content binding for all 14 Ansible test
files and the six previously unbound checker scripts, rejection of unexpected
import-path Python sources, workflow continuation with retained final failure,
F1-F4 source mutations, the full repository gates, and a new A78 review.

The grant is recorded under A115 and does not mint a new ruling or reuse A119.
It authorizes no live worker, host, DigitalOcean, Anthropic, Console,
requirement-1 refresh, acceptance case, requirement-3 work, rotation, or
qualification-flag action.

## Isolated Python and workflow-continuation repair

Exact technical commit `4402577064e0ba1055e7603fea6da4e6fb3b98d1`
closes the conceded F1-F4 paths:

- the workflow, infrastructure wrapper, Ansible wrapper, ShellCheck installer,
  and live qualifier invoke every Python gate in this boundary with
  `python3 -I`;
- the workflow-rooted checker, spend checker, and new unittest runner refuse
  non-isolated execution, require their security-sensitive imports to resolve
  beneath the interpreter's standard-library directory, and reject a
  repository path in `sys.path`;
- `tools/run-isolated-unittest.py` accepts only the 14 exact test file paths
  and loads one file per process under a synthetic non-package module name;
- the root checker exact-digest binds 33 execution-closure sources, including
  all 14 test files, all seven infrastructure checker files, both wrappers,
  the runner, pin parser and data, production entry points, and readiness
  sources;
- the root checker requires the complete `infra/**/*.py` census, rejects every
  repository `__init__.py`, rejects protected standard-library and dependency
  shadow filenames, and refuses symlinked bound sources;
- `tools/check-infra.sh` aggregates all seven static checkers, so the retained
  issuance failure no longer hides the later preview check, while returning
  nonzero if any checker failed; and
- the workflow gives the Ansible step the exact `if: ${{ always() }}`
  continuation property. The preceding infrastructure step has no
  `continue-on-error`, so its failure remains the job's final failure.

Final source identities at that commit are:

| File | SHA-256 |
| --- | --- |
| `tools/check-a101-readiness-root.py` | `fb0a3ee170c72f7e798b09ce5d67c8aba6d0bfd7eac9583ab32522f5177fb0b4` |
| `tools/run-isolated-unittest.py` | `9291cee8008ce693ad0c891271450606d5f547e4be0821867ac81b95d7d6572f` |
| `tools/check-ansible.sh` | `f702dd84863bbc1973edbb41f21c95d8467cf703d6174e277418c44d92bf2d29` |
| `tools/check-infra.sh` | `61ec9e3485ce0933ce7a5a74a81512e8438f6d8a4e00a2d018369e18a827c265` |
| `tools/check-anthropic-spend.py` | `8c31bb1e3a1f350a4641a180642c4c43a6de0c2359ec54aad7e76c9a69767a1c` |
| `infra/ansible/tests/test_a101_readiness_root.py` | `2f3ad2be6e2d1c5793064cb307ab7adeac7233e10e22dbdf54cd53402730fde4` |

The production readiness helper and replacement operator remain byte-identical
at
`5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba`
and
`27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e`.
All 13 `credential_qualified` flags remain false.

## Isolated repair focused tests and mutations

All 7 root tests, all 7 readiness tests, all 27 spend tests, and the independent
spend checker pass. The root suite mutates each of the 33 bound sources and
requires every mutation to fail. It also proves directly that:

- the root checker, test runner, and spend checker refuse ordinary Python;
- a repository `hashlib.py` cannot conceal a real helper mutation;
- package initializers neither execute through the runner nor survive the
  source census;
- a `hashlib` poison cannot survive into a second test process;
- removing workflow continuation fails the root checker; and
- executable content in the tool-version data file remains inert.

Four detached mutation worktrees at exact technical commit `4402577` installed
the conceded attacks rather than merely calling unit helpers:

| Finding | Installed mutation | Exact result |
| --- | --- | --- |
| F1 | guarded alternate provider client plus `tools/hashlib.py` mapping real mutant digest `9a9cb515d41233986b58bc78c8b6148e9f7c431e013ae7e3d9c37940481812c7` to the pinned helper digest | ordinary root and spend checkers failed isolation/provenance; isolated root exposed the real digest and rejected the protected shadow |
| F2 | executable `infra/ansible/tests/__init__.py` plus a one-case passing issuance test | the file runner ran the one case without executing the initializer, while the root rejected both the initializer and changed test digest |
| F3 | removed `if: ${{ always() }}` from the Ansible workflow step | root exited 1 with `Ansible step does not run after infrastructure failure` |
| F4 | replaced the issuance checker with a two-line passing program | the forged checker exited 0 and the root exited 1 on its exact source identity |

All four mutation assertions returned success only when the attacked gate
returned nonzero. Their worktrees were removed and pruned. No mutation invoked
a real network client or opened a socket.

## Isolated repair infrastructure and Ansible gates

At exact technical commit `4402577`, the infrastructure wrapper passed the
workflow root, all three OpenTofu initializations and validations, stack,
independence, worker runtime, worker qualification, and the spend checker. The
known requirement-1 issuance fixture then failed on only its disclosed stale
host contract. The new aggregate wrapper continued, preview runtime passed,
and the wrapper returned 1.

The Ansible wrapper ran all 156 tests in 14 independent isolated processes.
It passed 155: all 7 root, 7 readiness, 27 spend, 95 other non-issuance, and 19
of 20 issuance tests. The only failure was the same stale requirement-1 host
contract. All four Ansible lint profiles then passed with zero failures and
zero warnings; all four syntax checks passed; the final isolated trust-root
check passed; and the wrapper returned 1 for the retained failure.

## Isolated repair application gate

The first full application invocation passed all 39 browser-control tests with
the one Docker-only skip, then exited 127 because the invoking shell lacked the
installed `/var/lib/conductor/.cargo/bin` directory in `PATH`. The same clean
commit was rerun with that established tool path. Every substantive gate
passed: formatting, Clippy, all Rust tests, triage replay, two clean
reproducible builds, checksum install/rollback, the 1,175-record RustSec scan,
cargo-deny, cargo-vet, cargo-machete, and model validation/tests.
`factory-verify` reproduced SHA-256
`99e3d1da120848b5cb4198788504404bea2e2c178316f301c603a987e8795bae`,
and cargo-vet reported `Vetting Succeeded (321 exempted)`.

That invocation reached only the expected final deterministic projection drift
caused by the added Python runner, checks, tests, and this work record. After
regenerating and committing that projection, the complete application wrapper
was rerun at exact clean record commit
`155b2684bff7c3b12238154ef5724967675c0a79`. It returned 0. The same substantive
results above passed again, including reproducible `factory-verify` SHA-256
`99e3d1da120848b5cb4198788504404bea2e2c178316f301c603a987e8795bae`,
`Vetting Succeeded (321 exempted)`, all 10 model tests, and the byte-identical
codebase-metrics projection.

## Isolated repair A78 handoff

A78 must review the exact final record head identified in the PR handoff from
a new detached worktree. It must independently test the F1-F4 attacks, verify
the complete 33-source binding and import-path closure, prove the file runner
does not import package initializers, and confirm the workflow runs Ansible
after the retained infrastructure failure without masking that failure.

The review may run repository source/tests only. It authorizes no network,
live host, worker, DigitalOcean, Anthropic, Console, requirement-1 refresh,
acceptance, requirement-3, rotation, or qualification-flag action.

## Isolated repair A78 result

A78 reviewed exact final record commit
`a0bd964d2c8b9690af5b257fe14617096b3eb612` in a fresh detached worktree and
returned NOT A PASS with one High and two Medium material findings:

1. High: an unchecked-hash `.pyc` at a normal test cache path replaces the
   content executed by `spec_from_file_location` while every bound `.py` digest
   and both isolated checkers remain green;
2. Medium: three independent workflow failure-masking mutations preserve the
   root checker's asserted fragments; and
3. Medium: three repository sources execute at test-module import time but are
   outside both the exact source identities and relevant census.

A78 confirmed that prior F1 standard-library shadowing and F4 unbound checker
sources are closed, package initializers are rejected, the current workflow
continuation and wrapper aggregation work, and the repair's numeric and gate
claims are accurate. The exact review is
`2026-07-31-a78-a101-isolated-python-review.md`.

## Isolated repair A77 disposition

The build seat independently conceded all three findings with A78's severities
sustained. The exact adjudication is
`2026-07-31-a77-a101-isolated-python-review-adjudication.md`.

A77 reproduced:

- a force-addable unchecked-hash bytecode artifact that changed the unchanged
  issuance module from 20 tests with one honest failure to one forged passing
  test while the root and spend checkers exited 0;
- `tools/check-infra.sh || true`, job-level `continue-on-error: true`, and
  Ansible-step `continue-on-error: true`, each independently accepted by the
  root checker; and
- an import-time mutation in unbound `anthropic-spend-evidence.py` that made a
  changed readiness digest pass the nominally independent 27-test spend suite,
  while the poison alone remained invisible to both separate checkers.

## Isolated repair A9 stop

No further source repair was made. The authorized repair completed its A78
loop and failed, so A9 requires this stop. Further work requires a new explicit
bounded authorization under A115 to prevent bytecode-cache execution, bind and
census the three import-executed sources, bind exact workflow non-masking, add
the reproduced source attacks, run the full gates, and obtain a new A78 review.

No new numbered ruling should record that operational grant. No live system,
worker, provider, credential, Console limit, requirement-1 evidence,
acceptance case, requirement-3 artifact, rotation state, or qualification flag
changed.

## Isolated execution-closure repair authorization

Jacob explicitly authorized one new bounded source-only sequence at the merged
PR head. The source boundary is limited to closing the three conceded findings
above before returning the result to A78. This is a new authorization after the
recorded A9 stop, not an unrecorded continuation of the exhausted loop.

The same grant separately authorizes planning a fresh replacement and disposal
of quarantined worker `588858421`, but only after this source review. It grants
no apply. This section records only the source work and changes no worker,
firewall, plan, credential, provider, Console value, requirement-1 fixture,
acceptance case, requirement-3 artifact, rotation state, or qualification flag.

## Isolated execution-closure source repair

The production readiness helper, replacement operator, and A101 qualifier are
byte-identical to the previously reviewed candidate. The repair changes only
the proof boundary:

1. the isolated test runner redirects bytecode lookups to a fresh private
   temporary cache and compiles the exact opened test source, so a repository
   `.pyc` cannot replace the executed test content;
2. the three import-executed sources are exact-digest bound by the independent
   trust root and by their consuming test modules, which compile their exact
   opened bytes rather than using import loaders;
3. the trust root carries an explicit `tools/*.py` census, so a new executable
   tools source cannot enter the test closure unnoticed; and
4. the complete infrastructure workflow is exact-template bound, including the
   trust-root block, job controls, infrastructure command, and continuing
   Ansible step.

## Focused gates and installed mutations

The repaired baseline passed:

- 11 isolated A101 trust-root tests;
- 7 worker-firewall readiness tests;
- 27 Anthropic spend contract tests;
- all 3 WIF-admin and both log-scanner tests;
- the independent A101 root and Anthropic spend checkers; and
- Bash syntax plus `git diff --check`.

The new tests install the former unchecked-hash bytecode attack: a conventional
cache-path `.pyc` contains a forged passing test while the exact source contains
a failing test. The runner returns 1 on `exact source executed`, and the forged
module's marker remains absent. They also install and reject seven workflow
masking variants: infrastructure `|| true`; job-level `continue-on-error`,
`if: false`, and a masking default shell; Ansible-step `continue-on-error`;
Ansible `|| true`; and trust-root `|| true`.
Each of the three import-executed sources is separately mutated and refused
before its changed bytes execute, and a new `tools/unbound-executable.py` is
rejected by the census.

The production readiness mutation harness was rerun. In-memory source mutation
`.status == "succeeded"` to `.status != "succeeded"` failed on the exact
settled-status binding, and `MAX_ATTEMPTS=24` to `MAX_ATTEMPTS=240` failed on
the exact bounded-attempt binding. Neither weakening survived the suite.

## Isolated execution-closure A78 handoff

A78 must review the exact pushed head named in the PR handoff from a new
detached worktree. It should independently reproduce the unchecked-hash
bytecode, workflow-masking, import-source mutation, and tools-census attacks;
verify the complete execution closure and exact command scalars; run the 11
root, 7 readiness, and 27 spend tests plus the independent checkers; and return
PASS or material findings.

Review authorizes source inspection and local disposable mutations only. It
authorizes no network, live host, worker, DigitalOcean, Anthropic, Console,
requirement-1 refresh, acceptance, requirement-3, rotation, or
qualification-flag action.
