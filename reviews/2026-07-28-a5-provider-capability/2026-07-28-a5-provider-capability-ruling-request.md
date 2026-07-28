# A-5 provider credential capability matrix and A113 disposition

Date: 2026-07-28

Providers in scope: Anthropic, OpenAI, xAI

Requirements: issuance, delivery, expiry, revocation, crash cleanup, and
provider-side spend enforcement

## Status and decision boundary

This is a capability matrix, not a qualification result. All three entries in
`policy/provider-egress.json` remain `credential_qualified: false`. Session 5
proved the shared secret-free worker boundary with a synthetic canary; it did
not exercise a provider credential. No ordinary credentialed run or behavioral
acceptance case has been started.

A113 has answered all five semantic questions that accompanied this matrix.
Its outcomes are recorded inline below so this document no longer presents
settled questions as open. A113 did not qualify any provider or authorize a
behavioral acceptance case.

A read-only inspection of Patchyard's OpenAI organization console on 2026-07-28
satisfied A113 clause 5's configuration-surface check. Clause 4 therefore
resolves directly to Anthropic plus OpenAI as the first pair; no ruling
amendment is required. The check created or saved nothing and does not qualify
either provider.

A provider becomes routable only after a reviewed implementation produces live
evidence for all six requirements. A77 additionally requires at least two
qualified providers from different model families before implement and review
can occupy different families. One qualified provider is therefore not a
useful terminal state.

Official provider documentation was re-checked on 2026-07-28. These surfaces
are newer than the original Session 5 record and must be treated as mutable
external capabilities until the live qualification freezes exact observations.

## Requirement interpretation

| Requirement | Qualification evidence required |
| --- | --- |
| Issuance | The control plane obtains a new provider credential for the selected provider and run identity without placing a standing inference credential on the worker. The provider records or returns a distinct credential/token identity. |
| Delivery | Only the selected credential crosses the existing read-only capability drive. The guest copies it into guest tmpfs, unmounts the drive before model output, and receives no other provider or factory authority. |
| Expiry | The provider, not merely the guest clock or cleanup script, rejects the credential after its declared lifetime. The live fixture records issuance time, expiry time, and a post-expiry denial without recording the credential. |
| Revocation | An authorized control disables the key, federation rule, mapping, or principal and the provider rejects either the active credential or every subsequent exchange according to a ruled maximum revocation window. The proof includes a positive call before and a provider denial after. |
| Crash cleanup | Forced termination at each credential-bearing phase leaves zero credential drive, guest tmpfs copy, process, mount, jail, tap, nftables table, or host staging file. Provider-side revocation/expiry still bounds any credential copied out before the crash. |
| Provider-side spend enforcement | A provider-owned hard limit scoped tightly enough to the Factory principal/project/workspace/team rejects further paid calls. A local token counter, alert, or post-hoc billing report is not sufficient. The live proof records the provider error and bounded overshoot semantics. |

## Provider-by-provider matrix

Legend: `documented` means the provider has a first-party capability;
`integration gap` means Factory has not implemented or proven it; `ruled by
A113` means the semantic contract is fixed but still needs live evidence.

