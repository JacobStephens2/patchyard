# A120 runner failure diagnostics - source work record

Date: 2026-08-02

Status: source complete; awaiting A78 review before any worker mutation or
provider request

Base: `1cdc6cc4fa30e6e4be623adc3b2c57e5ecd5dea6`

## Result

The Anthropic qualification runner now identifies unexpected shell failures,
names the first failed post-launcher evidence predicate, and retains the failed
`evidence.json` for inspection. It does not fix or infer the predicate that
failed during the paid 2026-08-02 operational acceptance.

The request body, prompt calibration, uncached-token floor, cache exclusion,
one-shot transport, provider request cardinality, A120 stop conditions,
launcher, guest image, and evidence finalizer are byte-identical to the base.

## Failure reporting

The runner enables Bash `errtrace` and installs an `ERR` trap before its first
assertion. An unexpected nonzero command now emits its status, source line, and
shell-escaped `BASH_COMMAND` as
`anthropic_qualification_runner_failed`.

The prior post-launcher `jq -e` conjunction is decomposed into 41 named checks
in the same evaluation order. Every original predicate, constant, conditional
branch, exact-object comparison, and absence check remains present with the
same strictness. The first failure emits
`anthropic_evidence_validation_failed clause=<name> jq_status=<status>`.

The existing-output precondition now emits
`anthropic_qualification_output_directory_exists path=<shell-escaped-path>`
instead of exiting silently.

## Failed-evidence preservation boundary

The runner creates no preservation path until after both existing recursive
scans have proved that neither the exact Anthropic bearer nor the exact OIDC
assertion occurs in launcher output or any result file. It then deletes both
credential needles before defining the preservation helper.

On a named evidence-validation failure, the runner copies only
`evidence.json` to:

```text
/run/patchyard-anthropic/failed/<run-id>/evidence.json
```

The existing `/run/patchyard-anthropic` parent is root:root mode 0700. The
runner explicitly installs both new directories as root:root mode 0700 and the
copy as root:root mode 0600. The copy therefore has the same credential-free
precondition as accepted evidence while remaining root-only and outside the
per-run directory deleted by the exit trap. It persists until explicitly
removed or the control plane reboots its `/run` tmpfs.

## Mutation results

Three no-network tests execute extracted or early runner logic without a
credential exchange, worker invocation, or provider request.

1. The first bare configuration assertion was replaced with
   `[[ forced-bare-assertion == pass ]]`. It exited nonzero and printed:

   ```text
   anthropic_qualification_runner_failed status=1 line=44 command=\[\[\ forced-bare-assertion\ ==\ pass\ \]\]
   ```

2. A credential-free retained requirement-1 evidence copy was first validated
   unchanged. The validation path returned zero with empty stdout and empty
   stderr. Its `provider_call.endpoint` was then changed from
   `/v1/models?limit=1` to `/v1/messages`. It exited nonzero and printed the
   following leading diagnostics, with the test-only temporary root standing
   in for the production root-only path:

   ```text
   anthropic_evidence_validation_failed clause=provider_call.endpoint jq_status=1
   anthropic_evidence_preserved path=<temporary-root>/failed/<run-id>/evidence.json
   anthropic_qualification_runner_failed status=1 line=<line> command=return\ \"\$jq_status\"
   ```

   The preserved bytes matched the failed input exactly; directory modes were
   0700 and the file mode was 0600. The test also source-binds the production
   root ownership and proves preservation occurs after both credential scans
   and needle deletion.

3. An existing temporary output directory exited 1 and printed
   `anthropic_qualification_output_directory_exists path=<path>`.

The successful runner's only final output statement remains byte-identical:

```text
anthropic_qualification_result=$OUTPUT_DIR run_id=$RUN_ID requirement=$QUALIFICATION_REQUIREMENT
```

## Required requirement-1 refresh

`worker/qualification/patchyard-run-anthropic-issuance` participates in both
host contracts: requirement 1 binds runner plus launcher, and requirement 2
binds runner plus launcher plus transport. Its reviewed source SHA-256 is now
`73a70f22b45f494606cf258a65867a5ca5ec135c8e8e10656deec6614dfa7cc7`.
The resulting two-file requirement-1 host contract is
`b8f2577ba1236039c7b1eb145c1e38b64f928771ad41aee5a56eaa4e1c1575d2`,
so the qualified fixture at
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`
is intentionally stale.

Exactly one free requirement-1 refresh is owed after this change merges and
the exact merged source converges. This source work neither performs nor
simulates that refresh; the stale live check remains red until the authorized
post-merge run records the new host contract.

## Gate results

The full repository gate set ran against the completed source:

- `tools/check-infra.sh` initialized and validated all three OpenTofu roots.
  The A101 trust root, stack, independence, worker runtime, worker
  qualification, A120 spend, and preview checks passed. The wrapper returned 1
  only because the live requirement-1 artifact still records
  `eef6e16e...d52977` instead of the intentionally new
  `b8f2577b...c1575d2` host contract.
- `tools/check-ansible.sh` ran 171 isolated tests. 170 passed; the only failure
  was `test_live_evidence_binds_current_host_contract`, asserting the same
  deliberate requirement-1 staleness. ShellCheck, all four Ansible lint
  profiles, all four playbook syntax checks, and the terminal A101 trust-root
  recheck passed.
- `tools/check-application.sh` returned zero across the constitution, preview,
  Rust format, clippy, unit/integration/property, replay,
  reproducible-release, advisory, license, vet, dependency, model, and
  byte-exact codebase-metrics gates. The one Docker-only Traefik case used its
  declared local skip; hosted PR CI supplies that service.
- Direct `bash -n` and ShellCheck passed for the changed runner. The isolated
  A120 spend checker and all 31 spend tests passed. The three new diagnostic
  mutation tests passed. The isolated requirement-1 checker remains honestly
  red only for the refresh owed above.

The two nonzero wrappers therefore expose one expected stale live fixture, not
an unrelated source or gate failure. No checker or test was weakened to hide
it.

## Negative-scope attestation

This work made no provider request, minted no credential, changed no Anthropic
Console limit, applied no infrastructure, converged no host, mutated no worker,
refreshed no fixture, performed no behavioral acceptance, and started no
requirement-3 work. It introduced no bare `ANTHROPIC_API_KEY` or long-lived
key. All 13 `credential_qualified` values remain false. The logging-harness
`PIPESTATUS` footer, `check-ansible.sh` all-pass tail, UTC-midnight
`postgres_dashboard` test, and every other queued item remain untouched.
