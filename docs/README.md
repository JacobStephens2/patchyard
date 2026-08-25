# docs/

Factory documentation that is not the phase-1 build contract (`SPEC.md` /
`PLAN.md` at the repo root) and not the constitution (`AGENTS.md`).

| File | Kind | Authority |
| :-- | :-- | :-- |
| [`decision-log.md`](decision-log.md) | Design authority | Canonical ruling log (accepted / deferred / rejected) |
| [`model-boundary.md`](model-boundary.md) | Design authority | What belongs in `model/factory-model.json` |
| [`repository-boundary.md`](repository-boundary.md) | Design authority | Factory repo vs orchestration provenance |
| [`schema.mmd`](schema.mmd) | Generated projection | Mermaid ERD byte-generated from the migrated PostgreSQL catalog; never hand-edited |
| [`bench.md`](bench.md) | Living ops | At-a-glance pairing (provider/harness/model/reasoning) status; cites `research/`. Its Pairs table is generated from `bench.json` |
| [`bench.json`](bench.json) | Living ops | Structured source of truth for the Pairs table (schema: [`bench.schema.json`](bench.schema.json)). Edit it, then run `python3 tools/check-bench.py --write` |
| [`rust-practices.md`](rust-practices.md) | Living ops | Binding Rust rules distilled from the council research; rules activate at tagged sessions |
| [`agent-content-trust.md`](agent-content-trust.md) | Living ops | Binding content-trust floor (F1-F8) - hostile request content never becomes agent instructions; session-tagged |
| [`dashboard-security.md`](dashboard-security.md) | Living ops | Binding rendering/CSP (session 11) + upload-hardening (session 12) floor for the privileged admin dashboard; session-tagged |
| [`session-8-triage-plan-bin.md`](session-8-triage-plan-bin.md) | Build evidence | Typed triage boundary, provider-free replay, and durable plan-bin transition contract |
| [`stack.md`](stack.md) | Living ops | Canonical technology stack with ruling anchors; exclusions enforced by `tools/check-stack.py` in CI |
| [`bedrock-haiku.md`](bedrock-haiku.md) | Living ops | Bedrock Haiku + Claude Code runbook |
| [`vertex-access.md`](vertex-access.md) | Living ops | Vertex AI project / SA handoff for bench |
| [`ideas.md`](ideas.md) | Scratch inbox | No authority; graduate into the decision log |
| [`git-signing.md`](git-signing.md) | Ops | SSH commit signing so GitHub shows Verified for JacobStephens2 |
| [`production-cutover.md`](production-cutover.md) | Ops | Issue 207: what flips the resident daemon to real Fieldbook, and the checklist before merge and converge |

Nothing in this directory is factory runtime. Runtime state will live under
`/var/lib/patchyard/` (see `SPEC.md`).
