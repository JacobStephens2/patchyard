# Outside-council review of the Patchyard Factory technology stack

*2026-07-21. Reviewer: Kimi K3 × Kimi Code. Target: the stack council packet
at commit `c89eb71473a35cceffe87fa3c0560883945e2b3d` (brief + stack.md + model
diagram + SPEC snapshot). Scale calibration: ~20 requests/week, three named
users, two small VMs plus one ephemeral worker droplet. The five packet
invariants are treated as fixed. Provenance: written with the Grok 4.5 council
review visible in the repo; findings were re-derived from the packet itself,
and the appendix records where the two reviews converge and where they
diverge.*

## Verdict

The architecture's center of gravity is correct. The factory's difficulty is
not throughput but safely turning untrusted request content into a
human-reviewed patch, and the stack spends its weight accordingly: OS-enforced
worker isolation, an exec boundary around every agent, an append-only ledger,
deny-path tripwires, and one human merge gate. None of that should be
simplified at 20 requests per week.

The exclusions table also stands unchallenged. Nothing at this scale argues
for npm, TypeScript, a front-end framework, Compose/Kubernetes, an in-process
agent SDK, or a cloud queue, and the CI tripwire that enforces the table costs
essentially nothing.

The phase-1 perimeter is nevertheless too broad, and the breadth is in the
wrong place. Convenience scope - a co-located CI runner, four projection views
including a bespoke introspection pair, per-page usage rows, and a new tracing
backend - ships in phase 1 for a three-user internal tool, while the failures
most likely to hurt at *current* scale sit elsewhere:

1. A queued request stranded by a missed `LISTEN/NOTIFY` - the packet's claim
   path is LISTEN-driven and never states a startup backlog scan or periodic
   sweep, so an unclaimed row (no lease to expire) can wait forever, silently
   violating the A65 invariant with no error anywhere.
2. Loss of the control-plane VM, taking ledger, artifacts, and publisher with
   it - the backup clause names no off-host destination, no RPO/RTO, and no
   proved clean-host restore.
3. Silent parity decay as Fieldbook's production schema drifts from the dated
   redacted snapshot the worker verifies against (A85's refresh pipeline is
   unspecified).
4. A browser evidence job that renders agent-modified code and holds a
   cross-system bearer credential on the same host as the ledger and the
   publishing authority.

The packet also contradicts itself in three places that must be fixed before
sessions execute: publisher worktrees are placed "on orchestration" by the
worktree contract in both SPEC and PLAN while A68 places the publisher on the
control-plane VM; the dashboard is ruled factory-native auth with no
`forward_auth`, yet the SSE paragraph still authenticates "through the same
forward_auth session" and the authorization paragraph names a "members store";
and the SPEC header says v2.4 while its own preamble records changes through
v2.11.

Recommended adjustment: trim the convenience scope, and spend the recovered
sessions on recovery semantics, a restore drill, snapshot refresh, and
evidence-job isolation.

## 1. What is over-engineered at 20 runs per week

### 1.1 The self-hosted Actions runner on the control-plane VM

A76's stated reason is warm caches and quota: Rust builds eat hosted minutes
and start cold, and a warm runner on owned hardware is fast and quota-free.
Both halves are answerable without owning a runner. A Rust cache action
(`Swatinem/rust-cache`, or a seeded `actions/cache` over `target/` and
`~/.cargo`) restores most of the warm-build benefit on hosted runners, and the
CI volume here - hygiene checks on factory PRs through a 17-session build - is
a few hundred hosted-minutes per month, typically inside the free allowance
for a private repo and single-digit dollars above it.

A76 is right that untrusted-fork risk is structurally absent. The residual
cost is not forks but a code-execution service - workflow YAML and every
action it pulls - co-resident on the one host that holds the ledger, the
artifact store, and the publisher, plus a registration-token lifecycle, runner
upgrades, and single-job cleanup to operate forever. The `gha-runner` user
cannot peer-authenticate to PostgreSQL or read 0700 artifacts, so the
isolation is honest against accidents; the question is why carry any residual
kernel co-tenancy and an owned lifecycle for a benefit a cache action
provides. GitHub-hosted runners - the stack's own named fallback - are the
proportionate choice. R4 is untouched: hygiene CI is not the coding runtime.
(This is also my section 7.)

