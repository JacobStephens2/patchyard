#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  echo "usage: $0 <digitalocean|aws|github> <tofu arguments...>" >&2
  exit 2
}

[[ $# -ge 2 ]] || usage
TOFU_ROOT=$1
shift

case "$TOFU_ROOT" in
  digitalocean|aws|github) ;;
  *) usage ;;
esac

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
TOFU_DIR="$REPO_ROOT/infra/$TOFU_ROOT"
PROVIDER_AWS_ACCESS_KEY_ID=${ORIGINAL_AWS_ACCESS_KEY_ID:-${AWS_ACCESS_KEY_ID:-}}
PROVIDER_AWS_SECRET_ACCESS_KEY=${ORIGINAL_AWS_SECRET_ACCESS_KEY:-${AWS_SECRET_ACCESS_KEY:-}}

: "${AWS_S3_TOFU_STATE_ACCESS_KEY_ID:?missing backend access key}"
: "${AWS_S3_TOFU_STATE_SECRET_ACCESS_KEY:?missing backend secret key}"
: "${AWS_S3_TOFU_STATE_ENCRYPTION_PASSPHRASE:?missing state encryption passphrase}"

export TF_IN_AUTOMATION=1
export TF_INPUT=0
export TF_VAR_state_encryption_passphrase="$AWS_S3_TOFU_STATE_ENCRYPTION_PASSPHRASE"
export AWS_ACCESS_KEY_ID="$AWS_S3_TOFU_STATE_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$AWS_S3_TOFU_STATE_SECRET_ACCESS_KEY"
export AWS_REGION=us-east-1
export AWS_PAGER=

case "$TOFU_ROOT" in
  digitalocean)
    : "${DO_API_TOKEN:?missing DigitalOcean provider token}"
    export DIGITALOCEAN_TOKEN="$DO_API_TOKEN"
    if [[ -z "${TF_VAR_spaces_management_access_key:-}" ]]; then
      TF_VAR_spaces_management_access_key=$(
        tofu -chdir="$TOFU_DIR" output -raw factory_backup_management_access_key 2>/dev/null || true
      )
      export TF_VAR_spaces_management_access_key
    fi
    if [[ -z "${TF_VAR_spaces_management_secret_key:-}" ]]; then
      TF_VAR_spaces_management_secret_key=$(
        tofu -chdir="$TOFU_DIR" output -raw factory_backup_management_secret_key 2>/dev/null || true
      )
      export TF_VAR_spaces_management_secret_key
    fi
    ;;
  aws)
    : "${ROUTE53_AWS_ACCESS_KEY_ID:=$PROVIDER_AWS_ACCESS_KEY_ID}"
    : "${ROUTE53_AWS_SECRET_ACCESS_KEY:=$PROVIDER_AWS_SECRET_ACCESS_KEY}"
    : "${ROUTE53_AWS_ACCESS_KEY_ID:?set ROUTE53_AWS_ACCESS_KEY_ID or ORIGINAL_AWS_ACCESS_KEY_ID}"
    : "${ROUTE53_AWS_SECRET_ACCESS_KEY:?set ROUTE53_AWS_SECRET_ACCESS_KEY or ORIGINAL_AWS_SECRET_ACCESS_KEY}"
    AWS_MANAGEMENT_ACCESS_KEY_ID=${AWS_FACTORY_A96_OPERATOR_ACCESS_KEY_ID:-$ROUTE53_AWS_ACCESS_KEY_ID}
    AWS_MANAGEMENT_SECRET_ACCESS_KEY=${AWS_FACTORY_A96_OPERATOR_SECRET_ACCESS_KEY:-$ROUTE53_AWS_SECRET_ACCESS_KEY}
    export TF_VAR_aws_provider_access_key_id="$AWS_MANAGEMENT_ACCESS_KEY_ID"
    export TF_VAR_aws_provider_secret_access_key="$AWS_MANAGEMENT_SECRET_ACCESS_KEY"
    export TF_VAR_route53_provider_access_key_id="$ROUTE53_AWS_ACCESS_KEY_ID"
    export TF_VAR_route53_provider_secret_access_key="$ROUTE53_AWS_SECRET_ACCESS_KEY"
    if [[ -z "${TF_VAR_control_plane_ipv4:-}" && -d "$REPO_ROOT/infra/digitalocean/.terraform" ]]; then
      TF_VAR_control_plane_ipv4=$("$0" digitalocean output -raw control_plane_ipv4 2>/dev/null || true)
      export TF_VAR_control_plane_ipv4
    fi
    ;;
  github)
    GITHUB_PROVIDER_TOKEN=${GH_FACTORY_ADMIN_PAT:-${GH_TOKEN:-}}
    : "${GITHUB_PROVIDER_TOKEN:?set GH_FACTORY_ADMIN_PAT or GH_TOKEN for the GitHub provider}"
    export GITHUB_TOKEN="$GITHUB_PROVIDER_TOKEN"
    ;;
esac

exec tofu -chdir="$TOFU_DIR" "$@"
