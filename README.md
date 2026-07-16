# factory

*(GitHub: `JacobStephens2/patchyard`; local checkout on the
orchestration VM lives at `/srv/orchestration/patchyard/` to avoid
colliding with the orchestration repo's `factory/queue/` until the queue
migrates here at build.)*

Patchyard's software factory: small, self-describing staff requests in, evidenced
pull requests out. One human gate - the PR - held by the engineering
department + the company owner. The production deploy path is never touched.

- **Spec:** [SPEC.md](SPEC.md) - the phase-1 build spec (status: awaiting
  review by Jacob + adversarial critique by GPT 5.6-Sol, per ruling A41).
- **Design record:** the synthesis, 73-ruling decision log, and comparison of
  the five founding proposals live in the orchestration repo at
  `projects/software-factory/synthesis/`; the interactive review is at
  https://report.example.com/software-factory-review.html
- **Constitution:** `agents.md` (migrates here from the orchestration repo at
  build start; until then the orchestration copy is canonical). Its hard
  rules ride every factory agent prompt.
- **Canonical model:** `factory-model.json` (same migration note).

Build status: **approved in scope, not yet started** - console ruling
2026-07-16, "don't build it yet." Nothing in this repo executes anything
until Jacob's go.
