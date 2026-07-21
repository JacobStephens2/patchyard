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
WORKER_IMAGE_RECIPE_SHA256=$(sed -n \
  's/^worker_image_recipe_sha256:[[:space:]]*//p' \
  "$REPO_ROOT/infra/ansible/group_vars/all.yml")
SSH_ARGS=(-i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
FRESH_SSH_ARGS=("${SSH_ARGS[@]}" -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=4)

echo "qualifying control plane $CONTROL_HOST"
ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo /usr/local/sbin/qualify-factory-control \
    "$FACTORY_REVISION" "$CONTROL_PRIVATE_IP" "$CONTROL_PRIVATE_IP/32"

echo "qualifying worker $WORKER_HOST"
ssh "${SSH_ARGS[@]}" "conductor@$WORKER_IP" \
  sudo /usr/local/sbin/qualify-factory-worker \
    "$WORKER_PRIVATE_IP" "$CONTROL_PRIVATE_IP/32" \
    "$WORKER_IMAGE_RECIPE_SHA256"

run_factory_manager() {
  ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
    sudo -u factory-manager /usr/local/sbin/patchyard-management-ssh "$@"
}

cleanup_breakglass_probe() {
  run_factory_manager worker unblock-breakglass >/dev/null 2>&1 || true
}

echo "qualifying A101 private-VPC management transport"
run_factory_manager control probe
run_factory_manager worker probe
run_factory_manager worker block-breakglass
trap cleanup_breakglass_probe EXIT
if ssh "${FRESH_SSH_ARGS[@]}" "conductor@$WORKER_IP" true >/dev/null 2>&1; then
  echo "orchestration break-glass path remained reachable during isolation probe" >&2
  exit 1
fi
run_factory_manager worker qualify
cleanup_breakglass_probe
trap - EXIT
echo "A101 management transport: pass"

python3 "$REPO_ROOT/tools/check-independence.py"
