# docs/

Factory documentation that is not the phase-1 build contract (`SPEC.md` /
`PLAN.md` at the repo root) and not the constitution (`agents.md`).

| File | Kind | Authority |
| :-- | :-- | :-- |
| [`decision-log.md`](decision-log.md) | Design authority | Canonical ruling log (accepted / deferred / rejected) |
| [`model-boundary.md`](model-boundary.md) | Design authority | What belongs in `model/factory-model.json` |
| [`repository-boundary.md`](repository-boundary.md) | Design authority | Factory repo vs orchestration provenance |
| [`bench.md`](bench.md) | Living ops | At-a-glance (model × harness) status; cites `research/` |
| [`bedrock-haiku.md`](bedrock-haiku.md) | Living ops | Bedrock Haiku + Claude Code runbook |
| [`vertex-access.md`](vertex-access.md) | Living ops | Vertex AI project / SA handoff for bench |
| [`ideas.md`](ideas.md) | Scratch inbox | No authority; graduate into the decision log |
| [`git-signing.md`](git-signing.md) | Ops | SSH commit signing so GitHub shows Verified for JacobStephens2 |

Nothing in this directory is factory runtime. Runtime state will live under
`/var/lib/patchyard/` (see `SPEC.md`).
