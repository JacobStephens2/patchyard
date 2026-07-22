#!/usr/bin/env python3
"""Mechanical checks for the Session 7 preview and verifier slice."""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess


REPO = Path(__file__).resolve().parent.parent
PREVIEW = REPO / "preview"
errors: list[str] = []

python_files = [
    PREVIEW / "patchyard-preview-lease.py",
    PREVIEW / "patchyard-headless.py",
    PREVIEW / "patchyard-preview-capture.py",
]
for path in python_files:
    try:
        ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as error:
        errors.append(f"Python syntax error in {path.name}: {error}")

shell_files = [
    PREVIEW / "bootstrap-preview-bridge",
    PREVIEW / "patchyard-preview-access",
    REPO / "worker/runtime/patchyard-run-verifier",
    REPO / "worker/runtime/patchyard-verify-runtime",
]
for path in shell_files:
    result = subprocess.run(["bash", "-n", path], check=False, capture_output=True, text=True)
    if result.returncode:
        errors.append(f"shell syntax error in {path.name}: {result.stderr.strip()}")

lease = python_files[0].read_text()
for contract in (
    '"owner": args.owner',
    '"request_id": args.request_id',
    '"expected_sha": args.expected_sha',
    '"expires_at":',
    'os.environ.get("SSH_ORIGINAL_COMMAND")',
    '"preview_head": guest_sha',
    'result = sweep()',
    'cleanup = destroy(slot, lease_id)',
):
    if contract not in lease:
        errors.append(f"preview lease contract missing: {contract}")

headless = python_files[1].read_text()
for contract in (
    '"declarativeNetRequest"',
    '"Authorization"',
    'f"Bearer {bearer}"',
    '"--dump-dom"',
    '"blank_sentinel"',
):
    if contract not in headless:
        errors.append(f"headless capture contract missing: {contract}")

capture = python_files[2].read_text()
for contract in (
    '"acquire"',
    '"verify"',
    '"release"',
    'finally:',
    '"page.html"',
    '"snapshot.json"',
):
    if contract not in capture:
        errors.append(f"preview coordinator contract missing: {contract}")

if errors:
    print("preview runtime check: failed")
    for error in errors:
        print(f"  {error}")
    raise SystemExit(1)
print("preview runtime check: pass")
