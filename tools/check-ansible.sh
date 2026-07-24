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
  "$ANSIBLE_ROOT/roles/control_plane/files/patchyard-cancel-child"

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s "$ANSIBLE_ROOT/tests" -v

cd "$ANSIBLE_ROOT"
ansible-lint site.yml
ansible-lint preview.yml
ansible-playbook --syntax-check -i inventory/ci.yml site.yml
ansible-playbook --syntax-check -i inventory/ci.yml -i inventory/preview.yml preview.yml
