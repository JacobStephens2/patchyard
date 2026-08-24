# Session 9 pipeline evidence

`factory-supervisor` is the single pipeline implementation used by its resident
`LISTEN` loop and by `factoryctl run <id>`. The installed Session 9 service is
deliberately dry-run-only and provider-free: its implement, triage, review,
disposition, and verifier commands are fixtures. The private-VPC worker
transport is installed and bounded, but no live provider credential or A-5
qualification is introduced.

## Recovery and authority

- PostgreSQL rows determine work. Startup, every notification, every LISTEN
  reconnect, and a 30-second timer call the same control-first claim sweep.
  Claimed rows sort ahead of queued rows and recovery is not blocked by a later
  daily admission cap.
- `NOTIFY` payloads are wake hints only. No transition depends on payload
  delivery. Worker launch/result intake is keyed by `run_id + attempt`; the
  remote transport resumes a complete result and compensates an incomplete
  staging root.
- All four bounded worker results are persisted and hash-linked before the
  side-effect row becomes `completed`. A restart rebuilds the typed worker
  result from those durable artifacts; a completed effect with missing or
  digest-mismatched results fails closed instead of invoking the worker again.
- The F3 accept automaton receives the authoritative TaskSpec. Its exact
  `allowed_paths` and `allowed_globs` are the scope input before caps, deny
  paths, dependency, sink, and secret gates. Neither its signature nor the
  OutContract contains confidence.
- Triage is the only packet type containing raw request text. Worker, reviewer,
  disposition, dispute, and repair packets are separate deny-unknown-fields
  types without request text or transcript fields. Transcripts go only to the
  artifact store and ledger link; they never become downstream instructions.

## Async cancellation-safety audit

| Site | Futures in competition | Tokio data-loss / queue-position result | Recovery rule |
| --- | --- | --- | --- |
| `process::run_bounded` | `Child::wait`, `CancellationToken::cancelled`, `Sleep` | All three are cancellation-safe. The losing futures own no data buffer or queue position. stdout/stderr drains live in owned tasks and are joined. | Timeout/cancel explicitly kills and reaps the child, then joins both drains. |
| `daemon::run` | `PgListener::recv`, interval tick, shutdown token | Tick and token are cancellation-safe. A cancelled `recv` may lose only a notification wake, never the row or a work queue position. | Every branch scans rows; startup, reconnect, and timer scans close the missed-NOTIFY window. |

There is no `tokio::time::timeout` call in the supervisor. SQLx connection
acquire and OTLP exporter timeouts are library configuration, not cancellation
of a data-bearing future. OTLP is outside the ledger/evidence path and is
fail-open.

No production supervisor module uses a mutex or read/write lock. PostgreSQL
transactions are held across awaits intentionally as database transactions,
not in-process lock guards; no Tokio task can inherit a synchronous guard.

## Executor and cleanup audit

Git tree hashing, artifact hashing/writes/fsync/rename, recursive directory
operations, file hashing, permission changes, and test repository setup use
`spawn_blocking`. Subprocess and filesystem I/O use Tokio. This keeps work that
can exceed the 10-100µs poll budget off executor threads.

Fallible cleanup is explicit and checked:

- `ExactBundle::close` removes the source bundle.
- `DetachedWorktree::close` removes each inspection/materialization/reviewer
  worktree with a fresh cleanup token, so run cancellation cannot cancel the
  cleanup operation itself.
- `ProcessWorkerBackend::teardown` invokes remote teardown before the durable
  `worker.terminated` event, then removes local intake.
- cancellation and kill await worker teardown; kill then releases the lease and
  appends the terminal `run.killed` event.
- `Pipeline::run_claim` explicitly releases its lease on every return path.
- `RuntimeComponents::close` closes the SQLx pool and
  `TelemetryGuard::shutdown` flushes optional telemetry in a blocking task.
  Their `Drop` implementations are not correctness paths.

## Provider-free acceptance fixtures

`cargo test --package factory-supervisor --test pipeline_fixture` proves:

- ALPHABETIZE classifies lane A, targets only
  `mfieldbook/common_functions.php` and `mfieldbook/leads/assign.php`, and produces
  the asserted sorted-permutation patch.
- two reviewers execute at the materialized reviewed SHA; their in-sandbox
  probes cannot see sibling review or shared-scratch paths; both submissions
  cross the supervisor-held barrier before persistence.
- `worker.terminated` precedes `verify.started`; all eight provenance hashes and
  the resolved seat/config version pass the same ledger constructor used by
  PostgreSQL.
- the successful terminal event is `run.dry_run_complete`, with
  `dry_run=true` and `publish_invoked=false`.
- a blocking finding flows through typed author disposition to the third-family
  arbitration stub and escalates.
- a verifier that fails twice gets one repair only, then terminal
  `repair.exhausted` escalation, and that repair attempt is handed the
  assertions the verdict named.
- a rejection the model cannot act on - one stating no reason, or one rejecting
  the task's shape rather than the patch - escalates on the first attempt with
  terminal `repair.not_attempted`, spending no second implement run.
- restart replay completes after the fixture removes the worker executable,
  proving that the durable result is recovered without a second invocation.

The PostgreSQL fixture additionally proves daily admission at claim time,
claimed-row recovery despite that admission limit, pause/resume/kill control
rows, kill's terminal event and lease release, and a timer/startup-style sweep
finding an eligible durable row without relying on a notification or being
starved by an older foreign lease.
