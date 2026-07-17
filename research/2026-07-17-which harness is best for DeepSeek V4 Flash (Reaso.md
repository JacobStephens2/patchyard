<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# which harness is best for DeepSeek V4 Flash (Reasoning, Max Effort)?

**Best overall: Claude Code via DeepClaude.** It gives DeepSeek V4 Flash the strongest autonomous coding loop—planning, file editing, shell execution, and subagents—while correctly preserving reasoning across tool calls. A cross-harness benchmark scored V4 Flash at 78/100 in only three minutes and roughly \$0.01, though the detailed harness uplift was validated more thoroughly with V4 Pro than Flash.

## Practical ranking

| Harness | Best use | Verdict |
| :-- | :-- | :-- |
| **Claude Code + DeepClaude** | Larger features, repo-wide changes | **Best overall capability** |
| **Oh My Pi** | Direct DeepSeek API, predictable compatibility | **Best native/reliable option** |
| **OpenCode** | Existing OpenCode workflows | Good, but requires explicit interleaved-reasoning configuration |
| **Cline/KiloCode** | IDE-centric editing | Convenient, but provider compatibility can vary |

DeepClaude routes Claude Code’s mature agent loop through DeepSeek’s Anthropic-compatible endpoint, avoiding the `reasoning_content` failures that affected thinner or improperly configured harnesses.

## My recommendation

Given your terminal-heavy workflow, I’d use:

- **DeepClaude + Claude Code** for serious autonomous implementation.
- **Oh My Pi (`omp`)** when you want the cleanest direct-API setup and maximum control.
- **OpenCode** only if you already prefer its TUI and configure `interleaved.field` as `reasoning_content`.

For OMP, use the official custom `models.yml`; its built-in V4 entries remain incomplete for long reasoning/tool-call sessions. The critical settings map `xhigh` to DeepSeek’s `max`, disable `tool_choice`, and preserve `reasoning_content` across turns.[^1_1]

```bash
omp --model deepseek/deepseek-v4-flash
```

**Bottom line:** choose **DeepClaude** for the best coding-agent harness; choose **OMP** for the least fragile native DeepSeek V4 Flash integration.
<span style="display:none">[^1_10][^1_11][^1_12][^1_13][^1_14][^1_15][^1_16][^1_17][^1_18][^1_19][^1_2][^1_20][^1_21][^1_22][^1_3][^1_4][^1_5][^1_6][^1_7][^1_8][^1_9]</span>

<div align="center">⁂</div>

[^1_1]: https://www.reddit.com/r/DeepSeek/comments/1u1ndv0/how_are_you_running_deepseek_v4_pro_flash_in_the/

[^1_2]: https://artificialanalysis.ai/models/comparisons/deepseek-v4-flash-vs-deepseek-v4-pro-high

[^1_3]: https://pub.towardsai.net/i-tested-all-4-deepseek-v4-modes-on-20-real-tasks-the-0-04-flash-won-7-of-them-0ef0fb5c1771

[^1_4]: https://aiprofitboardroom.com/blog/deepseek-harness/

[^1_5]: https://bestaiagentcommunity.com/blog/deepseek-harness/

[^1_6]: https://www.reddit.com/r/DeepSeek/comments/1t26avf/how_you_using_v4_and_which_harness/

[^1_7]: https://aisuccesslabjuliangoldie.com/blog/deepseek-harness/

[^1_8]: https://www.mindstudio.ai/blog/agent-harnesses-beat-model-upgrades-5-benchmarks

[^1_9]: https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro/discussions/197

[^1_10]: https://github.com/Kilo-Org/kilocode/issues/9512

[^1_11]: https://github.com/NousResearch/hermes-agent/issues/21577

[^1_12]: https://artificialanalysis.ai/articles/deepseek-is-back-among-the-leading-open-weights-models-with-v4-pro-and-v4-flash

[^1_13]: https://www.akitaonrails.com/en/2026/05/04/llm-benchmarks-deepseek-unlocked-deepclaude/

[^1_14]: https://pi.dev/models/opencode/deepseek-v4-flash

[^1_15]: https://artificialanalysis.ai/changelog

[^1_16]: https://www.youtube.com/watch?v=n6CwdnSFz_o

[^1_17]: https://www.youtube.com/watch?v=yHgHU75N5T8

[^1_18]: https://artificialanalysis.ai/evaluations/harvey-lab-aa

[^1_19]: https://news.ycombinator.com/item?id=47984407

[^1_20]: https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/

[^1_21]: https://artificialanalysis.ai/evaluations/itbench-aa

[^1_22]: https://opencode.ai/data/deepseek/deepseek-v4-flash


---

# could I use DeepClaude + Claude Code with DeepSeek v4 Flash from DeepInfra?

**Yes. DeepInfra now exposes an Anthropic-compatible endpoint specifically compatible with Claude Code, so you can run DeepSeek V4 Flash through Claude Code directly—DeepClaude itself is optional.**[^2_1]

## Recommended setup

Add this function to `~/.zshrc`:

```bash
deepclaude-flash() {
  ANTHROPIC_BASE_URL="https://api.deepinfra.com/anthropic" \
  ANTHROPIC_AUTH_TOKEN="$DEEPINFRA_TOKEN" \
  ANTHROPIC_MODEL="deepseek-ai/DeepSeek-V4-Flash" \
  ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-ai/DeepSeek-V4-Flash" \
  ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-ai/DeepSeek-V4-Flash" \
  ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-ai/DeepSeek-V4-Flash" \
  CLAUDE_CODE_SUBAGENT_MODEL="deepseek-ai/DeepSeek-V4-Flash" \
  CLAUDE_CODE_EFFORT_LEVEL="max" \
  CLAUDE_CODE_MAX_OUTPUT_TOKENS="32768" \
  claude "$@"
}
```

Then:

```bash
export DEEPINFRA_TOKEN="your-token"
source ~/.zshrc

cd ~/your-project
deepclaude-flash
```

DeepInfra documents `https://api.deepinfra.com/anthropic` as its Claude Code endpoint and uses the full catalog identifier as `ANTHROPIC_MODEL`.  DeepInfra lists V4 Flash as supporting a 1M-token context and Non-think, Think High, and Think Max modes.[^2_2][^2_1]

## DeepClaude caveat

The `aattaran/deepclaude` wrapper is primarily configured around the first-party DeepSeek API and OpenRouter, although its stated architecture supports Anthropic-compatible backends.  You can modify its backend definition to use:[^2_3]

```bash
BASE_URL="https://api.deepinfra.com/anthropic"
API_KEY="$DEEPINFRA_TOKEN"
MODEL="deepseek-ai/DeepSeek-V4-Flash"
```

However, the shell function above is simpler and produces essentially the same Claude Code agent loop without another wrapper.

## Max-effort verification

`CLAUDE_CODE_EFFORT_LEVEL=max` is the appropriate Claude Code-side setting—DeepSeek’s official Claude Code integration uses that exact variable for maximum effort.  Because DeepInfra describes Think Max as involving a dedicated system prompt, verify the actual mode on an initial request rather than assuming every compatibility-layer release translates Claude’s effort field identically.[^2_4][^2_2]

If max reasoning does not activate consistently, run a direct API test against DeepInfra’s OpenAI-compatible endpoint and explicitly set the provider-supported reasoning option:

```text
https://api.deepinfra.com/v1/openai
model: deepseek-ai/DeepSeek-V4-Flash
reasoning_effort: max
```

DeepInfra identifies that URL as its OpenAI-compatible endpoint.  For Claude Code, though, use `/anthropic`, **not** `/v1/openai`; otherwise you would need an additional Anthropic-to-OpenAI translation proxy.[^2_5]
<span style="display:none">[^2_10][^2_11][^2_12][^2_13][^2_14][^2_15][^2_16][^2_17][^2_18][^2_19][^2_20][^2_21][^2_22][^2_23][^2_24][^2_25][^2_26][^2_27][^2_28][^2_29][^2_30][^2_31][^2_32][^2_33][^2_34][^2_35][^2_36][^2_37][^2_38][^2_39][^2_6][^2_7][^2_8][^2_9]</span>

<div align="center">⁂</div>

[^2_1]: https://docs.deepinfra.com/integrations/anthropic

[^2_2]: https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash

[^2_3]: https://github.com/aattaran/deepclaude

[^2_4]: https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/

[^2_5]: https://deepinfra.com/blog/deepseek-v4-pro-deepinfra

[^2_6]: https://www.reddit.com/r/ClaudeCode/comments/1t5xm50/tested_deepseek_v4_as_my_claude_code_backend_for/

[^2_7]: https://www.reddit.com/r/ClaudeWorkflows/comments/1t600ru/workflow_claude_code_integrate_deepseek_v4/

[^2_8]: https://forums.developer.nvidia.com/t/deepseek-v4-pro-v4-flash-on-nvidia-nim-streaming-tool-calls-do-not-continue-in-claude-code-anthropic-compatible-agent-workflow/368085

[^2_9]: https://news.ycombinator.com/item?id=48002136

[^2_10]: https://www.youtube.com/watch?v=ait_Na4JbUI

[^2_11]: https://www.mindstudio.ai/blog/run-claude-code-against-deepseek-v4-free-cloud-code-proxy

[^2_12]: https://www.datacamp.com/blog/deepseek-v4-vs-claude-opus-4-7

[^2_13]: https://www.verdent.ai/guides/deepseek-tui-vs-claude-code

[^2_14]: https://www.youtube.com/watch?v=EibhUi-FnTs

[^2_15]: https://deepinfra.com/blog/deepseek-v4-pro-max-api-benchmarks-latency-throughput-cost

[^2_16]: https://deepinfra.com/blog/deepseek-v4-pro-model-overview

[^2_17]: https://deepinfra.com/blog/step-3.7-flash-release

[^2_18]: https://fireworks.ai/models/fireworks/deepseek-v4-flash

[^2_19]: https://deepinfra.com/

[^2_20]: https://openrouter.ai/deepseek/deepseek-v4-flash

[^2_21]: https://deepinfra.com/stepfun-ai/Step-3.7-Flash

[^2_22]: https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash/api

[^2_23]: https://deepinfra.com/google/gemini-2.5-flash/api

[^2_24]: https://www.requesty.ai/models/deepinfra/deepseek-ai-deepseek-v4-flash

[^2_25]: https://deepinfra.com/blog/glm-5-2-pricing-benchmarks-cost-comparison

[^2_26]: https://build.nvidia.com/deepseek-ai/deepseek-v4-flash

[^2_27]: https://deepinfra.com/blog/best-glm-5-2-max-api-providers

[^2_28]: https://github.com/openclaw/openclaw/issues/43896

[^2_29]: https://docs.openclaw.ai/providers/deepinfra

[^2_30]: https://github.com/moazbuilds/claudeclaw/issues/215

[^2_31]: https://www.reddit.com/r/ClaudeAI/comments/1l88015/how_to_set_custom_base_url_in_claude_code_like/

[^2_32]: https://gitlawb.com/z6MkqDnb7Siv3Cwj7pGJq4T5EsUisECqR8KpnDLwcaZq5TPr/openclaude

[^2_33]: https://www.linkedin.com/posts/theburningmonk_github-aattarandeepclaude-use-claude-activity-7457066428421304320-GoEK

[^2_34]: https://github.com/Gitlawb/openclaude

[^2_35]: https://github.com/zed-industries/zed/discussions/35333

[^2_36]: https://news.ycombinator.com/item?id=44653950

[^2_37]: https://github.com/OpenRouterTeam/deepclaude

[^2_38]: https://ofox.ai/blog/claude-code-switch-tutorial-2026/

[^2_39]: https://www.sitepoint.com/how-to-route-deepseekv4-through-claude-code-for-local-agentic-coding/


---

# What is DeepClaude?

**DeepClaude is an open-source wrapper that runs the Claude Code agent harness while replacing Anthropic’s Claude model with DeepSeek or another compatible backend.** In short, it keeps Claude Code’s “body” but swaps its “brain.”[^3_1]

## What stays

Claude Code continues to provide:

- Repository exploration and file editing
- Bash and Git execution
- Tool calls and MCP servers
- Subagents and multi-step loops
- Hooks, settings, session resume, and IDE integrations[^3_2][^3_1]


## What changes

Instead of sending inference requests to Anthropic, DeepClaude adjusts Claude Code’s environment and routes those requests to an Anthropic-compatible endpoint, such as DeepSeek, OpenRouter, or another provider. Its implementation is essentially a small shell wrapper and local Node proxy that also handles backend switching and some subagent-routing edge cases.[^3_3][^3_2]

```text
Your prompt
    ↓
Claude Code agent harness
    ↓
DeepClaude routing/proxy layer
    ↓
DeepSeek V4 Flash or another model
    ↓
Claude Code executes returned tool calls
```

It does **not** combine Claude and DeepSeek, and it does not require Claude to review DeepSeek’s answers. Only the selected backend model performs inference; Claude Code supplies the surrounding agent loop.[^3_1]

## Do you need it?

For your DeepInfra setup, **probably not**. DeepInfra already offers an Anthropic-compatible Messages API intended for Claude Code, so setting `ANTHROPIC_BASE_URL`, the authentication token, and model variables gives you the important functionality directly.[^3_4]

DeepClaude remains useful when you want:

- `/deepseek`, `/anthropic`, and `/openrouter` runtime switching
- Provider profiles wrapped in one command
- Automatic restoration of your original Claude environment
- Compatibility handling for providers whose Anthropic implementation has rough edges[^3_3][^3_1]

The term is ambiguous: there are older projects also named DeepClaude that combine DeepSeek R1 reasoning with Claude generation. In our discussion, **DeepClaude means `aattaran/deepclaude`, the Claude Code backend-routing wrapper**, not those hybrid inference projects.[^3_5][^3_1]
<span style="display:none">[^3_10][^3_6][^3_7][^3_8][^3_9]</span>

<div align="center">⁂</div>

[^3_1]: https://github.com/aattaran/deepclaude

[^3_2]: https://agentconn.com/agents/deepclaude/

[^3_3]: https://www.reddit.com/r/ClaudeCode/comments/1t3hrcx/deepclaude_full_claude_code_agent_loop_on/

[^3_4]: https://docs.deepinfra.com/integrations/anthropic

[^3_5]: https://github.com/OpenRouterTeam/deepclaude

[^3_6]: https://news.ycombinator.com/item?id=48002136

[^3_7]: https://tech.yahoo.com/ai/claude/articles/deepclaude-lets-run-claude-code-201937968.html

[^3_8]: https://deepclaude.app/

[^3_9]: https://hdrobots.com/ai-tools/deepclaude

[^3_10]: https://www.youtube.com/watch?v=ymunCZzgzeg

