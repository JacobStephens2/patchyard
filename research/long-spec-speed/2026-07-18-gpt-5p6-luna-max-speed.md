# GPT-5.6 Luna max speed addendum - OpenAI x Codex

*2026-07-18. Operator: the orchestration agent on the orchestration VM. This
extends the six-pair `docx/specs.md` speed probe. It is one harness run plus a
repeated direct-API diagnostic, not factory admission or pass^k evidence.*

## Verdict

**Keep GPT-5.6 Luna max fourth in the speed preference order.** Codex produced
the only fully conforming document among the first four pairs in approximately
115 seconds, behind Nemotron's 38.165-second run but ahead of GLM's 175.731
seconds. The direct control delivered visible text at 166.2 common tokens per
second once it began, but max reasoning delayed the first visible answer for
81.348 seconds.

The supplied 186 t/s figure described decode speed, not time to a usable
artifact. Artificial Analysis' live Luna result had already moved to roughly
210-221 t/s during this test, with roughly 95-114 seconds to first answer at max
reasoning. Both its live result and this local result show why decode-only speed
does not predict Patchyard factory wall time.

## Configuration

- Model: `gpt-5.6-luna`
- Provider: OpenAI first-party API
- Reasoning: `max`
- Direct surface: Responses API, streamed
- Harness: Codex CLI 0.144.5, `codex exec --json --ephemeral`
- Fixture: [`fixtures/bench/docx-spec-speed/request.md`](../../fixtures/bench/docx-spec-speed/request.md)
- Common direct cap: 6,000 output tokens, three runs
- Supplemental throughput cap: 30,000 output tokens, one run
- Harness cap: 240 seconds

OpenAI's Chat Completions endpoint rejected `reasoning_effort=max` for this
model and listed `none`, `low`, `medium`, `high`, and `xhigh` as supported. The
Responses API accepted `reasoning={"effort":"max"}`. The benchmark runner now
uses Responses for Luna so the API control matches the named Codex effort.

## Direct API results

At the same 6,000-token cap used for the other candidates, all three Luna runs
ended `incomplete` after spending exactly 6,000 output tokens on reasoning and
producing no visible answer.

| Measure | Result |
| :-- | --: |
| Runs with visible content | **0/3** |
| Median wall | **43.389 s** |
| Individual walls | 43.389 s, 42.155 s, 43.496 s |
| API output tokens | 6,000/run |
| Reasoning tokens | 6,000/run |

The 30,000-token supplemental run separated reasoning latency from streaming
speed and completed normally:

| Measure | Result |
| :-- | --: |
| Wall | **99.468 s** |
| First visible answer | **81.348 s** |
| Visible content span | 17.717 s |
| Visible common tokens | 2,945 |
| Locally observed visible output rate | **166.2 t/s** |
| API output / reasoning tokens | 14,813 / 11,868 |
| Content | 1,957 words; all headings in order; over the 1,800-word limit |

The 166.2 t/s result is the comparable local decode-rate observation. It does
not include the 81.3-second wait before content. The common 6,000-token result
is the more important operational warning: Luna max needs a materially larger
output budget than the other candidates merely to begin the answer.

## Codex long-spec result

Codex ran in a fresh directory with a minimal environment, workspace-write
sandbox, no persistent session, the explicit Luna model, and explicit max
reasoning. The model wrote a 2,207-word first draft, recognized the length
failure, revised it, removed placeholder-like ellipses, and verified the final
artifact itself.

| Measure | Result |
| :-- | --: |
| End-to-end wall | **approximately 115 s** |
| Process result | Exit 0 |
| Created files | Exactly `docx/specs.md` |
| Final length | **1,536 words - pass** |
| Required headings | **8/8, exact order - pass** |
| Placeholder scan | **Pass** |
| Codex input / cached input tokens | 343,680 / 311,840 |
| Codex output / reasoning output tokens | 17,639 / 6,042 |

The wall is rounded because this first add-on run was not wrapped by an
external timer; it is derived from the fresh job directory's creation and last
activity timestamps. That uncertainty is only a few seconds and cannot change
the ordering against the adjacent 38.165- and 175.731-second runs.

## Decision

Keep Luna max as an intelligence-oriented Codex candidate, not the speed seat.
It is substantially more reliable on this specification than the three faster
pairs, but max reasoning turns fast decode into a roughly two-minute job. For a
speed-specific Luna retest, compare `high` or `xhigh` against max rather than
raising the output budget silently; for production max jobs, provision more
than 6,000 output tokens and budget around 80-110 seconds before visible text.

References:

- [OpenAI: GPT-5.6 Luna model](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [Artificial Analysis: GPT-5.6 Luna](https://artificialanalysis.ai/models/gpt-5-6-luna)
