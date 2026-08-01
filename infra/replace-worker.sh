#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
MODE=${1:-}

require_clean_revision() {
  [[ -z "$(git -C "$REPO_ROOT" status --porcelain)" ]] || {
    echo 'worker replacement requires a committed, clean operator checkout' >&2
    exit 2
  }
}

require_approved_revision() {
  local current_revision
  : "${PATCHYARD_REPLACE_APPROVED_REVISION:?set PATCHYARD_REPLACE_APPROVED_REVISION to the reviewed source commit}"
  [[ "$PATCHYARD_REPLACE_APPROVED_REVISION" =~ ^[0-9a-f]{40}$ ]] || {
    echo 'worker replacement approved revision must be one full lowercase commit ID' >&2
    exit 2
  }
  current_revision=$(git -C "$REPO_ROOT" rev-parse HEAD)
  [[ "$current_revision" == "$PATCHYARD_REPLACE_APPROVED_REVISION" ]] || {
    echo 'worker replacement source differs from the reviewed revision' >&2
    exit 2
  }
  if ! git -C "$REPO_ROOT" merge-base --is-ancestor "$current_revision" origin/master; then
    [[ "${PATCHYARD_REPLACE_A115_UNMERGED_APPROVED:-}" == yes ]] || {
      echo 'worker replacement source is unmerged; the A115 exception was not approved' >&2
      exit 2
    }
  fi
}

verify_approved_plan_sha256() {
  local plan_file=$1 actual_plan_sha256
  : "${PATCHYARD_REPLACE_APPROVED_SHA256:?set PATCHYARD_REPLACE_APPROVED_SHA256 to the reviewed plan SHA-256}"
  [[ "$PATCHYARD_REPLACE_APPROVED_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo 'worker replacement approved SHA-256 must be 64 lowercase hexadecimal characters' >&2
    exit 2
  }
  read -r actual_plan_sha256 _ < <(sha256sum -- "$plan_file")
  [[ "$actual_plan_sha256" == "$PATCHYARD_REPLACE_APPROVED_SHA256" ]] || {
    echo 'worker replacement plan SHA-256 differs from the reviewed value' >&2
    exit 2
  }
}

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
  [[ "$worker_action" == '[["create","delete"]]' ]] || {
    echo "worker replacement plan lacks one exact worker replacement: $worker_action" >&2
    exit 2
  }
  firewall_action=$(jq -c '
    [.resource_changes[]
     | select(.address == "digitalocean_firewall.worker")
     | .change.actions]
  ' <<<"$plan_json")
  [[ "$firewall_action" == '[["update"]]' ]] || {
    echo "worker replacement plan has an unexpected worker-firewall action: $firewall_action" >&2
    exit 2
  }
}

case "$MODE" in
  plan)
    require_clean_revision
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
    sha256sum "$PLAN_FILE" "$PLAN_FILE.txt"
    echo "review $PLAN_FILE.txt, then run the apply mode with the encrypted plan"
    ;;
  apply)
    require_clean_revision
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
    require_approved_revision
    verify_approved_plan_sha256 "$PLAN_FILE"
    verify_worker_plan "$PLAN_FILE"
    "$REPO_ROOT/infra/tofu.sh" digitalocean show -no-color "$PLAN_FILE"
    "$REPO_ROOT/infra/ansible/converge.sh" --check-inputs
    verify_approved_plan_sha256 "$PLAN_FILE"
    "$REPO_ROOT/infra/tofu.sh" digitalocean apply "$PLAN_FILE"
    "$REPO_ROOT/infra/ansible/converge.sh"
    "$REPO_ROOT/infra/ansible/converge.sh"
    "$REPO_ROOT/infra/wait-do-worker-firewall.sh"
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
