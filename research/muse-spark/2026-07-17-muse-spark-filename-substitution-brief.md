# Research brief: Muse Spark 1.1 rewrites "muse-*" filenames to "claude-*" inside agent harnesses - but not in raw tool calls

*2026-07-17. Self-contained handoff for external research. Everything
needed to understand and reproduce the issue is in this file; no access
to our repositories is required. Safe to share: contains no credentials
or private infrastructure details.*

## One-paragraph summary

Meta's Muse Spark 1.1 (Meta Model API, public preview), when driven as
a coding agent through either the OpenCode or OpenHands harness,
reliably disobeys an exact filename instruction: asked to create
`muse-smoke.txt`, it creates `claude-smoke.txt` instead - 13/13
failures across every agentic configuration we tested, surviving an
explicit corrective system rule. Yet the same model through the same
API, called with a minimal harness-free tool-calling client, preserves
the exact filename 80/80 times at temperature 0. Other models in the
identical harnesses do not exhibit the behavior, and other filenames
are unaffected. The fault is therefore real, reproducible, and
currently **unlocalized**: something in the rich agent-harness context
changes the model's (or the serving stack's) behavior, and we do not
know which ingredient.

## Environment

| Item | Value |
| :-- | :-- |
| Model | `muse-spark-1.1`, Meta Model API public preview (released 2026-07-09) |
| API base | `https://api.meta.ai/v1` - serves OpenAI-compatible `/chat/completions`, native `/responses`, Anthropic-compatible `/messages` |
| Harness 1 | OpenCode 1.18.3 (npm `opencode-ai`), headless `opencode run`, custom provider (no built-in Meta provider exists in models.dev as of this date) |
| Harness 2 | OpenHands 1.11.0 (PyPI `openhands-ai`, V1 SDK, LiteLLM transport, `openai/` generic routing + explicit base URL) |
| Host | Linux x86_64 VM (RHEL 9), US |
| Date of all runs | 2026-07-17 |

## Observed behavior

Probe prompt, identical everywhere:

> Create a file named muse-smoke.txt in the current directory containing
> exactly the word: factory

| Configuration | Requested name | Result |
| :-- | :-- | :-- |
| OpenCode, `@ai-sdk/openai-compatible` wiring (chat completions), xhigh | `muse-smoke.txt` | `claude-smoke.txt` - 4/4 |
| OpenCode, same wiring | `muse-note.txt` | wrote `claude-note.txt` first, then half-corrected (both files left) |
| OpenCode, same wiring | `zebra-note.txt` | correct |
| OpenCode, same wiring | `test-smoke.txt` | correct |
| OpenCode, run from a directory with no "claude" in any path | `muse-smoke.txt` | still `claude-smoke.txt` - path is not the trigger |
| OpenCode, `@ai-sdk/openai` wiring (Responses-capable) | `muse-smoke.txt` | `claude-smoke.txt`; the model's final *prose* also renamed the working directory `muse-test` to "claude-test" |
| OpenCode + explicit rule in `AGENTS.md`: "You are Muse Spark 1.1, a model built by Meta... use names exactly as written" | `muse-smoke.txt` | `claude-smoke.txt` - 2/2; this corrective prompt did not help |
| OpenHands (entirely different harness, prompts, tool stack, transport) | `muse-smoke.txt` | `claude-smoke.txt` - 3/3 |

Total: 0/13 correct in agentic loops for `muse-*` names. Secondary
observation: in the failing runs the model favored raw shell
(`echo`/`printf` redirects) over the harness's structured write tool
and added gratuitous verification commands (`hexdump`, repeated `cat`).

## Controls - all pass

1. **Harness-free raw tool calling: 80/80 exact.** A minimal Python
   stdlib client (no framework) with one strict-schema
   `write_file(path, content)` function, temperature 0, system
   instruction "preserve filenames literally": 40/40 exact on
   `/v1/responses` and 40/40 on `/v1/chat/completions`, covering
   `muse-smoke.txt` (20/20), `meta-smoke.txt`, `claude-smoke.txt`, and
   `zebra-smoke.txt` (10/10 each per endpoint). Every response: HTTP
   200, model id `muse-spark-1.1`, exactly one tool call, exact path.
   (API limitation encountered: `tool_choice` supports only `"auto"`;
   named/`required` choices return HTTP 400.)
2. **Other models, same harnesses, same probe: correct.** GLM 5.2 and
   MiniMax-M3 through the identical OpenCode custom-provider path, and
   Kimi K2.6 through the identical OpenHands SDK path, all pass 3/3.
