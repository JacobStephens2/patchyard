# Session 16 cutover

Status: failure paths, terminal states, verification limits, and live coverage
were declared before the first Session 16 implementation change or cutover
mutation. Jacob gave the A97 hard-checkpoint authorization on 2026-07-26.

## Change boundary

Session 16 turns the installed two-host topology into the phase-1 artifact. It
does not merge a pull request, deploy Fieldbook code, send a requester reply, or
raise a production intake cap. Qualification remains attended and
manifest-bound under A107/A108. Engineer Two is an authorized approver and merger,
and A111 keeps approvals optional: Jacob or Engineer Two may satisfy A1 alone for
any Factory code or policy PR after its required checks and adversarial review.

The cutover owns these production changes:

1. converge the control plane and disposable worker from the reviewed commit;
2. restrict protected Factory `master` updates to Jacob or Engineer Two while
   leaving required approvals at zero under A111; one authorized human may
   merge code or proposer-authored policy, while the Factory App cannot merge;
3. install the control-plane-local Fieldbook deploy marker source and protect
   `refs/heads/deploy/production` without depending on orchestration;
4. expose the runtime proposer inbox at admin-only, read-only `GET /ideas`
   through the existing untrusted-markdown filter;
5. migrate or remove remaining orchestration-side factory records while
   retaining only explicit pointers;
6. install and operate runbook v0: operate, converge, replace, back up,
   restore, roll back, and kill; and
7. execute the installed intake, replacement, backup/restore, rollback, kill,
   and post-cutover smoke paths rather than accepting source descriptions.

