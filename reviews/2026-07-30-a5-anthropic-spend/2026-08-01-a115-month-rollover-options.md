# A115 August rollover options - Anthropic spend enforcement and later proofs

Date: 2026-08-01

Status: options for A78 review and Jacob's ruling; analysis only

Canonical inputs: A113, A115, A117, A118, and A119 in
`docs/decision-log.md`; `docs/anthropic-spend-enforcement.md`;
`docs/anthropic-issuance.md`; the current Anthropic checkers; and the complete
requirement-2 work record in this directory.

## Decision requested

The August rollover correctly stopped the attended requirement-2 procedure.
Jacob must decide both:

1. how a new monthly baseline may become greater than the temporary workspace
   cap without reviving the failed spend ramp; and
2. whether the remaining Anthropic lifecycle work may proceed before
   requirement 2, so shared source changes happen before rather than after the
   expensive live spend proof.

No option in this paper is self-authorizing. This paper makes no provider
request, issues no credential, changes no Console value, mutates no worker,
refreshes no fixture, starts no later requirement, and changes no
qualification flag. All 13 `credential_qualified` values remain false.

## Findings that every option must respect

### The baseline dependency is circular

The current proof needs settled workspace month-to-date spend above $1.00 and
below $50.00. Lowering the workspace cap to $1.00 then puts the cap below
already-settled spend and makes the refusal phase causal without deliberately
ramping spend while the lower cap is active.

July had a usable, if accidental, baseline because the failed eight-request
attempt had already settled at $7.68168. August does not inherit that amount.
The dedicated workspace cannot accumulate genuine ordinary inference spend
because Factory is not qualified to use it, and Factory cannot finish
qualification without accumulated spend. Waiting alone does not break that
circle.

### The idle interval does not reach backward, but a separate prohibition does

The exact idle binding is:

> Keep the dedicated workspace idle except for the three named phase requests
> from the first acceptance until the post-refusal cost snapshot.

Therefore, the exclusivity interval begins at the first named acceptance. It
does not, by its own words, prohibit a request before that acceptance.

That observation does not authorize pre-sequence accumulation. The immediately
preceding rollover stop says:

> Do not create spend to manufacture a baseline, change the $1.00 binding, or
> reuse the failed eight-request ramp.

The convenient reading - that anything before the first acceptance is allowed
- would discard this separate sentence. Pre-sequence accumulation is an option
only if a new ruling explicitly changes the no-manufactured-baseline guard.

### The settlement floors are evidence, not scheduling estimates

The current checker requires at least 10,260 seconds from the first acceptance
to the pre-activation settled-cost snapshot and at least another 10,260 seconds
from the refusal to the post-refusal snapshot. The minimum live sequence is
therefore 20,520 seconds, or 5 hours 42 minutes, plus operator and reporting
delay. These are floors. A Cost Report observation that is still unsettled
must wait longer.

The first floor prevents the positive-control charge from arriving after the
baseline snapshot. The second prevents a late refusal-period charge from being
misreported as zero overshoot. A cheaper-looking option that removes either
floor loses attribution and does not qualify.

### The failed history rules out several apparent shortcuts

These are not options:

- Reuse or shorten the eight-request ramp. Its eight calls were all accepted;
  they contained 1,536,296 uncached input tokens and eight output tokens and
  settled at exactly $7.68168. The result proved spend, not refusal.
- Reclassify the later HTTP 400. Its body did not cross the failed guest
  boundary, the active cap was not temporally bound, and its cost observation
  was short of the observed settlement delay.
- Treat the workspace readback, Cost Report plateau, notification, or local
  counter as provider enforcement. A113 and A115 require provider refusal.
- Treat $6.68168 as denial overshoot. It was pre-existing accepted spend above
  $1.00, not incremental spend between activation and a qualifying refusal.
- Exercise Patchyard's shared $500 organization cap. It is not Factory-scoped and
  would risk unrelated Patchyard work.
