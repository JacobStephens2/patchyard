#!/usr/bin/env bash
set -euo pipefail

PROBE_ROOT=/var/tmp/patchyard-s3-probe
FC_ROOT=$PROBE_ROOT/firecracker
FIRECRACKER=$FC_ROOT/release-v1.15.1-x86_64/firecracker-v1.15.1-x86_64
TAP=patchyard-s3-tap
GUEST_IP=172.16.0.2
HOST_IP=172.16.0.1
POLICY_TABLE=eta_session3_firecracker
BASE_FIREWALL_HASH=$(nft list ruleset | sha256sum | cut -d' ' -f1)
BASE_FORWARD=$(sysctl -n net.ipv4.ip_forward)
CURRENT_RUN=
LAUNCHER_PID=

remove_control_rule() {
  local handle
  handle=$(nft -a list chain inet patchyard_worker_egress output \
    | awk '/session3-firecracker-host-control/ {print $NF; exit}')
  if [[ -n "$handle" ]]; then
    nft delete rule inet patchyard_worker_egress output handle "$handle"
  fi
}

cleanup_cycle() {
  if [[ -n "$CURRENT_RUN" ]]; then
    pkill -KILL -u factory-worker -f "firecracker.*$CURRENT_RUN/config.json" \
      2>/dev/null || true
  fi
  if [[ -n "$LAUNCHER_PID" ]]; then
    wait "$LAUNCHER_PID" 2>/dev/null || true
  fi
  nft delete table inet "$POLICY_TABLE" 2>/dev/null || true
  remove_control_rule
  ip link delete "$TAP" 2>/dev/null || true
  if [[ -n "$CURRENT_RUN" ]]; then
    rm -rf -- "$CURRENT_RUN"
  fi
  CURRENT_RUN=
  LAUNCHER_PID=
}

finish() {
  cleanup_cycle
  sysctl -q -w "net.ipv4.ip_forward=$BASE_FORWARD"
}
trap finish EXIT

sysctl -q -w net.ipv4.ip_forward=1

