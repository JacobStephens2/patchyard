# A77 adjudication - A101 F1-F6 structural-redesign review

## Disposition

The build seat independently resolved all five A78 findings:

| Finding | A77 disposition |
| --- | --- |
| A1 unpinned transitive state oracle | **concede, High sustained** |
| A2 shared-process discovery and unreachable checker | **concede with scope correction, Medium-High** |
| A3 repository-internal digest graph | **concede the trust-root observation; refute the claimed semantic all-pass bypass** |
| A4 stale requirement-1 fixture | **concede the fact; refute it as a new F1-F6 defect** |
| A5 executable tool-version data | **concede, severity raised to High** |

No live action or evidence refresh follows from these dispositions. The next
source repair was separately authorized by Jacob under A115 and must not mint
a new numbered ruling.

## A1 experiment - conceded

In a disposable detached worktree, the build seat changed `infra/tofu.sh` to
intercept only `digitalocean show`, execute inert `/nonexistent/curl` and
`/nonexistent/wget` paths, and return substituted state. The mutated script
still passed ShellCheck. `tools/check-anthropic-spend.py` passed, and complete
Ansible discovery ran 149 tests with only the same stale issuance failure.

This independently reproduces the unbound state oracle. Source inspection
also confirms that `replace-worker.sh` reaches unbound `converge.sh`,
`qualify.sh`, and the inventory wrapper. A1 is conceded at High.

## A2 experiment - conceded with corrected scope

The build seat added an inert alternate-client path to the helper and changed
the unpinned issuance test to monkeypatch `hashlib.sha256`, mapping that
mutant's actual digest to the expected helper digest. Complete discovery ran
149 tests and again failed only the stale issuance assertion. The readiness
and spend modules inside that shared process accepted the forged digest.

The independent `python3 tools/check-anthropic-spend.py` process did not accept
the mutation. It exited nonzero with:

```text
A101 firewall readiness helper differs from its complete source binding
```

A2 is therefore conceded for shared-process discovery, missing module census,
and current wrapper ordering. The claim that the monkeypatch neutralizes the
out-of-process checker is refuted. Severity is Medium-High: the independent
control exists, but the red requirement-1 check currently prevents the normal
infrastructure wrapper from reaching it.

## A3 experiment - semantic bypass refuted

The build seat inserted three representative weakenings into the helper at
once: an alternate `/nonexistent/wget`, a parameter-assembled absolute curl,
and a sourced sibling. It then rolled the helper digest through the readiness
test, spend checker, and spend contract test; rolled the resulting readiness
test digest into the checker and spend test; and rolled the checker digest into
the spend test.

The independent spend checker and all 27 spend tests passed. The actual
seven-test readiness suite did not:

```text
ValueError: readiness curl executor is not singular
Ran 7 tests
FAILED (errors=2)
```

Thus the digests are only change tripwires and need a workflow-rooted reviewed
identity, which A77 concedes. But the stronger claim that rolling the digest
graph makes a genuine alternate-client weakening pass all three semantic gates
does not reproduce and is refuted with the experiment above. A source author
can always rewrite both production and its tests; that is a review-root issue,
not evidence that the existing semantic check accepted this weakening.

## A4 experiment - inherited boundary sustained

The exact reviewed head runs 149 Ansible tests: 148 pass, and only the current
host-contract digest versus the historical requirement-1 digest fails. All
four lint profiles and all four syntax checks pass when run separately.

A77 concedes that `set -e` hides those later results in the combined wrapper.
It refutes A4 as a new defect in the F1-F6 implementation. The honest red
fixture is an already disclosed live-evidence boundary and may not be refreshed
by source work. A wrapper redesign may continue independent gates and return
the aggregate failure, but it must retain the stale failure.

## A5 experiment - conceded and raised to High

The build seat appended shell functions named `shellcheck`, `python3`,
`ansible-lint`, and `ansible-playbook` to `infra/tool-versions.env`. The
modified `tools/check-ansible.sh` invocation exited zero without running the
tests, lints, or syntax checks. The independent spend checker still passed
because the nominal data file was outside its source bindings.

The demonstrated result is a complete green bypass of the combined Ansible
gate, so A77 raises A5 from Medium to High. The file must be parsed as inert
data rather than sourced as shell code, and it must enter the reviewed trust
root.

## Authorized next boundary

Jacob authorized a bounded source repair after this adjudication. Its scope is:

1. establish a workflow-pinned A101 trust-root checker for the complete
   readiness execution and gate closure;
2. run the independent spend checker before the stale requirement-1 boundary;
3. replace open-ended shared-process discovery with an explicit module census
   and isolated security-gate processes;
4. parse infrastructure tool versions as data and reject executable content;
5. continue all independent Ansible lint and syntax gates while aggregating
   the honest stale fixture failure; and
6. install source mutations for A1, A2, A3, and A5, run the full repository
   gates, and return the exact result to A78.

The grant authorizes no production worker replacement, host, DigitalOcean,
Anthropic, Console, credential, requirement-1 refresh, acceptance,
requirement-3, rotation, or qualification-flag action.
