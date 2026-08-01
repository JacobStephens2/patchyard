# A78 operational-record review - quarantined successor

Review target:
`d56d71e29ccac41fe4ce7e0f0e51a7681b7dcf1b`

Reviewer: Opus 5 `[xhigh]` via Claude Code on Anthropic, seat A78, in a
fresh detached worktree under A87.

Canonical review:
<https://github.com/JacobStephens2/patchyard/pull/79#issuecomment-5138195261>

## Access limit

The reviewer's available DigitalOcean token was the revoked predecessor and
returned HTTP 401. A78 therefore did not independently verify droplet
existence, the settled firewall readback, or the predecessor HTTP 404. A78
reviewed the committed record, executable path, qualification flags, and
internal consistency, and treated the build seat's cloud observations as
reported rather than independently corroborated.

## Requested checks

A78 found all five requested properties:

1. the wrapper's nonzero status and terminal stop are preserved;
2. the record assigns no unobserved cause to the A101 timeout;
3. the later settled-firewall readback is not relabeled as a passing A101
   probe;
4. successor `588858421` is operationally quarantined despite the absent
   automated taint marker; and
5. negative scope is complete, all 13 `credential_qualified` values remain
   false, and the deliberately stale requirement-1 fixture was not refreshed.

A78 also confirmed that A101 targeted successor `588858421`'s recorded private
address, `10.132.0.15`, rather than a stale address for the destroyed worker.
The review found the fail-closed stop correct under the authorized sequence and
reported no finding against the operational record.

## Forward-looking finding

A78 identified a twice-seen failure shape. Session 16 recorded A101 timing out
while the new worker firewall attachment remained in `pending_changes`; after
the firewall reached `status=succeeded`, direct TCP and both management probes
passed. The July 31 sequence also timed out on A101 immediately after a worker
replacement, and its later post-stop firewall readback was `succeeded` with
zero pending changes.

A78 described the leading hypothesis as an A101 race against firewall
attachment propagation and recommended that the next bounded sequence add one
of these desired-state protections before a timeout becomes terminal:

- wait until the firewall reports `status=succeeded` and zero
  `pending_changes` before A101; or
- give A101 a bounded readiness retry.

The recommendation does not alter the July 31 stop or authorize either source
change.

## Operational state

A78 made the resulting capacity state explicit: Factory currently has no
qualified worker. Predecessor `588826948` is destroyed, and successor
`588858421` is quarantined and ineligible for repair or reuse. Any next bounded
sequence must provision and qualify a fresh worker and dispose of the
quarantined successor; it cannot rerun A101 against `588858421`.

## Position

A78 returned **PASS with no finding against the operational record**. The
desired-state readiness improvement and the no-qualified-worker state were
left for Jacob's next bounded-sequence decision under A1.
