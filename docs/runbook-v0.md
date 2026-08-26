# Patchyard Factory runbook v0

This runbook operates the installed production topology. Every source revision
used below must already be human-reviewed and merged. An operator invokes every
apply, deployment, rollback, kill, and restore step; no scheduler or factory
process may merge or deploy its own output (A1). Host edits are never an
alternative to these paths (A69).

## Safety contract and terminal outcomes

Before any change, capture the current Factory revision, Fieldbook deployed
marker, database row counts, artifact count/bytes, runtime-ideas hash, active
services, and OpenTofu plans in the Session 16 record. Stop on the first
unexplained difference.

| Operation | Success | Named failure |
| --- | --- | --- |
| operate | all expected units, sockets, health endpoints, marker read, and private management probes pass | `operate_health_failed` |
| converge | reviewed cloud plans apply, first Ansible converge succeeds, second reports `changed=0`, qualification passes | `converge_failed` or `converge_not_idempotent` |
| replace worker | exact replacement plan applies; two converges, host qualification, isolation probe, and no-residue probe pass with no restored worker state | `worker_replacement_failed` |
| back up | active work refuses as `backup_busy`; otherwise writers quiesce, dump/manifests complete, age ciphertext uploads, remote metadata hash round-trips, `LATEST` advances, prior service state resumes | `backup_busy`, `backup_failed`, or `service_resume_failed` |
| restore | clean host is provisioned, migrations precede data restore, every row/file/hash matches, dashboard starts, historical evidence opens | `restore_failed` or `restore_verification_failed` |
| roll back | merged target with equal desired and qualified migration pins converges and qualifies, then the reviewed cutover revision reconverges and requalifies; both preserve declared durable state | `rollback_target_refused`, `rollback_busy`, `rollback_failed`, or `rollback_recovery_failed` |
| kill | control row reaches `completed`, child/worker residue is zero, lease is released, run and request terminate as `killed` with an event | `kill_failed` |

Never label a partial operation as success. Preserve its command output and the
last verified state in `docs/session-16-cutover.md` before repairing it.

## Operate

Run read-only status first:

```bash
infra/plan.sh digitalocean "$PLAN_DIR"
infra/plan.sh aws "$PLAN_DIR"
infra/plan.sh github "$PLAN_DIR"
infra/ansible/converge.sh --check --diff
infra/ansible/qualify.sh
```

On the control plane, the expected runtime is:

```bash
sudo systemctl is-active postgresql factory-dashboard factory-supervisor caddy \
  node-exporter postgres-exporter
sudo systemctl is-enabled patchyard-backup.timer
sudo curl --fail --silent \
  --unix-socket /run/patchyard-dashboard/dashboard.sock \
  http://localhost/healthz
sudo -u factory-manager /usr/local/sbin/patchyard-converge-hosts --check
sudo bash -c 'set -a; source /etc/patchyard/deployed-version.env; set +a; exec /usr/local/libexec/patchyard-deployed-version' | jq .
```

The on-host management probe derives its backup bootstrap inputs from the
host-resident `/etc/patchyard/backup.env` (installed by the orchestration
converge) and its reviewed-binary inputs from the installed `/usr/local/bin`
copies. For bootstrap-injected inputs the management path preserves and
verifies, never establishes or redefines: the GitHub App id and installation
id render from `group_vars/all.yml` (identifiers in Git, secrets out), the
App pem is asserted present and intact (regular file, `0440`,
`root:factory-manager`, non-empty) rather than re-copied, and the enabled
dashboard accounts are asserted to equal the Git roster exactly rather than
re-provisioned. The only genuinely bootstrap-injected control-plane inputs
left are the pem and the account passwords - both actual secrets. Converge
therefore fails closed on any out-of-band dashboard account: an identity
added or elevated outside Git stops every converge path until it is either
rostered in `group_vars/all.yml` or disabled with `factoryctl account
disable`.

`patchyard-deployed-version` must report the protected Fieldbook
`refs/heads/deploy/production` commit. A missing, unreadable, malformed, or
non-commit marker remains fail closed; it is never replaced with a guessed SHA.
Compare that SHA to an independent `factory-manager` read of the clean Fieldbook
production checkout. The ongoing marker-advance contract is installed by the
human-merged orchestration PR #5; a deploy is not complete if its read-back
marker update fails.

The marker is a qualification dependency, not merely an observation. A GitHub
API or App outage therefore makes converge and worker replacement fail closed
at qualification even when the local services are healthy. Preserve the local
health evidence and retry qualification after marker authority recovers; never
substitute the checkout SHA for the protected ref.

