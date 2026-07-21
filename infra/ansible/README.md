# Factory host desired state

Ansible initializes both Rocky Linux 9 hosts. `inventory/tofu.sh` reads the
DigitalOcean outputs directly, so no address is transcribed by hand.

Session 0 owns:

- the `conductor` management identity and SSH/firewalld restrictions;
- pinned node_exporter and postgres_exporter binaries on both hosts, bound to
  private addresses and scrapeable only by `10.132.0.14/32`;
- the control-plane prerequisites (Caddy binary, Chromium, and an exact Git
  checkout transferred as a credential-free bundle);
- the unprivileged `factory-worker` identity, transient paths, cleanup, and a
  host-level block on new private-network egress;
- journald retention and hardened exporter services.

It deliberately installs no self-hosted Actions runner, Tempo/OTLP collector,
Podman, or Firecracker. The runtime choice belongs to Session 3.

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

`converge.sh` creates a temporary Git bundle, passes it to Ansible, and removes
it. No GitHub credential reaches either host. A second normal converge must end
with `changed=0` for both hosts.
