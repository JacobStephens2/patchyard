#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
MODE=${1:-}

verify_worker_plan() {
  local plan_file=$1 plan_json unexpected worker_action firewall_action
  plan_json=$("$REPO_ROOT/infra/tofu.sh" digitalocean show -json "$plan_file") || {
    echo 'worker replacement refused because the reviewed plan could not be inspected' >&2
    exit 2
  }
  unexpected=$(jq -r '
    .resource_changes[]
    | select(.change.actions != ["no-op"])
    | .address
    | select(. != "digitalocean_droplet.worker" and . != "digitalocean_firewall.worker")
  ' <<<"$plan_json")
  [[ -z "$unexpected" ]] || {
    echo "worker replacement plan changes an out-of-scope resource: $unexpected" >&2
    exit 2
  }
  worker_action=$(jq -c '
    [.resource_changes[]
     | select(.address == "digitalocean_droplet.worker")
     | .change.actions]
  ' <<<"$plan_json")
  [[ "$worker_action" == '[["create","delete"]]' \
    || "$worker_action" == '[["delete","create"]]' ]] || {
    echo "worker replacement plan lacks one exact worker replacement: $worker_action" >&2
    exit 2
  }
  firewall_action=$(jq -c '
    [.resource_changes[]
     | select(.address == "digitalocean_firewall.worker")
     | .change.actions]
  ' <<<"$plan_json")
  [[ "$firewall_action" == '[["no-op"]]' || "$firewall_action" == '[["update"]]' ]] || {
    echo "worker replacement plan has an unexpected worker-firewall action: $firewall_action" >&2
    exit 2
  }
}

case "$MODE" in
  plan)
    REPLACE_ROOT=${2:?usage: infra/replace-worker.sh plan /absolute/output/directory}
    if [[ "$REPLACE_ROOT" != /* ]]; then
      echo "replacement plan directory must be absolute" >&2
      exit 2
    fi
    install -d -m 0700 "$REPLACE_ROOT"
    PLAN_FILE="$REPLACE_ROOT/worker-replacement.tfplan"
    "$REPO_ROOT/infra/check-do-tag-firewalls.sh"
    "$REPO_ROOT/infra/tofu.sh" digitalocean init -reconfigure
    "$REPO_ROOT/infra/tofu.sh" digitalocean plan \
      -replace=digitalocean_droplet.worker \
      -out="$PLAN_FILE"
    verify_worker_plan "$PLAN_FILE"
    "$REPO_ROOT/infra/tofu.sh" digitalocean show -no-color "$PLAN_FILE" \
      >"$PLAN_FILE.txt"
    echo "review $PLAN_FILE.txt, then run the apply mode with the encrypted plan"
    ;;
  apply)
    PLAN_FILE=${2:?usage: infra/replace-worker.sh apply /absolute/worker-replacement.tfplan}
    if [[ "$PLAN_FILE" != /* || ! -f "$PLAN_FILE" ]]; then
      echo "replacement apply requires an existing absolute plan path" >&2
      exit 2
    fi
    : "${PATCHYARD_REPLACE_APPROVED:?set PATCHYARD_REPLACE_APPROVED=yes after human review}"
    if [[ "$PATCHYARD_REPLACE_APPROVED" != yes ]]; then
      echo "replacement approval must be the literal value yes" >&2
      exit 2
    fi
    verify_worker_plan "$PLAN_FILE"
    "$REPO_ROOT/infra/tofu.sh" digitalocean show -no-color "$PLAN_FILE"
    "$REPO_ROOT/infra/tofu.sh" digitalocean apply "$PLAN_FILE"
    "$REPO_ROOT/infra/ansible/converge.sh"
    "$REPO_ROOT/infra/ansible/converge.sh"
    "$REPO_ROOT/infra/ansible/qualify.sh"
    INVENTORY_JSON=$("$REPO_ROOT/infra/ansible/inventory/tofu.sh")
    CONTROL_HOST=$(jq -r '.control_plane.hosts[0]' <<<"$INVENTORY_JSON")
    CONTROL_IP=$(jq -r --arg host "$CONTROL_HOST" \
      '._meta.hostvars[$host].ansible_host' <<<"$INVENTORY_JSON")
    REPLACEMENT_EVIDENCE="/var/lib/patchyard/artifacts/worker-replacement-$(date -u +%Y%m%dT%H%M%SZ)"
    ssh -i /var/lib/conductor/.ssh/id_ed25519 \
      -o BatchMode=yes -o StrictHostKeyChecking=yes \
      "conductor@$CONTROL_IP" \
      sudo -u factory-manager /usr/local/sbin/patchyard-run-isolation-probe \
      /var/lib/patchyard/snapshots/current "$REPLACEMENT_EVIDENCE"
    "$REPO_ROOT/infra/ansible/qualify.sh"
    ;;
  *)
    echo "usage: $0 <plan /absolute/output/directory | apply /absolute/worker-replacement.tfplan>" >&2
    exit 2
    ;;
esac
