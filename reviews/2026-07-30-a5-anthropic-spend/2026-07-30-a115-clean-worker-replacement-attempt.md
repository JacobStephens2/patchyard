# A115 clean-worker replacement attempt

Status: **replacement failed; stopped under A9; no provider request**

This is the requirement-2 operational record for Jacob's explicit
authorization of the reviewed plan, worker replacement, and a provider request
only if later prerequisites made one useful. It is an operational grant under
A115, not a new decision-log ruling. A119 remains reserved for the merged
reviewer-seat reassignment.

## Reviewed boundary

| Field | Value |
| --- | --- |
| plan generated from | `c65ac0e28cbf994055f7f5a2948eac23e0b5e2ab` |
| repaired apply source | `6c161e91ea0107f6c9d8bb9dac4eb88a27450213` |
| saved binary plan SHA-256 | `b7d842ffc57702a16726b5413fd29bea4ba93202ce2a993351a67e07b5f29490` |
| rendered plan SHA-256 | `d4dedabc603d0770c2995fb90b0ceb2f4bda6c8326e8622cde913262dfb2e561` |
| A78 verdict after one repair | PASS |
| old worker | `588590370`, public `167.71.81.211`, private `10.132.0.15` |
| old worker disposition | `BOUNDARY_TAINTED`, destroyed, never reused |
| pre-apply work state | `paused=0,full_stop=0,active=0`; backup service inactive |
| cap/provider state | no cap action and no provider request |

The plan and both secret input files were owner-only. `converge.sh
--check-inputs` returned `converge_inputs_valid` before apply. The apply command
provided the exact plan SHA-256, exact reviewed source revision, literal human
approval, and the explicit A115 unmerged-source flag.

## Cloud apply

OpenTofu completed the exact reviewed plan:

- created worker `588761785` at `64.225.18.250` / `10.132.0.11`;
- updated firewall `01af87da-4951-4441-a1c8-ddfc0214811b` to that worker;
- destroyed quarantined worker `588590370`;
- reported `1 added, 1 changed, 1 destroyed`.

The post-failure state read at `2026-07-30T16:30:13Z` contains only worker
`588761785` in the worker resource and firewall attachment. The control-plane
droplet remains `586468414` and active.

## Fail-closed convergence

The first converge failed its immutable-image gate on the new worker:

```text
TASK [Wait for cloud-init to release package management]
fatal: [factory-worker.example.com]: FAILED!
cmd: ["cloud-init", "status", "--wait"]
rc: 1
stdout: "status: error"
```

The worker's cloud-init record identifies the exact failure:

```text
Command: ['dnf', '-y', 'install', 'firewalld', 'python3', 'sudo']
Problem: installed python-unversioned-command-3.9.25-7.el9_8 requires
python3 = 3.9.25-7.el9_8, but BaseOS also selects
python3-3.9.25-7.el9_8.2 and cannot install both.
Failed to enable unit: Unit file firewalld.service does not exist.
```

Read-only package projection confirmed:

```text
firewalld-1.3.4-18.el9_7.noarch                    baseos
python3-3.9.25-7.el9_8.x86_64                     baseos
python3-3.9.25-7.el9_8.2.x86_64                   baseos
python-unversioned-command-3.9.25-7.el9_8.noarch  appstream
```

The new worker has `cloud-init=error`, failed `cloud-final`, no installed
`firewalld`, no `/var/lib/patchyard-worker`, no `BOUNDARY_TAINTED`, and zero
files matching the bounded credential/Anthropic/bearer scan. It is not cleanly
provisioned or qualified and is ineligible for Factory work.

Ansible safely excluded the failed worker and finished the control-plane play:

```text
factory-control.example.com : ok=221 changed=19 failed=0
factory-worker.example.com  : ok=1   changed=0  failed=1
wrapper exit status: 2
```

The control plane now has clean checkout revision `6c161e9`, active PostgreSQL,
dashboard, supervisor, Caddy, and backup timer, zero active work, and public
health `ok`. Its changed items include the reviewed Anthropic binding and
runner, worker inventory/address, runtime operators, checkout revision, and
normalization of two July 30 artifact trees. The second converge, host
qualification, production isolation probe, post-probe qualification, and every
Anthropic phase did not run.

## A9 stop

The plan-wrapper review consumed the one bounded repair and then passed A78.
The subsequent live replacement exposed this different base-image/repository
failure. No manual package installation, `--nobest`, distro-sync, cloud-init
rerun, worker reuse, replacement retry, cap change, provider request,
credential issuance, fixture finalization, requirement-3 work, behavioral
acceptance, or qualification-flag change was attempted.

Further work requires a new bounded authorization. A repair would need to make
the immutable bootstrap tolerate the Rocky image's temporarily split Python
package versions, bind that behavior with tests and mutation checks, receive
A78 review, and replace the failed worker from a newly reviewed plan. Reusing
worker `588761785` is not proposed.
