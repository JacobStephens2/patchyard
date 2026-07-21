# Session 3 isolation threat-model input

This is a pre-spike input, not a Firecracker-versus-Podman decision. Session 3
must evaluate both candidates under PLAN's predeclared probes and A91 time-box.

## Session 0 residual risk: host-owned egress guardrail

The Session 0 worker host rejects RFC1918, carrier-grade NAT, link-local, and
IPv6 unique-local destinations in a host nftables output chain. That prevents
ordinary worker processes from reaching Patchyard private networks and metadata, but
it is mutable by host root and defaults to allowing other public destinations.
It is therefore defense in depth for the unprivileged host account, not A61's
single-provider-per-boot isolation boundary.

Session 3 must treat worker-to-host privilege escalation as a boundary failure,
not as an event the nftables rule can contain. The selected runtime must prove:

- untrusted implement/verifier processes cannot alter host nftables or acquire
  host root;
- each boot can reach only its selected A61 provider endpoint, including IPv4,
  IPv6, and DNS behavior;
- metadata and all private ranges remain unreachable from inside the runtime;
- teardown removes the per-boot egress policy and leaves no reusable authority;
- any failed containment probe destroys the disposable worker and requires a
  clean desired-state rebuild plus qualification before reuse.

Cloud firewalls are not a substitute: DigitalOcean's allowlist model cannot
express a private-destination deny while retaining arbitrary public package
access. At the Session 0 pre-apply check, no live DigitalOcean firewall targeted
the existing `production` tag, so attaching that tag introduced no inherited
firewall-rule union. Re-run that read-only check before later applies and during
drift review.
