# A115 spend run-root repair

Status: **A78 review failed on two conceded medium findings; repair iteration
exhausted and clean-worker replacement blocked**

This is the requirement-2 work record for Jacob's explicit authorization of
the bounded repair after the first successor operational attempt. It is an
operational grant under A115, not a new numbered ruling. A119 remains reserved.

## Bounded Console readback

Jacob opened the Patchyard Factory workspace and organization limit pages without
changing either limit. The control plane bracketed his readback in UTC and
stored only the credential-free observations in a root-owned volatile file:

| Field | Observed value |
| --- | --- |
| capture start | `2026-07-30T18:46:35Z` |
| capture end | `2026-07-30T18:46:55Z` |
| workspace | `Patchyard Factory` / `wrkspc_000000000000000000000000` |
| displayed workspace state | `$7.68 of $50.00`, resets 1 Aug 2026 |
| organization | `aaadc747-869a-42d2-af51-58a5be8e3b7f` |
| displayed organization state | `$500.00` monthly limit, `$72.27` spent, 14% used |

The 20-second bracket satisfies the five-minute bound. The workspace was
already at the reviewed `$50.00` operational cap, and the organization limit
remained `$500.00`; no Console mutation was made. On the control plane,
`/run/patchyard-anthropic` is `root:root 0700` and its
`cap-readbacks.json` is `root:root 0600`. The temporary file contains no
credential.

## First operational attempt and stop

At technical source
`673b89fbfad5c287f79f9d6b7d046c35f1881cee`, preflight confirmed the exact
installed revision, active control services, idle backup operation,
`paused=false`, `full_stop=false`, `active_work=0`, and an absent target
artifact directory. The runner invoked exactly one operational-acceptance
phase:

```text
run ID: anthropic-s2-operational-20260730-e7b0d43df8
worker start: 2026-07-30T18:48:57Z
failure/taint: 2026-07-30T18:49:05Z
runner exit: 1
diagnostic: anthropic-spend-provider-transport-failed-23
failure stage: provider-one-shot-transport
launcher line: 525
```

Curl status 23 is a local write-path failure, not a provider response. The run
produced no sanitized provider observation and no control-plane artifact
directory. It therefore proves neither provider acceptance nor refusal, and it
does not establish whether Anthropic received the attempted transfer or
whether any incremental spend settled. No HTTP status, request ID, provider
error, usage figure, denial figure, or overshoot figure is claimed from this
attempt.

The launcher cleanup removed the run tmpfs, source stage, input stage, provider
namespace, provider veth, provider nftables table, and worker process. The
worker nevertheless correctly made itself ineligible because a
provider-qualification run failed:

```text
run=anthropic-s2-operational-20260730-e7b0d43df8 reason=containment-qualification-failed stage=provider-one-shot-transport line=525 detected_at=2026-07-30T18:49:05Z
```

The marker is `/var/lib/patchyard-worker/BOUNDARY_TAINTED`, mode
`root:root 0600`. An initial manual residue probe mistakenly checked the
control-plane prefix `/var/lib/patchyard/BOUNDARY_TAINTED` and reported it
absent. A direct check of the worker's canonical path corrected that error.
The marker will not be cleared and worker `588778422` will not be reused.

The post-attempt worker qualifier exited nonzero at its intentional taint-file
guard. A separate read-only `e2fsck -fn` completed successfully and the rootfs
digest remained exact; the failed qualifier is evidence of quarantine, not a
rootfs-corruption diagnosis.

## A77 diagnosis - concede

The source defect is conceded. The launcher created `$RUN_TMPFS` as
`root:root 0700`, then created the provider directory as
`root:factory-worker 0710` and its raw directory as
`factory-worker:factory-worker 0700`. The one-shot helper launches the network
client as `factory-worker`. POSIX path traversal fails at the root-owned
`0700` ancestor before the child can use its narrowly owned files.

