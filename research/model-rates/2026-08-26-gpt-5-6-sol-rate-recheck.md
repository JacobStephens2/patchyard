# GPT-5.6 Sol rate re-check: what happens after 2026-11-21

*Read 2026-08-26. Answers [#308](https://github.com/JacobStephens2/patchyard/issues/308),
which is open question 3 of
[`2026-08-24-openai-xai-token-rates.md`](2026-08-24-openai-xai-token-rates.md) promoted to
its own ticket. Fact-finding only; the numbers land in `policy/model-rates.json` and a
decision-log row under
[#295](https://github.com/JacobStephens2/patchyard/issues/295). No authority
(research/README.md convention 4). This record does not amend the 2026-08-24 file - it
stands beside it as a second dated reading.*

## Summary

**The question does not have an answer yet, and the reason is now better established than
it was on 2026-08-24.** Three OpenAI-owned pages agree, two days on:

1. **Every rate is unchanged.** All six figures from the 2026-08-24 reading reproduce
   exactly, plus the cache-write figures. Nothing moved.
2. **The promotional clause is unchanged, word for word, and the date has not moved** -
   still "at least through November 21, 2026". **No post-promotional rate is published
   anywhere on OpenAI's docs.** The successor number does not exist to be read; it is not
   that we failed to find it.
3. **The scope is still stated only as "the model"** - no tier, no figure, no token
   category is named. But the changelog adds a fact the pricing page alone did not carry:
   the promotion is the **2026-08-21 price cut itself**, and it is quantified. That gives
   the promotion a *floor date* and an implied pre-promotional price, which is the closest
   thing to a successor number that exists - and it is an inference, not a publication.
   See "What replaces it" below.

A fourth finding, unasked: the promotional footnote sits **only under the Standard tier
tab**. Sol's Batch, Flex and Fast-mode tables carry the same 10%-uplift footnote without
it. Read literally that is narrower scope than "the model" - read as page structure it is
one footnote in one pane. Treated here as ambiguous, not as a scope narrowing; see
"Scope".

## Current rates

Standard tier, per 1M tokens. Read 2026-08-26 from
[API pricing](https://developers.openai.com/api/docs/pricing) and
[the model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol); the two agree.

| Token category | Standard | Long context (>272K input tokens) |
| :-- | --: | --: |
| Input | $4.00 / M | $8.00 / M |
| Cached input (read) | $0.40 / M | $0.80 / M |
| Cache writes | $5.00 / M | $10.00 / M |
| Output | $20.00 / M | $30.00 / M |

The pricing page now tabulates cache writes as **its own column**, per tier, rather than
leaving them to the model page's multiplier rule. The two statements agree:
*"Cache writes are billed at 1.25x the uncached input token rate"* (model page) gives
$4.00 x 1.25 = $5.00 and $8.00 x 1.25 = $10.00, which is what the table prints.

The long-context rule is unchanged and still repricing the whole request:
*"Prompts with >272K input tokens are priced at 2x input and 1.5x output for the full
request."*

### Other service tiers, for completeness

The seats in `policy/routing.json` run Standard, so these are context rather than the
answer. Same page, same read, short context / long context:

| Tier | Input | Cached input | Cache writes | Output |
| :-- | --: | --: | --: | --: |
| Standard | $4.00 / $8.00 | $0.40 / $0.80 | $5.00 / $10.00 | $20.00 / $30.00 |
| Batch | $2.00 / $4.00 | $0.20 / $0.40 | $2.50 / $5.00 | $10.00 / $15.00 |
| Flex | $2.00 / $4.00 | $0.20 / $0.40 | $2.50 / $5.00 | $10.00 / $15.00 |
| Fast mode | $8.00 / $16.00 | $0.80 / $1.60 | $10.00 / $20.00 | $40.00 / $60.00 |

Two footnotes on that table bear on any cost figure this repo publishes:
*"Regional processing (data residency) endpoints are charged a 10% uplift for models
released on or after March 5, 2026"*, and *"OpenAI models in Amazon Bedrock are billed
through AWS and may differ from direct OpenAI pricing."* Neither applies to the current
seats; both are ways a `(model, provider)` key could stop identifying a price.

## Diff against the 2026-08-24 reading

| Fact as read 2026-08-24 | As read 2026-08-26 |
| :-- | :-- |
| Input $4.00 / M standard | **unchanged** |
| Cached input $0.40 / M standard | **unchanged** |
| Output $20.00 / M standard | **unchanged** |
| Input $8.00 / M long context | **unchanged** |
| Cached input $0.80 / M long context | **unchanged** |
| Output $30.00 / M long context | **unchanged** |
| Cache writes 1.25x uncached input ($5.00 / M standard) | **unchanged**; additionally now confirmed as an explicit pricing-page column, $5.00 standard / $10.00 long context |
| Long-context threshold >272K input tokens, 2x input / 1.5x output, full request | **unchanged** |
| `reasoning.effort` supports `none, low, medium, high, xhigh, max`, no price attached | **unchanged** (`medium` is marked default) |
| Promotional clause present on the pricing page | **unchanged**, verbatim; and it is **also** on the model page and the changelog - a corroboration the 2026-08-24 record did not claim |
| Promotional end date 2026-11-21 | **unchanged** - the date has not moved |
| No post-promotional rate published | **unchanged** - still none |
| Scope stated as the model, not a tier | **unchanged** in wording; see "Scope" for the one new wrinkle |

**Nothing in the 2026-08-24 reading requires correction.** The confirmed figures are the
whole diff: every line above is "unchanged".

New facts, not corrections - things this reading turned up that the earlier one did not
record:

- The promotion **started 2026-08-21**, five days before this reading (changelog).
- The cut was **20% off input and 33% off output** (changelog, model page).
- Sol has **Batch, Flex and Fast-mode** rates, and Fast mode gained long-context support on
  2026-08-05 (changelog).
- `daybreak-blue-latest` is an alias currently pointing at `gpt-5.6-sol`, priced to match
  the underlying model, and the alias will be repointed as new frontier models ship
  (pricing page). A rate table keyed on the alias would silently reprice itself; keyed on
  `gpt-5.6-sol` it does not.
- An **Ultrafast mode** service tier was announced 2026-08-13 in limited preview, with no
  published rate.

## The promotional clause

Verbatim, and identical on all three pages:

> GPT-5.6 Sol's promotional pricing is available at least through November 21, 2026.

Where it appears, read 2026-08-26:

- [API pricing](https://developers.openai.com/api/docs/pricing) - footnote under the
  **Standard** tier table.
- [Model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol) - in the pricing
  section, immediately after: *"GPT-5.6 Sol costs $4 per million input tokens and $20 per
  million output tokens, a 20% reduction in input pricing and a 33% reduction in output
  pricing."*
- [Changelog](https://developers.openai.com/api/docs/changelog), entry dated **Aug 21**,
  labelled `Update gpt-5.6-sol`: *"GPT-5.6 Sol now costs $4 per million input tokens and
  $20 per million output tokens, representing 20% lower input pricing and 33% lower output
  pricing. GPT-5.6 Sol's promotional pricing is available at least through November 21,
  2026."*

"At least through" is worth reading precisely: it is a **floor on the window, not a
terminus**. The published commitment is that the rates hold to 2026-11-21; it does not
state that they stop there. So 2026-11-21 is the date after which the published rates carry
no guarantee - not a date on which a known different price takes effect.

The changelog is the load-bearing addition. It is dated, it is OpenAI's own, and it makes
the promotion a specific event - the 2026-08-21 cut - rather than an unanchored adjective.
It also confirms nothing has changed since: **Aug 21 is the most recent entry on the
changelog as of this reading**, so there has been no pricing action in the two days since
the 2026-08-24 record.

### What replaces it after 2026-11-21

**Nothing is published.** Searched: the pricing page (all four service tiers plus the Cyber
table), the model page, and the changelog. No page states a post-promotional rate, a
scheduled increase, or a rate the promotion is a discount *from*.

One number is *derivable* and must not be mistaken for a published one. The changelog's own
percentages invert: $4.00 is 20% below **$5.00**, and $20.00 is 33% below **$30.00**
(33.3%, rounded in the source). Those two figures are corroborated as a real OpenAI price
point - they are exactly the published `gpt-5.5 (<272K context length)` row, $5.00 input /
$0.50 cached / $30.00 output, and the model page's own "Quick comparison" prints GPT-5.5 at
$5.00.

So the pre-promotional Sol price was $5.00 / $30.00. **That is where the price came from,
not a statement about where it goes.** Reverting to it is a guess. Recorded here so that if
#295 ever wants a worst-case bound it is bounding against a sourced number, and so that the
guess is not later mistaken for a citation. Nothing published rules out a further cut, a
different structure, or an indefinite extension. Cached-input and cache-write pre-promotion
figures are not derivable at all - the changelog quantifies only input and output.

## Scope: still "the model", with one wrinkle

The clause names `GPT-5.6 Sol` and no token category, tier or figure. #304's reading holds:
as far as the source states, the promotion covers all of the model's published numbers.
Nothing published narrows it to, say, output only.

The wrinkle is placement rather than wording. The pricing page renders four service-tier
panes, and the promotional sentence is in the footnote of the **Standard** pane only; the
Batch, Flex and Fast-mode panes carry the data-residency footnote without it. Two readings:
either the promotion is scoped to Standard-tier rates, or the footnote was simply written
once in the pane most people read. **Nothing on the page distinguishes them**, and the model
page and changelog both state the clause with no tier qualifier at all, which leans toward
the second. Recorded as an ambiguity, not as a finding.

This matters little today - the OpenAI seats run Standard - and it would matter immediately
if a seat moved to Batch or Flex to save money.

## Bearing on #295

- **The re-check found no drift, which is a result about the numbers, not about the
  process.** Two days is a short interval and the promotion is five days old; the same check
  in November is the one that will matter. The read-date remains part of the fact.
- **The table still cannot be given a post-2026-11-21 number**, because none exists to be
  given. A table that fails closed on a missing entry is the right shape for this; a table
  that carries $4.00 with no expiry date is not.
- **What the table can carry is the expiry**, which is published and precise. A rate entry
  for `gpt-5.6-sol` that records `2026-11-21` alongside the read-date turns a future stale
  number into a detectable one rather than a silent one.
- **Cache writes are now a first-class published column**, not a derived multiplier. The
  fourth finding of the 2026-08-24 record - that no seat table here prices writes - is
  reinforced: the number is sitting in the provider's own table.

## Open questions

Carried forward or newly raised. None blocks #295.

1. **What replaces the promotional rate on 2026-11-22?** Still unanswered, and now known to
   be unanswerable from published sources rather than merely unfound. The action is a
   re-check dated close to the deadline, not more reading now.
2. **Is the promotion scoped to the Standard tier?** New, from the footnote placement above.
   Only matters if a seat moves to Batch or Flex.
3. **Does the `>272K` threshold count cache reads toward prompt size?** Unchanged from
   2026-08-24 open question 4; still unaddressed by any page read here.
4. **What is Ultrafast mode priced at?** Announced 2026-08-13, limited preview, no published
   rate. Not reachable by any current seat.

## Sources

All read **2026-08-26**. OpenAI-owned pages only, per #304 - no aggregator is cited for any
rate.

- OpenAI, [API pricing](https://developers.openai.com/api/docs/pricing)
- OpenAI, [GPT-5.6 Sol model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- OpenAI, [API changelog](https://developers.openai.com/api/docs/changelog) (entries of Aug 21, Aug 13, Aug 5, Jul 30, 2026)
