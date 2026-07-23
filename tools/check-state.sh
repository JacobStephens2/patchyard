#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
: "${DATABASE_URL:?admin DATABASE_URL is required}"
: "${FACTORY_TEST_DATABASE_URL:?runtime role URL is required}"
: "${FACTORY_TEST_ADMIN_DATABASE_URL:?test admin URL is required}"
: "${POSTGRES_CONTAINER_ID:?PostgreSQL service container id is required}"

cd "$REPO_ROOT"

cargo test --locked --package factory-core --test postgres_state -- --test-threads=1

STATE_CHECK_TEMP=$(mktemp -d /tmp/patchyard-state-check.XXXXXX)
trap 'rm -r -- "$STATE_CHECK_TEMP"' EXIT
target/debug/factoryctl schema-mermaid --output "$STATE_CHECK_TEMP/schema.mmd"
cmp --silent docs/schema.mmd "$STATE_CHECK_TEMP/schema.mmd" || {
  diff --unified docs/schema.mmd "$STATE_CHECK_TEMP/schema.mmd" || true
  echo "docs/schema.mmd does not match the migrated PostgreSQL catalog" >&2
  exit 1
}
target/debug/factoryctl schema-json \
  | jq --exit-status '
      (.relations | map(select(.kind == "table")) | length == 9)
      and (.foreign_keys | length >= 8)
      and (.indexes | length >= 12)
      and (.roles | map(.name) | index("grafana_ro") != null)
      and (.grants | map(select(.grantee == "grafana_ro")) | length > 0)
    ' >/dev/null

tools/check-state-restart.sh
echo "state contract: pass"