The Fieldbook deployment marker is not complete until the companion
orchestration change in
[orchestration PR #5](https://github.com/example-org/orchestration/pull/5)
is human-reviewed, merged, and installed. That pointer-only repository change
advances the marker only after a successful production deploy and verifies the
read-back SHA. Session 16 does not merge or install it for the human operator.

### A103 executable namespace mapping

A103 names the conceptual marker as `refs/deploy/production`. GitHub repository
rules cannot protect that custom ref namespace, so the executable implementation
uses the protectable branch `refs/heads/deploy/production` (branch pattern
`deploy/production`). Every Factory reader, orchestration writer, OpenTofu rule,
runbook command, and cutover check names that exact branch; no parallel
unprotected `refs/deploy/production` ref is created. This is an intentional
platform mapping from the ruling's wording, recorded here rather than silently
discovered after cutover.

Factory PR #51 must preserve its commits through the normal merge-commit path,
not GitHub rebase-and-merge or squash. A manual fast-forward that preserves the
exact objects is also valid. The rollback drill's exact target is the intermediate
reviewed anchor `7b032c7c7ceb7c427cf5e73c43e2116acaf5614a`; automatic rollback
requires that object to be an ancestor of merged `origin/master`.

## Before-state inventory

The read-only preflight on 2026-07-26 observed:

- desired source `84708ba8a1e0c6786a9b934f110a5f6b8adfde3b` and installed control-plane
  source `8832cd420d492f81c09c97362497d0d5115eee36`;
- active dashboard, supervisor, Caddy, PostgreSQL, node exporter, and Postgres
  exporter on `factory-control.example.com`;
- active worker egress enforcement and node exporter on
  `factory-worker.example.com`;
- 9 applied migrations, 28 requests, 27 runs, 1,198 events, 23 PR-state rows,
  3 control rows, and 475 artifact ledger rows;
- 516 artifact-tree files totaling 1,592,485 bytes;
- 0 spool files - PostgreSQL requests are the durable spool, while the spool
  directory is upload staging only;
- the real clean Fieldbook deployment at
  `ad636c21847b8f2488bfb0479f8d3ade43f9b5a7`, while
  `refs/heads/deploy/production` did not exist and the installed reconcile source
  was the explicit fail-closed stub;
- the live Factory `master` protection rule at zero required approvals;
- one orchestration-side pointer file, zero orchestration-side processed-ruling
  records, and zero factory runtime-ledger files in the tracked pointer tree;
  the factory repository carries both processed rulings; and
- unexpected runtime GitHub CLI state at `/opt/patchyard/.local/` inside the
  credential-free checkout. Runtime state must move under the declared private
  state root; it must not remain an untracked checkout artifact.

The counts above are evidence inputs, not postconditions. The restore drill
must compare against a fresh backup manifest captured at drill time so that
legitimate attended cutover events are not mistaken for drift.

## Execution record - 2026-07-27

Current terminal state: `converge_failed`. The installed cutover revision is
healthy and idempotent, but its committed host qualifier found that the idle
supervisor's Prometheus endpoint returned HTTP 200 with an empty body after the
required restart. The remaining live drills are paused at that boundary. No
Session 17 behavioral acceptance case has started.

| Step | Actual result |
| --- | --- |
| Credential preflight | `DO_API_TOKEN` and `GH_FACTORY_ADMIN_PAT` were nonempty without printing either value. The current DigitalOcean token returned HTTP 200 for the active account. |
| Selected source | Factory PR #51 merged as `ed15a6d6d0065b31a3c0ecebbdd41109d233f463`. Both GitHub CI workflows passed at that SHA. Fresh application, infrastructure, and Ansible source checks also passed. Jacob then merged installed-qualification repair PR #54 as `a54627ee9f585a792a2ac1524ae877ac06b3e375` and Grafana grant-count repair PR #55 as `6f6a149fa13ef6f6ea06d309aece29f594d493cd`; both workflows passed for each repair. |
| Infrastructure | The reviewed bootstrap created only the Spaces management key. The complete DigitalOcean plan created only the private, versioned backup bucket and bucket-scoped runtime key; AWS changed nothing; GitHub updated Factory protection and created Fieldbook deploy-marker protection. Every saved plan applied with zero destroys. |
| Deploy marker | Jacob's existing GitHub identity created protected `refs/heads/deploy/production` at independently observed Fieldbook production SHA `ad636c21847b8f2488bfb0479f8d3ade43f9b5a7`. The installed reader returned that exact commit, and invalid App identity inputs failed closed with exit 22. Jacob merged orchestration PR #5 as `a5b681d86982e618ee292e8c0b9d390b7a06ab13`, then explicitly authorized its installation. The live checkout was fast-forwarded to that exact SHA without touching unrelated worktree changes; the full Ansible path installed the fixed repair wrapper and both reviewed sudoers policies with zero failures; Ansible restarted the dashboard at 2026-07-27 17:54:08 UTC; local health returned `ok`; both sudoers files parsed cleanly; and the no-argument repair wrapper independently resolved production and returned `marker already at ad636c21847b8f2488bfb0479f8d3ade43f9b5a7`. Ongoing marker advancement is installed. |
| First converge | Control plane: `ok=212 changed=37 failed=0 unreachable=0`. Worker: `ok=82 changed=1 failed=0 unreachable=0`. |
| Installed state | `/opt/patchyard` is clean at `6f6a149fa13ef6f6ea06d309aece29f594d493cd`; the undeclared `.local` tree is absent; 11 migrations are applied; dashboard, supervisor, Caddy, PostgreSQL, and both exporters are active; the backup timer is enabled and active; dashboard health is `ok`. The repaired `/etc/patchyard/backup.env` sources successfully and the live Spaces `head-bucket` check passes. |
| Second converge | Control plane: `ok=204 changed=0 failed=0 unreachable=0`. Worker: `ok=82 changed=0 failed=0 unreachable=0`. |
| PR #54 repair converge | First repair pass: control plane `ok=209 changed=8 failed=0 unreachable=0`; worker `ok=82 changed=0 failed=0 unreachable=0`. Second full pass: control plane `ok=204 changed=0 failed=0 unreachable=0`; worker `ok=82 changed=0 failed=0 unreachable=0`. |
| PR #55 repair converge | First repair pass: control plane `ok=209 changed=6 failed=0 unreachable=0`; worker `ok=82 changed=0 failed=0 unreachable=0`. Second full pass: control plane `ok=204 changed=0 failed=0 unreachable=0`; worker `ok=82 changed=0 failed=0 unreachable=0`. |
| Installed qualification | PR #54 cleared the child-unit and backup-environment defects. PR #55 cleared the exact Grafana grant-count assertion: the live role has the declared 20 column privileges and remains denied raw request bodies and artifact paths. The next exact installed run passed TLS, `pg_up`, and node-exporter checks, then found an HTTP 200 but empty supervisor metrics body immediately after converge restarted the service. `metrics-exporter-prometheus` stores `describe_counter!` metadata but renders no family until a series is registered, so a behavioral run would have warmed `factory_runs_total`; none was started. The repair instead declares and sets an unlabeled `factory_supervisor_up` gauge at startup and qualifies that truthful idle-process signal. No host, database, or runtime counter was edited to bypass the failure. |

The frozen Session 17 manifest in draft Factory PR #53 at
`914d90a052b70600eece39afbf8042a270b9865c` is superseded and has not been
executed. Its replacement must derive the installed revision from the observed
11-migration state, carry a provider-by-provider A-5 capability matrix, require
at least two qualified providers before A77 places implementation and review
in different families, and price the actual subcase and seat-call graph rather
than multiplying 21 top-level repetitions. Until that replacement is reviewed
and at least two providers qualify, acceptance remains paused.

## Failure-path inventory

Every Session 16 operator record ends in one of the named states below. A
failure state preserves the last verified production revision or invokes the
reviewed rollback path; it never improvises a host edit. Secret values, request
bodies, session cookies, preview capabilities, and backup credentials are not
recorded.

| Terminal state | Terminal condition |
| --- | --- |
| `cutover_complete` | Every required installed drill and final smoke passed, and the evidence record was closed. |
| `preflight_failed` | Identity, revision, service, capacity, secret-reference, clean-tree, or maintenance-window checks failed before mutation. |
| `source_verification_failed` | CI/source checks failed or the reviewed commit was not the exact commit selected for converge. |
| `infrastructure_plan_failed` | An OpenTofu plan failed, widened an undeclared surface, or did not match the reviewed target set. |
| `deploy_marker_failed` | The marker was absent, malformed, stale, could not be moved to the independently observed production SHA, or failed read-back verification. |
| `deploy_marker_protection_failed` | The marker could be deleted or changed by an unauthorized path after desired state was applied. Verified rollback force-moves remain limited to Jacob and Engineer Two. |
| `converge_failed` | Either host failed desired-state application, migration, binary/hash assertion, service restart, or host qualification. |
| `converge_non_idempotent` | The immediate second converge reported an unexplained change. |
| `remnant_migration_failed` | Before/after counts did not balance, a canonical record was missing, or the orchestration tree retained non-pointer factory state. |
| `intake_failed` | A real authenticated form submission did not create exactly one durable request and receipt. |
| `spool_identity_failed` | The supervisor did not consume the exact request ID and hash written by the dashboard, or another intake path was used. |
| `qualification_budget_failed` | An attended qualification exceeded or bypassed its digest-pinned request/run/wall-time budget or the separately enforced provider seat-call and two-open-PR ceilings. |
| `reconcile_failed_closed` | GitHub or the deploy-marker source was unavailable/invalid; the run remained pending with the bounded failure recorded. |
| `reconcile_projection_failed` | A real marker SHA was observed but reconcile persisted a different repository, SHA, source, or state. |
| `replacement_failed` | Worker replacement, second converge, isolation probe, or no-residue check failed; no old worker data is restored. |
| `backup_busy` | The attended or scheduled backup observed active work before quiescence, or caught a claim in the stop-window recheck; state-derived recovery resumes any transiently interrupted claim. |
| `backup_failed` | Bucket versioning, quiescence, `pg_dump`, artifact manifest, row-count manifest, encryption, or off-host upload failed. |
| `backup_verification_failed` | `LATEST`, its receipt, ciphertext metadata, age, download, decryption, or payload hashes did not agree. |
| `restore_target_refused` | The drill target binding was absent, artifact/runtime roots differed from the exact declarative clean-host baseline, or requests/runs/events/artifacts/PR-state/leases were nonempty. No restore mutation began. |
| `restore_provision_failed` | Declarative PostgreSQL/role or clean restore-root provisioning failed. |
| `restore_migration_failed` | Migrations did not reapply from the reviewed checkout before data restore. |
| `restore_data_failed` | The dump did not restore cleanly into the drill database. |
| `restore_artifact_failed` | The artifact archive did not restore into the clean drill root. |
| `restore_verification_failed` | Restored row counts, artifact membership/hashes, grants, or a historical evidence fetch differed from the backup manifest. |
| `rollback_target_refused` | The target was unmerged, stale, or its desired and qualification migration pins did not exactly match the installed return revision; no boundary or host mutation began. |
| `rollback_failed` | The reviewed previous revision could not be reinstalled, qualified, and served with equal per-table row counts/content digests and artifact hashes outside bounded declarative-account audits and bounded qualifier-created login challenges; an evidence mismatch keeps the public boundary and reboot-durable backup exclusion in force for explicit release. |
| `rollback_busy` | Dashboard Full stop was not durably active or a production/proposer run was still active before the public-write boundary. |
| `rollback_recovery_failed` | Reapplying the cutover revision after rollback did not converge and requalify cleanly. |
| `kill_failed` | A dashboard-issued control did not terminate the target work, release its lease, append `killed`, appear over SSE, or leave zero worker/child residue. |
| `proposer_live_check_failed` | Installed reporting, runtime ideas projection, bounded child, publication cap, cancellation/restart, or residue checks differed from the Session 15 contract. |
| `smoke_failed` | Any final health, auth, projection, service, revision, drift, or independence assertion failed. |

Failures that occur after a durable pipeline transition retain that pipeline or
proposer terminal state as well as the cutover terminal above. Session 13's
S13-N01 through S13-N12, Session 14's S14-N01 through S14-N17, and Session
15's proposer terminal inventory remain unchanged rather than being collapsed
into a generic cutover error.

## Verification limits

GitHub-hosted CI and local source checks can prove:

- the application state machine and dashboard behavior against disposable
  PostgreSQL, including A110's role matrix and hostile-content filter;
- ShellCheck, Ansible lint/syntax, and static cutover contracts cover the
  versioned quiescence, manifest, path/type, encryption, hash/count,
  clean-host, rollback, and terminal-state shape;
- OpenTofu formatting and schema validation succeed without live authority;
- `GET /ideas` is admin-only, read-only, runtime-backed, raw-HTML-free,
  image-free, and restricted to safe link schemes through the same filter as
  `/decisions`;
- A111 keeps required approvals at zero, one authorized human merge satisfies
  A1 for code and proposer-authored policy, the Factory App has no merge API,
  and protected `master` allows only Jacob or Engineer Two to push; policy PRs
  still require cross-family adversarial review before that human merge;
  and
- the complete application gate still passes formatting, clippy, tests,
  deterministic replay, release reproducibility, audit, deny, vet, model, and
  projection checks.

Those checks cannot prove:

- the real systemd, SELinux, filesystem, Caddy, PostgreSQL peer map, GitHub App,
  GitHub ref protection, private VPC, firewall, S3, Firecracker/KVM, or worker
  replacement behavior;
- the backup and restore programs reject every corrupt-object variant against
  the actual `age`, GNU tar, AWS CLI, and PostgreSQL versions;
- the deploy-marker HTTP response parser sees GitHub's real response shape and
  fails closed on real API/authority errors;
- a human browser can authenticate, submit the production form, receive the
  receipt, and observe the same durable request the supervisor claims;
- the real Fieldbook deployment SHA is projected through the protected marker;
- the installed proposer/report path and runtime ideas ownership;
- a backup generation survives download into a clean restore root and restores
  row counts plus every artifact hash;
- rollback actually serves and then returns to the cutover revision;
- kill latency, SSE delivery, lease release, and residue cleanup; or
- A68 independence while the orchestration host is unavailable.

Only installed evidence may close those items. A fixture pass is never labeled
as installed proof.

Because the protected marker is a qualification dependency, a real GitHub API
or App outage also prevents installed converge, worker replacement, and
rollback recovery from qualifying. The same is true of the real DigitalOcean
Spaces `head-bucket` qualification check: endpoint, credential, or bucket
unavailability fails closed even when local services are healthy. Automatic
rollback/recovery additionally
depends on the AWS S3 OpenTofu state backend, DigitalOcean authority, and the
pinned Cargo inputs being locally available or fetchable. CI can prove only
the fail-closed behavior and the manifest-bound, state-backend-free boundary
release path, not availability of those external authorities. The live drill
must exercise that release path with the state backend deliberately unavailable.

## Deliberate live coverage

The live sequence is ordered to keep a known recoverable checkpoint before
each destructive or externally visible step:

1. capture exact Git, cloud, service, database, artifact, GitHub, and
   orchestration-remnant before-state; verify disk headroom and no active work;
2. run all source checks with the PostgreSQL-backed suite explicitly active,
   review all three OpenTofu plans, and apply no plan whose target set differs
   from its declaration;
3. apply GitOps protection that restricts both creation and updates, then have
   a named operator create `refs/heads/deploy/production` at the independently
   observed clean production SHA; exercise both valid and
   fail-closed observations, and require the companion orchestration deploy
   flow before declaring ongoing marker advancement installed;
4. converge the cutover commit, apply migrations, qualify both hosts, repeat
   converge for `changed=0`, and verify installed binary and checkout hashes;
5. use a real authenticated dashboard session to submit the committed
   qualification request, then correlate form receipt, request row, claim
   event, run row, and supervisor journal by the same IDs and hashes;
6. exercise Session 15's installed read-only report and runtime ideas
   projection, then only the provider-free/operator cases permitted by the
   still-declared seat boundary; the schedule remains disabled unless the
   complete live-provider isolation matrix passes;
7. run the worker replacement from a reviewed `-replace` plan, restore no
   worker data, converge twice, run the production isolation probe, and prove
   zero residue;
8. prove `backup_busy` without interrupting a bounded active qualification,
   then quiesce writers, create `pg_dump` plus row-count and artifact manifests,
   upload the encrypted generation off-host, redownload it, verify its hashes,
   require live bucket versioning, and exercise the remote `LATEST`
   age/receipt check;
9. bind a generated inventory to the planned droplet's provider metadata ID,
   provision a clean drill PostgreSQL/role boundary and clean artifact root
   from desired state, reapply migrations, restore the dump and archive,
   compare every row count and artifact hash, rerun the Grafana content canary,
   start the drill application, fetch one historical evidence object through
   its authenticated route, and prove a populated/wrong-inventory restore is
   refused before mutation;
10. use dashboard Full stop and wait for zero active work; enter the versioned
    public-write rollback boundary, install the declared compatible Session 16
    rollback anchor `7b032c7c7ceb7c427cf5e73c43e2116acaf5614a` after it is
    human-reviewed and merged (pre-cutover `84708ba` is structurally ineligible
    because its desired migration count is 11 but its qualifier pins 7),
    application/config revision, qualify and smoke it without reversing
    append-only migrations, then reinstall the cutover revision, repeat
    qualification, remove the boundary, and use dashboard Resume;
11. start a bounded attended qualification run through the form and issue its
    admin kill through the dashboard; observe SSE `killed`, process teardown,
    lease release, and zero residue; and
12. run final public/authenticated health, projections, intake readiness,
    services, revision, drift, remote `LATEST`, backup-age, deploy-marker equal
    to the independently observed live Fieldbook SHA, metrics, and A68
    independence smoke before recording `cutover_complete`.

Qualification PRs, if any, are closed unmerged with an explicit disposition.
No production cap is raised. The future first genuine Jacob request remains a
production form submission and requires no console fallback.

## Recovery objectives

Phase-1 runbook v0 declares an RPO of 24 hours. Its four-hour RTO objective is
limited to the drilled clean-host data restore after replacement compute and a
backup-compatible revision are available. End-to-end actual-loss replacement,
identity move, and review time remains unvalidated and is not claimed as an RTO.
A backup is accepted only after off-host verification. Expired artifacts disappear from
new generations after the normal retention sweep; older versioned generations
age out under the separately declared backup lifecycle, so an artifact is
never deleted from the only remaining restorable generation.

### Accepted backup-storage trust limit

The bucket-scoped runtime key necessarily has DigitalOcean's combined
Read/Write/Delete object permission: Spaces does not expose a write-without-
delete access level, and its documented S3 compatibility surface does not
offer bucket Object Lock/retention configuration. Versioning therefore gives a
seven-day recovery window for overwritten/deleted current objects, not WORM
immutability. `age` authenticates ciphertext integrity to the recovery key,
but the receipt and ciphertext are written by the same runtime authority; a
control-plane compromise can replace both by encrypting a new payload to the
public recipient. The management key and private recovery identity remain off
host, each accepted generation's receipt/hash is copied into the human cutover
record, and restore operators inspect object versions with management custody
when compromise is suspected. This is a named Phase-1 residual risk, not an
immutability claim. DigitalOcean's current capability references are the
[Spaces permission matrix](https://docs.digitalocean.com/reference/api/spaces/)
and [S3 compatibility table](https://docs.digitalocean.com/products/spaces/reference/s3-compatibility/).

The separate bootstrap/management Spaces key is broader: DigitalOcean issues
it as account-wide `fullaccess`, and the provider wrapper supplies it during
all Spaces-capable DigitalOcean plans. It is retained only in encrypted
OpenTofu state and never installed on a Factory host, but compromise of the
orchestration authority could affect other Spaces resources in the account.
That bootstrap/provider breadth is also an accepted Phase-1 residual risk.

Worker recovery has no RPO because the worker contains no durable data. Its
recovery source is the reviewed OpenTofu + Ansible revision, the parity image,
and the redacted snapshot artifact supplied anew.
