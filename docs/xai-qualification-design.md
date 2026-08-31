# xAI A-5 qualification: fixture designs (issue #358 step 4)

This is the design record for xAI's six A131 requirements, written before any
collector, checker, or Result exists. It is not normative the way
`docs/anthropic-lifecycle.md` and `docs/openai-lifecycle.md` are; when the
fixtures land, this file's content moves into `docs/xai-issuance.md`,
`docs/xai-spend-enforcement.md`, and `docs/xai-lifecycle.md`, preserving the
four-plus-two derivation A131 relies on to make the enumeration checkable.
Where a design below needs a ruling that does not exist yet, the gap is named
in "Open rulings" rather than papered over.

## The credential shape, and what it changes

xAI is the first provider whose credential is a **static team-scoped API
key** rather than a workload-identity exchange. There is no assertion, no
signing key, no token endpoint, no per-attempt bearer with its own expiry.
The provisioned state (recorded in the A113 clause-3 record taken at
creation, 2026-08-31) is:

- a dedicated Factory team, **Patchyard Factory**, id
  `24472de3-304e-46ae-824b-2f99ffb3aed8`, with a verified $0.00 prepaid
  balance;
- one API key, `factory-arbiter-seat`, created 2026-08-31, landed at
  `/etc/patchyard/xai-seat.key` (`root:root` 0600);
- the mint path (`patchyard-mint-xai-seat-bearer` behind
  `patchyard-xai-seat-mint@.service`) staging the bearer to
  `/run/patchyard-seats/<agent-id>/bearer` at `factory-manager:factory`
  0600, smoke-tested the same day (`factory-manager:factory:600 84`);
- **no effective postpaid spending limit yet**: a desired soft limit of 1000
  USD cents was POSTed to the management API and clamped by a 0
  `hardSlAuto`; every limit field still reads `"0"`. Requirement 2 is
  blocked on a nonzero `effectiveSl` readback.

Three consequences follow for the six requirements:

1. The **bearer is the key**. "Issuance" is the mint's root boundary
   delivering a copy into a supervisor-owned stage, not a provider minting
   anything. The provider-attested half of requirement 1 is therefore a
   provider call accepting the delivered bearer, and nothing else.
2. Requirements 4 and 5 name mechanisms xAI does not have
   (federation rules, signing keys). Issue #358 already carries the A113
   adaptation for revocation - key deletion in the xAI console followed by a
   provider denial, positive call before - but requirement 5's "A-14
   signing-key rotation path" has no stated analogue. The design below
   proposes one and flags the ruling it needs.
3. Unlike OpenAI's console-only workload identity (the case A132 was ruled
   for), xAI exposes a **management API for exactly the mutations these
   fixtures perform**: API-key create/delete and spending-limit get/set. A
   mutation performed through it returns a response and supports an
   independent readback - a receipt, in A132's terms. The designs below
   prefer the management API for every mutation so the attestation machinery
   and its provenance mark are mostly unnecessary; the console is the
   fallback, and any console-only mutation takes the full A132 shape
   (baseline control, bounded before/after capture, two parties, bracket).

The management key that authorizes the management API is itself a
credential. Each fixture that needs one has the operator create it
immediately before the run and delete it immediately after, and it crosses
the evidence boundary the way every other credential does: never.

## Requirement 1: issuance and delivery

**Claim.** The mint delivers the bearer to the supervisor identity under the
postconditions the seat build pinned, and the provider accepts that
delivered bearer. Nothing about how the key was provisioned - that is the
clause-3 record's job, and A136's logic applies: the provider's answer under
its own request id carries the claim directly.

**Fixture.** One run, two halves:

- *Delivery*: request a seat stage through the production requester path
  (requester -> Polkit -> `patchyard-xai-seat-mint@.service` -> mint),
  then record the postconditions as observed facts: owner, group, mode,
  byte length, stage path shape, and the mint's own fail-closed checks
  having passed. Negatives mirror Anthropic's delivery block: the key file
  itself not delivered anywhere else, no admin credential delivered, stage
  removed at teardown with zero credential files remaining.
- *Issuance (provider half)*: one call to a free endpoint with the staged
  bearer - `GET https://api.x.ai/v1/models` - recording HTTP status,
  provider request id, and the presence of the arbiter seat's pinned model
  id (`grok-4.5`) in the listing. A free endpoint keeps requirement 1 cheap
  to re-run, the property A142 names for Anthropic's `/v1/models?limit=1`.

