# A115 M1/M2 clean-worker replacement attempt

Status: **exact replacement applied; both converges and standalone host
qualifications passed; A101 private-VPC probe timed out; sequence stopped**

This is the operational record for Jacob's explicit approval, "I approve the
plan." The approval applied only the exact A78-reviewed worker-replacement plan
and the wrapper's built-in convergence, qualification, and credential-free
isolation gates. It authorized no Anthropic credential, provider request,
Console limit action, requirement-1 refresh, behavioral acceptance,
requirement-3 work, or provider qualification-flag change. The grant is
recorded under A115; no new numbered ruling is minted, and A119 is not reused.

## Exact reviewed boundary

| Field | Value |
| --- | --- |
| operational source | `bc496e47bfeb703876495e80b011d88e10c7c232` |
| reviewed technical repair | `520663f25cbaf862d252067e9ca5d933b00b0e9b` |
| binary plan SHA-256 | `a87568c6707f7d1e5bf581072d70584be117d01e785d1e12ff64ee3665415a59` |
| rendered-plan SHA-256 | `d5c222e7b353e67eead2ff391fad1800e2537fe2e8bfedadd471cf3202649891` |
| A78 plan verdict | PASS, no material finding |
| old worker | `588778422`, public `159.203.171.240`, private `10.132.0.15` |
| replacement worker | `588826948`, public `134.209.170.42`, private `10.132.0.11` |
| worker firewall | `01af87da-4951-4441-a1c8-ddfc0214811b` |

The apply ran from a clean detached worktree at the exact operational source.
The plan directory remained `conductor:conductor 0700`, both plan files
remained `conductor:conductor 0600`, and both digests matched the reviewed
values immediately before apply.

## Pre-apply bracket

Two preliminary read-only bracket attempts stopped before the apply and made
no state change. The first ran the taint-file `stat` as `conductor` rather than
through the required privileged read path and received permission denied. The
second ran the dashboard Unix-socket curl as `conductor` rather than through
the service-access path and received curl status 7. Independent privileged
checks then confirmed the same underlying states. These were operator probe
mistakes, not infrastructure or source failures.

The final complete pre-apply bracket ran from `2026-07-30T21:19:12Z` through
`2026-07-30T21:19:26Z` and passed:

- old worker `588778422` was active at the reviewed addresses and its canonical
  `BOUNDARY_TAINTED` marker remained exact;
- the production tag contained only that worker and the Factory control plane;
- the worker firewall was `succeeded`, had zero pending changes, and attached
  only old worker `588778422`;
- no live firewall targeted the `production` tag;
- the DigitalOcean account was active with 19 of 500 droplet slots used, and
  NYC3 advertised the required size and image;
- Factory state was `paused=0,full_stop=0,active_work=0`, the backup service was
  inactive, and control services and health were passing.

The GitHub App key and dashboard account roster were materialized from the
existing secret store into a separate mode-0700 temporary directory as
mode-0600 files. The key parsed successfully, the roster contained exactly the
three reviewed identities and roles, and `converge.sh --check-inputs` returned
`converge_inputs_valid`. No secret was printed or recorded. The complete
temporary input directory was deleted after the one-shot wrapper ended.

## Exact apply and convergence

OpenTofu applied exactly `1 added, 1 changed, 1 destroyed`:

- created worker `588826948` from the declared stock Rocky Linux 9 image;
- updated firewall `01af87da-4951-4441-a1c8-ddfc0214811b` to the new worker;
  and
- destroyed quarantined worker `588778422`.

The new worker completed cloud-init, passed the reviewed Rocky-base checks,
built the production parity root filesystem, installed the checksum-pinned
Firecracker and PHP/PHPUnit artifacts, installed the repaired A115 provider
transport and A114 teardown operation, and enabled the private-egress policy.

First convergence passed:

```text
factory-control.example.com : ok=221 changed=16 failed=0
factory-worker.example.com  : ok=94  changed=71 failed=0
```

Second convergence was fully idempotent:

```text
factory-control.example.com : ok=216 changed=0 failed=0
factory-worker.example.com  : ok=84  changed=0 failed=0
```

The standalone control-plane qualification and standalone worker qualification
both passed. The worker qualification included the canonical taint guard,
empty runtime staging roots, absence of Firecracker and jailer processes, exact
rootfs integrity, all 13 false provider qualification flags, and the standing
credential scan.

## A101 stop

The wrapper then stopped at the first control-to-worker private-VPC management
probe:

```text
qualifying A101 private-VPC management transport
ssh: connect to host 10.132.0.11 port 22: Connection timed out
wrapper exit status: 1
```

