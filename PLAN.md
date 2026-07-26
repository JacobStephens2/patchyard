# factory - phase 1 build plan

*(Companion to `SPEC.md`. The spec says what must exist and why; this plan says in what order, cut into sessions, each with a verifiable exit. Build remains gated on Jacob's explicit "go" - this document is prep, not build.)*

*Status: v5.1, 2026-07-21 (18 sessions; A86/A88-A94 amendments folded per the decision log; Session 0's A68 exit clarified after the approved E4 sequencing recommendation) - v4 of 2026-07-18 re-planned v2 after the adversarial review (`reviews/2026-07-16-plan-adversarial-review.md`; dispositions in `reviews/2026-07-16-plan-review-disposition.md`; all findings conceded; A86 later added the proposer session and A89 the evidence-isolation session - an 18-session baseline). v1's ~10+1 sessions re-baselined to ~15: same components, honest cuts - isolation qualification, preview-integrated verification, dashboard hardening, and post-cutover acceptance each get their own exit instead of hiding inside another session's. Builder: GPT-5.6 Sol [xhigh] via Codex on OpenAI (A78, amending A41). Cross-family adversarial reviewer: Fable 5 [max] via Claude Code on Anthropic on each build PR, under A87 isolation. *(Seat names corrected post-session-0; the original v5 text predated A78.)* Merge gate: engineering + owner (A33). v3 applies A56: phase 1 starts on local, socket-only PostgreSQL with peer authentication and role-enforced service boundaries; no SQLite or dual-engine implementation is built. v4 applies A57: phase 1 adds a dedicated secret-free worker droplet, OpenTofu + Ansible desired state, and a clean-room replacement exit, for ~16 sessions total.*

The factory's own macro-shape is Plan → Implement → Verify (A47), and lane B demands a plan before implementation. Phase 1's build is itself a lane-B job, so this is the factory eating its own process: `SPEC.md` is the approved spec, this plan is its Guide, and the session exits below are its human-approved budget.

## Ground rules for every session

- **Exit criteria are review anchors.** A session ends at its verifiable exit, which becomes the checklist for that build PR's review. No PR bundles two sessions unless both exits are met.
- **Spikes end on decisions, not implementations.** A spike session's deliverable is a recorded decision (in `research/` or `docs/`), even if its code is thrown away.
- **The factory repo gets infrastructure CI in session 0** (OpenTofu format/validate and Ansible lint/syntax) and application CI in session 1 (fmt, clippy, test, `cargo audit`, `cargo deny`, `./model/check-model.sh`). This does not conflict with R4: Actions is rejected as the *coding runtime for fieldbook changes*; the factory repo running its own test suite in CI is ordinary hygiene.
- **Nothing touches fieldbook prod.** All live-fire runs target scratch branches and the preview fleet until the acceptance matrix passes.
- **Model edits follow `docs/model-boundary.md`'s workflow** (bump `modelVersion`, `python3 model/model-id.py --write`, `python3 model/render-model.py`, `./model/check-model.sh`) and the generated json/schema/identity/mmd/svg/png under `model/` get copied to the orchestration VM's `hosted/` in the same change.
- **Nothing is called end-to-end before its dependencies exist.** An exit may use fixtures and seeded state when the real mechanism lands later, but must say so; the full-pipeline claims live only in the final acceptance session, which runs against the cut-over topology.

## Session sequence

Session 0 covers the worker desired-state component; sessions 1-2 cover the control-plane scaffold and state layer; 3-5 cover worker isolation; 6-7 the verifier plus remote-runtime integration; 8-9 the skill; 10 the publisher; 11-12 the dashboard; 13 the evidence lifecycle; 14 cutover; 15 final acceptance. There is no padded buffer - an overrun surfaces as an overrun instead of compressing the security and failure testing.

### Session 0 - desired-state foundation, control-plane VM, and worker droplet

- **A80**: the Ansible desired state installs node_exporter and postgres_exporter on both factory hosts, firewalled to scrape-only access - the factory exposes metrics, never pushes them; scrape access is allowlisted to the fleet monitoring droplet over the private network (A84). Fleet-side integration is two file_sd target entries in the observability repo - a small PR outside this repo, noted so session 0 doesn't forget it.
- **A96 backend adoption**: the hand-bootstrapped state backend (bucket `example-tofu-state` with its versioning/SSE/public-block/TLS-only/lifecycle configuration, IAM user `orchestrator-tofu-state`, inline policy `s3-patchyard-tofu-state`, and the widened `route53-patchyard-create-read` policy) is `tofu import`-ed into the desired state this session - and the import's first code change sets `route53-patchyard-create-read`'s correct description (AWS makes descriptions immutable, so tofu's create-before-destroy replace is the safe fix for the stale "CREATE-only" text; the ARN change lands in the same reviewed commit) - bootstrap-by-hand becomes drift-checked code, the A68 bootstrap-then-independence shape applied to the backend itself. Deliberate exception: the access key stays unmanaged so the secret never enters state.
- **A76/A88**: CI runs on GitHub-hosted runners with a Rust cache action - no runner is provisioned on any factory host (disposition E-1); the escalation path, if private-network CI is ever measured to be needed, is an ephemeral single-job runner on a disposable droplet.
- **A69**: the session's deliverable layout is `infra/<provider>` (nightloch pattern) - OpenTofu for droplets, Route 53 DNS, firewalls, and GitHub repo settings/branch protection; Ansible for all host config; encrypted state backend chosen and documented. Nothing about the factory is console-clicked from here on.
- **A68**: session 0 is the bootstrap act - orchestration agents create/initialize two hosts from one desired state: the control-plane VM (supervisor daemon, PostgreSQL, artifact store, dashboard, Caddy, headless Chromium, its own factory-repo checkout and secret injection) and the secret-free worker droplet. Session 0's exit proves structural independence: after initialization, desired state and runtime roles contain no dependency on the orchestration VM. Live serve/authenticate/run evidence belongs to the sessions that build those components and to final acceptance. `factory.example.com` DNS points at the control-plane VM.
- Entry: Jacob's "go". Pin OpenTofu and the Ansible runtime/collections on the orchestration controller; add `infra/opentofu/` and `infra/ansible/` with one documented plan, apply, check, replace, and rollback path.
- Configure DigitalOcean Spaces remote state with `use_lockfile`; backend and provider credentials come only from the controller environment. OpenTofu owns the worker droplet, cloud firewall, SSH public-key attachment, attachment to existing Patchyard tags, and inventory outputs. The worker receives no DigitalOcean credential.
- Ansible provisions the base OS, `factory-worker` user, packages, host firewall, management access restricted to orchestration, tmpfs/transient run paths, logging, and cleanup. No application/provider secret is copied.
- Exit: a human-reviewed plan is applied from orchestration; inventory feeds Ansible without hand transcription; the second converge reports no changes; a disposable clean-room replacement reaches the same state from Git; and secret scans find no standing Patchyard/provider credentials on either worker.

### Session 1 - toolchain, scaffold, service identities, CI

- Entry: Jacob's "go"; repo access live (done 2026-07-16). **The GitHub App dependency opens now, not at session 10**: Jacob starts `patchyard` App creation + installation (org admin; private key to 1Password, `env.tpl` entry); token minting gets a smoke test as soon as the key exists.
- Install rustup/cargo for `conductor`; pin `rust-toolchain.toml`; commit `Cargo.lock`.
- Cargo workspace: `factory-core` (types, the parse-don't-validate intake constructor, shared constants), `factory-verify`, `factoryctl`, `factory-web` - empty shells beyond core.
- **Provision all control-plane service identities now**: `factory-web` user and `factory` group; `/var/lib/patchyard/` skeleton with asserted ownership and modes recorded as tests, before anything depends on them implicitly. The worker identity is Ansible-owned from session 0 and its contract is asserted here rather than duplicated locally.
- Verify the in-repo constitution (`AGENTS.md`, canonical here since dee992d) is wired into CI as a checked artifact.
- Exit: `cargo test` green on the skeleton; **CI green on a PR on GitHub-hosted runners with the cache action warm (A76/A88)** - timings and minutes cost recorded at a fixed commit; identity/ownership assertions pass; README gains build/run instructions.

### Session 2 - PostgreSQL state layer behind a domain boundary

- Install and initialize the supported PostgreSQL package on the control-plane VM (A68); disable TCP for application access; place the Unix socket in a restricted directory; configure peer mappings for the service identities created in session 1. The sole TCP surface (A84/A94): the `grafana_ro` listener on the private/VPC interface, firewalled to the monitoring droplet, TLS on with cert expiry on the alert path. No database passwords or application secrets.
- Provision owner/migrator, supervisor, dashboard, and `grafana_ro` roles declaratively - `grafana_ro` (A84/A94) gets column-level grants on views pinned to metadata and aggregates, never a table grant. The dashboard grant contract is executable acceptance: read factory state, insert only request-intake columns, and fail on state updates, deletes, truncation, event mutation, or DDL. The worker receives no role and no socket access.
- Use PostgreSQL SQLx only behind a domain repository boundary - no SQLite implementation and no engine-neutral SQL claim. Schema + migrations (queued rows carry a W3C trace-id column, A90) for `requests`, `runs`, `events`, `artifacts`, `pr_state`, `leases` (SPEC § State layer); `runs` includes **all eight provenance hash columns** from day one. Commit SQLx offline metadata or give CI a disposable PostgreSQL service so checked queries are reproducible. Add artifact-directory lifecycle (0700, retention sweep).
- **ERD generator (A81)**: bespoke introspection (`pg_catalog`/`information_schema`) emitting the committed Mermaid `erDiagram`; CI regenerates from an ephemeral migrated Postgres and byte-compares. The same query module later backs `/schema` (session 11) - one implementation, two projections.
- `factoryctl` v0: `request new` (through the single core parse function - A53), `status`, `claim` (lease TTL), `close`, `retention-sweep`; `reconcile` stubbed, lands in session 10.
- Exit: the `grafana_ro` canary test passes (a seeded fixture row's canary strings are unreachable through every read view - A94); automated crash tests at **named state boundaries** (kill before/after each transition; drop connections and restart the test server at declared points; idempotent retry converges); lease claim/expiry, double-claim rejection, transaction rollback, request/run/event/lease invariants, and the complete role/grant matrix asserted as tests.

### Session 3 - isolation spike: Firecracker vs rootless Podman

- Probe `/dev/kvm` on the new worker droplet - the orchestration VM's verified KVM result does not transfer - then run the **half-session time-boxed evaluation (A91)**: adopt Firecracker if KVM is present and it is not much operationally harder than hardened rootless Podman - ties go to the kernel boundary; the Podman fallback runs under the same mount/egress contract (A44) and is the accepted outcome only on material operational cost or absent KVM.
- **Probe manifest predeclared before running**: read-only request mount, read-write worktree mount, host-write attempts, egress beyond the boot's single allowlisted provider endpoint (A61; IPv4, IPv6, DNS), credential absence, startup and teardown overhead - with must-pass selection criteria written down first.
- Exit: **a decision recorded in this repo** - runtime, rationale, raw probe results against the predeclared criteria, and the credential plumbing shape across the physical `conductor`/`factory-worker` split. Implementation may be partial; the probes may not be.

### Session 4 - worker runtime build-out

- **Management transport (A101)**: before credential/source transfer, replace session 0's orchestration-only host management with a factory **control-plane** management identity reaching the worker over the private VPC; the orchestration host's SSH authorization is repurposed to bootstrap/break-glass, never a runtime path. Covers *both* hosts per the A101 sweep (the `common` role, both droplet firewalls, cloud-init gecos, the `orchestration_public_cidr` variable). The independence tripwire and a live 'orchestration unreachable, control plane still manages the worker' check are its exit evidence.
- The chosen runtime becomes the production worker shape: image construction, mount wiring, egress enforcement (one allowlisted provider per boot, A61), short-lived spend-capped model credential in memory/tmpfs (never `conductor`'s env), exact-SHA source/input transfer, worker I/O contract (a patch + a rationale and bounded verification evidence out, nothing else), guaranteed teardown.
- **Environment parity (A85)**: the image pins prod Fieldbook's PHP version/extensions/web-server config from desired state; a local MySQL 8.4 seeds per run from the dated redacted snapshot artifact (built on the control plane from the manager-sandbox redaction lineage, shipped with the bundle, fail-static on refresh failure); the worker boots the app and exercises a page against seeded data.
- Exit: a toy request yields a patch through the real inter-host boundary **from inside the parity environment** (asserted: PHP version matches the pin, the app boots, a seeded query returns rows, snapshot version lands in provenance); egress and mount contracts hold under the probe scripts from session 3; teardown leaves no residue (asserted).

### Session 5 - worker adversarial qualification

- **Enumerated hostile-test manifest, all automated**: environment variables, SSH/`op` file paths, sockets, cloud metadata endpoints, private IPv4/IPv6 ranges, DNS exfiltration, filesystem boundary writes, and alternate output channels beyond the patch+rationale contract.
- Exit: every manifest entry passes (canary secret unread, private network unreachable, no out-of-contract output, no credential or request residue after teardown); the manifest and results are committed - they become regression fixtures for acceptance.

### Session 6 - factory-verify crate (pure logic)

- `caps`, `deny-paths`, `postconditions` (sort skill, against canned DOM fixtures at this stage), `ledger-append` - which **also validates provenance-field completeness** on every run record; mutation self-tests enumerating every mutation each subcommand must reject (A10).
- Exit: cargo test proves each subcommand fails its enumerated mutations; **two independent clean builds produce identical binary hashes**; checksum-verified install and rollback exercised, not just documented.

### Session 7 - preview slice + verifier runtime

- **The minimal preview mechanism lands here, before anything claims integrated verification** (review finding 1): preview lease (owner, request-id, expected SHA, TTL, guaranteed cleanup), in-preview `git rev-parse HEAD` verification, headless bearer-header extension, baseline-DOM capture at the base SHA.
- **Verifier runtime harness**: agent worker terminated before verify (asserted, not assumed); verification runs on the worker droplet as `factory-worker` in a clean environment; before/after tree-hash equality; **targeted PHPUnit selection and execution as `factory-worker`**.
- Exit: the sort postcondition runs against a real preview baseline on a fixture branch; PHPUnit runs under the verifier identity; lease cleanup proven on both success and failure paths.

### Session 8 - /factory skill part 1: triage + the plan bin

- Constitution already canonical here as `AGENTS.md` - its hard rules ride the triage prompt from the first run. `rubric.md` migrated into this repo; no-shell triage subagent (Read/Grep/Glob frontmatter allowlist - A37); lane classification against the rubric.
- **All plan-bin transitions, not just the exits** (A46/A48): approved B re-enters implement with the spec as Guide and a human-approved budget replacing lane-A caps; answered D re-triages; executed C closes; rejected-at-plan closes with its reason.
- Exit: a replay manifest states the expected lane per fixture and every fixture classifies correctly; **each plan-bin re-entry and close transition is exercised** with its ledger row.

### Session 9 - /factory skill part 2: pipeline orchestration

- **Supervisor daemon (A65/A67)**: `factory-supervisor` - the claim loop (`LISTEN` under systemd) and the full pipeline orchestration as one Rust program; agentic stages exec as bounded headless subprocesses; the skill playbook lands as prompt/policy files the daemon consumes; `factoryctl run <id>` drives the same code path in foreground; `factoryctl pause`/`resume` gate claiming; per-submitter and global daily run limits enforced at claim time; **seat routing (A74)**: agentic invocations resolve via the versioned routing config (static rules in phase 1); resolved triple + config version into provenance. **Adversarial review hook (A73/A77)**: the exec path supports a second family (codex) as a configured stage review; the adjudication contract runs as code - author disposition (concede/refute/escalate) recorded per finding, dispute-arbitration path to the third family stubbed; one fixture exercises review → disposition → escalation end-to-end; **reviewer isolation (A87)** enforced and tested - reviewer execs in a fresh worktree at the reviewed SHA, a probe from inside the review environment proves sibling reviews and shared scratch are unreachable, and the multi-reviewer submission barrier holds in a two-reviewer fixture. **control-row execution (A70)**: pause/resume/kill/full-stop commands consumed from the same channel, worker teardown + lease release + terminal `killed` event.

- **Observability endpoint (A80)**: the daemon serves Prometheus `/metrics` via the Rust `metrics` crate (counters: runs by stage/outcome, LLM tokens and cost by model, stage latency histograms); `tracing` instrumentation throughout with the OTLP exporter wired and **dormant by default** (A82/A90 - endpoint config ships empty) - fail-open by test: a run completes with the collector endpoint unreachable and identically with it unset.
- Supervisor as deterministic steps only, with a test proving raw request content flows exclusively into the isolated triage/worker path - never into the supervisor's own instructions (SPEC trust architecture).
- **Transcript capture (A83)**: each agentic invocation's full harness transcript persisted to the artifact store and linked from its event row - asserted in the ALPHABETIZE dry run.
- Exact-SHA bundle transfer, remote worker invocation, bounded result intake, verify integration, one repair loop (A9) with exhaustion escalating, **provenance fields populated on every run** (model id, CLI version, constitution/rubric/skill/prompt-template/verifier-binary hashes, base tree hash).
- Exit: ALPHABETIZE dry run with expected lane, target files, and patch semantics asserted; worker-terminated-before-verify ordering observed; provenance complete (ledger-append accepts); repair exhaustion escalates; stops before publish - and is labeled a dry run, not end-to-end.

### Session 10 - publisher, bot identity, reconcile

- Bot identity live: GitHub App token minting (smoke-tested since session 1); the fallback, if needed, is a **dedicated machine-user fine-grained PAT, never Jacob's** (A45) - and "PR author is the machine identity" is part of the exit either way.
- **Full worktree lifecycle per SPEC**: credentialed bare clone and publisher worktrees stay under `/var/lib/patchyard/worktrees/` on the control-plane VM (A68); fetch-before-branch, export the exact base SHA without a Git remote, accept only the bounded worker result, refuse an existing branch unless it belongs to the same request, and clean both hosts on failure, close, and merge.
- Publisher state machine: apply verified patch at recorded base SHA, tree-hash confirm, push, draft PR; crash points tested (crash before/after branch push resumes to one branch + one PR, no orphans); PR-cap check under the publisher lease, fail-closed on stale GitHub state.
- `factoryctl reconcile`: bounded call (argument-vector exec, timeout, output cap); **deployed-SHA comparison against the status dashboard's existing deployed-version source**; **admin-bypassed merges recorded as not-a-passing-run**.
- Exit: draft PR authored by the bot on a scratch branch; per-transition and per-crash-point tests pass; cap race (two simultaneous publishes → one PR); stale-state fail-closed observed.

### Session 11 - dashboard part 1: routes, auth, service

- Axum + Askama SSR (no WASM, no npm - A53); **`factory-dashboard.service`** (the SPEC's unit name) running as the **`factory-web` user** with the SPEC's hardening; Unix socket; Caddy vhost; **factory-native auth (A68)** - own users table, argon2, session cookies, accounts provisioned at bootstrap; `factory_submit`/`factory_admin` roles live in factory Postgres, not the orchestration members store.
- **Scribe-only boundary enforced and tested** (A53): the submit handler calls the same `factory-core` constructor as `factoryctl`; application tests prove the dashboard has no transition, cap, triage, or verification path, while PostgreSQL integration tests prove its role cannot update/delete state or mutate events even through direct SQL. Form constraints are template-injected from core constants. Refresh action triggers the bounded reconcile. **Decision-log view (A75)**: `/decisions` via pulldown-cmark from the checkout, per-ruling anchors. **Bench + schema views (A72)**: `/bench` from the checkout's `bench.json`; `/schema` from live introspection with row counts; both in the role matrix. **Model projection (A71)**: `GET /model` serving the repo-generated SVG + canonical links from the local checkout; live run-dot overlay wired to the SSE stream. **Kill-switch controls (A70)**: admin-only buttons writing control rows (pause/resume, per-run kill, full stop); role-matrix covers them; integration test proves a kill lands as a terminal event.
- **Visual style (A64)**: templates ship on the vendored `assets/dashboard/terminal.css` + `patchyard-theme.css` (matrix boxy terminal, Patchyard green accent); assets served by the dashboard binary, none fetched externally.
- **Live visibility (A63)**: SSR event-ledger timeline on the detail page; `GET /request/<id>/events` SSE endpoint driven by PostgreSQL `LISTEN/NOTIFY` (no polling at any layer); inline vanilla `EventSource` fragment (presentation-only, within A53); conditional `Refresh`-header fallback while non-terminal; Caddy configured unbuffered/long-lived on the events route.
- **Bench roster page: ruled into phase 1 (A72, superseding this session's earlier deferral)** - `/bench` renders `docs/bench.json` from the checkout. (`docs/bench.html`, its interim browser renderer, was retired early in the 2026-07-21 chiseling pass; `bench.md` stays the repo-readable projection until `/bench` ships.)
- **Codebase view (A102)**: `/codebase` renders `docs/codebase-metrics.json`; `tools/check-codebase.sh` (pinned `tokei`) generates it and joins CI with a byte-identical check, and the view groups lines by role (product/infra/tooling/governance).
- Exit: a **route-by-role matrix** (anonymous/submitter/admin × every route, exact 302/200/403 outcomes - the SSE route included) green against seeded state; an integration test proves a seeded event insert reaches a connected `EventSource` client as a frame within a second, and the non-terminal fallback header renders; a submitted form yields a queued row that the (session-9) listener claims end-to-end in the integration environment - submit → run with no console step - and `factoryctl pause` verifiably stops claiming; systemd/Caddy/socket hardening asserted. Full-run stage-transition display is explicitly *not* claimed here - it lands in session 15.

### Session 12 - dashboard part 2: upload hardening + threat model

- The SPEC's full upload contract: canonical server-generated IDs and filenames, create-new + atomic rename, magic-byte sniffing, decoder pixel limits, re-encode to clean PNG/JPEG, archive/executable/SVG rejection, per-request and per-user quotas, rate limits, disk-full behavior, strict CSP + `Content-Disposition: attachment`, symlink/hardlink defense.
- The budgeted **threat-model/fuzz session** runs here against the upload and path surfaces, with seed corpus and time budget declared up front.
- Exit: every named adversarial fixture rejected (traversal names, double extensions, MIME spoofing, decompression bombs, malformed images, duplicate/concurrent submissions); fuzz campaign completed within its declared budget with zero unresolved findings.

### Session 13 - evidence-capture isolation (A89)

- Evidence capture becomes a per-run, no-authority isolation job (disposition A-1): fresh container/microVM holding no PostgreSQL socket, GitHub App key, model credential, vault capability, repo credential, or artifact-tree mount; the supervisor copies the bounded outputs (screenshot, extracted DOM, hashes, execution manifest) into the artifact store only after the job has ended.
- Egress profile is the preview, enforced at the network layer: the leased preview host plus required DNS only; cloud metadata and the private fleet denied; redirect targets re-evaluated against the allowlist. It never shares the implement worker's model-provider boot profile.
- One-use, short-lived preview bearer delivered in tmpfs and destroyed at teardown; helper contract fixed (allowed URL, bounded selectors/actions, timeouts, maximum output sizes, expected SHA; no caller-supplied JavaScript outside reviewed tests).
- Exit: adversarial fixtures each land in their named fail-closed state - redirect chains, DNS rebinding, subresource exfiltration, popups, downloads, oversized pages, bearer-disclosure probes, browser crashes; a probe from inside the evidence environment proves no credential, socket, or artifact path is reachable; teardown leaves nothing behind.
- **Isolation-spawn design (A104)**: session 13 resolves reviewer isolation (A87) and evidence-browser isolation (A89) with ONE spawn mechanism under the hardened `factory-supervisor` unit (which cannot create unprivileged user namespaces) - a scoped privileged helper, `systemd-run` transient scopes, or the worker's Firecracker. Exit proves the hardened daemon completes a review-bearing run (closing the session-10 decision-3 gap) as well as an isolated evidence capture.

### Session 14 - evidence lifecycle

- The full draft-PR evidence lifecycle on session 7's preview slice: GitHub CI wait states, evidence artifacts (screenshots + extracted DOM order) stored with hashes, PR-body links via the authenticated dashboard evidence route, ready-for-review flip with the full contract (A26 quiz, explain-diff, drafted reply).
- Failure paths are first-class: CI/preview timeouts fail closed; lease cleanup on success and failure; navigation restricted to the leased host; bearer header redacted from logs, verified by a log-secret scan.
- Exit: a full ALPHABETIZE run produces an evidence-linked ready-for-review draft PR **and** each failure path lands in its named fail-closed state.

### Session 15 - improvement proposer v0 (A86)

- **Substrate first (A93)**: `factoryctl lessons-report` lands before the seat - deterministic, no model in the path, emitting typed outcome facts + bounded quoted spans from the ledger; runnable standalone as the manual learning loop's tool.
- The scheduled seat the supervisor execs on the control-plane VM (A56/A84) consumes **only the lessons-report's typed facts** - raw transcripts never enter its prompt (framed there as untrusted data); its policy PRs route through the same cross-family adversarial review as code PRs (A-10)
- **Evidence threshold**: below n≥10 relevant runs, `docs/ideas.md` appends only (authority-free by that file's rule 1); at threshold, a PR citing the run IDs and rates that motivated it. A proposer PR without ledger evidence is as unacceptable as a lane-A PR without a root cause.
- **Authority surface**: `policy/` + `docs/ideas.md` only; hard cap one open proposer PR; bot identity authors (A62); human merge only (A1); R19 airtight including the proposer's own prompt.
- Exit: lessons-report runs standalone and its output validates against its schema; a test proves the proposer prompt contains typed facts and bounded quotes only - no raw transcript text; below-threshold seeded ledger → ideas.md append, no PR; at-threshold ledger → exactly one evidence-cited PR against `policy/`; a second attempt while it stands open is refused; a write outside the authority surface fails in test.

### Session 16 - cutover

- Rulings queue already relocated into this repo (`rulings-queue/`, 2026-07-20); this session migrates the remaining orchestration-side remnants (processed-rulings pointer dir, any stray ledger artifacts) and verifies before/after counts.
- Runbook v0: operate, converge, replace, back up, restore, roll back, kill. Worker replacement begins from OpenTofu + Ansible and restores no worker data. The control-plane backup is a `pg_dump` plus artifact manifest; restore starts from declarative PostgreSQL/role provisioning, reapplies migrations, restores database + artifacts, and verifies row counts and hashes. Restore and rollback are actually drilled, not described.
- Exit: the installed topology is live; a request filed via the dashboard reaches the same spool the skill consumes; the orchestration repo carries pointers only; post-cutover smoke passes.

### Session 17 - final acceptance against the installed topology

- **Acceptance runs are qualification-class (A107)**: the manifest declares the qualification budget for the batch up front. The production per-submitter and global daily caps are not raised to accommodate it, and the batch is excluded from cost-per-surviving-fix and adoption metrics.
- **Frozen, versioned case manifest first**: the seven behavioral SPEC § Acceptance cases (smoke, hidden positives, near-miss negatives, injection, concurrency/crash, gate self-tests, dashboard incl. the full-run stage-transition display) × 3 repetitions, each with expected lane, end state, and publication count; fixture hashes recorded. The infrastructure case runs once afterward as a clean-room worker replacement.
- Run at pass^k, k=3, **against the cut-over topology from session 16**
  - the accepted artifact is the installed system, not a pre-cutover approximation. Discovered failures: fix, then rerun the affected criteria from a clean base; zero unresolved failures.
- Exit: all eight criteria pass on the installed topology, including one clean-room worker replacement with no manual edits or copied worker state; results recorded in the ledger and `research/`.

## Jacob-side dependencies (surfaced early)

1. The "go" itself - gates session 0.
2. **Done early, 2026-07-22**: `patchyard` App (ID 0000000) created and installed on fieldbook + factory; token minting smoke-tested from the orchestration host with per-mint narrowing (A-3) verified. The key was rotated 2026-07-22 (old flattened key superseded; new key mint-verified from the vault copy) - the first executed entry of the A-14 rotation runbook. Original item: GitHub App creation + installation on the fieldbook repo - **starts at session 1** (needs org admin - the PAT lacks it); only the smoke test blocks on it early, the publisher (session 10) blocks on it late. The PAT fallback is a dedicated machine user, to be created if the App path stalls.
3. Optional: factory repo description/topics via the GitHub UI (text already provided), or grant the PAT Administration permission.
4. The A96 state backend provisioned before session 0: S3 bucket `example-tofu-state` (versioned, SSE, public-blocked), its scoped IAM user's keys in 1Password with `env.tpl` refs, the client-side state-encryption key in 1Password, and the Route 53 policy widened to the record lifecycle on the example.com zone.

## Known risks

- **PostgreSQL is a new local daemon** - the orchestration VM does not currently have PostgreSQL installed. Session 2 must make socket-only exposure, peer-role mappings, upgrades, health checks, backup, and restore testable operating contracts; a running server without those exits does not count as state layer completion.
- **Firecracker on the new DO droplet** - KVM availability must be re-probed; jailer + networking under the service-user split is the real test; the Podman fallback is pre-approved (A44), so the spike cannot dead-end.
- **Remote-state bootstrap** - the Spaces bucket/key live outside the state they protect. Session 0 must verify locking and recovery before creating the durable worker resource; local state is not an accepted fallback.
- **Inter-host result contract** - a remote boundary is useful only if source input and patch/evidence output stay bounded and authenticated. Sessions 4, 5, 7, and 9 test transport tampering, replay, cleanup, and fail-closed loss.
- **GitHub App friction** - now opened at session 1 precisely so permission iteration burns calendar time, not session time.
- **Preview-fleet coupling** - the evidence lifecycle leases shared mutable previews; sessions 7 and 13 must fail closed on lease conflicts, never queue silently.
- **Dashboard security floor**: `docs/dashboard-security.md` binds sessions 11-12 - contextual escaping + event-filtered markdown + strict nonce-CSP + A-11 auth (session 11), the validate/limit/time/re-encode upload pipeline + fuzz (session 12).
- **Agent-content trust floor**: `docs/agent-content-trust.md` binds build sessions - F1 TaskSpec (session 8), F3/F5 automaton + non-propagation (session 9), F4 independent re-derivation (session 7 + A-9), proposer form (session 14); mechanical rules move into the verifier/policy checks.
- **Rust practice floor**: `docs/rust-practices.md` binds build sessions - session-tagged rules distilled from the council research; mechanical ones join `check-application.sh` as they activate.
- **Operating contract (A97-A100)**: continuous build with hard checkpoints at sessions 3/5/10/16; reviewer on every PR at open; Jacob batch-merges; paired email + SMS only for checkpoints, stalled escalations, and spend alerts (A100 as amended); $300/month spend visibility line; Engineer Two informed, not gating.
- **No buffer session** - the 18-session baseline is honest rather than padded; if a session overruns, the overrun is reported in that build PR rather than absorbed silently (the ground rules forbid compressing the security and failure testing to stay on schedule).
