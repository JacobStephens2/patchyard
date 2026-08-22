# Anthropic A-5 lifecycle proofs

## Status and boundary

This source implements the A113 expiry-denial and federation-rule-revocation
halves, the A-14 signing-key rotation path, and A130's crash-cleanup procedure.
The expiry proof ran on
2026-08-04 and the rule-removal/restoration proof ran on 2026-08-05. Two
attended rotation runs followed on 2026-08-05.

The first, `anthropic-l3-20260805-27e8a245ed`, completed events 1 through 9 and
11 of the then-current sequence, but the event-10 admin command failed after
the provider accepted issuer retirement because its immediate GET returned the
stale two-key state. The failed event could not enter that eleven-event
fixture, so the run assembled no result. It did produce the first observation
of the retired-key denial.

The second, `anthropic-l3-20260805-5ed79595e2`, ran after that race was fixed
and completed all eleven events in the old shape. That result is preserved in
git history and was superseded at the canonical path by run
`anthropic-l3-20260805-68e104a18d`, which completed A129's thirteen-event
sequence. Its post-retirement active/denial/active bracket closed in 1.02
seconds, within the 120-second bound, and the default checker accepts the
current result as conforming qualification evidence.

**Rotation is qualified.** The retired-key denial is bracketed by two
active-replacement exchange-and-Models controls at the stable path. A128's
separate provenance limitation is unchanged: the checker proves internal
consistency, not that each recorded value came from the provider call it names.
That limitation also applies to requirement 1, requirement 2, and the expiry
denial.

The A130 crash-cleanup procedure and checker have not run live and qualify
nothing. All 13 provider `credential_qualified` flags remain false. Any further
live execution, provider mutation, key activation, evidence
publication, fixture refresh, or qualification-flag change requires a new
authorization after adversarial review.

The implementation is intentionally outside the existing host contract. It
does not call or modify:

- `worker/qualification/patchyard-run-anthropic-issuance`;
- `worker/runtime/patchyard-firecracker-run`;
- `worker/runtime/patchyard-anthropic-one-shot`; or
- any file under `worker/image/`.

`tools/anthropic-wif-lifecycle.py` is the source-pinned root-only control-plane
harness used by the qualified expiry result. The smaller
`tools/anthropic-wif-revocation.py` adapter loads that exact harness, records
the revocation-specific denial fields and positive-exchange start times, and
allowlists the two A129 post-retirement controls. This preserves the expiry
evidence's source binding while making the revocation contract recordable.
`tools/anthropic-wif-crash-cleanup.py` is another source-bound adapter. It uses
the existing reserved output unchanged, holds a validated bearer in a child at
the pre-terminal checkpoint, observes that child's actual wait status from a
separate supervisor, and emits only sanitized metadata from its run-scoped
surface search.
`tools/anthropic-wif-lifecycle-admin.py` is a separate attended operator tool
using the `patchyard-admin` operator admin profile. Access tokens stay
short-lived; `ant auth print-credentials --profile patchyard-admin
--access-token` refreshes them from the stored refresh token. None accepts an
API key: the WIF admin endpoints reject Admin API keys. All strip
ambient Anthropic credential variables, reject HTTP redirects and ambient
proxies, use fixed Anthropic endpoints, write only to a new mode-0600 file, and
never emit an assertion or bearer. Bearer-bearing proof actions make no retry.
The admin tool alone retries safely sanitized post-mutation state mismatches
within a bounded readback deadline.

Every mutating or bearer-bearing command reserves its output before the first
provider or local operation. The initial record says `status: in_progress`.
A successful command atomically replaces it with the qualifying event. A
caught failure atomically replaces it with `status: failed`, the failure phase,
credential-free partial provider observations, and local state or an
independent provider readback where mutation was possible. An abrupt process
death leaves the `in_progress` record. Neither terminal form can pass a
complete live evidence contract; the A126 observation-only mode validates one
sanitized denial predicate and says explicitly that it is not qualification
evidence. Failure to persist or fsync the terminal record is itself a nonzero
result. The root harness also rejects any output or temporary private
key outside the exact root-owned mode-0700
`/run/patchyard-anthropic/<run-id>` directory and verifies that `/run` is
`tmpfs` before reserving an output.

When a provider mutation was accepted but its readback does not validate, the
admin terminal record keeps `failed_validation_response`, containing the
sanitized receipt and state that failed, separately from the fresh
`post_failure_readback`. Issuer responses retain only key IDs and public-key
thumbprints; JWK modulus and additional provider-field values do not enter
either record.

