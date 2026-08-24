# Does Anthropic share the OpenAI identity blind spot?

Findings for issue
[#275](https://github.com/JacobStephens2/patchyard/issues/275),
raised by
[#269](https://github.com/JacobStephens2/patchyard/issues/269)
("consider extending it to Anthropic if the same blind spot exists there").

**Desk research only. No live API call was made, and no factory-side state was
read except the committed files named below.** Every factory fact restated here
comes from `policy/anthropic-wif.json`, `tools/anthropic-wif-admin.py`, and
`docs/anthropic-issuance.md` at master `f13fd2e`.

Primary sources, all fetched 2026-08-20 from `platform.claude.com` (the
`docs.claude.com` and `docs.anthropic.com` hosts 301 to it):

- `/docs/en/manage-claude/admin-api` — Admin API overview and authentication
- `/docs/en/manage-claude/wif-admin-api` — Manage WIF with the Admin API
- `/docs/en/manage-claude/wif-reference` — scopes, validation, error table
- `/docs/en/manage-claude/workload-identity-federation` — concepts, exchange
- `/docs/en/api/admin/service_accounts` — generated service-account reference

## Verdict

**No. Anthropic does not share the blind spot, and the detector should not be
ported.** The failure mode OpenAI exhibits — a live mapping whose target
identity has ceased to exist, with the exchange still returning 200 — is
unreachable through Anthropic's documented API, for three independent reasons.
But the credential story runs the opposite way: Anthropic offers **no read-only
admin credential at all**, so the
[#274](https://github.com/JacobStephens2/patchyard/issues/274)
provisioning pattern does not transfer even if we wanted it.

Anthropic is **better on the assertion, worse on the credential.**

## 1. Does the exchange succeed for a deleted or disabled service account?

Not documented as a deny reason — the docs never enumerate "archived service
account" in the token-exchange error table. But the question is largely moot,
because the state it describes cannot be constructed.

**a. Service accounts cannot be hard-deleted.** There is no DELETE. The only
removal is `POST /v1/organizations/service_accounts/{id}/archive`, described as
a soft delete: the object persists with `archived_at` set, and
`include_archived=true` lists it. Nothing can vanish from the roster the way
`user-6tzs2hdFVN7GoYQbWfC0eu7k` did.

**b. Archival is interlocked against live rules.** From the reference:

> Rejected with 400 if any live (non-archived) federation rule still targets
> this service account, same as issuer archival; archive those rules first or
> change their target to another service account.

So to archive `svac_01BqCdjSqFsWTvfDyCucThZy` the caller must first archive
`fdrl_000000000000000000000000` — and an archived rule is one of the *documented*
401 rows in the exchange error table ("The `federation_rule_id` does not exist,
is archived, or the JWT is not authorized for it"). The OpenAI state — mapping
alive, identity dead, exchange 200 — is refused by construction.

**c. The service account's live state is checked at exchange time.** Three
separate statements establish this, none of which has an OpenAI analogue:

- The exchange body **names the service account**: `service_account_id`
  (`svac_...`) is a required field of `POST /v1/oauth/token`. OpenAI's exchange
  resolves the mapping and never names the identity.
- "At exchange time, Anthropic checks that the federation rule's workspace
  matches one of the service account's workspace memberships." And an archived
  service account has none: the memberships endpoint says "Memberships are
  returned only while the service account is active; an archived service
  account returns an empty list." An archived target therefore cannot satisfy
  the workspace check.
- The reference states the account's *mutable* state is enforced at exchange
  too: "A rule granting `org:admin` whose target is later demoted to
  `developer` is rejected at token exchange."

**Residual risk, stated plainly.** All three arguments describe the documented
API. What removed the OpenAI account was *not* a documented API mutation — it
left no audit event at all
([#267](https://github.com/JacobStephens2/patchyard/issues/267)
reached the audit log at 200 and got zero events even unbounded). A Console or
provider-side path that bypasses the archival interlock would not be visible in
these docs. That risk is unquantifiable from documentation and is **not** worth
buying down with a detector, for the reasons in §3.

## 2. Is there an Administration API surface that lists service accounts?

**Yes — three of them, and better than OpenAI's.** The factory already calls the
first: `tools/anthropic-wif-admin.py:163` issues
`GET /v1/organizations/service_accounts?limit=100&include_archived=false`.

| Call | Discriminates |
| --- | --- |
| `GET /v1/organizations/service_accounts` (`include_archived`, `limit`, `page`) | Presence in the org roster |
| `GET /v1/organizations/service_accounts/{id}` | Returns `archived_at`, `archived_by_actor_id`, `organization_role` |
| `GET /v1/organizations/service_accounts/{id}/workspaces` | Membership in `wrkspc_000000000000000000000000`, and its `workspace_role` |

This is strictly richer than OpenAI, where the per-project `service_accounts`
listing is the *only* call that discriminates and
`GET /v1/organization/users/{id}` 404s even for healthy accounts. Anthropic's
per-id GET works, returns a first-class archived flag, and names the actor that
archived it — the attribution OpenAI's empty audit log could not provide.

**The assertion is not the problem here. The credential is.**

## 3. The credential: the #274 pattern does not transfer

[#274](https://github.com/JacobStephens2/patchyard/issues/274)
provisions a *Restricted, read-only* OpenAI Administration key, proven read-only
by a negative control, and installs it at
`/etc/patchyard/openai-admin-readonly.key`. Anthropic has no equivalent to
provision. Two documented facts close the door:

**Admin API keys are refused outright on these endpoints — reads included.**

> Admin API keys are not accepted on these endpoints, for reads or writes; use
> an `org:admin` OAuth token.

The overview repeats it: "Service accounts, federation issuers, and federation
rules (these endpoints require an `org:admin` OAuth token; Admin API keys are
not accepted)." This is why `tools/anthropic-wif-admin.py` shells out to
`ant auth print-credentials --profile ... --access-token` rather than reading a
key file.

**`org:admin` has no read-only or narrower variant.**

> Finer-grained scopes (per resource, or read versus write) are not currently
> available.

`org:admin` is "Full access to the Admin API (organization members, invites,
workspaces, API keys, and the rest)", and "grants access to the whole
organization: any workspace binding is ignored."

That leaves exactly two ways to give an unattended host the one read we want,
and both are worse than the thing #274 rejected:

1. **A `org:admin` federation rule** (the documented "Workload (CI and
   automation)" path): a Console-created rule with `oauth_scope: org:admin`
   targeting a service account whose `organization_role` is `admin`. The
   control plane could then mint full Admin API tokens *keylessly, on demand,
   indefinitely*. #274 declined to put an All-permissions OpenAI key on the
   host because it would put every A132 two-party mutation one host compromise
   away. This is that, minus the need to steal a file.
2. **An interactive `ant auth login --profile admin --scope org:admin`
   credential resident on the host**: a refresh token at
   `<config_dir>/credentials/<profile>.json`, mode 0600, acting as an admin
   *user*. Same blast radius, plus interactive re-login when it lapses.

Both fail the test #274 set. There is no third option.

## Recommendation

**Do not build an Anthropic liveness detector.** The blind spot is closed by
construction (§1), and the only credentials that could power a detector are
strictly more dangerous than the risk they would retire (§3).

If daily assurance is ever wanted, the right design is **not** an admin
listing — it is the requirement-1 shape, run as a probe:

- exchange the control plane's own five-minute RS256 assertion, then
- `GET /v1/models?limit=1` under the minted bearer.

That is genuinely credential-free (it uses the root-only signing key the control
plane already owns), needs no admin credential of any kind, generates no tokens
and no spend, and — unlike the OpenAI exchange — **is** evidence of liveness,
because the exchange validates the named service account and its workspace
membership before minting. This is the mechanism `#214`'s kid assertion has and
`#269` could not have on OpenAI. It is post-destination hygiene, not route work.

One further signal Anthropic has and OpenAI lacks: the Console's [WIF
authentication history](https://platform.claude.com/settings/workload-identity-federation?tab=history)
records every exchange attempt with the deny reason that the opaque 401 refuses
to disclose. Where OpenAI's audit log returned zero events unbounded, this is a
real trail. It is Console-only, so it is a diagnostic surface, not an assertion
surface.

## Doc-reliability note

Unlike OpenAI — four recorded self-contradictions — nothing contradictory
surfaced here. The overview page, the WIF admin guide, the reference and the
generated API reference agree on the credential rule, the archival interlock and
the scope table, and the `svac_` id form matches
`policy/anthropic-wif.json`. Two gaps rather than contradictions: the exchange
error table never names an archived *service account* as a deny reason (only an
archived rule), and the exchange-time workspace-membership check is stated in
the concepts page but absent from the error table.
