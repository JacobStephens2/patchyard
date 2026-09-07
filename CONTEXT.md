# Patchyard Factory

The factory ships software through model-driven pipelines governed by a
human-adjudicated decision log. This glossary fixes terms that have been
resolved; vocabulary still under discussion is deliberately absent.

## Credential qualification

**Requirement**:
One of the six credential-lifecycle properties a provider must demonstrate.
_Avoid_: fixture, test, check, criterion

**Proven**:
The state of a requirement whose result has been committed and accepted.
_Avoid_: qualified, passed, satisfied, met

**Qualified**:
The state of a provider all six of whose requirements are proven.
_Avoid_: proven, verified, approved, certified

**Result**:
The committed file recording one attended run of one requirement.
_Avoid_: fixture, artifact, record, evidence used as a countable noun

**Evidence**:
What a result contains, taken together and never counted.
_Avoid_: naming a file or a quantity

**Receipt**:
A provider-issued record of one interaction with that provider.
_Avoid_: attestation, observation, log entry

**Attestation**:
An operator-recorded observation of a control-plane change for which no receipt
can be obtained. An Attestation is a human-observed fact.
_Avoid_: receipt, witness, sign-off, manual record

**human_authorization**:
A named accountable human's permission for one exact attended run. It is not an
Attestation. It may name a route authorization as its source.
_Avoid_: attestation, approval, sign-off, route authorization

**route authorization**:
A named human's standing permission for model action and decision on the
remaining tickets of one named map, until that map's destination. It is not an
Attestation and is not human_authorization.
_Avoid_: attestation, human_authorization, standing exception used generically

**model_actions**:
The console Saves a named model performed during a model-operated qualification
run.
_Avoid_: attestation, actor log, mutation record

**model_console_observations**:
The live console readings a named model made during a model-operated
qualification run.
_Avoid_: attestation, operator reading, witness

**Control-plane mutation**:
A change to provider-side configuration governing credential trust or spend.
_Avoid_: config change, admin action, setting

**Subject-expression revocation**:
Revoking a federation subject mapping by a console Edit of its claim assertion
to a run-scoped sentinel value; restoration is editing the original expression
back. The mapping stays present and enabled throughout.
_Avoid_: disable, remove, rule deletion, mapping edit used generically

**Issued claim**:
A field the issuance JWT carries. Distinct from a mapping condition.
_Avoid_: mapping condition, assertion claim, live claim, console row

**Mapping condition**:
A Key/Value row on a provider subject mapping. Distinct from an issued claim.
_Avoid_: issued claim, rule.claims, CEL string

**Baseline control**:
A positive control made before a control-plane mutation, which shows that the
path worked before the change.
_Avoid_: pre-mutation positive, prior check, warm-up

**Bracketing control**:
A positive control paired with a denial, which shows that the mutation caused
the denial.
_Avoid_: post-mutation positive, confirmation, sanity check

**Provenance mark**:
A machine-readable statement that a result or an attestation does not rest on a
provider receipt.
_Avoid_: marker, flag, tag, annotation

**Qualified image inventory**:
The worker image files, by name and digest, that a result's evidence ran under.
_Avoid_: recipe digest, image hash, manifest, snapshot

**Descriptor / assembler**:
A descriptor is an inventory file that describes what the guest contains, and is
bound by its digest; the assembler is the program that builds the guest, and is
bound by its effects. Residency is not the test - `pins.env` and the
`*-packages.txt` files are host-side descriptors.
_Avoid_: host file, build script, guest file

**Identity liveness**:
The mapped principal still resolves in the provider's per-project
service-account listing. Not implied by a successful token exchange, and not
established by any console or organization-level view.
_Avoid_: valid, active, working, authenticated

**Signing identity**:
The key pair one provider's issuer trusts to sign assertions, together with the
control-plane path holding its private half. One per provider - two providers on
one signing identity means a rotation for either silently unqualifies the other.
_Avoid_: signing key, key file, kid, credential

**Operator admin profile**:
The named `ant` user_oauth profile (`patchyard-admin`) that holds the
`org:admin` refresh token used to call Anthropic's Admin API. Distinct from an
Admin API key, which federation endpoints reject, and from a federated
`org:admin` token, which depends on the federation this profile exists to
diagnose.
_Avoid_: admin API key, OAuth token used unqualified, ant login

**Steady-state kid authority**:
The per-provider signing-identity registry: the one place that records which kid
a provider's issuer trusts outside a lifecycle run. Minting asserts against it;
a frozen policy's recorded kid is historical, not authoritative.
_Avoid_: policy kid, live kid, current key

**Transitional kid**:
The kid a lifecycle collector mints with mid-run, before the registry catches up
by PR. The collector owns this truth for the instrument it invokes; the registry
is never mutated out-of-band to match it.
_Avoid_: temporary key, override, patch

**Fixture**:
A committed input to a test or a checker, never a record of a live run.
_Avoid_: naming a result, a requirement, or a proof

## Cost accounting

**Rate**:
The dated provider-published unit price for one model and token category,
recorded in `policy/model-rates.json`. A rate may carry context tiers and a
published validity boundary. It is reporting policy, never a spending limit.
_Avoid_: cost, budget, cap

**Cost**:
The supervisor-derived price of one invocation's normalized token usage,
rounded to the nearest micro-USD after all categories are summed. It feeds
telemetry and the per-model rollup; it grants no authority to spend.
_Avoid_: rate, spend cap, provider bill

**Spend cap**:
The provider-enforced ceiling attached to a minted bearer. It is the money
safety control and remains distinct from the supervisor's reporting arithmetic.
_Avoid_: rate table, reported cost, daily run cap

## Adversarial review

**Finding**:
One falsifiable defect claim a reviewer makes against a change, carrying its own
evidence and a severity. It is a claim to be checked, never a statement to be
trusted.
_Avoid_: comment, issue, objection, review note

**Severity**:
How much a Finding is worth: blocking, major, or minor. Only a blocking Finding
can end a run; a severity that costs the run nothing is the reviewer's own
statement that the change may proceed.
_Avoid_: priority, weight, level

**Disposition**:
The author's one permitted move on one Finding - concede, refute, or escalate.
Every Finding gets exactly one.
_Avoid_: response, reply, verdict, resolution

**Concession**:
The Disposition in which the author admits a Finding. On a blocking Finding it
is an admitted defect and obliges a repair, never a note that the run carries
forward unchanged.
_Avoid_: agreement, acceptance, acknowledgement

**Dispute**:
The record raised when the author refutes or escalates a Finding, pairing that
Finding with its Disposition. It is the arbiter's whole subject.
_Avoid_: disagreement, conflict, escalation, contested finding

**Arbitration**:
A third-family seat's decision on one Dispute, made from its own projection of
the reviewed SHA. It decides the disputed Finding only, never the change.
_Avoid_: adjudication, appeal, tie-break, third opinion

**Experiment**:
A bounded execution whose observed result settles a claim. Reading repository
bytes is not an Experiment - it is reading the evidence, and a claim decidable
that way is decidable by a seat that was given the bytes.
_Avoid_: check, test, verification, investigation, looking at the code

**Evidence gap**:
A reviewer's report that it was not shown what a claim needs - a windowed range,
an omitted body, an absent call site. It is a request for evidence, not a
Finding, and nothing about the change follows from one.
_Avoid_: finding, blocker, unverifiable claim, missing evidence used loosely
