# A78 adversarial source review - readiness invocation singularity

## Verdict

**NOT A PASS** - one High material finding.

Reviewed record commit:
`6e9e9821e17c8d0e3a47169e829e060a3a51eec7`; technical test commit:
`0339826785a5202d6aba8097e71dfc3d382e4df6`.

Reviewer: A78, Claude Opus 5 at `xhigh` effort through Claude Code 2.1.220 on
Anthropic. The detached worktree was clean at the exact reviewed commit before
and after review.

## Verified repair properties

- All 7 focused tests passed on Python 3.9.25.
- All 34 shipped mutations were on-target and rejected: 25 static helper
  mutations, 5 curl-argv mutations, and 4 operator mutations.
- The mock receives the intended 17-token baseline argv in exact order.
- The five shipped curl variants genuinely changed effective argv and were
  rejected at the mock length gate.
- Independently varied short timeout, alias, shell function, short config,
  stdin config, retry, arithmetic maximum attempts, `command sleep`, absolute
  sleep, output path, argument ordering, poll arithmetic, duplicate valid
  calls, command-path escape, and bearer-smuggling cases were exercised
  offline.
- The production helper, replacement operator, and Ansible wrapper remained
  byte-identical to the parent record.

## M1 - rejected extra curl invocations are invisible

Severity: **High, material**.

The mock validates argv before incrementing `MOCK_CURL_CALLS`. A rejected call
therefore leaves no record. If the helper discards that call's failure with
`|| true`, every accepted-call assertion still sees the expected count.

A78 installed two additive helper mutations in disposable offline copies. Both
passed all 7 tests:

1. an extra timeout-and-retry curl before the bound call, which can expand the
   readiness wall clock far beyond the intended bound; and
2. an extra curl after the provider call but before reading the response file,
   which can overwrite that file with a forged ready payload.

The second mutation leaves the legitimate mock payload in place because the
mock refuses the rogue argv before writing. Real curl would perform the extra
transfer and overwrite the response before `firewall_is_ready` evaluates it.
The test can therefore stay green while production could pass A101 against a
firewall that never converged.

This behavior predates the repair, but the authorized binding required one
exact ordered effective curl vector. The repair binds the accepted vector but
does not bind invocation singularity, so that requirement is incomplete.

A78's proposed smallest repair is test-only: count every mock invocation before
argv validation, keep the accepted counter, and assert exact total and accepted
counts in every behavior case and mutation case.

## Nonblocking observations

- `read -t 900 -r _ || true` adds a non-`sleep` delay without another sleep
  lexeme. It timed out under A78's 150-second harness rather than producing a
  green suite. Its effect depends on whether stdin is already at EOF.
- Redirecting the bound curl's stderr to `/dev/null` passes all 7 tests but
  changes diagnostics rather than verdict or timing.
- The five shipped argv mutants all reach the length gate. Independent tests
  established that the output-path, positional, and config-equality gates work,
  but the shipped mutation set does not pin each one separately.
- The private-output glob also accepts paths nested below the private directory.
  A78 found no way to exploit that while keeping the helper's read path
  coherent.
- Arithmetic reassignment evades assignment-substring checks but is rejected by
  the behavioral call and sleep assertions.

## Review execution and safety

A78 exercised 20 independent mutations: 16 were caught, one reached the
reviewer's bounded timeout, two material mutants passed, and one diagnostic-only
mutant passed. All mutations ran in disposable copies and were removed.

The review remained offline. The only curl executable reached was the suite
mock. No real curl, network, web, GitHub, DigitalOcean, Anthropic, SSH, Ansible,
OpenTofu, worker, provider, Console, or qualification action occurred. No
environment variable or credential was inspected or printed. No subagent was
used, and no prior review or adjudication file was opened.
