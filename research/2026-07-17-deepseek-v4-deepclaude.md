# DeepSeek V4 x DeepClaude x DeepInfra factory experiment

*2026-07-17. Operator: the orchestration agent, on the orchestration VM.
This is a factory implementation-worker evaluation, not an interactive
developer setup.*

## Outcome

Both text-only treatments pass the exact-instruction floor at `k=3`:

| Treatment | Floor | Mean wall time | Provider cost, three runs | Image input | Standing |
| :-- | :-- | --: | --: | :-- | :-- |
| Claude Code 2.1.212 x patched DeepClaude `70518b6` x DeepSeek V4 Flash (max) via DeepInfra | **PASS 3/3** | 8.704 s | `$0.000684828` | **No** | Advance to the text-only alphabetize fixture gauntlet |
| Claude Code 2.1.212 x patched DeepClaude `70518b6` x DeepSeek V4 Pro (max) via DeepInfra | **PASS 3/3** | 5.108 s | `$0.008947600` | **No** | Advance to the text-only alphabetize fixture gauntlet |

Each successful run made a two-turn `Write` loop, exited cleanly, created only
`muse-smoke.txt`, and left exact bytes `factory`. The floor is necessary but
not sufficient: neither pair is admitted to a factory seat until it passes the
fixture gauntlet and shadow mode.

Pro was faster in this small probe and cost about 13 times more. `k=3` is not
enough to infer a general latency distribution or capability difference.

Both models reject image content, so neither can fill a screenshot-reading
seat. They remain candidates only where the factory assembles a complete text
evidence packet.

The private Muse reproduction repository was also published before the
experiment. GitHub reports it as private, and remote `main` resolves to
`09261cc7be6715d632b29492ab03b65d41c02495`.

## Treatment and method

The scored prompt was identical for every run:

```text
Create a file named muse-smoke.txt in the current directory containing exactly the word: factory
```

Flash and Pro ran independently at `k=3`. Every run had:

- a fresh working directory;
- a fresh `CLAUDE_CONFIG_DIR` outside that directory;
- only the `Write` tool exposed and pre-approved;
- `--effort max` plus DeepClaude's max-effort environment setting;
- `--safe-mode` and no session persistence;
- single-result JSON output; and
- a 300-second timeout.

The Claude Code arguments were:

```text
-p --effort max --tools Write --allowedTools Write
--permission-mode dontAsk --safe-mode --output-format json
--no-session-persistence
```

Pass required exactly one top-level artifact, the exact requested filename,
and exact 7-byte content with no newline. Final prose did not count.

The first attempted Flash transport call occurred while the account balance
was `$0.00` and returned HTTP 402 before inference. The user then added `$5.00`;
the account reported `suspended: false`, and the six scored runs began from
new directories. The rejected call consumed zero tokens and is not part of
the score.

## Provenance and source review

- DeepClaude repository: `https://github.com/aattaran/deepclaude.git`
- Reviewed upstream commit:
  `70518b6cdcf3cc488e62e817b86da4b550dd7dfa`
- Upstream subject: `fix: strip thinking blocks on backend switch - close DeepSeek/Anthropic 400s`
- License: MIT
- Claude Code: `2.1.212 (Claude Code)`
- Reviewed Linux launcher: all 278 upstream lines of `deepclaude.sh`
- Also reviewed: all 443 lines of `proxy/model-proxy.js` and all 58 lines of
  `proxy/start-proxy.js`
- Installation: none. The reviewed clone stayed under `/tmp` and was invoked
  explicitly with `bash`.

Upstream DeepClaude contains fixed first-party DeepSeek, OpenRouter,
Fireworks, and Anthropic cases. It has neither a DeepInfra case nor a generic
custom-backend flag. Its ordinary non-remote path sets environment variables
and `exec`s Claude Code; the Node proxy is used only for remote control and
live switching.

The evaluated source is therefore the actual pinned launcher with a minimal
DeepInfra backend patch:

- `https://api.deepinfra.com/anthropic` as backend `di`;
- `DEEPINFRA_API_KEY` as its credential source;
- `DEEPCLAUDE_MODEL` as the exact catalog selector; and
- `ANTHROPIC_MODEL` in addition to DeepClaude's alias/subagent variables.

The exact patch is
[`2026-07-17-deepclaude-deepinfra.patch`](2026-07-17-deepclaude-deepinfra.patch).
Its SHA-256 is
`d343338e96bdfe2261833dc292cf3b74a4c0bad87ab8de326886562d9f5db91e`;
the resulting working-tree diff SHA-256 is
`b597b095110edd1b2f3625e6e18f0890b064ba1614e20414cc9a09bfeda2c6aa`.
The patched launcher SHA-256 is
`28768bfc8b3bb7e399bb13ffea8d49e14845b894a604cb6f5858873746981dad`.
`bash -n`, `git diff --check`, and reverse application of the archived patch
against the evaluated clone all passed.

## Routing proof

An offline dry run replaced `claude` with `/usr/bin/env` and selected Flash
through the patched launcher. The non-secret effective environment was:

