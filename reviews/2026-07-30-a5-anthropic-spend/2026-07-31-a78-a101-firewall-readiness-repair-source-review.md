# A78 adversarial source review - A101 firewall-readiness repair

## Verdict

**NOT A PASS** - one medium material test-binding finding.

Reviewed commit:
`cdd931ec4545f426bf07bd53efd18673e140d346`, parent
`097a5b4acdf68fb27b173445f0df0ff6fb3b7e74`.

Reviewer: A78, Opus 5 at `xhigh` effort via Claude Code 2.1.220 on Anthropic.
The review used a fresh detached worktree and ended with clean status at the
exact reviewed commit.

## F1 - additive overrides evade all shipped mutations

Severity: **medium, material**.

The repaired production helper resisted the reviewed attacks, but
`validate_readiness_contract` remains a textual required-fragment check. All 20
helper mutations are passed only to that validator; no mutated helper is
executed. Additive source can therefore preserve each required fragment exactly
once and override its behavior elsewhere.

A78 built three independent mutants. Each passed all 7 focused tests, including
the test that runs all 24 shipped source mutations:

| Mutant | Effective behavior |
| --- | --- |
| Pipe jq output through `tail -n1` | A stream containing a rejected value followed by a ready value becomes the exact accepted string `true`. |
| Append `--connect-timeout 900 --max-time 900` | Curl uses the later values, expanding each nominally three-second request to 900 seconds. |
| Append `POLL_SECONDS=600` | Bash uses the later assignment, making 23 sleeps total approximately 3.8 hours. |

The sleep mock already records each argument, but the suite counts lines without
checking their values. The provider mock has no multi-value JSON case. The
validator requires the original timeout fragment once but does not require the
timeout options themselves to occur only once.

The smallest repair is test-only:

1. add a two-ready-values provider mode to the fail-closed response set;
2. assert that every recorded sleep argument is exactly `2`; and
3. assert that `--connect-timeout` and `--max-time` each occur exactly once.

Add permanent mutations for the same three additive override classes.

## Verified source behavior

A78 found the repaired production source fail-closed for:

- empty, whitespace-only, and malformed bodies;
- four multi-value JSON orderings;
- missing, null, array, and string `.firewall` values;
- HTTP errors plus non-200 204 and 302 responses;
- malformed, duplicate, mismatched, and non-array state bindings; and
- provider identity, status, pending-change, worker, attachment-cardinality,
  and tag mismatches.

The operator order remains apply, converge twice, direct fatal readiness, then
one-shot A101 through `qualify.sh`. The bearer was absent from a real process
argv canary. Curl truncates the response output on each accepted 2xx response,
so A78 found no stale-body reuse path.

All 13 provider `credential_qualified` values remain false. No bare
`ANTHROPIC_API_KEY` assignment or long-lived Anthropic credential was added.
`infra/replace-worker.sh` and `tools/check-ansible.sh` remain byte-identical to
the first review.

## Nonblocking observations

1. The EXIT trap does not name `INT` or `TERM`; A78 measured one temporary
   response-file residue after SIGTERM.
2. The firewall-ID regular expression remains shape-loose and fails later at
   the provider boundary.
3. The state scan ignores child modules. No OpenTofu `module` block exists in
   the repository.

## Review disclosures

- One repository-wide grep was not review-path-excluded, so matching
  boilerplate lines from `reviews/**` appeared in output. A78 did not open a
  review file and did not base a conclusion on those lines.
- One cleanup experiment unintentionally left real curl on PATH for
  approximately one second. Up to one read-only HTTPS GET to
  `api.digitalocean.com` may have been attempted with literal placeholder
  bearer `goodtoken`. The outcome was not retained. No real credential or
  mutating method was used.
- A zero-byte scratch file created by that experiment was removed before final
  status verification.

No tracked file, worker, DigitalOcean resource, Anthropic credential or
request, Console limit, requirement-1 fixture, acceptance case, requirement-3
artifact, rotation state, or qualification flag changed.
