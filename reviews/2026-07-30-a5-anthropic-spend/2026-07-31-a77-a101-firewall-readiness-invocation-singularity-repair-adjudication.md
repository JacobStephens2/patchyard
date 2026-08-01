# A77 adjudication - invocation-singularity repair review

## Disposition

The build seat independently reproduced and **concedes all six A78 findings**:

| Finding | A77 disposition |
| --- | --- |
| F1 alternate network clients | concede, High sustained |
| F2 quote and parameter assembly | concede, High sustained |
| F3 source and Bash-builtin networking | concede, Medium sustained |
| F4 operator-wide executor gap | concede, Medium sustained |
| F5 wrapper coverage membership | concede, Medium sustained |
| F6 attempted-counter redirection | concede, Low sustained from A78's Low/Medium range |

No repair follows. The authorized repair completed its fresh A78 loop and the
review failed, so A9 requires this stop and failure record. Further work needs
a new explicit bounded authorization under A115 and must not mint another
numbered ruling.

## Independent source-mutation experiments

The build seat imported the real seven-test class from exact reviewed commit
`b66e6dcd77b9b32dca95b279beaa30039f9f6535`, supplied one mutated helper or
operator at a time, and used new disposable directories unrelated to A78's
copies. Results were:

| Mutation | Tests | Result | Independent observation |
| --- | ---: | --- | --- |
| F1 absolute alternate client | 7 | green | local stub executed 436 times |
| F2 parameter-assembled absolute client | 7 | green | local stub executed 436 times |
| F3 guarded repository sibling source | 7 | green | source was absent from the fixture copy |
| F3 guarded `/dev/tcp` builtin | 7 | green | guard remained dormant with the test environment |
| F4 unbounded operator curl after apply | 7 | green | operator mutation was accepted and never executed by the focused class |
| F6 quote-split curl with redirected total | 7 | green | hidden counter recorded 436 rejected extra attempts |

F1 is conceded because the stub used an alternate absolute client name and
was actually invoked on every applicable behavior and mutation path without
touching either curl counter. Replacing a local no-network stub with a real
alternate client would change production network behavior; that last step is
an inference and was not executed.

F2 is conceded because the command path was assembled from a variable and
contained no literal curl token. It bypassed PATH and every curl-specific
binding while actually executing the local stub 436 times.

F3 is conceded because the test fixture copies only the helper and therefore
cannot exercise a newly sourced repository sibling. A dormant `/dev/tcp`
branch also passes the source validator and cannot be observed by an external
command mock. These are latent source-expansion channels within the reviewed
boundary.

F4 is conceded because the operator validator accepted the added executor
outside its narrow readiness interval. The focused class remained green, and
source inspection confirms that only call ordering and interval text are
bound.

F6 is conceded because substituting an independently observable hidden file
for `/dev/null` recorded 436 extra rejected mock calls while all 7 tests stayed
green. The source under test controls the counter destination. Low severity is
appropriate because the bypass must name a test-only environment variable in
production source, making it conspicuous even though it defeats the test.

All mutation directories were removed. No real network client or socket was
used.

## F5 independent wrapper experiment

Repository search found the readiness helper's ShellCheck membership only in
`tools/check-ansible.sh`; no contract reads and binds that membership. The
GitHub infrastructure workflow invokes the wrapper but does not enumerate its
tests or inputs. A new empty discovery directory produced:

```text
Ran 0 tests in 0.000s
OK
empty_discovery_rc=0
```

F5 is conceded at Medium because open-ended discovery has no minimum census
and no independent gate requires the readiness module or the helper's
ShellCheck argument. Generated codebase metrics may expose an unregenerated
file deletion, but they do not bind these semantics and can be legitimately
regenerated; they do not refute the finding.

## A9 stop and proposed next boundary

The smallest credible next step is a bounded test-and-gate structural redesign,
not another list of curl spellings. If authorized, it should:

1. bind exact helper, operator, and Ansible-wrapper source identities outside
   the behavior being checked, so any production source-only mutation fails;
2. replace the helper-controlled attempted-counter path with a mock-private
   channel;
3. forbid undeclared helper sourcing and Bash builtin networking;
4. bind operator-wide executor policy rather than only the readiness interval;
5. bind an explicit Ansible test census and ShellCheck membership; and
6. permanently install and reject each F1-F6 mutation class before the full
   gates and another clean A78 review.

That proposed authorization includes no production helper or operator behavior
change and no worker plan or apply, cloud mutation, credential, provider
request, Console action, requirement-1 refresh, behavioral acceptance,
requirement 3, rotation work, or qualification-flag change.
