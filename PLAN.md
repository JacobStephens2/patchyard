# factory - phase 1 build plan

*(Companion to `SPEC.md`. The spec says what must exist and why; this
plan says in what order, cut into sessions, each with a verifiable exit.
Build remains gated on Jacob's explicit "go" - this document is prep,
not build.)*

*Status: v4, 2026-07-18 - v2 re-planned after the adversarial review
(`reviews/2026-07-16-plan-adversarial-review.md`; dispositions in
`reviews/2026-07-16-plan-review-disposition.md`; all findings conceded).
v1's ~10+1 sessions re-baselined to ~15: same components, honest cuts -
isolation qualification, preview-integrated verification, dashboard
hardening, and post-cutover acceptance each get their own exit instead
of hiding inside another session's. Builder: the orchestration agent.
Cross-family reviewer: GPT 5.6-Sol xhigh in Codex on each build PR (A41). Merge
gate: engineering + owner (A33). v3 applies A56: phase 1 starts on local,
socket-only PostgreSQL with peer authentication and role-enforced service
boundaries; no SQLite or dual-engine implementation is built. v4 applies
A57: phase 1 adds a dedicated secret-free worker droplet, OpenTofu + Ansible
desired state, and a clean-room replacement exit, for ~16 sessions total.*

The factory's own macro-shape is Plan → Implement → Verify (A47), and
lane B demands a plan before implementation. Phase 1's build is itself a
lane-B job, so this is the factory eating its own process: `SPEC.md` is
the approved spec, this plan is its Guide, and the session exits below
are its human-approved budget.

## Ground rules for every session

- **Exit criteria are review anchors.** A session ends at its verifiable
  exit, which becomes the checklist for that build PR's review. No PR
  bundles two sessions unless both exits are met.
- **Spikes end on decisions, not implementations.** A spike session's
  deliverable is a recorded decision (in `research/` or `docs/`), even if
  its code is thrown away.
- **The factory repo gets infrastructure CI in session 0** (OpenTofu format/
  validate and Ansible lint/syntax) and application CI in session 1 (fmt,
  clippy, test, `cargo audit`, `cargo deny`, `./model/check-model.sh`). This does not
  conflict with R4: Actions is rejected as the *coding runtime for
  fieldbook changes*; the factory repo running its own test suite in CI is
  ordinary hygiene.
- **Nothing touches fieldbook prod.** All live-fire runs target scratch
  branches and the preview fleet until the acceptance matrix passes.
- **Model edits follow `docs/model-boundary.md`'s workflow** (bump
  `modelVersion`, `python3 model/model-id.py --write`,
  `python3 model/render-model.py`, `./model/check-model.sh`) and the
  generated json/schema/identity/mmd/svg/png under `model/` get copied to
  the orchestration VM's `hosted/` in the same change.
- **Nothing is called end-to-end before its dependencies exist.** An
  exit may use fixtures and seeded state when the real mechanism lands
  later, but must say so; the full-pipeline claims live only in the
  final acceptance session, which runs against the cut-over topology.

## Session sequence

Session 0 covers the worker desired-state component; sessions 1-2 cover the
control-plane scaffold and state layer; 3-5 cover worker isolation; 6-7 the
verifier plus remote-runtime integration; 8-9 the skill; 10 the publisher;
11-12 the dashboard; 13 the evidence lifecycle; 14 cutover; 15 final
acceptance. There is no padded buffer - an overrun surfaces as an overrun
instead of compressing the security and failure testing.

### Session 0 - desired-state foundation and worker droplet

- Entry: Jacob's "go". Pin OpenTofu and the Ansible runtime/collections on
  the orchestration controller; add `infra/opentofu/` and `infra/ansible/`
  with one documented plan, apply, check, replace, and rollback path.
- Configure DigitalOcean Spaces remote state with `use_lockfile`; backend and
  provider credentials come only from the controller environment. OpenTofu
  owns the worker droplet, cloud firewall, SSH public-key attachment,
  attachment to existing Patchyard tags, and inventory outputs. The worker receives
  no DigitalOcean credential.
- Ansible provisions the base OS, `factory-worker` user, packages, host
  firewall, management access restricted to orchestration, tmpfs/transient
  run paths, logging, and cleanup. No application/provider secret is copied.
