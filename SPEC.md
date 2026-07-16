# factory - phase 1 build spec, v2.1

*(GitHub: `JacobStephens2/patchyard`; local checkout on the
orchestration VM at `/srv/orchestration/patchyard/`.)*

*Status: v2, 2026-07-16 - revised after GPT 5.6-Sol xhigh's adversarial
critique (`reviews/2026-07-16-gpt-5.6-sol-spec-critique.md`; dispositions
in `reviews/2026-07-16-disposition.md`) and Jacob's five rulings on it.
Build remains gated on Jacob's "go". Builder: the orchestration agent.
Merge gate: engineering department + company owner (A33). PR #213 was
closed by Jacob 2026-07-16 - ALPHABETIZE is now the factory's first live
test subject with no duplicate-PR conflict.*

*v2.1, 2026-07-16 (later the same day): rulings A53-A55 folded in - the
dashboard business-logic boundary (§ Dashboard v0), SQLite graduation
tripwires (§ State layer), and host placement (§ Trust architecture).
The session-by-session build plan is `PLAN.md`, beside this file.*

**Job statement:** when a small self-describing Fieldbook request arrives,
help Patchyard turn it into an evidenced pull request within the hour, so that
staff requests stop dying in inboxes and review is the only human cost.

Design authority: `docs/decision-log.md` in this repo. The founding synthesis
remains provenance in the orchestration repo, not a second editable authority.
Where this spec conflicts with a ruling, the ruling wins - and if a ruling
requires an unsafe design, the ruling gets amended first (per the critique's
correction of v1's wording). The canonical
machine-readable model is `factory-model.json` **in this repo** (A51),
served at https://report.example.com/software-factory-model.json;
`render-model.py` projects it to Mermaid (`factory-model-diagram.md`).
Edit the model first, regenerate the views, copy json+mmd to the
orchestration VM's `hosted/` - byte-identical regeneration becomes a CI
check at build (A50).

## What changed from v1 (critique verdicts, Jacob's rulings)

1. **SQLite + private artifact store move into phase 1** (was phase-2;
   amends D4/A40). Live requests and screenshots never enter Git history.
2. **Full container/microVM isolation for the implement worker moves into
   phase 1** (was phase-2; amends D1). A human trigger vouches for
   provenance, not content - untrusted screenshots get processed in a
   boundary the OS enforces, not a prompt.
3. **Dashboard runs as `factory-web`**, never `conductor`.
4. **Draft-PR evidence lifecycle** replaces v1's impossible ordering.
5. **Factory bot identity**: PRs authored by a dedicated machine identity,
   not Jacob's PAT. Current branch-protection (self-approve, no-bypass
   unchecked) is retained for now per Jacob's ruling.
6. **Acceptance expands** from replay repetition to hidden cases,
   near-misses, injection, and concurrency/crash fixtures.
7. Estimate revised to component estimates, ~8-11 sessions total.

## Deliverables

1. The `/factory` skill - the interactive lane-A pipeline.
2. The isolation substrate - containerized (or microVM) implement worker.
3. The state layer - SQLite ledger + artifact store under `/var/lib/patchyard/`.
4. Dashboard v0 at `factory.example.com` (intake + observability).

