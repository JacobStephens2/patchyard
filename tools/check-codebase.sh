#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
source "$REPO_ROOT/tools/rust-tool-versions.env"
cd "$REPO_ROOT"

if [[ "$(tokei --version | awk '{print $2}')" != "$TOKEI_VERSION" ]]; then
  echo "tokei $TOKEI_VERSION is required; run tools/install-tokei.sh" >&2
  exit 1
fi
if ! tokei --version | grep -Fq 'serialization support: json'; then
  echo "the pinned tokei build lacks JSON serialization support" >&2
  exit 1
fi

CODEBASE_TEMP=$(mktemp -d /tmp/patchyard-codebase.XXXXXX)
trap 'rm -r -- "$CODEBASE_TEMP"' EXIT

tokei crates migrations assets --output json > "$CODEBASE_TEMP/product.json"
tokei infra worker preview --output json > "$CODEBASE_TEMP/infrastructure.json"
tokei tools model fixtures .github Cargo.toml Cargo.lock rust-toolchain.toml \
  --output json > "$CODEBASE_TEMP/tooling.json"
tokei docs policy research reviews rulings-queue AGENTS.md PLAN.md SPEC.md README.md \
  --exclude docs/codebase-metrics.json \
  --output json > "$CODEBASE_TEMP/governance.json"

python3 tools/codebase-metrics.py \
  --repo-root "$REPO_ROOT" \
  --tokei-version "$TOKEI_VERSION" \
  --product "$CODEBASE_TEMP/product.json" \
  --infrastructure "$CODEBASE_TEMP/infrastructure.json" \
  --tooling "$CODEBASE_TEMP/tooling.json" \
  --governance "$CODEBASE_TEMP/governance.json" \
  --output "$CODEBASE_TEMP/codebase-metrics.json"

if [[ "${1:-}" == "--write" ]]; then
  install -m 0644 "$CODEBASE_TEMP/codebase-metrics.json" \
    docs/codebase-metrics.json
  echo "docs/codebase-metrics.json generated"
  exit 0
fi
if [[ $# -ne 0 ]]; then
  echo "usage: tools/check-codebase.sh [--write]" >&2
  exit 2
fi

cmp --silent docs/codebase-metrics.json "$CODEBASE_TEMP/codebase-metrics.json" || {
  diff --unified docs/codebase-metrics.json "$CODEBASE_TEMP/codebase-metrics.json" || true
  echo "docs/codebase-metrics.json is not the byte-identical pinned tokei projection" >&2
  exit 1
}
echo "codebase metrics projection: pass"
