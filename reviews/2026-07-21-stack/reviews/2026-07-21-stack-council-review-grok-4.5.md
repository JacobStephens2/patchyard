# Outside-council review of the Patchyard Factory technology stack

*2026-07-21. Target: the stack council packet at commit
`c89eb71473a35cceffe87fa3c0560883945e2b3d`. Scope: technology and
operational architecture at approximately 20 requests per week. The five
packet invariants are treated as fixed.*

## Verdict

The core stack is appropriate. Keep Rust/Axum, PostgreSQL, SQLx, the local
filesystem artifact store, Caddy/systemd, exec-bound agent harnesses, the
dedicated secret-free worker, and the human-merged PR boundary. None of those
choices is disproportionate merely because throughput is low. The difficult
property here is not traffic; it is safely executing code derived from
untrusted input.

The phase-1 perimeter is nevertheless too broad. It spends scarce build and
operating capacity on a co-located self-hosted CI runner, a new tracing
backend, page-view accounting, and several convenience projections while
three failures that can occur at current scale remain underspecified:

1. A daemon restart can strand work if `LISTEN/NOTIFY` is treated as a durable
   queue rather than a wake-up hint.
2. Loss of the control-plane VM can lose the authoritative ledger and its
   evidence unless backup consistency, off-host storage, and clean-host
   restoration are proved.
3. Headless Chromium processes agent-modified Fieldbook pages on the same VM
   that holds the ledger, artifacts, and publishing authority. That is the
   first boundary I would attack.

There is also a direct pre-build contradiction: the host-placement section
moves the publisher onto the dedicated control-plane VM, while the worktree
contract in both SPEC and PLAN still puts credentialed publisher worktrees
"on orchestration." That violates the packet's runtime-independence invariant
as written and must be corrected before sessions are executed.

My recommended phase-1 adjustment is therefore small but material: remove the
self-hosted GitHub Actions runner, defer the Tempo backend and non-operational
dashboard views, and spend the recovered sessions on crash recovery, a full
restore drill, and an isolated evidence-capture job.

## 1. What is over-engineered at 20 runs per week

### Remove the self-hosted Actions runner from the control-plane VM

Factory-repository CI is described as credential-free hygiene, and the stack
already names GitHub-hosted runners as a one-line fallback. A self-hosted
runner therefore buys little while adding a service account, registration
token lifecycle, runner upgrades, single-job cleanup, resource contention,
systemd hardening, and another process sharing the control-plane kernel.

Use GitHub-hosted runners for factory-repository lint, format, audit, schema,
and projection checks. Keep all agent execution, Fieldbook verification, and
request processing on Patchyard-owned infrastructure. This respects R4's reason:
GitHub Actions does not become the coding runtime.

### Keep tracing in the code, but do not make Tempo a phase-1 deliverable

Instrument the supervisor with `tracing` and stable span fields from day one,
and keep the fail-open OTLP exporter interface. Initially emit structured
local logs and allow the OTLP endpoint to be absent. The event ledger and full
transcripts already answer the principal questions for one supervisor and one
worker at low concurrency.

If the fleet already operates Tempo by the time the factory launches,
connecting the exporter is cheap and should be done. If Tempo must be newly
deployed for this project, its ingestion, retention, upgrades, storage, and
access controls are not justified yet. A useful graduation trigger is the
first incident whose causal sequence cannot be reconstructed from events,
structured logs, and transcripts, or the addition of a second concurrent
worker path.

### Defer convenience projections and page-view ledger rows

The live request timeline, evidence view, queue state, and kill controls are
operational. `/model`, `/bench`, `/schema`, and `/decisions` are convenient
repo or database projections, but they do not advance the job statement.
Likewise, three named users do not need authoritative per-page usage rows;
Caddy access logs are enough to establish whether a page is used.

Defer those four views and page-view rows until the basic factory has survived
real runs. This removes routes, authorization cases, templates, queries, and
retention questions without weakening a safety boundary or the human gate.
The canonical files remain available in Git.

### Time-box Firecracker evaluation

The dedicated, disposable, secret-free droplet is already the outer blast
radius. Rootless Podman on that host is a defensible phase-1 isolation layer
when private-network denial, metadata denial, read-only mounts, process
cleanup, and short-lived spend-capped credentials are all proved.