- Exit: a human-reviewed plan is applied from orchestration; inventory feeds
  Ansible without hand transcription; the second converge reports no changes;
  a disposable clean-room replacement reaches the same state from Git; and
  secret scans find no standing Patchyard/provider credentials on either worker.

### Session 1 - toolchain, scaffold, service identities, CI

- Entry: Jacob's "go"; repo access live (done 2026-07-16). **The GitHub
  App dependency opens now, not at session 10**: Jacob starts
  `patchyard` App creation + installation (org admin; private key to
  1Password, `env.tpl` entry); token minting gets a smoke test as soon
  as the key exists.
- Install rustup/cargo for `conductor`; pin `rust-toolchain.toml`;
  commit `Cargo.lock`.
- Cargo workspace: `factory-core` (types, the parse-don't-validate
  intake constructor, shared constants), `factory-verify`, `factoryctl`,
  `factory-web` - empty shells beyond core.
- **Provision all control-plane service identities now**: `factory-web` user
  and `factory` group; `/var/lib/patchyard/` skeleton
  with asserted ownership and modes recorded as tests, before anything
  depends on them implicitly. The worker identity is Ansible-owned from
  session 0 and its contract is asserted here rather than duplicated locally.
- Verify the in-repo constitution (`AGENTS.md`, canonical here since
  dee992d) is wired into CI as a checked artifact.
- Exit: `cargo test` green on the skeleton; CI green on a PR; identity/
  ownership assertions pass; README gains build/run instructions.

### Session 2 - PostgreSQL state layer behind a domain boundary

- Install and initialize the supported PostgreSQL package on the orchestration
  VM;
  disable TCP; place the Unix socket in a restricted directory; configure
  peer mappings for the service identities created in session 1. No
  database passwords or application secrets.
- Provision owner/migrator, supervisor, and dashboard roles declaratively.
  The dashboard grant contract is executable acceptance: read factory
  state, insert only request-intake columns, and fail on state updates,
  deletes, truncation, event mutation, or DDL. The worker receives no role
  and no socket access.
- Use PostgreSQL SQLx only behind a domain repository boundary - no SQLite
  implementation and no engine-neutral SQL claim. Schema + migrations for
  `requests`, `runs`, `events`, `artifacts`, `pr_state`, `leases` (SPEC §
  State layer); `runs` includes **all eight provenance hash columns** from
  day one. Commit SQLx offline metadata or give CI a disposable PostgreSQL
  service so checked queries are reproducible. Add artifact-directory
  lifecycle (0700, retention sweep).
- `factoryctl` v0: `request new` (through the single core parse
  function - A53), `status`, `claim` (lease TTL), `close`,
  `retention-sweep`; `reconcile` stubbed, lands in session 10.
- Exit: automated crash tests at **named state boundaries** (kill
  before/after each transition; drop connections and restart the test
  server at declared points; idempotent retry converges); lease
  claim/expiry, double-claim rejection, transaction rollback,
  request/run/event/lease invariants, and the complete role/grant matrix
  asserted as tests.

### Session 3 - isolation spike: Firecracker vs rootless Podman

- Probe `/dev/kvm` on the new worker droplet - the orchestration VM's verified
  KVM result does not transfer - then evaluate Firecracker first;
  fallback candidate rootless Podman under the same mount/egress
  contract (A44).
- **Probe manifest predeclared before running**: read-only request
  mount, read-write worktree mount, host-write attempts, egress beyond
  the boot's single allowlisted provider endpoint (A61; IPv4, IPv6,
  DNS), credential absence, startup and
  teardown overhead - with must-pass selection criteria written down
  first.
- Exit: **a decision recorded in this repo** - runtime, rationale, raw
  probe results against the predeclared criteria, and the credential
  plumbing shape across the physical `conductor`/`factory-worker` split.
  Implementation may be partial; the probes may not be.

### Session 4 - worker runtime build-out

