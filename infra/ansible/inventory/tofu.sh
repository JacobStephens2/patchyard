#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
exec "$REPO_ROOT/infra/tofu.sh" digitalocean output -json ansible_inventory
