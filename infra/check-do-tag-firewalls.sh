#!/usr/bin/env bash
set -euo pipefail

: "${DO_API_TOKEN:?missing DigitalOcean provider token}"

TAG_NAMES_JSON=${TF_VAR_existing_eta_tag_names:-'["production"]'}
if ! jq -e 'type == "array" and length > 0 and all(.[]; type == "string" and length > 0)' \
  <<<"$TAG_NAMES_JSON" >/dev/null; then
  echo "TF_VAR_existing_eta_tag_names must be a non-empty JSON string array" >&2
  exit 2
fi

FIREWALLS=$(curl --fail --silent --show-error \
  -H "Authorization: Bearer $DO_API_TOKEN" \
  'https://api.digitalocean.com/v2/firewalls?per_page=200')

CONFLICTS=$(jq -r --argjson desired "$TAG_NAMES_JSON" '
  .firewalls[]
  | . as $firewall
  | [($firewall.tags // [])[]] as $attached
  | select(any($desired[]; . as $tag | $attached | index($tag)))
  | "\(.name)\ttags=\(($firewall.tags // []) | join(","))"
' <<<"$FIREWALLS")

if [[ -n "$CONFLICTS" ]]; then
  echo "DigitalOcean tag-firewall union would affect the factory hosts:" >&2
  printf '%s\n' "$CONFLICTS" >&2
  exit 1
fi

printf 'tag-firewall check: no live firewall targets desired tags (%s)\n' \
  "$(jq -r 'join(",")' <<<"$TAG_NAMES_JSON")"
