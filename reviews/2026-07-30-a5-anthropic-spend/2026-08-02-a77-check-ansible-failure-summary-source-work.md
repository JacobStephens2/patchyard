# A77 check-ansible failure summary - source work record

Date: 2026-08-02

Status: source complete; awaiting A78 adversarial review; no operational action
authorized

Base: `60b80a6e89ad5e58eb97f2878d1fad18e68f5d85`

## Jacob's decision and A77 dispositions

Jacob directed the build seat to proceed with Target 1 only and record Target
2 as refuted.

- **Target 1 - concede and repair.** `tools/check-ansible.sh` retained the
  correct aggregate exit status, but a failed early gate could be followed by
  many passing gates with no failure identity at the end of the log.
- **Target 2 - refute with evidence.** The claimed decorative rootfs digest is
  not a defect. The launcher binds the runtime observation to the computed
  rootfs digest before publication, while the tracked contract deliberately
  does not ask CI to recompute non-reproducible ext4 bytes.

No finding remains escalated.

## Target 1 result

`run_gate` now retains the shell-escaped command for each failed aggregate
gate. After the existing terminal A101 readiness recheck, a failing run prints
the retained commands in failure order under `Failed Ansible gates:` and then
exits with the unchanged aggregate status.

Every gate invocation, gate order, command argument, strictness rule, and
terminal `exit "$gate_status"` remains unchanged. A passing run never enters
the new reporting branch and emits no additional bytes.

The focused regression executes the exact `gate_status`/`run_gate` block and
the exact production footer from `tools/check-ansible.sh`. It proves both that
an early failure is named after a later passing gate and that a passing
aggregate emits exactly its two simulated gate lines with no summary bytes.

## Old/new mutation evidence

One simulated unit-test gate was forced to fail, followed by passing lint and
syntax gates. The `origin/master` aggregate returned 1 and ended in passing
output with no retained failure identity:

```text
OLD forced-failure exit=1
test_anthropic_spend: FAIL
ansible-lint rollback-boundary.yml: pass
playbook: rollback-boundary.yml
```

The repaired aggregate returned the same exit status and ended by naming the
failed gate:

```text
NEW forced-failure exit=1
test_anthropic_spend: FAIL
ansible-lint rollback-boundary.yml: pass
playbook: rollback-boundary.yml
Failed Ansible gates:
  failing_unit_test
```

The same all-pass aggregate was run against both sources. The outputs were
byte-identical, with SHA-256
`4b0edd34bc125d5d7332fe14dfc84ccf14636250ab71e5738c331c41c73a7cea`:

```text
first gate: pass
final gate: pass
```

Running only
`test_failure_tail_names_gate_after_later_passes` against the
`origin/master` wrapper failed as required: master returned only
`unit test: fail` and `playbook: rollback-boundary.yml` where the regression
expected the terminal failure header and `failing_unit_test`. The same test
passes against the repaired wrapper.

## Complete source-binding re-pin

The change preserves the complete-source trust chain rather than weakening a
checker to accept stale bytes:

| Source | Reviewed SHA-256 |
| --- | --- |
| `tools/check-ansible.sh` | `68c32d300bdd2884d8e106a947fe6595231b3ddd4dd976f2cf7360b1c4572bab` |
| `infra/ansible/tests/test_worker_firewall_readiness.py` | `4c23f6e35b8a5fa7eeaae07d35b80862270b59acc24729c67d0d43f3e43bf866` |
| `tools/check-anthropic-spend.py` | `68b86bf24b979422eedbb3b21fc33fb9f99682bcc6d8dd842576c7ecd143d424` |
| `infra/ansible/tests/test_anthropic_spend.py` | `022faa5fc2ce8c0b1943b662296033777f4697f8a0cf8507f826c719cab76f84` |
| `tools/check-a101-readiness-root.py` | `aba26d07f37b056ae9a1019c57fa64bda3cbc81534402510ddc36c18e7670eff` |

`tools/check-anthropic-spend.py` binds the changed wrapper and readiness test.
Its focused test binds the checker, wrapper, and readiness test. The A101
readiness root binds all four changed executable/test sources, and
`.github/workflows/infrastructure.yml` pins the resulting A101 root digest.
Both direct source checkers and the terminal workflow-rooted check pass.

## Target 2 refutation

`worker/runtime/patchyard-firecracker-run` line 767 passes the launcher's
computed `ROOTFS_SHA256` into the result-evidence check. Line 777 then requires
`.observed_rootfs_sha256 == $rootfs_sha256` before evidence publication and
line 778 rejects the reproducible-source field in this runtime-observation
branch.

The tracked contract in `docs/anthropic-issuance.md` lines 31-36 explains why:
ext4 rootfs bytes include non-reproducible filesystem identity and metadata,
so `observed_rootfs_sha256` is explicitly a runtime observation. The worker
verifies it against the exact rootfs bytes before launch and again before
publication. CI has no rootfs bytes to hash and therefore validates the field's
contract shape without pretending it is a CI-recomputable source binding.

The checker accepting a fabricated but well-formed runtime observation in a CI
mutation is therefore by design. The original **"decorative digest" finding
was incorrect**. A78 independently verified the launcher binding and contract
classification. This work makes no rootfs evidence-contract, checker-semantic,
or fixture change, so the same incorrect mutation should not be proposed as a
repair later.

## Gate results

The completed source ran through the full repository gate set:

- `tools/check-infra.sh` returned zero after validating all three OpenTofu
  roots plus the stack, independence, worker runtime, worker qualification,
  Anthropic spend, Anthropic issuance, and preview contracts.
- `tools/check-ansible.sh` returned zero with task-scoped writable Ansible
  cache paths. All 174 isolated tests passed, including the two new aggregate
  reporting tests. All four production lint profiles, four playbook syntax
  checks, and both A101 trust-root checks passed.
- `tools/check-application.sh` returned zero with the documented Rust tools and
  task-scoped writable Cargo/XDG caches. The preview suite, Rust format,
  clippy, unit/integration/property tests, replay, reproducible release,
  checksum install/rollback, advisory, deny, vet, machete, model, and
  byte-exact codebase-metrics gates passed. The one Docker-only Traefik test
  used its declared local skip.

The initial unsandboxed Ansible and Cargo invocations also provided real
failure-footer evidence. Their failures were limited to read-only tool cache
paths; after relocating those caches under `/tmp`, the unchanged gates passed.

## Negative-scope attestation

The live Anthropic spend procedure remains exactly where it began: phase 1 has
valid evidence, and phase 2 is waiting on Cost Report settlement. This work
made no provider request, issued no credential, performed no paid inference,
changed no Console limit, applied no infrastructure, converged no host,
mutated no worker, refreshed no fixture, performed no behavioral acceptance,
and started no requirement-3 work.

The issuance runner, Firecracker launcher, one-shot transport, guest image,
evidence semantics, and fixtures are byte-identical to the base. No bare
`ANTHROPIC_API_KEY` or long-lived key was introduced. All 13
`credential_qualified` values remain false.
