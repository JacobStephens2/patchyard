# A77 adjudication - A117 source review

## Disposition

The build seat **concedes all six material A78 findings** and **escalates under
A9**. A117 authorized one bounded structural redesign but explicitly added no
repair loop. No source repair, worker replacement, provider request, cap
change, or live A115 attempt follows this adjudication without a new ruling.

## A117-1 - concede

The build seat independently created a local-only user/network namespace,
brought up the same IPv4 veth shape, and installed an output catch-all using
the named rejection counter. With no application traffic it read:

```text
immediate=0
after_5s=10
ipv6_all=0 ipv6_default=0
```

Repeating the experiment after setting both namespace IPv6 controls before
link-up held the counter at zero after five seconds. This resolves the
checkable claim in A78's favor. Because the helper runs before the counter
assertion, the defect can spend the authorized request and then discard its
evidence. Severity high is sustained.

## A117-2 - concede

The exact current expression did not match the representative kernel line:

```text
3: efh1234abcd@efn1234abcd: <BROADCAST,MULTICAST,M-DOWN> ...
```

The bounded `[@:]` form did match. The independent runner check is therefore
ineffective for veth residue. Severity medium-high is sustained.

## A117-3 - concede

Repository search confirms the parent spend checker contained the exact
issuance block, two exact loopback blocks, and a residual provider-capable
command scan. None exists in the current issuance checker, while the issuance
guest still contains the Models call and receives the credential drive and
provider route. The older finite scan is not a proof of one request, but
deleting its coverage without an issuance-specific replacement is a real
regression before the required live requirement-1 rerun. Severity medium is
sustained.

## A117-4 - concede

The build seat appended `--http2` after `--http1.0` in a disposable copy. The
real spend checker passed and all 24 focused spend tests passed. Against a
loopback-only listener, the installed curl emitted:

```text
GET /v1/messages HTTP/1.1
Connection: Upgrade, HTTP2-Settings
Upgrade: h2c
Connection: close
```

Last-option-wins behavior defeats the intended HTTP-version primitive while
the source gates stay green. Severity medium is sustained.

## A117-5 - concede

The build seat replaced the admit rule's exact provider destination with
`0.0.0.0/0` in a second disposable copy. The real spend checker and all 24
focused spend tests remained green. The mutation demonstrates that the new
closure binding is incomplete. Severity medium is sustained.

## A117-6 - concede

The source confirms the five counter/set comparisons are one silent shell
assertion. Failure reaches only the generic stage/line trap, and the runner
allowlist has no cardinality record. A117-1 makes this a likely paid failure,
not a hypothetical diagnostic edge. Severity medium is sustained.

## Nonblocking observations

The eight A78 observations are accepted as review notes. None changes the stop
decision. The same-principal symlink race, parent-directory residue, installed
mode check, and unlinked-namespace holder concerns would be candidates for a
future authorized repair, but were not independently promoted to material
findings in this adjudication.

## Stop state

- Commit `1ef616e` remains the reviewed A117 source revision.
- Draft PR #79 remains unqualified and must not merge.
- Worker `588590370` remains quarantined and unchanged.
- The operator-reported workspace cap remains restored to $50.00; no console
  action occurred in this review.
- Requirement 3 and behavioral acceptance remain unopened.
- All 13 provider qualification flags remain false.
- No bare `ANTHROPIC_API_KEY` or long-lived Anthropic key was introduced.

A further source change requires Jacob to decide whether to authorize one more
bounded repair. If authorized, the smallest consolidated scope is the six
conceded material findings above, followed by another A78 source review and a
separately reviewed clean-worker replacement plan. It would not add a provider
attempt or enlarge A115's live A9 budget.