Qualification also performs a real `head-bucket` against the configured
DigitalOcean Spaces backup bucket. A Spaces endpoint, credential, or bucket
outage therefore fails converge, worker replacement, and rollback-recovery
qualification even when local services and the GitHub marker are healthy.
Preserve the local evidence and retry after that authority recovers; never
waive the off-host backup check.

## Converge

Use only a clean checkout at a merged revision. Create plans with
`infra/plan.sh`, review their plaintext renderings, and apply the exact saved
plans DigitalOcean, AWS, then GitHub. The first Spaces adoption is deliberately
two-stage because Spaces bucket management itself needs a Spaces key:

```bash
# One-time bootstrap, from the reviewed cutover revision.
infra/tofu.sh digitalocean plan \
  -target=digitalocean_spaces_key.backup_management \
  -target=tls_private_key.factory_backup_recovery \
  -out="$PLAN_DIR/backup-bootstrap.tfplan"
infra/tofu.sh digitalocean show -no-color "$PLAN_DIR/backup-bootstrap.tfplan"
infra/tofu.sh digitalocean apply "$PLAN_DIR/backup-bootstrap.tfplan"

# Then generate and review the complete plan before applying it.
infra/plan.sh digitalocean "$PLAN_DIR"
infra/tofu.sh digitalocean apply "$PLAN_DIR/digitalocean.tfplan"
```

The bootstrap management key is an account-wide DigitalOcean Spaces
`fullaccess` key because the provider needs it to create and manage the bucket
itself. The OpenTofu wrapper supplies it to every DigitalOcean provider
invocation after bootstrap. This broad management authority is an accepted
Phase-1 residual risk; it remains only in client-side-encrypted OpenTofu state
and is never installed on either Factory host. The control plane receives the
separate bucket-scoped object key and only the public age recipient. It never
receives the recovery private key.

After all reviewed plans:

```bash
infra/ansible/converge.sh
infra/ansible/converge.sh
infra/ansible/qualify.sh
```

The second normal converge must show `changed=0` for both durable hosts. A
check-mode difference is drift; inspect and encode the repair rather than
editing the host.

Session 13 qualification waits for the two states a working control plane
passes through rather than sampling them once: the supervisor restarting under
a converge handler, and isolated children the supervisor legitimately has in
flight. A converge may therefore pause briefly inside qualification, and a
supervisor that is actively processing work qualifies without draining its
queue. Because the wait is the qualifier's own, a Session 13 qualification
failure is a finding to investigate, never something to re-run past: a failed
child unit, an unrecognized child unit name, or a failed supervisor is refused
immediately, and isolation residue no live child owns fails once the wait
expires.

### A-14 rotation and expiring-dependency inventory

This inventory contains no credential values. Rotation means creating or
updating the credential, updating its stable 1Password reference when needed,
relaunching the orchestration session when the value changed, proving the new
authority, revoking its predecessor, and proving the predecessor fails. A
vault update alone is not a completed rotation.

