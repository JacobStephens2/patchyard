# OpenAI A-5 lifecycle: requirements 3 through 6

## A150: the mapped service-account id is registry-resolved

Every collector on this page resolves the service-account id it sends from
`policy/openai-identity-history.json` (`current_service_account_id`), **not**
from `policy/openai-wif.json`. The 2026-08-12 account
`user-6tzs2hdFVN7GoYQbWfC0eu7k` ceased to exist without a recorded mutation and
was replaced on 2026-08-20 by `user-1UnalMTUg8XaoKcNDHpcsqZU`, verified from the
per-project `service_accounts` listing before the mapping was bound to it. The
frozen policy's two id fields are demoted by meaning to the account the banked
Results were minted against, and the checkers accept any id in the roster.

Two consequences for anyone running these procedures. The console **cannot**
repoint a mapping's service account - that field is read-only in *Edit mapping*
- so a repoint is a create-then-bind through *Create mapping* with its
"Create a new service account in this project" checkbox **unchecked**; leaving
it checked is the 2026-08-12 trap. And OpenAI's token exchange returns **200 for
a service account that no longer exists**, so exchange success is not evidence
that the federated identity is live.

## A151: what an OpenAI exchange Result establishes

A150's finding is this section's premise: OpenAI's token exchange returns **200
for a service account that no longer exists**. What follows is what that does,
and does not do, to the evidence already banked on this page.

**Exchange success is evidence about the token endpoint, never about the
principal behind it.** The endpoint answers whether an assertion is trusted. It
does not answer whether the mapped principal exists, belongs to a project, or
can make a billable call.

**All four banked OpenAI exchange Results are undisturbed**, and by one
mechanism: the dead account was a *constant*, not a variable, in every arm of
every one of them. Requirement 4's bracket is 200 (baseline `sub`) / 401
(sentinel `sub`) / 200 (restored `sub`) with the same dead `service_account_id`
on all three arms - only the subject expression moved, and the endpoint tracked
it. Requirement 3 (expired assertion) and requirement 5 (retired kid, with its
overlap positive control) have the same shape: a mutated input against a
constant account. Requirement 6 needs no argument, because A130 already bounds
it to local non-recoverability. The live-window argument - that requirements
1/3/5 ran on 2026-08-12/13 while the console read the account live - was
available and is **rejected**: it would re-lean on exactly the class of
evidence that failed here, and only the per-project `service_accounts` listing
discriminates liveness.

**Requirement 4 stays Proven, on the narrow reading.** It claims that
revocation is observable at the token endpoint - the mapping's `sub` condition
controls issuance. It does **not** claim that revocation removes the identity's
ability to act. A149 clause 2 refused to let the 401 speak to *cause*; A151
supplies the symmetric refusal on the other end: **the bracket's two 200s prove
issuance, not capability.** Said plainly, because it is thinner than the
requirement's name suggests - and thinner for Anthropic's analogue too, where
it went unnoticed only because that requirement 1 calls `/v1/models`.

**Requirement 1's meaning narrows, and its Result is not re-produced.**
`openai-first-token-exchange.json` stays byte-identical. Requirement 1 proves
the issuance-and-delivery **path** - mint, exchange, bearer in hand, removal at
`credential_removed_at` - and explicitly **not** that the bearer authorizes
anything. OpenAI requirement 1 is exchange-only and has never called
`/v1/models`; that clause is Anthropic's. The Result's own fields never
overclaimed (`qualification_evidence: false`,
`response_predicate.enforced: false`) - this page did, and that is what is
corrected here.

**Every OpenAI qualification run preflights the service-account listing.**
Before a run produces a Result, assert that the mapped `service_account_id`
resolves in `GET /v1/organization/projects/{project}/service_accounts` at HTTP
200, and record the observation - account id, project, HTTP status, timestamp -
in the Result, in the shape `model_console_observations` already takes. The
preflight is called **out of band**, never from inside a collector: the
collectors build a `credential_free_env()` that pops `OPENAI_ADMIN_KEY`,
`PATCHYARD_OPENAI_ADMIN_KEY` and `OPENAI_API_KEY` before exchanging, and a
preflight inside one would need the exact key the collector exists to prove it
never held. The observation is therefore operator-supplied and must never be
described as provider-attested. This obligation is forward-only: the four
banked Results are cleared by the argument above and are not reopened.

**Requirement 2 is now the only capability evidence this provider will ever
have.** Every other OpenAI requirement is a control-plane observation. It is
load-bearing and cannot be waived, downgraded, or satisfied by an exchange.

Scope: this ruling covers OpenAI's console-only WIF surface and is explicitly
not generalized to Anthropic, whose requirement 1 exercises the minted
credential against `/v1/models` and whose lifecycle mutations carry provider
request IDs. That exemption is earned by those two facts, and evaporates for
any future provider that is console-only.

## Status and scope

OpenAI requirement 1, issuance and delivery, is Proven by the committed Result
from the attended 2026-08-12 exchange. This change does not run a provider
call, does not create a Result, and does not make any other Requirement Proven.
OpenAI is not Qualified, and all 13 `credential_qualified` values remain
`false`.

This change builds the attended control-plane paths for:

- requirement 3, credential expiry denial; and
- requirement 6, A130 crash-cleanup local non-recoverability.

It defines the capture procedures, but performs no run and no control-plane
mutation, for:

- requirement 4, federation-rule revocation; and
- requirement 5, signing-key rotation.

Requirement 2 remains separate. It needs a billable API call through the
provider-neutral execution plane and stays deferred behind this work.

## Execution-plane measurement

The committed Anthropic Results confirm the boundary rather than merely naming
it. In each of requirement 2's three phases, `provider_transport` contains 13
fields and the worker-delivery subset contains four:

