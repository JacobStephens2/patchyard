#!/usr/bin/env bash
set -uo pipefail

PASS=0
FAIL=0

record() {
  local id=$1
  local status=$2
  local detail=$3
  printf '%s=%s detail=%s\n' "$id" "$status" "$detail"
  if [[ "$status" == PASS ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
  fi
}

expect_failure() {
  local label=$1
  shift
  if timeout 4 "$@" >/dev/null 2>&1; then
    printf '%s=UNEXPECTED_SUCCESS\n' "$label"
    return 1
  fi
  printf '%s=DENIED\n' "$label"
  return 0
}

printf 'candidate_probe_started=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'kernel=%s\n' "$(uname -srmo)"
printf 'identity=%s\n' "$(id)"

request_ok=true
request_sha=$(sha256sum /input/request.md 2>/dev/null | cut -d' ' -f1)
[[ -n "$request_sha" ]] || request_ok=false
for operation in \
  "printf x >>/input/request.md" \
  "touch /input/new" \
  "mv /input/request.md /input/renamed" \
  "chmod 0600 /input/request.md" \
  "rm /input/request.md"; do
  if bash -c "$operation" >/dev/null 2>&1; then
    printf 'request_mutation=UNEXPECTED_SUCCESS command=%q\n' "$operation"
    request_ok=false
  else
    printf 'request_mutation=DENIED command=%q\n' "$operation"
  fi
done
if $request_ok; then
  record P1 PASS "sha256=$request_sha; all mutation forms denied"
else
  record P1 FAIL "request missing or mutable"
fi

worktree_ok=true
worktree_sha=$(sha256sum /work/base.txt 2>/dev/null | cut -d' ' -f1)
[[ -n "$worktree_sha" ]] || worktree_ok=false
printf 'created\n' >/work/result.tmp 2>/dev/null || worktree_ok=false
printf 'edited\n' >>/work/result.tmp 2>/dev/null || worktree_ok=false
mv /work/result.tmp /work/result.txt 2>/dev/null || worktree_ok=false
touch /work/delete-me 2>/dev/null || worktree_ok=false
rm /work/delete-me 2>/dev/null || worktree_ok=false
if $worktree_ok; then
  record P2 PASS "base_sha256=$worktree_sha; create/edit/rename/delete succeeded"
else
  record P2 FAIL "worktree mutation contract failed"
fi

boundary_ok=true
for path in \
  /host/sentinel \
  /proc/1/root/host/sentinel \
  /var/tmp/patchyard-s3-probe/host-credential-canary \
  /dev/kvm \
  /run/podman/podman.sock \
  /var/run/docker.sock; do
  if [[ -e "$path" ]]; then
    printf 'host_path=VISIBLE path=%s\n' "$path"
    boundary_ok=false
  else
    printf 'host_path=ABSENT path=%s\n' "$path"
  fi
done

mkdir -p /tmp/session3-mount
if mount -t tmpfs tmpfs /tmp/session3-mount >/dev/null 2>&1; then
  printf 'internal_mount=ISOLATED_GUEST_SUCCESS\n'
  umount /tmp/session3-mount >/dev/null 2>&1 || true
else
  printf 'internal_mount=DENIED\n'
fi
if mknod /tmp/session3-device c 10 232 >/dev/null 2>&1; then
  printf 'internal_mknod=ISOLATED_GUEST_SUCCESS\n'
  rm -f /tmp/session3-device
else
  printf 'internal_mknod=DENIED\n'
fi
if command -v nft >/dev/null 2>&1 && nft add table inet session3_escape >/dev/null 2>&1; then
  printf 'internal_nft=ISOLATED_GUEST_SUCCESS\n'
  nft delete table inet session3_escape >/dev/null 2>&1 || true
else
  printf 'internal_nft=DENIED\n'
fi
if $boundary_ok; then
  printf 'P3_INSIDE=PASS detail=host paths and devices absent; host hashes pending launcher verification\n'
else
  printf 'P3_INSIDE=FAIL detail=host path or device exposed\n'
  FAIL=$((FAIL + 1))
fi

http_code=$(curl --silent --show-error --output /dev/null \
  --connect-timeout 4 --max-time 10 --write-out '%{http_code}' \
  https://api.openai.com/v1/models 2>/dev/null || true)
if [[ "$http_code" =~ ^[1-5][0-9][0-9]$ ]]; then
  record P4 PASS "http_status=$http_code"
else
  record P4 FAIL "no HTTP response; status=${http_code:-none}"
fi

if expect_failure forbidden_ipv4 bash -c '</dev/tcp/1.1.1.1/443'; then
  record P5 PASS "1.1.1.1:443 denied"
else
  record P5 FAIL "1.1.1.1:443 reachable"
fi

if expect_failure forbidden_ipv6 bash -c '</dev/tcp/2606:4700:4700::1111/443'; then
  record P6 PASS "forbidden IPv6 denied or IPv6 disabled"
else
  record P6 FAIL "forbidden IPv6 reachable"
fi

dns_ok=true
if timeout 4 getent ahosts example.net >/dev/null 2>&1; then
  printf 'forbidden_dns_name=RESOLVED\n'
  dns_ok=false
else
  printf 'forbidden_dns_name=DENIED\n'
fi
if timeout 4 dig +time=2 +tries=1 @1.1.1.1 example.net A >/dev/null 2>&1; then
  printf 'direct_dns_udp=RESPONSE\n'
  dns_ok=false
else
  printf 'direct_dns_udp=DENIED\n'
fi
if timeout 4 dig +tcp +time=2 +tries=1 @1.1.1.1 example.net A >/dev/null 2>&1; then
  printf 'direct_dns_tcp=RESPONSE\n'
  dns_ok=false
else
  printf 'direct_dns_tcp=DENIED\n'
fi
if $dns_ok; then
  record P7 PASS "runtime resolution and direct UDP/TCP DNS denied"
else
  record P7 FAIL "a forbidden DNS path succeeded"
fi

private_ok=true
for target in \
  10.132.0.14/9090 \
  10.132.0.1/22 \
  100.64.0.1/443 \
  169.254.169.254/80 \
  fd00::1/443; do
  host=${target%/*}
  port=${target##*/}
  if timeout 3 bash -c "</dev/tcp/$host/$port" >/dev/null 2>&1; then
    printf 'private_target=REACHABLE target=%s\n' "$target"
    private_ok=false
  else
    printf 'private_target=DENIED target=%s\n' "$target"
  fi
done
if $private_ok; then
  record P8 PASS "private, metadata, CGNAT, and ULA targets denied"
else
  record P8 FAIL "a private or metadata target was reachable"
fi

credential_ok=true
if env | cut -d= -f1 | grep -Eq \
  '^(PATCHYARD_PROBE_CANARY|DO_API_TOKEN|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|GH_TOKEN|OP_SERVICE_ACCOUNT_TOKEN)$'; then
  printf 'credential_environment=VISIBLE\n'
  credential_ok=false
else
  printf 'credential_environment=ABSENT\n'
fi
for path in \
  /etc/op.env \
  /etc/orchestration/op.env \
  /root/.aws/credentials \
  /root/.config/op \
  /var/lib/patchyard-worker/.aws/credentials \
  /var/lib/patchyard-worker/.config/op; do
  if [[ -e "$path" ]]; then
    printf 'credential_path=VISIBLE path=%s\n' "$path"
    credential_ok=false
  else
    printf 'credential_path=ABSENT path=%s\n' "$path"
  fi
done
if $credential_ok; then
  record P9 PASS "credential variables, canary, and standard paths absent"
else
  record P9 FAIL "credential surface visible"
fi

printf 'candidate_probe_finished=%s pass=%d fail=%d\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PASS" "$FAIL"
exit "$((FAIL != 0))"