| Credential | Current authority and dates | Review and rotation proof | Failure surface |
| --- | --- | --- | --- |
| DigitalOcean `conductor-v7`, `op://example-vault/digital-ocean/personal-access-token` | Replaced 2026-07-27; prior 33 scopes plus `spaces_key:create_credentials`, `spaces_key:read`, `spaces_key:delete`, and `account:read`; approximate expiry 2026-09-27. | Review 2026-08-27 and rotate no later than 2026-09-20. Current proof-of-life is HTTP 200 from `/v2/account` plus the reviewed Spaces bootstrap and apply. `conductor-v5` and `conductor-v6` are revoked; the recorded old-token `/v2/spaces/keys` response had the API's unauthorized 404 shape. A 401 from a process launched before replacement means relaunch through `codex-orchestrate`, not scope widening. | Fails mid-converge, not at plan time, when DigitalOcean or Spaces authority is first exercised; source checks do not prove the live credential. |
| GitHub `patchyard-admin-pat`, `op://example-vault/patchyard-github-app/patchyard-admin-pat` | Scope-edited in place 2026-07-27; repository access is exactly `example-org/fieldbook` and `JacobStephens2/patchyard`, with Administration read/write and metadata read, no organization permissions; expires 2026-10-19. | Review 2026-09-19 and rotate no later than 2026-10-12. Current proof-of-life is exact repository/admin visibility plus the reviewed GitHub protection apply. The 2026-07-27 edit retained the same credential, so there is no dead predecessor to test; the next value rotation must revoke the old value and prove an administration read fails before closure. No relaunch was needed for the in-place scope edit. | Fails mid-converge, not at plan time, at the GitHub protection apply; source checks and the earlier provider plans do not prove its live repository administration authority. |
| Anthropic operator admin profile `patchyard-admin` | `user_oauth` profile on the attended operator host at `$ANTHROPIC_CONFIG_DIR/credentials/patchyard-admin.json` (default `~/.config/anthropic`). Scope `org:admin`. Access tokens expire in about eight hours; durability is the refresh token `ant auth print-credentials` uses. Proven 2026-08-18: an access token expired eighteen hours refreshed without a browser, and `GET /v1/organizations/federation_issuers/fdis_01A8wjwFPKfutAGtFN3oqF8J` returned HTTP 200. Not in 1Password. Admin API keys cannot replace it: WIF admin endpoints reject them. A federated `org:admin` token is not this path, because diagnosis must not depend on the federation it inspects. | Re-login with `ant auth login --profile patchyard-admin --scope org:admin --no-browser` when print-credentials cannot refresh. Review whenever an attended federation ticket finds the diagnosis path dead. Current proof-of-life is print-credentials plus the issuer GET in `docs/anthropic-lifecycle.md` § Prove the operator admin profile. | Attended admin tools fail at `ant auth print-credentials` before any provider mutation; federation GETs cost a browser login again and the 2026-08-13 class of breakage stays invisible. |
| Anthropic WIF assertion signing key, `/etc/patchyard/anthropic-wif-signing.pem` | Created on the control plane 2026-07-29; root-only, non-expiring, deliberately absent from backups and every worker; its public JWK is bound to issuer `fdis_01A8wjwFPKfutAGtFN3oqF8J`. | Review before any control-plane replacement or federation issuer change. The source-only attended procedure is `docs/anthropic-lifecycle.md`: stage old+replacement, prove replacement exchange and Models, atomically activate it while both remain trusted, prove the active path, retire old at the provider, then prove a fresh retired-key assertion is denied. The procedure ran on 2026-08-06 under A129's thirteen-event contract and requirement 5 is proven; three rotations were performed that day and the active key is `patchyard-39acdfd2bfc0acb0`. Requirement 1's bootstrap admin tool still rejects JWKS drift. The private key never enters the repository, worker, evidence, or vault. | A clean control-plane replacement generates a different key. `issuer-export-current-jwks` plus overlap staging supplies a reviewed recovery path for a new control plane, but loss of the old private key makes the A113 retired-key denial impossible; recovery restores access but does not qualify rotation. |
| Remi PHP RPM signing key (public trust root) | Full primary fingerprint `B1ABF71E14C9D74897E198A8B19527F1478F8947` in `remi_signing_key_fingerprint`; imported and proven on a clean worker 2026-07-28. | Review before any Remi key or pinned-PHP rotation. Stage the new fingerprint alongside the old one, import and prove the new key with GPG checking enabled, then remove the old key and prove an old-key-signed package is rejected before deleting its fingerprint from desired state. A clean replacement key is not sufficient evidence by itself. | Fails on clean worker provisioning when DNF verifies the pinned PHP RPMs; a one-key edit without the rejection proof can silently widen or replace the trust root. |

Exact upstream package pins also need a durable acquisition path. The mirrored
objects below live outside the `generations/` lifecycle prefix, so backup
retention never expires them. Ansible requests the recorded object version,
checks remote metadata and local byte count/SHA-256, and then installs with RPM
signature verification still enabled.

The current controlled copy shares the versioned `patchyard-backups` bucket
and its bucket-scoped runtime credential with backup/restore. That replaces
EPEL retention risk with a declared coupling: loss of this bucket, its runtime
credential, or Spaces reachability blocks both backup recovery and clean-host
Chromium acquisition. A separate dependency bucket and credential would be the
stronger independence boundary; this PR records rather than conceals the
current trade.

The A-14 installed-environment declarations in `group_vars/all.yml` are the
single source for the Chromium NEVRAs, desired migration count, and exact
Grafana column-grant count. Ansible renders the installed qualifier from those
declarations; the qualifier carries no second per-revision copy and keeps
A112's current-contract checks exact rather than weakening them to ranges.

