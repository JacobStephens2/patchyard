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
   capability ID, and explicitly releases the lease.
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

## Durable and cancellation semantics

`awaiting_ci`, `capturing_evidence`, and `finalizing_pr` are resumable durable
states. CI success, each evidence pack, the final body update, and the
ready-for-review mutation have idempotent side-effect rows. Recovery accepts
an evidence pack only when all six kinds are present as bounded regular files
and every stored digest still matches.

No Rust or database lock is held across GitHub, SSH, preview, browser, log
scan, or filesystem awaits. Caller cancellation before bearer issuance leaves
the durable stage resumable. Once a bearer exists, the supervisor uses a
fresh teardown token for the post-capture SHA check and both log scans; the
outer preview lease release also uses a fresh token. Cleanup is an explicit
checked close, never `Drop`. A cleanup error overrides success and every other
operation result.

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
- CI wait timeout and malformed/wrong-head snapshots fail closed;
- success and injected evidence failure both call explicit lease release;
- cleanup failure overrides both successful and failed capture;
- child output is not imported before child teardown, post-capture SHA proof,
  zero-match log scans, and lease release;
- partial, symlinked, oversized, or digest-changed recovery packs are rejected;
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
`/usr/local/sbin/patchyard-stage-session14-qualification`. It accepts only a
queued request whose source is an enabled dashboard account, stops the resident
dry-run supervisor, runs `factoryctl run` through the production pipeline, and
restores the resident supervisor on every exit. The form remains the only
intake. The operator never creates or edits a request.

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

The full failure and success runs are blocked at the intentionally fail-closed
form gate. Production currently has zero `factory.users`,
`factory-dashboard.service` is absent, and
`https://factory.example.com` refuses connections. Session 11's open A69
escalation deliberately left `factory_dashboard_account_identities` empty
until the two admin identities and one bare submitter are ruled. A66 forbids
substituting `factoryctl request new`, raw SQL, or another intake path. Once
that roster is named and converged, the two form submissions above are the
only remaining live steps.
