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
  bearer; network egress is the exact leased preview endpoint only.

The helper uses the same fixed Bubblewrap mount/PID/IPC/UTS/cgroup/network
construction for both kinds. Before untrusted code starts, a trusted probe runs
in a disposable instance of that construction and writes into a probe-only
directory. The helper validates the result, makes it root-only, and never
mounts that directory or the probe executable into the subsequent
reviewer/browser stage. The tested party therefore cannot forge its
attestation. The helper deliberately denies user namespaces: privileged
setup retains only `CAP_SETUID` and `CAP_SETGID`, then a fixed `setpriv`
wrapper becomes `nobody` with zero effective capabilities before any probe,
harness, reviewed source, or browser code executes. For evidence the helper
joins that child to a fresh routed network namespace and establishes host
firewall rules before starting Chromium. A fixed DevTools-protocol
controller intercepts every page request before use, rejects any origin other
than the contract origin, and adds the preview capability only to accepted
requests; selectors are data in fixed reviewed controller code, never
caller-supplied JavaScript. The child sees only explicit
read-only inputs, a tmpfs home and secret path, and one new output directory.
For a review, the root helper temporarily makes only the manifest-validated
worktree root traversable, binds that exact path read-only, and restores its
private mode during checked teardown; the supervisor-private parent remains
inaccessible to every other host identity throughout. Private inputs,
worktrees, secrets, and output exchanges are opened by the helper and passed
to Bubblewrap as file descriptors, so the target UID never gains pathname
traversal through their private host parents.
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

Live evidence qualification uses
`factory-evidence-qualification.service`, a fixed one-shot entry point to the
same Rust `EvidenceCapture` and `IsolatedChildSpawner` path. It runs as
`factory-manager` with `NoNewPrivileges=true`, `ProtectSystem=strict`, no
database or GitHub environment, and `AF_UNIX` only. A root-owned staging
command obtains the one-use capability through the credential-free preview
bridge, writes the fixed capture contract into `/run` tmpfs, starts the
qualification service, validates its terminal proof, prints only a
secret-free summary, and removes the qualification input and result. The
one-shot service is a qualification caller, not another isolation boundary:
both review and evidence still cross only the UUID-templated child helper.

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
from deny-all and permits only the pinned preview addresses on TCP 443.
Chromium receives the same stable set through a private `/etc/hosts`; no
resolver configuration or DNS egress is present. Metadata, loopback,
link-local, RFC 1918, CGNAT, ULA, public DNS resolvers, and the rest of the
private fleet are denied (private preview targets are never accepted).

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
  token. The template's fixed `ExecStopPost` reaper also runs after a killed
  launcher, removes deterministic namespace/veth/nft/mount/secret residue, and
  invalidates any terminal that claimed clean teardown before residue was
  found.
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

## Attestation and verification semantics

The boundary distinguishes trusted observations from independent supervisor
verification:

- The fixed probe's seven isolation facts and the fixed browser controller's
  redirect, request, popup, download, final-URL, and disclosure counters are
  **attested observations**. Their producers are reviewed trusted code in the
  declared TCB. The untrusted reviewer, page, renderer, and returned files
  cannot rewrite the probe result.
- The expected SHA is **verified before capture** by the preview lease manager:
  both the host checkout and running preview checkout must equal it before a
  capability bound to that lease, slot, origin, and SHA is issued. The
  execution and hash manifests carry that verified provenance forward; their
  SHA field is an acknowledgement, not a second independent checkout
  measurement.
- The supervisor independently verifies the request digest, exact canonical
  network-policy digest, terminal schema and state/fact relationships,
  per-contract output ceilings, single-link regular-file descriptors, output
  byte lengths and SHA-256 values, artifact-name allowlists, bearer absence,
  secret-path absence, and zero teardown counters before import.

The canonical evidence network policy is the preview host on TCP 443 with
`dns=none`. The privileged helper resolves the name twice, rejects a changed
answer set, writes the stable addresses into a private `/etc/hosts`, and pins
the same set in nftables. Chromium therefore needs no resolver egress, closing
the QNAME covert channel while retaining the PLAN's "required DNS only"
ceiling: for this pinned design, required DNS inside the child is empty.

