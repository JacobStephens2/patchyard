# OpenAI requirement 2: spend-refusal capture procedure

This document is written before the mutation it governs, which is the point of
it. OpenAI's spend limit has no Administration API surface, so the change from a
soft cap to a hard cap is a control-plane mutation with no obtainable receipt.
Under A132 that makes it an attestation, and an attestation records a bounded
capture of the state *before* and *after*. A before-state cannot be recovered
once the change is made.

Requirement 1 already demonstrates the cost of learning this late. Its
first-token-exchange observation is real and provider-attested, but the console
mutations behind it - provider creation, JWKS upload, subject mapping - were
made without a bounded capture, so no conforming attestation can be built for
them now. Requirement 2 is still avoidable.

## Do not flip the hard-limit toggle yet

The toggle is a step *inside* the captured run, not a prerequisite to it.
Flipping it early destroys the before-state and puts requirement 2 in the same
position as requirement 1.

## What blocks the run today

Requirement 2 needs the provider to *refuse* a billable call. Observing that
needs three things the factory does not yet have for OpenAI:

1. **A billable call.** `tools/openai-wif-issuance.py` performs the exchange and
   destroys the bearer without calling anything. That is correct for requirement
   1 and insufficient for requirement 2.
2. **The execution plane.** Anthropic's requirement 2 ran its call through
   `worker/runtime/patchyard-anthropic-one-shot` under
   `worker/runtime/patchyard-firecracker-run`, recorded in the result as
   `provider_transport.mechanism = host-one-shot-network-namespace-v1`.
3. **A provider-neutral launcher**, which A133 rules must exist and must contain
   no provider name. Built 2026-08-11 as
   `worker/runtime/patchyard-provider-run`, with its provider facts in
   `policy/provider-qualification.json` and the no-provider-name condition
   enforced by `tools/check-freeze-graph.py`.

The OpenAI one-shot client and the policy file's OpenAI entry were built
2026-08-13 as `worker/runtime/patchyard-openai-one-shot` (installed by the
`neutral_launcher` role). The client mirrors the frozen three-argument
contract; per A125 its refusal predicate is unenforced — a `temporary_refusal`
non-200 is recorded as it arrives, never matched against an expected status or
shape. Its calibrated request was verified against the live API on 2026-08-13
with the standing operator key (not the WIF path): `gpt-5.6-luna`,
`max_completion_tokens: 16`, 64,021 uncached prompt tokens, HTTP/1.0 with
`Connection: close` accepted, `x-request-id` of the form `req_<hex>`, and
`usage.prompt_tokens_details.cached_tokens` present (recorded by the client,
not enforced). The policy entry's `phase_spend_cap_cents` values are **zero
placeholders**: Phase 0 below discovers what the console permits and a
reviewed change replaces them before any capture phase runs. A capability
minted for the run must carry the same values, so the placeholders cannot
silently authorize a differently-capped run.

The execution plane cannot be reused. Six worker artifacts are protected, but
not all in the same way, and the difference matters when planning the neutral
launcher. Verify with `tools/check-freeze-graph.py` rather than trusting this
table:

| worker artifact | protection | held by |
| :-- | :-- | :-- |
| `worker/runtime/patchyard-anthropic-one-shot` | frozen | `anthropic-spend-enforcement.json` |
| `worker/image/production-parity.json` | frozen | three committed results |
| `worker/qualification/hostile-test-manifest.json` | frozen | `session-5-hostile-qualification.json` |
| `worker/runtime/patchyard-firecracker-run` | checker-pinned | `check-anthropic-{spend,expiry,revocation}.py` |
| `worker/image/patchyard-guest-run` | checker-pinned | `check-anthropic-{spend,expiry,revocation}.py` |
| `worker/qualification/patchyard-run-anthropic-issuance` | checker-pinned | `check-anthropic-{spend,expiry,revocation}.py` |

The bottom three left the freeze census when A134 superseded the checkers that
had pinned them; the census is now "reachable from a Result at its *current*
digest". **Absence from the census is not permission.** Their digests are still
asserted by three checkers that guard Anthropic's six proven requirements, so
editing one in place forces a repin of a checker whose job is to validate
already-banked evidence. That is a worse move than duplication, not a cheaper
one: it changes what Anthropic's evidence is checked against in order to make
room for OpenAI.

The conclusion is unchanged - build the neutral launcher as a new artifact -
but the reason is "three frozen and three checker-pinned", not "six frozen".

