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

### Model and Harness Choice
I'm interested in these model - harness pairs for coding agent work. I want each pair to use a different harness and different model family to avoid rubber stamping and get advantages of various harnesses. I want each model to be accept text and image inputs - so that much multimodality for these. It is fine if they can only output text. All the money for the usage of these harnesses and models should go to American companies. It is fine if the model was created in China, so long as it can be run entirely on American infrastructure, such as GLM-5.2, created by Z.ai, though can be run on the American Fireworks.

For all the seats below, use the provenance and modality guidance above. And for each spot, use a different model family and if choosing a harness, a different harness.

Thinking about the Artificial Analysis - George Cameron & Micah Hill-Smith, "The Cost of Intelligence" talk at AI Engineer World's Fair 2026, (https://www.youtube.com/live/4sX_He5c4sI?si=1PBBniU0_vYktiHr&t=30236), if there is a ceiling to the quality of the task output relative to the amount of intelligence in, then choose the cheapest model that will get the job done at reliability parity (i.e. alphabetize these employees' names, or how many customer payments were made last month) - the output of these tasks is more simple / quantitative to verify. However, if there is no ceiling on the quality of output relative to intelligence in - often tasks with a less clearly verifiable metric of better, or quality is more qualitative, then we should choose the max intelligence, even if more expensive. This might be tasks like, make Fieldbook more intuitive to navigate, or write a job description for a new salesperson.

The Artificial Analysis charts renders client-side, so they probably need to be scraped with a headless browser.

#### Triage and cross-family verification agent seats

