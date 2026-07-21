# Stack council review - Patchyard Factory technology stack

*2026-07-21. Reviewer: Grok 4.5 (outside council). Packet: `reviews/2026-07-21-stack-council-packet.md`. Targets: `docs/stack.md` (exclusions + inventory) in the context of `SPEC.md` phase-1 architecture and the generated model diagram. Phase 1 is not yet built; this is a pre-build stack review, not a code review.*

## Calibration and ground rules (how this review is read)

Scale accepted as stated: ~20 requests/week, three named users, one subject codebase (Fieldbook), two standing VMs plus an ephemeral secret-free worker droplet. Recommendations below are sized to that. Where a larger system would need something this one does not, the form is "at Nx you would need Y," not "you need Y."

Invariants A1, R19, A68, A57/A59/A61, and ledger-as-authority are treated as fixed design constraints. Exclusion challenges engage the *stated reason*, not popularity. I do not re-open "should agents merge" or "should policy auto-revise."

## Verdict

**Build phase 1 from this stack, with three deliberate simplifications and one security-first probe order.** The core shape - Rust control plane, PostgreSQL ledger with peer auth, OS-enforced worker isolation, human-merged PRs, harness-exec'd agents, ledger-first observability - is correctly sized for a small travel company that cannot afford a platform team and cannot afford a credentialed agent on untrusted screenshots.

The stack is **not** over-engineered in its *safety architecture*. It is over-engineered in its *day-one observability and IaC surface*, and it is under-engineered in a few places where complexity hides behind "evaluate first" or "fail-open." The biggest operational risk is not traffic; it is the two-host GitOps + dual-engine (Postgres factory / MySQL subject) maintenance burden on a team of one IT owner plus agents. The first boundary I would attack is not Firecracker; it is the control-plane publisher and the short-lived model credential path that must still touch the secret-bearing plane.

---

## 1. Over-engineered for 20 runs/week - delete or simplify with no loss

These are simplifications that preserve the invariants and the lethal-trifecta split. They do not remove isolation, human merge, or ledger authority.

### 1.1 Defer Tempo / OTLP shipping until the first real "where did stage X hang?" incident

