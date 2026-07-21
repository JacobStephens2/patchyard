# DigitalOcean desired state

This root owns the two Rocky Linux 9 factory droplets, their VPC placement,
attachment to existing Patchyard tags, cloud firewalls, the managed orchestration SSH
public identity, and the machine-readable inventory output consumed by Ansible.
It uses the `factory/digitalocean/tofu.tfstate` key in the A96 S3 backend.

The normal desired state protects the control plane from accidental
replacement. This replacement-staging revision uses create-before-destroy to
correct the bootstrap key on both still-empty hosts; restore `prevent_destroy`
immediately after it converges. The worker is disposable by design; use
`../replace-worker.sh` for a reviewed replacement.

Both hosts attach to the existing `production` tag, matching production-facing
hosts in the same nyc3 VPC. The provider token must manage droplets, firewalls,
and the versioned SSH public key; attach/detach the existing tag; and delete the
worker for clean-room replacement. A token missing any one of those
capabilities fails at the provider boundary; these resources are never replaced
by console work or host-only filtering.
