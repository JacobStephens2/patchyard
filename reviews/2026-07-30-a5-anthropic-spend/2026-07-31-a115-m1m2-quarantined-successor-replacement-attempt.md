# A115 M1/M2 quarantined-successor replacement attempt

Status: **exact replacement applied; both converges and standalone host
qualifications passed; A101 private-VPC probe timed out; sequence stopped**

This is the operational record for Jacob's explicit `AUTHORIZE APPLY`. The
grant applied only the exact A78-reviewed saved plan and the wrapper's built-in
convergence, qualification, and credential-free isolation gates. It authorized
no Anthropic credential, provider request, Console limit action, requirement-1
refresh, behavioral acceptance, requirement-3 work, credential rotation, or
provider qualification-flag change. The grant is recorded under A115; no new
numbered ruling is minted, and A119 is not reused.

## Exact reviewed boundary

| Field | Value |
| --- | --- |
| operational source | `d8b2955c4de050a67d932d763fd58f2509f34df5` |
| reviewed technical repair | `520663f25cbaf862d252067e9ca5d933b00b0e9b` |
| binary plan | `/tmp/patchyard-replace-a115-m1m2-successor.4Dq9kk/worker-replacement.tfplan` |
| binary plan SHA-256 | `62adfcaac371203a5c9127ed307f29fdbd1593e2f2a466ae22836551e9fd91c3` |
| rendered-plan SHA-256 | `b77a32f12f3480e08496d6b8ff83fb38dc6c2b300999649ff0b9ad94169cafae` |
| A78 plan verdict | PASS, no material finding |
| old worker | `588826948`, public `134.209.170.42`, private `10.132.0.11` |
| replacement worker | `588858421`, public `159.203.170.236`, private `10.132.0.15` |
| worker firewall | `01af87da-4951-4441-a1c8-ddfc0214811b` |

The apply ran from a clean detached checkout at the exact operational source.
The plan directory and files retained their reviewed owner-only modes and both
digests matched immediately before apply. The wrapper independently decoded
the action shape, revalidated the convergence inputs, and rechecked the exact
binary digest immediately before the cloud mutation.

## Pre-apply bracket and secret inputs

The complete pre-apply bracket ran from `2026-07-31T00:34:52Z` through
`2026-07-31T00:35:08Z` and passed:

- old worker `588826948` was active at the plan-bound addresses, stock image,
  region, and size;
- its canonical `BOUNDARY_TAINTED` marker was absent, while the committed
  failed-sequence record remained the binding operational quarantine;
- the production tag contained only that worker and Factory control plane
  `586468414`;
- worker firewall `01af87da-4951-4441-a1c8-ddfc0214811b` was `succeeded`, had
  zero pending changes, and attached only old worker `588826948`;
- no live firewall targeted the broad `production` tag;
- the DigitalOcean account was active with 19 of 500 droplet slots used, and
  NYC3 advertised the required image and size;
- Factory state was `paused=0,full_stop=0,active_work=0`, with zero pending or
  executing controls; and
- PostgreSQL, dashboard, supervisor, Caddy, Unix-socket health, and the worker
  host services passed while the backup service was inactive.

The existing GitHub App key and exact three-account dashboard roster were
materialized into a separate mode-0700 temporary directory as mode-0600 files.
The key parsed, the roster matched the committed identities and roles, and the
wrapper's `converge.sh --check-inputs` returned `converge_inputs_valid`. No
secret was printed or recorded. Both files and their now-empty temporary
directory were deleted immediately after the wrapper stopped.

## Exact apply and convergence

The one-shot wrapper started at `2026-07-31T00:36:32Z`. OpenTofu applied
exactly `1 added, 1 changed, 1 destroyed`:

- created replacement worker `588858421` from the declared stock Rocky Linux 9
  image;
- updated only firewall `01af87da-4951-4441-a1c8-ddfc0214811b` to attach the
  replacement; and
- destroyed operationally quarantined worker `588826948`.

The replacement completed cloud-init, built the production parity root
filesystem, installed the checksum-pinned Firecracker and PHP/PHPUnit
artifacts, installed the reviewed A115 provider transport and A114 teardown
operation, and enabled the private-egress policy.

First convergence passed:

```text
factory-control.example.com : ok=221 changed=15 failed=0
factory-worker.example.com  : ok=94  changed=71 failed=0
```

Second convergence was fully idempotent:

```text
factory-control.example.com : ok=216 changed=0 failed=0
factory-worker.example.com  : ok=84  changed=0 failed=0
```

## A101 stop

The standalone control-plane qualification and standalone worker qualification
both passed. The wrapper then stopped at the first control-to-worker
private-VPC management probe:

```text
qualifying A101 private-VPC management transport
ssh: connect to host 10.132.0.15 port 22: Connection timed out
wrapper exit status: 1
```

