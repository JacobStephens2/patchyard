# A113 clause 2 amendment ruling request - Anthropic workspace spend enforcement

Date: 2026-07-30

Status: option 1 accepted by Jacob as A115 on 2026-07-30

Canonical ruling: `docs/decision-log.md`, A115

Related implementation: PR #78, `a5-anthropic-spend-enforcement`

## Accepted decision

**Disposition:** Jacob accepted the requested Anthropic causal-proof amendment
and its separate one-time reauthorization as A115. The text below is the full
proposal A115 resolved; the decision log is the canonical operative ruling.

Amend A113 clause 2 for Anthropic so a controlled
acceptance-refusal-acceptance sequence can prove that Anthropic enforces the
dedicated Factory workspace limit even when the refusal does not explicitly
name that limit. Preserve the provider-refusal requirement, the dedicated
Factory billing scope, the unchanged and nonbinding organization limit, exact
observed figures, and restoration of the reviewed operational cap.

The amendment must also distinguish spend already above a newly lowered cap
from spend incurred while enforcement catches up. The former is
`preexisting_excess_at_activation`; only the latter is enforcement overshoot.
The July 29 total was $6.68168 above the displayed $1.00 value, but a future
cap-toggle test must remeasure its own settled baseline rather than copy that
figure. The July 29 amount is not retroactively an A113 overshoot measured at
denial.

A separate operative clause must authorize a new implementation and live
attempt because PR #78 consumed A9's single repair loop. Without that clause,
amending the evidence semantics alone does not authorize another source repair,
provider request, taint-marker removal, or worker replacement.

## Why A113 cannot be satisfied from the current evidence

A113 clause 2 currently requires a provider hard cap scoped to a dedicated
Factory project or workspace, provider refusal, and a measured observed
overshoot with no preset ceiling. The clause permits delayed enforcement but
does not permit a console setting, alert, local counter, or billing report to
substitute for provider refusal.

The Anthropic evidence establishes these facts:

- Patchyard has a dedicated `Patchyard Factory` workspace,
  `wrkspc_000000000000000000000000`.
- Anthropic Console accepted and displayed a workspace limit below Patchyard's
  unchanged $500.00 organization limit.
- The initial fixture's eight requests all returned HTTP 200 and later settled
  at exactly $7.68168. That is $6.68168 above the displayed $1.00 workspace
  value, but the provider did not refuse those requests.
- The repaired fixture made one tiny request and received HTTP 400, but its raw
  response did not cross the failed guest boundary. The response therefore
  cannot be attributed to workspace spend enforcement.
- The reported `$7.68 of $1.00` and `$7.68 of $50.00` observation times precede
  the worker's journaled repaired-run interval. They cannot establish which
  workspace limit was active during the HTTP 400.
- Cost Report remained $7.68168 through a read-only observation 42 minutes
  after the repaired request. The initial cost took about 2 hours 51 minutes to
  appear, so that observation does not prove $0 incremental repair spend.
- Console behavior proves that a lower workspace value can be saved and read
  back. It does not, without a provider refusal attributable to that value,
  prove that the workspace limit independently binds server-side.

Requirement 2 therefore remains unqualified. All 13
`credential_qualified` flags remain false, behavioral acceptance remains
paused, and the current worker remains quarantined by `BOUNDARY_TAINTED`.

## Proposed ruling text

> **A113 clause 2 is amended for Anthropic's delayed workspace-pause
> control:** a value accepted and displayed by Anthropic Console does not by
> itself establish a Factory-scoped provider hard cap. Anthropic workspace
> enforcement may instead be proved by a controlled
> acceptance-refusal-acceptance sequence in the dedicated Factory workspace.
> Using the same Factory service-account principal, model, endpoint, and
> byte-identical valid request body, the fixture must record provider acceptance
> under the reviewed operational workspace limit, provider refusal after only
> that workspace limit is lowered below already-settled workspace spend, and
> provider acceptance after the reviewed operational limit is restored. Patchyard's
> organization limit remains unchanged, organization aggregate spend remains
> demonstrably far below it, and no other workspace is modified.
>
> The refusal response crosses the evidence boundary in credential-free form,
> including HTTP status, provider request ID, response type, and sanitized error
> shape. The refusal need not name the workspace limit when successful WIF
> exchanges, the bracketing successful requests, response status and shape, and
> the recorded cap-state change together exclude credential, request-validity,
> model-availability, rate-limit, and organization-limit causes. A generic
> status without the bracketing positive controls does not qualify.
>
> The fixture records independently timestamped workspace and organization
> readbacks, the settled workspace spend immediately before cap activation,
> the spend reported after the provider's observed settlement window, the
> provider responses for all three phases, and restoration of the reviewed
> operational limit. When settled spend already exceeds the temporary cap at
> activation, the fixture records
> `preexisting_excess_at_activation_usd = settled_spend_before_activation_usd - temporary_cap_usd`
> separately from
> `incremental_spend_before_refusal_usd`. Only the second figure is enforcement
> overshoot. Neither figure has a preset acceptance ceiling; both are observed
> results.
>
> A Console readback, `notify_and_pause` client text, notification, local spend
> counter, Cost Report plateau, or Patchyard organization hard cap alone does not
> satisfy this clause. This Anthropic amendment does not change A113 clause 2
> for OpenAI or A113 clause 3 for xAI.

