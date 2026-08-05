# Anthropic A-5 lifecycle proofs

## Status and boundary

This source implements the A113 expiry-denial and federation-rule-revocation
halves plus the A-14 signing-key rotation path. The expiry proof ran on
2026-08-04 and the rule-removal/restoration proof ran on 2026-08-05. Signing-key
rotation has not run. Any further live execution, provider mutation, key
activation, evidence publication, fixture refresh, or qualification-flag
change requires a new authorization after adversarial review.

The implementation is intentionally outside the existing host contract. It
does not call or modify:

- `worker/qualification/patchyard-run-anthropic-issuance`;
- `worker/runtime/patchyard-firecracker-run`;
- `worker/runtime/patchyard-anthropic-one-shot`; or
- any file under `worker/image/`.

`tools/anthropic-wif-lifecycle.py` is the source-pinned root-only control-plane
harness used by the qualified expiry result. The smaller
`tools/anthropic-wif-revocation.py` adapter loads that exact harness and changes
only the two revocation-denial actions; this preserves the expiry evidence's
source binding while making the observed rule response recordable.
`tools/anthropic-wif-lifecycle-admin.py` is a separate attended operator tool
using the short-lived `ant` OAuth profile. None accepts an API key. All strip
ambient Anthropic credential variables, reject HTTP redirects and ambient
proxies, use fixed Anthropic endpoints, make no retry, write only to a new
mode-0600 file, and never emit an assertion or bearer.

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

The administrative primitives follow Anthropic's documented WIF surface:
removing a rule workspace disables that mapping, adding it restores the same
mapping, and a partial issuer update replaces the complete inline JWKS. The
live rule-disabled exchange returned HTTP 401 `authentication_error`, not the
documented HTTP 400 `invalid_grant`. No retired-signing-key denial has been
observed. The documentation-derived HTTP 400 `invalid_grant` expectation is
accepted but deliberately not enforced as the retired-key exact predicate
under A125. See the official
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

`research/isolation/results/anthropic-revocation-rotation.json` is also absent
until an authorized live run succeeds. It binds the policy, qualified expiry
harness, revocation adapter, and administrative tool digests and contains these
exact, strictly ordered events:

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
| 11 | `retired_key_exchange_denial` | After the settling floor, a fresh assertion signed by the retired key receives a provider 4xx denial. Documentation predicts HTTP 400 `invalid_grant`, but the exact status, error type, and response shape remain unenforced until observed. |

The checker requires 16 distinct bracketing request IDs from the positive and
administrative calls. Each denial records `request_id_supplied`; a supplied ID
must be valid and distinct, while an absent ID is attributed by its bracketed
position. The observed rule-disabled 401 did carry a request ID, unlike the
expiry 401, so the checker retains it without making denial IDs part of the
mandatory count. It also requires exact rule and issuer state transitions,
continuity of both public-key thumbprints, five-minute-or-shorter bearers for
every positive control, and a final Models success from the active replacement.
The locally atomic activation is required but never substitutes for either
provider denial.

Every exchange that immediately tests a provider configuration mutation has a
90-second minimum settling interval from the preceding administrative readback
to `request_started_at`: both denials, the restored-rule positive, and the
staged-replacement positive. An attempt started sooner fails as inconclusive,
regardless of its HTTP result. This is the smallest directly observed interval
that produced the enforced rule denial: 0.85 seconds was too early, while the
accepted observation began 90.867688 seconds after the disabled-state
readback. It is a qualification floor, not a provider propagation SLA. The
initial positive has no preceding mutation; the final replacement positive
follows local atomic activation after the staged provider state was already
settled and proven. Rollback events terminate the attempt and are not
qualification-event predecessors.

`fixtures/provider-observations/anthropic-revocation-denial-2026-08-05.json`
is byte-identical to the credential-free terminal capture from the live rule
proof. The observation-only checker mode validates the corrected response
predicate without treating that failed terminal record as complete
qualification evidence:

```bash
python3 -I tools/check-anthropic-revocation.py \
  --observed-denial fixtures/provider-observations/anthropic-revocation-denial-2026-08-05.json
```

