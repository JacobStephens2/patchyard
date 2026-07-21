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
SKIP_DIRS = {".git", ".terraform", "node_modules", "__pycache__", ".obsidian", "target", ".venv", ".pytest_cache", ".ruff_cache"}

violations = []
for path in REPO.rglob("*"):
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    if path.is_file():
        if path.name in FORBIDDEN_NAMES:
            violations.append(f"{path.relative_to(REPO)} - {FORBIDDEN_NAMES[path.name]}")
        elif path.suffix in FORBIDDEN_SUFFIXES:
            violations.append(f"{path.relative_to(REPO)} - {FORBIDDEN_SUFFIXES[path.suffix]}")

# Doc-version tripwire: SPEC's status line must match its last changelog entry
# (the v2.4-stuck-header defect, council-flagged, recurred within a day - D3/audit 2026-07-21).
spec = (REPO / "SPEC.md").read_text()
import re as _re
changelog_versions = _re.findall(r"v(2\.\d+), 20\d\d-\d\d-\d\d", spec)
status_m = _re.search(r"\*Status: v(2\.\d+),", spec)
if changelog_versions and status_m:
    newest = max(changelog_versions, key=lambda v: tuple(map(int, v.split("."))))
    if status_m.group(1) != newest:
        violations.append(f"SPEC.md - status line says v{status_m.group(1)} but newest changelog entry is v{newest}")
if _re.search(r"build spec, v\d", spec.splitlines()[0]):
    violations.append("SPEC.md - title carries a version; the status line owns it")

if violations:
    print("check-stack: excluded-technology artifacts found:")
    for v in violations:
        print(f"  {v}")
    sys.exit(1)
print("check-stack: no excluded-technology artifacts")
