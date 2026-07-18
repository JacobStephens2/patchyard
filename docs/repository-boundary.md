# Factory repository boundary

The factory repository should become self-contained for build and runtime
policy without absorbing the orchestration repository's research archive.
Do not bulk-copy `projects/software-factory/`.

## Migrated into this repository

### Decision log

`docs/decision-log.md` is now the canonical ruling log. The model contains
structured references such as `A39` and `A52`; model validation rejects a
ruling identifier absent from this local log. The synthesis directory keeps a
pointer for historical links.

### Factory constitution

`AGENTS.md` is now canonical here through the human-reviewed policy process
required by that file (uppercase name matches the cross-tool instruction-file
convention so harnesses auto-load it). Its hard rules are available before the
`/factory` skill work because the constitution is prompt input, not a cutover
artifact.

### Acceptance fixtures

`fixtures/alphabetize/` contains the minimum synthetic request text, expected
classification, postconditions and scrubbed images needed by the smoke test.
Bench-only prompts live under `fixtures/bench/`. The canonical model package
lives under `model/` (JSON, schema, identity, projectors, tests). Raw email
attachments and proposal directories remain outside this repo; the spec allows
only sanitized fixtures in Git, while live artifacts belong in the private
artifact store.

## Keep in the orchestration repository

- `prompt.md` and the independent Fable, GPT, Grok and research-council
  responses: immutable provenance for how the design was formed.
- `comparison.md`, `model-assessments.md` and the research notes: comparative
  analysis, not factory runtime input.
- `synthesized-solution.md`: historical synthesis superseded for construction
  by `SPEC.md` v2.2 and the later rulings. Do not create a second authoritative
  copy.
- `review.html`: a human projection deployed by the orchestration/reporting
  repository. It should fetch the served canonical JSON and generated assets,
  not become part of the factory runtime repository.
- Raw screenshots and request artifacts: keep out of Git unless explicitly
  sanitized into acceptance fixtures.

## Migration rule

Every migration must leave one canonical home and pointers elsewhere. A copy
with two editable homes is worse than the current cross-repository reference.
