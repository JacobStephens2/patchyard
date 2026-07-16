# factory - phase 1 build spec

*Status: spec for review. Written 2026-07-16 by the orchestration agent as
phase-1 preparation (ruling: approved in scope, "don't build it yet").
Review path per A41: Jacob reads it, GPT 5.6-Sol xhigh critiques it
adversarially, findings fold back in, then Jacob's "go" starts the build.
Builder: the orchestration agent. Cross-family review of the build PR:
GPT 5.6-Sol. Merge gate: engineering department + company owner (A33).*

**Job statement:** when a small self-describing Fieldbook request arrives,
help Patchyard turn it into an evidenced pull request within the hour, so that
staff requests stop dying in inboxes and review is the only human cost.

Design authority: the 73-ruling decision log and synthesized solution in
the orchestration repo (`projects/software-factory/synthesis/`). This spec
only *instantiates* rulings; where it seems to conflict with one, the
ruling wins and the spec has a bug.

## Deliverables

1. **The `/factory` skill** - the interactive lane-A pipeline, run from an
   orchestration-VM session by an engineer.
2. **Dashboard v0** at `factory.example.com` - manual request intake +
   pipeline observability (A32).

Explicit non-goals (phase 2, do not build): mailbox intake, credential-free
worker/publisher split, GitHub App identity, SQLite ledger, kill switch,
cross-family verify automation, requester-facing dashboard pages (A34's
option b activates in phase 2).

## Repo layout (this repo, after build)

```
factory/  (checkout: /srv/orchestration/patchyard)
├── README.md · SPEC.md
├── agents.md              # constitution (A36) - migrates from orchestration at build start
├── factory-model.json     # canonical model - same migration
├── rubric.md              # triage rubric v1 (versioned; edits via PR only)
├── skills/
│   └── ui.sort-dropdown.md
├── queue/                 # requests + rulings (moves from orchestration/factory/queue)
│   └── processed/
├── runs.md                # the ledger
├── verify/                # Rust crate → `factory-verify` binary (A42)
│   ├── Cargo.toml · src/      # subcommands: caps · deny-paths · postconditions · ledger-append
│   │                          # exit nonzero = fail; A10 gate self-tests are cargo tests
│   └── (preview screenshots shell out to /opt/headless/render.py - the
│        Selenium harness stays Python; ecosystem owns that job)
├── subagents/              # A37 role definitions, installed to .claude/agents/
│   ├── factory-triage.md      # tools: Read, Grep, Glob ONLY
│   ├── factory-implement.md   # tools: Read/Grep/Glob/Edit/Write/Bash, worktree-scoped
│   └── factory-verify.md      # tools: Read/Grep/Glob/Bash (execute checks; no Edit/Write)
├── dashboard/              # Rust (Axum) app (A42)
│   ├── Cargo.toml · src/ · templates/ (Askama) · static/
└── systemd/factory-dashboard.service   # runs the compiled binary; no venv
```

## The `/factory` skill

Invocation: `/factory <queue-id>` in an orchestration session, after the
request exists at `queue/<id>/request.md` (entered by hand, by email
forward, or via dashboard v0 - all write the identical format proven by
pilot-001).

Stage contract (hierarchical pipeline, A39; constitution's hard rules ride
every stage prompt as static context, A36; each stage is its own subagent
with restricted tools, A37):

0. **Intake check** - request.md exists, attachments hashed, id unique.
1. **Triage** (`factory-triage`, read-only) - classify A/B/C/D against
   `rubric.md`; lane A requires a named skill match AND naming the exact
   pages/files with evidence; confidence recorded, authorizing nothing.
   B/C/D exit to drafts in `queue/<id>/draft-*.md` and the run ends.
2. **Implement** (`factory-implement`) - fresh worktree from
   `origin/master` at a recorded SHA under `/srv/orchestration/fieldbook`
   worktrees; branch `factory/<id>-<slug>`; playbook rides the prompt
   (Guide, A27); smallest coherent diff; stop-and-demote on anything
   schema-shaped or over-cap.
3. **Verify** (`factory-verify` subagent, no write tools) - run the
   `factory-verify` binary's subcommands in order (caps, deny-paths, then
   php -l on touched files, postconditions), plus preview screenshots of
   the exact pages via the existing headless harness, then targeted
   PHPUnit. One
   repair loop (A9): a narrow defect returns ONCE to implement with the
   log; second failure escalates to the human.
4. **PR** - `gh pr create` with the full contract: request verbatim, lane +
   rubric version, root cause at file:line, named assumptions,
   before/after screenshots, extracted DOM order, CI link at SHA, risk +
   rollback, drafted reply text, 1-2 question reviewer quiz, explain-diff
   section when a shared function is touched (A26). Labels `factory`,
   `fast-lane`. Then STOP - merge belongs to humans.
5. **Ledger** - append `runs.md` row: id, received/triaged/PR timestamps
   (never self-report, A24), lane, skill, files/lines, tokens, turns,
   agent minutes, eval scores, outcome (filled at merge/close).

## rubric.md v1 (content)