`infra/ansible/tests/test_anthropic_lifecycle.py` invokes the actual isolated
checkers against a valid contract and then mutates it. Both checkers reject a
fabricated denial, a missing positive control, a local-cleanup-only record, and
an out-of-order timestamp. The same tests exercise exact rule disable/restore,
two-key staging, retirement, and both rotation rollback paths with a fake API.
`fixtures/checker-contracts/anthropic-revocation-positive-settling.json`
demonstrates the two valid 90-second timing predicates. It is explicitly
synthetic and timing-only: it contains no provider response and makes no
provider-observation or qualification claim.

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
seconds after each readback, and the checker measures both attempts from those
readbacks. Atomic local activation needs no propagation wait: it changes no
provider state, and both public keys have already been read back and proven as
trusted.

Before A126, the checker required HTTP 400 `invalid_grant` for the retired key,
which is what the provider documentation says for an unknown signing key. No
captured retired-key response exists in this repository or the staged A126
material. That predicate was authored, not observed, and cannot satisfy A125.
The corrected checker therefore accepts a bounded provider 4xx denial without
enforcing the retired response's exact status, error type, or sanitized shape,
but returns exit 2 with a JSON `unpinned_denial_contract` signal. The evidence
is preserved as an observation and cannot qualify rotation until that observed
contract is pinned in a reviewed follow-up. This applies even if the first
response matches the documented HTTP 400 `invalid_grant`; the checker does not
infer the retired response from the rule-disabled response. Request-ID behavior
is likewise unobserved, so only the 16 positive/admin IDs are mandatory and a
retired-denial ID is retained only if supplied.

The qualified expiry result binds the existing lifecycle harness digest, so
changing that file would invalidate requirement 3 while fixing requirement 4.
The source-bound revocation adapter is the narrow compatibility boundary: for
post-mutation positives it adds `request_started_at`; for denials it records
that timestamp and explicit request-ID presence, enforces the observed
rule-disabled response, and leaves the retired exact response unpinned. If
rotation produces a retired response, preserve that observation and bind the
exact predicate in a reviewed follow-up before any complete result is
qualified.

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

Wait at least 90 seconds after the retirement readback before the one retired
assertion. An earlier denial or acceptance is inconclusive:

```bash
/usr/bin/sleep 90
sudo python3 -I tools/anthropic-wif-revocation.py exchange-denial \
  --run-id "$RUN_ID" --event-type retired_key_exchange_denial \
  --key-role retired_staging --signing-key "$CONTROL_STAGE/retired.pem" \
  --output "$CONTROL_STAGE/11-retired-key-denial.json"
```

If issuer retirement fails ambiguously, do not make the denial attempt. Use
the `issuer-restore-overlap` plan to determine whether provider state is
replacement-only; apply it only when needed to restore the already-proven
two-key overlap, then stop. If the retired assertion is accepted, stop without
retry. The adapter accepts a bounded provider 4xx so the first real denial can
be preserved without guessing its exact shape. The checker then emits the
machine-readable unpinned-contract signal and blocks qualification regardless
of whether the response matches documented HTTP 400 `invalid_grant`; bind the
observed response in a reviewed follow-up. The active replacement has already
been provider-proven, so do not re-trust the retired key merely to make the
test pass.

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

After a valid denial, remove only the two explicitly named tmpfs private-key
copies. The active replacement remains at the stable root-only path:

```bash
sudo rm -f -- "$CONTROL_STAGE/retired.pem" "$CONTROL_STAGE/replacement.pem"
```

## Assemble and validate the revocation fixture

Place the eleven sanitized events in one operator directory with the numeric
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
      "retired_key_exchange_denial"
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
  11-retired-key-denial.json \
  > anthropic-revocation-rotation.json
python3 -I tools/check-anthropic-revocation.py \
  --evidence "$PWD/anthropic-revocation-rotation.json"
```

Checker exit 1 rejects malformed evidence. Exit 2 accepts the observation but
blocks qualification and emits its JSON pinning signal; only exit 0 can count
as qualified evidence. Do not hand-edit an event, fill a missing request ID,
relabel a local observation, reorder a timestamp, or publish a partial fixture
as success. Files whose top level has `status` are terminal diagnostics rather
than success events and must not be substituted into the eleven-event list.

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
