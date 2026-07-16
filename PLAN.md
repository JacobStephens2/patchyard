# factory - phase 1 build plan

*(Companion to `SPEC.md`. The spec says what must exist and why; this
plan says in what order, cut into sessions, each with a verifiable exit.
Build remains gated on Jacob's explicit "go" - this document is prep,
not build.)*

*Status: v1, 2026-07-16. Builder: the orchestration agent. Cross-family
reviewer: GPT 5.6-Sol xhigh on each build PR (A41). Merge gate:
engineering + owner (A33).*

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
  deliverable is a recorded decision (in `reviews/` or `docs/`), even if
  its code is thrown away.
- **The factory repo gets CI in session 1** (fmt, clippy, test,
  `cargo audit`, `cargo deny`, byte-identical model regeneration per
  A50). This does not conflict with R4: Actions is rejected as the
  *coding runtime for fieldbook changes*; the factory repo running its own
  test suite in CI is ordinary hygiene.
- **Nothing touches fieldbook prod.** All live-fire runs target scratch
  branches and the preview fleet until the acceptance matrix passes.
- **Model edits regenerate views** (`render-model.py`; copy json + mmd
  to the orchestration VM's `hosted/`) in the same commit.

## Session sequence

Component estimates from `SPEC.md` § Component estimates map to sessions
as noted; ~10 sessions plus session 11 as buffer/cutover, inside the
8-11 estimate.

### Session 1 - toolchain + workspace scaffold *(component 1, first half)*

- Entry: Jacob's "go"; repo access live (done 2026-07-16).
- Install rustup/cargo for `conductor`; pin `rust-toolchain.toml`;
  commit `Cargo.lock`.
- Cargo workspace: `factory-core` (types, the parse-don't-validate
  intake constructor, shared constants), `factory-verify`, `factoryctl`,
  `factory-web` - empty shells beyond core.
- CI per the ground rule above.
- Exit: `cargo test` green on the skeleton; CI green on a PR; README
  gains build/run instructions.
- Non-goals: no schema, no dashboard, no isolation work.

### Session 2 - state layer *(component 1, second half)*

- SQLite schema + migrations for `requests`, `runs`, `events`,
  `artifacts`, `pr_state`, `leases` (SPEC § State layer); WAL;
  `/var/lib/patchyard/` layout, ownership, permissions.
- `factoryctl` v0: `request new` (through the single core parse
  function - A53), `status`, `claim` (lease TTL), `close`,
  `retention-sweep`; `reconcile` stubbed, lands in session 7.
- Exit: `factoryctl request new` inserts a row and `factoryctl status`
  reads it back; lease claim/expiry and double-claim rejection covered
  by cargo tests; crash recovery demonstrated (kill mid-write, reopen,
  ledger consistent).
- Non-goals: no GitHub calls; no dashboard.

### Session 3 - isolation spike: Firecracker vs rootless Podman *(component 2, spike)*

- Evaluate Firecracker first (`/dev/kvm` verified present 2026-07-16):
  boot a microVM with the request mounted read-only, one fresh worktree
  read-write, no reachable network beyond the model endpoint. Fallback
  candidate: rootless Podman under the same mount/egress contract (A44).
- Measure: startup overhead, image build story, egress-restriction
  mechanism, credential plumbing shape under the
  `conductor`/`factory-worker` user split.
- Exit: **a decision recorded in this repo** (runtime, rationale,
  measurements, the credential path) - implementation may be partial.

### Session 4 - worker image + credential plumbing *(component 2, remainder)*

- Build the worker environment per the session-3 decision: worker
  contract (a patch + a rationale out, nothing else), short-lived
  spend-capped model credential (never `conductor`'s env).
- Exit: scripted demo - a hostile fixture inside the boundary cannot
  read a canary secret planted on the host, cannot reach the private
  network, and a toy request still yields a patch.

### Session 5 - factory-verify crate *(component 3)*

- `caps`, `deny-paths`, `postconditions` (sort skill), `ledger-append`
  per SPEC § Verification; mutation self-tests enumerating every
  mutation each subcommand must reject (A10).
- Exit: cargo test proves each subcommand fails its enumerated
  mutations; reproducible build documented; binary checksummed.

### Session 6 - /factory skill + rubric + triage *(component 4)*

- Skill playbook; `rubric.md` migrated into this repo; no-shell triage
  subagent (Read/Grep/Glob frontmatter allowlist - A37); plan-bin exits
  for B/C/D with ledger rows (A46/A48); one repair loop (A9); replay
  fixtures wired.
- Exit: dry run on the ALPHABETIZE fixture through triage → worker →
  verify, stopping before publish; B/C/D fixtures land in the plan bin
  with ledger rows.

### Session 7 - publisher + factory bot identity *(components 4/6)*

- **Jacob dependency**: create + install the `patchyard` GitHub App
  (needs org admin - the PAT lacks it); private key into 1Password;
  `env.tpl` entry. PAT fallback (A45) keeps the session unblocked if
  App friction bites.
- Publisher: apply the verified patch at the recorded base SHA in a
  fresh worktree under `/var/lib/patchyard/worktrees/`, confirm tree
  hash, push, open a **draft PR** as the bot; `factoryctl reconcile`
  lands (bounded call, fail-closed on stale GitHub state); PR-cap check
  under the publisher lease.
- Exit: a draft PR authored by the bot on a scratch branch; cap race
  test passes (two simultaneous publishes → one PR).

### Session 8 - dashboard v0 *(component 5)*

- Axum + Askama SSR (no WASM, no npm - A53); `factory-web` systemd unit
  with the SPEC's hardening; Unix socket; Caddy vhost + forward_auth;
  `factory_submit`/`factory_admin` permissions in the members store.
- Intake form constraints template-injected from `factory-core`
  constants (A53); upload hardening + adversarial fixtures per SPEC.
- Exit: SPEC acceptance item 7 in full (submit → receipt; admin sees
  stage transitions through a run; anonymous 302; upload fixtures
  rejected; evidence route authenticated).

### Session 9 - evidence lifecycle *(component 6, first half)*

- Draft-PR evidence lifecycle per SPEC: preview lease, in-preview SHA
  verification, headless bearer-header extension, evidence into the
  artifact store, PR-body links via the dashboard evidence route,
  ready-for-review flip with the full contract (A26 quiz, explain-diff,
  drafted reply).
- Exit: a full ALPHABETIZE run produces an evidence-linked
  ready-for-review draft PR.

### Session 10 - acceptance matrix + threat-model session *(component 6, second half)*

- Run SPEC § Acceptance criteria 1-7 at pass^k, k=3 (smoke, hidden
  positives, near-miss negatives, injection, concurrency/crash, gate
  self-tests, dashboard); the budgeted threat-model/fuzz session on the
  upload + path surfaces; fix and re-run what fails.
- Exit: all seven criteria pass; results recorded in the ledger and
  `reviews/`.

### Session 11 - cutover + buffer

- Migrate `queue/` + ledger out of the orchestration repo; repoint
  `/api/rulings` to the intake spool; migrate the `agents.md`
  constitution into this repo (A36); runbook v0 (operate, back up, roll
  back, kill); sync memory and docs.
- Exit: the orchestration repo carries pointers only; a request filed
  via the dashboard reaches the same spool the skill consumes.

## Jacob-side dependencies (surfaced early)

1. The "go" itself - gates session 1.
2. GitHub App creation + installation on the fieldbook repo - gates
   session 7's preferred path (PAT fallback exists).
3. Optional: factory repo description/topics via the GitHub UI (text
   already provided), or grant the PAT Administration permission.

## Known risks

- **Firecracker on a DO droplet** - `/dev/kvm` is present, but jailer +
  networking under the service-user split is the real test; the Podman
  fallback is pre-approved (A44), so the spike cannot dead-end.
- **GitHub App friction** - installation/permission iteration may push
  publisher work wide; the PAT fallback keeps session 7 shippable.
- **Preview-fleet coupling** - the evidence lifecycle leases shared
  mutable previews; session 9 must fail closed on lease conflicts, never
  queue silently.
