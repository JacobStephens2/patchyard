#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
ANSIBLE_ROOT="$REPO_ROOT/infra/ansible"
FACTORY_REVISION=$(git -C "$REPO_ROOT" rev-parse HEAD)

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
  echo "converge requires a committed, clean desired-state revision" >&2
  exit 1
fi

CONVERGE_TEMP=$(mktemp -d /tmp/patchyard-converge.XXXXXX)
trap 'rm -r -- "$CONVERGE_TEMP"' EXIT
FACTORY_BUNDLE="$CONVERGE_TEMP/factory.bundle"
git -C "$REPO_ROOT" bundle create "$FACTORY_BUNDLE" --all

if [[ -x "$ANSIBLE_ROOT/.venv/bin/ansible-playbook" ]]; then
  ANSIBLE_PLAYBOOK="$ANSIBLE_ROOT/.venv/bin/ansible-playbook"
else
  ANSIBLE_PLAYBOOK=ansible-playbook
fi

cd "$ANSIBLE_ROOT"
"$ANSIBLE_PLAYBOOK" \
  -i inventory/tofu.sh \
  site.yml \
  -e "factory_repo_bundle=$FACTORY_BUNDLE" \
  -e "factory_repo_revision=$FACTORY_REVISION" \
  "$@"
