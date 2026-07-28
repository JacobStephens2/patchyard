# A-5 provider credential capability matrix and ruling request

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
`integration gap` means Factory has not implemented or proven it; `ruling gap`
means the semantics need a human decision before a fixture can claim success.

| Provider | Issuance | Delivery | Expiry | Revocation | Crash cleanup | Provider-side spend enforcement | Capability position |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Anthropic | **Documented.** Workload Identity Federation exchanges a trusted OIDC JWT at `POST /v1/oauth/token` for a service-account bearer token. Federation rules bind issuer claims, service account, workspace, OAuth scope, and token lifetime. | **Shared path exists; integration gap.** The control plane can exchange before boot and place only the bearer token on the existing capability drive. `api.anthropic.com` remains the guest's sole provider hostname; token exchange need not occur in the guest. | **Documented.** Rule lifetime is configurable from 60 to 86,400 seconds and is further capped by remaining assertion validity. The intended fixture would use a run-bounded assertion and token. | **Documented for future exchange; active-token semantics need proof/ruling.** Archiving a federation rule makes it reject token exchange; archiving an issuer makes all referencing rules reject exchange. The first-party docs do not promise immediate invalidation of an already minted bearer token. A short token lifetime bounds that gap. | **Shared path qualified synthetically; live-provider gap.** Session 5 already covers drive/tmpfs/process/mount/network teardown and forced cleanup. It must be rerun with the Anthropic token, including crash before and after capability unmount. | **Documented.** Anthropic defines organization monthly spend caps that pause API use and lower workspace spend limits evaluated alongside the organization limit. The qualification needs a dedicated Factory workspace and an intentionally tiny temporary cap so the provider denial can be observed without disturbing other Anthropic use. | Eligible for a reviewed live-qualification design; not qualified. Revocation-window ruling is required. |
| OpenAI | **Documented, with issuer-access caveat.** Workload Identity Federation exchanges an external OIDC JWT at `https://auth.openai.com/oauth/token` for a short-lived access token backed by a project service account and mapping. OpenAI documents specific platforms and SPIFFE; arbitrary issuers are not generally supported without the uploaded-JWKS/custom-issuer option or provider approval. | **Shared path exists; integration gap.** Exchange can occur on the control plane; only the returned bearer crosses the capability drive. The guest still needs egress only to `api.openai.com`. The Factory must first prove its organization exposes a supported issuer configuration. | **Documented.** Access tokens expire after at most one hour and never outlive the external subject token. A run-bounded subject token can therefore bound the provider token to the worker's five-minute attempt. | **Documented for future exchange; active-token semantics need proof/ruling.** A disabled mapping fails token exchange, and deleting/disabled principals can remove future authority. The WIF reference does not promise immediate revocation of an already issued bearer. Subject-token and access-token expiry bound the residual window. | **Shared path qualified synthetically; live-provider gap.** Reuse the Session 5 crash matrix with the OpenAI bearer and prove the same zero-residue set plus post-expiry/provider denial. | **Documented.** Organization and project hard spend limits return `429 insufficient_quota`; enforcement is explicitly not instantaneous and recorded spend may slightly exceed the configured amount. The live fixture needs a dedicated Factory project and a ruled maximum overshoot. | Eligible for a reviewed discovery/qualification design; not qualified. Issuer availability, revocation-window, and spend-overshoot rulings are required. |
| xAI | **Documented.** The Management API creates a team-bound API key and returns the full secret only on creation. It supports endpoint/model ACLs and exposes propagation status. | **Shared path exists; integration gap.** The control plane can create the key, wait for propagation, and deliver only that key on the capability drive. Guest egress remains `api.x.ai` only. | **Documented.** `expireTime` is a key field; a key whose expiration is in the past is rejected. The qualification can create a five-minute key directly. | **Documented.** A key can be disabled, rotated (permanently invalidating the old secret), or deleted; the propagation endpoint can bound when the change reaches inference clusters. Live proof is still required. | **Shared path qualified synthetically; live-provider gap.** Reuse the crash matrix with the xAI key, then disable/delete from the control plane and prove zero local residue. | **Documented but team-scoped and conditional.** xAI stops the API after prepaid credits are consumed and the team reaches its postpaid spending limit. The postpaid limit does not restrict prepaid consumption; setting postpaid to zero still spends existing prepaid credit. Qualification therefore needs a dedicated Factory team with bounded/no unrelated prepaid balance, or a ruling that this scope is too broad. | Eligible for a reviewed live-qualification design; not qualified. Team/prepaid spend scoping needs a ruling. |

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

## Candidate qualification topology

Anthropic can trust a Factory-owned OIDC issuer with an inline public JWKS.
OpenAI can use the same assertion design only if Patchyard's organization exposes the
documented uploaded-JWKS/custom-issuer option; otherwise its documented
portable path is SPIFFE JWT-SVID, which adds a SPIRE issuer to the control
plane. Either path keeps provider inference credentials out of durable state:

1. The control plane signs a single-use, run-bound OIDC assertion from a
   root-owned key unavailable to the worker.
2. It exchanges that assertion with the selected provider for a short-lived
   service-account bearer.
3. It places only that bearer in the existing host-tmpfs-backed capability
   drive and boots the existing one-provider Firecracker boundary.
4. The guest copies the bearer to guest tmpfs and removes the drive before the
   model can produce output.
5. Teardown deletes every local credential surface. The control plane disables
   the mapping/rule on the revocation fixture; ordinary runs rely on the
   run-bounded token expiry unless the ruling requires per-run mappings.
6. A dedicated Anthropic workspace or OpenAI project carries a hard provider
   spend limit. The fixture uses a temporary low limit in an isolated billing
   scope and restores the reviewed operational cap afterward.

xAI does not need an OIDC issuer: its Management API can create a per-run key
with `expireTime`, narrow ACLs, and explicit disable/delete. Its unresolved
issue is whether team-level billing plus prepaid-credit precedence is a narrow
enough provider-side cap for A-5.

## Ruling request

Please rule on these questions before implementation:

1. **Revocation window:** For Anthropic and OpenAI WIF, does disabling the
   federation rule/mapping plus a provider-enforced run-bounded expiry satisfy
   revocation if first-party documentation does not guarantee immediate
   invalidation of an already minted bearer? Proposed bound: token expiry no
   later than the five-minute worker attempt, with future exchange denied
   immediately and live proof of both facts.
2. **Spend overshoot:** OpenAI documents that a hard limit can overshoot
   slightly while enforcement propagates. Is a hard project cap with a measured
   and recorded maximum fixture overshoot acceptable, or must the provider
   promise a strict zero-overshoot ceiling?
3. **xAI spend scope:** Is a dedicated Factory team with bounded/no unrelated
   prepaid balance and a postpaid limit sufficient, or does A-5 require a hard
   cap attached directly to each key/run?
4. **First two providers:** Which two capability designs should proceed to
   implementation and live qualification first? The narrowest cross-family
   candidate is Anthropic WIF plus OpenAI WIF if Patchyard's OpenAI organization has
   the needed issuer option. Otherwise Anthropic plus xAI avoids deploying
   SPIRE, subject to the xAI spend-scope ruling.
5. **OpenAI issuer prerequisite:** Should the first implementation checkpoint
   be a read-only console/API proof that Patchyard can configure uploaded-JWKS or a
   custom issuer, with SPIFFE rejected unless separately reviewed? The matrix
   must not convert a generally documented WIF feature into an assumed
   organization entitlement.

Until those rulings and the resulting live fixtures land, no provider entry is
eligible and A77 cannot place implement and review in different families.
