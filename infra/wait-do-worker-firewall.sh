#!/usr/bin/env bash
set -euo pipefail
umask 077

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
MAX_ATTEMPTS=24
POLL_SECONDS=2

: "${DO_API_TOKEN:?missing DigitalOcean provider token}"

STATE_JSON=$("$REPO_ROOT/infra/tofu.sh" digitalocean show -json) || {
  echo 'worker firewall readiness refused because current OpenTofu state could not be inspected' >&2
  exit 2
}

BINDING_JSON=$(jq -cer '
  [
    .values.root_module.resources[]?
    | select(
        .address == "digitalocean_droplet.worker"
        or .address == "digitalocean_firewall.worker"
      )
  ] as $resources
  | [$resources[] | select(.address == "digitalocean_droplet.worker")] as $workers
  | [$resources[] | select(.address == "digitalocean_firewall.worker")] as $firewalls
  | if
      ($workers | length) == 1
      and ($firewalls | length) == 1
      and ($workers[0].values.id | tostring | test("^[1-9][0-9]*$"))
      and ($firewalls[0].values.id | type) == "string"
      and ($firewalls[0].values.id | test("^[0-9a-f-]{36}$"))
      and ($firewalls[0].values.droplet_ids | type) == "array"
      and ($firewalls[0].values.droplet_ids | length) == 1
      and (
        $firewalls[0].values.droplet_ids[0] | tostring
      ) == (
        $workers[0].values.id | tostring
      )
    then
      {
        worker_id: ($workers[0].values.id | tostring),
        firewall_id: $firewalls[0].values.id
      }
    else
      error("worker/firewall state binding is not exact")
    end
' <<<"$STATE_JSON") || {
  echo 'worker firewall readiness refused because current OpenTofu state does not bind one firewall to one worker' >&2
  exit 2
}

WORKER_ID=$(jq -r '.worker_id' <<<"$BINDING_JSON")
FIREWALL_ID=$(jq -r '.firewall_id' <<<"$BINDING_JSON")

firewall_is_ready() {
  local response=$1
  jq -e \
    --arg firewall_id "$FIREWALL_ID" \
    --arg worker_id "$WORKER_ID" '
      .firewall
      | (type == "object")
        and (.id == $firewall_id)
        and (.name == "patchyard-worker")
        and (.status == "succeeded")
        and (
          (.pending_changes | type) == "array"
          and (.pending_changes | length) == 0
        )
        and (
          (.droplet_ids | type) == "array"
          and (.droplet_ids | length) == 1
          and (.droplet_ids[0] | tostring) == $worker_id
        )
        and (
          (.tags | type) == "array"
          and (.tags | length) == 0
        )
    ' <<<"$response" >/dev/null 2>&1
}

for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
  FIREWALL_RESPONSE=
  if FIREWALL_RESPONSE=$(curl -q --fail --silent --show-error \
    --connect-timeout 3 --max-time 3 --proto '=https' \
    -H "Authorization: Bearer $DO_API_TOKEN" \
    "https://api.digitalocean.com/v2/firewalls/$FIREWALL_ID"); then
    if firewall_is_ready "$FIREWALL_RESPONSE"; then
      printf 'worker firewall readiness: pass (firewall=%s worker=%s attempt=%s)\n' \
        "$FIREWALL_ID" "$WORKER_ID" "$attempt"
      exit 0
    fi
  fi
  if ((attempt < MAX_ATTEMPTS)); then
    sleep "$POLL_SECONDS"
  fi
done

echo 'worker replacement stopped because the exact worker firewall did not reach provider desired state' >&2
exit 1
