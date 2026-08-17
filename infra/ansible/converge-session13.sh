#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
ANSIBLE_ROOT="$REPO_ROOT/infra/ansible"
FACTORY_REVISION=$(git -C "$REPO_ROOT" rev-parse HEAD)
CARGO_BIN=${CARGO_BIN:-/var/lib/conductor/.cargo/bin/cargo}

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
  echo "Session 13 convergence requires a committed, clean desired-state revision" >&2
  exit 1
fi

CONVERGE_TEMP=$(mktemp -d /tmp/patchyard-session13-converge.XXXXXX)
trap 'rm -r -- "$CONVERGE_TEMP"' EXIT
FACTORY_BUNDLE="$CONVERGE_TEMP/factory.bundle"
git -C "$REPO_ROOT" bundle create "$FACTORY_BUNDLE" --all

"$CARGO_BIN" build --locked --release --package factoryctl --package factory-supervisor
FACTORYCTL_BINARY="$REPO_ROOT/target/release/factoryctl"
FACTORYCTL_SHA256=$(sha256sum "$FACTORYCTL_BINARY" | cut -d' ' -f1)
FACTORY_SUPERVISOR_BINARY="$REPO_ROOT/target/release/factory-supervisor"
FACTORY_SUPERVISOR_SHA256=$(sha256sum "$FACTORY_SUPERVISOR_BINARY" | cut -d' ' -f1)
FACTORY_EVIDENCE_QUALIFY_BINARY="$REPO_ROOT/target/release/factory-evidence-qualify"
FACTORY_EVIDENCE_QUALIFY_SHA256=$(
  sha256sum "$FACTORY_EVIDENCE_QUALIFY_BINARY" | cut -d' ' -f1
)

if [[ -x "$ANSIBLE_ROOT/.venv/bin/ansible-playbook" ]]; then
  ANSIBLE_PLAYBOOK="$ANSIBLE_ROOT/.venv/bin/ansible-playbook"
else
  ANSIBLE_PLAYBOOK=ansible-playbook
fi

cd "$ANSIBLE_ROOT"
exec "$ANSIBLE_PLAYBOOK" \
  -i inventory/tofu.sh \
  site.yml \
  --tags session13 \
  -e "factory_repo_bundle=$FACTORY_BUNDLE" \
  -e "factory_repo_revision=$FACTORY_REVISION" \
  -e "factoryctl_binary=$FACTORYCTL_BINARY" \
  -e "factoryctl_sha256=$FACTORYCTL_SHA256" \
  -e "factory_supervisor_binary=$FACTORY_SUPERVISOR_BINARY" \
  -e "factory_supervisor_sha256=$FACTORY_SUPERVISOR_SHA256" \
  -e "factory_evidence_qualify_binary=$FACTORY_EVIDENCE_QUALIFY_BINARY" \
  -e "factory_evidence_qualify_sha256=$FACTORY_EVIDENCE_QUALIFY_SHA256" \
  "$@"
