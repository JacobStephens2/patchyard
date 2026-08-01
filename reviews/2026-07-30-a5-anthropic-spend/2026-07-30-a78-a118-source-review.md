# A78 adversarial source review - A118

## Verdict

**FINDINGS** - one medium and one low material finding. All six intended A118
repairs are present and effective where behaviorally checkable. The remaining
findings are binding-completeness gaps in the new policy closure.

Reviewed commit: `0b7b6ceb29bcd46f6d12b90c83efdec64015ab71`
(parent `44c7704`). The detached review worktree was clean and unmodified.

## Material findings

### A118-1 - the digest binds a region, not the complete construction

Severity: **medium**.

The namespace-policy digest covers only the marked nftables block in
`setup_provider_transport`. It does not constrain additional namespace rules
after the end marker. An `nft insert` after the marker can prepend an
unqualified new-connection acceptance rule, making the bound destination,
interface, source, port, and state qualifiers dead code.

A78 added this rule immediately after the end marker in a disposable copy:

```bash
ip netns exec "$PROVIDER_NETNS" nft insert rule inet eta_anthropic_one_shot output \
  ct state new add @admitted '{' ct id '}' add @used '{' ip saddr '}' \
  counter name admitted_new accept
```

The real spend checker passed and all 24 spend tests passed. A local namespace
experiment used a destination and port deliberately different from the bound
provider address:

```text
baseline  curl_rc=7 http=000 final=0,1,0,1,0
weakened  curl_rc=0 http=200 final=1,0,1,0,1
```

The weakened path therefore reaches an arbitrary worker-host-local endpoint
and publishes exactly the accepted cardinalities. The host forwarding chain
still restricts forwarded external traffic unless it is weakened separately.

Smallest repair: move the begin marker to the first line of
`setup_provider_transport`, move the end marker to its last line, and re-pin
the policy digest so the marked region is the whole construction.

### A118-2 - adjacent transport controls remain unbound

Severity: **low**.

The marked policy excludes the host provider forward/postrouting construction.
The checker also requires IPv6 write/readback strings and their ordering, but
does not bind the exact three-way preflight comparison.

A78 tested two disposable mutations:

- replace the host-forward provider destination with `0.0.0.0/0` and its
  terminal rejection with acceptance; and
- replace the preflight's three-way OR comparison with an ineffective
  three-way AND comparison containing an impossible `eth0 != 9` term.

The real spend checker and all 24 spend tests passed in both copies. The IPv6
writes remain in place, so its mutation removes defense in depth rather than
the primary control.

Smallest repair: include the host transport construction in the whole-function
digest described under A118-1, and require the exact preflight comparison in
the checker.

## Verified sound

- IPv6 `all` and `default` are set before veth creation, the moved `eth0`
  inherits the setting, and `all`, `default`, and `eth0` are read before the
  helper. A78 measured no named-counter change through ten seconds of
  post-request idle time. A second connection changed the cardinality and
  failed closed.
- The new veth residue expression matched real kernel `name@peer:`,
  same-namespace peer, and plain-name forms.
- The requirement-1 checker rejects a provider-capable command outside its
  three exact issuance and loopback blocks.
- The complete one-shot helper digest, exact header-only config, singular
  config path, one client, one URL, and competing HTTP-version rejection held.
- Mutations inside the marked namespace-policy block changed its digest and
  failed the checker.
- All five cardinality values survive through the launcher diagnostic and the
  runner sanitizer without admitting non-integer or secret-bearing forms.
- A114 teardown behavior, evidence schema, digest checks, secret handling, and
  the thirteen false provider qualification flags did not regress.

## Nonblocking observations

1. The restored historical requirement-1 command-name scan does not include
   every interpreter class covered by the spend checker.
2. Explicit `exit 1` preserves the five cardinality values but the taint marker
   reports an unknown source line.
3. The existing `jq` secret predicate accepts one trailing newline; curl does
   not turn that shape into a second config record.
4. The host veth can emit IPv6 into the namespace, but the input drop policy
   does not increment the named output counter.
5. The issuance live evidence remains stale, as disclosed before A118.
6. A78 could not run the pinned codebase projection tool in its isolated
   environment; the build seat's full application gate did run it successfully.
7. The A117 nonblocking notes concerning launcher-authored constants, the
   same-principal write surface, parent-directory residue, installed mode, and
   an unlinked namespace holder remain outside A118.

## Review execution

A78 ran Claude Code with `claude-opus-5` at `xhigh` effort. It used source
inspection and disposable local-only Bash experiments. It ran the real spend
checker and all 24 spend tests against the mutations, exercised exact nftables
behavior in local user/network namespaces, and checked real link-name forms.

No provider, worker, console, credential, cap, or external-network action
occurred. No Anthropic or other provider request was made.
