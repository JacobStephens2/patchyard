# A78 adversarial source review - A117

## Verdict

**FINDINGS** - six material findings and eight nonblocking observations.

Reviewed commit: `1ef616e6cc4907f20a00b6d0f90aff35dc5ef89c`
(parent `fdc7170`). The detached review worktree was clean and unmodified.

The one-connection primitive itself worked in local experiments: the dynamic
sets admitted one conntrack ID, kept retransmits on that ID, and rejected later
connections. The implemented acceptance predicate is nevertheless
unsatisfiable on the reviewed worker network setup, and it is evaluated only
after the authenticated request.

## Material findings

### A117-1 - idle IPv6 traffic makes the post-request gate unsatisfiable

Severity: **high, blocker**.

`worker/runtime/patchyard-firecracker-run` sends every unmatched namespace
output packet through the named `rejected_new` counter, then requires that
counter to equal zero after the provider transfer. Bringing up the veth causes
the new namespace to emit IPv6 MLDv2, router-solicitation, and duplicate-address
detection traffic. Those packets reach the catch-all even when the application
makes no connection.

A78's exact-rule local experiment read zero immediately and seven rejected
packets after 15 seconds. The first nonzero read occurred after 457 ms. With
IPv6 disabled inside the new namespace before link-up, the counter remained
zero and the intended first-connection-pass/later-connection-reject behavior
held. A new network namespace does not inherit a parent namespace's
`disable_ipv6` values.

The helper makes the paid request before the launcher reads this counter. The
run therefore spends, fails without evidence, and taints the worker. A bounded
repair would disable IPv6 inside the provider namespace before link-up and
independently read both `all` and `default` values before returning from setup.

### A117-2 - the independent provider-veth residue regex cannot match

Severity: **medium-high**.

The control-plane runner searches `ip -o link show` with
`efh[0-9a-f]{8}:`. A veth line places `@peer` between the interface name and
the colon, so provider-veth residue never matches. The launcher still checks
its own action, but A114 requires an independent readback. A bounded pattern is
`efh[0-9a-f]{8}[@:]`.

### A117-3 - requirement-1 guest-wide provider-client binding was removed

Severity: **medium**.

A117 removes the earlier exact issuance block, loopback block, and residual
provider-capable-command scan from `tools/check-anthropic-spend.py` without
moving an equivalent binding to `tools/check-anthropic-issuance.py`.
Requirement 1 still delivers its bearer and provider route to the guest, and
the changed image and host contract are scheduled for a live requirement-1
rerun. A bounded repair would restore the issuance-specific exact blocks and
residual scan in the requirement-1 checker, excluding only the retired spend
Messages block.

### A117-4 - a later HTTP-version option defeats the HTTP/1.0 binding

Severity: **medium**.

The checker requires `--http1.0` to be present but does not reject a later
`--http1.1`, `--http2`, or `--http3` option. A78 appended `--http2`; the
checker and focused suite stayed green, while local curl used HTTP/1.1 upgrade
semantics and displaced the intended connection behavior. Over TLS, HTTP/2 can
multiplex requests on the sole admitted conntrack ID. The generated curl
configuration is also outside the extracted transfer block's option checks.

A bounded repair would reject every competing HTTP-version option and bind the
configuration generator to header-only records, one `$AUTH_CONFIG` reference,
and one `--config` option.

### A117-5 - security qualifiers on the nft admit rule are unbound

Severity: **medium**.

The checker binds fragments that add the conntrack ID and used source, but not
the admit rule's interface, source, destination, port, and `ct state new`
qualifiers. It also does not bind both chain drop policies or both terminal
reject rules. Removing the provider destination from the admit rule leaves the
checker and mutation suite green. A bounded repair would bind the complete
admit rule and both closure paths rather than isolated suffixes.

### A117-6 - cardinality failure loses the observed counters

Severity: **medium**.

The five-way shell assertion emits only the generic worker stage, source line,
and status. The runner has no allowlist entry for a bounded cardinality
diagnostic. Because the namespace is removed on failure, operators cannot
recover which value failed after an already-spent request. A bounded repair
would emit and allowlist the five integer values before failing.

## Nonblocking observations

1. The A117 design record reports connection-set cardinalities but not a clean
   single-connection sample of the packet counter that A117-1 breaks.
2. Several receipt fields are launcher-authored constants; the guest comparison
   is a tamper check, not independent corroboration.
3. Some documentation says rejected connections where the code separately
   measures rejected packets and rejected conntrack IDs.
4. Root writes the bearer configuration into a subordinate-owned directory,
   leaving an avoidable same-principal symlink race.
5. `/etc/netns` itself may remain after the per-run directory is removed.
6. The launcher checks the transport executable for executable/not-symlink but
   not its exact installed ownership and mode; the runner catches digest drift.
7. Namespace removal is checked by name and would not detect an unlinked
   namespace retained by a surviving process; no such holder exists today.
8. The issuance live result remains stale. A78 reproduced the same checker
   failure on parent `fdc7170`, so this is disclosed pre-existing evidence
   state, not a new A117 regression.

## Review execution

A78 ran Claude Code with `claude-opus-5` at `xhigh` effort. The first model
transport failed mid-response after stating only that a reproducible defect
existed; no incomplete claim from that run was used. A fresh resumable A78 run
independently completed this report.

The completed review used Read, Grep, and local Bash actions. It ran the spend
checker, all 24 spend tests, source/digest inspection, exact nftables rules in
local user/network namespaces, local-only listeners, link-format tests, and a
loopback curl HTTP-version experiment. The spend checker and focused suite
passed despite the A117-4 weakness. The issuance checker had the disclosed
four stale-evidence errors on both the reviewed commit and its parent.

No provider, worker, console, credential, cap, or external-network action
occurred. No Anthropic or other provider request was made. All network
experiments were confined to loopback or disposable local namespaces.
