# A77 adjudication - A101 firewall-readiness repair source review

## Disposition

The build seat **concedes F1** and sustains its medium material severity. The
production helper remains source-sound under the reviewed attacks, but the test
suite does not reject additive overrides of three intended bindings.

No repair follows. The authorized repair loop has been consumed, so A9 requires
escalation with this failure record. Further work requires a new bounded
authorization and is recorded under A115 rather than as a new numbered ruling.

## F1 - concede with independent experiments

The build seat created each mutation independently in a disposable detached
worktree at exact commit `cdd931e`. Every mutated tree passed all 7 focused
tests, including all 24 shipped mutations.

### Multi-value filter

The exact jq predicate received a rejected object followed by a ready object.
With the additive `tail -n1` pipeline, the observed output and exit status were:

```text
true
exit=0
```

This converts a multi-value response into the exact accepted shell string
without removing any required fragment.

### Duplicate curl timeout

The helper retained its exact three-second timeout fragment and appended
900-second timeout options. All 7 tests passed. A local-only delayed HTTP
server then established curl's duplicate-option behavior:

```text
curl --max-time 0.05 --max-time 2
curl_duplicate_max_time_exit=0 body='ok'
```

The response arrived after 0.3 seconds, proving the later value controlled the
request.

### Duplicate poll assignment

The helper retained `POLL_SECONDS=2` and appended `POLL_SECONDS=600`. All 7
tests passed. Bash readback reported:

```text
effective_poll_seconds=600
```

The current mock asserts 23 sleep calls but never asserts that each recorded
argument is `2`.

## Nonblocking observations and review disclosures

- **Concede:** a direct SIGTERM-specific cleanup binding would be stronger than
  EXIT-only cleanup. A78's measured residue is nonblocking because readiness
  fails closed and the file is private under umask 077. It is not part of the
  smallest F1 repair.
- **Concede:** the firewall-ID expression is permissive, then fails closed at
  the fixed provider endpoint and exact returned-ID predicate.
- **Concede as a structural limit:** child-module resources are not scanned.
  An independent repository scan found no OpenTofu module block.
- **Concede the review-process deviations:** one grep displayed review-file
  boilerplate, and one experiment may have issued an unauthenticated read-only
  GET with a literal placeholder bearer. Neither supplied evidence used in the
  source verdict, exposed a real credential, or changed provider state. Both
  are retained in the audit record rather than omitted.

## A9 stop and proposed boundary

The smallest next repair changes only
`infra/ansible/tests/test_worker_firewall_readiness.py`:

1. add a multi-value provider response fixture to the exhaustive fail-closed
   set;
2. assert every sleep argument is exactly `2`;
3. require exactly one `--connect-timeout` and one `--max-time`; and
4. add three corresponding additive source mutations.

If authorized, the sequence would run the focused suite and its mutations, the
complete repository gates, and a new clean A78 review. It would not change the
production helper or operator and would authorize no worker plan or apply,
host or cloud mutation, provider credential or request, Console action,
requirement-1 refresh, behavioral acceptance, requirement 3, rotation work, or
qualification-flag change.
