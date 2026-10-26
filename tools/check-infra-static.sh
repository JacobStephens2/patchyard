#!/usr/bin/env bash
# Static infrastructure checks for CI: syntax, lint, and the unit tests that
# do not depend on recorded live evidence.
#
# tools/check-infra.sh and tools/check-ansible.sh remain the full gates. Their
# live-evidence checks bind qualification Results to exact source bytes, and
# the 2026-09 identity scrub changed those bytes after the runs were recorded,
# so they can only pass again by re-running the live qualifications. See
# README.md § Continuous integration.
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
ANSIBLE_ROOT="$REPO_ROOT/infra/ansible"

gate_status=0
failed_gates=()
run_gate() {
  if "$@"; then
    return 0
  fi
  local failed_gate
  printf -v failed_gate '%q ' "$@"
  failed_gates+=("${failed_gate% }")
  gate_status=1
  return 0
}

OPENTOFU_VERSION=$(
  python3 -I "$REPO_ROOT/tools/read-infra-tool-version.py" OPENTOFU_VERSION
)
if [[ "$(tofu version -json | jq -r .terraform_version)" != "$OPENTOFU_VERSION" ]]; then
  echo "OpenTofu must be exactly $OPENTOFU_VERSION" >&2
  exit 1
fi
SHELLCHECK_VERSION=$(
  python3 -I "$REPO_ROOT/tools/read-infra-tool-version.py" SHELLCHECK_VERSION
)
ACTUAL_SHELLCHECK_VERSION=$(
  shellcheck --version | awk '$1 == "version:" { print $2 }'
)
if [[ "$ACTUAL_SHELLCHECK_VERSION" != "$SHELLCHECK_VERSION" ]]; then
  echo "ShellCheck must be exactly $SHELLCHECK_VERSION; run tools/install-shellcheck.sh" >&2
  exit 1
fi

run_gate tofu fmt -check -recursive "$REPO_ROOT/infra"

export TF_VAR_state_encryption_passphrase=ci-only-passphrase-not-a-secret
export TF_VAR_aws_provider_access_key_id=ci-placeholder
export TF_VAR_aws_provider_secret_access_key=ci-placeholder-secret
export TF_VAR_route53_provider_access_key_id=ci-route53-placeholder
export TF_VAR_route53_provider_secret_access_key=ci-route53-placeholder-secret
export TF_VAR_control_plane_ipv4=192.0.2.1
export DIGITALOCEAN_TOKEN=ci-placeholder
export GITHUB_TOKEN=ci-placeholder

CHECK_TEMP=$(mktemp -d /tmp/patchyard-infra-static.XXXXXX)
trap 'rm -r -- "$CHECK_TEMP"' EXIT

for TOFU_ROOT in digitalocean aws github; do
  export TF_DATA_DIR="$CHECK_TEMP/$TOFU_ROOT"
  run_gate tofu -chdir="$REPO_ROOT/infra/$TOFU_ROOT" init -backend=false
  run_gate tofu -chdir="$REPO_ROOT/infra/$TOFU_ROOT" validate
done

# The launcher's EXIT trap is the root of its cleanup call graph, which makes
# reachable helpers look unused to ShellCheck's SC2329 analysis.
run_gate shellcheck --exclude=SC2329 --shell=bash \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-child-launcher" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-reap-child" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-spawn-child" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-cancel-child" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-request-seat-bearer" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-render-request" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-run-session14-qualification" \
  "$REPO_ROOT/worker/qualification/patchyard-run-anthropic-issuance" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-stage-session14-qualification" \
  "$ANSIBLE_ROOT/roles/control_plane/files/qualify-factory-session13" \
  "$ANSIBLE_ROOT/roles/control_plane/files/qualify-factory-session14" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-backup" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-restore" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-restore-evidence-probe" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-deployed-version" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-converge-hosts" \
  "$ANSIBLE_ROOT/converge-session14.sh" \
  "$ANSIBLE_ROOT/converge.sh" \
  "$REPO_ROOT/infra/plan.sh" \
  "$REPO_ROOT/infra/tofu.sh" \
  "$REPO_ROOT/infra/replace-worker.sh" \
  "$REPO_ROOT/infra/wait-do-worker-firewall.sh" \
  "$REPO_ROOT/infra/restore-drill.sh" \
  "$REPO_ROOT/infra/rollback-control.sh" \
  "$REPO_ROOT/worker/runtime/patchyard-provider-run" \
  "$REPO_ROOT/worker/runtime/patchyard-openai-one-shot" \
  "$REPO_ROOT/worker/image/patchyard-guest-dispatch" \
  "$REPO_ROOT/worker/image/patchyard-guest-qualify" \
  "$REPO_ROOT/worker/qualification/patchyard-run-openai-spend"

run_gate python3 -I "$REPO_ROOT/tools/check-signing-identities.py"
run_gate python3 -I "$REPO_ROOT/tools/check-openai-identity-liveness.py"
run_gate python3 -I "$REPO_ROOT/tools/check-stack.py"
run_gate python3 -I "$REPO_ROOT/tools/check-independence.py"
run_gate python3 -I "$REPO_ROOT/tools/check-preview-runtime.py"

# Unit tests that carry no live-evidence binding.
TEST_FILES=(
  infra/ansible/tests/test_child_launcher.py
  infra/ansible/tests/test_cloud_init_bootstrap.py
  infra/ansible/tests/test_dashboard_checkout.py
  infra/ansible/tests/test_demonstration_run.py
  infra/ansible/tests/test_factory_checker_runtime.py
  infra/ansible/tests/test_live_arbiter_seat.py
  infra/ansible/tests/test_live_review_disposition_seats.py
  infra/ansible/tests/test_log_secret_scan.py
  infra/ansible/tests/test_merge_refix.py
  infra/ansible/tests/test_preview_capability_deployment.py
  infra/ansible/tests/test_production_cutover.py
  infra/ansible/tests/test_repair_brief_render.py
  infra/ansible/tests/test_replace_worker.py
  infra/ansible/tests/test_repository_copy.py
  infra/ansible/tests/test_session13_settle.py
  infra/ansible/tests/test_session14_qualification.py
  infra/ansible/tests/test_session15_proposer.py
)
for test_file in "${TEST_FILES[@]}"; do
  run_gate python3 -I "$REPO_ROOT/tools/run-isolated-unittest.py" \
    "$REPO_ROOT/$test_file"
done

cd "$ANSIBLE_ROOT"
run_gate ansible-lint site.yml preview.yml restore.yml rollback-boundary.yml
run_gate ansible-playbook --syntax-check -i inventory/ci.yml site.yml
run_gate ansible-playbook --syntax-check -i inventory/ci.yml -i inventory/preview.yml preview.yml
run_gate ansible-playbook --syntax-check -i inventory/ci.yml restore.yml
run_gate ansible-playbook --syntax-check -i inventory/ci.yml rollback-boundary.yml \
  -e factory_rollback_boundary=enter

if ((${#failed_gates[@]} > 0)); then
  printf 'Failed static infrastructure gates:\n' >&2
  printf '  %s\n' "${failed_gates[@]}" >&2
fi
exit "$gate_status"
