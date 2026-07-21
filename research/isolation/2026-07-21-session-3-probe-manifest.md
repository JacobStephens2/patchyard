# Session 3 isolation probe manifest

Status: predeclared before the first remote worker probe

This manifest fixes the comparison and selection rules for PLAN Session 3. The
criteria may not be weakened after probing starts. A probe that cannot be run
inside the time-box is `BLOCKED`, not silently omitted or converted into a
documentation claim.

## Time-box and candidates

Hands-on remote evaluation is capped at two wall-clock hours from the first
worker command. The result record must contain the UTC start and stop times.
The rest of the session is reserved for recording the decision, checking the
repo, and opening the review PR.

The candidates are:

1. Firecracker using `/dev/kvm`, a disposable root filesystem, and separate
   read-only request and read-write worktree block devices.
2. Rootless Podman as `factory-worker`, with a disposable container,
   read-only request bind mount, and read-write worktree bind mount.

Candidate setup may fetch checksum- or digest-pinned public artifacts before
the untrusted runtime starts. No real Patchyard, provider, vault, GitHub, database,
or cloud credential may enter either candidate.

## Fixed probe fixture

- Selected provider endpoint: `api.openai.com:443` (OpenAI is on the A61
  roster). The host resolves the endpoint before boot and injects only the
  resulting address mapping. Runtime DNS is not required for the allowed path.
- Forbidden public IPv4 target: `1.1.1.1:443`.
- Forbidden public IPv6 target: `[2606:4700:4700::1111]:443`.
- Forbidden DNS name: `example.net`.
- Forbidden direct resolvers: `1.1.1.1:53` over UDP and TCP.
- Request fixture: `/input/request.md`, containing a known SHA-256 marker.
- Worktree fixture: `/work`, initially containing a known SHA-256 marker.
- Host sentinel: a root-owned file outside all runtime mounts.
- Credential canary: a synthetic value present in the privileged launcher
  environment and in a root-only host file. It is not a real secret.

The allowed endpoint passes when a TLS/HTTP response is received; an expected
unauthenticated response is sufficient. A connection to any forbidden target,
successful resolution of the forbidden name, or observation of the canary is
a failure.

## Mandatory probes

Each candidate receives `PASS`, `FAIL`, or `BLOCKED` for every row, plus the
exact command/result in the raw log.

| ID | Property | Must-pass observation |
| --- | --- | --- |
| P0 | Host eligibility | Firecracker only: `/dev/kvm` is a character device and a minimal VM can use it as the unprivileged runtime identity or through a narrow root-owned launcher. |
| P1 | Request mount | Marker reads correctly; create, append, rename, chmod, and delete attempts fail; the host hash is unchanged. |
| P2 | Worktree mount | Marker reads correctly; create, edit, rename, and delete succeed; the returned host tree contains exactly the expected final fixture. |
| P3 | Host write boundary | The host sentinel is not visible or mutable; attempts through `/host`, `/proc/1/root`, device creation, mounting, and host firewall mutation fail; the sentinel hash and host firewall hash are unchanged. |
| P4 | Selected endpoint | `api.openai.com:443` produces a TLS/HTTP response using only the boot-time address mapping. |
| P5 | IPv4 denial | `1.1.1.1:443` cannot be reached. |
| P6 | IPv6 denial | The forbidden IPv6 target cannot be reached; an entirely disabled IPv6 stack passes. |
| P7 | DNS denial | `example.net` cannot resolve, and direct UDP or TCP DNS to `1.1.1.1:53` cannot exchange a response. |
| P8 | Private/metadata denial | DigitalOcean metadata and representative loopback, RFC1918, carrier-grade NAT, link-local, and IPv6 ULA destinations cannot be reached outside the runtime itself. |
| P9 | Credential absence | The synthetic launcher canary and standard Patchyard/provider credential variables and paths are absent. |
| P10 | Forced teardown | After `SIGKILL`/forced stop, no runtime process, mount, tap/network namespace, cgroup, credential canary, or candidate run directory remains. Cleanup is idempotent. |
| P11 | Lifecycle overhead | Five clean start/stop cycles complete; raw durations and median startup and teardown time are recorded. |

The firewall and credential hashes are observations only; raw secret values or
environment dumps are forbidden in logs.

## Selection rule

A candidate is selectable only if every applicable P0-P10 probe passes and all
five P11 cycles clean up. Firecracker is selected when KVM is present and it is
not materially harder to operate than hardened rootless Podman. A close result
therefore selects Firecracker.

For this spike, Firecracker is *materially harder* only if at least one of these
predeclared conditions is observed:

- it cannot pass a mandatory probe within the time-box after one documented
  corrective attempt;
- forced cleanup leaks privileged host state in any of the five cycles;
- its production shape requires an untrusted process to hold host root, rather
  than a bounded root-owned launcher configuring KVM, tap devices, and policy;
- its reproducible artifact path requires a locally hand-built or unpinned
  guest kernel/root filesystem, rather than pinned and verifiable inputs; or
- median startup or teardown is at least five seconds slower than Podman.

Rootless Podman is selected only if KVM is absent or one of those material-cost
conditions occurs and Podman passes its own mandatory probes. The losing
candidate remains the documented escalation/graduation path; Session 3 does
not build the production runtime.

## Result evidence contract

The committed decision must include:

- the unchanged manifest commit SHA;
- UTC start/stop timestamps and the time-box outcome;
- host facts needed to interpret the result, without unique credentials;
- a candidate-by-candidate P0-P11 result table;
- sanitized raw logs and hashes for every fixture/artifact used;
- the selected runtime and the selection-rule calculation; and
- the credential plumbing shape across the physical control-plane/worker split,
  including minting, transfer, in-memory lifetime, egress binding, teardown,
  and proof that reusable authority does not remain on the worker.
