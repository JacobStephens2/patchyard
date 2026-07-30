# A78 clean-worker replacement plan review

Review target:

- source before repair: `c65ac0e28cbf994055f7f5a2948eac23e0b5e2ab`;
- source after the one bounded repair: `6c161e91ea0107f6c9d8bb9dac4eb88a27450213`;
- saved binary plan SHA-256:
  `b7d842ffc57702a16726b5413fd29bea4ba93202ce2a993351a67e07b5f29490`;
- rendered plan SHA-256:
  `d4dedabc603d0770c2995fb90b0ceb2f4bda6c8326e8622cde913262dfb2e561`;
- quarantined replacement target: DigitalOcean droplet `588590370`.

A78 ran Claude Code with Opus 5 at requested effort `max` in plan/read-only
mode. Neither review regenerated or applied a plan, accessed DigitalOcean,
connected to a host, changed a provider cap, or made a provider request.
Claude Code exposed no realized-effort field, so this record claims the
requested setting only.

## First review - FAIL

A78 independently verified both artifact hashes, decoded the saved plan through
a bounded projection, and found exactly two acting resources:

- `digitalocean_droplet.worker`: `["create","delete"]`, replacing droplet
  `588590370` from the stock Rocky Linux 9 image;
- `digitalocean_firewall.worker`: `["update"]`, changing only its droplet
  reference while retaining the same rules.

The plan was correct, create-before-destroy, carried no worker snapshot or
volume, and left both control-plane resources as no-op. A78 nevertheless
returned FAIL for three material apply-wrapper defects:

1. **M1 - reviewed plan bytes were not bound at apply.** The approval flag
   admitted any later plan with the same broad resource shape.
2. **M2 - the apply source revision had no explicit binding.** The wrapper
   could converge an unmerged revision without distinguishing A115's specific
   pre-merge authorization from normal merged-revision operation.
3. **M3 - destructive apply preceded converge-input validation.** Missing
   file-based credentials would stop only after cloud replacement.

A78 also observed that the shape gate admitted destroy-before-create and a
firewall no-op. Other defense-in-depth observations covered stale host-key
entries, the bootstrap-to-firewall attachment interval, and explicit new-worker
identity readback.

## Bounded repair

Commit `6c161e9` requires the exact approved plan digest twice, including after
the input preflight immediately before apply. It requires the exact approved
source revision. A merged source follows the normal path; an unmerged source
also requires literal `PATCHYARD_REPLACE_A115_UNMERGED_APPROVED=yes`. It runs
`converge.sh --check-inputs` before cloud apply and accepts only
create-before-destroy worker replacement plus a worker-firewall update.

Executable tests cover plan-digest mismatch, revision mismatch, refusal and
explicit admission of the A115 exception, failed input preflight, event order,
destroy-first refusal, firewall-no-op refusal, and the post-preflight digest
recheck. Seven source-only weakening mutations were rejected:

1. plan-digest comparison;
2. exact-revision comparison;
3. merged-or-A115 gate;
4. pre-apply input preflight;
5. create-before-destroy action;
6. firewall-reference update;
7. post-preflight digest recheck.

## Re-review - PASS

A78 independently verified clean source `6c161e9`, both unchanged plan hashes,
and identical `infra/digitalocean` trees at the plan-generation and apply
commits. It reran the focused tests and independently reconstructed all seven
mutations; all were rejected. A78 ruled M1, M2, M3, and the permissive-action
observation closed and returned **PASS**.

Two non-blocking findings remain:

- `docs/runbook-v0.md` still shows the old one-variable invocation. It fails
  closed at the new required variables but needs a later documentation repair.
- the full Ansible discovery suite retains the two known requirement-1 stale
  live image-recipe and host-contract digests. They block the eventual PR gate,
  not this exact replacement, and were byte-identical at the repair's parent.

A78 also recorded defense-in-depth notes about operator-declared approval
values, later removal of the A115 exception, build-tool preflight breadth, the
small plan-file time-of-check interval, the local `origin/master` ref, textual
coverage of the second digest check, and the out-of-band proof that the
plan-generating Terraform tree was unchanged. None was a material blocker to
the exact reviewed apply.