- Carry July's $7.68168 into August. The proof and Cost Report observations are
  monthly, and the stop explicitly fires at rollover.

## Question 1 - viable baseline options

Dollar examples below use A119's recorded Opus 5 price of $5 per million input
tokens and $25 per million output tokens. They are planning figures, not
accepted evidence. The live fixture must record actual Usage and Cost Report
figures, and A113 permits no preset ceiling on observed refusal overshoot.

### Option 1 - lower the temporary cap to fit one small named acceptance

**Mechanism.** Replace the fixed $1.00 temporary value with the smallest
strictly positive Console-enforced value `C`, and make the first named request
large enough to have a conservative, source-reviewed uncached cost floor above
`C`. After that one acceptance settles, lower the workspace cap to `C`, make
the byte-identical request once for the refusal, restore $50.00, observe the
second settlement floor, and make the restored acceptance.

A concrete target is `C = $0.01` and a request proven to contain at least 4,000
uncached input tokens. At A119's price, each accepted control costs at least
$0.020 plus at most the one-token output configured by the current transport.
The two planned acceptances therefore cost about $0.04. This target is only
valid if Anthropic both accepts a one-cent workspace limit and treats it as an
enforced limit. A zero value is not an acceptable substitute unless provider
semantics independently prove that zero means a hard pause rather than
"unlimited" or "disabled."

**Elapsed time.** At least 5 hours 42 minutes after the first acceptance, plus
cap readbacks, the calls, and any Cost Report delay beyond the floors.

**Binding changes.** This changes A115's $1.00 value, the rollover stop, and the
current "minimal request" procedure. Source changes would include
`policy/anthropic-wif.json`, the runner, launcher, one-shot transport, evidence
finalizer, checker, tests, and documentation. Because the runner and launcher
change, the current requirement-1 host contract becomes stale and requirement
1 must be refreshed after the complete shared source contract is frozen.

**Evidence preserved and lost.** It preserves the strongest A115 properties:
one request in each phase, the same principal/model/endpoint/body, a cap below
settled spend, the unchanged nonbinding organization cap, immediate restoration,
the exclusive interval, both settlement floors, and separate pre-existing and
incremental figures. It changes comparability to the July $1.00 experiment and
gives up an absolutely minimal request. It does not give up the causal
acceptance-refusal-acceptance proof.

**Failure if the central assumption is wrong.** If Console does not support a
strictly positive sub-dollar limit, treats it as nonbinding, or if the request
cannot be proven to settle above it without relying on output length or cache
behavior, stop before any inference request. Do not retry at successively
larger sizes. That would reconstruct the rejected ramp.

### Option 2 - keep $1.00 and make the first named acceptance cost more than $1

**Mechanism.** Keep the known $1.00 temporary value but replace the minimal
body with one byte-identical three-phase body whose uncached input alone has a
reviewed cost floor above $1.00. The first named acceptance creates the needed
settled baseline inside the existing sequence. There is still exactly one
provider request in each phase and no request is made while searching for a
working size.

At A119's price, 210,000 uncached input tokens would nominally cost at least
$1.05. The two accepted controls would therefore cost about $2.10, plus their
bounded outputs. The historical average was 192,037 input tokens and one
output token per accepted ramp call, or about $0.96021 per call. Reusing one of
those old calls is consequently not enough; the old record is evidence against
that shortcut.

**Elapsed time.** At least 5 hours 42 minutes, plus operator and excess
settlement delay.

**Binding changes.** This changes the minimal-body procedure and the
no-manufactured-baseline stop but preserves A115's $1.00 cap. A narrow design
can change only the one-shot transport, checker constants, tests, and
documentation. Requirement 1 does not include the one-shot transport in its
host digest, so a transport-only implementation does not mechanically stale
the current requirement-1 fixture. Requirement-2 source and its three-file
host digest still change and must return to A78.

