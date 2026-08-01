# A78 adversarial review - A115 spend run-root repair

## Review identity and scope

| Field | Value |
| --- | --- |
| exact commit | `8cdfeef955ba3d574030e21aff65549219642b86` |
| parent | `11910c50542196b483d1a198cc3abc5b10d6bffe` |
| reviewer seat | A78 |
| harness and model | Claude Code 2.1.220, `claude-opus-5` |
| requested effort | `xhigh`; the harness exposed no realized-effort field |
| permission mode | plan/read-only |
| session | `e67d7dc1-a909-4f13-91cf-238ecf9cd51a` |
| API duration | 1,008,698 ms |

The session completed with no permission denials, web searches, web fetches,
worktree edits, commits, pushes, subagents, provider calls, credential flows,
limit mutations, OpenTofu operations, or infrastructure mutations. It used
only read-only source inspection, local tests, and disposable `/tmp` mutation
copies, which it removed before returning.

## Verdict

**FAIL - two medium material findings.** The permission choice itself is
sufficient and least-privilege, but the new verification path is not yet fit
for the one remaining A115 attempt. A clean-worker replacement may not proceed.

## M1 - unguarded ordering anchors discard checker diagnostics

Severity: **medium**.

`tools/check-anthropic-spend.py` uses four `str.index()` calls in the new
run-root ordering check. The exact block is guarded by a prior `count()`, but
the three surrounding anchors are not. Removing or equivalently rewriting an
anchor raises `ValueError` before the checker reaches its accumulated error
report. That suppresses even the complete-launcher digest failure already
stored in `errors` and violates the mutation harness's declared diagnostic
shape.

A78 reproduced this with three source mutations:

| Launcher mutation | Result |
| --- | --- |
| `FAILURE_STAGE=runtime-staging` changed | traceback at checker line 216; no checker diagnostic |
| add `--` before `$RESULT_EXTRACT` | traceback at checker line 217; no checker diagnostic |
| spell capability path as `${RUN_TMPFS}` | traceback at checker line 220; no checker diagnostic |

The checker already contains the correct pattern for another ordering
contract: guarded lookups with `try` / `except ValueError` and a controlled
diagnostic. The run-root check must use the same fail-closed form.

## M2 - no realized-permission or consuming-identity readback

Severity: **medium**.

The repair creates `$RUN_TMPFS` with the intended owner, group, and mode but
never reads that state back. It also never tests the path as the
`factory-worker` identity that consumes it. The one-shot helper's existing
checks cover the capability and provider directory, but they run as root and
therefore cannot detect the ancestor traversal failure that caused the live
curl status 23.

A78 verified that GNU `install -d` changes an existing directory's mode and
follows a pre-existing symlink to a directory. Realized state can therefore
depend on filesystem state, and source-string binding alone is not an A114
post-condition readback. A mismatch would again reach the provider transport
with an unattributed curl failure rather than stop during runtime staging.

A78's repair direction is to read back the exact `stat -c '%U:%G:%a'` result on
both branches and, on the spend branch, run `test -x "$RUN_TMPFS"` through the
established `runuser -u factory-worker` primitive before capability creation
or provider transport. Those commands and their ordering must be included in
the spend checker's exact binding.

## Permission-chain assessment

A78 confirmed that the repair's intended chain is sufficient:

| Path | Intended owner, group, mode |
| --- | --- |
| `/run` | `root:root 0755` |
| `/run/patchyard-worker` | `factory-worker:factory-worker 0700` |
| spend `$RUN_TMPFS` | `root:factory-worker 0710` |
| `$PROVIDER_STAGE` | `root:factory-worker 0710` |
| `$RAW` | `factory-worker:factory-worker 0700` |

The request process can search the two group-accessible ancestors, read its
own 0400 config and request, and create its response files in its 0700 raw
directory. `0710` is the minimal POSIX search-only group grant: it provides no
directory listing or write access. The grant is scoped only to the spend run
root. Capability and needle files stay `root:root 0600`; the non-spend branch
is explicitly restored to `root:root 0700` and is tighter than the parent
source's implicit ownership.

