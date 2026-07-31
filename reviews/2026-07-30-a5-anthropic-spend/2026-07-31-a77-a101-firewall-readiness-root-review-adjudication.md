# A77 adjudication - A101 readiness root-of-trust review

## Disposition

The build seat independently resolved all five A78 findings:

| Finding | A77 disposition |
| --- | --- |
| F1 repository Python shadowing | **concede, Critical sustained** |
| F2 package and name-only census gaps | **concede, High sustained** |
| F3 workflow skips repaired wrapper | **concede, High sustained** |
| F4 unbound invoked checkers | **concede, Medium sustained** |
| F5 one binder for `tofu.sh` | **concede the fact; refute separate materiality as subsumed by F1** |

No repair follows. The authorized root repair completed its fresh A78 loop and
the review failed. A9 requires this stop and failure record. Any next source
sequence needs a new explicit bounded authorization under A115 and must not
mint another numbered ruling.

## F1 experiment - conceded

In a new detached worktree at exact reviewed head, A77 added a guarded
`/nonexistent/wget` path to the production helper. Its real SHA-256 became
`9301f3dad204ac6d314ca32d0f05d49cd1d6d0fd094dabffd7937f9f20a596c8`
instead of pinned
`5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba`.

A77 then added `tools/hashlib.py`. The shim uses the standard `_hashlib`
extension for every digest but maps only that exact mutant digest to the pinned
value. The workflow's literal root-checker SHA remained valid. Both:

```text
python3 tools/check-a101-readiness-root.py
python3 tools/check-anthropic-spend.py
```

exited 0. Runtime inspection showed the imported module was the added
repository file. Running the unchanged checker as:

```text
python3 -I tools/check-a101-readiness-root.py
```

exited 1 and reported the exact mutant helper digest. F1 is independently
conceded at Critical.

## F2 experiments - conceded

A77 added `infra/ansible/tests/__init__.py` with a harmless private marker
write. The root checker passed, a fast censused module passed, and the marker
proved the uncensused initializer executed inside the test process.

A77 then replaced the unbound `test_anthropic_issuance.py` with one trivial
passing case. The root checker passed and direct execution ran one green test
instead of the 20-case requirement-1 contract. These independently reproduce
both the executable-package and name-only content gaps. F2 is conceded at
High.

## F3 experiment - conceded

At exact head, the workflow runs `tools/check-infra.sh` at lines 57-58 and the
Ansible wrapper only in the next unconditional step at lines 60-61. There is no
`continue-on-error`, `if: always()`, or equivalent.

The build seat's exact-source infrastructure run already independently passed
the root, OpenTofu validation, stack, independence, worker-runtime,
worker-qualification, and spend checker, then exited 1 at the stale issuance
checker. Its output contained no preview-runtime result. GitHub's normal failed
step semantics therefore skip the later Ansible step. F3 is conceded at High.

## F4 experiment - conceded

A77 replaced only `tools/check-anthropic-issuance.py` with a two-line passing
program. The root checker, independent spend checker, and altered issuance
checker all exited 0. Source inspection confirms the reported six checker
scripts are executed by a bound wrapper but absent from `BOUND_SOURCES`.

Because the issuance checker currently determines whether CI reaches the
Ansible step, this is material even apart from F1. F4 is conceded at Medium.

## F5 experiment - fact conceded, separate materiality refuted

A77 changed only `infra/tofu.sh`. The root checker exited 1 with its expected
and observed digests. The independent spend checker and all 7 readiness tests
remained green.

This sustains A78's factual count: `tofu.sh` has one workflow-rooted binder.
It does not establish a new bypass. A single externally rooted binder is the
design's trust boundary, and the mutation was rejected exactly as intended.
F1 makes that binder forgeable, so F5 describes reduced defense in depth but
adds no independently material attack after F1. A77 refutes F5 as a separate
blocking finding while retaining it as a repair-direction consideration.

## A9 stop and proposed next boundary

The smallest credible next step is a bounded Python-import and workflow-gate
repair, followed by focused tests, installed mutations, the full repository
gates, and another clean A78 review. If separately authorized, it should:

1. run every repository Python checker through isolated mode and bind standard
   library module provenance, with a pinned isolated test harness that loads
   exact test files without package initializer execution;
2. exact-digest bind all 14 Ansible test sources and all six checker sources
   invoked by the infrastructure/Ansible wrappers;
3. reject unexpected Python files in every importable path used by those
   processes, including package initializers and module shadows;
4. guarantee in the workflow that the Ansible wrapper runs after the retained
   infrastructure failure, while preserving the job's final nonzero result;
5. bind that workflow continuation property in the pinned root checker; and
6. install F1-F4 source attacks plus an independent transitive-oracle mutation
   before a new A78 review.

No live Factory, worker, DigitalOcean, Anthropic, Console, requirement-1
refresh, acceptance, requirement-3, rotation, or qualification action is part
of that proposed boundary.

All adjudication mutations were restored. The adjudication worktree ended
clean at exact reviewed head.