- `assertion_delivered`;
- `credential_delivered_to_guest`;
- `credential_removed_before_guest_boot`; and
- `worker_host_tmpfs`.

Seventeen fields across three phases is 51 execution-plane fields. The
committed expiry, revocation/rotation, and crash-cleanup Results contain zero
worker or provider-transport fields. OpenAI requirements 3 through 6 therefore
remain control-plane exchange or local-cleanup shapes. No worker, Firecracker
launcher, guest runner, or provider-neutral execution plane participates in
the procedures below.

## Shared source and Evidence rules

`tools/openai-wif-expiry.py` and
`tools/openai-wif-crash-cleanup.py` are siblings of every frozen source. Each
loads `tools/anthropic-wif-lifecycle.py` only after verifying its exact SHA-256
digest. Neither imports it, edits it, or imports another repository module.

Both adapters use the root-only signing key at
`/etc/patchyard/openai-wif-signing.pem`. They derive the assertion `kid`
from the active public DER as:

```text
"patchyard-" + sha256(public DER)[:16]
```

No fixed `kid` belongs in a command or procedure. Before an attended run, a
read-only console comparison must show that the currently uploaded public JWK
is the one derived from the active key. If it is not, stop. Updating the console
would be a control-plane mutation and is not authorized by a requirement 3 or
requirement 6 run.

The two checkers deliberately duplicate these stable hygiene helpers:
`is_within`, `digest`, `parse_time`, `exact_keys`, `secret_named_key`,
`isolation_errors`, and `load_json_file`. A133 permits that prospective
duplication because those helpers have one historical revision; provider
judgment stays in each checker rather than entering a shared Evidence-semantics
module.

Each adapter reserves a new mode-0600 output in a root-owned mode-0700 `/run`
tmpfs stage before signing or making a provider call. Every checker requires
isolated Python, exact keys, ordered UTC observations, current source digests,
and the absence of credential-shaped values. A Fixture is accepted only in
`--contract-fixture` mode and is refused as qualification Evidence.

Under A125, every OpenAI response predicate in this change is unenforced. No
expiry-denial or future revocation/rotation denial status, error type, error
code, request-ID rule, or message shape has been observed. Each predicate
carries a `basis` that says so. An attended run records the bounded response as
OpenAI returned it; a later reviewed change may descend an enforced predicate
from that observation.

## Requirement 3: credential expiry denial

### Contract

The expiry adapter mints a 300-second assertion with `iat` 305 seconds before
mint and `exp` five seconds before mint. It derives the active key identifier,
attempts exactly one JSON token exchange at
`https://auth.openai.com/oauth/token`, and immediately removes the assertion
from its request state. It never writes the assertion, response body, bearer,
or private key.

The sanitized observation records the assertion times, one-attempt request
contract, bounded HTTP metadata, response field types, and whether an
`access_token` field was supplied. It does not decide what OpenAI's response
means. In particular, the checker accepts any bounded HTTP status in
observation mode and rejects any attempt to set
`response_predicate.enforced = true` before the first observation.

No control-plane mutation is made or causally claimed. A132 therefore requires
no Attestation. The Result still carries the provenance mark with
`mutation_receipt_obtained: false`, `control_plane_mutation_claimed: false`,
and `attestation_required: false`.

`fixtures/checker-contracts/openai-expiry-denial.json` is a synthetic Fixture.
Its provider response is an explicitly unobserved placeholder, and it carries:

```json
{
  "fixture_kind": "synthetic-openai-expiry-satisfiability",
  "provider_response_observed": false,
  "qualification_evidence": false
}
```

The Fixture demonstrates that the contract has an accepting case. It is not a
Result and contains no Evidence from a provider interaction.

### Attended procedure

Do not run this procedure during build, review, CI, or an unattended session.
It requires separate authorization for one live OpenAI exchange. It requires
no console change. If any console change appears necessary, stop rather than
folding it into this run.

On the control plane, verify the exact deployed revision and static contracts:

```bash
cd /opt/patchyard
git status --short
git rev-parse HEAD
python3 -I tools/check-freeze-graph.py
python3 -I tools/check-openai-wif-expiry.py --allow-missing-results
jq -e '.providers.openai.credential_qualified == false' policy/provider-egress.json
sudo test "$(stat -c '%U:%G:%a' \
  /etc/patchyard/openai-wif-signing.pem)" = root:root:400
```

Stop if the checkout is dirty, the revision is not the reviewed revision for
the attended run, the freeze graph reports drift, a checker rejects static
preflight, the OpenAI `credential_qualified` value is true (the gate is
OpenAI-scoped: other providers' qualification changes independently, and
Anthropic is qualified since the live review seats), another OpenAI lifecycle run
is active, or the read-only console comparison does not match the public JWK
derived from the active key.

Create one fresh root-owned tmpfs stage and one new output:

```bash
RUN_ID="openai-expiry-$(date -u +%Y%m%d)-$(openssl rand -hex 5)"
CONTROL_STAGE="/run/patchyard-openai/$RUN_ID"
RESULT="$CONTROL_STAGE/openai-expiry-denial.json"
sudo install -d -m 0700 -o root -g root "$CONTROL_STAGE"
sudo python3 -I tools/openai-wif-expiry.py \
  --run-id "$RUN_ID" --output "$RESULT"
```

The command makes one exchange and no retry. A transport failure with no HTTP
response writes a failed terminal record and is not a Result. Any bounded HTTP
response produces a sanitized, non-qualifying observation. Check it without
editing it:

```bash
sudo python3 -I tools/check-openai-wif-expiry.py \
  --observation "$RESULT"
```