| Dependency contract | Controlled copy | Review and qualification proof | Failure surface |
| --- | --- | --- | --- |
| Chromium `150.0.7871.181-1.el9.x86_64` plus `chromium-common` at the same version; ChromeDriver is deliberately absent because the evidence child speaks CDP to its one-shot Chromium subprocess and never uses WebDriver. | Private versioned Spaces bucket `patchyard-backups`: `dependencies/epel/9/x86_64/chromium-150.0.7871.181-1.el9.x86_64.rpm` version `9k88XXeRJzRUTRwYOFcTu2ICMqWR3iJ`, SHA-256 `05bda830ab035517ee6388c1a0d963d6de67eadb03c68cdd6ff90e8f888fd086`, 132085705 bytes; matching `chromium-common` object version `Gfh5nef193tTyupbpfhjGMofEJmg0-v`, SHA-256 `b2f46d0d00cb47e4fd6a5b73b7edc02e196feb7d683fbfa5007e0a34cfb45202`, 16974965 bytes. | Review on every browser pin change and monthly with the DigitalOcean credential. Every converge proves the exact remote versions and cached bytes; the installed qualifier proves both RPM NEVRAs and hashes. Re-render `fixtures/visual/chromium-baseline.html` with the evidence harness flags after a browser change and stop on an unexplained DOM or screenshot difference. The `.124` to `.181` recheck is recorded in `fixtures/visual/chromium-baseline.json`: DOM SHA-256 `aa1f5b8b3a43b2ec3fd16d9d86075b51cd28504287b347027b0215c5ab1d5b27` and screenshot SHA-256 `e5f7076666fdd849e0cbb6eb3408605cbe97e14a67d79d042a11561a0db9cc18` were byte-identical. | A missing/deleted object or mismatched metadata fails during converge before Chromium installation. A cached wrong byte fails qualification. EPEL remains a dependency source for ordinary transitive packages, but clean provisioning no longer depends on EPEL retaining these two finite-lived exact NEVRAs. |

## Replace the worker

The worker has no durable state and receives no backup restore:

```bash
REPLACE_DIR=$(mktemp -d /tmp/patchyard-replace.XXXXXX)
infra/replace-worker.sh plan "$REPLACE_DIR"
# Review worker-replacement.tfplan.txt.
PATCHYARD_REPLACE_APPROVED=yes \
  infra/replace-worker.sh apply "$REPLACE_DIR/worker-replacement.tfplan"
```

The apply path creates from OpenTofu, converges from Ansible twice, qualifies
the host, runs the production Firecracker isolation probe, and qualifies zero
residue. Do not copy `/var/lib/patchyard-worker`, snapshots, caches, keys, or
other old-host data to the replacement.

## Back up

RPO is 24 hours; the timer runs daily at 02:20 UTC with up to ten minutes of
jitter. The four-hour RTO is an objective only for the reviewed clean-host
data-restore sequence after replacement compute and the backup-compatible
revision are available. Full control-plane loss - including authoring and
reviewing replacement identity/DNS/firewall desired state - has not been timed
and carries no validated RTO in v0. Artifact and runtime generations expire off-host
after 90 days; non-current overwritten versions under the `generations/`
prefix expire after seven days, while the tiny `LATEST` pointer versions are
conservatively retained; local encrypted staging older than seven days is
removed. Because a generation
captures the then-live 90-day artifact window, an artifact can remain in an
off-host generation for at most roughly 180 days after creation.

Run an attended backup before a deployment, rollback, restore drill, or durable
control-plane repair:

```bash
sudo systemctl start patchyard-backup.service
sudo systemctl status --no-pager patchyard-backup.service
sudo journalctl -u patchyard-backup.service -n 100 --no-pager
sudo bash -c 'set -a; source /etc/patchyard/backup.env; set +a; exec /usr/local/sbin/patchyard-backup --verify-latest'
```

The executable contract first requires live bucket versioning, takes an
advisory lock, and refuses with `backup_busy` when it observes active
production or proposer work. A claim in the narrow interval after the first
check can be interrupted by writer quiescence; the required second check then
returns `backup_busy`, and normal state-derived recovery resumes that work.
It remembers which public and writer services were active; stops Caddy before
dashboard and supervisor so systemd dependency propagation cannot hide Caddy
from the restart set; rejects non-regular artifact/runtime
entries and unsupported path characters; records exact table counts; creates
a custom data-only `pg_dump` excluding `_sqlx_migrations`; manifests artifacts and the
runtime ideas projection; creates deterministic tar inputs; encrypts the whole
payload to the recovery public key; uploads the ciphertext and receipt over
HTTPS; round-trips its SHA-256 metadata; then advances `LATEST`. It rechecks
active work after stopping writers to close the intake/claim race. A trap resumes
only the writers that were active before the attempt.

