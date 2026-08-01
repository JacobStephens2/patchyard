# A77 adjudication: runner, guest, and install-task binding review

## Scope and method

The build seat adjudicated every A78 observation against exact technical commit
`62d2502be0fab15c7e5740390d7824077a995e4e`. Experiments used independently
constructed disposable repository copies. They did not use A78's scratch files
and caused no provider, credential, worker, cap, or external-state action.

## Target-findings adjudication

**Concede the factual experiments and sustain A78's closure of both target
findings.** The complete runner, guest, and worker task digests recompute to the
three checker constants, and the checker recomputes to its focused-test
constant. All 24 focused tests pass, including twenty-six real-checker mutation
subcases. A source-only weakening of any reviewed target file without
coordinated pin changes fails.

The runner's installed launcher and one-shot comparisons execute before the WIF
exchange. Consequently, later installed-path overwrites outside the task digest
can make a run fail closed, but cannot silently redirect the paid transfer while
the reviewed runner remains intact.

## Observation dispositions

### A78-D1: concede

The build seat inserted a post-install `sed` command into
`build-parity-image` that removes the `ETA_CREDENTIAL` absence assertion from
the rootfs copy of the guest, then updated only the ordinary recipe pin to the
recomputed
`399fecdd472c081791254387442ee6ebc89d3779b73d5a4cefeacb4cd37f67af`.
Worker-runtime, worker-qualification, the spend checker, and all 24 focused
tests exited zero.

The observation is real and its defense-in-depth classification is sustained.
The host launcher and runner independently enforce the qualification facts, so
neutralizing a guest duplicate assertion does not create a qualifying false
positive or another provider request. The documentation sentence claiming the
image recipe is a complete binding of the guest surface is also conceded as
inaccurate. It is recorded rather than repaired here because the authorized
post-A118 repair loop is exhausted and A78 found no material defect in the
bounded target.

### A78-D2: concede

The build seat added a later Ansible copy task with destination
`/usr/local/sbin/{{ item }}`, then coordinately updated the complete task and
checker pins. The task source became
`32f6421281190e551217b924d8a35e84848c6c22f74f27d287ff80c0a7a89d8e`
and the checker became
`680e3cb5f6722df4721326269041f452fe289d49edf0080f026b1027a30f2108`.
The checker and all 24 focused tests exited zero.

The literal singular-destination check is therefore defense in depth. The
complete task digest is the reviewed primary binding and rejects the same
source change without coordinated re-pinning.

### A78-D3: concede

The build seat appended a handler that listens to the existing `Restart worker
egress policy` notification and overwrites the launcher. The checker and all 24
focused tests exited zero. This establishes that the task digest is not a
complete Ansible execution-graph binding. The pinned runner still detects the
installed mismatch before issuance, so severity remains defense in depth and
the target finding stays closed.

### A78-D4: concede

The build seat made two guest delivery comparisons self-referential, updated
the guest digest in checker and test, and updated the checker digest in the
test. The mutated guest digest was
`5933829e036dce817d65632dc56b0d2657842c3979716e0ca802fe3873688baf`
and the mutated checker digest was
`d2c318903487a229c714ee33003de951fa6771b869011a494ea5da540a02a03a`.
The checker and all 24 focused tests exited zero.

This is the terminal trust boundary of repository tests, not an in-scope
source-binding bypass: the coordinated edit changes the source, checker, and
test that reviews the checker. It remains visible in the PR test diff and
requires human and adversarial review.

### A78-D5: concede with scope clarification

Deleting the spend-checker invocation from `tools/check-infra.sh` left all 24
focused tests green. This unwires one direct invocation, not all enforcement:
`tools/check-ansible.sh` still discovers the focused test that independently
checks the source and checker digests. The observation is real and limited as
A78 described.

### A78-D6: concede

The new complete-file pins deliberately couple unrelated edits in the shared
guest and worker-task files to Anthropic-spend constant review. That maintenance
cost is the authorized structural tradeoff that closes non-local Bash and
Ansible bypasses. It is not a functional regression.

## Final adjudication

A78's **PASS** verdict is sustained. Both authorized target findings are
closed. There is no material finding to repair or escalate. The six conceded
observations remain explicitly defense in depth; the inaccurate recipe-binding
sentence is now an acknowledged documentation limitation rather than evidence
for qualification.

The third post-A118 operational source-repair grant is exhausted. No further
source repair, worker plan or mutation, provider request, credential issuance,
cap action, behavioral acceptance, requirement-3 work, or qualification-flag
change follows from this adjudication.
