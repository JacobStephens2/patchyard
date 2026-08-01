# A115 post-A101 authorized apply preflight stop

Status: **the exact reviewed wrapper stopped at its local converge-input
preflight before OpenTofu apply; no cloud mutation occurred; no retry**

This is the operational record for Jacob's explicit `AUTHORIZE APPLY` against
the exact A78-reviewed post-A101 worker-replacement plan. The grant covered
only the wrapper's built-in apply, two converges, DigitalOcean firewall
readiness gate, first qualification, production isolation probe, and final
qualification. Any nonzero result was terminal. The wrapper stopped before
the cloud apply because a required controller-local credential-file variable
was absent, so the existing quarantined worker remains the only Factory worker.

No retry, input staging, plan regeneration, host repair, fixture refresh, or
later wrapper stage followed. A new attempt requires a new explicit
authorization; this record does not preserve or imply unused apply authority.

## Exact reviewed boundary

| Field | Value |
| --- | --- |
| approved operational source | `672f851ebed3ced133840483e7d4d26da09424e4` |
| plan-generation source | `c03a32fc6541378a85bb4adfebdae07276706713` |
| binary plan | `/tmp/patchyard-replace-a115-a101.ZUTbIb/worker-replacement.tfplan` |
| binary plan SHA-256 | `02073c1c7955ffb343b0a1ba677832ca141da0e697a618cee9b75823fd4b72ab` |
| rendered plan | `/tmp/patchyard-replace-a115-a101.ZUTbIb/worker-replacement.tfplan.txt` |
| rendered-plan SHA-256 | `d0a98a9410c76183ece2a2d54681e94918e9cb01a6e8fef0d057c7210a3896c7` |
| A78 plan verdict | PASS, no finding ([review](https://github.com/JacobStephens2/patchyard/pull/79#issuecomment-5149809002)) |
| unchanged worker | `589089036`, public `167.172.239.1`, private `10.132.0.11` |
| worker firewall | `01af87da-4951-4441-a1c8-ddfc0214811b` |

The authorized wrapper invocation ran from the existing dedicated worktree,
clean at the exact approved revision. The shared checkout remained clean on `master` at
`43303c95b217f4da9f097d5ab4367bf52d3b0218`.

A78 independently recomputed both plan digests, decoded the binary as nine
resource changes with exactly two non-no-ops, verified the live DigitalOcean
before-state, and confirmed `c03a32f` is an ancestor of `672f851e`. The exact
approved head contains `PROBE_MAX_ATTEMPTS=5` and the `outcome=exhausted`
emission. Had the wrapper reached A101, it would have exercised the reviewed
bounded 45-second probe rather than the historical single-attempt probe.

## Pre-apply bracket

Immediately before authorization, A78 found the plan unchanged and live state
matching. The build seat then independently rechecked the following facts
before invoking the wrapper:

- Git was clean at exact approved source `672f851e`.
- The binary remained mode `0600`, owned by `conductor:conductor`, with exact
  reviewed SHA-256
  `02073c1c7955ffb343b0a1ba677832ca141da0e697a618cee9b75823fd4b72ab`.
- The decoded plan still contained exactly nine resource changes and only
  `digitalocean_droplet.worker ["create","delete"]` plus
  `digitalocean_firewall.worker ["update"]` as acting resources.
- Worker `589089036` was active in `nyc3` on stock image
  `rockylinux-9-x64`, size `s-8vcpu-16gb`, at exact plan-bound public
  `167.172.239.1` and private `10.132.0.11`.
- Firewall `01af87da-4951-4441-a1c8-ddfc0214811b` was `succeeded`, had zero
  pending changes and no tags, and attached only worker `589089036`.
- The account was active with 19 of 500 droplet slots in use. The only Factory
  droplets were active control plane `586468414` and worker `589089036`.
- Public image `rockylinux-9-x64`, ID `234045074`, and size
  `s-8vcpu-16gb` were both available in `nyc3` at
  `2026-08-01T05:38:47Z`.
- All 13 provider `credential_qualified` values were false.

Two read-only bracket projectors made no mutation and were not counted as
passing brackets. The first used jq's reserved `end` token as a variable and
failed to compile. The corrected projection then exited 4 because it asserted
the control plane's unrelated size as `s-2vcpu-4gb`; the live value is
`s-4vcpu-8gb`. A narrow read at `2026-08-01T05:38:35Z` established that this
was the sole identified assertion error and reconfirmed the reviewed worker and
firewall before-state. Neither projector invoked the wrapper or changed state.

## Exact wrapper stop

The one authorized wrapper invocation started at
`2026-08-01T05:39:35Z` with the exact four approved values:

```text
PATCHYARD_REPLACE_APPROVED=yes
PATCHYARD_REPLACE_APPROVED_SHA256=02073c1c7955ffb343b0a1ba677832ca141da0e697a618cee9b75823fd4b72ab
PATCHYARD_REPLACE_APPROVED_REVISION=672f851ebed3ced133840483e7d4d26da09424e4
PATCHYARD_REPLACE_A115_UNMERGED_APPROVED=yes
```

The wrapper passed its clean-checkout, approved-revision, unmerged-exception,
first binary-digest, and exact action-shape gates. It rendered the exact
reviewed `1 added, 1 changed, 1 destroyed` plan, then invoked
`infra/ansible/converge.sh --check-inputs`. That preflight emitted this exact
terminal line:

```text
/srv/orchestration/patchyard-a120-worker-replacement-plan/infra/ansible/converge.sh: line 12: GH_PATCHYARD_APP_PRIVATE_KEY_FILE: GH_PATCHYARD_APP_PRIVATE_KEY_FILE is required
```

The environment contained the GitHub App ID and installation ID. It did not
contain `GH_PATCHYARD_APP_PRIVATE_KEY_FILE` or
`FACTORY_DASHBOARD_ACCOUNTS_FILE`. The first absent variable stopped execution
at line 12, before the dashboard-file check on line 13.

Because the preflight stopped, the wrapper did not reach its second digest
check or `tofu apply`. It ran neither convergence, the provider-firewall gate,
qualification, the production isolation probe, nor final qualification.

## Complete log and capture defect

The owner-only complete wrapper stdout/stderr log is:

| Field | Value |
| --- | --- |
| path | `/tmp/patchyard-replace-a115-a101.ZUTbIb/authorized-apply-20260801T0539Z.HuKQX7.log` |
| mode and owner | `conductor:conductor 0600` |
| bytes | `3,224` |
| SHA-256 | `497c412a255dd307c15072d6dcafe9b38ffed658d16231fe4ccf04bddcde5383` |

The outer logging harness incorrectly escaped its Bash `PIPESTATUS` array.
After the real wrapper preflight error, the harness wrote the false footer
`wrapper exit status: 0` and then emitted these diagnostics to the command
relay rather than the file:

```text
/bin/bash: line 21: printf: ${pipe_status[0]}: invalid number
/bin/bash: line 24: [[: ${pipe_status[1]}: syntax error: operand expected (error token is "${pipe_status[1]}")
/bin/bash: line 28: exit: ${pipe_status[0]}: numeric argument required
```

The unified outer command returned 2 from that final invalid numeric exit. The
child wrapper's exact numeric status was not preserved, so this record does not
invent it. The fatal required-parameter expansion is independently nonzero
under the same Bash `set -euo pipefail` semantics, but that observation does
not repair the lost child status. The log's zero footer is invalid metadata,
not evidence that the wrapper passed.

The log itself remains unchanged and hashes exactly as recorded. It contains
one preflight-error marker and zero OpenTofu create/apply-complete, Ansible
recap, firewall-readiness, A101-attempt, or isolation-probe markers.

## Declared sequence results

| Layer | Observed result |
| --- | --- |
| approval, revision, first digest, and action-shape gates | PASS |
| converge input preflight | **STOP** - required key-file variable absent |
| OpenTofu apply | not run |
| first convergence | not run |
| second convergence | not run |
| DigitalOcean worker-firewall readiness gate | not run |
| standalone control-plane qualification | not run |
| standalone worker qualification | not run |
| A101 private-VPC management transport | not run |
| production Firecracker isolation probe | not run |
| post-isolation qualification | not run |

## A101 attempt-level evidence

The complete log contains **zero** lines beginning with the repaired probe's
`A101 private-VPC probe target=` prefix. There are therefore no per-attempt
lines to quote, and this record does not manufacture or summarize an A101
verdict. None of the three predeclared outcomes occurred:

- no `attempt=1/5 outcome=pass` line exists;
- no `attempt=1/5 outcome=ssh-failed` or later `outcome=pass` line exists; and
- no five-failure sequence or `outcome=exhausted attempts=5` line exists.

The slow-first-connection hypothesis remains unsettled because execution never
reached A101. This is a pre-apply input stop, not a result about private-VPC
readiness.

## Read-only post-stop state

Read-only state and provider checks from `2026-08-01T05:41:53Z` through
`05:42:05Z` confirmed no cloud mutation:

- OpenTofu state still identifies worker `589089036` as active at public
  `167.172.239.1` and private `10.132.0.11`.
- DigitalOcean still reports exactly the active control plane and the same
  worker as the two Factory droplets. No successor exists.
- Worker firewall `01af87da-4951-4441-a1c8-ddfc0214811b` remains
  `succeeded`, zero-pending, untagged, and attached only to `589089036`.
- The saved plan and both reviewed digests remain unchanged.
- The complete log contains zero apply, converge, firewall-readiness,
  A101-attempt, or isolation markers.

Worker `589089036` remains alive, active, and operationally quarantined. The
Factory still has no qualified worker. No host repair or reuse is permitted by
this record.

## Negative scope and A9 stop

The deliberately stale requirement-1 fixture remains untouched. It still
records host-contract SHA-256
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`,
while current source recomputes to
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`.

No Anthropic credential was issued, no provider request or paid inference ran,
and neither Anthropic limit changed. No requirement-2 spend work resumed. No
requirement-1 refresh, behavioral acceptance, requirement-3 work, credential
rotation, provider qualification-flag change, worker mutation, firewall
mutation, convergence, qualification, or isolation probe followed. All 13
`credential_qualified` flags remain false.

The reviewed stop rule was followed. No input was staged and the wrapper was
not retried. A9 permits no iteration around this terminal operational result
under the current grant.

## Full repository gates

The complete application wrapper returned 0 at the final record head. All
browser-control, Rust unit, integration, property, fixture, documentation,
triage replay, reproducible release, advisory, license, source, vet,
dependency, model, and byte-exact codebase-projection checks passed.

The complete infrastructure wrapper initialized and validated all three
OpenTofu roots. The A101 trust root, stack, independence, worker runtime,
worker qualification, Anthropic spend, and preview checks passed. It returned
1 only for the deliberately stale requirement-1 Anthropic issuance fixture.

The complete Ansible wrapper ran 164 tests in 14 isolated processes. It passed
163; the only failure was the same retained host-contract mismatch. ShellCheck,
all four Ansible lint profiles, all four playbook syntax checks, and the
terminal isolated A101 trust-root check passed.

## A78 operational-record review request

A78 should review the exact pushed record head from a fresh detached worktree
under A87 and inspect the owner-only artifacts in place. It should:

1. recompute the binary, rendered-plan, and complete wrapper-log digests and
   the log's byte count and custody;
2. verify the wrapper passed its approval/revision/first-digest/action gates,
   then stopped at the exact missing key-file preflight before cloud apply;
3. verify the invalid zero footer and outer logger diagnostics are disclosed
   and not used as wrapper-pass evidence;
4. confirm live DigitalOcean and OpenTofu state still identify only unchanged
   quarantined worker `589089036` and its exact firewall attachment;
5. confirm both converges, firewall readiness, all qualification layers, the
   isolation probe, and every A101 attempt line are absent, leaving the timing
   hypothesis unsettled;
6. confirm the no-retry A9 stop, retained stale fixture, negative scope, and
   all 13 false qualification flags; and
7. return PASS or material findings without staging an input, retrying or
   applying the plan, repairing or reusing the worker, accessing Anthropic or
   its Console, issuing a credential, refreshing a fixture, or changing live
   state.