The administrative primitives follow Anthropic's documented WIF surface:
removing a rule workspace disables that mapping, adding it restores the same
mapping, and a partial issuer update replaces the complete inline JWKS. The
live rule-disabled exchange returned HTTP 401 `authentication_error`, not the
documented HTTP 400 `invalid_grant`. The retired-signing-key exchange at
`/v1/oauth/token` likewise returned HTTP 401 `authentication_error`,
contradicting the documented HTTP 400 `invalid_grant`; that observed contract
is now enforced. See the official
[WIF Admin API](https://platform.claude.com/docs/en/manage-claude/wif-admin-api),
[rule-workspace removal](https://platform.claude.com/docs/en/api/admin/federation_rules/workspaces/delete),
[rule-workspace addition](https://platform.claude.com/docs/en/api/admin/federation_rules/workspaces/create),
[issuer update](https://platform.claude.com/docs/en/api/admin/federation_issuers/update),
and [WIF error reference](https://platform.claude.com/docs/en/manage-claude/wif-reference).

## Evidence contracts

### Expiry

`research/isolation/results/anthropic-expiry-denial.json` is the committed
2026-08-04 live result. Its exact top-level shape is:

```text
schema_version, provider, qualification_requirement, authorization_ruling,
run_id, signing_key, issuance, positive_control, expiry_denial,
credential_removed_at, policy_sha256, lifecycle_harness_sha256
```

The checker requires all of the following:

- one successful WIF exchange with `expires_in` from 60 through 300 seconds;
- one successful `GET /v1/models?limit=1` before the provider-recorded expiry;
- exactly one reuse of that same bearer after expiry, denied by Anthropic as
  HTTP 401 `authentication_error`, explicitly recording that no request ID was
  supplied;
- strict capture and provider order
  `issued <= positive < expiry <= denial <= credential removal`;
- two distinct provider request IDs bracketing the unidentified denial;
- current policy and harness digests; and
- no credential-shaped field, bearer, or JWT.

The denial's `source` must be `anthropic_http_response`. A cleanup event cannot
occupy that field.

### Federation revocation and signing-key rotation

`research/isolation/results/anthropic-revocation-rotation.json` was assembled by
run `anthropic-l3-20260805-68e104a18d` in A129's thirteen-event shape. The
accepted result binds the current policy, qualified expiry harness, revocation
adapter, and administrative tool digests and contains these exact, strictly
ordered events:

| Order | Event | Required fact |
| :-- | :-- | :-- |
| 1 | `rule_enabled_positive` | Current key exchanges and calls Models. |
| 2 | `rule_disabled` | The one Factory workspace mapping is removed and read back absent. |
| 3 | `rule_disabled_exchange_denial` | After the settling floor, the next fresh assertion receives provider HTTP 401 `authentication_error`. |
| 4 | `rule_restored` | The same mapping is restored and read back present. |
| 5 | `rule_restored_positive` | After the settling floor, exchange and Models prove restoration. |
| 6 | `issuer_rotation_staged` | Provider JWKS changes from old-only to exactly old+replacement. |
| 7 | `replacement_key_positive` | After the settling floor, the staged replacement key exchanges and calls Models. |
| 8 | `replacement_key_activated` | The old private key is retained only in root tmpfs for its denial, then the replacement is atomically installed at the active path. |
| 9 | `replacement_key_final_positive` | The active path exchanges and calls Models while both public keys remain trusted. |
| 10 | `issuer_retired_key` | Provider JWKS changes from exactly old+replacement to replacement-only. |
| 11 | `post_retirement_active_positive` | After the settling floor, the active replacement key at the stable path exchanges and calls Models. |
| 12 | `retired_key_exchange_denial` | A fresh assertion signed by the retired key receives provider HTTP 401 `authentication_error`. |
| 13 | `post_retirement_active_positive_final` | The active replacement key at the same stable path exchanges and calls Models again. |

The checker requires 20 distinct bracketing request IDs from the positive and
administrative calls. Both observed exchange denials supplied distinct
identifiers, so this contract requires 22 distinct identified provider requests
in total. Each denial still records `request_id_supplied`; an absent identifier
is an explicit observation, but cannot qualify this observed rotation contract.
The checker also
requires exact rule and issuer state transitions, continuity of both public-key
thumbprints, and five-minute-or-shorter bearers for every positive control. The
adapter fixes all three post-retirement token exchanges to the same endpoint
and policy state; the checker requires the controls to bind the active
replacement and the denial to bind the retired key. The locally atomic
activation is required but never substitutes for either provider denial.

Every exchange that immediately tests a provider configuration mutation has a
90-second minimum settling interval from the preceding administrative readback
to `request_started_at`: both denials, the restored-rule positive, the
staged-replacement positive, and both post-retirement controls. An attempt
started sooner fails as inconclusive, regardless of its HTTP result. This is
the smallest directly observed interval that produced the enforced rule
denial: 0.85 seconds was too early, while the accepted observation began
90.867688 seconds after the disabled-state readback. It is a qualification
floor, not a provider propagation SLA. The initial positive has no preceding
mutation; the final replacement positive follows local atomic activation after
the staged provider state was already settled and proven. Rollback events
terminate the attempt and are not qualification-event predecessors.

After issuer retirement, the first active control, retired-key denial, and
final active control must be serial and complete within one 120-second window,
measured from the first control's exchange `request_started_at` through the
final control's Models `observed_at`. The first Models call must complete before
the denial begins, and the denial must complete before the final exchange
begins. Five serial HTTPS calls plus attended command entry can comfortably
finish within two minutes, while the bound is short enough that a longer-lived
authentication fault cannot masquerade as a retirement-only denial. Event 3
needs no added controls: its mapping mutation is already applied after event 1
and reversed before event 5.

The administrative state readback is a separate bounded operation. After any
rule or issuer mutation, the admin tool polls immediately, then after 0.25,
0.5, 1, and at most 2 seconds between later attempts until the complete target
state appears or a 90-second monotonic deadline expires. A converged first GET
adds no delay. A state that never converges still fails closed, preserving the
last mismatching response and an independent post-failure readback. This retry
does not replace the 90-second settling floor before exchange or Models tests.

`fixtures/provider-observations/anthropic-revocation-denial-2026-08-05.json`
is byte-identical to the credential-free terminal capture from the live rule
proof. The observation-only checker mode validates the corrected response
predicate without treating that failed terminal record as complete
qualification evidence:

```bash
python3 -I tools/check-anthropic-revocation.py \
  --observed-denial fixtures/provider-observations/anthropic-revocation-denial-2026-08-05.json
```

`fixtures/provider-observations/anthropic-retired-key-denial-2026-08-05.json`
is byte-identical to the credential-free old event-11 observation, now event 12
in the canonical sequence. Its digest is pinned in the test suite, and its HTTP
status, error type, and sanitized response shape drive the denial predicate.
`fixtures/checker-contracts/anthropic-revocation-thirteen-event.json` is the
complete synthetic thirteen-event satisfiability fixture accepted by the
actual checker. Its positive shapes descend from positive events in the
recorded run, while its identifiers and times are explicitly synthetic. It is
not a live rotation result and makes no provider-observation or qualification
claim.

`infra/ansible/tests/test_anthropic_lifecycle.py` invokes the actual isolated
checkers against a valid contract and then mutates it. Both checkers reject a
fabricated denial, a missing positive control, a local-cleanup-only record, and
an out-of-order timestamp. The same tests exercise exact rule disable/restore,
two-key staging, retirement, and both rotation rollback paths with a fake API.
`fixtures/checker-contracts/anthropic-revocation-positive-settling.json`
demonstrates all four post-mutation positive settling predicates. It is explicitly
synthetic and timing-only: it contains no provider response and makes no
provider-observation or qualification claim.

### Crash cleanup

The future live result path is
`research/isolation/results/anthropic-crash-cleanup.json`. It does not exist yet.
The exact result binds the policy, qualified lifecycle harness, and crash
adapter, and records:

- a successful exchange checkpoint with the bearer still held in the child,
  before any terminal write, with core dumps disabled and no configured swap;
- a positive search that observes both the live child and the distinct private
  key genuinely staged at `replacement.pem`;
- the supervisor's observed child return code `-9`, signal name `SIGKILL`, and
  absence of that exact PID/start-time identity afterward, followed immediately
  by its removal and directory-fsync of the run-scoped private key;
- the identical bounded search over the identical run directory after that
  automatic key cleanup, finding no bearer, JWT assertion, or private key;
- the byte-identical `status: in_progress` attempt at checkpoint, after
  `SIGKILL`, and at collection, with no terminal fields; and
- exit 1 from every Anthropic checker that accepts a caller-supplied evidence
  path. The fixed-result issuance and spend checkers have no such input path.

The search is one implementation, not two similarly named commands. Both
captures use `scan` with the same checkpoint; only their new output filenames
differ. Its contract fixes the root, target PID/start time, recursive regular-file
surface, material classes, and byte/file ceilings. The positive control must
find exactly the real run-scoped `replacement.pem`, not a generated canary or a
different directory. A missing key, a broken scanner returning zero, a symlink,
an unreadable/special entry, enabled scanner core dumps, configured swap, or a
changed search contract fails closed.

The bearer and assertion exist only in the credential process. The distinct
private key and every adapter output exist only in that run's verified tmpfs
directory. Process absence, disabled core dumps, zero swap, and the empty
post-kill filesystem search therefore compose the bounded local
non-recoverability result. This proof concerns the Anthropic credential in
flight; it does not claim that an unrelated stable signing identity elsewhere
on the control plane disappeared.

This boundary is mandatory in both evidence and prose: **the killed bearer can
remain valid at Anthropic until its natural expiry**. Anthropic exposes no
per-bearer revocation operation. Local crash cleanup proves no provider denial
and no provider-side invalidation. The separately qualified expiry result bounds
that residual provider exposure to five minutes or less; neither guarantee may
be substituted for the other.

`fixtures/checker-contracts/anthropic-crash-cleanup.json` is the labeled
synthetic satisfiability case. Its staged-key issuance shape descends from the
observed `replacement_key_positive` event in the current rotation result; its
local PID, times, and search outcome are synthetic. It carries
`fixture_kind`, `provider_response_observed: false`, and
`qualification_evidence: false`. Contract-fixture mode accepts it, while the
qualification path rejects that same file explicitly. The isolated lifecycle
tests also reject SIGTERM, a missing or vacuous positive control, any checker
acceptance of `in_progress`, and any credential material in evidence.

## Attended live procedure: expiry

Do not run this section without a post-A78 live authorization. Before starting,
confirm that requirement 2 is not running, the reviewed revision is deployed
to the control plane, its checkout is clean, all 13 `credential_qualified`
flags remain false, and the four protected source digests still pass both new
checkers in static mode.

On the control plane, from the exact deployed checkout:

```bash
cd /opt/patchyard
RUN_ID="anthropic-l3-$(date -u +%Y%m%d)-$(openssl rand -hex 5)"
CONTROL_STAGE="/run/patchyard-anthropic/$RUN_ID"
sudo install -d -m 0700 -o root -g root "$CONTROL_STAGE"
sudo python3 -I tools/anthropic-wif-lifecycle.py expiry \
  --run-id "$RUN_ID" \
  --output "$CONTROL_STAGE/anthropic-expiry-denial.json"
```

The command performs one positive exchange, one Models call, waits through the
recorded bearer expiry, performs one post-expiry Models attempt, and exits. It
does not use the worker or guest. Copy only the resulting JSON through the
reviewed management path, then on the orchestration host run:

```bash
python3 -I tools/check-anthropic-expiry.py \
  --evidence /absolute/path/anthropic-expiry-denial.json
```

Stop without retry if any command fails, the positive control is denied, the
lifetime exceeds 300 seconds, the post-expiry call is accepted, the denial is
not HTTP 401 `authentication_error`, request-ID presence is not recorded
exactly as observed, or the checker rejects the fixture. Never replace a
missing provider denial with cleanup evidence. Preserve only credential-free
diagnostics and remove the root tmpfs directory after adjudication. A `status:
failed` or `status: in_progress` terminal record is failure evidence, not a
result to edit or assemble.

## Prove the operator admin profile

Before any attended federation read or mutation, confirm the profile can mint
a fresh bearer without a browser. On the operator host:

```bash
ant --profile patchyard-admin auth print-credentials --access-token >/dev/null
ant --profile patchyard-admin auth status
export ANTHROPIC_OAUTH_TOKEN="$(
  ant --profile patchyard-admin auth print-credentials --access-token
)"
curl --fail-with-body -sS \
  "https://api.anthropic.com/v1/organizations/federation_issuers/fdis_01A8wjwFPKfutAGtFN3oqF8J" \
  --header "anthropic-version: 2023-06-01" \
  --header "authorization: Bearer $ANTHROPIC_OAUTH_TOKEN"
unset ANTHROPIC_OAUTH_TOKEN
```

`auth status` must show scope `org:admin` and a future expiry. The issuer GET
must return HTTP 200. If `print-credentials` cannot refresh, re-login; do not
open a browser for a one-shot access token and do not substitute an Admin API
key:

```bash
ant auth login --profile patchyard-admin --scope org:admin --no-browser
```

Do not mint a federated `org:admin` token for this path. Diagnosis must not
depend on the federation it is inspecting.

## Attended live procedure: rule revocation and restoration

Do not run this section without a separate live authorization. Use one fresh
run ID and fresh mode-0700 staging directories on the control plane and
operator host. Every `--output` path below must be new. Transfer only JSON event
files and public JWKS files between hosts. On the attended operator host:

```bash
umask 077
RUN_ID="anthropic-l3-$(date -u +%Y%m%d)-$(openssl rand -hex 5)"
ADMIN_STAGE="$(mktemp -d /tmp/patchyard-anthropic-admin.XXXXXXXXXX)"
test "$(stat -c '%a' "$ADMIN_STAGE")" = 700
```

Carry that exact `RUN_ID`, but no credential, to the control plane and create
its root tmpfs directory:

```bash
cd /opt/patchyard
RUN_ID="anthropic-l3-YYYYMMDD-0000000000" # exact value from the operator host
CONTROL_STAGE="/run/patchyard-anthropic/$RUN_ID"
sudo install -d -m 0700 -o root -g root "$CONTROL_STAGE"
```

First prove the enabled rule from the control plane:

```bash
sudo python3 -I tools/anthropic-wif-lifecycle.py exchange-positive \
  --run-id "$RUN_ID" --event-type rule_enabled_positive \
  --key-role active --output "$CONTROL_STAGE/01-rule-enabled-positive.json"
```

On the operator host, inspect the exact read-only plan, then apply the one
workspace-mapping removal:

```bash
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin rule-disable --run-id "$RUN_ID"
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin --apply \
  --output "$ADMIN_STAGE/02-rule-disabled.json" \
  rule-disable --run-id "$RUN_ID"
```

After the apply command returns its disabled-state readback, wait at least 90
seconds. Starting from command completion is conservative because completion
follows that readback:

```bash
/usr/bin/sleep 90
```

Then make exactly one fresh exchange attempt from the control plane. The
checker measures from the readback's `observed_at` to the denial's
`request_started_at`; an attempt inside 90 seconds is inconclusive, not a
provider result:

```bash
sudo python3 -I tools/anthropic-wif-revocation.py exchange-denial \
  --run-id "$RUN_ID" --event-type rule_disabled_exchange_denial \
  --key-role active --output "$CONTROL_STAGE/03-rule-disabled-denial.json"
```

Restore the mapping even if that denial command failed. Review the plan, apply,
wait through the same propagation floor after its readback, and prove provider
access:

```bash
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin rule-restore --run-id "$RUN_ID"
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin --apply \
  --output "$ADMIN_STAGE/04-rule-restored.json" \
  rule-restore --run-id "$RUN_ID"
/usr/bin/sleep 90
sudo python3 -I tools/anthropic-wif-revocation.py exchange-positive \
  --run-id "$RUN_ID" --event-type rule_restored_positive \
  --key-role active --output "$CONTROL_STAGE/05-rule-restored-positive.json"
```

If the disable command fails after its provider request, immediately run the
restore plan. If it plans a restore, apply it. If it rejects because the rule
is already enabled, run the disable plan only as a readback confirmation and
stop. If neither exact state validates, stop and escalate. Never continue into
rotation without the restored admin readback and restored provider positive.
Never retry the denied exchange. Preserve the failed admin terminal record: it
contains a fresh readback or states that the readback itself failed.

The A126 capture was produced by the source-pinned expiry harness while it
still expected `400 invalid_grant`, so it is a `status: failed` terminal
observation. The observation-only checker mode proves the corrected denial
predicate, but that record must not be substituted for the complete event or a
qualification result. Future denial events use the revocation adapter above.

### Rotation pre-flight audit

Before A126, rotation specified no settling interval after either provider
JWKS mutation. The staged-replacement positive and retired-key denial followed
their administrative readbacks immediately. The procedure below now waits 90
seconds after each readback. After retirement, the checker measures both active
controls and the retired-key denial from the same readback. Atomic local
activation needs no propagation wait: it changes no provider state, and both
public keys have already been read back and proven as trusted.

The 2026-08-05 attempt supplied the first captured retired-key response. The
provider returned HTTP 401 `authentication_error`, rather than the documented
HTTP 400 `invalid_grant`, and the checker now pins the observed response. Its
complete synthetic acceptance case reaches exit 0.

The same attempt did not produce a complete live fixture. The issuer-retire
POST was accepted, but the immediate GET returned the stale two-key state and
the admin tool raised while validating the expected one-key state. Its terminal
record is therefore a failure event, even though its fresh failure-path readback
then saw the replacement-only state. Events 1 through 9 and 11 cannot be
assembled around a failed event 10. The bounded admin readback retry addresses
that race for a clean re-run; it does not convert the incomplete attempt into
qualification evidence.

The later `anthropic-l3-20260805-5ed79595e2` run completed the old eleven-event
shape and remains recorded. It predates A129's controls, so it is not a current
acceptance case and cannot be upgraded by adding the separate positive that ran
afterward. The default checker rejects it; static preflight accepts only its
exact pinned digest so preserving the historical file does not hold CI red.

The qualified expiry result binds the existing lifecycle harness digest, so
changing that file would invalidate requirement 3 while fixing requirement 4.
The source-bound revocation adapter is the narrow compatibility boundary: for
post-mutation positives it adds `request_started_at`; for denials it records
that timestamp and explicit request-ID presence, and enforces both observed
denial responses. It also allowlists A129's two active-key control event types
without changing the lifecycle harness.

## Attended live procedure: signing-key rotation

Continue under the same live authorization only after rule restoration passed.
On the control plane, derive the current public JWKS, generate a replacement in
root tmpfs, and derive its public JWKS:

```bash
sudo python3 -I tools/anthropic-wif-lifecycle.py jwks \
  --run-id "$RUN_ID" \
  --signing-key /etc/patchyard/anthropic-wif-signing.pem \
  --output "$CONTROL_STAGE/current-jwks.json"
sudo test ! -e "$CONTROL_STAGE/replacement.pem"
sudo install -m 0400 -o root -g root /dev/null \
  "$CONTROL_STAGE/replacement.pem"
sudo openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out "$CONTROL_STAGE/replacement.pem"
sudo test "$(stat -c '%U:%G:%a' "$CONTROL_STAGE/replacement.pem")" = root:root:400
sudo python3 -I tools/anthropic-wif-lifecycle.py jwks \
  --run-id "$RUN_ID" \
  --signing-key "$CONTROL_STAGE/replacement.pem" \
  --output "$CONTROL_STAGE/replacement-jwks.json"
```

Copy the two public JWKS files to new absolute paths under `$ADMIN_STAGE`.
Review and apply the overlap update. The tool refuses any provider state other
than the exact current key supplied by `--expected-current-jwks`:

```bash
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin issuer-stage --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin --apply \
  --output "$ADMIN_STAGE/06-issuer-rotation-staged.json" \
  issuer-stage --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
```

Wait through the same conservative propagation floor, then prove the
replacement while the old key still works:

```bash
/usr/bin/sleep 90
```

```bash
sudo python3 -I tools/anthropic-wif-revocation.py exchange-positive \
  --run-id "$RUN_ID" --event-type replacement_key_positive \
  --key-role replacement_staging \
  --signing-key "$CONTROL_STAGE/replacement.pem" \
  --output "$CONTROL_STAGE/07-replacement-positive.json"
```

If this fails, use `issuer-rollback-stage` with the same two JWKS arguments,
review its plan, apply it to a new rollback evidence path, and stop. Do not
activate or retire either key.

```bash
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin issuer-rollback-stage --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin --apply \
  --output "$ADMIN_STAGE/issuer-stage-rollback.json" \
  issuer-rollback-stage --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
```

After the replacement positive, atomically activate it. This operation first
copies the old private key to the named root-only tmpfs path so the retired-key
denial remains possible:

```bash
sudo python3 -I tools/anthropic-wif-lifecycle.py activate-replacement \
  --run-id "$RUN_ID" \
  --replacement-key "$CONTROL_STAGE/replacement.pem" \
  --expected-retired-jwks "$CONTROL_STAGE/current-jwks.json" \
  --retired-key-output "$CONTROL_STAGE/retired.pem" \
  --output "$CONTROL_STAGE/08-replacement-activated.json"
sudo python3 -I tools/anthropic-wif-lifecycle.py exchange-positive \
  --run-id "$RUN_ID" --event-type replacement_key_final_positive \
  --key-role active --output "$CONTROL_STAGE/09-active-replacement-positive.json"
```

If the active-path positive fails, run `rollback-activation` with
`retired.pem` as `--replacement-key`, `replacement-jwks.json` as
`--expected-retired-jwks`, and a new path for the displaced failed key. The
provider still trusts both keys at this point. Stop after rollback.

```bash
sudo python3 -I tools/anthropic-wif-lifecycle.py rollback-activation \
  --run-id "$RUN_ID" --replacement-key "$CONTROL_STAGE/retired.pem" \
  --expected-retired-jwks "$CONTROL_STAGE/replacement-jwks.json" \
  --retired-key-output "$CONTROL_STAGE/failed-replacement.pem" \
  --output "$CONTROL_STAGE/replacement-activation-rollback.json"
```

Only after both replacement positives may the provider retire the old public
key:

```bash
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin issuer-retire --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin --apply \
  --output "$ADMIN_STAGE/10-issuer-retired-key.json" \
  issuer-retire --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
```

Wait at least 90 seconds after the retirement readback. Then run the active
control, retired-key denial, and final active control serially, with no planned
pause between them. All three exchange starts are measured from the retirement
readback, and the first exchange start through the final Models completion must
fit within 120 seconds. An earlier attempt or a longer bracket is
inconclusive:

```bash
/usr/bin/sleep 90
sudo python3 -I tools/anthropic-wif-revocation.py exchange-positive \
  --run-id "$RUN_ID" --event-type post_retirement_active_positive \
  --key-role active \
  --signing-key /etc/patchyard/anthropic-wif-signing.pem \
  --output "$CONTROL_STAGE/11-post-retirement-active-positive.json"
sudo python3 -I tools/anthropic-wif-revocation.py exchange-denial \
  --run-id "$RUN_ID" --event-type retired_key_exchange_denial \
  --key-role retired_staging --signing-key "$CONTROL_STAGE/retired.pem" \
  --output "$CONTROL_STAGE/12-retired-key-denial.json"
sudo python3 -I tools/anthropic-wif-revocation.py exchange-positive \
  --run-id "$RUN_ID" --event-type post_retirement_active_positive_final \
  --key-role active \
  --signing-key /etc/patchyard/anthropic-wif-signing.pem \
  --output "$CONTROL_STAGE/13-post-retirement-active-positive-final.json"
```

If issuer retirement fails ambiguously, do not make any of the three attempts.
Use the `issuer-restore-overlap` plan to determine whether provider state is
replacement-only; apply it only when needed to restore the already-proven
two-key overlap, then stop. Once the first control begins, do not restore the
retired key. If either control fails, the retired assertion is accepted, any
command is retried, or the bracket exceeds 120 seconds, stop and preserve the
terminal records as non-qualifying evidence. The adapter accepts a bounded
provider 4xx so the denial can be preserved without credential material, but
the checker requires the pinned HTTP 401 `authentication_error` contract. Do
not re-trust the retired key merely to make the test pass.

```bash
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin issuer-restore-overlap --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin --apply \
  --output "$ADMIN_STAGE/issuer-retirement-rollback.json" \
  issuer-restore-overlap --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
```

After all three attempts succeed, remove only the two explicitly named tmpfs
private-key copies. The active replacement remains at the stable root-only
path:

```bash
sudo rm -f -- "$CONTROL_STAGE/retired.pem" "$CONTROL_STAGE/replacement.pem"
```

## Assemble and validate the revocation fixture

Place the thirteen sanitized events in one operator directory with the numeric
names above. Assemble only in this exact order:

```bash
jq -e -s --arg run_id "$RUN_ID" '
  . as $events
  | if (map(.event_type)) != [
      "rule_enabled_positive",
      "rule_disabled",
      "rule_disabled_exchange_denial",
      "rule_restored",
      "rule_restored_positive",
      "issuer_rotation_staged",
      "replacement_key_positive",
      "replacement_key_activated",
      "replacement_key_final_positive",
      "issuer_retired_key",
      "post_retirement_active_positive",
      "retired_key_exchange_denial",
      "post_retirement_active_positive_final"
    ] then error("lifecycle event order differs") else . end
  | {
      schema_version: 1,
      provider: "anthropic",
      qualification_requirement: "federation-revocation-and-key-rotation",
      authorization_ruling: "A113",
      run_id: $run_id,
      policy_sha256: $events[0].source.policy_sha256,
      lifecycle_harness_sha256: $events[0].source.lifecycle_harness_sha256,
      revocation_harness_sha256: $events[2].source.revocation_harness_sha256,
      admin_tool_sha256: $events[1].source.admin_tool_sha256,
      events: $events
    }
' \
  01-rule-enabled-positive.json \
  02-rule-disabled.json \
  03-rule-disabled-denial.json \
  04-rule-restored.json \
  05-rule-restored-positive.json \
  06-issuer-rotation-staged.json \
  07-replacement-positive.json \
  08-replacement-activated.json \
  09-active-replacement-positive.json \
  10-issuer-retired-key.json \
  11-post-retirement-active-positive.json \
  12-retired-key-denial.json \
  13-post-retirement-active-positive-final.json \
  > anthropic-revocation-rotation.json
python3 -I tools/check-anthropic-revocation.py \
  --evidence "$PWD/anthropic-revocation-rotation.json"
```

Checker exit 1 rejects malformed evidence. Exit 2 remains reserved for a future
denial event whose provider contract has not yet been observed and pinned; the
current thirteen-event contract has no such blocker, and a valid complete result
reaches exit 0. Do not hand-edit an event, fill a missing request ID, relabel a
local observation, reorder a timestamp, or publish a partial fixture as
success. Files whose top level has `status` are terminal diagnostics rather
than success events and must not be substituted into the thirteen-event list.

## Attended live procedure: crash cleanup

Do not run this procedure without separate authorization for the live exchange
and temporary issuer mutation. It is a dedicated attempt, not an extra event to
splice into an earlier rotation result. Start from an old-key-only issuer state,
use a fresh run ID, and stop if either host checkout differs from the exact SHA
approved for the run.

On the attended operator host, create the operator stage:

```bash
umask 077
RUN_ID="anthropic-l3-$(date -u +%Y%m%d)-$(openssl rand -hex 5)"
ADMIN_STAGE="$(mktemp -d /tmp/patchyard-anthropic-crash.XXXXXXXXXX)"
test "$(stat -c '%a' "$ADMIN_STAGE")" = 700
```

Carry only that run ID to the control plane. Create the exact root tmpfs stage,
derive the current public JWKS, and generate a distinct run-scoped key:

```bash
cd /opt/patchyard
RUN_ID="anthropic-l3-YYYYMMDD-0000000000" # exact operator-host value
CONTROL_STAGE="/run/patchyard-anthropic/$RUN_ID"
sudo install -d -m 0700 -o root -g root "$CONTROL_STAGE"
sudo python3 -I tools/anthropic-wif-lifecycle.py jwks \
  --run-id "$RUN_ID" \
  --signing-key /etc/patchyard/anthropic-wif-signing.pem \
  --output "$CONTROL_STAGE/current-jwks.json"
sudo install -m 0400 -o root -g root /dev/null \
  "$CONTROL_STAGE/replacement.pem"
sudo openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out "$CONTROL_STAGE/replacement.pem"
sudo test "$(stat -c '%U:%G:%a' "$CONTROL_STAGE/replacement.pem")" = root:root:400
sudo python3 -I tools/anthropic-wif-lifecycle.py jwks \
  --run-id "$RUN_ID" \
  --signing-key "$CONTROL_STAGE/replacement.pem" \
  --output "$CONTROL_STAGE/replacement-jwks.json"
```

Copy only `current-jwks.json` and `replacement-jwks.json` to those exact names
under `$ADMIN_STAGE`; never copy `replacement.pem`. On the operator host, review
and apply the temporary two-key overlap, then wait from the returned readback:

```bash
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin issuer-stage --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin --apply \
  --output "$ADMIN_STAGE/crash-issuer-staged.json" \
  issuer-stage --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
/usr/bin/sleep 90
```

Back on the control plane, name every new output and start the supervisor in the
background. The supervisor reserves its own record and launches the credential
child; the child separately reserves `crash-attempt.json` before exchanging:

```bash
ATTEMPT="$CONTROL_STAGE/crash-attempt.json"
CHECKPOINT="$CONTROL_STAGE/crash-checkpoint.json"
POSITIVE="$CONTROL_STAGE/crash-positive-search.json"
KILL_OBSERVATION="$CONTROL_STAGE/crash-sigkill.json"
POST_KILL="$CONTROL_STAGE/crash-post-kill-search.json"
RESULT="$CONTROL_STAGE/anthropic-crash-cleanup.json"
sudo python3 -I tools/anthropic-wif-crash-cleanup.py supervise \
  --run-id "$RUN_ID" \
  --signing-key "$CONTROL_STAGE/replacement.pem" \
  --attempt-output "$ATTEMPT" \
  --checkpoint-output "$CHECKPOINT" \
  --positive-control "$POSITIVE" \
  --kill-output "$KILL_OBSERVATION" &
SUPERVISOR_PID=$!
for _ in $(seq 1 600); do
  sudo test ! -s "$CHECKPOINT" || break
  /usr/bin/sleep 0.1
done
sudo jq -e '
  .phase == "bearer_live_before_terminal_write"
  and .bearer_live == true
  and .terminal_record_written == false
  and .core_dump_limits == [0,0]
  and .swap_entries == 0
' "$CHECKPOINT" >/dev/null
CREDENTIAL_PID=$(sudo jq -er '.target_pid' "$CHECKPOINT")
```

Do not send a signal yet. Run the positive control while that exact process
holds the live bearer. This is the first of the two identical searches:

```bash
sudo python3 -I tools/anthropic-wif-crash-cleanup.py scan \
  --run-id "$RUN_ID" --checkpoint "$CHECKPOINT" --output "$POSITIVE"
sudo jq -e '
  .credential_material_found == true
  and .material_classes_found == ["private_key"]
  and .matches == [{
    material_class:"private_key",
    relative_path:"replacement.pem",
    occurrences:1
  }]
  and .target_process_present == true
  and .scanner_core_dump_limits == [0,0]
  and .swap_entries == 0
' "$POSITIVE" >/dev/null
```

The kill happens here, and only here. `SIGTERM`, an interactive interrupt, or a
timeout is a failed attempt. Send `SIGKILL` to the checkpoint PID, then wait for
the separate supervisor to observe child return code `-9`:

```bash
sudo kill -KILL -- "$CREDENTIAL_PID"
set +e
wait "$SUPERVISOR_PID"
SUPERVISOR_STATUS=$?
set -e
test "$SUPERVISOR_STATUS" -eq 0
sudo jq -e '
  .event_type == "credential_process_sigkill_observed"
  and .signal_name == "SIGKILL"
  and .signal_number == 9
  and .child_returncode == -9
  and .supervisor_timed_out == false
  and .target_process_present == false
  and .signing_key_removed == true
  and .signing_key_present_after_cleanup == false
' "$KILL_OBSERVATION" >/dev/null
```

The supervisor has now removed the one run-scoped private key and fsynced the
run directory. Independently confirm its absence. Do not remove, copy, replace,
or edit the attempt record. Then invoke the same `scan` action with the same
checkpoint over the same stage; only the new output path differs:

```bash
sudo test ! -e "$CONTROL_STAGE/replacement.pem"
sudo python3 -I tools/anthropic-wif-crash-cleanup.py scan \
  --run-id "$RUN_ID" --checkpoint "$CHECKPOINT" --output "$POST_KILL"
sudo jq -e '
  .credential_material_found == false
  and .material_classes_found == []
  and .matches == []
  and .target_process_present == false
  and .scanner_core_dump_limits == [0,0]
  and .swap_entries == 0
' "$POST_KILL" >/dev/null
sudo jq -e '.status == "in_progress"' "$ATTEMPT" >/dev/null
```

The provider still trusts the staged public key at this point. On the operator
host, review and apply the old-key-only rollback even if the local proof failed:

```bash
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin issuer-rollback-stage --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin --apply \
  --output "$ADMIN_STAGE/crash-issuer-rollback.json" \
  issuer-rollback-stage --run-id "$RUN_ID" \
  --expected-current-jwks "$ADMIN_STAGE/current-jwks.json" \
  --replacement-jwks "$ADMIN_STAGE/replacement-jwks.json"
```

That rollback prevents new assertions from using the discarded key. **It does
not invalidate the bearer already issued to the killed process.** That bearer
can remain usable at Anthropic until the recorded natural expiry. Do not add a
provider-denial field to this result and do not describe issuer rollback as
bearer revocation.

After the exact rollback readback succeeds, assemble the local result on the
control plane. Collection rechecks both searches, all three attempt hashes, and
the actual rejection of the raw `in_progress` file by the expiry, revocation,
and crash-cleanup checkers:

```bash
sudo python3 -I tools/anthropic-wif-crash-cleanup.py collect \
  --run-id "$RUN_ID" \
  --attempt "$ATTEMPT" \
  --checkpoint "$CHECKPOINT" \
  --kill-observation "$KILL_OBSERVATION" \
  --positive-control "$POSITIVE" \
  --post-kill-search "$POST_KILL" \
  --output "$RESULT"
sudo python3 -I tools/check-anthropic-crash-cleanup.py \
  --evidence "$RESULT"
```

Collect the sanitized issuer-stage and rollback admin records as attended
operational attachments. The proposed qualification artifact is only `RESULT`;
it embeds the checkpoint, both searches, kill observation, unchanged
`in_progress` record, and checker exits. Never collect the private key, process
memory, assertion, bearer, exchange response, or a core. Preserve the run stage
through evidence review so the raw `in_progress` file remains inspectable; only
after the result has been copied and adjudicated may the operator remove the
entire run directory.

If checkpoint creation, the positive scan, `SIGKILL`, supervisor wait, key
removal, post-kill scan, checker rejection, or issuer rollback fails, the run is
not qualification evidence. If the child is still present on any failure path,
send that exact checkpoint PID `SIGKILL` before doing anything else. Once the
child is absent, remove a remaining `replacement.pem` as recovery and record
that the automatic cleanup failed; manual recovery is not proof. Never use
`SIGTERM` as cleanup or retry the exchange. A fresh attempt needs a fresh run
ID, fresh key, fresh provider overlap, and new output paths.

## Control-plane-loss recovery is not qualification

If the old private key is already gone, the admin tool can export the
provider's current public JWKS to a new mode-0600 file using the read-only
`issuer-export-current-jwks` action. That file can serve as the exact expected
current input to `issuer-stage`, while the replacement control plane supplies
the new public JWKS. This restores an overlap and lets the new key prove access
before retirement.

```bash
python3 -I tools/anthropic-wif-lifecycle-admin.py \
  --profile patchyard-admin \
  --output "$ADMIN_STAGE/provider-current-jwks.json" \
  issuer-export-current-jwks
```

That recovery closes the availability exposure, but it cannot produce a fresh
assertion from the lost retired key. It therefore cannot satisfy the A113
retired-key denial and must never be committed as qualified rotation evidence.
It needs its own live authorization and operational record.