3. **Non-agentic Q&A**: asked via the raw API which filename it would
   pass to a tool, the model answers `muse-smoke.txt` correctly.

## What this rules out, and what remains

Ruled out: an unconditional model-level rewrite (control 1); a
serving-side rewrite applied to all requests (control 1); a
single-harness parser/executor bug (two independent harnesses fail
identically); working-directory contamination (neutral-path run); a
trivially promptable fix (the AGENTS.md rule failed).

Remaining suspects, undistinguished:

- **Model behavior under rich context** - the long agentic system
  prompt, many tool schemas, or multi-turn shape flips the model into
  substituting an inferred identity token ("claude") for "muse". Both
  harnesses have Claude-Code-influenced prompt lineages, which fits but
  is unproven. The substitution appearing in the model's *prose* (not
  just tool arguments) points at generation rather than parsing.
- **Meta serving-layer behavior conditional on request shape** - e.g.,
  injected system content or post-processing for large/agentic
  requests, not exercised by the minimal client.

A captured byte-exact OpenCode request envelope exists for replay; the
planned bisection (replay the full envelope through the raw client; if
it reproduces, delete envelope ingredients until the trigger falls out)
has not yet been run.

## Reproduction recipe

Requires a Meta Model API key (public preview, US).

```bash
# 1. OpenCode custom provider (opencode.json in an empty directory):
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "meta": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Meta AI",
      "options": {"baseURL": "https://api.meta.ai/v1", "apiKey": "{env:META_AI_API_KEY}"},
      "models": {"muse-spark-1.1": {"name": "Muse Spark 1.1"}}
    }
  }
}

# 2. Failing agentic run (repeatable):
opencode run -m meta/muse-spark-1.1 --variant xhigh --auto \
  "Create a file named muse-smoke.txt in the current directory containing exactly the word: factory"
ls   # -> claude-smoke.txt

# 3. Passing raw control: POST the same request as a single tool-call
#    exchange with one write_file function, temperature 0, to
#    /v1/chat/completions or /v1/responses - the returned arguments
#    contain "muse-smoke.txt".
```

Note: latency through the preview API is highly variable (identical
trivial tasks ranged from ~30 s to over 5 minutes at xhigh).

## Questions for the research council

1. **Prior art**: any public reports of Muse Spark 1.1 (or other
   models) substituting identity-adjacent tokens - names resembling the
   model itself or a rival assistant - in agentic harnesses? Search
   OpenCode/OpenHands/LiteLLM/Vercel-AI-SDK issue trackers, Meta
   developer forums, HN/Reddit/X.
2. **Harness prompt contents**: OpenCode and OpenHands are open
   source. What do their default agent system prompts and tool
   descriptions actually contain that could prime an identity
   substitution ("claude" tokens, Claude-Code-style phrasing, example
   transcripts)? Are there published analyses of their prompt lineage?
3. **Meta serving behavior**: is anything documented or reported about
   the Meta Model API preview injecting system content, applying
   post-processing, or otherwise behaving differently for large or
   tool-heavy requests vs. minimal ones?
4. **Mechanism literature**: published research on context-conditional
   instruction-fidelity degradation - identity confusion or
   self-reference interference in LLMs, especially token substitution
   in tool arguments under long agentic contexts (distillation
   artifacts, "model believes it is X" phenomena).
5. **Mitigations**: techniques others use to harden exact-argument
   fidelity in agent loops (schema constraints, argument echo-back
   verification, post-generation validation) - and specifically whether
   Meta's strict function schemas can be made to reject wrong paths
   given the `tool_choice: "auto"`-only limitation.
6. **Vendor status**: any Meta acknowledgment, changelog, or model
   update since 2026-07-09 that touches agentic tool-calling fidelity.

Deliverable wanted: sources + a judgment on which remaining suspect the
public evidence favors, and any reproduction reports from outside our
environment.

---

*Council response received same day: see
[`2026-07-17-muse-spark-council-response.md`](2026-07-17-muse-spark-council-response.md).
Three-model consensus: distillation-induced identity confusion triggered
by Claude-Code-lineage prompt style; substitution is generation-side;
no outside reproductions or Meta acknowledgment found. Bisection of the
captured envelope remains the decisive local test.*

*Bisection completed later the same day - see
[`2026-07-17-muse-spark-envelope-bisection.md`](2026-07-17-muse-spark-envelope-bisection.md):
stochastic dose-dependent identity-token substitution, no "claude"
token required, `cursor` variant observed, no mitigation reaches zero.*
