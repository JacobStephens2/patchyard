# A115 A101 firewall-readiness repair attempt

Status: **source candidate written; one repair loop consumed; focused test
harness still fails; A9 stop and escalation**

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
