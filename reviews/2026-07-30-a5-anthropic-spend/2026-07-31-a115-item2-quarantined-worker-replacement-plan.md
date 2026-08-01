# A115 item 2 quarantined-worker replacement plan

Status: **saved plan produced; awaiting A78 review; not applied**

Jacob authorized item 2 as planning only after A78 passed item 1, the A101
firewall-readiness gate, at exact PR head
`db1204f09488a6afbbf8c59c66a915110eef1c57`. This operational grant is
recorded under A115 and does not mint a new numbered ruling. It authorizes one
saved worker-replacement plan that creates a fresh worker and retires
operationally quarantined worker `588858421` through one create-before-destroy
replacement. Applying the plan requires a separate explicit `AUTHORIZE APPLY`
from Jacob against the exact binary SHA-256 below.

## Exact source and saved artifacts

| Field | Value |
| --- | --- |
| operational plan source | `db1204f09488a6afbbf8c59c66a915110eef1c57` |
| item-1 A78 verdict | PASS, no finding requiring repair |
| saved binary plan | `/tmp/patchyard-replace-a115-item2.fAu8qn/worker-replacement.tfplan` |
| saved binary SHA-256 | `633524ded3c485fc82ac7b0e4c503b56fa334f93e05d7c70873605776807c5f4` |
| rendered plan | `/tmp/patchyard-replace-a115-item2.fAu8qn/worker-replacement.tfplan.txt` |
| rendered-plan SHA-256 | `3fe7b11df6d116dd6e7506d8fafdb88fd8bfb661be989c9c92a0681dee62320b` |
| binary generation time | `2026-07-31T21:21:42.790317867Z` |
| final rendered-plan time | `2026-07-31T21:22:49.599096628Z` |
| directory mode | `conductor:conductor 0700` |
| both plan-file modes | `conductor:conductor 0600` |

The source checkout was committed and clean. The operator invoked exactly:

```text
infra/replace-worker.sh plan /tmp/patchyard-replace-a115-item2.fAu8qn
```

The wrapper passed the production tag-firewall guard, initialized the
DigitalOcean root, refreshed encrypted remote state, generated one saved
`-replace=digitalocean_droplet.worker` binary, and reached the final render
step only after `verify_worker_plan` accepted that binary. No second saved
replacement plan was generated.

The Codex command relay terminated its child while the wrapper's final
`tofu show -no-color` process had an open zero-byte render target. The binary
plan was already complete and unchanged. The operator completed only the
wrapper's exact final render command against that same binary, then read both
digests and modes back. This was a render completion, not a source repair,
plan regeneration, cloud retry, or apply.

## Pre-plan bracket

The read-only API bracket ran from `2026-07-31T21:20:52Z` through
`2026-07-31T21:20:54Z`. The normal no-replacement OpenTofu plan then returned
exit 0 with `No changes. Your infrastructure matches the configuration.`
before the saved replacement binary was created.

- Git was clean at exact source `db1204f`; `git status --porcelain` returned
  zero entries.
- OpenTofu state and the live provider both identified worker `588858421` as
  active in `nyc3`, size `s-8vcpu-16gb`, stock image
  `rockylinux-9-x64`, at public `159.203.170.236` and private
  `10.132.0.15`.
- Worker firewall `01af87da-4951-4441-a1c8-ddfc0214811b` was `succeeded`,
  had zero pending changes and no tags, and attached only worker `588858421`.
- The production tag-firewall guard passed. The production-tag Factory subset
  contained only active control plane `586468414` and worker `588858421`.
- The DigitalOcean account was `active`, with 19 of 500 droplet slots in use.
- Public stock image `rockylinux-9-x64`, image ID `234045074`, reported
  `available` in `nyc3`.
- Size `s-8vcpu-16gb` reported `available` and included `nyc3` in its regions.

These are time-bounded plan facts. A separately authorized apply must sample
the complete bracket again and must continue to treat worker `588858421` as
operationally quarantined and ineligible for repair or reuse.

## Exact old and new addresses