| Provider | Issuance | Delivery | Expiry | Revocation | Crash cleanup | Provider-side spend enforcement | Capability position |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Anthropic | **Documented.** Workload Identity Federation exchanges a trusted OIDC JWT at `POST /v1/oauth/token` for a service-account bearer token. Federation rules bind issuer claims, service account, workspace, OAuth scope, and token lifetime. | **Shared path exists; integration gap.** The control plane can exchange before boot and place only the bearer token on the existing capability drive. `api.anthropic.com` remains the guest's sole provider hostname; token exchange need not occur in the guest. | **Documented.** Rule lifetime is configurable from 60 to 86,400 seconds and is further capped by remaining assertion validity. The intended fixture would use a run-bounded assertion and token. | **Documented for future exchange; ruled by A113.** Archiving a federation rule makes it reject token exchange; archiving an issuer makes all referencing rules reject exchange. The fixture must prove post-expiry denial of the minted bearer and denial of the next exchange after disabling the rule or mapping. | **Shared path qualified synthetically; live-provider gap.** Session 5 already covers drive/tmpfs/process/mount/network teardown and forced cleanup. It must be rerun with the Anthropic token, including crash before and after capability unmount. | **Documented.** Anthropic defines organization monthly spend caps that pause API use and lower workspace spend limits evaluated alongside the organization limit. The qualification needs a dedicated Factory workspace and an intentionally tiny temporary cap so the provider denial can be observed without disturbing other Anthropic use. | Eligible for a reviewed live-qualification design under A113; not qualified. |
| OpenAI | **Documented; organization surface observed.** Workload Identity Federation exchanges an external OIDC JWT at `https://auth.openai.com/oauth/token` for a short-lived access token backed by a project service account and mapping. Patchyard's organization exposes a free-text issuer URL plus custom discovery, uploaded JWKS, and attribute transformations rather than a fixed provider picker. | **Shared path exists; integration gap.** Exchange can occur on the control plane; only the returned bearer crosses the capability drive. The guest still needs egress only to `api.openai.com`. Uploaded JWKS lets the control plane remain outbound-only. Server-side acceptance when the provider is first saved remains unproven. | **Documented.** Access tokens expire after at most one hour and never outlive the external subject token. A run-bounded subject token can therefore bound the provider token to the worker's five-minute attempt. | **Documented for future exchange; ruled by A113.** A disabled mapping fails token exchange, and deleting/disabled principals can remove future authority. The fixture must prove post-expiry denial of the minted bearer and denial of the next exchange after disabling the mapping. | **Shared path qualified synthetically; live-provider gap.** Reuse the Session 5 crash matrix with the OpenAI bearer and prove the same zero-residue set plus post-expiry/provider denial. | **Documented; ruled by A113.** Organization and project hard spend limits return `429 insufficient_quota`; enforcement is explicitly not instantaneous and recorded spend may slightly exceed the configured amount. The fixture measures observed overshoot in a dedicated Factory project explicitly created inside `org-38MlwVEu4eU9CkGeEMCvPp5j`, never an ambient organization. | A113 clause 5's surface check passed, making OpenAI a first-pair provider. Saving the configuration is the first implementation residual; not qualified. |
| xAI | **Documented.** The Management API creates a team-bound API key and returns the full secret only on creation. It supports endpoint/model ACLs and exposes propagation status. | **Shared path exists; integration gap.** The control plane can create the key, wait for propagation, and deliver only that key on the capability drive. Guest egress remains `api.x.ai` only. | **Documented.** `expireTime` is a key field; a key whose expiration is in the past is rejected. The qualification can create a five-minute key directly. | **Documented.** A key can be disabled, rotated (permanently invalidating the old secret), or deleted; the propagation endpoint can bound when the change reaches inference clusters. Live proof is still required. | **Shared path qualified synthetically; live-provider gap.** Reuse the crash matrix with the xAI key, then disable/delete from the control plane and prove zero local residue. | **Documented; ruled by A113.** xAI stops the API after prepaid credits are consumed and the team reaches its postpaid spending limit. Qualification requires a dedicated Factory team with a low postpaid limit and a verified zero prepaid balance. | Eligible for a reviewed live-qualification design under A113; not qualified. |

## First-party sources

### Anthropic

