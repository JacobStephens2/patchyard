# Session 4 worker runtime

## Installed shape

The control plane owns the `factory-manager` private key and reaches both
factory hosts only over their private VPC addresses. Orchestration's
`conductor` identity remains authorized from `142.93.121.94/32` for initial
provisioning and break-glass use, but it is not part of source transfer,
worker execution, or result collection. The live A101 qualification temporarily
rejects orchestration at the worker while the control plane re-qualifies that
same worker.

Each attempt gets a new Firecracker 1.15.1 microVM under `jailer`, with the VMM
running as the unprivileged `factory-worker` host identity. The root-owned
launcher supplies five bounded surfaces:

| Surface | Guest mode | Contract |
| --- | --- | --- |
| root filesystem | read-write copy | Reproducibly built parity image; discarded |
| request and run inputs | read-only | Manifest, request, provider mappings, snapshot |
| exact-base source | read-write | Credential-free archive whose SHA-256 and Git base SHA are checked |
| result | read-write | Internal status plus patch, rationale, and bounded JSON evidence |
| capability, when required | read-only | Host-tmpfs-backed block device, copied to guest tmpfs and unmounted before model execution output |

The Firecracker process starts with the jailer's cleared environment. The
launcher resolves only the selected provider before boot, writes the fixed
mapping into the read-only input, and permits the tap to those addresses on TCP
443 only. Runtime DNS, all other IPv4, IPv6, private networks, metadata, and
guest-to-host traffic are rejected. A `provider: none` fixture gets no egress.
Every A61 provider is represented in
[`provider-egress.json`](../policy/provider-egress.json), but all remain
credential-ineligible until Session 5 proves issuance, delivery, expiry,
revocation, crash cleanup, and provider-side spend enforcement. The launcher
will not treat a standing key as a fallback.

Successful intake accepts exactly three files: a patch of at most 1 MiB, a
rationale of at most 64 KiB, and evidence of at most 128 KiB. It validates the
run/base identity, patch hash, zero Git remotes, capability removal, and
`git apply --check` before moving those files into the caller's output
directory. The host bounds the result image at 16 MiB and extracts the fixed
result names with version-pinned `debugfs` as the unprivileged worker identity;
it never mounts the guest-written filesystem into the host kernel or parses it
as root. The microVM, jail,
tap, nftables table, temporary drives, logs, and credential material are
removed first.

## Production parity

[`production-parity.json`](../worker/image/production-parity.json) records the
production observation and source-config hashes. The desired state pins Rocky
Linux 9.8, PHP 8.4.21 and its production extension RPM set, Apache 2.4.62, and
MySQL Community 8.4.8. The HTTP-only guest configuration preserves the
production Fieldbook document root, directory rules, PHP-FPM Unix-socket path,
authorization forwarding, index order, and TRACE/TRACK rejection. Production
TLS certificates and production-only terminal proxies are intentionally not
copied into a no-inbound-network microVM.

The guest creates a fresh local MySQL data directory on every boot, imports the
selected snapshot, starts PHP-FPM and Apache, and exercises Fieldbook through
HTTP. No worker or guest route reaches a real database or Fieldbook host.

## Snapshot operations

Patchyard's IT Manager owns the snapshot contract in
[`snapshot-policy.json`](../policy/snapshot-policy.json). Refresh is required
after every applied Fieldbook migration and every manager-sandbox redaction
lineage change. The bootstrap operation exports **schema only** from the
already-scrubbed `fieldbook_training` database; no source row, trigger, database
credential, or network access reaches the control plane or worker. The control
plane combines that schema with the versioned synthetic seed and records:

- snapshot date and version;
- source-schema and artifact SHA-256 values;
- manager-fieldbooks revision and both redaction-script hashes;
- snapshot-policy hash and the zero-source-row data shape.

Publication is atomic. A failed build leaves `current` on the last valid
artifact. The artifact is visibly stale after 7 days and ineligible for new
runs after 30 days. Node exporter publishes age, stale, and eligibility gauges;
fleet alerting is an external handoff. Every Fieldbook PR must record the snapshot
version and date used for parity verification.

The initial provisioning command is:

```bash
infra/ansible/bootstrap-parity-snapshot.sh
infra/ansible/bootstrap-fieldbook-source.sh
```

That command is a bootstrap input producer, not a factory runtime dependency:
it sends only a schema-only file to the control plane, where the committed
builder creates and owns the artifact. Existing valid runs, snapshot selection,
bundle transfer, and worker execution remain independent of orchestration.

## Worker lifetime and boundary failure

[`worker-lifecycle.json`](../policy/worker-lifecycle.json) resolves the worker
lifetime contract. A microVM lasts for one attempt and at most 300 seconds. The
otherwise-empty worker droplet is replaced at 30 days, or immediately after a
containment-qualification failure or incomplete teardown. The launcher records
`/var/lib/patchyard-worker/BOUNDARY_TAINTED` when boundary cleanup is
ambiguous; that marker makes every later run and qualification fail closed and
Ansible deliberately does not remove it.

Replacement uses the existing human-reviewed OpenTofu plan and restores no
worker state. Readmission requires two converges (`changed=0` on the second),
host qualification, the production Firecracker isolation probe, and a second
no-residue qualification. Orchestration remains the sole cloud writer; this is
planned maintenance/bootstrap authority, not part of an ordinary factory run.

## Session 4 live evidence procedure

After the exact DigitalOcean firewall plan is approved and applied:

```bash
infra/ansible/converge.sh
infra/ansible/converge.sh
infra/ansible/bootstrap-parity-snapshot.sh
infra/ansible/qualify.sh
```

From the control plane as `factory-manager`, run the production-runtime
isolation replay, then the inter-host Fieldbook fixture:

```bash
/usr/local/sbin/patchyard-run-isolation-probe \
  /var/lib/patchyard/snapshots/current /var/lib/patchyard/artifacts/session-4-isolation
/usr/local/sbin/patchyard-run-fixture \
  /var/lib/patchyard/bootstrap-sources/fieldbook-current <exact-fieldbook-sha> \
  /opt/patchyard/worker/runtime/session-4-request.md \
  /var/lib/patchyard/snapshots/current /var/lib/patchyard/artifacts/session-4-fixture
```

The committed evidence is the immutable desired state and bounded fixture
definition. Live result hashes, version assertions, teardown counts, and the
A101 independence transcript belong in the Session 4 PR checklist; no runtime
artifact or transcript containing request content enters Git.