The owner-only complete apply log is
`/tmp/patchyard-replace-a115-m1m2-successor.4Dq9kk/authorized-apply-20260731.log`.
It is `conductor:conductor 0600`, contains 413240 bytes, ended at
`2026-07-31T01:15:37Z`, and has SHA-256
`9f7e55663c275125984138dd8325d254c5a0f521e1a491997a12011a7a586ca2`.

The timeout occurred before the wrapper blocked the orchestration break-glass
path and before its production isolation probe. The isolation probe, post-probe
qualification, requirement-1 refresh, and every Anthropic phase did not run.
No bearer was minted, no Anthropic endpoint was contacted, no paid request was
made, and neither Console limit was changed.

## Read-only post-stop state

Read-only checks after the stop made no host, firewall, cloud, provider, or cap
change:

- DigitalOcean reported successor `588858421` active in NYC3 on stock image
  `rockylinux-9-x64`, size `s-8vcpu-16gb`, at public `159.203.170.236` and
  private `10.132.0.15`;
- the worker firewall was `succeeded`, had zero pending changes, and attached
  only successor `588858421`;
- predecessor `588826948` returned provider HTTP 404, and the Factory subset of
  the production-tag inventory contained only successor `588858421` and
  control plane `586468414`;
- public break-glass inspection found `sshd`, `firewalld`, and the worker-egress
  service active, no canonical taint marker, zero runtime-root entries, zero
  network namespaces, and zero Factory runtime processes;
- PostgreSQL, dashboard, supervisor, Caddy, and dashboard Unix-socket health
  remained active, while the backup service remained inactive; and
- the installed control-plane checkout was clean at exact source
  `d8b2955c4de050a67d932d763fd58f2509f34df5`.

The provider firewall was not sampled at the instant of the private-VPC
timeout, and the failed management probe was not retried. The later settled
firewall readback therefore does not establish the cause and does not rewrite
the failed qualification into a pass.

## Repository gates and mutation status

The post-record focused gates passed: 47 Session 16 cutover contract tests, all
25 Anthropic spend tests, the Anthropic spend checker, the byte-exact codebase
metrics projection, and `git diff --check`. The spend suite includes the
36-case real-checker source-mutation harness that rejects the reviewed
run-root, consuming-identity, traversal, and ordering weakenings.

The complete application wrapper passed, including 39 browser-control tests
with the one local Docker-only integration skip, every Rust unit and
integration test, the reproducible `factory-verify` release build, dependency
and advisory checks, model checks, and the byte-exact codebase projection.

The complete infrastructure wrapper initialized and validated all three
OpenTofu roots and passed its stack, independence, worker-runtime, and
worker-qualification checks. It then stopped only at the deliberately stale
requirement-1 host-contract fixture: live
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`
versus current
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`.
The complete Ansible wrapper likewise passed 139 of 140 tests and stopped only
on that exact known mismatch. Refreshing the live fixture after this failed
sequence would falsely claim a rerun that did not occur.

This operational record changes no executable binding, so there is no new
source weakening to mutate. It retains the latest passing source-mutation
results rather than relabeling documentation as a source repair.

## Stop boundary

The exact reviewed plan required the operator to stop and preserve any nonzero
result. That rule was followed. No qualifier retry, host or source repair,
isolation probe, requirement-1 refresh, credential issuance, provider request,
Console action, behavioral acceptance, requirement-3 work, qualification-flag
change, or credential rotation followed.

Although the automated taint marker is absent because no isolation or provider
runtime began, the reviewed plan independently makes every failed successor
ineligible for repair or reuse. Worker `588858421` is therefore operationally
quarantined by this record. Continuing requires escalation and a new explicit
bounded sequence; this worker cannot be silently reused.

## A78 operational-record review and A77 adjudication

A78 reviewed exact record commit
`d56d71e29ccac41fe4ce7e0f0e51a7681b7dcf1b` in a fresh detached worktree and
returned **PASS with no finding against the operational record**. The reviewer
confirmed the nonzero stop, unknown-cause wording, non-passing settled-firewall
readback, independent operational quarantine, complete negative scope, 13
false provider qualification flags, deliberate requirement-1 non-refresh, and
the correct A101 target `10.132.0.15`.

A78's DigitalOcean token returned HTTP 401, so its cloud review was limited to
the committed account and internal consistency; it did not independently
corroborate the build seat's cloud readbacks.

Under A77, the build seat:

- concedes the twice-seen post-replacement A101 failure shape and the
  forward-looking need to decide a provider-firewall readiness gate before
  another replacement;
- refutes as unproved the stronger causal claim that firewall propagation
  caused this July 31 timeout, because the firewall was not sampled at failure
  and A101 was not retried; and
- concedes that Factory has no qualified worker and that a future bounded
  sequence must replace, not retry or repair, quarantined worker `588858421`.

The complete review and disposition are recorded in
`2026-07-31-a78-quarantined-successor-operational-record-review.md` and
`2026-07-31-a77-quarantined-successor-operational-record-adjudication.md`.
They authorize no repair or live action.
