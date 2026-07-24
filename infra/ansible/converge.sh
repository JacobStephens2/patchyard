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
: "${FACTORY_DASHBOARD_ACCOUNTS_FILE:?FACTORY_DASHBOARD_ACCOUNTS_FILE is required}"
if [[ ! -f "$GH_PATCHYARD_APP_PRIVATE_KEY_FILE" ]]; then
  echo "GitHub App private-key file is not a regular file" >&2
  exit 1
fi
if [[ ! -f "$FACTORY_DASHBOARD_ACCOUNTS_FILE" ]]; then
  echo "Dashboard account bootstrap file is not a regular file" >&2
  exit 1
fi
DASHBOARD_ACCOUNTS_MODE=$(stat -c '%a' "$FACTORY_DASHBOARD_ACCOUNTS_FILE")
if (( (8#$DASHBOARD_ACCOUNTS_MODE & 8#077) != 0 )); then
  echo "Dashboard account bootstrap file must not be group/world accessible" >&2
  exit 1
fi
jq --exit-status '
  type == "array"
  and length >= 3
  and all(.[];
    (keys | sort) == ["display_name","password","role","username"]
    and (.username | type == "string" and length > 0)
    and (.display_name | type == "string" and length > 0)
    and (.password | type == "string" and length >= 14)
    and (.role == "factory_admin" or .role == "factory_submit")
  )
  and ([.[] | select(.role == "factory_admin")] | length >= 2)
  and ([.[] | select(.role == "factory_submit")] | length >= 1)
' "$FACTORY_DASHBOARD_ACCOUNTS_FILE" >/dev/null || {
  echo "Dashboard account bootstrap file does not match the required JSON contract" >&2
  exit 1
}

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
  --package factoryctl --package factory-verify --package factory-supervisor \
  --package factory-web
FACTORYCTL_BINARY="$REPO_ROOT/target/release/factoryctl"
FACTORYCTL_SHA256=$(sha256sum "$FACTORYCTL_BINARY" | cut -d' ' -f1)
FACTORY_VERIFY_BINARY="$REPO_ROOT/target/release/factory-verify"
FACTORY_VERIFY_SHA256=$(sha256sum "$FACTORY_VERIFY_BINARY" | cut -d' ' -f1)
FACTORY_SUPERVISOR_BINARY="$REPO_ROOT/target/release/factory-supervisor"
FACTORY_SUPERVISOR_SHA256=$(sha256sum "$FACTORY_SUPERVISOR_BINARY" | cut -d' ' -f1)
FACTORY_EVIDENCE_QUALIFY_BINARY="$REPO_ROOT/target/release/factory-evidence-qualify"
FACTORY_EVIDENCE_QUALIFY_SHA256=$(
  sha256sum "$FACTORY_EVIDENCE_QUALIFY_BINARY" | cut -d' ' -f1
)
FACTORY_WEB_BINARY="$REPO_ROOT/target/release/factory-web"
FACTORY_WEB_SHA256=$(sha256sum "$FACTORY_WEB_BINARY" | cut -d' ' -f1)

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
  -e "factory_evidence_qualify_binary=$FACTORY_EVIDENCE_QUALIFY_BINARY" \
  -e "factory_evidence_qualify_sha256=$FACTORY_EVIDENCE_QUALIFY_SHA256" \
  -e "factory_web_binary=$FACTORY_WEB_BINARY" \
  -e "factory_web_sha256=$FACTORY_WEB_SHA256" \
  -e "factory_dashboard_accounts_file=$FACTORY_DASHBOARD_ACCOUNTS_FILE" \
  -e "factory_github_app_id=$GH_PATCHYARD_APP_ID" \
  -e "factory_github_app_installation_id=$GH_PATCHYARD_APP_INSTALLATION_ID" \
  -e "factory_github_app_private_key_file=$GH_PATCHYARD_APP_PRIVATE_KEY_FILE" \
  "$@"
