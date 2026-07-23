# Session 10 publisher evidence

Session 10 replaces the pre-publish stop with a credentialed, draft-only
publisher on the factory control plane. The worker remains secret-free and
receives an exact-SHA archive with no Git remote. The pipeline accepts its
bounded patch/evidence contract, runs the existing review and verifier gates,
then persists a typed `publish-input` artifact before entering `verified`.
Only the publisher can move the run through `publishing` to
`ready_for_review`.

## Identity and credential boundary

- The preferred `patchyard` GitHub App path is the only configured live
  path. There is no Jacob credential fallback.
- Each token mint sends both the one-repository list and the exact permission
  map. Publication requests `contents:write` and `pull_requests:write`;
  reconciliation requests the read equivalents. The returned repository and
  permission maps must exactly match, apart from GitHub's implicit
  `metadata:read`, and expiry must remain inside the short-lived window.
- The App private key is bootstrap-injected at
  `/etc/patchyard/github-app.pem`. It is read at mint time, never flattened
  into an environment variable. The publisher rejects a symlink, non-file, or
  world-accessible key.
- Git receives the installation token through a fixed askpass helper and a
  cleared subprocess environment. The token is never an argument.
- The commit name, commit noreply address, and PR author are all checked
  against the App bot identity (A45, A62).

## Durable publisher state machine

The global `factory.publisher_leases` row fences one repository's cap check
and PR creation. The phase-one TTL is fixed at one hour; a restart of the same
run can reclaim its exact durable lease identity. No database or Rust lock is
held across Git, GitHub, filesystem, or hashing awaits.

The state machine:

1. Mints a repository- and permission-narrowed token.
2. Looks for an existing PR for the durable branch and validates its draft,
   author, base, head, parent, and result tree.
3. Fetches the base branch into the credentialed bare clone beneath
   `/var/lib/patchyard/worktrees/`.
4. Refuses an unexpected bare remote or a branch that is not owned by the
   request.
5. Checks a fresh, complete GitHub snapshot for at most two open
   factory-authored PRs while holding the publisher lease. A failed, old, or
   page-capped observation fails closed.
6. Applies the digest-checked verified patch at the recorded base SHA in a
   fresh detached worktree, recomputes the result tree hash, commits as the App
   bot, closes the worktree, and pushes the exact commit object.
7. Creates a draft PR and confirms GitHub reports the App bot as author.
8. Completes both durable side-effect rows and then transitions the run to
   `ready_for_review`.

Failed clone fragments and all disposable worktrees have awaited cleanup.
Worker cleanup remains the existing explicit two-host lifecycle; no publisher
worktree or Git credential is placed on the worker or orchestration host
(A68).

## PR-body trust boundary

Request-derived source/body text is bounded, labeled as untrusted, and enclosed
in a dynamically sized code fence. Outside that fence, generated bodies reject
Markdown links/images, HTML anchors/images, HTTP(S), mailto, and common `www`
autolinks. The title contains only the durable request UUID. This applies F7
at the merger-facing boundary.

## Reconcile

`factoryctl reconcile <request-id>` mints a read-only narrowed token, finds the
bot-authored PR by durable branch, and records its GitHub state. Merged runs
count as passing only when a latest review approves the exact head and the
strict deployed-version response matches the merge commit. A merge without
that head approval is durably marked `admin_bypassed=true` and
`passing_run=false`.

The deployed-version source is an argument-vector subprocess with a timeout,
output cap, cleared environment, strict JSON schema, exact repository, and
40-character lowercase Git SHA. Source failure is recorded and returned
fail-closed.

## Qualification

The committed tests cover:

- exact installation-token repository and permission maps, including rejection
  of a broader returned permission;
- F7 request-data fencing and rendered-link/image rejection;
- pre-publish pipeline transition ordering and durable `publish-input`;
- process-death recovery immediately before and after branch push, including
  an unreleased lease, converging to one branch and one PR;
- two concurrent publishes at one remaining cap slot, producing one PR;
- stale GitHub state failing before a push;
- exact bot commit/PR identity and foreign branch rejection paths;
- PostgreSQL publisher-lease fencing;
- strict deployed-version parsing and admin-bypassed merge classification;
- cancellation-safe bounded subprocess behavior and explicit worktree cleanup.

## Escalations

The production deployed-version command is deliberately not configured.
PLAN Session 10 requires reuse of the orchestration status dashboard's existing
deployed-version source, while A68 prohibits every factory runtime dependency
on the orchestration host. The existing source is an in-process
`VersionStore`/direct probe with no factory-safe command or authenticated
interface. Calling it remotely would violate A68; copying its probe logic into
the factory would violate the instruction not to reimplement it.

The adapter and fail-closed behavior are complete and tested, but Jacob must
decide which side of that contradiction governs production wiring. Until then,
`FACTORY_DEPLOYED_VERSION_PROGRAM` remains required for reconcile and unset in
the installed service environment.

## Live checkpoint

The control-plane convergence result, App mint scope, bot-authored Fieldbook
draft URL, author, branch, base/head/tree hashes, and the factory draft PR are
recorded in the Session 10 checkpoint PR.
