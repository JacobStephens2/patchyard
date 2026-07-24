#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
ANSIBLE_ROOT="$REPO_ROOT/infra/ansible"

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s "$ANSIBLE_ROOT/tests" -v

cd "$ANSIBLE_ROOT"
ansible-lint site.yml
ansible-lint preview.yml
ansible-playbook --syntax-check -i inventory/ci.yml site.yml
ansible-playbook --syntax-check -i inventory/ci.yml -i inventory/preview.yml preview.yml
