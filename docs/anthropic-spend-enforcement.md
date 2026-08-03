# Anthropic A-5 requirement 2: provider-side spend enforcement

## Qualification contract

A120 amends A115's baseline mechanism after the August rollover, and A121
amends its settlement condition after the measured August 2-3 rollover.
Anthropic requirement 2 qualifies only through a controlled three-phase provider
sequence in the dedicated `Patchyard Factory` workspace
(`wrkspc_000000000000000000000000`):

1. Anthropic accepts one pre-sized Messages request while the workspace
   monthly limit is the reviewed operational $50.00. Its uncached input alone
   has a reviewed conservative cost floor of $1.50.
2. After that request's cost is settled above $1.00, only the Factory workspace
   limit is lowered to $1.00, below the now-settled workspace spend. Anthropic
   refuses one byte-identical request.
3. The workspace limit is restored to $50.00. After the refusal's UTC day has
   closed, its workspace-attributed Cost Report row exists, and the subordinate
   10,260-second floor has elapsed, Anthropic accepts the same request again.

Each phase uses a fresh five-minute WIF bearer for the same Factory service
account, rule, workspace, model, and endpoint. The worker host makes exactly
one provider request through the A117 one-shot transport; the general-purpose
guest receives neither the bearer nor a provider route. The $500.00
organization monthly limit remains unchanged and
nonbinding, and no other workspace changes. The two accepted requests bracket
the refusal and exclude credential, request-validity, model-availability, and
organization-limit causes. HTTP 429, `rate_limit_error`, and
`overloaded_error` are rejected rather than attributed to spend enforcement.

### Fixed body, token floor, and cache exclusion

The transport constructs one 800,306-byte body with SHA-256
`b3751a164cde71cbca2fe5de05d3fc8a836649e46114c616cdaf4a210bdfccf4`.
Its user message contains two text blocks, each byte-identical to the exact
400,083-byte synthetic prompt used by the July eight-request attempt. That
attempt recorded 1,536,296 uncached input tokens for eight accepted,
byte-identical calls and zero cache-read or cache-creation tokens: 192,037
uncached input tokens per call. Two independently delimited copies therefore
pre-compute to 384,074 uncached input tokens. The source binds a deliberately
lower conservative floor of 300,000 tokens, leaving 84,074 tokens of margin
against the same-model calibration. At A119's $5 per million input-token
price, the bound floor is $1.50, $0.50 above the temporary value. Output is
still limited to one token and is not part of the floor. The 384,074-token
projection is also below Opus 5's documented default 1-million-token
[context window](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model),
so it requires no context-window beta or model change.