### 1.2 The bespoke introspection pair, and half the projection views

A81 mandates a bespoke dual-reader PostgreSQL introspection implementation -
shared catalog queries feeding both `/schema` and a byte-identical-checked
Mermaid ER diagram - to keep mermerd/tbls out of the supply chain. The
supply-chain instinct is fine; the deliverable is not phase-1-sized. The
migrations are already canonical, and SQLx already enforces query-schema
agreement at compile time. `/schema` is an admin debugging convenience and the
ER diagram is documentation for a schema its handful of readers can read in
SQL. Defer both, and the A81 machinery with them; revisit when a second
engineer joins or the schema stops fitting in one head.

Of the other projections: keep `/decisions` (one server-side markdown render
of a file that already exists; it serves the constitution's transparency story
at near-zero marginal cost) and keep `/model` as a static SVG, but cut the
live run-dot overlay (a second SSE consumer for three users) and defer
`/bench` (a render of a committed JSON file admins can read in the repo). None
of these touches a safety boundary.

### 1.3 Page-view ledger rows (A79)

A79's reason - "which runs got viewed before merge" is a join question - is
real but thin at three named users. The Caddy access log, kept as the
cross-check anyway, answers it at this volume, and the events ledger already
records the actions that matter. The middleware adds a write path on every
GET, a table, retention rules, and exclusion logic to save someone an
occasional `grep`. Defer to phase 2; if a usage question actually gets asked
twice, build it then. Lowest-priority trim - it is small - but small unneeded
write paths are how internal tools accrete.

### 1.4 A new Tempo deployment as a phase-1 deliverable

Keep `tracing` instrumentation and the fail-open OTLP exporter in the daemon
from day one; retrofitting instrumentation is genuinely painful and `tracing`
is idiomatic Rust. But a new tracing *backend* is not a phase-1 need: the
append-only event ledger already stores the span-equivalent record (stage,
actor, timestamps, durations) for a one-daemon system, and transcripts carry
the content. If the fleet adopts Tempo for its own reasons, flip the exporter
on. Do not let the factory be the reason Tempo exists.

### 1.5 Firecracker evaluation: time-box it

The packet's own ordering (evaluate first, rootless Podman fallback) is right;
bound the evaluation. The worker droplet is already disposable, secret-free,
and egress-pinned to one provider, so a container escape lands on a host with
nothing durable to steal - the microVM's kernel boundary defends the
patch-return contract, not stored authority. Probe `/dev/kvm` on the actual
droplet, give Firecracker half a session, and adopt it only if it is no harder
to operate than hardened rootless Podman (seccomp, no-new-privileges,
read-only mounts, private-network and metadata denial all proved). It remains
the graduation path if the worker ever gains authority or fails a hostile
isolation test.

### What should not be simplified

- PostgreSQL + SQLx + the grant matrix: leases, append-only events, and role
  separation are safety machinery, not scale machinery; they cost the same at
  one run as at a thousand. The A56 socket-only choice is right.
- The filesystem artifact store: the simplest correct store here. Only its
  backup destination needs fixing (section 2).
- `LISTEN/NOTIFY` as wake-up: do not add a queue - a second durable-state
  system is strictly more machinery at this volume. Pair it with the recovery
  sweep in section 2 so notifications stay hints, as the exclusions row
  intends.
- Rust + Axum/Askama SSR, factory-native argon2 auth (A68's independence
  demands it), per-run MySQL parity (A85), the deny-paths tripwire, and
  exec-bound agent harnesses. All correctly sized.

## 2. What is under-engineered, and when it breaks

