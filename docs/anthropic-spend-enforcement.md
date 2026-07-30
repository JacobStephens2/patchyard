# Anthropic A-5 requirement 2: provider-side spend enforcement

## Built contract and live disposition

The PR #78 contract placed the intended limit on the dedicated `Patchyard Factory`
workspace (`wrkspc_000000000000000000000000`), not to a guest-side counter and
not to the Patchyard Anthropic organization as a whole. The reviewed operational
workspace cap is $50.00 per month. The attended qualification temporarily
replaces it with a $1.00 `notify_and_pause` cap and makes one minimal
`claude-opus-5` probe through the same five-minute WIF and read-only Firecracker
delivery path as requirement 1. That fixture succeeds only when Anthropic
rejects `/v1/messages` with a spend-, credit-, or billing-attributable error.
The operator then restores $50.00 before collecting the final cost report.

A115 supersedes that one-probe qualification contract for future Anthropic
requirement-2 work. Its successor proof uses an
acceptance-refusal-acceptance sequence, separates spend already above a lowered
cap from spend incurred after cap activation, and starts only after every
conceded A78 defect and a separately reviewed clean-worker replacement are
resolved. A115 does not qualify the PR #78 attempts.

The first-party [rate-limit documentation](https://platform.claude.com/docs/en/api/rate-limits)
states that all applicable organization and workspace limits are evaluated.
The [workspace documentation](https://platform.claude.com/docs/en/manage-claude/workspaces)
allows a workspace limit below the organization limit. A read-only inspection
of the live Console interface on 2026-07-29 found client implementation text
that calculates the effective displayed limit as the minimum of the
organization and workspace values and refuses a workspace value above the
organization value. That proves the configuration surface and client behavior,
not independent server-side workspace enforcement. A115 requires the controlled
live provider sequence to establish the Factory-scoping property.

The Console dialog displays only the dollar amount; it has no enforcement-mode
selector. The `notify_and_pause` value above comes from the first-party Console
implementation, which posts that exact action when it saves the displayed
workspace limit. It is not represented as a user-selected UI observation.

Under the PR #78 contract, provider denial with an attributable error response
was the qualification event. A115 additionally permits causal attribution from
the complete controlled sequence even when the refusal does not name the cap.
The Anthropic
[Cost Report API](https://platform.claude.com/docs/en/api/usage-cost-api)
does not substitute for that denial; it measures the dedicated workspace's
month-to-date cost after the denial, when no later calls have occurred. Cost
Report `amount` values are USD minor units and are converted from cents before
the fixture records `observed_spend_at_denial_usd` and
`measured_overshoot_usd`. The latter is the amount above the exact $1.00
provider cap. There is deliberately no accepted overshoot ceiling. This first
qualification was intended to establish the observed baseline required by
A113; the unsuccessful attempts instead establish an escalation record.

### Live attempts and A9 escalation

The initial 2026-07-29 attempt used eight large requests separated by five
seconds. Anthropic accepted all eight even though their eventual usage exceeded
the temporary cap, and the fixture failed closed because it observed no denial.
Its sanitized failure record preserves the exact usage, exact billed cost once
reported, cap history, and failure diagnostic. That attempt established that a
short request-count ramp is not a safe bound for delayed provider enforcement.
The record is
`research/isolation/results/anthropic-spend-enforcement-initial-failure.json`.
The one permitted repair does not generate another ramp: after Anthropic's Cost
Report records the already-incurred workspace spend above $1.00, it lowers the
workspace cap again and submits exactly one tiny request. Acceptance of that
request is terminal failure; only an attributable provider refusal qualifies.

The repaired fixture ran once as
`anthropic-s2-20260730-4d80267abf`. Anthropic returned HTTP 400 to the one tiny
Messages request, but the response did not satisfy the pre-bound error envelope
and spend-attribution checks. The failed guest exported only the allowlisted
status `anthropic-spend-unexpected-response-400`; by design it did not export
the unaccepted provider body. Cost Report snapshots through 42 minutes after
the repair remained exactly $7.68168, but the initial cost took about 2 hours
51 minutes to appear. Those snapshots prove only that no new cost had reported
yet, not that the repaired request added $0. The initial settled total is
**$6.68168 above the displayed $1.00 value**; it is not an A113 overshoot
measured at an attributable denial.

The Console readback was `$7.68 of $1.00` before restoration and `$7.68 of
$50.00` afterward; the organization limit remained $500.00. The operator
reported 02:05Z and 02:07Z for those observations, but both times precede the
worker's journaled 02:21:34Z-02:21:53Z execution interval. The committed failure
record preserves that inconsistency explicitly and does not use those times as
ordering evidence.

Because the raw provider error is unavailable, the HTTP 400 cannot be bound to
workspace spend enforcement and does not satisfy A113 clause 2. The runtime
also set its fail-closed `BOUNDARY_TAINTED` marker at 02:21:53Z; subsequent
worker qualification stops at that marker. PR #78 consumed its A9 repair loop
and correctly stopped. A115 later authorized one successor implementation and
attempt plus a fresh A9 repair loop, but only after every conceded A78 defect
and a separately reviewed clean-worker replacement are resolved. It does not
authorize clearing the marker or reusing the current worker. The terminal
record is
`research/isolation/results/anthropic-spend-enforcement-repair-failure.json`.

The committed fixture binds the deterministic request, deterministic patch,
production-parity manifest, complete image recipe, and exact two-file host
contract to current source. The ext4 rootfs remains explicitly observational
as `observed_rootfs_sha256`, for the reproducibility reason documented under
requirement 1. A successful fixture would bind the before, temporary, and
restored workspace values, require the organization value to remain identical,
and require it to stay safely above the workspace operational value. Neither
failure record contains a bearer or assertion.

This builds the requirement 2 path and includes the A114 teardown-status
repair, but the live fixture does **not** qualify requirement 2. It also does
not prove expiry, revocation, or credential-bearing crash cleanup.
Anthropic and every other provider therefore remain
`credential_qualified: false`, and behavioral acceptance remains paused.

## Attended live procedure (historical; superseded by A115)

Use an authenticated Anthropic Console session only for cap readback and cap
changes. The public Admin API currently exposes cost reports but no documented
workspace spend-limit mutation endpoint. Never place that Console session or a
standing Anthropic inference key in Factory state or `/srv/orchestration/env.tpl`.
In particular, never introduce a bare `ANTHROPIC_API_KEY`.

1. Converge and qualify the exact reviewed commit. Capture the isolated
   workspace baseline through the public Cost Report API:

   ```bash
   tools/anthropic-spend-evidence.py snapshot \
     --output /run/patchyard-anthropic/spend-before.json
   ```

2. In Anthropic Console, select the explicit Patchyard organization and the explicit
   `Patchyard Factory` workspace. Read the organization cap and current workspace
   cap. Record only the values and observation time in a root-only temporary
   `cap-readbacks.json` object. Set the workspace monthly spend limit to $1 with
   the pause behavior, read it back, and record that observation. Do not change
   the organization limit.
3. On the control plane, run the paid fixture once:

   ```bash
   sudo /usr/local/sbin/patchyard-run-anthropic-issuance run-spend \
     /var/lib/patchyard/snapshots/current \
     /var/lib/patchyard/artifacts/anthropic-spend-enforcement
   ```

4. Immediately restore the workspace cap to $50, read it back, and record the
   organization value again. The readback file has this credential-free shape:

   ```json
   {
     "schema_version": 1,
     "provider": "anthropic",
     "organization_id": "aaadc747-869a-42d2-af51-58a5be8e3b7f",
     "workspace_id": "wrkspc_000000000000000000000000",
     "before": {
       "observed_at": "RFC3339",
       "workspace_monthly_limit_usd": "50.00",
       "organization_monthly_limit_usd": "OBSERVED",
       "enforcement": "notify_and_pause"
     },
     "qualification": {
       "observed_at": "RFC3339",
       "workspace_monthly_limit_usd": "1.00",
       "organization_monthly_limit_usd": "OBSERVED_UNCHANGED",
       "enforcement": "notify_and_pause"
     },
     "restored": {
       "observed_at": "RFC3339",
       "workspace_monthly_limit_usd": "50.00",
       "organization_monthly_limit_usd": "OBSERVED_UNCHANGED",
       "enforcement": "notify_and_pause"
     }
   }
   ```

5. Wait for the Cost Report API to include all Factory workspace usage, capture
   an after snapshot, and finalize the worker evidence. The helper converts the
   API's USD-cent amounts to USD:

   ```bash
   tools/anthropic-spend-evidence.py snapshot \
     --output /run/patchyard-anthropic/spend-after.json
   tools/anthropic-spend-evidence.py finalize \
     --worker-evidence /var/lib/patchyard/artifacts/anthropic-spend-enforcement/evidence.json \
     --before-cost /run/patchyard-anthropic/spend-before.json \
     --after-cost /run/patchyard-anthropic/spend-after.json \
     --cap-readbacks /run/patchyard-anthropic/cap-readbacks.json \
     --output research/isolation/results/anthropic-spend-enforcement.json
   ```

6. Rerun requirement 1 because the shared guest image and host contract have
   changed. Copy only its sanitized `evidence.json`, then run both Anthropic
   checkers and the complete repository gate set. Remove the root-only
   temporary snapshots and readbacks after the committed sanitized fixture is
   verified.

The deployed PR #78 repair makes exactly one provider probe. If that probe is
accepted or returns an error that cannot be attributed to spend, credit, or
billing, the repair fails closed and A9 requires escalation with the failure
log rather than another implementation or paid attempt. That stop condition
occurred on 2026-07-30. This procedure is retained for reviewability and must
not be repeated. A115 successor work uses the accepted three-phase contract and
its separately authorized A9 budget.
