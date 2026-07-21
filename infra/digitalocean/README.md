# DigitalOcean desired state

This root owns the two Rocky Linux 9 factory droplets, their VPC placement,
factory tags, cloud firewalls, attached orchestration SSH public identity, and
the machine-readable inventory output consumed by Ansible. It uses the
`factory/digitalocean/tofu.tfstate` key in the A96 S3 backend.

The control plane is protected from accidental replacement. The worker is
disposable by design; use `../replace-worker.sh` for a reviewed replacement.

The provider token must manage droplets, tags, and firewalls, including worker
deletion for clean-room replacement. A token missing any one of those scopes
fails at the provider boundary; these resources are never replaced by console
work or host-only filtering.
