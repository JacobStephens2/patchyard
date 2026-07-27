#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
TOFU_ROOT=${1:?usage: infra/plan.sh <digitalocean|aws|github> /absolute/output/directory}
PLAN_ROOT=${2:?usage: infra/plan.sh <digitalocean|aws|github> /absolute/output/directory}

[[ -z "$(git -C "$REPO_ROOT" status --porcelain)" ]] || {
  echo 'OpenTofu planning requires a committed, clean operator checkout' >&2
  exit 2
}

case "$TOFU_ROOT" in
  digitalocean|aws|github) ;;
  *) echo "unknown OpenTofu root: $TOFU_ROOT" >&2; exit 2 ;;
esac

if [[ "$PLAN_ROOT" != /* ]]; then
  echo "plan output directory must be absolute" >&2
  exit 2
fi
install -d -m 0700 "$PLAN_ROOT"

export ORIGINAL_AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
export ORIGINAL_AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}

if [[ "$TOFU_ROOT" == aws ]]; then
  export TF_VAR_control_plane_ipv4
  TF_VAR_control_plane_ipv4=$("$REPO_ROOT/infra/tofu.sh" digitalocean output -raw control_plane_ipv4)
fi

if [[ "$TOFU_ROOT" == digitalocean ]]; then
  "$REPO_ROOT/infra/check-do-tag-firewalls.sh"
fi

"$REPO_ROOT/infra/tofu.sh" "$TOFU_ROOT" init -reconfigure
if [[ "$TOFU_ROOT" == digitalocean ]]; then
  state_list=$("$REPO_ROOT/infra/tofu.sh" digitalocean state list) || {
    echo 'routine DigitalOcean plan refused because restore-drill state could not be inspected' >&2
    exit 2
  }
  if grep -Fxq 'digitalocean_droplet.restore_drill[0]' <<<"$state_list"; then
    echo 'routine DigitalOcean plan refused while the restore drill exists; use restore-drill.sh plan-destroy' >&2
    exit 2
  fi
fi
"$REPO_ROOT/infra/tofu.sh" "$TOFU_ROOT" plan -out="$PLAN_ROOT/$TOFU_ROOT.tfplan"
"$REPO_ROOT/infra/tofu.sh" "$TOFU_ROOT" show -no-color "$PLAN_ROOT/$TOFU_ROOT.tfplan" \
  >"$PLAN_ROOT/$TOFU_ROOT.tfplan.txt"

echo "encrypted plans and human-readable views written under $PLAN_ROOT"