## One-time reauthorization text

The evidence amendment and the new repair budget should be ruled together but
remain separate clauses:

> **One-time Anthropic requirement 2 reauthorization:** the July 29-30 attempts
> remain terminal failure evidence and do not qualify requirement 2. After the
> conceded A78 source and evidence defects are repaired and a clean-worker
> replacement is separately reviewed, one new implementation and qualification
> attempt plus one A9 repair loop are authorized under the amended contract.
> Historical failure records remain committed. A successor result identifies
> this ruling as its authorization and may coexist with those records only
> after the checker and schema are reviewed to express that lineage. No
> qualification flag changes unless the complete amended fixture passes
> adversarial review.

This authorization is intentionally narrow. It does not authorize requirement
3, a behavioral acceptance case, an organization-limit change, deletion of
failure history, clearing the current worker's marker, or reuse of the current
worker.

## Required controlled sequence

The live proof should use three bounded phases. The successful phases use the
smallest valid request and are the only expected new spend.

1. **Operational-limit acceptance.** Read back the Patchyard Factory workspace at
   $50.00 and the Patchyard organization at $500.00. Record the control-plane UTC
   observation without human timezone conversion. Mint a fresh run-bounded WIF
   bearer and make the deterministic minimal request. Require HTTP 200 and
   record its credential-free request and usage evidence. Wait until Cost
   Report includes this request and record the settled workspace total.
2. **Temporary-limit refusal.** Lower only the Patchyard Factory workspace cap to
   $1.00, read it back with an independently captured UTC time, and leave the
   organization limit unchanged. Mint a fresh bearer for the same service
   account and repeat the byte-identical request once. Require a provider
   refusal and export its sanitized response before the guest result boundary
   closes. Restore $50.00 immediately after the request, regardless of result.
   Wait at least the previously observed settlement window before fixing the
   incremental-spend figure.
3. **Restored-limit acceptance.** Read back $50.00 and the unchanged $500.00
   organization limit. With another fresh run-bounded bearer for the same
   service account, repeat the byte-identical request. Require HTTP 200. This
   final positive control makes the workspace cap state the only intended
   difference between acceptance and refusal.

Every phase binds the same request SHA-256, model, endpoint, workspace, service
account, and source digests. Each WIF bearer remains per-run and is never
recorded. Cap changes and positive-control runs occur only in the dedicated
Factory workspace. No action changes Patchyard's organization limit or another
workspace.

## Evidence fields added by the amendment

The successor fixture should record at least:

| Field | Purpose |
| --- | --- |
| `authorization_ruling` | Distinguishes the reviewed successor from an unauthorized retry after the A9 stop record. |
| `workspace_id`, `service_account_id`, `organization_id` | Binds every phase to the dedicated Factory scope and explicit Patchyard organization. |
| `request_sha256`, `model`, `endpoint` | Proves the three provider calls exercised the same request contract. |
| `operational_acceptance` | Timestamp, $50.00 readback, HTTP status, provider request ID, sanitized response type, and usage. |
| `temporary_refusal` | Timestamp, $1.00 readback, HTTP status, provider request ID, sanitized error shape, and server Date. |
| `restored_acceptance` | Timestamp, restored $50.00 readback, HTTP status, provider request ID, sanitized response type, and usage. |
| `organization_limit_observations` | Proves $500.00 remained unchanged and nonbinding through all phases while allowing the two tiny controls to appear in aggregate spend. |
| `settled_spend_before_activation_usd` | Freezes the workspace total before the temporary cap becomes active. |
| `preexisting_excess_at_activation_usd` | Records spend already above the lowered cap without mislabeling it enforcement overshoot. |
| `incremental_spend_before_refusal_usd` | Records the actual additional spend, if any, between cap activation and provider refusal. |
| `settlement_window_seconds` | Shows that the final cost observation waited at least as long as the previously observed reporting delay. |
| `restoration` | Proves the reviewed $50.00 operational cap was restored even if a provider or fixture step failed. |
| `containment` | Records honest teardown state and clean-worker disposition under A114. |

The sanitized refusal shape must be diagnosable but forward-compatible. It
should require the provider fields used for attribution while allowing
compatible additional fields. A rejected response exports a credential-free
shape descriptor so an unrelated HTTP 400 and a provider-contract extension do
not collapse into the same status.

## Preconditions before another provider request

The amendment does not waive the conceded A78 findings. Before another live
request, review must verify these repairs:

- Record the initial worker taint and approved replacement history rather than
  freezing a failure schema that cannot express it.
