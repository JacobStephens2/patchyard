# Adversarial review of the phase-1 build plan

*2026-07-16. Reviewer: Codex. Target: `PLAN.md` and the given `SPEC.md` at
commit `dee992d`, including the same-day constitution/fixture migration. This
review treats `SPEC.md` as authoritative and does not re-litigate its
requirements.*

## Verdict

Do not execute the sessions in their current order. The plan names most of
the large components, but it does not yield a system that has been accepted
in its final configuration. It verifies against a mechanism that arrives
later, declares the dashboard's full-run acceptance before the
evidence lifecycle exists, performs final acceptance before cutover, and
leaves several SPEC requirements without an owning implementation task.

The session count is also not credible as written. Session 11 is called a
buffer but contains a real migration and cutover, while sessions 4, 6-10,
and probably 5 each contain more than one normal build session of work. The
most likely result is either 14+ sessions or compressed security and failure
testing.

## Blocking dependency and sequencing errors

### 1. Verification depends on a preview mechanism not built until session 9

Session 5 promises `postconditions` “per SPEC,” and session 6 exits only
after ALPHABETIZE has passed through verify (`PLAN.md:90-107`). The SPEC's
sort postcondition requires baseline DOM from the same preview mechanism at
the base SHA (`SPEC.md:240-246`). Preview leasing, in-preview SHA checks, and
headless integration do not land until session 9 (`PLAN.md:134-142`).

At best, session 5 can unit-test a postcondition against canned DOM and
session 6 can run a synthetic replay. Neither is the integrated verification
the exit currently claims. At worst, the builder invents a temporary preview
path that session 9 later replaces, invalidating the earlier tests.

Required repair: either move the minimal preview allocation/SHA/baseline-DOM
slice ahead of session 5, or explicitly split verifier work into pure
fixture tests and post-preview integration. Do not call the session-6 run
end-to-end until the SPEC preview mechanism supplies its baseline.

### 2. Session 8 claims full-run dashboard acceptance before the run can finish

Session 8's exit is SPEC acceptance item 7 “in full,” including stage
transitions “through a run” (`PLAN.md:123-132`). Session 9 is where CI wait,
preview evidence, artifact links, the PR-body update, and the
ready-for-review transition are implemented (`PLAN.md:134-142`). Those are
states in the full pipeline contract (`SPEC.md:211-222`).

The session-8 exit can only use seeded/fake state or stop before the final
states, neither of which is “in full.”

Required repair: make session 8 exit on route, role, upload, hardening, and
seeded-state rendering tests. Put the real full-run stage-transition check
after session 9, in final acceptance.

### 3. Final acceptance precedes material cutover changes

Session 10 declares all acceptance criteria passed. Session 11 then moves
the queue and ledger, repoints `/api/rulings`, and changes operational
documentation and memory (`PLAN.md:144-159`). Those are not cosmetic changes:
they alter intake routing and state location after the accepted build.

Required repair: perform cutover before the final matrix, or give session 11
a mandatory post-cutover regression matrix covering intake, claim, verify,
publish, evidence, retention, and rollback. The final accepted artifact must
be the installed topology, not its pre-cutover approximation.

### 4. Required service identities are used before their creation is assigned

Session 2 requires `/var/lib/patchyard/` ownership and permissions, and
session 3 evaluates the `conductor`/`factory-worker` split
(`PLAN.md:55-59,69-79`). The first explicit service installation is session
8's dashboard unit (`PLAN.md:123-127`). No earlier task creates
`factory-worker`, `factory-web`, or the `factory` group.

Required repair: provision and test all service users/groups in session 1 or
2. Record exact ownership and access assertions before the isolation spike;
do not leave account creation implicit in a later systemd task.

### 5. The GitHub identity dependency is surfaced early but activated late

