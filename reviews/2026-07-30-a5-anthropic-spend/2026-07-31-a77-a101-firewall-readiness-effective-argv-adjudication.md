# A77 adjudication - readiness effective argv review

## Disposition

The build seat **concedes M1, M2, and M3** and sustains A78's severities. No
repair follows. The authorized test-only repair has completed its review loop,
so A9 requires escalation with this failure record.

Further work requires a new bounded authorization under A115. It must not mint
a new numbered ruling.

## M1 - concede

The build seat appended `-m 900` after the helper's exact long-form
three-second timeout fragment in a disposable detached worktree at commit
`96d5d0c`. All 7 tests passed.

A local-only delayed HTTP experiment then supplied
`--max-time 0.05 -m 2`. The response arrived after 0.25 seconds:

```text
curl_short_override_exit=0 body='ok'
```

Curl therefore honored the later short-form option. The test validates one
literal spelling rather than the effective argv consumed by curl. A78's medium
severity is sustained.

The smallest repair should validate the complete ordered argv inside the mock,
including:

- `-q --config -`;
- the exact failure, visibility, connect-timeout, transfer-timeout, and
  protocol options;
- the dynamic private output path;
- the exact write-out format; and
- the exact state-bound firewall URL.

No extra, short-form, retry, wrapper-prepended, or additional-config option may
remain.

## M2 - concede

The build seat appended `MAX_ATTEMPTS=240` in memory while retaining
`MAX_ATTEMPTS=24`. The repaired structural validator accepted the source:

```text
duplicate_MAX_ATTEMPTS accepted by structural validator
```

The existing behavioral call count still detects the installed mutation. A78's
low coverage-asymmetry severity is sustained.

## M3 - concede

The build seat added `/bin/sleep 0.02` after the PATH-observed sleep in a
disposable copy. All 7 tests passed in 16.879 seconds. The recorded mock values
remained exact because the absolute sleep bypassed the mock. A78's low severity
is sustained.

## Nonblocking observations and disclosure

- **Concede:** multiple-value JSON and poll reassignment now have independent
  structural and behavioral bindings.
- **Concede as preexisting:** the operator validator does not reject a PATH
  mutation before its exact second-converge/readiness interval. This finding is
  not introduced by the test-only repair and is outside the smallest M1-M3
  repair.
- **Concede the review-process disclosure:** one broad grep displayed
  review-path fragments. The reviewer did not open those files, and its
  experiments and conclusions remained independent and offline.

## A9 stop and proposed boundary

The smallest next repair changes only the readiness test:

1. make mock curl require one exact ordered argv vector and reject every extra
   option;
2. require exactly one `MAX_ATTEMPTS=` assignment;
3. require exactly one sleep command; and
4. add mutations for short-form timeout, a wrapper/prepended timeout, extra
   retry or config options, duplicate maximum attempts, and absolute extra
   sleep.

If authorized, the sequence would run the focused suite and installed
mutations, the complete repository gates, and another clean A78 review. It
would authorize no production helper or operator change, worker plan or apply,
cloud mutation, provider credential or request, Console action, requirement-1
refresh, behavioral acceptance, requirement 3, rotation work, or
qualification-flag change.
