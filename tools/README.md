# Tools

Repository checks, bootstrap helpers, bench scripts, and measurement scripts.
They are not factory runtime. Bench tools probe providers and harnesses, write
evidence under `research/`, and never edit the decision log or reseat models on
their own.

| Script | Purpose |
| :-- | :-- |
| `check-application.sh` | Hosted/local Rust, supply-chain, constitution, and model gate |
| `prepare-state-ci.sh` | Provision roles, migrate, and grant a pinned disposable PostgreSQL service |
| `check-state.sh` | PostgreSQL durability, complete grant matrix, A94 canary, shared catalog, and ERD drift gate |
| `check-state-restart.sh` | Restart PostgreSQL at the declared post-commit boundary and prove retry idempotence |
| `check-constitution.sh` | Verify the reviewed `AGENTS.md` digest |
| `install-rustup.sh` | Install checksum-pinned rustup and resolve `rust-toolchain.toml` |
| `install-rust-tools.sh` | Install checksum-pinned cargo-audit and cargo-deny binaries |
| `smoke-github-app.sh` | Mint a narrowed App token and prove repository scoping without printing credentials |
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
