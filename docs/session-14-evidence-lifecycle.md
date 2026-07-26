# Session 14 evidence lifecycle

Status: failure inventory and verification limits declared before the first
Session 14 implementation PR and before live qualification; clean production
qualification completed on 2026-07-26.

## Decision

The supervisor owns one restart-safe lifecycle after the publisher creates a
draft pull request:

1. It mints a fresh GitHub App token for the Fieldbook repository with exactly
   `contents:read`, `pull_requests:write`, and `checks:read`. That token owns
   observation and PR-body work, not the final ready mutation.
2. It waits for every GitHub check run on the durable PR head to reach
   `success`. An empty check set is a wait state, not success. Every other
   terminal conclusion has its own run state.
3. It leases Session 7's preview slice at the exact baseline SHA, authorizes
   one short-lived evidence capability, runs Session 13's isolated browser,
   re-verifies the SHA, scans control-plane and preview logs for the bearer and
   capability ID, and explicitly releases the lease. The browser supplies the
   capability only to Traefik's forward-auth boundary, which removes the
   private header before legacy PHP receives the translated application
   authority.
4. It repeats that sequence for the exact candidate SHA.
5. Only after each isolated child has ended, the SHA proof and both log scans
   have passed, and the lease has been released does it import the bounded
   child outputs into the private artifact store. Baseline and candidate
   filenames are unique. The artifact ledger carries the SHA-256 for every DOM
   snapshot, screenshot, extracted order, child hash manifest, execution
   manifest, and lifecycle proof.
6. It replaces the pending evidence section in the PR body with authenticated
   dashboard links and each artifact SHA-256, then verifies the full A11 and
   A26 contract as live GitHub state. Only at that final gate does it mint a
   second repository-only token with exactly `contents:write` and
   `pull_requests:write`, the scope GitHub's GraphQL ready-for-review mutation
   requires; that token performs only that mutation. The drafted requester
   reply is body text only and is never sent (A34).

The dashboard remains a read-only scribe (A53/A66). The supervisor performs
every transition and side effect (A65). The orchestration host is absent from
the runtime path (A68). No process self-merges or deploys (A1).

## Preview authorization boundary

The isolated evidence browser sends its short-lived authority only as
`X-Patchyard-Factory-Capability` to the numbered preview origin. Traefik passes that
header to its file-provider `forwardAuth`, whose translator validates the
capability's host, method, expiry, lease, and digest before returning the
preview authority as `X-Patchyard-Factory-Preview-Authorization`. Traefik's
`authResponseHeadersRegex` removes the capability from the forwarded request,
while `authResponseHeaders` copies the returned replacement header into it.
Apache receives that replacement, projects its value byte-for-byte into
ordinary `Authorization` with the `mod_headers` request function, removes the
replacement, and explicitly passes only `Authorization` through the PHP-FPM
CGI boundary. The capability therefore terminates at Traefik and never reaches
Apache, PHP-FPM, or the Fieldbook application.

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
  replacement and no `X-Patchyard-Factory-Capability` header; desired-state tests
  prove Apache projects only that replacement into application
  `Authorization`;
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
- the installed Traefik image is the exact digest exercised by the behavioral
  capability-boundary integration test;
- the deployed Traefik forward-auth boundary authenticates the private
  capability and removes it before the legacy PHP backend;
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
deduplication and exact-ID transport retries, while terminal failures remain
durable audit records and no longer suppress a fresh identical dashboard
submission. Core, property, and dashboard PostgreSQL regressions cover both
sides of that boundary. After the reviewed migration and control-plane
converge, the clean retry will again use the production dashboard form and the
real `#sales_person_id` selector.

The first migration-9 form retry then returned a dashboard `500` without
creating a request. The durable receipt path was intact; the Session 14
converger had installed the new schema but, because it did not carry the
`factory-web` binary, had left the dashboard on the prior partial-conflict SQL.
That old binary correctly failed closed against the replaced global unique
constraint. The converger now builds, hashes, installs, and restarts the
reviewed dashboard binary alongside the qualification binaries, with a static
regression assertion. The failed HTTP attempts created no intake row, did not
consume a claim, and did not alter the request body or terminal records.

The first repair converge exposed one more deployment-boundary omission: those
dashboard-binary tasks were untagged, so the Session 14 tagged play skipped
them even though the converger supplied the reviewed hash. The control role
now includes that complete assertion-and-install chain in `session13`, the
tag inherited by the Session 14 converge path. The regression checks both the
converger handoff and the task tags; the reconverge must prove the installed
binary hash before the final form retry.

