#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
POSTGRES_CONTAINER_ID=${POSTGRES_CONTAINER_ID:?GitHub PostgreSQL service container id is required}
DATABASE_URL=${DATABASE_URL:?admin DATABASE_URL is required}
FACTORY_TEST_DATABASE_URL=${FACTORY_TEST_DATABASE_URL:?runtime role URL is required}

cd "$REPO_ROOT"

for _ in $(seq 1 30); do
  if docker exec "$POSTGRES_CONTAINER_ID" pg_isready -U postgres -d patchyard_ci >/dev/null; then
    break
  fi
  sleep 1
done
docker exec "$POSTGRES_CONTAINER_ID" pg_isready -U postgres -d patchyard_ci

docker exec -i "$POSTGRES_CONTAINER_ID" \
  psql --set=ON_ERROR_STOP=1 --username=postgres --dbname=postgres \
  < infra/ansible/roles/control_plane/files/postgresql-roles.sql

docker exec "$POSTGRES_CONTAINER_ID" \
  psql --set=ON_ERROR_STOP=1 --username=postgres --dbname=postgres \
  --command="ALTER DATABASE patchyard_ci OWNER TO patchyard_owner"
docker exec "$POSTGRES_CONTAINER_ID" \
  psql --set=ON_ERROR_STOP=1 --username=postgres --dbname=patchyard_ci \
  --command="ALTER ROLE patchyard_migrator IN DATABASE patchyard_ci SET role TO patchyard_owner"

cargo build --locked --package factoryctl
DATABASE_URL="postgresql://patchyard_migrator@localhost:5432/patchyard_ci?sslmode=disable" \
  target/debug/factoryctl migrate

docker exec -i "$POSTGRES_CONTAINER_ID" \
  psql --set=ON_ERROR_STOP=1 --username=postgres --dbname=patchyard_ci \
  < infra/ansible/roles/control_plane/files/postgresql-grants.sql

DATABASE_URL="$FACTORY_TEST_DATABASE_URL" \
  target/debug/factoryctl status 00000000-0000-4000-8000-000000000001 \
  >/dev/null 2>&1 && {
    echo "unexpected CI fixture exists before state tests" >&2
    exit 1
  }

echo "disposable PostgreSQL state service: prepared"
