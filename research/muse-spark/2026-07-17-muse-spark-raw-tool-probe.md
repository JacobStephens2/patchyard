# Muse Spark 1.1 preserves exact filenames in raw Meta tool calls

*2026-07-17. Operator: the orchestration agent, on the orchestration VM.
Model: `muse-spark-1.1` through Meta's public-preview Model API. This is
the missing harness-free control for
[`2026-07-17-harness-smoke-test.md`](../floors/2026-07-17-harness-smoke-test.md).*

## Result

Muse Spark 1.1 returned the exact requested path in **80/80 raw tool
calls**: 40/40 through `POST /v1/responses` and 40/40 through `POST
/v1/chat/completions`. `muse-smoke.txt` passed 10/10 on each endpoint,
as did `meta-smoke.txt`, `claude-smoke.txt`, and `zebra-smoke.txt`.
Every matrix request returned HTTP 200, model identifier
`muse-spark-1.1`, exactly one `write_file` call, and content `factory`.

This overturns the prior report's broad **model-level** attribution.
The minimal Meta serving path does not unconditionally rewrite
`muse-smoke.txt` in tool-call arguments. The failure remains real in
the tested OpenCode and OpenHands loops, but the evidence does not yet
locate it in model generation under the richer harness context,
adapter parsing, or tool execution. It also cannot distinguish model
weights from Meta's system prompt, post-processing, or serving layer in
contexts that were not reproduced here.

## Method

The injected `META_AI_API_KEY` was confirmed nonempty without printing
or recording it. A small Python standard-library client then called
Meta directly - no OpenCode, OpenHands, SDK, or other agent framework.
The client never executed a returned call and persisted each raw HTTP
body before parsing it for the summary.

Each endpoint received 10 fresh requests for each of four paths, for
80 matrix trials total, from 17:49:20 through 17:49:44 UTC:

| Dimension | Value |
| :-- | :-- |
| Model | `muse-spark-1.1` |
| Endpoints | `/v1/responses`; `/v1/chat/completions` |
| Paths | `muse-smoke.txt`; `meta-smoke.txt`; `claude-smoke.txt`; `zebra-smoke.txt` |
| Trials | 10 per path per endpoint - 80 total |
| Sampling | `temperature: 0`, the lowest accepted value |
| Tools | exactly one synthetic strict-schema function, `write_file(path, content)` |
| System instruction | preserve filenames literally; call the requested tool once with exact arguments |
| User instruction | call `write_file` with the selected path and content `factory` |
| Execution | none |

The endpoint envelopes differed only where the APIs require it.
Responses used `instructions`, string `input`, and a flat function
definition; Chat Completions used system/user `messages` and a function
nested under `tools[].function`.

An initial schema control used a named `tool_choice` on each endpoint.
Both returned HTTP 400 with the same limitation:

```text
only `"auto"` is supported for `tool_choice`. `"none"`, `"required"`,
and named function choices are not currently supported
```

Those two rejected controls are retained in the evidence but excluded
from the 80 trials. Both comparable matrix envelopes were then changed
explicitly to `tool_choice: "auto"`; no other schema adaptation was
made.

## Endpoint results

| Endpoint | Requested path | Exact call | HTTP/model/status |
| :-- | :-- | --: | :-- |
| `/v1/responses` | `muse-smoke.txt` | 10/10 | 10 HTTP 200; model exact; `completed` |
| `/v1/responses` | `meta-smoke.txt` | 10/10 | 10 HTTP 200; model exact; `completed` |
| `/v1/responses` | `claude-smoke.txt` | 10/10 | 10 HTTP 200; model exact; `completed` |
| `/v1/responses` | `zebra-smoke.txt` | 10/10 | 10 HTTP 200; model exact; `completed` |
| `/v1/chat/completions` | `muse-smoke.txt` | 10/10 | 10 HTTP 200; model exact; `tool_calls` |
| `/v1/chat/completions` | `meta-smoke.txt` | 10/10 | 10 HTTP 200; model exact; `tool_calls` |
| `/v1/chat/completions` | `claude-smoke.txt` | 10/10 | 10 HTTP 200; model exact; `tool_calls` |
| `/v1/chat/completions` | `zebra-smoke.txt` | 10/10 | 10 HTTP 200; model exact; `tool_calls` |

Responses usage ranged from 581-582 input tokens, 223-497 output
tokens, and 804-1,078 total tokens. Chat Completions ranged from
581-582 prompt tokens, 213-535 completion tokens, and 794-1,117 total
tokens. Every raw response identifier and full usage object is retained
in the evidence.

## Representative redacted specimens

The successful Responses request for `muse-smoke.txt` had this shape:

```json
{
  "model": "muse-spark-1.1",
  "temperature": 0,
  "instructions": "Preserve every filename literally and exactly as supplied by the user. When asked to use a tool, call it once with the exact requested arguments.",
  "input": "Call write_file with path muse-smoke.txt and content factory.",
  "tools": [{
    "type": "function",
    "name": "write_file",
    "description": "Write exact content to the exact path provided.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string"},
        "content": {"type": "string"}
      },
      "required": ["path", "content"],
      "additionalProperties": false
    },
    "strict": true
  }],
  "tool_choice": "auto"
}
```