| Failure | Breaks at | Minimum repair |
| :-- | :-- | :-- |
| Stranded queued request - missed `NOTIFY`, listener drop, or a restart between form POST and claim | **1x** - the first unlucky restart | The claim path is described as LISTEN-driven; no startup backlog scan or timer sweep is stated, and an unclaimed row holds no lease to expire. Treat notifications as hints only: claim-scan on startup plus a low-frequency timer; every transition idempotent. Kill control rows (A70) get the same polling path - kill latency is otherwise bounded only by lease TTL. |
| Control-plane VM loss removes ledger, artifacts, and publisher | **1x** - host or provider failure, independent of volume | The backup clause names no destination, RPO, or RTO. Encrypted off-host copies, a stated RPO/RTO, and a clean-VM restore drill as an acceptance gate. |
| Parity decay - prod Fieldbook schema drifts from the dated redacted snapshot | **1x** - the first prod migration after the snapshot date | The worker verifies the patched app against a stale local MySQL. "Refresh fail-static" is ambiguous: last-good means silent staleness, halt means lost availability; either way the refresh trigger, owner, and cadence are unspecified. Refresh on every Fieldbook migration, alert on snapshot age, print the snapshot date in the PR contract. |
| Seat breakage - model deprecation, provider outage, or silent served-model change under a constant alias | **1x** - the first provider-side change | Phase-1 static routing has no fallback rule; the run fails, or worse, quietly changes behavior. Add a routing fallback chain and gate any changed seat on a frozen-canary pass (section 4). |
| The within-the-hour promise vs. the 2-open-PR cap | **1x**, whenever two PRs sit unmerged - a staffing fact, not a defect | A31 already rules review capacity binding at current volume; the cap converts overflow into queue age from day one. Surface queue age and expected wait on the submitter receipt so intake does not over-promise. |
| One preview/evidence slot serializes ready-to-review work | About **3-5x**, earlier if previews are flaky | Add a second leased slot only when measured slot wait exceeds active evidence time. Preserve exact-SHA and cleanup invariants. |
| Single worker saturation | Roughly **5-10x**, model-latency dominated | Row claims and leases already support N workers; add hardware only on measured service time and queue age. |
| `pg_dump` + artifact-tree backup window | More likely **10x+** or a transcript-retention increase | Incremental artifact backup, and WAL archiving if the RPO demands it. Not preemptively. |
| PostgreSQL or `LISTEN/NOTIFY` throughput | Not credibly before **50x** at this workload | Re-measure before proposing any queue or second database. Human review, previews, model latency, and storage fail first. |

Two scale-independent clauses belong in the state-machine contract before
build (stated plainly here because everything else in this section depends on
them):

1. Every external side effect carries an idempotency key and a replay rule:
   worker boot, branch push, PR create/update, preview lease, artifact copy,
   cleanup.
2. Recovery is state-derived: a fresh supervisor inspects the row plus
   external facts and decides resume, compensate, or stop - no dependence on
   in-memory tasks or previously delivered notifications.

## 3. Operational burden being underestimated

### 3.1 The redacted-snapshot refresh pipeline

A85 makes a dated, redacted MySQL snapshot the worker's parity base. Keeping
it true is a recurring, easy-to-forget job: re-run redaction, verify lineage,
absorb prod schema changes, and record the version in run provenance. It is
the burden most likely to be discovered by a bad run instead of a calendar.
Give it an owner, a trigger (every Fieldbook migration), a staleness alert, and
a periodic drill.

### 3.2 The Chromium/ChromeDriver matched pair

Evidence is the product. A browser upgrade that shifts rendering invalidates
visual comparison quietly, and the pair must upgrade in lockstep. Pin both,
upgrade deliberately, and keep one visual-baseline fixture that must pass
before a new pair takes evidence duty.

### 3.3 The model-provider estate

The A61 allowlist is thirteen names, but only routed seats should hold live
credentials - keep it that way. Each live provider is a billing relationship,
a spend cap to tune, a key to rotate, and a deprecation calendar to watch.
Model deprecations are now routine ops events and deserve a runbook: rotate
the seat, re-canary, update the bench.

### 3.4 The one TCP exception

The `grafana_ro` listener means certificate issuance and rotation for a
cluster that otherwise needs no TLS material - exactly the class of thing that
expires at 3 a.m. Until the ledger dashboards prove their worth, consider
whether metrics-only access (Prometheus exporters, no TCP exception) suffices.
If the listener stays, cert expiry joins backup age on the alert path, and the
read views' columns get pinned (section 6).

### 3.5 The two-writer GitOps question

OpenTofu "runs only from the orchestration controller," yet the control plane
"can re-apply its own desired state." Name one writer per layer: orchestration
owns cloud, DNS, firewall, and repository settings; the control plane at most
re-applies its own local Ansible subset and cannot touch cloud state. Record
desired-vs-applied commit per host on the dashboard, and give drift reports an
owner - a drift report nobody reads is a cron that mails /dev/null.

### 3.6 `cargo audit` / `cargo deny` triage

