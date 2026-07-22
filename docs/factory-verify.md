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
  base SHA, branch, lane, skill, and all eight canonical SHA-256 provenance
  fields. Only a validated record can connect. The run and `run.queued` event
  commit in one transaction.
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

## A10 mutation inventory

| Subcommand | Rejected mutations exercised by `cargo test` |
| --- | --- |
| `caps` | recorded-base change; whitespace-only padding; third file; rename; mode; binary; generated change |
| `deny-paths` | one path from every constitution deny category; workflow/infra/policy/verifier-self gate changes; forbidden rename source and destination |
| `postconditions` | WHERE-clause change; option-value change; option membership; sort-key swap; selected value; shared caller; priority-bearing `listOrder`; sentinel move; duplicate count |
| `ledger-append` | each of eight provenance fields missing; each malformed; invalid run envelope fields |
| `runtime` | unsafe/duplicate/unbounded PHPUnit targets; content/mode tree mutation; wrong identity, environment, hashes, or Git remote |

`tools/check-factory-verify-release.sh` creates two clean release target trees
and requires byte-identical binary SHA-256 values. It then installs one only
after checksum verification and rolls back to a distinct runnable prior binary,
again checksum-verified. The hosted application workflow runs this drill.
