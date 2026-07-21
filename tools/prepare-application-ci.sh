#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

tools/install-rustup.sh
tools/install-rust-tools.sh
python3 -m pip install --requirement model/requirements-model.txt
