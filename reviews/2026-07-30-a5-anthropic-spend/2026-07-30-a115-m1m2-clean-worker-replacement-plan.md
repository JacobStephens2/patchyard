# A115 M1/M2 clean-worker replacement plan

Status: **A78 passed; separately authorized apply stopped at A101 private-VPC
transport after replacement and idempotent convergence passed**

This is the non-executing plan Jacob authorized after A78 passed the bounded
spend run-root M1/M2 repair. The authorization covers plan preparation and a
separate A78 review. It does not authorize applying the plan, modifying a
worker, clearing taint, issuing a credential, making a provider request,
changing either Anthropic limit, starting behavioral acceptance or requirement
3, or changing a provider qualification flag. It is recorded under A115; no
new numbered ruling is minted, and A119 remains reserved.

## Exact source and saved plan

| Field | Value |
| --- | --- |
| plan source revision | `bc496e47bfeb703876495e80b011d88e10c7c232` |
| reviewed technical repair | `520663f25cbaf862d252067e9ca5d933b00b0e9b` |
| technical-tree relation | byte-identical across `infra/`, `worker/`, `tools/`, `policy/`, and `research/isolation/results/` |
| saved binary plan | `/tmp/patchyard-replace-a115-m1m2.HH5bbg/worker-replacement.tfplan` |
| saved binary SHA-256 | `a87568c6707f7d1e5bf581072d70584be117d01e785d1e12ff64ee3665415a59` |
| rendered plan | `/tmp/patchyard-replace-a115-m1m2.HH5bbg/worker-replacement.tfplan.txt` |
| rendered-plan SHA-256 | `d5c222e7b353e67eead2ff391fad1800e2537fe2e8bfedadd471cf3202649891` |
| generation time | `2026-07-30T20:35:30Z` |
| directory mode | `conductor:conductor 0700` |
| both plan-file modes | `conductor:conductor 0600` |

The source checkout was committed and clean. The operator ran the production
tag-firewall guard, initialized only the ignored local OpenTofu directory, read
the encrypted remote state, refreshed live provider state, generated a saved
`-replace=digitalocean_droplet.worker` plan, and ran the repository's
`verify_worker_plan` gate. No cloud apply or host mutation occurred.

The binary plan contains sensitive no-op state values. It remains outside the
repository in its owner-only directory. Review may decode it locally but must
not copy the full JSON, no-op outputs, or secrets into a prompt, transcript,
commit, or PR.

## Mechanical plan projection

The plan has nine resource changes. Seven are exact no-ops. Exactly two act:

| Address | Action | Bound fact |
| --- | --- | --- |
| `digitalocean_droplet.worker` | `["create","delete"]` | replaces target `588778422` create-before-destroy |
| `digitalocean_firewall.worker` | `["update"]` | changes firewall `01af87da-4951-4441-a1c8-ddfc0214811b` from target `588778422` to the not-yet-known replacement ID |

The control-plane droplet and firewall, backup bucket, both Spaces keys,
management SSH key, and backup recovery key are no-op. No restore-drill
resource exists. Only `ansible_inventory`, `worker_ipv4`, and
`worker_private_ipv4` change, all because the replacement addresses are not
known until apply; the control-plane address outputs are no-op.

The replacement uses the declared stock `rockylinux-9-x64` image in `nyc3`,
size `s-8vcpu-16gb`, the existing Factory VPC and management public key, the
`production` tag, no backups, and no restored worker state. The planned
`user_data` identity is SHA-1
`bc402dfdc683c7b582aaab68b6e0ca30b359952d`, equal to an independent render of
the current cloud-init template. That template contains the already-live-proven
coherent `dnf -y --nobest` bootstrap, RPM assertions, and firewalld enablement.

An independent source projection rejected any plan other than the exact two
acting addresses, the exact action order, the exact old worker ID, and an
absent restore-drill resource. Both saved-file digests were read back after
generation.

## Read-only live prerequisites

The readback bracket was `2026-07-30T20:38:18Z` through
`2026-07-30T20:38:21Z`:

- worker `588778422` was active in `nyc3`, size `s-8vcpu-16gb`, at public
  `159.203.171.240` and private `10.132.0.15`;