| Plan address | Action | Old | New |
| --- | --- | --- | --- |
| `digitalocean_droplet.worker` | `["create","delete"]` | ID `588858421`; public `159.203.170.236`; private `10.132.0.15` | ID, public address, and private address all `(known after apply)` |
| `digitalocean_firewall.worker` | `["update"]` | firewall `01af87da-4951-4441-a1c8-ddfc0214811b`; `droplet_ids=[588858421]` | same firewall; replacement droplet ID `(known after apply)` |
| output `worker_ipv4` | update | `159.203.170.236` | `(known after apply)` |
| output `worker_private_ipv4` | update | `10.132.0.15` | `(known after apply)` |
| output `ansible_inventory` worker host | update | public `159.203.170.236`; private `10.132.0.15` | both `(known after apply)` |

The worker action is ordered create-before-destroy. It creates the declared
stock Rocky Linux 9 worker in `nyc3` at size `s-8vcpu-16gb`, with no backups,
IPv6, attached volume, snapshot restore, or old-host state transfer.

## Mechanical plan projection

The encrypted binary has nine resource changes. Seven are exact no-ops.
Exactly two act:

1. `digitalocean_droplet.worker` is replaced by request with ordered actions
   `["create","delete"]`, retiring current state target `588858421`.
2. `digitalocean_firewall.worker` is updated in place only to replace its
   worker attachment.

The rendered summary is exactly:

```text
Plan: 1 to add, 1 to change, 1 to destroy.
```

The seven no-op resources are the control-plane droplet and firewall, backup
bucket, both Spaces keys, management SSH key, and backup recovery key. No
restore-drill resource exists. Only `ansible_inventory`, `worker_ipv4`, and
`worker_private_ipv4` change as outputs, because the successor addresses do
not exist until apply. A fail-closed local projection required these exact
addresses, actions, old worker ID and old IPs and rejected every other acting
resource or output.

## Sensitive-plan handling incident

The encrypted plan necessarily contains sensitive no-op state. During local
verification, one overbroad JSON projection mistakenly emitted sensitive
no-op output values into the private Codex tool transcript. No such value was
written to Git, this record, the rendered plan, a GitHub comment, or the A78
handoff. Credential rotation is outside this authorization, so none occurred.
This operator-process incident is disclosed for separate human disposition and
does not change the saved binary or its mechanical action shape.

## Negative scope and stop boundary

No apply command ran. DigitalOcean still reported worker `588858421` active
after plan generation. No worker, firewall, host, provider, Console value,
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
`633524ded3c485fc82ac7b0e4c503b56fa334f93e05d7c70873605776807c5f4`.

## Full repository gates

The complete application wrapper returned 0. All 39 browser-control tests
passed with the one expected Docker-only integration skip; every Rust unit,
integration, property, fixture, and doc test passed; triage replay passed all
11 fixtures; and the two clean release builds reproduced `factory-verify`
SHA-256
`99e3d1da120848b5cb4198788504404bea2e2c178316f301c603a987e8795bae`.
The 1,177-record RustSec scan, cargo-deny, cargo-vet, cargo-machete, all 10
model tests, and the byte-exact codebase-metrics projection passed.

The complete infrastructure wrapper initialized and validated all three
OpenTofu roots. The A101 trust root, stack, independence, worker runtime,
worker qualification, Anthropic spend, and preview checks passed. The wrapper
returned 1 only for the deliberately stale requirement-1 Anthropic issuance
host-contract fixture:

```text
live bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f
current eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977
```

The complete Ansible wrapper ran 160 tests in 14 isolated processes. It passed
159; the only failure was the same retained host-contract mismatch. All four
Ansible lint profiles passed with zero failures and zero warnings, all four
playbook syntax checks passed, and the terminal isolated A101 trust-root check
passed. Refreshing the fixture is explicitly outside item 2 and would falsely
claim a live requirement-1 rerun, so the honest retained failure remains.

## A78 review request

A78 should review the exact record head named in the PR handoff from a fresh
detached worktree and inspect the owner-only artifacts in place. It should:

1. recompute both artifact hashes and confirm directory and file custody;
2. decode the exact binary without publishing sensitive no-op values;
3. confirm the exact two acting resource addresses, ordered actions, old ID
   and IPs, unknown successor addresses, firewall attachment update, three
   acting outputs, seven no-op resources, and absence of restore state;
4. confirm the plan is exactly 1 added, 1 changed, and 1 destroyed, with no
   resource beyond the worker and its firewall touched;
5. confirm plan source `db1204f` contains the already-passed A101 readiness
   gate and that all 13 provider qualification flags remain false; and
6. return PASS or material findings without regenerating or applying a plan,
   accessing Anthropic or its Console, issuing a credential, refreshing the
   stale fixture, or changing any live state.
