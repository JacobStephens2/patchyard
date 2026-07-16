# Factory repository boundary

The factory repository should become self-contained for build and runtime
policy without absorbing the orchestration repository's research archive.
Do not bulk-copy `projects/software-factory/`.

## Migrate into this repository

### Decision log

Move `projects/software-factory/synthesis/decision-log.md` to
`docs/decision-log.md` in a coordinated, reviewed change. The model contains
structured references such as `A39` and `A52`; their definitions should
eventually resolve inside the same repository. After migration, leave a
pointer in the synthesis directory and extend model validation to reject a
ruling identifier absent from the local log.

### Factory constitution

Move `projects/software-factory/synthesis/agents.md` to this repository as
`agents.md` through the human-reviewed policy process required by that file.
This must happen no later than the `/factory` skill work: the constitution's
hard rules are prompt input, not a cutover after the skill is built. The
current build plan places the move in session 11; move that one item forward
to session 6 when the plan is next revised.

### Acceptance fixtures

Create a sanitized ALPHABETIZE fixture under `fixtures/` when replay work
begins. Bring only the minimum request text, expected classification,
postconditions and scrubbed images needed by the acceptance test. Do not copy
raw email attachments or the proposal directories wholesale; the spec allows
only sanitized fixtures in Git, while live artifacts belong in the private
artifact store.

## Keep in the orchestration repository

- `prompt.md` and the independent Fable, GPT, Grok and research-council
  responses: immutable provenance for how the design was formed.
- `comparison.md`, `model-assessments.md` and the research notes: comparative
  analysis, not factory runtime input.
- `synthesized-solution.md`: historical synthesis superseded for construction
  by `SPEC.md` v2.1 and the later rulings. Do not create a second authoritative
  copy.
- `review.html`: a human projection deployed by the orchestration/reporting
  repository. It should fetch the served canonical JSON and generated assets,
  not become part of the factory runtime repository.
- Raw screenshots and request artifacts: keep out of Git unless explicitly
  sanitized into acceptance fixtures.

## Migration rule

Every migration must leave one canonical home and pointers elsewhere. A copy
with two editable homes is worse than the current cross-repository reference.