**Consumer note.** This credential's consumer is the control-plane arbiter
seat, not the worker plane. Requirement 1 therefore runs on the control
plane under the supervisor identity, with no capability envelope and no
worker; the execution-plane field count for this Result is zero, and the
Result says so the way `docs/openai-lifecycle.md` counts fields.

**Recorded**: times, request id, HTTP status, model id, stage postconditions,
byte length. **Never**: the key, the response body.

## Requirement 2: provider-side spend enforcement - blocked

**Precondition (A113 clause 3).** A nonzero `effectiveSl` read back from
`GET /v1/billing/teams/<id>/postpaid/spending-limits`, and a $0.00 prepaid
reading taken at qualification time. Both readings are part of the Result.
Neither exists yet: `hardSlAuto` is 0 for this new team and clamps any
desired soft limit. The unblock is one of the paths in "Open rulings".

**Fixture (designed now, runnable after the unblock).** The A115 shape
transfers: a controlled acceptance-refusal sequence on the same surface with
the same request body, with independently timestamped limit readbacks. The
xAI version is simpler than Anthropic's because the mutation half carries
receipts:

1. Readback: spending limits (nonzero `effectiveSl`) and prepaid balance
   ($0.00), each timestamped. The zero-prepaid reading is what makes the
   postpaid limit binding - a team carrying credit defers enforcement until
   the credit is gone, which is exactly what A113 clause 3 excludes.
2. Baseline acceptance: a minimal chat completion against `grok-4.5` under
   the limit, recorded by status, request id, and usage arithmetic.
3. Drive settled postpaid spend past the soft limit with the cheapest
   available requests.
4. Provider refusal: the denied request's status, error shape (sanitized),
   and request id.
5. The **measured overshoot as an observed figure with no preset ceiling**
   (A113 clause 2): settled spend at refusal minus the limit. The first
   qualification establishes the baseline.

**Usage arithmetic caveat.** xAI publishes no cache-write price and caching
cannot be disabled (`research/model-rates/2026-08-26-xai-prompt-caching.md`);
`cached_tokens` is the reported field. The spend arithmetic in steps 2-5
must therefore tolerate cached-token discounts in the observed spend rather
than predicting request cost from list price.

**Cost bound.** Driving spend past even a $10 soft limit is real money. The
fixture should set the soft limit to the smallest value the provider
accepts before the run, and the overshoot figure is measured against that.

## Requirement 3: credential expiry denial

