# A118 bounded source repair

## Scope

Jacob authorized one additional bounded source repair after the A117
adjudication. A118 is limited to the six conceded material findings A117-1
through A117-6. It authorizes no worker plan or mutation, provider request,
credential issuance, cap action, requirement 3 work, behavioral acceptance, or
qualification-flag change.

## Repairs

### A117-1 - namespace IPv6 preflight

The launcher now sets `net.ipv6.conf.all.disable_ipv6=1` and
`net.ipv6.conf.default.disable_ipv6=1` inside the new provider namespace before
the veth is created or moved. After setup and before the paid helper, a separate
preflight reads `all`, `default`, and `eth0` and requires all three values to be
one. A failure emits a bounded preflight diagnostic and stops before the
credential is consumed. The accepted transport receipt records
`namespace_ipv6_disabled: true`.

### A117-2 - independent veth readback

The control-plane residue check accepts the kernel's `name@peer:` and plain
`name:` forms with `efh[0-9a-f]{8}[@:]`. The focused test binds the exact
expression.

### A117-3 - requirement-1 guest scan

`tools/check-anthropic-issuance.py` now owns the exact issuance Models block,
the exact loopback health block, the exact loopback parity block, and the
residual provider-capable-command scan. A behavioral test removes the stale
live fixture from a disposable copy, proves the static preflight is green, adds
an extra guest curl call, and requires the real issuance checker to fail.

### A117-4 - HTTP and curl configuration closure

The spend checker rejects competing HTTP 0.9, HTTP 1.1, HTTP 2, and HTTP 3
options in addition to retry, redirect, parallel, and next-transfer controls.
It requires one config argument, the exact header-only generator, four exact
config references, one config path, and the complete one-shot source digest.
The complete installed helper remains part of the spend host-contract digest.

### A117-5 - complete namespace-policy binding

The entire namespace nftables construction - tables, drop policies, dynamic
sets, named counters, input closure, exact provider/interface/source/port/new
admit rule, used-source rejection, later-new rejection, and terminal rejection
- is one marked block. The checker independently verifies the block's SHA-256,
rather than accepting selected suffixes.

### A117-6 - cardinality diagnostic

If the admitted-new packets, rejected packets, admitted IDs, rejected IDs, or
used sources differ from `1,0,1,0,1`, the launcher publishes all five bounded
integers in order before failing. The control-plane sanitizer accepts only the
five-integer shape.

## Local experiments retained

No provider or external-network action occurred. The build seat independently
reproduced the pre-repair defect in a local-only namespace:

```text
immediate=0
after_5s=10
ipv6_all=0 ipv6_default=0
```

With IPv6 disabled before link-up, the same catch-all counter remained zero
after five seconds. The veth format experiment rejected the old expression and
accepted `[@:]`. A loopback listener showed that `--http1.0 --http2` caused
curl to send HTTP/1.1 upgrade headers, establishing the last-option-wins defect
that the repaired checker now rejects.

## Mutation set

The focused suite runs the real spend checker against disposable source copies
and requires failure for each of these weakenings:

1. append HTTP/2 after HTTP/1.0;
2. add a curl `next` record to the config generator;
3. add a second Messages URL;
4. weaken admitted-new equality;
5. replace the exact provider destination with `0.0.0.0/0`;
6. change the terminal namespace rejection to acceptance;
7. re-enable namespace IPv6;
8. restore the broken veth residue expression;
9. remove the five-value cardinality diagnostic; and
10. add a Messages call back to the spend guest.

The issuance suite separately adds an extra Models call to the credentialed
guest and requires its real checker to fail. A78 source re-review remains the
next gate before any clean-worker replacement plan.