The database remains unavailable to writers during the dump. A failed backup
does not advance `LATEST`, and its EXIT path removes plaintext dump/tar staging.
Check service state even when the unit fails. The `--verify-latest` path proves
that the remote pointer resolves to a receipt and ciphertext metadata within
the 26-hour operational window; it does not turn the shared bucket writer into
an independent provenance authority.

The control-plane key has DigitalOcean's bucket-scoped Read/Write/Delete
permission because Spaces offers no put-without-delete key. Versioning retains
non-current objects for seven days, but this is recovery from ordinary or
detected destructive writes, not WORM storage. `age` authenticates ciphertext
integrity; it does not prove that a compromised runtime writer did not replace
both ciphertext and receipt. Preserve the accepted receipt/hash in the Session
16 record and inspect versions with the off-host management key after any
suspected compromise.

## Restore

The clean-host drill uses a temporary droplet that is reachable only from the
orchestration break-glass address. It is never a production worker and receives
no worker data. The create and destroy are separately planned and reviewed:

```bash
RESTORE_DIR=$(mktemp -d /tmp/patchyard-restore.XXXXXX)
infra/restore-drill.sh plan-create "$RESTORE_DIR"
# Review restore-drill-create.tfplan.txt.
PATCHYARD_RESTORE_APPROVED=yes \
PATCHYARD_RESTORE_APPROVED_SHA256=REPLACE_WITH_REVIEWED_SHA256 \
  infra/restore-drill.sh apply-restore \
    "$RESTORE_DIR/restore-drill-create.tfplan" latest

infra/restore-drill.sh plan-destroy "$RESTORE_DIR"
# Review restore-drill-destroy.tfplan.txt.
PATCHYARD_RESTORE_DESTROY_APPROVED=yes \
  infra/restore-drill.sh apply-destroy \
    "$RESTORE_DIR/restore-drill-destroy.tfplan"
```

While a restore drill resource exists, an ordinary DigitalOcean plan with the
default `restore_drill_enabled=false` proposes to destroy it. Do not create or
apply routine DigitalOcean plans during the drill; use only the restore
operator's reviewed create and destroy plans until the drill resource is gone.

The restore play provisions Rocky, exact PostgreSQL packages, peer roles,
socket policy, binaries, and migrations from Git before downloading data. It
keeps the supervisor and backup timer disabled, decrypts with an ephemeral
private key, truncates only the new migrated database, restores database,
artifacts, and the runtime ideas projection, reapplies grants, and verifies
every manifest count and digest. It then starts the dashboard only, creates a
drill-only admin after count verification, authenticates through the real
login route, opens one historical run evidence route, and verifies the response
hash. controller-side recovery credentials are passed only through the
attended Ansible process environment, never staged in a controller file or
placed in argv; the recovery key and probe password are removed from the
target's `/run` afterward.
Its first tasks bind the generated drill flag and public IP to the planned
DigitalOcean droplet ID read from the provider metadata endpoint; running the
play against normal production or a caller-spoofed inventory refuses before
roles, services, or data are touched. After restoration it also reruns the A94
Grafana canary-content probe. Re-running the data restore against populated
targets must refuse rather than delete them.

`infra/ansible/restore.yml` is drill-only and refuses a normal production
inventory. For actual control-plane loss, first preserve the failed host and
its volume. The control-plane resource has `prevent_destroy`; create and review
a desired-state replacement plus the later DNS/firewall identity move rather
than repointing or replacing it by hand. Record both review durations; they are
outside v0's unvalidated actual-loss recovery time, not hidden inside the
clean-host four-hour objective. Provision the replacement from the backup manifest's
`source_revision` (or a reviewed revision with exactly the same migration set)
and apply those migrations.
Before invoking the installed restore executable against production paths,
stop `factory-dashboard`, `factory-supervisor`, `patchyard-backup.service`,
and `patchyard-backup.timer`, and independently verify zero active production
and proposer work. The executable repeats those checks before download or data
mutation. Restore the selected generation, verify all manifest counts and
hashes, and only then apply the reviewed identity move. The production
executable accepts and consumes only the exact declarative clean-host baseline:
an empty `artifacts/uploads/` directory and the sole runtime
`docs/ideas.md` file byte-identical to `/opt/patchyard/docs/ideas.md`, plus
zero rows across requests, runs, events, artifacts, PR-state, and leases. The
database baseline is checked after migration compatibility and again
immediately before `TRUNCATE`. Any additional filesystem entry, changed seed,
or durable pipeline row refuses as `restore_target_refused` before database or
filesystem mutation. Never restore over preserved production data.