**Evidence preserved and lost.** It preserves the $1.00 value, all causal
bracketing, one request per phase, the idle interval, and both settlement
floors. It loses the minimal-request property and deliberately makes each
positive control material spend. It is not the eight-request ramp: its
contract allows one pre-sized request per phase and forbids size discovery by
live retry.

**Failure if the central assumption is wrong.** The option fails if the model
does not accept the pre-sized context, tokenization cannot establish a
conservative input-cost floor before the call, caching can lower billable input
below $1.00, or pricing changes before execution. If the first acceptance
settles at $1.00 or less, stop. A second larger acceptance is not authorized.

### Option 3 - explicitly authorize one separate pre-sequence seed

**Mechanism.** Add one separately named WIF-backed seed action under the
operational $50.00 cap, pre-sized once to settle above $1.00 and below $50.00.
Wait at least 10,260 seconds and until it is settled. Only then begin the
currently reviewed three-phase procedure with its existing minimal body and
its two existing settlement floors.

The idle sentence permits this request in time because it precedes the first
acceptance. The no-manufactured-baseline sentence prohibits it in purpose, so a
new ruling must say exactly that one seed is allowed. It must use the ephemeral
WIF path; no standing key or bare `ANTHROPIC_API_KEY` is acceptable.

Using the Option 2 worked size, planned model spend is about $1.05 for the seed
plus the two minimal accepted controls. Any refusal-period increment remains an
observed amount with no preset ceiling.

**Elapsed time.** At least three settlement floors from seed to completion:
30,780 seconds, or 8 hours 33 minutes, plus operations and reporting delay.

**Binding changes.** This changes the explicit no-manufacture stop and A115's
three-request exclusivity at the procedure level by adding one authorized
request before that interval. A safe implementation needs a distinct runner,
launcher, and transport action with fixed cardinality and evidence lineage,
which stales requirement 1 through the runner/launcher and returns the spend
source to A78.

**Evidence preserved and lost.** It preserves the reviewed minimal body for
all three causal phases and adds, rather than removes, a settlement floor. It
loses the important property that the starting excess was incidental
pre-existing spend. The baseline becomes a qualification artifact.

**Failure if the central assumption is wrong.** If the single seed settles at
$1.00 or less, reaches $50.00, is cached unexpectedly, or cannot be exclusively
attributed, the procedure still cannot start. Retrying or adding seed calls
would be a ramp. This option is dominated by Option 2 in cost and time unless
preserving the current minimal three-phase body is judged more valuable than
the extra call and settlement window.

### Option 4 - obtain a dedicated Factory Anthropic organization

**Mechanism.** Establish a separate billing organization used only by Factory,
with its own enforceable organization hard cap, then rebuild the WIF issuer,
rule, service account, workspace, policy, and fixtures against that scope. This
returns to the clean semantic alternative recorded in the A115 ruling request:
the provider hard cap itself is Factory-only, so testing it cannot interrupt
other Patchyard Anthropic work.

The new ruling must still specify how a zero-spend organization reaches its
first refusal. Viable forms are an enforceable sub-dollar or zero hard cap that
can refuse a bounded first request, or one explicitly authorized initial
acceptance followed by a cap below its settled cost. A new organization does
not magically remove the baseline problem if its minimum cap is still $1.00
and its enforcement still depends on accumulated spend.

**Dollar and elapsed cost.** Repository evidence does not establish that Patchyard
can obtain a second organization, what provider or administrative charge it
would carry, or its provisioning lead time. Those figures are unknown, not
zero. Once the organization and reviewed source exist, retain both 10,260
second settlement floors, so the causal live portion is at least 5 hours 42
minutes. Inference cost depends on the ruled cap mechanism and any measured
overshoot and cannot be bounded in advance under A113.

**Binding changes.** This replaces A115's workspace amendment or materially
amends it, and changes the organization, workspace, service-account, issuer,
and rule identities in policy. All Anthropic live fixtures against the current
organization become inapplicable, including qualified requirement 1. The
administrative and operational surface is also larger.

