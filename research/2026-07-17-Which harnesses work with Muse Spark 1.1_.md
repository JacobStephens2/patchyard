<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# Which harnesses work with Muse Spark 1.1?

Muse Spark 1.1 currently has confirmed support or demonstrated integration with **OpenCode, Cline, OpenClaw, Kilo Code, and Claude Code**. **Cursor is not supported yet**, though its team has indicated plans to add it.[^1_1][^1_2][^1_3]

## Compatibility status

| Harness | Status | Notes |
| :-- | :-- | :-- |
| **OpenCode** | Officially demonstrated | Meta used it for debugging and DeepSWE evaluation demos. [^1_1] |
| **Cline** | Confirmed | Cline was an early Muse Spark partner and explicitly announced developer access. [^1_1] |
| **OpenClaw** | Confirmed | Meta lists OpenClaw as a working agent environment. [^1_1] |
| **Kilo Code** | Available now | Select `meta/muse-spark-1.1` in Kilo’s VS Code, JetBrains, CLI, or cloud harness. |
| **Claude Code** | Works through API redirection | Meta’s developer instructions support configuring Claude Code to use the Meta endpoint and API key. [^1_3] |
| **Custom OpenAI-style harnesses** | Generally compatible | The Meta Model API uses an OpenAI-compatible interface, making custom agents and compatible clients straightforward to connect. [^1_1] |
| **Cursor** | Not yet | Cursor has said support is planned but still being worked out. [^1_2] |

Meta also says the model was specifically trained for varied harnesses and supports planning, goal conditioning, subagent delegation, MCP servers, custom skills, and context compaction.[^1_1]

For the smoothest setup today, I’d choose **OpenCode** for a terminal-native workflow or **Kilo Code/Cline** for IDE integration.
<span style="display:none">[^1_10][^1_11][^1_12][^1_13][^1_14][^1_15][^1_16][^1_17][^1_18][^1_19][^1_20][^1_21][^1_22][^1_23][^1_4][^1_5][^1_6][^1_7][^1_8][^1_9]</span>

<div align="center">⁂</div>

[^1_1]: https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/

[^1_2]: https://forum.cursor.com/t/support-for-muse-spark-1-1/165339

[^1_3]: https://www.youtube.com/watch?v=meNE3EAKmP4

[^1_4]: https://news.ycombinator.com/item?id=48846184

[^1_5]: https://www.reddit.com/r/LocalLLaMA/comments/1usbfz3/meta_are_apparently_working_on_an_open_source/

[^1_6]: https://www.youtube.com/watch?v=XCYYDhG9zKw

[^1_7]: https://sakercanine.com/blogs/gear/key-differences-between-the-muse-harness-and-the-canyon-light-series

[^1_8]: https://kingy.ai/blog/muse-spark-1-1-benchmarks-specs-evals/

[^1_9]: https://sakercanine.com/pages/muse-dog-harness

[^1_10]: https://www.datacamp.com/blog/muse-spark-1-1

[^1_11]: https://ruffwear.com/products/web-master-harness

[^1_12]: https://nlp.elvissaravia.com/p/ai-agents-weekly-gpt-56-family-meta

[^1_13]: https://igendesign.com/smart-dog-harness-for-jk9lab

[^1_14]: https://shop.shinepay.co/products/replacement-harness

[^1_15]: https://chipos.io/news/brief/meta-s-muse-spark-1-1-outperforms-glm-5-2-in-coding-and-costs-slightly-less-22ffe602fab63412

[^1_16]: https://www.facebook.com/groups/9003421258/posts/10164107141871259/

[^1_17]: https://www.youtube.com/watch?v=kdJhdo0VqVY

[^1_18]: https://www.youtube.com/watch?v=ZtiDMXiDARs

[^1_19]: https://www.labellerr.com/blog/meta-muse-spark-1-1-the-future-of-agentic-ai-and-coding/

[^1_20]: https://clawvard.school/blog/best-ai-coding-agents-2026-muse-spark-claude-code-gemini

[^1_21]: https://www.facebook.com/groups/868876935222403/posts/1357291459714279/

[^1_22]: https://explainx.ai/blog/muse-spark-1-1-meta-model-api-july-2026

[^1_23]: https://kilo.ai/models/meta-muse-spark-1-1


---

# Verify these findings.

