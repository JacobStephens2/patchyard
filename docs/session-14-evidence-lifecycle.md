# Session 14 evidence lifecycle

Status: failure inventory and verification limits declared before the first
Session 14 implementation PR and before live qualification.

## Decision

The supervisor owns one restart-safe lifecycle after the publisher creates a
draft pull request:

1. It mints a fresh GitHub App token for the Fieldbook repository with exactly
   `contents:read`, `pull_requests:write`, and `checks:read`.
2. It waits for every GitHub check run on the durable PR head to reach
   `success`. An empty check set is a wait state, not success. Every other
   terminal conclusion has its own run state.
3. It leases Session 7's preview slice at the exact baseline SHA, authorizes
   one short-lived evidence capability, runs Session 13's isolated browser,
   re-verifies the SHA, scans control-plane and preview logs for the bearer and
   capability ID, and explicitly releases the lease. The browser supplies the
   capability only to Traefik's forward-auth boundary; an ordered Traefik
   middleware removes the private header before legacy PHP receives the
   translated application authorization.
4. It repeats that sequence for the exact candidate SHA.
5. Only after each isolated child has ended, the SHA proof and both log scans
   have passed, and the lease has been released does it import the bounded
   child outputs into the private artifact store. Baseline and candidate
   filenames are unique. The artifact ledger carries the SHA-256 for every DOM
   snapshot, screenshot, extracted order, child hash manifest, execution
   manifest, and lifecycle proof.
6. It replaces the pending evidence section in the PR body with authenticated
   dashboard links and each artifact SHA-256, verifies the full A11 and A26
   contract as live GitHub state, then uses GitHub's ready-for-review mutation.
   The drafted requester reply is body text only and is never sent (A34).

The dashboard remains a read-only scribe (A53/A66). The supervisor performs
every transition and side effect (A65). The orchestration host is absent from
the runtime path (A68). No process self-merges or deploys (A1).

## A26 explain-diff scope

The Session 14 implementation does not infer PHP call-graph sharing. Its
`shared_function_touched` gate is deliberately conservative but filename-based:
every changed target whose path ends in `.php`, including the Session 7 target
`mfieldbook/common_functions.php`, requires the A26 explain-diff section. The
guarantee is therefore limited to PHP-suffix matching; it does not establish
semantic shared-function detection or cover shared functions in non-PHP files.
This is the actual installed scope, recorded here rather than implied to be a
general shared-function analysis.

## Durable and cancellation semantics

`awaiting_ci`, `capturing_evidence`, and `finalizing_pr` are resumable durable
states. CI success, each evidence pack, the final body update, and the
ready-for-review mutation have idempotent side-effect rows. The CI effect's
original `started_at` is the restart-stable deadline, and even a completed
effect is re-observed against GitHub before evidence work resumes. Recovery
accepts an evidence pack only when all six kinds are present as bounded
regular files, every stored digest still matches, and the lifecycle manifest
binds the exact stage and SHA being resumed. One initial lifecycle entry plus
two resumptions is the durable maximum.

No Rust or database lock is held across GitHub, SSH, preview, browser, log
scan, or filesystem awaits. Caller cancellation before bearer issuance leaves
the durable stage resumable. Once a bearer exists, the supervisor uses a
fresh teardown token for the post-capture SHA check and both log scans; the
outer preview lease release also uses a fresh token. Cleanup is an explicit
checked close, never delegated to `Drop`. A checked holder logs any future
that is dropped without observing explicit release, while the TTL sweeper
remains only the non-graceful backstop. Acquisition errors run a deterministic
lease-ID compensation through the bridge before the original error is
returned. A cleanup error overrides success and every other operation result.

Both log scanners now require a positive proof of observation: a unique,
non-secret sentinel is emitted into the bounded window and must be found,
`bytes_scanned` must be positive, and exact bearer/capability matches must
remain zero. CI executes each scanner against a real subprocess stream with a
planted bearer and independently counted sentinel.

## Predeclared failure-path inventory

Every triggered failure below must persist exactly the named terminal run
state, leave the PR unmerged and draft, send no requester reply, and import no
partial evidence pack. CI conclusion rows are deliberately separate because
GitHub gives each a distinct terminal meaning.

