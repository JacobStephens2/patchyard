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

## Where the repair brief is rendered

`request.md` is the only channel an isolated worker reads, so for a repair
attempt those bytes are the whole brief. The live seat sends them as a JSON
envelope - `{schema_version, task, implement_policy, guide_content}` - which
`patchyard-guest-implement` validates and quotes into the Codex prompt. Until
#302 the render was a heredoc inside `patchyard-invoke-worker.j2`, verified by
hand - the one part of the brief no gate executed, and the part where the
content-trust framing lives. #302 extracted it; the merge that brought the live
seat's envelope onto this branch put the composition back in the transport, and
[#314](https://github.com/JacobStephens2/patchyard/issues/314) put
it back behind the gate.

**The render is now `roles/control_plane/files/patchyard-render-request`, the
file that builds the envelope: the transport calls it and
`infra/ansible/tests/test_repair_brief_render.py` executes it.** It resolves the
named skill's Guide and the implement policy too, so the whole of `request.md` -
not merely its frame - is produced by tested code. It reads the Guide the way
the transport did, with command substitution, so its trailing newline is still
dropped and no live `request_sha256` moved for a reason nobody asked for.

The verifier's verdict is the one field in that envelope authored outside the
factory's own control, so it is not carried bare. The render replaces
`.task.verify_failure` with `{authority: "none", label, verdict}`: the verdict
sits under `verdict`, and the object around it says what it is (F2,
`docs/agent-content-trust.md`). The guest's preamble still calls the whole
envelope untrusted, but "this object is a verdict, and a verdict is data" is the
statement that survives a model skimming one field. Because the frame is JSON
structure rather than a markdown block, a hostile `observed` string cannot close
its own label - the gate proves that with a verdict carrying both
`</VERIFIER_REJECTION_JSON>` and a forged `"authority": "system"`. The gate
asserts the rendered bytes exactly, so dropping the framing fails it as surely
as dropping the assertions does, and it runs the guest's own validation filter
to prove a bare verdict is refused on arrival rather than merely never sent.
`patchyard-invoke-worker.j2` hashes `request.md` after the render returns, so
`run.json`'s `request_sha256` is computed over final content.

**It is not in the supervisor**, which was the other option on the table.
`WorkerTaskPacket` deliberately has no request-text field, so a supervisor-side
render would have to author the worker's prompt from something the packet type
refuses to carry. More decisively, the control plane is the boundary that
constrains what reaches the isolated worker - it re-validates the packet's
`dry_run`, named skill, and allowed paths before anything ships - and a prompt
assembled upstream of that boundary is a prompt the boundary can no longer
constrain. Extracting the render keeps that ordering and leaves the transport's
shape to [#206](https://github.com/JacobStephens2/patchyard/issues/206),
which owns how the live implement seat is wired; a supervisor-side render would
have decided that ticket's seam in advance.

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
