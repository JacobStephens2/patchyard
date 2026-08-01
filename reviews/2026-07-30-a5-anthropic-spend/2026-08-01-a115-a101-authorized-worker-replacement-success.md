# A115 post-A101 authorized worker replacement success

Status: **the exact reviewed replacement completed; both converges, the
provider-firewall gate, both complete qualification passes, and the production
isolation probe passed; the Factory has a qualified worker again**

This is the operational record for Jacob's second explicit `AUTHORIZE APPLY`
against the unchanged A78-reviewed post-A101 worker-replacement plan. The first
grant stopped correctly before cloud apply because its authorization omitted
two controller-local input paths. A78 verified that stop against live state,
assigned the omission to the review prompt rather than the build seat, and
ruled that the unchanged plan required no regeneration or new plan review.

The second grant covered only the wrapper's built-in apply, two converges,
DigitalOcean firewall readiness gate, first qualification, production
isolation probe, and final qualification. The wrapper ran once. No retry,
repair, plan regeneration, or out-of-band host action occurred.

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
| A78 preflight-stop verdict | PASS, no build-seat finding ([review](https://github.com/JacobStephens2/patchyard/pull/79#issuecomment-5150076624)) |
| retired worker | `589089036`, public `167.172.239.1`, private `10.132.0.11`, created `2026-07-31T22:10:03Z` |
| replacement worker | `589159466`, public `165.227.77.173`, private `10.132.0.15`, created `2026-08-01T06:14:48Z` |
| worker firewall | `01af87da-4951-4441-a1c8-ddfc0214811b` |

The wrapper ran from the existing dedicated worktree, detached and clean at the
exact approved source. The prior operational-record branch remained anchored
at `49b834c8a7550a5b635b328d79a575fddfb9dbe0` until recording resumed after the
wrapper. The shared checkout remained clean on `master` at
`43303c95b217f4da9f097d5ab4367bf52d3b0218`.

The approved source contains the reviewed bounded A101 transport:
`readonly PROBE_MAX_ATTEMPTS=5` and the terminal
`outcome=exhausted attempts=%d total_elapsed_seconds=%d` emission are each
present once in the installed management-SSH template.

## Pre-apply bracket

The final read-only bracket ran from `2026-08-01T06:12:04Z` through
`06:12:30Z` and established:

- the operator worktree was clean at exact source `672f851e`;
- the binary and rendered plan remained owner-only and matched both reviewed
  digests;
- the decoded binary still contained nine resource changes, with exactly two
  non-no-ops: ordered `["create","delete"]` for
  `digitalocean_droplet.worker` and `["update"]` for
  `digitalocean_firewall.worker`;
- the plan remained bound to worker `589089036`, creation timestamp
  `2026-07-31T22:10:03Z`, and exact public/private addresses
  `167.172.239.1` / `10.132.0.11`;
- OpenTofu state and live DigitalOcean both identified the same active worker;
- the account was active with 19 of 500 droplet slots used, and the only
  Factory droplets were active control plane `586468414` and worker
  `589089036`;
- firewall `01af87da-4951-4441-a1c8-ddfc0214811b` was live `succeeded`, had
  zero pending changes and no tags, and attached only worker `589089036`;
- no live firewall targeted the broad `production` tag;
- public image `rockylinux-9-x64`, ID `234045074`, and size
  `s-8vcpu-16gb` were available in `nyc3`; and
- all 13 provider `credential_qualified` values were false.

OpenTofu's stored firewall `status` field read `waiting` while the direct
provider read was `succeeded` with zero pending changes. The acting attachment,
ID, and tags matched in both projections; the live provider status was the
readiness fact.

The first source-marker projection in the bracket queried `qualify.sh` rather
than the management-SSH template and therefore recorded two path-specific zero
counts. A correction was appended before apply, identified the wrong file
explicitly, and asserted one max-attempt declaration and one exhausted marker
in the actual installed template. This was a read-only projector mistake, not
a failed source gate or wrapper attempt.

The complete owner-only bracket log is:

| Field | Value |
| --- | --- |
| path | `/tmp/patchyard-replace-a115-a101.ZUTbIb/pre-apply-bracket-20260801T061204Z.3ISqN8.log` |
| mode and owner | `conductor:conductor 0600` |
| bytes | `3,268` |
| SHA-256 | `337734841e457be58016f60aa04aa1a4532aade845ae1a7c7a7046e3d8b50acf` |

## Controller-local secret inputs

The existing GitHub App private key and exact three-account dashboard roster
were materialized at `2026-08-01T06:14:11Z` into the separate
`/tmp/patchyard-replace-inputs.sygz72` directory. The directory was
`conductor:conductor 0700`; both files were `conductor:conductor 0600`.

The private key parsed without output. The dashboard JSON contained exactly the
Git-controlled identities and roles - two `factory_admin` and one
`factory_submit` - and every password met the 14-character minimum. Neither
secret value was printed or logged. Before the wrapper began, the exact approved
source and plan digest were rechecked and:

```text
converge_inputs_valid
```

was observed from `infra/ansible/converge.sh --check-inputs`. The wrapper's own
identical preflight emitted the same line before its second plan-digest check.

Immediately after the wrapper stopped at `2026-08-01T06:54:32Z`, both files
were removed with `shred --remove=unlink --zero`, then the empty directory was
deleted. Absence was rechecked before any log hashing or post-run cloud read.

The secret-free input-custody record is:

| Field | Value |
| --- | --- |
| path | `/tmp/patchyard-replace-a115-a101.ZUTbIb/input-preflight-20260801T061410Z.oc0k2l.log` |
| mode and owner | `conductor:conductor 0600` |
| bytes | `716` |
| SHA-256 | `ee53fa1477d86fc5fcfd7c76879322a59045bdd7330aa023031bfa560e359a9a` |

## Exact apply and convergence

The wrapper passed its clean-checkout, approved-revision, explicit unmerged
exception, first binary-digest, exact action-shape, controller-input, and second
binary-digest gates. OpenTofu then emitted exactly:

```text
Apply complete! Resources: 1 added, 1 changed, 1 destroyed.
```

It:

- created worker `589159466` from the declared stock Rocky Linux 9 image at
  public `165.227.77.173` and private `10.132.0.15`;
- updated only firewall `01af87da-4951-4441-a1c8-ddfc0214811b` to attach the
  replacement; and
- destroyed quarantined worker `589089036`.

First convergence passed after building the production parity root filesystem
and installing the reviewed runtime:

```text
factory-control.example.com : ok=221  changed=15   unreachable=0    failed=0    skipped=18   rescued=0    ignored=0
factory-worker.example.com : ok=94   changed=71   unreachable=0    failed=0    skipped=5    rescued=0    ignored=0
```

Second convergence was fully idempotent:

```text
factory-control.example.com : ok=216  changed=0    unreachable=0    failed=0    skipped=22   rescued=0    ignored=0
factory-worker.example.com : ok=84   changed=0    unreachable=0    failed=0    skipped=9    rescued=0    ignored=0
```

The bounded provider-firewall gate passed on its first attempt:

```text
worker firewall readiness: pass (firewall=01af87da-4951-4441-a1c8-ddfc0214811b worker=589159466 attempt=1)
```

## First qualification and A101 result

The first complete qualification pass produced, in order:

- standalone control-plane qualification: PASS;
- standalone worker qualification: PASS;
- A101 control-plane private-VPC probe: PASS on attempt 1;
- A101 worker private-VPC probe: PASS on attempt 1;
- orchestration break-glass rejection while blocked: PASS by progression;
- worker qualification through the private management path: PASS;
- break-glass restoration: PASS by progression; and
- terminal independence checker: PASS.

These are the complete attempt-level A101 lines from the first qualification,
quoted verbatim:

```text
A101 private-VPC probe target=control attempt=1/5 outcome=pass attempt_elapsed_seconds=1 total_elapsed_seconds=1 ssh_exit_status=0
A101 private-VPC probe target=worker attempt=1/5 outcome=pass attempt_elapsed_seconds=0 total_elapsed_seconds=0 ssh_exit_status=0
```

The worker passed on attempt 1 with `total_elapsed_seconds=0`. Under the
predeclared interpretation, the historical stops had a different cause and the
slow-first-connection hypothesis is excluded. This result does not identify or
assign the different historical cause.

The first qualification ended with:

```text
A101 management transport: pass
independence check: runtime roles and reconcile source contain no orchestration-host dependency
```

## Production isolation and final qualification

The production isolation runner emitted the nonfatal freshness observation
`snapshot stale: age=10d warning=7d`, then completed the real Firecracker run:

```text
factory worker run complete: s4-probe-20260801-d58e4d142e
isolation_probe_result=/var/lib/patchyard/artifacts/worker-replacement-20260801T065324Z run_id=s4-probe-20260801-d58e4d142e
```

No snapshot refresh or other action followed the warning. The authorized probe
completed and left three files in the named evidence directory.

The final complete qualification repeated every layer successfully. These are
its complete attempt-level A101 lines, again quoted verbatim rather than
collapsed into a verdict:

```text
A101 private-VPC probe target=control attempt=1/5 outcome=pass attempt_elapsed_seconds=1 total_elapsed_seconds=1 ssh_exit_status=0
A101 private-VPC probe target=worker attempt=1/5 outcome=pass attempt_elapsed_seconds=0 total_elapsed_seconds=0 ssh_exit_status=0
```

It again ended with private-path worker qualification, break-glass restoration,
`A101 management transport: pass`, and the terminal independence-check pass.
There were four attempt lines total - two in each qualification pass - with no
`ssh-failed`, `connect-timeout`, `ssh-timeout`, detail, or exhausted line.

## Complete wrapper log and status capture

The complete wrapper stdout/stderr log is:

| Field | Value |
| --- | --- |
| path | `/tmp/patchyard-replace-a115-a101.ZUTbIb/authorized-apply-staged-20260801T061410Z.YnXRbA.log` |
| mode and owner | `conductor:conductor 0600` |
| bytes | `415,814` |
| SHA-256 | `cd15c1319fe68e2c0e1a57b865ec3ef99c7567e44800843210baae0ba11e44dd` |

The known A114 status-footer defect was not changed or bundled into this live
run. This capture appended no synthetic `wrapper exit status` footer at all.
The outer `pipefail` pipeline returned 0, which means both the wrapper and its
`tee` sink returned 0, and the log independently contains exactly one apply
completion, two Ansible recaps, one firewall pass, two full qualification
sequences, four A101 attempt lines, and one isolation result. No unreliable
footer is used as success evidence.

## Read-only post-success state

Read-only OpenTofu, provider, and host checks from
`2026-08-01T06:56:22Z` through `06:56:37Z` established:

- OpenTofu state identifies worker `589159466`, created
  `2026-08-01T06:14:48Z`, active at public `165.227.77.173` and private
  `10.132.0.15`;
- DigitalOcean reports exactly control plane `586468414` and worker
  `589159466` as the two Factory droplets, both active;
- firewall `01af87da-4951-4441-a1c8-ddfc0214811b` is live `succeeded`, has
  zero pending changes and no tags, and attaches only worker `589159466`;
- retired worker `589089036` returns provider HTTP 404;
- no live firewall targets the broad `production` tag;
- worker cloud-init is done; `sshd`, `firewalld`, and the worker egress service
  are active;
- the worker has no `BOUNDARY_TAINTED` marker, runtime-root entry, temporary
  runtime entry, network namespace, Firecracker process, or jailer process;
- the worker's installed policy still contains exactly 13 false
  `credential_qualified` values;
- control-plane PostgreSQL, dashboard, supervisor, and Caddy are active, the
  one-shot backup service is inactive, and dashboard health is `ok`;
- the credential-free control-plane checkout is clean at exact approved source
  `672f851ebed3ced133840483e7d4d26da09424e4`;
- the control-plane isolated-child runtime root is empty; and
- isolation evidence directory
  `/var/lib/patchyard/artifacts/worker-replacement-20260801T065324Z`
  exists with three files.

The complete owner-only post-success readback is:

| Field | Value |
| --- | --- |
| path | `/tmp/patchyard-replace-a115-a101.ZUTbIb/post-success-readback-20260801T065622Z.9oYRpy.log` |
| mode and owner | `conductor:conductor 0600` |
| bytes | `2,815` |
| SHA-256 | `1f89ef69f9d14ffadadcf649276b5ebcb3d8b70aaf0e2843ba0e98bdc9249845` |

Worker `589159466` is the Factory's qualified worker. It is not quarantined.
The Factory has no second worker and no partial replacement resource.

## Negative scope

The deliberately stale requirement-1 Anthropic issuance fixture remains
untouched. It still records host-contract SHA-256
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`,
while current source recomputes to
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`.

No Anthropic credential was issued, no provider request or paid inference ran,
and neither Anthropic Console limit changed. No requirement-1 fixture refresh,
behavioral acceptance, requirement-3 work, credential rotation, or provider
qualification-flag change occurred. All 13 `credential_qualified` flags remain
false. Requirement-2 spend work did not resume and still requires a separate
explicit authorization from Jacob.

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

1. recompute the plan, rendered-plan, bracket, input-custody, complete apply,
   and post-success digests and byte counts;
2. verify `converge_inputs_valid` preceded the wrapper and that both staged
   secret files and their directory were removed immediately after it stopped;
3. decode the binary plan and match the exact one-add, one-change, one-destroy
   apply to live DigitalOcean and OpenTofu state;
4. verify both converge recaps, the attempt-1 firewall gate, both complete
   qualification sequences, and the isolation artifact;
5. compare all four verbatim A101 attempt lines to the complete log and confirm
   that both worker probes passed on attempt 1 with zero total elapsed seconds;
6. verify retired worker `589089036` is absent, successor `589159466` is the
   sole clean qualified worker, and its live firewall attachment is settled;
7. confirm the known A114 footer defect was not modified, no unreliable footer
   was used, the stale fixture remains stale, all 13 flags remain false, and
   the negative scope held; and
8. return PASS or material findings without applying, converging, qualifying,
   running another isolation probe, accessing Anthropic or its Console,
   refreshing a fixture, resuming spend work, or changing live state.
