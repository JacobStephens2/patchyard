# Factory infrastructure operations

Session 0 encodes the two-host factory foundation with the nightloch-style
`infra/<provider>` layout. OpenTofu owns cloud resources; Ansible owns host
configuration. No console edit is part of the operating path.

## Layout

| Path | Ownership | Encrypted S3 state key |
| --- | --- | --- |
| `digitalocean/` | two droplets, VPC placement, tags, cloud firewalls, SSH public identity, inventory outputs | `factory/digitalocean/tofu.tfstate` |
| `aws/` | A96 bucket configuration and IAM adoption, Route 53 lifecycle policy, `factory.example.com` | `factory/aws/tofu.tfstate` |
| `github/` | repository settings and `master` branch protection | `factory/github/tofu.tfstate` |
| `ansible/` | both Rocky 9 hosts, identities, host firewall, exporters, control prerequisites, worker transient state | n/a |

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

The second converge must show `changed=0` on both hosts. `qualify.sh` checks the
installed revision and control prerequisites, exporter bindings/services, the
absence of a self-hosted runner and Tempo/OTLP collector, the worker identity,
private-network egress rejection, and standing-credential paths/patterns.

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
runs qualification. No old worker state is restored.

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
status-dashboard dependency, secret-injection reference, or orchestration IP.
The orchestration public IP appears only in the bootstrap management firewall.

Full serve/authenticate/run independence cannot be exercised until the runtime
exists in Sessions 1-14; Session 0 proves the topology and static half without
claiming an end-to-end system early.

Fleet-side Prometheus is outside this repository. After the hosts exist, add two
file_sd targets in the observability repository using the OpenTofu private-IP
outputs, scraping `:9100` and `:9187`. This is a handoff, not a Session 0 change
to the fleet repository. Tempo and an OTLP collector remain absent.