Advisories arrive weekly; most are irrelevant to this binary, but someone must
triage each one or CI turns red and learns to be ignored. Budget the standing
half-hour and document the triage convention (patch, ignore-with-reason, or
accept).

### 3.7 Rotation inventory

GitHub App key, dashboard session secret, live provider keys, OpenTofu backend
credentials, preview bearer material, SSH host and management keys. For each:
rotation command, revocation command, and a proof-of-death test showing the
old credential fails. A vault entry in 1Password is not a rotation.

### 3.8 Canonical version metadata

The SPEC header says v2.4 while the preamble records changes through v2.11.
Run provenance needs one unambiguous spec version plus commit SHA. One-line
fix before the build gate opens.

## 4. The AI-layer blind spot

The headline blind spot: **the design pins labels, but the things labels
denote are mutable - and the bench that authorizes seats is a dated snapshot
of moving targets.**

Provenance records model id, CLI version, routing-config version, and
prompt/skill/rubric hashes. But providers change served weights under constant
aliases, harness CLIs ship weekly (and A60's own evidence - the Muse Spark
envelope bisection - shows the harness envelope changes model behavior), and
endpoints get silently re-quantized. Meanwhile phase-1 routing is static: the
factory stores per-run eval scores but has no feedback path that demotes a
silently degraded seat, and the learning loop's n≥10 evidence threshold needs
roughly two weeks of poisoned runs at current volume before the proposer could
even notice. The likely failure is not a bad answer; it is a slow drift in
seat quality that every dashboard labels as the same seat that used to pass.

Protections, all cheap at this volume:

- Treat any change in a seat's identity elements - model alias, provider,
  harness CLI version, system prompt, effort - as a new seat: a frozen-canary
  pass (the acceptance fixtures already exist) before it takes production
  runs, with the canary score recorded in provenance.
- Pin harness CLI versions in desired state; a CLI upgrade is a seat change,
  not an ops detail.
- Alarm per-run eval scores against the seat's rolling baseline instead of
  only storing them.
- Give routing a fallback chain for hard provider failures, with the fallback
  recorded in run provenance.

Second blind spot: **the improvement proposer is the designed-in injection
target.** It is the one component whose job is reading raw transcripts - every
hostile request body, OCR string, and tool output ever captured - and its
output is policy PRs, the only artifact that can weaken every future gate at
once. A86's bounds (n≥10, one open PR, bot-authored, human-merged, R19 form)
are the right shape. Add: proposer inputs restricted to typed outcome facts
plus bounded quoted spans, transcripts framed as untrusted data in its own
prompt, and its policy diffs routed through the same cross-family adversarial
review as code PRs - prose diffs are where a patient injection hides.

Third: **adjudication has no quality signal for what reviewers let go.** A77
measures findings (concede, refute, escalate) and arbitrates stood-firm
disputes, but nothing audits the runs where the reviewer found nothing, and
nothing tracks whether refuted findings later proved right (post-merge reverts
attributed to the originating run). "Reviewer found nothing" and "author
refuted everything" are both free moves until a sampled human audit and a
refutation-accuracy column exist in the ledger.

## 5. What you will wish you had instrumented on day one

1. **Request → ready-for-review latency, decomposed.** The job statement
   promises a draft PR within the hour; that latency and its breakdown are the
   numbers the factory will be judged on: queue wait, worker boot, model time,
   verify, CI, preview, publish. The events ledger yields stage durations for
   free; what it does not yield is *cap-blocked wait* - a run parked behind
   the 2-open-PR cap. Make that an explicit state or timestamp pair from day
   one, because it will dominate the decomposition whenever approvers are
   busy.
2. **The survival metric's +14-day job.** The constitution's cost metric is
   per surviving fix - merged, not reverted or rewritten within two weeks.
   Nothing in the packet schedules the fourteen-day re-check, so the headline
   metric is unmeasurable as designed. Day one: a scheduled reconcile of every
   merged factory PR at +14 days (deployed SHA vs. merge SHA, revert/rewrite
   detection) writing a survival label to the ledger.
3. **First-pass-approval ratio with its >98% drift alarm**, computed from the
   ledger and surfaced per the constitution's measurement rules - sustained
   >98% is an alarm to report, not a win to celebrate.
