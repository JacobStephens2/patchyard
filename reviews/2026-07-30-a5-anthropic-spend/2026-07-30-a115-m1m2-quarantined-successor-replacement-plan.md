# A115 M1/M2 quarantined-successor replacement plan

Status: **A78 passed; separately authorized apply stopped at A101 private-VPC
transport after replacement and idempotent convergence passed**

Jacob explicitly authorized "a new clean-worker replacement plan plus A78
review." This operational grant is recorded under A115 and does not mint a new
decision-log ruling. A119 is already taken. The grant authorizes only plan
generation, exact evidence recording, and a fresh read-only A78 review. It does
not authorize applying the plan, modifying or reusing the current worker,
clearing a taint marker, issuing a credential, making a provider request,
changing either Anthropic limit, refreshing requirement 1, starting behavioral
acceptance or requirement 3, or changing a provider qualification flag.

## Exact source and saved plan

| Field | Value |
| --- | --- |
| operational plan source | `d8b2955c4de050a67d932d763fd58f2509f34df5` |
| reviewed technical repair | `520663f25cbaf862d252067e9ca5d933b00b0e9b` |
| technical-tree relation | byte-identical across `infra/`, `worker/`, `tools/`, `policy/`, and `research/isolation/results/` |
| saved binary plan | `/tmp/patchyard-replace-a115-m1m2-successor.4Dq9kk/worker-replacement.tfplan` |
| saved binary SHA-256 | `62adfcaac371203a5c9127ed307f29fdbd1593e2f2a466ae22836551e9fd91c3` |
| rendered plan | `/tmp/patchyard-replace-a115-m1m2-successor.4Dq9kk/worker-replacement.tfplan.txt` |
| rendered-plan SHA-256 | `b77a32f12f3480e08496d6b8ff83fb38dc6c2b300999649ff0b9ad94169cafae` |
| binary generation time | `2026-07-30T22:28:35Z` |
| rendered-plan generation time | `2026-07-30T22:28:56Z` |
| directory mode | `conductor:conductor 0700` |
| both plan-file modes | `conductor:conductor 0600` |

The source checkout was committed and clean. The operator ran the production
tag-firewall guard, initialized only the ignored local OpenTofu directory, read
the encrypted remote state, refreshed live provider state, generated a saved
`-replace=digitalocean_droplet.worker` plan, and ran the repository's
`verify_worker_plan` gate. No cloud apply or host mutation occurred.

The first invocation produced no plan and made no cloud change because
`init -reconfigure` timed out querying the OpenTofu registry for the already
cached TLS provider after two attempts. One identical retry initialized from
the locked cached providers and generated the artifact above. This was an
external dependency-lookup retry, not a source repair or a second plan.

The binary plan contains sensitive no-op state values. It remains outside the
repository in its owner-only directory. Review may decode it locally but must
not copy the full JSON, no-op output values, or credentials into a prompt,
transcript, commit, or PR.

## Mechanical plan projection

The plan has nine resource changes. Seven are exact no-ops. Exactly two act:

| Address | Action | Bound fact |
| --- | --- | --- |
| `digitalocean_droplet.worker` | `["create","delete"]` | `replace_by_request` replaces current worker `588826948` create-before-destroy |
| `digitalocean_firewall.worker` | `["update"]` | changes firewall `01af87da-4951-4441-a1c8-ddfc0214811b` from target `588826948` to the not-yet-known replacement ID |

The control-plane droplet and firewall, backup bucket, both Spaces keys,
management SSH key, and backup recovery key are no-op. No restore-drill
resource exists. Only `ansible_inventory`, `worker_ipv4`, and
`worker_private_ipv4` change, all because the replacement addresses are not
known until apply. Every control-plane, backup, and restore output is no-op.

The replacement uses the declared stock `rockylinux-9-x64` image in `nyc3`,
size `s-8vcpu-16gb`, the existing Factory VPC and management public key, the
`production` tag, no backups, no IPv6, enabled monitoring and droplet agent,
no attached volume, and no restored worker state. The plan's `user_data`
identity is SHA-1 `bc402dfdc683c7b582aaab68b6e0ca30b359952d`.
Substituting the plan-bound management public key into the current template in
an independent render reproduced the same SHA-1 without displaying the key.

The plan contains one provider-refresh drift entry for the worker firewall. It
moves the prior saved state from `waiting` with the old worker removal and new
worker attachment pending to `succeeded` with no pending changes. Its droplet
attachment is `588826948` on both sides. This is the settled-state refresh from
the preceding failed sequence, not another planned action.

