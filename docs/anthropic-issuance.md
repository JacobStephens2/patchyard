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
places that JSON on a Firecracker read-only drive. The guest proves the drive
rejects a write, copies the capability to guest tmpfs, unmounts the drive, and
uses a mode-0400 curl config owned by the unprivileged `factory-agent` identity
inside its mode-0700 runtime directory, so only the calling identity can read
the bearer and the bearer does not enter a process argument.
It then performs `GET /v1/models?limit=1`, an inference-scope provider call
that does not generate tokens, and deletes the credential before writing any
result.

The committed fixture records provider request IDs, issuance and expiry times,
the exact object IDs and scope, read-only delivery and unmounting, credential
removal, and host teardown. It rejects any credential or assertion in accepted
stdout, stderr, or evidence. The live private signing identity is deliberately
absent from restore drills and from the worker.

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

## Control-plane replacement and key rotation

The signing key is deliberately absent from backups. A replacement control
plane therefore generates a new key whose public JWK does not match the
existing Anthropic issuer until the provider binding is updated. Treat that as
a planned rotation, not as a healthy host followed by an unexplained exchange
failure:

1. Keep acceptance paused and do not run the issuance fixture with the new key.
2. Read the new public JWK with
   `/usr/local/sbin/patchyard-run-anthropic-issuance jwks`.
3. Run `tools/anthropic-wif-admin.py` without `--apply`, review its exact issuer
   update, and obtain any required operator approval before applying it.
4. Apply the reviewed provider update, prove one positive exchange and Models
   call with the new key, then prove an assertion signed by the retired key is
   rejected before declaring rotation complete.

The host qualifier proves key ownership, mode, and public-JWK derivation. It
cannot prove that Anthropic currently trusts that JWK; only the provider
exchange supplies that proof.
