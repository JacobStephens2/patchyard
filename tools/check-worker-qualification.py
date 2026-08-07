#!/usr/bin/env python3
"""Mechanical checks for the Session 5 hostile-qualification contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parent.parent
QUALIFICATION = REPO / "worker" / "qualification"
MANIFEST_PATH = QUALIFICATION / "hostile-test-manifest.json"
RESULT_PATH = (
    REPO
    / "research"
    / "isolation"
    / "results"
    / "session-5-hostile-qualification.json"
)

EXPECTED_CLASSES = {
    "alternate_output",
    "cloud_metadata",
    "dns_exfiltration",
    "environment_variables",
    "filesystem_boundary",
    "malformed_result_filesystem",
    "private_network",
    "residue",
    "sockets",
    "ssh_op_file_paths",
}
EXPECTED_EXECUTOR_COUNTS = {
    "control_boundary": 3,
    "guest": 14,
    "host_result": 7,
}


errors: list[str] = []
manifest = json.loads(MANIFEST_PATH.read_text())
tests = manifest.get("tests", [])
ids = [test.get("id") for test in tests]
if manifest.get("schema_version") != 1 or manifest.get("session") != 5:
    errors.append("hostile manifest identity is not Session 5 schema version 1")
if len(tests) != 24 or len(set(ids)) != 24:
    errors.append("hostile manifest must contain exactly 24 unique tests")
if {test.get("class") for test in tests} != EXPECTED_CLASSES:
    errors.append("hostile manifest does not cover the complete required class set")
executor_counts = {
    executor: sum(test.get("executor") == executor for test in tests)
    for executor in EXPECTED_EXECUTOR_COUNTS
}
if executor_counts != EXPECTED_EXECUTOR_COUNTS:
    errors.append(f"hostile executor counts differ: {executor_counts}")
if any(not test.get("targets") or not test.get("expected") for test in tests):
    errors.append("every hostile test must declare targets and an expected outcome")

manifest_sha256 = hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()
launcher = (REPO / "worker" / "runtime" / "patchyard-firecracker-run").read_text()
guest = (REPO / "worker" / "image" / "patchyard-guest-run").read_text()
probe = (REPO / "worker" / "image" / "patchyard-hostile-probe").read_text()
extractor = (
    REPO / "worker" / "runtime" / "patchyard-extract-result-image"
).read_text()
result_tester = (QUALIFICATION / "patchyard-test-result-contract").read_text()
control_runner = (
    QUALIFICATION / "patchyard-run-hostile-qualification"
).read_text()
hostile_launch = (QUALIFICATION / "patchyard-hostile-launch").read_text()
worker_tasks = (
    REPO / "infra" / "ansible" / "roles" / "worker" / "tasks" / "main.yml"
).read_text()
control_tasks = (
    REPO
    / "infra"
    / "ansible"
    / "roles"
    / "control_plane"
    / "tasks"
    / "main.yml"
).read_text()

for required in (
    "adversarial-qualification",
    "qualification_manifest_sha256",
    "patchyard-extract-result-image",
    "setsid env -i PATH=/usr/local/bin:/usr/bin:/bin \"$JAILER\"",
):
    if required not in launcher:
        errors.append(f"production launcher is missing qualification binding: {required}")
if "tail -n" in launcher:
    errors.append("production launcher can export guest-controlled console lines")
for required in (
    "patchyard-hostile-probe",
    "session5_guest_results",
    "credential_removed_before_output: true",
):
    if required not in guest:
        errors.append(f"guest qualification path is missing: {required}")
if "session5-console-canary=" not in probe:
    errors.append("guest probe does not exercise the serial-console alternate channel")
for required in (
    "RESULT_IMAGE_MAX_BYTES=16777216",
    "runuser -u factory-worker",
    "debugfs -R 'ls -p /'",
):
    if required not in extractor:
        errors.append(f"bounded non-root result extractor is missing: {required}")
for assertion in (
    "extra_result_rejected",
    "missing_result_rejected",
    "symlink_result_rejected",
    "corrupt_filesystem_rejected",
    "oversized_image_rejected",
    "oversized_file_rejected",
):
    if assertion not in result_tester:
        errors.append(f"host result-contract executor is missing: {assertion}")
for required in (
    "PATCHYARD_SESSION5_CANARY",
    "/run/patchyard-session5-canary",
    "session5-privileged-canary-mutated",
):
    if required not in hostile_launch:
        errors.append(f"privileged canary wrapper is missing: {required}")
for required in (
    "grep -R -F -q -- \"$CANARY\"",
    "grep -R -F -q -- \"$CANARY_SHA256\"",
    "length == 24 and all(.status == \"PASS\")",
    "request_residue: false",
    "runtime_residue: false",
):
    if required not in control_runner:
        errors.append(f"control-boundary qualification is missing: {required}")
for required in (
    "hostile-test-manifest.json",
    "patchyard-hostile-launch",
    "patchyard-test-result-contract",
):
    if required not in worker_tasks:
        errors.append(f"worker desired state does not install: {required}")
if "patchyard-run-hostile-qualification" not in control_tasks:
    errors.append("control-plane desired state does not install the hostile runner")

allow_missing = "--allow-missing-results" in sys.argv[1:]
if not RESULT_PATH.exists():
    if not allow_missing:
        errors.append("committed Session 5 hostile-qualification results are missing")
else:
    result = json.loads(RESULT_PATH.read_text())
    result_tests = result.get("session5_results", [])
    if result.get("session5_manifest_sha256") != manifest_sha256:
        errors.append("committed result does not bind the exact hostile manifest")
    if [item.get("id") for item in result_tests] != sorted(ids):
        errors.append("committed result IDs differ from the sorted hostile manifest IDs")
    if len(result_tests) != 24 or any(
        item.get("status") != "PASS" for item in result_tests
    ):
        errors.append("every committed hostile result must pass")
    boundary = result.get("session5_boundary", {})
    if boundary != {
        "privileged_canary_exported": False,
        "serial_console_exported": False,
        "request_residue": False,
        "runtime_residue": False,
    }:
        errors.append("committed boundary result does not prove zero export/residue")
    if "canary_sha256" in result:
        errors.append("committed result contains the synthetic canary marker")

if errors:
    print("worker qualification check: failed", file=sys.stderr)
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    raise SystemExit(1)

result_status = "with live result" if RESULT_PATH.exists() else "static preflight"
print(
    "worker qualification check: pass "
    f"({result_status}; manifest {manifest_sha256})"
)
