#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
ANSIBLE_ROOT="$REPO_ROOT/infra/ansible"
python3 -I "$REPO_ROOT/tools/check-a101-readiness-root.py"
SHELLCHECK_VERSION=$(
  python3 -I "$REPO_ROOT/tools/read-infra-tool-version.py" SHELLCHECK_VERSION
)

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

ACTUAL_SHELLCHECK_VERSION=$(
  shellcheck --version | awk '$1 == "version:" { print $2 }'
)
if [[ "$ACTUAL_SHELLCHECK_VERSION" != "$SHELLCHECK_VERSION" ]]; then
  echo "ShellCheck must be exactly $SHELLCHECK_VERSION; run tools/install-shellcheck.sh" >&2
  exit 1
fi

# The launcher's EXIT trap is the root of its cleanup call graph, which makes
# reachable helpers look unused to ShellCheck's SC2329 analysis.
run_gate shellcheck --exclude=SC2329 --shell=bash \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-child-launcher" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-reap-child" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-spawn-child" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-cancel-child" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-request-seat-bearer" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-run-session14-qualification" \
  "$REPO_ROOT/worker/qualification/patchyard-run-anthropic-issuance" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-stage-session14-qualification" \
  "$ANSIBLE_ROOT/roles/control_plane/files/qualify-factory-session14" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-backup" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-restore" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-restore-evidence-probe" \
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-deployed-version" \
  "$ANSIBLE_ROOT/converge-session14.sh" \
  "$ANSIBLE_ROOT/converge.sh" \
  "$REPO_ROOT/infra/plan.sh" \
  "$REPO_ROOT/infra/tofu.sh" \
  "$REPO_ROOT/infra/replace-worker.sh" \
  "$REPO_ROOT/infra/wait-do-worker-firewall.sh" \
  "$REPO_ROOT/infra/restore-drill.sh" \
  "$REPO_ROOT/infra/rollback-control.sh"

run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-spend.py"

# Security-sensitive files run first and every file gets a fresh isolated
# Python process. The pinned runner loads each file under a synthetic,
# non-package module name, so repository package initializers cannot execute.
TEST_FILES=(
  infra/ansible/tests/test_a101_readiness_root.py
  infra/ansible/tests/test_attended_collector_runner.py
  infra/ansible/tests/test_anthropic_issuance.py
  infra/ansible/tests/test_anthropic_lifecycle.py
  infra/ansible/tests/test_anthropic_spend.py
  infra/ansible/tests/test_anthropic_wif_admin.py
  infra/ansible/tests/test_child_launcher.py
  infra/ansible/tests/test_cloud_init_bootstrap.py
  infra/ansible/tests/test_dashboard_checkout.py
  infra/ansible/tests/test_freeze_graph.py
  infra/ansible/tests/test_live_review_disposition_seats.py
  infra/ansible/tests/test_log_secret_scan.py
  infra/ansible/tests/test_merge_refix.py
  infra/ansible/tests/test_neutral_guest_qualification.py
  infra/ansible/tests/test_openai_control_plane_lifecycle.py
  infra/ansible/tests/test_openai_wif_issuance.py
  infra/ansible/tests/test_preview_capability_deployment.py
  infra/ansible/tests/test_replace_worker.py
  infra/ansible/tests/test_session14_qualification.py
  infra/ansible/tests/test_session15_proposer.py
  infra/ansible/tests/test_session16_cutover.py
  infra/ansible/tests/test_triage_seat_deployment.py
  infra/ansible/tests/test_worker_firewall_readiness.py
)
for test_file in "${TEST_FILES[@]}"; do
  run_gate python3 -I "$REPO_ROOT/tools/run-isolated-unittest.py" \
    "$REPO_ROOT/$test_file"
done

cd "$ANSIBLE_ROOT"
run_gate ansible-lint site.yml
run_gate ansible-lint preview.yml
run_gate ansible-lint restore.yml
run_gate ansible-lint rollback-boundary.yml
run_gate ansible-playbook --syntax-check -i inventory/ci.yml site.yml
run_gate ansible-playbook --syntax-check -i inventory/ci.yml -i inventory/preview.yml preview.yml
run_gate ansible-playbook --syntax-check -i inventory/ci.yml restore.yml
run_gate ansible-playbook --syntax-check -i inventory/ci.yml rollback-boundary.yml \
  -e factory_rollback_boundary=enter

cd "$REPO_ROOT"
run_gate python3 -I "$REPO_ROOT/tools/check-a101-readiness-root.py"
if ((${#failed_gates[@]} > 0)); then
  printf 'Failed Ansible gates:\n' >&2
  printf '  %s\n' "${failed_gates[@]}" >&2
fi
exit "$gate_status"
