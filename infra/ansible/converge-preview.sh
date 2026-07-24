#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
ANSIBLE_ROOT="$REPO_ROOT/infra/ansible"

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
  echo "preview convergence requires a committed, clean desired-state revision" >&2
  exit 1
fi

if [[ -x "$ANSIBLE_ROOT/.venv/bin/ansible-playbook" ]]; then
  ANSIBLE_PLAYBOOK="$ANSIBLE_ROOT/.venv/bin/ansible-playbook"
else
  ANSIBLE_PLAYBOOK=ansible-playbook
fi

cd "$ANSIBLE_ROOT"
exec "$ANSIBLE_PLAYBOOK" \
  -i inventory/tofu.sh \
  -i inventory/preview.yml \
  preview.yml \
  "$@"
