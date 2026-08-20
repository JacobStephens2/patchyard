# OpenAI workload identity: provider descriptor and first exchange

## Status and provenance

An attended operator reported the following OpenAI state on 2026-08-06. This
build seat did not create, query, or mutate it. The service account row is the
exception: the 2026-08-06 account was destroyed by the provider-side deletion
cascade A140 records, and the row now names its 2026-08-12 recreation, which an
attended operator verified at the console on 2026-08-12 (zero API keys, the
unchanged provider's sole mapping pointing at it):

| Object | Identifier | Name |
| :-- | :-- | :-- |
| Organization | `org-000000000000000000000000` | Example Company |
| Project | `proj_4zpZhhPPNYCvPRE5vGuRBALH` | `patchyard` |
| Service account | see the identity registry below | `patchyard-worker` |
| Workload identity provider | `idp_DlzD7RlQXgXxd1VSG2V93eEU` | `patchyard` |

**A150: the service-account id lives in `policy/openai-identity-history.json`,
not here and not in `policy/openai-wif.json`.** The 2026-08-12 account
`user-6tzs2hdFVN7GoYQbWfC0eu7k` ceased to exist without a recorded mutation
sometime before 2026-08-18 and was replaced on 2026-08-20 by
`user-1UnalMTUg8XaoKcNDHpcsqZU`, created explicitly in the factory project and
verified at HTTP 200 by `GET /v1/organization/projects/{project}/service_accounts`
before the mapping was bound to it. The registry names the current identity and
keeps the historical one, on the A144 pattern; collectors and the requirement-2
driver resolve the current id, and the checkers accept any id in the roster
because the banked Results carry the historical one.

`policy/openai-wif.json` still records `user-6tzs...` in `service_account.id`
and `rule.service_account_id`. Those fields are **demoted by meaning** to "the
account the banked issuance-era evidence was minted against" - exactly as A145
demoted that file's `issuer.jwks_kid` - and no program reads them for the wire.
The file is not edited because all five banked OpenAI Results pin its digest as
`policy_sha256`.

The only Administration API call that discriminates a live service account is
the per-project `service_accounts` listing: `GET /v1/organization/users/{id}`
returns 404 for healthy service accounts too, so a detector built on it would
fire false every day of an account's healthy life.

### Liveness detection

`tools/check-openai-identity-liveness.py` closes the blind spot that let the
disappearance run for six days. Two modes:

- **Static** (the default, a `check-infra.sh` gate) validates the registry
  against the A150 contract with no network and no credential: one current
  entry, unique ids, one project, and no id promoted to current without
  `administration_api_verified` - the field that records a primary-source
  Administration API confirmation rather than a console reading.
- **`--live`** reads the per-project listing to exhaustion and asserts the
  current id is in it. On the control plane the
  `patchyard-openai-identity-metric` timer runs it daily at 06:25 UTC,
  publishing `patchyard_openai_identity_live` and
  `patchyard_openai_identity_checked_timestamp_seconds` to the node-exporter
  textfile collector; the converge asserts it once directly, so a missing
  account fails the converge rather than waiting a day. Alert on the timestamp
  as well as the gauge: a reading that cannot be completed fails the unit
  without republishing, so staleness is the signal for a broken detector.

Three cheaper signals are ruled out by primary-source observation and must
never be substituted: the token exchange returns 200 for a deleted account;
`GET /v1/organization/users/{id}` 404s for healthy service accounts; and
`GET /v1/organization/audit_logs` returns zero events even unbounded for this
organization. Because the audit log records nothing, the daily reading *is*
the record.

Unlike the A144 kid assertion this detector cannot be credential-free. It reads
a **Restricted, read-only** Administration key from
`/etc/patchyard/openai-admin-readonly.key`, `0400 root:root`, installed once
by the operator and never re-injected by converge, and excluded from restore
drills. The standing All-permissions operator key is deliberately not used: it
can create service accounts, mint API keys and change spend limits - the
mutations A132 puts behind attestation - and a host-resident copy would put
them one host compromise away, a worse trade than the blind spot being closed.
The detector makes no token exchange and no billable call.

The operator reported that the service account has zero API keys, the project
has a USD 50 monthly spend limit with whole-dollar granularity, and the
provider has this configuration:

- issuer `https://factory.example.com/workload-identity`;
- audience `https://api.openai.com`;
- uploaded JWKS enabled, at that time with `kid patchyard-39acdfd2bfc0acb0`
  (retired by the requirement-5 rotation on 2026-08-13; the console now trusts
  `patchyard-de842961c20b52a8`, recorded as `providers.openai.trusted_kid`
  in `policy/signing-identities.json`);
- OIDC discovery disabled; and
- subject `patchyard-control-plane` mapped to the service account above.

The project and service-account readbacks are provider receipts. The provider,
mapping, uploaded JWKS, and spend-limit changes are console-only control-plane
mutations for which no receipt is obtainable. Under A132 they require a
separate two-party attestation; this document is not that attestation. Every
first-exchange result carries the binary provenance mark
`mutation_receipt_obtained: false` and remains non-qualifying.

No OpenAI exchange was attempted while building this path. No credential
requirement is proven, OpenAI is not qualified, and all 13
`credential_qualified` values remain false.

A135 therefore forbids delivering any OpenAI bearer to a seat. This adapter
does not create a bearer file or credential path and changes none of the five
seat variables; it only performs the attended capture described below.

## Source contract

`policy/openai-wif.json` is the exact provider descriptor. It mirrors the
Anthropic policy's organization, project/workspace, spend, service-account,
issuer, and rule shape while using OpenAI's identifiers and exchange audience.
`rule.claims.factory_environment` is issued-claim vocabulary, not a mapping
condition: issuance still mints it and checkers require it on the assertion,
but the live OpenAI mapping card is `sub` only. The policy file stays
byte-untouched; the field's meaning is demoted the same way A145 demoted
`issuer.jwks_kid`. Restore the live claim table, never this field.

The assertion maximum is 300 seconds. OpenAI documents a one-hour ceiling, not
a required lifetime, and an exchanged bearer never outlives its subject token.
Five minutes is enough for one attended HTTPS exchange, preserves the
factory's already measured exposure bound, and avoids expanding credential
life for no operational benefit. The frozen base harness backdates `iat` by
five seconds for clock skew and sets `exp` 295 seconds after minting, so
`exp - iat` is exactly 300 seconds.

`tools/openai-wif-issuance.py` loads
`tools/anthropic-wif-lifecycle.py` only after verifying SHA-256
`10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d`.
It does not import or edit that frozen harness. It uses the root-only OpenAI
signing key at `/etc/patchyard/openai-wif-signing.pem`, whose current
public `kid` is the uploaded OpenAI JWKS key. A144 splits the signing
identity per provider: this path is OpenAI's alone, and
`policy/signing-identities.json` records each provider's path and trusted
`kid`. It changes only the policy data,
assertion audience, token endpoint, token-exchange body, and sanitized result
shape.

A145 re-points the minting kid authority. The adapter derives the kid from
the pem's public JWK and asserts it equals the registry's
`providers.openai.trusted_kid`: the registry is the steady-state kid
authority. The frozen policy's `issuer.jwks_kid` is no longer read for
minting; it means only "the kid the banked issuance-era evidence was minted
under," and the checker validates evidence era-split on the recorded adapter
digest. Mid-rotation the invoking collector owns the transitional kid and
passes it as an explicit `expected_kid`, overriding the registry for exactly
that run; the registry itself is never mutated out-of-band and updates by PR
after the run banks.

The adapter sends exactly one JSON request to
`https://auth.openai.com/oauth/token` with:

```text
grant_type           urn:ietf:params:oauth:grant-type:token-exchange
subject_token_type   urn:ietf:params:oauth:token-type:jwt
subject_token        the in-memory signed assertion
identity_provider_id idp_DlzD7RlQXgXxd1VSG2V93eEU
service_account_id   current_service_account_id from the A150 identity registry
```

No `scope` is sent because OpenAI says a request-body scope grants nothing.
A `scope` may come back in the *response* whenever the mapping defines
Permissions, so the requirement-2 driver records what arrives rather than
asserting absence (A150 clause 6).
Exchanged tokens cannot call Administration API endpoints. The adapter makes
no subsequent API call and never writes the assertion, response body, or
bearer.

## Unenforced response predicate

The [token exchange reference](https://developers.openai.com/api/reference/workload-identity-federation)
says arbitrary OIDC issuers are not supported, while the
[AWS configuration guide](https://developers.openai.com/api/docs/guides/workload-identity-federation/aws)
and the live console describe uploaded JWKS for a self-hosted issuer. This
contradiction is deliberately unresolved.

Under A125, no expected success status, denial status, error type, response
field set, request-ID form, or bearer lifetime is enforced before an OpenAI
response has been observed. A bounded HTTP response of any status is a valid
first observation. The adapter records only:

- request and observation UTC times, HTTP status, safe header metadata, and
  byte count;
- a type-only structural description of JSON fields, or `non_json`;
- whether an `access_token` field was supplied, never its value; and
- safely bounded `token_type`, `expires_in`, and error-type observations when
  present.

`response_predicate.enforced` is therefore `false`. An HTTP denial is captured
as the provider returned it instead of becoming a harness crash. Adjudicating
that observation and enforcing a descended predicate requires a later reviewed
change. A future requirement result must also include the required
attestation, baseline control, bracketing control, and permanent provenance
mark where its causal chain depends on console-only mutations.

The committed
`fixtures/checker-contracts/openai-first-token-exchange.json` is a Fixture: a
synthetic satisfiability input with an explicitly unobserved response
placeholder. It carries `fixture_kind`, `provider_response_observed: false`,
and `qualification_evidence: false`. The checker accepts it only in
`--contract-fixture` mode and refuses it as qualification evidence. It is not a
Result and its contents are not Evidence from a provider interaction.

The checker duplicates the established hygiene helpers (`is_within`,
`digest`, `parse_time`, `exact_keys`, `secret_named_key`, `isolation_errors`,
and `load_json_file`). A133 found one git revision for each helper and permits
that prospective duplication; provider-specific judgment remains in this
checker instead of a shared evidence-semantics module.

## Attended first-exchange procedure

Do not run these commands during build, review, CI, or an unattended session.
After the PR is merged and the exact revision is present on the control plane,
an attended operator may attempt the first exchange under a separate live
authorization.

First verify the deployed checkout and static contract:

```bash
cd /opt/patchyard
git status --short
git rev-parse HEAD
python3 -I tools/check-openai-wif-issuance.py --allow-missing-results
jq -e '.providers.openai.credential_qualified == false' policy/provider-egress.json
```

The gate is OpenAI-scoped on purpose: it protects against running an exchange
while an OpenAI bearer path is already qualified, and other providers'
qualification states change independently (Anthropic became qualified with the
live review seats and stays true).

Stop if the checkout is dirty, the revision is not the reviewed revision, the
checker rejects static preflight, the OpenAI credential flag is true, another
OpenAI exchange run is active, or the root signing key is not the intended
active identity.

Create one new root-owned directory on `/run` tmpfs and reserve one new output:

```bash
RUN_ID="openai-wif-$(date -u +%Y%m%d)-$(openssl rand -hex 5)"
CONTROL_STAGE="/run/patchyard-openai/$RUN_ID"
sudo install -d -m 0700 -o root -g root "$CONTROL_STAGE"
sudo python3 -I tools/openai-wif-issuance.py exchange \
  --run-id "$RUN_ID" \
  --output "$CONTROL_STAGE/openai-first-token-exchange.json"
```

The output is reserved as mode 0600 with `status: in_progress` before signing
or network activity. A completed HTTP interaction atomically replaces it with
the sanitized, non-qualifying observation. Copy only that JSON through the
reviewed management path to a new operator-host path, then run:

```bash
python3 -I tools/check-openai-wif-issuance.py --observation \
  /absolute/path/openai-first-token-exchange.json
```

Do not copy `/run/patchyard-openai`, a process dump, request body, assertion,
raw response, or bearer. Do not edit an observation to make the checker accept
it. Preserve the sanitized JSON for adjudication, then remove the control-plane
run directory after the reviewer has confirmed the copied bytes.

## Failure paths

- A root/argument failure, frozen-harness digest mismatch, invalid stage
  ownership/mode/tmpfs, inexact signing-key path, or inability to reserve the
  new output exits nonzero before any provider call and produces no usable
  Result.
- After output reservation, a policy mismatch or signing-key
  ownership/mode/content failure atomically writes `status: failed`, exits
  nonzero, and makes no provider call.
- A transport failure with no HTTP response writes `status: failed` and
  `provider_response_observed: false`. The observation checker refuses it.
- Any bounded HTTP response, including a denial or non-JSON body, is preserved
  as a sanitized provider observation. The adapter does not retry and does not
  classify it as success or failure.
- An oversized response or a failure to sanitize or durably write the terminal
  result exits nonzero. An abrupt process death can leave `status: in_progress`;
  that record is inert and cannot be used as a Result.
- Any checker finding an extra key, duplicate JSON key, out-of-order UTC time,
  stale source digest, credential-named field, bearer, JWT, or private-key
  material rejects the file.

None of these paths proves a requirement. The first observed response only
supplies the fact from which a later response predicate can descend.
