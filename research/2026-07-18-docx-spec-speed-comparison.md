# Long-spec speed comparison - six provider x OpenCode pairs

*2026-07-18. Operator: the orchestration agent on the orchestration VM. This
is a speed probe, not factory admission. Direct APIs were repeated; the
long-form harness leg is one run per pair. Existing exact-file floors remain
the reliability evidence.*

## Verdict

For an Patchyard `docx/specs.md`-class writing job, the clear speed choice is
**OpenCode x gpt-oss-120b (high) x Cerebras**. It delivered the direct workload
in a 3.586-second median and completed the OpenCode file-writing job in 12.651
seconds. The next completed harness run, Command A+, took 22.514 seconds;
Nemotron took 38.165 seconds; GLM 5.2 max took 175.731 seconds. Gemini and
Qwen did not exit before the 240-second cap.

Do not use the supplied headline list as a provider ranking. It mixed
Artificial Analysis' model representation with particular providers. The
largest correction is Qwen3.7 Max: its roughly 204 t/s model representation is
driven by Alibaba Cloud, while the requested Novita route currently measures
about 54 t/s. The local direct runs reproduced Novita at 54.5 and 60.7 visible
t/s.

GLM was the only pair to pass every long-form content check in its one harness
run. That makes it an interesting quality control, not the speed seat. Cerebras
was about 14x faster end to end but exceeded the requested word range. Prompt
fit must be scored separately from throughput.

## Scope and method

No `docx/specs.md` exists in this worktree, repository history, or the other
checked `/srv/orchestration` working trees. The probe therefore used the
sanitized synthetic request in
[`fixtures/docx-spec-speed/request.md`](../fixtures/docx-spec-speed/request.md):
a production specification for a deterministic Markdown-to-DOCX service,
1,400-1,800 words, with eight exact level-two sections.

Two layers keep provider speed separate from harness behavior:

1. **Direct streaming API:** identical prompt, 6,000 requested output tokens,
   180-second wall cap, provider high/max effort where named, common
   `cl100k_base` token count over visible answer text. First-content time
   includes input and reasoning; visible t/s covers first-to-last answer
   content. Three interleaved runs per original candidate. Qwen was added later
   and has two independently timed runs plus one additional completed specimen.
2. **OpenCode 1.18.3:** one fresh directory per pair, `--pure`, explicit title,
   JSON events, auto-approved tools, and a 240-second hard cap. The common
   harness removes cross-harness startup and prompt differences. Variants were
   `high` for gpt-oss, Command A+, and Gemini, `max` for GLM, and provider
   default for Nemotron and Qwen.

Harness acceptance required the target file, no other file, all headings in
order, 1,400-1,800 words, no `TODO`/`TBD`, and normal process completion. The
single harness run is diagnostic only - it is not pass^k or an admission gate.

Reproduction tools:

```bash
uv run --with openai --with tiktoken benchmark_spec_speed.py \
  --rounds 3 --max-tokens 6000 --timeout 180

python3 benchmark-harness-speed.py \
  --output-dir /tmp/patchyard-docx-spec-speed --timeout 240
```

## Correcting the Artificial Analysis list

Values below are the live pages observed on 2026-07-18. They move with the
rolling window. "Model representation" is a first-party result or provider
median; it is not automatically the speed of the provider named beside it.

| Candidate | Supplied t/s | Current provider-level t/s | What changed |
| :-- | --: | --: | :-- |
| gpt-oss-120b (high) x Cerebras | 266 | **1,727.5** | Supplied value was not the current Cerebras route |
| Nemotron 3 Ultra x Blackbox AI | 190 | **437.1** | 190 was approximately the model representation, not Blackbox |
| Command A+ x Cohere | 185 | **185.3** | Correct pairing and order of magnitude |
| GLM 5.2 (max) x Fireworks | 171 | **314.3** | Supplied value was not the current Fireworks route |
| Gemini 3.5 Flash (high) x Google | 163 | **159.5** | Essentially current; first-answer latency remains material |
| Qwen3.7 Max x Novita | 205 | **53.5** | 204.1 is the model representation; Alibaba Cloud is about 203 |

Artificial Analysis defines output speed after streaming begins. It does not
include input processing or a reasoning model's delay before the first answer
token. Its provider pages now expose that distinction directly. Qwen/Novita,
for example, shows about 2 seconds to first reasoning token but about 47 seconds
to first answer token.

## Direct API results

| Pair | Runs | Median first visible answer | Median visible t/s | Median wall | Outcome |
| :-- | --: | --: | --: | --: | :-- |
| gpt-oss-120b high x Cerebras | 3 | **1.228 s** | **1,889.8** | **3.586 s** | Answer every run; 3,749-4,549 visible common tokens; strict content acceptance 0/3, mainly verbosity |
| Nemotron 3 Ultra x Blackbox | 3 | 1.290 s | 161.7 | 36.676 s | Answer every run; all hit the 6,000-token cap and greatly exceeded the word range |
| Command A+ x Cohere | 3 | No answer | n/a | 23.386 s | Adaptive reasoning consumed all 6,000 tokens in every run before visible content |
| GLM 5.2 max x Fireworks | 3 | 74.777 s among answer runs | 104.8 | 86.688 s | One run produced no answer; two produced partial, under-length specs before the cap |
| Gemini 3.5 Flash high x Google | 3 | 8.756 s | 229.3 | 25.175 s | Answer every run; 0/3 exact section-and-length acceptance |
| Qwen3.7 Max x Novita | 2 | 97.000 s | 57.6 | 131.466 s | One of two timed outputs passed all content checks; separate batch also produced a 1,701-word complete specimen before a later request stalled |