**The A113 clause-1 semantics do not transfer literally.** They were written
for per-attempt WIF bearers ("an expiry no later than the five-minute worker
attempt"). A static key has no per-attempt bearer; the seat key itself is
deliberately non-expiring. What xAI does offer is **key-level expiry set at
creation** (the console's create dialog carries an Expiry field, default "No
expiry").

**Fixture (needs ruling 2).** A dedicated probe key on the same team,
created with the shortest expiry the console or management API accepts,
exercised through the same staged-bearer path:

1. Positive call with the probe key before expiry (status, request id).
2. Wait past the recorded `expires_at`.
3. Denial after expiry (status, sanitized error shape, request id).
4. Positive control with the seat key after the denial, proving the denial
   is the probe key's expiry and not a team-wide or endpoint cause - the
   A129 bracketing logic, carried over because it is what makes the denial
   *about expiry*.

The probe key is deleted at the end of the run regardless of outcome.
**Recorded**: creation and expiry times, all four calls. **Never**: either
key.

## Requirements 4 and 5: key revocation and rotation, jointly

**Proposed as one artifact**, `xai-revocation-rotation.json`, with
`qualification_requirement` naming both - Anthropic's precedent, and A131
says explicitly that six requirements are not six files.

**Revocation (requirement 4's analogue, per issue #358).** The mutation is
key deletion, performed through the management API so it carries a receipt
and a readback (the key list no longer contains it):

1. Baseline control: positive call with the seat key (A132(5), kept even
   though the mutation has a receipt - it is cheap and the bracket is the
   causal argument).
2. Delete `factory-arbiter-seat` via the management API; record the
   response and an independent key-list readback.
3. Provider denial with the deleted key (status, sanitized shape, request
   id). The residual window between deletion and first denial is recorded
   as an observed figure, mirroring A113 clause 1's bounded-window logic.

**Rotation (requirement 5's analogue - needs ruling 1).** A-14's rotation
path exists so a credential can be replaced without a gap the adversary can
use and without the old credential remaining valid. For a static-key
provider the honest analogue is **key replacement end-to-end**:

4. Create a successor key on the same team via the management API (receipt
   plus readback).
5. Land it at `/etc/patchyard/xai-seat.key` through the same attended
   root install the first key used. This step is a human at a root shell;
   it is recorded as times and the file postconditions, exactly like the
   clause-3 landing.
6. Positive call through the production mint path with the successor key -
   proving the whole chain (console to mint to stage to provider) survives
   rotation.

The sequence is deliberately ordered denial-before-successor so the run
never holds two valid keys, and the old key's denial (step 3) plus the
successor's acceptance (step 6) bracket the rotation the way A129's
thirteen-event sequence brackets Anthropic's.

**Sequencing warning.** Step 2 destroys the live arbiter seat until step 5
re-lands a key. This fixture runs **last** of the five runnable
requirements, and the restore-drill behavior (a drill host never carries
the key) already tolerates the file's absence.

## Requirement 6: crash cleanup (A130)

The existing pattern transfers almost unchanged, because the thing being
proven is local: a collector that stages a bearer, checkpoints an
in-progress record at `/run/patchyard-xai/<run_id>/crash-attempt.json`,
is SIGKILLed mid-run, and then proves non-recoverability - with the
`in_progress_record` digest bound at checkpoint, after kill, and at
collection, and `checker_rejections` pinning exactly three xAI checkers
that must each reject the in-progress record.

**The one xAI-specific honesty requirement**: for WIF providers the crashed
bearer was ephemeral, so local non-recoverability meant the credential was
gone. Here the staged bearer is a *copy* of a long-lived key that continues
to exist at `/etc/patchyard/xai-seat.key` (root-only) and at the
provider. The Result must claim only what is true: the supervisor-readable
staged copy is non-recoverable after the crash, and the root-owned source
is outside the crashed identity's reach. It must not claim the credential
ceased to exist, because it did not.

## Artifacts this design implies

Mirroring the Anthropic/OpenAI inventory, xAI needs: an entry in
`policy/provider-qualification.json`; collectors under `tools/xai-*`;
per-requirement checkers `tools/check-xai-*.py` wired into
`tools/check-infra.sh` (not into `check-ansible.sh`, whose list is
digest-bound); `RESULT_SHAPES` entries in `tools/factory_checker_runtime.py`;
accepting and rejecting contract Fixtures under `fixtures/checker-contracts/`
(each carrying `provider_response_observed: false`,
`qualification_evidence: false`); Results under
`research/isolation/results/xai-*.json`; and, at flip time, the
`PROVIDER_RESULTS["xai"]` bindings in `tools/check-credential-qualification.py`
covering requirements 1-6 arithmetically. The clause-3 record moves from the
repo root to `docs/` when the requirement-2 Result cites it.

## Open rulings, before fixtures run

1. **Requirement 4/5 semantics for a static-key provider.** Does key
   deletion (with receipt and bracket) satisfy "federation-rule
   revocation", and does end-to-end key replacement satisfy "signing-key
   rotation, the A-14 path", jointly evidenced in one artifact? This is an
   A113-style substitution - a bounded, provable property standing in for a
   mechanism the provider does not have - and wants the same explicit
   treatment A115 gave Anthropic's workspace pause.
2. **Requirement 3 expiry semantics.** The clause-1 expiry text is
   WIF-specific. Ruling wanted: a probe key with provider-set expiry,
   bracketed as designed above, is the static-key expiry proof; the
   non-expiring seat key is not itself a defect.
3. **The requirement-2 unblock.** `hardSlAuto` is 0 and clamps the soft
   limit. Either xAI enables invoiced billing for the team (the documented
   path is contacting sales), or a small prepaid purchase spent to zero
   before qualification unlocks postpaid history. The second path needs a
   reading of A113 clause 3: the clause requires zero prepaid *checked at
   qualification*, and a purchase spent to exhaustion beforehand arguably
   satisfies the letter while touching the reason the clause exists. Not
   decided here.
4. **Management-API mutations as receipts.** The designs read A132 as
   attaching attestation only where "no provider receipt can be obtained",
   which the management API's response-plus-readback satisfies. If that
   reading is wrong, every mutation above takes the attestation shape
   instead; the fixtures' sequences do not change, only their record shape.

## Sequencing

1 (cheap, non-destructive) -> 6 (local, no provider mutation) -> 3 (probe
key only) -> 4+5 (destroys and replaces the seat key; last of the runnable
four) -> 2 when the limit unblocks. Requirement 2 is independent of the
other five and can slot in whenever `effectiveSl` reads back nonzero.
