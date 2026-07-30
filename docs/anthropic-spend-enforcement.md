# Anthropic A-5 requirement 2: provider-side spend enforcement

## Qualification contract

A115 supersedes the unsuccessful PR #78 one-probe contract. Anthropic
requirement 2 now qualifies only through a controlled three-phase provider
sequence in the dedicated `Patchyard Factory` workspace
(`wrkspc_000000000000000000000000`):

1. Anthropic accepts one minimal Messages request while the workspace monthly
   limit is the reviewed operational $50.00.
2. After that request's cost is settled, only the Factory workspace limit is
   lowered to $1.00, below the already-settled workspace spend. Anthropic
   refuses one byte-identical request.
3. The workspace limit is restored to $50.00. After the refusal has had a full
   settlement window, Anthropic accepts the same request again.

Each phase uses a fresh five-minute WIF bearer for the same Factory service
account, rule, workspace, model, and endpoint. The worker host makes exactly
one provider request through the A117 one-shot transport; the general-purpose
guest receives neither the bearer nor a provider route. The $500.00
organization monthly limit remains unchanged and
nonbinding, and no other workspace changes. The two accepted requests bracket
the refusal and exclude credential, request-validity, model-availability, and
organization-limit causes. HTTP 429, `rate_limit_error`, and
`overloaded_error` are rejected rather than attributed to spend enforcement.

The refusal evidence contains only its HTTP status, request ID, response type,
error type, a SHA-256 of the message, a bounded key-shape descriptor, and a
classification of whether the message names spend. Required-key containment
allows provider-added fields; the raw error message and credential never cross
the result boundary. A refusal need not name the workspace limit when the full
A115 sequence supplies the causal attribution.

