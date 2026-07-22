# Session 5 worker adversarial qualification

## Contract

[`hostile-test-manifest.json`](../worker/qualification/hostile-test-manifest.json)
is the sole enumerated test list. Its 24 automated entries exercise sensitive
environment names and a random privileged canary, SSH and 1Password paths,
host sockets, metadata, private IPv4 and IPv6 destinations, DNS exfiltration,
read-only input and host-filesystem boundaries, the result-filesystem parser,
alternate output, and teardown residue.

The production launcher has one explicit `adversarial-qualification` mode. The
control-plane runner creates a random canary, passes only its SHA-256 in the
read-only guest manifest, and streams the canary itself to a root wrapper on the
secret-free worker. The wrapper keeps it in a root-only tmpfs file and launcher
environment. Firecracker starts with an empty environment, so the guest can
prove that it sees neither representation. The guest deliberately writes the
hash to its serial console; the launcher never echoes guest console content,
and the control plane rejects the run if either the canary or its hash reaches
stdout, stderr, or an accepted artifact.

The guest executor covers the runtime boundary. A second worker-host executor
feeds the production non-root `e2fsck`/`debugfs` extractor exact, extra,
missing, symlink, corrupt, oversized-image, and oversized-file cases. Finally,
the control plane deletes the transferred request and asserts zero processes,
TAPs, nftables tables, console files, request directories, canary files, or
boundary taint before it combines the three executors. Publication permits only
`change.patch`, `rationale.txt`, and `evidence.json`.

This qualifies the secret-free worker boundary with a synthetic canary. It does
not qualify provider-native credential issuance, revocation, or spend controls,
so every provider remains `credential_qualified: false` and the launcher still
rejects an ordinary credentialed run.

## Regression fixture

The committed result is
[`session-5-hostile-qualification.json`](../research/isolation/results/session-5-hostile-qualification.json).
`tools/check-worker-qualification.py` binds it to the exact manifest hash,
requires the complete sorted ID set and `PASS` for every entry, and asserts the
zero-export and zero-residue summary. Infrastructure CI runs that check after
the live result is committed.

## Live procedure

Converge and qualify the exact committed desired state twice, then run the
hostile suite from the control-plane identity:

```bash
infra/ansible/converge.sh
infra/ansible/converge.sh
infra/ansible/qualify.sh
sudo -u factory-manager /usr/local/sbin/patchyard-run-hostile-qualification \
  /var/lib/patchyard/snapshots/current \
  /var/lib/patchyard/artifacts/session-5-hostile-qualification
```

Copy only the sanitized `evidence.json` into the regression-fixture path and
run `tools/check-infra.sh`. Session 5 is a hard checkpoint: after the draft PR
is reviewable, work stops for Jacob's approval before Session 6.