Give the Firecracker probe a fixed budget, such as half a session. Adopt it
only if KVM is immediately available and the qualification suite is no harder
to operate than the container path. Do not let image building, kernel
maintenance, networking, and snapshot tooling consume multiple sessions for
an inner boundary whose host contains no durable authority. Firecracker
should remain the graduation path if rootless isolation cannot pass hostile
tests or the worker later receives more authority.

### What should not be simplified

- PostgreSQL is not excessive here. Transactions, leases, append-only events,
  role separation, and crash recovery matter at one run as much as at 1,000.
- The filesystem artifact store is the simplest suitable store at this scale.
  An object-store application dependency would add more failure modes than it
  removes, provided backups are off-host.
- Rust and server-rendered Axum/Askama are a coherent one-language control
  plane. Rewriting them in a more familiar scripting stack would trade build
  speed for a second implementation of process, state-machine, and privilege
  boundaries.
- OS-enforced worker isolation is required by the content threat model, not by
  request volume.

## 2. What is under-engineered, and when it breaks

| Failure | Likely breakpoint | Minimum repair |
| :-- | :-- | :-- |
| Missed `NOTIFY`, listener disconnect, or supervisor restart strands a queued or in-progress row | **1x** - the first restart at the wrong time | Treat notifications only as hints. On startup, reconnect, and a low-frequency timer, scan canonical rows for claimable or recoverable work. Make every transition and external side effect idempotently resumable. |
| Control-plane disk or VM loss removes ledger plus evidence | **1x** - independent of throughput | Create encrypted off-host backups, state an RPO/RTO, and restore PostgreSQL, artifacts, roles, and application state onto a clean VM in an automated drill. |
| Full transcripts and screenshots fill disk or make backup windows unpredictable | **1x by bytes**, plausibly **5x by run count** | Measure bytes per artifact kind, set disk/inode alerts and high-water shutdown behavior, enforce retention, and capacity-plan from the 95th-percentile bytes per run rather than request count. |
| Human review and the two-open-PR cap dominate latency | About **3x** current volume, or 60 requests per week, assuming the present lane-A proportion | Report oldest-ready-PR age and queue age. Add reviewers or narrow intake before adding workers. The database is not this bottleneck. |
| One preview/evidence slot serializes ready-to-review work | About **3-5x**, or earlier if previews are slow or flaky | Add a second leased slot only after measured slot wait exceeds active work time. Preserve exact-SHA and cleanup invariants. |
| One worker cannot keep up | Roughly **5-10x**, depending on model latency and test duration | Add a worker only after measuring service time and queue age. PostgreSQL row claims and leases can support this without replacing the queue. |
| Full `pg_dump` plus artifact-tree backup becomes too slow | More likely **10x+** or a transcript-retention increase | Move to incremental artifact backup and, if the RPO demands it, PostgreSQL WAL archiving. Do not add them preemptively. |
| PostgreSQL or `LISTEN/NOTIFY` throughput becomes the limiting factor | Not credibly before **50x+** for this workload | Re-measure before proposing a separate queue or database. Human review, previews, model latency, and storage will fail first. |

Two scale-independent details belong in the state-machine contract before
build:

1. Every external action needs an idempotency key and a replay rule: worker
   boot, branch push, PR create/update, preview lease, artifact copy, and
   cleanup.
2. Recovery must be state-derived. A new supervisor should be able to inspect
   a row plus external facts and decide to resume, compensate, or stop without
   relying on an in-memory task or a previously delivered notification.

## 3. Operational burden being underestimated

### The two-VM GitOps loop has an ownership ambiguity

The packet says OpenTofu runs only from the orchestration controller, but it
also says the control plane can re-apply its own desired state. Unless the
verbs and layers are narrowed, this creates two potential writers with
different checkouts and credentials.

Define one writer per layer:

- The orchestration controller is the only OpenTofu writer for cloud, DNS,
  firewall, and repository settings.
- One declared deployment command applies control-plane and worker Ansible at
  an exact reviewed commit. If the control plane may apply only its own local
  configuration, name that subset and ensure it cannot change cloud state.
- Every apply records desired commit, plan hash, actor, start/end time, and
  result in an operations log.
