# Session 8 - triage and the plan bin

Session 8 makes the intent boundary executable without invoking a model.

## Triage contract

- `policy/triage.md` grants exactly Read, Grep, and Glob. Its rendered prompt
  carries the exact `AGENTS.md` hard-rules section and JSON-datamarks request
  body and screenshot OCR as `authority: none`.
- `policy/rubric.md` contains one parsed JSON policy block. The classifier takes
  only a Rust `TaskSpec`; request text and model confidence are absent from its
  function signature.
- `policy/task-spec.schema.json` documents the same deny-unknown-fields contract
  enforced by Rust: exact paths/globs, intent class, typed acceptance tests,
  dependency/test/CI flags, budget authority, and Guide.
- `fixtures/triage/replay-manifest.json` records expected lanes for positive,
  deny-rule, over-cap, not-code, ambiguous, and hostile-request cases. Run it
  with `cargo run --locked -p factoryctl -- triage-replay`; no provider or
  database is involved.

Lane A requires exact evidenced mfieldbook targets, a supported named skill, the
matching skill Guide, deterministic acceptance, no effect glob, no dependency
or CI flag, and the 2-file/50-line policy budget. Intent routes and deny rules
can remove authority; confidence cannot add it.

## Durable plan-bin transitions

Non-A triage atomically appends `triage.classified` (including the validated
TaskSpec and hashes) plus `plan.entered`, changes the request to `plan_bin`, and
releases its claim. Generic claim and close operations reject that state, so
the ruled transition cannot be bypassed.

| Human decision | State/result | Ledger event |
| --- | --- | --- |
| Approve B | queued for implement; approved-plan Guide and human budget become the authoritative TaskSpec | `plan.reenter.implement` |
| Answer D | queued for triage; answer stored as an authority-free untrusted channel | `plan.reenter.triage` |
| Mark C executed | request closed as `executed-not-code` | `plan.closed` |
| Reject B/C/D | request closed as `rejected-at-plan`, exact reason retained | `plan.closed` |

Every decision has a UUID and content digest. A byte-equivalent retry returns
the original transition without appending another event; reusing an ID with
different content fails closed. Request-row locking serializes concurrent
decisions. `authoritative_implementation_task_spec` returns a TaskSpec only
after lane-A routing or approved-B re-entry; it never reads `requests.body`.

The disposable-PostgreSQL test
`every_plan_bin_reentry_and_close_has_its_ledger_row` exercises all four edges,
their request states, exact ledger rows, idempotent B approval, D's untrusted
label, approved-B TaskSpec retrieval, and the generic claim/close bypass guard.
Hosted application CI runs it with the real migration and supervisor grants.
