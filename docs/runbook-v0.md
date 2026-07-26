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
| back up | writers quiesce, dump/manifests complete, age ciphertext uploads, remote metadata hash round-trips, `LATEST` advances, prior service state resumes | `backup_failed` or `service_resume_failed` |
| restore | clean host is provisioned, migrations precede data restore, every row/file/hash matches, dashboard starts, historical evidence opens | `restore_failed` or `restore_verification_failed` |
| roll back | merged target with equal migration count converges; installed SHA, services, and health match; durable state is unchanged | `rollback_failed` |
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
sudo /usr/local/libexec/patchyard-deployed-version | jq .
```

`patchyard-deployed-version` must report the protected Fieldbook
`refs/heads/deploy/production` commit. A missing, unreadable, malformed, or
non-commit marker remains fail closed; it is never replaced with a guessed SHA.

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

The management key remains only in client-side-encrypted OpenTofu state. The
control plane receives the separate bucket-scoped object key and only the
public age recipient. It never receives the recovery private key.

After all reviewed plans:

```bash
infra/ansible/converge.sh
infra/ansible/converge.sh
infra/ansible/qualify.sh
```

The second normal converge must show `changed=0` for both durable hosts. A
check-mode difference is drift; inspect and encode the repair rather than
editing the host.

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
jitter. RTO is four hours. Artifact and runtime generations expire off-host
after 90 days; non-current overwritten versions expire after seven days; local
encrypted staging older than seven days is removed. Because a generation
captures the then-live 90-day artifact window, an artifact can remain in an
off-host generation for at most roughly 180 days after creation.

Run an attended backup before a deployment, rollback, restore drill, or durable
control-plane repair:

```bash
sudo systemctl start patchyard-backup.service
sudo systemctl status --no-pager patchyard-backup.service
sudo journalctl -u patchyard-backup.service -n 100 --no-pager
```

The executable contract takes an advisory lock; remembers which writers were
active; stops dashboard and supervisor; rejects non-regular artifact/runtime
entries and unsupported path characters; records exact table counts; creates
a custom data-only `pg_dump` excluding `_sqlx_migrations`; manifests artifacts and the
runtime ideas projection; creates deterministic tar inputs; encrypts the whole
payload to the recovery public key; uploads the ciphertext and receipt over
HTTPS; round-trips its SHA-256 metadata; then advances `LATEST`. A trap resumes
only the writers that were active before the attempt.

The database remains unavailable to writers during the dump. A failed backup
does not advance `LATEST`. Check service state even when the unit fails.

## Restore

The clean-host drill uses a temporary droplet that is reachable only from the
orchestration break-glass address. It is never a production worker and receives
no worker data. The create and destroy are separately planned and reviewed:

```bash
RESTORE_DIR=$(mktemp -d /tmp/patchyard-restore.XXXXXX)
infra/restore-drill.sh plan-create "$RESTORE_DIR"
# Review restore-drill-create.tfplan.txt.
PATCHYARD_RESTORE_APPROVED=yes \
  infra/restore-drill.sh apply-restore \
    "$RESTORE_DIR/restore-drill-create.tfplan" latest

infra/restore-drill.sh plan-destroy "$RESTORE_DIR"
# Review restore-drill-destroy.tfplan.txt.
PATCHYARD_RESTORE_DESTROY_APPROVED=yes \
  infra/restore-drill.sh apply-destroy \
    "$RESTORE_DIR/restore-drill-destroy.tfplan"
```

The restore play provisions Rocky, exact PostgreSQL packages, peer roles,
socket policy, binaries, and migrations from Git before downloading data. It
keeps the supervisor and backup timer disabled, decrypts with an ephemeral
private key, truncates only the new migrated database, restores database,
artifacts, and the runtime ideas projection, reapplies grants, and verifies
every manifest count and digest. It then starts the dashboard only, creates a
drill-only admin after count verification, authenticates through the real
login route, opens one historical run evidence route, and verifies the response
hash. The recovery key and probe password are removed from `/run` afterward.

For actual control-plane loss, first preserve the failed host and its volume.
Create a reviewed replacement resource rather than repointing the production
name by hand, apply the same declarative provisioning, and run the same restore
contract against the selected generation. Only after verification may an
operator plan the DNS/firewall identity move. Never restore into an active
database or a non-empty artifact/runtime target.

## Roll back

Application rollback preserves PostgreSQL, artifacts, backup storage, and
OpenTofu state. The target and actually installed revision must both already be
merged to `origin/master`, and the script refuses a target with a different
migration count:

```bash
ROLLBACK_DIR=$(mktemp -d /tmp/patchyard-rollback.XXXXXX)
infra/rollback-control.sh plan <merged-prior-sha> "$ROLLBACK_DIR"
# Review control-rollback.json and its checksum.
PATCHYARD_ROLLBACK_APPROVED=yes \
  infra/rollback-control.sh apply "$ROLLBACK_DIR/control-rollback.json"
```

The apply refuses a stale plan if the installed revision moved, captures every
database table count plus every artifact/runtime file hash, creates an isolated
worktree at the target commit, converges its binaries, versioned configuration,
and credential-free checkout, then verifies the installed SHA, core health,
and byte-identical durable-state record. It preserves the before/after records
and result JSON next to the reviewed manifest. To roll forward, create and
approve a second manifest targeting the current merged cutover SHA. Schema
rollback is not this operation; it needs a separately ruled migration and
recovery plan.

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
