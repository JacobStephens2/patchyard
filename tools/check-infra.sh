#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
source "$REPO_ROOT/infra/tool-versions.env"

if [[ "$(tofu version -json | jq -r .terraform_version)" != "$OPENTOFU_VERSION" ]]; then
  echo "OpenTofu must be exactly $OPENTOFU_VERSION" >&2
  exit 1
fi

tofu fmt -check -recursive "$REPO_ROOT/infra"

export TF_VAR_state_encryption_passphrase=ci-only-passphrase-not-a-secret
export TF_VAR_aws_provider_access_key_id=ci-placeholder
export TF_VAR_aws_provider_secret_access_key=ci-placeholder-secret
export TF_VAR_route53_provider_access_key_id=ci-route53-placeholder
export TF_VAR_route53_provider_secret_access_key=ci-route53-placeholder-secret
export TF_VAR_control_plane_ipv4=192.0.2.1
export DIGITALOCEAN_TOKEN=ci-placeholder
export GITHUB_TOKEN=ci-placeholder

CHECK_TEMP=$(mktemp -d /tmp/patchyard-infra-check.XXXXXX)
trap 'rm -r -- "$CHECK_TEMP"' EXIT

for TOFU_ROOT in digitalocean aws github; do
  export TF_DATA_DIR="$CHECK_TEMP/$TOFU_ROOT"
  tofu -chdir="$REPO_ROOT/infra/$TOFU_ROOT" init -backend=false
  tofu -chdir="$REPO_ROOT/infra/$TOFU_ROOT" validate
done

python3 "$REPO_ROOT/tools/check-stack.py"
python3 "$REPO_ROOT/tools/check-independence.py"
python3 "$REPO_ROOT/tools/check-worker-runtime.py"
python3 "$REPO_ROOT/tools/check-worker-qualification.py"
python3 "$REPO_ROOT/tools/check-anthropic-issuance.py"
python3 "$REPO_ROOT/tools/check-anthropic-spend.py"
python3 "$REPO_ROOT/tools/check-preview-runtime.py"
