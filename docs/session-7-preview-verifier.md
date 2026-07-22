# Session 7 preview and verifier evidence

Evidence captured on 2026-07-22 UTC against the live factory control plane,
secret-free worker, and shared preview fleet. The raw DOM and screenshots stay
in the private factory evidence path because the preview data is not a public
fixture. This file records bounded paths, immutable SHAs, and artifact hashes.

## Fixture refs and implement boundary

- Fieldbook base ref `factory/session-7-alphabetize-base`:
  `fddd383c32429037c89253d57153ded2c0ce5f21`. It contains the targeted test and
  the unchanged parity health probe.
- The real parity implement run was `s4-20260722-21976d04a414`. Its evidence is
  `/var/lib/patchyard/artifacts/session-7-implement/evidence.json` on the
  control plane, SHA-256
  `66458e6c079e588cfe6dee53cca086725b012f10ea715f4ee6ed3b8ceb5a1f09`.
- Implement teardown reported zero processes, TAPs, nftables tables, run
  directories, and credential files. The returned patch SHA-256 is
  `4877d9b2bfff05dd4136d6e740721bfa7a7183e48bb90f1b15a3937c99ce34b9`.
- The returned patch byte-compared equal to the candidate-branch diff. Fieldbook
  candidate ref `factory/session-7-alphabetize-candidate` is
  `75d6c1eb145b560311a02751a1badecb8f124557`.
- `caps` passed at two files and three changed lines; `deny-paths` passed. The
  normalized diff manifest SHA-256 is
  `86ede79430fd0a823c522abb9cdcecf9d907d1f5edd73568e0640dd97bd7a1b1`.

## Independent worker verification

Raw evidence is
`/var/lib/patchyard/artifacts/session-7-verifier/evidence.json`, SHA-256
`60aa1e3f83d8ac7fe32cd90457939d3134b5b60eea89a359bdb2710e47f5f62e`.

- Run: `s7-20260722-38760a684ec1`.
- Identity: `factory-worker`, UID 990, clean environment, zero Git remotes.
- The shared worker lock was held and Firecracker/jailer counts were `0/0`
  both before and after verification. The implement worker was therefore
  terminated before verify rather than merely assumed to be gone.
- PHPUnit 10.5.63, binary SHA-256
  `3160398ef3e1ac041866fab0e88bdbc46349c7420824b750d2ede9a58ead1ba8`,
  ran `tests/Unit/AlphabetizeSalespeopleTest.php` on PHP 8.4.21. Result:
  `OK (1 test, 4 assertions)`.
- Before and after tree hashes were both
  `13655cad0850ed645758f36eb3f07c2a0caea88eaad0f68c75feb58ce72c7749`.

## Live preview evidence

Both captures used the bearer-header Chromium extension and the live
`#sales_person_id` select at
`/mfieldbook/leads/assign?rqst_id=96429`. Each lease recorded owner, request ID,
expected SHA, expiry, and random lease ID. The checkout and running preview
container returned the expected `git rev-parse HEAD` before and after capture.

- Baseline evidence:
  `/var/lib/patchyard/preview/session-7-baseline-2/evidence.json`, SHA-256
  `cd2e397fc5db7d0c7bcb326a5b910e3b0a0ab341c6388ad464db8581bf520d6b`.
  The captured DOM SHA-256 is
  `01f0da94c5e9577cc2167ea48b8cb297e39b86fbb1ea69a7639343a1bb61c412`;
  baseline snapshot SHA-256 is
  `29b2ca0b5d48337f28449f83e3b5b3811453f2843166dd270370867a254fcb01`.
- Candidate evidence:
  `/var/lib/patchyard/preview/session-7-candidate/evidence.json`, SHA-256
  `9a9b369d460f332b7f45c49229fb5d0bab6fe70a32f7af0d226bdaa935973e70`.
  The captured DOM SHA-256 is
  `61144c27ba2f066f16af8f0a032d1ba57e805f06a0e536aa385f2dfe39be5c76`;
  candidate snapshot SHA-256 is
  `582bb567b003e8d0ae5cb1a8bb99f1f19093bacae3ba39b0a9e180e26eeb6c42`.
- The combined sort evidence SHA-256 is
  `7bc35458d808088bc88e118d14f24f239a88a4abae7ecc8ed65fd6903473f84f`.
  `factory-verify postconditions` returned `postconditions: pass` against it.

## Cleanup proof

- Success: both baseline and candidate records report `cleanup.attempted: true`,
  `cleanup.complete: true`, and forced release `cleanup_complete: true`.
- Failure: the first baseline browser attempt failed after acquiring and
  verifying the exact base preview. Its retained evidence is
  `/var/lib/patchyard/preview/session-7-baseline/evidence.json`, SHA-256
  `edc2aecf3ead3221f7722c08ebab60b2e423413410374ce166e02013d477c93e`;
  it reports the error and `cleanup.complete: true` from the coordinator's
  `finally` path.
- Final host assertion: canonical `slots.json` contained zero factory leases,
  no `preview-4` container remained, `/opt/preview-fieldbooks/checkouts/4` was
  absent, and `patchyard-preview-sweep.timer` was active.

No cloud resource was changed and no OpenTofu apply ran in this session.
