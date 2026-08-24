# factory-verify contract

`factory-verify` is the deterministic gate vocabulary used after an isolated
implement worker returns a candidate patch. Session 6 supplies pure validation
over bounded JSON inputs; `ledger-append` additionally performs the ruled
PostgreSQL write only after validation. Session 7 adds collection of real
preview DOM and the worker-side targeted-test runtime.

All JSON inputs reject unknown fields and are capped at 1 MiB. A nonzero exit
means the patch cannot remain in lane A.

## Commands

- `caps --manifest DIFF.json --expected-base-sha SHA` counts additions plus
  deletions against the recorded 40-hex base. Tests and whitespace-only lines
  count. Renames, mode changes, binary changes, and generated changes are
  explicit fields and fail closed. The open-PR cap remains publisher state.
- `deny-paths --manifest DIFF.json` checks both old and final paths against all
  constitution deny categories: schema/migrations; auth/sessions/permissions/
  secrets; finance; outbound/scheduled work; customer-facing surfaces;
  dependencies/lockfiles; CI; and deploy paths. It also rejects the factory's
  own gate surfaces: `.github/workflows/`, `infra/`, `policy/`, and
  `crates/factory-verify/`.
- `postconditions --evidence SORT.json` consumes normalized snapshots shaped
  like [`sort-valid.json`](../crates/factory-verify/tests/fixtures/sort-valid.json).
  It requires identical WHERE clauses and shared-getter callers; permits a
  `listOrder` replacement only when recorded as presentation order; preserves
  the exact option multiset, values, selected flags, duplicates, and blank
  sentinel positions; and requires a stable Unicode NFKC-case-folded first-name
  order.
- `ledger-append --record RUN.json --database-url URL` requires run/request UUIDs,
  base SHA, branch, lane, skill, resolved model/CLI/harness/provider/effort,
  routing-config version, and all eight canonical SHA-256 provenance fields.
  Only a validated record can connect. The run and `run.queued` event commit in
  one transaction.
- `runtime --manifest RUNTIME.json --worktree TREE --patch PATCH` runs only as
  `factory-worker` from an allowlisted clean environment. The root launcher
  first holds the same nonblocking worker lock used by Firecracker and asserts
  that no agent VMM or jailer remains. It then checks the exact source archive
  and patch hashes, creates a remote-free worktree, applies the patch, and
  invokes the checksum-pinned PHPUnit PHAR with only the enumerated `tests/`
  paths. A deterministic filesystem hash (content, mode, path, and symlink
  target; `.git` excluded) must be byte-identical before and after PHPUnit.

## Session 7 live evidence boundary

`preview/patchyard-preview-lease.py` is the forced SSH command on the shared
preview host. A lease records owner, request ID, expected SHA, creation and
expiry timestamps, and a random lease ID in canonical `slots.json`. The
editable preview checkout and the running container must both report the exact
expected `git rev-parse HEAD`; every capture verifies that invariant before and
after Chromium. Release is in the coordinator's `finally` path, failed acquire
also destroys its slot, and a systemd timer sweeps expired leases.

The Session 7 browser helper installs the preview bearer into a temporary
Manifest V3 header extension scoped to the one leased host. It accepts only a
numbered preview URL and bounded element-ID selectors, captures the DOM and a
screenshot, extracts option order, and destroys the extension/profile. The
stronger per-run no-authority browser isolation remains Session 13 scope.

## Verifier rejection contract

This binds whatever program `FACTORY_VERIFIER_PROGRAM` names, not one
implementation. A verifier is swappable; what it must say when it rejects a
patch is not.

**A rejection states its reason.** On exit non-zero the program writes
`evidence.json` into its output directory carrying a non-empty `failures` array,
each entry naming the `assertion` that failed and what it `expected` against
what it `observed`:

```json
{
  "schema_version": 1,
  "status": "failed",
  "gate": "alphabetize-semantics",
  "failures": [
    {
      "assertion": "patch_touches_assign",
      "expected": "at least one line matching mfieldbook/leads/assign.php",
      "observed": "0 matching lines"
    }
  ],
  "publish_invoked": false
}
```

**Failing through a silent builtin is not a way to reject a patch.** A bare
`grep -q` or `test` under `set -e` exits non-zero having said nothing, and the
verdict the supervisor is left with carries no reason at all. Collect the failed
assertions and write them; do not let the shell terminate the program on the
first one.

`fixtures/pipeline/bin/verifier-stub` is the worked example of the shape,
`verifier-task-reject-stub` the worked example of a task-shape rejection, and
`verifier-silent-fail-stub` the deliberate breach the supervisor is tested
against.

