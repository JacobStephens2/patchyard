# Harness smoke test - exact-instruction floor check across candidate pairs

*2026-07-17. Operator: the orchestration agent, on the orchestration VM.
Subject: the worker-seat candidate pairs from `docs/ideas.md` plus
same-day additions from Jacob. This is a pre-gauntlet floor probe, not
admission: it checks one behavior (exact-instruction adherence in a
headless agentic run), k=3 per pair. Admission remains the full fixture
gauntlet + shadow mode (D6).*

**Final Muse attribution update:** the later harness-free tool-call
control passed 80/80 across Meta's Responses and Chat Completions APIs.
That result supersedes this report's interim "model-level" conclusion;
see [the raw tool probe](2026-07-17-muse-spark-raw-tool-probe.md) and
the final Muse addendum below.
An external research council (three cross-family models) reviewed the
published brief the same day: consensus favors distillation-induced
identity confusion activated by Claude-Code-lineage prompt style -
OpenCode's `system.ts` has no `muse`/`meta` branch, so the model
receives the default Claude-heritage prompt - with concrete mitigations
proposed (non-Claude-style custom agent prompt; the
`experimental.chat.system.transform` hook). See
[the council response](2026-07-17-muse-spark-council-response.md).
Attribution formally remains open until the envelope bisection runs.
**Bisection run same evening** - see
[`2026-07-17-muse-spark-envelope-bisection.md`](2026-07-17-muse-spark-envelope-bisection.md):
the substitution is stochastic and dose-dependent (100% under the full
harness prompt, ~40-50% under minimal agentic envelopes, 0% in the
fully synthetic probe), needs no "claude" token (the captured envelope
contains none), generalizes beyond claude (`cursor-smoke.txt`
observed), and no tested mitigation eliminates it. Final attribution:
model-side context-conditional identity-token substitution.

## Method

One probe, identical for every pair, three runs each in a fresh
directory:

> Create a file named muse-smoke.txt in the current directory containing
> exactly the word: factory

Pass = `muse-smoke.txt` exists with content `factory`, three for three
(pass^k, k=3, per the acceptance discipline). The probe began as a
mechanical exec-mode check and became a behavioral test when the first
candidate failed it in an unexpected way (below).

Harness versions (pin these when re-running - harness churn is real):
Claude Code 2.1.211 · codex-cli 0.144.4 · Grok Build 0.2.101 ·
OpenCode 1.18.3 · pi 0.73.1 (`@mariozechner/pi-coding-agent`) ·
Gemini CLI 0.51.0 · OpenHands 1.11.0 (V1 SDK) · Cline CLI 3.0.44. Model access: native
APIs for Anthropic/OpenAI/xAI/Google; Fireworks AI serverless for GLM
5.2 (`accounts/fireworks/models/glm-5p2`), MiniMax-M3 (`.../minimax-m3`,
unlisted on the account but served), Kimi K2.6 (`.../kimi-k2p6`).

## Results

