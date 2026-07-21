#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

tools/check-constitution.sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace --all-features
cargo audit --deny warnings
cargo deny check --allow license-not-encountered
cargo vet --locked
cargo machete
./model/check-model.sh

if [[ -n "${FACTORY_TEST_DATABASE_URL:-}" ]]; then
  tools/check-state.sh
fi