The first-party [rate-limit documentation](https://platform.claude.com/docs/en/api/rate-limits)
states that applicable organization and workspace limits are evaluated. The
[workspace documentation](https://platform.claude.com/docs/en/manage-claude/workspaces)
allows a workspace limit below the organization limit. The Console limit
dialog exposes a dollar value, not an enforcement-mode selector. Its displayed
value, client implementation, notifications, or Cost Report plateau are not
independent proof of server-side enforcement. Only the provider refusal inside
the bracketing sequence qualifies.

## Spend accounting

The fixture uses the Anthropic Cost Report API for the dedicated workspace. Its
minor-unit amounts are converted to USD. Because Anthropic reporting was
observed to take about 2 hours 51 minutes during the first attempt, A115 binds
a minimum 10,260-second settlement window both before cap activation and after
the refusal. The first window prevents late phase-1 cost from being counted as
refusal cost. These are settlement floors, not overshoot ceilings.

The final evidence records separate figures:

- `settled_spend_before_activation_usd` - workspace month-to-date spend before
  lowering the cap;
- `preexisting_excess_at_activation_usd` - that settled amount minus $1.00;
- `settled_spend_after_refusal_usd` - workspace spend after the full settlement
  window; and
- `incremental_spend_before_refusal_usd` - the latter minus the former.

Only `incremental_spend_before_refusal_usd` is the observed enforcement
overshoot. It may be zero, and it has no preset ceiling. Pre-activation spend
must remain below the $50.00 positive-control value so the first acceptance is
not ambiguous. That eligibility condition is applied to spend that already
exists before activation; it is not a limit on the recorded incremental
figure. Post-refusal settled spend has no $50.00 schema ceiling. If the
positive controls or timing become ambiguous, the result is unqualified and
the figures are never relabelled to make it pass.

## Historical failures retained

The first 2026-07-29 attempt made eight large requests. Anthropic accepted all
eight; later Usage and Cost reports settled at $7.68168. The guest failed
closed because no denial was observed. Its boundary-taint marker and the
reviewed destroy-and-replace history are retained in
`research/isolation/results/anthropic-spend-enforcement-initial-failure.json`.

The one PR #78 repair ran as `anthropic-s2-20260730-4d80267abf`. Anthropic
returned HTTP 400, but the old exact-key parser rejected the response and did
not export a sanitized shape. The operator-reported `$7.68 of $1.00` and
restored `$7.68 of $50.00` timestamps precede the worker's journaled execution
interval, so they cannot order that refusal against the cap. Cost Report was
still $7.68168 only 2,543 seconds after the repair - too early to prove the
repair added $0. The $6.68168 figure is merely initial settled spend above the
displayed $1.00 value; it is not denial overshoot. The corrected terminal
record is
`research/isolation/results/anthropic-spend-enforcement-repair-failure.json`.

Those attempts remain unqualified. A115 supplies a distinct successor
authorization and A9 budget; it does not rewrite the historical outcome.

## Fail-closed implementation

The control-plane runner exposes three separate actions:

- `run-spend-operational`
- `run-spend-refusal`
- `run-spend-restored`

The phase and expected workspace value are in the short-lived capability and
run manifest. The worker resolves one reviewed Anthropic address, places the
fixed client in a dedicated host network namespace, disables IPv6 before
link-up, independently reads the namespace and interface controls, and admits
one conntrack ID. Retransmits on that ID remain possible; every later
connection is rejected.
The client uses HTTP/1.0, `Connection: close`, one fixed Messages URL, one
deterministic one-token body, no redirect, and no retry. Before accepting the
result, the launcher independently reads one admitted-new packet, zero
rejected packets, one admitted conntrack ID, zero rejected conntrack IDs, and
one used source from the kernel. A mismatch preserves all five values in a
bounded diagnostic. It then
deletes the bearer, raw headers and body, namespace, veth, and rules before it
boots the spend guest.

The spend guest receives only credential-free issuance metadata, the bounded
provider observation, and the host-owned transport receipt. Its provider-hosts
file is empty, no credential drive is attached, and the host additionally
requires zero rejected guest-egress packets. This removes the false A116 claim
that a command-name scan could make a general-purpose parity image a one-call
environment. The exact installed one-shot client joins the spend host-contract
digest; its complete source and curl header-only configuration are also pinned
by the source checker. The complete marked namespace policy has one verified
digest, so a qualifier, drop policy, or terminal rejection cannot change while
leaving the source gate green. The guest image recipe remains a complete
binding of the guest surface. Requirement 1 separately pins its exact Models
request and two loopback calls, then rejects a remaining provider-capable guest
command.

A provider response that does not meet the bounded A115 phase contract fails
with a response-stage diagnostic, not the obsolete `denial-not-observed` label.
Empty bodies fail as `empty-body`; whitespace, malformed JSON, multiple
documents, and other non-single-object inputs fail before jq can treat an
absent document as a successful predicate. A missing request-ID header retains
the observed HTTP status and bounded response-shape class in the diagnostic.

The A114 child-launcher repair also treats output purge, ownership and mode
normalization, network-lock release, and terminal publication failures as
teardown failures. Network-lock release occurs before terminal publication so
an unlock failure is represented by `state: teardown_failed`. Any teardown
failure forces a nonzero process exit even if the child itself succeeded.

## Attended live procedure

This procedure starts only after A78 has reviewed the successor source and the
clean-worker replacement plan. Never clear or reuse a `BOUNDARY_TAINTED`
worker. Never add a standing Anthropic inference key to Factory state or
`/srv/orchestration/env.tpl`, and never introduce a bare
`ANTHROPIC_API_KEY`.

The sequence is month-scoped. All provider, cap, and settled-cost observations
must occur in one Anthropic monthly billing period. For the authorized attempt,
July's already-settled $7.68168 makes it possible to lower the temporary value
below settled spend without generating a ramp. If the month rolls over before
the sequence completes, or if the current month-to-date baseline is no longer
above $1.00 and below $50.00, stop and escalate to Jacob for a new ruling. Do
not create spend to manufacture a baseline, change the $1.00 binding, or reuse
the failed eight-request ramp.

Keep the dedicated workspace idle except for the three named phase requests
from the first acceptance until the post-refusal cost snapshot. The two full
settlement windows and that exclusive-workspace interval make the Cost Report
difference the observed refusal increment rather than an upper bound that may
contain a late positive-control charge.

Use a root-only working directory. Record Console readbacks with control-plane
UTC commands immediately before and after each observation. Each phase object
has this shape:

```json
{
  "captured_before_at": "RFC3339",
  "captured_after_at": "RFC3339",
  "workspace_monthly_limit_usd": "50.00 or 1.00",
  "organization_monthly_limit_usd": "500.00",
  "capture_method": "operator_console_readback_bounded_by_control_plane_utc"
}
```

The complete `cap-readbacks.json` is schema version 2, identifies the
organization and workspace, and has `operational_acceptance`,
`temporary_refusal`, and `restored_acceptance` objects. Each UTC bracket must
be no wider than five minutes. Do not record or claim an enforcement-mode
selector that the Console does not expose.

1. Confirm the organization limit is $500.00 and the workspace limit is
   $50.00. Record the bounded operational readback. Run the first positive
   control:

   ```bash
   sudo /usr/local/sbin/patchyard-run-anthropic-issuance \
     run-spend-operational \
     /var/lib/patchyard/snapshots/current \
     /var/lib/patchyard/artifacts/anthropic-spend-operational
   ```

2. Wait at least 10,260 seconds after the first acceptance and until Cost
   Report contains the positive-control charge, then capture the settled
   pre-activation snapshot:

   ```bash
   tools/anthropic-spend-evidence.py snapshot \
     --output /run/patchyard-anthropic/settled-before.json
   ```

   The settled amount must exceed $1.00 and remain below $50.00.

3. Change only the Patchyard Factory workspace limit to $1.00. Confirm the
   organization limit remains $500.00 and record the bounded temporary
   readback. Immediately run the refusal phase once:

   ```bash
   sudo /usr/local/sbin/patchyard-run-anthropic-issuance \
     run-spend-refusal \
     /var/lib/patchyard/snapshots/current \
     /var/lib/patchyard/artifacts/anthropic-spend-refusal
   ```

4. Immediately restore only the Factory workspace limit to $50.00. Confirm the
   organization limit remains $500.00 and record the bounded restored
   readback. Do not wait to restore the operational cap.

5. Wait at least 10,260 seconds after the provider refusal and until Cost
   Report is settled. Capture the post-refusal snapshot. Then run the restored
   positive control:

   ```bash
   tools/anthropic-spend-evidence.py snapshot \
     --output /run/patchyard-anthropic/settled-after.json
   sudo /usr/local/sbin/patchyard-run-anthropic-issuance \
     run-spend-restored \
     /var/lib/patchyard/snapshots/current \
     /var/lib/patchyard/artifacts/anthropic-spend-restored
   ```

6. Finalize the credential-free evidence:

   ```bash
   tools/anthropic-spend-evidence.py finalize \
     --operational-evidence /var/lib/patchyard/artifacts/anthropic-spend-operational/evidence.json \
     --refusal-evidence /var/lib/patchyard/artifacts/anthropic-spend-refusal/evidence.json \
     --restored-evidence /var/lib/patchyard/artifacts/anthropic-spend-restored/evidence.json \
     --settled-before /run/patchyard-anthropic/settled-before.json \
     --settled-after /run/patchyard-anthropic/settled-after.json \
     --cap-readbacks /run/patchyard-anthropic/cap-readbacks.json \
     --output research/isolation/results/anthropic-spend-enforcement.json
   ```

7. Rerun requirement 1 because the shared guest image, runner, and launcher have
   changed. Copy only its sanitized evidence. Run both Anthropic checkers, the
   full repository gates, and the prescribed mutations. Delete the root-only
   temporary snapshots and readbacks after the committed evidence passes.

If any phase fails, preserve the sanitized failure log and use at most the one
A9 live-attempt repair loop authorized by A115. A116, A117, and A118 authorized
only pre-attempt source work; none added a provider request or another live
repair loop. Then escalate rather than making another provider request.

Requirement 2 remains unqualified until the completed A115 result lands.
Behavioral acceptance remains paused, all 13 `credential_qualified` flags stay
false, and requirement 3 must not begin.
