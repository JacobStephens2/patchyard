#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
ANSIBLE_ROOT="$REPO_ROOT/infra/ansible"
MODE=${1:-}

require_clean_revision() {
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
    echo 'restore drill requires a committed, clean desired-state revision' >&2
    exit 2
  fi
}

verify_plan_addresses() {
  local plan_file=$1 expected_action=$2
  local unexpected
  unexpected=$("$REPO_ROOT/infra/tofu.sh" digitalocean show -json "$plan_file" \
    | jq -r --arg action "$expected_action" '
      .resource_changes[]
      | select(.change.actions != ["no-op"] and .change.actions != [$action])
      | .address
    ')
  [[ -z "$unexpected" ]] || {
    echo "restore drill plan contains an unexpected action: $unexpected" >&2
    exit 2
  }
  unexpected=$("$REPO_ROOT/infra/tofu.sh" digitalocean show -json "$plan_file" \
    | jq -r '
      .resource_changes[]
      | select(.change.actions != ["no-op"])
      | .address
      | select(. != "digitalocean_droplet.restore_drill[0]" and . != "digitalocean_firewall.restore_drill[0]")
    ')
  [[ -z "$unexpected" ]] || {
    echo "restore drill plan changes an out-of-scope resource: $unexpected" >&2
    exit 2
  }
}

case "$MODE" in
  plan-create)
    require_clean_revision
    output_dir=${2:?usage: infra/restore-drill.sh plan-create /absolute/output/directory}
    [[ "$output_dir" == /* ]] || exit 2
    install -d -m 0700 "$output_dir"
    plan_file="$output_dir/restore-drill-create.tfplan"
    TF_VAR_restore_drill_enabled=true \
      "$REPO_ROOT/infra/tofu.sh" digitalocean plan -out="$plan_file"
    verify_plan_addresses "$plan_file" create
    "$REPO_ROOT/infra/tofu.sh" digitalocean show -no-color "$plan_file" \
      >"$plan_file.txt"
    echo "review $plan_file.txt, then run apply-restore"
    ;;
  apply-restore)
    require_clean_revision
    plan_file=${2:?usage: infra/restore-drill.sh apply-restore /absolute/create.tfplan <generation|latest>}
    generation=${3:-latest}
    [[ "$plan_file" == /* && -f "$plan_file" ]] || exit 2
    : "${PATCHYARD_RESTORE_APPROVED:?set PATCHYARD_RESTORE_APPROVED=yes after human plan review}"
    [[ "$PATCHYARD_RESTORE_APPROVED" == yes ]] || exit 2
    verify_plan_addresses "$plan_file" create
    "$REPO_ROOT/infra/tofu.sh" digitalocean apply "$plan_file"

    restore_ip=$("$REPO_ROOT/infra/tofu.sh" digitalocean output -raw restore_drill_ipv4)
    restore_private_ip=$("$REPO_ROOT/infra/tofu.sh" digitalocean output -raw restore_drill_private_ipv4)
    restore_droplet_id=$("$REPO_ROOT/infra/tofu.sh" digitalocean output -raw restore_drill_id)
    live_inventory=$("$ANSIBLE_ROOT/inventory/tofu.sh")
    worker_host=$(jq -r '.worker.hosts[0]' <<<"$live_inventory")
    worker_ip=$(jq -r --arg host "$worker_host" '._meta.hostvars[$host].ansible_host' <<<"$live_inventory")
    worker_private_ip=$(jq -r --arg host "$worker_host" '._meta.hostvars[$host].private_ip' <<<"$live_inventory")
    control_private_ip=$(jq -r '.control_plane.hosts[0] as $host | ._meta.hostvars[$host].private_ip' <<<"$live_inventory")
    monitoring_private_cidr=$(jq -er '.all.vars.monitoring_private_cidr' <<<"$live_inventory")
    orchestration_public_cidr=$(jq -er '.all.vars.orchestration_public_cidr' <<<"$live_inventory")

    drill_root=$(mktemp -d /tmp/patchyard-restore-drill.XXXXXX)
    trap 'rm -r -- "$drill_root"' EXIT
    inventory_file="$drill_root/inventory.json"
    jq -n \
      --arg restore_ip "$restore_ip" --arg restore_private_ip "$restore_private_ip" \
      --arg worker_host "$worker_host" --arg worker_ip "$worker_ip" \
      --arg worker_private_ip "$worker_private_ip" \
      --arg control_private_cidr "$control_private_ip/32" \
      --arg monitoring_private_cidr "$monitoring_private_cidr" \
      --arg orchestration_public_cidr "$orchestration_public_cidr" \
      '{all:{vars:{ansible_user:"conductor",ansible_ssh_private_key_file:"/var/lib/conductor/.ssh/id_ed25519",monitoring_private_cidr:$monitoring_private_cidr,orchestration_public_cidr:$orchestration_public_cidr,control_plane_private_cidr:$control_private_cidr},children:{control_plane:{hosts:{"factory-restore-drill.example.com":{ansible_host:$restore_ip,private_ip:$restore_private_ip,factory_role:"control-plane"}}},worker:{hosts:{($worker_host):{ansible_host:$worker_ip,private_ip:$worker_private_ip,factory_role:"worker"}}}}}}' \
      >"$inventory_file"

    backup_identity=$("$REPO_ROOT/infra/tofu.sh" digitalocean output -raw factory_backup_age_identity)
    backup_access=$("$REPO_ROOT/infra/tofu.sh" digitalocean output -raw factory_backup_runtime_access_key)
    backup_secret=$("$REPO_ROOT/infra/tofu.sh" digitalocean output -raw factory_backup_runtime_secret_key)
    backup_bucket=$("$REPO_ROOT/infra/tofu.sh" digitalocean output -raw factory_backup_bucket)
    backup_endpoint=$("$REPO_ROOT/infra/tofu.sh" digitalocean output -raw factory_backup_endpoint)
    backup_recipient=$("$REPO_ROOT/infra/tofu.sh" digitalocean output -raw factory_backup_age_recipient)
    probe_password=$(openssl rand -base64 36 | tr -d '/+=')

    bundle_file="$drill_root/factory.bundle"
    git -C "$REPO_ROOT" bundle create "$bundle_file" --all
    cargo_bin=${CARGO_BIN:-/var/lib/conductor/.cargo/bin/cargo}
    "$cargo_bin" build --locked --release \
      --package factoryctl --package factory-verify --package factory-supervisor \
      --package factory-web
    revision=$(git -C "$REPO_ROOT" rev-parse HEAD)
    extra_vars="$drill_root/extra-vars.json"
    jq -n \
      --arg bundle "$bundle_file" --arg revision "$revision" \
      --arg generation "$generation" \
      --arg factoryctl "$REPO_ROOT/target/release/factoryctl" \
      --arg factory_verify "$REPO_ROOT/target/release/factory-verify" \
      --arg factory_supervisor "$REPO_ROOT/target/release/factory-supervisor" \
      --arg evidence_qualify "$REPO_ROOT/target/release/factory-evidence-qualify" \
      --arg factory_web "$REPO_ROOT/target/release/factory-web" \
      --arg app_id "$GH_PATCHYARD_APP_ID" \
      --arg installation_id "$GH_PATCHYARD_APP_INSTALLATION_ID" \
      --arg restore_expected_host "$restore_ip" \
      --arg restore_droplet_id "$restore_droplet_id" \
      --arg backup_bucket "$backup_bucket" \
      --arg backup_endpoint "$backup_endpoint" \
      --arg backup_recipient "$backup_recipient" \
      '{factory_restore_drill:true,factory_restore_expected_host:$restore_expected_host,factory_restore_expected_droplet_id:$restore_droplet_id,factory_restore_generation:$generation,factory_backup_age_identity:"{{ lookup(\"env\", \"ETA_RESTORE_IDENTITY\") }}",factory_backup_runtime_access_key:"{{ lookup(\"env\", \"ETA_RESTORE_BACKUP_ACCESS\") }}",factory_backup_runtime_secret_key:"{{ lookup(\"env\", \"ETA_RESTORE_BACKUP_SECRET\") }}",factory_backup_bucket:$backup_bucket,factory_backup_endpoint:$backup_endpoint,factory_backup_age_recipient:$backup_recipient,factory_restore_probe_password:"{{ lookup(\"env\", \"ETA_RESTORE_PROBE_PASSWORD\") }}",factory_repo_bundle:$bundle,factory_repo_revision:$revision,factoryctl_binary:$factoryctl,factory_verify_binary:$factory_verify,factory_supervisor_binary:$factory_supervisor,factory_evidence_qualify_binary:$evidence_qualify,factory_web_binary:$factory_web,factory_dashboard_accounts_file:"/dev/null",factory_github_app_private_key_file:"/dev/null",factory_github_app_id:$app_id,factory_github_app_installation_id:$installation_id}' \
      >"$extra_vars"
    for binary in factoryctl factory-verify factory-supervisor factory-evidence-qualify factory-web; do
      key=$(tr '-' '_' <<<"$binary")_sha256
      jq --arg key "$key" --arg value "$(sha256sum "$REPO_ROOT/target/release/$binary" | cut -d' ' -f1)" \
        '.[$key]=$value' "$extra_vars" >"$extra_vars.next"
      mv "$extra_vars.next" "$extra_vars"
    done
    chmod 0600 "$extra_vars"
    ansible_playbook="$ANSIBLE_ROOT/.venv/bin/ansible-playbook"
    [[ -x "$ansible_playbook" ]] || ansible_playbook=ansible-playbook
    (
      cd "$ANSIBLE_ROOT"
      ETA_RESTORE_IDENTITY="$backup_identity" \
      ETA_RESTORE_BACKUP_ACCESS="$backup_access" \
      ETA_RESTORE_BACKUP_SECRET="$backup_secret" \
      ETA_RESTORE_PROBE_PASSWORD="$probe_password" \
        "$ansible_playbook" -i "$inventory_file" restore.yml -e "@$extra_vars"
    )
    ;;
  plan-destroy)
    require_clean_revision
    output_dir=${2:?usage: infra/restore-drill.sh plan-destroy /absolute/output/directory}
    [[ "$output_dir" == /* ]] || exit 2
    install -d -m 0700 "$output_dir"
    plan_file="$output_dir/restore-drill-destroy.tfplan"
    "$REPO_ROOT/infra/tofu.sh" digitalocean plan -out="$plan_file"
    verify_plan_addresses "$plan_file" delete
    "$REPO_ROOT/infra/tofu.sh" digitalocean show -no-color "$plan_file" \
      >"$plan_file.txt"
    echo "review $plan_file.txt, then run apply-destroy"
    ;;
  apply-destroy)
    require_clean_revision
    plan_file=${2:?usage: infra/restore-drill.sh apply-destroy /absolute/destroy.tfplan}
    [[ "$plan_file" == /* && -f "$plan_file" ]] || exit 2
    : "${PATCHYARD_RESTORE_DESTROY_APPROVED:?set PATCHYARD_RESTORE_DESTROY_APPROVED=yes after human plan review}"
    [[ "$PATCHYARD_RESTORE_DESTROY_APPROVED" == yes ]] || exit 2
    verify_plan_addresses "$plan_file" delete
    "$REPO_ROOT/infra/tofu.sh" digitalocean apply "$plan_file"
    ;;
  *)
    echo 'usage: infra/restore-drill.sh <plan-create|apply-restore|plan-destroy|apply-destroy> ...' >&2
    exit 2
    ;;
esac