- its canonical `/var/lib/patchyard-worker/BOUNDARY_TAINTED` remained present
  as `root:root 0600`, still naming the failed run
  `anthropic-s2-operational-20260730-e7b0d43df8`;
- worker firewall `01af87da-4951-4441-a1c8-ddfc0214811b` reported `succeeded`,
  zero pending changes, and only droplet `588778422` attached;
- no live firewall targeted the desired `production` tag;
- the DigitalOcean account was active with 19 of 500 droplet slots used, and
  `nyc3` advertised `s-8vcpu-16gb` as available;
- the Factory control state read `paused=0,full_stop=0,active_work=0`, and the
  backup service was inactive.

These are time-bounded review facts, not promises about a later apply. Every
one must be sampled again within the separately authorized apply bracket.

The current operator shell does not have the two file-valued converge inputs
materialized. This is an intentional apply blocker, not a plan-generation
failure. A later authorized operator must create separate owner-only files for
the GitHub App private key and dashboard account roster and let
`converge.sh --check-inputs` validate them before cloud apply. Neither file nor
its contents belongs in this plan record.

## Proposed apply sequence - not yet authorized

If and only if A78 passes this exact saved plan and Jacob separately authorizes
apply, the operator would:

1. use a clean detached worktree at exact revision
   `bc496e47bfeb703876495e80b011d88e10c7c232` and the exact saved plan above;
2. re-read both digests and owner-only modes, confirm the old worker ID and
   taint, absence of an orphan Factory worker, firewall settled state,
   tag-firewall safety, account headroom, region/size availability, idle
   Factory state, and inactive backup operation;
3. materialize the two converge input files in a separate mode-0700 temporary
   directory as mode-0600 files and run the wrapper with the literal human
   approval, exact revision, exact binary-plan digest, and the explicit A115
   unmerged-source exception;
4. allow `infra/replace-worker.sh apply` to re-decode the action shape, validate
   converge inputs, recheck the plan digest immediately before applying, apply
   the saved plan, converge twice, run full host qualification, run the
   credential-free production isolation probe, and qualify again; and
5. stop and preserve the failure if any step is nonzero. A failed successor is
   quarantined and never manually repaired or reused. No Anthropic credential
   or request follows a failed replacement sequence.

A successful wrapper would still not make requirement 2 ready. The new worker
must first receive an independently recorded identity/address readback, the
destroyed worker must return provider 404 and be absent from the production-tag
inventory, and requirement 1 must be refreshed because its live host-contract
digest is deliberately stale against this source. Any later Console bracket,
cap mutation, or paid provider sequence remains outside this plan.

## Later apply disposition

Jacob later explicitly approved this exact plan. The apply created worker
`588826948`, updated the matching firewall, and destroyed quarantined worker
`588778422`. Both convergence passes succeeded, the second with zero changes,
and the standalone control and worker qualifications passed. The wrapper then
stopped because the first control-to-worker A101 management probe timed out to
`10.132.0.11:22`.

No isolation or provider phase ran. A later read-only invocation of the same
installed management probe succeeded without a state change, and DigitalOcean
reported the firewall settled with zero pending changes. Provider attachment
propagation is therefore plausible but remains an inference. The failed
sequence and operational quarantine are recorded in
`2026-07-30-a115-m1m2-clean-worker-replacement-attempt.md`.

## Review questions

A78 must independently:

1. verify both saved-plan digests and owner-only modes without publishing
   sensitive plan contents;
2. decode the exact binary and confirm the full resource, output, target,
   create-before-destroy, firewall-rule, stock-image, no-snapshot/no-volume,
   cloud-init, and no-restore shape;
3. verify the apply wrapper binds the exact digest and source revision, runs
   input preflight before cloud mutation, and rechecks the digest immediately
   before apply;
4. verify the operational source differs from the prior A78-reviewed repair
   only by review/evidence records and generated metrics;
5. mutation-check the plan and source bindings, including foreign attributes,
   output-only changes, target substitution, action reordering, digest/revision
   weakening, input-preflight removal, and post-preflight digest removal; and
6. return PASS or material findings without regenerating or applying the plan,
   accessing a host or provider Console, issuing a credential, or making a
   provider request.