- Capture cap observations with independently bound UTC times and reject
  impossible ordering instead of preserving it as usable evidence.
- Remove the unsettled `$0` repair-cost claim and keep pre-existing excess
  separate from enforcement overshoot.
- Replace exact error-key equality with required-key containment, preserve
  type, message, and request-ID checks, and test a compatible extra-field case.
- Set a distinct post-denial failure state immediately after accepting the
  provider envelope.
- Delete the guest bearer before publishing any result, including every
  failure path.
- Describe workspace binding as the result of the controlled live proof, not
  as an inference from Console client behavior.
- Bind the one-request contract against retry options and loop forms directly,
  not only through an incidental image-recipe digest.
- Bind A114 exit-status calculation after all residue and teardown failures,
  and make output purge, ownership, mode, terminal-write, and unlock failures
  contribute to the aggregate nonzero outcome.
- Replace the quarantined worker only through a separately reviewed plan. Do
  not clear `BOUNDARY_TAINTED` or copy state from the current worker.

## What the amendment changes

The amendment changes one semantic point: Anthropic can establish independent
workspace enforcement by a controlled provider-response differential rather
than by an error message that explicitly says "workspace spend limit."

It also changes how the first Anthropic observed baseline is represented when
the workspace already carries settled spend. The fixture records both the
pre-existing amount above the newly lowered cap and any additional spend after
activation. It does not call the full difference delayed-enforcement overshoot.

Everything else remains:

- the provider must refuse;
- the Factory workspace must be the enforcing scope;
- Patchyard's shared organization cap cannot be the cause of refusal;
- observed amounts have no preset qualification ceiling;
- the reviewed $50.00 workspace cap must be restored;
- credentials never enter evidence or durable Factory state;
- all six provider requirements must land before Anthropic's
  `credential_qualified` flag changes;
- behavioral acceptance remains paused.

## Alternatives and dispositions

### Keep A113 unchanged and create a dedicated Anthropic organization

This is the cleanest semantic alternative. A separate Factory organization
with its own organization hard cap would satisfy the existing scope requirement
without treating a workspace pause control as a hard ceiling. It adds a new
billing organization, administration surface, and operational relationship.
Its availability to Patchyard is not established.

### Treat the $500.00 Patchyard organization cap as Anthropic requirement 2

Reject. That cap protects and can interrupt every Patchyard Anthropic workspace. It
is not scoped to the Factory principal and cannot be tested without risking
other Patchyard usage.

### Accept the workspace readback and Cost Report without another refusal

Reject. The readback proves configuration, and Cost Report proves billing.
Neither proves provider enforcement. This would remove the central property
A113 clause 2 requires.

### Count the July 30 HTTP 400 retroactively

Reject. The error body did not cross the failed guest boundary, the cap in
force at the request is unproved, and the incremental cost is unsettled. No
ruling should convert missing evidence into qualification.

### Call $6.68168 the measured denial overshoot

Reject. The amount is exact settled initial spend above the displayed $1.00
value. The initial calls were accepted, and the later refusal is unattributed.
It is not spend accumulated between cap activation and a qualifying denial.

## Effect on PR #78

PR #78 remains an implementation and escalation artifact, not a qualified
requirement 2 result. It should not be merged as though Anthropic passed spend
enforcement. If the amendment is refused, close the Anthropic requirement 2
path as unsatisfied unless a dedicated Factory organization becomes available.

If the amendment is accepted, its successor work starts from a new branch and
new reviewed worker. It retains PR #78's failure records, repairs every conceded
source defect before a provider call, adds explicit ruling lineage to the
checker and evidence schema, runs the controlled sequence once, receives A78
review, and stops again under A9 if the amended proof does not qualify.

## Decision options presented

Jacob was presented with three outcomes:

1. **Accept the proposed Anthropic causal-proof amendment and one-time
   reauthorization.** This preserves provider refusal and Factory scope while
   allowing a generic but controlled provider response to qualify.
2. **Keep A113 unchanged and require a dedicated Factory Anthropic
   organization.** No further workspace-cap attempt is authorized unless that
   organization exists with its own hard cap.
3. **Close Anthropic requirement 2 as unsatisfied.** Anthropic cannot become
   credential-qualified under the present provider capability; the A-5 first
   pair requires a separate ruling.

No option treats the existing July 29-30 record as a qualification, changes a
provider flag, starts requirement 3, or resumes behavioral acceptance.

## A115 disposition

Jacob accepted option 1 on 2026-07-30. A115 amends A113 clause 2 for Anthropic
and grants the proposed one-time requirement-2 reauthorization. The July 29-30
attempts remain unqualified historical failures. Before another provider
request, successor work must repair every conceded A78 defect and receive
separate review of a clean-worker replacement. The current worker remains
quarantined and cannot be reused.

Acceptance of the ruling does not itself perform those repairs, replace a
worker, make a provider request, start requirement 3, change a qualification
flag, or resume behavioral acceptance.
