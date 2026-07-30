# A78 adversarial review - A115 spend run-root repair (M1/M2 iteration)

## Review identity and exact commit

| Field | Value |
| --- | --- |
| requested object | `520663f8180ea4f5d859439548687c9f8d8ed23d` - does not resolve |
| resolved exact commit | `520663f25cbaf862d252067e9ca5d933b00b0e9b` |
| resolution method | unique short ID `520663f` to full commit object |
| parent | `0b06bd54d67330823b1c85c765b4bbedd72fa4b0` |
| branch and HEAD | `a5-anthropic-spend-a115-successor`; HEAD equals reviewed commit |
| reviewer seat | A78 |
| harness and model | Claude Code 2.1.220, `claude-opus-5` |
| requested effort | `xhigh`; the result exposed no separate realized-effort field |
| permission mode | plan/read-only |
| session | `b5da2aa3-17aa-4e06-ab0b-ebd9ffa7f81c` |
| API duration | 756,150 ms |
| wall duration | 1,122,617 ms |

The prompt's mistaken 40-hex object does not exist. The reviewer resolved the
unique short ID and reviewed exact commit
`520663f25cbaf862d252067e9ca5d933b00b0e9b`.

The worktree was clean before and after. The session completed with no
permission denials, edits, commits, pushes, subagents, web searches, web
fetches, provider calls, credential flows, Console actions, worker access, or
infrastructure mutations. It created and removed only disposable `/tmp`
source-mutation copies and left pre-existing temporary artifacts untouched.

## Verdict

**PASS.** Both conceded medium findings are repaired at exactly the scope A78
and A77 specified. The repair is fit to proceed to a separately reviewed
clean-worker replacement plan. PASS does not authorize replacement, credential
issuance, provider requests, Console limit action, behavioral acceptance,
requirement 3, or a qualification-flag change.

## Material findings

None. Every adversarial attempt to defeat the repair source-only was rejected
with a controlled diagnostic.

## M1 - repaired and verified

`tools/check-anthropic-spend.py` resolves all three ordering anchors inside one
`try`/`except ValueError` and appends the controlled diagnostic
`A115 spend run-root traversal is outside runtime staging` on absence or
misordering. An AST scan confirmed that the only `.index()` outside a `try` in
the checker is the exact-block lookup, which is structurally reached only after
the preceding singularity guard passes.

A78 ran seven independent mutations that are not the authored suite:

| Mutation | Exit | Traceback | Diagnostics |
| --- | --- | --- | --- |
| delete `FAILURE_STAGE=runtime-staging` | 1 | no | digest plus ordering |
| delete the `$RESULT_EXTRACT` install line | 1 | no | digest plus ordering |
| delete the `CAPABILITY=` line | 1 | no | digest plus ordering |
| delete all three anchors | 1 | no | digest plus ordering |
| move the block after `$RESULT_EXTRACT` | 1 | no | digest plus ordering |
| move `FAILURE_STAGE` after the block | 1 | no | digest plus ordering |
| move `CAPABILITY=` before the block | 1 | no | digest plus ordering |

Every run began with `Anthropic spend check: failed`, retained the already
accumulated complete-launcher digest diagnostic, and emitted no traceback. The
ordering chain is now
`runtime-staging < block < RESULT_EXTRACT < CAPABILITY`.

## M2 - repaired and verified

The launcher reads back `stat -c '%U:%G:%a'` on both branches. The spend branch
probes search permission as the consuming identity through
`/usr/sbin/runuser -u factory-worker -- /usr/bin/test -x "$RUN_TMPFS"`.
This is independent kernel readback rather than the actor reporting on itself.

Runtime ordering is unconditional: `set -euo pipefail`, the `ERR` trap,
`FAILURE_STAGE=runtime-staging`, both readbacks, and then the first capability
write. Nothing writes the capability earlier.

A78 executed a faithful harness of the block with the same traps, errexit, and
construct nesting:

| Simulated condition | Result |
| --- | --- |
| spend owner/group/mode mismatch | runtime-staging ERR, taint, exit 1, no capability |
| spend readback matches | proceeds; the check is not vacuous |
| non-spend mismatch | runtime-staging ERR, exit 1 |
| non-spend readback matches | proceeds |
| readback matches but search permission is removed | identity probe fails at runtime-staging, exit 1 |

