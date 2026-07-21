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

It deliberately installs no self-hosted Actions runner or Tempo/OTLP collector.
Session 3 selected Firecracker; Session 4 owns its production installation and
runtime contract.

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
qualifies the worker over the private VPC.

After bootstrap, the control plane can re-apply the current host-local desired
state without orchestration or cloud credentials:

```bash
sudo -u factory-manager /usr/local/sbin/patchyard-converge-hosts
```

That entry point cannot mutate DigitalOcean, AWS, GitHub, or OpenTofu state.
