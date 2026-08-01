# A78 adversarial review - A101 F1-F6 structural redesign

## Verdict

**NOT A PASS** - two High findings, one Medium-High finding, one inherited
Medium boundary, and one Medium finding.

Reviewed record commit:
`2a325357810837ee384a2ca22633dee8900029d2`.

Reviewer: A78, Claude Opus 5 at `xhigh` effort through Claude Code 2.1.220 on
Anthropic. The exact reviewed commit was detached in a fresh worktree, which
was clean before and after review. A78 used no subagent and performed no
network, host, cloud, provider, or Console action.

## Verified redesign properties

A78 independently verified all three production identities:

| File | SHA-256 |
| --- | --- |
| `infra/wait-do-worker-firewall.sh` | `5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba` |
| `infra/replace-worker.sh` | `27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e` |
| `tools/check-ansible.sh` | `ead1c23f932f39ec423222f70775304be6453dcd1cd7c24a45b99699d001158e` |

All 7 readiness tests, all 27 Anthropic spend tests, and the independent
Anthropic spend checker passed. A78 reproduced all ten installed mutation
classes. The alternate client, assembled absolute client, sourced sibling,
Bash builtin networking, operator-wide curl, removed ShellCheck member,
zero-test discovery, counter redirection, weakened checker, and re-exposed
counter-path mutations each made an intended gate fail. F5 and F6 from the
prior review are therefore genuinely repaired.

A78 also confirmed the dependency repair is limited to `event-listener`
5.4.2, removal of its unused `concurrent-queue` dependency and exemption, and
the corresponding exact bootstrap-exemption rollover. It made no Patchyard audit
claim.

## A1 - readiness trusts an unpinned transitive state oracle

Severity: **High, material**.

`infra/wait-do-worker-firewall.sh` obtains its worker and firewall identities
through `infra/tofu.sh`, but the new complete-source bindings do not bind that
script. A78 inserted inert alternate clients and a state-output override in
`infra/tofu.sh`. The independent spend checker still passed, and complete
Ansible discovery added no failure beyond the disclosed stale requirement-1
fixture.

The same transitive-trust issue reaches the operator's unpinned
`infra/ansible/converge.sh` and `infra/ansible/qualify.sh` calls. A source-only
change can therefore alter what the readiness gate observes or what surrounds
it without changing a currently bound identity.

## A2 - open-ended discovery shares one mutable Python process

Severity: **High, material** as reported by A78.

`tools/check-ansible.sh` uses open-ended unittest discovery. A preceding,
unpinned module can mutate interpreter globals before the readiness and spend
modules load. A78 modified `test_anthropic_issuance.py` to replace
`hashlib.sha256`, then changed the helper. Discovery accepted the forged
source identities and added no failure beyond the existing stale issuance
fixture.

The independently launched spend checker is a separate process and does not
inherit that monkeypatch. Its invocation, however, occurs after the stale
issuance checker in `tools/check-infra.sh`, so the current wrapper stops before
reaching it. Neither the invocation ordering nor the workflow membership is
part of a trust-root binding.

## A3 - the digest graph has no repository-external root

Severity: **Medium-High, material** as reported by A78.

The helper, wrapper, test, and checker digests form an acyclic graph entirely
inside the repository. A78 reported that changing the helper and rolling the
dependent constants can make the checker, readiness suite, and spend suite
agree on the new identities. The hashes therefore detect an isolated source
change but do not, by themselves, establish which complete source set was
reviewed.

## A4 - the Ansible wrapper remains red at requirement 1

Severity: **Medium, inherited**.

The exact-head Ansible wrapper fails on the deliberately stale Anthropic
issuance host-contract fixture. Because the wrapper uses `set -e`, it stops
before the Ansible lint and syntax stages. The individual lint profiles and
syntax checks pass when launched separately. Refreshing the fixture without a
new live requirement-1 run would be false evidence and remains outside this
work's authority.

## A5 - executable tool-version loading can bypass the wrapper

Severity: **Medium, material** as reported by A78.

The source-bound Ansible wrapper executes
`source "$REPO_ROOT/infra/tool-versions.env"`, but that sourced file is not
bound. Function definitions in the nominal data file can shadow
`shellcheck`, `python3`, `ansible-lint`, and `ansible-playbook`. A78 demonstrated
a modified file that made the wrapper exit zero without running those gates.

## Nonblocking observations

- The quote normalizer is incomplete, although complete-source binding caught
  the installed forms A78 exercised.
- The helper has no semantic alternate-client census independent of complete
  source identity.
- The source-expression check does not recognize every spelling of a guarded
  dot command.
- The operator network rule is a substring restriction rather than a parsed
  command allowlist.
- The spend test's identity remains an in-repository binding rather than a
  workflow trust root.

## Review safety

All mutations were local and disposable. No mutation opened a socket or
invoked a real network client. A78 read no environment credential and made no
GitHub, DigitalOcean, Anthropic, SSH, Ansible, OpenTofu, worker, Console,
acceptance, requirement-1, requirement-3, rotation, or qualification action.
