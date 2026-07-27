# Factory infrastructure operations

The nightloch-style `infra/<provider>` layout encodes the two-host factory
foundation and its PostgreSQL state service. OpenTofu owns cloud resources;
Ansible owns host configuration. No console edit is part of the operating path.

## Layout

| Path | Ownership | Encrypted S3 state key |
| --- | --- | --- |
| `digitalocean/` | two durable droplets, temporary restore-drill host, VPC placement, cloud firewalls, SSH identity, encrypted/versioned Spaces backup bucket, split management/runtime keys, recovery encryption key, inventory outputs | `factory/digitalocean/tofu.tfstate` |
| `aws/` | A96 bucket configuration and IAM adoption, Route 53 lifecycle policy, `factory.example.com` | `factory/aws/tofu.tfstate` |
| `github/` | Factory repository settings and `master` branch protection, plus Fieldbook `deploy/production` marker protection | `factory/github/tofu.tfstate` |
| `ansible/` | both Rocky 9 hosts, bootstrap/break-glass and factory-management identities, host firewall, exporters, control prerequisites, PostgreSQL/roles/migrations, Firecracker parity runtime and worker transient state | n/a |

Each OpenTofu root pins OpenTofu 1.12.0 and its provider, enables native S3
lockfiles without DynamoDB, requests SSE-S3, and enforces PBKDF2/AES-GCM
client-side encryption for both state and saved plans. The passphrase is wired
to the key provider through an ephemeral input variable. It is never written to
source, a variable file, a plan argument, or a backend config file.

The backend access key is deliberately unmanaged. `tofu.sh` maps the injected
backend, provider, and encryption credentials into process environment only.

## First adoption

Preserve the Route 53 identity before the wrapper maps `AWS_*` to the backend
identity, then import the hand-created backend:

```bash
infra/import-a96.sh
infra/import-github.sh
```

The A96 import is intentionally fail-closed unless the provider identity can
read and manage the existing bucket configuration and IAM resources. The first
AWS plan replaces the immutable stale Route 53 policy description with the
correct full-record-lifecycle description using create-before-destroy, moves
the user attachment to the replacement ARN, and only then removes the old
policy. The access key never enters state.

## Plan and apply

Plans are staged because Route 53 consumes the control-plane address created by
the DigitalOcean apply:

```bash
PLAN_DIR=$(mktemp -d /tmp/patchyard-plan.XXXXXX)
infra/plan.sh digitalocean "$PLAN_DIR"
# Human reviews $PLAN_DIR/digitalocean.tfplan.txt.
infra/tofu.sh digitalocean apply "$PLAN_DIR/digitalocean.tfplan"

infra/plan.sh aws "$PLAN_DIR"
# Human reviews $PLAN_DIR/aws.tfplan.txt, including policy replacement + DNS.
infra/tofu.sh aws apply "$PLAN_DIR/aws.tfplan"

infra/plan.sh github "$PLAN_DIR"
# Human reviews $PLAN_DIR/github.tfplan.txt.
infra/tofu.sh github apply "$PLAN_DIR/github.tfplan"

infra/ansible/converge.sh
infra/ansible/converge.sh
infra/ansible/qualify.sh
```

The first converge connects from orchestration with the `conductor` bootstrap
identity. It creates `factory-manager` on both hosts, generates the only private
management key on the control plane, pins both host keys, and opens SSH from the
control plane's private address. Normal host convergence can then run from the
control plane with `/usr/local/sbin/patchyard-converge-hosts`; that path uses
only the private VPC and the credential-free checkout. OpenTofu/cloud changes
remain orchestration-owned and human-reviewed. `conductor` remains authorized
solely for bootstrap and break-glass use.

Cloud-init is a create-time bootstrap input and is ignored for updates after a
droplet exists. New/replacement hosts receive the current template; Ansible owns
the converged identity metadata. This prevents a comment or bootstrap-package
change from silently turning into a host replacement.

