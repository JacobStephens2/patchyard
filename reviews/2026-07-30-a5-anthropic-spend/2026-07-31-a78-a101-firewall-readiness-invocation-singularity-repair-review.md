# A78 adversarial source review - invocation-singularity repair

## Verdict

**NOT A PASS** - six material findings: two High, three Medium, and one
Low/Medium.

Reviewed record commit:
`b66e6dcd77b9b32dca95b279beaa30039f9f6535`; technical test commit:
`3ec94b419fe6fc50ba0bfc5609437a1c8f0afb07`.

Reviewer: A78, Claude Opus 5 at `xhigh` effort through Claude Code 2.1.220 on
Anthropic. The detached worktree was clean at the exact reviewed commit before
and after review.

## Verified repair properties

- All 7 focused tests passed.
- A subtest census exercised 56 subtests with no failure: 18 behavior cases,
  38 named mutation subtests, and the additional inline attempted-call
  mutation. All 39 shipped mutation paths were live and detected.
- Direct mock probes confirmed that rejected argv increments the attempted
  counter before validation while leaving the accepted counter at zero.
- Every behavior uses exact totals: 1/1 for ready, 2/2 for pending then ready,
  24/24 for provider exhaustion, 0/0 before provider polling, 0/24 for the five
  rejected effective-argv mutants, and 1/2 for the rejected wrapper mutation.
- The five installed mutation classes were independently reproduced and
  detected: timeout/retry, response overwrite, absolute path, three quoted or
  escaped spellings, and an extra rejected wrapper call.
- The helper, operator, and Ansible wrapper matched their required SHA-256
  values byte-for-byte. The repair remained test-only.

## F1 - alternate network clients are unobserved

Severity: **High, material**.

The source rule binds a literal `curl` token rather than the security property
of one network-client invocation. The mock directory supplies only curl and
sleep while the test PATH retains `/usr/bin:/bin`. A different client can
therefore execute without touching either curl counter. A78 made local stub
clients execute while all 7 tests passed and statically confirmed that wget
and Python urllib forms preserve the lexical contract.

The smallest proposed direction is an allowlisted execution environment that
records or rejects every unexpected command, rather than a curl-name-only
counter.

## F2 - quote and parameter assembly bypass the lexical rule

Severity: **High, material**.

The normalizer removes only empty adjacent quote pairs and simple backslashes.
It accepts nonempty quote splitting such as `cu"r"l`, absolute paths assembled
from variables, and shell substitutions that contain no literal `curl`. An
absolute assembled command also bypasses PATH, so the lexical rule, mock total,
accepted count, argv check, and endpoint-prefix count all remain satisfied.
A78 executed three local stub variants with a 900-second timeout and retry
shape; all 7 tests passed.

The smallest proposed direction is an exact executed-command trace or a
complete allowlist for simple command words, including rejection of absolute
and parameter-expanded command words.

## F3 - sourced files and shell-builtin networking are outside the contract

Severity: **Medium, material**.

The validator reads only the helper text, and the test fixture copies only the
helper. A guarded source of a repository sibling therefore passes while the
dependency is absent from the test fixture but can exist in the installed
repository. A guarded Bash `/dev/tcp` command also passes because it executes
no external binary. Both variants kept all 7 tests green.

The smallest proposed direction is to forbid undeclared sourcing and Bash
`/dev/tcp` or `/dev/udp` use in the helper contract.

## F4 - operator executors outside the readiness interval are unbound

Severity: **Medium, material**.

The operator validator checks the ordered apply, converge, readiness, and A101
calls and requires the readiness interval to be exact. It does not scan the
rest of the operator for network executors. A78 added an unbounded curl after
OpenTofu apply and separately after A101; both forms passed the complete
focused suite.

The smallest proposed direction is an operator-wide executor or source
identity binding, with only the reviewed sub-script calls allowed.

## F5 - the Ansible wrapper does not bind its own readiness coverage

Severity: **Medium, material**.

The workflow invokes `tools/check-ansible.sh`, and the wrapper currently
shellchecks the helper and discovers the readiness test. No independent test
requires either membership. Python unittest discovery succeeds when zero tests
are present, so removal of the test module or helper ShellCheck argument can
silently remove the gate after the corresponding source change.

The smallest proposed direction is an independent contract for the explicit
test census and helper/operator ShellCheck membership rather than relying only
on open-ended discovery.

## F6 - code under test controls the attempted-counter destination

Severity: **Low/Medium, material**.

The mock reads `MOCK_CURL_TOTAL` from the helper environment on every call. An
extra quote-split curl can override that variable with `/dev/null`, reach the
mock, fail argv validation, and discard its increment. The legitimate call
then leaves both asserted counters exact, and all 7 tests pass.

The smallest proposed direction is a counter destination that the helper
cannot redirect, such as a mock-embedded path or inherited descriptor.

## Nonblocking observations

- The repair closes every mutation it was explicitly authored to close, and
  none of the 39 shipped paths is dead or vacuous.
- Sleep uses a broader substring singularity check than curl; the two source
  disciplines should eventually be made consistent.
- The inline rejected-wrapper mutation would report more clearly as a named
  subtest.
- The source lexical rule remains useful for rejected commands that never
  reach the runtime mock, even though it is not complete by itself.
- The printed verdict said "five material findings" before enumerating F1
  through F6. This is a clerical count inconsistency; six distinct findings
  were reported and handed off.

## Review execution and safety

A78 ran the shipped suite, the 39 mutation paths, the five required installed
mutation classes, 12 additional mutants, and a 13-spelling static matrix.
Local stub clients recorded 872 invocations; no stub opened a socket.

The review stayed offline. No real curl, network, DNS, browser, web, GitHub,
DigitalOcean, Anthropic, SSH, Ansible, OpenTofu, worker, provider, Console, or
qualification action occurred. No environment secret or credential was read.
No subagent was used, no file under `reviews/` was opened, and all disposable
mutation files were removed.