4. **Routing and boundary events:** seat requested vs. resolved (with
   routing-config version), provider response codes, retries and fallbacks,
   worker egress denials, metadata/private-network probes, credential
   issue/expiry timestamps, teardown completeness, orphaned-droplet count.
   Bounded labels only; request text, prompts, and transcript content never
   enter metrics or span attributes.
5. **Recovery-path metrics:** supervisor restarts, LISTEN reconnects, last
   successful backlog sweep, duplicate-side-effect suppressions,
   impossible-transition attempts - and **kill latency** (control row written
   to worker confirmed terminated). The kill switch is the safety path; its
   latency is a safety metric, not a performance one.
6. **Capacity and recoverability:** bytes and inodes by artifact kind,
   95th-percentile bytes per run, PostgreSQL growth, snapshot age, backup age,
   last successful restore-drill date, desired-vs-applied commit per host. All
   are dashboard fields; all are cheap.
7. **One correlation vocabulary:** `request_id`, `run_id`, attempt, stage,
   base SHA, worker boot ID, preview lease ID on every event, span, and log
   line. High-cardinality IDs live in spans, logs, and ledger rows - never in
   Prometheus labels.

## 6. The boundary I would attack first

**The preview evidence-capture job on the control-plane VM.** It is the only
component that both renders attacker-influenced code (the agent-modified
Fieldbook branch, on a shared preview environment) *and* holds a reusable
cross-system credential (the dev-fleet bearer header file), while living on
the host that also holds the ledger, the artifact store, and the GitHub App
publishing authority. The implement worker is secret-free by design; the
browser job is not. Attack paths: agent-written JS/PHP to a Chromium renderer
exploit or helper-API abuse, yielding code execution as the evidence user on
the highest-value host; or an open redirect / DNS rebinding on the preview
side, navigating the helper off-lease so the bearer leaks to an attacker
origin and buys dev-fleet access. Host navigation restrictions are a
helper-config promise, not a boundary.

Make evidence capture a per-run, no-authority isolation job:

1. Fresh container or microVM; no PostgreSQL socket, GitHub App key, model
   credential, vault capability, repo credential, or artifact-tree mount.
2. Egress to the leased preview host plus DNS only; the private fleet and
   cloud metadata denied. Its egress profile is the preview host - it must
   not share the implement worker's model-provider boot profile.
3. One-use bearer delivered in tmpfs, destroyed at teardown.
4. Bounded outputs only - screenshot, extracted DOM, hashes, execution
   manifest - copied into the artifact store by the supervisor after the job
   has ended.
5. Adversarial fixtures: redirect chains, DNS changes, subresource
   exfiltration, popups, downloads, oversized pages, bearer disclosure,
   browser crashes.

Second target: **the policy-PR channel** (section 4) - the highest leverage
per success in the whole design, since one merged rubric weakening degrades
every future run and it is defended today only by human prose review.

Third: **the `grafana_ro` read views.** A84's sole TCP exception is
well-bounded at the network layer, but the packet never defines the views'
columns. The `requests` table holds verbatim request text and the pointers to
its screenshots; if a read view exposes those, the fleet Grafana becomes a
second store of sensitive request content under a different access list. Pin
the views to metadata and aggregates, use column-level grants rather than
table grants, and test the views against a fixture row containing canary
content.

And before implementation, collapse the auth contradictions named in the
verdict: one identity store (factory PostgreSQL users, argon2 sessions),
`factory_submit` / `factory_admin` roles, and every route - HTML, evidence,
control POSTs, and the SSE handshake - tested against that single
implementation.

## 7. One outright replacement

**Replace the self-hosted GitHub Actions runner on the control-plane VM with
GitHub-hosted runners.**

Section 1.1 engages A76's stated reason; the short form is that a Rust cache
action delivers most of the warm-build benefit, hygiene-CI minutes at this
volume cost about nothing, and no user-mode hardening removes the fact that a
code-execution service shares a kernel with the ledger host for a benefit that
is cheaper elsewhere. R4 stands: the coding runtime never moves to GitHub.

Because phase 1 is unbuilt, migration cost is two to four hours:

1. Flip `runs-on` to a GitHub-hosted image and add the cache action.
2. Delete the runner user, systemd unit, registration-token flow, and Ansible
   roles from the build plan.
3. Confirm every workflow is hermetic, credential-free, and needs no
   private-network or factory-state access.
