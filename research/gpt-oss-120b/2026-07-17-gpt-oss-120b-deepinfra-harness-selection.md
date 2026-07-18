# gpt-oss-120b × DeepInfra harness selection

*2026-07-17. Operator: the orchestration agent, on the orchestration VM.
This is the ordered harness search specified in `docs/ideas.md`, not a
fixture-gauntlet admission.*

## Outcome

OpenCode 1.18.3 is the first harness in the requested order that passes the
exact-instruction floor. It passed 3/3 with the high-reasoning variant, made
one native `write` call per run, and created the exact seven bytes `factory`.
Cline and Roo Code were not tested because the instruction says to stop at the
first working harness.

| Order | Harness treatment | Result | Decision |
| --: | :-- | :-- | :-- |
| 1 | Harmony Agent + native Harmony | Exact acceptance missed on the first standardized run: `factory\n` | Reject - a 3/3 streak was no longer possible |
| 2 | Codex CLI + Responses-to-Chat Harmony adapter | DeepInfra returned native Harmony actions that Codex could not deserialize | Protocol-incompatible - no floor score |
| 3 | mini-swe-agent + LiteLLM/DeepInfra Harmony integration | **4/10 exact**; six runs wrote `factory\n` | Reject - stochastic shell-action choice |
| 4 | OpenCode + dedicated DeepInfra provider | **PASS 3/3** | Select and stop |
| 4b | Cline / Roo Code | Not run | Later alternatives in the same fallback tier |

The floor remains necessary but insufficient. This pair advances only to the
text-only alphabetize fixture gauntlet, then shadow mode.

Credential-free structured evidence is in
[`2026-07-17-gpt-oss-120b-deepinfra-floor-results.json`](2026-07-17-gpt-oss-120b-deepinfra-floor-results.json).

## Common treatment

Every scored run used the unchanged smoke prompt from
`../floors/2026-07-17-harness-smoke-test.md`:

```text
Create a file named muse-smoke.txt in the current directory containing exactly the word: factory
```

Pass required one file named `muse-smoke.txt` whose complete content was the
seven-byte sequence `66 61 63 74 6f 72 79`. A trailing newline failed. Each
run used a fresh temporary working directory, environment-variable
authentication, a 240- or 300-second wall timeout, and the exact DeepInfra
model ID `openai/gpt-oss-120b`.

DeepInfra documents gpt-oss-120b as text-only with a 131,072-token context,
function calling, and low/medium/high reasoning:
https://deepinfra.com/openai/gpt-oss-120b. Its live catalog metadata exposed
the same three effort values. The provider prices at test time were `$0.037`
per million input tokens and `$0.17` per million output tokens. The `$0.06`
figure in `docs/ideas.md` is the Artificial Analysis task estimate; this
experiment also used it as the per-run cap where the harness exposed a cap.

OpenAI documents that gpt-oss was trained on the Harmony response format and
should be used with it: https://github.com/openai/harmony. Each route below
therefore had to preserve Harmony either natively or through the provider
integration; ordinary text completion was not treated as an agent harness.

## Harmony Agent missed exact acceptance

The reviewed Harmony Agent source was
https://github.com/borislavmavrin/harmonyagent at commit
`175dda4a212193b79e5d860186c5043fd9cdc8e1`. Its upstream `vllm_raw.py`
transport is fixed to a local vLLM raw-completions endpoint. A disposable
transport class retained the upstream `HarmonyAgent`, `AgentConfig`,
`LocalEnvironment`, templates, parser, and tools while sending the already
rendered Harmony prompt unchanged to DeepInfra's documented raw-completions
endpoint, `https://api.deepinfra.com/v1/openai/completions`.

The standardized configuration was:

```text
reasoning_effort=high
step_limit=1000
cost_limit=0.06
max_new_tokens=65536
max_context_window=131070
environment_timeout=300
tools=Harmony Agent defaults
```

Every one of the 14 raw requests contained Harmony Agent's `Reasoning: high`
control marker. The agent submitted after 27.635 seconds and spent an
estimated `$0.00124437`, but its `repo_browser.apply_patch` action produced
eight bytes: `factory\n`. This is an exact failure, even though the intended
word is visually correct.

Three earlier setup runs used a non-upstream four-step cap while the transport
was being checked. Two happened to write seven exact bytes and one wrote no
file. They are not scored because the step cap changed the treatment. They do
show that the result is variable; Harmony Agent needs an `n>=10` rate study if
it is reconsidered. The ordered acceptance search stopped its standardized
series at the first failure because it could no longer attain the required
3/3 qualification.

One secondary compatibility defect appeared: `repo_browser.print_tree`
invoked a missing `tree` executable despite its source description referring
to `find`. The agent recovered, so that was not the acceptance failure.

## Codex needs an action translator, not only a wire adapter

Codex CLI 0.144.5 no longer supports a Chat Completions provider. A direct
`wire_api = "chat"` configuration exits before inference with:

```text
`wire_api = "chat"` is no longer supported.
```

That removal is documented at
https://github.com/openai/codex/discussions/7782 and enforced in the reviewed
v0.144.5 source at commit
`87db9bc18ba5bc82c1cb4e4381b44f693ee35623`.

