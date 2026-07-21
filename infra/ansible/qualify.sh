#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
INVENTORY_JSON=$("$REPO_ROOT/infra/ansible/inventory/tofu.sh")
CONTROL_HOST=$(jq -r '.control_plane.hosts[0]' <<<"$INVENTORY_JSON")
WORKER_HOST=$(jq -r '.worker.hosts[0]' <<<"$INVENTORY_JSON")
CONTROL_IP=$(jq -r --arg host "$CONTROL_HOST" '._meta.hostvars[$host].ansible_host' <<<"$INVENTORY_JSON")
WORKER_IP=$(jq -r --arg host "$WORKER_HOST" '._meta.hostvars[$host].ansible_host' <<<"$INVENTORY_JSON")
CONTROL_PRIVATE_IP=$(jq -r --arg host "$CONTROL_HOST" '._meta.hostvars[$host].private_ip' <<<"$INVENTORY_JSON")
WORKER_PRIVATE_IP=$(jq -r --arg host "$WORKER_HOST" '._meta.hostvars[$host].private_ip' <<<"$INVENTORY_JSON")
FACTORY_REVISION=$(git -C "$REPO_ROOT" rev-parse HEAD)
SSH_ARGS=(-i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=accept-new)

echo "qualifying control plane $CONTROL_HOST"
ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo /usr/local/sbin/qualify-factory-control "$FACTORY_REVISION" "$CONTROL_PRIVATE_IP"

echo "qualifying worker $WORKER_HOST"
ssh "${SSH_ARGS[@]}" "conductor@$WORKER_IP" \
  sudo /usr/local/sbin/qualify-factory-worker "$WORKER_PRIVATE_IP"

python3 "$REPO_ROOT/tools/check-independence.py"
