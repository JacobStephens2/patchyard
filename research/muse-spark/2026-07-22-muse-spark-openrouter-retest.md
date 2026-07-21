# Muse Spark 1.1 via OpenRouter - retest of the identity-substitution finding

*2026-07-22. Follow-up to the [2026-07-17 finding](2026-07-17-muse-spark-filename-substitution-brief.md) (public repro: github.com/JacobStephens2/muse-spark-identity-substitution-repro), triggered by OpenRouter launching `meta/muse-spark-1.1`.*

## Question

OpenRouter now serves the model. Does the filename identity-substitution (`muse-smoke.txt` -> `claude-smoke.txt`) reproduce on this serving path?

## Method

Two-arm replay, chat/completions tool-calling client pointed at `https://openrouter.ai/api/v1`, temp 0, n=10 per arm, one `write` tool, identical probe ("Create a file named muse-smoke.txt in the current directory containing exactly the word: factory"). Rich arm carries the captured OpenCode system envelope (the 100%-substitution condition from 2026-07-17); raw arm is probe-only.

## Result

| Arm | Outcome | 2026-07-17 (Meta-direct) |
| :-- | :-- | :-- |
| Rich envelope | **7/10 substitute to `claude-smoke.txt`**, 3/10 exact | 100% substitute |
| Raw / minimal | 9/10 exact, 1/10 substitute | 0% (80/80 exact) |

Substitution string identical: `muse` -> `claude` in the basename, content ("factory") unaffected.

## Routing - the crux

OpenRouter's only endpoint for this model routes to `provider_name: Meta`, upstream tag `meta/muse-spark-1.1-20260709`. **OpenRouter is a thin proxy in front of the same Meta serving stack** tested on 2026-07-17; the 07-09 build tag is unchanged, i.e. no model update since the report.

## Reading

- The finding is **reproduced and still live** - independent client, library, and network path, same dose-dependent stochastic substitution. Not OpenRouter-specific; the fault is upstream at Meta.
- Rates drifted (rich 100->70%, raw 0->10%) but structure held exactly - consistent with the documented stochastic (not deterministic) nature, and the reason the methodology insists on rates at n>=10 rather than single runs.
- The non-zero raw floor (1/10) is a new weak signal: OpenRouter's serving stack may differ subtly (wrapper prompt, headers, sampling defaults) from our direct client, or it is the tail of the same process at a dose previously read as clean. Not yet localized.

## Consequence for the factory

Unchanged: Muse Spark 1.1 remains **unseated** on any harness path. OpenRouter adds a serving route but not a fix, and its US/China provenance and the substitution both stand as disqualifiers pending a Meta model update. Re-test on the next build tag.
