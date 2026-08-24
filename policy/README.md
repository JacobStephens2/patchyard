# Daemon-consumed, human-ruled files (sessions 8-9)

The machine-read half of governance, distinct from `docs/` (human-read): stage prompts (triage, implement, adversarial review - A73), `rubric.md` (lane classification), skill playbooks, and the versioned `routing` config (A74: task class → selection rule → seated pair; per A77 it also carries reviewer count per task class and the arbiter seat - Grok 4.5 × Grok Build per A77-as-amended). The proposer's prompt (A93) consumes typed outcome facts + bounded quoted spans only and frames transcripts as untrusted data; its policy PRs get cross-family review. Review-stage prompts carry the A87 isolation contract: fresh worktree at the reviewed SHA, no sibling-review visibility until the submission barrier lifts, no shared scratch. The constitution's hard rules (`../AGENTS.md`) ride every prompt from here. Everything markdown or plain config; changes via reviewed PR like all policy.

Session 8 adds the first executable policy surface: `triage.md` has an exact
Read/Grep/Glob tool allowlist, `rubric.md` contains the parsed deterministic
lane rules, and `task-spec.schema.json` documents the Rust-validated output
contract. The wrapper captures the no-write triage agent's JSON, validates it,
and only then writes `TASK.json`; request text remains labeled untrusted data.

## `a101-census.sha256`

The A101 readiness trust root's census of the files it binds, in
`sha256sum --check` format. `tools/check-a101-readiness-root.py` **derives**
which files are governed - every `tools/*.py`, every `infra/**/*.py`, plus the
shell entry points and checker fixtures it names explicitly - and this file
records what each one must hash to. Adding a checker or an Ansible test needs
no edit to the trust root: the new file is governed the moment it exists, and
fails closed until it is censused.

The trust chain still terminates in CI. `.github/workflows/infrastructure.yml`
`sha256sum --check`s **both** halves before it runs anything - the rules
(`check-a101-readiness-root.py`) and the data those rules assert (this file) -
so moving the ledger out of the checker did not move it out of the anchor.

Regenerate after a declared change with
`python3 -I tools/check-a101-readiness-root.py --write-census`. It exits 2 and
writes nothing if the tree fails for a reason the census does not own - a
missing bound file, a stdlib shadow, an ungated checker, a broken wrapper
contract - so a rewrite can never launder a failing tree into a pass. On a
rewrite it names every row it adds, drops, or re-pins, and prints the two
workflow rows a human then pastes in; it never writes CI config itself.
