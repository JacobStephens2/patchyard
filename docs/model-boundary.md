# Factory model boundary

`factory-model.json` is the canonical machine-readable architecture model. It
is deliberately narrower than the factory's complete design record.

## What belongs in the model

- Stable identifiers and relationships: lanes, stages, entities, edges and
  macro-stage membership.
- Actor classifications and intake-source classifications.
- Safety limits and the immutable human-approval boundary.
- Structured phase states and measurable evidence thresholds.
- Capacity-simulator inputs.
- Ruling identifiers needed to trace structural choices.

These fields have consumers or invariants that code can validate. The JSON
Schema defines their shape; `validate-model.py` checks cross-references and
graph properties that JSON Schema cannot express.

## What does not belong in the model

- Design rationale, examples, implementation notes and prose restatements of
  graph transitions.
- Named people, availability notes or current approver rosters.
- Repository, pull-request, deployment or branch-protection status.
- Dated demand evidence, review dispositions or build-progress narration.
- Runtime requests, runs, artifacts, leases or current pipeline state.

The phase-1 build contract belongs in `SPEC.md`; its session ordering belongs
in `PLAN.md`; critique records belong in `reviews/`. The decision log and
founding synthesis currently remain in the orchestration repository at
`projects/software-factory/synthesis/`. Runtime state will live in SQLite and
the private artifact store described by the spec.

## Authority and identity

The authorities answer different questions:

1. Human rulings and the decision log say **why** a choice was made.
2. `SPEC.md` says **what must be built** in phase 1.
3. `factory-model.json` says **what the stable architecture is** in a form
   projectors and other software can query.
4. SQLite will say **what is happening now** after the runtime exists.

`factory-model.sha256` is the SHA-256 of the model's stable canonical JSON
serialization: UTF-8, sorted object keys, no insignificant whitespace. A run
must record this identity together with the factory repository commit. The
hash identifies model content; the commit identifies its reviewed history.

## Editing workflow

1. Edit `factory-model.json` and increment `modelVersion` for a semantic
   change. Increment `schemaVersion` only for a schema-contract change.
2. Run `python3 model-id.py --write`.
3. Run `python3 render-model.py`.
4. Run `./render-model-assets.sh` when the rendered web assets are needed.
5. Run `./check-model.sh` before committing.

Generated projections are never edited by hand.
