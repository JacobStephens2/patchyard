<!-- Frozen provenance copy, vendored 2026-07-20 per the AGENTS.md dependency audit: the factory repo is self-contained (A68/A69). Original lived in the orchestration repo at projects/software-factory/synthesis/; that copy is historical. -->

# Comparison - four proposals, dimension by dimension

Shorthand used below: **Fable** = `fable-5-xhigh`, **GPT** =
`gpt-5-6-sol-xhigh`, **Grok** = `grok-4-5-high`, **Council** =
`perplexity-model-council` (GLM 5.2, Gemini 3.1 Pro Thinking, Kimi K2.6
Thinking - cited individually where they diverge).

## Where all four agree (treat as settled)

1. **The autonomy boundary is an evidenced PR.** Nothing merges itself;
   Jacob's merge is the gate; the existing typed-hostname prod deploy flow
   is untouched. Unanimous, stated independently by every proposal.
2. **Email and screenshots are untrusted input**, even forwarded by a
   colleague. Every design quarantines request text as data, not
   instructions.
3. **Triage into lanes, with rules that can only demote.** All four
   reject "model confidence authorizes coding": Fable ("confidence below
   threshold never promotes"), GPT ("deterministic veto... confidence is
   not an authorization mechanism"), Grok ("rule-first, model-second"),
   Kimi ("aggressive about refusing automation").
4. **Start with exactly one request class** (dropdown alphabetization) and
   widen only on measured evidence. Unanimous, including the Council.
5. **Schema/DDL, payments, auth, and outbound comms are never
   auto-resolvable.** All four exclude them by name.
6. **The factory never sends external email.** Drafts (Fable, Grok) or
   `mailto:` links (GPT); the Council's auto-reply idea is its one outlier
   (see decision log).
7. **Measure human-minutes-per-shipped-change, not PR count.** All four
   land on the same core metric independently.

The disagreement space is therefore narrow: where the machinery runs, how
much isolation the coding step needs, and how much to build before volume
is proven.

## Summary matrix

| Dimension | Fable | GPT | Grok | Council |
| :-- | :-- | :-- | :-- | :-- |
| Grounded in Patchyard's real infra | Yes - ran the pilot (PR #213) | Yes - builds on the pilot, cites CI run | Yes - own root-cause of both files | No - designed blind, GLM invents a repo layout |
| Control plane location | This VM, orchestration repo | New `/srv/software-factory` Python app | This VM, `factory/` in orchestration repo | Cloud Run / GitHub Actions / Zapier |
| Coding runtime | claude-orchestrator in a worktree | `codex exec` in a locked-down container | Existing agent wrappers in a worktree | Claude Code Action / Agentic Workflows on Actions runners |
| Isolation of unattended runs | Named as phase-2 question | Central design input: worker has zero credentials | conductor privileges + path gates | Actions sandbox / safe outputs |
| Intake | Manual → mailbox + cron poll | Dedicated mailbox, `gmail.readonly` OAuth, 2-min poll | Manual → dashboard form → mailbox | Gmail Pub/Sub push, or Zapier/Postmark webhook |
| Publish identity | Existing `gh` PAT (phase 1) | Repo-scoped GitHub App, draft PRs | conductor + `gh` | github-actions bot |
| Lanes | 4 (A auto / B spec / C ops / D clarify) | 4 (A / B investigate / C clarify / D ops-reject) | 2 (Fast / Spec) + human triage bucket | 3 (AUTO_SAFE / AUTO_ASSIST / MANUAL) |
| Lane-A caps | ≤2 files / ≤50 lines | ≤5 files / ≤100 lines | Per-skill, e.g. 5/80 for sort-dropdown | Small-diff principle, no number |
| State/ledger | `queue/` + `runs.md` markdown | SQLite WAL, explicit state machine, leases | Queue dirs + `events.jsonl` | GitHub issues as the queue |
| Verification | php -l, CI, preview screenshot mandatory | Deterministic patch gate, DOM assertion, independent review, 1 repair loop | Diff budget, greps, headless evidence, security bookend, fail-twice escalation | Kimi: deterministic resolver with permutation postcondition |
| Self-improvement | Every misclassification edits `rubric.md` | Labeled outcomes + replay corpus; never self-edits policy | Rejects amend skill docs within 48h, via PR | Convergence loops (implementer + checker) |
| Estimated cost to useful | 1-2 sessions (phase 1) | 8-14 engineering days (phases 0-2) | 3-4 weeks side-project time | Days (GLM phase 1) to weeks |

## The five real divergences

### 1. Where the factory runs: this VM vs the cloud

Fable, GPT, and Grok all put the control plane on the orchestration VM,
because the parts bin is here: fieldbook checkout, preview envs, headless
Chromium, deploy dashboard, secrets plumbing. The Council, designing
without access to any of that, reaches for Cloud Run + Pub/Sub + GCS
(GLM), Zapier + Agentic Workflows (Gemini), or a generic pipeline (Kimi).
GLM goes as far as inventing `src/content/` and `tours.json` - a repo
structure Fieldbook does not have - and proposes storing internal ERP
screenshots in a GCS bucket with public-read URLs.

The split is explained entirely by information access, and it is the
strongest argument in the whole corpus for keeping execution local: the
three proposals that could see the codebase found the same two root-cause
files (`common_functions.php` `get_salespeople_usernames()` with no
`ORDER BY`; `leads/assign.php` ordering by `listOrder`); the council
never located a file. A GitHub-Actions coding runtime would have the
Council's view of the world, not this VM's.

### 2. How much isolation the coding step needs

The widest genuine disagreement.

- **Fable** runs everything as `conductor` via `claude-orchestrator`,
  flags headless-auth as a phase-2 question, and leans on caps + review.
- **Grok** keeps conductor privileges but adds path allow/refuse gates
  enforced outside the model and a "security bookend" re-check of the
  final diff.
- **GPT** treats the current wrapper as disqualifying for unattended use -
  "it resolves the full `env.tpl` secret set and starts Claude Code with
  permission checks bypassed" - and designs a zoned system: a coding
  worker with no credentials at all, a deterministic verifier that runs
  after the worker is terminated, and a separate credentialed publisher
  that only ever applies a verified patch artifact.
- **Gemini** gets the same property from GitHub's safe-outputs primitive:
  the agent proposes in a read-only sandbox; a narrowly scoped handler
  performs the write.

These positions are reconcilable once you notice they answer different
questions. Fable and Grok describe *interactive* runs - Jacob triggers the
session, so a human vouches for the input at time zero. GPT and Gemini
describe *unattended* runs - arbitrary email starts the machinery with
nobody watching, so prompt injection in a screenshot must land in a
process that has nothing to steal. The synthesis adopts exactly that
split: interactive phase 1 on the current wrapper, and GPT's
worker/publisher separation as a hard precondition for phase 2, not an
optional hardening.

### 3. Intake mechanics

Manual forward (all), then: cron-polled dedicated mailbox (Fable, GPT,
Grok phase 4) vs Gmail Pub/Sub push (GLM, Kimi) vs third-party webhook
(Gemini via Zapier/Postmark). GPT is the only one to specify the scope
discipline that matters: a *dedicated* mailbox, `gmail.readonly` only
(no `gmail.modify`, which can send), no domain-wide delegation, sender
allowlist, idempotency keys on Gmail message IDs. The Council's own GLM
concedes polling is the pragmatic start; Kimi proposes push then
immediately documents the watch-renewal and historyId-invalidation
failure modes that make push an ops project. At Patchyard volume (requests per
week, maybe per month), a 2-minute poll is indistinguishable from push
for the requester and strictly simpler to operate.

### 4. State: markdown vs JSONL vs SQLite vs GitHub issues

Fable's `runs.md`, Grok's queue-directories + `events.jsonl`, GPT's
SQLite state machine with leases and uniqueness constraints, the
Council's GitHub-issues-as-queue. This tracks each proposal's phase
ambition: markdown is fine while a human triggers every run and can see
what happened; the moment runs are unattended, GPT's arguments bite -
crash recovery, duplicate-forward dedup, "reprocessing the same email
returns the existing run instead of opening a second PR." GitHub issues
as the queue (GLM) puts request state where the requesters aren't and
adds a public-ish surface for internal screenshots.

### 5. How the factory improves

Three mechanisms, increasing in rigor: Fable edits `rubric.md` on every
misclassification; Grok amends skill playbooks within 48h of a rejection,
via reviewed PR; GPT labels every human outcome, maintains a replay
corpus, and requires any policy/prompt/model change to pass replay before
shipping - and states the sharpest constraint: **the factory never edits
its own policy.** The Council's "convergence loop" (implementer iterates
against a checker until green) is the runtime version of improvement;
GPT caps the same idea at exactly one repair attempt so an unattended
agent cannot loop until it finds a way around a gate. One-repair-then-
escalate is the safer default; Grok independently lands nearby
(fail-twice → escalate).

