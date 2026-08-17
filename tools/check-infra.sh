#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
python3 -I "$REPO_ROOT/tools/check-a101-readiness-root.py"
OPENTOFU_VERSION=$(
  python3 -I "$REPO_ROOT/tools/read-infra-tool-version.py" OPENTOFU_VERSION
)

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

gate_status=0
run_gate() {
  if "$@"; then
    return 0
  fi
  gate_status=1
  return 0
}

run_gate python3 -I "$REPO_ROOT/tools/check-freeze-graph.py"
# The A133 neutral launcher cannot ride check-ansible.sh's ShellCheck list,
# because that file's digest is bound by check-anthropic-spend.py; the gate
# lives here instead, and CI installs the pinned ShellCheck before this runs.
run_gate shellcheck --exclude=SC2329 --shell=bash \
  "$REPO_ROOT/worker/runtime/patchyard-provider-run"
run_gate shellcheck --exclude=SC2329 --shell=bash \
  "$REPO_ROOT/worker/runtime/patchyard-openai-one-shot"
# The guest half of the same neutral path, added alongside the pinned general
# runner rather than editing it.
run_gate shellcheck --exclude=SC2329 --shell=bash \
  "$REPO_ROOT/worker/image/patchyard-guest-dispatch"
run_gate shellcheck --exclude=SC2329 --shell=bash \
  "$REPO_ROOT/worker/image/patchyard-guest-qualify"
# The OpenAI requirement-2 driver rides the same gate as its launcher: the
# check-ansible.sh ShellCheck list is digest-bound by check-anthropic-spend.py.
run_gate shellcheck --exclude=SC2329 --shell=bash \
  "$REPO_ROOT/worker/qualification/patchyard-run-openai-spend"
run_gate python3 -I "$REPO_ROOT/tools/check-credential-qualification.py"
# A144 path-collision gate: no two providers may name one signing-key path.
run_gate python3 -I "$REPO_ROOT/tools/check-signing-identities.py"
run_gate python3 -I "$REPO_ROOT/tools/check-stack.py"
run_gate python3 -I "$REPO_ROOT/tools/check-independence.py"
run_gate python3 -I "$REPO_ROOT/tools/check-worker-runtime.py"
run_gate python3 -I "$REPO_ROOT/tools/check-worker-qualification.py"
run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-spend.py"
run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-issuance.py"
run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-expiry.py" --allow-missing-results
run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-revocation.py" --allow-missing-results
run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-crash-cleanup.py" --allow-missing-results
run_gate python3 -I "$REPO_ROOT/tools/check-openai-wif-issuance.py" --allow-missing-results
run_gate python3 -I "$REPO_ROOT/tools/check-openai-wif-expiry.py" --allow-missing-results
run_gate python3 -I "$REPO_ROOT/tools/check-openai-wif-crash-cleanup.py" --allow-missing-results
run_gate python3 -I "$REPO_ROOT/tools/check-openai-wif-federation-revocation.py" --allow-missing-results
run_gate python3 -I "$REPO_ROOT/tools/check-openai-wif-signing-key-rotation.py" --allow-missing-results
run_gate python3 -I "$REPO_ROOT/tools/check-openai-spend.py" --allow-missing-results
run_gate python3 -I "$REPO_ROOT/tools/check-preview-runtime.py"
exit "$gate_status"