A133 recorded that the launcher names Anthropic in three places. A raw count
gives more, but a count is a poor estimator in both directions and should not
be used to plan the work. Measured on the launcher: 32 occurrences across 30
lines, which is 8 logical sites once repeated identifiers are collapsed.

**The launcher is closer to neutral than the count suggests.** It reads
`PROVIDER` from the manifest, resolves hostnames from
`.providers[$provider].hostnames[]` in
`/etc/patchyard-worker/provider-egress.json`, and derives every per-run
resource name from `$SHORT_ID` - `PROVIDER_NETNS`, the veth pair, and
`PROVIDER_NFT_TABLE="eta_fp_$SHORT_ID"`. Where its occurrences actually are:

| what | occurrences | sites |
| :-- | --: | :-- |
| `eta_anthropic_one_shot` nft table | 18 | lines 213-274, one literal |
| `ANTHROPIC_ONE_SHOT` client path | 6 | one variable, line 29 |
| provider mode gates | 2 | lines 62, 91 |
| hosts-file entry | 1 | line 180 |
| spend-mode host assertion | 1 | line 457 |
| error-string literals | 2 | lines 257, 554 |
| jq result predicate | 1 | line 774 |

The nft table is 18 of the 32 and is a single name; the run-scoped pattern to
follow sits two lines above its first use. The two error strings and the jq
predicate are easy to miss when planning from a count, which is why they are
listed.

**The guest runner is where the real coupling is**, and 24 occurrences
understates it, because these are protocol rather than naming:

- it calls `https://api.anthropic.com/v1/models?limit=1` as its provider probe;
- it writes an auth config carrying `anthropic-version: 2023-06-01`;
- its spend-qualification artifacts are named for the provider and its result
  JSON hard-codes `provider:"anthropic"`.

An endpoint path, an auth header shape and a version header are provider facts,
not launcher facts, so neutralising the guest runner means deciding where they
live rather than renaming anything.