`test -x` on a directory was independently confirmed to test search permission.
The required primitives are provisioned: `util-linux` and `factory-worker` are
in worker desired state, and the one-shot already uses the same absolute
`runuser` form.

A78 attempted twelve source-only weakenings: `|| true` on either new line;
PATH-relative `runuser`; dropping `--` from `stat`; globbing the mode
comparison; swapping the lines; duplicating or relocating the block; wrapping
it in `if false`; and appending `chmod 0777` or `setfacl`. All were rejected.

## Record and gate verification

| Claim | Result |
| --- | --- |
| launcher SHA-256 `60b71fb2...f133e3f` | matches |
| checker SHA-256 `d2d32fc9...b471e09` | matches the pinned test value |
| requirement-1 host contract `eef6e16e...d52977` | recomputed and matches |
| prior fixture `bd360182...d8e2f` | matches the recorded stale value |
| seven new mutations, 29 to 36 | AST count confirms 36 at HEAD and 29 at parent |
| focused tests | 25 of 25 pass |
| full Ansible discovery | 139 of 140 pass; only stale host contract fails |
| unmodified spend checker | passes with historical failures retained |
| ShellCheck, Bash parse, Python compile | pass |
| codebase projection | passes with pinned tokei 14.0.0 |
| four lint and four syntax profiles | pass |
| provider qualification flags | 13 providers, all false |
| credential naming | no bare key, `sk-ant-` literal, or `api_key=` |

The checker-source pin is real. A78 added `chmod 0777 "$RUN_TMPFS"` in three
scenarios. Launcher-only mutation failed the checker and suite. Re-pinning only
the checker constant made the checker pass but the focused suite still failed.
Only a visible coordinated launcher/checker/test re-pin passed, which is the
already-recorded terminal review boundary.

The stale requirement-1 failure is honest: both its checker and unit test fail
on exactly `bd360182... != eef6e16e...`. The live fixture is untouched. The
work record is additive and does not modify a failure fixture, issuance
evidence, or provider policy. It does not claim a provider status, request ID,
usage, refusal, or overshoot from the curl-23 attempt.

## Nonblocking observations

### N1 - curl 23 diagnosis and narrower preflight opportunity

An offline reproduction showed that curl 7.76.1 treats an unreadable
`--config` and unreadable `--data-binary @file` as warnings, then returns
`curl: (23) Failed writing received data to disk/application` with HTTP `000`
when it cannot open the dump-header/output paths. This precisely reproduces the
live transport-failed-23 signature and corroborates the traversal diagnosis.

The failed attempt therefore could have lacked a bearer and body, but the
record correctly makes no retrospective provider-receipt or spend claim. The
current repair verifies `$RUN_TMPFS`, not narrower readability/writability at
`$PROVIDER_STAGE/raw` or its `0400` files. An identity-scoped precondition such
as `test -r "$AUTH_CONFIG"` may be useful in a future bounded repair. This is
pre-existing one-shot behavior, outside M1/M2, and not a regression.

### N2 - direct-test ordering asymmetry

The direct source test does not separately express the
`RESULT_EXTRACT < CAPABILITY` leg that the real checker asserts. The exact
block, checker ordering contract, complete-source binding, and mutations make
this harmless asymmetry nonblocking.

### N3-N4 - prior observations unchanged

`stat` follows symlinks, so the previously adjudicated D2 remains open. D1,
D3, D4, and D5 are also unchanged; none is a new regression.

### N5 - reviewer network boundary

A78 did not independently rerun the application wrapper or OpenTofu roots
because a clean OpenTofu initialization requires network and the review prompt
forbade network. The build-seat gate results are reported as such rather than
misrepresented as independently confirmed.

### N6 - direct lint execution

`tools/check-ansible.sh` stops at the disclosed stale unit test before its lint
phase. A78 instead ran all four lint and four syntax profiles directly; all
passed.

## Next boundary

The M1/M2 review gate is closed. The next permissible artifact is a separately
reviewed clean-worker replacement plan. Requirement-1 evidence must remain red
until reviewed source is live on a clean replacement and that fixture is rerun.
Worker `588778422` remains ineligible and its taint marker must not be cleared.
No provider request, cap action, credential issuance, behavioral acceptance,
requirement-3 work, or qualification-flag change is authorized. A119 remains
reserved.