| Harness × Model | Result | Invocation notes |
| :-- | :-- | :-- |
| Claude Code × Fable 5 | PASS 3/3 | `claude -p --allowedTools Write` |
| Codex × GPT-5.6 Sol (xhigh) | PASS 3/3 | `codex exec --skip-git-repo-check -s workspace-write -c model_reasoning_effort="xhigh"` |
| Grok Build × Grok 4.5 (high) | PASS 3/3 | `grok -p --permission-mode bypassPermissions --reasoning-effort high` |
| OpenCode × Muse Spark 1.1 (xhigh) | **FAIL 0/4** | see finding below |
| OpenCode × GLM 5.2 | PASS 3/3 | custom provider block, `--auto` |
| OpenCode × MiniMax-M3 | PASS 3/3 | same provider block |
| Pi × GLM 5.2 | PASS 3/3 | `pi --provider fireworks --model <id> --api-key ... -p` |
| Gemini CLI × Gemini 3.5 Flash | PASS 3/3 | needs `GEMINI_CLI_TRUST_WORKSPACE=true` + `--approval-mode yolo` |
| Gemini CLI × Gemini 3.1 Pro (preview) | PASS 3/3 | same; no CLI flag to pin thinking level yet Vertex surface re-verified 2026-07-18: PASS 3/3, 16-17 s/run (`example-model-bench`, location `global`, dedicated SA, AI Studio key unset during runs) |
| OpenHands × Kimi K2.6 | PASS 3/3 | no CLI executable in 1.11.0 - driven via a ~15-line SDK script (`uv run --python 3.12 --with openhands-ai`), LiteLLM `fireworks_ai/` prefix |
| Claude Code × DeepSeek V4 Flash (DeepInfra, direct) | PASS 3/3 | 2026-07-18: 6-8 s/run via DeepInfra's own Anthropic surface (`https://api.deepinfra.com/anthropic`) - no DeepClaude proxy needed for floor purposes; complements the DeepClaude-routed record |
| Claude Code × DeepSeek V4 Pro (DeepInfra, direct) | PASS 3/3 | 2026-07-18: 4-5 s/run, same direct wiring - fastest full agentic runs on the bench |
| Claude Code × GLM 5.2 (Fireworks, direct) | PASS 3/3 | 2026-07-18: 6-10 s/run. Resolves the 07-17 "not runnable" verdict: the failure was a double-pathed base URL (`.../inference/v1` + CLI-appended `/v1/...`); the correct Anthropic base is `https://api.fireworks.ai/inference`. No gateway or FireConnect needed for headless probes |
| Kimi Code CLI × Kimi K2.6 (Fireworks) | PASS 3/3 | 2026-07-18: 7-14 s/run; second provider block in `~/.kimi-code/config.toml` (type "openai", Fireworks base URL, `accounts/fireworks/models/kimi-k2p6`). Native-family harness, US hosting - no provenance exception required, unlike the K3 pairing |
| OpenCode × Qwen3.7 Max (Novita) | PASS 3/3 | 2026-07-18: 11-14 s/run after one >300 s stall (Novita-side, same class as Blackbox's). Not servable on Novita's Anthropic surface (per-model gating), so Claude Code preference falls to OpenCode |
| Claude Code × MiMo-V2.5-Pro (Novita) | PASS 3/3 | late 07-17, Jacob's preferred-harness pick: 8-10 s/run, clean Write-tool usage. **First direct Claude Code × non-Anthropic pairing** - `CLAUDE_CONFIG_DIR` isolation + `ANTHROPIC_BASE_URL=https://api.novita.ai/anthropic` + `--model xiaomimimo/mimo-v2.5-pro` just works; Novita's Anthropic-compatible endpoint satisfies the CLI's model validation where Fireworks' did not (the "needs a proxy" verdict was per-endpoint, not absolute). OpenCode fallback not needed |
| Kimi Code CLI × Kimi K3 (OpenRouter → Moonshot AI) | PASS 3/3 | late 07-17: 15-18 s/run, clean Write-tool usage. Kimi Code 0.27.0 (`@moonshot-ai/kimi-code`, bin `kimi`): `-p` non-interactive mode auto-approves by default (rejects `--yolo`/`--auto` as redundant); custom provider via `~/.kimi-code/config.toml` (key must live in the file, 0600 - the CLI reads no env credentials; models.dev catalog import fails on OpenRouter's wire type). **Provenance exception, ruled by Jacob**: K3 is served only by Moonshot (money to China) pending the expected open-weights release + US hosting in ~weeks; tested now via OpenRouter under that interim exception. Intelligence #3 (57), image input - prime triage/verify candidate once a US host exists |
| OpenCode × Nemotron 3 Ultra 550B-A55B (Blackbox AI) | PASS 3/3 | second speed-tab candidate (late 07-17): 12-16 s/run when responsive, correct Write-tool usage - but **intermittent provider stalls** (two runs hung >300 s with zero output before a clean streak). Raw generation from this droplet: 60-87 tok/s direct on Blackbox, 135-189 tok/s via OpenRouter→DeepInfra - nowhere near the AA speed-tab billing for this pairing, and an order of magnitude below Cerebras' gpt-oss numbers. Reasoning-mode toggle not exercised (provider default). `blackboxai/nvidia/nemotron-3-ultra`, custom provider block |
| Cline CLI × gpt-oss-120b (Fireworks) | PASS 3/3 | speed probe (added later same day): **4s / 4s / 6s wall-clock per full agentic run** - an order of magnitude faster than every other pair. `cline -P fireworks -k ... -m ... --auto-approve true`. Caveat: Cline's `--thinking high` injects fields the fireworks provider schema rejects, so runs used provider-default effort; Fireworks itself accepts `reasoning_effort: "high"` for gpt-oss (verified), so the "(high)" pin awaits a Cline schema fix or a proxy |

Not scored: OpenCode's first run per new provider timed out at 300s
(one-time provider-package download); retries were immediate and clean.

## Finding: Muse Spark × OpenCode rewrites "muse-*" filenames

The pair created `claude-smoke.txt` (correct content, wrong name) four
out of four times, plus a fifth run that half-corrected after first
writing the wrong name. Isolation matrix:

| Probe | Outcome |
| :-- | :-- |
| `muse-smoke.txt` via OpenCode | wrote `claude-smoke.txt` (4/4) |
| `muse-note.txt` via OpenCode | wrote `claude-note.txt` first, half-corrected |
| `zebra-note.txt` via OpenCode | correct |
| `test-smoke.txt` via OpenCode | correct |
| neutral cwd (no "claude" in path) | still wrong - path is not the trigger |
| `muse-smoke.txt` question via direct Meta API, no harness | correct |

At this stage the defect appeared to need both the OpenCode context and
a `muse-*` name. The initial working hypothesis was that OpenCode's
Claude-Code-derived prompt lineage triggered an identity substitution.
The later raw tool-call control and captured OpenCode envelope supersede
that hypothesis as an attribution: the precise later-loop change point
remains unknown. The runs also showed weaker tool discipline (raw
`echo` redirects instead of the write tool, gratuitous verification
commands).

Factory relevance: wrong-filename behavior is wrong-target-file
behavior. `factory-verify`'s caps check would reject the patch
deterministically - the gates are the containment - but the pair starts
any shadow-mode audition with a strike, and the trigger (a token no one
would have guessed) is the argument for odd-corner fixtures over
benchmark trust. Note both public indices rank this pair top-11; neither
measures this floor.

## Not runnable, and why

- **Claude Code × GLM 5.2**: Fireworks does expose an
  Anthropic-compatible `/inference/v1/messages` (verified live), but the
  claude CLI rejects non-Claude model names (`--model` and
  `ANTHROPIC_MODEL` both refused). Needs a name-translating proxy
  (claude-code-router / LiteLLM) if this pairing is ever wanted.
- **Cursor CLI × Composer 2.5**: no Cursor credentials on this VM. Add a
  key to the example vault + `env.tpl` to unblock.
- **MiniMax Code × MiniMax-M3**: desktop app (macOS/Windows) only, and
  no MiniMax platform key here. M3 itself is covered via
  OpenCode × Fireworks. Its headline "Agent Teams" feature is the
  pattern R21 standing-rejects.
- **OpenSymphony**: an orchestrator (Linear issues → OpenHands/Codex
  backends), not a harness - i.e. a control plane, which R11 rules the
  factory builds rather than buys.

## Implications for seat assignment

1. The floor check discriminates pairs, not models or harnesses alone:
   GLM and MiniMax pass in the same OpenCode harness where Muse Spark
   fails, and Muse Spark passes with no harness at all. Evals must bind
   to (model × harness × effort), matching the run-provenance schema.
2. Image-input coverage (the multimodal-in requirement): Fable 5, Sol,
   Grok 4.5, Kimi K2.6, MiniMax-M3, and both Geminis take images; GLM
   5.2 is text-only and cannot fill a screenshot-reading seat despite
   passing.
3. Every qualified pair ran headlessly with env-var auth and no TTY -
   the worker-box contract holds across nine pairs, so seat rotation is
   an operational choice, not a porting project.

Tooling from this exercise persists on the VM (`opencode`, `pi`,
`gemini`, `uv` under `~/.local/bin`; provider wiring recorded in the
orchestration agent's memory). Re-running the matrix after a harness
upgrade is ~30 minutes.

## Addendum (same day, superseded): failure reproduced across two harnesses

Follow-up prompted by two research docs Jacob supplied (harness
recommendations for Muse Spark; an OpenHands × Muse Spark guide). Four
new experiments, all on the same probe:

| Experiment | Result |
| :-- | :-- |
| OpenCode via Responses-capable wiring (`@ai-sdk/openai` instead of `@ai-sdk/openai-compatible`) | still `claude-smoke.txt`; its completion message also renamed the working *directory* from `muse-test` to `claude-test` in prose |
| OpenCode + explicit identity rule in `AGENTS.md` ("You are Muse Spark 1.1, a model built by Meta... use names exactly as written") | still `claude-smoke.txt`, 2/2 - this one prompt did not correct it; no broader prompt-independence claim |
| **OpenHands (V1 SDK) × Muse Spark** - an entirely different harness, prompts, tool stack, and transport | **still `claude-smoke.txt`, 3/3** |
| Registry check: the research doc's claim that OpenCode ships a built-in Meta provider | false as of OpenCode 1.18.3 / current models.dev - no `meta` provider exists; custom wiring remains the only route |

These runs established cross-harness reproduction, not a defect in the
model weights or every agentic context. Full tally: 0/13 correct across
the tested configurations (two OpenCode wirings, identity-primed
OpenCode, and OpenHands), while the same harnesses ran GLM 5.2,
MiniMax-M3, and Kimi K2.6 correctly. That evidence moved the working
hypothesis away from an OpenCode-only bug, but it did not capture the
raw later-turn argument before adapter parsing and execution. The final
Muse addendum below supersedes the stronger attribution originally
drawn here.

Bench consequence: Muse Spark 1.1's implementation-seat candidacy is
impaired under both tested harnesses until a configuration passes this
probe. Its raw-API judgment-seat candidacy is untouched.

Operational notes from the follow-up: Meta's API also serves native
`/v1/responses` and Anthropic-compatible `/v1/messages`; the OpenHands
guide's `openhands --headless` CLI does not exist in the current PyPI
package (1.11.0 is the V1 SDK, no executable - the SDK-script pattern
in this report is the working route), and its LiteLLM `meta/` provider
prefix postdates the litellm version OpenHands pins (use
`openai/muse-spark-1.1` + `base_url`). Muse Spark runs also showed
high latency variance through both wirings (occasional >5-minute
runs on a trivial task).

## Final Muse addendum (same day): raw tool calls pass 80/80

The missing harness-free control used one synthetic `write_file` tool,
four filenames, 10 fresh trials per filename, and both Meta tool-capable
API shapes. `/v1/responses` passed 40/40 and
`/v1/chat/completions` passed 40/40. `muse-smoke.txt` was preserved in
20/20 raw returned argument strings. Every request returned HTTP 200,
the exact model identifier, one `write_file` call, and content
`factory`. No returned tool call was executed.

OpenCode's captured initial build request also preserved
`muse-smoke.txt` and contained no `Claude` or `Anthropic` strings. A
direct replay of that richer envelope made `bash` the first call; the
protocol stopped without executing it, before the later write turn.
The proven defect boundary is therefore narrower than either earlier
hypothesis: minimal raw Meta tool calls are correct, initial OpenCode
request construction is correct, and completed OpenCode/OpenHands loops
are wrong. The exact later turn where the argument changes remains
unisolated.

Updated attribution: **harness-context or later-loop defect**, without
yet choosing among model behavior induced by the richer prompt,
adapter serialization/parsing, or executor mutation. This result rules
out an unconditional Muse/Meta filename substitution and overturns the
interim model-level claim. It does not exonerate the model in the richer
multi-turn context or prove a harness adapter bug. Full method, raw
credential-free evidence, specimens, and limitations are in
[`2026-07-17-muse-spark-raw-tool-probe.md`](2026-07-17-muse-spark-raw-tool-probe.md).

Factory decision: Muse remains out of an implementation seat under the
current OpenCode and OpenHands configurations. The raw 80/80 pass is a
necessary control, not admission; the actual model × harness × adapter
version still has to pass this floor, the fixture gauntlet, and shadow
mode. Raw-text success supports the narrower judgment seat, while raw
tool-call success restores Muse as a candidate for future harness work.

## Addendum 2: gpt-oss-120b provider head-to-head - Cerebras vs Fireworks

Same day, after Jacob enabled Cerebras billing
(`CEREBRAS_API_KEY` now in env.tpl). Identical requests (400
completion tokens, `reasoning_effort: high`), interleaved C-F-C-F so a
transient load spike on either side cannot masquerade as an
architecture difference:

| Provider | TTFB | Total (400 tok) | Generation rate | Variance |
| :-- | :-- | :-- | :-- | :-- |
| Cerebras | 34-54 ms | 0.42-0.44 s | **~1,000-1,100 tok/s** | ±5% |
| Fireworks | 43-67 ms | 1.75-3.46 s | 118-234 tok/s | ~3× swing |

Raw generation: **Cerebras ~5-8× faster, with far tighter variance.**
First-token latency is a wash.

Agentic leg: Cline CLI × gpt-oss-120b **via Cerebras** (native `-P
cerebras` provider) passes the probe 3/3 at **4.0 / 4.6 / 4.6 s** -
statistically identical to the Fireworks 4-6 s runs. Conclusion: at
small task sizes the agentic loop is harness-bound (session startup,
tool round-trips, per-turn TTFB), so provider throughput is invisible;
it becomes decisive on long-generation work (big diffs, long
rationales, high-effort reasoning) and for keeping many-turn latency
predictable. For a factory speed seat, Cerebras is the better host for
this model on the evidence - same price class, same wire format, 5-8×
the headroom - with the note that Cerebras' catalog also lists
`zai-glm-4.7` and `gemma-4-31b` as additional US-hosted options.
