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
| Service account | `user-6tzs2hdFVN7GoYQbWfC0eu7k` | `patchyard-worker` |
| Workload identity provider | `idp_DlzD7RlQXgXxd1VSG2V93eEU` | `patchyard` |

The operator reported that the service account has zero API keys, the project
has a USD 50 monthly spend limit with whole-dollar granularity, and the
provider has this configuration:

- issuer `https://factory.example.com/workload-identity`;
- audience `https://api.openai.com`;
- uploaded JWKS enabled with `kid patchyard-39acdfd2bfc0acb0`;
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
It does not import or edit that frozen harness. It reuses the root-only active
signing key at `/etc/patchyard/anthropic-wif-signing.pem`, whose current
public `kid` is the uploaded OpenAI JWKS key. It changes only the policy data,
assertion audience, token endpoint, token-exchange body, and sanitized result
shape.

The adapter sends exactly one JSON request to
`https://auth.openai.com/oauth/token` with:

```text
grant_type           urn:ietf:params:oauth:grant-type:token-exchange
subject_token_type   urn:ietf:params:oauth:token-type:jwt
subject_token        the in-memory signed assertion
identity_provider_id idp_DlzD7RlQXgXxd1VSG2V93eEU
service_account_id   user-6tzs2hdFVN7GoYQbWfC0eu7k
```

No `scope` is sent because OpenAI says a request-body scope grants nothing.
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
jq -e '[.providers[].credential_qualified] | length == 13 and all(. == false)' \
  policy/provider-egress.json
```

Stop if the checkout is dirty, the revision is not the reviewed revision, the
checker rejects static preflight, any credential flag is true, another OpenAI
exchange run is active, or the root signing key is not the intended active
identity.

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
