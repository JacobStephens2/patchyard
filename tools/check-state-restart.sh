#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
: "${FACTORY_TEST_DATABASE_URL:?runtime role URL is required}"
POSTGRES_CONTAINER_ID=${POSTGRES_CONTAINER_ID:?PostgreSQL service container id is required}

cd "$REPO_ROOT"

RESTART_CHECK_TEMP=$(mktemp -d /tmp/patchyard-restart-check.XXXXXX)
trap 'rm -r -- "$RESTART_CHECK_TEMP"' EXIT
REQUEST_ID=$(tr -d '-' </proc/sys/kernel/random/uuid)
REQUEST_UUID="${REQUEST_ID:0:8}-${REQUEST_ID:8:4}-${REQUEST_ID:12:4}-${REQUEST_ID:16:4}-${REQUEST_ID:20:12}"
TRACE_ID=$(tr -d '-' </proc/sys/kernel/random/uuid)
printf 'server-restart idempotency fixture %s\n' "$REQUEST_UUID" \
  >"$RESTART_CHECK_TEMP/request.md"

FIRST_RESULT=$(DATABASE_URL="$FACTORY_TEST_DATABASE_URL" target/debug/factoryctl \
  request new "$RESTART_CHECK_TEMP/request.md" --id "$REQUEST_UUID" --trace-id "$TRACE_ID")
test "$FIRST_RESULT" = "$REQUEST_UUID created"

# Named crash boundary: restart PostgreSQL after the intake commit and before
# the caller's idempotent retry. The retry must find one row and one event.
docker restart "$POSTGRES_CONTAINER_ID" >/dev/null
for _ in $(seq 1 60); do
  if docker exec "$POSTGRES_CONTAINER_ID" pg_isready -U postgres -d patchyard_ci >/dev/null; then
    break
  fi
  sleep 1
done
docker exec "$POSTGRES_CONTAINER_ID" pg_isready -U postgres -d patchyard_ci

SECOND_RESULT=$(DATABASE_URL="$FACTORY_TEST_DATABASE_URL" target/debug/factoryctl \
  request new "$RESTART_CHECK_TEMP/request.md" --id "$REQUEST_UUID" --trace-id "$TRACE_ID")
test "$SECOND_RESULT" = "$REQUEST_UUID existing"

REQUEST_COUNT=$(docker exec "$POSTGRES_CONTAINER_ID" psql --tuples-only --no-align \
  --username=postgres --dbname=patchyard_ci \
  --command="SELECT count(*) FROM factory.requests WHERE id = '$REQUEST_UUID'")
EVENT_COUNT=$(docker exec "$POSTGRES_CONTAINER_ID" psql --tuples-only --no-align \
  --username=postgres --dbname=patchyard_ci \
  --command="SELECT count(*) FROM factory.events WHERE request_id = '$REQUEST_UUID'")
test "$REQUEST_COUNT" = 1
test "$EVENT_COUNT" = 1

echo "server-restart boundary: idempotent retry converged"
