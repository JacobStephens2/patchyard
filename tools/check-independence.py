#!/usr/bin/env python3
"""Prove Session 0's structural half of the A68 independence invariant."""

from pathlib import Path
import sys

repo = Path(__file__).resolve().parent.parent
runtime_inputs = [
    repo / "infra" / "ansible" / "roles" / "control_plane",
    repo / "infra" / "ansible" / "roles" / "exporters",
    repo / "infra" / "ansible" / "roles" / "worker",
]
forbidden = {
    "/srv/orchestration": "orchestration-host filesystem",
    "status.example.com": "status-dashboard runtime",
    "env.tpl": "orchestration secret injection",
    "op.env": "orchestration secret injection",
    "142.93.121.94": "orchestration runtime address",
}

violations = []
for root in runtime_inputs:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.startswith("qualify-"):
            continue
        text = path.read_text(errors="ignore")
        for needle, reason in forbidden.items():
            if needle in text:
                violations.append(f"{path.relative_to(repo)}: {reason} ({needle})")

if violations:
    print("independence check: runtime dependency found", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    raise SystemExit(1)

print("independence check: runtime roles contain no orchestration-host dependency")