**Evidence preserved and lost.** This gives the strongest scope isolation: a
provider-native organization cap dedicated to Factory. Retaining the
settlement floors preserves measured overshoot. It gives up continuity with
the already-proven WIF objects and current workspace and must re-prove issuance
and delivery from the beginning.

**Failure if the central assumption is wrong.** If Anthropic does not make a
second organization available, its minimum or enforcement semantics recreate
the same circularity, or migration cannot preserve short-lived WIF, this
option cannot qualify.

### Option 5 - wait for genuine independent August spend

**Mechanism.** Make no qualification spend. Start the existing procedure only
after unrelated, independently authorized use of this exact workspace has
settled and the observed August amount is greater than $1.00 and less than
$50.00.

**Dollar and elapsed cost.** Qualification-created spend is $0. Calendar wait
is indeterminate, followed by the existing minimum 5 hours 42 minutes.

**Date it becomes viable.** Under current authorization there is no calendar
date on which passage of time makes this option viable. It becomes viable at
the actual August settlement timestamp `T` of more than $1.00 of genuine
independent workspace use. No such use is currently authorized, which is the
circularity rather than a scheduling gap. September 1 is not a solution; the
monthly amount resets and the same condition recurs.

For August 2026, the first acceptance would have to occur strictly before
`2026-08-31T18:18:00Z` even under the impossible assumption that both floors
finish at their exact minimum and every cap observation and request takes zero
time. A real operational cutoff must be hours earlier. If no qualifying
independent spend has settled by that cutoff, waiting cannot produce an August
attempt.

**Binding changes and evidence effect.** No binding changes. Every current
evidence property, including the $1.00 value, minimal body, idle interval, and
both settlement floors, is preserved.

**Failure if the central assumption is wrong.** If independent spend never
arrives, arrives too late, reaches $50.00, cannot be attributed to the exact
workspace, or is itself Factory qualification activity under another name,
the option never becomes viable.

### Option 6 - close Anthropic requirement 2 and rule a different first pair

**Mechanism.** Record Anthropic requirement 2 as unsatisfied under the
available provider control and replace A113's first-pair selection with another
two-family pair, most plausibly OpenAI plus xAI. This is the strategic exit
already preserved by the A115 ruling request, not an interpretation of the
failed Anthropic evidence as success.

**Dollar and elapsed cost.** Anthropic baseline spend is $0. The new providers'
administrative, source-review, live-proof, and spend-test costs are not
established in this repository and cannot honestly be assigned a dollar or
calendar figure. xAI would still need A113's dedicated team, low postpaid
limit, and verified zero prepaid balance.

**Binding changes.** This changes A113's first-pair ruling, closes A115 without
a qualifying result, and requires new provider-specific implementation and
review authorization.

**Evidence preserved and lost.** All Anthropic failure history and its
qualified issuance/delivery proof remain honest records, but Anthropic does
not become an eligible Factory provider. The provider-side spend property is
not weakened; it must be proved by the replacement pair.

**Failure if the central assumption is wrong.** If either replacement provider
lacks the ruled issuance, revocation, crash, or spend surface in Patchyard's actual
account, the first-pair blockage moves rather than resolves.

## Question 1 recommendation

Recommend Option 1 as the default, conditional on a source-independent finding
that Anthropic exposes a strictly positive sub-dollar limit with hard-pause
semantics. It makes the first required positive control create its own
baseline, keeps the two settlement floors and the causal three-phase proof,
costs about four cents of planned accepted inference at the worked one-cent
target, and does not add a fourth provider request. It changes more shared
source than Option 2, but that cost can be absorbed once if the remaining
lifecycle source is consolidated before any fixture is refreshed.

