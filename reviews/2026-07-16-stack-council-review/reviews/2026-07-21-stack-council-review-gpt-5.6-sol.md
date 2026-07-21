# Codex outside-council review of the Patchyard Factory stack

*2026-07-21. Target: `reviews/2026-07-21-stack-council-packet.md` at
`c89eb71473a35cceffe87fa3c0560883945e2b3d`. Scope: the technology and
operational architecture at approximately 20 requests per week. The packet's
five invariants are treated as fixed.*

## Verdict

The core stack is appropriate. Keep Rust/Axum, PostgreSQL, SQLx, the local
filesystem artifact store, Caddy/systemd, exec-bound agent harnesses, the
dedicated secret-free worker, and the human-merged PR boundary. Those choices
are not disproportionate merely because throughput is low. The hard property
is safely executing code derived from untrusted input, not serving traffic.

The phase-1 perimeter is nevertheless too broad. It spends build and operating
capacity on a co-located self-hosted CI runner, a new tracing backend,
page-view accounting, and convenience projections while three failures that
can occur at current scale remain underspecified:

1. A restart can strand work if `LISTEN/NOTIFY` is treated as a durable queue
   rather than a wake-up hint.
2. Loss of the control-plane VM can lose the authoritative ledger and evidence
   unless backup consistency, off-host storage, and clean-host restoration are
   proved.
3. Headless Chromium processes agent-modified Fieldbook pages on the same VM
   that holds the ledger, artifacts, and publishing authority. That is the
   first boundary I would attack.

There is also a direct contradiction to fix before build: host placement moves
the publisher onto the dedicated control-plane VM, while the worktree contract
in both SPEC and PLAN still puts credentialed publisher worktrees "on
orchestration." That violates the runtime-independence invariant as written.

My recommended phase-1 adjustment is small but material: use hosted CI, defer
a new Tempo deployment and non-operational dashboard views, and spend the
recovered sessions on crash recovery, a full restore drill, and isolated
evidence capture.

## 1. What is over-engineered at 20 runs per week

### Remove the self-hosted Actions runner from the control plane

Factory-repository CI is credential-free hygiene, and the stack already names
GitHub-hosted runners as a one-line fallback. A self-hosted runner therefore
buys little while adding a service account, registration-token lifecycle,
runner upgrades, single-job cleanup, resource contention, hardening tests, and
another process sharing the control-plane kernel.

Use GitHub-hosted runners for factory-repository lint, format, audit, schema,
and projection checks. Keep all agent execution, Fieldbook verification, and
request processing on Patchyard-owned infrastructure. This engages R4's reason:
GitHub Actions does not become the coding runtime.

### Keep tracing calls, but do not make a new Tempo backend a prerequisite

Instrument the supervisor with `tracing` and stable span fields from day one,
and keep a fail-open OTLP exporter interface. Initially emit structured local
logs and allow the OTLP endpoint to be absent. The event ledger and transcripts
already answer the principal questions for one supervisor and one worker.

If fleet Tempo exists by launch, connecting the exporter is cheap. If it must
be deployed for this project, ingestion, retention, upgrades, storage, and
access control do not belong on the critical path. Graduate it after the first
incident whose sequence cannot be reconstructed from events, logs, and
transcripts, or when a second concurrent worker creates genuinely distributed
traces.

### Defer convenience projections and page-view rows

The request timeline, evidence view, queue state, and kill controls are
operational. `/model`, `/bench`, `/schema`, and `/decisions` are convenient
projections, but they do not advance the phase-1 job statement. Three named
users also do not need authoritative page-view rows; Caddy logs can establish
whether a page is used.

Defer those four views and page-view rows until the core factory has survived
real runs. The canonical files remain in Git. This removes routes,
authorization cases, templates, queries, and retention behavior without
weakening isolation or the human gate.

### Time-box Firecracker evaluation

The dedicated, disposable, secret-free droplet is already the outer blast
radius. Rootless Podman on it is a defensible phase-1 layer when private
network and metadata denial, read-only mounts, process cleanup, resource
limits, and short-lived spend-capped credentials are proved.

Give Firecracker a fixed probe budget, such as half a session. Adopt it only
if KVM is immediately available and qualification is no harder to operate than
the container path. Keep it as the graduation path if rootless isolation fails
hostile tests or the worker later gains authority.

### Do not simplify the load-bearing core

- PostgreSQL is proportionate. Transactions, leases, role separation, and
  crash recovery matter at one run as much as at 1,000.
