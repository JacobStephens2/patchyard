# Ideas

Hand-written inbox for factory ideas - the plan bin, applied to the factory's own design. Free-form and cheap by intent: date it, write it, move on. No required fields, no schema, no CI validation.

Two rules only:

1. **Nothing here carries authority.** An idea becomes real by graduating into `docs/decision-log.md` (accepted / deferred / rejected), and from there into SPEC/PLAN/model/bench. Nothing cites ideas.md.
2. **Annotate graduations, then sweep.** When an idea is ruled on, annotate it (`→ A58`, `→ rejected, see R22`) so the trail is walkable while neighboring ideas are still live. Once an entry's content fully lives in its authoritative home, delete it in a sweep commit - git history and the target file are the trail from then on. *(Amended 2026-07-20 from "mark instead of deleting"; the 2026-07-17 entries - provider allowlist, model-and-harness choice with all seat tables, Cursor/Composer - were swept the same day, graduated as A58-A61 and R22 with operative rosters in `bench.md` § Seat preference orders.)*

---

## 2026-07-20

Task-time model selection for phase 2: use the Artificial Analysis LLM API Providers Leaderboard snapshots (`../research/artificial-analysis/providers-leaderboard/` - 523 provider × model endpoint rows: intelligence, cost/task, tok/s, first-chunk latency, function-calling/JSON-mode flags, API IDs) as (a) a discovery source for new models and providers worth probing, and (b) the data behind deterministic per-task selection rules - e.g., "for this task, use the cheapest endpoint with Intelligence Index >= 40" - with the candidate set always restricted to (model, harness, provider) pairs already tested in our environment (bench floor + gauntlet) and on the A61 allowlist. This is A58's ceiling branch made computable at run time: a rule picks the seat, not a model's judgment (A4-consistent), and the chosen snapshot date should land in run provenance.

## 2026-07-21

Improvement-proposer agent in phase 1 - giving the model's learning edge an actor. The `ledger → rubric` learning edge (A48) is currently human-only; add a scheduled agent seat on the control-plane VM (where the socket is - A56 makes the data-locality decision for us) that reads the ledger + transcripts and opens PRs against the factory repo. R19-compliant by construction: it proposes diffs, never merges (A1 gate), never revises policy in place. Sketch for a v0 worth ruling on: authority surface = `policy/` + this file only (not SPEC, not the decision log, not `crates/`); every PR must cite ledger evidence - run IDs and rates, n>=10 before claiming a pattern (the Muse lesson); hard cap of one open proposer PR; authored by the factory bot identity (A62); seat resolved through A74 routing as its own task class (judgment work - A58's no-ceiling order applies); cold-start guard - below the evidence threshold it may only append here (ideas.md entries are authority-free by rule 1, so thin-data speculation costs no review bandwidth). Cost if ruled into phase 1: one added session after evidence lifecycle (session 13), pushing cutover/acceptance to 15/16 - ~17 sessions total, reported plainly per the no-buffer ground rule.
