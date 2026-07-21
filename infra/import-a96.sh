#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)

# Preserve the Route 53 identity before tofu.sh maps AWS_* to the backend user.
export ORIGINAL_AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
export ORIGINAL_AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
export TF_VAR_control_plane_ipv4=${TF_VAR_control_plane_ipv4:-192.0.2.1}

"$REPO_ROOT/infra/tofu.sh" aws init -reconfigure

AWS_MANAGEMENT_ACCESS_KEY_ID=${AWS_FACTORY_A96_OPERATOR_ACCESS_KEY_ID:-$ORIGINAL_AWS_ACCESS_KEY_ID}
AWS_MANAGEMENT_SECRET_ACCESS_KEY=${AWS_FACTORY_A96_OPERATOR_SECRET_ACCESS_KEY:-$ORIGINAL_AWS_SECRET_ACCESS_KEY}

if ! AWS_ACCESS_KEY_ID="$AWS_MANAGEMENT_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$AWS_MANAGEMENT_SECRET_ACCESS_KEY" \
  aws iam get-user --user-name orchestrator-tofu-state >/dev/null 2>&1; then
  echo "A96 import blocked: the AWS management identity cannot read the hand-created IAM and bucket resources." >&2
  echo "Use a temporary operator credential with IAM and S3 configuration management; never use the backend access key as that credential." >&2
  exit 1
fi

import_if_absent() {
  local address=$1
  local id=$2
  if ! "$REPO_ROOT/infra/tofu.sh" aws state show "$address" >/dev/null 2>&1; then
    "$REPO_ROOT/infra/tofu.sh" aws import "$address" "$id"
  fi
}

import_if_absent aws_s3_bucket.state example-tofu-state
import_if_absent aws_s3_bucket_versioning.state example-tofu-state
import_if_absent aws_s3_bucket_server_side_encryption_configuration.state example-tofu-state
import_if_absent aws_s3_bucket_public_access_block.state example-tofu-state
import_if_absent aws_s3_bucket_lifecycle_configuration.state example-tofu-state
import_if_absent aws_s3_bucket_policy.state example-tofu-state
import_if_absent aws_iam_user.state orchestrator-tofu-state
import_if_absent aws_iam_user_policy.state orchestrator-tofu-state:s3-patchyard-tofu-state
import_if_absent aws_iam_policy.route53_records arn:aws:iam::000000000000:policy/route53-patchyard-create-read
import_if_absent aws_iam_user_policy_attachment.route53_records \
  orchestrator-route53/arn:aws:iam::000000000000:policy/route53-patchyard-create-read

echo "A96 resources imported. Review the policy replacement and all drift before apply."