An independent projection rejected any acting address beyond the exact worker
and worker firewall, any action other than the ordered replacement and update,
a target other than `588826948`, or a present restore-drill resource. Both
saved-file digests were read back after generation. As previously adjudicated,
the durable apply binding is the twice-checked exact encrypted-plan digest;
`verify_worker_plan` itself is an action-shape gate rather than a complete
target/attribute/output predicate.

## Read-only live prerequisites

The pre-plan readback bracket was `2026-07-30T22:25:25Z` through
`2026-07-30T22:27:27Z`:

- worker `588826948` was active in `nyc3`, size `s-8vcpu-16gb`, stock image
  `rockylinux-9-x64`, at public `134.209.170.42` and private `10.132.0.11`;
- its canonical `BOUNDARY_TAINTED` marker was absent, as expected because the
  prior wrapper stopped before isolation or provider runtime;
- the committed failed-sequence record nevertheless makes worker `588826948`
  operationally quarantined and ineligible for repair or reuse;
- the production tag contained only that worker and Factory control plane
  `586468414`;
- worker firewall `01af87da-4951-4441-a1c8-ddfc0214811b` reported `succeeded`,
  zero pending changes, and only worker `588826948` attached;
- the production tag-firewall guard passed: no live firewall targeted the
  desired `production` tag;
- the DigitalOcean account was active with 19 of 500 droplet slots used, and
  NYC3 advertised the required size as available;
- Factory control state was `paused=0,full_stop=0,active_work=0`, with zero
  pending or executing controls; and
- PostgreSQL, dashboard, supervisor, Caddy, and Unix-socket health passed while
  the backup service was inactive.

One initial read-only SQL probe used an incomplete terminal-state list and
reported 21 historical runs as active. The repository's canonical backup
predicate includes the full terminal-state set and proposer work. Repeating
that exact predicate returned zero, and the control queue independently
returned zero. The earlier number was a probe-definition error, not live work.
An earlier default-socket attempt also failed before reading the database; the
correct restricted socket is `/run/patchyard-postgres`. Neither probe changed
state.

These are time-bounded plan facts, not promises about a later apply. Every
prerequisite must be sampled again inside a separately authorized apply
bracket. The absent host marker cannot substitute for the committed operational
quarantine, and no operator may use that absence to repair or reuse this host.

## Proposed apply sequence - not authorized

If and only if A78 passes this exact saved plan and Jacob separately authorizes
apply, the operator would:

1. use a clean detached worktree at exact revision
   `d8b2955c4de050a67d932d763fd58f2509f34df5` and the exact saved binary plan;
2. reread both artifact digests and owner-only modes, bind current worker
   `588826948` to this committed operational-quarantine record, confirm no
   orphan Factory worker, and recheck the firewall, production-tag guard,
   account headroom, region/size availability, idle Factory state, inactive
   backup operation, control health, and all 13 false qualification flags;
3. materialize the existing GitHub App key and dashboard account roster in a
   separate mode-0700 temporary directory as mode-0600 files, validate them
   with `converge.sh --check-inputs`, and invoke the wrapper with the literal
   human approval, exact revision, exact binary digest, and explicit A115
   unmerged-source exception;
4. allow `infra/replace-worker.sh apply` to re-decode the action shape, recheck
   the plan digest after input preflight, apply only the saved plan, converge
   twice, qualify both hosts, run the credential-free production isolation
   probe, and qualify again; and
5. stop and preserve any nonzero result. Any failed successor is operationally
   quarantined and must not be manually repaired or reused.

A successful wrapper would still not authorize an Anthropic action or satisfy
requirement 2. The operator must first record the new worker identity and
addresses, provider 404 for old worker `588826948`, absence of the old worker
from the production-tag inventory, settled firewall attachment, and a refreshed
requirement-1 live fixture because its host-contract digest is deliberately
stale. Any later Console bracket, cap mutation, credential issuance, or paid
provider sequence requires separate authority.

## Build-seat verification before A78

