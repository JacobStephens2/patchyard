#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
ANSIBLE_ROOT="$REPO_ROOT/infra/ansible"

cd "$ANSIBLE_ROOT"
ansible-lint site.yml
ansible-playbook --syntax-check -i inventory/ci.yml site.yml