The four lanes verbatim from the synthesized solution, the full deny-rule
list, the never-guess rule for lane D, the wrong-target warning, and a
version header. Every misclassification becomes a PR against this file
(A14) - it is the factory's self-improvement surface.

## skills/ui.sort-dropdown.md (content)

Grok's playbook format: intent; examples (ALPHABETIZE); typical files
(`common_functions.php` getters, report pages, `components/
salespeople_select.php`); Guide block (do/don't: never change WHERE
clauses or list membership, never drop listOrder from the DB); per-skill
budget 2 files/50 lines under the global caps; acceptance checks (ORDER BY
or stable sort present; WHERE unchanged); postcondition (rendered option
labels equal their sorted copy and are a permutation of the before-set,
A8); **eval rubric (A38)**: correct deny-rule citations in triage, Guide
adherence, tool-path sanity, no out-of-scope reads - graded 0-2 each on
every replay run.

## Dashboard v0

- Rust: Axum on `127.0.0.1:5001` (Askama templates, tower-http static
  files, multipart uploads with hard size/type limits enforced in types),
  compiled binary run by systemd `factory-dashboard.service` (user
  `conductor`), Caddy vhost `factory.example.com` with the same
  `forward_auth` gate as report/docs. Build items in the status-dashboard
  app: an `auth-check` branch for the new host (reports permission) and a
  `_SAFE_NEXT_HOSTS` entry. DNS A record → 142.93.121.94: DONE (Route 53, Jacob, 2026-07-16). The Caddy vhost itself is build work - the subdomain stays unserved until the build.
- Routes: `GET /` request list with stage badges (intake → triage → lane →
  implementing → verifying → PR open → merged → deployed → closed);
  `GET /request/<id>` detail with the verbatim request, current stage,
  drafts, PR + evidence links; `GET/POST /new` intake form (title,
  requester, description, screenshot uploads - size/type-limited) writing
  `queue/<id>/request.md` + attachments; `GET /healthz`.
- Stage derivation, v0: filesystem truth only - queue dir contents,
  `runs.md`, and `gh pr view` state. No database, no polling daemon; the
  page derives state at request time.
- Identity: trust the `X-Forwarded-Email` header from the auth gate (the
  db-admin vhost pattern - Caddy strips client-supplied copies). CSRF on
  the POST. No outbound email of any kind (guardrail 5).

## Acceptance criteria (the build is done when, pass^k with k=3)

1. **Golden path (A35):** replaying ALPHABETIZE from Fred's raw email +
   screenshots yields lane A, both root-cause files, and a patch
   equivalent to PR #213's - 3/3 runs, without opening a duplicate PR
   (dry-run mode: everything except `gh pr create`, plus one live run).
2. **Demotions:** an over-cap fixture demotes to B with analysis attached;
   a schema fixture routes to C naming the migration path; a vague fixture
   yields exactly one lane-D question with two readings - 3/3 each.
3. **Gate self-test (A10):** every `bin/` helper demonstrably fails on an
   intentionally wrong patch before its pass counts.
4. **Evals (A38):** rubric scores recorded in the ledger for every replay.
5. **Dashboard:** a request entered at `/new` appears in the queue and its
   detail page tracks a full run's stage transitions; anonymous requests
   302 to the dashboard sign-in; uploads over limits are rejected.
6. **Caps outside the model:** helpers enforce 2/50/2-open-PRs regardless
   of what any prompt says.

## Language policy (A42)

Rust wherever it buys correctness or will run long-lived: the
`factory-verify` crate (the gates ARE the product - typed, cargo-tested,
single static binary) and the dashboard (Axum; a fleet-legible static
binary, no venv). Existing Python host tooling where the ecosystem owns
the job: the Selenium/headless harness, and the status-dashboard
touchpoints (`/api/rulings` repoint, auth-check branch) which live in
that Python app. Prompts, policy, and playbooks stay markdown. Phase-2
direction: the supervisor/poller/publisher daemons are Rust - small
attack surface, static binaries, and the credential-free worker image
stays tiny. Grounding: Jacob's preference (performance + correctness,
2026-07-16), notes p.184 and p.202 (typing puts the burden of
correctness on the model), and the compiler acting as a free
deterministic verifier inside the agent loop. Toolchain note: rustup +
cargo are NOT yet installed on the orchestration VM - first build step.

## Build sequence and estimate (2-3 sessions, + toolchain setup)

1. Install rustup/cargo for `conductor`; migrate constitution + model;
   scaffold rubric, skill, subagents, verify/ crate.
2. `factory-verify` crate green under cargo test (A10 self-tests built
   in); `/factory` skill against replay fixtures until acceptance 1-4
   green.
3. Dashboard v0 + vhost + auth wiring; acceptance 5.
4. Move `factory/queue/` here; repoint `/api/rulings` queue path; ledger
   begins; acceptance 6 and the full pass.

## Amendments this repo enacts (A40)

Ruling A2's location clause and guardrail 8 relocate: factory code,
policy, queue, and ledger live in `patchyard` (checked out on the
orchestration VM, gitignored there like `fieldbook/`); the orchestration
repo keeps the design record. The audit-trail principle is unchanged -
one repo's commit history holds the factory's every move.
