# Disposition of the GPT 5.6-Sol critique

*2026-07-16. Adjudicated by the orchestration agent; ruling calls by
Jacob. Target: critique of SPEC v1 (`3e7a76b`); result: SPEC v2.*

| # | Finding | Disposition |
| --- | --- | --- |
| 1 | Human trigger ≠ content trust; interactive worker holds fleet credentials | **Conceded in principle; Jacob ruled the strong remedy**: full container isolation in phase 1, with microVMs (Firecracker) evaluated first - /dev/kvm verified present. One correction retained against the critique: harness-enforced tool removal is a real boundary (a no-Bash subagent cannot shell out); it is kept as defense-in-depth under the OS boundary, not as the boundary |
| 2 | Dashboard must not run as conductor | **Conceded** - `factory-web` user, Unix socket, systemd hardening |
| 3 | Git is not a runtime ledger; privacy in Git history | **Conceded; Jacob ruled**: SQLite + `/var/lib/patchyard/` artifact store in phase 1 (amends D4, A40); Git keeps code/policy/fixtures |
| 4 | Evidence pipeline impossible as written | **Conceded** - draft-PR lifecycle, preview leases with SHA verification, headless auth extension, authenticated evidence route |
| 5 | Approval identity broken (author = Jacob's PAT) | **Partially conceded; Jacob ruled**: current branch protection and self-approve retained for now; factory gets its own machine identity (GitHub App preferred, machine-user PAT fallback) so PRs read as factory-authored and any approver may review. Admin-bypassed merges do not count as passing runs |
| 6 | Authorization scope conflates submit/view | **Conceded** - `factory_submit` / `factory_admin`; admin-only lists and evidence in phase 1 |
| 7 | Upload security asserted, not specified | **Conceded** - hardening acceptance criteria + adversarial fixtures in SPEC v2 |
| 8 | Live `gh` at render time | **Conceded** - reconcile into SQLite, render local, fail closed on the cap |
| 9 | Replay set memorizes the pilot | **Conceded** - hidden positives, near-miss negatives, injection, concurrency fixtures; wrong-target rate measured |
| 10 | ALPHABETIZE live test vs held PR | **Resolved by Jacob**: PR #213 closed 2026-07-16; live run publishes the factory's own draft PR |
| 11 | Closure/deploy transitions unowned | **Conceded** - `factoryctl reconcile/close`; deployed SHA from the status dashboard's source |
| 12 | Estimate + supply chain | **Conceded; Jacob accepted higher estimate** - component estimates ~8-11 sessions; toolchain pinning, cargo audit/deny, threat-model session |
| 13 | Sort postcondition underdefined | **Conceded** - capture semantics, ruled sort key, sentinel/duplicate handling, shared-caller enumeration, listOrder evidence requirement |
| 14 | bin/ vocabulary mismatch | **Conceded** - single `factory-verify` vocabulary; mutations enumerated per subcommand |
| 15 | Cap definitions incomplete | **Conceded** - diff accounting defined; open-PR cap moved to publisher state under lease |
| 16 | Worktree root in shared cache | **Conceded** - dedicated bare clone under `/var/lib/patchyard/worktrees/` |
| 17 | No provenance in run records | **Conceded** - model/CLI/constitution/rubric/skill/prompt/verifier/tree hashes recorded per run |

Net: 15 conceded, 2 resolved by ruling with modifications (1, 5). Zero
findings rejected outright; one sub-claim corrected (tool-allowlist
enforcement, folded into finding 1's disposition).
