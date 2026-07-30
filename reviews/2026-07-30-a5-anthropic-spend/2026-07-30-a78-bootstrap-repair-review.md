# A78 immutable-bootstrap repair review

Review target:

- exact repair commit:
  `cec58db1ccf20dbf05e80445cd6845186a6ea379`;
- parent: `ba65448707b3eef9c374523964d49b03cfb4e7ac`;
- reviewer: A78, Claude Code with Opus 5 at requested effort `max`;
- session: `1a887a02-7681-43ce-9248-30659f617629`;
- verdict: **PASS - no material finding**.

The review ran in a clean detached worktree. It did not read repository review
records, edit source, contact DigitalOcean or Anthropic, connect to a host,
generate or apply a plan, or make a provider request. Claude Code reported the
requested model but exposed no independently realized effort field.

## Confirmed behavior

A78 traced the list-form runcmd through Rocky's installed cloud-init source.
Cloud-init renders one `bash -ceu` command; a command failure propagates through
`scripts_user`, makes `cloud-init status --wait` return 1, fails Ansible, and
exits the replacement wrapper before the second converge or qualification.
Metadata refresh remains ordered before runcmd after removal of the `packages`
list. Local schema validation accepted the template.

The review independently confirmed that Rocky's `best=True` default and the
installed `python-unversioned-command` exact dependency explain the failure.
`--nobest` differs from both dependency-erasing `--allowerasing` and
package-skipping `--skip-broken`. Nothing downstream requires latest packages.
`rpm -q` returns nonzero if a named package is absent, and service enablement
cannot run before that assertion.

The full Ansible discovery found the new test and ran 139 cases. The three
bootstrap cases passed; only the two already disclosed requirement-1 live
digest cases failed. A78 reproduced those same two failures at the parent.

Novel disposable mutations of the exact repair included:

- source-only and coordinated `-ceu` to `-cu` changes;
- adding `--skip-broken` while updating the expected command;
- appending `|| true` while updating the expected command; and
- an equivalent folded-YAML representation.

All were rejected. A78 concluded that the repair's source-only contract and
functional failure-boundary tests have teeth.

## Defense-in-depth observations

A78 reported four nonblocking observations:

1. The validator rejects the old `packages` key but does not allowlist the
   complete top-level cloud-init surface. Added `bootcmd`, `write_files`, or
   `yum_repos` siblings can pass the focused test.
2. The functional test executes hard-coded `/bin/bash -ceu` rather than the
   parsed outer argv. Exact structural validation still binds that argv, and
   the mutation no-op guard rejects the obvious coordinated weakening.
3. The same test does not bind the unchanged SSH password/root surface.
4. The restore-drill droplet consumes the template without `ignore_changes`;
   the README's general statement that existing droplets ignore cloud-init
   updates is too broad for a live drill. Existing plan guards fail closed and
   the drill defaults absent.

None is a current source bypass or a regression caused by the repair. A78 also
noted that a human must confirm the repaired user-data command in the fresh
worker plan because the action-shape validator does not inspect that value.

## Reviewer experiments

A78 ran focused and full Ansible discovery, local cloud-init schema validation,
cloud-init call-chain inspection, a parsed-argv fail-fast probe, RPM/DNF option
and dependency inspection, OpenTofu formatting, `ignore_changes` semantics
inspection, current-vs-parent failure comparison, source sweeps, and nine
disposable mutations. It deliberately did not run OpenTofu init/plan, converge,
qualification, SSH, or any provider call.
