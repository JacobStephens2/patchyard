# xAI prompt caching: automatic, undisableable, and reported as `cached_tokens`

*Read 2026-08-26. Answers open question 2 of
[`2026-08-24-openai-xai-token-rates.md`](2026-08-24-openai-xai-token-rates.md), raised as
[#307](https://github.com/JacobStephens2/patchyard/issues/307) out of
[#304](https://github.com/JacobStephens2/patchyard/issues/304). Fact-finding
only. No authority (research/README.md convention 4) - A154 clause (5) stays A154's to
revisit.*

## Summary

The gap #304 recorded is closed. xAI **does** document caching mechanics; the earlier
record missed them because they live under `advanced-api-usage/`, not under pricing or the
model page, neither of which links to them. Five answers, all from xAI's own documentation
except where marked:

| # | Question | Answer | Evidence class |
| :-- | :-- | :-- | :-- |
| 1 | Automatic? | **Yes**, stated in bold by xAI | Official docs |
| 2 | Token threshold? | **None published.** xAI documents no minimum anywhere | Official docs are *silent* |
| 3 | Disableable at the API? | **No.** No parameter, header, or account setting exists to turn it off | Official docs (absence across the full REST reference) |
| 4 | Can Grok Build reach a control? | **No such control exists to reach**, and Grok Build is built to *maximize* hits | Official docs + Apache-2.0 source |
| 5 | Usage field? | `usage.prompt_tokens_details.cached_tokens` (Chat Completions), `usage.input_tokens_details.cached_tokens` (Responses), `usage.cached_prompt_text_tokens` (gRPC SDK) | Official docs |

**Consequence for the `dispute_arbitration` seat: A154 clause (5) fires.** It fires for the
same structural reason it fires on the implement seat, but on stronger evidence - the
OpenAI finding rested partly on an open bug report, while this one is documented behaviour
plus first-party source. Detail in the last section.

One genuine difference from OpenAI is worth carrying forward: **xAI publishes no
cache-write token category and no cache-write price.** The pricing page has three columns -
input, cached input, output - and the caching docs' own billing table lists four token
types with no write bucket. So the "fourth finding" of the 2026-08-24 record (writes are a
separately billed category no seat table prices) is an OpenAI/Anthropic property, not an
xAI one.

## 1. Caching is automatic

xAI states it in bold, in a callout on the section landing page:

> "The xAI API performs prompt caching **automatically**. However, we recommend setting the
> `x-grok-conv-id` HTTP header to maximize your cache hit rate."

and in the opening line of the same page:

> "When consecutive requests share the same starting messages, the xAI API automatically
> caches them. On the next request, messages at the beginning that match exactly are served
> from cache."

- [Prompt Caching](https://docs.x.ai/developers/advanced-api-usage/prompt-caching), read 2026-08-26.

The mechanism is prefix matching from the start of the messages array, the same shape as
OpenAI's:

> "The cache works from the **start of your messages array**. When a request arrives, the
> system checks how many messages at the beginning match a previous request exactly - that
> matching portion is the 'prefix' and gets served from cache"

- [How It Works](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/how-it-works), read 2026-08-26.

Automatic is not the same as guaranteed, and xAI is explicit that a hit is best-effort:

> "Prompt caching is not 100% guaranteed. Cache entries can be evicted due to memory
> pressure, and requests may be routed to different servers."

- How It Works, read 2026-08-26.

Coverage is all-models, which includes the seat's `grok-4.5`:

> "Prompt caching is available on all `grok` language models."

- [Best Practices & FAQ](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/best-practices), read 2026-08-26.

## 2. No published token threshold

**xAI documents no minimum prompt size for caching to engage.** All five caching pages, the
pricing page, and the `grok-4.5` model page were read; none names a floor. The worked
example in the docs caches a 3-message prefix, and the multi-turn walkthrough shows
`cached_tokens=50` on turn 2 from a 50-token turn-1 prompt:

> ```text
> Turn 1: prompt_tokens=50,  cached_tokens=0    # First request, cache established
> Turn 2: prompt_tokens=120, cached_tokens=50   # Previous 50 tokens cached
> Turn 3: prompt_tokens=200, cached_tokens=120  # Previous 120 tokens cached
> ```

- [Usage & Pricing](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing), read 2026-08-26.

State the evidence class plainly: **that example is illustrative, not a specification.** It
shows a 50-token prefix being cached, which is inconsistent with a floor anywhere near
OpenAI's 1,024 tokens, but it does not *establish* that no floor exists. The honest reading
is that xAI is silent and its own example implies any floor is small. Either way the
distinction is inert for this seat: an agentic harness prompt is orders of magnitude above
any plausible floor, so no threshold reachable by this evidence would spare the seat.

Contrast with OpenAI, which publishes its floor outright ("caching is enabled automatically
for prompts that are 1,024 tokens or longer"). Absence of an xAI floor is absence of
evidence.

## 3. There is no way to disable it

**No parameter, no header, no account setting.** This is a negative claim, so here is what
was checked rather than an assertion:

- The five prompt-caching pages document exactly two caching controls, and both *increase*
  hit rate rather than suppress it: the `x-grok-conv-id` header (Chat Completions, gRPC
  metadata) and the `prompt_cache_key` body field (Responses API). Neither has an "off"
  value; the docs describe them identically as *"routes requests to the same server for
  cache reuse."* - [Maximizing Cache Hits](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/maximizing-cache-hits), read 2026-08-26.
- The full REST reference for the inference chat endpoint documents `prompt_cache_key` as
  *"A stable cache key for best-effort sticky routing / prompt-cache hits"* and, across
  every request schema on the page (Chat Completions, Responses, streaming variants),
  contains **no other cache-related request field** - no boolean, no mode, no breakpoint,
  no opt-out. - [REST API Reference - Chat](https://docs.x.ai/developers/rest-api-reference/inference/chat), read 2026-08-26.
- The caching FAQ answers the nearest question that was asked, and its answer is not a
  disable:

  > "**Can I force a cache miss?** Yes - use a different `x-grok-conv-id` or omit the header
  > entirely. This will route your request to a potentially different server where no cache
  > exists for your prompt."
  >
  > - Best Practices & FAQ, read 2026-08-26.

  Read that carefully before treating it as an opt-out. It is a *routing* trick, and xAI
  words the outcome as *"a potentially different server"*. It cannot drive `cached_tokens`
  to zero deterministically: land on the same server and the prefix still hits. It is the
  opposite of a guarantee, and a fail-closed supervisor gate needs a guarantee.

This is a materially weaker position than OpenAI's, where
`prompt_cache_options.mode = "explicit"` with no breakpoints is documented to produce no
caching at all. **On xAI, no such lever is published to exist at any layer.**

## 4. Grok Build cannot reach a control, and is engineered to maximize cache hits

Grok Build is Apache-2.0 and public at
[xai-org/grok-build](https://github.com/xai-org/grok-build), so this question is answerable
from first-party source rather than inference. Cloned at `main`, read 2026-08-26.

**There is no configuration knob.** `crates/codegen/xai-grok-pager/docs/user-guide/26-config-reference.md`
- the full `config.toml` key reference - contains one occurrence of the string "cach", and
it is about `requirements.toml` being a signed cache. No caching key exists. A repo-wide
search for `no_cache` / `disable_cache` / `cache_disabled` / `NO_CACHE` returns only
scrollback, subagent-catalog, markdown-bench, auth-token and update-version matches - none
about prompt caching.

**The conversation id is always sent, and is the session id.** The header is applied
unconditionally on every request:

```rust
// crates/codegen/xai-grok-sampler/src/client.rs
let mut b = builder
    .header("x-grok-conv-id", self.conv_id)
```

and the main agent turn passes the session id as that conv id, unchanged for the life of
the session:

```rust
// crates/codegen/xai-grok-shell/src/session/acp_session_impl/turn.rs:2295
let request = self.chat_state_handle.build_request(
    effective_tools, memory_reminder, self.memory.is_enabled(), /* trace */ …,
    self.session_info.id.to_string(),   // ← conv_id
    req_id.to_owned(),
)
```

That is precisely the "stable conversation ID" xAI's best-practices page asks for. The FAQ's
only miss-forcing technique - vary or omit `x-grok-conv-id` - is therefore not merely
unexposed to the operator, it is actively defeated by the harness's own design.

**The harness treats cache hits as a correctness goal.** The side-call path exists to keep
auxiliary model calls on the parent's cached prefix, and the source comments say so:

```rust
// crates/codegen/xai-grok-shell/src/session/acp_session_impl/side_call.rs
/// Request skeleton for an auxiliary call that replays the parent conversation
/// under the parent's `prompt_cache_key`.
…
// Effort changes the prompt ahead of the conversation history, so dropping it here
// would share no prefix with the main turn.
reasoning_effort: call.reasoning_effort,
x_grok_conv_id: Some(conv_id),
…
prompt_cache_key: Some(session_id),
```

with the recap path documented as preserving reasoning content *"so their conversation
prefix stays byte-identical to the parent turn."* A harness that goes to this length to keep
prefixes byte-identical is not one that can be talked out of caching by configuration.

**Grok Build does report cached tokens to a supervisor.** Headless mode's result JSON
carries the bucket explicitly, which is the field a supervisor-side gate would actually read:

```json
"usage": {
  "input_tokens": 7210,
  "cache_read_input_tokens": 41000,
  "cache_creation_input_tokens": 0,
  "output_tokens": 1893,
  "reasoning_tokens": 412,
  "total_tokens": 50103
}
```

with the documented policy that *"`usage.input_tokens` and `modelUsage.*.inputTokens` are
**uncached only**"*, `cache_read_input_tokens` is the hit bucket, and
`total_tokens = input_tokens + cache_read_input_tokens + cache_creation_input_tokens + output_tokens`.
- `crates/codegen/xai-grok-pager/docs/user-guide/14-headless-mode.md`, read 2026-08-26.

Two cautions on that shape, both load-bearing for anyone wiring a gate to it:

1. The names are **Anthropic-shaped, not xAI-shaped**. Grok Build supports non-xAI backends,
   and `cache_creation_input_tokens` is a Messages-API bucket. xAI's own API has no
   cache-write category and publishes no write price, so on an xAI-backed seat that field
   should read `0`. A gate that keys on it will be keying on a field the provider never
   populates.
2. The doc warns that ACP `_meta.usage.inputTokens` is the **full** prompt sum while only
   the headless projector subtracts cache - *"Prefer headless fields for spend automation."*
   A supervisor reading the ACP field instead would see cache reads folded silently into
   input and never observe a non-zero cached count at all.

## 5. The usage field, by surface

| API surface | Path to cached tokens |
| :-- | :-- |
| Chat Completions | `usage.prompt_tokens_details.cached_tokens` |
| Responses | `usage.input_tokens_details.cached_tokens` |
| gRPC (Python `xai_sdk`) | `response.usage.cached_prompt_text_tokens` |
| Grok Build headless result JSON | `usage.cache_read_input_tokens` / `modelUsage.<model>.cacheReadInputTokens` |

The first two are given as literal response bodies on
[Usage & Pricing](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing);
the third appears in the gRPC example on
[Maximizing Cache Hits](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/maximizing-cache-hits);
the fourth in Grok Build's headless-mode guide. All read 2026-08-26.

xAI also publishes the interpretation table, which is exactly the predicate A154 clause (5)
would evaluate:

| `cached_tokens` | xAI's stated meaning |
| :-- | :-- |
| `0` | Cache miss - *"expected on the first request or after cache eviction"* |
| `> 0` | Cache hit |
| `== prompt_tokens` | Full cache hit, *"rare"* |

Note `prompt_tokens_details.text_tokens` is documented as *"Total text prompt token used
(cached + non-cached text tokens)"* - i.e. `cached_tokens` is a **subset** of the prompt
count, not an additional bucket beside it. Billing follows: cached tokens bill at the cached
rate, the remainder at full input rate.

## Bonus: cached tokens count toward the long-context threshold

Not asked, and it settles open question 4 of the 2026-08-24 record for xAI:

> "Long context pricing applies when total prompt tokens (**including cached tokens**)
> exceed the model's long context threshold. Both cached and non-cached tokens use their
> respective long-context rates in this case."

- Usage & Pricing, read 2026-08-26 (emphasis in the original is absent; the parenthetical is
  verbatim).

So a long Grok Build session whose prompt is mostly cache reads still crosses into the
`>= 200k` tier at $4.00 / $0.60 / $12.00. The OpenAI half of that open question remains
unanswered.

## What this means for A154 clause (5) on the `dispute_arbitration` seat

Stated plainly, because the ticket asked for a prediction rather than a hedge:

**A154 clause (5) will fire on this seat, on its second model call and every one after.**
The chain is short and every link is sourced above:

1. Caching is automatic and needs no opt-in (§1).
2. No threshold is published that an agentic prompt could sit below (§2).
3. No control exists at the API to switch it off - the nearest published technique is
   best-effort routing, not suppression (§3).
4. The harness sends a stable `x-grok-conv-id` on every request and is engineered to keep
   prefixes byte-identical, which is the configuration that maximises hits (§4).
5. `cached_tokens` is non-zero exactly when a prefix hit occurs, and the harness surfaces it
   (§5).

The one qualification, and it is a real one: xAI does not guarantee hits. Eviction and
routing mean an individual request can legitimately report `cached_tokens = 0`. **That makes
the failure non-deterministic, which is worse operationally than a certain one** - the seat
would pass intermittently and fail on the runs where the cache happened to work, which is a
flake that looks like a bug in whatever the arbiter was doing.

Comparison to the implement seat, since #304 established that baseline: the *conclusion* is
the same, but the *evidence* is stronger here. On OpenAI, the load-bearing claim was
"Codex cannot emit `prompt_cache_breakpoint`", sourced to an open bug report - a defect that
could be fixed. On xAI there is no control to be unable to reach: the provider publishes no
opt-out at all, so this is not a harness gap awaiting an upstream fix. Refusing cached tokens
on this seat cannot be repaired by a Grok Build release.

And as with OpenAI, the refusal is not forced by missing pricing. The cached read has a
published rate - $0.30 / M below 200k prompt tokens, $0.60 / M at or above
([pricing](https://docs.x.ai/developers/pricing), corroborated on the
[grok-4.5 model page](https://docs.x.ai/docs/models/grok-4.5), both read 2026-08-26,
unchanged from the 2026-08-24 reading). Pricing a cached token on this seat is arithmetic,
not guesswork.

## Sources

All read 2026-08-26. Provider-owned pages and first-party source only.

- xAI, [Prompt Caching](https://docs.x.ai/developers/advanced-api-usage/prompt-caching)
- xAI, [Prompt Caching - How It Works](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/how-it-works)
- xAI, [Prompt Caching - Maximizing Cache Hits](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/maximizing-cache-hits)
- xAI, [Prompt Caching - What Breaks Caching](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/multi-turn)
- xAI, [Prompt Caching - Usage & Pricing](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing)
- xAI, [Prompt Caching - Best Practices & FAQ](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/best-practices)
- xAI, [REST API Reference - Inference / Chat](https://docs.x.ai/developers/rest-api-reference/inference/chat)
- xAI, [API pricing](https://docs.x.ai/developers/pricing)
- xAI, [Grok 4.5 model page](https://docs.x.ai/docs/models/grok-4.5)
- xai-org/grok-build (Apache-2.0), `main` @ 2026-08-26 - `crates/codegen/xai-grok-sampler/src/client.rs`, `crates/codegen/xai-chat-state/src/actor/request_builder.rs`, `crates/codegen/xai-grok-shell/src/session/acp_session_impl/turn.rs`, `crates/codegen/xai-grok-shell/src/session/acp_session_impl/side_call.rs`, `crates/codegen/xai-grok-pager/docs/user-guide/14-headless-mode.md`, `crates/codegen/xai-grok-pager/docs/user-guide/26-config-reference.md`
- OpenAI, [Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching) (cited only as the contrast case for the published 1,024-token floor and the documented opt-out)
