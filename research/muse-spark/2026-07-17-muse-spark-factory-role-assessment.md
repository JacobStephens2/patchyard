# Muse Spark 1.1 Factory Role Assessment

Mostly yes, with two important corrections:

1. Muse Spark 1.1 is excluded from the implementation worker seat.
2. "Verification" should mean supplementary model review, not the factory's authoritative verification stage.

| Factory role | Muse Spark 1.1 status |
|---|---|
| Implementation worker | Closed. No tested harness achieved acceptable reliability. |
| Deterministic verifier | Not an LLM role. Rust checks, tests, and policy gates remain authoritative. |
| Supplementary reviewer | Plausible candidate using a bounded, tool-free API call. Not yet qualified. |
| Triage classifier | Plausible candidate if all required evidence is assembled before the call. Not yet qualified. |

## Implementation worker

The implementation conclusion is explicit in the research: no harness configuration, including the purpose-built minimal loop, achieved reliable artifact fidelity. Muse sometimes corrected an erroneous first write but left the incorrect artifact behind. That is unacceptable for a worker responsible for mutable repository state.

See [the final seat decision](2026-07-17-muse-spark-envelope-bisection.md#production-decision).

Muse Spark 1.1 should remain excluded from the implementation worker seat pending a model update and a complete retest.

## Triage classifier

For triage, Muse could receive a deterministic evidence packet containing the request, attachments, rubric, relevant repository facts, and deny rules, then return strict JSON such as:

```json
{
  "lane": "A",
  "deny_rules": [],
  "confidence": 0.97,
  "reason": "...",
  "question": null
}
```

That would not require Claude Code, OpenCode, or a general agent harness. It would still require a thin deterministic adapter that:

- assembles a fixed, bounded input envelope;
- invokes the model without repository or execution tools;
- validates the response against a strict schema; and
- fails closed on malformed, incomplete, or unrecognized output.

If Muse must explore the repository through `Read`, `Grep`, or `Glob`, it is back inside a tool-using agent envelope, and today's research does not establish that as safe. The existing specification currently expects tool-assisted, read-only triage in [`SPEC.md`](../../SPEC.md). Adopting Muse without a harness would therefore require separating triage into two stages:

1. Deterministic evidence collection.
2. Tool-free model classification.

Muse remains a candidate for that narrow classification role, not a qualified triage worker yet.

## Verification and supplementary review

Muse should not replace `factory-verify`, PHPUnit, patch validation, or policy gates. Those remain deterministic and authoritative under the verification pipeline defined in [`SPEC.md`](../../SPEC.md).

Muse could instead serve as an independent cross-family reviewer in a later phase. It could examine a bounded packet containing the proposed patch, acceptance criteria, and deterministic verification evidence, looking for semantic mistakes that tests might miss.

This should be called **supplementary review** or a **judgment seat**, rather than verification, because the model would not constitute proof that the patch is correct. Its response could be advisory or an additional fail-closed gate, but it should never supersede deterministic verification.

The reviewer should have no write, shell, repository exploration, or execution tools.

## What the raw 80/80 result establishes

The clean raw-API 80/80 result does not qualify either seat by itself. It proved exact tool-call fidelity for one small synthetic envelope:

- two Meta endpoints;
- four target filenames;
- ten trials per endpoint and filename combination; and
- eighty exact tool-call results out of eighty trials.

The subsequent envelope bisection showed that reliability changed as the prompt and execution environment became more agent-like. The 80/80 result was therefore a property of that exact minimal envelope, not evidence that Muse is generally reliable without a harness.

The factory must evaluate the exact production triage and review envelopes rather than infer their reliability from the raw probe.

## Recommended policy

- Exclude Muse Spark 1.1 from the implementation worker seat pending a model update and complete retest.
- Build a harness-free, structured triage experiment.
- Build a separate tool-free patch-review experiment.
- Qualify each against its own replay corpus, including prompt injection, ambiguous requests, known-bad patches, false positives, false negatives, strict-schema compliance, and repeated-run reliability.
- Require zero unsafe triage promotions and define explicit false-positive and false-negative limits for review.
- Admit Muse only to the specific seat whose complete production envelope passes, not to a general "non-writing model" category.

## Conclusion

Triage classification and supplementary review are the two realistic factory seats still open to Muse Spark 1.1, but neither is approved yet. The implementation worker seat is closed.