- The chosen runtime becomes the production worker shape: image
  construction, mount wiring, egress enforcement (one allowlisted
  provider per boot, A61), short-lived
  spend-capped model credential in memory/tmpfs (never `conductor`'s env),
  exact-SHA source/input transfer, worker I/O contract (a patch + a rationale
  and bounded verification evidence out, nothing else), guaranteed teardown.
- Exit: a toy request yields a patch through the real inter-host boundary; egress
  and mount contracts hold under the probe scripts from session 3;
  teardown leaves no residue (asserted).

### Session 5 - worker adversarial qualification

- **Enumerated hostile-test manifest, all automated**: environment
  variables, SSH/`op` file paths, sockets, cloud metadata endpoints,
  private IPv4/IPv6 ranges, DNS exfiltration, filesystem boundary
  writes, and alternate output channels beyond the patch+rationale
  contract.
- Exit: every manifest entry passes (canary secret unread, private
  network unreachable, no out-of-contract output, no credential or request
  residue after teardown); the manifest and
  results are committed - they become regression fixtures for
  acceptance.

### Session 6 - factory-verify crate (pure logic)

- `caps`, `deny-paths`, `postconditions` (sort skill, against canned
  DOM fixtures at this stage), `ledger-append` - which **also validates
  provenance-field completeness** on every run record; mutation
  self-tests enumerating every mutation each subcommand must reject
  (A10).
- Exit: cargo test proves each subcommand fails its enumerated
  mutations; **two independent clean builds produce identical binary
  hashes**; checksum-verified install and rollback exercised, not just
  documented.

### Session 7 - preview slice + verifier runtime

- **The minimal preview mechanism lands here, before anything claims
  integrated verification** (review finding 1): preview lease (owner,
  request-id, expected SHA, TTL, guaranteed cleanup), in-preview
  `git rev-parse HEAD` verification, headless bearer-header extension,
  baseline-DOM capture at the base SHA.
- **Verifier runtime harness**: agent worker terminated before verify
  (asserted, not assumed); verification runs on the worker droplet as
  `factory-worker` in a clean environment; before/after tree-hash equality;
  **targeted
  PHPUnit selection and execution as `factory-worker`**.
- Exit: the sort postcondition runs against a real preview baseline on
  a fixture branch; PHPUnit runs under the verifier identity; lease
  cleanup proven on both success and failure paths.

### Session 8 - /factory skill part 1: triage + the plan bin

- Constitution already canonical here as `AGENTS.md` - its hard rules
  ride the triage prompt from the first run. `rubric.md` migrated into
  this repo; no-shell triage subagent (Read/Grep/Glob frontmatter
  allowlist - A37); lane classification against the rubric.
- **All plan-bin transitions, not just the exits** (A46/A48): approved
  B re-enters implement with the spec as Guide and a human-approved
  budget replacing lane-A caps; answered D re-triages; executed C
  closes; rejected-at-plan closes with its reason.
- Exit: a replay manifest states the expected lane per fixture and
  every fixture classifies correctly; **each plan-bin re-entry and
  close transition is exercised** with its ledger row.

### Session 9 - /factory skill part 2: pipeline orchestration

- **Resident supervisor listener (A65)**: a long-running claim loop
  (`LISTEN` on the intake channel under systemd) that picks up
  dashboard-queued requests and drives the same pipeline the console
  path uses; `factoryctl pause`/`resume` gate claiming; per-submitter
  and global daily run limits enforced at claim time.

- Supervisor as deterministic steps only, with a test proving raw
  request content flows exclusively into the isolated triage/worker
  path - never into the supervisor's own instructions (SPEC trust
  architecture).
- Exact-SHA bundle transfer, remote worker invocation, bounded result intake,
  verify integration, one repair loop (A9) with
  exhaustion escalating, **provenance fields populated on every run**
  (model id, CLI version, constitution/rubric/skill/prompt-template/
  verifier-binary hashes, base tree hash).
- Exit: ALPHABETIZE dry run with expected lane, target files, and patch
  semantics asserted; worker-terminated-before-verify ordering observed;
  provenance complete (ledger-append accepts); repair exhaustion
  escalates; stops before publish - and is labeled a dry run, not
  end-to-end.

### Session 10 - publisher, bot identity, reconcile

- Bot identity live: GitHub App token minting (smoke-tested since
  session 1); the fallback, if needed, is a **dedicated machine-user
  fine-grained PAT, never Jacob's** (A45) - and "PR author is the
  machine identity" is part of the exit either way.