- The filesystem is the simplest suitable artifact store, provided it is
  backed up off-host.
- Rust plus server-rendered Axum/Askama is one coherent control-plane stack.
  Rewriting it would reimplement the process, state-machine, and privilege
  boundaries for little operational gain.
- OS-enforced worker isolation is required by the content threat, not request
  volume.

## 2. What is under-engineered, and when it breaks

| Failure | Breakpoint | Minimum repair |
| :-- | :-- | :-- |
| A missed `NOTIFY`, listener reconnect, or supervisor restart strands a row | **1x** - the first restart at the wrong time | Treat notifications only as hints. Scan for claimable and recoverable rows at startup, reconnect, and on a slow timer. Make every transition and external effect idempotently resumable. |
| Control-plane disk or VM loss removes ledger and evidence | **1x**, independent of volume | Create encrypted off-host backups, state RPO/RTO, and restore PostgreSQL, artifacts, roles, and application state onto a clean VM. |
| Transcripts and screenshots fill disk or make backup time unpredictable | **1x by bytes**, plausibly **5x by run count** | Measure bytes by artifact kind, alert on disk and inodes, enforce high-water fail-closed behavior and retention, and plan from p95 bytes per run. |
| Human review and the two-open-PR cap dominate latency | About **3x**, or 60 requests per week, depending on the lane-A proportion | Report oldest-ready-PR and queue age. Add reviewers or narrow intake before adding workers. |
| One preview slot serializes ready work | About **3-5x**, or earlier if previews are flaky | Add a second leased slot only when measured wait time exceeds active evidence time. Preserve exact-SHA and cleanup guarantees. |
| One worker cannot keep up | Roughly **5-10x**, depending on agent and test duration | Add a worker after measuring service time and queue age. PostgreSQL claims and leases remain sufficient. |
| Full dump plus artifact backup becomes too slow | More likely **10x+** or after a retention increase | Add incremental artifact backup and, only if RPO requires it, PostgreSQL WAL archiving. |
| PostgreSQL or `LISTEN/NOTIFY` throughput limits the system | Not credibly before **50x+** | Re-measure before adding a queue. Human review, preview capacity, model latency, and storage fail first. |

Two scale-independent details belong in the state-machine contract:

1. Give every external action an idempotency key and replay rule: worker boot,
   branch push, PR create/update, preview lease, artifact copy, and cleanup.
2. Make recovery state-derived. A new supervisor must decide to resume,
   compensate, or stop from the ledger and external facts, without an
   in-memory task or a previously delivered notification.

## 3. Operational burden being underestimated

### The publisher remains on the wrong host in two operative sections

The trust architecture says the supervisor, publisher, credentialed clone,
and worktrees belong on the control-plane VM. Later, SPEC's worktree paragraph
and PLAN session 10 put `/var/lib/patchyard/worktrees/` "on orchestration."
A runtime fetch, push, PR update, cleanup, or recovery would then depend on the
bootstrap host and put publishing authority on the wrong machine.

Place the credentialed bare clone and publisher worktrees at
`/var/lib/patchyard/worktrees/` on the control-plane VM. The exact source
bundle crosses from control plane to worker; the bounded patch and evidence
cross back. An ordinary run should never touch the orchestration host.

### The GitOps loop needs one writer per layer

The packet says OpenTofu runs only from orchestration but also says the control
plane can re-apply its desired state. Narrow those verbs:

- Orchestration is the only OpenTofu writer for cloud, DNS, firewall, and repo
  settings.
- One declared command applies control-plane and worker Ansible at an exact
  reviewed commit. If the control plane may apply only local configuration,
  name that subset and deny cloud-state changes.
- Record desired commit, plan hash, actor, timestamps, and result for every
  apply.
- Give remote state locking, versioning, backup, and a tested recovery path.

Runtime independence does not require two configuration writers. A replacement
controller can be bootstrapped from Git and the vault.

### Pinning creates an upgrade queue

Pinned Rust, OpenTofu, infrastructure packages, the Fieldbook runtime,
Chromium/ChromeDriver, and MySQL snapshot improve reproducibility, but each
becomes an owned upgrade. The work is proving that an update did not change
browser evidence, SQL behavior, isolation, or harness output.

