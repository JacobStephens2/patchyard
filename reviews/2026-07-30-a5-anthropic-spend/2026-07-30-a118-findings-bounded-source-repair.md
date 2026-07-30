# A118 findings bounded source repair

## Authorization and scope

Jacob authorized one additional bounded source-only repair after the A118
adjudication. Under the subsequent governance-hygiene direction, this
operational authorization is recorded in the requirement-2 work record rather
than minted as another numbered policy ruling. It is limited to the conceded
A118-1 and A118-2 findings.

The authorization covers no clean-worker plan or mutation, provider request,
credential issuance, cap action, requirement 3 work, behavioral acceptance, or
qualification-flag change. It adds no live attempt or further repair loop.

## Complete transport-setup binding

The A118 digest covered only the namespace nftables lines between two markers.
The repair removes those nested markers. The checker now extracts one singular
transport-control section from the `setup_provider_transport` declaration
through the complete `assert_provider_transport_preflight` closing brace and
verifies one hard-coded SHA-256.

That section includes:

- namespace IPv6 writes before link creation;
- veth creation, addressing, link-up, and default route;
- host IP forwarding;
- the host forward and postrouting chains, exact provider destination and
  port, return path, terminal rejection, and masquerade;
- namespace tables, chains, drop policies, sets, and named counters;
- loopback and established-connection handling;
- exact namespace interface, source, destination, port, and new-state admit
  rule;
- used-source, later-new-connection, and terminal rejection; and
- the complete IPv6 preflight readback and failure path.

An added rule, an early preflight bypass, or a weakening anywhere in that
section changes the verified digest.

## Exact IPv6 preflight

The checker separately requires exactly one byte-identical comparison:

```bash
if [[ "$ipv6_all" != 1 || "$ipv6_default" != 1 || "$ipv6_eth0" != 1 ]]; then
```

This keeps the independently readable intent visible in addition to the
complete transport-control digest.

## Mutation set

The real spend checker now runs against fifteen disposable source weakenings.
The five additions for this repair are:

1. add the formerly green unqualified namespace rule immediately before the
   complete setup function's closing brace;
2. replace the host-forward provider destination with `0.0.0.0/0`;
3. change the host-forward terminal rejection to acceptance;
4. replace the exact IPv6 OR comparison with the ineffective AND comparison
   reproduced during A77 adjudication; and
5. return successfully before evaluating the exact comparison.

All five fail, as do the ten A118 mutations. The focused spend suite remains 24
tests because the mutations are subcases of its real-checker behavioral test.

## Boundary

No provider or external-network action occurred. No worker, credential, cap,
acceptance, requirement-3, or qualification-flag state changed. A78 review of
the exact repaired source SHA remains the next gate before any clean-worker
replacement plan.