Copy only the sanitized JSON through the reviewed management path to a new
operator-host path. Never copy the stage, request body, assertion, response
body, bearer, process memory, or signing key. Preserve the observation for
adjudication. A Requirement becomes Proven only after a conforming Result is
committed and accepted; the attended command alone does not change status.

## Requirement 6: A130 local non-recoverability

### What the OpenAI issuance path leaves behind

The frozen first-exchange Result shows that the bearer was removed from the
issuance adapter's state 393 microseconds after it was observed. The successful
terminal output contains only sanitized metadata. An abrupt death before that
terminal replacement is the unmeasured case: the assertion and bearer can both
be live in the process image while the reserved output still says
`status: in_progress`.

The crash adapter measures that boundary directly:

1. The credential child reserves `crash-attempt.json` before signing.
2. It performs one exchange using the active signing identity and pauses after
   the provider supplies a bearer but before a terminal write.
3. The positive control receives the exact live assertion and bearer through a
   root-only Unix socket, checks their SHA-256 fingerprints against the
   credential-free checkpoint, and finds both exact byte sequences in the
   target process's readable mappings. It records no credential bytes.
4. The operator sends that exact PID `SIGKILL` while the assertion lifetime is
   still open. `SIGTERM` and a supervisor timeout are rejected.
5. The same scanner, with the same contract digest, runs after the PID/start
   identity is absent. It scans every bounded regular file in the run stage and
   finds no JWT, OpenAI bearer shape, bearer header, or private-key PEM.
6. Collection proves the original `status: in_progress` bytes are unchanged and
   that every OpenAI checker rejects that inert record.

Core dumps are disabled in both the credential child and scanner, configured
swap must be zero, the run stage is verified `/run` tmpfs, and the scanner
fails closed on symlinks, unexpected special files, unreadable inputs, or byte
and region ceilings.

The stable signing identity remains at its root-only source path. The adapter
asks `openssl` to sign with it; the adapter never loads private-key bytes and
never copies the key into the run stage. A130's bounded subject is the OpenAI
credential in flight and any run-scoped copy, not the unrelated stable signing
identity. The Result says this explicitly.

This local property makes no provider-side claim. The killed bearer may remain
valid at OpenAI until natural expiry. No denial is attempted, no Attestation is
required, and local cleanup never substitutes for requirement 3 or requirement
4. The Result carries the same no-mutation provenance mark as requirement 3.

`fixtures/checker-contracts/openai-crash-cleanup.json` is a synthetic Fixture.
Its sanitized success response shape descends from the committed requirement 1
Result; its PID, fingerprints, times, `SIGKILL`, and scanner outcomes are
synthetic. It carries `fixture_kind`, `provider_response_observed: false`, and
`qualification_evidence: false`. Contract-fixture mode accepts it, while the
qualification path refuses it.

### Attended procedure

Do not run this procedure during build, review, CI, or an unattended session.
It requires separate authorization for one live OpenAI exchange and an
attended `SIGKILL`. It requires no console change. If the active public key is
not already the uploaded JWK, stop.

Run the same revision, freeze, `credential_qualified`, key-mode, and read-only
console preflight from requirement 3, then add:

```bash
python3 -I tools/check-openai-wif-crash-cleanup.py --allow-missing-results
test "$(cat /proc/sys/kernel/core_pattern)" != ""
test "$(tail -n +2 /proc/swaps | wc -l)" -eq 0
```

Create the fresh stage and name every output:

```bash
RUN_ID="openai-crash-$(date -u +%Y%m%d)-$(openssl rand -hex 5)"
CONTROL_STAGE="/run/patchyard-openai/$RUN_ID"
ATTEMPT="$CONTROL_STAGE/crash-attempt.json"
CHECKPOINT="$CONTROL_STAGE/crash-checkpoint.json"
POSITIVE="$CONTROL_STAGE/crash-positive-search.json"
KILL_OBSERVATION="$CONTROL_STAGE/crash-sigkill.json"
POST_KILL="$CONTROL_STAGE/crash-post-kill-search.json"
RESULT="$CONTROL_STAGE/openai-crash-cleanup.json"
sudo install -d -m 0700 -o root -g root "$CONTROL_STAGE"
```

Start the supervisor. It reserves its own output and launches the credential
child, which separately reserves the abrupt-death record:

```bash
sudo python3 -I tools/openai-wif-crash-cleanup.py supervise \
  --run-id "$RUN_ID" \
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
  and .assertion_live == true
  and .bearer_live == true
  and .terminal_record_written == false
  and .core_dump_limits == [0,0]
  and .swap_entries == 0
  and .signing_key.kid_derived_from_public_der == true
  and .signing_key.copied_to_run_stage == false
  and .signing_key.private_key_bytes_loaded_by_adapter == false
' "$CHECKPOINT" >/dev/null
CREDENTIAL_PID=$(sudo jq -er '.target_pid' "$CHECKPOINT")
```

Do not signal the process yet. Run the positive control with the exact
checkpoint. The command transfers the live values only through the root-only
local socket, finds them in the target process image, zeroes its mutable copies,
and writes only class names and bounded counts:

```bash
sudo python3 -I tools/openai-wif-crash-cleanup.py scan \
  --run-id "$RUN_ID" --checkpoint "$CHECKPOINT" --output "$POSITIVE"
sudo jq -e '
  .credential_material_found == true
  and .material_classes_found == ["jwt_assertion","openai_bearer"]
  and (.matches | length) == 2
  and all(.matches[]; .surface == "process_image")
  and .target_process_present == true
  and .scan_socket_used == true
  and .memory_regions_examined > 0
  and .memory_bytes_examined > 0
  and .scanner_core_dump_limits == [0,0]
  and .swap_entries == 0
' "$POSITIVE" >/dev/null
```

