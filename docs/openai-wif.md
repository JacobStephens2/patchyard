# OpenAI workload identity: A113 clause 5 checkpoint and contract survey

## Status

A113 clause 5 requires, as the first implementation checkpoint, "a read-only
console or API proof that Patchyard's OpenAI organization exposes uploaded-JWKS or a
custom issuer."

**The checkpoint passes.** Patchyard's organization exposes both. No workload identity
provider is configured, no OpenAI credential has been issued to the factory, and
no OpenAI A-5 requirement is qualified. All 13 provider `credential_qualified`
flags remain false.

This document records what is established, what is contradicted between two
OpenAI documents, and one structural finding that has to be ruled before any
OpenAI harness is written.

## Organization

| | |
| :-- | :-- |
| Name | Example Company |
| ID | `org-000000000000000000000000` |
| Admin credential | `PATCHYARD_OPENAI_ADMIN_KEY`, read-only Administration API scope, created 2026-08-06 |

The admin key is stored at `op://example-vault/patchyard-openai-account/admin-key`
and injected through `env.tpl`. It is a distinct credential from `OPENAI_API_KEY`,
which is a project key with no organization scope and returns HTTP 403 on every
`/v1/organization/*` path.

## Verified from this host, read-only

Confirmed directly against the Administration API with the admin key:

| Endpoint | Result |
| :-- | :-- |
| `/v1/organization/projects` | 200 - `Default project`, `fieldbook-preview` |
| `/v1/organization/projects/{id}/service_accounts` | 200 - two in the default project, none in `fieldbook-preview` |
| `/v1/organization/admin_api_keys` | 200 |
| `/v1/organization/workload_identity_providers` and eight path variants | 404 |

**There is no factory project and no factory service account.** Anthropic's
requirement-1 work runs against a dedicated workspace; the OpenAI equivalent does
not exist yet and will have to be created before issuance can be attempted.

## The provider surface is console-only

Workload identity providers are created and managed at
`https://platform.openai.com/settings/organization/security/workload-identity-provider`
(Organization Settings -> Security -> Workload Identity Provider). The
[federation guide](https://developers.openai.com/api/docs/guides/workload-identity-federation)
states this explicitly, and the
[token exchange reference](https://developers.openai.com/api/reference/workload-identity-federation)
documents no management API. The 404s above are consistent with that: they are
absent endpoints, not a wrong path.

Create-provider fields, observed in the console on 2026-08-06 and matching the
field list in the
[AWS configuration guide](https://developers.openai.com/api/docs/guides/workload-identity-federation/aws):

- **Name**
- **OIDC Issuer URL** (required; must match the token `iss` claim)
- **Audience** (required; defaults to `https://api.openai.com`)
- **Description** (optional)
- Advanced: **Use custom URL for OIDC discovery**
- Advanced: **Use uploaded JWKS for token verification**
- **Attribute transformations** via CEL expressions, `openai.` prefix applied

There is no preset cloud-provider selector. The fields are generic OIDC.

## Token exchange contract

`POST https://auth.openai.com/oauth/token`, `Content-Type: application/json`.

| Parameter | Required | Value |
| :-- | :-- | :-- |
| `grant_type` | yes | `urn:ietf:params:oauth:grant-type:token-exchange` |
| `subject_token_type` | yes | `urn:ietf:params:oauth:token-type:jwt` or `...:id_token` |
| `subject_token` | yes | the external OIDC JWT |
| `identity_provider_id` | yes | the configured provider's ID |
| `service_account_id` | yes | the OpenAI service account to map onto |

The response carries `access_token`, `token_type: Bearer`, and `expires_in`.
Documented limits:

- token lifetime **at most one hour**, and never beyond the subject token's own expiry;
- a scope value in the request body grants nothing - permissions come from the mapping;
- exchanged tokens **cannot call Administration API endpoints**;
- 50 providers per organization, 50 mappings per provider;
- SPIFFE support is JWT-SVID only. A113 refuses SPIFFE and SPIRE under every
  branch regardless.

Note the contrast with Anthropic, whose qualified expiry evidence uses a
five-minute-or-shorter bearer. An hour is a ceiling, not a floor, but the expiry
requirement's shape for OpenAI is not simply Anthropic's with names changed.

## Unresolved: the documentation contradicts itself

The token exchange reference states "arbitrary OIDC issuers not yet supported."
The AWS guide describes uploaded JWKS as the mechanism for "self-hosted or
non-standard OIDC providers where automatic discovery isn't available," and the
console exposes a generic issuer URL with no provider preset.

The factory's issuer is `https://factory.example.com/workload-identity`, a
self-hosted arbitrary issuer. Under the first reading it is unsupported; under
the second it is the documented case for uploaded JWKS.

**This is not resolvable by reading.** A126 recorded a provider contradicting its
own documentation about a denial shape, and A125 requires evidence to descend
from observed responses rather than descriptions. The question is settled by
configuring a provider against the factory issuer and attempting one exchange -
which is a console mutation, and therefore attended.

## Structural finding: requirements 4 and 5 have no evidentiary path yet

A131 enumerates the six A-5 requirements. Anthropic's requirement 4
(federation-rule revocation) and requirement 5 (signing-key rotation) are
evidenced by `tools/anthropic-wif-lifecycle-admin.py` performing plan, apply,
readback and rollback against Anthropic's Administration API. Every event in
`anthropic-revocation-rotation.json` carries a provider request ID and an
independent readback, and A129's bracketing controls depend on being able to
mutate provider state and observe the result programmatically.

OpenAI exposes no such API. A console mutation driven by a browser agent produces
no provider request ID, no receipt, and no readback - nothing A125 would accept
as an observed provider response, and nothing A129's controls could bracket.

Requirements 4 and 5 therefore have no evidentiary path on OpenAI under the
current contract. That is a ruling question, not an implementation detail, and it
bears directly on A113 clause 4: the first qualified pair is Anthropic plus
OpenAI *if* the clause 5 check passes. Clause 5 passes. Whether OpenAI can reach
six fixtures at all is a separate question this document does not answer.

## What has not been done

No provider configured, no service account created, no factory project created,
no token exchange attempted, no credential issued, no policy file written, no
harness or checker built. Nothing in this document is qualification evidence.