## Known verification limits and host assumptions

GitHub-hosted CI does not execute the root launcher, create its network
namespace, or apply its nftables policy. Its privileged-launcher suite is
static and source-contract based: checksum-pinned ShellCheck 0.11.0 and
`bash -n` cover the four boundary scripts, while assertions pin the exact
probe separation, DNS-free policy, DNS-change ordering, residue measurements,
and reaper commands. The behavioral proof remains the operator-triggered live
qualification on the converged Rocky control-plane host, through the fixed
staging command and `factory-evidence-qualification.service`; it exercises the
installed systemd, Bubblewrap, namespace, nftables, Chromium, probe, and
teardown path. This division is deliberate; the current GitHub-hosted
environment is not a faithful substitute for that host. A disposable
privileged runner is the predeclared escalation if live qualification can no
longer provide reliable or timely evidence.

The control-plane host is deliberately not a router.
`net.ipv4.ip_forward=0` is versioned Ansible desired state, asserted by the
Session 13 qualifier, and required by the launcher before it creates any
network resource. Evidence networking is serialized by
`/run/lock/patchyard-evidence.lock`; the launcher temporarily enables
forwarding and restores the checked zero baseline. The crash reaper forces
the same zero baseline rather than preserving an unexpected router
configuration. A future need for host routing therefore requires an explicit
isolation redesign rather than an ambient configuration change.

## Qualification results

The provider-free review exit ran through the resident hardened supervisor:

- request `9e5ec323-5c70-4c14-a0c3-0ae327a7b802`;
- run `ded245ab-f7c6-4f26-91ea-3304d0f21af3`;
- exact reviewed Fieldbook SHA
  `fdb9b62ac58ec28730e3076c4cdbaa679708432b`;
- two independent `review.submitted` events followed by `verify.passed` and
  `run.dry_run_complete`;
- no child unit or `/run/patchyard-children` entry after completion.

The live evidence exit leased preview slot 15 at exact Fieldbook SHA
`4ef35181f7a700b02e63808e483d7c23f33b91d8` and completed:

- qualification request `25969aad-e7ce-4733-85e0-43322b5448a0`;
- qualification run `7e55f3b9-3f8e-4b7b-941c-6afc581304ad`;
- isolated job `ab2bb1fc-ca01-4f9d-b4c6-bf06415e2705`;
- five post-teardown imports: DOM
  `28f1d17dee3ec8086f30744491aea4e1a09f63220803fbc480666bf260a3c40b`,
  screenshot
  `d4c1f6039718d268b6ac193b3144d87ce10e3da49b52933ef9519be1bf68461e`,
  extract
  `5e220d5fde8aeebe7e28d09dd366c789a929993b200c5099be2ddcf42fa6d7a0`,
  hashes
  `041726dab380fcf5e749120496f5899e2dada688ccf9dbae21ce74847f2c796f`,
  and execution manifest
  `19352c490866de4685713a85276d5da14e52f954e1fcf63937cbebe6c419230a`;
- all seven isolation facts true and all eight teardown residue counters zero;
- preview release reported `cleanup_complete`, with no child unit, child
  staging entry, network namespace, veth, or child nftables table remaining.

The declared negative inventory is executable at two layers. The real
Chromium suite reaches the named redirect, cross-origin, popup, download,
oversize, bearer-disclosure, browser-crash, and timeout states. The stable
resolver suite changes the answer set between its two production resolution
calls and asserts the process-level exit-42/`dns_binding_changed` contract.
The privileged-launcher contract suite runs mandatory Bash syntax checks,
checksum-pinned ShellCheck, and source-contract assertions for probe-output
separation, the non-router precondition, pre-network DNS-change mapping,
DNS-free egress, real cgroup/mount accounting, and the template reaper. The
Rust boundary fixture asserts all S13-N01 through S13-N12 terminal states,
zero imported artifacts, and empty staging after each case; additional
completed-child fixtures prove that forged probe facts, secret residue,
bearer output, and a per-job output-cap violation are rejected after the
completed-state short-circuit. The live positive child independently runs the
authority and network probes inside the actual Bubblewrap/network namespace;
any reachable protected path or destination maps to
`authority_probe_failed` or `egress_probe_failed` before import.
