# A77 adjudication - A118 source review

## Disposition

The build seat **concedes both material A78 findings** and **escalates under
A9**. A118 authorized one bounded source repair of A117-1 through A117-6; it
did not add another repair loop. No further source repair, worker replacement,
provider request, cap change, or live A115 attempt follows this adjudication
without a new ruling.

## A118-1 - concede

The build seat independently added the unqualified `nft insert` immediately
after the end marker in a disposable source copy. The real spend checker passed
and all 24 spend tests passed.

The build seat then independently installed the exact namespace rule shape in
disposable local user/network/mount namespaces. The baseline tried a local
endpoint outside the bound destination and port; the weakened case added the
post-marker rule:

```text
baseline curl_rc=7 http=000 final=0,1,0,1,0
weakened curl_rc=0 http=200 final=1,0,1,0,1
```

The mutation both bypasses the bound qualifiers and produces the exact accepted
cardinalities. A single change reaches arbitrary worker-host-local endpoints;
combined with the separately green host-forward weakening, it can reach
arbitrary forwarded destinations. Severity medium is sustained.

## A118-2 - concede

The build seat made each adjacent-control mutation in a separate disposable
copy:

- host-forward destination `0.0.0.0/0` plus terminal acceptance; and
- ineffective three-way AND IPv6 comparison.

For each copy, the real spend checker passed and all 24 spend tests passed.
The host mutation expands the forwarded egress boundary. The preflight mutation
removes an independent verification but leaves the IPv6 writes intact.
Severity low is sustained for the combined finding.

## A77 conclusion

Both findings are checkable, reproduced, and conceded. Refutation is not
supported by the evidence. A118's smallest repair would be:

1. digest the complete `setup_provider_transport` construction rather than a
   nested region;
2. bind the exact IPv6 preflight comparison; and
3. add mutations for an out-of-region namespace rule, the host-forward
   qualifiers and terminal rule, and the comparison itself.

That repair is **not authorized** by A118 and has not been made.

## Stop state

- Commit `0b7b6ce` remains the reviewed A118 source revision.
- Draft PR #79 remains unqualified and must not merge.
- Worker `588590370` remains quarantined and unchanged.
- The operator-reported workspace cap remains restored to $50.00; no console
  action occurred in this review.
- Requirement 3 and behavioral acceptance remain unopened.
- All 13 provider qualification flags remain false.
- No bare `ANTHROPIC_API_KEY` or long-lived Anthropic key was introduced.

A further source change requires Jacob to decide whether to authorize one more
bounded repair. Any such ruling should remain source-only, add no provider
attempt, and leave the separately reviewed clean-worker plan downstream of a
clean A78 source verdict.

## Post-escalation disposition

Jacob subsequently authorized that bounded source-only repair. A119 records
the authorization in `docs/decision-log.md`; its implementation and mutation
record are in `2026-07-30-a119-bounded-source-repair.md`. A119 is limited to
A118-1 and A118-2, adds no live attempt or further repair loop, and leaves the
clean-worker plan downstream of another A78 source review.
