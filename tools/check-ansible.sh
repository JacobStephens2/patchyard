#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
ANSIBLE_ROOT="$REPO_ROOT/infra/ansible"
source "$REPO_ROOT/infra/tool-versions.env"

ACTUAL_SHELLCHECK_VERSION=$(
  shellcheck --version | awk '$1 == "version:" { print $2 }'
)
if [[ "$ACTUAL_SHELLCHECK_VERSION" != "$SHELLCHECK_VERSION" ]]; then
  echo "ShellCheck must be exactly $SHELLCHECK_VERSION; run tools/install-shellcheck.sh" >&2
  exit 1
fi

# The launcher's EXIT trap is the root of its cleanup call graph, which makes
# reachable helpers look unused to ShellCheck's SC2329 analysis.
shellcheck --exclude=SC2329 --shell=bash \
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

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s "$ANSIBLE_ROOT/tests" -v

cd "$ANSIBLE_ROOT"
ansible-lint site.yml
ansible-lint preview.yml
ansible-lint restore.yml
ansible-lint rollback-boundary.yml
ansible-playbook --syntax-check -i inventory/ci.yml site.yml
ansible-playbook --syntax-check -i inventory/ci.yml -i inventory/preview.yml preview.yml
ansible-playbook --syntax-check -i inventory/ci.yml restore.yml
ansible-playbook --syntax-check -i inventory/ci.yml rollback-boundary.yml \
  -e factory_rollback_boundary=enter