The kill happens here, and only here. A timeout, `SIGTERM`, interactive
interrupt, missing positive control, or kill after the recorded assertion
expiry is a failed attempt:

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
  and .scan_socket_present_after_cleanup == false
' "$KILL_OBSERVATION" >/dev/null
```

Do not remove, copy, replace, or edit the attempt record. Run the identical
scanner after the process is gone:

```bash
sudo python3 -I tools/openai-wif-crash-cleanup.py scan \
  --run-id "$RUN_ID" --checkpoint "$CHECKPOINT" --output "$POST_KILL"
sudo jq -e '
  .credential_material_found == false
  and .material_classes_found == []
  and .matches == []
  and .target_process_present == false
  and .scan_socket_used == false
  and .memory_regions_examined == 0
  and .memory_bytes_examined == 0
  and .scanner_core_dump_limits == [0,0]
  and .swap_entries == 0
' "$POST_KILL" >/dev/null
sudo jq -e '.status == "in_progress"' "$ATTEMPT" >/dev/null
```

Collect and check the sanitized local Result:

```bash
sudo python3 -I tools/openai-wif-crash-cleanup.py collect \
  --run-id "$RUN_ID" \
  --attempt "$ATTEMPT" \
  --checkpoint "$CHECKPOINT" \
  --kill-observation "$KILL_OBSERVATION" \
  --positive-control "$POSITIVE" \
  --post-kill-search "$POST_KILL" \
  --output "$RESULT"
sudo python3 -I tools/check-openai-wif-crash-cleanup.py \
  --evidence "$RESULT"
