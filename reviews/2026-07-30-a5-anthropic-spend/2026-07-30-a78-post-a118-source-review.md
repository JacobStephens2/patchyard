# A78 post-A118 source review

## Review configuration

- Reviewer seat: A78, Opus 5, effort `max`
- Exact reviewed commit: `4a1fb529898da139fe982872199a7fef9e32e3a9`
- Review surface: detached worktree containing that commit
- Provider, worker, credential, cap, and acceptance actions: none

## Verdict

**Findings.** The post-A118 binding rejects all fifteen authored mutations but
does not bind the complete executed transport path. Four source-only
weakenings pass both the real checker and all 24 focused spend tests.

## P1 - later function definitions replace the hashed definitions - high

The digest covers the first textual `setup_provider_transport` and
`assert_provider_transport_preflight` definitions. Bash executes the last
definition. A later preflight definition returning success passes the checker.
A later setup definition written with the equivalent two-line brace form also
evades the checker's declaration count.

The reviewer constructed a runtime-viable replacement setup that retained the
objects needed by downstream cardinality checks while removing the used-source
guard, terminal rejection, host destination and port qualifications, IPv6
writes, and drop policies. The real checker and all 24 focused tests passed.

The binding must cover the executed launcher or prove the singularity of every
equivalent function declaration form, not only one textual spelling.

## P2 - the preflight call can be moved into dead code - high

The checker searches for an indented preflight-call substring and compares its
position with the setup and one-shot substrings. Moving the call into
`if false; then` with four-space indentation preserves that substring and its
ordering while preventing execution. A variable-controlled false branch has
the same result. The checker and all 24 focused tests passed both mutations.

The call sequence needs one exact adjacent binding from setup through
preflight to the paid transfer, plus a declaration-and-call cardinality check.

## P3 - counter and set readbacks remain replaceable - high

The hashed region ends before `provider_counter_packets` and
`provider_set_elements`. Replacing those helpers with constants that report
the expected `1,0,1,0,1` cardinalities fabricates the receipt without querying
nftables. The checker and all 24 focused tests passed.

The transport binding needs to include both readback helper bodies. Extending
the current region through the closing brace before `remove_runtime` produced
the reviewer-computed digest
`d20a2cab8640cae9c128c0c221766ce156c1c29e6973831e2ab5b980fe70dab4`
for the reviewed source, but no repair was made during review.

## P4 - commands can be inserted between setup and the paid transfer - medium

An inserted host `nft` accept rule after setup and before the one-shot transfer
is outside the digest and is not rejected by the call-order check. It removes
the host destination, port, and terminal-rejection defense while the namespace
rules remain. The checker and all 24 focused tests passed.

The complete executed sequence needs one binding that excludes intervening
commands capable of changing transport state.

## Verified properties and nonblocking observations

The reviewer independently recomputed the current transport-control digest,
confirmed the intended 177-260 source section is complete, confirmed all
fifteen authored mutations fail, and found no regression in the A114 teardown
repair, A118 evidence schema, secret handling, or qualification flags.

Nonblocking observations:

- a second syntactically different one-shot invocation is not source-bound but
  fails closed at runtime;
- teardown helper bodies remain outside this binding and are only partially
  defended by other checks;
- the mutation harness asserts nonzero status, not the specific checker
  diagnostic, so a checker crash could satisfy it;
- the known requirement-1 live-evidence digests remain stale;
- `tokei` was unavailable in the reviewer environment; and
- the section-scoped work-record claim is accurate, while the broader
  enforcement-document statement that early bypass is impossible is not.

## Review boundary

This was source review only. No source repair, provider action, worker change,
cap change, credential issuance, behavioral acceptance, requirement-3 work,
or qualification-flag change occurred.
