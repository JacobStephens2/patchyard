# A77 adjudication - post-A118 source review

## Disposition

The build seat **concedes all four material A78 findings** and **escalates
under A9**. Each checkable claim reproduced against exact reviewed commit
`4a1fb529898da139fe982872199a7fef9e32e3a9`. The authorized bounded repair is
complete; no second repair is implied by this adjudication.

Per the governance-hygiene direction, this adjudication mints no numbered
decision-log ruling. Any later operational repair grant belongs in the
requirement-2 work record, with authorizer, scope, reason, and loop count.

## P1 - concede, high

In a disposable copy, the build seat added later definitions of both transport
functions after the hashed region. The setup used the equivalent form:

```bash
setup_provider_transport()
{
  return 0
}
```

The preflight replacement also returned success. The real checker passed and
all 24 focused spend tests passed. A separate Bash experiment defined the same
function twice and printed `second` from the second definition, confirming
last-definition execution.

The existing digest can therefore remain valid while neither hashed function
is the function executed by the spend path. The complete transport enforcement
can be replaced without invalidating the claimed binding. High severity is
sustained.

## P2 - concede, high

In a separate disposable copy, the build seat changed the direct preflight call
to:

```bash
if false; then
  assert_provider_transport_preflight
fi
```

The real checker passed and all 24 focused spend tests passed. The required
substring remains present and ordered, but Bash cannot execute the preflight.
The source binding therefore does not establish the required fail-closed
readback. High severity is sustained.

## P3 - concede, high

In a separate disposable copy, the build seat made the two unbound readback
helpers return constants before their nftables queries. The counter helper
returned one only for `admitted_new`; the set helper returned zero only for
`rejected`. Those values fabricate the exact accepted cardinalities while the
real queries remain unreachable.

The real checker passed and all 24 focused spend tests passed. The evidence
receipt can therefore claim transport enforcement without reading the provider
namespace state. High severity is sustained.

## P4 - concede, medium

In a separate disposable copy, the build seat inserted this valid host rule
between setup and preflight:

```bash
nft insert rule inet "$PROVIDER_NFT_TABLE" forward \
  iifname "$PROVIDER_HOST_VETH" counter accept
```

Because `insert` places the rule before the setup-created qualified rules, it
accepts forwarding from the provider namespace without the bound destination
or port. The namespace layer remains, but one of the two independently claimed
egress boundaries is gone. The real checker passed and all 24 focused spend
tests passed. Medium severity is sustained.

## A77 conclusion

All four findings are checkable, reproduced, and conceded. Refutation is not
supported by the evidence. A smallest credible repair would bind:

1. every executable definition of the setup and preflight functions;
2. the exact adjacent setup, preflight, and one-shot call sequence;
3. both counter and set readback helpers; and
4. the absence of transport-changing commands between setup and transfer.

A whole-launcher digest is the simplest structural design identified by the
review, provided its update and mutation procedure prevents a decorative hash.
That design is not authorized and has not been implemented.

## Stop state

- Commit `4a1fb52` remains the exact reviewed source revision.
- Draft PR #79 remains unqualified and must not merge.
- Worker `588590370` remains quarantined and unchanged.
- The operator-reported workspace cap remains restored to $50.00; no console
  action occurred in this review or adjudication.
- Requirement 3 and behavioral acceptance remain unopened.
- All 13 provider qualification flags remain false.
- No bare `ANTHROPIC_API_KEY` or long-lived Anthropic key was introduced.

Further source repair requires a new bounded authorization. If granted, it is
to be recorded in the requirement-2 work record rather than as A119 or another
per-loop decision-log entry.