## Roll back

Application rollback preserves PostgreSQL, artifacts, backup storage, and
OpenTofu state. The target and actually installed revision must both already be
merged to `origin/master`. The script refuses unless each revision's desired
migration count and hard qualification count are present and all four values
agree:

```bash
ROLLBACK_DIR=$(mktemp -d /tmp/patchyard-rollback.XXXXXX)
infra/rollback-control.sh plan <merged-prior-sha> "$ROLLBACK_DIR"
# Review control-rollback.json and its checksum.
PATCHYARD_ROLLBACK_APPROVED=yes \
  infra/rollback-control.sh apply "$ROLLBACK_DIR/control-rollback.json"
```

The apply refuses a stale plan if the installed revision moved, captures every
database table count and deterministic content digest plus every
artifact/runtime file hash, creates an isolated worktree at the target commit,
converges its binaries, versioned configuration, and credential-free checkout,
and runs that revision's host qualification. It then repeats convergence and
qualification at the reviewed return revision before removing the public
boundary. Both installed stages must prove the SHA, core health, and
byte-identical durable-state record outside two declared allowances. An older
target revision may
append its bounded `account.provisioned` audit events during declarative
account convergence; the script permits only that exact action/client class,
records each delta, hashes every audit row without exporting its contents,
proves every prior and target-stage row survives unchanged, and rejects every
other target-stage or recovered audit mutation. Each qualification
also performs one unauthenticated CSP probe that inserts an anti-CSRF login
challenge. The script hashes every challenge row without exporting its
contents, proves every pre-existing and target-stage hash survives unchanged,
and permits at most four new rows through the target stage and eight total
through recovery. It excludes no other login/session table. It preserves the
before/target/recovered stable records and result JSON next to the reviewed
manifest. Schema
rollback is not this operation; it needs a separately ruled migration and
recovery plan.

Base revision `84708ba` and the other pre-cutover revisions are not valid
automatic rollback targets: their desired migration count is 11 while their
host qualifier hard-codes 7, so they would enter the boundary and then fail by
construction. Installed preflight also rejected the initially selected
`7b032c7c7ceb7c427cf5e73c43e2116acaf5614a` anchor: although both migration
counts are 11, it still qualifies Chromium `.124` and 19 Grafana column
privileges, while the installed contract requires `.181` and 20. The earliest
safe Session 16 rollback anchor is merged, installed, and fully qualified PR
#61 revision `02c9e2da1f2ebdd877a5e867351da1f500eeaa45`. Use it or a later
compatible merged revision. A target rejected by this preflight ends as
`rollback_target_refused` before the public boundary or any host mutation.

This exact whole-revision target is the reviewed Session 16 drill contract,
not the permanent incident-rollback design. Two invalidated anchors showed
that a qualifier asserting exact equality against advancing environment
constants makes every earlier whole revision ineligible.

**A112 rules the permanent model.** The infrastructure and qualification
contract is forward-only, and rollback installs an earlier *application*
revision under the *current* contract, never an earlier whole revision.
Environment constants - package NEVRA pins, database grant counts, desired
migration count - belong in the declared A-14 pin inventory that the qualifier
reads, not hard-coded per revision in `qualify-factory-control`. Compatible
qualifier ranges are rejected: a range on a grant count would accept an
over-grant and defeat the least-privilege check it exists to make.

Session 16 may continue to use the whole-revision target above for its
already-declared drill only while the installed return revision predates PR
#63. Its interim preflight compares the exact Chromium pin, Grafana grant
count, desired migration count, and qualifier migration count before any
boundary or host mutation. PR #63 makes the qualifier read those constants
from the inventory, which is a necessary A112 prerequisite but does not itself
provide an application-under-current-contract deployment path. Once an
inventory-backed qualifier is installed, the whole-revision operator refuses
fail closed until that application-only path is separately implemented and
reviewed. It never substitutes compatible ranges. A target failing the interim
compatibility predicate ends as `rollback_target_refused` before the public
boundary or any host mutation.

PR #51 must be merged with a merge commit (the repository's established
practice) or a manual fast-forward that preserves the exact commits, never
GitHub rebase-and-merge or squash. Either rewrite would omit the declared
anchor from `origin/master`, and the operator correctly refuses any target that
is not its ancestor. Before the drill, independently prove
`git merge-base --is-ancestor 7b032c7 origin/master` succeeds.

