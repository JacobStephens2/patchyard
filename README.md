# factory

*(GitHub: `JacobStephens2/patchyard`; local checkout on the
orchestration VM lives at `/srv/orchestration/patchyard/` to avoid
colliding with the orchestration repo's `factory/queue/` until the queue
migrates here at build.)*

Patchyard's software factory: small, self-describing staff requests in, evidenced
pull requests out. One human gate - the PR - held by the engineering
department + the company owner. The production deploy path is never touched.

## Layout

| Path | Role |
| :-- | :-- |
| `SPEC.md` / `PLAN.md` | Phase-1 build contract and session plan |
| `AGENTS.md` | Constitution - hard rules that ride every factory agent prompt |
| `model/` | Canonical architecture model + validators, projectors, tests |
| `docs/` | Decision log, boundaries, living ops (bench, runbooks), ideas inbox |
| `research/` | Dated world-facing evidence, grouped by topic |
| `reviews/` | Critiques of our own artifacts plus dispositions |
| `fixtures/` | Sanitized acceptance fixtures (`alphabetize/`) and bench prompts (`bench/`) |
| `tools/` | Bench and measurement scripts (not factory runtime) |

Root stays thin so the upcoming Cargo workspace can land without fighting a
pile of Python helpers. Runtime code will live beside this tree at build;
design authority and evidence stay where they are.

## Key documents

- **Spec:** [SPEC.md](SPEC.md) - the phase-1 build contract.
- **Bench status:** [`docs/bench.md`](docs/bench.md) - living at-a-glance
  status of every (model × harness) pair: floor result, seat eligibility,
  provenance. Evidence lives in the dated records it cites.
- **Bedrock Haiku runbook:**
  [`docs/bedrock-haiku.md`](docs/bedrock-haiku.md) - provisioned identities,
  1Password mapping, STS boundary, verified Claude Code launcher, manual
  smoke test, costs, and remaining isolation work.
- **Dated records:** [`reviews/`](reviews/) holds critiques of our own
  artifacts plus their dispositions; [`research/`](research/) holds
  world-facing evidence - harness and provider measurements, external
  research briefs and their responses. See [`research/README.md`](research/README.md).
- **Ideas inbox:** [`docs/ideas.md`](docs/ideas.md) - hand-written,
  pre-ruling scratch space. Carries no authority; ideas graduate into the
  decision log or die there.
- **Design record:** [`docs/decision-log.md`](docs/decision-log.md) is the
  canonical 87-ruling log. The independent proposals, comparison and
  historical synthesis remain as provenance in the orchestration repo at
  `projects/software-factory/`; the interactive review is at
  https://report.example.com/software-factory-review.html. Repository
  ownership is documented in
  [`docs/repository-boundary.md`](docs/repository-boundary.md).
- **Constitution:** [`AGENTS.md`](AGENTS.md). Its hard rules ride every factory
  agent prompt and change only through a human-reviewed pull request.
- **Acceptance fixtures:** sanitized replay inputs live under
  `fixtures/alphabetize/`; raw requests and screenshots never enter Git.
  Bench-only prompts live under `fixtures/bench/`.
- **Canonical model:** `model/factory-model.json`, governed by
  `model/factory-model.schema.json` and the boundary in
  [`docs/model-boundary.md`](docs/model-boundary.md). Its canonical JSON
  SHA-256 is committed in `model/factory-model.sha256`. The model contains
  stable, queryable architecture and limits; prose, people, status, evidence
  and runtime state live elsewhere.

## Model workflow

Install the model-validation dependency into the development environment:

```bash
python3 -m pip install -r model/requirements-model.txt
```

After a semantic model edit, increment `modelVersion`, then run:

```bash
python3 model/model-id.py --write
python3 model/render-model.py
./model/render-model-assets.sh
./model/check-model.sh
```

`model/check-model.sh` rejects schema violations, duplicate JSON keys, broken
graph references and invariants, a stale canonical identity, stale text
projections, or failing validator tests. Web deployments copy the JSON,
schema, identity, Mermaid, SVG and PNG as generated artifacts; the
`model/` copies remain canonical.

## Bench tools

Measurement scripts live under [`tools/`](tools/) (see
[`tools/README.md`](tools/README.md)). They write evidence into `research/`
and never reseat production policy.

Build status: **approved in scope, not yet started** - console ruling
2026-07-16, "don't build it yet." Nothing in this repo executes factory
runtime until Jacob's go.