The GitHub App needs an org administrator, installation, a 1Password key,
and permission iteration, but it appears inside session 7
(`PLAN.md:109-121`). If work starts only when session 7 starts, a human lead
time blocks the publisher and everything after it. The stated PAT fallback
also needs qualification: the SPEC permits a machine-user fine-grained PAT,
not the existing human PAT (`SPEC.md:105-115`).

Required repair: open the App provisioning dependency at session 1 and test
token minting before session 7. If the fallback remains, name its dedicated
machine identity and make “PR author is that identity” part of the exit.

## Exit criteria that can pass without proving the session's contract

Session 1's exit is adequately concrete. The remaining weak exits should be
replaced or supplemented as follows.

| Session | Problem with the stated exit | Objective evidence needed |
| --- | --- | --- |
| 2 | “Kill mid-write” and “ledger consistent” do not identify crash points or invariants. A successful SQLite reopen alone can pass. | Automated crashes before and after each state boundary; asserted request/run/event/lease invariants; `integrity_check`; idempotent retry result. |
| 3 | A recorded decision can exist even if neither runtime has demonstrated the mandatory isolation contract. “Measurements” has no required dataset or decision threshold. | Reproducible probe scripts and raw results for mounts, egress, credentials, startup, teardown, and host writes; explicit must-pass selection criteria. |
| 4 | “Cannot read a canary” and “cannot reach the private network” leave the tested secret locations, CIDRs, protocols, DNS behavior, mount writes, and alternate output channels undefined. | An enumerated hostile test manifest covering environment, SSH/op files, sockets, metadata endpoints, private IPv4/IPv6, DNS, filesystem boundaries, and output schema; all tests automated. |
| 5 | Documentation plus one checksum does not prove a reproducible build or a safe install/rollback. The exit also does not prove the verifier runs cleanly and without mutating its input. | Two independent clean builds with identical hashes; checksum-verified install and rollback exercise; pre/post tree-hash equality under the actual `factory-worker` runtime. |
| 6 | “Dry run through” does not assert the lane, target files, patch semantics, process ordering, provenance, targeted PHPUnit, or repair-loop behavior. Putting B/C/D rows in a bin does not prove any return path. | A replay manifest with exact expected lane/files/postconditions; worker-terminated-before-verify assertion; PHPUnit result; all provenance fields; repair exhaustion; every plan-bin re-entry/close transition. |
| 7 | One scratch PR and one cap race can pass while stale-base refusal, branch ownership, push-crash recovery, cleanup, or reconcile bounds are broken. | Tests for each publisher state transition and crash point; exact bot login; no orphan branch/PR; recorded tree hashes; timeout/output-cap assertions; stale GitHub fail-closed result. |
| 8 | “Acceptance item 7 in full” does not enumerate routes, roles, stage badges, or upload fixtures, and is temporally impossible before session 9. | Route-by-role matrix; exact expected 302/200/403 outcomes; every named upload fixture; systemd/Caddy/socket assertions; seeded rendering tests only at this stage. |
| 9 | One evidence-linked ready PR can pass without proving lease cleanup, before/after SHA checks, navigation restriction, header redaction, extracted DOM, or fail-closed timeouts. | Ledger and artifact assertions for each lifecycle state; both SHA observations; lease cleanup on success/failure; host restriction test; log-secret scan; screenshot and DOM hashes; CI/preview timeout cases. |
| 10 | “All seven criteria pass” has no frozen case manifest, per-case expected state, evidence format, or definition of the fuzz campaign. “Fix and re-run what fails” is open-ended. | Versioned manifest listing every case and each of its three repetitions; expected lane/state/publication count; frozen hashes; fuzz seed/corpus/time budget; zero unresolved failures; rerun from a clean base after fixes. |
| 11 | “Pointers only” and “same spool” do not prove complete migration, namespace separation, disabled old writers, or a usable rollback. | Before/after row and artifact counts/hashes; configuration assertions; old-path write rejection; distinct ruling/request namespace tests; restore and rollback drill; post-cutover smoke. |

