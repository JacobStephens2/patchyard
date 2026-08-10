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
   no provider name. It has not been built.

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

A133 recorded that the launcher names Anthropic in three places. It is
materially more than that: 30 occurrences in the launcher, 24 in the guest
runner, 26 in the one-shot client. The occurrences A133 did not name are the
expensive ones, because they are not string constants but structure:

- line 180 writes `api.anthropic.com` into the worker's hosts file;
- lines 213-274 name the entire egress firewall `eta_anthropic_one_shot` - table,
  three chains, three sets and two counters;
- line 457 asserts that the provider host set *is* exactly `api.anthropic.com`.

An OpenAI request cannot leave that worker. This is a sequencing fact, not a
defect: A133 already ruled the neutral launcher must be built, and this is the
first requirement that cannot proceed without it.

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
