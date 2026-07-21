# Patchyard Factory stack council review

*Prepared 2026-07-21 from `2026-07-21-stack-council-packet.md` only. I did not consult the other council reviews.*

## Executive verdict

The core is well chosen for the stated scale. PostgreSQL, Rust, Axum/Askama, systemd, Ansible, OpenTofu, a filesystem artifact store, and a dedicated secret-free execution host are a coherent small-system stack. The deliberate exclusions are mostly right. Adding Node, Kubernetes, a cloud queue, or a third-party factory control plane would increase the failure surface without solving a current problem.

The design's main risk is not throughput. It is that some hostile execution still appears to occur on the credentialed control-plane host, while some durability properties are described as though `LISTEN/NOTIFY` and GitOps make them automatic. Before the build starts, I would make four changes:

1. Move browser evidence capture off the control-plane VM into a disposable, secret-free boundary with network enforcement.
2. Specify a durable reconciliation loop around every `LISTEN/NOTIFY` path. Notifications may wake work; rows must determine work.
3. Define off-host backup, restore, and loss-of-host acceptance, not only `pg_dump` plus a local manifest.
4. Use GitHub-hosted CI runners for credential-free repository checks instead of a runner sharing the control-plane kernel.

I would also defer Firecracker, an active Tempo backend, and the automated improvement proposer until observed operation gives each one a job. Keep the interfaces that permit those additions later.

## Priority findings

| Priority | Finding | When it breaks | Recommendation |
| :-- | :-- | :-- | :-- |
| P0 | Headless Chromium renders agent-produced application output on the control plane | Current scale; one malicious or compromised patch is enough | Run evidence capture in a disposable worker/browser sandbox. Permit only the leased preview host and a narrow artifact-return path at the network layer. |
| P0 | `LISTEN/NOTIFY` wake-ups have no explicit repair protocol | Current scale; a restart, disconnect, or listen/commit race is enough | On start and reconnect, scan durable queued/control rows. Re-scan periodically. Make claims and control execution idempotent. Measure notification-to-reconciliation gaps. |
| P0 | Backup language does not establish off-host recoverability | Current scale; loss or corruption of the control-plane disk is enough | Encrypted off-host database and artifact backups, a declared RPO/RTO, automated integrity checks, and a clean-host restore drill before go-live. |
| P1 | The self-hosted GitHub Actions runner shares the control-plane kernel | Current scale; repository CI is an attacker-controlled execution surface | Make GitHub-hosted runners primary for credential-free CI. If a private runner becomes necessary, put it on a separate disposable VM. |
| P1 | Preview evidence uses a shared mutable database | Current scale; concurrency is not required for external or background mutation to invalidate evidence | Give each evidence run a snapshot identity and isolated database/schema, or prove and continuously check that the leased preview dataset cannot change during capture. |
| P1 | “Short-lived, spend-capped” model credentials are a requirement without an issuance protocol | Current scale; the security invariant depends on it | Prove issuance, delivery, expiry, revocation, crash cleanup, and provider-side spend enforcement for every seated provider before that provider is eligible. |
| P1 | The packet contains stale host-boundary language | Build time | Remove the statement that publisher worktrees live “on orchestration”; it conflicts with A68. Resolve whether OpenTofu has one controller or two, and replace the remaining `forward_auth` wording with factory-native auth. |
| P2 | Phase 1 contains several pre-data optimization loops | No immediate break; they consume build and operating attention | Start with static versioned seat selection, one reviewer, manual improvement review, and dormant trace export. Add machinery from ledger evidence. |

## 1. What is over-engineered at 20 runs/week?

### Firecracker-first evaluation

Use hardened rootless Podman first, on a disposable secret-free worker, and retain Firecracker as an escalation. The dedicated host has no fleet access, durable data, GitHub credential, database identity, or reusable provider credential. At this scale, a microVM image pipeline, kernel/rootfs patching, KVM qualification, guest boot diagnostics, and a second isolation implementation create more operational risk than they remove.

This simplification is safe only if “ephemeral worker droplet” means what it says. If the droplet survives across runs, a container escape can persist and observe later per-run credentials or alter later output. The design must state whether the droplet is per-run, periodically replaced, or long-lived. Rootless Podman is the right default if the host is destroyed or re-qualified after a boundary failure. Firecracker becomes justified if hostile multi-tenant workloads share a host, a persistent worker must be trusted after arbitrary code execution, or testing demonstrates an unacceptable kernel-risk path.

### Active Tempo in phase 1