- The remote OpenTofu state has locking, versioning, backup, and a tested
  recovery procedure.

Runtime independence from orchestration does not require two configuration
writers. A replacement controller can be bootstrapped from the repo and vault
when the ordinary controller is unavailable.

### The publisher is still placed on the wrong host in two operative sections

The trust architecture says the supervisor, publisher, credentialed clone,
and worktrees belong on the dedicated control-plane VM. Later, SPEC's
worktree paragraph and PLAN session 9 put
`/var/lib/patchyard/worktrees/` "on orchestration." That is not harmless
wording: a runtime fetch, branch push, PR update, cleanup, or crash recovery
would depend on the bootstrap host and would place publishing authority on the
wrong machine.

Resolve this by putting the credentialed bare clone and publisher worktrees at
`/var/lib/patchyard/worktrees/` on the control-plane VM. The source bundle
crosses from control plane to worker; the bounded patch and evidence cross
back. No ordinary run should connect to, read from, or write to the
orchestration host.

### Pinning creates an upgrade queue

The stack pins Rust, OpenTofu, infrastructure packages, the Fieldbook runtime
image, Chromium/ChromeDriver, and a redacted MySQL snapshot. That improves
reproducibility, but each pin becomes an owned upgrade with a qualification
matrix. The underestimated work is not applying an update; it is proving that
the update did not change browser evidence, SQL behavior, isolation, or model
harness output.

Maintain a single inventory with owner, installed version, upstream support
state, last qualification, and next review date for:

- OS and kernel on both hosts;
- Caddy, PostgreSQL, exporters, and the selected isolation runtime;
- Rust toolchain and Cargo dependencies;
- Chromium and ChromeDriver as a matched pair;
- PHP/extensions/web-server parity image and redacted MySQL snapshot;
- Claude Code, Codex, model identifiers, provider endpoints, and routing
  policy;
- OpenTofu providers, Ansible collections, and GitHub Actions.

### Backup correctness spans two stores

A `pg_dump` and an artifact manifest are not automatically one consistent
backup. Define a backup cutoff, retain append-only artifacts referenced at
that cutoff, hash them, and copy both database dump and artifact set to
encrypted off-host storage. Alert on backup age and manifest mismatch.
The 90-day artifact deletion policy must also state how expired material ages
out of backup generations; otherwise "deleted" transcripts remain recoverable
indefinitely from the backup system.

The acceptance test should restore onto a clean control-plane VM, provision
roles from desired state, apply migrations, restore the dump and artifacts,
verify hashes and counts, start the application, and open a historical run's
evidence. A restore test that stops at `pg_restore` is insufficient.

At current scale, nightly backup and a regular clean-host restore drill are
more valuable than point-in-time recovery. Choose the exact RPO, RTO, and
drill interval before launch rather than inheriting accidental defaults.

### Rotation needs a complete capability inventory

Caddy automates public certificate renewal, but the system still has GitHub
App private keys, model-provider credentials, preview bearer material,
OpenTofu backend/cloud credentials, SSH host and management keys, PostgreSQL
TLS material for Grafana, dashboard sessions, and bootstrap passwords.

For each capability, record issuer, holder, storage location, scope, expiry,
rotation command, revocation command, and the test proving the old credential
no longer works. Rotation must include safe service reload and rollback. A
secret reference in Git and a value in 1Password do not by themselves prove
that a running daemon consumed the new value.

### The disposable worker still requires routine hygiene

Disposability moves work from repair to rebuild; it does not remove work.
Base images must be refreshed, old droplets detected, provider firewall and
metadata behavior rechecked, redacted database snapshots updated, and failed
teardowns reconciled. Alert on worker age, orphaned resources, cleanup
failure, and spend, not merely on supervisor health.

### Canonical metadata needs one version

The SPEC heading and status still say v2.4 while the same preamble records
changes through v2.11. Commit identity is sufficient for this review, but
operators and acceptance records will otherwise cite an ambiguous spec
version. Before build, make the displayed version match the latest included
ruling set and use that version plus commit hash in run provenance.

## 4. AI-layer blind spot

The largest blind spot is **common-mode oracle failure**.

