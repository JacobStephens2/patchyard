#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${DB_REPLICA_HOST:?missing DB replica host}"
: "${DB_REPLICA_MYSQL_USER:?missing DB replica MySQL user}"
: "${DB_REPLICA_MYSQL_PASS:?missing DB replica MySQL password}"

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
INVENTORY_JSON=$("$REPO_ROOT/infra/ansible/inventory/tofu.sh")
CONTROL_HOST=$(jq -r '.control_plane.hosts[0]' <<<"$INVENTORY_JSON")
CONTROL_IP=$(jq -r --arg host "$CONTROL_HOST" '._meta.hostvars[$host].ansible_host' <<<"$INVENTORY_JSON")
SNAPSHOT_DATE=${SNAPSHOT_DATE:-$(date -u +%F)}
SSH_ARGS=(-i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=accept-new)

BOOTSTRAP_TEMP=$(mktemp -d /tmp/patchyard-snapshot-bootstrap.XXXXXX)
trap 'rm -r -- "$BOOTSTRAP_TEMP"' EXIT
SCHEMA_SQL=$BOOTSTRAP_TEMP/fieldbook-training-schema.sql

MYSQL_PWD="$DB_REPLICA_MYSQL_PASS" mysqldump \
  -h "$DB_REPLICA_HOST" -u "$DB_REPLICA_MYSQL_USER" \
  --no-data --skip-triggers --single-transaction --set-gtid-purged=OFF \
  --default-character-set=latin1 fieldbook_training >"$SCHEMA_SQL"
! grep -Eiq '^[[:space:]]*(INSERT|REPLACE|LOAD[[:space:]]+DATA)[[:space:]]' "$SCHEMA_SQL"

REMOTE_SCHEMA="/var/tmp/patchyard-schema-$SNAPSHOT_DATE.sql"
scp "${SSH_ARGS[@]}" "$SCHEMA_SQL" "conductor@$CONTROL_IP:$REMOTE_SCHEMA"
ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo chown factory-manager:factory-manager "$REMOTE_SCHEMA"
ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo -u factory-manager /usr/local/sbin/build-redacted-snapshot \
  "$REMOTE_SCHEMA" "$SNAPSHOT_DATE" /var/lib/patchyard/snapshots
ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo /usr/local/sbin/patchyard-snapshot-metric
ssh "${SSH_ARGS[@]}" "conductor@$CONTROL_IP" \
  sudo /usr/bin/shred --remove "$REMOTE_SCHEMA"
