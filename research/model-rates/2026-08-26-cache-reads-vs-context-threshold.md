# Do cache-read tokens count toward the long-context repricing threshold?

*Read 2026-08-26. Answers open question 4 of
[`2026-08-24-openai-xai-token-rates.md`](2026-08-24-openai-xai-token-rates.md), raised as
[#309](https://github.com/JacobStephens2/patchyard/issues/309) out of
[#304](https://github.com/JacobStephens2/patchyard/issues/304).
Fact-finding only. No authority (research/README.md convention 4).*

## Summary

**xAI: yes, and it is published.** **OpenAI: unpublished; the natural reading is yes, and
that reading is not a finding.**

| Provider | Answer | Evidence class |
| :-- | :-- | :-- |
| xAI (`grok-4.5`) | Cache reads **count** toward the 200k prompt-token threshold | **Finding** - stated in xAI's own caching docs in those words |
| OpenAI (`gpt-5.6-sol`) | Cache reads **most likely count** toward the >272K input-token threshold | **Inference** - no OpenAI page states it either way; built from two OpenAI facts plus one step of reading |

The asymmetry matters more than the answers agree. On xAI the question is settled and can
be encoded. On OpenAI the *same* structure is undocumented, and the seat it decides money
for - `implement`, the highest-spend seat - is the one whose input is mostly cache reads.
It is a factor of two, resting on inference. Section 3 gives the cheapest way to convert
that inference into a measurement.

## 1. xAI - finding

**Primary source, verbatim.** xAI, [Prompt Caching - Usage & Pricing](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing)
([`.md`](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing.md)),
read 2026-08-26, in a callout under the Pricing heading:

> Long context pricing applies when total prompt tokens (including cached tokens) exceed
> the model's long context threshold. Both cached and non-cached tokens use their
> respective long-context rates in this case.

That is the question asked, answered in the parenthesis. Nothing further is needed for xAI.

Three corroborating facts from the same provider, all read 2026-08-26, that make the
statement consistent rather than an outlier:

- The tier is measured against the **prompt**, not against the uncached remainder:
  *"Requests whose prompt reaches 200k tokens are billed at the higher rate for all tokens
  in the request."* - [Grok 4.5 model page](https://docs.x.ai/developers/models/grok-4.5).
  The [pricing page](https://docs.x.ai/developers/pricing) carries the same sentence in
  general form: *"Models listed with two rows use long context pricing: requests whose
  prompt reaches the listed token threshold are billed at the higher rate for all tokens in
  the request."*
- **Cached tokens are prompt tokens by xAI's own definition**, not a parallel category:
  *"**Cached prompt tokens**: Prompt tokens that were served from cache rather than
  recomputed"* - [pricing page](https://docs.x.ai/developers/pricing), Token Costs.
- **The usage object confirms the subset relation numerically.** The documented Chat
  Completions response shows `"prompt_tokens": 125` with
  `"prompt_tokens_details": { "cached_tokens": 98 }`, and the verification table states
  that `cached_tokens` *"Equal to `prompt_tokens`"* means *"**Full cache hit** - your entire
  prompt was served from cache"* -
  [Usage & Pricing](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing).
  `cached_tokens` is a component of `prompt_tokens`, never additional to it.

**One near-miss to not misread.** The xAI pricing page also says *"The 2x multiplier
applies to all token types - input, output, cached, and reasoning. Prompt caching discounts
are applied before the multiplier."* That sentence is under **Priority Processing**, and
its 2x is the priority premium, not the long-context tier. It is easy to cite as if it
answered this question. It does not. The long-context answer is the callout quoted at the
top of this section.

## 2. OpenAI - inference, not finding

**No OpenAI page found states whether cache reads count toward the >272K threshold.** The
pages checked, all read 2026-08-26, all fetched as first-party markdown where OpenAI
publishes it (`.md` suffix per the docs site's own convention):

| Page | What it says about the threshold | Cached tokens mentioned in that context? |
| :-- | :-- | :-- |
| [GPT-5.6 Sol model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol) | *"Prompts with >272K input tokens are priced at 2x input and 1.5x output for the full request."* | No |
| [API pricing](https://developers.openai.com/api/docs/pricing) | Tier columns only: `Short context input / Short context cached input / Short context cache writes / Short context output / Long context ...`. Older rows labelled `gpt-5.5 (<272K context length)`. No prose defining either tier. | Priced, never defined |
| [Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching) | **Silent.** No occurrence of "272", "long context", "context length" or "threshold" in the tiering sense anywhere in the 37KB page. | n/a |
| [GPT-5.4 model page](https://developers.openai.com/api/docs/models/gpt-5.4) | Same sentence, worded *"for the full session"*, plus a **rate-limit** bucket headed `### Long Context` defined as `> 272K input tokens` | No |
| [Rate limits guide](https://developers.openai.com/api/docs/guides/rate-limits) | *"For long context models like GPT-5.5, there is a separate rate limit for long context requests."* No token accounting given. | No |
| [Prompt Caching 201 cookbook](https://developers.openai.com/cookbook/examples/prompt_caching_201) | Caching economics only; no context tier | n/a |
| [Community forum, "Pricing by Context: Does Context (Short/Long context) include complete tokens"](https://community.openai.com/t/pricing-by-context-does-context-short-long-context-includes-complete-tokens/1381331) | Establishes the tier is measured on **input tokens only**, not input+output. The one reply is from a community member (`_j`), **not OpenAI staff**, and does not address caching. | No |

No official changelog entry or staff forum answer on the point was found. Aggregator and
blog write-ups do assert an answer; none cite an OpenAI page for it, and per #304 no
aggregator is cited here for anything.

### The inference, stated as a chain

Two OpenAI-published facts, then one step of reading:

1. **The threshold is measured against "input tokens."** Model page, verbatim above.
2. **`usage.input_tokens` includes cache reads and cache writes** - OpenAI's own
   cost-calculation code in the
   [prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
   (read 2026-08-26) subtracts them out to get the ordinary remainder:

   ```python
   input_tokens = usage.input_tokens
   cached_tokens = usage.input_tokens_details.cached_tokens
   cache_write_tokens = usage.input_tokens_details.cache_write_tokens
   ordinary_input_tokens = input_tokens - cached_tokens - cache_write_tokens
   ```

   Subtraction is only meaningful if `cached_tokens` is a component of `input_tokens`. The
   same page's monitoring advice - *"Track the token cache-hit rate by dividing total
   cached tokens by total input tokens"* - is a ratio, which is only coherent on the same
   footing.
3. **Therefore** the only quantity OpenAI publishes under the name "input tokens" is the
   one that includes cache reads, and a threshold phrased against "input tokens" most
   naturally reads against that quantity. **This is inference. OpenAI does not say it.**

### What does *not* support the inference, though it looks like it does

The pricing page carries a distinct `Long context cached input` rate ($0.80/M for
`gpt-5.6-sol`, exactly 2x the $0.40/M short-context cached rate). It is tempting to read
that column as proof. It is not: a request can be in the long-context tier on its uncached
tokens alone and still contain cache reads, which is enough to give that column a job. It
proves cache reads get repriced *once a request is in the tier*; it says nothing about what
put the request in the tier. Recorded here so the argument is not re-made from it later.

Likewise, xAI publishing the inclusive rule is evidence about xAI. Two providers converging
on a design is a reason to expect the same design, not a reason to report it as OpenAI's.

### If the inference is wrong

Worth stating the alternative plainly, because it is not absurd. If OpenAI measured the
tier against *uncached* input only, a long stable-prefix Codex session would sit in the
short tier almost permanently: `implement`'s prompt grows past 272K while the per-turn
uncached delta stays in the low thousands. That is a materially cheaper world, and it is
the world an optimistic rate table would silently assume. Under the inference above, the
same session crosses into 2x on every turn once the prompt passes 272K - including the
$0.40 -> $0.80 doubling on the cache reads that make up most of it. **The two readings
differ by roughly a factor of two on the highest-spend seat, and nothing published
distinguishes them.**

## 3. Cheapest way to settle OpenAI

Not by asking; by measuring. A deliberately designed pair of billed requests answers it for
a few cents, and the design matters more than the spend.

**Shape of the probe.** Two requests, same stable prefix of roughly 280,000 tokens - just
over the 272K threshold - sent with the same `prompt_cache_key` so both land on the same
engine (the cookbook reports hit rates going 60% -> 87% with the key set):

- **Request A** primes the cache. Expect `cached_tokens` near 0, `input_tokens` ~280K. It
  is in the long tier under either reading, so it discriminates nothing - it exists to
  create the cache entry.
- **Request B** repeats the same prefix plus a few hundred new tokens. Expect
  `cached_tokens` ~280K, ordinary input in the low hundreds. **This is the discriminating
  request.** If cache reads count, B bills its cached tokens at the long-context cached
  rate; if they do not, B is a sub-272K request and bills at the short-context cached rate.
  For `gpt-5.6-sol` that is $0.80/M vs $0.40/M on ~280K tokens - about $0.22 vs $0.11, a
  difference large enough to read cleanly off the billing line and too small to matter.

**Run it on the cheapest model in the family that carries the same two-tier structure**,
not on `gpt-5.6-sol`. The pricing page gives `gpt-5.6-luna` short/long columns of
$0.20/$0.40 input and $0.02/$0.04 cached, so the same 280K probe costs single-digit cents.
**Caveat that must be recorded with the result:** OpenAI publishes the threshold per model,
not as a family-wide billing rule, so a result measured on `luna` is evidence about `luna`.
It is strong evidence about the mechanism and weak evidence about `sol`. If the answer is
going to be load-bearing for the implement seat's rate table, re-run the discriminating
request once on `sol` - about $0.22 - and cite that.

**Record, per request:** exact model id and snapshot, UTC timestamp, request id, the
complete `usage` object including `input_tokens_details.cached_tokens` and
`cache_write_tokens`, the `prompt_cache_key` used, and - the part that actually settles it
- the matching line from the organization costs/usage endpoint for that request, since the
usage object reports tokens and only the billing line reports the rate applied. A token
count alone cannot answer a pricing question.

**Two ways the probe fails silently**, both worth pre-empting: if `cached_tokens` on
request B comes back well below the prefix size, the cache was evicted or the request was
routed elsewhere and B is not the request you designed - re-run rather than interpret it.
And if B's ordinary input is large enough to reach 272K by itself, B is in the long tier
under both readings and discriminates nothing; keep the new suffix small.

Do not attempt this as a side effect of a real seat run. The reason the question is open is
that reported usage on a normal Codex turn is consistent with both readings; only a request
built to separate them separates them.

## Bearing on the open questions

- Open question 4 of the 2026-08-24 record is **closed for xAI** and **still open for
  OpenAI**, now with a bounded price to close it.
- The finding sharpens, and does not change, that record's conclusion that a rate is not
  two integers. On xAI the tier's input is now known to be `prompt_tokens` inclusive of
  `cached_tokens`, so a table can compute the tier from reported usage without guessing.
  On OpenAI a table that computes the tier from `usage.input_tokens` is making the
  inference in section 2 - which is defensible, and should be *labelled* in the code as an
  assumption with this file as its reference, not written as though it were sourced.
- Nothing here bears on Anthropic, which publishes no context tier at all.

## Sources

All read 2026-08-26. Provider-owned pages only, plus one community thread cited explicitly
as non-staff. OpenAI pages fetched as `.md` where the docs site publishes that form.

- xAI, [Prompt Caching - Usage & Pricing](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing) - **the load-bearing xAI source**
- xAI, [Prompt Caching - How It Works](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/how-it-works)
- xAI, [API pricing](https://docs.x.ai/developers/pricing)
- xAI, [Grok 4.5 model page](https://docs.x.ai/developers/models/grok-4.5)
- OpenAI, [GPT-5.6 Sol model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- OpenAI, [GPT-5.4 model page](https://developers.openai.com/api/docs/models/gpt-5.4)
- OpenAI, [API pricing](https://developers.openai.com/api/docs/pricing)
- OpenAI, [Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching) - source of the `input_tokens` subtraction identity
- OpenAI, [Rate limits guide](https://developers.openai.com/api/docs/guides/rate-limits)
- OpenAI, [Prompt Caching 201 cookbook](https://developers.openai.com/cookbook/examples/prompt_caching_201)
- OpenAI Developer Community, [Pricing by Context](https://community.openai.com/t/pricing-by-context-does-context-short-long-context-includes-complete-tokens/1381331) - **non-staff**, cited only for the input-only reading of the tier