**Keep** day-one `tracing` instrumentation and journald (A82's free half). **Defer** the OTLP exporter, Tempo adoption, and the config plumbing that couples the factory to a fleet collector that may not exist on day one.

Reason at this scale: ~20 runs/week produce a few hundred stage transitions. The ledger already answers cost, outcome, stage, tokens, and duration. Transcripts (A83) answer "what did the agent do." Spans answer "which subprocess waited on which socket" - valuable, rare, and easy to retrofit once the instrumentation hooks exist. Shipping Tempo in the same 17-session baseline as Firecracker eval, MySQL parity snapshots, and native auth is concurrent complexity with low early yield.

What you lose by deferring: multi-service waterfall charts across supervisor → worker SSH/bootstrap → harness. At one control plane and one worker, journald + ledger timestamps + transcript wall clocks cover the same questions for months.

At 10x (200 runs/week) or when stage latency becomes the dominant complaint, re-enable the exporter - instrumentation is already there.

### 1.2 Collapse "GitOps maximalism" for GitHub repo settings and Route 53 until second host exists

**Keep** OpenTofu for the two DigitalOcean droplets, firewalls, and tags; Ansible for host config; encrypted remote state. **Defer** OpenTofu-managed GitHub branch protection and Route 53 records as *phase-1 blockers*.

Reason: those objects change a handful of times a year. Encoding them is good doctrine (A69) but each provider adds token scope, plan noise, and a failure mode on apply day. Manual (or one-shot scripted) DNS + branch-protection checklist for a single hostname and a single repo is cheaper than a third OpenTofu provider onboarding during session 0-2. Encode them in git as *documented desired state* (markdown + checked-in JSON export) if you must version them without live apply.

At 3+ hostnames or multi-repo branch-rule drift, graduate the providers.

### 1.3 Do not run a self-hosted GHA runner on the control plane until CI time is painful

**Keep** thin YAML wrappers and GitHub-hosted runners as default. **Defer** A76's control-plane self-hosted runner until cold Rust builds or minute cost actually bites.

Reason at this scale: a second unprivileged user, registration token lifecycle, resource caps, and "zero factory-state access" proofs on the *same box* as PostgreSQL and the publisher is operational surface for a problem you may not have. Hosted runners are the fallback A76 already names; starting there and flipping `runs-on` later is exactly the thin-wrapper promise.

Challenge to the stated reason ("Rust builds eat minutes"): true for large monorepos; for a greenfield multi-crate factory with modest CI matrix, hosted is fine for phase 1. Revisit when CI wall time > developer wait tolerance or minutes appear on a bill someone cares about.

### 1.4 Improvement proposer (A86) as a manual/scripted seat, not a phase-1 session

**Keep** the R19 shape (lessons as PRs, evidence thresholds, policy surface only). **Defer** the scheduled autonomous proposer to after n≥10 real runs exist - which is definitionally after cutover.

Reason: session 14 builds a seat that, by its own gate, cannot open policy PRs until enough evidence accumulates. Before that it only appends to `ideas.md`. A monthly human or ops-agent pass over ledger SQL + ideas.md produces the same artifact with zero daemon surface. Re-introduce the scheduled seat when the evidence exists to exercise it.

### 1.5 What not to simplify

Do **not** drop: peer-auth PostgreSQL role matrix, secret-free worker droplet, factory-native auth, harness-exec boundary, mutation-tested factory-verify, artifact store outside Git, draft-PR evidence lifecycle, or Firecracker-first isolation eval. Those are load-bearing for the trust model, not vanity for 20 runs/week. SQLite-instead-of-Postgres was already correctly superseded (A56): the role matrix is the product of the choice, not the query volume.

---

## 2. Under-engineered - what breaks first, and at what multiple

### 2.1 Breaks first at 1x: worker environment parity (A85) is the long pole and the silent quality leak

The design correctly says parity-by-artifact, never parity-by-access. What is under-specified for *ops*, not architecture:

- **Snapshot refresh fail-static** means a six-month-old redacted MySQL dump still "works" while schema drift vs prod Fieldbook makes every PHPUnit and Selenium pass a lie relative to production.
- **Who owns the redaction pipeline** when manager-sandbox lineage changes is not a stack choice; it is a single-person bus factor.
- **Firecracker vs Podman is still open.** "Evaluate first" is fine in a packet; as a build blocker it means session 3 can produce a decision document while the rest of the plan assumes a substrate.

What breaks first in practice: a green factory run against a stale snapshot, merge of a patch that fails on real `fieldbook_db`, and loss of trust in the factory. That is not 10x traffic - it is the **first production-shaped request** after ALPHABETIZE.

Mitigation that fits scale: pin snapshot max-age as a hard gate (fail the run or mark evidence `parity-stale` rather than fail-static forever), and make "snapshot younger than N days" a dashboard admin badge. Do not wait for 10x.

### 2.2 Breaks around 3-5x (~60-100 runs/week): single-worker serialization and preview slot contention

LISTEN/NOTIFY and one worker droplet are correct at 20/week. At a few concurrent staff submissions (or one stuck implement + a queue), the 2-open-PR cap and daily limits protect GitHub and humans, but:

- One worker boot at a time (implied by one droplet + isolation) makes p95 latency a queueing problem, not a model problem.
- Preview leases on a **shared mutable preview DB** (SPEC) will collide or produce non-reproducible DOM evidence under parallel ready-for-review pressure.

At 3-5x you need either a second worker droplet (same Ansible role, N inventory entries) or explicit single-flight with honest Patchyard on the receipt - not Kubernetes. At 10x you need the second worker and preview isolation (DB snapshot per lease or read-only replica), still not a cluster orchestrator.

### 2.3 Breaks around 10x: control-plane disk and transcript retention

Full transcripts (A83) + screenshots + MySQL snapshot artifacts + worktrees will dominate `/var/lib/patchyard` long before CPU does. 90-day retention is stated; **restore drills and disk-full behavior** are the under-engineered part. At 10x, retention-sweep bugs become outages. Prometheus will show disk; the ledger will not if artifact GC fails silently.

### 2.4 Breaks only at much higher multiples (do not buy now)

- Postgres LISTEN/NOTIFY fan-out and single-node Postgres: fine past 100x of this load.
- SSE to three browsers: fine.
- Axum/Askama SSR: fine.
- Replacing peer auth with a connection pooler: not before multi-host app tier, which you should not have.

---

## 3. Operational burden underestimation

This is where the design is most optimistic relative to a two-person IT+GM world.

### 3.1 Two-VM GitOps loop

OpenTofu from orchestration → Ansible converge → control plane self-applies → worker replaceability is four moving parts with four failure modes (state lock stuck, inventory drift, partial Ansible, secret injection path wrong). Phase 1 acceptance includes clean-room worker replacement - good - but **does not budget a clean-room control-plane restore** with the same rigor. The ledger + artifacts *are* the business record of the factory; the worker is disposable. Ops burden is inverted from the write-up's emotional focus: practice restoring the control plane from `pg_dump` + artifact manifest + Ansible, not only rebuilding the worker.

Underestimated costs:

| Item | Why it bites |
| :-- | :-- |
| OpenTofu state backend + lock recovery | Rare, high-panic; document break-glass with two people who know it |
| Ansible second-converge emptiness | Rots when someone "just fixes" a unit on the box |
| Dual desired-state ownership | Orchestration applies vs control-plane self-apply - clarify who is allowed to apply what after day 0 |
| rust-toolchain + Firecracker/Podman + MySQL 8.4 + Chromium pins | Four upgrade clocks; security CVEs will not wait for a factory session |
| GitHub App key rotation | Publisher outage class; needs a rehearsed re-inject without re-bootstrap |
| Spend-capped model credentials | Short-lived is good; mint/revoke automation is still ops |
| Snapshot redaction refresh | Calendar work, not git work |
| `grafana_ro` TLS certs + VPC firewall to monitoring droplet | Sole TCP exception (A84); first hole when someone "temporarily" opens 5432 |

### 3.2 Upgrades

Rust minor upgrades are cheap with CI. **Harness CLI upgrades** (Claude Code, Codex) are not: they change stream-JSON shapes, flags, and exit codes that the supervisor parses. Pin versions, checksum installs, and treat harness upgrade as a factory release with a replay fixture - same discipline as `factory-verify` binary hash in provenance.

### 3.3 Backups

`pg_dump` + artifact-tree manifest is the right shape. Missing at stack level: **encrypted off-host copy**, restore time objective, and a calendar drill. Three users will not notice silent backup failure until the droplet dies. Put backup success into the same Prometheus scrape (node exporter textfile or a tiny cron metric) so the fleet Grafana already watching the host notices.

### 3.4 Cert and key rotation

Caddy automates public TLS. Still manual or vault-driven: GitHub App private key, any DO API token on the bootstrap host, 1Password service account for factory inject, model provider keys, `grafana_ro` client/server certs if used. Stack.md names 1Password as vault of record - good - but **rotation runbooks are not stack decorations; they are the difference between A68 on paper and A68 at 02:00**.

### 3.5 People load

GitOps maximalism shifts toil from "SSH and edit" to "PR and apply." For one primary operator that is a win only if apply is boring. If every small firewall tweak is a multi-repo plan, people will bypass (R19's cousin: lessons land as diffs - ops will land as `vim` on the box). Keep emergency break-glass documented and reconcile-after, or the desired state becomes fiction.

---

## 4. AI layer - failure mode the design is blind to

The design is strong on: exec boundary, one provider per boot, seat routing from bench, cross-family review, human merge, provenance hashes, no in-process SDK.

### 4.1 Blind spot: correlated harness and policy failure (not model family)

Cross-family review assumes **independent mistakes**. The underrated failure mode is **shared framing**: both families read the same constitution, rubric, skill prompts, and deny-lists. A wrong-but-clear rubric line, an outdated deny path, or a postcondition that encodes the bug as intended behavior will pass *both* builder and reviewer. Family diversity does not diversify policy.

Compounding form: the improvement proposer (A86) and seat routing (A74) both learn from ledger rates. If the verifier's postconditions are weak, high pass rates train the system to be confidently wrong. Adversarial review of *code* does not substitute for adversarial review of *acceptance predicates*.

Mitigation that fits: keep mutation self-tests (A10) as sacred; add a periodic human "rubric red team" on near-miss fixtures independent of model family; never let proposer PRs touch `factory-verify` predicates without the same merge gate as production code (already policy-surface-only - hold that line).

### 4.2 Blind spot: silent tool-boundary drift in headless CLIs

Harnesses gain tools, MCP hooks, and default permissions across releases. The supervisor's "no-shell triage" and "worker has only model egress" depend on **flags and sandbox defaults remaining stable**. A CLI update that enables broader tools by default, or that reads `~/.` config you did not know existed, is an isolation regression that no LISTEN/NOTIFY metric will show.

Mitigation: harness invocation is a single audited argv template per seat; CI fixture runs `strace`/`seccomp` or at least environment dumps in the qualification suite; pin CLI versions in provenance (already planned) and **fail closed on harness version skew** rather than "best effort."

### 4.3 Blind spot: spend-cap and provider outage as product outages

Short-lived spend-capped credentials are correct. At 20 runs/week, a provider outage or cap exhaustion does not look like "scale" - it looks like "the factory is down" for the one person who submitted. Fail-closed is right for safety; the missing product piece is a **clear, human-visible reason** on the SSE timeline (`provider_unavailable`, `spend_cap_hit`) distinct from model stupidity, so staff do not re-submit into a brick wall.

### 4.4 Blind spot: eval gaming of pass^k on a tiny fixture set

ALPHABETIZE + a few hidden cases will be memorized by prompt accretion and proposer feedback. pass^k=3 on a fixed set measures stability, not generalization. Blindness is claiming lane-A competence for Fieldbook broadly when the suite is still a handful of sort bugs.

Mitigation: treat hidden case expansion as a standing ops tax; freeze suite versions in provenance; score wrong-target rates, not only pass rates (SPEC already asks for wrong-target measurement - enforce it in the ledger schema day one).

### 4.5 Not blind (correctly handled)

In-process SDKs excluded, lethal trifecta split, human merge, transcript capture, and "telemetry is not evidence" are the right instincts. Do not weaken them.

---

## 5. Observability - what you will wish you had instrumented from day one

Ledger-first is correct. Fleet Prometheus scrape + fail-open OTLP + transcripts is a coherent shape. Gaps:

### 5.1 Instrument day one (cheap, high regret if missing)

| Signal | Why |
| :-- | :-- |
| **Stage transition timestamps in ledger with error class enum** | Already mostly planned; make `error_class` first-class (`verify_fail`, `provider_5xx`, `cap`, `kill`, `parity_stale`, `github_timeout`) - dashboards and proposer both need it |
| **Artifact store bytes per run and per kind** | Disk is the real capacity limit; bill/forecast before OOM |
| **Worker boot phase timings** | Image pull / snapshot seed / harness start / first token - otherwise "implement is slow" is un-debuggable |
| **Harness argv + version + exit code** as structured ledger fields | Not only in the transcript blob |
| **Publisher GitHub API latency and rate-limit remaining** | Fail-closed PR cap races need visibility |
| **Backup last-success timestamp** | See §3.3 |
| **Snapshot artifact age** | See §2.1 |
| **Kill / pause control-row metrics** | Ops health of attended mode |

### 5.2 Can wait

- Tempo waterfalls (see §1.1)
- Loki: journald + `journalctl` on two hosts is enough until log volume or multi-host search hurts; do not adopt Loki "because the stack diagram wants three letters"
- Client-side RUM: three users, SSR, no

### 5.3 Wish-you-had that is not metrics

**Join key from page-view rows (A79) to run ids** when the path is `/request/<id>` - so "did anyone look before merge?" is SQL, not log archaeology. Parse path parameters into a nullable `request_id` column at write time.

**Transcript redaction markers**: if a harness ever echoes env or secrets, you want a retention-time redaction path before the first incident, not after transcripts land in backups.

---

## 6. Security - which boundary to attack first

Trust architecture summary: untrusted content meets a secret-free worker; control plane holds GitHub App, model minting, ledger, artifacts; humans merge; dashboard is a scribe.

### Attack order I would use

**1. Control-plane publisher path and GitHub App key (highest value, smallest surface)**  
Compromise of the publisher identity yields arbitrary PRs as the factory bot, branch pushes, and social-engineering of human reviewers ("factory already verified"). Isolation of the worker does not help. Prioritize: key only in memory/tmpfs at mint, App permissions minimal (contents + PRs on one repo), no workflow scope, alert on App installation changes, and never reuse bootstrap DO tokens on the control plane.

**2. Model-credential minting and the channel that injects the per-run secret into the worker**  
The worker is secret-free *at rest*; the mint/inject path is the temporary bridge. Attack: steal the minting principal, swap the worker bundle, or exfiltrate the short-lived key via a compromised harness that still has provider egress (exfil to the *allowed* provider is still exfil of source+request). Mitigations: spend cap, TTL measured in minutes, one provider DNS/IP allowlist actually enforced by host firewall (not only "policy"), and no other egress including metadata endpoints.

**3. `grafana_ro` TCP exception (A84)**  
Sole intentional hole in A56's socket-only story. Attack: pivot from monitoring host, SQLi-via-Grafana plugin, or over-broad view grants (`SELECT` on raw request text). Keep views redacted for request bodies if dashboards only need aggregates; firewall to one IP; TLS required as written - verify it is not "TLS optional in phase 1."

**4. Dashboard upload / SSR surface**  
Classic path traversal, image bombs, session fixation. Blast radius is intentionally limited (scribe role) - good. Still a beachhead for targeting staff sessions and reading artifacts. Hardening acceptance criteria in SPEC are strong; do not skip the adversarial fixtures for schedule pressure.

**5. Worker breakout (Firecracker/Podman)**  
Important, and correctly prioritized in design rhetoric, but **third or fourth in expected attacker ROI** if the publisher and mint path are soft. A breakout without credentials and without private network is a noisy foothold; combine with (2) it becomes serious. Still run the qualification suite; do not skip KVM probe on the *worker* droplet.

**6. Supply chain: harness binaries and `cargo deny` exceptions**  
Less glamorous; high impact. Pin and checksum.

### What I would not attack first

LISTEN/NOTIFY injection, SSE, or three-user argon2 sessions - not because they are perfect, but because the value density is lower than the GitHub App.

---

## 7. One outright replacement

### Replace: Firecracker-first as a *phase-1 schedule commitment* with **rootless Podman as the default substrate, Firecracker as a measured upgrade**

**Not** "use Docker Compose" (exclusion reason stands: scale mismatch, systemd+Ansible own hosts). **Not** "skip isolation."

**Replacement:** ship phase 1 on **rootless Podman** (or the already-understood container path) with the full secret-free, egress-allowlist, no-KVM-required contract, and treat Firecracker as a **sessioned upgrade** when (a) the worker droplet has working `/dev/kvm`, (b) the image/snapshot workflow is stable on Podman, and (c) a concrete threat or compliance need justifies the microVM tax.

**Why the stated Firecracker-first preference is costly at this scale:**  
Firecracker brings a second packaging story (rootfs, kernel, vsock/net model), harder interactive debug, and a KVM dependency that SPEC already admits the orchestration host cannot prove for the new droplet. "Evaluate first" in a 17-session plan with MySQL-in-boundary and redacted snapshots often becomes "half of isolation works, Firecracker deferred, Podman undocumented." Starting on Podman makes the *contract* (secret-free, one provider, patch out) real earlier; microVMs improve the *depth* of isolation without being the critical path to first evidenced PR.

**Migration cost at your scale:** low if the supervisor only ever speaks "start isolation by run id / collect patch." Keep a thin substrate interface (`IsolationBackend`) from day one - that is the real stack choice. Switching backend later is a weekend + qualification suite, not a rewrite. Switching after Firecracker-specific assumptions leak into Ansible and snapshot format is a multi-session tax.

If Jacob's preference for Firecracker is non-negotiable as learning goal, keep the eval - but **do not gate ALPHABETIZE acceptance or sessions 5-9 on it.** Gate them on the isolation *contract* tests.

---

## Exclusions table - engagements only where the reason is wrong for this scale

| Exclusion | Engage the reason? | Finding |
| :-- | :-- | :-- |
| npm / TypeScript / WASM | No | A53 reason holds; three-user SSR admin tool gains nothing from a second type system |
| Docker Compose / k8s / Helm | No | Scale mismatch is correct; two systemd units + Ansible is the right ops model |
| In-process agent SDKs | No | Exec boundary is load-bearing for the lethal trifecta |
| Cloud queues | No | LISTEN/NOTIFY at this QPS is correct |
| Third-party control planes | No | R11 matches a company that cannot outsource the approval plane |
| Subscription-gated deps | No | R22 is rational for a small fleet |
| Plaintext tfstate in git | No | Non-negotiable |

No exclusion needs overturning. The over-engineering is in **adopted** phase-1 scope (Tempo, self-hosted runner, early proposer, maximal OpenTofu surface), not in the deny list.

---

## Answers scored against the seven questions (compact)

| # | Answer in one line |
| :-- | :-- |
| 1 Over-engineered | Defer Tempo shipping, GitHub/Route53 OpenTofu providers, control-plane GHA runner, and autonomous proposer until evidence or pain exists; keep safety architecture. |
| 2 Under-engineered | Snapshot freshness + substrate decision break at 1x; worker/preview concurrency at 3-5x; disk/transcripts at 10x. |
| 3 Ops burden | Control-plane restore, harness upgrades, key rotation, dual GitOps apply paths, and redaction calendar are understated relative to worker rebuild rhetoric. |
| 4 AI blind spot | Correlated policy/verifier failure across families; harness default drift; pass^k on a tiny suite; opaque provider/cap failures. |
| 5 Observability wish | Error-class enums, artifact bytes, worker boot phases, harness version/exit, backup and snapshot age, page-view→request_id join - before Tempo/Loki. |
| 6 Attack first | Publisher / GitHub App and model-credential mint path; then grafana_ro; then upload SSR; then worker breakout. |
| 7 Replace | Firecracker-as-critical-path → Podman-default + substrate interface; Firecracker as upgrade. Migration cheap if the interface is real. |

---

## Recommended dispositions (for the human adjudicator)

Per A77, these are proposed moves the author may concede, refute, or escalate - not automated changes.

1. **Concede and schedule:** defer Tempo exporter activation, self-hosted runner, and A86 autonomous seat from the critical path; keep instrumentation hooks and R19/manual ideas loop.
2. **Concede and design:** add `IsolationBackend` seam; default Podman for phase-1 acceptance; Firecracker remains preferred upgrade with recorded KVM probe.
3. **Concede and schema:** first-class `error_class`, snapshot age, artifact byte counts, harness version/exit in ledger.
4. **Ops addendum (not a stack swap):** control-plane restore drill + backup metric + key-rotation runbook before first live staff submission.
5. **Hold:** Rust control plane, PostgreSQL peer-auth matrix, secret-free worker, harness exec, human merge, no npm, no cloud control plane, ledger as authority.

---

## Closing

This stack is a serious, coherent answer to "how does a three-person company run untrusted-request automation without melting the fleet." The failure mode of the design is not fashion - it is **scope density**: too many correct optional systems (Tempo, maximal GitOps, self-hosted CI, microVM, proposer) scheduled as if they were as mandatory as the lethal-trifecta split. Ship the safety core and the evidenced PR path; let the rest graduate on measured pain at 1x, 3x, and 10x as above.

*End of stack council review.*
