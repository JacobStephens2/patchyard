# A78 adversarial source review - A101 firewall readiness

## Verdict

**NOT A PASS** - one high blocking finding, one medium test-strength finding,
and one low credential-exposure finding.

Reviewed commit:
`097a5b4acdf68fb27b173445f0df0ff6fb3b7e74`. A78 used Claude Code 2.1.220
with Opus 5 at `xhigh` effort in a fresh detached worktree. The worktree
remained byte-clean at the reviewed revision.

## F1 - empty provider bodies pass readiness

Severity: **high, blocking**.

`firewall_is_ready` relied only on `jq -e`'s exit status. With jq 1.6, empty
and whitespace-only input produce no value and exit zero. A successful curl
transfer with a zero-byte body therefore caused the helper to report readiness
on attempt 1 without evaluating any provider predicate.

A78 reproduced this end to end against the exact helper. The defect admits an
empty HTTP 200 or 204 response and an empty redirect response. The smallest
repair is to reject an empty or whitespace-only body and accept only jq output
that is exactly the single value `true`. An exact HTTP-status binding is useful
additional defense.

## F2 - independent weakenings evade the contract test

Severity: **medium**.

A78's independent mutations found four unbound classes:

1. an environment-controlled conditional around the readiness call;
2. weakened OpenTofu worker or firewall cardinality;
3. removal of curl's `--fail`; and
4. removal of the provider top-level object-type predicate.

The provider pending fixture also combined `status=waiting` with a nonempty
`pending_changes`, so it did not independently exercise the pending-change
predicate. The state fixtures did not cover two workers or a firewall with two
state attachments.

The smallest repair is to bind a direct fatal operator call, bind every state
cardinality and HTTP predicate, and add independent fixtures for
`status=succeeded` with pending changes, extra provider attachments, two state
workers, and two state attachments.

## F3 - DigitalOcean bearer appears in curl argv

Severity: **low**.

The helper supplied `Authorization: Bearer $DO_API_TOKEN` with curl's `-H`
argument. On this host, `/proc` does not use `hidepid`, so another process with
sufficient access could read the bearer while curl is running. No output path
printed the token, and the same pattern predates this helper in
`infra/check-do-tag-firewalls.sh`, but this helper added a new instance.

The repository already contains a safer pattern in
`patchyard-deployed-version`: validate the bearer alphabet and provide the
header through curl config on standard input.

## Verified properties

- The helper derives exactly one worker and one worker firewall from current
  OpenTofu state and polls only the state-derived firewall endpoint.
- Aside from F1, the provider ID, name, status, pending-change, worker,
  attachment-cardinality, and tag predicates are fail-closed.
- The loop has 24 attempts, two-second inter-attempt sleeps, and three-second
  connect and transfer timeouts.
- The operator currently calls readiness after both converges and before A101.
  A101 remains one-shot and terminal.
- All 13 provider `credential_qualified` values remain false.
- No bare Anthropic credential assignment was introduced.

## Nonblocking observations

A78 also noted that the firewall-ID expression accepts any 36-character
lowercase-hex-and-dash string before the provider rejects it, jq 1.6 uses the
last duplicate JSON key, only root-module state resources are scanned, firewall
rule equality is not re-read here, the older tag-firewall guard remains
plan-only, jq is not version-pinned, and the response has a time bound but no
explicit byte bound. These observations did not change the three findings or
the NOT A PASS verdict.

## Review execution

A78 ran:

- ShellCheck;
- all 6 readiness tests;
- an offline matrix of 22 provider-response shapes and 11 OpenTofu-state
  shapes;
- all 11 authored mutations plus 12 independent mutations;
- direct jq empty and whitespace exit-status experiments;
- loopback curl status experiments; and
- a bearer argv canary.

The authored suite rejected 11 of 11 mutations. Four of A78's 12 independent
mutations survived as described in F2. No worker, DigitalOcean resource,
Anthropic credential or request, Console limit, acceptance case, requirement-1
fixture, requirement-3 artifact, or qualification flag changed.