## Smaller contrasts worth recording

- **Caps.** 2/50 (Fable) vs 5/100 (GPT) vs per-skill (Grok). The actual
  pilot diff was 2 files / 3 lines. Fable's tighter cap costs nothing at
  current volume and demotion to lane B is cheap; caps can widen with
  evidence, but not credibly tighten after an incident.
- **The PR as a product.** Grok is best on the reviewer experience:
  mandatory explainer template, before/after evidence, an optional 1-2
  question "reviewer quiz" as an anti-rubber-stamp device, and the
  explicit anti-metric that zero human review time is a failure, not a
  goal. GPT specifies the most complete PR body contract.
- **Verification of the verifier.** Grok's dry-run checklist requires the
  verify script to *fail* on an intentionally wrong patch before it may
  pass the right one. Nobody else thought of testing the gate itself;
  GPT's factory acceptance tests are the system-level equivalent.
- **The dominant failure mode.** Kimi names it best: not "sorted wrong"
  but "edited the wrong thing" - ambiguous forwarded email plus
  screenshot-only context means target identification, not code
  generation, is where the risk lives. GPT's evidence requirements and
  Fable's category D (never guess; draft a clarifying question) are the
  countermeasures.
- **Business continuity.** Only Grok says out loud that Fred's fix should
  not wait for process design - ship it now, use it as the factory's
  golden-path fixture. Fable made the same call implicitly by actually
  opening PR #213 before writing the spec.