The focused replacement suite passed all seven tests. The focused Anthropic
spend suite passed all 25 tests, including its 36 real-checker source mutations
of run-root mode, consuming identity, traversal, and ordering bindings. The
unmodified spend checker passed, the regenerated codebase-metrics projection
passed, and `git diff --check` passed. An independent fail-closed projection of
the saved plan required the exact two acting addresses and ordered actions,
target `588826948`, exact firewall ID, absent restore resource, and exact three
acting output names. Seven in-memory mutations - acting-address substitution,
action reversal, worker-target substitution, firewall-ID substitution,
restore-resource insertion, extra acting output, and missing acting output -
were all rejected while the unmodified artifact passed.

The complete application wrapper passed: 39 browser-control tests passed with
the one Docker-only integration skip; every Rust unit, integration, property,
fixture, and database test passed; the release binary reproduced byte-for-byte;
and dependency, advisory, model, and generated-projection checks passed.

The complete infrastructure wrapper initialized and validated all three
OpenTofu roots and passed its stack, independence, worker-runtime, and
worker-qualification checks. It stopped only at the deliberately stale
requirement-1 host-contract fixture: live
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`
versus current
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`.
The complete Ansible wrapper likewise passed 139 of 140 tests and stopped only
on that exact known mismatch. Refreshing that fixture before a successful new
worker exists would falsely claim a live rerun, so this plan does not alter it.

## Review questions

A78 must independently:

1. verify both saved-plan digests and owner-only modes without publishing
   sensitive plan contents;
2. decode the exact binary offline and confirm every resource and output
   action, target `588826948`, create-before-destroy ordering, firewall rules,
   stock image, VPC and management key, no snapshot/volume/restore shape,
   cloud-init identity, and disclosed provider-refresh drift;
3. verify the apply wrapper binds the exact digest and source revision, runs
   input preflight before cloud mutation, and rechecks the digest immediately
   before apply;
4. verify operational source `d8b2955` is technically byte-identical to the
   A78-reviewed repair `520663f` across the five named technical trees, all 13
   qualification flags remain false, and no bare Anthropic credential was
   introduced;
5. mutation-check plan and source bindings, including foreign acting
   resources, output-only changes, target substitution, action reordering,
   digest/revision weakening, input-preflight removal, and post-preflight
   digest removal; and
6. assess whether the absent marker plus explicit committed operational
   quarantine is represented without suggesting current-worker reuse, then
   return PASS or material findings without regenerating or applying the plan,
   accessing a host or provider Console, issuing a credential, or making a
   provider request.

## A78 result and A77 adjudication

A78 reviewed exact plan-record commit
`9c40b086a3c59a5955ebd484f942319e02786c68` and the two saved artifacts above
with Claude Code 2.1.220 and `claude-opus-5` at requested effort `xhigh`. The
reviewer returned **PASS with no material findings** after a complete offline
decode, 7 of 7 replacement tests, 25 of 25 spend tests, the spend checker and
codebase projection, 17 rejected plan mutations, and a corrected independent
31-case wrapper harness. All 12 attacks on the unmodified wrapper were refused;
13 of 16 source mutations reached mocked apply and proved their guards
load-bearing, while the other three remained stopped by an independent guard.

A78 confirmed that these exact bytes replace rather than repair or reuse worker
`588826948`, that the explicit operational quarantine remains binding despite
the absent automated marker, and that the deliberately stale requirement-1
fixture must not be refreshed before a successful replacement. The reviewer
withdrew an initial A119 numbering observation after receiving the governing
cross-branch coordination fact. Eight remaining nonblocking observations and
their A77 dispositions are recorded in
`2026-07-30-a78-quarantined-successor-replacement-plan-review.md` and
`2026-07-30-a77-quarantined-successor-replacement-plan-adjudication.md`.

No repair or plan regeneration followed the PASS.

## Authorized apply disposition

Jacob later explicitly authorized applying these exact reviewed bytes. The
wrapper created successor worker `588858421`, moved only the reviewed firewall
attachment, destroyed operationally quarantined worker `588826948`, converged
twice, and passed the standalone control and worker qualifications. The second
convergence was fully idempotent with zero changes on both hosts.

The wrapper then stopped nonzero when the first A101 control-to-worker
private-VPC probe timed out to `10.132.0.15:22`. The failed probe was not
retried. No production isolation probe, requirement-1 refresh, Anthropic
credential or request, Console action, behavioral acceptance, requirement-3
work, credential rotation, or qualification-flag change followed. Successor
`588858421` is operationally quarantined and ineligible for repair or reuse.
The exact apply boundary, log digest, post-stop readbacks, and stop disposition
are recorded in
`2026-07-31-a115-m1m2-quarantined-successor-replacement-attempt.md`.