Requirement 1 does not need the grant because root bind-mounts its credential
image before the VMM uses the mount point. The one-shot removes capability and
raw material before guest boot, the launcher independently checks their
absence, and root cleanup can remove the narrowed run root. The new mode does
not weaken cleanup or taint behavior.

## Source and mutation binding

A78 independently counted 25 focused tests and 29 real-checker mutations: 18
launcher, four issuance runner, three one-shot, three guest, and one Ansible
task mutation. The suite passed. It additionally proved that block relocation,
duplication, and an unbound source-only `chmod 0777 "$RUN_TMPFS"` all fail.

Removing the semantic run-root check while updating the checker digest caused
three focused tests to fail. Coordinately appending a later `chmod 0777` or
`setfacl` and refreshing every source/checker/test digest passed; A78 records
that as defense in depth because a coordinated re-pin changes the reviewed
checker and its terminal test trust boundary. Source-only weakening remains
rejected as required.

## Historical evidence and gates

A78 recomputed the repaired launcher digest as
`5e69e5f99389bbbcc7796d1623fc0cefa1912ae4050b14eb2c47cb3772b697d5`
and the new requirement-1 host contract as
`2b7a904489e9fa4886c5677a9221fc66978f31e492edf740e7c4ea6b35c37d5b`.
The parent and live evidence both bind the prior host contract
`bd36018284041c4ed12f2bea19248ec5f855cfa06f9d4823670a6d87d86d8e2f`.
The parent issuance checker passes, while the reviewed commit correctly fails
as stale. Full Ansible discovery returned 139 passes and only that one expected
failure. A78 agreed that requirement 1 must be refreshed only through a live
rerun on a reviewed clean replacement worker.

The operational record accurately retains both older failure fixtures, the
new curl status 23 stop, the corrected taint path, and the absence of any HTTP,
request-ID, usage, refusal, or overshoot claim. Codebase metric deltas reconcile
arithmetically. All 13 provider qualification flags remain false, and none of
the six changed files introduces a bare `ANTHROPIC_API_KEY`.

## Defense-in-depth observations

1. The positive exact block does not negatively scan for later permission
   operations on `$RUN_TMPFS`; coordinated source/checker/test re-pins can
   admit a later `chmod` or ACL change.
2. `$RUN_TMPFS` has no explicit absent-and-not-symlink precondition. The random
   run ID and clean-host boundary make pre-planting impractical, and the issue
   predates this repair.
3. The taint marker is root-owned but lives in a worker-owned directory, so the
   `factory-worker` identity could unlink it. Control-plane destruction remains
   the authoritative quarantine mechanism.
4. Numeric `stat` mode does not enumerate extended ACL entries; an ACL-aware
   check would be stronger.
5. Process cleanup matches the declared run ID in argv; a process that rewrites
   its argv can evade that specific detector. This predates the repair.
6. A78's default PATH lacked the pinned `tokei`, so it verified the codebase
   projection arithmetically rather than executing the projection wrapper.

These observations are nonblocking for the reviewed repair and do not change
the FAIL verdict, which rests only on M1 and M2.

## Commands and outcomes

- exact commit diff and status: six changed files at the reviewed commit;
  worktree clean before and after;
- focused spend suite: 25 of 25 passed;
- spend checker: passed with historical failures retained;
- full Ansible discovery: 139 of 140 passed; sole failure was the disclosed
  stale requirement-1 host contract;
- issuance checker at the parent: passed; at the repair: failed stale as
  intended;
- ShellCheck on launcher and one-shot: passed;
- three anchor mutations: each produced an uncontrolled `ValueError`;
- relocation, duplication, and source-only permission broadening: rejected;
- coordinated permission broadening with complete re-pinning: passed, recorded
  as the terminal review-boundary limitation;
- policy audit: 13 providers, all qualification flags false;
- credential-name scan: no new bare Anthropic environment variable.

## Next boundary

The clean-worker replacement gate is closed. M1 and M2 require another bounded
source repair and re-review before a replacement plan may be generated. The
stale requirement-1 evidence must remain red until the reviewed repair is live
on a clean worker. No provider request, cap action, behavioral acceptance,
requirement-3 work, or qualification-flag change is authorized. A119 remains
reserved.
