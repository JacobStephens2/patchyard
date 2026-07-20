# tools/

Bench and measurement scripts. Not factory runtime; they probe providers and
harnesses, write evidence under `research/`, and never edit the decision log
or reseat models on their own.

| Script | Purpose |
| :-- | :-- |
| `aa-sweep.py` | Artificial Analysis catalog snapshot + move report |
| `check-bench.py` | Validate `docs/bench.json` (schema + invariants) and sync the generated Pairs table in `docs/bench.md` (`--write` to regenerate; no flag = drift check) |
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
