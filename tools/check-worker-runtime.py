#!/usr/bin/env python3
"""Mechanical checks for the Session 4 worker desired-state contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys


REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "policy" / "provider-egress.json"
BENCH = REPO / "docs" / "bench.md"
IMAGE = REPO / "worker" / "image"
GROUP_VARS = REPO / "infra" / "ansible" / "group_vars" / "all.yml"
CANDIDATE_PROBE = REPO / "research" / "isolation" / "harness" / "candidate-probe.sh"
PARITY = IMAGE / "production-parity.json"
SNAPSHOT_POLICY = REPO / "policy" / "snapshot-policy.json"
LIFECYCLE_POLICY = REPO / "policy" / "worker-lifecycle.json"


def normalized(value: str) -> str:
    previous = None
    while previous != value:
        previous = value
        value = re.sub(r"\([^()]*\)", "", value)
    return re.sub(r"[^a-z0-9]", "", value.lower())


def roster() -> set[str]:
    flat = re.sub(r"\s+", " ", BENCH.read_text())
    match = re.search(r"provider allowlist.*?union\s*-\s*(.*?)\.", flat)
    if not match:
        raise ValueError("could not parse A61 provider roster")
    return {normalized(item) for item in match.group(1).split(",")}


def recipe_sha256() -> str:
    records = []
    for path in sorted(path for path in IMAGE.rglob("*") if path.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(f"{digest}  {path.relative_to(IMAGE)}\n")
    return hashlib.sha256("".join(records).encode()).hexdigest()


errors: list[str] = []
config = json.loads(CONFIG.read_text())
providers = config.get("providers", {})
configured = {normalized(item["display_name"]) for item in providers.values()}
if configured != roster():
    errors.append(
        "provider egress roster differs from docs/bench.md: "
        f"missing={sorted(roster() - configured)} extra={sorted(configured - roster())}"
    )

hostname_pattern = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
for provider, item in providers.items():
    hosts = item.get("hostnames", [])
    if not hosts or any(not hostname_pattern.fullmatch(host) for host in hosts):
        errors.append(f"{provider}: invalid or empty hostname allowlist")
    if item.get("credential_qualified") is not False:
        errors.append(f"{provider}: credential eligibility advanced before Session 5 evidence")

expected_recipe = recipe_sha256()
pins = (IMAGE / "pins.env").read_text()
parity = json.loads(PARITY.read_text())
pin_values = dict(
    line.split("=", 1)
    for line in pins.splitlines()
    if line and not line.startswith("#") and "=" in line
)
for field, pin in (
    ("php_version", "PHP_VERSION"),
    ("httpd_version", "HTTPD_VERSION"),
    ("mysql_version", "MYSQL_VERSION"),
):
    if parity.get(field) != pin_values.get(pin):
        errors.append(f"production parity {field} differs from {pin}")

php_nevras = {
    line for line in (IMAGE / "php-packages.txt").read_text().splitlines() if line
}
php_rpm_records = [
    line.split()
    for line in (IMAGE / "php-rpms.sha256").read_text().splitlines()
    if line
]
php_rpm_nevras = {
    filename.removesuffix(".x86_64.rpm") for _, filename in php_rpm_records
}
if php_nevras != php_rpm_nevras:
    errors.append("checksum-pinned PHP RPM set differs from production NEVRA set")
for digest, filename in php_rpm_records:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors.append(f"invalid PHP RPM SHA-256: {filename}")
if len(php_rpm_records) != len({filename for _, filename in php_rpm_records}):
    errors.append("checksum-pinned PHP RPM manifest contains duplicates")
if "REMI_SNAPSHOT_BASE_URLS=(" not in pins:
    errors.append("checksum-pinned PHP RPM mirror set is missing")
image_builder = (IMAGE / "build-parity-image").read_text()
if "--setopt=localpkg_gpgcheck=True" not in image_builder:
    errors.append("checksum-pinned PHP RPM signatures are not enforced")

parity_conf = (IMAGE / "patchyard-parity.conf").read_text()
for directive in (
    "DocumentRoot /var/www/html",
    "Options -Indexes +FollowSymLinks",
    "SetEnvIfNoCase ^Authorization$",
    'SetHandler "proxy:unix:/run/php-fpm/www.sock|fcgi://localhost"',
):
    if directive not in parity_conf:
        errors.append(f"production HTTP parity directive missing: {directive}")

snapshot_policy = json.loads(SNAPSHOT_POLICY.read_text())
if snapshot_policy.get("warn_after_days") != 7:
    errors.append("snapshot warning threshold must be seven days")
if snapshot_policy.get("ineligible_after_days") != 30:
    errors.append("snapshot ineligible ceiling must be thirty days")
if "retain the last valid artifact" not in snapshot_policy.get("failure_mode", ""):
    errors.append("snapshot fail-static behavior is not explicit")

lifecycle_policy = json.loads(LIFECYCLE_POLICY.read_text())
if lifecycle_policy.get("run_max_seconds") != 300:
    errors.append("worker run ceiling must be five minutes")
if lifecycle_policy.get("worker_host_max_age_days") != 30:
    errors.append("worker host maximum lifetime must be thirty days")
if len(lifecycle_policy.get("readmission_gates", [])) != 4:
    errors.append("worker replacement readmission gates are incomplete")

launcher = (REPO / "worker" / "runtime" / "patchyard-firecracker-run").read_text()
if "debugfs -R 'ls -p /'" not in launcher:
    errors.append("worker result filesystem lacks bounded user-space extraction")
if re.search(r"mount[^\n]*result\.ext4", launcher):
    errors.append("guest-written result filesystem must never be host-mounted")
if 'mount --bind "$RUN_TMPFS/credential.ext4"' not in launcher:
    errors.append("credential drive is not kept on host tmpfs")
if "RESULT_IMAGE_MAX_BYTES=16777216" not in launcher:
    errors.append("guest-written result image is not bounded before parsing")
if "runuser -u factory-worker" not in launcher:
    errors.append("guest-written result image parser does not drop root")
if 'FIRECRACKER_EXECUTABLE=$(readlink -f -- "$FIRECRACKER")' not in launcher:
    errors.append("jailer path is not derived from the resolved Firecracker executable")
if 'JAIL_ROOT="$JAIL_BASE/$FIRECRACKER_JAIL_NAME/$RUN_ID/root"' not in launcher:
    errors.append("staged runtime path does not match jailer's executable-name layout")
if 'VMM_PID=$(<"$VMM_PID_FILE")' not in launcher:
    errors.append("launcher does not assume lifecycle ownership of jailer's Firecracker PID")
if '"--id[ =]$RUN_ID"' not in launcher:
    errors.append("cleanup does not match Firecracker's separated run-id argument")

group_vars = GROUP_VARS.read_text()
for package_pin in (
    "worker_e2fsprogs_nevra: e2fsprogs-1.46.5-8.el9.x86_64",
    "worker_e2fsprogs_libs_nevra: e2fsprogs-libs-1.46.5-8.el9.x86_64",
    "worker_libcom_err_nevra: libcom_err-1.46.5-8.el9.x86_64",
):
    if package_pin not in group_vars:
        errors.append(f"host result-parser pin missing: {package_pin}")

probe_pin = re.search(r"^CANDIDATE_PROBE_SHA256=([0-9a-f]{64})$", pins, re.MULTILINE)
probe_actual = hashlib.sha256(CANDIDATE_PROBE.read_bytes()).hexdigest()
if not probe_pin or probe_pin.group(1) != probe_actual:
    errors.append(
        f"Session 3 candidate probe pin is stale: actual={probe_actual}"
    )
match = re.search(
    r"^worker_image_recipe_sha256:\s*([0-9a-f]{64})$",
    GROUP_VARS.read_text(),
    re.MULTILINE,
)
if not match:
    errors.append("worker_image_recipe_sha256 is missing from Ansible group vars")
elif match.group(1) != expected_recipe:
    errors.append(
        "worker image recipe pin is stale: "
        f"desired={match.group(1)} actual={expected_recipe}"
    )

if errors:
    print("worker runtime check: failed", file=sys.stderr)
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    raise SystemExit(1)

print(f"worker runtime check: pass (recipe {expected_recipe})")