##### No ceiling
When no ceiling exists, reference the Artificial Analysis Intelligence Index (https://artificialanalysis.ai/#intelligence-tabs). There's no loop on this seat, so harness is not as much of a concern here.

Below I'm skipping Kimi K3 (index 57) because as of July 17 2026 there is no way to use it that keeps money in the United States. Moonshot AI's API is the only availability at this time, which sends money to China, which we avoid for geopolitical reasons.

Model, harness if needed, model provider, Index, as of July 17, 2026
1. Claude Fable 5 (with fallback), Claude Code, Anthropic, 60
2. GPT-5.6 Sol (max), Codex, OpenAI, 59
3. Kimi K3, Kimi Code CLI, OpenRouter, 57
4. Grok 4.5 (high), Grok Build, SpaceXAI, 54

##### Ceiling
When a ceiling exists, reference the Cost per Intelligence Index Task (https://artificialanalysis.ai/#cost-tabs), and prefer the lowest price American AI Gateway / API provider for the model.

###### Text input only

Model, harness if needed, model provider, cost per task, as of July 17, 2026
1. DeepSeek V4 Flash (max), DeepClaude and Claude Code, DeepInfra (FP4), $0.02
2. MiMo-V2.5-Pro, Claude Code > OpenCode, Novita, $0.03
3. gpt-oss-120b (high), OpenCode, DeepInfra, $0.06
4. MiniMax-M3, OpenCode, Novita, $0.12

###### Text and image input

Model, harness if needed, model provider, cost per task, as of July 17, 2026
1. MiniMax-M3, OpenCode, Novita, $0.12
2. GPT-5.6 Luna (max), Codex, OpenAI, $0.21
3. Muse Spark 1.1 (xhigh), only reliable without harness, Meta, $0.26
  a. If a fallback is needed, put Claude 4.5 Haiku in this slot 3, and then use the provisional slot 5
4. Claude 4.5 Haiku, Claude Code, Amazon, $0.27
5. Gemini 3.1 Pro Preview, Gemini CLI, Google (Vertex preferable over AI Studio), $0.29 // present for if Muse Spark fallback is needed


#### Factory implement worker agent seat

Harness model pairing makes more impact on this seat given that tool use and loop quality impact the work done here more.

##### Preference order when there is no ceiling on output quality

Use the Artificial Analysis Coding Agent Index (https://artificialanalysis.ai/agents/coding-agents?coding-agents-performance-chart=index#coding-agents-index) to stay up to date. Use that coding agent index primarily.

Model, harness, provider, Index, as of July 17, 2026
1. GPT-5.6 Sol (max), Codex, OpenAI, 61
2. Fable 5 (max, with fallback), Claude Code, Anthropic, 59
3. Grok 4.5 (high), Grok Build, SpaceXAI, 58
4. Kimi K3, Kimi Code CLI, OpenRouter, 57

Note on Kimi K3, I'm accepting it initially before fully available on American infrastructure, because it is set to be released as open weights around July 27 2026, and then American infrastructure will probably serve it soon after that.

→ smoke-tested 2026-07-17, see `../research/floors/2026-07-17-harness-smoke-test.md`:
pairs 1-3 pass k=3; pair 4 **fails 0/13 in the tested OpenCode and
OpenHands loops** (rewrites `muse-*` names to `claude-*` through both
wirings and past an explicit identity rule) - but the harness-free
control passes **80/80** raw tool calls on both Meta endpoints
(`../research/muse-spark/2026-07-17-muse-spark-raw-tool-probe.md`), localized by envelope
bisection (`../research/muse-spark/2026-07-17-muse-spark-envelope-bisection.md`):
stochastic model-side identity-token substitution, dose-dependent on
agentic-envelope richness (100% rich / ~50% minimal / 0% synthetic),
no "claude" token needed, also emits `cursor-*`; no mitigation reaches
zero - implement seat closed pending a Meta model update. Same-day additions tested
there too: OpenCode/Pi × GLM-5.2, OpenCode × MiniMax-M3, Gemini
CLI × 3.5-flash and 3.1-pro, OpenHands × Kimi-K2.6 all pass; Cursor ×
Composer 2.5 blocked on missing credentials.

##### Preference order when there is a ceiling on output quality

Use the coding agent cost per task chart to decide here (https://artificialanalysis.ai/agents/coding-agents#coding-agents-cost-chart-tabs).

###### text input only
Model, harness, provider, cost per task, as of July 17, 2026
1. DeepSeek V4 Pro (high), Claude Code (probably with DeepClaude), —, $0.27
2. GPT 5.6 Luna (max), Codex, OpenAI, $1.57
3. Gemini 3.1 Pro Preview, Gemini CLI, Google (Vertex preferable over AI Studio), $2.00
4. Grok 4.5 (high), Grok Build, —, $2.59

###### text and image input
Model, harness, provider, cost per task, as of July 17, 2026
1. GPT 5.6 Luna (max), Codex, OpenAI, $1.57
2. Gemini 3.1 Pro Preview, Gemini CLI, Google (Vertex preferable over AI Studio), $2.00
3. Grok 4.5 (high), Grok Build, —, $2.59
4. Kimi K3, Kimi Code CLI, OpenRouter, $3.18

#### Preference order if we find a need for speed

Reference the Artificial Analysis Output Speed table: https://artificialanalysis.ai/#speed-tabs. Headline output speed excludes reasoning delay and harness behavior, so this preference order uses our end-to-end long-spec harness wall time. The local visible output rate is retained to show the provider's raw delivery speed.

Model, harness, API provider, locally observed visible output tokens per second, long-spec harness wall time, as of July 18, 2026

1. gpt-oss-120b (high), OpenCode, Cerebras, 1,889.8, 12.651 seconds
2. Command+ (high requested), OpenCode, Cohere, 209.7 with thinking disabled, 22.514 seconds
3. Nemotron 3 Ultra, OpenCode, Blackbox AI, 161.7, 38.165 seconds
4. GPT-5.6 Luna (max), Codex, OpenAI, 166.2 after an 81.348-second reasoning delay, approximately 115 seconds
5. GLM-5.2 (default), Claude Code, Fireworks, 104.8, 63.5-71.1 seconds
  → harness switched from OpenCode 2026-07-18 per the effort-matched A/B
  (`../research/long-spec-speed/2026-07-18-docx-spec-speed-comparison.md`
  addendum 2): Claude Code 3/4 full-pass at 63-71 s vs OpenCode 1/3 at
  ~169 s at identical default effort - the OpenCode figure (175.731 s at
  max requested) was a harness effect, not a model or effort property
6. Gemini 3.5 Flash (high), OpenCode, Google AI Studio, 229.3, timed out after 240 seconds
7. Qwen3.7 Max, OpenCode, Novita, 57.6, timed out after 240 seconds

## Cursor x Composer 2.5

I'm not using Cursor CLI or Composer 2.5 Fast because they don't appear to have API pricing available without a $20 / month Cursor pro subscription, and I don't want any LLM dependencies that require subscriptions.
