# Anthropic A-5 requirement 1: issuance and delivery

## Qualified contract

The control plane owns one root-only 3072-bit RSA signing key. It creates a
five-minute RS256 assertion containing an exact issuer, subject, audience,
environment claim, and single-use JTI. Anthropic verifies that assertion using
an inline public JWKS and mints a bearer for the dedicated `Patchyard Factory`
workspace, the `patchyard-worker` service account, and only the
`workspace:inference` scope.

The assertion and private key remain on the control plane. The interactive
admin credential remains only on the orchestration operator host during
bootstrap and never enters either Factory host. Only the resulting bearer and
non-authority metadata cross to the worker, over standard input into host
tmpfs. The existing capability path
places that JSON on a Firecracker read-only drive. The guest proves the kernel
block device is read-only and that the mounted filesystem rejects a write,
copies the capability to guest tmpfs, unmounts the drive, and
uses a mode-0400 curl config owned by the unprivileged `factory-agent` identity
inside its mode-0700 runtime directory, so only the calling identity can read
the bearer and the bearer does not enter a process argument.
It then performs `GET /v1/models?limit=1`, an inference-scope provider call
that does not generate tokens, and deletes the credential before writing any
result.

The committed fixture records provider request IDs, issuance and expiry times,
the exact object IDs and scope, read-only delivery and unmounting, credential
removal, and host teardown. Five digests are enforced bindings: the checker
recomputes the deterministic request and patch, the production-parity manifest,
the complete image recipe, and the host contract. The ext4 rootfs bytes are not
reproducible because the image build creates filesystem identity and metadata;
`observed_rootfs_sha256` is therefore explicitly a runtime observation. The
worker verifies that observation against the exact rootfs bytes before launch
and again before publishing evidence, but the repository checker does not
misrepresent it as a reproducible source binding. The host-contract digest
binds the proof to the exact reviewed control-plane issuance runner and worker
Firecracker launcher;
before exchanging the assertion, the runner compares its installed bytes and
the remote launcher digest with the exact sources in the deployed
credential-free checkout. The worker address is not executable template text:
Ansible writes it to a separate root-only file, and the runner accepts exactly
one canonical RFC1918 IPv4 line from that file. The checker rejects stale
evidence after either host-side program changes. It also rejects any credential
or assertion in accepted stdout, stderr, or evidence. The live private signing
identity is deliberately absent from restore drills and from the worker.

This proves only requirement 1. It does not prove provider-side spend
enforcement, expiry denial, federation-rule revocation, or crash cleanup.
Anthropic therefore remains `credential_qualified: false`; no behavioral
acceptance case is enabled.

## Bootstrap and live procedure

The initial bootstrap has two committed desired-state converges because the
public JWKS is derived from the control-plane-only key before the provider
object IDs exist:

1. Converge the clean requirement-1 implementation to create the signing key.
2. Read `/usr/local/sbin/patchyard-run-anthropic-issuance jwks` from the
   control plane. This emits only the public JWK.
3. Run `tools/anthropic-wif-admin.py --profile patchyard-admin --jwks JWKS`
   without `--apply` and review the exact plan.
4. Add `--apply` to create or validate the dedicated service account,
   workspace membership, inline issuer, and inference-only rule. The tool
   refuses any same-name object whose reviewed fields differ.
5. Commit the returned `svac_`, `fdis_`, and `fdrl_` IDs into
   `policy/anthropic-wif.json`; converge twice and run
   `infra/ansible/qualify.sh` at that exact commit.
6. On the control plane, run:

```bash
sudo /usr/local/sbin/patchyard-run-anthropic-issuance run \
  /var/lib/patchyard/snapshots/current \
  /var/lib/patchyard/artifacts/anthropic-issuance-delivery
```

Copy only the sanitized `evidence.json` to
`research/isolation/results/anthropic-issuance-delivery.json`, then run
`tools/check-anthropic-issuance.py` and the complete repository checks. Never
copy the JWKS staging directory, assertion, exchange response, or capability
from runtime tmpfs into the repository.

## Control-plane replacement before key rotation is qualified

The signing key is deliberately absent from backups. A replacement control
plane therefore generates a new key whose public JWK does not match the
existing Anthropic issuer. Requirement 1 does not implement that rotation:
`tools/anthropic-wif-admin.py` intentionally rejects an existing issuer whose
JWKS differs and cannot plan or apply an issuer update.

The source-only provider-update, overlap, rollback, activation, and retired-key
denial path is now documented in `docs/anthropic-lifecycle.md`. It has not been
executed and does not authorize an issuer change. Until that attended procedure
passes under separate authorization, a replacement control plane with a new
key is not qualified for Anthropic issuance. Keep acceptance paused and expect
the bootstrap admin tool and token exchange to fail closed on the key mismatch.

The host qualifier proves key ownership, mode, and public-JWK derivation. It
cannot prove that Anthropic currently trusts that JWK; only the provider
exchange supplies that proof. Rotation is complete only after the lifecycle
procedure proves replacement-key exchange and Models positives, atomically
activates that key, and records a provider denial for a fresh assertion signed
by the retired key.
