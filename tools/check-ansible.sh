#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
ANSIBLE_ROOT="$REPO_ROOT/infra/ansible"
python3 "$REPO_ROOT/tools/check-a101-readiness-root.py"
SHELLCHECK_VERSION=$(
  python3 "$REPO_ROOT/tools/read-infra-tool-version.py" SHELLCHECK_VERSION
)

gate_status=0
run_gate() {
  if "$@"; then
    return 0
  fi
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

run_gate python3 "$REPO_ROOT/tools/check-anthropic-spend.py"

# Security-sensitive modules run first and every module gets a fresh Python
# process. An earlier test therefore cannot alter hashlib or another module's
# globals, and the trust-root checker binds this complete explicit census.
TEST_MODULES=(
  infra.ansible.tests.test_a101_readiness_root
  infra.ansible.tests.test_worker_firewall_readiness
  infra.ansible.tests.test_anthropic_spend
  infra.ansible.tests.test_anthropic_issuance
  infra.ansible.tests.test_anthropic_wif_admin
  infra.ansible.tests.test_child_launcher
  infra.ansible.tests.test_cloud_init_bootstrap
  infra.ansible.tests.test_dashboard_checkout
  infra.ansible.tests.test_log_secret_scan
  infra.ansible.tests.test_preview_capability_deployment
  infra.ansible.tests.test_replace_worker
  infra.ansible.tests.test_session14_qualification
  infra.ansible.tests.test_session15_proposer
  infra.ansible.tests.test_session16_cutover
)
for test_module in "${TEST_MODULES[@]}"; do
  run_gate env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest "$test_module" -v
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
run_gate python3 "$REPO_ROOT/tools/check-a101-readiness-root.py"
exit "$gate_status"