Prompt caching cannot reduce that floor. Anthropic's
[prompt-caching contract](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
enables automatic caching through a top-level `cache_control` field and
explicit caching through a content-block `cache_control` field. The exact
three-key request body contains neither, uses no tools or server-side loop,
and the exact header-only curl configuration cannot enable caching. As a
postcondition rather than a sizing experiment, each expected positive-control
response must report both `cache_creation_input_tokens` and
`cache_read_input_tokens` as zero and at least 300,000 ordinary input tokens.
Failure stops the run after that one request; it never authorizes a resized
retry. The same fixed body is used in all three phases.

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

The fixture uses the Anthropic Cost Report API's daily buckets for the dedicated
workspace. Its minor-unit amounts are converted to USD. A121 requires each
snapshot to be captured only after the UTC day containing the request it
accounts for has closed and to contain a Factory workspace row for that exact
day. Sixteen probes over 9.07 hours on August 2 returned no such row; the exact
`$3.84074` row appeared 13 minutes after UTC day close. Elapsed time alone is
therefore not settlement evidence.

Each month-to-date query sets the maximum daily `limit` of 31 and still exhausts
`has_more`/`next_page` through the terminal page. This prevents the API's
default seven daily buckets from silently truncating a month-length read. A
read with no Factory workspace row fails closed rather than producing a zero
snapshot. Snapshot schema 2 records every UTC day for which the complete read
returned a Factory row.

The already-captured pre-activation snapshot is schema 1 because it predates
A121. The finalizer accepts that one legacy shape only for the measured August
2 request at the exact `$3.84074`; its row and rollover are the observations
that caused A121. No other schema-1 snapshot is admissible, and the pending
post-refusal snapshot must use schema 2 and name the refusal's UTC day.

The 10,260-second minimum remains subordinate to the UTC-day-close condition,
both before cap activation and after the refusal, so a request immediately
before midnight cannot be treated as settled immediately after midnight. The
first window proves that the self-seeding phase-1 charge settled above $1.00 and
prevents late phase-1 cost from being counted as refusal cost. These are
settlement floors, not overshoot ceilings.

The final evidence records separate figures:

- `settled_spend_before_activation_usd` - workspace month-to-date spend,
  including the first named acceptance, before lowering the cap;
- `preexisting_excess_at_activation_usd` - that settled amount minus $1.00;
  the field name means pre-existing at cap activation, not inherited from a
  prior request or month;
- `settled_spend_after_refusal_usd` - workspace spend after both settlement
  conditions; and
- `incremental_spend_before_refusal_usd` - the latter minus the former.

The measurement also records
`pre_activation_workspace_cost_utc_day` and
`post_refusal_workspace_cost_utc_day`; each must equal its corresponding
provider request's UTC day.

Only `incremental_spend_before_refusal_usd` is the observed enforcement
overshoot. It may be zero, and it has no preset ceiling. The settled first
acceptance must put pre-activation spend strictly above $1.00 and below the
$50.00 positive-control value. If it settles at $1.00 or less, the sequence
stops before the temporary cap or second provider request; no larger retry is
authorized. Post-refusal settled spend has no $50.00 schema ceiling. If the
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
The client uses HTTP/1.0, `Connection: close`, one fixed Messages URL, the
digest-bound two-block body above, a one-token output limit, no redirect, and
no retry. Before accepting the result, the launcher independently reads one
admitted-new packet, zero
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
environment. The complete worker install-task source is digest-bound, and the
exact installed launcher and one-shot destinations each have one Ansible
writer. The runner independently compares their installed bytes to the checkout
sources before bearer issuance, and one reviewed SHA-256 binds the complete
runner source so those comparisons cannot be bypassed or made self-referential
without changing the binding. The exact installed one-shot client joins the
spend host-contract digest; its complete source and curl header-only
configuration are also pinned by the source checker. A second reviewed SHA-256
binds the complete launcher source, including every executable function
definition, transport setup, preflight, counter and set readback, teardown
helper, and call site. The checker also requires one exact adjacent
setup-preflight-transfer sequence and the exact three-way IPv6 comparison. A
later replacement definition, dead-code preflight, fabricated kernel readback,
intervening transport change, rule or qualifier change, or early bypass changes
the complete launcher digest. The complete spend guest source is independently
digest-bound, so its credential-drive absence, empty provider-hosts file, and
receipt-cardinality checks cannot be dead-coded or short-circuited without
changing the binding. The guest image recipe remains a complete binding of the
guest surface.
Requirement 1 separately pins its exact Models request and two loopback calls,
then rejects a remaining provider-capable guest command.

A provider response that does not meet the bounded A115/A120 phase contract fails
with a response-stage diagnostic, not the obsolete `denial-not-observed` label.
Empty bodies fail as `empty-body`; whitespace, malformed JSON, multiple
documents, and other non-single-object inputs fail before jq can treat an
absent document as a successful predicate. A missing request-ID header retains
the observed HTTP status and bounded response-shape class in the diagnostic.
Provider acceptance in the temporary-refusal phase emits the bounded
`anthropic-spend-provider-response-rejected-200-provider-accepted-workspace-scope-qualified-negative`
diagnostic and exits nonzero before the positive-control usage postcondition.
Under A120, acceptance itself is the qualified negative for workspace-scope
enforcement even if its usage breakdown is unexpected; it is not permission to
retry. In the operational and restored phases, an accepted response with fewer
than 300,000 ordinary input tokens or any cache-read or cache-creation tokens
fails immediately.

The A114 child-launcher repair also treats output purge, ownership and mode
normalization, network-lock release, and terminal publication failures as
teardown failures. Network-lock release occurs before terminal publication so
an unlock failure is represented by `state: teardown_failed`. Any teardown
failure forces a nonzero process exit even if the child itself succeeded.

## Attended live procedure

This A121 amendment is source-only and authorizes no live action. The remaining
procedure resumes only
after A78 has reviewed the changed source and Jacob has ruled the requirements
3+ freeze order. Never clear or reuse a `BOUNDARY_TAINTED` worker. Never add a
standing Anthropic inference key to Factory state or
`/srv/orchestration/env.tpl`, and never introduce a bare `ANTHROPIC_API_KEY`.

The sequence is inherently a multi-UTC-day procedure but remains month-scoped.
All provider, cap, and settled-cost observations must occur in one Anthropic
monthly billing period. A pre-existing
month-to-date baseline is neither required nor permitted as a hidden fourth
request: the first named acceptance creates the baseline. If the month rolls
over before the sequence completes, stop. Do not change the $1.00 binding,
resize after a live call, add a seed call, or reuse the failed eight-request
ramp.

Keep the dedicated workspace idle except for the three named phase requests
from the first acceptance until the post-refusal cost snapshot. The two
day-close conditions, subordinate elapsed floors, and that exclusive-workspace
interval make the Cost Report
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
be no wider than five minutes. A wider bracket is void and must be retaken; its
timestamps are never adjusted after capture. Do not record or claim an
enforcement-mode selector that the Console does not expose.

1. Confirm the organization limit is $500.00 and the workspace limit is
   $50.00. Record the bounded operational readback. Confirm the installed
   transport matches the reviewed A120 source, then run the one fixed-size
   first acceptance exactly once:

   ```bash
   sudo /usr/local/sbin/patchyard-run-anthropic-issuance \
     run-spend-operational \
     /var/lib/patchyard/snapshots/current \
     /var/lib/patchyard/artifacts/anthropic-spend-operational
   ```

2. Do not capture the pre-activation snapshot until the UTC day containing the
   first acceptance has closed, at least 10,260 seconds have elapsed, and Cost
   Report contains a Factory workspace row for that request day:

   ```bash
   tools/anthropic-spend-evidence.py snapshot \
     --output /run/patchyard-anthropic/settled-before.json
   ```

   For the in-flight August sequence this step is already complete. Preserve
   its measured schema-1 snapshot; do not refresh or rewrite it.

   The settled amount must exceed $1.00 and remain below $50.00. If the settled
   amount is $1.00 or less, stop. A second or larger acceptance is not
   authorized. Do not lower the cap or issue another credential. A result at
   or above $50.00 is also terminal because the operational positive control
   is ambiguous.

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
   readback. Do not wait to restore the operational cap. If the refusal command
   emitted
   `anthropic-spend-provider-response-rejected-200-provider-accepted-workspace-scope-qualified-negative`,
   preserve that exact sanitized diagnostic, its source revision, the temporary
   and restored cap readbacks, and the command's UTC bounds as the terminal
   record. This is a qualified negative for workspace-scope enforcement: stop
   without the restored provider request or any repair request, and escalate
   for Jacob's
   ruling between a Factory-scoped organization (Option 4) and a replacement
   first pair (Option 6). No differently sized call is authorized.

5. Do not capture the post-refusal snapshot until the UTC day containing the
   provider refusal has closed, at least 10,260 seconds have elapsed, and Cost
   Report contains a Factory workspace row for that request day. Then run the
   restored positive control:

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

7. Run both Anthropic checkers, the full repository gates, and the prescribed
   mutations. Delete the root-only temporary snapshots and readbacks after the
   committed evidence passes. A121's behavioral changes are confined to the
   offline spend checker, evidence finalizer, tests, and procedure; the issuance
   runner, Firecracker launcher, one-shot transport, and guest image remain
   byte-identical.
   Requirement 1's qualified
   `eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`
   host contract is therefore not stale and is not refreshed by this change.

If any phase fails, preserve the sanitized failure log. The two A120 terminal
outcomes above authorize no repair request. Other failures remain subject to at
most the one A9 live-attempt repair loop authorized by A115; then escalate
rather than making another provider request. A116 through A118 and the later
A118-findings work-record authorization cover only pre-attempt source work and
added no provider request or live repair loop.

Requirement 2 remains unqualified until the completed A115/A120/A121 result
lands.
Behavioral acceptance remains paused, all 13 `credential_qualified` flags stay
false, and requirement 3 must not begin.