Representative raw result, condensed without changing the returned
function name or argument string:

```json
{
  "id": "resp_6a5a6b227e5de671412c45fe",
  "model": "muse-spark-1.1",
  "status": "completed",
  "output": [{
    "type": "function_call",
    "name": "write_file",
    "arguments": "{\"path\": \"muse-smoke.txt\", \"content\": \"factory\"}"
  }],
  "usage": {
    "input_tokens": 581,
    "output_tokens": 278,
    "total_tokens": 859
  }
}
```

The equivalent Chat Completions specimen returned response identifier
`chatcmpl-e403fee7-de09-494d-80e3-b580428ffa6a`, finish reason
`tool_calls`, and the same raw function name and argument string. Its
usage was 581 prompt, 245 completion, and 826 total tokens.

The complete credential-free artifacts are
[`2026-07-17-muse-spark-raw-tool-probe-evidence.jsonl`](2026-07-17-muse-spark-raw-tool-probe-evidence.jsonl)
and its
[`parsed summary`](2026-07-17-muse-spark-raw-tool-probe-evidence-summary.json).
The raw artifact contains 82 request/response records: two rejected
named-choice controls and 80 accepted matrix trials. It contains no
request headers, bearer value, or API key.

## OpenCode envelope comparison

A local capture-only proxy recorded OpenCode 1.18.3 request bodies but
no headers, used a dummy non-credential key, did not forward the
OpenCode run, and therefore could not receive or execute a tool call.
The build request preserved the user text and `muse-smoke.txt` exactly.
It also contained zero case-insensitive occurrences of `Claude` or
`Anthropic`.

| Field | Minimal raw control | OpenCode build request |
| :-- | :-- | :-- |
| API path | `/v1/responses` | `/v1/responses` |
| Stream | omitted/false | `true` |
| Temperature | `0` | omitted |
| Tool choice | `auto` | `auto` |
| Tools | one: `write_file` | ten: `bash`, `edit`, `glob`, `grep`, `read`, `skill`, `task`, `todowrite`, `webfetch`, `write` |
| System context | 150 characters | 9,393 characters; identifies OpenCode and Muse Spark |
| User filename sent | exact | exact |

One captured OpenCode build body was then replayed directly to Meta
without OpenCode. Meta returned HTTP 200, response
`resp_6a5a6bf492ff2efde00a4bef`, model `muse-spark-1.1`, and a first call
to `bash` with `{"command": "pwd && ls -la"}`. The call was not
executed, so this replay did not reach the later write turn where the
historical substitution appeared. The redacted request and raw SSE
response are retained in
[`2026-07-17-muse-spark-opencode-envelope-replay.json`](2026-07-17-muse-spark-opencode-envelope-replay.json).

The comparison rules out OpenCode changing the filename in the initial
user message. It does not rule out the richer prompt or tool-loop state
causing Muse to emit the wrong argument later, nor an adapter or tool
executor changing a later correct argument.

## Updated attribution and limitations

The proven boundary is now:

| Boundary | Evidence |
| :-- | :-- |
| Minimal raw Meta tool response | exact path, 80/80 overall and 20/20 for `muse-smoke.txt` |
| Initial OpenCode request body | exact user filename |
| OpenCode and OpenHands completed tool loops | wrong `claude-smoke.txt`, 13/13 historical runs |
| Exact later turn where the argument changes | not yet captured |

The leading attribution shifts from an unconditional Muse/Meta defect
to a **harness-context or later-loop defect**. That phrase deliberately
does not choose among model behavior induced by the harness prompt,
adapter serialization/parsing, or execution. Cross-harness
reproduction makes an OpenCode-only implementation bug less likely,
but two harnesses do not justify "any agent loop," and one failed
identity prompt does not justify "not promptable away."

This probe covers one synthetic function, English instructions, and
one API/model version on one date. Temperature zero reduced sampling
variance but does not make a generative model mathematically
deterministic. No comparison model was run: Meta's injected credential
exposed only `muse-spark-1.1`, while a cross-vendor comparison would not
isolate Meta's serving path. The four filename controls and both native
endpoint shapes provide the relevant within-model control.

The next isolating experiment is to capture the raw Meta response on
the precise later OpenCode or OpenHands turn that requests the write,
then compare its argument byte-for-byte with the adapter's parsed call
and executor input. A safe alternative is a direct multi-turn replay
with synthetic tool outputs, so no returned command is executed.

## Patchyard Factory operational conclusion

Muse Spark 1.1 should **not occupy an implementation seat under either
currently tested harness**. The end-to-end OpenCode and OpenHands probe
still fails the exact-target-file floor, regardless of which later
component is responsible. The raw 80/80 result restores Muse as a
candidate for a future harness configuration, but it is a necessary
control rather than an implementation-seat admission. The actual
model × harness × adapter version must pass this exact-filename probe,
then the full fixture gauntlet and shadow mode.

Simple raw-text success still supports only the narrower judgment-seat
case previously tested. This stronger raw tool-call success shows that
Meta's minimal tool path can preserve exact filenames; it does not make
a failing implementation loop safe.
