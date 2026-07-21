# Session 3 isolation decision

## Decision

Select **Firecracker 1.15.1** for the phase-1 worker runtime. Keep hardened
rootless Podman 5.8.2 as the pre-qualified fallback and graduation path.

Both candidates passed the predeclared containment contract on the actual
worker. Firecracker booted through `/dev/kvm` as the unprivileged
`factory-worker` host identity, kept guest root behind a kernel boundary, and
was 3.666 seconds slower than Podman at median startup. That difference is
below the manifest's five-second material-cost threshold. No other material
cost trigger fired, so A91's tie-break selects the stronger kernel boundary.

This is the A97 hard checkpoint. Session 4 implementation does not begin until
Jacob accepts the decision through the normal review/merge gate.

## Predeclaration and time-box

- Manifest commit:
  `408eeb2c822a2f474fe19ed72612013af9a1511b`
- Remote probe start: `2026-07-21T20:59:17Z`
- Remote probe stop: `2026-07-21T21:15:19Z`
- Elapsed: 16 minutes 2 seconds of the predeclared two-hour ceiling
- Worker: Rocky Linux 9.8, kernel `5.14.0-687.10.1.el9_8.0.1.x86_64`
- KVM: `/dev/kvm` character device present; a Firecracker VM successfully used
  it while the VMM ran as host UID 991 (`factory-worker`)

The manifest is
[`research/isolation/2026-07-21-session-3-probe-manifest.md`](../research/isolation/2026-07-21-session-3-probe-manifest.md).
No worker probe preceded that commit.

## Results against the fixed criteria

| Probe | Firecracker | Rootless Podman | Evidence |
| --- | --- | --- | --- |
| P0 KVM eligibility | PASS | N/A | KVM device present; Firecracker 1.15.1 booted an Ubuntu 24.04 guest as `factory-worker` |
| P1 request read-only | PASS | PASS | Five mutation forms denied; request SHA-256 stayed `50df41f...94a6a3e` |
| P2 worktree read-write | PASS | PASS | Read/create/edit/rename/delete passed; expected `result.txt` returned |
| P3 host-write boundary | PASS | PASS | Host paths/devices absent; sentinel and host-firewall hashes unchanged. Guest-local mount/mknod succeeded only inside Firecracker's kernel boundary |
| P4 one allowed endpoint | PASS | PASS | `api.openai.com:443` returned HTTP 401 without a credential; allow counters advanced |
| P5 forbidden IPv4 | PASS | PASS | `1.1.1.1:443` denied; IPv4 reject counters advanced |
| P6 forbidden IPv6 | PASS | PASS | IPv6 disabled/denied; forbidden target unreachable |
| P7 DNS egress | PASS | PASS | `example.net` unresolved; direct UDP and TCP DNS denied |
| P8 private/metadata | PASS | PASS | Representative VPC, CGNAT, link-local metadata, and ULA targets denied |
| P9 credential absence | PASS | PASS | Launcher canary, credential variables, known paths, KVM device, and host sockets absent |
| P10 forced teardown | PASS | PASS | First lifecycle killed forcibly; zero processes, taps, policies, cgroups/containers, control rules, or run dirs remained |
| P11 five lifecycles | PASS | PASS | All five cycles cleaned up; timings below |

### Lifecycle timing

| Candidate | Startup median | Teardown median | Five startup samples | Five teardown samples |
| --- | ---: | ---: | --- | --- |
| Firecracker | 3,973 ms | 403 ms | 3973, 4090, 3868, 4117, 3931 | 130, 403, 487, 320, 421 |
| Rootless Podman | 307 ms | 381 ms | 307, 354, 299, 334, 280 | 353, 422, 447, 371, 381 |

Firecracker's boot-to-SSH measurement includes a full systemd guest boot, not a
snapshot restore. Session 4 may optimize it, but this decision does not depend
on that work.

## Selection-rule calculation

| Predeclared material-cost trigger | Observed? |
| --- | --- |
| Mandatory probe still failing after one corrective attempt | No - P0-P10 all passed |
| Privileged state leaked in any forced/normal cleanup cycle | No - 5/5 clean |
| Untrusted process needs host root | No - VMM ran as `factory-worker`; only the bounded launcher owned tap/nft setup |
| Locally hand-built or unpinned production kernel/rootfs required | No - the spike used exact Firecracker CI inputs and recorded their hashes; Session 4 owns the reproducible image recipe |
| Startup or teardown median at least five seconds slower than Podman | No - startup delta 3.666 s; teardown delta 0.022 s |