DigitalOcean planning fails closed if any live cloud firewall targets a desired
host tag. This prevents a tag-attached firewall's rule union from silently
widening either host before a reviewer sees the resource plan.

The second converge must show `changed=0` on both hosts. `qualify.sh` checks the
installed revision and control prerequisites, PostgreSQL version/socket/TLS,
peer maps, the full runtime grant matrix, the Grafana canary boundary, exporter
bindings/services, the absence of a self-hosted runner and Tempo/OTLP collector,
the worker identity, private-network egress rejection, and standing-credential
paths/patterns.

## Read-only drift check

```bash
infra/plan.sh digitalocean "$PLAN_DIR"
infra/plan.sh aws "$PLAN_DIR"
infra/plan.sh github "$PLAN_DIR"
infra/ansible/converge.sh --check --diff
```

Scheduled drift detection may report; it never remediates automatically.

## Clean worker replacement

The worker stores no durable data. Generate and review the replacement first,
then apply that exact encrypted plan:

```bash
REPLACE_DIR=$(mktemp -d /tmp/patchyard-replace.XXXXXX)
infra/replace-worker.sh plan "$REPLACE_DIR"
# Human reviews $REPLACE_DIR/worker-replacement.tfplan.txt.
PATCHYARD_REPLACE_APPROVED=yes \
  infra/replace-worker.sh apply "$REPLACE_DIR/worker-replacement.tfplan"
```

The script replaces only `digitalocean_droplet.worker`, converges twice, and
runs host qualification, the production Firecracker isolation probe, and
post-probe no-residue qualification. No old worker state is restored.

## Backup and clean-host restore

The executable production paths, RPO/RTO, retention, terminal outcomes, and
separately reviewed clean-host create/destroy drill are in
[`../docs/runbook-v0.md`](../docs/runbook-v0.md). The control plane receives a
bucket-scoped Spaces object key and public age recipient. The full bucket
management key and recovery private key remain only in client-side-encrypted
OpenTofu state.

## Rollback

Create a temporary worktree at the last reviewed commit. Plan each root from
that checkout and review the reverse diff before applying it in the same order.
Then converge Ansible from the old commit's credential-free bundle. OpenTofu
state itself is recoverable from S3 object versions; state rollback is reserved
for state corruption and uses a copied prior object version, never an unreviewed
resource rollback. The control-plane droplet has `prevent_destroy`; application
rollback in later sessions is a binary/config revision, not host replacement.

## Independence and observability handoff

The installed control plane receives a valid Git checkout through a temporary
credential-free bundle. Runtime roles contain no orchestration-host path,
identity, status-dashboard dependency, secret-injection reference, or
orchestration IP. The orchestration public IP and public key appear only in the
bootstrap/break-glass surface. `qualify.sh` temporarily rejects the orchestration
source at the worker host firewall, proves that a fresh break-glass SSH
connection fails, and proves in the same window that `factory-manager` still
qualifies the worker over the private VPC. The timed reject expires after 45
seconds even if the qualification process is interrupted.

Full serve/authenticate/run independence cannot be exercised until the runtime
exists in Sessions 1-14; Session 0 proves the topology and static half without
claiming an end-to-end system early.

Fleet-side Prometheus and Grafana are outside this repository. The handoff is:

- retain the two private-IP file_sd targets per host for `:9100` and `:9187`;
- alert when `patchyard_postgresql_tls_certificate_remaining_seconds` is
  below 30 days or `pg_up` is zero;
- configure the Grafana PostgreSQL datasource at the control-plane private IP
  on `:5432`, database `patchyard`, role `grafana_ro`, TLS verification on,
  with `/etc/patchyard/postgresql-server-ca.crt` as the non-secret trust root.

The cloud and host firewalls accept `:5432` only from the monitoring droplet.
This is a handoff, not a change to the fleet repository. Tempo and an OTLP
collector remain absent.