for cycle in 1 2 3 4 5; do
  CURRENT_RUN=$FC_ROOT/run-cycle-$cycle
  install -d -m 0750 -o factory-worker -g factory-worker "$CURRENT_RUN"
  cp --reflink=auto --sparse=always \
    "$FC_ROOT/rootfs-template.ext4" "$CURRENT_RUN/rootfs.ext4"
  chown factory-worker:factory-worker "$CURRENT_RUN/rootfs.ext4"
  touch "$CURRENT_RUN/firecracker.log" "$CURRENT_RUN/console.log"
  chown factory-worker:factory-worker \
    "$CURRENT_RUN/firecracker.log" "$CURRENT_RUN/console.log"

  jq -n \
    --arg kernel "$FC_ROOT/vmlinux-6.1.155" \
    --arg rootfs "$CURRENT_RUN/rootfs.ext4" \
    --arg tap "$TAP" \
    --arg log "$CURRENT_RUN/firecracker.log" \
    '{
      "boot-source": {
        "kernel_image_path": $kernel,
        "boot_args": "console=ttyS0 reboot=k panic=1 pci=off"
      },
      "drives": [{
        "drive_id": "rootfs",
        "path_on_host": $rootfs,
        "is_root_device": true,
        "is_read_only": false
      }],
      "network-interfaces": [{
        "iface_id": "net1",
        "guest_mac": "06:00:AC:10:00:02",
        "host_dev_name": $tap
      }],
      "machine-config": {
        "vcpu_count": 2,
        "mem_size_mib": 512,
        "smt": false
      },
      "logger": {
        "log_path": $log,
        "level": "Info",
        "show_level": true,
        "show_log_origin": false
      }
    }' >"$CURRENT_RUN/config.json"
  chown factory-worker:factory-worker "$CURRENT_RUN/config.json"

  ip tuntap add dev "$TAP" mode tap user factory-worker
  ip addr add "$HOST_IP/30" dev "$TAP"
  ip link set "$TAP" up

  nft insert rule inet patchyard_worker_egress output \
    ip daddr "$GUEST_IP" counter accept \
    comment "session3-firecracker-host-control"
  nft add table inet "$POLICY_TABLE"
  nft "add chain inet $POLICY_TABLE forward { type filter hook forward priority -50; policy accept; }"
  nft "add chain inet $POLICY_TABLE postrouting { type nat hook postrouting priority srcnat; policy accept; }"
  nft "add rule inet $POLICY_TABLE forward iifname $TAP ip daddr { 162.159.140.245, 172.66.0.243 } tcp dport 443 counter accept"
  nft "add rule inet $POLICY_TABLE forward iifname $TAP ip daddr 0.0.0.0/0 counter reject"
  nft "add rule inet $POLICY_TABLE forward iifname $TAP ip6 daddr ::/0 counter reject"
  nft "add rule inet $POLICY_TABLE postrouting ip saddr 172.16.0.0/30 oifname != $TAP masquerade"

  start_ns=$(date +%s%N)
  runuser -u factory-worker -- env -i \
    HOME=/var/lib/patchyard-worker \
    PATH=/usr/local/bin:/usr/bin:/bin \
    "$FIRECRACKER" \
      --api-sock "$CURRENT_RUN/api.sock" \
      --config-file "$CURRENT_RUN/config.json" \
      >"$CURRENT_RUN/console.log" 2>&1 &
  LAUNCHER_PID=$!

  ready=false
  for _ in $(seq 1 150); do
    if ssh -i "$FC_ROOT/id_ed25519" \
      -o BatchMode=yes \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=1 \
      "root@$GUEST_IP" true >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 0.1
  done
  if ! $ready; then
    echo "cycle=$cycle startup=FAILED"
    tail -n 80 "$CURRENT_RUN/console.log"
    exit 1
  fi
  ready_ns=$(date +%s%N)

  if [[ "$cycle" == 1 ]]; then
    pkill -KILL -u factory-worker -f "firecracker.*$CURRENT_RUN/config.json"
    mode=forced-kill
  else
    ssh -i "$FC_ROOT/id_ed25519" \
      -o BatchMode=yes \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      "root@$GUEST_IP" poweroff >/dev/null 2>&1 || true
    pkill -TERM -u factory-worker -f "firecracker.*$CURRENT_RUN/config.json" \
      2>/dev/null || true
    mode=guest-poweroff-plus-vmm-term
  fi
  wait "$LAUNCHER_PID" 2>/dev/null || true
  LAUNCHER_PID=

  nft delete table inet "$POLICY_TABLE"
  remove_control_rule
  ip link delete "$TAP"
  rm -rf -- "$CURRENT_RUN"
  CURRENT_RUN=
  end_ns=$(date +%s%N)

  process_count=$(pgrep -u factory-worker -f 'firecracker.*run-cycle-' \
    | wc -l || true)
  link_count=$(ip -o link show "$TAP" 2>/dev/null | wc -l || true)
  table_count=$(nft list table inet "$POLICY_TABLE" 2>/dev/null | wc -l \
    || true)
  control_count=$(nft list chain inet patchyard_worker_egress output \
    | grep -c session3-firecracker-host-control || true)
  run_count=$(find "$FC_ROOT" -maxdepth 1 -type d -name 'run-cycle-*' \
    | wc -l)

  printf 'cycle=%d startup_ms=%d teardown_ms=%d mode=%s processes=%d taps=%d policies=%d control_rules=%d run_dirs=%d\n' \
    "$cycle" \
    "$(((ready_ns - start_ns) / 1000000))" \
    "$(((end_ns - ready_ns) / 1000000))" \
    "$mode" "$process_count" "$link_count" "$table_count" \
    "$control_count" "$run_count"
done

sysctl -q -w "net.ipv4.ip_forward=$BASE_FORWARD"
printf 'firewall_restored=%s\n' \
  "$(nft list ruleset | sha256sum | cut -d' ' -f1)"
printf 'firewall_baseline=%s\n' "$BASE_FIREWALL_HASH"
printf 'ip_forward_restored=%s\n' "$(sysctl -n net.ipv4.ip_forward)"