| ID | Trigger | Required terminal state |
| --- | --- | --- |
| S14-N01 | GitHub returns no check runs, or at least one queued/in-progress check, until the lifecycle deadline | `ci_wait_timed_out` |
| S14-N02 | GitHub check observation fails, is paginated/inconsistent, names the wrong head, or contains an unknown status/conclusion | `ci_observation_failed` |
| S14-N03 | A completed check concludes `failure` | `ci_failed` |
| S14-N04 | A completed check concludes `cancelled` | `ci_cancelled` |
| S14-N05 | A completed check concludes `timed_out` | `ci_job_timed_out` |
| S14-N06 | A completed check concludes `action_required` | `ci_action_required` |
| S14-N07 | A completed check concludes `neutral` | `ci_neutral` |
| S14-N08 | A completed check concludes `skipped` | `ci_skipped` |
| S14-N09 | A completed check concludes `stale` | `ci_stale` |
| S14-N10 | A completed check concludes `startup_failure` | `ci_startup_failed` |
| S14-N11 | Preview acquisition, authorization, bridge response, or leased-host validation fails | `preview_failed` |
| S14-N12 | Preview bridge or isolated browser crosses its deadline | `preview_timed_out` |
| S14-N13 | Host or running preview HEAD differs before or after capture | `preview_sha_changed` |
| S14-N14 | The isolated child returns a rejected browser/navigation/output state, an incomplete pack, or a recovered artifact digest mismatch | `evidence_failed` |
| S14-N15 | Child output, control-plane logs, or preview logs contain bearer material, or either bounded log scan cannot prove zero matches | `secret_scan_failed` |
| S14-N16 | Preview or isolated-child teardown reports any residue on a success, failure, timeout, or cancellation path | `lease_cleanup_failed` |
| S14-N17 | Durable/live PR identity, exact head, bot author, full body contract, body update, or ready-for-review mutation differs from intent | `pr_contract_failed` |

Session 13's S13-N01 through S13-N12 fixtures remain the browser-boundary
substates beneath S14-N12, N14, N15, and N16. In particular, a redirect,
cross-origin navigation, popup, or download never broadens the leased-host
allowlist; it makes the evidence operation fail closed.

## Verification limits and live coverage plan

GitHub-hosted CI can prove source-level and provider-free behavior:

- every GitHub terminal conclusion maps to its declared state;
- CI wait timeout and malformed/wrong-head snapshots fail closed, completed
  waits are re-observed, and resume cannot reset the original deadline;
- success and injected evidence failure both call explicit lease release;
- cleanup failure overrides both successful and failed capture;
- child output is not imported before child teardown, post-capture SHA proof,
  zero-match log scans, and lease release;
- partial, symlinked, oversized, digest-changed, or wrong-SHA recovery packs
  are rejected;
- every Session 13 browser terminal substate maps through the full lifecycle
  to its declared Session 14 state;
- preview acquisition compensation, bounded lifecycle attempts, premature
  ready-effect resume, and retained failure classification are regression
  tested;
- real-stream planted-secret tests prove detection and require a visible
  non-secret sentinel plus positive bytes from both scan implementations;
- a real Traefik integration test proves the forward-auth service receives the
  private capability, while the downstream backend receives the translated
  application `Authorization` and no `X-Patchyard-Factory-Capability` header;
- only the exact numbered leased preview origin is accepted;
- final bodies contain the A11/A26 contract, authenticated `/evidence` links,
  artifact SHA-256 values, and no sent reply;
- cancellation and subprocess cleanup obey `docs/rust-practices.md`.

The converged control-plane and preview hosts must prove what a source-text
test cannot:

- the installed GitHub App can mint the exact lifecycle scope and observe the
  real Fieldbook Actions check on the published head;
- the real draft PR waits through GitHub's observed states and becomes
  ready-for-review only after both evidence packs are durable;
- the baseline and candidate slots run the exact requested SHAs and all
  browser navigation remains on the leased numbered host;
- the deployed Traefik middleware order authenticates the private capability
  and removes it before the legacy PHP backend;
- the installed journal and preview-container scan reads its real bounded log
  sources and reports zero bearer/capability matches;
- success and an injected post-authorization failure both leave no lease,
  capability, checkout, container, network, mount, child unit, or staging
  residue;
- authenticated dashboard sessions can fetch every linked artifact and the
  served bytes match the linked SHA-256.

