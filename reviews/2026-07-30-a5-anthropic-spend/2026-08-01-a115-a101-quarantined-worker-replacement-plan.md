# A115 post-A101 quarantined-worker replacement plan

Status: **one saved replacement plan produced and mechanically verified;
awaiting A78 review; not applied**

Jacob authorized planning only after A78 passed the A101 readiness repair at
exact PR head `c03a32fc6541378a85bb4adfebdae07276706713`. The repair bounds
the private-SSH readiness probe to five attempts and 45 seconds, fails closed
on exhaustion, preserves the exact `factory-manager` identity assertion, and
emits one result line for every attempt. A78's PASS is recorded in
[PR #79 comment 5149007414](https://github.com/JacobStephens2/patchyard/pull/79#issuecomment-5149007414).

This operational grant is recorded under A115 and does not mint a new numbered
ruling. It authorizes one saved plan that creates a fresh worker and retires
quarantined worker `589089036` through one create-before-destroy replacement.
Applying it requires a separate explicit `AUTHORIZE APPLY` from Jacob against
the exact binary SHA-256 below.

## Exact source and saved artifacts

| Field | Value |
| --- | --- |
| operational plan source | `c03a32fc6541378a85bb4adfebdae07276706713` |
| `origin/master` at planning | `43303c95b217f4da9f097d5ab4367bf52d3b0218` |
| A101 A78 verdict | PASS, correct and complete, no finding |
| saved binary plan | `/tmp/patchyard-replace-a115-a101.ZUTbIb/worker-replacement.tfplan` |
| saved binary SHA-256 | `02073c1c7955ffb343b0a1ba677832ca141da0e697a618cee9b75823fd4b72ab` |
| rendered plan | `/tmp/patchyard-replace-a115-a101.ZUTbIb/worker-replacement.tfplan.txt` |
| rendered-plan SHA-256 | `d0a98a9410c76183ece2a2d54681e94918e9cb01a6e8fef0d057c7210a3896c7` |
| binary plan timestamp | `2026-08-01T04:10:50Z` |
| binary file completion | `2026-08-01T04:10:52.065426122Z` |
| rendered file completion | `2026-08-01T04:11:11.610655078Z` |
| directory mode | `conductor:conductor 0700` |
| both plan-file modes | `conductor:conductor 0600` |

The source checkout was committed and clean. There were no unprocessed ruling
files, and all 13 provider `credential_qualified` values were false. The
operator invoked exactly:

```text
infra/replace-worker.sh plan /tmp/patchyard-replace-a115-a101.ZUTbIb
```

The wrapper passed the production tag-firewall guard, initialized the
DigitalOcean root, refreshed encrypted remote state, generated one saved
`-replace=digitalocean_droplet.worker` binary, and created the rendered file
only after `verify_worker_plan` accepted that binary. No second saved plan was
generated.

The Codex command relay released the wrapper session after the final render
completed but before its two hash lines were returned. The operator did not
rerun the plan mode. A read-only render of the same binary reproduced the
saved rendered-plan SHA-256 exactly, and the strict projection below accepted
the same binary.

## Pre-plan bracket

The complete read-only provider bracket ran from `2026-08-01T04:09:13Z`
through `2026-08-01T04:09:25Z`. A normal no-replacement OpenTofu plan then
returned detailed exit code 0 with:

```text
No changes. Your infrastructure matches the configuration.
```

The bracket established:

- Git was clean at exact source `c03a32f`; `git status --porcelain` returned
  zero entries.
- OpenTofu desired state was clean. The prior encrypted snapshot still carried
  the worker firewall's historical computed `waiting` metadata, while the live
  provider reported that same firewall `succeeded` with zero pending changes.
  The saved plan records this settled refresh on the same firewall, and its
  refreshed after-side is exactly the planned attachment update's before-side.
- State and the live provider both identified worker `589089036` as active in
  `nyc3`, size `s-8vcpu-16gb`, stock image `rockylinux-9-x64`, at public
  `167.172.239.1` and private `10.132.0.11`.
- Worker firewall `01af87da-4951-4441-a1c8-ddfc0214811b` had no tags, had zero
  live pending changes, and attached only worker `589089036`.
- The production tag-firewall guard passed. The production-tag Factory subset
  contained only active control plane `586468414` and worker `589089036`.
- The DigitalOcean account was `active`, with 19 of 500 droplet slots in use.
- Public base image `rockylinux-9-x64`, image ID `234045074`, reported
  `available` and included `nyc3` in its regions.
- Size `s-8vcpu-16gb` reported `available` and included `nyc3` in its regions.

These are time-bounded planning facts. A separately authorized apply must
sample its complete pre-apply bracket again. Worker `589089036` remains
quarantined and ineligible for repair or reuse.

## Exact old and new addresses

| Plan address | Action | Old | New |
| --- | --- | --- | --- |
| `digitalocean_droplet.worker` | `["create","delete"]` | ID `589089036`; public `167.172.239.1`; private `10.132.0.11` | ID, public address, and private address all `(known after apply)` |
| `digitalocean_firewall.worker` | `["update"]` | firewall `01af87da-4951-4441-a1c8-ddfc0214811b`; `droplet_ids=[589089036]` | same firewall; replacement droplet ID `(known after apply)` |
| output `worker_ipv4` | update | `167.172.239.1` | `(known after apply)` |
| output `worker_private_ipv4` | update | `10.132.0.11` | `(known after apply)` |
| output `ansible_inventory` worker host | update | public `167.172.239.1`; private `10.132.0.11` | both `(known after apply)` |

The plan allocates no successor address before apply. The worker action is
ordered create-before-destroy and has action reason `replace_by_request`. It
creates the declared stock Rocky Linux 9 worker in `nyc3` at size
`s-8vcpu-16gb`, with backups and IPv6 disabled, no configured volume, no
snapshot restore, and no old-host state transfer.

## Mechanical plan projection

The encrypted binary has nine resource changes. Seven are exact no-ops.
Exactly two act:

1. `digitalocean_droplet.worker` is replaced by request with ordered actions
   `["create","delete"]`, retiring current state target `589089036`.
2. `digitalocean_firewall.worker` is updated in place only to replace its
   worker attachment.

The rendered summary is exactly:

```text
Plan: 1 to add, 1 to change, 1 to destroy.
```

The seven no-op resources are the control-plane droplet and firewall, backup
bucket, both Spaces keys, management SSH key, and backup recovery key. No
restore-drill resource exists. Only `ansible_inventory`, `worker_ipv4`, and
`worker_private_ipv4` change among the outputs. The old worker ID and addresses
are exact; every successor ID and address is explicitly unknown until apply.

The sole `resource_drift` entry reconciles
`digitalocean_firewall.worker` from historical `waiting` metadata to the live
`succeeded`, zero-pending state. Its refreshed result is exactly the planned
change's before-side. This is not a third acting resource. A strict independent
projection required all facts above and rejected any other acting resource,
action, output, old identity, or allocated successor address.

## What the eventual apply must record

The A101 repair makes the next replacement a direct experiment. A separately
authorized apply record must quote every emitted per-attempt line verbatim.
The attempt-level detail is the result and must not be collapsed into
"A101 passed" or "A101 failed."

- A line containing `attempt=1/5 outcome=pass` means the three historical
  stops had a different cause. The slow-first-connection hypothesis is
  excluded.
- A line containing `attempt=1/5 outcome=ssh-failed`, followed by a later line
  containing `outcome=pass`, confirms slow first connection with its measured
  attempt and total latency. The bounded retry already fixes that case.
- Five failed-attempt lines followed by a line containing
  `outcome=exhausted attempts=5` exclude the slow-first-connection hypothesis
  and preserve clean failure evidence.

The emitted lines include target, attempt number, outcome, attempt elapsed
seconds, total elapsed seconds, and SSH status. The eventual record must copy
the complete lines exactly, including those fields and any bounded detail
line, rather than quoting only the fragments above.

## Negative scope and stop boundary

No apply command ran. A read-only provider check at `2026-08-01T04:13:19Z`
still reported worker `589089036` active at public `167.172.239.1` and private
`10.132.0.11`; its firewall remained `succeeded`, zero-pending, and attached
only to `589089036`. No worker, firewall, host, provider, Console value,
credential, fixture, or qualification state changed. In particular:

- no Anthropic credential was issued and no provider request or paid
  inference occurred;
- neither Anthropic limit changed;
- the deliberately stale requirement-1 fixture was not refreshed;
- requirement 3 and behavioral acceptance did not start;
- no credential was rotated; and
- all 13 provider `credential_qualified` values remain false.

The binary is review-only. Do not run `infra/replace-worker.sh apply` without a
new explicit `AUTHORIZE APPLY` naming binary SHA-256
`02073c1c7955ffb343b0a1ba677832ca141da0e697a618cee9b75823fd4b72ab`.

## Full repository gates

The complete application wrapper returned 0 at the final plan-record head.
All browser-control, Rust unit, integration, property, fixture, documentation,
triage replay, reproducible release, advisory, license, source, vet,
dependency, model, and byte-exact codebase-projection checks passed.

The complete infrastructure wrapper initialized and validated all three
OpenTofu roots. The A101 trust root, stack, independence, worker runtime,
worker qualification, Anthropic spend, and preview checks passed. The wrapper
returned 1 only for the deliberately stale requirement-1 Anthropic issuance
host-contract fixture:

```text
live    bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f
current eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977
```

The complete Ansible wrapper ran 164 tests in 14 isolated processes. It passed
163; the only failure was the same retained host-contract mismatch. ShellCheck,
all four Ansible lint profiles, all four playbook syntax checks, and the
terminal isolated A101 trust-root check passed. Refreshing the fixture is
explicitly outside this authorization and would falsely claim a live
requirement-1 rerun, so the honest retained failure remains.

## A78 review request

A78 should review the exact pushed record head named in the PR handoff from a
fresh detached worktree under A87 and inspect the owner-only artifacts in
place. It should:

1. recompute both artifact hashes and confirm directory and file custody;
2. decode the exact binary without publishing sensitive no-op values;
3. confirm exactly two acting resource addresses, ordered actions, old worker
   ID and addresses, unknown successor addresses, the attachment-only firewall
   update, three acting outputs, seven no-op resources, and no restore state;
4. confirm exactly 1 added, 1 changed, and 1 destroyed, with no resource beyond
   the worker and its firewall touched;
5. confirm the settled firewall refresh is the same resource and its after-side
   exactly equals the planned attachment update's before-side;
6. confirm plan source `c03a32f` contains the already-passed bounded A101 probe,
   and that all 13 provider qualification flags remain false; and
7. confirm the eventual apply-record obligation preserves every complete
   per-attempt A101 line verbatim.

A78 must return PASS or material findings without regenerating or applying a
plan, accessing a live host, backend, provider, Anthropic, or its Console,
issuing a credential, refreshing the stale fixture, changing a limit, starting
behavioral acceptance or requirement 3, rotating a credential, or changing a
qualification flag.