Maintain one inventory with owner, installed version, support state, last
qualification, and next review date for the OS/kernel, Caddy, PostgreSQL,
exporters, isolation runtime, Rust/Cargo dependencies, browser/driver pair,
PHP image, redacted snapshot, agent CLIs, model/provider routes, OpenTofu
providers, Ansible collections, and Actions.

### Backup correctness spans two stores

A `pg_dump` and an artifact manifest are not automatically one consistent
backup. Define a cutoff, retain every artifact referenced at that cutoff, hash
the set, and copy dump plus artifacts to encrypted off-host storage. Alert on
backup age and manifest mismatch. The 90-day deletion policy must also say how
expired transcripts age out of backups.

Restore acceptance should provision a clean control-plane VM, apply roles and
migrations, restore dump and artifacts, verify hashes/counts, start the app,
and open historical evidence. At this scale, a nightly backup and regular
clean-host restore drill are more valuable than point-in-time recovery. Choose
the exact RPO, RTO, and drill interval before launch.

### Rotation requires a capability inventory

Caddy automates public certificate renewal, but the system still has GitHub
App keys, model credentials, preview bearer material, cloud/backend
credentials, SSH keys, Grafana/PostgreSQL TLS material, dashboard sessions,
and bootstrap passwords.

For each, record issuer, holder, storage location, scope, expiry, rotation,
revocation, and the test proving the old capability no longer works. Include
safe reload and rollback. A new value in 1Password does not prove a daemon has
consumed it.

### The worker remains an operating obligation

Disposability moves work from repair to rebuild. Refresh base images, detect
old/orphaned droplets, recheck metadata and firewall behavior, update redacted
snapshots, and reconcile failed teardowns. Alert on worker age, cleanup
failure, and spend, not merely supervisor health.

The SPEC heading/status also says v2.4 while its preamble includes changes
through v2.11. Normalize the displayed version before build and record that
version plus commit hash in run provenance.

## 4. AI-layer blind spot

The largest blind spot is **common-mode oracle failure**.

Cross-family review diversifies model and harness behavior, but every seat can
receive the same mistaken framing, inspect the same misleading code, optimize
against the same visible fixtures, and rely on the same flawed postcondition.
Builder, reviewer, arbitrator, and verifier can then agree for the same reason
and produce high-confidence evidence for the wrong behavior. A third family
does not create independence from a shared oracle.

The protection is independent evidence, not more debate:

- Keep some positives, negatives, and mutations hidden from both author and
  reviewer prompts.
- Derive postconditions from the requested user-visible invariant and a base
  observation, not the proposed patch shape.
- Link later corrections, rewrites, reverts, and defects to the originating
  model, harness, prompt, skill, and verifier versions.
- Randomly audit runs where the adversarial reviewer found nothing. Review
  yield measures only what a reviewer chose to report.
- Run a frozen canary set whenever a model alias, provider, CLI, system prompt,
  or effort setting changes. Model ID plus CLI version does not prove stable
  behavior when a provider can change the served model.
- Keep raw transcripts untrusted when the improvement proposer reads them.
  Typed outcomes and quoted evidence may inform proposals; transcript text is
  never instruction authority.

Distinguish empirically disproved findings, policy disagreements, and
author-overruled judgments in adjudication. Otherwise a high refutation rate
can mean either a poor reviewer or a defensive author.

## 5. What to instrument from day one

The design will regret omitting recovery and boundary telemetry, not another
HTTP graph.

### Use one correlation vocabulary

Events, structured logs, transcript pointers, and spans should carry the
applicable `request_id`, `run_id`, `attempt`, stage, base SHA, worker boot ID,
preview lease ID, and configuration/provenance hashes. Agent-stage spans also
need model, harness, provider, and resolved routing choice.

Do not use request/run IDs as Prometheus labels; that creates unbounded
cardinality. Put them in spans, logs, and the ledger. Metrics should use
bounded dimensions such as stage, outcome, lane, model class, provider, and
failure category. Never put request text, prompts, transcripts, credentials,
or customer data in metric labels or span attributes.

### Instrument state recovery

Record queue depth and oldest age by state/lane; time working and waiting in
each stage; supervisor restarts; listener reconnects; last backlog sweep;
recovered runs; duplicate-effect suppression; invalid transitions; retries,
timeouts, cancellations, kills, and compensation; and reconciliation age.

### Instrument security and cleanup

Record worker image/runtime/policy hashes, credential issue and expiry,
teardown result, remaining-process/mount checks, and output hashes. Count
denied egress, metadata/private-network probes, output-contract violations,
resource-limit kills, and orphaned workers without recording hostile content.

