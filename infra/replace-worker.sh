#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
MODE=${1:-}

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
      -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
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