Before creating or applying the rollback manifest, use the dashboard `Full
stop` and wait until the dashboard shows no active production or proposer run.
The apply verifies those durable facts, then installs a versioned firewalld
boundary that rejects public HTTP/HTTPS while the target and return revisions
run their own Ansible convergence and qualifications. Scheduled backup is
stopped before the boundary preflight and cannot restart inside convergence.
A persistent boundary sentinel plus a versioned systemd condition also refuses
the backup service after a reboot, while leaving the timer enabled so both the
current and rollback-anchor host qualifiers can verify its desired installation.
An already-established HTTP keep-alive can outlive the firewalld transition;
any resulting submission changes the per-table row count/content digest or
artifact hash comparison and strands the operation fail closed as
`rollback_failed` rather than being silently accepted.
This keeps the dashboard and
supervisor processes available for real target-revision qualification without
giving either a writer input. If a target-stage failure occurs, the EXIT trap
retries the reviewed return revision and removes the boundary only after that
revision qualifies; otherwise the public reject and scheduled-backup exclusion remain in force
for explicit recovery. The reboot-durable scheduled-backup exclusion remains
active even if systemd reactivates the enabled timer. After a successful
rollback/recovery drill, use
dashboard `Resume`; the operator script never writes the full-stop state
directly.

Once the reviewed return revision has qualified, the evidence comparison is a
separate fail-closed gate. A row count, deterministic ordered-row digest,
artifact hash, pre-existing challenge mutation, challenge-count bound, or
allowed-audit mismatch keeps the public reject and scheduled-backup exclusion in force
even though the return revision is healthy; the systemd condition continues to
refuse backup service execution after a reboot. Preserve the evidence, investigate,
and use the explicit state-backend-free `release-boundary` path only after
independent verification.

If recovery qualification cannot complete because the GitHub marker API is
unavailable, the safe terminal state intentionally leaves the public reject,
Full stop, and scheduled-backup exclusion in force. Preserve the rollback evidence.
The persistent condition continues to refuse backup service execution after a
reboot even if the enabled timer itself is reactivated.
The automatic rollback/recovery path also depends on the AWS S3 OpenTofu state
backend, DigitalOcean provider authority, and locally available pinned Cargo
inputs. An outage or cold-cache fetch failure in any of those can strand the
same fail-closed boundary. The reviewed rollback manifest therefore freezes
the control-plane host and address before entry; releasing the boundary does
not require OpenTofu state or a provider API.
After independently proving that the reviewed return revision is installed,
its local services and durable state are healthy, marker authority is restored,
and qualification passes, a human operator may explicitly release only the
versioned boundary with:

```bash
PATCHYARD_ROLLBACK_RELEASE_APPROVED=yes \
  infra/rollback-control.sh release-boundary "$ROLLBACK_MANIFEST"
```

Then verify the public health path and use dashboard `Resume`. Do not run this
recovery command merely because the automated trap failed.

`GET /ideas` fails closed with HTTP 500 if the declared runtime projection is
missing or unreadable. It does not render an empty page that could be mistaken
for an intact proposer record.

## Kill and full stop

The dashboard is the operator path. Do not write control rows by hand.

- `Pause` stops new production claims but does not terminate active work.
- `Resume` permits claims again unless full stop remains set.
- `Kill` on a live run requests that exact run’s terminal teardown.
- `Full stop` blocks claims and requests termination of active work.

For an attended kill drill, submit through `/new` under the declared
qualification manifest and budget, wait until the run owns a worker lifecycle,
then use its dashboard `Kill` button. Confirm on the SSE timeline and in the
ledger that the control becomes `completed`, the run and request become
`killed`, the lease is released, and the control event gives the reason. Run
worker and child no-residue qualification afterward. Qualification PRs are
closed unmerged with their recorded disposition. A production cap is never
raised to make room for a qualification (A107/A108).

Use `Full stop` before uncertain external side effects or when multiple active
runs cannot be individually assessed. Recovery from full stop is a deliberate
dashboard `Resume`, after the external facts and ledger have been reconciled.

## Ansible converge and a foreground run

`infra/ansible/converge.sh` refuses before doing anything unless both input
paths are exported. Export them in the same shell as the run:

```bash
export GH_PATCHYARD_APP_PRIVATE_KEY_FILE=/var/lib/conductor/.config/patchyard-converge/github-app-private-key.pem
export FACTORY_DASHBOARD_ACCOUNTS_FILE=/var/lib/conductor/.config/patchyard-converge/dashboard-accounts.json
infra/ansible/converge.sh --check-inputs   # prints converge_inputs_valid
infra/ansible/converge.sh
infra/ansible/qualify.sh
```

