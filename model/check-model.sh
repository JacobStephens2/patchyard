#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

python3 "$HERE/validate-model.py"
python3 "$HERE/render-model.py" --check
python3 -m unittest discover -s "$HERE/tests" -p 'test_*.py'