Instrument with `tracing` and stable correlation IDs from day one, but initially leave OTLP export disabled. The ledger, append-only events, complete bounded transcripts, Prometheus metrics, and Caddy/system logs already answer most phase-1 questions. Operating Tempo before there is a distributed system or a measured debugging gap produces another retention policy, upgrade path, certificate path, and failure mode.

A sensible trigger is evidence from several incidents that cannot be reconstructed from the ledger and transcripts, or expansion to a concurrent worker pool where cross-host timing is materially hard to follow. The code-level span structure is cheap to preserve now; the backend is cheap to add later.

### Automated improvement proposer and elaborate adjudication

At 20 runs/week, the first 50 to 100 runs should be reviewed by a human using SQL and sampled transcripts. A scheduled proposer with threshold logic, ideas fallback, open-PR serialization, its own prompt, and its own learning governance is an additional production subsystem before the factory has demonstrated stable operation. Defer it without weakening R19: humans can still put every lesson through a reviewed policy diff.

Likewise, keep seat routing versioned but static. One builder and one cross-family reviewer are sufficient initially. Add third-family arbitration only after real unresolved disputes show that it is useful. More reviewers can amplify shared error as easily as they reduce it.

### Self-hosted CI on the control-plane VM

This is both over-engineered and less isolated than the simpler option. The credential-free checks are already designed to be backend-swappable. GitHub-hosted runners remove runner registration, updates, ephemeral-mode supervision, resource caps, and same-kernel risk. They do not add a new control plane: GitHub already owns the repository, pull-request checks, and merge gate.

### Choices I would retain

- PostgreSQL rather than SQLite or MySQL for factory state. The role matrix, append-only ledger, leases, and reconciliation semantics justify one local database daemon.
- Axum, Askama, SSR, SSE, and slight vanilla JavaScript. This is proportionate to three users and avoids a second application runtime.
- Systemd plus Ansible rather than Kubernetes or Docker Compose.
- The local filesystem artifact store. Object storage is unnecessary while there is one control plane, provided off-host backup and capacity limits are real.
- The dedicated worker boundary and one-provider egress. Those respond to the threat model, not traffic.

## 2. What is under-engineered, and what breaks first?

Several things can fail at 1x scale:

1. **Wake-up loss.** PostgreSQL notifications are transient. The correct protocol is: establish `LISTEN`, scan durable eligible rows, process notifications as hints, scan after reconnect, and run a slow periodic repair scan. Control rows need the same treatment. Claiming, killing, resuming, publishing, and lease release must each be safe after duplicate delivery and crash replay.
2. **Host-loss recovery.** PostgreSQL and artifacts share the control plane's fate. A manifest detects mismatch but does not survive disk loss unless both sides are copied elsewhere. Restore testing should include users, peer-role mappings, sessions or intentional session invalidation, artifact hashes, ledger-to-artifact referential checks, and the ability to reconcile open PRs after recovery.
3. **Evidence reproducibility.** A code SHA does not identify database state. Browser evidence against a shared mutable preview DB can be irreproducible even with read-only browser actions. Record and isolate a database snapshot/fixture identity just as the worker records the MySQL parity artifact.
4. **Native-auth details.** The packet specifies Argon2 and server-side sessions but not CSRF tokens, login throttling, session fixation prevention, secure cookie attributes, idle and absolute expiry, account disable/reset, or audit events. These are phase-1 requirements because the same session can submit work and issue kill controls.
5. **Credential feasibility.** The system needs a concrete capability broker, not an adjective. If a provider cannot issue a short-lived, independently capped credential, that provider does not satisfy A61 until an enforceable proxy or equivalent boundary exists.

Capacity pressure arrives later:

- **Around 2x current volume:** one worker and the two-open-PR cap become the first queueing bottlenecks. Current intake is about four requests per workday. By Little's Law, a cap of two supports that rate only if a ready PR remains open for about half a workday on average. At eight requests/day, the average must fall to about a quarter day or the queue grows continuously. That may be an intentional quality throttle, but the dashboard should show it as such.
- **Around 3x to 5x:** a single preview slot and worker boot/image/snapshot time dominate. Add a small worker pool and use PostgreSQL row claims; this still does not require a cloud queue. `SKIP LOCKED` earns its place only here.
- **Around 10x:** artifact bytes, transcript retention, database connection counts from SSE/Grafana, and provider rate limits need explicit capacity planning. PostgreSQL, systemd, and the SSR application can still handle this volume. The likely changes are worker concurrency, preview isolation, and perhaps object-backed artifact copies, not Kubernetes or a new application framework.

## 3. Underestimated operational burden

