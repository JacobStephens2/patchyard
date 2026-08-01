# A115 August rollover options - summary

Date: 2026-08-01

Status: awaiting A78 review and Jacob's ruling in
[PR #82](https://github.com/JacobStephens2/patchyard/pull/82)

Full analysis:
[`2026-08-01-a115-month-rollover-options.md`](2026-08-01-a115-month-rollover-options.md)

## Result

The August requirement-2 procedure cannot run under A115 as written. Its
baseline dependency is circular: the dedicated workspace needs more than
$1.00 of settled month-to-date spend to qualify, but Factory is not qualified
to create ordinary spend in that workspace.

The idle-workspace interval begins at the first named acceptance, so it does
not reach backward to earlier activity. That does not authorize a seed
request. The separate rollover stop explicitly forbids creating spend to
manufacture a baseline. Any seed or changed cap therefore needs a new ruling.

## Recommended baseline path

Use a conditional two-step decision:

1. Default to a strictly positive sub-dollar temporary cap if Anthropic's
   actual control supports one with hard-pause semantics. At a worked $0.01
   cap, one request with a reviewed floor of at least 4,000 uncached input
   tokens would cost about $0.02 per accepted control, or about $0.04 for both
   positive controls.
2. If $1.00 is the smallest enforceable value, keep it and use one pre-sized
   first acceptance with an uncached input-cost floor above $1.00. A worked
   210,000-token request costs about $1.05 per acceptance, or about $2.10 for
   both positive controls.

Neither path permits live size discovery or retry. If its single first
acceptance does not establish the ruled baseline, stop rather than recreating
the failed eight-request ramp.

Both paths retain the two 10,260-second settlement floors. The live sequence
therefore takes at least 20,520 seconds, or 5 hours 42 minutes, plus operator
and reporting delay. Any refusal-period spend remains an observed amount with
no preset ceiling.

## Other baseline options

- One separate pre-sequence seed is possible only under a new explicit ruling.
  It adds a fourth request and a third settlement floor, raising minimum
  elapsed time to 8 hours 33 minutes.
- A dedicated Factory Anthropic organization is the strongest scope-isolation
  alternative, but its availability, price, and cap semantics are unproved.
  It does not solve a zero baseline unless its hard-cap behavior differs.
- Waiting costs $0 but has no viable date under current authorization. It
  becomes viable only when independent authorized August use has actually
  settled above $1.00 and below $50.00. The theoretical latest first
  acceptance is strictly before `2026-08-31T18:18:00Z`; September resets the
  same circularity.
- Closing Anthropic requirement 2 and ruling a different first provider pair
  preserves the evidence standard but restarts provider qualification work.

## Requirements 3+ sequencing

The current `requirement 3 must not begin` direction remains operative. The
decision log records it as a limit of the A115, A117, and A118 authorizations,
not as a permanent semantic dependency. Jacob can change the order through a
new ruling.

Requirement 1 binds the issuance runner and Firecracker launcher. Requirement
2 binds those two files plus the one-shot transport. Both also bind the full
guest image recipe. Consequently:

- a transport-only spend redesign does not mechanically stale requirement 1;
- a runner, launcher, or guest-image change does stale requirement 1; and
- crash cleanup needs at least a guest-image boundary change under the current
  source, so doing it after requirement 2 would also stale that expensive live
  proof.

The lowest-rework order is to choose the baseline option, implement and
A78-review all shared requirement-2 and requirements-3+ source, freeze the
runner, launcher, transport, and guest image, refresh requirement 1 once, then
run the remaining live proofs against that frozen contract. Expiry, revocation,
and crash controls can use the zero-inference-token Models endpoint and must
not be repurposed as hidden baseline generation.

## Decision needed

Jacob must rule:

1. which requirement-2 baseline mechanism is authorized; and
2. whether requirements 3+ may proceed first on one frozen source contract.

Until that ruling lands, no provider request, credential issuance, Console
change, worker mutation, fixture refresh, requirement-3 execution, behavioral
acceptance, or qualification-flag change is authorized. All 13
`credential_qualified` values remain false.
