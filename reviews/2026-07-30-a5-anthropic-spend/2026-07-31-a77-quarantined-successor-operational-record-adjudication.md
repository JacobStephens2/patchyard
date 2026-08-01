# A77 adjudication - quarantined-successor operational record

## Scope and verdict

The build seat adjudicated A78's review of exact operational-record commit
`d56d71e29ccac41fe4ce7e0f0e51a7681b7dcf1b`. A78 returned **PASS with no
finding against the record**. The build seat sustains that verdict.

No record correction, source repair, qualifier retry, worker action, provider
action, or Console action follows this adjudication. Successor `588858421`
remains operationally quarantined.

## A78 access limit - concede

A78 could not independently verify current DigitalOcean state because its
available token returned HTTP 401. That is a real limit on the review's cloud
corroboration, not a contradiction in the reviewed record.

The record distinguishes build-seat readbacks from reviewer verification. Its
post-stop cloud claims remain bound to the contemporaneous build-seat
read-only checks: successor `588858421` was active at private
`10.132.0.15`; the worker firewall was `succeeded` with zero pending changes
and attached only to that successor; and predecessor `588826948` returned HTTP
404. A78 did not independently reproduce those observations and this
adjudication does not relabel them as A78-verified.

## Five requested checks and target address - concede

Source inspection agrees with A78:

1. the wrapper status remains 1 and the sequence remains stopped;
2. the record does not assign a cause to the timeout;
3. the settled-firewall readback is not a passing A101 result;
4. the failed-successor rule quarantines `588858421` independently of the
   absent taint marker; and
5. the negative scope, 13 false qualification flags, and deliberately stale
   requirement-1 fixture are represented accurately.

The attempt log and record also bind A101 to `10.132.0.15`, the same private
address recorded for successor `588858421`. There is no stale-target defect.

## Twice-seen shape and readiness risk - concede

The recurrence is checkable and real. Session 16 observed a new-worker A101
timeout while the firewall attachment was still in `pending_changes`, followed
by a settled firewall and passing direct TCP and management probes. The July 31
replacement also reached A101 immediately after replacement, timed out, and
later showed a settled firewall with zero pending changes.

That history is sufficient to concede a forward-looking readiness risk: the
next source and operational design should explicitly decide how provider
firewall readiness gates the first A101 probe. Repeating the unchanged sequence
would risk consuming a third worker on the same externally observed failure
shape.

## Cause for the July 31 timeout - refute with evidence

A78's stronger sentence that A101 **races firewall attachment propagation** is
not established as the cause of the July 31 timeout.

The two records carry materially different evidence:

- Session 16 sampled the firewall in `pending_changes` at the failure and later
  observed passing probes after it settled.
- The July 31 sequence did not sample firewall state at the failure instant,
  did not retry the failed probe, and observed only a later settled state.

The July 31 evidence is consistent with the Session 16 race, but it is also
consistent with another transient or host/network cause that had cleared by
the readback. A settled after-state alone cannot distinguish them. Experiment
on `588858421` is prohibited by its quarantine, so the cause must remain
unknown rather than be resolved by retry.

This partial refutation does not defeat A78's desired-state recommendation. A
provider-state readiness gate can be justified by the demonstrated recurrence
and the cost of false terminal failure without asserting a causal fact that was
not observed.

## No-qualified-worker state - concede

Factory presently has no qualified worker: predecessor `588826948` is
destroyed and successor `588858421` is quarantined and ineligible. A future
bounded sequence must dispose of `588858421` while provisioning and qualifying
a fresh successor. It may not repair, retry, or reuse the current worker.

## Escalated next decision

The operational record needs no repair. The forward-looking readiness design
and another clean-worker replacement are new work and remain Jacob's decision
under A1. If authorized, they must be recorded as an operational grant under
A115 rather than minted as a new numbered ruling; A119 remains taken.

No readiness implementation, replacement plan, provider request, behavioral
acceptance, requirement-3 work, credential rotation, requirement-1 refresh, or
qualification-flag change is authorized by this adjudication.