- **Full worktree lifecycle per SPEC**: credentialed bare clone and publisher
  worktrees stay under `/var/lib/patchyard/worktrees/` on orchestration;
  fetch-before-branch, export the exact base SHA without a Git remote, accept
  only the bounded worker result, refuse an existing branch unless it belongs
  to the same request, and clean both hosts on failure, close, and merge.
- Publisher state machine: apply verified patch at recorded base SHA,
  tree-hash confirm, push, draft PR; crash points tested (crash before/
  after branch push resumes to one branch + one PR, no orphans); PR-cap
  check under the publisher lease, fail-closed on stale GitHub state.
- `factoryctl reconcile`: bounded call (argument-vector exec, timeout,
  output cap); **deployed-SHA comparison against the status dashboard's
  existing deployed-version source**; **admin-bypassed merges recorded
  as not-a-passing-run**.
- Exit: draft PR authored by the bot on a scratch branch; per-transition
  and per-crash-point tests pass; cap race (two simultaneous publishes →
  one PR); stale-state fail-closed observed.

### Session 11 - dashboard part 1: routes, auth, service

- Axum + Askama SSR (no WASM, no npm - A53);
  **`factory-dashboard.service`** (the SPEC's unit name) running as the
  **`factory-web` user** with the SPEC's hardening; Unix socket; Caddy
  vhost + forward_auth; `factory_submit`/`factory_admin` permissions in
  the members store.
- **Scribe-only boundary enforced and tested** (A53): the submit
  handler calls the same `factory-core` constructor as `factoryctl`;
  application tests prove the dashboard has no transition, cap, triage,
  or verification path, while PostgreSQL integration tests prove its role
  cannot update/delete state or mutate events even through direct SQL.
  Form constraints are template-injected from core constants. Refresh
  action triggers the bounded reconcile.
- **Visual style (A64)**: templates ship on the vendored
  `assets/dashboard/terminal.css` + `patchyard-theme.css` (matrix boxy
  terminal, Patchyard green accent); assets served by the dashboard binary,
  none fetched externally.
- **Live visibility (A63)**: SSR event-ledger timeline on the detail
  page; `GET /request/<id>/events` SSE endpoint driven by PostgreSQL
  `LISTEN/NOTIFY` (no polling at any layer); inline vanilla `EventSource`
  fragment (presentation-only, within A53); conditional `Refresh`-header
  fallback while non-terminal; Caddy configured unbuffered/long-lived on
  the events route.
- **Not built in phase 1: a model-roster page.** The seat roster
  already has a read-only gated projection (`docs/bench.html` +
  `bench.json`, published on report.example.com behind the
  existing sign-in); folding a roster page into this dashboard is a
  phase-2 decision. It is A53-compatible (read-only, no intake write),
  so if Jacob rules it into phase 1 it lands here as one SSR route
  rendering `bench.json` - but it is not in this session's exit.
- Exit: a **route-by-role matrix** (anonymous/submitter/admin × every
  route, exact 302/200/403 outcomes - the SSE route included) green
  against seeded state; an integration test proves a seeded event
  insert reaches a connected `EventSource` client as a frame within a
  second, and the non-terminal fallback header renders;
  a submitted form yields a queued row that the (session-9) listener
  claims end-to-end in the integration environment - submit → run with
  no console step - and `factoryctl pause` verifiably stops claiming;
  systemd/Caddy/socket hardening asserted. Full-run stage-transition
  display is explicitly *not* claimed here - it lands in session 15.

### Session 12 - dashboard part 2: upload hardening + threat model

- The SPEC's full upload contract: canonical server-generated IDs and
  filenames, create-new + atomic rename, magic-byte sniffing, decoder
  pixel limits, re-encode to clean PNG/JPEG, archive/executable/SVG
  rejection, per-request and per-user quotas, rate limits, disk-full
  behavior, strict CSP + `Content-Disposition: attachment`,
  symlink/hardlink defense.
- The budgeted **threat-model/fuzz session** runs here against the
  upload and path surfaces, with seed corpus and time budget declared
  up front.
- Exit: every named adversarial fixture rejected (traversal names,
  double extensions, MIME spoofing, decompression bombs, malformed
  images, duplicate/concurrent submissions); fuzz campaign completed
  within its declared budget with zero unresolved findings.

### Session 13 - evidence lifecycle

- The full draft-PR evidence lifecycle on session 7's preview slice:
  GitHub CI wait states, evidence artifacts (screenshots + extracted
  DOM order) stored with hashes, PR-body links via the authenticated
  dashboard evidence route, ready-for-review flip with the full
  contract (A26 quiz, explain-diff, drafted reply).
- Failure paths are first-class: CI/preview timeouts fail closed; lease
  cleanup on success and failure; navigation restricted to the leased
  host; bearer header redacted from logs, verified by a log-secret
  scan.
- Exit: a full ALPHABETIZE run produces an evidence-linked
  ready-for-review draft PR **and** each failure path lands in its
  named fail-closed state.

### Session 14 - cutover

- Migrate `queue/` + ledger out of the orchestration repo with
  before/after row and artifact counts + hashes; repoint `/api/rulings`
  to the intake spool with **distinct ruling and software-request
  namespaces, tested** - including old-path write rejection.
- Runbook v0: operate, converge, replace, back up, restore, roll back, kill.
  Worker replacement begins from OpenTofu + Ansible and restores no worker
  data. The control-plane backup is a
  `pg_dump` plus artifact manifest; restore starts from declarative
  PostgreSQL/role provisioning, reapplies migrations, restores database +
  artifacts, and verifies row counts and hashes. Restore and rollback are
  actually drilled, not described.
- Exit: the installed topology is live; a request filed via the
  dashboard reaches the same spool the skill consumes; the orchestration
  repo carries pointers only; post-cutover smoke passes.

### Session 15 - final acceptance against the installed topology

- **Frozen, versioned case manifest first**: the seven behavioral SPEC §
  Acceptance cases (smoke, hidden positives, near-miss negatives, injection,
  concurrency/crash, gate self-tests, dashboard incl. the full-run
  stage-transition display) × 3 repetitions, each with expected lane, end
  state, and publication count; fixture hashes recorded. The infrastructure
  case runs once afterward as a clean-room worker replacement.
- Run at pass^k, k=3, **against the cut-over topology from session 14**
  - the accepted artifact is the installed system, not a pre-cutover
  approximation. Discovered failures: fix, then rerun the affected
  criteria from a clean base; zero unresolved failures.
- Exit: all eight criteria pass on the installed topology, including one
  clean-room worker replacement with no manual edits or copied worker state;
  results recorded in the ledger and `research/`.

## Jacob-side dependencies (surfaced early)

1. The "go" itself - gates session 0.
2. GitHub App creation + installation on the fieldbook repo - **starts at
   session 1** (needs org admin - the PAT lacks it); only the smoke
   test blocks on it early, the publisher (session 10) blocks on it
   late. The PAT fallback is a dedicated machine user, to be created if
   the App path stalls.
3. Optional: factory repo description/topics via the GitHub UI (text
   already provided), or grant the PAT Administration permission.
4. A DigitalOcean Spaces access key for locked remote OpenTofu state if the
   existing state-backend bootstrap task is not complete when session 0 starts.

## Known risks

- **PostgreSQL is a new local daemon** - the orchestration VM does not
  currently have PostgreSQL installed. Session 2 must make socket-only
  exposure, peer-role
  mappings, upgrades, health checks, backup, and restore testable operating
  contracts; a running server without those exits does not count as state
  layer completion.
- **Firecracker on the new DO droplet** - KVM availability must be re-probed;
  jailer + networking under the service-user split is the real test; the Podman
  fallback is pre-approved (A44), so the spike cannot dead-end.
- **Remote-state bootstrap** - the Spaces bucket/key live outside the state
  they protect. Session 0 must verify locking and recovery before creating the
  durable worker resource; local state is not an accepted fallback.
- **Inter-host result contract** - a remote boundary is useful only if source
  input and patch/evidence output stay bounded and authenticated. Sessions 4,
  5, 7, and 9 test transport tampering, replay, cleanup, and fail-closed loss.
- **GitHub App friction** - now opened at session 1 precisely so
  permission iteration burns calendar time, not session time.
- **Preview-fleet coupling** - the evidence lifecycle leases shared
  mutable previews; sessions 7 and 13 must fail closed on lease
  conflicts, never queue silently.
- **No buffer session** - the 16-session baseline is honest rather than
  padded; if a session overruns, the overrun is reported in that build
  PR rather than absorbed silently (the ground rules forbid compressing
  the security and failure testing to stay on schedule).