The redacted MySQL parity artifact is likely the largest recurring cost. It needs an owner, refresh cadence, schema-drift detection, redaction regression tests, provenance, retention, rollback, and a response when production schema changes but a safe snapshot cannot be produced. “Fail-static” is correct, but the dashboard must say that a run used stale parity and policy must say when stale becomes ineligible.

The next largest burden is the two-VM GitOps loop. The packet says OpenTofu runs only from orchestration, while also saying the control-plane VM can re-apply its desired state. Pick one writer for infrastructure state. Backend locking prevents simultaneous OpenTofu mutation, but it does not settle ownership of Ansible runs, repo checkout freshness, secret-reference resolution, or partial convergence. A practical model is: orchestration is the sole infrastructure controller; the control plane runs the factory and can restore its services from a pinned checkout, but does not mutate cloud resources. Runtime independence from orchestration still holds.

Before go-live, assign an owner and tested procedure for:

- PostgreSQL major/minor updates, schema migration rollback, database growth, backup encryption, restore, and role-grant drift.
- Artifact retention, transcript size bounds, disk-full behavior, orphan cleanup, and ledger/artifact consistency.
- Chromium/browser updates and evidence compatibility; Caddy updates and certificate expiry; Rust and OS security updates.
- GitHub App key rotation, model-provider credential rotation, session invalidation, operator SSH key rotation, OpenTofu backend credentials, DigitalOcean credentials, and Route 53 credentials.
- Rootless Podman image rebuilds and MySQL 8.4 image/snapshot compatibility. If Firecracker remains, add guest kernel and rootfs patching.
- Fleet Prometheus/Grafana/Tempo datasource changes and the `grafana_ro` TLS certificate. Direct PostgreSQL access should fail without affecting factory runs.
- Clean rollback after a partial OpenTofu apply, partial Ansible converge, broken control-plane binary rollout, and incompatible database migration.

At this scale, a nightly encrypted off-host backup may be enough if a 24-hour RPO is consciously accepted. Whatever interval is chosen, a scheduled clean-host restore is more valuable than a more sophisticated backup tool. Test it before the first live request and then at least quarterly and after material schema/artifact-layout changes.

## 4. AI-layer blind spot

The principal blind spot is **correlated semantic error presented as independent review**.

Different model families do not create an independent oracle when builder and reviewer see the same request framing, repository conventions, tests, generated evidence, and likely public programming priors. A builder can produce a plausible but wrong interpretation, targeted tests that encode the same mistake, and evidence selected around that interpretation. A cross-family reviewer can agree for the same reasons. A third model then increases consensus, not necessarily truth. This is most dangerous when the human merge gate comes to treat a clean evidence package as proof rather than an argument.

Improve independence before increasing reviewer count:

- Give the reviewer the base tree, request, and patch, but withhold the builder's rationale and proposed tests on its first pass.
- Require the reviewer to state an independently derived behavioral oracle and identify what observation would falsify it.
- Keep blind acceptance fixtures inaccessible to implementation and review seats. Measure escaped defects and false confidence by seated pair, not only pass rate.
- Prefer deterministic domain assertions, differential behavior against the base, and exact data invariants over model votes.
- Randomly deep-audit a sample of passing PRs and feed post-merge regressions back to the bench. A bench that sees only pre-merge fixtures will select for fixture performance.
- Pin and hash agent CLI/harness binaries and configuration, run permission canaries before route changes, and treat provider/model behavior drift as a deployment even when the advertised model ID is unchanged.

The existing rule that empirical disputes resolve by running the check is good. Extend it: when no decisive check exists, the result is uncertainty for the human reviewer, not model-majority approval.

## 5. What to instrument from day one

The most valuable day-one observability answers two questions: “why is this run waiting?” and “can this evidence be reproduced?” Record the facts in the ledger where they are authoritative and expose low-cardinality aggregates through Prometheus.

Instrument:

- Separate timestamps for intake wait, cap/throttle wait, lease wait, worker provisioning, provider wait, execution, verification, preview wait, evidence capture, and human review. Use stable reason codes for every wait and terminal state.
- Lease acquisition, renewal, expiry, steal/recovery, and release; supervisor restarts; PostgreSQL listener reconnects; repair-scan discoveries; notification-to-row latency; duplicate-control suppression.
- Worker image hash, OS/runtime versions, MySQL snapshot identity and age, boot/teardown duration, cleanup result, cgroup OOM/timeout, denied network attempts, and credential issue/expiry/revocation results.
- Provider request attempts, provider request IDs, rate limits, retry classes, time to first output, schema/contract violations, tokens, claimed cost, and later reconciliation to provider billing.
- Artifact bytes by kind, transcript completeness or truncation, capture failures, checksum failures, orphan count, retention backlog, filesystem headroom, database size, backup age, and last successful restore drill.
- Preview slot identity, database snapshot identity, expected and observed SHA, redirects and blocked destinations, browser crash/timeout, and header issuance/expiry.
- Login failures, session creation/expiry/revocation, permission changes, request submissions, pause/resume/kill actions, artifact reads, and rejected uploads.
- Queue depth and oldest queued age, open-PR-cap utilization, PR reconciliation staleness, worker utilization, and success/failure/escalation rates by stage and versioned route.