- **Sort-key judgment call.** Fable and GPT both flag first-name-vs-last-
  name as a decision the PR must surface (PR #213 sorts by first name,
  matching the "First Last" labels); Grok's skill notes the listOrder
  nuance and tells the agent to escalate if the request said "fix the
  order" without "A-Z". Same instinct three ways: reversible assumptions
  are allowed if named in the PR; silent guesses are not.

## Addendum (2026-07-14, later the same day) - the fifth input

A fifth input arrived after the comparison above was written:
`../perplexity-computer-orchestrator/` - Perplexity's computer agent
orchestrating a nine-agent research council (A1 operating model through
A9 skeptical review) into `FINAL_ai_native_software_factory.md`. It is
not commensurable with the four proposals row-by-row, for two reasons,
so it gets an addendum rather than a fifth matrix column.

**It answered a different prompt.** Its brief (its own `prompt.md`) asks
for the general AI-native factory *operating model* - autonomy ladder,
risk tiers, metrics, governance - for a generalized Patchyard (40 employees - correct, per Jacob 2026-07-16 - with containers, IaC, multi-OS agent fleets; Patchyard's headcount matches, but its engineering capacity is ~one person and it ships a PHP monolith to VMs). The four proposals designed the ALPHABETIZE
email-to-PR pipeline; this designs the policy regime around any such
pipeline.

**It is not independent.** The brief was written after the synthesis
existed and embeds its trust model verbatim - "separating credential-free
coding workers from privileged publishers," untrusted-input handling, an
autonomy ladder. So where it lands on the same architecture, that is a
directed research-validation pass coming back positive, not a fifth
blind convergence. What it validates, now with citations: the
worker/publisher split as the single most important architectural
decision, single-agent-per-task as the default, verification structurally
separate from generation, machine-enforced (not memo) governance, risk
tier over model confidence, and human review capacity - not compute - as
the binding constraint.

**What it adds that no pipeline proposal had** (now in the decision log
as A18-A24, D9-D10):

- **Evidence-gated promotion with expiry.** Pre-registered gate numbers,
  quarterly re-certification of any widened autonomy, and pre-defined
  demotion triggers. Its sharpest single idea: a verifier approval rate
  sustained above ~98% is a *drift alarm*, because from the inside a
  too-agreeable gate is indistinguishable from a perfect factory.
- **Cross-model-family verification.** The unattended verifier should be
  a different provider than the implementer, on a clean context, prompted
  to reject - LLM judges measure at sub-25% true-negative rates on code
  correctness, so a same-family second opinion is mostly a rubber stamp.
- **The counter-evidence dossier (A9).** METR's RCT (experienced devs 19%
  slower while believing 20% faster), Veracode (~45% of generated samples
  carry an OWASP Top 10 flaw, flat across model sizes), GitClear (churn
  and copy-paste rising), the curl bounty collapse, Replit/Amazon Q/MCP
  incidents. This is the strongest available argument for the synthesis's
  existing conservatism - and for measuring with timestamps, not
  impressions.
