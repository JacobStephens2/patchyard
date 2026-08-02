# A120 spend evidence validation repair - source work record

Date: 2026-08-02

Status: source complete; awaiting separate A78 review before any worker
mutation or provider request

Base: `5b8b3aa23d09f210bebf5a4ece67666c1d711c38`

## Result

The Anthropic qualification runner now applies its three capability-drive
evidence predicates only to `issuance-delivery`. Their issuance strictness is
unchanged. The `provider-spend-enforcement` path retains its exact six-key
`.delivery` equality and every other paid-path predicate unchanged.

## A77 adjudication

The runner, not the guest, was wrong.

A117 says requirement 1 remains on the guest read-only credential-drive path.
For requirement 2, the worker host consumes the bearer in its one-shot network
namespace, destroys the namespace and credential, and then boots a
credential-free spend guest with no provider allowlist. A118 preserves that
split while hardening only the host transport. The guest therefore correctly
emits two evidence shapes:

- issuance reports the capability drive as read-only, unmounted before the
  provider call, and removed before output; and
- spend reports exactly `worker_host_tmpfs`, `credential_delivered_to_guest`,
  `credential_removed_before_guest_boot`, `assertion_delivered`,
  `signing_key_delivered`, and `admin_credential_delivered`.

A no-network execution of the pre-repair validator confirmed the contradiction.
The exact six-key spend object failed first at
`delivery.capability_drive_read_only`. Adding the three capability fields made
those unconditional predicates pass but then failed at the exact
`delivery.spend_contract` predicate. No `.delivery` object could satisfy both.

The alternative guest-side conclusion is refuted by A117's explicit
credential-free guest boundary and by the host-owned transport receipt. No
guest image or image binding changed.

## Change

Only these three runner predicates gained the same
`if $qualification_requirement == "issuance-delivery" then ... else true end`
applicability guard already used by the adjacent path-specific predicates:

1. `delivery.capability_drive_read_only`;
2. `delivery.capability_drive_unmounted_before_provider_call`; and
3. `delivery.credential_removed_before_output`.

The spend request body, uncached-token floor, cache exclusion, transport,
cardinality, phase stops, and exact six-key delivery match are byte-identical
to the base.

## Regression and mutation proof

Before this commit, the executable runner-validation harness covered only the
retained requirement-1 issuance fixture. Repository history contained no
passing spend-path runner evidence fixture. The two spend JSON records were
historical failure summaries with no runner `.delivery`, `provider_transport`,
`provider_observation`, or `host_teardown` object, and no test supplied
`provider-spend-enforcement` evidence to the extracted validator.

The harness now supplies a credential-free spend fixture with the exact
six-key guest delivery object and executes the real runner validation block.
The pre-repair test failed at
`delivery.capability_drive_read_only`; the repaired test returns zero with
empty stdout and stderr.

The same test proves the reverse direction:

- intact issuance evidence with all three capability facts validates;
- issuance evidence with all three facts absent is rejected;
- removing each capability fact individually is rejected at that fact's named
  clause; and
- adding the capability facts to spend evidence is still rejected by
  `delivery.spend_contract`, proving the exact six-key match was not weakened.

No provider, worker, or network action occurs in these tests.

## Host contracts and the one owed refresh

The repaired runner SHA-256 is
`91c3fdc09b34d009a02e4f8d1290976c558b0a654e89171dcaa5b3fd037a7608`.
It participates in both host contracts. With the unchanged launcher, the
requirement-1 contract moves from the diagnostics commit's
`b8f2577ba1236039c7b1eb145c1e38b64f928771ad41aee5a56eaa4e1c1575d2`
to
`9b9890a3b2c722d428708098dd45ce296b89393ff35c48678d5c9df73d1911f2`.
With the unchanged launcher and one-shot transport, the requirement-2 host
contract is
`620b7789b67b88b4af9e1b371db6f5d50e19ec0d3febb22783968393eb1d732a`.

Because this repair and the diagnostics commit land before any converge, they
still incur exactly one requirement-1 refresh after the reviewed branch is
deployed. The committed requirement-1 fixture remains intentionally bound to
`eef6e16e54b6c0945f3874dae71063e8ef2248fea470f2fe4b2579ce22d52977`.
Its check will fail locally and in CI until that separately authorized deploy
and live refresh. This work does not hide, simulate, or perform the refresh.

## Gate results

The full repository gate set ran against the completed source:

- `tools/check-infra.sh` initialized and validated all three OpenTofu roots.
  The A101 trust root, stack, independence, worker runtime, worker
  qualification, A120 spend, and preview checks passed. The wrapper returned 1
  only because the live requirement-1 artifact records `eef6e16e...d52977`
  instead of the new `9b9890a3...1911f2` host contract.
- `tools/check-ansible.sh` ran 171 isolated tests. 170 passed; the only failure
  was `test_live_evidence_binds_current_host_contract`, asserting that same
  deliberate staleness. ShellCheck, all four Ansible lint profiles, all four
  playbook syntax checks, and the terminal A101 trust-root recheck passed. The
  local run used disposable `/tmp` Ansible cache and home paths because the
  sandbox exposes the service account's normal cache paths read-only.
- `tools/check-application.sh` returned zero across the constitution, 39
  preview tests, Rust format, clippy, unit/integration/property tests, replay,
  reproducible release, audit, deny, vet, dependency, model, and byte-exact
  codebase-metrics gates. The declared Docker-only Traefik test was skipped
  locally; hosted PR CI supplies that service. A disposable writable Cargo
  home was used for the advisory database because the normal cache path is
  read-only in this sandbox.
- Direct Bash syntax and ShellCheck passed for the changed runner. The A120
  spend checker and all 31 spend tests passed. The focused evidence-validation
  regression failed before the runner repair at the first unconditional
  capability clause and passed afterward in both directions, including all
  three issuance-field mutations. The isolated requirement-1 checker remains
  honestly red only for the refresh owed above.

The two nonzero wrappers therefore expose one expected stale live fixture, not
an unrelated source or gate failure. No checker or test was weakened to hide
it.

## Negative-scope attestation

This work made no provider request, minted no credential, changed no Anthropic
Console limit, applied no infrastructure, converged no host, mutated no worker,
refreshed no fixture, performed no behavioral acceptance, and started no
requirement-3 work. It introduced no bare `ANTHROPIC_API_KEY` or long-lived
key. All 13 `credential_qualified` values remain false.
