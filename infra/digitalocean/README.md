# DigitalOcean desired state

This root owns the two Rocky Linux 9 factory droplets, their VPC placement,
attachment to existing Patchyard tags, cloud firewalls, the attached orchestration
SSH public identity, and the machine-readable inventory output consumed by Ansible. It uses the
`factory/digitalocean/tofu.tfstate` key in the A96 S3 backend.

The control plane is protected from accidental replacement. The worker is
disposable by design; use `../replace-worker.sh` for a reviewed replacement.

Read the live tag inventory and supply the reviewed names as
`TF_VAR_existing_eta_tag_names` (a JSON list). The provider token must manage
droplets and firewalls, read and attach the existing tags, and delete the worker
for clean-room replacement. A token missing any one of those capabilities fails
at the provider boundary; these resources are never replaced by console work or
host-only filtering.