Cross-family review diversifies model and harness behavior, but every seat can
still receive the same mistaken task framing, inspect the same misleading
code, optimize against the same visible fixtures, and rely on the same flawed
deterministic postcondition. In that case the builder, reviewer, arbitrator,
and verifier agree for the same reason and produce high-confidence evidence
for the wrong behavior. Adding a third family does not create independence
from a shared oracle.

The protection is independent evidence, not more debate:

- Keep some positive, negative, and mutation cases hidden from both author
  and reviewer prompts.
- Build postconditions from the requested user-visible invariant and a base
  observation, not from the proposed patch shape.
- Track later human corrections, rewrites, reverts, and production defects by
  originating run, model, harness, prompt, skill, and verifier version.
- Randomly audit a sample of runs where the adversarial reviewer found
  nothing. Review yield alone measures only what the reviewer chose to say.
- Run a frozen canary set whenever a model alias, provider, CLI, system prompt,
  or effort setting changes. A model name and CLI version do not prove stable
  behavior if the provider silently changes the served model.
- Prevent the improvement proposer from treating transcript text as
  instructions. It should consume typed outcome facts and quoted evidence;
  raw request and tool output remain untrusted data even after a run closes.

The adjudication ledger should distinguish empirically disproved findings,
policy disagreements, and author-overruled judgments. Otherwise a high
"refuted" rate can mean either a poor reviewer or a defensive author.

## 5. Day-one observability

The design will most regret omitting recovery and boundary telemetry, not
another HTTP graph.

### Establish one correlation vocabulary

Every event, structured log, transcript pointer, and span should carry the
applicable `request_id`, `run_id`, `attempt`, stage, base SHA, worker boot ID,
preview lease ID, and configuration/provenance hashes. Model, harness,
provider, and exact resolved routing choice belong on agent-stage spans.

Do not use request or run IDs as Prometheus labels; that creates unbounded
cardinality. Put them in spans, logs, and ledger rows. Metrics should use
bounded dimensions such as stage, outcome, lane, model class, provider, and
failure category. Never put request text, prompts, transcript fragments,
credentials, or customer data in metric labels or span attributes.

### Instrument the state machine and recovery path

Record and alert on:

- queue depth and oldest-row age by state and lane;
- time in each stage, including time waiting for PR capacity, worker,
  reviewer, CI, and preview;
- supervisor restarts, listener disconnect/reconnect, last successful backlog
  sweep, recovered runs, duplicate-side-effect suppression, and impossible
  transition attempts;
- retry, timeout, cancellation, repair-loop, kill, and compensation reasons;
- branch/PR reconciliation age and stale-cap fail-closed duration.

### Instrument the security and cleanup boundaries

Record worker image hash, isolation-runtime version, egress policy version,
credential issue/expiry time, teardown result, remaining process/mount check,
and artifact output hashes. Count denied egress, metadata/private-network
probes, output-contract violations, resource-limit kills, and orphaned
workers. These signals should not include hostile content itself.

For evidence capture, record browser and driver versions, target host, expected
and observed SHA before/after, navigation-denial count, credential expiry,
output sizes/hashes, and cleanup result.

### Instrument capacity and recoverability

Track disk bytes and inodes by artifact kind, bytes per run, retention-sweep
age/result, PostgreSQL growth, worker boot and test duration, provider
latency/rate-limit errors, and external service availability. Add backup age,
last verified restore time, desired-versus-applied Git commit, drift age, and
credential expiry horizon to the operational dashboard.

At 20 runs per week, retain all operational traces for a bounded period if
storage permits. The full transcript has separate sensitivity and retention
rules; a trace should point to it by hash rather than duplicate its content.

## 6. Security boundary to attack first

I would attack **preview evidence capture on the control-plane VM**.

The browser loads a Fieldbook branch containing agent-written code and renders
responses derived from a shared preview environment. It also receives a
preview bearer credential and needs network access. The same VM holds
PostgreSQL, the artifact store, the supervisor, and GitHub publishing
authority. Host navigation restrictions and a dedicated Unix user reduce
ordinary mistakes, but a Chromium exploit, DNS-rebinding mistake, bearer
leak, or unsafe helper feature lands inside the highest-value host.

Make evidence capture a deterministic, per-run isolation job with:

