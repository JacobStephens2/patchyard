# Bench status

*Living document - the at-a-glance answer to "what's the current status
of each (model × harness) pair?" Edited in place as statuses change; the
evidence stays in `../research/`'s dated records, which this file only
cites. Floor probe = the muse-smoke exact-instruction check
(`../research/2026-07-17-harness-smoke-test.md`), k=3 unless noted.
Seats are design-time assignments; nothing runs in production until
phase 1 builds.*

*Last updated: 2026-07-18 (GLM 5.2 × Claude Code direct via Fireworks added).*

## Pairs

| Model | Effort | Harness | Host | Floor | Img-in | Provenance | Current standing |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| Claude Haiku 4.5 | high | Claude Code | Amazon Bedrock | ✅ 3/3, 3.6 s and $0.0357/run | ✅ content; strict format miss | US | **Qualified floor configuration:** `claude -p --allowedTools Write`; exact 7-byte file every run. A follow-up environment-allowlisted child-process run also passed with only 15-minute STS AWS credentials present; Firecracker/Podman containment and egress are not built. Image labels were all correct, but the requested bare JSON was fenced. A `--bare --tools Write` variant failed 0/3 by claiming success without calling the tool; pin the canonical form ([record](../research/2026-07-17-claude-code-bedrock-haiku.md)) |
| Command A+ | high (requested) | OpenCode | Cohere | ✅ 3/3, ~7 s wall/run; 1.3-1.7 s event span | ❌ OpenCode image adapter | Canada-created; Cohere first-party API (processing region not pinned) | **Use OpenCode, not Terminus-2, for the first Patchyard test.** Native `write` produced the exact 7-byte artifact every run; direct raw streaming reproduced the speed claim at 209.7 tok/s. Advance only to the text gauntlet: OpenCode reports zero reasoning telemetry despite the high request, and both local and server-attached image paths failed while a direct Cohere image control passed. Terminus-2 remains the reference rerun for suspected harness-specific failures ([record](../research/2026-07-18-command-a-plus-opencode.md)) |
| DeepSeek V4 Flash | max (requested) | Claude Code (direct) | DeepInfra | ✅ 3/3, 6-8 s/run | ❌ text-only | US infra (CN-created, allowed) | **Preferred Flash wiring:** DeepInfra's Anthropic-compatible surface works directly; DeepClaude is unnecessary. Advance to the text-only alphabetize fixture gauntlet; provider mode still needs fixture validation ([floor record](../research/2026-07-17-harness-smoke-test.md)) |
| DeepSeek V4 Flash | max (requested) | Claude Code + DeepClaude | DeepInfra | ✅ 3/3, 5.8-12.3 s wall/run | ❌ text-only | US infra (CN-created, allowed) | Earlier patched-launcher treatment. Request-level max evidence captured, but retain only as historical comparison now that the direct route passes ([record](../research/2026-07-17-deepseek-v4-deepclaude.md)) |
| DeepSeek V4 Pro | max (requested) | Claude Code (direct) | DeepInfra | ✅ 3/3, 4-5 s/run | ❌ text-only | US infra (CN-created, allowed) | **Preferred Pro wiring and fastest full agentic floor runs on the bench:** direct DeepInfra Anthropic-compatible surface, no DeepClaude. Advance to the text-only alphabetize fixture gauntlet ([floor record](../research/2026-07-17-harness-smoke-test.md)) |
| DeepSeek V4 Pro | max (requested) | Claude Code + DeepClaude | DeepInfra | ✅ 3/3, 4.2-6.6 s wall/run | ❌ text-only | US infra (CN-created, allowed) | Earlier patched-launcher treatment. Request-level max evidence captured, but retain only as historical comparison now that the direct route passes ([record](../research/2026-07-17-deepseek-v4-deepclaude.md)) |
| Fable 5 | max | Claude Code | Anthropic | ✅ 3/3 | ✅ | US | Implement bench #2; **builder incumbent** |
| Gemini 3.1 Pro (preview) | default (not pinnable via CLI) | Gemini CLI | Google - **Vertex verified** (`example-model-bench`, location `global`; AI Studio also 3/3) | ✅ 3/3 both surfaces | ✅ | US | Judgment-seat candidate. Vertex is the preferred surface per ideas.md - dedicated SA/project provisioned 2026-07-17, ops reference in [`vertex-access.md`](vertex-access.md) |
| Gemini 3.5 Flash | default | Gemini CLI | Google | ✅ 3/3 | ✅ | US | Fast/cheap generalist; needs `GEMINI_CLI_TRUST_WORKSPACE=true` headless |
| GLM 5.2 | default | Claude Code | Fireworks | ✅ 3/3, 6-10 s/run | ❌ text-only | US infra (CN-created, allowed) | Direct pairing works (2026-07-18): `ANTHROPIC_BASE_URL=https://api.fireworks.ai/inference` - base **without** `/v1`; the CLI appends its own paths, and the earlier "not runnable" was a double-pathed base URL, not an endpoint limitation. FireConnect (Fireworks' alias-mapping tool) is the maintained route for full sessions with subagent slots; manual env suffices for headless probes |
| GLM 5.2 | default | OpenCode | Fireworks | ✅ 3/3 | ❌ text-only | US infra (CN-created, allowed) | Implement-capable; excluded from screenshot-reading seats |
| GLM 5.2 | default (`--thinking` available) | Pi | Fireworks | ✅ 3/3 | ❌ | US infra | Same as above; Pi exposes native thinking levels |
| GPT-5.6 Sol | xhigh | Codex | OpenAI | ✅ 3/3 | ✅ | US | Implement bench #1 (no-ceiling order); **adversarial reviewer incumbent** (A41) |
| gpt-oss-120b | default (pin blocked by Cline schema) | Cline | **Cerebras** (preferred) / Fireworks | ✅ 3/3, 4-6 s/run | ❌ | US | **Speed-seat lead** - Cerebras ~1,000-1,100 tok/s ±5% vs Fireworks 118-234 ([head-to-head](../research/2026-07-17-harness-smoke-test.md)) |
| gpt-oss-120b | high | Harmony Agent + Cerebras transport | Cerebras | ❌ **5/10 strict**, 6.103 s median; target bytes exact 10/10 | ❌ text-only | US infra; US-created, open weights | Native Harmony works and the long spec passed in 18.412 s, but default instructions created `.pytest_cache` or `.git` in half the floor runs. Keep as a diagnostic reference, not a factory runner. Upstream also hardcodes local vLLM, so Cerebras needs the recorded transport adapter ([record](../research/2026-07-18-gpt-oss-cerebras-harmonyagent.md)) |
| gpt-oss-120b | high | OpenCode | DeepInfra | ✅ 3/3, 12.9-16.9 s wall/run | ❌ text-only | US infra; US-created, open weights | **Preferred viable harness** from the ordered search: native `write` tool and exact 7-byte artifact in every run. Harmony Agent's earlier DeepInfra treatment missed exact acceptance, Codex + generic adapter was tool-protocol-incompatible, and mini-swe-agent scored 4/10 exact; Cline/Roo were not tested after OpenCode passed ([record](../research/2026-07-17-gpt-oss-120b-deepinfra-harness-selection.md)) |
| Grok 4.5 | high | Grok Build | xAI | ✅ 3/3 | ✅ | US | Implement bench #3; tiebreak-verifier candidate |
| Kimi K2.6 | default | Kimi Code CLI | Fireworks | ✅ 3/3, 7-14 s/run | ✅ | US infra | Native-family harness on US hosting - the clean-provenance Kimi pairing (no K3-style exception needed). Wired via a second provider block in `~/.kimi-code/config.toml`; K2.6 becomes the natural stand-in for the Kimi Code seat until K3 gets a US host |
| Kimi K2.6 | default | OpenHands | Fireworks | ✅ 3/3 | ✅ | US infra | Implement candidate; V1 SDK-script route (no CLI executable); good cost telemetry |
| Kimi K3 | default | Kimi Code CLI | OpenRouter → Moonshot | ✅ 3/3 | ✅ | ⚠️ **interim exception** (CN money; ruled by Jacob pending open weights + US host, ~weeks) | Prime triage/verify candidate (intelligence #3) once a US host exists; then: fresh floor probe, allowlist entry, fixture gauntlet |
| MiMo-V2.5-Pro | default | Claude Code | Novita | ✅ 3/3, 8-10 s/run | ? | CN-created; Novita hosting (jurisdiction to confirm for the allowlist ruling) | Jacob's ideas.md pick; first **direct** Claude Code × non-Anthropic pairing - Novita's Anthropic endpoint passes CLI model validation; intelligence 42 (#18) |
| MiniMax-M3 | default | OpenCode | Fireworks | ✅ 3/3 | ✅ | US infra | Implement candidate; the multimodal alternative to GLM |
| Muse Spark 1.1 | xhigh | OpenCode | Meta | ❌ 0/13 | ✅ | US | **Implement seat closed** - stochastic identity-token substitution, dose-dependent, no mitigation reaches zero ([bisection](../research/2026-07-17-muse-spark-envelope-bisection.md)). Candidate for *tool-free* judgment calls only, not yet qualified ([role assessment](../research/2026-07-17-muse-spark-factory-role-assessment.md)). Retest on Meta model update: B2 variant, n=10 |
| Nemotron 3 Ultra 550B-A55B | default (reasoning unexercised) | OpenCode | Blackbox AI | ✅ 3/3, with stalls | ? | US | On hold - AA speed claim not reproduced (60-87 tok/s here) and intermittent >300 s hangs disqualify it for a speed seat |
| Qwen3.7 Max | default | OpenCode | Novita | ✅ 3/3, 11-14 s/run (one >300 s stall before the streak) | ? | CN-created; Novita hosting (jurisdiction to confirm) | Floor passes 2026-07-18. Not on Novita's Anthropic surface (per-model gating: `does not support endpoint: anthropic`), so the ideas.md Claude Code preference falls to OpenCode. Speed claim already rejected in the long-spec probe below (real ~54-61 t/s) |

## Long-spec speed probe

One diagnostic harness run per pair on the same synthetic 1,400-1,800-word
`docx/specs.md` request, with a 240-second hard cap. OpenCode is the common
harness for the six original pairs; Luna uses Codex, and the later native
gpt-oss control uses Harmony Agent. This compares long-form wall time; it does
not replace pass^k floors or fixture admission. Full direct API repetitions,
provider-level corrections, and method are in the
[six-pair research record](../research/2026-07-18-docx-spec-speed-comparison.md),
[Luna addendum](../research/2026-07-18-gpt-5p6-luna-max-speed.md), and
[Harmony Agent addendum](../research/2026-07-18-gpt-oss-cerebras-harmonyagent.md).

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
  ([gateways note](../research/2026-07-17-claude-code-non-anthropic-gateways.md)).
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
- One provider per worker boot; provider allowlist ruling pending
  (candidates now: Anthropic, OpenAI, xAI, Google, Meta, Fireworks,
  Cerebras, DeepInfra, Novita, OpenRouter/Moonshot-interim, Blackbox, Cohere).
- Floor probes are necessary, never sufficient - admission is the
  fixture gauntlet + shadow mode (D6). Score **rates (n≥10), not
  runs**, on any suspected stochastic behavior.
- Retest triggers: harness upgrades (versions pinned in the smoke-test
  report), Meta model updates (Muse), K3's US host arriving,
  `aa-sweep.py` threshold hits (snapshots in
  `../research/aa-snapshots/`).
