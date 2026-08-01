# A117 bounded structural redesign

## Scope

Jacob authorized one bounded structural redesign after the A116 source
re-review escalation. A117 changes no A115 live semantics or budget. It does
not authorize a worker replacement, cap change, provider request, requirement
3 work, behavioral acceptance, or a qualification-flag change.

The redesign addresses the five conceded A116 findings as one boundary change:

- the general-purpose parity guest no longer receives the requirement-2 bearer
  or an Anthropic provider allowlist;
- the worker host runs the fixed Messages transfer in a dedicated network
  namespace that admits one conntrack ID and rejects later connections;
- the launcher independently reads the namespace counters and sets before it
  accepts `request_attempts: 1`;
- the exact installed one-shot client joins the spend host-contract digest;
- missing request IDs retain the completed call's HTTP status and bounded body
  shape in the response-stage diagnostic.

Requirement 1 remains on its existing read-only guest credential-drive path.
The spend-only client is not installed in the guest image, and its digest does
not enter the requirement-1 host contract.

## One-request construction

The namespace holds three dynamic sets: the source that has consumed the
allowance, the admitted conntrack ID, and any rejected conntrack ID. The first
new IPv4 connection to the one resolved Anthropic address on TCP 443 atomically
adds its source and conntrack ID. Packets belonging to that admitted ID remain
allowed, including a retransmitted packet. A later connection has a different
ID, is added to the rejected set, and is rejected.

The client supplies one literal Messages URL, uses HTTP/1.0 with
`Connection: close`, disables ambient curl configuration with `-q`, starts from
an empty environment, permits only HTTPS, and has no retry, redirect, parallel,
or next-transfer option. The combination means the sole admitted TLS
connection carries the sole fixed curl transfer. The launcher requires one
admitted ID, one admitted-new packet, zero rejected IDs, zero rejected packets,
and one used source. It deletes and independently reads back the provider
namespace, veth, nftables table, and hosts projection before guest boot.

The spend guest gets three credential-free JSON inputs: issuance metadata, the
sanitized provider observation, and the host transport receipt. The launcher
compares all three objects byte-semantically with the guest result. It also
requires an empty guest provider allowlist and zero rejected guest-egress
packets before publishing.

## Local structural experiment

The build seat executed the exact dynamic-set rule form against local-only
network namespaces and a local HTTP server. No provider, web, worker, or
Factory infrastructure request occurred.

```text
first=pass second=fail admitted_connections=1 rejected_connections=1
```

The experiment also exercised the JSON readers used by the launcher. The first
connection produced one admitted conntrack element. The second connection was
refused and produced one rejected conntrack element. All temporary namespaces,
veth devices, rules, and server processes were removed by the experiment trap.

## Test and mutation binding

The focused suite executes the response classifiers against empty, malformed,
multi-document, and bounded-extra bodies. It executes three missing-request-ID
paths - HTTP 403 with HTML, HTTP 400 with an empty body, and HTTP 200 with a
valid JSON object - and requires status plus shape in every failure.

The same suite copies a minimal repository projection, mutates one source at a
time, and runs the real spend checker. It requires failure after each of these
weakening mutations:

1. replace HTTP/1.0 with HTTP/2;
2. add a second Messages URL to the one-shot client;
3. weaken the admitted-new equality from one to at least one; and
4. add an Anthropic Messages call back to the guest.

A78 source re-review remains required before any clean-worker replacement plan
or live A115 phase.
