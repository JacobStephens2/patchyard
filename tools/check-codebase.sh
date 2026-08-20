#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
source "$REPO_ROOT/tools/rust-tool-versions.env"
cd "$REPO_ROOT"

# SUSPENDED until the map destination. Set back to 1 in
# https://github.com/JacobStephens2/patchyard/issues/261.
#
# The projection only regenerates on Linux x86_64, which the machine driving
# the map is not, so enforcing byte-identity charged every PR a blind CI round
# trip just to read the new numbers. Drift is still computed and printed on
# every run - only the failure is withheld - so A102's /codebase view can be
# made true again from any CI log, and re-arming is this one line.
CODEBASE_PROJECTION_ENFORCED=0

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
  if [[ "$CODEBASE_PROJECTION_ENFORCED" == "1" ]]; then
    exit 1
  fi
  echo "codebase metrics projection: STALE, enforcement suspended (issue 261)" >&2
  echo "the diff above is the exact refresh; A102 /codebase renders the stale file" >&2
  exit 0
}
echo "codebase metrics projection: pass"
