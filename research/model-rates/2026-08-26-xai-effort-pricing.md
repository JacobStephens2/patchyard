# Does xAI price `grok-4.5` by reasoning effort?

*Read 2026-08-26. Closes open question 1 of
[`2026-08-24-openai-xai-token-rates.md`](2026-08-24-openai-xai-token-rates.md), for
[#306](https://github.com/JacobStephens2/patchyard/issues/306). The seat at
issue is `dispute_arbitration`, which `policy/routing.json` runs as
`xai/grok-build/grok-4.5/high`. Fact-finding only; no authority
(research/README.md convention 4).*

## Summary

**No. On every xAI-owned page read, `grok-4.5` carries exactly one published rate table,
and reasoning effort is a request parameter with no price attached to any of its values.**

The evidence class matters and is not the same as OpenAI's. #304 could point at OpenAI's
model page documenting `reasoning.effort` *beside* the price and attaching nothing to it.
xAI's position is now stronger than the silence #304 found, but weaker than a published
denial:

- **Positive, not silent:** xAI *does* document `reasoning_effort` for `grok-4.5`, with
  named values (`low`, `medium`, `high`, `xhigh`), on a page in the same documentation set
  as the price. Effort is therefore a documented feature of the model that the pricing
  pages decline to key on - the same shape as the OpenAI finding, not a gap.
- **Still unchallenged, not proven:** no xAI page says "price does not depend on effort."
  The finding rests on the *absence of an effort dimension* in tables that do carry a
  context dimension - i.e. xAI demonstrably tiers price when it wants to, and did not tier
  it here. That is a strong inference from a primary source, not a first-party statement.

There is one genuine loose end, and it is adjacent to effort without being effort: **xAI
enumerates reasoning tokens as a token type distinct from output tokens, and publishes no
rate for that category.** See "Effort-adjacent findings".

## What the pages say

### `grok-4.5` model page

[docs.x.ai/docs/models/grok-4.5](https://docs.x.ai/docs/models/grok-4.5), read 2026-08-26.

One rate table, two columns, keyed on prompt size only:

| Type | < 200k prompt tokens | >= 200k prompt tokens |
| :-- | --: | --: |
| Input | $2.00 / M | $4.00 / M |
| Cached input | $0.30 / M | $0.60 / M |
| Output | $6.00 / M | $12.00 / M |

with the note *"Requests whose prompt reaches 200k tokens are billed at the higher rate for
all tokens in the request."* Matches the 2026-08-24 record exactly - the rates have not
moved in two days. The page lists aliases `grok-4.5-latest` and `grok-build-latest`, states
**"Batch API: Not supported"**, and does **not** mention `reasoning_effort`, effort levels,
or priority processing at all.

### API pricing page

[docs.x.ai/developers/pricing](https://docs.x.ai/developers/pricing), read 2026-08-26.

`grok-4.5` appears once, as two tier rows (< 200k / >= 200k) with the figures above. Every
other text model - `grok-4.6`, `grok-4.3`, `grok-4.20-0309-reasoning`,
`grok-4.20-0309-non-reasoning`, `grok-build-0.1`, `grok-4.20-multi-agent-0309` - has the
same shape: one row per context tier, no row per effort level. The page's price axes are
**model, context tier, and token category**. Effort is not an axis on it.

### Reasoning capability page - the corroborating second page

[docs.x.ai/developers/model-capabilities/text/reasoning](https://docs.x.ai/developers/model-capabilities/text/reasoning),
read 2026-08-26. This is the page that owns the parameter.

- `reasoning_effort` takes `"low"`, `"medium"`, `"high"` (**default**), `"xhigh"`.
- `"xhigh"` is available on `grok-4.6` and later; **on `grok-4.5` a request asking for
  `"xhigh"` is treated as `"high"`.**
- Reasoning cannot be disabled on a reasoning model.
- On billing it says only: *"When you use a reasoning model, the reasoning tokens are
  billed as part of your total consumption."* It names no rate, no per-effort rate, and no
  price difference between the four values. It exposes `reasoning_tokens` as a usage
  metric.

So the two pages corroborate in the way #304 asked for: the page that owns the price does
not mention effort, and the page that owns effort does not mention a price.

### The `grok-4.6` control

[docs.x.ai/developers/grok-4-6](https://docs.x.ai/developers/grok-4-6), read 2026-08-26.
Worth reading precisely because `grok-4.6` supports the *extra* effort level `grok-4.5`
does not. Its "At a glance" block lists Reasoning as *"Low, medium, high (default), or
xhigh"*, and its pricing table is still a single pair - $2.00 / M input, $6.00 / M output -
with no per-effort line items. **A model with four real effort levels publishes one rate.**
That is the closest thing to a positive result available: it rules out "xAI just has not
got round to tiering the model with the extra level."

### Cost reporting

[docs.x.ai/developers/cost-tracking](https://docs.x.ai/developers/cost-tracking), read
2026-08-26. xAI returns the billed amount per request in the response body as
`usage.cost_in_usd_ticks`, where `cost_usd = cost_in_usd_ticks / 10,000,000,000`, described
as *"the actual amount billed, after all applicable discounts (including prompt caching
reductions) have been applied, and inclusive of all token costs and server-side tool
invocation costs."* The page never mentions reasoning tokens or effort.

Two things follow, both useful to #295 beyond this question. First, **xAI hands us the
authoritative per-request cost directly**, so on this provider a rate table is a
cross-check rather than the only source of truth - and an empirical answer to the effort
question is one paired API call away (same prompt at `low` and at `high`, compare
`cost_in_usd_ticks` per token). This record is documentation-only and did not make that
call. Second, the field is a single aggregate with no per-category breakdown, so it cannot
by itself tell us what rate the reasoning tokens went out at.

### Billing FAQ

[docs.x.ai/developers/faq/billing](https://docs.x.ai/developers/faq/billing), read
2026-08-26. Five questions, all about payment cards, invoicing, refunds, charge timing, and
tokenizer discrepancies. **Nothing about reasoning tokens, effort, or effort-linked
pricing.** Read to close off the "it is documented, just somewhere else" branch; it is not.

## Effort-adjacent findings

The ticket asked whether anything on xAI ties price to something effort-adjacent. Three
things do, and none of them is an effort tier.

1. **Reasoning tokens are a named token category with no published rate.** The pricing page
   defines five token types - *"Input tokens: Your query and conversation history /
   Reasoning tokens: Agent's internal thinking and planning / Completion tokens: The final
   response / Image tokens: Visual content analysis (when applicable) / Cached prompt
   tokens: Prompt tokens that were served from cache rather than recomputed"* - and its rate
   tables have three rows: Input, Cached input, Output. **Reasoning has no row.** The
   natural reading is that reasoning tokens bill at the Output rate, and no xAI page read
   here says so. Worse, the discount sections enumerate reasoning *alongside* output as a
   separate type: the Batch API section says *"The batch discount applies to all token types
   - input tokens, output tokens, cached tokens, and reasoning tokens"* and Priority
   Processing says *"The 2x multiplier applies to all token types - input, output, cached,
   and reasoning."* If reasoning were merely a synonym for output, that enumeration would be
   redundant. This is the one place where effort could reach price without an effort tier:
   effort changes how many reasoning tokens are produced, and we cannot state their price
   from published sources. It does **not** force an A154 re-key - the rate would still be
   keyed by `(model, provider)`, effort would just move the *volume* - but it does widen the
   value again, exactly as the context tier did.
2. **Priority Processing is a 2x premium, and it is not effort.** *"Priority Processing
   gives text requests higher scheduling priority for lower latency. Priority requests are
   billed at a 2x premium over standard rates"*, on Chat Completions and Responses only, not
   image, video, or Batch. This is xAI's structural analogue of Anthropic's fast mode that
   #304 already dismissed: a latency/scheduling premium requested separately, not a
   reasoning-depth tier. The pricing page as read did not name the request parameter or the
   eligible model list - unresolved, and it matters only if a seat ever opts in. **A154
   should note it the same way it notes Anthropic's `speed`: a second price-moving request
   parameter that is not effort.**
3. **Batch API: a 20% discount `grok-4.5` cannot have.** The discount covers `grok-4.3`,
   `grok-4.20-0309-reasoning`, `grok-4.20-0309-non-reasoning`, `grok-4.20-multi-agent-0309`;
   *"Models not listed above have no batch discount."* The `grok-4.5` page independently
   says Batch API is not supported. Consistent across both pages, and moot for a synchronous
   arbiter seat.

And two non-findings worth recording so they are not re-investigated:

- **No effort-tier model ids.** No `grok-4.5-fast`, `-mini`, `-thinking`, or `-high` exists
  on the models index ([docs.x.ai/developers/models](https://docs.x.ai/developers/models),
  read 2026-08-26). `grok-4.5` appears once, in two context-tier rows.
- **`reasoning` / `non-reasoning` split ids are not a price tier either.** xAI does ship
  reasoning-split ids on the 4.20 line, which is the closest an id ever comes to encoding
  effort. They are priced *identically*: `grok-4.20-0309-reasoning` and
  `grok-4.20-0309-non-reasoning` both publish $1.25 / $0.20 / $2.50 and $2.50 / $0.40 /
  $5.00, on their own model pages
  ([reasoning](https://docs.x.ai/developers/models/grok-4.20-0309-reasoning),
  [non-reasoning](https://docs.x.ai/developers/models/grok-4.20-0309-non-reasoning), read
  2026-08-26). The non-reasoning page states *"Reasoning: No"*. So on the one model family
  where xAI does split reasoning out into its own billable identity, it charges the same
  either way. That is the strongest available evidence that xAI does not treat reasoning
  depth as a price axis.

## Bearing on A154 clause (2)

**No re-key.** The counter-example clause (2) warned about - *"a provider that ever prices
by effort forces a re-key"* - is not present on xAI. With #304 having settled OpenAI and
Anthropic, all three routed providers are now checked, and `(model, provider)` identifies a
price on every one of them.

Recording the strength honestly, since the clause is being relied on rather than merely
noted:

| Provider | Effort documented? | Priced by effort? | Evidence class |
| :-- | :-- | :-- | :-- |
| OpenAI | Yes, `reasoning.effort`, 6 values | No | Parameter documented on the price page, no price attached (#304) |
| Anthropic | n/a; `speed` is separate | No | Premium is keyed to `speed`, not effort (#304) |
| xAI | Yes, `reasoning_effort`, 4 values | No | Parameter documented on a sibling page; price pages key on model + context tier + token category only. **Unchallenged, not proven** - no first-party statement denies it |

The single cheapest thing that would upgrade xAI's row from *unchallenged* to *measured* is
one paired live call reading `usage.cost_in_usd_ticks` at two effort levels. That is a
probe, not a document read, and is out of scope here.

What this record does **not** close is the value shape. Between #304's context tiers and
this record's unpriced reasoning-token category, the pressure on A154 continues to fall on
what sits behind the key, not on the key.

## Open questions

1. **At what rate do reasoning tokens bill on xAI?** Presumed Output; not published. The
   only category in xAI's own five-type list with no row in its own rate table. This is the
   one live gap this record found.
2. **Which models accept Priority Processing, and what is the request parameter?** A
   documented 2x on all token types. Only matters if a seat opts in - but a 2x that a seat
   could turn on without the rate table knowing is the same class of defect A154 exists to
   prevent.
3. **Carried forward unchanged from 2026-08-24:** does xAI cache automatically, and can it
   be disabled from Grok Build? Nothing read today touched it.

## Sources

All read 2026-08-26. xAI-owned pages only.

- xAI, [Grok 4.5 model page](https://docs.x.ai/docs/models/grok-4.5)
- xAI, [API pricing](https://docs.x.ai/developers/pricing)
- xAI, [Reasoning capability guide](https://docs.x.ai/developers/model-capabilities/text/reasoning)
- xAI, [Grok 4.6 model page](https://docs.x.ai/developers/grok-4-6) (control: four effort levels, one rate)
- xAI, [Models index](https://docs.x.ai/developers/models)
- xAI, [Cost tracking](https://docs.x.ai/developers/cost-tracking)
- xAI, [Billing FAQ](https://docs.x.ai/developers/faq/billing)
- xAI, [grok-4.20-0309-reasoning](https://docs.x.ai/developers/models/grok-4.20-0309-reasoning)
- xAI, [grok-4.20-0309-non-reasoning](https://docs.x.ai/developers/models/grok-4.20-0309-non-reasoning)

Not used: `https://x.ai/api` (returned HTTP 403 to an unauthenticated fetch on 2026-08-24
and was not retried). No aggregator or secondary write-up is cited for any claim.