The Cerebras result is higher than the live provider page and the earlier local
1,000-1,100 t/s fixed-token control. This probe uses a common tokenizer over
visible text rather than provider token IDs, and workload and route state also
differ. Treat the local number as this workload on this route, not a replacement
for the standardized AA result.

Command A+'s raw result is a workload warning, not evidence that it cannot
write the document. Its OpenCode run did write one in 22.5 seconds. The direct
compatibility endpoint exposed 6,000 reasoning tokens, while OpenCode reported
zero reasoning tokens under `--variant high`. High effort remains requested,
not verified, in that adapter. A previous thinking-disabled direct control
measured 209.7 t/s.

## OpenCode long-spec result

| Pair | Wall | Event span | Output / reasoning telemetry | Content result | Standing |
| :-- | --: | --: | :-- | :-- | :-- |
| gpt-oss-120b high x Cerebras | **12.651 s** | 6.937 s | 8,854 / 2,217 | 2,372 words; all headings; over range | **Speed-seat lead** |
| Command A+ high requested x Cohere | **22.514 s** | 17.501 s | 3,311 / 0 | 1,290 words; all headings; under range | Second on wall time; fix effort evidence and length adherence before promotion |
| Nemotron 3 Ultra x Blackbox | 38.165 s | 30.966 s | 4,975 / 0 | 2,705 words; one heading wrong; over range | Hold - slower locally and prior intermittent stalls remain |
| GLM 5.2 max requested x Fireworks | 175.731 s | 169.186 s | 8,188 / 0 | **PASS**, 1,747 words | Only exact content pass; far too slow for the speed seat |
| Gemini 3.5 Flash high x Google | **240.069 s, timeout** | 227.653 s | 13,727 / 28,661 | File existed at 2,141 words, but agent kept looping | Pair fails this workload; use Gemini CLI only in a separate retest |
| Qwen3.7 Max x Novita | **240.115 s, timeout** | 232.039 s | 7,774 / 849 | File existed at 1,802 words, but agent kept looping | Pair fails; changing harness cannot repair Novita's raw throughput deficit |

OpenCode's costs are catalog estimates, not invoice evidence. Custom-provider
runs reported zero cost, so costs are intentionally not compared here.
Reasoning telemetry is also adapter-dependent: the direct GLM max and Qwen
runs exposed reasoning, while their OpenCode events did not report it reliably.

## Harness choices

- **gpt-oss-120b/Cerebras:** use OpenCode for this test seat. Unlike the earlier
  Cline floor configuration, it accepts the named `high` variant and produced
  the fastest long-form agent result. Keep Cline's 3/3 exact-file floor as a
  fallback, not as the timing comparator.
- **Command A+/Cohere:** keep OpenCode. The existing floor is 3/3 and the long
  spec completed. Terminus-2 adds no value unless a later terminal fixture
  appears OpenCode-specific.
- **Nemotron/Blackbox:** OpenCode is already proven to use its write tool, but
  the provider's local speed and stall history do not justify another harness.
- **GLM/Fireworks:** OpenCode carried `max` for the common comparison and
  produced the only accepted document. Pi remains a useful alternative when
  explicit native thinking controls matter.
- **Gemini/Google:** the tested OpenCode high pair timed out. Gemini CLI has the
  existing 3/3 exact-file floor, but its CLI cannot currently pin the same high
  effort, so it would be a different configuration rather than a retry.
- **Qwen/Novita:** OpenCode was the selected common harness. Do not spend time
  trying Claude Code and Qwen Code for a speed-seat decision: direct Novita
  inference already needs roughly two minutes for this spec. If Qwen's
  intelligence or price becomes the goal, Claude Code is the most relevant
  separate fallback given Patchyard's working Novita Anthropic path.

## Decision

Advance **OpenCode x gpt-oss-120b high x Cerebras** to a repeated long-spec
fixture after tightening the length verifier. Keep **OpenCode x Command A+** as
the cross-family runner-up. Use **GLM max** as evidence that slower reasoning
can improve exact prompt fit, not as a speed candidate. Do not advance the
Blackbox, Gemini-high/OpenCode, or Qwen/Novita pairs on speed evidence.

References:

- [Artificial Analysis: gpt-oss-120b providers](https://artificialanalysis.ai/models/gpt-oss-120b/providers)
- [Artificial Analysis: Nemotron 3 Ultra providers](https://artificialanalysis.ai/models/nvidia-nemotron-3-ultra-550b-a55b/providers)
- [Artificial Analysis: Command A+](https://artificialanalysis.ai/models/command-a-plus)
- [Artificial Analysis: GLM 5.2 providers](https://artificialanalysis.ai/models/glm-5-2/providers)
- [Artificial Analysis: Gemini 3.5 Flash](https://artificialanalysis.ai/models/gemini-3-5-flash)
- [Artificial Analysis: Qwen3.7 Max providers](https://artificialanalysis.ai/models/qwen3-7-max/providers)
- [Cerebras: gpt-oss reasoning controls](https://inference-docs.cerebras.ai/capabilities/reasoning)
- [Blackbox AI: OpenAI-compatible API](https://docs.blackbox.ai/api-reference/introduction)
- [Cohere: OpenAI compatibility API](https://docs.cohere.com/docs/compatibility-api)
- [Fireworks: GLM 5.2 model route](https://fireworks.ai/models/fireworks/glm-5p2)
- [Google: Gemini 3.5 Flash thinking levels](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5)
- [Novita: Qwen3.7 Max route and model ID](https://novita.ai/models/model-detail/qwen-qwen3.7-max)
- [OpenCode: custom providers](https://opencode.ai/docs/providers)