For evidence capture, record browser/driver versions, target, expected and
observed SHA before/after, navigation denials, credential expiry, output
sizes/hashes, and cleanup.

### Instrument capacity and recoverability

Track disk bytes/inodes by artifact kind, bytes per run, retention sweep,
PostgreSQL growth, worker boot/test duration, provider latency/rate limits,
backup age, last verified restore, desired-versus-applied commit, drift age,
and credential-expiry horizon. Traces should point to sensitive transcripts by
hash rather than duplicate them.

## 6. Security boundary to attack first

I would attack **preview evidence capture on the control-plane VM**.

The browser loads agent-written Fieldbook code, receives a preview bearer
credential, and needs network access. The same VM holds PostgreSQL, artifacts,
the supervisor, and publishing authority. Navigation restrictions and a Unix
user reduce mistakes, but a Chromium exploit, DNS-rebinding error, bearer leak,
or unsafe helper feature lands inside the highest-value host.

Make evidence capture a deterministic per-run isolation job with:

1. A fresh container/microVM and no factory DB socket, GitHub key, model/vault
   capability, repo credential, or artifact-tree mount.
2. Egress only to the leased preview host and required DNS; deny cloud
   metadata, the fleet, redirects, and all other destinations.
3. A one-use preview credential in tmpfs, removed at teardown.
4. A fixed helper contract: allowed URL, bounded actions, timeout, output
   limits, expected SHA, and no arbitrary caller JavaScript by default.
5. A narrow output directory containing screenshot, extracted DOM, hashes,
   and manifest; the supervisor copies it after the job ends.
6. Tests for redirects, DNS changes, subresources, popups, downloads,
   oversized output, bearer disclosure, and browser crashes.

This can use a distinct boot/profile on the disposable worker, preserving the
one-allowlist-per-boot invariant, or a separately proved isolation job on the
control plane. It must not share the agent worker's model-provider profile.

The second boundary to remove is the co-located Actions runner.

The authentication contract also contains stale text. It chooses native
argon2 sessions and says there is no status-dashboard `forward_auth`, but then
refers to a generic "members store" and says SSE uses `forward_auth`. Name one
source only: factory PostgreSQL users/sessions with `factory_submit` and
`factory_admin`. Test HTML, evidence, control POSTs, and SSE against it.

## 7. One outright replacement

**Replace the self-hosted GitHub Actions runner on the control-plane VM with
GitHub-hosted runners.**

This removes the most risk and operating burden for the least migration cost.
It preserves the intended checks, leaves coding execution on Patchyard-owned
infrastructure, and removes runner registration, updates, cleanup, resource
caps, and a co-resident execution service from the ledger VM.

Because phase 1 has not started, migration cost is about two to four hours:

1. Set workflow `runs-on` to a hosted image.
2. Remove runner user/unit/token flow and Ansible work from the plan.
3. Confirm workflows are hermetic, credential-free, and need no factory/private
   access.
4. Run the suite at a fixed commit and record time and included-minute cost.
5. Update the threat model and recovery docs.

If replaced after implementation, allow half to one session to prove no user,
unit, token, or firewall exception remains. If future CI needs private
resources, use an ephemeral single-job runner on a disposable host, never the
ledger VM.

## Priority before the build gate opens

Required before the first live request:

1. Specify and test backlog recovery with idempotent external effects.
2. Put browser evidence capture behind a no-authority isolation boundary.
3. Define RPO/RTO, off-host backup, and a clean-host full restore drill.
4. Move publisher clone/worktrees from orchestration to the control-plane VM,
   and remove stale `forward_auth`/members-store language.
5. Define one IaC/configuration writer per layer and record applied commits.
6. Define correlation, recovery, boundary, and no-sensitive-telemetry rules.

Remove or defer from phase 1:

1. Use GitHub-hosted factory-repository CI.
2. Keep tracing hooks, but make a new Tempo deployment post-launch.
3. Defer `/model`, `/bench`, `/schema`, `/decisions`, and page-view rows.
4. Time-box Firecracker and accept qualified rootless Podman if it is not
   operationally cheap.

Do not add Kubernetes, a cloud queue, object-store application dependency,
Loki, control-plane replicas, or more model reviewers. None addresses the
first failures above. At 10x, re-evaluate workers, preview slots, incremental
backups, and recovery targets from measured queue age, service time, bytes per
run, and incident history.