```

Copy only `RESULT` through the reviewed management path. Never copy the stage,
socket, fingerprints as a separate input, assertion, bearer, raw response,
process memory, core, or signing key. Preserve the stage until Evidence review
has confirmed the unchanged abrupt-death record; only then may the operator
remove the whole run directory.

If any checkpoint, positive scan, `SIGKILL`, supervisor observation, post-kill
scan, checker rejection, or collection step fails, the observation cannot make
the Requirement Proven. If the credential child remains present, send that
exact PID `SIGKILL` before recovery. Do not retry the provider call. A new
attempt requires a new run ID and new output paths.

**Status.** Proven by run `openai-crash-20260812-e12437747f` after #288
accepted its existing A130 Evidence. No new provider run was required. The
committed Result and every later conforming collector Result carry
`qualification_evidence: true`; default and `--evidence` checker modes accept
them. `response_predicate.enforced` remains false: this proves local
non-recoverability only, and the killed bearer may remain valid until natural
expiry.

## Requirement 4: federation-rule revocation capture

### The mutation is subject-expression revocation (A141); `remove` is forbidden (A140)

On OpenAI, deleting the federation subject mapping cascades provider-side into
destroying the mapped service account. Observed 2026-08-12: after a `remove`
mutation, run `openai-revocation-20260812-4924ca4ef5` failed its bracketing
control (`bracketing control did not supply a bearer`) even though its baseline
had exchanged HTTP 200 against `user-ibYSGwJI5TPOPeJ3ioADcfDH`; the follow-up
run `openai-revocation-20260812-64a8668459` failed its baseline outright, and
recreating the mapping minted a same-named service account with a **new** id.

`remove` therefore violates step 3's own "do not change the service account"
constraint by provider cascade, and makes step 6's "restore the exact original
mapping" unsatisfiable at the id level - every future attempt would re-break
the policy pin. A140 records the 2026-08-12 discontinuity once; no lineage
annotation attaches anywhere else.

A140 prescribed `disable` as the replacement, and the console cannot perform
it: the attended run `openai-revocation-20260812-e2f0bcef3c` aborted safely at
the mutation pause because the mapping card offers only Edit / delete /
Details and the provider Edit dialog has no enable/disable control. A disabled
state exists server-side - OpenAI's token-exchange error taxonomy lists
"matching mapping is disabled" - but no public surface flips it (research
2026-08-13, primary sources including the openai-openapi spec: the WIF
management plane is dashboard-only, with no provider or mapping CRUD in the
Admin API).

**The requirement-4 mutation is `--mapping-mutation subject-expression`
(A141): a console Edit of the subject mapping's claim assertion to the
run-scoped sentinel `sub=patchyard-control-plane-REVOKED-<run id>`.** The
mapping stays present and enabled throughout; what is revoked is the rule the
worker's assertion matches. Restoration is editing the original expression
back - same mapping, same service-account id - so step 5's "identical to
step 1" is literally satisfiable. The sentinel makes crashed-window residue
self-describing at the console: a mapping left mid-run carries a rule that
names the run that broke, not a disabled state and not plausible
configuration. Edit reversibility is inferred, not promised; each run's step 6
restoration reading is what proves it, and the runbook carries the edit-back
failure path.

### Non-recoverable precondition

**The subject-mapping control-plane mutation must not be made before the capture
begins.** Removing, disabling, or altering the mapping first permanently
destroys the bounded before-state. Requirement 1's setup mutations were made
without that capture and can never carry a conforming Attestation; do not try to
reconstruct, relabel, or backdate one.

This procedure is a design for a later separately authorized attended run. It
does not authorize a console action. Before the run, fix one reviewed lifecycle
instrument SHA that can make a fresh normal-assertion exchange with the active
key and sanitize any response without enforcing a denial shape. That exact
instrument digest, token endpoint, identity-provider ID, service-account ID,
request body shape, and assertion lifetime remain fixed for all three controls.

### Bounded window and the A146 model-operated record

A146 is a requirement-4-only exception. After a named accountable human
authorizes one exact run, a named model may perform both subject-expression
Saves, make the five live console readings, and write the Result. This is a
new record shape, not a flag on Attestation. Attestation remains a
human-observed fact and is unchanged for every other requirement.

Remaining runs on this map are authorized by A148's **route authorization**,
not by a per-run 45-minute GitHub comment. The Result embeds
`human_authorization` with `source: "route authorization"` pointing at that
grant. The checker does not fetch GitHub. A146's comment path remains for a
run after the destination. The output must never be described as human
attestation, independent evidence, or corroboration.

Use the named capture method:

```text
model_console_readback_bounded_by_control_plane_utc
```

Do not use `operator_console_readback_bounded_by_control_plane_utc`. Every
console reading is preceded by a reload. Each reading records
`captured_before_at` immediately before the reading and `captured_after_at`
immediately after it, using control-plane UTC, plus navigation (`url`,
`reloaded: true`, reload timestamps) and a unique `capture_action_id`. The
capture includes the provider identity, subject-mapping expression, mapped
service account, enabled state, uploaded-JWKS mode, and the console URL. It
never includes a private key, assertion, or bearer.

The Result permanently carries:

```json
{
  "mutation_receipt_obtained": false,
  "human_attestation_obtained": false,
  "human_authorship_mechanically_proven": false
}
```

`independence` and `corroboration` are absent, not set false. The marks are
permanent even if OpenAI later exposes a management API.

The committed Result from run `openai-revocation-20260819-6bd96462ce` now
carries the reviewed predicate (A149): HTTP 401 and no bearer. `error_type`,
request-id presence, `body_bytes`, and sanitized field types are not pinned.

```json
{
  "enforced": true,
  "http_status": 401,
  "access_token_supplied": false,
  "basis": "observed-openai-federation-revocation-response"
}
```

The predicate asserts the wire denial only. That the denial was *caused* by the
subject-expression mutation rides on A129's bracket - a 200 baseline before and
a 200 bracketing exchange after, on the same instrument - and on the mutation
Attestations, never on the predicate. OpenAI returns the same 401
`invalid_request_error` for an expired assertion and for a retired signing key,
so the predicate proves denial, not cause.

### Sequence

All steps below occur in one bounded window:

1. Record the window start in control-plane UTC. Capture the enabled mapping's
   before-state with the named method.
2. Make the baseline control: one fresh normal-assertion exchange on the token
   endpoint with the fixed instrument. It must supply a bearer. Record the
   provider response as a Receipt where OpenAI supplies a request ID.
3. With capture already active, record the mutation's immediate before-bound,
   record the model's pre-Save intent, have the named model **Edit** only the
   subject mapping's claim assertion to the run-scoped sentinel (never remove
   the mapping - A140), record the immediate post-Save confirmation, then
   reload and record the immediate after-state. Do not change the service
   account or uploaded JWK in this Requirement.
4. Wait at least the standing 90-second settling floor. An exchange before the
   floor measures propagation and cannot become Evidence of revocation.
5. Attempt exactly one fresh exchange with the same surface and instrument.
   Record whatever bounded response OpenAI returns. Do not require a status,
   error type, error code, message, or request-ID shape.
6. While capture remains active, reload and capture the sentinel-expression
   state, record the restore-Save intent, edit the exact original expression
   back, record the restore confirmation, then reload and capture the restored
   state.
7. Wait the same settling floor. Make the bracketing control: one fresh exchange
   with the same surface and instrument, which must supply a bearer.
8. Record the window end and bind the baseline control, denial observation,
   bracketing control, both Saves, the five reloaded readings, the embedded
   authorization, the same-task model identity, and the instrument digest into
   one proposed Result.

Steps 2, 5, and 7 are A129's positive, denial, positive sequence. They remain
inside one bounded window on the same token-exchange surface with the same
instrument digest. Under A132, this bracket and the baseline control are the
entire causal argument that the mapping mutation caused the denial. A denial
without either positive is Evidence only that one exchange failed.

If the mapping mutation, capture, settling interval, denial attempt, restore,
or either positive fails, restore the safe mapping state but do not describe the
run as conforming. A recovery outside the bounded window is operationally
necessary and cannot repair the record.

### Attended procedure

Do not run this procedure during build, review, CI, or an unattended session.
It requires separate authorization for three live OpenAI exchanges and two
console mutations. Unlike Requirement 3, this run deliberately changes the
control plane's federation configuration, and it is not finished until the
original mapping is back.

**Run it inside tmux.** The collector prompts on a terminal and blocks. A
dropped SSH connection destroys the pseudo-TTY, the kernel SIGHUPs the
collector, and the run dies holding an open mutation window with the mapping
still carrying the sentinel. That has already happened once. tmux owns the pseudo-TTY
itself, so a disconnect costs nothing and `tmux attach -t rev` resumes at the
same prompt.

```bash
ssh conductor@factory.example.com
tmux new -s rev
cd /opt/patchyard
```

Verify the deployed revision and static contracts before opening the window.

`/opt/patchyard` is owned by `factory-manager:factory`, so anything that
shells out to git has to run as that account: git refuses a repository whose
owner is not the calling user, and that includes root. `conductor` can read
the checkout, but `git status` and `check-freeze-graph.py` both fail for it
with "detected dubious ownership" - which looks like the drift this preflight
is meant to detect and is not. Run them as the owner:

```bash
fm() { sudo -n -u factory-manager env -C /opt/patchyard "$@"; }
fm git status --short
fm git rev-parse HEAD
fm python3 -I tools/check-freeze-graph.py
fm python3 -I tools/check-openai-wif-federation-revocation.py --allow-missing-results
sudo test "$(stat -c '%U:%G:%a' \
  /etc/patchyard/openai-wif-signing.pem)" = root:root:400