The root-owned launcher is necessary for tap creation, forwarding, and nftables
policy. That launcher is deterministic infrastructure, not an untrusted worker
process. Firecracker itself opened KVM and ran as `factory-worker` with its
default seccomp filter. Rootless Podman also needed root-owned nftables policy;
rootless networking alone did not implement the A61 allowlist.

## Credential plumbing across the physical split

The orchestration VM is absent from the runtime path. The intended Session 4
shape is:

1. The factory supervisor on the control-plane VM selects one A61 provider,
   resolves only its declared API endpoint, fixes the model and spend ceiling,
   and mints a provider-native short-lived credential. A provider without a
   revocable, run-scoped capability fails closed; a standing provider key is
   never copied as a fallback.
2. The supervisor streams the exact-SHA source bundle, read-only request input,
   signed run manifest, and credential envelope over a factory-owned management
   channel to a root-owned worker launcher. The worker has no client key that
   can reach another fleet host.
3. The launcher validates the manifest, installs the endpoint's boot-time A/AAAA
   mapping, and creates the request, worktree, and credential drives. The
   credential drive is backed only by `/run/patchyard-worker` tmpfs, is
   read-only in the guest, and never appears in the Firecracker config, kernel
   command line, VMM environment, image, journal, or probe output.
4. Guest init copies the capability into guest tmpfs for the one model process,
   unmounts the credential drive, and starts with a whitelisted environment.
   Host nftables permits the tap to reach only the boot's resolved provider
   addresses on TCP 443. Runtime DNS, all other IPv4, all IPv6 not explicitly
   required for that provider, metadata, and private ranges are rejected.
5. The model harness enforces the run budget in addition to the provider-side
   scope. The only returned mount is the bounded worktree/result contract.
6. Teardown kills the VMM even after a guest halt, deletes tap/nftables state and
   every tmpfs drive, and asks the control plane to revoke the capability. The
   run closes only after revocation/expiry evidence and the no-residue probe.

The launcher must use an empty environment for Firecracker. The canary probe
proved that a value present in the management shell did not appear in the VMM
or guest.

## Operational observations for Session 4

- The current worker's host-level RFC1918 rejection also blocks the host's
  control traffic to a Firecracker tap. The launcher needs an exact guest-IP
  exception for the run and must remove it at teardown.
- `net.ipv4.ip_forward` was disabled at rest. The launcher enabled it only while
  a microVM ran and restored it afterward.
- A guest `poweroff` did not terminate the Firecracker VMM. Normal and forced
  teardown must explicitly terminate and reap the VMM before deleting images.
- The official CI guest filesystem is a useful probe input, not the production
  image recipe. Session 4 must checksum-pin every input, build the image from
  versioned desired state, and keep package resolution reproducible.
- Rootless Podman's probe image started faster and passed the same network/mount
  contract. It remains a tested fallback if KVM disappears or Firecracker's
  operational burden materially changes.

## Escalation: control-plane-to-worker management identity

Resolved by A101 and implemented in Session 4: a control-plane-owned
`factory-manager` identity manages both factory hosts over the private VPC;
orchestration's `conductor` authorization remains bootstrap/break-glass only.

A68 forbids any factory runtime dependency on the orchestration VM. At the
Session 3 checkpoint, desired state permitted worker SSH only from the
orchestration public IP and installed only the orchestration management key.
That was sufficient for the bootstrap spike but could not carry the runtime
credential flow described above.

Session 4 therefore needs Jacob's disposition before its implementation thread:
authorize a distinct factory control-plane management identity and private-VPC
control-plane-to-worker path, retaining orchestration access as bootstrap or
break-glass only, or rule a different A68-compliant transport. No firewall or
identity change is included in Session 3.

## Raw evidence

- [`host-and-cleanup.log`](../research/isolation/results/host-and-cleanup.log)
- [`firecracker.log`](../research/isolation/results/firecracker.log)
- [`podman.log`](../research/isolation/results/podman.log)
- [`candidate-probe.sh`](../research/isolation/harness/candidate-probe.sh)
- [`firecracker-lifecycle.sh`](../research/isolation/harness/firecracker-lifecycle.sh)
- [`Containerfile.podman`](../research/isolation/harness/Containerfile.podman)

The worker was restored after the spike: all temporary packages, images,
subordinate-ID mappings, linger state, nftables rules, tap devices, and probe
directories were removed; the firewall hash returned to its starting value;
and `qualify-factory-worker` passed.