That hash-correct retry reached real GitHub CI successfully (Fieldbook PR #266,
head `f89499b115330cab73136f581d1a68affdf209af`) but its baseline child still
failed closed as `RedirectBlocked`. Its control scan reported `sources=1`,
`bytes_scanned=1617`, `matches=0`, and `sentinel_matches=1`; its preview scan
reported `sources=2`, `bytes_scanned=42024`, `matches=0`, and
`sentinel_matches=1`; the slot-15 release was explicit and
`cleanup_complete=true` with no cleanup errors. The failure left no evidence
pack and PR #266 remains draft and unmerged. The cause is the Apache
PHP-FPM boundary: `SetEnvIf` set an Apache request environment variable, but
`mod_proxy_fcgi` creates PHP's CGI environment later. The repair uses
`ProxyFCGISetEnvIf` to project only Traefik's translated `Authorization` into
`HTTP_AUTHORIZATION` at that exact FastCGI boundary. It still never exposes the
factory capability to PHP.

The next dashboard submission was request
`4fed5d04-3350-400c-935e-21e14cd91cab`, run
`e75e2674-3055-4a2e-8904-bad20ef50173`, and Fieldbook PR #267. Its durable base
was `4ef35181f7a700b02e63808e483d7c23f33b91d8` and its exact published head
was `ecca3da7ed0c6f5d8af7176bcfe618d76567fa42`. The one `PHPUnit Tests`
Actions run, ID `30184495693`, observed that exact head and completed
`success` from 02:24:09Z through 02:25:05Z. Baseline capture failed closed as
`RedirectBlocked`, with no imported evidence pack. Its control scan reported
`sources=1`, `bytes_scanned=1617`, `matches=0`, and `sentinel_matches=1`; its
preview scan reported `sources=2`, `bytes_scanned=38516`, `matches=0`, and
`sentinel_matches=1`. Both pre- and post-capture host/preview heads remained
the exact base. The explicit slot-15 release reported `ok=true`,
`already_absent=false`, `cleanup_complete=true`, and no cleanup errors. PR
#267 was closed at 03:27:23Z, still draft and unmerged.

The subsequent live boundary repairs converged the complete Traefik file
provider, middleware order, translated application authority, Apache request
function, and PHP-FPM projection. They also pinned the preview Traefik image to
the exact integration-tested digest, required the concrete composed capability
label, matched Docker's normalization, and gave the translator only the
directory-search capability required to traverse its private state mount. The
deployed qualifiers check those concrete properties rather than their template
source.

The next production-form request was
`ccc89229-a15a-4f3c-bee9-f840c7721fd4`, run
`11ed3eb4-009b-48db-a1bb-fa65ed06db8e`, and Fieldbook PR #268. It used the same
exact base and published head
`ef4d5fad068c99641db7e23d6615223ba92e429a`. Actions run `30186374646`
observed that head and completed `success` from 03:34:11Z through 03:34:53Z.
Baseline capture then rejected the live page as `ContractRejected`
(`document_api_denied_2xx`), so no evidence pack was imported. The control
scan was `sources=1`, `bytes_scanned=1715`, `matches=0`,
`sentinel_matches=1`; the preview scan was `sources=2`,
`bytes_scanned=33659`, `matches=0`, `sentinel_matches=1`. Before and after
host/preview heads all remained the exact base, and the explicit slot-15
release was `ok=true`, `already_absent=false`, `cleanup_complete=true`, with
no cleanup errors. PR #268 was closed at 07:18:34Z, draft and unmerged.

Request `b65a6ab4-67b3-4db7-8890-5c73c35b04ed`, run
`a42094a7-544a-4007-b04a-ddea50516530`, published Fieldbook PR #269 from the
same base at head `1b237e37b733ce65979d1e694c3616d76698bb82`. Actions run
`30190874000` observed that exact head and completed `success` from 06:20:09Z
through 06:20:53Z. The baseline browser returned `BrowserCrashed`; the
lifecycle retained `evidence_failed` and no evidence pack. The control scan
was `sources=1`, `bytes_scanned=1617`, `matches=0`,
`sentinel_matches=1`; the preview scan was `sources=2`,
`bytes_scanned=28785`, `matches=0`, `sentinel_matches=1`. All four before/after
head observations remained the exact base, and the explicit slot-15 release
was `ok=true`, `already_absent=false`, `cleanup_complete=true`, with no cleanup
errors. PR #269 was closed at 07:18:35Z, draft and unmerged.

Those failures exposed several diagnostic ambiguities rather than permission
to relax isolation. The browser and outer helper now preserve safe, named
failure categories; invalid result stages and rejected commands are explicit.
The fixed live mode also made the browser's real, immutable Google Fonts
preconnect and stylesheet dependencies visible. It aborts only those exact
cross-origin presentation requests before transmission and continues the
same-origin evidence operation; every other cross-origin resource still fails
closed. Regressions exercise both sides of that narrow exception. A final
isolated real-page probe then completed with five bound hashes, full isolation,
zero teardown residue, and a clean release before another claim was made.