The next attempt used `open-responses-server` branch
`fix/codex-cli-compat`, commit
`e885aff562bfe6e58a742592733f6baa1f44a411`, as a disposable generic
Responses-to-Chat adapter. Three narrow changes selected DeepInfra's endpoint
and model and translated Codex's `reasoning.effort` to
`reasoning_effort`. Adapter logs confirmed `high`, DeepInfra returned HTTP
200, and the response identified `openai/gpt-oss-120b`.

The returned Harmony action language did not match Codex's internal tool
protocol. Representative calls were:

```json
{"name":"exec","arguments":{"cmd":["apply_patch","-p0","--stdout","-","-","--","@@ -0,0 +1 @@\n+factory\n"],"timeout":10000,"env":{}}}
{"name":"apply_patch","arguments":{"patch":"*** Begin Patch\n*** Add File: muse-smoke.txt\n+factory\n*** End Patch"}}
```

Codex rejected repeated `exec`, `apply_patch`, and `exec.apply_patch` calls as
`tool ... invoked with incompatible payload`; no file was created. The run was
stopped after the incompatibility repeated. A production Codex Harmony
adapter must translate the model's action schemas into Codex's current tools
and results. No maintained drop-in translator for Codex 0.144.5 appeared in
the reviewed sources, so the closest generic Responses/Chat bridge was tested.
This result shows that bridge is insufficient; it does not prove that a future
purpose-built Codex action translator cannot work.

## mini-swe-agent was stochastic at 4/10

mini-swe-agent v2.3.0, commit
`adfe20233d456104c38c3129161b54f0fd39f2c7`, ran its official
`mini_textbased.yaml` agent with the `litellm_textbased` model class. LiteLLM
used DeepInfra's OpenAI-compatible Chat endpoint and handled the gpt-oss
Harmony conversion. Configuration overrides were:

```text
model=openai/openai/gpt-oss-120b
api_base=https://api.deepinfra.com/v1/openai
reasoning_effort=high
temperature=1
step_limit=20
cost_limit=0.06
global_call_limit=20
```

All ten runs reached `Submitted` in two model calls. Four selected `printf`
and wrote exact bytes; six selected a shell heredoc and wrote a trailing
newline. The exact sequence was pass, pass, fail, fail, pass, pass, fail,
fail, fail, fail. Total estimated provider cost was `$0.00118809`, or
`$0.000118809` per run.

The trajectories identify the actual provider model as
`openai/gpt-oss-120b`, retain `reasoning_content`, and record the high-effort
request option. This is not a transport failure. It is a stochastic choice
between two shell actions with different byte semantics.

## OpenCode passed and becomes the selected harness

OpenCode 1.18.3 ran its built-in `deepinfra` provider with no custom provider
block:

```text
opencode run --pure --auto --format json \
  --variant high \
  --model deepinfra/openai/gpt-oss-120b \
  --dir <fresh-workdir> \
  'Create a file named muse-smoke.txt in the current directory containing exactly the word: factory'
```

| Run | Wall | Recorded build-loop cost | Output tokens | Tool | Artifact |
| --: | --: | --: | --: | :-- | :-- |
| 1 | 12.884 s | `$0.000550258` | 400 | `write` with content `factory` | exact 7 bytes |
| 2 | 16.364 s | `$0.000543338` | 368 | same | exact 7 bytes |
| 3 | 16.907 s | `$0.000554989` | 425 | same | exact 7 bytes |

Recorded build-loop cost was `$0.001648585`; mean recorded cost was
`$0.000549528` per run. Each scored build loop made two model calls: one tool
turn and one final-text turn. OpenCode also made one small title-generation
request before each build loop; that call appears in the debug lifecycle but
not in the JSON event cost, so the cost figures above are lower bounds. Wall
time includes the title request. The final prose did not affect the score.

The installed model metadata lists `low`, `medium`, and `high` effort variants
for this exact model. OpenCode's reviewed v1.18.3 source, commit
`127bdb30784d508cc556c71a0f32b508a3061517`, resolves `--variant high`
through `reasoningVariants()` and returns `{reasoningEffort: "high"}` for
`@ai-sdk/deepinfra`; the request layer then merges the selected variant into
the model options. Its pinned `@ai-sdk/deepinfra` 2.0.41 subclasses
`@ai-sdk/openai-compatible` 2.0.37; that exact dependency serializes
`reasoningEffort` as the Chat Completions request field `reasoning_effort`.
This is source-traced wire construction from the installed release, not an
independent HTTP-body capture. DeepInfra accepted every scored call and the
three additional title calls. The dedicated provider uses the
`DEEPINFRA_API_KEY` environment variable and the documented base URL; see
https://ai-sdk.dev/providers/ai-sdk-providers/deepinfra.

## Next gate

Run OpenCode × gpt-oss-120b (high) through the text-only alphabetize fixture
gauntlet with the same model, provider, harness version, and variant. Do not
assign it a factory seat from this floor alone. Retest the floor after an
OpenCode provider/variant change, a DeepInfra model revision, or any future
Harmony Agent reconsideration.
