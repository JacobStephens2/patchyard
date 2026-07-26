# Session 15 improvement proposer v0

## Review declaration

This Session 15 candidate implements the A86 learning substrate and bounded
policy-proposer seat. The substrate is independently useful: `factoryctl
lessons-report` takes a repeatable-read ledger snapshot, emits only typed
production-run outcome facts plus an exact allowlist of bounded operator
quotes, and validates without invoking any model.

The seat remains disabled in installed configuration while A5 live-provider
isolation is unqualified. Its complete fixture path is present: daily
supervisor scheduling, base-pinned prompt bundles, offline proposer and
disposition children, evidence re-derivation, policy-only detached-worktree
validation, cross-family adversarial review with A77 author adjudication, a
durable publisher lease, a fresh GitHub snapshot with a hard one-open-PR cap,
bot authorship, draft-only creation, and no merge API.

Canonical pairing: Claude Fable 5 / max / Claude Code / Anthropic -> GPT-5.6
Sol / xhigh / Codex / OpenAI (`anthropic-claude_fable_5-max-claude_code` ->
`openai-gpt_5_6_sol-xhigh-codex`).

## Data boundary and threshold

`factory.runs.run_class` is now a durable enum copied from the exact
`request.claimed` fact. Normal claims are `production`. Only the fixed Session
14 qualification operator, manifest digest, two-request/two-run budget,
two-hour wall budget, and close-unmerged disposition can claim
`qualification`; the run insert trigger rejects a mismatch. Existing Session
14 claims are backfilled from their durable bypass fact.

The report selects finished production runs only. A relevant cohort is the
exact tuple `(lane, skill, rubric_sha256, prompt_template_sha256,
routing_config_version)`, so unlike policy versions are not silently pooled.
Ten production runs in that cohort are required for a policy candidate.
Qualification runs are absent from the report and cannot contribute to the
threshold, Grafana request aggregates, or run metrics.

Quotes are not arbitrary ledger text. Version 1 permits at most one quote per
run and 32 per report, only from `run.killed:/reason`, with at most 240 Unicode
scalar values. Each span carries its source event, source digest, bounds, and
an explicit `untrusted_operator_quote` label. Request bodies, review bodies,
artifacts, model transcripts, and other event payloads are never queried.

Below threshold the validated model result can only produce an idempotent,
locked, fsynced literal append to the private `docs/ideas.md` projection. The
report digest is the effect identity, so a crash after fsync cannot duplicate
the entry. Installed observations live at
`/var/lib/patchyard/proposer-inbox/docs/ideas.md`; Ansible seeds that file
once and never overwrites it. This is deliberately operator-inspected runtime
state under A69, not an automatic commit or reviewer artifact. An operator
graduates a worthwhile observation into the repository's `docs/ideas.md`
through an ordinary reviewed Git change. Rule 1 in that file makes both the
runtime observation and any later inbox entry authority-free. At threshold
the supervisor re-derives every cited run ID,
count, outcome, and basis-point rate from the report before inspecting the
patch. A PR body records those facts and the report, prompt-bundle, and patch
digests.

## Authority and R19

The model has no repository or GitHub authority. Its child receives the static
instruction prompt and typed packet as separate read-only file descriptors in
an offline bubblewrap namespace. No report byte is interpolated into the
instruction prompt, so a bounded quote cannot spoof a fixed prompt delimiter.
The supervisor applies model output to a detached scratch worktree and rejects
paths outside `policy/` plus the optional `docs/ideas.md` append.

The publisher then creates one deterministic App-authored commit locally. The
reviewer receives that exact SHA plus the supervisor-derived bounded unified
diff in its typed packet, without access to the shared Git object database.
Only that same commit object may be pushed, and the GitHub PR head must equal
the reviewed SHA. Policy review worktrees use a proposer-private capability
root, separate from concurrent pipeline reviewers. The persistent publisher
mirror imports and verifies the configured installed base before every
preparation, including after deploys.

The author and reviewer prompt bundles are resolved from the configured base
commit with `git show`, not the candidate filesystem. Both actual prompts begin
with the base-pinned `AGENTS.md` constitution. `policy/proposer-runtime.json`
is a typed, closed include graph and includes the proposer, reviewer, and
disposition prompts plus its own definition. Candidate graph closure is parsed
as data after patch application; the R19 refusal surface is the union of base
and candidate closures. Any patch that changes a path in that union fails the
authority gate, and a candidate-added dependency must remain under `policy/`
before that refusal is evaluated. Candidate instructions are never loaded into
the current execution or merely delegated to reviewer attention. Tests change
both proposer prompts, add a new runtime fragment, and add an outside-policy
runtime dependency, then prove each candidate is refused while current prompt
bytes remain base-pinned.

Successful author, reviewer, and disposition invocations retain their full
transcripts only as private artifact-store objects referenced by
`proposer_artifacts` and append-only ledger events. Typed review findings are
persisted separately. Every finding receives one concede, evidence-backed
refute, or escalation disposition; disputes become typed records routed to the
existing third-family arbitration stub, while empirical findings require an
experiment. Transcripts are never copied into a subsequent model packet,
report, PR body, or repository path.