- **Gaming-resistant metrics.** Cost per *surviving* fix (2-week churn
  window), mutation score over line coverage, and a PR-volume cap tied to
  review capacity.

**Where it is wrong for Patchyard as written** (decision log R15-R18): the
control-group pilot needs a second engineering track that does not exist
here; the platform stack (Modal/E2B sandboxes, OIDC→STS, cosign/SLSA,
canary delivery) assumes containers and cloud deploys fieldbook does not
have; the compliance apparatus (SBOM, WORM logs, MRM registers) outsizes
a company this small - a concession its own synthesis partly makes; and
its "not the ERP" pilot scope is contradicted by its own tier matrix,
which places non-payment ERP display fixes in T1 - precisely the
ALPHABETIZE class the pilot already shipped as PR #213.

Net effect on the synthesis: the pipeline is unchanged; the *policy
regime around it* got stricter. Gates became pre-registered and
expiring, the phase-2 verifier became cross-family, the ledger's
denominators became gaming-resistant, and the lethal-trifecta check
became a standing guardrail.

## Addendum 2 - the conference-notes pass

A final mining pass over Jacob's AIEWF 2026 notebook
(`../../../conferences/ai-engineer-worlds-fair-2026/notes-transcript.md`)
produced decision-log rows A25-A30, D11, and R19. Beyond the
incorporations, the notes independently corroborate several standing
rulings, worth citing because they come from practitioners rather than
proposals:

- **Sonar's CMU figure** (p.194) - a 3-5x velocity boost that dissipates
  within 8 months under +80% security/maintainability issues - is the
  best external justification for measuring cost per *surviving* fix
  (A22) rather than per merged PR.
- **Form3's production-agent talk** (p.158-161) - docker.sock as
  root-equivalent, microVM walls, egress allowlists - independently
  specifies the same credential-free worker the synthesis requires for
  unattended runs (D1).
- **Dailey's "the doc is the state; the agent is the action"** (p.50) is
  the queue/rubric/ledger design in one sentence, and his "too many PRs"
  failure mode is A21's PR cap seen from the team side.
- **Osmani's "orchestration tax"** (p.228) names why A21 exists: more
  agents running does not make more reviewer.
- **Garry Tan's "never do one-off work - skillify it"** (p.54) is the
  skill catalog's thesis (A6), from the closing keynote.
- **Horthy's brownfield warning** (p.182 - agents stall in decade-old
  codebases) tempts a stricter ERP stance but changes nothing: R18
  already fences ERP core while keeping display-order fixes in lane A.

## Addendum 3 - the agentic-SDLC survey pass (2026-07-16)

A survey of agentic engineering SDLCs ("Agentic Engineering SDLCs: A
Comprehensive Survey," uploaded 2026-07-16; archived at
`../research/agentic-sdlc-survey.md`) produced decision-log rows A36-A39
(constitution as stage zero, per-role subagents with tool restrictions,
evals alongside tests, topology named) and R20-R21 (no Spec Kit
dependency, no agent teams). Beyond those, it independently corroborates
standing rulings from a different literature than the fifth input drew
on - worth citing because convergence from separate sources is the
strongest signal this corpus produces:

- **Single-agent-per-task as the default.** The survey's decision
  heuristic lands on orchestrator-worker/pipeline for production and
  calls agent teams experimental - the same conclusion the fifth input's
  A2 reached from the vendor-dispute angle.
- **"Harness quality generally beats model quality"** (Google's
  whitepaper, per the survey). Grok's model-independent-harness argument
  - build the control plane, swap the workers - now with Google's name
  on it.
- **The 80% rule** - agents nail the first 80%; the last 20% (edge
  cases, error handling, integration nuance, subtle business rules) is
  where engineering lives. This is the theory behind lane-B demotion:
  over-cap and ambiguity triggers are precisely the factory detecting
  that it has hit the 20%.
- **Conductor vs orchestrator mindsets** map exactly onto the two-mode
  trust model: interactive phase 1 is conductor mode (human directs,
  step by step), unattended phase 2 is orchestrator mode (human defines
  objectives and reviews results).
- **The three durable human jobs - intent, architecture, judgment** -
  map onto the factory's human touchpoints: intent = the requester plus
  triage confirmation, architecture = lane-B specs staying
  human-approved, judgment = the merge gate. The factory automates
  everything except exactly the three things the survey says stay human.