## Sessions likely to exceed one-session estimates

The plan says roughly ten implementation sessions plus one buffer
(`PLAN.md:36-40`), but the component estimates are not actually allocated at
that granularity.

| Session | Why it is likely to overrun |
| --- | --- |
| 4 - worker image + credentials | It turns a possibly partial spike into production Firecracker or Podman isolation, image construction, egress enforcement, short-lived credential plumbing, worker I/O, teardown, and adversarial tests. The isolation component itself is estimated at 2-2.5 sessions; sessions 3 and 4 allocate only two. |
| 5 - verifier | Four subcommands, nuanced sort semantics, mutation suites, state integration, reproducible builds, install, and rollback are at least the top of the SPEC's 1-1.5 estimate. The missing runtime-boundary work makes one session less credible. |
| 6 - skill | Triage, harness enforcement, rubric migration, four lane behaviors, plan-bin loops, replay fixtures, repair, and end-to-end orchestration are assigned one session although component 4 is estimated at 1.5-2. Publisher work moving to session 7 does not remove most of this scope. |
| 7 - identity + publisher + reconcile | External App setup, per-run token minting, idempotent Git/worktree publication, a concurrency-safe cap, bounded GitHub reconciliation, and crash recovery are independent failure domains. One happy-path PR plus one race is not enough to finish them in one session. |
| 8 - dashboard | This is the clearest arithmetic mismatch: the SPEC estimates dashboard/auth/Caddy/upload hardening at 1.5-2 sessions, while the plan allocates one. Multipart image decoding/re-encoding, quotas, rate limits, disk-full behavior, auth roles, SSR routes, service hardening, Caddy, and adversarial concurrency plausibly need 2-3. |
| 9 - evidence lifecycle | GitHub CI state, preview allocation, SHA attestation, headless authentication changes, navigation confinement, two artifact types, protected links, PR mutation, cleanup, and timeout states span several systems. One successful ALPHABETIZE run will not harden all failure paths in one session. |
| 10 - acceptance + threat model | Applying `k=3` to the public case, multiple hidden positives, six named near-misses, five injection locations, crash/concurrency cases, gates, and dashboard produces dozens of executions before any discovered-failure reruns. Adding threat modeling, fuzzing, fixes, and clean reruns makes this at least 2 sessions and potentially several. |
| 11 - “buffer” | Queue/ledger migration, status-dashboard routing changes, constitution movement, runbook creation, and operational cutover are a real release session, likely more than one if rollback is exercised. It provides no contingency capacity for sessions 4-10. |

Sessions 1-2 are plausible as the two sessions assigned to component 1.
Session 3 is plausibly time-boxed only if its exit remains a decision and the
mandatory runtime probes are predeclared. The rest of the schedule has no
meaningful buffer.

## SPEC requirements with no owning delivery task

The following are not merely weak exits. No session task explicitly owns
their implementation. Broad headings such as “`/factory` skill” and
“dashboard v0” should not be treated as an assignment for omitted
cross-component behavior.

1. **Clean verifier runtime and ordering.** The SPEC requires the worker to
   be terminated, then verification to run as `factory-worker` in a clean
   environment with before/after tree hashes (`SPEC.md:86-88,204-209`).
   Session 4 owns only the implement-worker boundary, session 5 owns the
   crate, and session 6 merely draws the arrow `worker -> verify`.

2. **Targeted PHPUnit execution as `factory-worker`.** This is explicit at
   `SPEC.md:207-208`; no session task mentions implementing or selecting the
   targeted PHPUnit run.

3. **Plan-bin return paths.** The SPEC requires approved B plans to re-enter
   implement with a Guide and human budget, answered D items to re-triage,
   executed C runbooks to close, and rejected plans to close with a reason
   (`SPEC.md:204-205`). Session 6 implements only B/C/D exits into the bin and
   ledger rows (`PLAN.md:98-107`).