```

The collector itself still runs as root, per its own check; only the git-backed
preflight needs the owning account.

Stop if the checkout is dirty, the revision is not the reviewed revision for
the attended run, the freeze graph reports drift, a checker rejects static
preflight, or another OpenAI lifecycle run is active.

Have the console open on the provider page before starting, and confirm the
subject mapping is present, enabled, and carrying the original claim
assertion. The run cannot begin from a missing or disabled mapping, or from
one still carrying a `-REVOKED-` sentinel left by a crashed window: the first
reading is checked against `require_active_mapping`, which also rejects
sentinel residue. Residue is repaired by editing the original expression back
at the console before starting, never by starting a run over it.

Create one fresh root-owned tmpfs stage and one new output. The run ID must
match `openai-revocation-[0-9]{8}-[0-9a-f]{10}`, and the output must sit
inside the stage:

```bash
RUN_ID="openai-revocation-$(date -u +%Y%m%d)-$(openssl rand -hex 5)"
CONTROL_STAGE="/run/patchyard-openai/$RUN_ID"
RESULT="$CONTROL_STAGE/openai-federation-revocation.json"
sudo install -d -m 0700 -o root -g root "$CONTROL_STAGE"
sudo python3 -I tools/openai-wif-federation-revocation.py \
  --run-id "$RUN_ID" \
  --authorization-file "$CONTROL_STAGE/authorization.json" \
  --model-pairing "<provider>/<harness>/<model>/<reasoning>" \
  --codex-task-id "<codex task id>" \
  --mapping-mutation subject-expression --output "$RESULT"
```

The authorization file is the embedded GitHub-comment record for this exact
run. The pairing and Codex task id must match it. The same task must perform
the mutations, make the five readings, and write the Result.

The collector asks for five reloaded console readings, two Save
acknowledgements, and two Save confirmations, in this order. Answer each
prompt only when it appears; do not queue answers ahead.

| Step | Prompt | Mapping state to report |
|------|--------|-------------------------|
| 1 | enabled mapping before the baseline control | present and enabled, original expression |
| 2 | immediate state before the mutation | unchanged from step 1 |
| — | `MUTATION COMPLETE` | Edit the claim assertion to the sentinel first |
| 3 | immediate state after the mutation | present and enabled, expression is the sentinel |
| 4 | current mapping before safe restoration | **still the sentinel** |
| — | `RESTORATION COMPLETE` | edit the original expression back first |
| 5 | the safely restored mapping | present and enabled, identical to step 1 |

**Reload the console, then read it at each step. Do not prepare the JSON in
advance.** The capture method is
`model_console_readback_bounded_by_control_plane_utc`. Values written before
the window began produce a file that passes every checker while recording
nothing that was seen live.

Step 4 is the step that gets missed. It is captured *before* restoring, so
the mapping must still carry the sentinel when you answer it. Restoring early fails
the run with `mapping returned to its original state before captured
restoration`, and the collector treats that as a failure even though the
console is safe.

Each reading is one line of JSON with exactly these keys: `console_location`,
`enabled`, `identity_provider_id`, `mapped_service_account_id`,
`mapping_present`, `subject_mapping_expression`, `uploaded_jwks_mode`.
`mapping_present`, `enabled` and `uploaded_jwks_mode` are strictly boolean.
A run has already been rejected for sending the string `"Uploaded JWKS"`
where `true` was required. Absent fields are `null`, not empty strings.

The run pauses twice for the standing 90-second settling floor, once before
the denial attempt and once before the bracketing control. It prints the
remaining time. An exchange before the floor measures propagation and cannot
become Evidence of revocation.

If any step fails, restore the original mapping anyway. The collector's
`finally` block still prompts for restoration on the failure path, and
`safe_mapping_restored` records whether the mapping came back. A recovery
outside the bounded window is operationally necessary and cannot repair the
record: the run is then not conforming, and it is re-run from a clean
window rather than patched.

Check the terminal record without editing it:

```bash
sudo python3 -I tools/check-openai-wif-federation-revocation.py \
  --observation "$RESULT"
