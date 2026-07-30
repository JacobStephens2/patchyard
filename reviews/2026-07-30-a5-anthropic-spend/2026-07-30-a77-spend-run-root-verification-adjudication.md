# A77 adjudication - A115 spend run-root verification repair

## Scope

The build seat adjudicated A78's review of exact commit
`520663f25cbaf862d252067e9ca5d933b00b0e9b`. The requested long object in the
review prompt was a transcription error and did not resolve; both seats
verified that the unique short ID, HEAD, and parent identify the exact commit
above. No source repair, worker access, infrastructure mutation, credential
flow, provider request, Console action, or qualification-flag change occurred
during adjudication.

## Verdict and material findings

A78 returned **PASS with no material findings**. The build seat sustains that
verdict. The focused suite independently passed 25 of 25 tests, including all
36 real-checker source mutations. The complete application wrapper passed.
OpenTofu validated all three roots, all eight direct Ansible lint/syntax checks
passed, and 139 of 140 Ansible tests passed; the only failure is the deliberately
stale requirement-1 host-contract fixture. There is therefore no material A78
claim to concede, refute, or escalate.

## N1 - concede fact; sustain nonblocking disposition

The build seat independently reproduced the curl behavior without network. It
made the curl config, request, and output directory unreadable, then used a
local `file:///etc/hosts` source. Curl returned 23 and emitted:

```text
Warning: error trying read config from the ... file
Warning: Couldn't read data from file ..., this makes an empty POST.
Warning: Failed to open .../raw/headers
curl: (23) Failed writing received data to disk/application
000
```

This sustains A78's factual observation and strengthens the ordinary-mode-bit
diagnosis of the live stop. It does not establish whether Anthropic received
the historical attempt, and the record continues to make no receipt, status,
spend, or credential-exposure claim.

The narrower one-shot file preflight opportunity is also factual: source
inspection finds no identity-scoped readability check for the `0400` config or
request and no identity-scoped write check for the raw response paths before
curl. It predates the run-root repair, is outside the authorized M1/M2 scope,
and does not defeat the repaired ancestor traversal post-condition. A78 found
the exact repair fit for a separately reviewed replacement plan. No N1 source
repair is authorized or required by this adjudication.

## N2 - concede fact; sustain nonblocking disposition

The direct test asserts `staging < RESULT_EXTRACT` and
`staging < CAPABILITY`, not the separate `RESULT_EXTRACT < CAPABILITY` leg.
The production checker does assert the complete chain, and the permanent
missing-anchor mutations require its controlled diagnostic. This test-shape
asymmetry is not a material gap.

## N3-N4 - prior dispositions retained

Concede the unchanged factual limitations and refute any new-defect
classification. Symlink following and D1/D3/D4/D5 were already independently
adjudicated after the prior A78 review. Commit `520663f` neither expands nor
relies on them differently.

## N5 - concede reviewer boundary; refute an overall gate gap

A78 correctly states that it did not rerun network-dependent OpenTofu
initialization or the full application wrapper. The build seat did: all three
OpenTofu roots validated and the complete application wrapper passed on the
exact repair tree. The review record distinguishes reviewer proof from
build-seat proof, so no claim is overstated.

## N6 - concede

`tools/check-ansible.sh` stops after the honest stale requirement-1 unit-test
failure. Both seats ran the four production lint profiles and four syntax
checks directly; all eight passed. No repair is needed.

## Final disposition

A78 PASS is sustained. The authorized M1/M2 repair and its review are complete.
The next permissible action is preparation of a separate, mechanically pinned
clean-worker replacement plan for review. This adjudication does not authorize
applying such a plan, clearing taint, reusing worker `588778422`, issuing a
credential, making a provider request, changing a cap, beginning behavioral
acceptance or requirement 3, or changing any provider qualification flag.
A119 remains reserved, and this operational grant remains in the requirement-2
work record rather than the decision log.
