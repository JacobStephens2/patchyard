# gpt-oss-120b × Harmony Agent × Cerebras

*2026-07-18. Operator: the orchestration agent on the orchestration VM. Upstream
Harmony Agent commit `175dda4a212193b79e5d860186c5043fd9cdc8e1`, which was
still GitHub `HEAD` when tested. This is a transport probe, an n=10 exact-file
floor, and one long-spec diagnostic - not fixture admission.*

## Verdict

**The native Harmony path works through Cerebras, but Harmony Agent is not a
qualified Patchyard harness.** The model used Harmony analysis/tool/final channels and
completed the target in all ten floor runs. Every target file contained the
exact seven bytes `factory`, but only 5/10 runs left exactly the requested file:
four also created `.pytest_cache`, and one initialized `.git`.

The long-spec result was excellent: **18.412 seconds and a full content pass**.
It created only `docx/specs.md`, used the exact eight headings in order, and
landed at 1,621 words. This makes Harmony Agent a useful Cerebras reference
harness, but the 50% strict floor rate prevents replacing the qualified Cline or
OpenCode configurations.

Credential-free structured evidence is in
[`2026-07-18-gpt-oss-cerebras-harmonyagent-evidence.json`](2026-07-18-gpt-oss-cerebras-harmonyagent-evidence.json).

## What the earlier result meant

The prior Harmony Agent test used DeepInfra, not Cerebras. Its one standardized
run wrote `factory\n`, so it failed exact-byte acceptance and the ordered 3/3
search moved on. Three unscored setup runs had already shown variability. The
current n=10 Cerebras study resolves the open question: transport and exact
target bytes are fine, but upstream harness policy still creates unrequested
repository artifacts often enough to fail Patchyard's floor.

## The supplied integration claim needed one correction

Cerebras now documents `POST /v1/completions` for `gpt-oss-120b`, and that raw
endpoint preserves Harmony special tokens. Harmony Agent cannot simply be given
a different OpenAI SDK `base_url`, however. Its `VllmRawModel`:

- hardcodes `http://localhost:8000/v1/completions`;
- does not send a model name or API-key header; and
- sends vLLM-only `skip_special_tokens`, `stop_token_ids`, `min_p`, and `top_k`
  fields.

Pointing that payload at Cerebras with a model and key returned HTTP 400 listing
all four fields as unsupported. The working adapter retained Harmony Agent's
native rendering, parsing, messages, tools, and model loop, while translating
only the transport:

```text
endpoint: https://api.cerebras.ai/v1/completions
model: gpt-oss-120b
stop_token_ids [200002, 200012]
  -> stop strings ["<|return|>", "<|call|>"]
remove: skip_special_tokens, min_p, top_k
```

The reusable adapter is
[`benchmark-harmonyagent-cerebras.py`](../benchmark-harmonyagent-cerebras.py).

## Exact-file floor

Every run used a fresh empty directory, high reasoning, upstream default tools
and instructions, a 240-second cap, and the existing prompt:

```text
Create a file named muse-smoke.txt in the current directory containing exactly the word: factory
```

| Measure | Result |
| :-- | --: |
| Strict acceptance | **5/10 - fail** |
| Target content alone | **10/10 exact seven bytes** |
| Median wall | **6.103 s** |
| Wall range | 3.059-11.086 s |
| Model calls/run | 3-22 |
| Extra artifacts | `.pytest_cache` in 4; `.git` in 1 |

The failures follow Harmony Agent's own developer instruction to run tests and
its tendency to initialize an empty repository. They are not Cerebras output
corruption. Removing that instruction or limiting tools might improve this
synthetic floor, but that would be a different harness treatment and would hide
rather than measure upstream defaults.

## Long-spec speed result

The unchanged [`docx/specs.md` request](../fixtures/docx-spec-speed/request.md)
ran once with the same treatment:

| Measure | Result |
| :-- | --: |
| Harness wall | **18.412 s** |
| Content | **PASS - 1,621 words, all headings in order** |
| Created files | Exactly `docx/specs.md` |
| Model calls | 12 |
| Prompt / cached prompt tokens | 148,280 / 82,176 |
| Completion tokens | 22,921 |
| Provider completion time | 8.867 s |
| Provider-reported decode rate | **2,584.9 t/s** |

The high token count reveals a harness defect: `repo_browser.apply_patch` shells
out to an `apply_patch` executable that is not installed here. Four complete
patch attempts failed with exit 127 before the model switched to
`container.exec`, wrote the file, checked its word count and headings, and
submitted. Cerebras speed masked that waste; it should still be fixed before any
production reconsideration.

For the common speed list, OpenCode × the same model/provider remains faster at
12.651 seconds, though its one document was over length. Harmony Agent's 18.412
seconds is the faster exact content pass and materially faster than Command A+'s
22.514-second under-length run.

## Decision

Keep Harmony Agent as a raw-Harmony reference for diagnosing gpt-oss provider or
OpenCode behavior. Do not promote it to a factory runner until both conditions
hold:

1. the upstream tool implementation stops relying on missing `tree` and
   `apply_patch` executables; and
2. an unchanged-treatment n=10 floor reaches the reliability threshold without
   creating unrequested repository state.

References:

- [OpenAI Harmony response format](https://developers.openai.com/cookbook/articles/openai-harmony)
- [Cerebras Completions API](https://inference-docs.cerebras.ai/api-reference/completions)
- [Harmony Agent source](https://github.com/borislavmavrin/harmonyagent)