4. **The complete worktree lifecycle.** The SPEC requires a dedicated bare
   clone, fetch-before-branch, same-request ownership checks for an existing
   branch, and cleanup on failure, close, and merge (`SPEC.md:224-228`).
   Session 7 assigns a fresh worktree at the base SHA and a tree-hash check,
   but none of those remaining behaviors (`PLAN.md:115-121`).

5. **Deployed-SHA reconciliation.** `factoryctl` must obtain the deployed
   SHA from the status dashboard's existing source and compare it with the
   merge SHA (`SPEC.md:135-137`). Session 7's reconcile task only names
   bounded GitHub state, and no later session owns deployed-state logic.

6. **Population and validation of all provenance fields.** The schema is
   referenced in session 2, but no session writes or verifies model ID, CLI,
   constitution, rubric, skill, prompt-template, verifier, and base-tree
   hashes on every run as required by `SPEC.md:249-251`.

7. **Separate ruling and software-request namespaces.** Session 11 repoints
   `/api/rulings` to “the intake spool” but never implements or tests the
   namespace separation required at `SPEC.md:138-140`. Its wording instead
   risks putting both inputs into one undifferentiated spool.

8. **The SQLite abstraction boundary.** The SPEC requires sqlx or a thin
   storage trait so PostgreSQL graduation remains cheap (`SPEC.md:141-155`).
   Session 2 assigns SQLite directly without assigning either boundary.

9. **Dashboard-triggered reconciliation.** The SPEC allows a bounded
   reconcile via `factoryctl reconcile <id>` or a dashboard refresh action
   (`SPEC.md:130-134`). Session 7 implements the CLI command, but session 8
   does not assign the refresh action.

10. **Admin-bypassed merge outcome handling.** The SPEC says an
    admin-bypassed merge does not count as a passing factory run
    (`SPEC.md:112-115`). No reconcile, close, or acceptance task tests or
    records that outcome.

11. **The deterministic supervisor boundary.** The supervisor must never
    treat raw request content as instructions (`SPEC.md:67-70`). Session 6
    assigns the interactive skill but no concrete supervisor implementation
    or test that proves raw content is passed only into the isolated
    triage/worker path.

12. **The dashboard's scribe-only boundary.** The dashboard may write only
    an intake row and must use the same validated-request constructor as the
    CLI and pipeline (`SPEC.md:177-191`). Session 8 shares form constants but
    does not assign the server-side constructor call or a test rejecting
    dashboard-owned state transitions, cap checks, triage, and verification.

There is also a concrete manifest ambiguity: the SPEC names
`factory-dashboard.service` (`SPEC.md:159-164`), while session 8 calls for a
“`factory-web` systemd unit” (`PLAN.md:123-127`). If `factory-web` means the
service user, say so and retain the required unit name; if it means the unit
name, the plan contradicts the deployment contract.

## Minimum re-plan before build

1. Make session 1 verify the now-canonical constitution and provision service
   identities; start the GitHub App dependency at the same time.
2. Make session 2 own the storage trait, artifact lifecycle, and explicit
   state/crash invariants.
3. Keep the isolation spike, then split runtime implementation from its
   adversarial qualification if Firecracker wins.
4. Land the minimal preview/SHA/baseline-DOM mechanism before integrated
   verifier and skill acceptance.
5. Give the verifier runtime, targeted PHPUnit, provenance recording, and
   plan-bin return paths explicit owners and exits.
6. Split publisher/worktree/reconcile from bot provisioning and add deployed
   SHA plus crash-idempotency tests.
7. Budget at least two dashboard sessions and separate route/auth behavior
   from upload hardening.
8. Build evidence lifecycle, then cut over the final state/intake topology.
9. Run the frozen acceptance matrix last against that cut-over topology.

Until those changes are made, the plan's session exits can all be met while
the resulting phase 1 still violates the SPEC's verifier boundary, workflow
loops, deployment-state contract, provenance contract, and final-topology
acceptance requirement.
