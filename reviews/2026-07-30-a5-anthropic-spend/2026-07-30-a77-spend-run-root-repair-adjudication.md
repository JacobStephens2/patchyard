# A77 adjudication - A115 spend run-root repair

## Scope and experiments

The build seat adjudicated A78's review of exact commit
`8cdfeef955ba3d574030e21aff65549219642b86`. No source repair, host mutation,
provider request, credential flow, cap action, worker replacement, or taint-file
change occurred during adjudication.

For M1, three detached disposable worktrees changed one ordering anchor each.
The real checker exited 1 with `ValueError: substring not found` at lines 216,
217, and 220 respectively. None printed `Anthropic spend check: failed` or the
already-applicable complete-launcher digest diagnostic. All three worktrees
were removed after the experiment.

For M2, source inspection found the two `install -d` commands but no `stat`,
`runuser`, or identity-scoped `test` for `$RUN_TMPFS`. A disposable GNU
`install -d` experiment followed a symlink-to-directory and changed the target
from mode 0755 to 0710 while returning success. Live read-only inspection
confirmed `/run/patchyard-worker` is `factory-worker:factory-worker 0700`
with no extended ACL, and `/var/lib/patchyard-worker` is likewise
`factory-worker:factory-worker 0700` while the taint marker is
`root:root 0600`.

## Material findings

### M1 - concede

The factual claim and medium severity are sustained. Complete-source hashing
makes the mutated source fail in principle, but the uncontrolled exception
discards the diagnostic record the checker is designed to publish. That is an
A114 regression and repeats the diagnosed-response failure class requirement 2
has already repaired elsewhere.

The bounded repair, if separately authorized, is to guard every new ordering
anchor and append one controlled run-root-ordering diagnostic on absence or
misordering. The mutation suite must include all three missing-anchor cases and
assert the controlled diagnostic rather than only a nonzero status.

### M2 - concede

The factual claim and medium severity are sustained. The intended permission
chain is correct, but the exact defect being repaired was a realized
identity-specific traversal failure. Source-string binding does not prove the
installed directory's post-condition. A114 requires kernel readback, and the
single remaining A115 attempt should stop before bearer creation if that
post-condition is wrong.

The bounded repair, if separately authorized, is to read back exact
owner/group/mode on both branches and test spend-mode traversal using the
installed `factory-worker` identity before capability creation. The checker
and focused tests must bind the readbacks, the identity, their order, and
fail-closed diagnostics.

## Defense-in-depth observations

### D1 - concede fact; refute material defect classification

Coordinated re-pinning can preserve the positive block and add a later
permission expansion. This is the terminal checker/test trust boundary and
requires visible coordinated edits to the launcher, checker constants, and
checker-digest test. Source-only broadening fails, including A78's additional
`chmod 0777` experiment. No D1 repair is required by this adjudication.

### D2 - concede fact; refute current-repair materiality

GNU `install -d` follows a symlink to a directory, and the worker identity owns
the parent namespace. The condition predates this repair. The qualification
runner selects a 40-bit random run suffix, a reviewed clean replacement starts
without worker processes or runtime residue, and the repair's explicit
root ownership removes access after creation. A pre-existence guard would be
useful defense in depth, but D2 does not defeat the bounded mode repair.

### D3 - concede fact; refute current-repair materiality

The worker-owned state directory permits its identity to unlink the root-owned
taint marker. The observed marker remains present, the build seat will never
clear it or reuse worker `588778422`, and the separately reviewed replacement
operation destroys the entire droplet. The cloud resource disposition, not a
file protected from a hostile root-adjacent service account, is the
authoritative quarantine boundary. This pre-existing observation does not
alter M1/M2 scope.

### D4 - refute as an observed defect; concede hypothetical hardening

Read-only `getfacl` showed no extended or default ACL on the live tmpfs parent.
The proposed exact numeric mode readback therefore covers the observed host.
An ACL-aware assertion could harden against future host-policy drift but is not
evidence that the reviewed repair currently grants more access than claimed.

### D5 - concede fact; refute current-repair materiality

The argv-scoped process detector can miss a process that changes its argv. It
predates and is independent of the run-root permission change. Clean-worker
qualification, whole-resource replacement, and the current no-reuse stop
remain the applicable boundary.

### D6 - refute with evidence

The pinned `tokei` exists at `/var/lib/conductor/.cargo/bin/tokei` and reports
version 14.0.0 with JSON serialization. With the repository's declared tool
path, `tools/check-codebase.sh` passed byte-exactly during both the build-seat
gate and this adjudication. A78's default-PATH limitation is not a projection
gap in the reviewed commit.

## Final disposition and A9 stop

A78's FAIL verdict is sustained. M1 and M2 are conceded material defects, so a
clean-worker replacement may not proceed. The authorized bounded source-repair
iteration has reached adversarial review and is exhausted. Under A9, the build
seat will not silently iterate again.

Continuing requires Jacob to authorize one further bounded source repair of M1
and M2, its tests and source-mutation checks, and a new A78 review. Per the
governance-hygiene instruction, that authorization belongs in this
requirement-2 work record rather than a new numbered ruling. A119 remains
reserved. Until then there is no source edit, replacement plan, worker change,
credential issuance, provider request, cap action, behavioral acceptance,
requirement-3 work, or qualification-flag change.
