# A78 complete-launcher binding review

## Review configuration

- Reviewer seat: A78, Opus 5, effort `max`
- Exact reviewed commit: `36590dc4f549641f63cfa903fe78c009651d8117`
- Parent: `f9b497570bbb5ac6ca71425ccd0cac7adcc2ecea`
- Review surface: detached worktree containing the exact reviewed commit
- Provider, worker, credential, cap, and acceptance actions: none

The original generated review header incorrectly said effort `high`. A resumed
metadata-only correction confirmed that the invocation requested and used
`max`, with no evidence of a downgrade. The verdict and findings were
unchanged.

## Verdict

**Findings.** The complete-launcher SHA-256 closes all four conceded
post-A118 findings for the reviewed launcher file. It does not establish that
the reviewed launcher and one-shot transport are the programs executed on the
worker, and adjacent credential-free guest assertions remain substring-bound.

## Verified repair properties

The reviewer independently reproduced:

- launcher SHA-256
  `c2b4275704ab0447a08e157be994a0bd18e505a843f1a017ce496220f3e83928`;
- checker SHA-256
  `6b49386cd63cb73d4aca399ac7d3b4d4bdace93c6f66bddf7ec61190c1630048`;
- one exact setup-preflight-transfer sequence, IPv6 comparison, setup and
  preflight definition, and one-shot invocation;
- rejection of all twenty authored mutations; and
- a passing baseline checker and all 24 focused spend tests.

Novel variants of all four prior findings were also rejected: definitions at
end of file, variable-gated preflight, an `&&`-chain fabricated counter, and an
accept rule immediately before transfer. Disabling the checker digest changed
its SHA-256 to the work-recorded value and failed sixteen tests. A deliberately
crashing checker failed the controlled-diagnostic assertion, closing the prior
crash-satisfaction observation.

## Finding 1 - reviewed source is not bound to executed programs - high

The only launcher installation check is in
`patchyard-run-anthropic-issuance`. The spend checker requires its launcher
comparison only as a bare substring and does not bind the runner source. Moving
the comparison into `if false; then` or assigning the expected value from the
observed value leaves the checker and focused suite green. The analogous
one-shot transport comparison is not required by the checker at all and can be
removed while green.

The reviewer combined the dead launcher comparison with a later Ansible task
writing different bytes to `/usr/local/sbin/patchyard-firecracker-run`.
The spend checker, 24 focused tests, worker runtime and qualification checks,
stack and independence checks, ShellCheck, and `ansible-lint site.yml` all
passed. Full Ansible discovery retained only the two disclosed requirement-1
live-digest failures. The installed worker could therefore execute a different
program while source gates continued to bind the untouched repository file.

The host-contract evidence is constructed from installed hashes, but its
repository comparison occurs only while validating a live result, after the
provider request. That is not a pre-request fail-closed binding.

The smallest demonstrated repair is to bind the complete runner source, require
exactly one Ansible writer for each launcher and one-shot destination, mirror
the runner digest in the focused test, and add the dead-code, self-comparison,
removed-transport-comparison, and duplicate-writer mutations.

## Finding 2 - guest boundary assertions are substring-bound - medium

The source checker requires credential-drive absence, empty provider hosts,
and transport receipt values only as substrings in
`patchyard-guest-run`. Wrapping the two absence assertions in dead code stays
green. Rewriting the jq receipt predicate as `true or (...)` preserves the
required cardinality substrings while short-circuiting their evaluation; that
also stays green.

This removes the guest's independent confirmation of the credential-free
boundary and kernel-derived receipt. The launcher-side checks remain, so the
finding is medium rather than high. The complete runner repair proposed for
Finding 1 does not cover the guest source; it needs its own complete binding.

## Carried-forward checks

- The A114 teardown exit repair remains effective.
- All 13 provider qualification flags remain false.
- No bare `ANTHROPIC_API_KEY` or long-lived Anthropic key was introduced.
- The requirement-1 four checker errors and two test failures are byte-for-byte
  unchanged disclosed history.
- The repair touches only the checker, test, documentation, work record, and
  generated metrics. It changes no launcher bytes, policy, result, or flag.

## Nonblocking observations

- Fifteen launcher mutations now exercise the same complete-file digest path.
  Removing several semantic checks and re-pinning the checker can leave all 24
  tests green, so those checks can silently rot at a legitimate re-pin.
- The adjacent call-sequence check is logically subsumed by the digest between
  re-pins.
- The focused test remains the human-reviewed root of the digest chain.
- `tokei` was unavailable in the reviewer environment.
- The enforcement document's revised claim that the listed mutations change
  the complete launcher digest is accurate.
- Changing only the Ansible launcher `src` fails closed at the current runner;
  the bypass requires also defeating the runner guard.
- Repository file mode is outside the SHA-256, while Ansible explicitly sets
  the installed mode.

## Review boundary

This was source review only. No repair, provider action, worker change, cap
change, credential issuance, behavioral acceptance, requirement-3 work, or
qualification-flag change occurred.
