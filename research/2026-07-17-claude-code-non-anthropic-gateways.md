# Running non-Anthropic models through Claude Code at Patchyard

Patchyard already has the necessary gateway infrastructure.

## Findings

- The preview environment runs LiteLLM v1.87.0 at `10.132.0.7:4000`. It
  has been healthy for 11 days and is configured in
  [`preview-fieldbooks/litellm/config.yaml`](../../preview-fieldbooks/litellm/config.yaml).
  It exposes GPT, Claude, Gemini, GLM and Grok aliases.
- Tribunal runs a second LiteLLM v1.87.0 deployment with PostgreSQL spend
  logging and OpenTelemetry.
- Claude Code 2.1.212 successfully ran through the preview LiteLLM gateway
  using `glm-frontier`:
  - A plain response succeeded.
  - A real `Write` tool call succeeded and produced the exact requested
    10-byte file.
  - The combined test cost was approximately $0.0047.
- Therefore, the statement that Claude Code with GLM needs a name-translating
  proxy in
  [`2026-07-17-harness-smoke-test.md`](2026-07-17-harness-smoke-test.md)
  is correct, but its "not runnable" status is now stale because Patchyard already
  has that proxy.
- `OPENROUTER_API_KEY` was not available in the process that performed this
  investigation because `env.tpl` changed after it started. It will resolve
  the next time `claude-orchestrator` launches.

## Correction to the supplied vendor assessment

OpenRouter now supports Claude Code directly through its Anthropic-compatible
endpoint. LiteLLM is not required for that path. OpenRouter documents
`ANTHROPIC_BASE_URL=https://openrouter.ai/api`, while warning that
non-Anthropic models are not guaranteed to behave correctly in Claude Code.

Source: [OpenRouter Claude Code documentation](https://openrouter.ai/docs/cookbook/coding-agents/claude-code-integration).

## Recommendation for manual model experiments

Use an isolated launcher:

```bash
CLAUDE_CONFIG_DIR="$HOME/.claude-openrouter" \
ANTHROPIC_BASE_URL="https://openrouter.ai/api" \
ANTHROPIC_AUTH_TOKEN="$OPENROUTER_API_KEY" \
ANTHROPIC_API_KEY="" \
claude --model "<openrouter-model-id>"
```

The separate `CLAUDE_CONFIG_DIR` avoids logging out of or disturbing the
normal Claude Max configuration.

## Recommendation for the software factory

LiteLLM is preferable for controlled factory execution:

- Extend Tribunal's logged gateway rather than using the preview gateway.
- Add OpenRouter only as an optional upstream; retain direct-provider routes
  for established seats.
- Give each factory run a short-lived virtual key restricted by model and
  spend.
- Never put the preview or Tribunal master key inside the worker.
- Expose only the gateway endpoint to the isolated worker.

This aligns with the factory's credential-free, model-endpoint-only worker
design. LiteLLM officially supports translating Claude Code's Anthropic
Messages requests to non-Anthropic providers and supports virtual-key model
restrictions.

Source: [LiteLLM Claude Code guide](https://docs.litellm.ai/docs/tutorials/claude_non_anthropic_models).

Anthropic explicitly does not support non-Claude models through gateways, so
each model and Claude Code version must still pass the factory harness and
tool-use gauntlet.

Source: [Claude Code gateway documentation](https://code.claude.com/docs/en/llm-gateway).
