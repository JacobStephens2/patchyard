#!/usr/bin/env python3
"""Stack-doctrine tripwire (docs/stack.md exclusions): fail if artifacts of
excluded technologies appear in the repo. Runs in CI beside the other checks."""
import pathlib
import re
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

# Marketplace action tags are mutable. Every external workflow action must use
# an immutable 40-character commit SHA; the readable release stays a comment.
for workflow in (REPO / ".github" / "workflows").glob("*.y*ml"):
    for match in re.finditer(r"^\s*uses:\s*([^#\s]+)", workflow.read_text(), re.MULTILINE):
        action = match.group(1)
        if action.startswith("./"):
            continue
        _, separator, ref = action.rpartition("@")
        if not separator or not re.fullmatch(r"[0-9a-f]{40}", ref):
            violations.append(
                f"{workflow.relative_to(REPO)} - mutable action reference ({action})"
            )

# Doc-version tripwire: SPEC's status line must match its last changelog entry
# (the v2.4-stuck-header defect, council-flagged, recurred within a day - D3/audit 2026-07-21).
spec = (REPO / "SPEC.md").read_text()
changelog_versions = re.findall(r"v(2\.\d+), 20\d\d-\d\d-\d\d", spec)
status_m = re.search(r"\*Status: v(2\.\d+),", spec)
if changelog_versions and status_m:
    newest = max(changelog_versions, key=lambda v: tuple(map(int, v.split("."))))
    if status_m.group(1) != newest:
        violations.append(f"SPEC.md - status line says v{status_m.group(1)} but newest changelog entry is v{newest}")
if re.search(r"build spec, v\d", spec.splitlines()[0]):
    violations.append("SPEC.md - title carries a version; the status line owns it")

if violations:
    print("check-stack: excluded-technology artifacts found:")
    for v in violations:
        print(f"  {v}")
    sys.exit(1)
print("check-stack: no excluded-technology artifacts")
