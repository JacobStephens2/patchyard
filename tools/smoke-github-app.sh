#!/usr/bin/env bash
set -euo pipefail
umask 077

for required_name in \
  GH_PATCHYARD_APP_ID \
  GH_PATCHYARD_APP_INSTALLATION_ID \
  GH_PATCHYARD_APP_PRIVATE_KEY; do
  if [[ -z "${!required_name:-}" ]]; then
    echo "$required_name is not set; launch through the orchestration wrapper" >&2
    exit 1
  fi
done

APP_PRIVATE_KEY=$(op read "op://$GH_PATCHYARD_APP_PRIVATE_KEY")

base64url() {
  openssl base64 -A | tr '+/' '-_' | tr -d '='
}

NOW=$(date +%s)
HEADER=$(printf '%s' '{"alg":"RS256","typ":"JWT"}' | base64url)
PAYLOAD=$(jq -cn \
  --argjson issued_at "$((NOW - 60))" \
  --argjson expires_at "$((NOW + 540))" \
  --arg issuer "$GH_PATCHYARD_APP_ID" \
  '{iat: $issued_at, exp: $expires_at, iss: $issuer}' | base64url)
UNSIGNED_TOKEN="$HEADER.$PAYLOAD"
SIGNATURE=$(printf '%s' "$UNSIGNED_TOKEN" \
  | openssl dgst -sha256 \
      -sign <(printf '%s' "$APP_PRIVATE_KEY") -binary \
  | base64url)
APP_JWT="$UNSIGNED_TOKEN.$SIGNATURE"

MINT_RESPONSE=$(curl --fail --silent --show-error --request POST \
  --header "Accept: application/vnd.github+json" \
  --header "Authorization: Bearer $APP_JWT" \
  --header "X-GitHub-Api-Version: 2022-11-28" \
  --data '{"repositories":["factory"],"permissions":{"contents":"read"}}' \
  "https://api.github.com/app/installations/$GH_PATCHYARD_APP_INSTALLATION_ID/access_tokens")
INSTALLATION_TOKEN=$(jq -er '.token' <<<"$MINT_RESPONSE")
EXPIRES_AT=$(jq -er '.expires_at' <<<"$MINT_RESPONSE")

probe_repo() {
  local repo=$1 expected_status=$2 actual_status
  actual_status=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
    --header "Accept: application/vnd.github+json" \
    --header "Authorization: Bearer $INSTALLATION_TOKEN" \
    --header "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/example-org/$repo")
  if [[ "$actual_status" != "$expected_status" ]]; then
    echo "$repo returned HTTP $actual_status; expected $expected_status" >&2
    return 1
  fi
}

probe_repo factory 200
probe_repo fieldbook 404
echo "GitHub App smoke: narrowed token reaches factory only; expires $EXPIRES_AT"