The timeout occurred after the public-path standalone worker qualification and
before `worker block-breakglass`. The credential-free production isolation
probe, its post-probe qualification, and every Anthropic phase did not run.
No bearer was minted, no Anthropic endpoint was contacted, no paid request was
made, and neither Console limit was changed.

## Read-only diagnosis

Read-only diagnosis made no host, firewall, cloud, provider, or cap change. At
`2026-07-30T22:04:17Z`, the exact installed operation
`patchyard-management-ssh worker probe` succeeded to the same
`10.132.0.11:22`. Worker SSH logs recorded public-key acceptance for
`factory-manager` from control private IP `10.132.0.17`. Worker `sshd` and
`firewalld` were active, and the host firewall admitted SSH from exactly
`10.132.0.17/32` and orchestration break glass `142.93.121.94/32`.

DigitalOcean then reported worker `588826948` active in NYC3 at the declared
addresses. Firewall `01af87da-4951-4441-a1c8-ddfc0214811b` was `succeeded`,
had zero pending changes, and attached only that worker. Old worker
`588778422` returned provider HTTP 404, and the production-tag inventory
contained only replacement worker `588826948` and control plane `586468414`.
The installed control checkout was clean at the exact operational source; all
four control services and public health remained active.

The worker's canonical taint marker was absent. Its runtime staging roots,
network-namespace list, and `factory-worker` process list were empty; its only
nftables tables were the declared `firewalld` and
`patchyard_worker_egress` tables. The control-plane taint prefix was also
absent. These observations are consistent with the wrapper never entering an
isolation or provider runtime.

Because provider firewall status was not sampled at the instant of the
timeout, the no-change transition from timeout to a successful management
probe supports DigitalOcean firewall-attachment propagation only as an
inference. It does not rewrite the failed qualification into a pass.

## Repository gates and mutation proof

The complete application wrapper passed after this record was written. It
included 39 browser-control tests with the Docker-only integration skip, every
Rust unit and integration test, reproducible release verification, dependency
and advisory checks, model checks, and the byte-exact codebase projection.

The complete infrastructure wrapper initialized and validated all three
OpenTofu roots and passed the stack, independence, worker-runtime, and
worker-qualification gates. It then stopped at the intentionally stale
requirement-1 live host-contract binding: the live fixture records
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`,
while the reviewed current contract is
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`.
The complete Ansible wrapper likewise passed 139 of 140 tests and stopped only
on that same exact mismatch. Refreshing the live fixture is outside this failed
sequence and would falsely claim a rerun that did not occur.

The focused Anthropic spend suite passed 25 of 25 tests, and the unmodified
checker reported `Anthropic spend check: pass (A115 successor preflight;
historical failures retained)`. Its source-only mutation test rejected the
reviewed weakening set: broadened spend/non-spend run-root modes, replacement
of the consuming `factory-worker` identity, replacement of traversal with mere
existence, and removal or rewriting of the three ordering anchors. This record
adds no new executable binding; `git diff --check` and the regenerated
codebase-metrics projection also passed.

## Stop boundary

The exact reviewed plan required the operator to stop and preserve any
nonzero gate. The sequence is therefore failed and stopped. No qualifier
retry, isolation probe, requirement-1 refresh, worker mutation, capability
issuance, provider request, Console action, behavioral acceptance,
requirement-3 work, or qualification-flag change followed.

Although the automated taint marker is absent because no provider or isolation
runtime was entered, the reviewed plan also said a failed successor is not to
be repaired or reused. Worker `588826948` is therefore operationally
quarantined by this record. Continuing requires escalation and a new explicit
bounded sequence; it cannot silently reuse this worker.

## Authorized successor-plan disposition

Jacob later explicitly authorized "a new clean-worker replacement plan plus
A78 review." No retry, repair, or reuse of worker `588826948` followed. The
build seat instead generated a fresh owner-only saved plan that replaces that
exact operationally quarantined worker and updates only its existing firewall
attachment. The plan and its non-executing boundary are recorded in
`2026-07-30-a115-m1m2-quarantined-successor-replacement-plan.md`. The grant
does not authorize apply or any provider action, and the plan requires a fresh
A78 review before any separate apply decision.

A78 later returned PASS with no material findings on exact plan-record commit
`9c40b086a3c59a5955ebd484f942319e02786c68` and the unchanged saved plan. The
build seat sustained that result under A77. No retry of this failed sequence,
worker reuse, or apply occurred; only the separately generated successor plan
is eligible for a new explicit apply decision.