**Proposed adapter contract.** `policy/provider-egress.json` already holds the
per-provider egress facts the launcher consumes, and it is the file the neutral
launcher already reads. (The launcher build found this file cannot be extended
in place: `factory-supervisor` deserializes it with `deny_unknown_fields`, and
its shape is asserted by multiple committed checkers. The launcher's adapter
facts therefore landed in the sibling `policy/provider-qualification.json`; the
guest runner's probe block below faces the same constraint when it is built.)
Extend each provider entry with the probe the guest runner needs:

```json
{
  "probe": {
    "url": "https://api.anthropic.com/v1/models?limit=1",
    "method": "GET",
    "auth_header": "x-api-key",
    "extra_headers": { "anthropic-version": "2023-06-01" }
  }
}
```

The guest runner then carries no provider name and no endpoint, and adding a
provider is a policy edit rather than a new runner. `hostnames` stays the
authority for egress; `probe.url` must resolve to a host already in it, and the
runner should assert that rather than trusting the policy to be internally
consistent.

**None of the three can be edited in place**, per the protection table above,
so each neutral artifact is a new file and the Anthropic originals stay exactly
as they are for as long as Anthropic's committed Results point at them.

An OpenAI request cannot leave that worker. This is a sequencing fact, not a
defect: A133 already ruled the neutral launcher must be built, and this is the
first requirement that cannot proceed without it.

## What was built (2026-08-14)

The spend half of the neutral guest path exists. The probe block above is still
unbuilt and stays unbuilt: it belongs to issuance-delivery, which is not on the
OpenAI route, and A125 forbids pinning a protocol fact nobody has observed.

- `worker/image/patchyard-guest-qualify` validates the three host-staged
  receipts - `issuance.json`, `provider-transport.json`,
  `provider-observation.json` - from inside a guest holding no credential and
  no provider route, then emits the patch and evidence. Every provider-shaped
  value it checks against arrives as data.
- `worker/image/patchyard-guest-dispatch` decides which runner owns the boot,
  by the **shape of the input drive**: `qualification-policy.json` present
  routes to the qualification runner, absent leaves the general runner to run
  exactly as before. No provider name enters either program, and
  `tools/check-freeze-graph.py` now enforces that on both.
- The `spend_observation` block in `policy/provider-qualification.json` holds
  the endpoint, the cap field name, the identifier patterns, the accepted and
  refusal response vocabulary, the artifact naming and the ruling id. The
  launcher projects it with `jq -S` into the input drive, and the manifest's
  `qualification_policy_sha256` must equal that projection's digest.
- The OpenAI entry sets `refusal_response.enforced: false` with the basis
  `no-observed-openai-spend-refusal` (A125). The guest then requires nothing of
  the refusal's status or shape - but does require the observation to *say* the
  predicate was unenforced, so an unenforced predicate can never read as a met
  one. The Anthropic entry mirrors that provider's observed refusal shape and
  keeps it enforced; Anthropic runs continue to use the original runner.

**Why the dispatcher is its own unit rather than an `ExecStart` edit.** The
decision that specified this path recorded `patchyard-guest-run.service` as
individually unpinned. A142's qualified image inventory has since pinned it
byte-identical, and A143 released only `build-parity-image`. So the dispatcher
ships as `patchyard-guest-dispatch.service`, ordered `Before=` the general
runner's unit, which is left untouched and still enabled. A143 clause (4)
already ruled dispatcher primacy compatible with A115 - the evidence never
fixed which qualified-and-scanned program boots first - and unit ordering
reaches that outcome without overriding a pinned descriptor at all.

## What is receipt-backed and what is attested

An Administration API readback from the operator host on 2026-08-06T22:50:25Z
established which is which. Repeat this capture inside the run's window rather
than citing these values.

Receipt-backed, and usable as provider evidence:

- the project, the service account, and the project's API-key count;
- `/v1/organization/costs`, which gives a spend measurement independent of the
  console;
- `/v1/organization/projects/{project}/rate_limits`, which returns 200.

No receipt obtainable, so A132 attaches:

- the workload identity provider, which returns 404 on its Administration API
  path;
- **the project budget**, which returns 404. This is the mutation this document
  governs.

That OpenAI exposes an API for rate limits but not budgets is the second
independent confirmation that A132's per-mutation scope is correct and a
per-provider trigger would be wrong.

## The capture

The phase names match the shape requirement 2 already uses, so the attestation
and the result read the same way across providers.

Every phase records `captured_before_at` and `captured_after_at` in control-plane
UTC with `capture_method = operator_console_readback_bounded_by_control_plane_utc`,
and every console reading is taken by the operator, not inferred from a later
state.

**Phase 0 - discovery, before anything changes.** The minimum settable cap is not
known, and whether a cap at or below current spend is what produces a refusal is
not known. Read the console and record what the interface actually permits.
Current spend is near zero because the project holds no API keys and the
first-exchange run was not billable, so a refusal may require either a cap of
zero or a small deliberate spend first. Decide this from the reading, not from
this document.

**Phase 1 - operational acceptance.** With the cap as it stands, make one
billable call through the neutral launcher and record that it succeeds. This is
A132's required baseline control: it establishes the path worked before the
change, inside the same bounded window as the attestation's own capture.

**Phase 2 - temporary refusal.** Capture the budget state, make the console
change, capture it again, then repeat the identical call and record the refusal.
The request must be byte-identical to phase 1's; Anthropic's result pins one
`request_sha256` across all three phases for exactly this reason.

**Phase 3 - restored acceptance.** Restore the cap, capture before and after,
and repeat the identical call. Under A132 this bracket is the entire causal
argument, not corroboration for a readback that does not exist. Without phase 3,
phase 2 is evidence that one call failed, not that the cap refused it.

The settling floor applies unchanged between the console change and the call
that follows it. Console mutations propagate no faster than API ones.

## What must not be pinned

No expected refusal status, error type, error code, message shape or retry
header is enforced before an OpenAI refusal has been observed. A125 governs, and
this project has twice recorded a provider contradicting its own documentation:
Anthropic's retired-key denial is `401 authentication_error` where the
documentation predicts `400 invalid_grant`, and OpenAI accepted a self-hosted
issuer that its token-exchange reference says is unsupported.

Ship the refusal predicate unenforced, record what arrives, and enforce a
descended predicate in a later reviewed change.

## Two parties

A132 requires the attestation to record the actor that performed the change and
the named person who attests to it. The actor here is a person working in a
console rather than a model, which is the case the rule's wording does not
settle. Resolve who the second party is before the run, not after; an
attestation is by construction the one record nothing can check.

## Provenance

The attestation and the result both carry the provenance mark. The result-level
mark is binary: requirement 2's causal chain runs through a console-only
mutation, so `mutation_receipt_obtained` is false for the requirement regardless
of how much of the surrounding state is receipt-backed. The mark is permanent
and creates no duty to re-derive if OpenAI later exposes a budgets API.
