# Envelope bisection: the Muse Spark substitution is stochastic, dose-dependent, and needs no "claude" token

*2026-07-17, evening. Operator: the orchestration agent. Mandate from
Jacob: retry Muse Spark 1.1 informed by the council response
(`2026-07-17-muse-spark-council-response.md`), the harness-compatibility
research (`2026-07-17-Which harnesses work with Muse Spark 1.1_.md`),
and GPT 5.6-Sol's raw probe + captured envelope - test multiple
harnesses, none, and a custom one. This runs the bisection both prior
documents called for.*

## Headline findings

1. **The trigger is request content, not harness runtime.** The
   byte-exact captured OpenCode envelope, replayed through a plain
   stdlib HTTP client, reproduces the substitution (`bash: printf
   "factory" > claude-smoke.txt`, complete with the bash-over-write and
   gratuitous-hexdump signature).
2. **No "claude" token is involved.** The captured request contains
   zero occurrences of "claude" anywhere - 9.5 KB system prompt, 20 KB
   of tool schemas, user message. The model introduces the token
   itself. The council's literal-token version of the prompt-lineage
   hypothesis is dead; only the stylistic/structural version survives.
3. **The behavior is a biased coin, not a switch - and the bias scales
   with envelope richness.** Full OpenCode system prompt + only the
   `write` tool: **CLAUDE 10/10**. Minimal one-line prompt + neutral
   tool description + unquoted user message: CLAUDE 6 / MUSE 8 /
   CURSOR 1 over 15 trials (~40-50% substitution). GPT's fully
   synthetic single-shot probe: 0/80 substitution. Same model, same
   API, same question - three different substitution rates.
4. **`cursor-smoke.txt` happened.** One minimal-envelope trial
   substituted a *third* agent identity. The filename slot is being
   treated as a generic coding-agent-identity token and sampled from a
   distribution - claude is the mode, not the mechanism.
5. **Temperature 0 does not fix it** (2/3 substitution with minimal
   prompt + OpenCode write tool at `temperature: 0`), so GPT's clean
   80/80 is a property of its exact envelope, not of determinism.
6. **No single ingredient is necessary.** Stripping tools to one (B2),
   replacing the system prompt with one line (B3/B7), neutralizing the
   Claude-style tool description (B10), and removing OpenCode's
   quote-wrapping of the user message (B11) each shift the rate;
   none reaches reliable zero. Early small-n runs that looked decisive
   (a 3/3 MUSE after unquoting) regressed on more reps - every prior
   small-n conclusion in this saga, ours and others', was sitting on
   coin-flip noise.
7. **Multi-turn execution adds partial self-correction, not safety.** A
   custom ~40-line agentic loop (GPT-style minimal schema, real
   execution, up to 4 turns): first write was `claude-smoke.txt` in
   3/3 runs; 2/3 later noticed and also wrote `muse-smoke.txt`,
   leaving both files. A worker that writes the wrong file and
   sometimes fixes it is not a worker.

## Variant table

Replay client: python stdlib → `POST /v1/responses`, `stream: false`,
cache key dropped, otherwise the captured request. "Exploratory" =
first call was `pwd && ls -la` (single-shot probe cannot see the
model's second turn; not counted).

| Variant | Change from exact envelope | Trials | Result |
| :-- | :-- | --: | :-- |
| B1 exact | none | 3 + in-file replay | CLAUDE 2, exploratory 2 |
| B2 write-tool-only | 10 tools → 1 | 12 | **CLAUDE 12/12** |
| B3 minimal prompt | 9.5 KB system → 1 line | 2 | CLAUDE 1, exploratory 1 |
| B4 no system | system removed | 2 | exploratory 2 |
| B7 = B2+B3 | minimal prompt + write only | 3 | CLAUDE 2, MUSE 1 |
| B8 = B7 + temp 0 | + `temperature: 0` | 3 | CLAUDE 2, MUSE 1 |
| B10 = B7 + neutral tool desc | Claude-style write description → 1 neutral line (same params) | 3 | CLAUDE 2, MUSE 1 |
| B11 = B7 + unquoted user | OpenCode's literal quote-wrap removed | 5 | MUSE 3, CLAUDE 2 |
| B12 = B7+B10+B11 | all three fixes | 15 | MUSE 8, CLAUDE 6, **CURSOR 1** |
| B13 exact + unquoted | full envelope, quotes removed | 4 | CLAUDE 1, exploratory 3 |

## Harness leg

| Test | Result |
| :-- | :-- |
| Custom minimal loop (none/custom) | first-write substitution 3/3; partial self-correction 2/3 (both files left) |
| Cline × Muse | not runnable: `Unknown or disabled provider "meta"` in Cline 3.0.44, despite Meta naming Cline a partner - presumably a newer Cline |
| Claude Code × Muse via Meta redirection | not runnable as documented: Meta's Anthropic-compatible `/v1/messages` does **not** alias Claude model names (`claude-sonnet-4-5` → "Model not found"), and the claude CLI rejects `muse-spark-1.1`; needs a name-translating proxy |
| OpenCode + council's minimal-prompt mitigation | covered by B3/B7 above: reduces the rate, does not eliminate it |

## Revised attribution (final for today)

Model-side, context-conditional **identity-token substitution**: under
envelopes that resemble agentic-harness context, Muse Spark 1.1 treats
an identity-like name prefix in file paths as paraphrasable and samples
a coding-agent identity for it, with probability rising from ~0% (fully
synthetic single-shot) through ~40-50% (minimal agentic envelope) to
~100% (full harness prompt). Consistent with the council's
distillation-artifact mechanism in its stylistic form; independent of
literal "claude" text; not specific to OpenCode, OpenHands, or any
harness runtime; not curable by temperature, prompt slimming, tool-
description neutralization, or unquoting - each only moves the bias.

## Consequences

- **Implement seat: closed for Muse Spark 1.1**, now on stronger
  evidence than before - there is no harness configuration, including a
  purpose-built minimal one, that reaches reliable fidelity. Revisit on
  a Meta model update, and retest with the B2 variant at n=10 (two
  minutes, ~deterministic signal in the rich regime).
- **Report upstream.** We hold a clean reproduction package Meta could
  act on: a captured envelope with zero "claude" tokens that substitutes
  10/12 at worst, rate curves across ablations, and a `cursor` variant
  proving identity-slot generalization. Nothing public matches this
  (per the council's search).
- **For the factory's own probes: rates, not runs.** The floor gauntlet
  should score stochastic behaviors with n≥10 where a defect is
  suspected - pass^3 caught this one only because the rich-envelope
  rate is near 100%; a 40% defect would slip through 3 runs one time in
  five.
