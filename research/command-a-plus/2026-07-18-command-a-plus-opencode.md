# Command A+ x OpenCode - text floor passes; image adapter fails

*2026-07-18. Operator: the orchestration agent on the orchestration VM.
This is a pre-gauntlet floor probe and harness-selection record, not seat
admission. The scored unit is the exact model x harness x requested-effort
configuration below.*

## Verdict

Test **OpenCode first**, not Terminus-2. The native OpenCode path passed the
exact-file floor 3/3 and is the closer fit to the factory's existing worker
contract: one process in our isolated worker, explicit tools and permissions,
JSON events, and no second control plane. Advance this pair only through the
**text-only** alphabetize gauntlet for now.

Keep Terminus-2 as a reference harness if a later failure looks specific to
OpenCode. Cohere used Terminus-2 for its Terminal-Bench Hard launch number, but
that establishes benchmark comparability, not production-harness fitness.
Harbor calls Terminus-2 a research-preview reference agent: its single tool is
an interactive tmux session, it is intentionally fully autonomous, and Harbor
recommends it only in a sandbox. Harbor does provide good ATIF trajectories and
reward integration, so observability is not an OpenCode-only advantage.

This ruling does not qualify OpenCode as a security boundary. The factory's
Firecracker-or-rootless-Podman worker boundary, credential allowlist, egress
allowlist, wall-clock cap, deterministic verifier, and patch-only output remain
required.

## Configuration

- Model: `command-a-plus-05-2026`, Cohere's first-party API.
- Harness: OpenCode 1.18.3, native `@ai-sdk/cohere` provider.
- Requested effort: `high` (`--variant high`, catalog budget 16,000 thinking
  tokens).
- Prompt: the canonical muse-smoke exact-file instruction.
- Isolation for this probe: a fresh `/tmp` directory per run, not the future
  factory worker sandbox.
- Provider provenance: Cohere was founded in Toronto and describes itself as
  Canadian. The public SaaS processing location was not pinned by this probe;
  provider allowlisting remains a separate ruling.

Canonical invocation:

```bash
opencode run \
  --title command-a-plus-floor \
  --format json \
  --dir "$RUN_DIR" \
  --model cohere/command-a-plus-05-2026 \
  --variant high \
  --auto \
  'Create a file named muse-smoke.txt in the current directory containing exactly the word: factory'
```

Pin `--title` in automation. Without it OpenCode makes a separate model call to
name the session; one of the three scored runs logged
`INVALID_TOOL_GENERATION` on that auxiliary request even though the main task
completed. An explicit title removes an unnecessary model call and failure
surface.

## Text floor result - PASS 3/3

Every run:

- exited 0;
- used OpenCode's native `write` tool exactly once;
- created `muse-smoke.txt` with the exact seven bytes `factory`;
- completed the two model steps in a 1.34-1.74 second JSON-event span;
- took about 7 seconds for the whole cold OpenCode process.

| Run | Event span | OpenCode output-token telemetry | OpenCode cost estimate |
| :-- | --: | --: | --: |
| 1 | 1.585 s | 301 | $0.038765 |
| 2 | 1.742 s | 321 | $0.038965 |
| 3 | 1.336 s | 257 | $0.038325 |

The cost field is OpenCode's estimate from its model catalog, not a verified
Cohere invoice. Cohere currently documents Command A+ as free for trial and
production keys until the applicable rate limit.

### Effort caveat

OpenCode accepted `--variant high`, and its refreshed catalog maps that variant
to Cohere thinking with a 16,000-token budget. Its JSON events nevertheless
reported `reasoning: 0` on all six task steps. A direct Cohere image control,
without an explicit thinking override, separately reported 376 reasoning
tokens. The most likely explanation is incomplete adapter telemetry, but this
probe did not capture the outbound OpenCode request. Record the configuration
as **high requested, not high verified** until a fixture discriminates the
variants or the request body is captured safely.

## Speed control

Artificial Analysis currently reports 185.3 output tokens/second and 0.40
seconds to first token on Cohere's API. A direct, thinking-disabled Cohere
stream from this VM produced 512 output tokens with:

- 0.155 seconds to first content token;
- 2.442 seconds from first to last content token;
- 209.7 observed output tokens/second;
- 2.599 seconds end to end.

