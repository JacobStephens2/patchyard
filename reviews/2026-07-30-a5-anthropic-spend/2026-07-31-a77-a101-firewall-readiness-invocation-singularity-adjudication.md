# A77 adjudication - readiness invocation singularity review

## Disposition

The build seat **concedes M1 at High severity**. The finding is reproducible and
the authorized binding remains incomplete. No repair follows: the authorized
repair has completed its A78 loop, so A9 requires escalation with this failure
record.

Further work requires a new bounded authorization under A115. It must not mint
a new numbered ruling.

## M1 - concede

The build seat installed each A78 material mutant independently in disposable
detached worktrees at exact record commit `6e9e982`.

### Extra timeout and retry call

The helper gained a second curl before the bound provider call. It used
short-form timeout and retry controls and discarded failure. The real focused
suite reported:

```text
Ran 7 tests in 15.577s
OK
```

The test mock rejected the extra argv before incrementing its accepted-call
counter. The later bound call still supplied the expected payload and count.

### Response overwrite call

The helper gained a second curl after the bound provider call and before
`FIREWALL_RESPONSE` read the response file. It discarded failure. The real
focused suite reported:

```text
Ran 7 tests in 14.682s
OK
```

The mock again rejected the extra argv without recording it or changing the
file. In production, real curl would be able to replace the body that controls
the readiness verdict. A78's High severity is sustained.

### Mock-bypass refinement

The build seat also added an absolute `/nonexistent/curl` call before the bound
call and discarded its failure. This is an offline stand-in for an absolute
real-curl invocation; it cannot reach a network. All 7 tests passed in 12.667
seconds.

This proves that a mock-total counter alone would not observe a command that
bypasses PATH. It is an inference, not a live execution, that replacing the
nonexistent path with a real curl path would permit the extra transfer while
the ordinary bound call still satisfies the mock.

The smallest adequate repair should therefore combine:

1. an attempted-call counter incremented at mock entry before any validation;
2. exact attempted and accepted counts in every behavior and mutation case;
3. a source-level singular curl-executor binding that rejects additive
   absolute-path or indirect curl commands that cannot reach the PATH mock; and
4. permanent mutations for the rejected extra call, response overwrite call,
   and absolute-path stand-in.

## Nonblocking observations

- **Concede as nonblocking:** a non-`sleep` delay can reach a test timeout, but
  A78 did not produce a green suite and stdin controls whether the delay occurs.
- **Concede as nonblocking:** suppressing curl stderr loses diagnostics without
  changing the gate's verdict or bound.
- **Concede as coverage disclosure:** independent mutations reached the
  positional, output-path, and config gates, although shipped mutations do not
  pin each separately.
- **Concede as nonblocking:** the output-path glob accepts nested paths within
  the private directory; no verdict or confidentiality bypass was established.
- **Concede:** arithmetic maximum-attempt and poll overrides evade the lexical
  layer but are caught by the behavioral layer.

## A9 stop and proposed boundary

If authorized, the next repair changes only
`infra/ansible/tests/test_worker_firewall_readiness.py` and adds the attempted
counter, exact attempted/accepted assertions, source-level curl singularity,
and the three mutation classes above. It must then run installed mutations,
the complete repository gates, and another clean A78 review.

It authorizes no production helper or operator change, worker plan or apply,
cloud mutation, provider credential or request, Console action, requirement-1
refresh, behavioral acceptance, requirement 3, rotation work, or
qualification-flag change.
