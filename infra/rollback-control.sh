#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
MODE=${1:-}
SSH_ARGS=(-i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=accept-new)

require_clean_revision() {
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
    echo 'rollback requires a committed, clean operator checkout' >&2
    exit 2
  fi
}

resolve_reviewed_revision() {
  local revision=$1
  git -C "$REPO_ROOT" fetch --quiet origin master
  local resolved
  resolved=$(git -C "$REPO_ROOT" rev-parse --verify "$revision^{commit}")
  git -C "$REPO_ROOT" merge-base --is-ancestor "$resolved" origin/master || {
    echo 'rollback target must already be merged into origin/master' >&2
    exit 2
  }
  printf '%s\n' "$resolved"
}

control_ip() {
  local inventory control_host
  inventory=$("$REPO_ROOT/infra/ansible/inventory/tofu.sh")
  control_host=$(jq -r '.control_plane.hosts[0]' <<<"$inventory")
  jq -er --arg host "$control_host" '._meta.hostvars[$host].ansible_host' <<<"$inventory"
}

installed_revision() {
  local address=$1
  ssh "${SSH_ARGS[@]}" "conductor@$address" 'git -C /opt/patchyard rev-parse HEAD'
}

capture_durable_state() {
  local address=$1 destination=$2
  ssh "${SSH_ARGS[@]}" "conductor@$address" 'sudo /bin/bash -s' >"$destination" <<'REMOTE'
set -euo pipefail
socket=/run/patchyard-postgres
database=patchyard
while IFS=$'\t' read -r schema table; do
  count=$(runuser -u postgres -- psql --host="$socket" --dbname="$database" \
    --tuples-only --no-align --command="SELECT count(*) FROM \"$schema\".\"$table\"")
  printf 'row\t%s.%s\t%s\n' "$schema" "$table" "$count"
done < <(runuser -u postgres -- psql --host="$socket" --dbname="$database" \
  --tuples-only --no-align --field-separator=$'\t' \
  --command="SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('factory', 'public') ORDER BY schemaname, tablename")
for root in artifacts proposer-inbox; do
  while IFS= read -r -d '' path; do
    relative=${path#"/var/lib/patchyard/$root/"}
    printf 'file\t%s/%s\t%s\n' "$root" "$relative" "$(sha256sum "$path" | cut -d' ' -f1)"
  done < <(find "/var/lib/patchyard/$root" -type f -print0 | sort -z)
done
REMOTE
}

case "$MODE" in
  plan)
    require_clean_revision
    target=${2:?usage: infra/rollback-control.sh plan <merged-revision> /absolute/output/directory}
    output_dir=${3:-}
    [[ "$output_dir" == /* ]] || exit 2
    target=$(resolve_reviewed_revision "$target")
    address=$(control_ip)
    current=$(resolve_reviewed_revision "$(installed_revision "$address")")
    target_migrations=$(git -C "$REPO_ROOT" show "$target:infra/ansible/group_vars/all.yml" \
      | sed -n 's/^factory_migration_count:[[:space:]]*//p')
    current_migrations=$(git -C "$REPO_ROOT" show "$current:infra/ansible/group_vars/all.yml" \
      | sed -n 's/^factory_migration_count:[[:space:]]*//p')
    [[ "$target_migrations" =~ ^[0-9]+$ && "$target_migrations" == "$current_migrations" ]] || {
      echo 'automatic application rollback requires equal migration counts' >&2
      exit 2
    }
    install -d -m 0700 "$output_dir"
    manifest="$output_dir/control-rollback.json"
    jq -n --arg target_revision "$target" --arg return_revision "$current" \
      --arg target_tree "$(git -C "$REPO_ROOT" rev-parse "$target^{tree}")" \
      --arg return_tree "$(git -C "$REPO_ROOT" rev-parse "$current^{tree}")" \
      --argjson migration_count "$current_migrations" \
      --arg created_at "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
      '{schema_version:1,target_revision:$target_revision,target_tree:$target_tree,return_revision:$return_revision,return_tree:$return_tree,migration_count:$migration_count,created_at:$created_at,scope:"application-binaries-config-and-checkout",durable_state:"must-match-before-and-after"}' \
      >"$manifest"
    sha256sum "$manifest" >"$manifest.sha256"
    echo "review $manifest and $manifest.sha256, then run apply"
    ;;
  apply)
    require_clean_revision
    manifest=${2:?usage: infra/rollback-control.sh apply /absolute/control-rollback.json}
    [[ "$manifest" == /* && -f "$manifest" && -f "$manifest.sha256" ]] || exit 2
    : "${PATCHYARD_ROLLBACK_APPROVED:?set PATCHYARD_ROLLBACK_APPROVED=yes after manifest review}"
    [[ "$PATCHYARD_ROLLBACK_APPROVED" == yes ]] || exit 2
    (cd "$(dirname "$manifest")" && sha256sum --check "$(basename "$manifest").sha256")
    jq -e '.schema_version == 1 and .scope == "application-binaries-config-and-checkout" and .durable_state == "must-match-before-and-after" and (.target_revision | test("^[0-9a-f]{40}$")) and (.return_revision | test("^[0-9a-f]{40}$"))' \
      "$manifest" >/dev/null
    target=$(jq -r .target_revision "$manifest")
    target=$(resolve_reviewed_revision "$target")
    return_revision=$(resolve_reviewed_revision "$(jq -r .return_revision "$manifest")")
    [[ "$target" == "$(jq -r .target_revision "$manifest")" ]] || exit 2
    [[ "$(git -C "$REPO_ROOT" rev-parse "$target^{tree}")" == "$(jq -r .target_tree "$manifest")" ]] || exit 2
    [[ "$(git -C "$REPO_ROOT" rev-parse "$return_revision^{tree}")" == "$(jq -r .return_tree "$manifest")" ]] || exit 2

    address=$(control_ip)
    [[ "$(installed_revision "$address")" == "$return_revision" ]] || {
      echo 'installed revision changed after rollback plan review' >&2
      exit 2
    }
    result_root=${manifest%.json}
    before_state="$result_root.durable-before.tsv"
    after_state="$result_root.durable-after.tsv"
    result_file="$result_root.result.json"
    [[ ! -e "$before_state" && ! -e "$after_state" && ! -e "$result_file" ]] || {
      echo 'rollback evidence files already exist' >&2
      exit 2
    }
    capture_durable_state "$address" "$before_state"

    rollback_root=$(mktemp -d /tmp/patchyard-rollback.XXXXXX)
    trap 'git -C "$REPO_ROOT" worktree remove --force "$rollback_root" >/dev/null 2>&1 || true' EXIT
    git -C "$REPO_ROOT" worktree add --detach "$rollback_root" "$target"
    "$rollback_root/infra/tofu.sh" digitalocean init -reconfigure
    "$rollback_root/infra/ansible/converge.sh"
    installed=$(installed_revision "$address")
    [[ "$installed" == "$target" ]] || exit 3
    ssh "${SSH_ARGS[@]}" "conductor@$address" \
      'sudo systemctl is-active --quiet postgresql factory-dashboard factory-supervisor caddy && sudo curl --fail --silent --unix-socket /run/patchyard-dashboard/dashboard.sock http://localhost/healthz'
    ssh "${SSH_ARGS[@]}" "conductor@$address" \
      'sudo systemctl stop factory-dashboard.service factory-supervisor.service'
    resume_services=true
    resume_after_capture() {
      if [[ "$resume_services" == true ]]; then
        ssh "${SSH_ARGS[@]}" "conductor@$address" \
          'sudo systemctl start factory-dashboard.service factory-supervisor.service' || true
      fi
    }
    trap 'resume_after_capture; git -C "$REPO_ROOT" worktree remove --force "$rollback_root" >/dev/null 2>&1 || true' EXIT
    capture_durable_state "$address" "$after_state"
    cmp --silent "$before_state" "$after_state" || {
      diff --unified "$before_state" "$after_state" >&2 || true
      echo 'rollback changed durable row counts or file hashes' >&2
      exit 3
    }
    before_sha256=$(sha256sum "$before_state" | cut -d' ' -f1)
    after_sha256=$(sha256sum "$after_state" | cut -d' ' -f1)
    jq -n --arg target_revision "$target" --arg return_revision "$return_revision" \
      --arg before_sha256 "$before_sha256" --arg after_sha256 "$after_sha256" \
      --arg completed_at "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
      '{schema_version:1,target_revision:$target_revision,return_revision:$return_revision,before_sha256:$before_sha256,after_sha256:$after_sha256,durable_state:"verified_equal",completed_at:$completed_at}' \
      >"$result_file"
    resume_after_capture
    resume_services=false
    ssh "${SSH_ARGS[@]}" "conductor@$address" \
      'sudo systemctl is-active --quiet postgresql factory-dashboard factory-supervisor caddy && sudo curl --fail --silent --unix-socket /run/patchyard-dashboard/dashboard.sock http://localhost/healthz'
    git -C "$REPO_ROOT" worktree remove "$rollback_root"
    trap - EXIT
    printf 'rollback_complete revision=%s durable_state_sha256=%s\n' "$target" "$after_sha256"
    ;;
  *)
    echo 'usage: infra/rollback-control.sh <plan|apply> ...' >&2
    exit 2
    ;;
esac
