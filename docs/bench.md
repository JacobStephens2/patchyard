# Bench status

*Living document - the at-a-glance answer to "what's the current status
of each (model × harness) pair?" Edited in place as statuses change; the
evidence stays in `../research/`'s dated records, which this file only
cites. Floor probe = the muse-smoke exact-instruction check
(`../research/floors/2026-07-17-harness-smoke-test.md`), k=3 unless noted.
Seats are design-time assignments; nothing runs in production until
phase 1 builds.*

*Last updated: 2026-07-20 (`Preferred Harness` projection and A58-A61 seat
orders retained; Tencent Hy3 x Pi added with observed cost; pair-level speed
evidence projected into the Pairs table).*

*AA Intelligence (v4.1) is the [Artificial Analysis Intelligence Index](https://artificialanalysis.ai/methodology/intelligence-benchmarking) score for the corresponding tracked model/effort variant, using AA's canonical tracked variant where this bench's `default` has no separate AA row. Scores are rounded as displayed and checked 2026-07-20; they are model-level, not provider-level.*

## Pairs

`Preferred Harness` is `Yes` only when the row uses the current
model-specific harness choice. `No` includes alternate or retired treatments
and models whose only reliable preference is harness-free.

`Visible t/s` is raw provider delivery after visible text begins, so it omits
reasoning delay and harness work. `Long-spec wall` is end-to-end for the exact
model x harness row. Blank cells mean that treatment was not measured.

This table is generated from [`bench.json`](bench.json) (schema:
[`bench.schema.json`](bench.schema.json)) - edit the JSON, then run
`python3 tools/check-bench.py --write`. Do not hand-edit the table rows.

<!-- BEGIN GENERATED pairs table: edit docs/bench.json, then run `python3 tools/check-bench.py --write` -->
| Model | Effort | Harness | Preferred Harness | Host | Floor | Img-in | Provenance | Current standing | Visible t/s | Long-spec wall | AA Intelligence (v4.1) |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| Claude Fable 5 | max | Claude Code | Yes | Anthropic | ✅ 3/3 | ✅ | US | Implement bench #2; **builder incumbent** |  |  | 60 |
| Claude Haiku 4.5 | high | Claude Code | Yes | Amazon Bedrock | ✅ 3/3, 3.6 s and $0.0357/run | ✅ content; strict format miss | US | **Qualified floor configuration:** `claude -p --allowedTools Write`; exact 7-byte file every run. A follow-up environment-allowlisted child-process run also passed with only 15-minute STS AWS credentials present; Firecracker/Podman containment and egress are not built. Image labels were all correct, but the requested bare JSON was fenced. A `--bare --tools Write` variant failed 0/3 by claiming success without calling the tool; pin the canonical form ([record](../research/claude-code/2026-07-17-claude-code-bedrock-haiku.md)) |  |  | 30 |
| Command A+ | high (requested) | OpenCode | Yes | Cohere | ✅ 3/3, ~7 s wall/run; 1.3-1.7 s event span | ❌ OpenCode image adapter | Canada-created; Cohere first-party API (processing region not pinned) | **Use OpenCode, not Terminus-2, for the first Patchyard test.** Native `write` produced the exact 7-byte artifact every run; direct raw streaming reproduced the speed claim at 209.7 tok/s. Advance only to the text gauntlet: OpenCode reports zero reasoning telemetry despite the high request, and both local and server-attached image paths failed while a direct Cohere image control passed. Terminus-2 remains the reference rerun for suspected harness-specific failures ([record](../research/command-a-plus/2026-07-18-command-a-plus-opencode.md)) | 209.7 (thinking-disabled control) | 22.514 s | 23 |
| DeepSeek V4 Flash | max (requested) | Claude Code (direct) | Yes | DeepInfra | ✅ 3/3, 6-8 s/run | ❌ text-only | US infra (CN-created, allowed) | **Preferred Flash wiring:** DeepInfra's Anthropic-compatible surface works directly; DeepClaude is unnecessary. Advance to the text-only alphabetize fixture gauntlet; provider mode still needs fixture validation ([floor record](../research/floors/2026-07-17-harness-smoke-test.md)) |  |  | 40 |
| DeepSeek V4 Flash | max (requested) | Claude Code + DeepClaude | No | DeepInfra | ✅ 3/3, 5.8-12.3 s wall/run | ❌ text-only | US infra (CN-created, allowed) | Earlier patched-launcher treatment. Request-level max evidence captured, but retain only as historical comparison now that the direct route passes ([record](../research/deepseek-v4/2026-07-17-deepseek-v4-deepclaude.md)) |  |  | 40 |
| DeepSeek V4 Pro | max (requested) | Claude Code (direct) | Yes | DeepInfra | ✅ 3/3, 4-5 s/run | ❌ text-only | US infra (CN-created, allowed) | **Preferred Pro wiring and fastest full agentic floor runs on the bench:** direct DeepInfra Anthropic-compatible surface, no DeepClaude. Advance to the text-only alphabetize fixture gauntlet ([floor record](../research/floors/2026-07-17-harness-smoke-test.md)) |  |  | 44 |
| DeepSeek V4 Pro | max (requested) | Claude Code + DeepClaude | No | DeepInfra | ✅ 3/3, 4.2-6.6 s wall/run | ❌ text-only | US infra (CN-created, allowed) | Earlier patched-launcher treatment. Request-level max evidence captured, but retain only as historical comparison now that the direct route passes ([record](../research/deepseek-v4/2026-07-17-deepseek-v4-deepclaude.md)) |  |  | 44 |
| Gemini 3.1 Pro (preview) | default (not pinnable via CLI) | Gemini CLI | Yes | Google - **Vertex verified** (`example-model-bench`, location `global`; AI Studio also 3/3) | ✅ 3/3 both surfaces | ✅ | US | Judgment-seat candidate. Vertex is the preferred surface per ideas.md - dedicated SA/project provisioned 2026-07-17, ops reference in [`vertex-access.md`](vertex-access.md) |  |  | 46 |
| Gemini 3.5 Flash | default | Gemini CLI | Yes | Google | ✅ 3/3 | ✅ | US | Fast/cheap generalist; needs `GEMINI_CLI_TRUST_WORKSPACE=true` headless |  |  | 50 |
| Gemini 3.5 Flash | high | OpenCode | No | Google AI Studio | - | ? | US | Long-spec speed-only treatment; it timed out while still looping, so this does not replace the Gemini CLI floor. | 229.3 | 240.069 s timeout | 50 |
| GLM 5.2 | default | Claude Code | Yes | Fireworks | ✅ 3/3, 6-10 s/run | ❌ text-only | US infra (CN-created, allowed) | Direct pairing works (2026-07-18): `ANTHROPIC_BASE_URL=https://api.fireworks.ai/inference` - base **without** `/v1`; the CLI appends its own paths, and the earlier "not runnable" was a double-pathed base URL, not an endpoint limitation. FireConnect (Fireworks' alias-mapping tool) is the maintained route for full sessions with subagent slots; manual env suffices for headless probes **Preferred GLM 5.2 harness** (2026-07-18). Long-spec A/B (effort-matched, default): Claude Code 3/4 full pass at 63-71 s vs OpenCode 1/3 at ~169 s - harness effect confirmed ([record](../research/long-spec-speed/2026-07-18-docx-spec-speed-comparison.md)) | 104.8 (max control) | 63.5-71.1 s | 51 |
| GLM 5.2 | default | OpenCode | No | Fireworks | ✅ 3/3 | ❌ text-only | US infra (CN-created, allowed) | Floor passes, but **no longer the preferred GLM harness**: the effort-matched long-spec A/B showed ~169 s completions and 2/3 cap-outs vs Claude Code's 63-71 s - OpenCode's envelope triggers long first-turn generation on GLM. Kept as the eval-grid alternate | 104.8 (max control) | ~169 s default; 175.731 s max | 51 |
| GLM 5.2 | default (`--thinking` available) | Pi | No | Fireworks | ✅ 3/3 | ❌ | US infra | Floor passes; Pi exposes native thinking levels. Eval-grid alternate - Claude Code is the preferred GLM harness |  |  | 51 |
| GPT-5.6 Sol | xhigh | Codex | Yes | OpenAI | ✅ 3/3 | ✅ | US | Implement bench #1 (no-ceiling order); **adversarial reviewer incumbent** (A41) |  |  | 58 |
| GPT-5.6 Luna | max | Codex | Yes | OpenAI | - | ✅ | US | Long-spec speed-only treatment. The final document passed, but max reasoning delayed first visible text by 81.348 s ([record](../research/long-spec-speed/2026-07-18-gpt-5p6-luna-max-speed.md)). | 166.2 after 81.348 s delay | ~115 s | 51 |
| gpt-oss-120b | default (pin blocked by Cline schema) | Cline | No | **Cerebras** (preferred) / Fireworks | ✅ 3/3, 4-6 s/run | ❌ | US | **Speed-seat lead** - Cerebras ~1,000-1,100 tok/s ±5% vs Fireworks 118-234 ([head-to-head](../research/floors/2026-07-17-harness-smoke-test.md)) | Cerebras 1,000-1,100; Fireworks 118-234 |  | 24 |
| gpt-oss-120b | high | Harmony Agent + Cerebras transport | No | Cerebras | ❌ **5/10 strict**, 6.103 s median; target bytes exact 10/10 | ❌ text-only | US infra; US-created, open weights | Native Harmony works and the long spec passed in 18.412 s, but default instructions created `.pytest_cache` or `.git` in half the floor runs. Keep as a diagnostic reference, not a factory runner. Upstream also hardcodes local vLLM, so Cerebras needs the recorded transport adapter ([record](../research/gpt-oss-120b/2026-07-18-gpt-oss-cerebras-harmonyagent.md)) | 2,584.9 provider-reported | 18.412 s | 24 |
| gpt-oss-120b | high | OpenCode | Yes | Cerebras | - | ❌ text-only | US infra; US-created, open weights | Long-spec speed-only treatment; fastest wall, but its 2,372-word document missed the requested range. DeepInfra remains the floor-qualified preferred host treatment. | 1,889.8 | 12.651 s | 24 |
| gpt-oss-120b | high | OpenCode | Yes | DeepInfra | ✅ 3/3, 12.9-16.9 s wall/run | ❌ text-only | US infra; US-created, open weights | **Preferred viable harness** from the ordered search: native `write` tool and exact 7-byte artifact in every run. Harmony Agent's earlier DeepInfra treatment missed exact acceptance, Codex + generic adapter was tool-protocol-incompatible, and mini-swe-agent scored 4/10 exact; Cline/Roo were not tested after OpenCode passed ([record](../research/gpt-oss-120b/2026-07-17-gpt-oss-120b-deepinfra-harness-selection.md)) |  |  | 24 |
| Grok 4.5 | high | Grok Build | Yes | xAI | ✅ 3/3 | ✅ | US | Implement bench #3; tiebreak-verifier candidate |  |  | 54 |
| Hy3 (Tencent) | high | Pi | Yes | Novita | ✅ 3/3, 7.137-8.048 s (7.810 s median) | ❌ text-only | CN-created; Novita hosting (jurisdiction to confirm) | Pi 0.73.1 needs `supportsDeveloperRole: false`; then native `write` produced the exact seven-byte artifact with no extras. Novita's live model API says $0/M input and output, and the scored run's balance delta was $0.0000 at $0.0001 resolution. This is dated launch pricing, not an assumed permanent rate ([record](../research/hy3/2026-07-20-hy3-pi-novita.md)). |  |  | 41 |
| Kimi K2.6 | default | Kimi Code CLI | Yes | Fireworks | ✅ 3/3, 7-14 s/run | ✅ | US infra | Native-family harness on US hosting - the clean-provenance Kimi pairing. **Keeps the K2.6 seat after the long-spec A/B** (2/3 full pass vs Claude Code 0/3 - CC runs were faster but always overshot the word range; K2.6 verbosity is model-flavored and the native envelope reins it in). Natural stand-in for the Kimi Code seat until K3 gets a US host |  | 103.6 / 225.8 s (+1 timeout) | 44 |
| Kimi K2.6 | default | Claude Code | No | Fireworks | - | ✅ | US infra | Long-spec A/B alternate: faster than Kimi Code but 0/3 content pass because every run exceeded the requested word range. |  | 50.3 / 92.5 s (+1 timeout) | 44 |
| Kimi K2.6 | default | OpenHands | No | Fireworks | ✅ 3/3 | ✅ | US infra | Implement candidate; V1 SDK-script route (no CLI executable); good cost telemetry |  |  | 44 |
| Kimi K3 | default | Kimi Code CLI | Yes | OpenRouter → Moonshot | ✅ 3/3 | ✅ | ⚠️ **interim exception** (CN money; ruled by Jacob pending open weights + US host, ~weeks) | Prime triage/verify candidate (intelligence #3) once a US host exists; then: fresh floor probe, allowlist entry, fixture gauntlet |  |  | 57 |
| MiMo-V2.5-Pro | default | Claude Code | Yes | Novita | ✅ 3/3, 8-10 s/run | ? | CN-created; Novita hosting (jurisdiction to confirm for the allowlist ruling) | Jacob's ideas.md pick; first **direct** Claude Code × non-Anthropic pairing - Novita's Anthropic endpoint passes CLI model validation; intelligence 42 (#18) |  |  | 42 |
| MiniMax-M3 | default | Claude Code | Yes | Fireworks | ✅ 3/3, 4-9 s/run | ✅ | US infra | **Preferred MiniMax harness** (2026-07-18): long-spec A/B 3/3 full pass at 51-92 s while OpenCode capped out 0/3 with no file ([record](../research/long-spec-speed/2026-07-18-docx-spec-speed-comparison.md) addendum 3) |  | 50.7-92.0 s | 44 |
| MiniMax-M3 | default | OpenCode | No | Fireworks | ✅ 3/3 | ✅ | US infra | Short-probe floor passes, but 0/3 on the long-spec A/B (250 s cap-outs, no file) - the OpenCode long-form penalty on Fireworks models now reproduces across GLM and MiniMax. Eval-grid alternate; Claude Code preferred |  | 250 s timeout x3 | 44 |
| Muse Spark 1.1 | xhigh | OpenCode | No | Meta | ❌ 0/13 | ✅ | US | **Implement seat closed** - stochastic identity-token substitution, dose-dependent, no mitigation reaches zero ([bisection](../research/muse-spark/2026-07-17-muse-spark-envelope-bisection.md)). Candidate for *tool-free* judgment calls only, not yet qualified ([role assessment](../research/muse-spark/2026-07-17-muse-spark-factory-role-assessment.md)). Retest on Meta model update: B2 variant, n=10 |  |  | 51 |
| Nemotron 3 Ultra 550B-A55B | default (reasoning unexercised) | OpenCode | Yes | Blackbox AI | ✅ 3/3, with stalls | ? | US | On hold - AA speed claim not reproduced (60-87 tok/s here) and intermittent >300 s hangs disqualify it for a speed seat | 161.7 | 38.165 s | 38 |
| Qwen3.7 Max | default | OpenCode | Yes | Novita | ✅ 3/3, 11-14 s/run (one >300 s stall before the streak) | ? | CN-created; Novita hosting (jurisdiction to confirm) | Floor passes 2026-07-18. Not on Novita's Anthropic surface (per-model gating: `does not support endpoint: anthropic`), so the ideas.md Claude Code preference falls to OpenCode. Speed claim already rejected in the long-spec probe below (real ~54-61 t/s) | 57.6 | 240.115 s timeout | 46 |
<!-- END GENERATED pairs table -->

## Seat preference orders (A58-A61)

Graduated 2026-07-18 from `ideas.md`; this section is the operative
roster (`ideas.md` carries no authority). Method (A58): when task
quality has a ceiling relative to intelligence in / when it is verifiable / more easily verifiable, seat the cheapest
model that clears it at reliability parity; when there is no ceiling (especially non-verifiable tasks),
seat max intelligence. Constraints: usage money flows to American
companies (A59), no two seats share a model family or harness (A60),
and only allowlisted providers receive fieldbook source + request
content (A61). Reference charts are Artificial Analysis; they render
client-side, so refresh via the headless harness (`tools/aa-sweep.py`
snapshots to `../research/aa-snapshots/`). Reorders within these rules
are edits here, no new ruling; provider membership changes are A61
roster changes.

### Triage / cross-family verification seats

No loop on these seats, so the harness matters less (A58).

**No ceiling** ([AA Intelligence Index](https://artificialanalysis.ai/#intelligence-tabs), as of 2026-07-17):

| # | Model | Harness | Provider | Index |
| :-- | :-- | :-- | :-- | --: |
| 1 | Claude Fable 5 (with fallback) | Claude Code | Anthropic | 60 |
| 2 | GPT-5.6 Sol (max) | Codex | OpenAI | 59 |
| 3 | Kimi K3 | Kimi Code CLI | OpenRouter (A59 interim; K2.6 × Fireworks stands in until K3 gets a US host) | 57 |
| 4 | Grok 4.5 (high) | Grok Build | xAI | 54 |

**Ceiling** ([AA Cost per Intelligence Index Task](https://artificialanalysis.ai/#cost-tabs), lowest-price American gateway/API per model; as of 2026-07-17):

Text input only:

| # | Model | Harness | Provider | $/task |
| :-- | :-- | :-- | :-- | --: |
| 1 | DeepSeek V4 Flash (max) | Claude Code (direct; DeepClaude retired - see Pairs) | DeepInfra (FP4) | $0.02 |
| 2 | MiMo-V2.5-Pro | Claude Code (direct) | Novita | $0.03 |
| 3 | gpt-oss-120b (high) | OpenCode | DeepInfra | $0.06 |
| 4 | MiniMax-M3 | Claude Code (2026-07-18 A/B - see Pairs; ideas listed OpenCode) | Novita | $0.12 |

Text + image input:

| # | Model | Harness | Provider | $/task |
| :-- | :-- | :-- | :-- | --: |
| 1 | MiniMax-M3 | Claude Code (2026-07-18 A/B - see Pairs; ideas listed OpenCode) | Novita | $0.12 |
| 2 | GPT-5.6 Luna (max) | Codex | OpenAI | $0.21 |
| 3 | Claude 4.5 Haiku | Claude Code | Amazon Bedrock | $0.27 |
| 4 | Nemotron 3 Ultra | OpenCode | Blackbox | $0.27 |
| 5 | Gemini 3.1 Pro Preview | Gemini CLI | Google (Vertex preferred over AI Studio) | $0.29 |

Muse Spark 1.1 (xhigh) is worth reconsidering for seat 5 eventually, but it was not reliable with any given harness as of July 17 2026 testing.

### Implement worker seats

Harness pairing matters most here - tool use and loop quality dominate
(A58). Primary chart: [AA Coding Agent Index](https://artificialanalysis.ai/agents/coding-agents?coding-agents-performance-chart=index#coding-agents-index).

**No ceiling** (as of 2026-07-17):

| # | Model | Harness | Provider | Index |
| :-- | :-- | :-- | :-- | --: |
| 1 | GPT-5.6 Sol (max) | Codex | OpenAI | 61 |
| 2 | Fable 5 (max, with fallback) | Claude Code | Anthropic | 59 |
| 3 | Grok 4.5 (high) | Grok Build | xAI | 58 |
| 4 | Kimi K3 | Kimi Code CLI | OpenRouter (A59 interim) | 57 |

Seats 1-3 pass the floor at k=3
(`../research/floors/2026-07-17-harness-smoke-test.md`); Muse Spark's
implement seat is closed (see Pairs).

**Ceiling** ([AA coding-agent cost per task](https://artificialanalysis.ai/agents/coding-agents#coding-agents-cost-chart-tabs); as of 2026-07-17):

Text input only:

| #   | Model                  | Harness              | Provider                  | $/task |
| :-- | :--------------------- | :------------------- | :------------------------ | -----: |
| 1   | DeepSeek V4 Pro (high) | Claude Code (direct) | DeepInfra                 |  $0.27 |
| 2   | GPT-5.6 Luna (max)     | Codex                | OpenAI                    |  $1.57 |
| 3   | Gemini 3.1 Pro Preview | Gemini CLI           | Google (Vertex preferred) |  $2.00 |
| 4   | Grok 4.5 (high)        | Grok Build           | xAI                       |  $2.59 |

Text + image input:

| # | Model | Harness | Provider | $/task |
| :-- | :-- | :-- | :-- | --: |
| 1 | GPT-5.6 Luna (max) | Codex | OpenAI | $1.57 |
| 2 | Gemini 3.1 Pro Preview | Gemini CLI | Google (Vertex preferred) | $2.00 |
| 3 | Grok 4.5 (high) | Grok Build | xAI | $2.59 |
| 4 | Kimi K3 | Kimi Code CLI | OpenRouter (A59 interim) | $3.18 |

### Speed seats

Ranked by end-to-end long-spec harness wall time - headline
[AA output speed](https://artificialanalysis.ai/#speed-tabs) excludes
reasoning delay and harness behavior; local visible t/s is retained to
show raw delivery. Data: § Long-spec speed probe. As of 2026-07-18.
GLM-5.2 ranks above Luna on the post-A/B Claude Code wall time -
`ideas.md`'s list predates this re-rank.

| # | Model | Harness | Provider | Visible t/s | Long-spec wall |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | gpt-oss-120b (high) | OpenCode | Cerebras | 1,889.8 | 12.651 s |
| 2 | Command A+ (high requested) | OpenCode | Cohere | 209.7 (thinking disabled) | 22.514 s |
| 3 | Nemotron 3 Ultra | OpenCode | Blackbox AI | 161.7 | 38.165 s (on hold - stalls; see Pairs) |
| 4 | GLM-5.2 (default) | Claude Code (switched from OpenCode 2026-07-18 per effort-matched A/B) | Fireworks | 104.8 | 63.5-71.1 s |
| 5 | GPT-5.6 Luna (max) | Codex | OpenAI | 166.2 after 81.348 s reasoning delay | ~115 s |
| 6 | Gemini 3.5 Flash (high) | OpenCode | Google AI Studio | 229.3 | timeout at 240 s |
| 7 | Qwen3.7 Max | OpenCode | Novita | 57.6 | timeout at 240 s |

## Long-spec speed probe

One diagnostic harness run per pair on the same synthetic 1,400-1,800-word
`docx/specs.md` request, with a 240-second hard cap. OpenCode is the common
harness for the six original pairs; Luna uses Codex, and the later native
gpt-oss control uses Harmony Agent. This compares long-form wall time; it does
not replace pass^k floors or fixture admission. Full direct API repetitions,
provider-level corrections, and method are in the
[six-pair research record](../research/long-spec-speed/2026-07-18-docx-spec-speed-comparison.md),
[Luna addendum](../research/long-spec-speed/2026-07-18-gpt-5p6-luna-max-speed.md), and
[Harmony Agent addendum](../research/gpt-oss-120b/2026-07-18-gpt-oss-cerebras-harmonyagent.md).

| Pair | Harness wall | Content check | Speed standing |
| :-- | --: | :-- | :-- |
| gpt-oss-120b high × Cerebras, OpenCode | **12.651 s** | Miss: 2,372 words, over range | **Lead** - direct median 3.586 s and 1,889.8 visible common t/s |
| gpt-oss-120b high × Cerebras, Harmony Agent | **18.412 s** | **Pass**, 1,621 words | Fastest exact long-spec result, but floor reliability is only 5/10 |
| Command A+ high requested × Cohere | **22.514 s** | Miss: 1,290 words, under range | Runner-up; retain OpenCode, but high remains requested rather than verified |
| Nemotron 3 Ultra × Blackbox | 38.165 s | Miss: over range and one heading | Hold; local direct 161.7 visible t/s and prior stalls |
| GPT-5.6 Luna max × OpenAI, Codex | **~115 s** | **Pass**, 1,536 words | Fourth on wall; direct 166.2 visible t/s came only after 81.348 s to first answer |
| GLM 5.2 max requested × Fireworks | 175.731 s | **Pass**, 1,747 words | Exact but about 14× slower than Cerebras; not the speed seat |
| Gemini 3.5 Flash high × Google | **240.069 s, timeout** | File existed; over range; agent kept looping | Pair fails this workload; Gemini CLI would be a separate configuration |
| Qwen3.7 Max × Novita | **240.115 s, timeout** | File existed at 1,802 words; agent kept looping | Do not advance for speed - the supplied 205 t/s was not Novita; live provider result and local direct runs are about 54-61 t/s |

## Gateway routes (change what's runnable)

- **Claude Code × non-Anthropic models is now viable**: verified through
  Patchyard's existing preview LiteLLM gateway (GLM `Write` call produced the
  exact requested file), and OpenRouter's Anthropic-compatible endpoint
  supports Claude Code directly
  ([gateways note](../research/claude-code/2026-07-17-claude-code-non-anthropic-gateways.md)).
  The smoke-test report's "not runnable" for Claude Code × GLM is stale.
- **Novita's Anthropic-compatible endpoint works with Claude Code
  directly** (no gateway): `ANTHROPIC_BASE_URL=https://api.novita.ai/anthropic`
  + the Novita model id as `--model`, in an isolated `CLAUDE_CONFIG_DIR`.
  First proof that the CLI's model validation is satisfied by a
  well-shaped third-party endpoint - the proxy requirement is
  per-endpoint, not absolute.
- **Fireworks works with Claude Code directly too**:
  `ANTHROPIC_BASE_URL=https://api.fireworks.ai/inference` (base
  **without** `/v1` - the CLI appends its own paths; the 07-17 "rejects
  non-Claude names" finding was a double-pathed base URL). DeepInfra's
  `https://api.deepinfra.com/anthropic` likewise. Direct Anthropic
  surfaces now verified on three hosts: Novita, Fireworks, DeepInfra.
- Meta's Anthropic-compatible endpoint does **not** alias Claude model
  names - Claude Code × Muse still needs one of the gateways above.

## Still blocked / not applicable

| Item | Status |
| :-- | :-- |
| Cursor CLI × Composer 2.5 | Blocked: no Cursor credentials on this VM |
| MiniMax Code × MiniMax-M3 | N/A: desktop app only (macOS/Windows), no MiniMax platform key; its Agent Teams pattern is R21-rejected anyway |
| OpenSymphony | Not a harness - an orchestrator (control plane), which R11 says we build, not buy |
| Hermes Agent (for Nemotron, per ideas.md speed list) | Discovered but not benched: only an *unofficial* npm bridge exists (0.18.2), and its headline design - "self-improving, creates skills from experience" - collides with R19 (no self-editing policy). Needs a deliberate call before any bench time |

## Standing rules and triggers

- Cross-family is a verification requirement; cross-harness is an eval
  technique; the verifier's own harness should approach zero.
- One provider per worker boot; provider allowlist **ruled (A61)**:
  the full seat-roster union - Anthropic, OpenAI, xAI, Google, Meta,
  Amazon (Bedrock), Fireworks, Cerebras, DeepInfra, Novita, OpenRouter
  (Moonshot-interim per A59), Blackbox AI, Cohere. Seating admits,
  unseating removes; Novita's processing jurisdiction still needs the
  confirm flagged in Pairs.
- Floor probes are necessary, never sufficient - admission is the
  fixture gauntlet + shadow mode (D6). Score **rates (n≥10), not
  runs**, on any suspected stochastic behavior.
- Retest triggers: harness upgrades (versions pinned in the smoke-test
  report), Meta model updates (Muse), K3's US host arriving,
  `tools/aa-sweep.py` threshold hits (snapshots in
  `../research/aa-snapshots/`).