4. Run the full CI suite at a fixed commit; record timings and minutes cost.
5. Update the threat model and A76's runner clauses accordingly.

If a future workflow genuinely needs private-network resources, use an
ephemeral single-job runner on a disposable host - never the ledger VM.

Named runner-up, conditional: **Selenium → Playwright for the evidence
harness**, if and only if the helper is being substantially rewritten for
phase 1 anyway. Playwright's pinned browser bundle removes the matched-pair
treadmill (section 3.2), and its network-interception model fits the
off-lease-navigation tests (section 6). If the existing Selenium helper works,
keep it and pin the pair - do not rewrite working evidence tooling for
elegance.

## Priority before the build gate opens

### Required before the first live request

1. NOTIFY-as-hint recovery: startup and timer claim-scan, idempotent
   transitions, polled kill rows (section 2).
2. Evidence-job isolation with its own no-authority egress profile (section 6).
3. Backup destination, RPO/RTO, and a clean-VM restore drill as an acceptance
   gate (sections 2, 3).
4. Resolve the publisher-placement contradiction (control-plane VM), the auth
   language (one store), and the spec version (one number) (verdict).
5. Snapshot refresh owner, migration trigger, staleness alert (section 3.1).
6. Day-one instrumentation: cap-blocked wait, the +14-day survival reconcile,
   the drift-alarm ratio, kill latency, boundary counts (section 5).

### Scope to remove or defer

1. GitHub-hosted factory-repo CI instead of the self-hosted runner (section 7).
2. Defer `/schema` + the A81 introspection pair + ER CI check, `/bench`, the
   `/model` overlay, and page-view ledger rows (sections 1.2-1.3).
3. Keep `tracing` instrumentation; make a new Tempo deployment the fleet's
   decision, post-launch (section 1.4).
4. Time-box Firecracker to a half-session probe; qualified rootless Podman is
   acceptable on the disposable worker (section 1.5).

### Do not add yet

Kubernetes, a cloud queue, Loki, an object-store application dependency, or
more reviewer families - none addresses the first failures above. At 10x
current demand, re-evaluate worker count, preview slots, and incremental
backups from measured queue age, service time, bytes per run, and incident
history - not before.

## Appendix: convergence and divergence with the Grok 4.5 review

That review was visible while this one was written, so independence is claimed
at the level of derivation, not exposure. Convergence worth weighting in
disposition (both reviews reach these from the packet independently):

- `LISTEN/NOTIFY` must be a wake-up hint with idempotent, state-derived
  recovery; the stranded-row failure is a 1x failure.
- Backup needs an off-host destination and a clean-host restore drill.
- Evidence capture must move off the ledger host behind a no-authority
  boundary; both reviews name it the first attack target.
- The publisher-on-orchestration wording and the `forward_auth`/members-store
  language are pre-build defects, not style issues.
- The self-hosted runner is the top outright replacement.
- Firecracker gets a time-box; convenience projections and page-view rows are
  phase-1 fat; canary fixtures should gate seat-identity changes; the proposer
  must treat transcripts as untrusted data; correlation fields and
  no-sensitive-telemetry rules belong in the day-one contract.

Divergence:

- **Projection views:** Grok defers all four; this review keeps `/decisions`
  and static `/model` (near-zero marginal cost, serving the transparency
  story) and defers only `/bench`, `/schema` + the A81 introspection pair, and
  the live overlay.
- **Q4 center:** Grok's is common-mode oracle failure - shared task framing
  corrupting every seat at once. This review's is identity-vs-behavior drift
  plus the n≥10 detection lag. Different failure modes; overlapping
  prescriptions (independent evidence channels over more debate); both stand.
- **Q5 additions not in Grok:** the +14-day survival reconcile, the >98%
  drift-alarm instrumentation, cap-blocked wait as an explicit state, and kill
  latency as a safety metric.
- **Q6 additions not in Grok:** the proposer policy-PR channel as second
  attack target and `grafana_ro` view-column scoping as third; Grok's second
  boundary is the runner, which both reviews remove in section 7 anyway.
- **Q2 framing:** Grok puts human-review saturation at roughly 3x; A31 already
  rules review capacity binding at 1x, and the cap converts that into queue
  age from day one - instrument it now, not at a multiple.
