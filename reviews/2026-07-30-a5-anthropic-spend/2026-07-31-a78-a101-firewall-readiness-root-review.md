# A78 adversarial review - A101 readiness root-of-trust repair

## Verdict

**NOT A PASS** - one Critical, two High, and one Medium material finding.
A fifth Medium observation is reported separately.

Reviewed record commit:
`ba109ee433956bf81070ae787f43fb0159795f3f`; technical repair commit:
`30615e80f6c564e08ed06a213078e2cad075c8b4`.

Reviewer: A78, Claude Opus 5 at `xhigh` effort through Claude Code 2.1.220 on
Anthropic. The worktree was detached and clean at the exact reviewed commit
before and after review. A78 used no subagent, opened no file under `reviews/`,
read no environment secret, and made no network, provider, host, or Console
action.

## Verified baseline

A78 verified:

- the workflow literal matches root-checker SHA-256
  `2914d771d38fcdeb8434045ecb86d7a56c6c4e7804c91058cd5f2965a582f921`;
- all 15 root-bound source digests match;
- the helper remains
  `5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba`;
- the replacement operator remains
  `27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e`;
- the root checker, 3 root tests, 7 readiness tests, 27 spend tests, and
  independent spend checker pass;
- all 14 modules run in separate processes when `check-ansible.sh` is invoked;
- `check-ansible.sh` returns 1 for only the retained stale issuance mismatch
  while still invoking all four lint and four syntax gates; and
- all 13 provider qualification flags remain false.

A78 replaced `ansible-lint` with a recording local stub during the combined
wrapper probe because its release check opens a socket. The real offline-safe
Ansible syntax checks ran. `tools/check-infra.sh` itself was not launched in
the review because OpenTofu initialization fetches providers; its post-init
checker tail was replayed offline.

## F1 - repository Python shadowing forges the trust root

Severity: **Critical, material**.

The workflow runs the pinned checker as:

```text
python3 tools/check-a101-readiness-root.py
```

Python therefore places repository-controlled `tools/` at `sys.path[0]`.
`hashlib` is not preloaded, so an added, uncensused `tools/hashlib.py` shadows
the standard-library module for both the root checker and independent spend
checker. A corresponding root-level `hashlib.py` shadows it for the current
`python3 -m unittest` processes.

A78 added a genuine helper mutation and a shim that delegates real hashing but
returns the pinned digest for those exact mutant bytes. The workflow's literal
checker checksum still passed, the root checker passed, the spend checker
passed, and the combined wrapper's failure set remained identical to the clean
baseline - only the retained issuance mismatch failed.

This defeats checker self-identity, the external workflow pin, the independent
spend binding, and the readiness test binding without changing the workflow or
the pinned checker bytes. `python3 -I` removed the repository script directory
from `sys.path` and made the same helper mutation fail. `-E -s` did not.

## F2 - the module census excludes executable import paths and most content

Severity: **High, material**.

The root checker censuses `test_*.py` names and digest-binds only three test
modules. It does not reject Python package initializers. A new
`infra/ansible/tests/__init__.py` or `infra/__init__.py` executes inside each
nominally separate module process before the test module loads while remaining
outside the census.

A78 used such an initializer to shim `hashlib` in each process. The root and
spend checkers passed and `check-ansible.sh` changed from its honest exit 1 to
exit 0, with all eight later gates still invoked.

Eleven of the 14 module sources are also name-only. Replacing
`test_anthropic_issuance.py` with a four-line trivial passing test retained the
expected filename, kept both checkers green, removed the stale assertion, and
made the combined wrapper exit 0.

## F3 - CI skips the repaired Ansible wrapper

Severity: **High, material**.

The aggregation inside `tools/check-ansible.sh` is real, but the infrastructure
workflow runs `tools/check-infra.sh` in the preceding step. That script remains
`set -euo pipefail` and exits at the deliberately stale issuance checker. The
next workflow step has no `if: always()` or equivalent, so GitHub Actions skips
the entire repaired Ansible wrapper.

Offline replay confirmed `check-infra.sh` reaches the independent spend
checker, fails issuance, and never runs `check-preview-runtime.py`. The normal
workflow therefore never invokes ShellCheck, the 14 isolated modules, four
lint gates, four syntax gates, or the terminal root recheck while the retained
fixture remains stale.

## F4 - six executed checker scripts are outside the trust root

Severity: **Medium, material**.

The wrappers execute six unbound checker sources:

- `tools/check-anthropic-issuance.py`;
- `tools/check-independence.py`;
- `tools/check-preview-runtime.py`;
- `tools/check-stack.py`;
- `tools/check-worker-qualification.py`; and
- `tools/check-worker-runtime.py`.

Replacing the issuance checker with one passing print left both root and spend
checkers green and removed the one result that controls whether CI reaches the
Ansible step. The root checker validates spend-before-issuance order, but not
the identities of these invoked gates.

## F5 - the transitive state oracle has only one binder

Severity: **Medium as reported by A78**.

Mutating `infra/tofu.sh` is caught by the root checker, so the prior unbound
oracle finding is repaired. The independent spend checker and readiness suite
both remain green for the same mutation. The helper and operator have three
binders; the state oracle has only the workflow-rooted checker, which F1 can
currently collapse.

## Properties that do hold

- A direct root-checker source mutation fails both the workflow checksum and
  the checker's expectation that the workflow pin its current bytes.
- Executable tool-version content is rejected and never evaluated; the prior
  tool-version sourcing finding is repaired.
- The independent spend checker is before issuance in the Ansible wrapper.
- The Ansible wrapper aggregates a nonzero result and invokes all later gates
  when called.
- A helper mutation without an import-environment attack is caught by the root,
  spend, and readiness bindings.
- Adding or removing a `test_*.py` module fails the filename census.
- A repository `sitecustomize.py` in the script directory does not execute
  early enough to provide the same shadow route.

## Nonblocking observations

- Several semantic source checks in the root checker are redundant with exact
  wrapper digests and mainly improve diagnostics.
- The module and bound-source lists are duplicated between source and test,
  making drift diagnostics less direct.
- The fresh-process test proves two hand-launched Python processes are
  isolated; the wrapper digest, not that test, binds the production loop.
- The workflow intentionally runs the trust root before `actions/setup-python`,
  so the checker must remain compatible with the default `ubuntu-latest`
  Python.

## Suggested source-only direction

A78 proposed isolated Python mode for every checker and test, explicit
standard-library provenance for `hashlib`, a complete census of executable
Python import paths, exact bindings for all 14 tests and six invoked checkers,
and a workflow mechanism that runs the Ansible step despite the retained
infrastructure failure.

## Safety and cleanup

All attacks were local and disposable. No real network client or socket ran.
No GitHub, DigitalOcean, Anthropic, SSH, DNS, browser, OpenTofu backend,
Ansible live inventory, worker, credential, Console, requirement-1 refresh,
acceptance, requirement-3, rotation, or qualification action occurred. Every
mutation and added module was removed. The review worktree ended clean at the
exact reviewed commit.
