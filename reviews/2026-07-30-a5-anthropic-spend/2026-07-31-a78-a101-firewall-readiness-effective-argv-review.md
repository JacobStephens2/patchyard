# A78 adversarial source review - readiness effective argv

## Verdict

**NOT A PASS** - one medium and two low material test-binding findings.

Reviewed commit:
`96d5d0cc61e98b08193f8d3f34b7aac629fc28f3`, technical test commit
`bb91d7ecd14d3284be5ee73b20c052f75f5e3fe7`.

Reviewer: A78, Opus 5 at `xhigh` effort through Claude Code 2.1.220 on
Anthropic. The detached worktree was clean at the exact reviewed commit before
and after review.

## M1 - alternate curl controls evade the timeout binding

Severity: **medium, material**.

The test binds the literal long-form strings `--connect-timeout` and
`--max-time`, but its mock curl ignores the effective option vector after
checking config stdin, `--fail`, bearer absence, and the output path.

A78 installed four independent fragment-preserving mutants. Each passed all 7
tests while changing the effective transfer timeout from 3 to 900 seconds:

1. append short option `-m 900`;
2. enable aliases and define `curl='curl -m 900'`;
3. define a shell `curl` function that prepends `-m 900`; and
4. append a second curl config containing `max-time = 900`.

An additional retry configuration
`--retry 100 --retry-delay 60 --retry-all-errors` also survived. The
replacement wrapper could therefore remain between its second converge and
A101 for hours while every asserted source fragment remains present.

Smallest repair: make the mock curl reject every argv vector except the exact
ordered contract, with only the generated output path and state-bound firewall
ID variable. That must reject prepended aliases/functions, alternate short
options, appended config, retry options, and every other extra argument.

## M2 - maximum-attempt assignment is not singular

Severity: **low**.

The new singularity tuple includes `POLL_SECONDS=` but omits
`MAX_ATTEMPTS=`. Appending `MAX_ATTEMPTS=240` preserves the exact
`MAX_ATTEMPTS=24` line and passes both structural tests.

The behavior cases still reject the mutation because they require 24 curl
calls, so this is a coverage asymmetry rather than a full-suite escape.

Smallest repair: require exactly one `MAX_ATTEMPTS=` assignment.

## M3 - extra sleep commands are not bound

Severity: **low**.

Adding `/bin/sleep 0.02` alongside the bound
`sleep "$POLL_SECONDS"` passes all 7 tests. The mock records only calls reached
through PATH; it cannot observe the absolute command. A larger extra delay
would hang rather than fail.

Smallest repair: require the helper to contain exactly one sleep command as
well as the exact existing poll assignment and argument.

## Verified properties

- All 7 focused tests pass on Python 3.9.25.
- All 27 shipped mutations raise from distinct on-target checks.
- The three formerly green mutations are now caught on structural and
  behavioral layers as intended.
- The multiple-ready fixture independently catches pre-jq, post-jq, and
  call-site truncation strategies.
- Every PATH-observed sleep argument is exactly `2`.
- The production helper, replacement operator, and Ansible wrapper remain
  byte-identical.
- ShellCheck passes with pinned version 0.11.0.
- All 13 provider `credential_qualified` values remain false.
- No bare `ANTHROPIC_API_KEY` assignment or long-lived Anthropic credential was
  introduced.

## Nonblocking observations

- An obfuscated poll reassignment evades the literal singularity test but fails
  behaviorally.
- The replacement operator lacks a behavioral test for a PATH shim inserted
  before the first converge. This predates the test-only repair.
- `docs/codebase-metrics.json` changed consistently with the test-file line
  delta.

## Review execution and safety

A78 ran the focused suite, instrumented all 27 shipped mutations, and tested 20
independent additive mutations in disposable offline copies. No real curl,
network call, web access, subagent, live host, cloud API, provider credential,
replacement, provider request, or cap action occurred.

One early broad credential grep displayed matching single-line fragments from
review paths before the search was narrowed. No review document was opened and
no conclusion used those fragments. The final detached worktree was clean.
