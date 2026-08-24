# OpenAI's project binding for a WIF-exchanged service-account token

*2026-08-20. Desk research against OpenAI's primary developer documentation, read
today at `developers.openai.com` (the `platform.openai.com/docs/*` URLs now 301 to
it) and against OpenAI's published OpenAPI specification. **No live API call was
made in the course of this note** - every factory-side fact restated here comes
from [issue 264](https://github.com/JacobStephens2/patchyard/issues/264)
and the last comment on [issue 210](https://github.com/JacobStephens2/patchyard/issues/210),
not from a probe. Where documentation is silent this note says so rather than
filling the gap.*

## Summary

**Yes - a workload-identity-federated token is a general-purpose API credential and
is documented to call inference endpoints; it is the Administration API that it
explicitly *cannot* call.** OpenAI's own example token-exchange response carries
`"scope": "api.model.read api.model.request"`, and `api.model.request` is the
documented permission for `/v1/chat/completions`. The admin-only hypothesis is
dead, and it is dead in the opposite direction from the one feared.

The observed 401 is therefore **not** explained by "WIF tokens can't do inference".
The documented candidate causes that remain are project/permission binding on the
mapped service account - and OpenAI does **not** document a distinct error `type`
or `code` for any of them.

## 1. Can a WIF token call inference endpoints?

**Documented: yes.** Three independent statements establish it.

- The exchange reference's success example returns
  `"scope": "api.model.read api.model.request"`, described as the OAuth-scope
  rendering of the mapping's **Permissions**.
  ([Workload identity token exchange - Response](https://developers.openai.com/api/reference/workload-identity-federation))
- Every provider setup guide tells you to pick inference permissions on the
  mapping: "Select appropriate **Permissions** such as `api.model.request` and
  `api.vector_store.read` to further narrow access tokens minted from this
  mapping."
  ([Configuring WIF for AWS](https://developers.openai.com/api/docs/guides/workload-identity-federation/aws);
  the identical sentence appears in the Kubernetes, GitHub Actions, Google Cloud,
  Azure, Oracle, SPIFFE and X.509 guides)
- The RBAC guide maps that permission onto endpoints: "Model capabilities Request
  (`api.model.request` and `model.request`) for `/v1/audio`,
  `/v1/chat/completions`, `/v1/embeddings`, `/v1/images`, `/v1/moderations`,
  `/v1/realtime`, and `/v1/responses`".
  ([Manage permissions in the OpenAI platform](https://developers.openai.com/api/docs/guides/rbac))

The **Limitations** section states the exclusion list, and it is the inverse of the
feared one:

> - Workload identity access tokens can't be used to call Admin API endpoints. For
>   Admin APIs, use an admin API key.
> - Workload identity access tokens aren't accepted by these endpoints:
>   `DELETE /v1/models/{id}` and `POST /v1/images/request_audit`.

([Workload identity token exchange - Limitations](https://developers.openai.com/api/reference/workload-identity-federation))

`/v1/chat/completions` is not on that list. The general authentication page
likewise treats the two credential types as peers: "The OpenAI API accepts bearer
credentials from API keys or from short-lived access tokens created with workload
identity federation."
([API Overview - Authentication](https://developers.openai.com/api/reference/overview))

*Inferred, not documented:* nothing states that an inference call by a WIF token is
billed to the owning project, but since the token "authorize[s] like service-account
API credentials" and usage is attributed to the project of the credential, the
factory's requirement-2 spend capture should attribute to `patchyard` once the
call succeeds. This is an inference from two documented sentences, not a documented
guarantee.

## 2. How does a token acquire project scope?

**Documented: through the mapped service account's owning project. Not through a
header, not through a claim, not through the audience.**

> Workload identity access tokens are backed by an OpenAI service account and
> project. On OpenAI API surfaces, they authorize like service-account API
> credentials rather than user OAuth tokens.

([Workload identity token exchange - Authorization behavior](https://developers.openai.com/api/reference/workload-identity-federation))

The mapping itself carries the project. Its dashboard fields are:

| Option | Documented description |
| :-- | :-- |
| Project | "The project that owns the target service account." |
| Service account | "The service account the workload can use. You can create a new service account in the selected project or select an existing service account." |
| Permissions | "Optional API permissions that further narrow access tokens minted from this mapping. These permissions can't grant access beyond the mapped service account." |

([Workload identity federation - Configure service account mappings](https://developers.openai.com/api/docs/guides/workload-identity-federation))

Taking the candidate mechanisms in turn:

**(a) Service-account project membership - yes, this is the mechanism.** Confirmed
by the "backed by an OpenAI service account and project" sentence above and by "An
OpenAI service account is a nonhuman identity owned by a project."
([Manage service accounts with Terraform](https://developers.openai.com/api/docs/guides/terraform/service-accounts))

**(b) `OpenAI-Project` header - documented as unnecessary here, and not documented
as a scope-conferring mechanism at all.** The authentication section gates it on a
narrow case:

> If you belong to more than one organization or access projects through a legacy
> user API key, pass a header to specify which organization and project to use for
> an API request

([API Overview - Authentication](https://developers.openai.com/api/reference/overview))

A WIF token is neither a legacy user API key nor multi-org - it resolves to exactly
one service account in exactly one project. The header is documented for *selecting
among* things the credential already reaches, never for *granting* project access.
The OpenAI Terraform provider docs say the same from the other side: "When these
optional variables aren't set, OpenAI resolves the organization and project from the
API key."
([Manage OpenAI resources with Terraform](https://developers.openai.com/api/docs/guides/terraform))
Whether the header is *ignored* or *validated* for a service-account token is **not
documented** (see below).

**(c) A claim in the federation rule / token request - no.** Claims and derived
`openai.*` attributes are used only for *mapping resolution* - deciding which single
mapping matches - never for authorization. "OpenAI looks up mappings for the
requested `identity_provider_id` and `service_account_id` ... and issues a token only
if exactly one enabled mapping matches all configured attributes."
([WIF guide - Mapping resolution example](https://developers.openai.com/api/docs/guides/workload-identity-federation))
And explicitly: "The token exchange uses the permissions configured on the matching
service account mapping. A `scope` value in the request body doesn't grant access."
([Token exchange - Request parameters](https://developers.openai.com/api/reference/workload-identity-federation))

**(d) The audience - no.** The `aud` value is purely a subject-token verification
input: "**Audience** - The expected `aud` claim on the external subject token", and
the guides say to configure "the exact audience your workflow requests, such as
`your-wif-audience` or `https://api.openai.com/v1`."
([WIF guide](https://developers.openai.com/api/docs/guides/workload-identity-federation);
[GitHub Actions guide](https://developers.openai.com/api/docs/guides/workload-identity-federation/github-actions))
An arbitrary opaque string is an acceptable audience, which settles that it carries
no authorization meaning. The factory's `https://api.openai.com` (no `/v1`) is
therefore fine as long as it matches the provider config - and it does, since the
exchange returns 200.

**(e) Something else - the mapping's optional Permissions, which narrow but never
widen.** "If a mapping defines permissions, those permissions further narrow the
effective API access for tokens minted from that mapping. If a mapping doesn't
define permissions, OpenAI doesn't add a workload identity federation-specific scope
restriction, and authorization is derived from the mapped service account's project
and organization roles."
([Token exchange - Authorization behavior](https://developers.openai.com/api/reference/workload-identity-federation))

The load-bearing consequence: **leaving mapping Permissions blank does not grant
everything - it falls through to the service account's roles.** The setup guides
state this plainly: "Leave permissions blank to avoid adding a WIF-specific scope
restriction; the token still authorizes as the mapped service account."
([AWS guide, step 5](https://developers.openai.com/api/docs/guides/workload-identity-federation/aws))

And the closing statement, which is the one that matters for the observed 401:

> Workload identity tokens don't bypass normal endpoint authorization. The target
> endpoint must still allow the effective permissions and project access carried by
> the token.

## 3. Can a service account exist without project membership?

**Documented: service accounts are inherently project-owned - but a service account
can hold no project permissions.** These are two different things, and the
distinction is exactly the ambiguity issue 210 is stuck on.

*Ownership is structural.* Every Administration API path for a service account is
nested under a project - `GET|POST /v1/organization/projects/{project_id}/service_accounts`
and `GET|POST|DELETE /v1/organization/projects/{project_id}/service_accounts/{service_account_id}`.
([openai/openai-openapi `openapi.yaml`](https://github.com/openai/openai-openapi/blob/master/openapi.yaml))
There is no org-level service-account collection and no move-between-projects
operation in the spec. The Terraform provider encodes the same shape: the import ID
for a project service account is `<project_id>/<service_account_id>`.
([Import and reconcile OpenAI resources](https://developers.openai.com/api/docs/guides/terraform/import-and-reconcile))

*Permission is separable.* The `ProjectServiceAccount` schema's `role` is an enum of
`owner`, `member`, **`none`**, and Terraform documents creating an account in that
state: "The provider creates the service-account identity without generating an API
key or assigning a default project role. ... At this stage, the service account has
no project permissions."
([openapi.yaml](https://github.com/openai/openai-openapi/blob/master/openapi.yaml);
[Manage service accounts with Terraform](https://developers.openai.com/api/docs/guides/terraform/service-accounts))

So the honest reading of "the project shows zero service accounts" is **not**
established by documentation to mean "the account has no project". It could equally
mean the account is owned by a different project, or - and this is a real
possibility the docs leave open - that the console's Members > Service accounts view
lists by *role assignment* rather than by ownership, in which case a `role: none`
account owned by `patchyard` would render as "No members found" while remaining the
mapping's valid target. **Nothing in the documentation resolves which of these the
console shows.** The `GET /v1/organization/projects/proj_4zpZhhPPNYCvPRE5vGuRBALH/service_accounts`
listing is the primary-source test that would.

*What a token minted from a permission-less service account does:* **not
documented.** The exchange's documented failure modes are all identity/mapping
failures (see §4); "the service account has no project role" is not among them, and
the mapping resolution step is described purely in terms of attribute matching. The
inference - and it is only that - is that the exchange still succeeds (which matches
the factory's observed 200) and the API call fails downstream, per "If token exchange
succeeds but a later OpenAI API request fails, debug the minted access token as an
authorization issue."

*On deletion and shared display names.* Deletion is documented **only by id**:
`DELETE /v1/organization/projects/{project_id}/service_accounts/{service_account_id}`,
whose path parameters are "The ID of the project" and "The ID of the service
account". There is no name-keyed delete, no name-uniqueness constraint anywhere in
the spec, and the `name` field carries no `unique` marker - so two accounts sharing
the display name `patchyard-worker` is a documented-possible state, and deleting
one by id cannot affect the other. Nothing about issue 229's deletion is
contradicted by the documentation. ([openapi.yaml](https://github.com/openai/openai-openapi/blob/master/openapi.yaml))

*A lead worth pulling:* OpenAI's audit log emits `service_account.created`,
`service_account.updated` (with `changes_requested.role`), `service_account.deleted`,
and `workload_identity_provider_mapping.created` / `.updated` / `.deleted` events.
([openapi.yaml, `AuditLogEventType`](https://github.com/openai/openai-openapi/blob/master/openapi.yaml);
[Audit logs reference](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/audit_logs))
These would settle *when* `user-6tzs2hdFVN7GoYQbWfC0eu7k` lost or never had its role
- 2026-08-12, 2026-08-19, or never - which issue 210 records as open. This requires an
admin API key, which WIF tokens cannot supply.

## 4. Documented 401 `type`/`code` per cause

**This is where the documentation is thinnest, and the answer is largely "OpenAI does
not document it."**

What *is* documented, in the error-codes guide, is four 401 rows - none of which
carries a machine-readable `code`, and all of which are written for human API-key
holders rather than for federated service accounts:

| Documented 401 | Documented cause | Machine `code`? |
| :-- | :-- | :-- |
| Invalid Authentication | "Invalid Authentication" - expanded as a revoked key, "a different API key than the one assigned to the requesting organization or project", or "an API key that does not have the required permissions for the endpoint you are calling" | none published |
| Incorrect API key provided | typo, "an API key that belongs to a different organization or project", deleted/deactivated key | none published |
| You must be a member of an organization to use the API | "You have left or been removed from your previous organization" / "from your previous project" | none published |
| IP not authorized | request IP outside the allowlist | `ip_not_authorized` |

([Error codes - API errors](https://developers.openai.com/api/docs/guides/error-codes);
the `ip_not_authorized` code is confirmed on the
[IP allowlist guide](https://developers.openai.com/api/docs/guides/ip-allowlist))

The error envelope shape itself is documented - `{"error": {"type", "message",
"param", "code"}}`, with `type` and `message` required and `code` nullable
([openapi.yaml, `Error` / `ErrorResponse`](https://github.com/openai/openai-openapi/blob/master/openapi.yaml))
- which matches the "well-formed JSON error envelope" the factory observed.

Two of these rows are directly on point for the factory's situation and are the
best available attribution candidates:

- **"Invalid Authentication"** explicitly covers *"a credential that does not have
  the required permissions for the endpoint you are calling"*. That is the missing
  `api.model.request` case, and it is documented as **401, not 403**.
- **"You must be a member of an organization to use the API"** explicitly names
  *"You have left or been removed from your previous project"* as a cause. That is
  the no-project-membership case, again **401**.

Both are stated in API-key language; **neither is restated for WIF tokens anywhere.**

## What is NOT documented

Stated plainly, because each of these is actionable as a gap:

1. **No WIF-specific API-call error table.** The exchange reference has a thorough
   error table, but it covers *token exchange* only. For post-exchange failures the
   entire published guidance is one sentence: "If token exchange succeeds but a later
   OpenAI API request fails, debug the minted access token as an authorization issue.
   The token still has the project, service account, endpoint authorization, IP
   allowlist, and other policy checks that apply to normal OpenAI API requests."
   No status code, no `type`, no `code`, no worked example.
2. **No `code` value for any 401 except `ip_not_authorized`.** The observed envelope
   cannot be attributed to a documented cause by `code`, because OpenAI publishes no
   `code` for invalid-token, expired-token, missing-project, or
   insufficient-permission. Only the human-readable `message` distinguishes them, and
   messages are not a contract.
3. **No documented behaviour for a token whose service account has `role: none`.**
   Not at exchange time, not at call time.
4. **No documented behaviour for `OpenAI-Project` on a service-account or WIF
   token** - whether it is ignored, honoured, or rejected on mismatch. The header is
   only ever documented for multi-org users and legacy user keys.
5. **No documented 401-vs-403 rule.** The 403 rows in the error-codes guide are
   geography and (for the X.509 endpoint) wrong-method; the Python SDK's
   `PermissionDeniedError` is described only as "You don't have access to the
   requested resource" with no status mapping. Insufficient *permission* is
   documented under 401, so **a project-viewer-vs-member distinction would not
   reliably show up as 403** and cannot be used to discriminate causes.
6. **Whether the console's project Members > Service accounts view lists by
   ownership or by role.** Load-bearing for interpreting "zero service accounts", and
   entirely undocumented.
7. **The X.509 flow is documented as returning deliberately generic errors** -
   "X.509 token exchange returns generic OAuth errors and doesn't expose certificate,
   root, provider, or mapping details."
   ([X.509 guide](https://developers.openai.com/api/docs/guides/workload-identity-federation/x509))
   That is an explicit design stance toward opacity, and it is reasonable to expect
   the same reticence in the JWT path's API-call errors. Plan for attribution to
   require experiment, not documentation.

### Where the docs look unreliable

Flagged per this project's standing habit of recording provider self-contradiction.
Nothing here rises to a contradiction of fact, but two things are loose:

- **The permission-to-endpoint mapping for `/v1/responses` is stated twice,
  inconsistently.** The RBAC permissions table lists "Responses API - Create
  responses" as its own permission (and the Terraform guide uses
  `api.responses.write`), while the Batch implications table in the *same page* says
  `api.model.request` covers `/v1/responses`.
  ([Manage permissions](https://developers.openai.com/api/docs/guides/rbac))
  If the factory ever moves the one-shot from `/v1/chat/completions` to
  `/v1/responses`, do not assume one permission covers it - grant both or test.
  `/v1/chat/completions` itself is unambiguous: `api.model.request`.
- **Service-account identifier format.** Documentation and the OpenAPI examples use
  `svc_acct_*` throughout (including `OPENAI_SERVICE_ACCOUNT_ID="svc_acct_example"`
  in the X.509 guide), while the factory's mapping targets
  `user-6tzs2hdFVN7GoYQbWfC0eu7k`. OpenAI does not document a `user-*` form for
  service accounts anywhere. This may be nothing - the exchange resolves the id
  successfully, so OpenAI clearly accepts it - but it is an undocumented shape, and
  an account carrying a *user*-shaped id is worth confirming is genuinely a service
  account rather than an organization user, since the two have different project
  semantics.

## What this means for the factory

**The 401 is an authorization failure on a live, correctly-federated identity.**
Question 1's answer removes the catastrophic branch: there is no need to abandon WIF
for inference, and requirements 1, 4 and 5 rest on a mechanism OpenAI documents as
general-purpose. What remains is a binding problem with two documented candidate
causes, both of which surface as 401:

- **(A) The mapped service account holds no project role** (`role: none`, or removed
  from the project). Documented 401 row: "You must be a member of an organization to
  use the API", whose stated causes include removal from a project.
- **(B) The mapped service account holds a role, but the effective permissions
  exclude `api.model.request`** - either because the *mapping's* Permissions are set
  to something narrower (for example `api.model.read` alone, which is exactly enough
  for the `/v1/models` call requirement 1 has always made and exactly not enough for
  `/v1/chat/completions`), or because the service account's project role lacks Model
  capabilities Request. Documented 401 row: "Invalid Authentication", whose stated
  causes include a credential without the required permissions for the endpoint.

**(B) deserves more weight than issue 210 gave it.** Every prior requirement
exercised only the exchange and `/v1/models`. `api.model.read` satisfies `/v1/models`
and nothing else. A mapping configured with `api.model.read` alone would produce
exactly the observed history: 200 at the exchange, 200 at `/v1/models`, 401 at
`/v1/chat/completions`, and it would do so **regardless of project membership**. The
"zero service accounts in the project" observation is consistent with (A) but does
not exclude (B), and (B) is repairable in the dashboard without touching the service
account at all.

**The mapping's `scope` response field is free evidence the factory is currently
throwing away.** The exchange returns `scope` whenever the mapping defines
permissions. Capturing and logging that string on the next run discriminates (A) from
(B) before the inference call is even made: a `scope` containing `api.model.request`
rules out the mapping-permissions branch; a `scope` of `api.model.read` alone, or an
absent `scope`, is decisive the other way. This is cheaper than any console work and
costs nothing billable.

**On the frozen one-shot request being defective.** Documentation does not support
adding `OpenAI-Project`. Project scope is documented to come from the mapped service
account, and the header is documented only for multi-org users and legacy user keys.
Sending `Authorization` plus `content-type` is the documented-correct shape for a
WIF bearer, so **the calibrated request is not defective on this axis**, and
`request_sha256` / the assembler's phase-invariant `request_body_sha256` do not need
to move. Since the header's behaviour on a service-account token is undocumented,
adding it speculatively would perturb the frozen request hash for no documented
benefit and with a non-zero chance of introducing a *new* failure. Recommend not
adding it.

**On evidence capture.** Issue 210 correctly identifies that `preserve_failed_evidence`
never fires at the transport stage. Given finding §4 - that OpenAI publishes no `code`
for any of the relevant 401 causes - the `message` string is the *only* signal that
distinguishes them, and it is unversioned. Preserving the raw 401 body (plus the
`x-request-id` header, which OpenAI recommends logging for support escalation) is
therefore not a nice-to-have: without it, attribution is impossible from documentation
alone, and this note cannot be tightened further.

**Repairs, in documented-cost order.** All are console or Admin API work; none
touches the worker.

1. Capture the exchange response's `scope` and the 401 body plus `x-request-id`.
   Free, and discriminates (A) from (B).
2. Read `GET /v1/organization/projects/proj_4zpZhhPPNYCvPRE5vGuRBALH/service_accounts`
   with an admin key. This is the primary-source answer to "does the project own the
   account", independent of whatever the console's Members view chooses to display.
3. If (B): set the mapping's Permissions to include `api.model.request`, or clear
   them so authorization falls through to the service account's roles.
4. If (A): grant the service account a project role carrying Model capabilities
   `Request`. Note the documented propagation delay - "Allow up to **30 minutes** for
   role changes and group sync to propagate"
   ([Manage permissions](https://developers.openai.com/api/docs/guides/rbac)) - which
   means a re-run immediately after a console change can produce a false negative.
   Prefer a custom least-privilege project role over the built-in `member`, per
   OpenAI's own guidance: "Don't assign the built-in `member` or `owner` role when a
   custom project role provides the permissions your workload needs."
5. Only if the account turns out to be owned by the wrong project: recreate it in
   `patchyard` and repoint the mapping. There is no documented move operation, and
   the new account gets a new id, so the mapping's `service_account_id` must change -
   which is a mapping edit, not a worker change.

Steps 3 and 4 leave the banked requirement-1/4/5 evidence intact: neither changes the
provider, the audience, the subject, the exchange request, or the one-shot request
body. Step 5 changes the mapping's target id, which is control-plane configuration
rather than worker contract.

## Sources

All read 2026-08-20. `platform.openai.com/docs/*` now 301-redirects to
`developers.openai.com/api/docs/*`; the `developers.openai.com` URLs are cited.

- [Workload identity federation (guide)](https://developers.openai.com/api/docs/guides/workload-identity-federation)
- [Workload identity token exchange (reference)](https://developers.openai.com/api/reference/workload-identity-federation)
- [Configuring workload identity federation for AWS](https://developers.openai.com/api/docs/guides/workload-identity-federation/aws)
- [Configuring workload identity federation for GitHub Actions](https://developers.openai.com/api/docs/guides/workload-identity-federation/github-actions)
- [Configure workload identity federation with X.509 certificates (beta)](https://developers.openai.com/api/docs/guides/workload-identity-federation/x509)
- [API Overview (authentication, headers, request IDs)](https://developers.openai.com/api/reference/overview)
- [Manage permissions in the OpenAI platform (RBAC)](https://developers.openai.com/api/docs/guides/rbac)
- [Error codes](https://developers.openai.com/api/docs/guides/error-codes)
- [Manage service accounts with Terraform](https://developers.openai.com/api/docs/guides/terraform/service-accounts)
- [Administration API overview](https://developers.openai.com/api/reference/administration/overview)
- [Organization Projects Service Accounts reference](https://developers.openai.com/api/reference/resources/organization/subresources/projects/subresources/service_accounts)
- [openai/openai-openapi `openapi.yaml`](https://github.com/openai/openai-openapi/blob/master/openapi.yaml)

Not usable: `help.openai.com` returned HTTP 403 to every automated fetch attempted
today, so no first-party help-centre article could be read directly. Nothing in this
note rests on one.
