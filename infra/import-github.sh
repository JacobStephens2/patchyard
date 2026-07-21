#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)

export GH_TOKEN=${GH_FACTORY_ADMIN_PAT:-${GH_TOKEN:-}}
: "${GH_TOKEN:?set GH_FACTORY_ADMIN_PAT for GitHub administration}"

PROTECTION_PRESENT=true
if ! PROTECTION_ERROR=$(gh api \
  repos/JacobStephens2/patchyard/branches/master/protection 2>&1); then
  if [[ "$PROTECTION_ERROR" == *"Branch not protected (HTTP 404)"* ]]; then
    PROTECTION_PRESENT=false
  else
    echo "GitHub import blocked: the admin token cannot read branch protection." >&2
    exit 1
  fi
fi

"$REPO_ROOT/infra/tofu.sh" github init -reconfigure

if ! "$REPO_ROOT/infra/tofu.sh" github state show github_repository.factory >/dev/null 2>&1; then
  "$REPO_ROOT/infra/tofu.sh" github import github_repository.factory factory
fi

if [[ "$PROTECTION_PRESENT" == true ]] && \
  ! "$REPO_ROOT/infra/tofu.sh" github state show github_branch_protection.master >/dev/null 2>&1; then
  "$REPO_ROOT/infra/tofu.sh" github import github_branch_protection.master factory:master
elif [[ "$PROTECTION_PRESENT" == false ]]; then
  echo "master has no protection rule; the reviewed OpenTofu apply will create it."
fi