```text
ANTHROPIC_BASE_URL=https://api.deepinfra.com/anthropic
ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-ai/DeepSeek-V4-Flash
ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-ai/DeepSeek-V4-Flash
ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-ai/DeepSeek-V4-Flash
ANTHROPIC_MODEL=deepseek-ai/DeepSeek-V4-Flash
CLAUDE_CODE_EFFORT_LEVEL=max
CLAUDE_CODE_SUBAGENT_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

Every real run printed DeepClaude's endpoint/model banner. Claude Code's
`modelUsage` then reported the selected full DeepInfra ID for the successful
tool loop. The scored treatment route was therefore:

```text
Claude Code 2.1.212 -> patched DeepClaude launcher ->
DeepInfra Anthropic-compatible endpoint -> selected DeepSeek V4 model
```

There was no local translation proxy in the scored treatments. This record
does not relabel a direct `ANTHROPIC_BASE_URL` shell function as DeepClaude.

DeepInfra's official integration page documents the same
[`/anthropic` Claude Code endpoint](https://docs.deepinfra.com/integrations/anthropic).
The authenticated live catalog returned both exact IDs with a
1,048,576-token context. At test time, standard prices per million tokens
were `$0.09` input / `$0.18` output / `$0.018` cache read for Flash and
`$1.30` / `$2.60` / `$0.10` for Pro.

## Max-reasoning proof

Max remained on the request wire across the tool loop for both models.

After the scored runs, a separate transparent capture adapter logged only
request structure and prompt hashes, never credentials or prompt text, while
forwarding request bodies unchanged to DeepInfra. These controls are not
scored floor runs and are kept distinct from the direct DeepClaude treatment.

For both Flash and Pro, the request before `Write` and the request after its
`tool_result` contained:

```json
{
  "thinking": {"type": "adaptive", "display": "omitted"},
  "output_config": {"effort": "max"},
  "max_tokens": 32000
}
```

The exact model ID remained unchanged, and each model's system-prompt hash was
identical before and after the tool call. DeepInfra accepted both requests and
completed both controls. This proves that Claude Code's max treatment reached
DeepInfra and persisted across tool calls. DeepInfra does not return a named
server-side reasoning mode, so no stronger internal-service claim is made.

Credential-free request summaries and results are in
[`2026-07-17-deepseek-v4-deepclaude-max-wire.json`](2026-07-17-deepseek-v4-deepclaude-max-wire.json).

## Scored results

| Model | Run | Wall | TTFT | Total input | Cached input | Output | Claude estimate | Artifact |
| :-- | --: | --: | --: | --: | --: | --: | --: | :-- |
| Flash | 1 | 5.763 s | 2.211 s | 3,328 | 1,280 | 153 | `$0.021105` | exact pass |
| Flash | 2 | 8.076 s | 5.353 s | 3,332 | 1,280 | 150 | `$0.021050` | exact pass |
| Flash | 3 | 12.274 s | 3.135 s | 3,328 | 1,536 | 146 | `$0.021058` | exact pass |
| Pro | 1 | 4.185 s | 1.595 s | 3,326 | 1,280 | 162 | `$0.021320` | exact pass |
| Pro | 2 | 4.588 s | 1.545 s | 3,326 | 1,536 | 152 | `$0.021198` | exact pass |
| Pro | 3 | 6.552 s | 3.250 s | 3,326 | 1,536 | 147 | `$0.021073` | exact pass |

Raw, complete Claude result objects plus artifact listings, work directories,
wall times, and verdicts are in
[`2026-07-17-deepseek-v4-deepclaude-raw.jsonl`](2026-07-17-deepseek-v4-deepclaude-raw.jsonl).

## Cost reconciliation

Claude Code reported `$0.126804` across the six runs, but that is a client-side
estimate using fallback pricing for model IDs it does not price correctly. It
is not the provider charge.

DeepInfra's token ledger exactly reconciles to the CLI model totals after
splitting cached input:

| Model | Uncached input | Cached input | Output | Calculated provider cost |
| :-- | --: | --: | --: | --: |
| Flash | 5,892 | 4,096 | 449 | `$0.000684828` |
| Pro | 5,626 | 4,352 | 461 | `$0.008947600` |
| **Total** | **11,518** | **8,448** | **910** | **`$0.009632428`** |

DeepInfra rounded the account's recent usage to `$0.01`. Provider billing,
not Claude Code's estimate, is the cost result for this adapter.

## Image-input check

A separate live modality probe sent the same synthetic 1x1 PNG as an
Anthropic image block to each exact model ID. Both returned HTTP 405 before a
model response:

```text
deepseek-ai/DeepSeek-V4-Flash: Model ... does not accept image input
deepseek-ai/DeepSeek-V4-Pro:   Model ... does not accept image input
```

This matches DeepInfra's Text Generation classification and the absence of a
vision capability in the live catalog. The factory classification is
definitively text-only, not unknown.

## Decision

- Advance both pairs to the alphabetize fixture gauntlet as text-only
  candidates.
- Keep them excluded from screenshot-reading seats.
- Prefer Flash on cost when both pass the same bounded work: it was about 13
  times cheaper on provider billing in this probe.
- Retain Pro as the capability/control comparison; its faster `k=3` result is
  promising but not yet a stable rate.
- Do not admit either pair directly to a seat. Fixture-gauntlet `pass^k` and
  shadow-mode evidence remain required.