If the smallest enforceable value is $1.00, recommend Option 2 as the fallback.
Its planned accepted spend is about $2.10, but it keeps the known cap value and
can avoid staling requirement 1 if the source change remains transport-only.
Option 3 should not be selected merely because the idle sentence permits its
timing; it is slower, adds a call, and explicitly converts baseline manufacture
into policy. Option 4 is the strongest semantic fallback if a second
organization is actually available. Option 5 is not a plan without a named
independent workload and settlement date. Option 6 remains the exit if
Anthropic cannot expose a testable Factory-scoped control.

## Question 2 - can the remaining proofs proceed first?

### The current stop is operative but not recorded as a permanent dependency

The end of `docs/anthropic-spend-enforcement.md` says:

> Requirement 2 remains unqualified until the completed A115 result lands.
> Behavioral acceptance remains paused, all 13 `credential_qualified` flags
> stay false, and requirement 3 must not begin.

That is a current stop and this paper does not cross it. The canonical A115
ruling uses narrower authorization language:

> No requirement 3 work, behavioral acceptance case, current-worker reuse, or
> qualification-flag change is authorized by this ruling.

A117 and A118 similarly say that their bounded source grants do not authorize
requirement 3. The decision log contains no separate ruling that requirement 3
is semantically or permanently dependent on requirement 2. The checkable
record therefore supports this conclusion: later work is currently forbidden,
but the prohibition is a scope guard on the A115/A117/A118 work authorization,
not a proved permanent ordering rule. A new Jacob ruling is required before
source work or live execution begins, and it may authorize a different order
without weakening any qualification property.

### The host-contract counterargument is materially right but needs one
correction

The current checkers do not give every Anthropic proof the same three-file
host digest:

| Binding | Exact current source | Consequence of a change |
| --- | --- | --- |
| Requirement 1 host contract | issuance runner + Firecracker launcher | Either change makes the qualified `eef6e16e...d52977` fixture stale. |
| Requirement 2 host contract | issuance runner + Firecracker launcher + one-shot transport | Any of the three changes invalidates a future requirement-2 fixture and requires new A78 source review now. The current three-file digest is `002aaa2d11265cbf1b47e3f953ecef8bb824495bd911782e922e49120221e6a0`. |
| Both requirements' image binding | complete `worker/image/` recipe, including the guest runner | A guest-image change stales the live fixture even when the host digest is unchanged. |

This distinction does not defeat the sequencing concern. On 2026-08-01,
requirement 1 had to be rerun because its recorded `bd360182...d8e2f` host
contract preceded the changed shared runner/launcher contract
`eef6e16e...d52977`. The refreshed run was
`anthropic-i1-20260801-c4402b94a1`, used `GET /v1/models?limit=1`, and generated
no inference tokens. Its issuance time was 14:48:05Z and the fixture commit was
14:54:45Z, a 6 minute 40 second live-to-commit interval when installed source
was already exact. That is the lower-bound shape of a refresh, not the full
cost of design, A78 review, deploy, converge, and qualification.

### Minimum credible source impact of each remaining proof

| Remaining proof | Current gap | Minimum credible impact on bound source |
| --- | --- | --- |
| Expiry denial | The runner always mints a 300-second bearer, and the guest makes its positive Models call immediately and deletes the token. There is no post-expiry use path. | A new root-only lifecycle harness can perform a positive Models call, wait through the recorded expiry, retry the same bearer for provider denial, and purge it without changing the runner, launcher, transport, or guest. If the existing runner is extended instead, requirement 1 immediately becomes stale. The sidecar design still needs A78 to prove equivalent credential containment. |
| Federation-rule revocation and signing-key rotation | `tools/anthropic-wif-admin.py` only plans/creates/validates and deliberately rejects JWKS drift. It cannot disable/restore a rule or update an issuer. | This can be a separate fail-closed administrative tool and evidence checker, with no inherent runner, launcher, transport, or guest change. The runbook also requires a replacement-key positive exchange and Models call plus denial for the retired key, so policy and admin source will change even if the live host digest does not. |
| Crash cleanup before and after credential-drive unmount | The guest unmounts at `worker/image/patchyard-guest-run` lines 219-235 but exposes no reviewed synchronization boundary. The production launcher has cleanup and residue checks, but no provider-specific two-boundary crash action. | A deterministic proof needs at least guest-image boundary signaling and a reviewed external kill/cleanup harness; a safer integrated design is likely also to change the launcher and runner. The one-shot spend transport is not needed if the zero-token Models endpoint is used. Any guest change stales both live image bindings; a launcher/runner change also stales requirement 1's host digest. |