That reproduces the order of magnitude behind Jacob's interest. It does not
predict factory job time: the relevant floor measurement is about 7 seconds
end to end, including OpenCode startup, its roughly 7,100-token agent prompt,
two model turns, and the file tool.

The first identical-class raw streaming attempt returned Cohere HTTP 422
`INVALID_TOOL_GENERATION` despite receiving no tool definitions; the retry
succeeded. Combined with the one failed OpenCode title request, this is a
stability signal to score over n>=10 in the fixture gauntlet, not a reason to
overturn the 3/3 floor.

The launch article's benchmark headline has already aged: it says Command A+
scored 37 on the Artificial Analysis Intelligence Index, while the live model
page now reports 23 under its current index. The speed measurement reproduced
here is interesting; neither intelligence number substitutes for Patchyard's
fixtures.

## Image control - model passes, OpenCode pair fails

The pair must not be marked image-capable yet.

1. Local `opencode run --file <png>` labeled the valid 1.0 MB PNG as
   `text/plain`. Cohere rejected the resulting request as more than 425,000
   tokens over the request size limit. OpenCode's current `run.ts` explicitly
   assigns local non-directory attachments `text/plain` in this path.
2. `opencode serve` plus `opencode run --attach` preserved `image/png` in the
   OpenCode session, but the Cohere adapter still expanded the image into an
   oversized request. Worse, the attached client exited 0 with empty output
   while the server-side session held the API failure.
3. A direct Cohere V2 SDK control sent the same PNG as the documented base64
   `image_url`. Command A+ answered in 2.784 seconds with the exact first four
   visible labels:

   ```json
   ["All", "Zane Quinn", "Piper Nova", "Jasper Bexley"]
   ```

   Cohere reported 2,315 image tokens and 376 reasoning tokens.

The direct control isolates a harness/adapter defect; it does not qualify a
second harness. Retest OpenCode image input after an OpenCode or
`@ai-sdk/cohere` update. Until then this pair is excluded from any factory seat
that reads screenshots.

## Why not Terminus-2 first

The supplied recommendation correctly identified Terminus-2's autonomy but
treated autonomy as the main selection criterion. For Patchyard it is already a
worker invariant, not a differentiator: a factory agent cannot ask a human
mid-run, and the worker is disposable.

The actual differences are architectural:

- Terminus-2 brings Harbor job/task packaging, a controller process, Docker
  environment assumptions, LiteLLM translation, and a tmux-only action loop.
- The factory already owns job state, isolation, caps, verification,
  publication, evidence, and retries. Harbor would overlap that control plane
  rather than fill the model-adapter slot.
- OpenCode exposes native file tools and structured events that map directly
  to the current provenance and patch contract.
- Terminus-2 is still the fair reference when comparing against Cohere's
  Terminal-Bench claim or diagnosing an OpenCode-specific failure.

Do not install Harbor merely to repeat this trivial floor. If the OpenCode pair
passes the text gauntlet but fails a long-horizon terminal fixture, run that one
fixture under Terminus-2 in the same disposable sandbox and record it as a
second model x harness pair.

## Next gate

1. Run the text-only alphabetize fixture gauntlet with an explicit title, hard
   timeout, JSON capture, and `high requested` provenance.
2. Score at least n=10 for completion, invalid-tool-generation errors, exact
   target selection, wall time, and surviving cost.
3. Do not assign a screenshot-reading seat unless the OpenCode image path is
   repaired and passes the sanitized PNG control.
4. Use Terminus-2 only as the named reference rerun described above.

References:

- [Cohere: Command A+ model documentation](https://docs.cohere.com/docs/command-a-plus)
- [Cohere: launch article and Terminal-Bench methodology](https://cohere.com/blog/command-a-plus)
- [Cohere: image input format](https://docs.cohere.com/docs/image-inputs)
- [Artificial Analysis: live Command A+ measurements](https://artificialanalysis.ai/models/command-a-plus)
- [OpenCode: non-interactive `run` CLI](https://opencode.ai/docs/cli/)
- [OpenCode: `run.ts` attachment implementation](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/cli/cmd/run.ts)
- [Harbor: Terminus-2](https://www.harborframework.com/docs/agents/terminus-2)
- [Cohere: company origin](https://cohere.com/about)
