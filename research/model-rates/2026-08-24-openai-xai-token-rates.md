# Published token rates for the OpenAI and xAI seats

*Read 2026-08-24. Sources the two rates [A154](../../docs/decision-log.md) declined to
invent, for [#304](https://github.com/JacobStephens2/patchyard/issues/304).
Fact-finding only - the numbers land in `policy/model-rates.json` and a decision-log row
as part of [#295](https://github.com/JacobStephens2/patchyard/issues/295).
No authority (research/README.md convention 4).*

## Summary

Both rates are sourced and corroborated against a second page from the same provider.
Three findings reach *how* the rate is applied, and bear on what #295 must build:

1. **No provider was found to price by effort.** OpenAI and Anthropic document an effort
   or speed parameter and attach no price to it; xAI's documentation is silent, which is
   absence of evidence rather than evidence of absence. A154 clause (2)'s key of
   `(model, provider)` is unchallenged by what is published, with xAI untested.
2. **Context length does move price - on OpenAI and xAI, but not on Anthropic.** A rate is
   not two integers. This does *not* force a re-key; it forces a richer *value* behind the
   existing key.
3. **Codex appears unable to disable prompt caching**, which would make A154 clause (5)'s
   fail-closed on non-zero cached tokens an **immediate blocker** on the implement seat
   rather than a quiet guard. Note the evidence class: the caching *rates and mechanics*
   come from OpenAI's own documentation, but the *Codex cannot emit the field* claim rests
   on an open bug report, which is weaker. See secondary question 1.

A fourth finding was not asked for and matters anyway: **cache writes are a separately
billed, separately reported token category** on both OpenAI and Anthropic, and no seat
table in this repo has ever priced them. Detail under secondary question 1.

## GPT-5.6 Sol on OpenAI

Seats: `implement`, `repair`, `improvement_proposer_review` (`policy/routing.json`).
API model id `gpt-5.6-sol`; pairing `openai/codex/gpt-5.6-sol/xhigh` (A105).

| Token category | Standard | Long context (>272K input tokens) |
| :-- | --: | --: |
| Input | $4.00 / M | $8.00 / M |
| Cached input (read) | $0.40 / M | $0.80 / M |
| Output | $20.00 / M | $30.00 / M |

Sources, both OpenAI's own:
[model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol) and
[API pricing](https://developers.openai.com/api/docs/pricing), read 2026-08-24. The two
agree.

- **Long-context tier.** The model page states: *"Prompts with >272K input tokens are
  priced at 2x input and 1.5x output for the full request."* The multipliers reproduce the
  pricing page's long-context column exactly ($4x2=$8, $0.40x2=$0.80, $20x1.5=$30). Note
  *for the full request* - it is not a marginal rate above the threshold, it reprices every
  token in the request.
- **Cache writes.** *"Cache writes are billed at 1.25x the uncached input token rate"* -
  $5.00 / M standard. Billed, and not the same number as either input or cached input.
- **Effort.** The model page documents `reasoning.effort` supporting
  `none, low, medium, high, xhigh, max` and attaches no price to any of them. No
  effort-keyed pricing on either page.
- **Promotional pricing.** The pricing page carries: *"GPT-5.6 Sol's promotional pricing is
  available at least through November 21, 2026."* **These rates have a published expiry.**
  The page does not say which figures are promotional - it names the model, not a tier - so
  the scope covers all six OpenAI numbers above as far as the source states. It also does
  not publish the post-promotional rate. Bearing on #295: a table that fails closed on a
  *missing* entry still reports confidently wrong money on a *stale* one, so the read-date
  above is part of the fact, not decoration.

## Grok 4.5 on xAI

Seat: `dispute_arbitration` (`policy/routing.json`). API model id `grok-4.5`
(aliases `grok-4.5-latest`, `grok-build-latest`); pairing `xai/grok-build/grok-4.5/high`.

| Token category | < 200k prompt tokens | >= 200k prompt tokens |
| :-- | --: | --: |
| Input | $2.00 / M | $4.00 / M |
| Cached input | $0.30 / M | $0.60 / M |
| Output | $6.00 / M | $12.00 / M |

Sources, both xAI's own:
[Grok 4.5 model page](https://docs.x.ai/docs/models/grok-4.5) and
[API pricing](https://docs.x.ai/developers/pricing), read 2026-08-24. The two agree.
(`https://x.ai/api` returned HTTP 403 to an unauthenticated fetch and was not used.)

- **Context tier.** The threshold is 200,000 prompt tokens, and as on OpenAI the higher
  rate applies to the whole request, not to the excess. Context window 500k.
- **Effort.** Not mentioned anywhere in xAI's pricing or model documentation. Recorded as
  *absent from the published source*, which is weaker than OpenAI's position - there the
  effort parameter is documented beside the price and carries none.
- **Caching mechanics undocumented.** xAI publishes a cached-input *rate* but documents
  neither whether caching is automatic nor whether it can be disabled. This is a genuine
  gap, not an omission in this record - see open questions.

## Secondary question 1: caching on the implement seat

**Prompt caching on OpenAI is automatic, always on above 1,024 tokens, and Codex cannot
turn it off.**

- *"Prompt Caching works automatically for eligible requests, with no code changes
  required"* and *"By default, caching is enabled automatically for prompts that are 1,024
  tokens or longer"* -
  [prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching),
  read 2026-08-24.
- An opt-out **exists at the API layer**: setting `prompt_cache_options.mode` to
  `"explicit"` disables the implicit breakpoint, and the guide states that *"If you set
  `mode` to `explicit` but provide no explicit breakpoints, the request does not use prompt
  caching or incur cache-write charges."* That would drive `cached_tokens` to zero.
- **The implement seat appears unable to reach that opt-out.** This is the one load-bearing
  claim in this record not sourced to provider documentation - it rests on a bug report,
  and is reported here as such rather than as a published fact. Codex cannot emit the
  field:
  [openai/codex#35300](https://github.com/openai/codex/issues/35300) (opened 2026-07-25,
  **still open** at time of reading) reports that `ContentItem::InputText` and `InputImage`
  carry no `prompt_cache_breakpoint` member or extension map, so the field *"is
  unrepresentable in both HTTP and WebSocket request construction."*

Consequence for A154 clause (5), stated plainly: the two observed live Codex runs on
request `bb995b19` sent 97,018 and 111,189 input tokens, roughly a hundred times the 1,024
token caching floor, on a harness whose prefix is stable across turns by construction.
Every turn after the first will report non-zero `cached_tokens`. **A supervisor-side
refusal on non-zero cached tokens will fail the implement seat on its first real run.**
That is the "immediate blocker" branch the ticket asked us to distinguish. The fact #295
needs in order to choose is that the cached read has a *published* rate - $0.40 / M - so
refusing cached tokens is not forced by an absence of pricing; the choice between refusing
and pricing them stays A154's to revisit, not this record's to make. The caveat carried on
[#206](https://github.com/JacobStephens2/patchyard/issues/206) is confirmed,
not merely plausible.

**Cache writes compound this**, and are the fourth finding named in the summary. GPT-5.6
and later report *two* fields, not one -
`cached_tokens` (read from cache) and `cache_write_tokens` (newly written), both under
`usage.input_tokens_details` on the Responses API and `usage.prompt_tokens_details` on Chat
Completions. Writes bill at 1.25x uncached input. A rate table with one cached-input number
prices the reads and silently drops the writes, which is the same class of defect as the
zero #295 is replacing. [openai/codex#37674](https://github.com/openai/codex/issues/37674)
independently reports high cache-write spend on this exact model where explicit cache
control is unavailable, so the write category is not theoretical money.

## Secondary question 2: does either provider price by effort tier?

**Not on OpenAI or Anthropic; xAI does not say. And the axis that demonstrably does move
price is context length, not effort.**

A154 clause (2) keyed rates by `(model, provider)` on the finding that *"harness is a local
client and effort is a request parameter; neither moves a published price, while provider
does."* That finding holds on every axis it names. But the clause anticipated a
counter-example forcing a *re-key*, and what turned up instead forces a **wider value**:

| Provider | Effort moves price? | Context length moves price? |
| :-- | :-- | :-- |
| OpenAI (`gpt-5.6-sol`) | No | **Yes** - >272K input, 2x input / 1.5x output, whole request |
| xAI (`grok-4.5`) | Not documented | **Yes** - >=200K prompt, 2x all categories, whole request |
| Anthropic (`claude-opus-5`, `claude-fable-5`) | No | **No** |

Anthropic is the control that makes this a provider property rather than an industry one:
*"Claude 4.6 and later models ... include the full 1M token context window at standard
pricing. (A 900k-token request is billed at the same per-token rate as a 9k-token
request.)"* -
[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), read
2026-08-24. The Anthropic rate *numbers* are deliberately not restated here - A154 keeps
A119 as their authority and is collapsing the copies of them, so this record cites only the
structural fact it needs: no context tier. That makes the two-integer shape the Anthropic
seat tables use correct *for those seats*, and never correct in general.

So the key survives and the value does not. `(model, provider)` still identifies a price;
the price it identifies is a small tiered structure, not a pair. What that costs #295 is a
question of representation, not of key: the published facts above cannot be expressed by
two integers, because they carry a context threshold, per-tier input/cached-input/output,
and a separately billed cache-write category on two of the three providers. How much of
that a table chooses to model is #295's call. Under the
current seats, today's traffic sits in the standard tier on both providers (the largest
observed implement prompt was 111,189 tokens against a 272K threshold), so a table that
modelled only the standard tier would be right by accident and wrong the first time a seat
sends a large repair brief.

## Open questions

None of these block #295; all four are cheap to get wrong silently.

1. **Does xAI price by reasoning effort?** Its documentation is silent, so the
   counter-example A154 clause (2) said would force a re-key is ruled out on OpenAI and
   Anthropic but merely *unobserved* on xAI. Cheap to settle by asking xAI directly; worth
   settling before the key is treated as proven on all three providers.
2. **Does xAI cache automatically, and can it be disabled from Grok Build?** xAI publishes
   a cached-input rate and documents no mechanics. The arbiter seat inherits whatever
   A154 clause (5) decides, on a provider where we cannot currently predict whether the
   refusal fires. Worth answering before the arbiter seat runs live rather than after.
3. **What is the GPT-5.6 Sol rate after 2026-11-21?** The promotional window is published
   and finite. A stale rate is a confidently wrong money number, which is the failure mode
   A154 exists to prevent, so the table wants a read-date and a re-check.
4. **Does the `>272K` threshold count cache reads toward the prompt size?** Both providers
   reprice *the full request* above the threshold, and neither states whether cached tokens
   count toward it. On a long-running Codex session where most input is cache reads, this
   decides whether a run crosses into the 2x tier.

## Sources

All read 2026-08-24. Provider-owned pages only, per #304 - no aggregator is cited for any
rate. The Artificial Analysis figures already in `research/artificial-analysis/` were
deliberately not used: their "$/M blended" column is a derived cost estimate, not a
published rate.

- OpenAI, [GPT-5.6 Sol model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- OpenAI, [API pricing](https://developers.openai.com/api/docs/pricing)
- OpenAI, [Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
- openai/codex, [#35300 - Codex cannot emit `prompt_cache_breakpoint`](https://github.com/openai/codex/issues/35300) (open)
- openai/codex, [#37674 - lacks explicit cache controls, high cache-write spend](https://github.com/openai/codex/issues/37674)
- xAI, [Grok 4.5 model page](https://docs.x.ai/docs/models/grok-4.5)
- xAI, [API pricing](https://docs.x.ai/developers/pricing)
- Anthropic, [Pricing](https://platform.claude.com/docs/en/about-claude/pricing) (control for the context-tier finding; A119 remains the authority for the Anthropic numbers)
