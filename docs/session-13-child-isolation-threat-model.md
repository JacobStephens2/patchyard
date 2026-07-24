# Session 13 unified child isolation threat model

Status: declared before implementation and before any Session 13 negative
fixture run.

## Decision

Use one root-owned, systemd-activated, scoped helper on the control-plane host
for both adversarial review and browser evidence jobs. The hardened
`factory-supervisor` remains `User=factory-manager`,
`NoNewPrivileges=true`, and `ProtectSystem=strict`. It writes a typed manifest
and bounded inputs into a new private staging directory, asks systemd to start
only `patchyard-child@<uuid>.service`, and waits for a terminal result.

The helper accepts two closed job kinds:

- `review`: one exact-SHA, read-only worktree plus the typed A87 review packet;
  no network in the current provider-free phase-1 configuration.
- `evidence`: one typed capture contract plus one short-lived, one-use preview
  bearer; network egress is the exact leased preview endpoint and required DNS
  only.

The helper creates the same fresh Bubblewrap mount/PID/IPC/UTS boundary for
both kinds. For evidence it additionally creates a fresh network namespace and
host firewall rules before starting Chromium. A fixed DevTools-protocol
controller intercepts every page request before use, rejects any origin other
than the contract origin, and adds the preview capability only to accepted
requests; selectors are data in fixed reviewed controller code, never
caller-supplied JavaScript. The child sees only explicit
read-only inputs, a tmpfs home and secret path, and one new output directory.
For a review, the root helper temporarily makes only the manifest-validated
worktree root traversable, binds that exact path read-only, and restores its
private mode during checked teardown; the supervisor-private parent remains
inaccessible to every other host identity throughout.
It never sees a PostgreSQL socket, GitHub App key, model or vault credential,
repository credential, sibling review, shared scratch, or artifact-tree mount.
The helper destroys its namespace, tmpfs secret, processes, and firewall state
before publishing a terminal execution manifest. Only then may the supervisor
copy validated, bounded outputs into the artifact store.

The helper's systemd/Polkit delegation is deliberately narrower than
`systemd-run`: `factory-manager` may start, stop, or clear the failed state of
only the fixed UUID-templated unit, whose `ExecStart` cannot be supplied or
altered by the caller. Clearing the failed state makes a completed or rejected
instance eligible for systemd garbage collection; it grants no new execution
verb. The helper accepts no command, shell text, mount list, environment name,
destination address, JavaScript, or Chromium argument from a job manifest.

## Alternatives considered

### Direct `systemd-run` transient scopes

Rejected. Authorizing `factory-manager` to create arbitrary transient units
would let the credentialed supervisor choose `ExecStart`, unit properties, and
mounts. A Polkit filter for a large, evolving transient property set would
make the privilege boundary implicit and difficult to audit. The fixed helper
uses systemd for activation and lifecycle without delegating unit construction.

### Run both children on the worker's Firecracker runtime

Rejected for this control-plane child class. Firecracker remains the correct
implement-worker boundary, but the current worker is a single serialized
Fieldbook-parity execution resource. Moving construction reviewers and Chromium
there would couple control-plane review/evidence progress to implement-worker
availability, add browser and reviewer payloads to the parity image, and
expand the management transport and result-image contracts. The no-authority
children do not need a second kernel to protect durable worker state because
they execute on the control plane with no host filesystem or authority mounts
and with a network namespace whose policy is established before untrusted code
starts. If the scoped-helper boundary fails qualification, Firecracker is the
predeclared escalation path, not a second simultaneously supported mechanism.

### Weaken the supervisor unit

Rejected by A104. Removing `NoNewPrivileges`, reducing `ProtectSystem`, or
granting network-administration capabilities to the process that holds the
GitHub App key and ledger access would enlarge the highest-value compromise
boundary. The supervisor's existing hardening is an invariant and is tested
as part of the Session 13 exit.

## Assets and attacker

The attacker controls request text, source code at the reviewed SHA, page HTML,
CSS, images, subresources, response headers, redirects, DNS answers after the
initial lease check, filenames, selector matches, browser renderer behavior,
and every byte a child writes to its output directory. The attacker may crash,
hang, fork, or intentionally exceed limits.

