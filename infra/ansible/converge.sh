#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
ANSIBLE_ROOT="$REPO_ROOT/infra/ansible"
FACTORY_REVISION=$(git -C "$REPO_ROOT" rev-parse HEAD)
CARGO_BIN=${CARGO_BIN:-/var/lib/conductor/.cargo/bin/cargo}

: "${GH_PATCHYARD_APP_ID:?GH_PATCHYARD_APP_ID is required}"
: "${GH_PATCHYARD_APP_INSTALLATION_ID:?GH_PATCHYARD_APP_INSTALLATION_ID is required}"
: "${GH_PATCHYARD_APP_PRIVATE_KEY_FILE:?GH_PATCHYARD_APP_PRIVATE_KEY_FILE is required}"
if [[ ! -f "$GH_PATCHYARD_APP_PRIVATE_KEY_FILE" ]]; then
  echo "GitHub App private-key file is not a regular file" >&2
  exit 1
fi

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
  echo "converge requires a committed, clean desired-state revision" >&2
  exit 1
fi

INVENTORY_JSON=$("$ANSIBLE_ROOT/inventory/tofu.sh")
jq -e '
  (.control_plane.hosts | length) == 1
  and (.worker.hosts | length) == 1
  and (._meta.hostvars | length) == 2
' <<<"$INVENTORY_JSON" >/dev/null || {
  echo "converge requires exactly one control-plane and one worker host" >&2
  exit 1
}

CONVERGE_TEMP=$(mktemp -d /tmp/patchyard-converge.XXXXXX)
trap 'rm -r -- "$CONVERGE_TEMP"' EXIT
FACTORY_BUNDLE="$CONVERGE_TEMP/factory.bundle"
git -C "$REPO_ROOT" bundle create "$FACTORY_BUNDLE" --all

"$CARGO_BIN" build --locked --release \
  --package factoryctl --package factory-verify --package factory-supervisor
FACTORYCTL_BINARY="$REPO_ROOT/target/release/factoryctl"
FACTORYCTL_SHA256=$(sha256sum "$FACTORYCTL_BINARY" | cut -d' ' -f1)
FACTORY_VERIFY_BINARY="$REPO_ROOT/target/release/factory-verify"
FACTORY_VERIFY_SHA256=$(sha256sum "$FACTORY_VERIFY_BINARY" | cut -d' ' -f1)
FACTORY_SUPERVISOR_BINARY="$REPO_ROOT/target/release/factory-supervisor"
FACTORY_SUPERVISOR_SHA256=$(sha256sum "$FACTORY_SUPERVISOR_BINARY" | cut -d' ' -f1)

if [[ -x "$ANSIBLE_ROOT/.venv/bin/ansible-playbook" ]]; then
  ANSIBLE_PLAYBOOK="$ANSIBLE_ROOT/.venv/bin/ansible-playbook"
else
  ANSIBLE_PLAYBOOK=ansible-playbook
fi

cd "$ANSIBLE_ROOT"
"$ANSIBLE_PLAYBOOK" \
  -i inventory/tofu.sh \
  site.yml \
  -e "factory_repo_bundle=$FACTORY_BUNDLE" \
  -e "factory_repo_revision=$FACTORY_REVISION" \
  -e "factoryctl_binary=$FACTORYCTL_BINARY" \
  -e "factoryctl_sha256=$FACTORYCTL_SHA256" \
  -e "factory_verify_binary=$FACTORY_VERIFY_BINARY" \
  -e "factory_verify_sha256=$FACTORY_VERIFY_SHA256" \
  -e "factory_supervisor_binary=$FACTORY_SUPERVISOR_BINARY" \
  -e "factory_supervisor_sha256=$FACTORY_SUPERVISOR_SHA256" \
  -e "factory_github_app_id=$GH_PATCHYARD_APP_ID" \
  -e "factory_github_app_installation_id=$GH_PATCHYARD_APP_INSTALLATION_ID" \
  -e "factory_github_app_private_key_file=$GH_PATCHYARD_APP_PRIVATE_KEY_FILE" \
  "$@"