The earlier answer was **mostly correct**, but it overstated some evidence. **OpenCode, Claude Code, OpenClaw, and Kilo Code are directly verified; Cline is strongly supported as an early-access integration; Cursor is planned but unavailable.**[^2_1][^2_2][^2_3]

## Verified status

| Harness | Verdict | Evidence |
| :-- | :-- | :-- |
| **OpenCode** | **Verified** | Meta explicitly demonstrates Muse Spark 1.1 debugging and DeepSWE evaluation inside OpenCode, and its developer guide provides OpenCode setup instructions. [^2_3] |
| **Claude Code** | **Verified** | Meta’s developer documentation says Claude-oriented tools—including Claude Code—work through the Anthropic Messages format. [^2_3][^2_4][^2_5] |
| **OpenClaw** | **Verified** | Meta identifies OpenClaw as an early partner and publishes an OpenClaw cookbook explicitly specifying `muse-spark-1.1` as the model and OpenClaw as the harness. [^2_6] |
| **Kilo Code** | **Verified independently** | Kilo offers Muse Spark 1.1 in its model selector across VS Code, JetBrains, CLI, and cloud agents. This is Kilo’s own integration rather than one documented by Meta’s launch post. [^2_1] |
| **Cline** | **Strongly supported** | Meta quotes Cline’s CEO saying Cline developers received early access, but the launch article does not provide Cline-specific configuration or explicitly label general availability. |
| **OpenAI-compatible agents** | **Verified, with qualification** | Meta documents an OpenAI-compatible endpoint and says compatible agents can generally connect through a custom-provider configuration using model ID `muse-spark-1.1`; individual harness behavior may still depend on support for custom base URLs and tool calling. [^2_7][^2_8][^2_5] |
| **Anthropic-compatible agents** | **Verified, with qualification** | Meta says its API is compatible with the Anthropic SDK and supports Anthropic-format agents, which is what enables Claude Code-style integrations. [^2_4][^2_5] |
| **Cursor** | **Not available yet** | The Cursor thread is a feature request, and a Cursor Community Support Engineer says support is planned but still being worked out. [^2_2] |

## Corrections

- The earlier claim that Meta’s launch post directly confirmed **Claude Code** was imprecise; the confirmation comes from Meta’s separate developer documentation.[^2_3]
- Calling **Cline fully confirmed** was slightly too strong without a public setup page; “early-access partner with strong evidence of compatibility” is more accurate.
- “Custom OpenAI-style harnesses are compatible” should not imply universal plug-and-play support; the harness must expose a custom endpoint/provider and correctly handle the API’s tool-calling behavior.[^2_7][^2_5]
- The earlier recommendation remains reasonable: **OpenCode** has the strongest first-party demonstration, while **Kilo Code** has the clearest immediately available IDE/CLI integration.[^2_1]
<span style="display:none">[^2_10][^2_11][^2_12][^2_13][^2_14][^2_15][^2_16][^2_17][^2_18][^2_19][^2_9]</span>

<div align="center">⁂</div>

[^2_1]: https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/

[^2_2]: https://forum.cursor.com/t/support-for-muse-spark-1-1/165339

[^2_3]: https://developer.meta.com/ai/resources/blog/build-with-muse-spark/

[^2_4]: https://ai.developer.meta.com/docs/getting-started/overview

[^2_5]: https://ai.developer.meta.com/docs/guides/coding-agents/

[^2_6]: https://ai.developer.meta.com/docs/getting-started/cookbook/rayban-openclaw/

[^2_7]: https://ai.developer.meta.com/docs/getting-started/cookbook/quickstart-chat-completions/

[^2_8]: https://ai.developer.meta.com/docs/features/chat-completion/

[^2_9]: https://forum.cursor.com/filter?page=11

[^2_10]: https://forum.cursor.com/top

[^2_11]: https://cline.bot/blog/introducing-cline-sdk-the-upgraded-agent-runtime

[^2_12]: https://ai.developer.meta.com/docs/getting-started/cookbook/one-shot-game-dev

[^2_13]: https://cline.bot/blog/guide-to-cursor-alternatives-without-usage-limits-2025

[^2_14]: https://developer.meta.com/ai/resources/cookbook/deploy_llama_on_vllm/

[^2_15]: https://cline.bot/blog/memory-bank-how-to-make-cline-an-ai-agent-that-never-forgets

[^2_16]: https://cline.bot/blog/20-one-shot-prompts-that-turn-kanban-into-an-autonomous-coding-machine

[^2_17]: https://developer.meta.com/ai/docs/deployment/infrastructure-migration/

