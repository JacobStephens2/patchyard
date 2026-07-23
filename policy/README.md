# Daemon-consumed, human-ruled files (sessions 8-9)

The machine-read half of governance, distinct from `docs/` (human-read): stage prompts (triage, implement, adversarial review - A73), `rubric.md` (lane classification), skill playbooks, and the versioned `routing` config (A74: task class → selection rule → seated pair; per A77 it also carries reviewer count per task class and the arbiter seat - Grok 4.5 × Grok Build per A77-as-amended). The proposer's prompt (A93) consumes typed outcome facts + bounded quoted spans only and frames transcripts as untrusted data; its policy PRs get cross-family review. Review-stage prompts carry the A87 isolation contract: fresh worktree at the reviewed SHA, no sibling-review visibility until the submission barrier lifts, no shared scratch. The constitution's hard rules (`../AGENTS.md`) ride every prompt from here. Everything markdown or plain config; changes via reviewed PR like all policy.

Session 8 adds the first executable policy surface: `triage.md` has an exact
Read/Grep/Glob tool allowlist, `rubric.md` contains the parsed deterministic
lane rules, and `task-spec.schema.json` documents the Rust-validated output
contract. The wrapper captures the no-write triage agent's JSON, validates it,
and only then writes `TASK.json`; request text remains labeled untrusted data.
