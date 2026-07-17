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
I'm interested in these model - harness pairs for coding agent work. I want each pair to use a different harness and different model family to avoid rubber stamping and get advantages of various harnesses. I want each model to be accept text and image inputs - so that much multimodality for these. It is fine if they can only output text. All the money for the usage of these harnesses and models should go to American companies. It is fine if the model was created in China, so long as it can be run entirely on American infrastructure, such as GLM-5.2, created by Z.ai, though can be run on the American Fireworks AI.

For all the seats below, use the provenance and modality guidance above. And for each spot, use a different model family and if choosing a harness, a different harness.

Thinking about the Artificial Analysis - George Cameron & Micah Hill-Smith, "The Cost of Intelligence" talk at AI Engineer World's Fair 2026, (https://www.youtube.com/live/4sX_He5c4sI?si=1PBBniU0_vYktiHr&t=30236), if there is a ceiling to the quality of the task output relative to the amount of intelligence in, then choose the cheapest model that will get the job done (i.e. alphabetize these employees' names, or how many customer payments were made last month) - the output of these tasks is more simple / quantitative to verify. However, if there is no ceiling on the quality of output relative to intelligence in - often tasks with a less clearly verifiable metric of better, or quality is more qualitative, then we should choose the max intelligence, even if more expensive. This might be tasks like, make Fieldbook more intuitive to navigate, or write a job description for a new salesperson.

The Artificial Analysis charts renders client-side, so they probably need to be scraped with a headless browser.

#### Factory implement worker agent seat

Harness model pairing makes more impact on this seat given that tool use and loop quality impact the work done here more.

##### Preference order when there is no ceiling on output quality

Use the Artificial Analysis Coding Agent Index (https://artificialanalysis.ai/agents/coding-agents?coding-agents-performance-chart=index#coding-agents-index) to stay up to date. Use that coding agent index primarily.

Harness, Model, Index, as of July 17, 2026
1. Codex, GPT-5.6 Sol (max), 80
2. Claude Code, Fable 5 (max, with fallback), 77
3. Grok Build, Grok 4.5 (high), 76
4. OpenCode, Muse Spark 1.1 (xhigh), 69

→ smoke-tested 2026-07-17, see `../reviews/2026-07-17-harness-smoke-test.md`:
pairs 1-3 pass k=3; pair 4 **fails 0/4** (rewrites `muse-*` filenames to
`claude-*`; model alone is clean - pair-level defect). Same-day additions
tested there too: OpenCode/Pi × GLM-5.2, OpenCode × MiniMax-M3, Gemini
CLI × 3.5-flash and 3.1-pro, OpenHands × Kimi-K2.6 all pass; Cursor ×
Composer 2.5 blocked on missing credentials.

##### Preference order when there is a ceiling on output quality

Use the coding agent cost per task chart to decide here (https://artificialanalysis.ai/agents/coding-agents#coding-agents-cost-chart-tabs).

Harness, Model, Cost per task, as of July 17, 2026
1. OpenCode, Muse Spark 1.1 (xhigh), $1.43
2. Grok Build, Grok 4.5 (high), $2.59
3. Codex, GPT-5.6 Sol (max), $7.08
4. Claude Code, Fable 5 (max, with fallback), $11.70

#### Triage and cross-family verification agent seats

##### No ceiling
When no ceiling exists, reference the Artificial Analysis Intelligence Index (https://artificialanalysis.ai/#intelligence-tabs). There's no loop on this seat, so harness is not as much of a concern here.

Below I'm skipping Kimi K3 (index 57) because as of July 17 2026 there is no way to use it that keeps money in the United States. Moonshot AI's API is the only availability at this time, which sends money to China, which we avoid for geopolitical reasons.

Model, Index, as of July 17, 2026
1. Claude Fable 5 (with fallback), 60
2. GPT-5.6 Sol (max), 59
3. Grok 4.5 (high), 54
4. Muse Spark 1.1 (xhigh), 51

##### Ceiling
When a ceiling exists, reference the Cost per Intelligence Index Task (https://artificialanalysis.ai/#cost-tabs)

Model, cost per task, as of July 17, 2026
1. Muse Spark 1.1 (xhigh), $0.26
2. Grok 4.5 (high), $0.31
3. GPT-5.6 Sol (max), $1.04
4. Claude Fable 5 (with fallback), $2.75
