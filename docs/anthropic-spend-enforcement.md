# Anthropic A-5 requirement 2: provider-side spend enforcement

## Qualified contract

The hard limit belongs to the dedicated `Patchyard Factory` workspace
(`wrkspc_000000000000000000000000`), not to a guest-side counter and not to the
Patchyard Anthropic organization as a whole. The reviewed operational workspace cap
is $50.00 per month. The attended qualification temporarily replaces it with a
$1.00 `notify_and_pause` cap, makes synthetic paid `claude-opus-5` requests
through the same five-minute WIF and read-only Firecracker delivery path as
requirement 1, and stops only when Anthropic rejects `/v1/messages` with a
spend-, credit-, or billing-attributable error. It then restores $50.00 before
collecting the final cost report.

The first-party [rate-limit documentation](https://platform.claude.com/docs/en/api/rate-limits)
states that all applicable organization and workspace limits are evaluated.
The [workspace documentation](https://platform.claude.com/docs/en/manage-claude/workspaces)
allows a workspace limit below the organization limit. A read-only inspection
of the live Console interface on 2026-07-29 confirmed the current implementation:
the workspace effective limit is the minimum of the organization enforced
limit and every workspace `notify_and_pause` limit. The same interface refuses
a workspace value above the organization value. A lower workspace limit
therefore binds independently as the narrower ceiling while the unchanged
organization ceiling continues to apply alongside it. This satisfies A113
clause 2 without changing or endangering Patchyard's organization limit.

The provider denial is the qualification event. The Anthropic
[Cost Report API](https://platform.claude.com/docs/en/api/usage-cost-api)
does not substitute for that denial; it measures the dedicated workspace's
month-to-date cost after the denial, when no later calls have occurred. The
fixture records `measured_overshoot_usd` as the amount above the exact $1.00
provider cap, or zero when Anthropic refuses the next estimated request before
recorded spend crosses the cap. There is deliberately no accepted overshoot ceiling.
The first live run establishes the baseline required by A113.

The committed fixture binds the deterministic request, deterministic patch,
production-parity manifest, complete image recipe, and exact two-file host
contract to current source. The ext4 rootfs remains explicitly observational
as `observed_rootfs_sha256`, for the reproducibility reason documented under
requirement 1. Cap readbacks bind the before, temporary, and restored workspace
values; the organization value must be identical in all three observations and
safely above the workspace operational value. The fixture never records a
bearer or assertion.

This proves only requirement 2 and includes the A114 teardown-status repair.
It does not prove expiry, revocation, or credential-bearing crash cleanup.
Anthropic and every other provider therefore remain
`credential_qualified: false`, and behavioral acceptance remains paused.

## Attended live procedure

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

5. Wait for the Cost Report API to include all successful request IDs, capture
   an after snapshot, and finalize the worker evidence:

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

The eight-call maximum is a qualification cost bound, not an overshoot
acceptance ceiling. A run that does not receive a provider-attributable denial
within that bound fails closed and is not qualification evidence.