```

Confirm on the record that `bounded_window` covers all three exchanges, that
`baseline_control` and `bracketing_control` both supplied a bearer, that
`denial_observation` sits between them on the same surface with the same
instrument digest, and that `safe_mapping_restored` is true.

Copy only the sanitized JSON through the reviewed management path to a new
operator-host path. Never copy the stage, request body, assertion, response
body, bearer, process memory, or signing key.

**Status.** Proven by run `openai-revocation-20260819-6bd96462ce` after A149
completed the deferred predicate (HTTP 401 and no bearer). OpenAI remains not
Qualified.

`--evidence` mode now passes on the committed Result: A149 completed the
deferred predicate and flipped `qualification_evidence` to true. A later
conforming run is born with the same enforced predicate. The run that produced
this Result was performed end to end by a named model under A148 route
authorization, with no human attestation and no independence; the predicate
descends from OpenAI's own Receipt, which is why a model-operated run can
support it.

## Requirement 5: signing-key rotation capture

**Status.** Proven by run `openai-rotation-20260813-c488000f8f` after A147
completed the deferred predicate (HTTP 401 and no bearer). OpenAI remains not
Qualified.

### Non-recoverable precondition

**The replacement-JWK upload or any other signing-key control-plane mutation
must not be made before the capture begins.** An uploaded replacement without a
bounded capture destroys the original one-key before-state. No later screenshot
or console reading can reconstruct a conforming Attestation.

This procedure is a design for a later separately authorized attended run. It
does not authorize JWK upload, retirement, or local key activation. Before the
run, fix one reviewed lifecycle instrument SHA that can use either the stable
active key or a root-only run-scoped replacement key while preserving an
identical token-exchange request surface and sanitized response contract.
Derive both key identifiers from their public DER during the run; never place a
fixed `kid` in this procedure.

### Bounded window and parties

Name the actor and attester before opening the window, applying A136's role
rule and independence limitation. A146 does not apply here. Use
`operator_console_readback_bounded_by_control_plane_utc` for every console
reading. Each JWK-set control-plane mutation gets bounded before and after UTC,
the complete public-key membership and enabled state, the named roles, and the
fixed instrument digest.

Every Attestation and the Result carry the permanent provenance mark
`mutation_receipt_obtained: false`. OpenAI exchange responses remain Receipts;
console JWK changes do not become Receipts merely because they are adjacent to
one.

The committed Result from run `openai-rotation-20260813-c488000f8f` now
carries the reviewed predicate (A147): HTTP 401 and no bearer. `error_type`,
request-id presence, `body_bytes`, and sanitized field types are not pinned.

```json
{
  "enforced": true,
  "http_status": 401,
  "access_token_supplied": false,
  "basis": "observed-openai-retired-signing-key-response"
}
```

### Sequence

All steps occur in one bounded window:

1. Record the window start. Capture the original console state before any
   replacement upload: uploaded-JWKS mode enabled, the single active public key,
   the unchanged subject mapping, and the mapped service account.
2. Make the baseline control using the active key and fixed lifecycle
   instrument. The token exchange must supply a bearer.
3. Generate a distinct 3072-bit RSA replacement key only in the root-owned
   `/run` stage. Derive both public JWK descriptors and confirm they are
   distinct. No private key crosses to the operator host or console.
4. Capture the immediate before-bound, have the actor upload the two-key overlap
   containing the original and replacement public JWKs, capture the immediate
   after-bound, and have the attester record the Attestation.
5. Wait at least 90 seconds. Make a replacement-key positive exchange with the
   same instrument and surface. If it does not supply a bearer, repeat the
   exchange at 90-second intervals up to four attempts in total, all above the
   settling floor; every attempt is journaled with its receipt, and the winning
   record's `attempt_count` discloses which attempt supplied the bearer. If the
   fourth attempt still does not supply a bearer, stop and perform the captured
   rollback; do not retire the original key.
6. Use the reviewed local activation action to preserve the original private key
   only in the root tmpfs stage and place the replacement at the stable active
   path. Capture the console state again before retirement.
7. With capture active, have the actor remove the original public JWK, capture
   the after-state showing only the replacement public JWK, and have the
   attester record this second control-plane mutation.
8. Wait at least 90 seconds. Begin one bounded A129 subwindow and perform, in
   order, a replacement-key positive exchange, one original-key exchange that
   records the bounded response without enforcing any denial shape, and a final
   replacement-key positive exchange.
9. Record the window end. Bind the baseline control, overlap positive, A129
   positive-denial-positive bracket, bounded state captures, named roles,
   derived public-key descriptors, and one fixed instrument digest into the
   proposed Result.

The three attempts in step 8 use the same token endpoint, identity provider,
service account, request shape, assertion lifetime, and instrument SHA; only the
signing key role differs. The original key is never re-trusted to make a test
pass. The reviewed predicate (A147) requires the retired-key exchange to be
HTTP 401 with `access_token_supplied` false. No error type, error code, message,
or request-ID shape is pinned.

If overlap, replacement positive, local activation, retirement, any bounded
capture, settling, or bracketing control fails, execute the predeclared safe
rollback under its own bounded capture. Preserve the failure observations. A
rollback restores operation; it does not make the failed run conforming, and a
fresh attempt needs a fresh run ID and replacement key.

### Attended procedure

Do not run this procedure during build, review, CI, or an unattended session.
It requires separate authorization for five live OpenAI exchanges, two console
mutations, and one local key activation.

**This one is not reversible.** Requirement 4 edits a mapping's claim
assertion and puts it back; a conforming rotation ends with the control plane signing under a new key
and the console trusting only that key. The original private key survives only
in the run's root tmpfs stage, which does not outlive a reboot. Treat a
completed rotation as the new steady state, not as something to undo.

**Confirm the console accepts two uploaded JWKs before starting.** The whole
design depends on an overlap: upload both keys, prove an exchange on the
replacement, and only then retire the original. If the console's uploaded-JWKS
set is capped at one key, the collector cannot reach a conforming state and the
run must not be attempted, because the only alternative is a hard cutover with a
window in which neither key works. This capacity was demonstrated on 2026-08-12
by run `openai-rotation-20260812-6f6da5d4b8`: the edit surface is a JWKS JSON
textarea and it accepted a two-key set (reading 3 recorded `2` public keys).
That run was not conforming - it aborted at the replacement-key positive control
and was rolled back to the original one-key state - so the console is back at
one key, and confirming capacity at step 0 without saving remains the first act
of any fresh attempt.

Run it inside tmux, for the same reason as Requirement 4:

```bash
ssh conductor@factory.example.com
tmux new -s rotate
```

Preflight, as the checkout owner:

```bash
fm() { sudo -n -u factory-manager env -C /opt/patchyard "$@"; }
fm git status --short
fm git rev-parse HEAD
fm python3 -I tools/check-freeze-graph.py
fm python3 -I tools/check-openai-wif-signing-key-rotation.py --allow-missing-results
sudo test "$(stat -c '%U:%G:%a' \
  /etc/patchyard/openai-wif-signing.pem)" = root:root:400
