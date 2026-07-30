# A119 bounded source repair

## Scope

Jacob authorized one additional bounded source-only repair after the A118
adjudication. A119 is limited to the conceded A118-1 and A118-2 findings. It
authorizes no clean-worker plan or mutation, provider request, credential
issuance, cap action, requirement 3 work, behavioral acceptance, or
qualification-flag change.

## Complete transport-setup binding

The A118 digest covered only the namespace nftables lines between two markers.
A119 removes those nested markers. The checker now extracts one singular
transport-control section from the `setup_provider_transport` declaration
through the complete `assert_provider_transport_preflight` closing brace and
verifies one hard-coded SHA-256.

That function includes:

- namespace IPv6 writes before link creation;
- veth creation, addressing, link-up, and default route;
- host IP forwarding;
- the host forward and postrouting chains, exact provider destination and
  port, return path, terminal rejection, and masquerade;
- namespace tables, chains, drop policies, sets, and named counters;
- loopback and established-connection handling;
- exact namespace interface, source, destination, port, and new-state admit
  rule; and
- used-source, later-new-connection, and terminal rejection.

An added rule, an early preflight bypass, or a weakening anywhere in that
section changes the verified digest.

## Exact IPv6 preflight

The checker separately requires exactly one byte-identical comparison:

```bash
if [[ "$ipv6_all" != 1 || "$ipv6_default" != 1 || "$ipv6_eth0" != 1 ]]; then
```

This keeps the independently readable intent visible in addition to the
complete setup-function digest.

## Mutation set

The real spend checker now runs against fifteen disposable source weakenings.
The five A119 additions are:

1. add the formerly green unqualified namespace rule immediately before the
   complete setup function's closing brace;
2. replace the host-forward provider destination with `0.0.0.0/0`;
3. change the host-forward terminal rejection to acceptance; and
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