The publisher uses the Patchyard Factory GitHub App identity, creates a draft PR,
and does not expose a merge operation. A serialized execution lease, database
single-active invariant, publisher lease, and fresh remote PR listing enforce
one active attempt and the one-open-proposer-PR cap. Publishing identity and PR
title/body are durable before review. The cap counts every open
`factory/proposer/` PR regardless of author identity. Startup, LISTEN reconnect, and the
ordinary bounded supervisor sweep run existing-work-only proposer recovery
even when new scheduled attempts are disabled; an active advisory lease means
"retry later," not daemon failure. Recovery checks an abandoned `proposing`
row against the locked, fsynced ideas digest marker before deciding whether
the effect exists. A
`publishing` attempt reconciles the exact branch/PR/head before any new report
or model call and retries deterministic per-run scratch cleanup plus Git
worktree pruning before terminal success. Full stop is read durably by
scheduler and CLI entry, is rechecked around the ideas effect, and writes a
durable publication-abort intent: recovery may observe an already-created PR
but cannot create a missing one after cancellation. The supervisor re-reads
full stop after `reviewing -> publishing`, and the concrete publisher re-reads
it immediately before each branch push and draft-PR creation effect.

Merge remains a human-only gate under A1. Because A99's App-authorship trigger
applies, enabling the installed schedule is additionally blocked unless
`FACTORY_PROPOSER_DUAL_REVIEW_ENFORCED=true`; operators may set that attestation
only after applying and verifying the GitOps branch-protection rule, which now
requires two approvals. The same at-threshold gate is enforced inside the
proposer, so manual execution cannot bypass it; startup recovery treats a
missing attestation as durable abort intent and cannot create a missing PR.
`FACTORY_PROPOSER_SCHEDULING_ENABLED` starts new scheduled attempts only;
existing durable work is always reconciled, and full stop is the publication
kill switch. The installed template leaves scheduling and dual-review
attestation false.

## Failure-path inventory

Every proposer attempt has its own durable lifecycle and does not enter
production run metrics. The named terminal states are:

| Terminal state | Terminal condition |
| :-- | :-- |
| `idea_appended` | A valid below-threshold idea was appended and fsynced. |
| `ready_for_review` | The exact evidence-cited candidate is an open draft PR. |
| `open_pr_cap_reached` | A fresh snapshot found an existing open proposer PR, including a race check immediately before PR creation. |
| `report_failed` | Snapshot creation or deterministic report validation failed. |
| `report_too_large` | The report or prompt packet exceeded its byte bound. |
| `proposer_contract_failed` | The child failed, was cancelled, timed out, or returned malformed output. |
| `evidence_citation_failed` | A citation did not exactly match the report cohort, run IDs, count, state, or rate. |
| `authority_surface_failed` | Patch application, limits, regular-file checks, R19 prompt-closure refusal, or the `policy/` plus optional ideas allowlist failed. |
| `adversarial_review_failed` | Review/disposition failed, findings were conceded, or a typed dispute/experiment requires a new attempt. |
| `publication_failed` | Candidate preparation failed before the durable publishing boundary. Once `publishing`, retryable external uncertainty stays nonterminal for reconciliation. |
| `cleanup_failed` | Scratch or child cleanup could not prove completion. |
| `killed` | Full stop, shutdown, cancellation, or termination interrupted the attempt. |

Transitions and finite reason codes are appended to `proposer_events`.
Incomplete attempts remain visible for reconciliation. The database permits
only one nonterminal proposer row, and a PostgreSQL advisory lease rejects a
concurrent timer/CLI attempt. No failure is rewritten as success and no PR is
merged automatically.

## Verification limits and planned live coverage

CI and local fixture verification prove schema validation, deterministic
byte-identical reporting, repeatable-read snapshot bounds, production-only
selection, quote allowlisting and truncation, report-only prompt construction,
below- and at-threshold behavior, same-cohort qualification exclusion above threshold,
exact evidence citations, the one-open-PR refusal, path and symlink rejection,
R19 base/candidate closure refusal, cross-family routing and A77 disposition,
durable full-stop re-reads, cancellation around a held ideas-file lock, lifecycle
transitions, and the fixed child-launcher mount/network contract. The
PostgreSQL acceptance test runs all migrations and grants against a disposable
PostgreSQL 16 service and recovers an fsynced idea marker after a simulated
process exit. A second local-bare-remote fixture uses the concrete publisher to
prove deterministic App identity, rejection of a pre-existing wrong-head PR,
acceptance and durable recording of an exact-head PR, reviewed SHA equals
published SHA, read-only abort recovery before PR creation, PR-record restart
reconciliation, and persistent-mirror refresh across two installed base
revisions. Source-level wiring additionally starts the existing-work recovery
sweep on daemon startup and every LISTEN reconnect; the installed service path
remains part of the live verification matrix below.

Those checks do not prove live provider execution, the installed App's real
GitHub draft-PR behavior, systemd scheduling, the control-plane
bubblewrap/kernel boundary, or persistent ideas projection ownership. After
A5 qualification, the live/operator path must deliberately cover: a read-only
standalone report against the installed ledger; one below-threshold append;
one disposable policy branch opened by the bot and closed unmerged; refusal
while that PR remains open; cancellation during proposer, reviewer, and
publisher phases; service restart at each durable boundary; hostile prompt
text in every allowed quote source; and verified zero residual processes,
mounts, namespaces, branches, and scratch paths. The installed schedule stays
off until that coverage succeeds. No source-text assertion is counted as a
substitute for those live postconditions.