At 07:15:25Z Jacob's dashboard form created request
`44294b6f-cd40-4d22-bd73-b8d770d66f1e`, but the normal claim path correctly
refused it because five distinct Jacob claim events already fell in the UTC
window. The receipt count had understated that history because one prior form
submission was claimed after midnight. The request created no run or PR and
was explicitly closed through the normal control operation at 07:16:54Z. The
daily cap was not raised; no SQL or console intake was used.

Engineer Two's production form then created request
`58808bf1-cbec-4a1e-a60f-22cf48430acc`, run
`c24adfc9-4b35-45ed-bdd1-75b358f6387d`, and Fieldbook PR #272. The run's exact
base was `4ef35181f7a700b02e63808e483d7c23f33b91d8` and its published head was
`d8b3168b7dc820f8cfb9f4be83c6b31449227f21`. Actions run `30192588149`
observed that head and completed `success` from 07:19:14Z through 07:20:07Z.
An initial open-PR-cap refusal was recovered through that same claimed run
after #268 and #269 were explicitly closed; it did not create replacement
intake or consume another daily claim.

Both #272 evidence captures validated and imported their complete packs. The
baseline hashes were:

- execution `3a03bf358808ee002a9068b37013fb05679cc131410bbacc901b7119d4b08f42`;
- lifecycle `4c92414832a71bede4e244099b7a0f28414271fdadb269decd6674f0b60a7115`;
- hashes `0acf3db9d768ddee4148e910e3fd54012fdebc94a57b50addc642c0ab7a6108c`;
- DOM `93b83873726ad98044c5b5b57aad38d1a660dbfb4980733f53c6c41784847954`;
- screenshot `9e81b0de6b92c71129a907d66186a17cc56a92124f27e0835285082c10e5821d`;
- extract `def4b3bfd30d80056e95b87754b65d16704e8d6df836ef239950287a5b99c801`.

The candidate hashes were:

- execution `7f5035520afd67ee58d8e50d811194ccf147e72fe275875fd36f818efd541075`;
- lifecycle `f8ce8d03df9df1d4206997f88c1f7c8935b98d4c22dac446ef7364e800ce9aa3`;
- hashes `6352bdd0b3f543204d5e6bf9258be1c7b080a2ec51e18ada0424812739d2d3c0`;
- DOM `f151bb2ce32eddb37c05e7dfa1c1f2f7cd07b65df7bb1c491fb2d66d8c7bad52`;
- screenshot `6749ef2b541fe03a7f71598d5a5bd97265516f07fbb646c236c1dceb6b53f902`;
- extract `cfd1a8d4f2af7a753a11dd4221d01e3a865a68dd81228ef5534af839178a1626`.

The baseline control/preview scans were respectively
`sources=1,bytes_scanned=1348,matches=0,sentinel_matches=1` and
`sources=2,bytes_scanned=51118,matches=0,sentinel_matches=1`; the candidate
pair was `sources=1,bytes_scanned=1380,matches=0,sentinel_matches=1` and
`sources=2,bytes_scanned=31600,matches=0,sentinel_matches=1`. Each capture
observed the exact expected host and preview head both before and after. Both
slot-15 releases reported `ok=true`, `already_absent=false`,
`cleanup_complete=true`, and no cleanup errors.

#272's real 7,221-byte body passed the new live A11/A26 contract gate with all
twelve hashes and ten authenticated evidence links. GitHub's GraphQL
ready-for-review mutation then returned status 1 because the lifecycle token's
`contents:read` scope was insufficient for that mutation. The run correctly
ended `pr_contract_failed` with reason `ready_for_review_update`; it did not
mark the PR ready. The repair preserves the original least-privilege lifecycle
token and mints a second repository-only token with exactly `contents:write`
and `pull_requests:write` only after evidence, CI re-observation, and the live
body gate pass. PR #272 was explicitly closed at 07:35:23Z, draft and unmerged,
with its disposition recorded in GitHub comments.

### Clean success

The final, unchanged ALPHABETIZE request was submitted through Engineer Two's
authenticated production dashboard form with the real `#sales_person_id`
selector. Request `6b7c19d7-d272-459c-82d0-fed98df3ff04` was received at
07:38:14.600893Z; run `60a28544-5102-4109-8933-e12b1f03c9bf` queued at
07:38:31.636594Z, started at 07:38:41.366576Z, and finished
`ready_for_review` at 07:43:46.997283Z. It published Fieldbook PR #273 from the
durable exact base `4ef35181f7a700b02e63808e483d7c23f33b91d8` at exact head
`729dad6d3f69d4a482341a5f7edf26fb7ebb7e66`. The target branch advanced after
publication, but the durable run and evidence remain bound to those original
base/head values.

