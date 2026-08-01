# A115 item 2 quarantined-successor replacement attempt

Status: **exact replacement applied; both converges, the provider-firewall
readiness gate, and standalone host qualifications passed; the A101 worker
private-VPC probe timed out; sequence stopped**

This is the operational record for Jacob's explicit `AUTHORIZE APPLY` against
the exact A78-reviewed item-2 plan. The grant covered only the wrapper's
built-in worker replacement, two converges, bounded DigitalOcean firewall
readiness gate, first qualification, production isolation probe, and final
qualification. It authorized no Anthropic credential, provider request,
Console action, requirement-1 refresh, behavioral acceptance, requirement-3
work, credential rotation, or provider qualification-flag change. The grant is
recorded under A115 and does not mint a new numbered ruling.

## Exact reviewed boundary

| Field | Value |
| --- | --- |
| approved operational source | `8c19d5506dce2a646a6c510df38d7ec3d0567e99` |
| plan-generation source | `db1204f09488a6afbbf8c59c66a915110eef1c57` |
| binary plan | `/tmp/patchyard-replace-a115-item2.fAu8qn/worker-replacement.tfplan` |
| binary plan SHA-256 | `633524ded3c485fc82ac7b0e4c503b56fa334f93e05d7c70873605776807c5f4` |
| rendered plan | `/tmp/patchyard-replace-a115-item2.fAu8qn/worker-replacement.tfplan.txt` |
| rendered-plan SHA-256 | `3fe7b11df6d116dd6e7506d8fafdb88fd8bfb661be989c9c92a0681dee62320b` |
| A78 plan verdict | PASS, no finding ([review](https://github.com/JacobStephens2/patchyard/pull/79#issuecomment-5147813735)) |
| retired worker | `588858421`, public `159.203.170.236`, private `10.132.0.15` |
| replacement worker | `589089036`, public `167.172.239.1`, private `10.132.0.11` |
| worker firewall | `01af87da-4951-4441-a1c8-ddfc0214811b` |

The apply ran from the clean dedicated worktree on branch
`a5-anthropic-spend-a115-successor` at the exact approved source. The shared
checkout remained clean on `master` at
`43303c95b217f4da9f097d5ab4367bf52d3b0218`.

The final pre-apply decode found nine resource changes: seven exact no-ops and
two acting resources. The worker had ordered `["create","delete"]` replacement
actions and the worker firewall had one in-place `["update"]`; only
`ansible_inventory`, `worker_ipv4`, and `worker_private_ipv4` changed as
outputs. The wrapper independently repeated its revision, digest, and action
shape checks before cloud mutation and rechecked the binary digest after input
preflight.

## Pre-apply bracket and secret inputs

The complete final pre-apply bracket ran from `2026-07-31T22:08:48Z` through
`2026-07-31T22:09:04Z` and passed:

- worker `588858421` was active in `nyc3` on stock image
  `rockylinux-9-x64` (`234045074`) and size `s-8vcpu-16gb`, at the exact
  plan-bound public and private addresses;
- its canonical `BOUNDARY_TAINTED` marker was absent, while the committed prior
  failed-sequence record remained the binding operational quarantine;
- the account contained exactly two Factory droplets, control plane
  `586468414` and worker `588858421`, both active with only the `production`
  tag;
- worker firewall `01af87da-4951-4441-a1c8-ddfc0214811b` was `succeeded`, had
  zero pending changes and no tags, and attached only worker `588858421`;
- no live firewall targeted the broad `production` tag;
- predecessor `588826948` returned provider HTTP 404;
- the DigitalOcean account was active with 19 of 500 droplet slots used, and
  NYC3 advertised the required image and size;
- the quarantined worker's `sshd`, `firewalld`, and egress-policy service were
  active, with zero runtime-root entries, network namespaces, or
  `factory-worker` processes;
- Factory state was `paused=0,full_stop=0,active_work=0`, with zero pending or
  executing controls;
- PostgreSQL, dashboard, supervisor, Caddy, and dashboard Unix-socket health
  passed while the backup service was inactive; and
- the installed control-plane checkout was clean at the prior operational
  source `d8b2955c4de050a67d932d763fd58f2509f34df5`.

The existing GitHub App key and exact three-account dashboard roster were
materialized into a separate mode-0700 temporary directory as mode-0600 files.
The key parsed, the roster matched the committed identities and roles, and the
input checker returned `converge_inputs_valid`. After the wrapper stopped and
the read-only state capture completed, both temporary files were removed with
`shred --remove=unlink --zero` and the empty directory was deleted.

One earlier read-only bracket collector ran from `22:07:34Z` through
`22:07:46Z`, emitted the complete cloud facts above, and then stopped before
the host summary because GNU `ps` returned its conventional no-match status
under that collector's `pipefail`. A direct read showed the intended value,
zero worker processes. No wrapper or operational gate had begun, and the
collector made no cloud or host mutation. The complete final bracket handled
the no-match status explicitly. Both owner-only logs are preserved:

| Log | Bytes | SHA-256 |
| --- | ---: | --- |
| `pre-apply-bracket-20260731T220734Z.log` | 2,060 | `321063885f13eb2afc1dbe368c55da0028dc8ca03943a2fc99249e0a13f49652` |
| `pre-apply-bracket-20260731T220848Z.log` | 3,071 | `027f940ebec6b125980d85a35bbf5ddc2890d9b5ba34f34e21b8993eaa32a6e8` |

## Exact apply and convergence

The one-shot wrapper started at `2026-07-31T22:09:28Z`. OpenTofu applied
exactly `1 added, 1 changed, 1 destroyed`:

- created worker `589089036` from the declared stock Rocky Linux 9 image at
  public `167.172.239.1` and private `10.132.0.11`;
- updated only firewall `01af87da-4951-4441-a1c8-ddfc0214811b` to attach the
  replacement; and
- destroyed operationally quarantined worker `588858421`.

The replacement completed cloud-init, built the production parity root
filesystem, installed the checksum-pinned Firecracker and PHP/PHPUnit
artifacts, installed the reviewed A115 provider transport and A114 teardown
operation, and enabled the private-egress policy.

First convergence passed:

```text
factory-control.example.com : ok=223 changed=22 failed=0
factory-worker.example.com  : ok=94  changed=71 failed=0
```

The control-plane changes advanced its clean desired-state checkout from
`d8b2955` to the approved `8c19d55`; the worker changes provisioned the new
host.

Second convergence was fully idempotent:

```text
factory-control.example.com : ok=216 changed=0 failed=0
factory-worker.example.com  : ok=84  changed=0 failed=0
```

## Firewall gate and qualification layers

The new bounded A101 provider-firewall gate ran after both converges and before
qualification. It passed on its first of at most 24 attempts:

```text
worker firewall readiness: pass
firewall=01af87da-4951-4441-a1c8-ddfc0214811b
worker=589089036
attempt=1
```

The wrapper then produced these qualification results in order:

| Layer | Result |
| --- | --- |
| standalone control-plane qualification | PASS |
| standalone worker qualification | PASS |
| A101 control-plane self probe | PASS by fail-fast progression to the following worker probe |
| A101 control-to-worker private-VPC probe | **FAIL** - SSH to `10.132.0.11:22` timed out |
| A101 break-glass block and isolated worker qualification | not run |
| terminal independence checker | not run |
| production Firecracker isolation probe | not run |
| post-isolation qualification | not run |

The exact terminal output was:

```text
qualifying A101 private-VPC management transport
ssh: connect to host 10.132.0.11 port 22: Connection timed out
wrapper exit status: 1
```

The wrapper stopped at `2026-07-31T22:45:58Z`. The owner-only complete apply
log is
`/tmp/patchyard-replace-a115-item2.fAu8qn/authorized-apply-20260731T220928Z.log`.
It is `conductor:conductor 0600`, contains 405,611 bytes, and has SHA-256
`f0f05f3e17c484b749524d5be70672609371a78ad1c5881a0a2528ba7c7a08fe`.

The firewall gate's provider readback immediately preceded this failure, and a
later provider readback also showed desired state. Those facts do not turn the
private-VPC probe into a pass and do not establish why it timed out. The probe
was not retried and no cause is assigned by this record.

## Read-only post-stop state

Read-only checks from `2026-07-31T22:47:25Z` through `22:47:30Z` made no host,
firewall, cloud, provider, cap, or fixture change:

- DigitalOcean reported successor `589089036` active in NYC3 on stock image
  `rockylinux-9-x64`, size `s-8vcpu-16gb`, at public `167.172.239.1` and
  private `10.132.0.11`;
- worker firewall `01af87da-4951-4441-a1c8-ddfc0214811b` was `succeeded`, had
  zero pending changes and no tags, and attached only successor `589089036`;
- both retired workers, `588858421` and `588826948`, returned provider HTTP
  404, and the account contained exactly successor `589089036` and control
  plane `586468414` as Factory droplets;
- public break-glass inspection found `sshd`, `firewalld`, and the worker
  egress-policy service active, no canonical taint marker, zero runtime-root
  entries, zero network namespaces, and zero Factory worker processes;
- PostgreSQL, dashboard, supervisor, Caddy, and dashboard Unix-socket health
  remained active, while the backup service remained inactive;
- Factory state remained `paused=0,full_stop=0,active_work=0`, with zero pending
  or executing controls;
- the installed control-plane checkout was clean at exact source
  `8c19d5506dce2a646a6c510df38d7ec3d0567e99`; and
- no new `worker-replacement-*` isolation artifact was created after the apply
  began.

The owner-only post-stop log is
`/tmp/patchyard-replace-a115-item2.fAu8qn/post-stop-readback-20260731T224725Z.log`.
It contains 3,245 bytes and has SHA-256
`213fac72eeabb828161ae2381fe2c04319c2c6d6a0dd11d8d5615217f082e4b0`.

## Retained fixture and negative scope

The deliberately stale requirement-1 fixture remains untouched. It still
records host-contract SHA-256
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`,
while the current source recomputes to
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`.
Refreshing it would falsely claim a requirement-1 rerun that did not occur.

All 13 `credential_qualified` flags remain false. No bearer was minted, no
Anthropic endpoint was contacted, no paid inference request was made, and
neither Anthropic limit changed. No requirement-2 spend phase resumed. No
requirement-1 refresh, behavioral acceptance case, requirement-3 work,
credential rotation, provider qualification-flag change, or production
isolation probe followed.

## Stop boundary

The reviewed grant required the operator to stop and preserve any nonzero
result. That rule was followed. No firewall-gate retry, qualifier retry,
private-VPC probe retry, host or source repair, fixture refresh, isolation
probe, credential issuance, provider request, Console action, behavioral
acceptance, requirement-3 work, qualification-flag change, or credential
rotation followed.

Although the automated taint marker is absent because no isolation or provider
runtime began, the reviewed plan independently makes every failed successor
ineligible for repair or reuse. Worker `589089036` is therefore operationally
quarantined by this record. Factory has no qualified worker. Any continuation
requires a new explicit bounded authorization and a fresh replacement; this
worker cannot be retried, repaired, or silently reused.

## A78 operational-record review request

A78 should review the exact record head named in the PR handoff from a fresh
detached worktree and inspect the owner-only artifacts in place. It should:

1. recompute the binary, rendered-plan, complete apply-log, and post-stop-log
   digests and byte counts;
2. verify the one exact apply, both converge recaps, firewall-gate attempt-1
   pass, standalone host passes, and terminal A101 timeout in the complete log;
3. verify live DigitalOcean identity, addresses, predecessor absence, exact
   firewall attachment, and absence of stray Factory droplets;
4. confirm that the successful provider-firewall readback is not relabelled as
   successful private-VPC qualification and that no unobserved cause is
   assigned;
5. confirm the operational quarantine, zero isolation artifact, deliberately
   stale requirement-1 fixture, complete negative scope, and all 13 false
   qualification flags; and
6. return PASS or material findings without retrying or repairing the worker,
   refreshing a fixture, accessing Anthropic or its Console, issuing a
   credential, or changing live state.