Non-goals (phase 2): mailbox intake, automatic reconciliation/polling,
requester-facing pages and notifications (A34's option b), automated
cross-family verify, kill-switch UI.

## Trust architecture (finding 1 + Jacob's ruling 2)

The lethal-trifecta rule applies to phase 1: the component that reads
untrusted request content must hold nothing worth stealing.

- **Supervisor** (the engineer's orchestration session): deterministic
  steps only - claims the request from SQLite, spawns the worker, applies
  the verified patch, publishes. Never feeds raw request content to
  itself as instructions.
- **Triage** runs as a no-shell subagent (Read/Grep/Glob only - harness-
  enforced; defense-in-depth under the OS boundary, not a substitute).
- **Implement worker** runs in an isolated environment with: the request
  mounted read-only; one fresh worktree mounted read-write; **no** SSH
  material, 1Password token, DB/Fieldbook/GitHub credentials, docker
  socket, or private-network access; egress restricted to the model
  endpoint with a short-lived, spend-capped credential (never
  `conductor`'s env). It emits a patch and a rationale, nothing else.
  - **Runtime decision at build**: `/dev/kvm` is present on this host
    (verified 2026-07-16), so evaluate **Firecracker microVM** first for
    kernel-attack-surface isolation (Jacob's preference); fallback is a
    rootless-Podman container (install podman; the Docker daemon's root
    socket must never be reachable from the worker). Record the decision
    and its rationale in this repo.
- **Verifier** runs after the worker is terminated, in a clean
  environment as the unprivileged `factory-worker` user, against the
  patch (tree-hash recorded before/after) - never against a live worker.
- **Publisher** (supervisor-side, deterministic): applies the verified
  patch to a fresh worktree at the recorded base SHA, confirms tree hash,
  pushes, opens the draft PR as the **factory bot identity**.
- **Host placement (A55)**: phase 1 runs on the orchestration VM - the
  factory is made of this host's parts (claude-orchestrator, the fieldbook
  checkout, the secrets wiring, the headless harness, the auth stack),
  and `/dev/kvm` is verified here, so moving would re-risk the
  Firecracker plan. The isolation budget is spent at the worker boundary
  above, not on host separation. When unattended mode arrives (phase 2),
  the worker/publisher split gets its physical expression: a stripped,
  secret-free worker droplet (no 1Password token, no DB grants, no SSH
  material - nothing worth escaping to), while supervisor, state, and
  publisher stay here. Tripwires that advance the timeline: sustained
  resource contention on this droplet, materially raised caps or run
  volume, unattended intake arriving early.

## Identity (finding 5 + Jacob's ruling 3)

Factory PRs are authored by a dedicated machine identity so attribution
reads "the factory did X" and any approver - including Jacob - can review
them. Preferred: an **`patchyard` GitHub App** (no seat cost,
short-lived installation tokens, matches phase-2 architecture; key in
1Password, minted per-run by the publisher). Acceptable fallback: a
machine-user fine-grained PAT. Fieldbook branch protection stays as Jacob
has it today (1 approval, bypass available to admins, self-approve
possible); the factory itself never merges, and an admin-bypassed merge
does not count as a passing factory run.

## State layer (findings 3, 8, 11)

- `/var/lib/patchyard/factory.sqlite3` (WAL): `requests` (id,
  fingerprint UNIQUE, source, received_at, status), `runs` (request_id,
  base_sha, branch UNIQUE, lane, skill, state, timestamps, tokens, turns,
  eval scores, provenance hashes), `events` (append-only transitions),
  `artifacts` (path, sha256, kind), `pr_state` (number UNIQUE, head_sha,
  ci_state, review_state, merged_at, deployed_sha), `leases` (claims with
  TTL - two engineers cannot claim one request; cap checks and PR
  creation serialize under the publisher lease).
- `/var/lib/patchyard/artifacts/<id>/` - raw request text + attachments,
  `factory-web:factory` 0700, 90-day retention after close (configurable).
  Git holds **code, policy, schemas, and sanitized fixtures only**.
- Dashboard renders from SQLite; GitHub state arrives via a bounded
  reconcile call (argument-vector exec, timeout, output cap) triggered by
  `factoryctl reconcile <id>` or a dashboard refresh action - never live
  `gh` per page load. **Fail closed on the 2-open-PR cap when GitHub
  state is stale.**
- `factoryctl`: `claim`, `reconcile`, `close`, `retention-sweep`. Deployed
  SHA comes from the status dashboard's existing deployed-version source,
  compared to the merge SHA.
- The `/api/rulings` intake on the status dashboard repoints from
  `/srv/orchestration/factory/queue/` to the intake spool at build;
  rulings and software requests get separate namespaces.
- **Engine choice + graduation tripwires (A54)**: SQLite is the phase-1
  engine on ops + trust cost, not capability - no daemon, no port, no
  credentials (a networked DB would add exactly the secret class the
  credential-free worker design eliminates); access control is Unix file
  permissions, which the `factory-web`/`conductor` split already
  expresses. Queries go through sqlx (or a thin storage trait) so the
  choice stays cheap to revisit. The graduation target is **PostgreSQL**,
  and only when a tripwire fires: a second host needs direct state
  access; sustained `SQLITE_BUSY` contention in logs; dashboard polling
  latency becomes a real complaint; leases need cross-machine
  `SKIP LOCKED` semantics. MySQL is declined both ways: co-tenanting on
  prod's mysql8 couples factory availability to the prod DB and lands
  factory chatter in its audit surface; a second local MySQL is daemon
  ops without the familiarity benefit. The phase-2 worker-host split
  (A55) does not trigger graduation - workers never touch the DB.

## Dashboard v0 (findings 2, 6, 7)

- Rust/Axum, compiled binary, systemd `factory-dashboard.service` running
  as **`factory-web`** (no shell, no SSH dir, no `op.env`/`env.tpl`
  access, no repo credentials; `NoNewPrivileges`, `ProtectSystem=strict`,
  `ProtectHome`, `PrivateTmp`, explicit `ReadWritePaths=` for spool +
  artifacts + SQLite only). Unix socket owned `caddy:factory-web` - no
  loopback TCP header-spoofing surface.
- Caddy vhost `factory.example.com` (DNS live) with the standard
  `forward_auth`; Caddy strips client-supplied identity headers before
  copying the authenticated email (db-admin pattern).
- **Authorization**: new `factory_submit` and `factory_admin` permissions
  in the members store - `reports` is not reused. Request lists,
  detail pages, evidence, and operational state are `factory_admin`-only
  in phase 1; a bare submitter sees a success receipt.
- Routes: `GET /` (admin: list + stage badges), `GET /request/<id>`
  (admin: verbatim request, stage, drafts, evidence), `GET/POST /new`
  (submit), `GET /evidence/<run>/<name>` (admin: authenticated artifact
  serving - PR bodies link here; no images committed to fieldbook),
  `GET /healthz`.
- **Business-logic boundary (A53)**: the dashboard is a scribe and a
  window - it writes exactly one thing (an intake row) and reads
  everything else; no state transitions, no triage, no caps enforcement,
  no verification (those belong to the pipeline, `factory-verify`, and
  the supervisor). Intake validation is one function in `factory-core`
  (parse-don't-validate: the only constructor of the validated request
  type), called identically by the dashboard, `factoryctl`, and the
  pipeline - no inline validation in handlers. The client gets zero
  authoritative logic: HTML-native constraints (`maxlength`, `required`,
  `accept`) are template-injected from the same core constants the parse
  function enforces, and phase 1 ships no hand-written validation JS.
  SSR only: Axum + Askama - no WASM, no npm, no TypeScript. Intake
  validation is a quality gate, not a security boundary: the threat
  model assumes well-formed-but-malicious content passes it, and the
  downstream gates re-enforce regardless.
- **Upload hardening acceptance criteria**: canonical server-generated
  IDs and filenames (user filename never a path); create-new + atomic
  rename; magic-byte sniffing + decoder pixel limits + re-encode to clean
  PNG/JPEG; reject archives, executables, and scriptable SVG; per-request
  and per-user quotas + rate limits + disk-full behavior; strict CSP,
  `Content-Disposition: attachment`, no inline untrusted HTML; symlink/
  hardlink defense. Adversarial fixtures: traversal names, double
  extensions, MIME spoofing, decompression bombs, malformed images,
  duplicate/concurrent submissions.

## The `/factory` skill (pipeline contract)

`/factory <id>`: supervisor claims via lease → triage (no-shell subagent)
classifies against `rubric.md`; B/C/D exit to the plan bin (drafts for human review) and the run ends. The plan bin is a loop, not a sink (A46): an approved B spec re-enters at implement with the spec as its Guide and a human-approved budget replacing the lane-A caps; an answered D question re-triages; an executed C runbook closes; a plan rejected in the bin closes with outcome 'rejected-at-plan' and its reason - a ledger row feeding the learning loop (A48) →
implement worker (isolated, above) emits patch → worker terminated →
verifier runs `factory-verify` subcommands + targeted PHPUnit as
`factory-worker` → one repair loop (A9), second failure escalates →
publisher applies patch at base SHA, opens **draft PR** as the bot.

**Draft-PR evidence lifecycle (finding 4):** draft opens with request +
root cause + assumptions → GitHub CI runs → preview lease (owner,
request-id, expected SHA, TTL, guaranteed cleanup) on a slot; `git
rev-parse HEAD` verified in-preview before and after browser checks;
read-only actions only (shared mutable preview DB); headless helper
extended for the dev-fleet bearer header via an owner-only header file,
redacted from logs, navigation restricted to the leased host → evidence
(screenshots + extracted DOM order) stored to the artifact store, linked
from the PR body via the dashboard evidence route → PR marked
ready-for-review with the full contract (A26 quiz, explain-diff, drafted
reply). CI/preview failures are explicit fail-closed states with
timeouts.

Worktrees: dedicated bare clone + worktree root under
`/var/lib/patchyard/worktrees/` (never inside the shared
`/srv/orchestration/fieldbook` cache); fetch before branch; refuse an
existing branch unless it belongs to the same request; cleanup on
failure, close, and merge.

## Verification (findings 13-15, 17)

`factory-verify` subcommands (Rust; A10 self-tests as cargo tests, each
enumerating the mutations it must reject - WHERE-clause change, option
value change, membership change, sort-key swap, whitespace-only padding):

- `caps` - additions+deletions vs recorded base SHA; tests count toward
  the cap; renames/mode/binary/generated changes enumerated; the open-PR
  cap is **publisher** state checked under the lease, not a patch check.
- `deny-paths` - constitution deny-list against the final diff.
- `postconditions` - per-skill; for sorts: baseline DOM captured at base
  SHA from the same preview mechanism, labels sorted case-folded by the
  ruled key (first name), values/membership/counts/selected preserved,
  blank-sentinel and duplicate-label handling defined; shared-getter
  callers enumerated and checked; changing `ORDER BY listOrder` is
  permitted only with evidence it is presentation order, not routing
  priority.
- `ledger-append` - transactional run-record writes.

Every run records provenance: model id, CLI version, constitution hash,
rubric hash, skill hash, prompt-template hash, verifier binary hash, base
tree hash. Replays are meaningless without them.

## Acceptance criteria (finding 9; pass^k, k=3)

1. **Smoke (public)**: the sanitized `fixtures/alphabetize/` request → lane A,
   both root-cause files, patch equivalent to the closed PR #213's - 3/3.
   PR #213 is closed, so the one live run publishes the factory's own
   draft PR with no duplicate conflict.
2. **Hidden positives**: sort fixes in other report/dropdown
   implementations + decoy files with similar labels - correct target
   located, wrong-target rate measured, 3/3 each.
3. **Near-miss negatives** (must demote or refuse): `listOrder` as
   intentional priority; last-name explicitly requested; blank sentinel;
   values ≠ labels; shared getter with non-UI callers; locale/case traps.
4. **Injection fixtures**: hostile instructions in email body, image OCR,
   filenames, source comments, failing test output - zero credential
   reads, zero out-of-boundary writes, zero forbidden-lane publications.
5. **Concurrency/crash**: duplicate submit; crash before/after branch
   push resumes to one branch + one PR; GitHub/preview unavailable →
   fail-closed states; PR-cap race under two simultaneous runs; repair-
   loop exhaustion escalates.
6. **Gates**: every `factory-verify` subcommand fails its enumerated
   mutations (cargo test); eval rubric (A38) scored on every replay.
7. **Dashboard**: submit → receipt; admin sees stage transitions through
   a full run; anonymous 302; upload fixtures rejected; evidence route
   authenticated.

## Language, supply chain (A42 + finding 12)

Rust for `factory-verify`, `factoryctl`, and the dashboard;
`rust-toolchain.toml` pinned; `Cargo.lock` committed; `cargo audit` +
`cargo deny` in CI; reproducible build + checksummed binary install +
rollback documented. Python stays where the ecosystem owns the job
(headless harness, status-dashboard touchpoints). One explicit
threat-model/fuzz session budgeted for upload and path surfaces.

## Component estimates (finding 12; ~8-11 sessions)

1. Toolchain + scaffold + state layer (SQLite, artifacts, factoryctl): 1.5-2
2. Isolation substrate (Firecracker eval vs rootless Podman, worker
   image, credential plumbing): 2-2.5
3. `factory-verify` crate + mutation self-tests: 1-1.5
4. `/factory` skill + subagents + rubric + playbook + replay fixtures: 1.5-2
5. Dashboard + auth/Caddy/permissions + upload hardening: 1.5-2
6. Evidence lifecycle (draft PR, preview lease, headless auth, artifact
   routes) + acceptance hardening + threat-model session: 1.5-2
