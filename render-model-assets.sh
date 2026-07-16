#!/usr/bin/env bash
# Render the canonical Mermaid projection as standalone SVG and PNG assets.
# The review page embeds the PNG because browsers may auto-darken HTML labels
# inside an SVG. The Mermaid CLI version is pinned so layout changes happen
# through a reviewed update, not an implicit latest-version pull.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PUPPETEER_EXECUTABLE_PATH="${PUPPETEER_EXECUTABLE_PATH:-/bin/chromium-browser}"

python3 "$HERE/validate-model.py"
python3 "$HERE/render-model.py" --check

MMDC=(npx --yes @mermaid-js/mermaid-cli@11.12.0)

"${MMDC[@]}" \
  -i "$HERE/factory-model.mmd" \
  -o "$HERE/factory-model.svg" \
  -c "$HERE/factory-model-mermaid-config.json" \
  -b white

"${MMDC[@]}" \
  -i "$HERE/factory-model.mmd" \
  -o "$HERE/factory-model.png" \
  -c "$HERE/factory-model-mermaid-config.json" \
  -s 3 \
  -b white