Protected assets are the GitHub App private key and token, factory PostgreSQL
socket and rows, model-provider credentials, vault capabilities, repository
credentials, factory management identity, artifact tree (including other
runs' transcripts and screenshots), preview bearer, private Patchyard fleet, cloud
metadata endpoint, control-plane host, sibling-review independence, and the
supervisor's availability.

The scoped helper and reviewed child programs are trusted deterministic code.
Systemd, Bubblewrap, the kernel namespace/firewall implementation, and Chromium
are trusted computing base. PostgreSQL, GitHub, the vault, the implement
worker, and the orchestration host are not runtime dependencies of the helper.

## Typed evidence contract

The evidence manifest permits only:

- one credential-free HTTPS URL on the leased numbered preview host;
- one expected 40-character lowercase Git SHA;
- one to eight unique ID selectors matching the fixed selector grammar;
- a bounded list of enum actions (`wait_for`, `extract_select`, `screenshot`);
- navigation, action, and total timeouts at or below the compiled ceilings;
- compiled maximum sizes for DOM, screenshot, extracts, hashes, and execution
  manifest.

Every redirect target and observed HTTP(S) request is re-parsed and compared
with the exact allowed origin before the request continues. Host resolution is
checked twice before launch; the allowed IPv4 set is installed into the
network-layer rule and pinned for
the browser. A changed set fails before Chromium starts. The firewall starts
from deny-all, permits the pinned preview addresses on TCP 443 and the declared
resolver addresses on TCP/UDP 53, and therefore denies metadata, loopback,
link-local, RFC 1918, CGNAT, ULA, and the rest of the private fleet unless one
is the preview lease itself (private preview targets are never accepted).

The preview lease manager issues a random capability bound to one lease ID,
slot, exact SHA, origin, capture ID, and expiry no more than five minutes after
issuance. The preview edge accepts it only while that hashed capability record
is active and translates it to the preview's existing authority on an internal,
no-egress Docker network. The long-lived preview authority never leaves the
preview host. The envelope is staged only beneath `/run` tmpfs, mounted
read-only into the child, and destroyed on every exit path. The scoped helper
revokes the remote capability after the child ends; revocation failure
overrides every other outcome with `teardown_failed`. Output validation rejects
the bearer bytes and capability ID in every returned file.

## Predeclared negative-fixture inventory

Every fixture must produce exactly its named terminal state and no accepted
evidence artifact:

| ID | Attack | Required terminal state |
| --- | --- | --- |
| S13-N01 | One or more HTTP redirect responses, including a return to the allowed origin | `redirect_blocked` |
| S13-N02 | The preview name returns a different address set between policy check and launch | `dns_binding_changed` |
| S13-N03 | HTML requests an HTTP(S) subresource from another origin, including one sharing the preview IP | `cross_origin_blocked` |
| S13-N04 | Page attempts `window.open`, target-blank navigation, or another top-level browsing context | `popup_blocked` |
| S13-N05 | Navigation or a page action attempts a download or attachment response | `download_blocked` |
| S13-N06 | DOM, response, screenshot, extract, transcript, or manifest crosses its byte ceiling | `output_limit_exceeded` |
| S13-N07 | Page or output attempts to disclose the bearer value/capability ID through DOM, URL, subresource, console, or returned file | `bearer_disclosure_blocked` |
| S13-N08 | Chromium exits, is killed, loses its DevTools channel, or fails before a complete manifest | `browser_crashed` |
| S13-N09 | In-child probe reaches a credential path, PostgreSQL/management socket, repository credential, sibling/shared scratch, or artifact path | `authority_probe_failed` |
| S13-N10 | In-child probe reaches cloud metadata, a representative private-fleet address, an undeclared DNS server, or any non-preview destination | `egress_probe_failed` |
| S13-N11 | Child forks or hangs past cancellation/timeout | `child_timed_out` |
| S13-N12 | Any process, mount, namespace, tmpfs bearer, active preview capability, staging path, or firewall rule remains after normal, failed, cancelled, or crashed execution | `teardown_failed` |

Positive fixtures are one provider-free review-bearing dry run through the
hardened daemon and one isolated evidence capture whose screenshot, DOM
extract, hashes, and execution manifest are accepted only after the helper
reports complete teardown.

## Fail-closed and cancellation rules

- An absent, malformed, duplicated, stale, symlinked, non-private, or
  caller-owned terminal file is failure, never an empty success.
- A child process never outlives its helper unit. Timeout and cancellation kill
  the complete cgroup, then teardown and residue checks run with a fresh cleanup
  token.
- Cleanup is an explicit checked `close`, not a `Drop` side effect. Cleanup
  failure overrides child success.
- The supervisor holds no Rust lock or database transaction across helper
  activation or child execution.
- The helper's terminal record is create-new plus atomic rename and is accepted
  only when its job ID, kind, input hashes, output hashes, network policy hash,
  and teardown counters match the supervisor's request.
- Browser and review output are untrusted bytes. Schema, count, size, path,
  ownership, link count, file type, and digest checks occur before artifact
  import.