Two ordering constraints that are not obvious and each cost a failed run:

**The supervisor must be running when you converge.** The control-plane play
ends with `qualify-factory-session13`, whose first assertion is
`systemctl is-active --quiet factory-supervisor`; `is-active` exits 3 on an
inactive unit. Converging with the unit stopped therefore always fails that
task, and because it aborts the control-plane play the worker play never runs -
so no image is rebuilt and `PLAY RECAP` shows the worker at `changed=0`.

The same qualifier can fail even with the unit enabled: several tasks notify
`Restart factory supervisor`, and the qualification runs about a second after
the last restart with no settle wait. Rapid restart cycling can hit systemd's
start rate limit and leave a multi-second window where the unit is between
stopped and started. If the qualifier fails on a converge that otherwise
reports no other failure, check the unit's state and re-run before treating it
as a real regression.

**The supervisor must be stopped when you run a request in the foreground**, so
the resident daemon cannot claim the row first. `factoryctl pause` does not
substitute: `claim()` rejects a paused claim unless the caller is the Session 14
qualification holder, so a plain `factoryctl run` under a pause fails with
`ClaimingPaused`. Stop the unit instead, and start it again afterwards.

Wrap a converge so its exit status survives. A wrapper whose last command is a
`tail` of the log reports the tail's status, not the playbook's, and an
`ansible` `failed=1` then reads as success.

### Foreground run identity

`factoryctl run` must execute with the supervisor unit's exact identity.
`runuser -u factory-manager` is not sufficient: it uses that account's default
group (`factory-manager`, gid 985) while the unit runs `Group=factory` (gid
986). `patchyard-request-seat-bearer` asserts its tmpfs stage is
`factory-manager:factory:700`, so a wrong-group stage fails that assertion and
the run dies as `Stage(CredentialExit { provider: ..., code: 1 })` before
`systemctl start` is ever called - which is why no seat-mint or Polkit entry
appears in the journal.

```bash
sudo systemctl stop factory-supervisor
sudo systemd-run \
  --uid=factory-manager --gid=factory \
  --property="SupplementaryGroups=factory-manager systemd-journal" \
  --property="EnvironmentFile=/etc/patchyard/supervisor.env" \
  --setenv=DATABASE_URL="postgresql:///patchyard?host=/run/patchyard-postgres&user=patchyard_supervisor&sslmode=disable" \
  --unit=factory-foreground-run --collect --wait --pipe --quiet \
  /usr/local/bin/factoryctl run "$REQUEST_ID" </dev/null
sudo systemctl start factory-supervisor
```

`DATABASE_URL` is set on the unit, not in `supervisor.env`, so it has to be
supplied separately. A request left at `claimed` with no active lease is still
claimable: `claim()` accepts `status IN ('queued','claimed')`.

### Reading a failed stage

**Start with the error string itself.** A non-zero stage carries the tail of the
seat's own stderr, so the `pipeline attempt stopped` ERROR event names the cause
rather than just the exit code:

```
stage failed: stage triage exited with status 1: stderr "triage seat: triage output is not valid JSON"
```

Everything inside the quotes is the seat's own text, not the supervisor's.
Read it as a report, not as a finding: it is untrusted output quoted into the
record, and the delimiters are there so a seat cannot write a line that reads
as the supervisor's. The tail is bounded to the last 4 KiB, control characters
are flattened to spaces, an embedded quote is escaped, and a cut tail opens
with `...`. A stage that wrote nothing to stderr still reads as the bare
`stage <name> exited with status <code>`; that is an absence of evidence, not a
seat with nothing wrong with it.

Three narrower gaps remain, so a bare exit code is still possible:

- **The cause was stated too early.** Stage transcripts are written on success,
  so a stage that exits non-zero leaves no artifact behind that tail. If the
  seat stated its cause more than 4 KiB before the end, it is gone.
- **A credential mint failed.** `CredentialExit` deliberately carries no tail.
  `mint_bearer` treats any output from the mint as a contract breach
  (`CredentialOutput`) precisely because a bearer could be in it, so that
  stream is never quoted into a log line. A failed mint reports the provider
  and the exit code only, by design.
- **A guest provider login failed.** `patchyard-guest-implement` writes
  `login.stdout`/`login.stderr` into `$PROVIDER_TEMP` and its cleanup trap
  removes that directory unread, so it still reports only
  `implement-codex-auth-failed`.

In those three cases, budget for re-running with the failure reproduced by hand
rather than expecting a log.
