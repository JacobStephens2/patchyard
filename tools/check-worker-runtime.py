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
if 'disable "$service"' not in image_builder:
    errors.append("parity services are not disabled independently")
if 'is-enabled "$service"' not in image_builder or "== disabled" not in image_builder:
    errors.append("parity service disabled state is not asserted before image sealing")
if '"$MOUNT_ROOT/etc/httpd/conf.d/ssl.conf"' not in image_builder:
    errors.append("unused guest TLS vhost is not removed from the parity image")
if "listen.acl_users = apache" not in image_builder:
    errors.append("PHP-FPM socket ACL is not narrowed to the installed web identity")
if 'find "$MOUNT_ROOT/var/log" -mindepth 1 ! -type d -delete' not in image_builder:
    errors.append("image sealing does not preserve labelled parity log directories")

guest_runner = (IMAGE / "patchyard-guest-run").read_text()
if "chown factory-agent:factory-agent /work" not in guest_runner:
    errors.append("mounted worktree root is not transferred to the agent identity")
if "context=system_u:object_r:httpd_sys_content_t:s0" not in guest_runner:
    errors.append("mounted worktree is not labelled read-only to the parity web stack")
if "mount --bind /work /var/www/html" not in guest_runner:
    errors.append("package webroot is not overlaid by the labelled parity worktree")
if "$WEBROOT_MOUNTED && umount /var/www/html" not in guest_runner:
    errors.append("parity webroot bind mount is not explicitly torn down")
if "install -m 0640 -o factory-agent -g apache" not in guest_runner:
    errors.append("local-only parity settings are not readable by the PHP runtime group")
if 'WORK_REMOTES=$(runuser -u factory-agent -- git -C /work remote)' not in guest_runner:
    errors.append("guest Git remote preflight can mask a command failure")
if 'WORK_STATUS=$(runuser -u factory-agent -- git -C /work status --porcelain)' not in guest_runner:
    errors.append("guest Git status preflight can mask a command failure")
if "chown factory-agent:factory-agent /work/result.txt" not in guest_runner:
    errors.append("root-run containment probe output is not transferred to the patch identity")
for fixture_failure in (
    "fixture-mysql-prepare-failed",
    "fixture-mysql-datadir-init-failed",
    "fixture-mysql-service-start-failed",
    "fixture-mysql-ready-failed",
    "fixture-mysql-grants-failed",
    "fixture-snapshot-import-failed",
    "fixture-settings-failed",
    "fixture-web-prepare-failed",
    "fixture-php-start-failed",
    "fixture-httpd-start-failed",
    "fixture-web-health-failed",
    "fixture-agent-failed",
    "fixture-parity-probe-failed",
    "fixture-patch-failed",
    "fixture-evidence-failed",
):
    if f"FAILURE={fixture_failure}" not in guest_runner:
        errors.append(f"fixture failure stage is missing: {fixture_failure}")

toy_agent = (IMAGE / "patchyard-toy-agent").read_text()
if 'chmod 0644 "$WORKTREE/mfieldbook/patchyard_session4_probe.php"' not in toy_agent:
    errors.append("fixture agent output is not readable by the parity web identity")

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
extractor = (
    REPO / "worker" / "runtime" / "patchyard-extract-result-image"
).read_text()
if 'find "$SOURCE_STAGE" -type d -exec chmod 0755 {} +' not in launcher:
    errors.append("credential-free source directories are not normalized for web traversal")
if 'find "$SOURCE_STAGE" -type f ! -perm /0111 -exec chmod 0644 {} +' not in launcher:
    errors.append("credential-free source files are not normalized for web reads")
if 'install -m 0400 -o 1000 -g 1000 "$REQUEST" "$INPUT_STAGE/request.md"' not in launcher:
    errors.append("the isolated agent cannot read its root-staged request")
if "'.patchyard-base-sha' 'lost+found/'" not in launcher:
    errors.append("ext4 metadata directory is not excluded from guest Git traversal")
if "/usr/local/libexec/patchyard-extract-result-image" not in launcher:
    errors.append("worker launcher does not use the shared result extractor")
if "debugfs -R 'ls -p /'" not in extractor:
    errors.append("worker result filesystem lacks bounded user-space extraction")
if re.search(r"mount[^\n]*result\.ext4", launcher + extractor):
    errors.append("guest-written result filesystem must never be host-mounted")
if 'mount --bind "$RUN_TMPFS/credential.ext4"' not in launcher:
    errors.append("credential drive is not kept on host tmpfs")
if "RESULT_IMAGE_MAX_BYTES=16777216" not in extractor:
    errors.append("guest-written result image is not bounded before parsing")
if "runuser -u factory-worker" not in extractor:
    errors.append("guest-written result image parser does not drop root")
if 'FIRECRACKER_EXECUTABLE=$(readlink -f -- "$FIRECRACKER")' not in launcher:
    errors.append("jailer path is not derived from the resolved Firecracker executable")
if 'JAIL_RUN_ROOT="$JAIL_BASE/$FIRECRACKER_JAIL_NAME/$RUN_ID"' not in launcher:
    errors.append("staged runtime path does not match jailer's executable-name layout")
if 'chown root:factory-worker \\' not in launcher:
    errors.append("non-root result parser cannot traverse the root-owned jail path")
if 'factory worker run failed: stage=%s line=%s status=%s' not in launcher:
    errors.append("fail-closed runtime diagnostics omit the bounded failing stage")
if '[[ "$RESULT_STATUS" =~ ^[a-z0-9,-]{1,128}$ ]]' not in launcher:
    errors.append("guest failure status is not sanitized before diagnostics")
if "incomplete guest result: file_count=%s expected_mask=%s" not in extractor:
    errors.append("incomplete guest results omit the bounded expected-file mask")
if "tail -n" in launcher or "console-$RUN_ID.log\" >&2" in launcher:
    errors.append("guest serial-console content can cross launcher diagnostics")
if 'setsid env -i PATH=/usr/local/bin:/usr/bin:/bin "$JAILER"' not in launcher:
    errors.append("jailer and Firecracker do not start from an empty environment")
if 'VMM_PID=$(<"$VMM_PID_FILE")' not in launcher:
    errors.append("launcher does not assume lifecycle ownership of jailer's Firecracker PID")
if 'VMM_CMDLINE=$(tr \'\\0\' \' \' <"/proc/$VMM_PID/cmdline")' not in launcher:
    errors.append("launcher PID ownership check can fail from a short-circuited pipeline")
if '[[ "$VMM_CMDLINE" == *"--id $RUN_ID"* ]]' not in launcher:
    errors.append("launcher does not bind the captured Firecracker PID to the run id")
if '"--id[ =]$RUN_ID"' not in launcher:
    errors.append("cleanup does not match Firecracker's separated run-id argument")

for result_runner_name in (
    "patchyard-run-isolation-probe",
    "patchyard-run-fixture",
    "../qualification/patchyard-run-hostile-qualification",
):
    result_runner = (REPO / "worker" / "runtime" / result_runner_name).read_text()
    if 'sudo test ! -e "$OUTPUT_DIR"' not in result_runner:
        errors.append(f"{result_runner_name} does not check the protected destination")
    if 'sudo chown -R factory-web:factory "$RUN_TEMP/result"' not in result_runner:
        errors.append(f"{result_runner_name} does not transfer result ownership")
    if 'sudo mv -- "$RUN_TEMP/result" "$OUTPUT_DIR"' not in result_runner:
        errors.append(f"{result_runner_name} cannot publish into the private artifact store")

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
