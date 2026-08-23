# Tools

Repository checks, bootstrap helpers, bench scripts, and measurement scripts.
Most are not factory runtime. An explicitly selected subset also serves as the
source for control-plane runtime assertions installed by Ansible; infrastructure
owns their deployed paths and schedules. Bench tools probe providers and
harnesses, write evidence under `research/`, and never edit the decision log or
reseat models on their own.

| Script | Purpose |
| :-- | :-- |
| `check-application.sh` | Hosted/local Rust, supply-chain, constitution, and model gate |
| `prepare-state-ci.sh` | Provision roles, migrate, and grant a pinned disposable PostgreSQL service |
| `check-state.sh` | PostgreSQL durability, complete grant matrix, A94 canary, shared catalog, and ERD drift gate |
| `check-state-restart.sh` | Restart PostgreSQL at the declared post-commit boundary and prove retry idempotence |
| `check-constitution.sh` | Verify the reviewed `AGENTS.md` digest |
| `check-freeze-graph.py` | Report the stable result-rooted frozen set and fail on digest drift |
| `check-credential-qualification.py` | Enforce A113's per-provider conditional by mapping six Requirements to five committed Results and re-running their checkers |
| `check-openai-identity-liveness.py` | Validate the A150 registry statically and serve as the source for the Ansible-installed daily control-plane liveness assertion |
| `install-rustup.sh` | Install checksum-pinned rustup and resolve `rust-toolchain.toml` |
| `install-rust-tools.sh` | Install checksum-pinned cargo-audit, cargo-deny, cargo-vet, and cargo-machete binaries |
| `install-shellcheck.sh` | Install the checksum-pinned ShellCheck used for privileged boundary scripts |
| `smoke-github-app.sh` | Mint a narrowed App token and prove repository scoping without printing credentials |
| `anthropic-wif-lifecycle.py` | Root-only A113 expiry, exchange, public-JWKS, key-activation, and rollback harness; never emits a bearer or assertion |
| `anthropic-wif-revocation.py` | Source-bound exchange adapter that preserves the qualified expiry harness while recording post-mutation request starts and A126's event-specific denial contract |
| `anthropic-wif-crash-cleanup.py` | Source-bound A130 supervisor, SIGKILL checkpoint, same-surface credential scanner, and sanitized result collector; never invalidates a provider bearer |
| `anthropic-wif-lifecycle-admin.py` | Attended fail-closed rule disable/restore and inline-JWKS overlap/retire/rollback administration; mints its bearer from the `patchyard-admin` operator admin profile via `ant auth print-credentials` |
| `openai-wif-issuance.py` | Source-bound attended adapter for one sanitized OpenAI token-exchange observation; never writes the assertion or bearer |
| `openai-wif-expiry.py` | Source-bound attended adapter for one expired-assertion OpenAI exchange with the reviewed 401-and-no-bearer predicate; v1 output stays non-qualifying pending A151 liveness support |
| `openai-wif-crash-cleanup.py` | Source-bound A130 supervisor, SIGKILL boundary, process-image/tmpfs scanner, and sanitized OpenAI Result collector |
| `control-plane-attestation-v1.py` | Digest-loaded A132 Attestation envelope with bounded console readings and explicit A136 party disclosure |
| `openai-wif-federation-revocation.py` | Attended requirement 4 collector; records the A146 model-operated shape (A148 route authorization or A146 comment, two Saves, five reloaded readings) and the A129 bracket |
| `openai-wif-signing-key-rotation.py` | Attended requirement 5 collector; derives both key identifiers, pauses for JWK control-plane mutations, and records the A129 bracket |
| `check-anthropic-expiry.py` | Validate the source-only expiry contract or its future credential-free live fixture |
| `check-anthropic-revocation.py` | Validate federation-revocation/key-rotation evidence; an unpinned denial is accepted as observation-only with exit 2 and a JSON qualification blocker |
| `check-anthropic-crash-cleanup.py` | Validate A130 local non-recoverability, its non-vacuous positive control, inert abrupt-death record, and explicit provider-exposure boundary |
| `check-openai-wif-issuance.py` | Validate the OpenAI policy, unenforced first-response predicate, non-qualifying observation, or synthetic contract fixture |
| `check-openai-wif-expiry.py` | Validate the reviewed OpenAI expired-assertion predicate, the A153 historical Result, a non-qualifying later observation, or synthetic Fixture |
| `check-openai-wif-crash-cleanup.py` | Validate the OpenAI A130 process-image positive control, SIGKILL, inert abrupt-death record, and local exposure boundary |
| `check-openai-wif-federation-revocation.py` | Validate the requirement-4 A146 record shape, A148 route authorization or A146 comment, settling floors, same-surface baseline/denial/bracketing controls, and the reviewed 401-and-no-bearer revocation predicate |
| `check-openai-wif-signing-key-rotation.py` | Validate requirement 5 derived keys, Attestations, overlap control, settling floors, A129 bracket, and the reviewed 401-and-no-bearer retired-key predicate |
| `aa-sweep.py` | Artificial Analysis catalog snapshot + move report |
| `check-bench.py` | Validate `docs/bench.json` (schema + invariants) and sync the generated Pairs table in `docs/bench.md` (`--write` to regenerate; no flag = drift check) |
| `check-seats.py` | Cross-check `docs/bench.md` § Seat preference orders against `bench.json` + the A61 allowlist (membership, preferred harness, floors, rank ordering, speed values; `--strict` fails on warnings) |
| `benchmark_spec_speed.py` | Direct-API long-spec speed probe |
| `benchmark_harness_speed.py` | OpenCode wall-time long-spec probe |
| `benchmark_harmonyagent_cerebras.py` | Harmony Agent × Cerebras diagnostic |

Default long-spec prompt:

```text
fixtures/bench/docx-spec-speed/request.md
```

Run from the repository root (or pass absolute `--prompt` / paths):

```bash
python3 tools/aa-sweep.py
python3 tools/benchmark_spec_speed.py --output-dir /tmp/patchyard-docx-spec-speed
python3 tools/benchmark_harness_speed.py --output-dir /tmp/patchyard-docx-spec-speed
```

Credentials come from the orchestrator environment (`claude-orchestrator`);
do not put keys in this directory.

The state scripts require the disposable PostgreSQL service variables supplied
by `.github/workflows/application.yml`; without those variables the ordinary
local application gate runs only database-independent tests.

## Local git hooks

`.githooks/pre-push` re-runs `check-codebase.sh` before every push and blocks
when `docs/codebase-metrics.json` is stale, so the projection failure lands
locally instead of in the Application CI check. Activate once per clone with
`git config core.hooksPath .githooks` (worktrees inherit it). The hook needs
the pinned tokei; install with `tools/install-tokei.sh`.
