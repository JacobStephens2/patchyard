# Bench status

*Living document - the at-a-glance answer to "what's the current status
of each (model × harness) pair?" Edited in place as statuses change; the
evidence stays in `../research/`'s dated records, which this file only
cites. Floor probe = the muse-smoke exact-instruction check
(`../research/2026-07-17-harness-smoke-test.md`), k=3 unless noted.
Seats are design-time assignments; nothing runs in production until
phase 1 builds.*

*Last updated: 2026-07-17 (late - Bedrock Haiku qualified).*

## Pairs

| Pair (effort) | Host | Floor | Img-in | Provenance | Current standing |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Codex × GPT-5.6 Sol (xhigh) | OpenAI | ✅ 3/3 | ✅ | US | Implement bench #1 (no-ceiling order); **adversarial reviewer incumbent** (A41) |
| Claude Code × Fable 5 (max) | Anthropic | ✅ 3/3 | ✅ | US | Implement bench #2; **builder incumbent** |
| Claude Code × DeepClaude × DeepSeek V4 Flash (max) | DeepInfra | ✅ 3/3, 5.8-12.3 s wall/run | ❌ text-only | US infra (CN-created, allowed) | Floor passes; advance to text-only alphabetize fixture gauntlet. Request-level max evidence captured; provider mode still needs fixture validation ([record](../research/2026-07-17-deepseek-v4-deepclaude.md)) |
| Claude Code × DeepClaude × DeepSeek V4 Pro (max) | DeepInfra | ✅ 3/3, 4.2-6.6 s wall/run | ❌ text-only | US infra (CN-created, allowed) | Floor passes; advance to text-only alphabetize fixture gauntlet. Request-level max evidence captured; provider mode still needs fixture validation ([record](../research/2026-07-17-deepseek-v4-deepclaude.md)) |
| OpenCode × gpt-oss-120b (high) | DeepInfra | ✅ 3/3, 12.9-16.9 s wall/run | ❌ text-only | US infra; US-created, open weights | **Preferred viable harness** from the ordered search: native `write` tool and exact 7-byte artifact in every run. Harmony Agent missed exact acceptance, Codex + generic adapter was tool-protocol-incompatible, and mini-swe-agent scored 4/10 exact; Cline/Roo were not tested after OpenCode passed ([record](../research/2026-07-17-gpt-oss-120b-deepinfra-harness-selection.md)) |
| Grok Build × Grok 4.5 (high) | xAI | ✅ 3/3 | ✅ | US | Implement bench #3; tiebreak-verifier candidate |
| OpenCode × Muse Spark 1.1 (xhigh) | Meta | ❌ 0/13 | ✅ | US | **Implement seat closed** - stochastic identity-token substitution, dose-dependent, no mitigation reaches zero ([bisection](../research/2026-07-17-muse-spark-envelope-bisection.md)). Candidate for *tool-free* judgment calls only, not yet qualified ([role assessment](../research/2026-07-17-muse-spark-factory-role-assessment.md)). Retest on Meta model update: B2 variant, n=10 |
| OpenCode × GLM 5.2 | Fireworks | ✅ 3/3 | ❌ text-only | US infra (CN-created, allowed) | Implement-capable; excluded from screenshot-reading seats |
| Pi × GLM 5.2 | Fireworks | ✅ 3/3 | ❌ | US infra | Same as above; Pi has native `--thinking` levels |
| OpenCode × MiniMax-M3 | Fireworks | ✅ 3/3 | ✅ | US infra | Implement candidate; the multimodal alternative to GLM |
| Gemini CLI × Gemini 3.5 Flash | Google | ✅ 3/3 | ✅ | US | Fast/cheap generalist; needs `GEMINI_CLI_TRUST_WORKSPACE=true` headless |
| Gemini CLI × Gemini 3.1 Pro (preview) | Google (AI Studio) | ✅ 3/3 | ✅ | US | Judgment-seat candidate; thinking level not pinnable via CLI yet. **Vertex path (preferred per ideas.md) blocked**: aiplatform API not enabled on the only available project (`vbt-seo-search-console`) and the BQ-reader SA lacks an aiplatform role - both Google-console steps; dedicated SA/project recommended |
| OpenHands × Kimi K2.6 | Fireworks | ✅ 3/3 | ✅ | US infra | Implement candidate; V1 SDK-script route (no CLI executable); good cost telemetry |
| Cline × gpt-oss-120b | **Cerebras** (preferred) / Fireworks | ✅ 3/3, 4-6 s/run | ❌ | US | **Speed-seat lead** - Cerebras ~1,000-1,100 tok/s ±5% vs Fireworks 118-234 ([head-to-head](../research/2026-07-17-harness-smoke-test.md)); effort pin blocked by Cline's provider schema |
| OpenCode × Nemotron 3 Ultra 550B-A55B | Blackbox AI | ✅ 3/3, with stalls | ? | US | On hold - AA speed claim not reproduced (60-87 tok/s here) and intermittent >300 s hangs disqualify it for a speed seat |
| Claude Code × MiMo-V2.5-Pro | Novita | ✅ 3/3, 8-10 s/run | ? | CN-created; Novita hosting (jurisdiction to confirm for the allowlist ruling) | Jacob's ideas.md pick; first **direct** Claude Code × non-Anthropic pairing - Novita's Anthropic endpoint passes CLI model validation; intelligence 42 (#18) |
| Claude Code × Claude Haiku 4.5 (high) | Amazon Bedrock | ✅ 3/3, 3.6 s and $0.0357/run | ✅ content; strict format miss | US | **Qualified floor configuration:** `claude -p --allowedTools Write`; exact 7-byte file every run. A follow-up environment-allowlisted child-process run also passed with only 15-minute STS AWS credentials present; Firecracker/Podman containment and egress are not built. Image labels were all correct, but the requested bare JSON was fenced. A `--bare --tools Write` variant failed 0/3 by claiming success without calling the tool; pin the canonical form ([record](../research/2026-07-17-claude-code-bedrock-haiku.md)) |
| Kimi Code CLI × Kimi K3 | OpenRouter → Moonshot | ✅ 3/3 | ✅ | ⚠️ **interim exception** (CN money; ruled by Jacob pending open weights + US host, ~weeks) | Prime triage/verify candidate (intelligence #3) once a US host exists; then: fresh floor probe, allowlist entry, fixture gauntlet |

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
- Meta's Anthropic-compatible endpoint does **not** alias Claude model
  names - Claude Code × Muse still needs one of the gateways above.

## Still blocked / not applicable

| Item | Status |
| :-- | :-- |
| Cursor CLI × Composer 2.5 | Blocked: no Cursor credentials on this VM |
| MiniMax Code × MiniMax-M3 | N/A: desktop app only (macOS/Windows), no MiniMax platform key; its Agent Teams pattern is R21-rejected anyway |
| OpenSymphony | Not a harness - an orchestrator (control plane), which R11 says we build, not buy |

## Standing rules and triggers

- Cross-family is a verification requirement; cross-harness is an eval
  technique; the verifier's own harness should approach zero.
- One provider per worker boot; provider allowlist ruling pending
  (candidates now: Anthropic, OpenAI, xAI, Google, Meta, Fireworks,
  Cerebras, DeepInfra, OpenRouter/Moonshot-interim, Blackbox).
- Floor probes are necessary, never sufficient - admission is the
  fixture gauntlet + shadow mode (D6). Score **rates (n≥10), not
  runs**, on any suspected stochastic behavior.
- Retest triggers: harness upgrades (versions pinned in the smoke-test
  report), Meta model updates (Muse), K3's US host arriving,
  `aa-sweep.py` threshold hits (snapshots in
  `../research/aa-snapshots/`).