[^2_18]: https://docs.cline.bot/provider-config/aws-bedrock/api-key

[^2_19]: https://developer.meta.com/ai/docs/getting-the-models/405b-partners/


---

# Which of these harnesses is most minimal?

**OpenCode is the most minimal practical harness for Muse Spark 1.1.** It runs directly in a terminal, needs no IDE extension or persistent gateway, and Meta documents it as a first-class Muse Spark coding-agent integration.[^3_1][^3_2]

## Relative footprint

| Harness | Minimality | Why |
| :-- | --: | :-- |
| **OpenCode** | **Best** | Terminal-first, straightforward provider configuration, and usable as a focused local coding loop. [^3_1][^3_3] |
| **Claude Code** | Close second | Also terminal-native with a simple native installation, but routing it to Muse Spark requires configuring Meta’s Anthropic-compatible endpoint rather than its default provider. [^3_4][^3_2] |
| **Kilo Code CLI** | Moderate | The CLI can be lean, but Kilo’s broader product spans IDE, CLI, cloud agents, and hosted integrations. [^3_5] |
| **Cline** | Heavier | Primarily operates as an IDE extension with UI-managed providers, tools, permissions, and MCP configuration. [^3_6][^3_7] |
| **OpenClaw** | Heaviest | Designed as an always-on agent platform with a gateway, dashboard, messaging channels, skills, and optional external coding harnesses. [^3_8][^3_9] |

## Recommendation

For your terminal-heavy workflow, use **OpenCode with only Muse Spark configured**, leaving MCP servers, subagents, plugins, and GitHub automation disabled until needed. OpenCode supports permissions and optional provider features without requiring them for the basic coding loop.[^3_10][^3_11]

Choose **Claude Code** instead if “minimal” means the smallest amount of installation and UI ceremony and you do not care about open-source inspectability. Choose **OpenCode** if it means the cleanest, least opinionated, provider-neutral Muse harness—which is probably the better interpretation here.
<span style="display:none">[^3_12][^3_13][^3_14][^3_15][^3_16][^3_17][^3_18][^3_19][^3_20][^3_21][^3_22][^3_23][^3_24][^3_25][^3_26]</span>

<div align="center">⁂</div>

[^3_1]: https://opencode.ai/docs/

[^3_2]: https://ai.developer.meta.com/docs/guides/coding-agents/

[^3_3]: https://www.freecodecamp.org/news/integrate-ai-into-your-terminal-using-opencode/

[^3_4]: https://code.claude.com/docs/en/setup

[^3_5]: https://kilo.ai/

[^3_6]: https://docs.cline.bot/provider-config/anthropic

[^3_7]: https://docs.cline.bot/mcp/mcp-overview

[^3_8]: https://ai.developer.meta.com/docs/getting-started/cookbook/rayban-openclaw/

[^3_9]: https://www.youtube.com/watch?v=DF97eH55dMg\&vl=en

[^3_10]: https://opencode.ai/docs/cli/

[^3_11]: https://opencode.ai/docs/permissions/

[^3_12]: https://cefboud.com/posts/coding-agents-internals-opencode-deepdive/

[^3_13]: https://gist.github.com/shibuiwilliam/1d1466b24cb5c8f0d9367f2c75c9c064

[^3_14]: https://www.youtube.com/watch?v=vHkLrDD2xrU

[^3_15]: https://dev.to/rosgluk/opencode-quickstart-install-configure-and-use-the-terminal-ai-coding-agent-4kcb

[^3_16]: https://claudefa.st/blog/guide/installation-guide

[^3_17]: https://www.linkedin.com/posts/kilo_introducing-kilo-claw-hosted-openclaw-activity-7425608955252465664-mFqf

[^3_18]: https://computingforgeeks.com/setup-opencode-ai-coding-agent/

[^3_19]: https://code.claude.com/docs/en/terminal-guide

[^3_20]: https://ai.sulat.com/the-definitive-guide-to-opencode-from-first-install-to-production-workflows-aae1e95855fb

[^3_21]: https://www.whytryai.com/p/claude-code-beginner-guide

[^3_22]: https://opencode.ai/docs/troubleshooting/

[^3_23]: https://opencode.ai/docs/zh-tw/

[^3_24]: https://opencode.ai/docs/themes/

[^3_25]: https://opencode.ai/docs/network/

[^3_26]: https://docs.cline.bot/core-workflows/using-commands

