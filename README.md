# factory

*(GitHub: `JacobStephens2/patchyard`; local checkout on the
orchestration VM lives at `/srv/orchestration/patchyard/` to avoid
colliding with the orchestration repo's `factory/queue/` until the queue
migrates here at build.)*

Patchyard's software factory: small, self-describing staff requests in, evidenced
pull requests out. One human gate - the PR - held by the engineering
department + the company owner. The production deploy path is never touched.

- **Spec:** [SPEC.md](SPEC.md) - the phase-1 build contract.
- **Design record:** [`docs/decision-log.md`](docs/decision-log.md) is the
  canonical 87-ruling log. The independent proposals, comparison and
  historical synthesis remain as provenance in the orchestration repo at
  `projects/software-factory/`; the interactive review is at
  https://report.example.com/software-factory-review.html. Repository
  ownership is documented in
  [`docs/repository-boundary.md`](docs/repository-boundary.md).
- **Constitution:** [`agents.md`](agents.md). Its hard rules ride every factory
  agent prompt and change only through a human-reviewed pull request.
- **Acceptance fixtures:** sanitized replay inputs live under `fixtures/`;
  raw requests and screenshots never enter Git.
- **Canonical model:** `factory-model.json`, governed by
  `factory-model.schema.json` and the boundary in
  [`docs/model-boundary.md`](docs/model-boundary.md). Its canonical JSON
  SHA-256 is committed in `factory-model.sha256`. The model contains stable,
  queryable architecture and limits; prose, people, status, evidence and
  runtime state live elsewhere.

## Model workflow

Install the model-validation dependency into the development environment:

```bash
python3 -m pip install -r requirements-model.txt
```

After a semantic model edit, increment `modelVersion`, then run:

```bash
python3 model-id.py --write
python3 render-model.py
./render-model-assets.sh
./check-model.sh
```

`check-model.sh` rejects schema violations, duplicate JSON keys, broken graph
references and invariants, a stale canonical identity, stale text projections,
or failing validator tests. Web deployments copy the JSON, schema, identity,
Mermaid, SVG and PNG as generated artifacts; the factory-repo copies remain
canonical.

Build status: **approved in scope, not yet started** - console ruling
2026-07-16, "don't build it yet." Nothing in this repo executes anything
until Jacob's go.
