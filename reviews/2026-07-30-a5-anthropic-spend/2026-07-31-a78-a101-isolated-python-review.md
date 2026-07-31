# A78 adversarial review - A101 isolated Python and workflow-continuation repair

## Verdict

**NOT A PASS** - one High and two Medium material findings.

Three of the four conceded findings are closed. The fourth (F2, "name-only /
unbound test content") is only closed for the `.py` bytes: the content that the
14 isolated test processes actually execute is still unbound, and the same
green-issuance attack A77 conceded is reproducible at this commit without
changing any bound source.

## Review identity and boundary

- Exact reviewed commit: `a0bd964d2c8b9690af5b257fe14617096b3eb612`
  ("docs: finalize isolated gate record").
- Parent of the reviewed source range: `5e2af3a98a926764d54b8cfb2ebca0a2418f7988`.
- Reviewer: adversarial review seat A78, Claude Code 2.1.220, model Opus 5,
  `xhigh` effort.
- **No subagents were used.** Every command in this record was run directly by
  the review seat.
- **No network access occurred.** No web tool, GitHub, MCP/connector, provider
  API, live host, worker, DigitalOcean, Anthropic, or Console action was taken,
  and no real network request or socket was opened. `rsync`, `git worktree`, and
  every experiment below are local-only.
- **No source file was altered.** All mutations were made in disposable copies
  under `/tmp/a78rev/*` and one disposable `git worktree`. All were removed; the
  reviewed worktree is clean and detached at the exact commit before and after
  the review. The only repository change is this review record.
- The deliberately stale requirement-1 evidence was **not** refreshed. It is
  still red exactly as disclosed.
- The long Rust/application suite was not rerun; its exact run is recorded at
  `155b2684bff7c3b12238154ef5724967675c0a79`. This review is confined to the
  security boundary.

### Records read in full

- `reviews/2026-07-30-a5-anthropic-spend/2026-07-31-a78-a101-firewall-readiness-root-review.md`
- `reviews/2026-07-30-a5-anthropic-spend/2026-07-31-a77-a101-firewall-readiness-root-review-adjudication.md`
- `reviews/2026-07-30-a5-anthropic-spend/2026-07-31-a115-a101-firewall-readiness-repair.md` (all 1,349 lines)

### Sources inspected

The complete `5e2af3a..a0bd964` diff (13 files, 724 insertions, 166 deletions)
and the full current text of `.github/workflows/infrastructure.yml`,
`tools/check-a101-readiness-root.py`, `tools/run-isolated-unittest.py`,
`tools/check-ansible.sh`, `tools/check-infra.sh`, `tools/check-anthropic-spend.py`,
`tools/install-shellcheck.sh`, `infra/ansible/qualify.sh`,
`infra/ansible/tests/test_a101_readiness_root.py`, the headers of
`infra/ansible/tests/test_anthropic_spend.py`,
`infra/ansible/tests/test_anthropic_wif_admin.py`,
`infra/ansible/tests/test_log_secret_scan.py`, and the seven infrastructure
checker scripts.

Interpreter under test: `Python 3.9.25` at `/bin/python3`.

## Verified baseline

Independently recomputed and confirmed:

- the workflow literal pin equals the checker's real SHA-256
  `fb0a3ee170c72f7e798b09ce5d67c8aba6d0bfd7eac9583ab32522f5177fb0b4`;
- all **33** `BOUND_SOURCES` digests match (0 mismatches), parsed straight out of
  the checker source rather than from the record;
- the production helper and replacement operator remain byte-identical at
  `5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba`
  and `27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e`;
- `python3 -I tools/check-a101-readiness-root.py` exits 0;
- 7 root tests, 7 readiness tests, and 27 spend contract tests pass through the
  production runner (`Ran 7 / Ran 7 / Ran 27 ... OK`);
- the full 14-file isolated loop runs **156** tests, 155 pass, and the only
  failure is the disclosed stale requirement-1 host contract
  (`bd360182... != eef6e16e...`), with aggregate status 1 and the terminal
  trust-root recheck passing;
- every Python gate in this boundary is invoked with `-I`. A repository-wide grep
  for `python3 ... tools/check-*`, `tools/read-infra-*`, and
  `run-isolated-unittest` found invocation sites only in
  `.github/workflows/infrastructure.yml:30`, `tools/check-infra.sh:6,8,45-51`,
  `tools/check-ansible.sh:6,8,52,74,90`, `tools/install-shellcheck.sh:7,10,13`,
  and `infra/ansible/qualify.sh:53` - all isolated.

## Requirement-by-requirement result

### 1. Isolated invocation and fail-closed provenance - holds

Non-isolated execution is refused by all three:

```text
$ python3 tools/check-a101-readiness-root.py           -> exit 1
  A101 readiness trust root requires python3 -I
  A101 readiness trust root has repository import path: .../tools
$ python3 tools/check-anthropic-spend.py               -> exit 1
  Anthropic spend checker requires python3 -I
$ python3 tools/run-isolated-unittest.py <censused file> -> exit 2
  isolated unittest runner requires python3 -I
```

Non-stdlib provenance is rejected on a real repository shadow. With
`tools/hashlib.py` present, the non-isolated checker reported:

```text
  A101 readiness trust root rejected hashlib provenance: '/tmp/a78rev/f1/tools/hashlib.py'
```

`-I` also neutralises environment injection: with
`PYTHONPATH=<dir containing hashlib.py>` and with `PYTHONHOME=/nonexistent`,
`python3 -I` still resolved `hashlib` to `/usr/lib64/python3.9/hashlib.py` and
`sys.path` began at `/usr/lib64/python39.zip`. Without `-I` the same PYTHONPATH
executed the shadow.

### 2. Runner loads exact files; content binding is incomplete - see Finding 1

The runner behaves as claimed at the path level. Probed from inside a loaded
test file:

```text
MODNAME  _patchyard_bound_test
SYSPATH  ['/usr/lib64/python39.zip', '/usr/lib64/python3.9',
          '/usr/lib64/python3.9/lib-dynload', '/usr/lib64/python3.9/site-packages',
          '/usr/lib/python3.9/site-packages']
HASHLIB  /usr/lib64/python3.9/hashlib.py
```

No repository directory is on `sys.path`, the module name is synthetic and
non-package, and rejection paths all fire:

| Case | Runner | Root checker |
| --- | --- | --- |
| uncensused `infra/ansible/tests/test_evil.py` | exit 2, "refuses an uncensused test file" | exit 1, "unexpected infrastructure Python source" |
| censused name replaced by a symlink | exit 2, "refuses a symlinked test file" | exit 1, "bound A101 source is a symlink" |
| censused file copied outside the test root | exit 2, "refuses a test outside its root" | n/a |
| nested `infra/ansible/roles/x/deep.py` | n/a | exit 1, "unexpected infrastructure Python source" |

Package initializers are rejected and never executed (see F2 below), and no
`__pycache__` or `.pyc` is produced by any of the 14 runs.

The content binding itself is **not** complete: see Finding 1 (forged bytecode)
and Finding 3 (unbound exec-loaded modules).

### 3. Workflow continuation is real; the non-masking binding is not - see Finding 2

`if: ${{ always() }}` is present on the Ansible step at the required 8-space
indentation, the infrastructure step has no `continue-on-error`, and removing
`always()` is caught. The continuation property therefore holds at this commit.
The companion property the record claims ("its failure remains the job's final
failure") is true today but is not load-bearingly bound - Finding 2.

### 4. `check-infra.sh` continues through preview and returns nonzero - holds

The aggregate block was extracted and diffed byte-for-byte against
`tools/check-infra.sh` (`diff` empty) and replayed offline. Only the seven
static checkers run; none of them opens a socket (verified by import inspection;
`check-preview-runtime.py`'s only subprocess use is `bash -n`). OpenTofu
initialization was not run because it fetches providers.

```text
check-stack: no excluded-technology artifacts
independence check: ... no orchestration-host dependency
worker runtime check: pass
worker qualification check: pass
Anthropic spend check: pass
Anthropic issuance check: failed
  live result is stale for the current Anthropic host contract; ...
preview runtime check: pass
aggregate exit=1
```

Preview runtime is reached and reported after the retained issuance failure, and
the wrapper still returns 1.

### 5. Load-bearing checks on the four conceded attacks

| Attack | Result |
| --- | --- |
| **F1** guarded `/nonexistent/wget` helper mutation (real digest `bdfcdba6...`) plus `tools/hashlib.py` mapping that digest to the pinned `5aa2f71c...` | The exploit primitive is genuine: non-isolated, the shim suppressed the helper-mismatch line entirely. It is still stopped three independent ways - `-I` prevents the shadow from loading at all (marker file absent, real digest reported), the provenance check rejects it when `-I` is absent, and the protected-shadow census rejects `tools/hashlib.py`. Isolated root exit 1; isolated spend checker exit 1 ("A101 firewall readiness helper differs"). |
| **F2** executable `infra/ansible/tests/__init__.py` plus a one-case passing issuance test | Runner ran the trivial case; initializer marker absent. Root exit 1 with three errors: changed test digest, "unexpected infrastructure Python source", "repository package initializer is forbidden". |
| **F3** remove `if: ${{ always() }}` | Root exit 1, "Ansible step does not run after infrastructure failure". |
| **F4** replace `tools/check-anthropic-issuance.py` with a passing print | Forged checker exit 0; root exit 1 on its exact identity (`expected 56a84e7f..., observed 91003f2d...`). |

Self-weakening of the three new isolation gates is also caught:

| Weakening | Result |
| --- | --- |
| `isolation_errors()` -> `return []` in the **root checker** | The checker's own self-pin fails ("infrastructure workflow does not pin this trust-root checker") **and** the workflow literal `sha256sum --check` fails. |
| same in **`check-anthropic-spend.py`** | Weakened checker passes non-isolated, but root exit 1 on its exact digest. |
| runner accepts any file | Root exit 1 on `tools/run-isolated-unittest.py` digest. |

Script entry points are not bytecode-cache attackable: forged
`tools/__pycache__/check-a101-readiness-root.cpython-39.pyc` and
`tools/__pycache__/run-isolated-unittest.cpython-39.pyc` were ignored
(`__main__` is never loaded from cache).

### 6. Residual bypasses - three found

Findings 1-3 below.

---

## Finding 1 - forged bytecode replaces the executed content of any bound test

Severity: **High, material.** Reopens the conceded F2 class for all 14 test files.

`tools/run-isolated-unittest.py` loads each test through
`importlib.util.spec_from_file_location(...)`, which uses `SourceFileLoader`.
`SourceFileLoader.get_code()` consults `__pycache__`. A PEP 552 *unchecked
hash-based* `.pyc` (flags `0b01`) is executed with **no source validation at
all**, so the bytes the gate runs need not correspond to the digest-bound `.py`.
The runner sets `sys.dont_write_bytecode = True`, which prevents writing but not
reading. Nothing in the repair censuses `.pyc` files: the census enumerates only
`(REPO/"infra").rglob("*.py")`, and `PROTECTED_MODULE_FILES` matches only `.py`
names.

Reproduced end-to-end in a disposable `git worktree` checked out at exact commit
`a0bd964` (removed and pruned afterwards). One force-added file was the entire
change:

```text
$ git add -f infra/ansible/tests/__pycache__/test_anthropic_issuance.cpython-39.pyc
$ git status --porcelain
A  infra/ansible/tests/__pycache__/test_anthropic_issuance.cpython-39.pyc
```

Before, in the same clean checkout:

```text
infra/ansible/tests/test_anthropic_issuance.py   FAIL  Ran 20 tests in 0.714s
  AssertionError: 'bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f'
              != 'eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977'
aggregate gate_status=1
```

After, with only that one file added:

```text
infra/ansible/tests/test_anthropic_issuance.py   PASS  Ran 1 test in 0.000s
... all other 13 files PASS ...
A101 readiness trust root: pass
aggregate gate_status=0
wrapper-loop exit=0
```

While that forged bytecode is present:

- `python3 -I tools/check-a101-readiness-root.py` -> **exit 0**, all 33 digests
  match, census clean, no initializer, no protected shadow;
- `python3 -I tools/check-anthropic-spend.py` -> **exit 0**;
- the wrapper's terminal isolated trust-root recheck -> **pass**.

This is precisely the attack A77 conceded at High ("a trivial one-case issuance
module that kept the filename census green"), now reachable with every bound
source byte-identical. The deliberately retained honest-red requirement-1
contract is silenced and 19 further issuance assertions disappear. The same
route applies to any of the 14 files, including
`test_a101_readiness_root.py` and `test_worker_firewall_readiness.py`, whose
three independent binders all hash the `.py` and none of which observes the
`.pyc`.

Practical constraints, stated fairly: `__pycache__/` and `*.py[cod]` are
gitignored (confirmed with `git check-ignore -v`), so the file needs `git add
-f`. I verified in a throwaway local repository that a force-added
`__pycache__/*.pyc` is committed and restored on checkout, so it lands in a
fresh CI checkout. Timestamp-based `.pyc` files would not survive a fresh
checkout's mtimes; the unchecked hash-based variant needs no such prediction.

Remediation direction (source-only): set `sys.pycache_prefix` to a private
temporary directory before loading, or read the source and load from a
`code` object compiled in-process, or add `__pycache__`/`*.pyc` under the test
root and `tools/` to the root checker's census.

## Finding 2 - the workflow non-masking binding is not load-bearing

Severity: **Medium, material.**

The root checker emits `infrastructure workflow masks the infrastructure
failure`, so it purports to bind the property the record states: "The preceding
infrastructure step has no `continue-on-error`, so its failure remains the job's
final failure." The binding is a substring test on one step body:

```python
if infra_step is None or infra_step.count("run: tools/check-infra.sh") != 1:
    ...
elif "continue-on-error" in infra_step:
    errors.append("infrastructure workflow masks the infrastructure failure")
```

Three source-only workflow weakenings preserve every literal assertion and keep
the checker at exit 0:

| Weakening | Root checker | Effect |
| --- | --- | --- |
| `run: tools/check-infra.sh \|\| true` | **pass (exit 0)** - the required substring is still present exactly once and no `continue-on-error` appears | the retained infrastructure failure is fully masked |
| job-level `continue-on-error: true` under `jobs.infrastructure` | **pass (exit 0)** - the key is outside every `      - name:` step body the regex captures | the failed job no longer fails the workflow run |
| `continue-on-error: true` on the newly added Ansible step | **pass (exit 0)** - only the `if:` line and the `run:` line are asserted | the entire point of the new `always()` step, its gate results, stops affecting the run conclusion |

Composed with Finding 1, a green job needs only the forged `.pyc` plus one of
these workflow lines, with all 33 bound digests intact. Requirement-1 stale
evidence and every Ansible gate result would be reported as passing.

The workflow is the human-reviewed root, which limits this to "the automated
binding does not help here", but the checker claims otherwise and the review
brief asks specifically whether the continuation property "does not mask the
preceding failure".

## Finding 3 - execution closure is incomplete by three unbound sources

Severity: **Medium, material.**

The record calls the 33 digests "execution-closure sources". Three repository
files execute arbitrary code at import time *inside* the nominally
content-bound isolated test processes, and none of them is bound anywhere. I
searched the whole repository (excluding review prose) for each file's digest:

| Executed source | Loaded by | SHA-256 | Bound in |
| --- | --- | --- | --- |
| `tools/anthropic-spend-evidence.py` | `test_anthropic_spend.py:43-45` (`spec_from_file_location` + `exec_module`) | `d79d8c69...9d97` | **none** |
| `tools/anthropic-wif-admin.py` | `test_anthropic_wif_admin.py:9-12` | `89794bd6...22c91` | **none** |
| `infra/ansible/roles/control_plane/files/patchyard-log-secret-scan` | `test_log_secret_scan.py:19-20` (`SourceFileLoader.load_module`) | `356c4a96...11eb8` | **none** |

They are outside `BOUND_SOURCES`, outside the `infra/**/*.py` census (two live
under `tools/`, which has no census; the third has no `.py` suffix), and outside
`PROTECTED_MODULE_FILES`.

Demonstrated impact on the claimed *independent* second binder. I appended one
comment line to `infra/ansible/tests/test_worker_firewall_readiness.py`
(mutant digest `2f025d2f...`) and ran the spend contract suite:

```text
(A) mutation only            -> Ran 27 tests ... FAILED (failures=1)   exit 1
(B) same mutation, plus import-time hashlib poisoning added to the
    unbound tools/anthropic-spend-evidence.py
                             -> Ran 27 tests ... OK                    exit 0
    unbound module executed inside the bound test process: YES
```

With the poison alone (readiness test restored), `python3 -I
tools/check-a101-readiness-root.py` and `python3 -I
tools/check-anthropic-spend.py` both exit 0 - the added executable content is
invisible to every gate.

The root checker's own digests are computed in a separate `-I` process and are
not affected, so this is not a full root bypass. It does defeat the deliberately
built redundancy ("the spend contract test independently exact-digest binds the
complete spend checker and the same four readiness sources") and admits
uncensused executable content into three of the fourteen "isolated" processes -
the same class as the conceded F2 initializer, through a different door.

## Properties that do hold

- The exact prior F1 mapped-digest `hashlib` exploit is closed three ways, and
  `-I` alone is sufficient.
- Package initializers neither execute through the runner nor survive the census
  (`infra/__init__.py`, `infra/ansible/__init__.py`,
  `infra/ansible/tests/__init__.py` all rejected).
- All six previously unbound checker scripts, plus `check-stack.py`, are now
  exact-digest bound; a forged passing issuance checker is rejected (F4 closed).
- The runner refuses uncensused, symlinked, out-of-root, and missing test files;
  the root checker refuses symlinked bound sources.
- `check-infra.sh` aggregates honestly: preview runtime runs after the retained
  issuance failure and the wrapper returns 1.
- The Ansible wrapper runs 14 separate isolated processes; a `hashlib` poison in
  one does not survive into the next.
- Removing `always()`, mutating any of the 33 bound sources, weakening the spend
  checker's or the runner's isolation logic, and rewriting the root checker's own
  isolation logic are all rejected.
- Executable content in `infra/tool-versions.env` remains inert.
- No `.pyc` is written by the gate itself, so Finding 1 is not self-inflicted -
  it requires a deliberately committed artifact.
- The record's numeric claims that I could check are accurate: 33 bound sources,
  156 tests across 14 isolated processes with 155 passing, 7/7/27 focused tests,
  and the exact F1-F4 mutation outcomes in its table.

## Nonblocking observations

- `PROTECTED_MODULE_FILES` is a fixed 20-name list. Under `-I` no repository
  directory is importable, so it is defense-in-depth only; but it omits most of
  what these processes actually import (`warnings`, `functools`, `enum`,
  `collections`, `io`, `codecs`, `traceback`, ...). If any invocation ever loses
  `-I`, the list would not cover them.
- The root checker binds the workflow's pin *string* and the `-I` invocation, but
  not the presence of `| sha256sum --check`. That pipeline is the only thing that
  catches a checker rewritten to drop its own self-pin assertion.
- `if: ${{ always() }}` also runs the Ansible step when the job is cancelled;
  `${{ !cancelled() }}` is the narrower idiom for "run after a failed step".
- `tools/check-application.sh` and `model/check-model.sh` still use non-isolated
  `python3 -m unittest discover`. That is outside this boundary and binds no A101
  digest, but the same shadow class applies there.
- The root checker walks `REPO.rglob("*.py")` and `rglob("__init__.py")` over the
  entire repository, so a local `.venv` or vendored Python tree would trip it.
  Robustness, not security.
- `tools/*.py` has no census; only the 20 protected names and the explicit
  bindings constrain it. That is what makes Finding 3 reachable.

## Commands and experiments run

All local. Scratch trees `/tmp/a78rev/{f1,f2,pyc,pyc2,wf,probe,probe2,closure,self,final,envtest,gitpyc,wt}`
were created and removed; pre-existing unrelated content under `/tmp/a78rev` was
left untouched.

1. `git show --stat` / `git diff 5e2af3a a0bd964` over all 13 changed files.
2. Independent recomputation of all 33 `BOUND_SOURCES` digests.
3. Non-isolated invocation of root checker, spend checker, and runner.
4. F1 mapped-digest `tools/hashlib.py` exploit against a real helper mutation,
   isolated and non-isolated.
5. F2 initializer + trivial issuance test against runner and root checker.
6. F3 `always()` removal; F4 forged issuance checker.
7. Three workflow masking weakenings (`|| true`, job-level and step-level
   `continue-on-error`).
8. Forged unchecked hash-based `.pyc` against the runner, against script entry
   points, and end-to-end in a `git worktree` at `a0bd964`.
9. Import-time poisoning of the unbound `tools/anthropic-spend-evidence.py`.
10. Byte-identical offline replay of the `check-infra.sh` aggregate block.
11. Full 14-file isolated test loop with aggregation (156 tests).
12. Runner census/symlink/out-of-root/nested-census probes; `sys.path`,
    `PYTHONPATH`, and `PYTHONHOME` probes under `-I`.
13. Self-weakening of the root checker, spend checker, and runner isolation logic.
14. Repository-wide search for invocation sites and for digest bindings of the
    three exec-loaded sources.

## Safety and cleanup

Every mutation was made in disposable copies or one disposable detached
worktree, which was removed with `git worktree remove --force` and pruned. No
real network client, socket, provider request, host, worker, DigitalOcean,
Anthropic, Console, requirement-1 refresh, acceptance, requirement-3, rotation,
or qualification-flag action occurred. All 13 `credential_qualified` flags were
untouched. The reviewed worktree ended clean and detached at
`a0bd964d2c8b9690af5b257fe14617096b3eb612`, with
`python3 -I tools/check-a101-readiness-root.py` passing, and this review record
is the only repository change.

## Verdict

**NOT A PASS.**

- Conceded **F1** (repository Python shadowing / provenance): **closed**.
- Conceded **F2** (initializer execution; name-only test content): **initializers
  closed; executed test content still unbound** - Finding 1.
- Conceded **F3** (workflow skipping the wrapper): **continuation closed; the
  companion non-masking property is unbound** - Finding 2.
- Conceded **F4** (six unbound checker scripts): **closed**.
- New: Finding 3, incomplete execution closure by three unbound exec-loaded
  sources.

The smallest credible next repair is source-only: make the runner load from
in-process compiled source (or redirect `sys.pycache_prefix`) and census
bytecode artifacts; bind the three exec-loaded sources and add a `tools/*.py`
census; and strengthen the workflow binding to assert the exact infrastructure
`run:` line, reject job-level and Ansible-step `continue-on-error`, and reject
shell suffixes on the gate invocations.