Use one correlation identifier across ledger events, transcripts, artifacts, worker execution, preview evidence, PR body, logs, and spans. Do not put request IDs, branch names, user names, or artifact paths into Prometheus labels. Those belong in the ledger, structured logs, or traces; metrics should retain bounded cardinality.

## 6. Security boundary to attack first

I would attack the **evidence browser on the control-plane VM** first.

It renders a page produced by an agent-authored patch and sends a privileged preview header. A malicious patch can emit active content, redirect, probe private addresses, attempt to leak the header, exploit browser/parser vulnerabilities, or target services reachable from the control-plane network. Selenium navigation checks are useful evidence controls but are not a network security boundary. Chromium's own sandbox also should not be the boundary protecting publisher credentials, the ledger, artifact store, and factory secrets.

Run Chromium inside a disposable evidence environment that has:

- no factory, GitHub, database, SSH, or fleet credential;
- a preview capability scoped to one host, one run, and a short TTL;
- network-layer allowlisting for the exact leased preview destination, with redirects re-evaluated and private/metadata ranges denied;
- a single bounded return channel for screenshots, DOM extracts, hashes, and an execution manifest;
- clean teardown before the publisher receives the result.

The next target would be the co-resident GitHub Actions runner. A dedicated Unix user and systemd hardening reduce accidental access, but untrusted CI still shares the host kernel and network. Moving credential-free jobs to GitHub-hosted runners is the simpler fix.

Also verify that triage and adversarial-review subprocesses really execute inside an OS boundary with no valuable filesystem or environment access. Tool allowlists such as Read/Grep/Glob are harness policy, not containment.

## 7. One choice to replace outright

**Replace the self-hosted GitHub Actions runner on the control-plane VM with GitHub-hosted runners as the phase-1 default.**

The repository CI is deliberately credential-free and wrapped in backend-neutral scripts. GitHub already hosts the repository, PR state, and merge gate, so using its runners does not introduce a new control-plane dependency. It removes an upgradeable daemon, registration-token lifecycle, resource contention, and an avoidable same-kernel execution boundary from the most sensitive host.

Migration cost at this scale is roughly half a session:

1. Change `runs-on`, preserve the pinned Rust/tool versions, and add or verify caches.
2. Run the complete hygiene suite on the hosted image and compare output to the local scripts.
3. Remove the runner user, systemd unit, network allowances, and provisioning tasks from the control plane.
4. Keep live read-only OpenTofu plans and Ansible checks as an explicitly invoked orchestration-side review artifact; do not move infrastructure credentials into PR CI.

If hosted runners later cannot meet a measured requirement, the replacement should be a separate ephemeral runner droplet, not a return to the control-plane VM.

## Recommended pre-build disposition

### Must resolve before session 1

- Evidence browser isolation and enforced network policy.
- Durable queue/control reconciliation protocol.
- Worker-droplet lifetime and cleanup contract.
- Off-host backup plus clean-host restore acceptance.
- One infrastructure-state controller and correction of stale orchestration/`forward_auth` text.
- Concrete model-credential issuance and revocation qualification.
- Native-auth session and CSRF requirements.

### Simplify before build

- Rootless Podman first; Firecracker only on a stated escalation trigger.
- GitHub-hosted CI; no runner on the control-plane host.
- `tracing` instrumentation with OTLP export dormant; add Tempo when evidence shows a need.
- Manual learning review until enough real runs exist; defer the improvement proposer and third-family arbitration.

### Keep as designed

- Human-only merge and reviewed policy changes.
- PostgreSQL as ledger, queue state, and source of truth, with notifications used only as hints.
- Rust/Axum/Askama/SSR and the no-Node client.
- Systemd, Ansible, OpenTofu, and a local artifact store.
- Dedicated secret-free worker execution, provider-specific egress, exact-base-SHA publishing, and deterministic verification.

With those changes, the stack is appropriately small, auditable, and capable of growing several multiples before it needs a new architectural layer.