Expiry and federation-rule revocation therefore do not inherently require a
change to the shared three-file spend contract. Crash cleanup does require at
least a guest-image change unless A78 accepts an external mechanism that can
prove both unmount boundaries without guest instrumentation. Current source
has no such mechanism, so assuming one would be another convenient reading
rather than evidence.

### Rework under the two possible orders

If requirement 2 runs first and later crash work changes the guest, launcher,
or runner, both the requirement-1 and requirement-2 live fixtures become stale.
The repeat cost is:

- another requirement-1 live refresh - zero inference-token cost and an
  observed 6 minute 40 second live-to-commit interval in the already-deployed
  August case, plus deploy, qualification, gates, and review; and
- another complete requirement-2 live proof - whatever baseline mechanism
  Jacob rules, three provider requests, and at least 5 hours 42 minutes of
  settlement floors. A month rollover can make that repeat impossible again.

If source-only work for the remaining proofs runs first, the build can absorb
the chosen requirement-2 baseline change, expiry/revocation tooling, and crash
instrumentation into one reviewed contract. Requirement 1 then refreshes once,
and requirements 2 and 3+ can bind the same frozen source. Current requirement
2 has no successful live fixture to invalidate, so this is the only point in
the sequence where shared-source consolidation is cheap.

### Question 2 recommendation

Authorize requirements 3+ to proceed during the blocked window, but in this
order and under explicit negative scope:

1. select the requirement-2 baseline option first;
2. implement and A78-review all source for that option plus expiry denial,
   federation-rule revocation/restore and signing-key rotation, and both crash
   boundaries;
3. freeze the runner, launcher, one-shot transport, and complete guest image;
4. deploy and qualify that exact source, then refresh requirement 1 once;
5. run the zero-inference-token expiry, revocation, and crash live proofs under
   their own reviewed procedures while requirement 2 is waiting on its ruled
   baseline; and
6. run requirement 2 only after the frozen contract and its viable monthly
   window are both established.

The intended later proofs need not create inference spend: expiry, key
rotation, and revocation can use the zero-token Models endpoint, and crash
cleanup can exercise the same credential delivery with a zero-token provider
control. They still carry operational risk. Rule disable/restore and issuer
update are provider mutations, and a failed crash cleanup can taint a worker
and require reviewed replacement. Those actions need separate source review,
attended procedures, stop conditions, and authorization. They must not be
repurposed as hidden baseline generation.

## Proposed ruling shape

Jacob can rule the two questions independently, but the lowest-rework result is
a combined ruling that:

- selects one Question 1 option and names its exact request budget, temporary
  cap, live-attempt budget, settlement floors, and stop conditions;
- authorizes source-only requirements 3+ work before requirement 2, followed
  by separately reviewed live procedures on one frozen contract;
- requires renewed A78 review of every changed requirement-2 binding;
- requires exactly one requirement-1 refresh after all runner, launcher, and
  guest-image changes are complete;
- preserves A9 stop-and-escalate behavior, credential-free fixtures, no bare or
  long-lived Anthropic key, the unchanged $500 shared organization cap, and all
  13 false qualification flags until every required live fixture passes; and
- states that no R3 proof, reviewer invocation, or other activity may be used
  to manufacture the requirement-2 baseline unless that spend mechanism is
  the option expressly selected.

Until that ruling lands, the rollover stop remains in force and none of these
actions is authorized.
