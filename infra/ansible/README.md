# Factory host desired state

Ansible initializes both Rocky Linux 9 hosts. `inventory/tofu.sh` reads the
DigitalOcean outputs directly, so no address is transcribed by hand.

Sessions 0-4 own:

- the `conductor` bootstrap/break-glass identity, retained on both hosts but
  excluded from every runtime role;
- the `factory-manager` identity, whose private key exists only on the control
  plane and manages both hosts over their private VPC addresses;
- pinned node_exporter and postgres_exporter binaries on both hosts, bound to
  private addresses and scrapeable only by `10.132.0.14/32`;
- the control-plane prerequisites (Caddy binary, Chromium, and an exact Git
  checkout transferred as a credential-free bundle);
- the `factory` group, no-login `factory-web` service identity, and asserted
  `/var/lib/patchyard/{artifacts,spool,worktrees}` ownership/modes;
- the unprivileged `factory-worker` identity, transient paths, cleanup, and a
  host-level block on new private-network egress;
- journald retention and hardened exporter services.
- PostgreSQL 16.14 on the control plane with restricted peer-only application
  socket access, declarative service roles, SQLx migrations, and the one
  TLS/private-VPC `grafana_ro` listener;
- a daily node_exporter textfile metric for PostgreSQL certificate expiry. The
  non-secret trust root is `/etc/patchyard/postgresql-server-ca.crt`.
- Firecracker 1.15.1, the reproducible production-parity guest image, the
  fail-static redacted snapshot pipeline, and the bounded inter-host worker
  launchers described in `../../docs/session-4-worker-runtime.md`;
- an hourly parity-snapshot freshness metric. The fleet alert rule remains an
  external Prometheus/Grafana handoff.

It deliberately installs no self-hosted Actions runner or Tempo/OTLP collector.
Session 3 selected Firecracker; Session 4 owns its production installation and
runtime contract.

## Dashboard account bootstrap

`factory_dashboard_account_identities` in `group_vars/all.yml` is the
Git-controlled A69 roster. The Session 14 adversarial review ruled Jacob
Stephens and Engineer Two as `factory_admin`, and the Owner as the
bare `factory_submit` identity.

`converge.sh` requires
`FACTORY_DASHBOARD_ACCOUNTS_FILE` to name a controller-local JSON file readable
only by its owner. The file adds one password to each exact committed identity;
it is secret input, never copied to the control plane or committed:

```json
[
  {
    "username": "owner@example.com",
    "display_name": "Owner",
    "role": "factory_admin",
    "password": "replace-with-a-vault-generated-secret"
  },
  {
    "username": "engineer@example.com",
    "display_name": "Engineer",
    "role": "factory_admin",
    "password": "replace-with-a-vault-generated-secret"
  },
  {
    "username": "submitter@example.com",
    "display_name": "Submitter",
    "role": "factory_submit",
    "password": "replace-with-a-vault-generated-secret"
  }
]
```

Provisioning hashes new passwords with Argon2id over stdin. Later converges
update names and roles without replacing existing passwords. Operators use
`factoryctl account disable`, `enable`, or `reset-password`; disable and reset
revoke every server-side session for that account.

## Controller setup

The committed pins support Rocky's Python 3.9 controller:

```bash
python3 -m venv .venv
.venv/bin/pip install -r infra/ansible/requirements.txt
.venv/bin/ansible-galaxy collection install -r infra/ansible/requirements.yml
```

## Converge and check

From a committed revision, after the DigitalOcean apply:

```bash
infra/ansible/converge.sh
infra/ansible/converge.sh --check
infra/ansible/converge-session13.sh
infra/ansible/converge-preview.sh
infra/ansible/qualify.sh
```

`converge.sh` creates a temporary Git bundle, builds `factoryctl` from the
locked revision, hashes both inputs, passes them to Ansible, and removes the
bundle. No GitHub credential reaches either host. A second normal converge must
end with `changed=0` for both hosts. `qualify.sh` asserts the control-plane and
worker identity contracts, PostgreSQL exposure and peer maps, the complete
runtime grant matrix, the Grafana canary boundary, and every factory
state-directory owner, group, and mode. It also proves A101 live: while a timed
worker rule rejects orchestration, the control-plane identity still reaches and
qualifies the worker over the private VPC. Worker qualification also verifies
the Firecracker/kernel/rootfs pins, 30-day host lifetime, zero runtime residue,
and the fail-closed boundary-taint state.

`converge-preview.sh` is the separate, narrow GitOps path for the shared
preview host and its credential-free control-plane client. It installs the
forced lease command, one-job capability translator, internal-only translator
network, factory-slot Traefik middleware, and lease expiry timer. The preview's
long-lived authority remains root-readable on that host; convergence removes
the superseded control-plane copy.

`converge-session13.sh` is the narrow control-plane apply path for the A104
child boundary while the unrelated dashboard identity roster remains
deliberately unresolved. It builds and hashes `factoryctl`,
`factory-supervisor`, and the credential-free evidence qualification entry
point, sends the committed repository as a credential-free bundle, selects
only tasks tagged `session13`, and runs the fixed Session 13 qualification
after service restarts. It does not bypass or synthesize dashboard identities.

After bootstrap, the control plane can run a maintenance converge of the
committed desired state without orchestration or cloud credentials:

```bash
sudo -u factory-manager /usr/local/sbin/patchyard-converge-hosts
```

That entry point cannot mutate DigitalOcean, AWS, GitHub, or OpenTofu state,
and it has no authority over bootstrap-injected inputs: it preserves and
verifies them, never establishes or redefines them. Where an input cannot be
derived without reading back an artifact the orchestration converge itself
wrote - the GitHub App pem, the dashboard account passwords - the management
path asserts presence, ownership, and consistency with Git instead of
re-injecting, a claim that can fail rather than a `changed=0` that means
nothing.