The one real `PHPUnit Tests` Actions run, ID `30193194057`, was created on the
exact head at 07:39:32Z and completed `success` at 07:40:21Z. The supervisor's
fresh GitHub observation persisted `ci.passed` with one exact-head check at
07:40:24.808140Z before acquiring any preview.

The final baseline artifact hashes are:

- execution `3a03bf358808ee002a9068b37013fb05679cc131410bbacc901b7119d4b08f42`;
- lifecycle `06a34d4e2562a17aa28018de23586957631427d2ad7272191619c78a336317fb`;
- hashes `e7946ea608e4da3544a312d18a55e366ee1a65b661e4d2b205fd05b935bde6a6`;
- DOM `93b83873726ad98044c5b5b57aad38d1a660dbfb4980733f53c6c41784847954`;
- screenshot `6749ef2b541fe03a7f71598d5a5bd97265516f07fbb646c236c1dceb6b53f902`;
- extract `def4b3bfd30d80056e95b87754b65d16704e8d6df836ef239950287a5b99c801`.

The final candidate artifact hashes are:

- execution `9f639c3f040eb899ee566a35132df8e4847fad58ddf983de0509a958220f389c`;
- lifecycle `793a7b77391d59ca6a69a0e1cbbed20984588fc176c08a9f1fe67d449695e59e`;
- hashes `ada5a480bf03bd2d3f16db025951c083ac53170471fc20964ad0a77ec1b0ad67`;
- DOM `f151bb2ce32eddb37c05e7dfa1c1f2f7cd07b65df7bb1c491fb2d66d8c7bad52`;
- screenshot `6749ef2b541fe03a7f71598d5a5bd97265516f07fbb646c236c1dceb6b53f902`;
- extract `cfd1a8d4f2af7a753a11dd4221d01e3a865a68dd81228ef5534af839178a1626`.

At 07:42:06.835982Z the baseline security proof reported
`sources=1,bytes_scanned=1348,matches=0,sentinel_matches=1` on the control
plane and `sources=2,bytes_scanned=35050,matches=0,sentinel_matches=1` on the
preview. All before/after host and preview observations were the exact base.
At 07:43:43.616902Z the candidate proof reported
`sources=1,bytes_scanned=1348,matches=0,sentinel_matches=1` and
`sources=2,bytes_scanned=30680,matches=0,sentinel_matches=1`; all four head
observations were the exact candidate. Each slot-15 release reported
`ok=true`, `already_absent=false`, `cleanup_complete=true`, and an empty cleanup
error set. These are two durable pairs of zero-match scans with positive
sentinel and positive-byte proofs, and two explicit clean preview releases.
No lease, capability, checkout, container, network, mount, child unit, or
staging residue remained.

The real PR body passed the production A11/A26 gate, including the lane and
rubric, verbatim untrusted request, root cause, named assumptions,
deterministic facts, ten authenticated evidence links, all twelve hashes,
shared-function explain-diff, risk and rollback, a requester reply explicitly
kept as an unsent draft, and the reviewer quiz. The narrow ready token then
performed only the ready mutation. PR #273 is open, non-draft, and unmerged.
Nothing self-merged or deployed, and no requester reply was sent.

The first authenticated post-run artifact fetch exposed one final live-only
defect: the supervisor service's `UMask=0077` reduced newly created run
directories to `2700` and files to `0600`, so the dashboard returned 500 even
though every artifact remained present with its correct ledger hash. Commit
`9bf6da2` makes every request/run/stage ancestor explicitly setgid `2750` and
every atomically written artifact explicitly `0640`; its regression checks all
three directory levels and the final file. Commit `daaf619` includes the
existing-artifact mode repair in Session 14 convergence. The repair converge
completed with `factory-control: ok=61, changed=7, failed=0` and
`factory-worker: ok=1, changed=0, failed=0`.

After that repair, a fresh authenticated dashboard session fetched all twelve
#273 artifacts through their exact production evidence routes. Every response
remained on the requested URL and all 482,613 served bytes matched the twelve
SHA-256 values above. Passwords, bearer material, capability values, and
sentinel values were not printed or recorded.

The first exact-head repeat then reported two changes despite no source drift:
the recursive checkout ownership task set `/opt/patchyard` to group
`factory-manager`, while the later dashboard-traversal task restored group
`factory`. Commit `3202bec` removes that conflicting recursive group mutation
and adds a desired-state regression. The management identity still owns the
checkout, and the dashboard retains only its intended read-only traversal
through the credential-free root.

### Disposition

Fieldbook PR #273 is deliberately left open, ready for review, non-draft, and
unmerged. It carries the real two-file ALPHABETIZE fix. Jacob decides whether
it is retained as a qualification artifact or reviewed on its merits. The
earlier failed qualification PRs are closed unmerged with explicit
dispositions; no PR was closed silently, and no qualification artifact was
merged or deployed.