- [Authentication and WIF](https://platform.claude.com/docs/en/manage-claude/authentication)
- [WIF configuration and exchange](https://platform.claude.com/docs/en/manage-claude/workload-identity-federation)
- [Create federation rule](https://platform.claude.com/docs/en/api/admin/federation_rules/create)
- [Federation issuer semantics](https://platform.claude.com/docs/en/api/admin/federation_issuers/retrieve)
- [Rate and spend limits](https://platform.claude.com/docs/en/api/rate-limits)
- [Workspace spend limits](https://platform.claude.com/docs/en/manage-claude/workspaces)

### OpenAI

- [Workload Identity Federation](https://developers.openai.com/api/docs/guides/workload-identity-federation)
- [Token exchange and expiry](https://developers.openai.com/api/reference/workload-identity-federation)
- [Hard spend limits](https://developers.openai.com/api/docs/guides/spend-limits)

### xAI

- [Management API key lifecycle](https://docs.x.ai/developers/rest-api-reference/management/auth)
- [Management API billing controls](https://docs.x.ai/developers/rest-api-reference/management/billing)

## OpenAI organization console evidence

A browser agent inspected the organization console read-only on 2026-07-28.
It opened the creation form only far enough to expose its fields, cancelled it,
and returned the page to its original empty state. Nothing was created,
modified, or saved.

- Organization: `Example Company`,
  `org-38MlwVEu4eU9CkGeEMCvPp5j`.
- Path: `platform.openai.com` -> `Organization settings` -> `Security` ->
  **"Workload Identity Provider"** tab.
- URL: `/settings/organization/security/workload-identity-provider`.
- The **"Create workload identity provider"** form offers **"Name"**, free-text
  **"OIDC Issuer URL"** with placeholder `https://issuer.example.com`,
  **"Audience"** with placeholder `https://api.openai.com`, and optional
  **"Description"**.
- The advanced section says:

  > "Configure custom OIDC discovery, uploaded JWKS, and derived attributes
  > for providers that cannot use standard discovery metadata or raw token
  > claims directly."

  It offers **"Use custom URL for OIDC discovery"**, **"Use uploaded JWKS for
  token verification"**, and **"Attribute transformations"** using CEL
  expressions that derive OpenAI attributes from token claims under
  `assertion`.
- SPIFFE is not offered as a named option, and there is no provider picker
  alongside which it could appear. The observed surface has no fixed
  pre-approved platform list.

This proves that this organization exposes the generic issuer and uploaded-JWKS
configuration surface required by A113 clause 5. It does **not** prove that the
server will accept a saved provider: **"Create"** was never submitted. The first
implementation step must create the reviewed provider in the explicit
organization and record server-side acceptance, retiring that residual as part
of fixture work.

The account also exposes a second organization named `Personal`. Every OpenAI
provider, service-account, project, and hard-cap operation must bind
`org-38MlwVEu4eU9CkGeEMCvPp5j` explicitly and fail closed if it differs; ambient
login state is not authority. Otherwise a dedicated Factory project could be
created in the wrong organization, where A113 clause 2's hard cap would not
bind Factory spend.

## Candidate qualification topology

The console evidence resolves the first pair to Anthropic plus OpenAI.
Anthropic accepts an inline public JWKS, and OpenAI exposes uploaded JWKS for a
free-text issuer. The uploaded-JWKS option is architecturally load-bearing:
without it, OpenAI would have to fetch a publicly reachable OIDC discovery
document and JWKS URL from the control plane. The dashboard behind Caddy is the
control plane's only current public exposure; serving issuer metadata would add
a new inbound surface with its own hardening, availability contract, and
qualification. With inline/uploaded JWKS, neither provider needs inbound
control-plane reachability; assertion signing and token exchange are purely
outbound.

SPIFFE and SPIRE remain refused under A113 for every branch and are now moot for
the first pair. The SPIRE fallback was avoided, not deferred. The permitted WIF
path keeps provider inference credentials out of durable state:

1. The implementation explicitly selects
   `org-38MlwVEu4eU9CkGeEMCvPp5j`, creates the reviewed OpenAI provider, and
   records server-side acceptance. A mismatch or save denial fails closed.
2. The control plane signs a single-use, run-bound OIDC assertion from a
   root-owned key unavailable to the worker.
3. It exchanges that assertion with the selected provider for a short-lived
   service-account bearer.
4. It places only that bearer in the existing host-tmpfs-backed capability
   drive and boots the existing one-provider Firecracker boundary.
5. The guest copies the bearer to guest tmpfs and removes the drive before the
   model can produce output.
6. Teardown deletes every local credential surface. The control plane disables
   the mapping/rule on the revocation fixture and proves that the next exchange
   fails; ordinary runs rely on the run-bounded token expiry, which the fixture
   separately proves by provider denial of the minted bearer.
7. A dedicated Anthropic workspace or OpenAI project carries a hard provider
   spend limit. The OpenAI project is created only inside the explicit Patchyard
   organization. The fixture uses a temporary low limit in an isolated billing
   scope and restores the reviewed operational cap afterward.

xAI does not need an OIDC issuer: its Management API can create a per-run key
with `expireTime`, narrow ACLs, and explicit disable/delete. A113 makes its
team-level billing scope acceptable only on a dedicated Factory team with a low
postpaid limit and a verified zero prepaid balance.

## A113 disposition of the five questions

1. **Revocation window - ruled.** The question was whether disabling the
   Anthropic/OpenAI federation rule or mapping plus run-bounded expiry satisfies
   revocation. **A113 outcome:** yes, only when the live fixture proves both a
   positive call followed by provider rejection of the minted bearer after an
   expiry no later than the five-minute worker attempt, and a positive exchange
   followed by provider rejection of the next exchange after disabling the
   rule or mapping. Record issuance, expiry, and both denials, never the token.
2. **Spend overshoot - ruled.** The question was whether OpenAI's non-instant
   hard limit is sufficient. **A113 outcome:** a hard cap on a dedicated Factory
   project or workspace qualifies. The fixture records measured overshoot as an
   observed figure with no preset ceiling; the first qualification establishes
   the baseline rather than promising zero overshoot.
3. **xAI spend scope - ruled.** The question was whether a team-scoped limit is
   narrow enough. **A113 outcome:** use a dedicated Factory team with a low
   postpaid limit and a verified zero prepaid balance, checked and recorded at
   qualification. Any prepaid balance disqualifies the fixture because it makes
   the postpaid limit non-binding.
4. **First two providers - resolved from the conditional ruling.** The question
   was which pair should proceed first. **A113 outcome:** Anthropic plus OpenAI
   if question 5's check passes; otherwise Anthropic plus xAI. The 2026-07-28
   console check found the generic issuer and uploaded-JWKS surface, so the
   first pair is **Anthropic plus OpenAI**. This executes A113's conditional
   clause directly; no ruling was skipped and no amendment is required.
5. **OpenAI issuer prerequisite - ruled; configuration surface proven.** The
   question was whether discovery must precede design. **A113 outcome:** the
   first checkpoint is a read-only console or API proof that Patchyard's OpenAI
   organization exposes uploaded-JWKS or a custom issuer. The console evidence
   above passes that surface check. It does not prove permission to save the
   provider, which remains an explicit first-implementation residual. SPIFFE
   and SPIRE remain refused rather than deferred and are unnecessary for the
   resolved first pair.

Until the resulting live fixtures land, no provider entry is eligible and A77
cannot place implement and review in different families. Acceptance remains
paused.
