# Rust practice floor

Distilled 2026-07-21 from the model-council synthesis at [`research/rust/2026-07-17_rust-best-practices-perplexity-computer-model-council.md`](../research/rust/2026-07-17_rust-best-practices-perplexity-computer-model-council.md) (three-model convergence + adjudicated divergences). This page carries only the **binding** rules; each activates at the session that first makes it meaningful, and every rule that can be mechanized moves into `tools/check-application.sh` when it activates. Build-session prompts cite this file; deviations are PR-visible decisions, not style drift.

## Standing (active since session 1, enforced today)

- `unsafe_code = "forbid"` workspace-wide. This supersedes the council's SAFETY-comment + Miri disciplines by making them moot; lifting `forbid` anywhere requires a ruling, which would activate those disciplines in the same PR.
- Flat workspace, virtual root, `resolver = "3"` explicit, crates one level deep. Exact toolchain pin (`rust-toolchain.toml`) rather than an MSRV floor - an unpublished application may pin what a library could only bound.
- CI baseline: `cargo fmt --check`, `clippy -Dwarnings`, `cargo test`, `cargo-audit`, `cargo-deny`, the constitution digest. `cargo-semver-checks` is deliberately absent: `publish = false`, no external consumers.

## Activates at session 2 - first real dependencies

- **`[workspace.dependencies]` inheritance from the first shared dependency.** Versions live once, in the root manifest.
- **`cargo vet` joins CI the day the first dependency lands** - audit chain-of-custody, not just CVE scanning - while the tree is small enough to vet completely. An unused-dependency check (`cargo-machete` or equivalent) joins beside it.
- **Errors split by audience and layer**: `thiserror` for library error types once they multiply; stacked per-layer errors at crate boundaries (each crate wraps the layer below as an opaque source) - never one workspace-spanning enum, and `anyhow` only in binary-crate top-level glue, never in a library signature.
- **Property tests (`proptest`) for state-machine invariants** - the session-2 lease/transition/idempotency contracts are exactly the bug class property testing exists for.

## Activates at session 9 - the supervisor daemon (async arrives in force)

- **One runtime per executable.** No nested or ad-hoc runtimes.
- **No lock guard held across `.await`.** `std::sync::Mutex` for short synchronous critical sections; `tokio::sync::Mutex` only where awaiting under the lock is genuinely required and stated.
- **Cancellation-safety audit, recorded in the PR**: every `select!` and `timeout` reviewed against Tokio's cancellation matrix - primitives that lose *data* when dropped (`read_exact`, `write_all`) vs. those that lose *queue position* (`Mutex::lock`, `Semaphore::acquire`, `Notify::notified`). The audit is a checklist item of session 9's exit, not a vibe.
- **The 10-100 µs rule**: CPU-bound or blocking work beyond that threshold leaves the executor (`spawn_blocking` / rayon / dedicated thread). Remember why it passes dev and fails prod: the multi-thread runtime hides starvation on an idle 8-core laptop.
- **Fallible cleanup is explicit `close()`/`shutdown()`; `Drop` is best-effort only.** For the supervisor this is a safety property, not style: worker teardown, lease release, and kill-path cleanup must be awaitable, checkable operations - a failing destructor during a panic aborts the process.

## Activates at session 11 - the dashboard

- The session-9 async rules apply unchanged to Axum handlers and the SSE path.
- `insta` snapshot tests are the sanctioned tool if template regressions bite; adopt on first bite, not preemptively.

## Deliberately not adopted

- Miri, SAFETY comments (moot under `forbid`); `cargo-semver-checks` (nothing published); FFI and `no_std` disciplines (no C bindings or embedded targets in scope - if one ever appears, the council doc's GPT 5.5 FFI section is the starting point, behind a ruling).
