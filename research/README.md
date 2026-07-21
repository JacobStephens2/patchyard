# research/

Dated, world-facing evidence for harness and provider measurements, external
briefs, and their responses. **`docs/bench.md` is the living summary**; this
tree holds the records it cites.

## Topic layout

| Directory | Contents |
| :-- | :-- |
| [`floors/`](floors/) | Floor / muse-smoke harness probes |
| [`muse-spark/`](muse-spark/) | Muse Spark 1.1 substitution investigation |
| [`deepseek-v4/`](deepseek-v4/) | DeepSeek V4 × DeepClaude / DeepInfra |
| [`gpt-oss-120b/`](gpt-oss-120b/) | gpt-oss-120b harness selection and Cerebras work |
| [`claude-code/`](claude-code/) | Claude Code gateways and Bedrock Haiku |
| [`command-a-plus/`](command-a-plus/) | Command A+ × OpenCode |
| [`long-spec-speed/`](long-spec-speed/) | Long-form DOCX-spec speed comparisons |
| [`aa-snapshots/`](aa-snapshots/) | Artificial Analysis catalog snapshots (`tools/aa-sweep.py`) |
| [`isolation/`](isolation/) | Session 3 Firecracker/rootless-Podman manifest, harness, and raw probe evidence |

## Conventions

1. **Date-prefix filenames:** `YYYY-MM-DD-kebab-topic.ext`.
2. **One summary markdown per investigation**; bulk evidence
   (`.json`, `.jsonl`, wire captures, patches) sits beside it in the same
   topic directory.
3. **Update `docs/bench.md`** when a record changes a floor result or seat
   standing - do not fold status into the dated file alone.
4. **No authority.** Research informs rulings; it does not replace
   `docs/decision-log.md` or `SPEC.md`.

Imported external briefs may retain their original body; rename the file to
kebab-case when they land so path links stay portable.
