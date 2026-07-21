#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)

if ! gh api repos/JacobStephens2/patchyard/branches/master/protection >/dev/null 2>&1; then
  echo "GitHub import blocked: GH_TOKEN cannot read or administer branch protection." >&2
  exit 1
fi

"$REPO_ROOT/infra/tofu.sh" github init -reconfigure

if ! "$REPO_ROOT/infra/tofu.sh" github state show github_repository.factory >/dev/null 2>&1; then
  "$REPO_ROOT/infra/tofu.sh" github import github_repository.factory factory
fi

if ! "$REPO_ROOT/infra/tofu.sh" github state show github_branch_protection.master >/dev/null 2>&1; then
  "$REPO_ROOT/infra/tofu.sh" github import github_branch_protection.master factory:master
fi