Live qualification is a deliberate operator path through the same supervisor,
preview bridge, isolated child, artifact store, database, and GitHub adapters.
It is not a second lifecycle implementation. The qualification record captures
the PR/run IDs, exact base/head SHAs, check-run facts, artifact hashes,
zero-match scans, and cleanup proofs without recording the preview bearer.

The fixed operator entry point is
`/usr/local/sbin/patchyard-stage-session14-qualification`. It accepts a
queued request whose source is an enabled dashboard account, or only the same
released claimed row when a foreground attempt failed before creating any run.
It stops the resident dry-run supervisor, runs `factoryctl run` through the
production pipeline, and restores the resident supervisor on every exit. The
form remains the only intake. The operator never creates or edits a request.

Qualification uses two form submissions containing the verbatim sanitized
`fixtures/acceptance/alphabetize/request.md` request, both pinned to the same
observed Fieldbook `master` SHA:

1. `failure` replaces the evidence selector with a deliberately absent ID.
   Preview authorization therefore precedes the isolated browser rejection.
   The expected result is `evidence_failed`, a still-draft PR, no imported
   artifacts, one durable pair of zero-match log scans, and an explicit clean
   preview release.
2. `success` uses the real `#sales_person_id` selector. The expected result is
   `ready_for_review`, a non-draft PR, twelve hashed baseline/candidate
   artifacts, two durable pairs of zero-match log scans, and two explicit clean
   preview releases.

The qualification service is a bounded two-hour oneshot with `SIGINT` graceful
cancellation, the same database role, GitHub App, preview SSH boundary, child
launcher, and artifact roots as the resident supervisor. Its deterministic
publisher fixture applies the real two-file SQL ordering patch to current
Fieldbook source; it does not substitute the synthetic Session 9 repository.

## Live qualification record

The preview host and control plane were converged from this branch on
2026-07-25. Preview convergence completed with `failed=0`; the control plane
applied migration 7, installed the lifecycle supervisor and qualification
entry point, and passed both the Session 13 and Session 14 host qualifiers.
Fieldbook `master` remained
`4ef35181f7a700b02e63808e483d7c23f33b91d8`, and the real two-file
ALPHABETIZE patch applied cleanly to that exact tree.

The first Session 14 host qualifier also found a live-only assertion defect:
systemd reports `KillSignal=SIGINT` canonically as `2`. The unit was correctly
configured, but the assertion expected the symbolic spelling. Commit
`9c577c3` now checks the canonical value, and the subsequent exact-head
converge passed (`factory-control`: `ok=52`, `failed=0`; `factory-worker`:
`ok=1`, `failed=0`). This is the same category of source-insufficient check
that the Session 13 verification-limits declaration anticipated.

Fable's review supplied the ruled roster: Jacob Stephens and Engineer Two are `factory_admin`; the Owner is `factory_submit`. That roster
is now committed as A69 desired state.

The reviewer-repair head `2ebdf2c5e62e979f9fa18264ae3db94430a49faf`
then converged on both live boundaries. Preview convergence completed with
`failed=0`. Control convergence applied migration 8, installed the sentinel
scanner and repaired lifecycle, and passed the Session 13 and Session 14 host
qualifiers (`factory-control`: `ok=53`, `failed=0`; `factory-worker`: `ok=1`,
`failed=0`). An immediate exact-head repeat was idempotent
(`factory-control`: `ok=48`, `changed=0`, `failed=0`; `factory-worker`:
`ok=1`, `changed=0`, `failed=0`).

The approved roster's three password references are now vault-backed inputs;
the qualification used real authenticated dashboard submissions only. Neither
the passwords nor the preview bearer were written to this repository, the
ledger, the journals, or this record.

The live path has exercised GitHub CI wait, preview acquisition, browser
rejection, both bounded log scans, and explicit preview release repeatedly.
Fieldbook PRs #255, #261, #262, #263, and #264 are all closed unmerged draft
qualification artifacts. Their terminal evidence failures each retained no
evidence pack, reported `matches=0` with a positive sentinel/byte proof on
both scanners, and reported `cleanup_complete=true`.

Live coverage found and repaired the following source-insufficient defects:

- a missing Traefik backend-port declaration and a post-start route readiness
  race; the lease now waits locally and bearer-free for an allowed route;
