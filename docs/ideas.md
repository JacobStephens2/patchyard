# Ideas

Hand-written inbox for factory ideas - the plan bin, applied to the
factory's own design. Free-form and cheap by intent: date it, write it,
move on. No required fields, no schema, no CI validation.

Two rules only:

1. **Nothing here carries authority.** An idea becomes real by
   graduating into `docs/decision-log.md` (accepted / deferred /
   rejected), and from there into SPEC/PLAN/model. Nothing cites
   ideas.md.
2. **Mark graduations instead of deleting.** When an idea is ruled on,
   annotate it (`→ A56`, `→ rejected, see R22`, `→ SPEC § Dashboard`) so
   the trail from scribble to ruling stays walkable.

---

## 2026-07-17

- Provider allowlist needs a ruling before any non-Anthropic byte leaves
  the worker boundary: which model providers may receive fieldbook source +
  request content (Anthropic and OpenAI de facto today; xAI qualified
  mechanically 2026-07-17 - Grok Build headless verified; Fireworks-hosted
  GLM under consideration). One accepted ruling naming the list, plus the
  one-provider-per-worker-boot egress rule.
