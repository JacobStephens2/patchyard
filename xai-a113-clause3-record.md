# xAI Factory team key — A113 clause 3 record (issue #358)

Recorded at credential creation for the qualification Result. The key
itself is deliberately not recorded anywhere.

- Team: Patchyard Factory (id `24472de3-304e-46ae-824b-2f99ffb3aed8`), dedicated to the Factory
- Postpaid spending limit: **NOT YET IN EFFECT.** A desired soft limit of
  1000 USD cents was POSTed to the management API on 2026-08-31, but the
  response and re-read show every limit still 0 (`softSl`, `effectiveSl`,
  `effectiveHardSl`, `hardSlAuto` all `"0"`); the likely cause is that the
  provider-side hard limit (`hardSlAuto`) is 0 for this new team, clamping
  any desired soft limit. The A113 money boundary does not exist until a
  nonzero `effectiveSl` is read back. The A-5 spend proof is blocked on this,
  and how the limit is obtained is ruled on in issue #364.
- Prepaid balance reading: $0.00 on 2026-08-31 (console showed $0.00; the
  wizard's "not $0.00" warning was a string-comparison artifact of typing
  the figure without the dollar sign)
- API key `factory-arbiter-seat` created: 2026-08-31 10:36 AM
- Key landed at `/etc/patchyard/xai-seat.key` (root:root 0600) and the
  mint smoke test ran the same day: pass: factory-manager:factory:600 84

Still open (issue #358 steps 4-6): the six A-5 qualification proofs, the
`credential_qualified` gate flip PR, and banking the first live envelope.

This file stays at the repo root until the requirement-2 Result cites it,
at which point it moves to `docs/` — see `docs/xai-qualification-design.md`
§ "Artifacts this design implies", which also designs the six fixtures the
facts above feed and names the four rulings they wait on (#362-#365).
