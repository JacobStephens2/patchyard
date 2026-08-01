# A77 adjudication - complete-launcher binding review

## Disposition

The build seat **concedes both material A78 findings** and **escalates under
A9**. Each checkable claim independently reproduced against exact reviewed
commit `36590dc4f549641f63cfa903fe78c009651d8117`. The authorized bounded repair
is complete; no further source repair is implied by this adjudication.

Per the governance-hygiene direction, this adjudication mints no numbered
decision-log ruling. Any later operational repair grant belongs in the
requirement-2 work record, with authorizer, scope, reason, and loop count.

## Finding 1 - concede, high

In one disposable copy, the build seat moved the launcher comparison into an
`if false` branch and removed the one-shot transport comparison. The real spend
checker passed and all 24 focused spend tests passed. A direct Bash control
rejected unequal hashes, while the dead-code version printed
`runner-mismatch-reached`.

In a second disposable copy, the build seat combined the dead launcher
comparison with a later Ansible task writing
`patchyard-run-fixture` to the production launcher destination. The two
source files have different SHA-256 values:

```text
c2b4275704ab0447a08e157be994a0bd18e505a843f1a017ce496220f3e83928  patchyard-firecracker-run
4f106114a3dd8c1e15f228dc1794d6d1b73715c57c67a37bfa0e3581903793e0  patchyard-run-fixture
```

Despite the later writer, the real spend checker and all 24 focused tests
passed. The worker-runtime, worker-qualification, stack, and independence
checks passed, and `ansible-lint site.yml` reported zero failures and zero
warnings.

The repository digest therefore does not bind the program executed at the
worker path. Removing the bearer-holding one-shot comparison in the same
unbound runner is at least as consequential. High severity is sustained.

## Finding 2 - concede, medium

In a third disposable copy, the build seat placed the credential-drive and
provider-hosts absence assertions inside `if false`. The real spend checker and
all 24 focused tests passed. A direct Bash experiment confirmed the absence
guard was skipped.

In a fourth disposable copy, the build seat wrapped the receipt cardinality and
boundary predicates in `true or (...)`. The real spend checker and all 24
focused tests passed. `jq -n -e 'true or (false)'` independently confirmed the
short-circuit result.

The guest's independent boundary confirmation can therefore be removed while
the source gate remains green. Launcher-side enforcement remains, so medium
severity is sustained.

## A77 conclusion

Both findings are checkable, reproduced, and conceded. Refutation is not
supported by the evidence. A smallest credible repair would:

1. bind the complete issuance runner source and independently mirror that
   digest in the focused test;
2. require singular Ansible writers for the launcher and one-shot destinations;
3. bind the complete spend guest source rather than its boundary substrings;
4. add dead-code launcher comparison, self-comparison, removed transport
   comparison, duplicate destination writer, dead guest absence, and
   short-circuited receipt mutations; and
5. retain controlled source-specific diagnostics for every mutation.

That repair is not authorized and has not been implemented.

## Stop state

- Commit `36590dc` remains the exact reviewed source revision.
- Draft PR #79 remains unqualified and must not merge.
- Worker `588590370` remains quarantined and unchanged.
- The operator-reported workspace cap remains restored to $50.00; no console
  action occurred in this repair, review, or adjudication.
- Requirement 3 and behavioral acceptance remain unopened.
- All 13 provider qualification flags remain false.
- No bare `ANTHROPIC_API_KEY` or long-lived Anthropic key was introduced.

Further source repair requires a new bounded authorization. If granted, it is
to be recorded in the requirement-2 work record rather than as A119 or another
per-loop decision-log entry.
