#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
SOURCE_REPO=${FIELDBOOK_SOURCE_REPO:-/srv/orchestration/fieldbook}
[[ -e "$SOURCE_REPO/.git" ]]
[[ -z "$(git -C "$SOURCE_REPO" status --porcelain)" ]] || {
  echo "Fieldbook bootstrap source must be clean" >&2
  exit 1
}
SOURCE_SHA=$(git -C "$SOURCE_REPO" rev-parse HEAD)
SOURCE_BRANCH=$(git -C "$SOURCE_REPO" symbolic-ref --short HEAD)
[[ "$SOURCE_BRANCH" =~ ^[A-Za-z0-9._/-]+$ ]]

INVENTORY_JSON=$("$REPO_ROOT/infra/ansible/inventory/tofu.sh")
CONTROL_HOST=$(jq -r '.control_plane.hosts[0]' <<<"$INVENTORY_JSON")
CONTROL_IP=$(jq -r --arg host "$CONTROL_HOST" \
  '._meta.hostvars[$host].ansible_host' <<<"$INVENTORY_JSON")
SSH_ARGS=(-i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
TEMP_ROOT=$(mktemp -d /tmp/patchyard-source-bootstrap.XXXXXX)
trap 'rm -r -- "$TEMP_ROOT"' EXIT
BUNDLE=$TEMP_ROOT/fieldbook.bundle
REMOTE_BUNDLE=/var/tmp/patchyard-fieldbook-$SOURCE_SHA.bundle
DESTINATION=/var/lib/patchyard/bootstrap-sources/fieldbook-$SOURCE_SHA

git -C "$SOURCE_REPO" bundle create "$BUNDLE" "$SOURCE_BRANCH"
scp "${SSH_ARGS[@]}" "$BUNDLE" "conductor@$CONTROL_IP:$REMOTE_BUNDLE"
ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo install -d -m 0700 -o factory-manager -g factory-manager \
  /var/lib/patchyard/bootstrap-sources
ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo chown factory-manager:factory-manager "$REMOTE_BUNDLE"
if ! ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo -u factory-manager test -d "$DESTINATION/.git"; then
  ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
    sudo -u factory-manager git clone --quiet --branch "$SOURCE_BRANCH" \
    "$REMOTE_BUNDLE" "$DESTINATION"
  ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
    sudo -u factory-manager git -C "$DESTINATION" remote remove origin
fi
REMOTE_SHA=$(ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo -u factory-manager git -C "$DESTINATION" rev-parse HEAD)
[[ "$REMOTE_SHA" == "$SOURCE_SHA" ]]
REMOTE_COUNT=$(ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo -u factory-manager git -C "$DESTINATION" remote | wc -l)
[[ "$REMOTE_COUNT" -eq 0 ]]
ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo -u factory-manager ln -sfn "fieldbook-$SOURCE_SHA" \
  /var/lib/patchyard/bootstrap-sources/fieldbook-current.tmp
ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo -u factory-manager mv -T \
  /var/lib/patchyard/bootstrap-sources/fieldbook-current.tmp \
  /var/lib/patchyard/bootstrap-sources/fieldbook-current
ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo /usr/bin/shred --remove "$REMOTE_BUNDLE"

echo "fieldbook_bootstrap_sha=$SOURCE_SHA control_path=$DESTINATION"
