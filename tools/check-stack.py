#!/usr/bin/env python3
"""Stack-doctrine tripwire (docs/stack.md exclusions): fail if artifacts of
excluded technologies appear in the repo. Runs in CI beside the other checks."""
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
FORBIDDEN_NAMES = {
    "package.json": "npm (A53)",
    "package-lock.json": "npm (A53)",
    "tsconfig.json": "TypeScript (A53)",
    "docker-compose.yml": "Compose (stack.md exclusions)",
    "docker-compose.yaml": "Compose (stack.md exclusions)",
    "Chart.yaml": "Helm (stack.md exclusions)",
}
FORBIDDEN_SUFFIXES = {".ts": "TypeScript (A53)", ".tsx": "TypeScript (A53)", ".tfstate": "plaintext tofu state (A69)"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".obsidian", "target", ".venv", ".pytest_cache", ".ruff_cache"}

violations = []
for path in REPO.rglob("*"):
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    if path.is_file():
        if path.name in FORBIDDEN_NAMES:
            violations.append(f"{path.relative_to(REPO)} - {FORBIDDEN_NAMES[path.name]}")
        elif path.suffix in FORBIDDEN_SUFFIXES:
            violations.append(f"{path.relative_to(REPO)} - {FORBIDDEN_SUFFIXES[path.suffix]}")

if violations:
    print("check-stack: excluded-technology artifacts found:")
    for v in violations:
        print(f"  {v}")
    sys.exit(1)
print("check-stack: no excluded-technology artifacts")