- an omitted Python `time` import in that readiness retry;
- selector polling that could consume the whole action deadline and be
  misclassified as a timeout;
- a Git `initializing` worktree lock requiring two explicit `--force` flags,
  covered by a real-Git regression test;
- a foreground qualification claim released before run creation, which is now
  recoverable only through the original dashboard request and only when no
  live foreign holder exists;
- legacy PHP seeing the short-lived capability in `Authorization` instead of
  the translated preview authority. Moving the capability into
  `X-Patchyard-Factory-Capability` eliminated that name collision, but review then
  correctly found that the custom header still reached PHP. The edge-strip
  correction in this branch orders a Traefik Headers middleware after
  ForwardAuth, so it authenticates the private header and removes it before
  Fieldbook receives the translated application `Authorization`. Its real
  Traefik integration test is GitHub-hosted CI coverage. Preview convergence
  on 2026-07-25 installed the edge-strip correction and passed the deployed
  label/order qualifier; the remaining live qualification must exercise it on
  a leased Fieldbook route.

The collision and edge-strip fixes are converged on the preview boundary. The
final successful live run is intentionally pending the next UTC daily-claim
window: the predeclared failure-path exercise consumed the approved roster's
existing per-submitter quota. No quota was raised, no request was created
through a console or SQL, and no terminal run was reopened. At the next window
the remaining proof is a fresh dashboard-submitted ALPHABETIZE run reaching
`ready_for_review`, with twelve hashed artifacts, two zero-match scan proofs,
and the full A11/A26 PR body contract, including the leased-route edge-strip
proof.

The first clean-success candidate was submitted through the production
dashboard on 2026-07-26 after that UTC window opened (request
`1f5851fe-3c59-45b0-86f4-32d853dcaf9c`; run
`73da062c-9061-48fb-a98d-7a47e10ea1d3`). It used base
`4ef35181f7a700b02e63808e483d7c23f33b91d8` and published Fieldbook PR #265 at
`b3d3ee547316f4c7d154bd95b408cf110b6f2555`. GitHub CI reached `success`, but
the baseline evidence child then returned `RedirectBlocked`, so the lifecycle
ended `evidence_failed`. It imported no evidence pack. The control-plane scan
reported `sources=1`, `bytes_scanned=1617`, `matches=0`, and
`sentinel_matches=1`; the preview scan reported `sources=2`,
`bytes_scanned=32910`, `matches=0`, and `sentinel_matches=1`. The explicit
slot-15 release reported `cleanup_complete=true` with no cleanup errors.
Neither scanner received nor recorded a bearer value.

The redirect exposed a deployed-boundary gap rather than a bypass: Traefik
had translated the capability and removed the private header, but the preview
Fieldbook image uses Apache's PHP-FPM proxy and did not project the translated
`Authorization` header into legacy PHP's `HTTP_AUTHORIZATION` environment.
`authenticate.php` therefore redirected to its login route, and the isolated
child correctly failed closed. The repair mounts a reviewed Apache
`SetEnvIfNoCase` projection into only factory-leased slots, keeps the ordered
Traefik strip intact, and adds desired-state regression coverage. PR #265 is
retained draft and unmerged as this failed qualification artifact while the
repair is converged and a fresh dashboard request is used for the replacement
success run. No quota was raised and no existing terminal run was reopened.

The replacement form submission exposed a second live-only intake defect. The
production dashboard correctly recognized the exact sanitized ALPHABETIZE
body, but returned the prior terminal failure receipt instead of creating a
new request. The same per-submitter body fingerprint had a durable terminal
row for each approved account from the predeclared failure exercise. The
original global unique fingerprint therefore made a clean retry impossible
without changing the request body, bypassing the form, or mutating a terminal
record. None of those alternatives was used: the dashboard receipt created no
new row, no quota was raised, and no terminal request was reopened.

Migration 9 changes that key to a partial unique index over only `queued`,
`claimed`, and `plan_bin` requests. The intake paths retain live-request
deduplication, while terminal failures remain durable audit records and no
longer suppress a fresh identical dashboard submission. Core and dashboard
PostgreSQL regressions cover both sides of that boundary. After the reviewed
migration and control-plane converge, the clean retry will again use the
production dashboard form and the real `#sales_person_id` selector.