1. A fresh container or microVM and no factory database socket, GitHub App
   key, model credential, 1Password capability, repo credential, or artifact
   tree mount.
2. Network access only to the leased preview host and required DNS, with
   cloud metadata, the private fleet, and all other destinations denied.
3. A one-use, short-lived preview credential delivered in tmpfs and removed
   at teardown.
4. A fixed helper contract: allowed URL, bounded selectors/actions, timeout,
   maximum output sizes, expected SHA, and no arbitrary caller-supplied
   JavaScript unless a reviewed test specifically requires it.
5. A narrow output directory containing only screenshot, extracted DOM,
   hashes, and an execution manifest. The supervisor copies those outputs
   into the artifact store after the job has ended.
6. Adversarial tests for redirect chains, DNS changes, subresource requests,
   popups, downloads, oversized pages/images, bearer disclosure, and browser
   crashes.

This can run on the disposable worker under a separate evidence profile, or
in a separately isolated job on the control plane if the boundary is proved.
It should not share the ordinary agent worker's model-provider egress profile.

The second boundary I would remove is the co-located self-hosted Actions
runner. Even a strongly hardened service shares the control-plane kernel and
resources; GitHub-hosted hygiene CI avoids the boundary entirely.

There is also an authentication contract contradiction to remove before
implementation. The dashboard section correctly chooses factory-native
argon2 sessions and says there is no status-dashboard `forward_auth`, but its
authorization paragraph still refers to a generic "members store," and the
SSE paragraph says the stream uses the same `forward_auth` session. The role
matrix should name one source only: factory PostgreSQL users and sessions,
with `factory_submit` and `factory_admin` roles. Test the HTML routes,
evidence downloads, control POSTs, and SSE handshake against that same
session implementation.

## 7. One outright replacement

**Replace the self-hosted GitHub Actions runner on the control-plane VM with
GitHub-hosted runners.**

This is the highest ratio of risk and operating burden removed to migration
cost. It preserves the intended CI checks, leaves the coding runtime on
Patchyard-owned infrastructure, and removes runner registration, updates, cleanup,
resource caps, and a co-resident code-execution service from the control
plane.

Because phase 1 has not been built, migration cost is approximately two to
four hours:

1. Set the workflow `runs-on` target to a GitHub-hosted image.
2. Remove the runner user, systemd unit, registration-token flow, and Ansible
   roles from the build plan.
3. Confirm every workflow is hermetic and credential-free and needs no
   private-network or factory-state access.
4. Run the complete CI suite at a fixed commit and record timings and any
   included-minute cost.
5. Update the threat model and recovery docs to remove the runner.

If implemented first and replaced later, allow half to one session for
deprovisioning and proving that no registration token, user, unit, or firewall
exception remains. If future CI genuinely requires private resources, use an
ephemeral single-job runner on a disposable host. Do not restore it to the
ledger VM.

## Priority before the build gate opens

### Required before the first live request

1. Specify and test startup/reconnect/backlog recovery with idempotent external
   effects.
2. Move browser evidence capture behind a no-authority isolation boundary.
3. Define RPO/RTO, encrypted off-host backup, and a clean-host full restore
   drill for PostgreSQL plus artifacts.
4. Move the publisher clone/worktrees from orchestration to the control-plane
   VM and remove the stale `forward_auth`/members-store language.
5. Resolve the OpenTofu/Ansible writer and applied-commit ownership model.
6. Define the day-one correlation fields, recovery metrics, boundary metrics,
   and no-sensitive-telemetry rule.

### Scope to remove or defer

1. Use GitHub-hosted factory-repository CI.
2. Keep tracing instrumentation but make a new Tempo deployment post-launch.
3. Defer `/model`, `/bench`, `/schema`, `/decisions`, and page-view ledger rows.
4. Time-box Firecracker evaluation and accept qualified rootless Podman on the
   disposable worker if Firecracker is not operationally cheap.

### Do not add yet

Do not add Kubernetes, a cloud queue, an object-store application dependency,
Loki, multiple control-plane replicas, or more model reviewers. None addresses
the first failures identified above. At 10x current demand, re-evaluate worker
count, preview slots, incremental backups, and control-plane recovery targets
from measured queue age, service time, bytes per run, and incident history.