A no-network disposable filesystem experiment reproduced the mismatch on the
worker: the `factory-worker` identity could neither traverse the parent nor
write the nested raw path (`factory_worker_parent_traverse_rc=1`,
`factory_worker_nested_write_rc=1`). The experiment removed its temporary
paths at `2026-07-30T18:50:17Z`. SELinux was enforcing and recorded no related
AVC, so the ordinary mode bits are sufficient to explain the result.

## Bounded source repair

Spend mode now creates only its exact run root as
`root:factory-worker 0710`. Group execute permits traversal but group read and
write remain absent. Non-spend runs explicitly retain `root:root 0700`.
Capability material remains `root:root 0600`; the provider directory remains
`root:factory-worker 0710`; and the raw request/response directory remains
`factory-worker:factory-worker 0700`.

The spend checker binds the exact conditional staging block, its location
between runtime staging and capability creation, and the complete launcher
digest. The focused suite includes a direct source-contract test and three new
real-checker mutations:

1. remove the spend-mode group traversal grant;
2. expand spend-mode group access from `0710` to `0770`; and
3. expand the non-spend run root from `root:root 0700` to the spend-mode
   ownership and mode.

All three mutations fail, as do the existing twenty-six source mutations. The
focused suite passes 25 of 25 tests, and the unmodified checker reports the
A115 successor preflight pass while retaining the historical failure records.

The repaired launcher SHA-256 is
`5e69e5f99389bbbcc7796d1623fc0cefa1912ae4050b14eb2c47cb3772b697d5`.
A live read-only parent-path check also confirmed that
`/run/patchyard-worker` is `factory-worker:factory-worker 0700`, so the new
child run root is the only missing traversal grant; no broader ancestor mode
change is needed.

## Pre-review gates

The complete application wrapper passed, including 39 browser-control tests
(one Docker-only integration skip), every Rust unit and integration test,
reproducible release verification, dependency and advisory checks, model
checks, and the byte-exact codebase projection. OpenTofu initialized and
validated all three roots. All four Ansible production lint profiles and all
four playbook syntax checks passed. ShellCheck passed, the spend checker passed,
and 139 of the 140 Ansible unit tests passed.

The only red gate is the intentional live-evidence dependency created by the
repair: requirement 1 records host-contract SHA-256
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`,
while the repaired host contract is
`2b7a904489e9fa4886c5677a9221fc66978f31e492edf740e7c4ea6b35c37d5b`.
Both the issuance checker and its unit test reject the stale live fixture.
That failure must remain visible until the reviewed repair is installed on a
clean replacement worker and requirement 1 is rerun; changing the evidence
without a live rerun would be false proof.

## A78 review and A77 adjudication

A78 reviewed exact commit
`8cdfeef955ba3d574030e21aff65549219642b86` with Opus 5 at requested effort
`xhigh` in plan/read-only mode. The review returned FAIL on two medium material
findings:

1. the new checker ordering anchors can raise uncontrolled `ValueError` and
   suppress every accumulated diagnostic; and
2. the launcher does not read back the realized directory mode or test
   traversal as `factory-worker` before capability creation.

The build seat reproduced both. Three independent anchor mutations each
produced the bare traceback and no controlled checker diagnostic. Source
inspection and a disposable `install -d` experiment confirmed the missing
readback and the dependence on realized filesystem state. Both findings and
their severity are conceded under A77. The six nonblocking observations are
individually adjudicated in
`2026-07-30-a77-spend-run-root-repair-adjudication.md`.

The exact A78 review is recorded in
`2026-07-30-a78-spend-run-root-repair-review.md`. Because the authorized
repair reached a failed adversarial review, A9 stops another implicit source
iteration. A separately authorized bounded M1/M2 repair and new A78 review are
required before any replacement plan.

## Boundary after review

No repaired source has been installed, no worker has been replaced, no taint
marker has been cleared, and no further capability or provider request has
been made. A clean-worker replacement is blocked. Behavioral acceptance,
requirement 3, and all provider qualification flags remain untouched.