**A rejection says what it rejected.** An optional `rejects` field names the
subject: `"patch"` (the default when the field is absent) means a different
patch could satisfy this gate; `"task"` means the task's own shape was rejected -
it is over-cap, it names a denied path, its acceptance check is not statable -
and no patch the task can produce will pass. Set it to `"task"` only when that
is true, because it ends the run.

### What the supervisor does with a rejection

`ProcessVerifierBackend::verify` reads the reason rather than trusting the exit
code alone. Exit 0 is a pass; a non-zero exit becomes a `VerifyRejection`
carrying one of four reason codes:

| Outcome | `reason_code` | Repair attempt |
| --- | --- | --- |
| verdict states a reason, rejects the patch | `deterministic_verifier_failed` | spent |
| verdict states a reason, rejects the task | `verifier_rejected_task` | not spent |
| verdict states a reason, `rejects` unrecognized | `verifier_rejection_subject_unknown` | not spent |
| verdict states no reason | `verifier_reason_missing` | not spent |

A verifier that wrote no `evidence.json` gets a synthesized verdict instead of
an empty one: `synthesized: true`, the exit code, and whatever the process put
on stdout and stderr, each bounded at 16 KiB with a `_truncated` flag. The
untruncated streams remain in the run's `transcript.log`. This is the only
account of such a rejection that exists, so it is carried rather than discarded.

### The one repair attempt, and when it is worth spending

The repair attempt is a second live implement run: another bundle, another
bearer, another provider bill. It is spent only on a rejection that
affirmatively states its assertions *and* affirmatively rejects the patch.
Request `bb995b19` spent one on neither - the verifier rejected a correct patch
and preserved no reason - and the run returned the byte-identical patch, which
is the only thing a model asked to fix an undisclosed failure can do.

So an unrepairable rejection escalates on one attempt rather than two. Both
escalations name themselves in the run's terminal event, because "ran out of
attempts" and "was never repairable" are different things to read in a ledger:

| Terminal event | `reason` | Attempts |
| --- | --- | --- |
| `repair.exhausted` | `repair_exhausted` | 2 |
| `repair.not_attempted` | `verify_not_repairable` | 1 |

Both payloads carry the `reason_code` that decided it, and `repair.not_attempted`
also carries the `gate`.

When the attempt *is* spent, it is handed what failed. The `verify_failure` on
the repair packet carries the gate, the reason code, the artifact holding the
full verdict, and the stated assertions themselves - at most 20 of them, each
field at most 2 KiB and stripped of control characters, with
`failures_truncated` set when the list was cut. The control plane appends that
object to the worker's `request.md`, which is the only channel the isolated
worker reads, as one line of JSON inside a `<VERIFIER_REJECTION_JSON
authority="none">` block introduced as data rather than instructions. A
verifier's output is an untrusted channel like any other tool stdout (F2 in
[`agent-content-trust.md`](agent-content-trust.md)), and this one is now the
only variable text in that file - it is labeled and stripped so it cannot forge
structure in the brief it is quoted into. That render is
`patchyard-render-request`, executed by
`infra/ansible/tests/test_repair_brief_render.py`; why it lives on the control
plane rather than in the supervisor is recorded in
[`session-9-pipeline.md`](session-9-pipeline.md).

`verifier_reason_missing` names a breach of this contract, not a healthy
failure. It does not change the disposition of the patch, which has already
failed closed - it changes what the run says about *why*. The reason is read
leniently on purpose: bytes that do not parse, an unexpected shape, and an
unknown key all read as "no reason stated" rather than as an error. A gap in
diagnostics must never be able to fail a run harder than the gate that produced
it already did.

## A10 mutation inventory

| Subcommand | Rejected mutations exercised by `cargo test` |
| --- | --- |
| `caps` | recorded-base change; whitespace-only padding; third file; rename; mode; binary; generated change |
| `deny-paths` | one path from every constitution deny category; workflow/infra/policy/verifier-self gate changes; forbidden rename source and destination |
| `postconditions` | WHERE-clause change; option-value change; option membership; sort-key swap; selected value; shared caller; priority-bearing `listOrder`; sentinel move; duplicate count |
| `ledger-append` | each of eight hash fields missing/malformed; each routing field missing/blank; invalid run envelope fields |
| `runtime` | unsafe/duplicate/unbounded PHPUnit targets; content/mode tree mutation; wrong identity, environment, hashes, or Git remote |

`tools/check-factory-verify-release.sh` creates two clean release target trees
and requires byte-identical binary SHA-256 values. It then installs one only
after checksum verification and rolls back to a distinct runnable prior binary,
again checksum-verified. The hosted application workflow runs this drill.
