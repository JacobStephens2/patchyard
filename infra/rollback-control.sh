#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
MODE=${1:-}
SSH_ARGS=(-i /var/lib/conductor/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes)

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

revision_uses_inventory_qualifier() {
  git -C "$REPO_ROOT" cat-file -e \
    "$1:infra/ansible/roles/control_plane/templates/qualify-factory-control.j2" \
    2>/dev/null
}

qualification_environment_inventory() {
  local revision=$1 group_vars qualifier declared_chromium qualifier_chromium
  local chromium_common='' grafana_grants migration_count qualified_migrations
  local mirror_block='' mirror_sha256=''
  group_vars=$(git -C "$REPO_ROOT" show \
    "$revision:infra/ansible/group_vars/all.yml") || exit 2
  declared_chromium=$(sed -n 's/^chromium_nevra:[[:space:]]*//p' \
    <<<"$group_vars")
  migration_count=$(sed -n 's/^factory_migration_count:[[:space:]]*//p' \
    <<<"$group_vars")

  if revision_uses_inventory_qualifier "$revision"; then
    qualifier=$(git -C "$REPO_ROOT" show \
      "$revision:infra/ansible/roles/control_plane/templates/qualify-factory-control.j2")
    for reference in \
      '{{ chromium_nevra | quote }}' \
      '{{ chromium_common_nevra | quote }}' \
      '{{ factory_grafana_column_privilege_count }}' \
      '{{ factory_migration_count }}' \
      '{% for rpm in chromium_rpm_mirror %}' \
      'chromium_rpm_mirror_directory'; do
      grep -Fq "$reference" <<<"$qualifier" || {
        echo "revision $revision qualifier does not read the complete declared environment inventory" >&2
        exit 2
      }
    done
    qualifier_chromium=$declared_chromium
    chromium_common=$(sed -n \
      's/^chromium_common_nevra:[[:space:]]*//p' <<<"$group_vars")
    grafana_grants=$(sed -n \
      's/^factory_grafana_column_privilege_count:[[:space:]]*//p' \
      <<<"$group_vars")
    qualified_migrations=$migration_count
    mirror_block=$(awk '
      /^chromium_rpm_mirror_directory:/ { capture = 1 }
      capture && /^age_nevra:/ { exit }
      capture { print }
    ' <<<"$group_vars")
    mirror_sha256=$(sha256sum <<<"$mirror_block" | cut -d' ' -f1)
  else
    qualifier=$(git -C "$REPO_ROOT" show \
      "$revision:infra/ansible/roles/control_plane/files/qualify-factory-control")
    # These sed programs deliberately match literal command substitutions in
    # the legacy qualifier; expanding them would execute the local rpm query.
    # shellcheck disable=SC2016
    qualifier_chromium=$(sed -n \
      's/^test "$(rpm -q chromium)" = //p' <<<"$qualifier")
    # shellcheck disable=SC2016
    chromium_common=$(sed -n \
      's/^test "$(rpm -q chromium-common)" = //p' <<<"$qualifier")
    grafana_grants=$(sed -n \
      "/information_schema.column_privileges/s/.*= \([0-9][0-9]*\)$/\1/p" \
      <<<"$qualifier")
    qualified_migrations=$(sed -n \
      "/SELECT count(\*) FROM public\._sqlx_migrations/s/.*= \([0-9][0-9]*\)$/\1/p" \
      <<<"$qualifier")
  fi

  [[ -n "$declared_chromium" \
    && "$declared_chromium" == "$qualifier_chromium" \
    && "$migration_count" =~ ^[0-9]+$ \
    && "$qualified_migrations" =~ ^[0-9]+$ \
    && "$migration_count" == "$qualified_migrations" \
    && "$grafana_grants" =~ ^[0-9]+$ \
    && ( -z "$chromium_common" || "$chromium_common" != *[[:space:]]* ) \
    && ( -z "$mirror_sha256" || "$mirror_sha256" =~ ^[0-9a-f]{64}$ ) ]] || {
    echo "revision $revision has an incomplete or internally inconsistent qualification environment" >&2
    exit 2
  }
  jq -cn \
    --arg chromium_nevra "$declared_chromium" \
    --arg chromium_common_nevra "$chromium_common" \
    --argjson grafana_column_privilege_count "$grafana_grants" \
    --argjson migration_count "$migration_count" \
    --argjson qualification_migration_count "$qualified_migrations" \
    --arg mirror_sha256 "$mirror_sha256" \
    '{chromium_nevra:$chromium_nevra,chromium_common_nevra:$chromium_common_nevra,grafana_column_privilege_count:$grafana_column_privilege_count,migration_count:$migration_count,qualification_migration_count:$qualification_migration_count,mirror_sha256:$mirror_sha256}'
}

control_target() {
  local inventory control_host address
  inventory=$("$REPO_ROOT/infra/ansible/inventory/tofu.sh")
  control_host=$(jq -er '.control_plane.hosts[0]' <<<"$inventory")
  address=$(jq -er --arg host "$control_host" \
    '._meta.hostvars[$host].ansible_host' <<<"$inventory")
  printf '%s\t%s\n' "$control_host" "$address"
}

write_boundary_inventory() {
  local host=$1 address=$2 destination=$3
  jq -n --arg host "$host" --arg address "$address" '
    {all:{vars:{
      ansible_user:"conductor",
      ansible_ssh_private_key_file:"/var/lib/conductor/.ssh/id_ed25519",
      ansible_ssh_common_args:"-o BatchMode=yes -o StrictHostKeyChecking=yes"
    },children:{control_plane:{hosts:{($host):{
      ansible_host:$address,
      factory_role:"control-plane"
    }}}}}}
  ' >"$destination"
  chmod 0600 "$destination"
}

validate_boundary_inventory() {
  local inventory=$1 expected_host=$2 expected_address=$3 rendered
  local ansible_inventory="$REPO_ROOT/infra/ansible/.venv/bin/ansible-inventory"
  [[ -x "$ansible_inventory" ]] || ansible_inventory=ansible-inventory
  rendered=$("$ansible_inventory" -i "$inventory" --list) || {
    echo 'rollback boundary inventory could not be parsed' >&2
    return 2
  }
  jq -e --arg host "$expected_host" --arg address "$expected_address" '
    (.control_plane.hosts // []) == [$host]
    and ._meta.hostvars[$host].ansible_host == $address
    and ._meta.hostvars[$host].factory_role == "control-plane"
  ' <<<"$rendered" >/dev/null || {
    echo 'rollback boundary inventory did not resolve the reviewed control host' >&2
    return 2
  }
}

installed_revision() {
  local address=$1
  ssh "${SSH_ARGS[@]}" "conductor@$address" \
    'sudo -n runuser -u factory-manager -- git -C /opt/patchyard rev-parse HEAD'
}

capture_durable_state() {
  local address=$1 destination=$2
  ssh "${SSH_ARGS[@]}" "conductor@$address" 'sudo /bin/bash -s' >"$destination" <<'REMOTE'
set -euo pipefail
socket=/run/patchyard-postgres
database=patchyard
while IFS=$'\t' read -r schema table; do
  count=$(runuser -u postgres -- psql --no-psqlrc --host="$socket" --dbname="$database" \
    --tuples-only --no-align --command="SELECT count(*) FROM \"$schema\".\"$table\"")
  digest=$(runuser -u postgres -- psql --no-psqlrc --host="$socket" --dbname="$database" \
    --tuples-only --no-align \
    --command="COPY (SELECT row_to_json(t)::text FROM \"$schema\".\"$table\" AS t ORDER BY row_to_json(t)::text) TO STDOUT" \
    | sha256sum | cut -d' ' -f1)
  printf 'row\t%s.%s\t%s\n' "$schema" "$table" "$count"
  printf 'table-sha256\t%s.%s\t%s\n' "$schema" "$table" "$digest"
  if [[ "$schema.$table" == factory.login_challenges ]]; then
    runuser -u postgres -- psql --no-psqlrc --host="$socket" --dbname="$database" \
      --tuples-only --no-align \
      --command="COPY (SELECT row_to_json(t)::text FROM factory.login_challenges AS t ORDER BY row_to_json(t)::text) TO STDOUT" \
      | while IFS= read -r challenge; do
          printf 'login-challenge-sha256\t%s\n' \
            "$(printf '%s' "$challenge" | sha256sum | cut -d' ' -f1)"
        done
  fi
  if [[ "$schema.$table" == factory.audit_events ]]; then
    runuser -u postgres -- psql --no-psqlrc --host="$socket" --dbname="$database" \
      --tuples-only --no-align \
      --command="COPY (SELECT row_to_json(t)::text FROM factory.audit_events AS t ORDER BY row_to_json(t)::text) TO STDOUT" \
      | while IFS= read -r audit_row; do
          printf 'audit-row-sha256\t%s\n' \
            "$(printf '%s' "$audit_row" | sha256sum | cut -d' ' -f1)"
        done
  fi
done < <(runuser -u postgres -- psql --no-psqlrc --host="$socket" --dbname="$database" \
  --tuples-only --no-align --field-separator=$'\t' \
  --command="SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('factory', 'public') ORDER BY schemaname, tablename")
runuser -u postgres -- psql --no-psqlrc --host="$socket" --dbname="$database" \
  --tuples-only --no-align \
  --command="SELECT 'audit' || E'\\t' || COALESCE(max(id),0) || E'\\t' || count(*) FROM factory.audit_events"
for root in artifacts proposer-inbox; do
  while IFS= read -r -d '' path; do
    relative=${path#"/var/lib/patchyard/$root/"}
    printf 'file\t%s/%s\t%s\n' "$root" "$relative" "$(sha256sum "$path" | cut -d' ' -f1)"
  done < <(find "/var/lib/patchyard/$root" -type f -print0 | sort -z)
done
REMOTE
}

unexpected_rollback_audits() {
  local address=$1 minimum_id=$2
  [[ "$minimum_id" =~ ^[0-9]+$ ]] || return 2
  # The only client-expanded value is validated as decimal digits above.
  # shellcheck disable=SC2029
  ssh "${SSH_ARGS[@]}" "conductor@$address" \
    "sudo -n runuser -u postgres -- psql --no-psqlrc --host=/run/patchyard-postgres --dbname=patchyard --tuples-only --no-align --command=\"SELECT count(*) FROM factory.audit_events WHERE id > $minimum_id AND (action <> 'account.provisioned' OR client_key <> 'factoryctl')\""
}

set_rollback_boundary() {
  local state=$1
  local ansible_playbook="$REPO_ROOT/infra/ansible/.venv/bin/ansible-playbook"
  [[ -x "$ansible_playbook" ]] || ansible_playbook=ansible-playbook
  validate_boundary_inventory "$boundary_inventory" "$control_host" "$address"
  (
    cd "$REPO_ROOT/infra/ansible" &&
    "$ansible_playbook" -i "$boundary_inventory" rollback-boundary.yml \
      -e "factory_rollback_boundary=$state"
  )
}

deploy_and_qualify_revision() {
  local revision=$1 label=$2
  rollback_root=$(mktemp -d "/tmp/patchyard-${label}.XXXXXX") || return
  git -C "$REPO_ROOT" worktree add --detach "$rollback_root" "$revision" || return
  (
    cd "$rollback_root" &&
    ./infra/tofu.sh digitalocean init -reconfigure &&
    ./infra/ansible/converge.sh -e factory_rollback_boundary=true
  ) || return
  [[ "$(installed_revision "$address")" == "$revision" ]] || {
    echo "$label installed an unexpected revision" >&2
    return 3
  }
  (
    cd "$rollback_root" &&
    ./infra/ansible/qualify.sh
  ) || return
  ssh "${SSH_ARGS[@]}" "conductor@$address" \
    'sudo systemctl stop patchyard-backup.timer && sudo systemctl is-active --quiet postgresql factory-dashboard factory-supervisor caddy && ! sudo systemctl is-active --quiet patchyard-backup.timer && sudo curl --fail --silent --unix-socket /run/patchyard-dashboard/dashboard.sock http://localhost/healthz' \
    || return
  git -C "$REPO_ROOT" worktree remove "$rollback_root" || return
  rollback_root=''
}

stable_durable_state() {
  local source=$1 destination=$2
  awk -F '\t' '$1 != "audit" && $1 != "audit-row-sha256" && $1 != "login-challenge-sha256" && !(($1 == "row" || $1 == "table-sha256") && ($2 == "factory.audit_events" || $2 == "factory.login_challenges"))' \
    "$source" >"$destination"
}

audit_hashes() {
  awk -F '\t' '$1 == "audit-row-sha256" {print $2}' "$1" | LC_ALL=C sort
}

challenge_hashes() {
  awk -F '\t' '$1 == "login-challenge-sha256" {print $2}' "$1" | LC_ALL=C sort
}

challenge_count() {
  awk -F '\t' '$1 == "login-challenge-sha256" {count += 1} END {print count + 0}' "$1"
}

case "$MODE" in
  plan)
    require_clean_revision
    target=${2:?usage: infra/rollback-control.sh plan <merged-revision> /absolute/output/directory}
    output_dir=${3:-}
    [[ "$output_dir" == /* ]] || exit 2
    target=$(resolve_reviewed_revision "$target")
    IFS=$'\t' read -r control_host address < <(control_target)
    current=$(resolve_reviewed_revision "$(installed_revision "$address")")
    if revision_uses_inventory_qualifier "$current"; then
      echo 'A112 application-under-current-contract rollback is not implemented; whole-revision rollback is disabled' >&2
      exit 2
    fi
    target_qualification_environment=$(qualification_environment_inventory "$target")
    current_qualification_environment=$(qualification_environment_inventory "$current")
    [[ "$target_qualification_environment" == \
      "$current_qualification_environment" ]] || {
      echo 'automatic whole-revision rollback requires an exact qualification-environment match' >&2
      exit 2
    }
    current_migrations=$(jq -r .migration_count \
      <<<"$current_qualification_environment")
    current_qualification_migrations=$(jq -r .qualification_migration_count \
      <<<"$current_qualification_environment")
    install -d -m 0700 "$output_dir"
    manifest="$output_dir/control-rollback.json"
    jq -n --arg target_revision "$target" --arg return_revision "$current" \
      --arg control_host "$control_host" --arg control_address "$address" \
      --arg target_tree "$(git -C "$REPO_ROOT" rev-parse "$target^{tree}")" \
      --arg return_tree "$(git -C "$REPO_ROOT" rev-parse "$current^{tree}")" \
      --argjson migration_count "$current_migrations" \
      --argjson qualification_migration_count "$current_qualification_migrations" \
      --argjson qualification_environment "$current_qualification_environment" \
      --arg created_at "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
      '{schema_version:3,target_revision:$target_revision,target_tree:$target_tree,return_revision:$return_revision,return_tree:$return_tree,control_host:$control_host,control_address:$control_address,migration_count:$migration_count,qualification_migration_count:$qualification_migration_count,qualification_environment:$qualification_environment,created_at:$created_at,scope:"application-binaries-config-and-checkout",durable_state:"must-preserve-with-declared-account-audits"}' \
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
    jq -e '.schema_version == 3 and .scope == "application-binaries-config-and-checkout" and .durable_state == "must-preserve-with-declared-account-audits" and (.migration_count | type == "number") and (.qualification_migration_count | type == "number") and (.qualification_environment | type == "object") and (.target_revision | test("^[0-9a-f]{40}$")) and (.return_revision | test("^[0-9a-f]{40}$")) and (.control_host | test("^[A-Za-z0-9.-]+$")) and (.control_address | test("^([0-9]{1,3}\\.){3}[0-9]{1,3}$"))' \
      "$manifest" >/dev/null
    target=$(jq -r .target_revision "$manifest")
    target=$(resolve_reviewed_revision "$target")
    return_revision=$(resolve_reviewed_revision "$(jq -r .return_revision "$manifest")")
    [[ "$target" == "$(jq -r .target_revision "$manifest")" ]] || exit 2
    [[ "$(git -C "$REPO_ROOT" rev-parse "$target^{tree}")" == "$(jq -r .target_tree "$manifest")" ]] || exit 2
    [[ "$(git -C "$REPO_ROOT" rev-parse "$return_revision^{tree}")" == "$(jq -r .return_tree "$manifest")" ]] || exit 2
    if revision_uses_inventory_qualifier "$return_revision"; then
      echo 'A112 application-under-current-contract rollback is not implemented; whole-revision rollback is disabled' >&2
      exit 2
    fi
    target_qualification_environment=$(qualification_environment_inventory "$target")
    return_qualification_environment=$(qualification_environment_inventory \
      "$return_revision")
    manifest_qualification_environment=$(jq -c .qualification_environment \
      "$manifest")
    [[ "$target_qualification_environment" == \
      "$manifest_qualification_environment" \
      && "$return_qualification_environment" == \
        "$manifest_qualification_environment" \
      && "$(jq -r .migration_count <<<"$return_qualification_environment")" == \
        "$(jq -r .migration_count "$manifest")" \
      && "$(jq -r .qualification_migration_count \
        <<<"$return_qualification_environment")" == \
        "$(jq -r .qualification_migration_count "$manifest")" ]] || {
      echo 'rollback qualification environment changed after plan review' >&2
      exit 2
    }

    control_host=$(jq -r .control_host "$manifest")
    address=$(jq -r .control_address "$manifest")
    [[ "$(installed_revision "$address")" == "$return_revision" ]] || {
      echo 'installed revision changed after rollback plan review' >&2
      exit 2
    }
    result_root=${manifest%.json}
    before_state="$result_root.durable-before.tsv"
    target_state="$result_root.durable-target.tsv"
    recovered_state="$result_root.durable-recovered.tsv"
    before_stable="$result_root.durable-before-stable.tsv"
    target_stable="$result_root.durable-target-stable.tsv"
    recovered_stable="$result_root.durable-recovered-stable.tsv"
    result_file="$result_root.result.json"
    [[ ! -e "$before_state" && ! -e "$target_state" \
      && ! -e "$recovered_state" && ! -e "$before_stable" \
      && ! -e "$target_stable" && ! -e "$recovered_stable" \
      && ! -e "$result_file" ]] || {
      echo 'rollback evidence files already exist' >&2
      exit 2
    }
    "$REPO_ROOT/infra/ansible/converge.sh" --check-inputs
    boundary_inventory=$(mktemp --suffix=.json /tmp/patchyard-rollback-boundary.XXXXXX)
    write_boundary_inventory "$control_host" "$address" "$boundary_inventory"
    set_rollback_boundary enter
    boundary_entered=true
    return_qualified=false
    evidence_verification_pending=false
    rollback_root=''
    release_boundary_and_cleanup() {
      if [[ -n "$rollback_root" ]]; then
        git -C "$REPO_ROOT" worktree remove --force "$rollback_root" >/dev/null 2>&1 || true
        rollback_root=''
      fi
      if [[ "$boundary_entered" == true && "$return_qualified" != true ]]; then
        echo 'rollback failed before verified recovery; retrying the reviewed return revision' >&2
        if deploy_and_qualify_revision "$return_revision" rollback-emergency-recovery; then
          return_qualified=true
        elif [[ -n "$rollback_root" ]]; then
          git -C "$REPO_ROOT" worktree remove --force "$rollback_root" >/dev/null 2>&1 || true
          rollback_root=''
        fi
      fi
      if [[ "$boundary_entered" == true && "$return_qualified" == true \
        && "$evidence_verification_pending" != true ]]; then
        if set_rollback_boundary exit; then
          boundary_entered=false
        fi
      fi
      if [[ "$boundary_entered" == true ]]; then
        if [[ "$evidence_verification_pending" == true ]]; then
          echo 'rollback evidence did not verify; public boundary and reboot-durable backup exclusion remain in force for explicit release' >&2
        else
          echo 'rollback recovery did not qualify; public boundary and reboot-durable backup exclusion remain in force' >&2
        fi
      fi
      if [[ -n "${boundary_inventory:-}" ]]; then
        rm -f -- "$boundary_inventory"
        boundary_inventory=''
      fi
    }
    trap release_boundary_and_cleanup EXIT
    capture_durable_state "$address" "$before_state"
    before_audit_max=$(awk -F '\t' '$1 == "audit" {print $2}' "$before_state")
    before_audit_count=$(awk -F '\t' '$1 == "audit" {print $3}' "$before_state")
    [[ "$before_audit_max" =~ ^[0-9]+$ && "$before_audit_count" =~ ^[0-9]+$ ]] \
      || exit 3

    deploy_and_qualify_revision "$target" rollback-target
    capture_durable_state "$address" "$target_state"
    [[ "$(unexpected_rollback_audits "$address" "$before_audit_max")" == 0 ]] || {
      echo 'rollback target emitted an audit action outside declarative account provisioning' >&2
      evidence_verification_pending=true
      exit 3
    }
    deploy_and_qualify_revision "$return_revision" rollback-recovery
    return_qualified=true
    evidence_verification_pending=true
    capture_durable_state "$address" "$recovered_state"

    target_audit_count=$(awk -F '\t' '$1 == "audit" {print $3}' "$target_state")
    recovered_audit_count=$(awk -F '\t' '$1 == "audit" {print $3}' "$recovered_state")
    [[ "$before_audit_max" =~ ^[0-9]+$ && "$before_audit_count" =~ ^[0-9]+$ \
      && "$target_audit_count" =~ ^[0-9]+$ \
      && "$recovered_audit_count" =~ ^[0-9]+$ \
      && "$target_audit_count" -ge "$before_audit_count" \
      && "$recovered_audit_count" -ge "$target_audit_count" ]] || exit 3
    target_audit_delta=$(( target_audit_count - before_audit_count ))
    total_audit_delta=$(( recovered_audit_count - before_audit_count ))
    (( target_audit_delta <= 32 && total_audit_delta <= 64 )) || {
      echo "rollback/recovery emitted an unbounded audit delta: $total_audit_delta" >&2
      exit 3
    }
    [[ "$(unexpected_rollback_audits "$address" "$before_audit_max")" == 0 ]] || {
      echo 'rollback emitted an audit action outside declarative account provisioning' >&2
      exit 3
    }
    if [[ -n "$(comm -23 <(audit_hashes "$before_state") \
      <(audit_hashes "$target_state"))" \
      || -n "$(comm -23 <(audit_hashes "$target_state") \
        <(audit_hashes "$recovered_state"))" ]]; then
      echo 'rollback changed or removed an existing audit event' >&2
      exit 3
    fi
    before_challenge_count=$(challenge_count "$before_state")
    target_challenge_count=$(challenge_count "$target_state")
    recovered_challenge_count=$(challenge_count "$recovered_state")
    [[ "$before_challenge_count" =~ ^[0-9]+$ \
      && "$target_challenge_count" =~ ^[0-9]+$ \
      && "$recovered_challenge_count" =~ ^[0-9]+$ \
      && "$target_challenge_count" -ge "$before_challenge_count" \
      && "$recovered_challenge_count" -ge "$target_challenge_count" ]] || exit 3
    if [[ -n "$(comm -23 <(challenge_hashes "$before_state") \
      <(challenge_hashes "$target_state"))" \
      || -n "$(comm -23 <(challenge_hashes "$target_state") \
        <(challenge_hashes "$recovered_state"))" ]]; then
      echo 'rollback changed or removed an existing login challenge' >&2
      exit 3
    fi
    target_challenge_delta=$(( target_challenge_count - before_challenge_count ))
    total_challenge_delta=$(( recovered_challenge_count - before_challenge_count ))
    (( target_challenge_delta <= 4 && total_challenge_delta <= 8 )) || {
      echo "rollback/recovery emitted an unbounded login-challenge delta: $total_challenge_delta" >&2
      exit 3
    }
    stable_durable_state "$before_state" "$before_stable"
    stable_durable_state "$target_state" "$target_stable"
    stable_durable_state "$recovered_state" "$recovered_stable"
    cmp --silent "$before_stable" "$target_stable" || {
      diff --unified "$before_stable" "$target_stable" >&2 || true
      echo 'rollback target changed durable state outside declared allowances' >&2
      exit 3
    }
    cmp --silent "$before_stable" "$recovered_stable" || {
      diff --unified "$before_stable" "$recovered_stable" >&2 || true
      echo 'rollback recovery changed durable state outside declared allowances' >&2
      exit 3
    }
    before_sha256=$(sha256sum "$before_state" | cut -d' ' -f1)
    target_sha256=$(sha256sum "$target_state" | cut -d' ' -f1)
    recovered_sha256=$(sha256sum "$recovered_state" | cut -d' ' -f1)
    jq -n --arg target_revision "$target" --arg return_revision "$return_revision" \
      --arg before_sha256 "$before_sha256" --arg target_sha256 "$target_sha256" \
      --arg recovered_sha256 "$recovered_sha256" \
      --argjson target_audit_delta "$target_audit_delta" \
      --argjson total_audit_delta "$total_audit_delta" \
      --argjson target_login_challenge_delta "$target_challenge_delta" \
      --argjson total_login_challenge_delta "$total_challenge_delta" \
      --arg completed_at "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
      '{schema_version:1,target_revision:$target_revision,return_revision:$return_revision,before_sha256:$before_sha256,target_sha256:$target_sha256,recovered_sha256:$recovered_sha256,target_audit_delta:$target_audit_delta,total_audit_delta:$total_audit_delta,target_login_challenge_delta:$target_login_challenge_delta,total_login_challenge_delta:$total_login_challenge_delta,durable_state:"verified_rollback_and_recovery_equal_except_declared_account_audits_and_qualification_login_challenges",completed_at:$completed_at}' \
      >"$result_file"
    evidence_verification_pending=false
    set_rollback_boundary exit
    boundary_entered=false
    ssh "${SSH_ARGS[@]}" "conductor@$address" \
      'sudo systemctl is-active --quiet postgresql factory-dashboard factory-supervisor caddy patchyard-backup.timer'
    trap - EXIT
    rm -f -- "$boundary_inventory"
    boundary_inventory=''
    printf 'rollback_complete target=%s recovered=%s durable_state_sha256=%s\n' \
      "$target" "$return_revision" "$recovered_sha256"
    ;;
  release-boundary)
    require_clean_revision
    manifest=${2:?usage: infra/rollback-control.sh release-boundary /absolute/control-rollback.json}
    [[ "$manifest" == /* && -f "$manifest" && -f "$manifest.sha256" ]] || exit 2
    : "${PATCHYARD_ROLLBACK_RELEASE_APPROVED:?set PATCHYARD_ROLLBACK_RELEASE_APPROVED=yes after independent recovery qualification}"
    [[ "$PATCHYARD_ROLLBACK_RELEASE_APPROVED" == yes ]] || exit 2
    (cd "$(dirname "$manifest")" && sha256sum --check "$(basename "$manifest").sha256")
    jq -e '.schema_version == 2 and (.return_revision | test("^[0-9a-f]{40}$")) and (.control_host | test("^[A-Za-z0-9.-]+$")) and (.control_address | test("^([0-9]{1,3}\\.){3}[0-9]{1,3}$"))' \
      "$manifest" >/dev/null
    control_host=$(jq -r .control_host "$manifest")
    address=$(jq -r .control_address "$manifest")
    return_revision=$(jq -r .return_revision "$manifest")
    [[ "$(installed_revision "$address")" == "$return_revision" ]] || {
      echo 'state-free boundary release refused: reviewed return revision is not installed' >&2
      exit 3
    }
    ssh "${SSH_ARGS[@]}" "conductor@$address" \
      'sudo systemctl is-active --quiet postgresql factory-dashboard factory-supervisor caddy && sudo curl --fail --silent --unix-socket /run/patchyard-dashboard/dashboard.sock http://localhost/healthz' \
      >/dev/null
    boundary_inventory=$(mktemp --suffix=.json /tmp/patchyard-rollback-boundary.XXXXXX)
    trap 'rm -f -- "$boundary_inventory"' EXIT
    write_boundary_inventory "$control_host" "$address" "$boundary_inventory"
    set_rollback_boundary exit
    ssh "${SSH_ARGS[@]}" "conductor@$address" \
      'sudo systemctl is-active --quiet postgresql factory-dashboard factory-supervisor caddy patchyard-backup.timer'
    echo 'rollback_boundary_released_from_reviewed_manifest'
    ;;
  *)
    echo 'usage: infra/rollback-control.sh <plan|apply|release-boundary> ...' >&2
    exit 2
    ;;
esac