```

Record the kid you are rotating away from by deriving it, never by quoting a
remembered value:

```bash
sudo -n python3 -I -c "
import importlib.util, pathlib
s = importlib.util.spec_from_file_location('base', '/opt/patchyard/tools/anthropic-wif-lifecycle.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
print(m.jwk_descriptor(m.load_public_jwk(pathlib.Path('/etc/patchyard/openai-wif-signing.pem')))['kid'])
"
```

Then start the run:

```bash
RUN_ID="openai-rotation-$(date -u +%Y%m%d)-$(openssl rand -hex 5)"
CONTROL_STAGE="/run/patchyard-openai/$RUN_ID"
RESULT="$CONTROL_STAGE/openai-signing-key-rotation.json"
sudo install -d -m 0700 -o root -g root "$CONTROL_STAGE"
sudo python3 -I /opt/patchyard/tools/openai-wif-signing-key-rotation.py \
  --run-id "$RUN_ID" --actor "<named actor>" \
  --actor-kind accountable_human --attester "<named attester>" \
  --output "$RESULT"
```

The collector asks for five console readings and three acknowledgements:

| Step | Prompt | Console state to report |
|------|--------|-------------------------|
| 1 | original one-key state | only the original kid |
| 2 | one-key state before the overlap upload | unchanged from step 1 |
| — | `OVERLAP COMPLETE` | upload the replacement's public JWK alongside the original |
| 3 | two-key overlap state | both kids present and enabled |
| — | `ACTIVATE LOCALLY` | nothing to do in the console; the collector swaps the local key |
| 4 | two-key overlap before retirement | still both kids |
| — | `RETIREMENT COMPLETE` | remove only the original public JWK |
| 5 | replacement-only state | only the replacement kid |

**The collector generates the replacement key itself** and, immediately after
generating it, prints the two-key overlap JWKS ready to paste into the
console's uploaded-JWKS textarea, followed by both derived public-key
descriptors (kid and thumbprint) for the readings. Upload only that printed
material. No private key ever crosses to the console, and there is nothing to
paste from the console into the collector except the state readings. The
printed material goes to the launching terminal's stderr, so under the
attended runner keep the tmux pane that started the run visible.

The reading shape differs from Requirement 4. Exactly these keys:
`console_location`, `identity_provider_id`, `uploaded_jwks_mode`,
`public_keys`, `subject_mapping_expression`, `mapped_service_account_id`,
`subject_mapping_enabled`. Note `subject_mapping_enabled`, not `enabled`.
`public_keys` is a list, each entry exactly `kid`, `jwk_thumbprint_sha256`,
`enabled`. Booleans are strictly boolean. Report the entries in any order:
duplicates are refused, but ordering is canonicalisation, not evidence, so the
collector sorts the membership by `(kid, jwk_thumbprint_sha256)` before
recording it.

There are two settling floors and, after retirement, a bounded subwindow
carrying the A129 bracket: a positive on the replacement, the denial attempt on
the retired key, and a second positive on the replacement.

The first of those floors is followed by a bounded retry, so expect the overlap
positive control to sit silent for up to six minutes before it either succeeds
or gives up: four attempts, 90 seconds apart. Every attempt journals its receipt
before it is required positive, so a failure now preserves the provider's HTTP
status, error type, and request id rather than losing them. Nothing else in the
run retries - every other exchange is one attempt exactly, and the checker
enforces that.

**Recovery is guided, and it decides the target for you.** Any failure after
the overlap upload sends `main()` into `capture_safe_rotation_rollback`, which
takes a bounded reading of the current console state, works out which state is
safe, and prompts for it. Expect a rollback capture on the failure path in
addition to the prompts in the table above.

The target it picks depends on how far the run got, which is why it is not
simply "put the original back":

| Local active key | Retirement confirmed | Rollback target |
|---|---|---|
| original | — | original one-key state |
| replacement | no | two-key overlap state |
| replacement | yes | replacement-only state |

The third row is the one to understand before you are staring at it. Once
retirement has succeeded, the safe state is the replacement alone: the retired
key is never re-trusted to recover a failed run, and the console is left as it
already is. If the console is already in the target state the collector records
`safe_state_already_present` and asks nothing.

Rollback readings are forgiving where the run itself is not: a malformed
reading during recovery is re-prompted instead of aborting, because the
reading is operator typing, not a provider observation, and the 2026-08-13 run
`openai-rotation-20260813-0ad23033ed` lost its rollback to exactly that. A
substantive mismatch - a console genuinely not in the target state - still
fails the rollback.

If the rollback itself fails, that is recorded as `rollback_failed` in the
terminal record rather than being lost, and the console is then in a state you
must reconcile by hand. A rollback restores operation; it does not make the
failed run conforming, and a fresh attempt needs a fresh run ID and a fresh
replacement key.

Check the terminal record without editing it:

```bash
sudo python3 -I /opt/patchyard/tools/check-openai-wif-signing-key-rotation.py \
  --observation "$RESULT"
```

**After a successful run the live kid has changed.** Re-derive it with the
command above and update anything that records it. The uploaded JWKS and the
control plane must agree; if they do not, the seat cannot mint.

`--evidence` mode now passes on the committed Result: A147 completed the
deferred predicate as HTTP 401 with no bearer, and flipped
`qualification_evidence` to true. Requirement 5 is Proven. A later conforming
run is born with the same enforced predicate.

## What remains unchanged

- Requirement 2 is not implemented here.
- No control-plane mutation or provider call occurred while building this path.
- No frozen source or committed Result is modified.
- No `credential_qualified` value changes.
- Neither synthetic Fixture is a Result or qualification Evidence.
- No Requirement becomes Proven from this change alone, and OpenAI remains not
  Qualified.
