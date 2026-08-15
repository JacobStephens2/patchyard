#!/usr/bin/env python3
"""Run and collect the A130 OpenAI crash-cleanup proof.

The frozen lifecycle harness is loaded by exact digest.  A credential child
reserves its root-only tmpfs output before signing, performs one OpenAI token
exchange, and pauses with the assertion and bearer live.  The same bounded
scanner first finds those exact values in the child process image, then runs
after an attended SIGKILL and verifies the process is gone and the run stage
contains no credential-shaped material.  No provider-side invalidation is
attempted or claimed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import socket
import stat
import struct
import subprocess
import sys
import time
import types
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy/openai-wif.json"
POLICY_SHA256 = "87cf13bb136ed9a365bd14822a14d4808a6ef585ce1c278b926fa173d1152e5f"
BASE_HARNESS_PATH = ROOT / "tools/anthropic-wif-lifecycle.py"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
SIGNING_KEY = Path("/etc/patchyard/openai-wif-signing.pem")
STAGING_ROOT = Path("/run/patchyard-openai")
TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
CHECKER_PATHS = (
    ROOT / "tools/check-openai-wif-issuance.py",
    ROOT / "tools/check-openai-wif-expiry.py",
    ROOT / "tools/check-openai-wif-crash-cleanup.py",
)
SUPERVISOR_CEILING_SECONDS = 360
MAX_RESPONSE_BYTES = 1_000_000
MAX_SCAN_FILES = 128
MAX_SCAN_FILE_BYTES = 1_000_000
MAX_SCAN_TOTAL_BYTES = 8_000_000
MAX_MEMORY_REGIONS = 1024
MAX_MEMORY_BYTES = 536_870_912
MEMORY_CHUNK_BYTES = 1_048_576
MAX_CREDENTIAL_BYTES = 1_000_000
RUN_ID_PATTERN = re.compile(r"openai-crash-[0-9]{8}-[0-9a-f]{10}")
SAFE_RESPONSE_STRING = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/+;-]{0,127}")
SAFE_FIELD_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
JWT_PATTERN = re.compile(
    rb"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
)
OPENAI_KEY_PATTERN = re.compile(rb"sk-[A-Za-z0-9_-]{16,}")
PRIVATE_KEY_PATTERN = re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
BEARER_HEADER_PATTERN = re.compile(rb"Bearer [A-Za-z0-9._~-]{16,}", re.IGNORECASE)
FILE_MATERIAL_PATTERNS = (
    ("jwt_assertion", JWT_PATTERN),
    ("openai_bearer", OPENAI_KEY_PATTERN),
    ("openai_bearer", BEARER_HEADER_PATTERN),
    ("private_key", PRIVATE_KEY_PATTERN),
)
SEARCH_MATERIAL_CLASSES = ["jwt_assertion", "openai_bearer", "private_key"]
SEARCH_CONTRACT_VERSION = "a130-openai-run-stage-process-image-v1"
SCAN_SOCKET_NAME = "credential-scan.sock"
TERMINAL_FIELDS = {
    "failed_at",
    "failure_phase",
    "failure_reason",
    "failure_type",
    "partial_evidence",
    "post_failure_state",
}
RESPONSE_PREDICATE = {
    "enforced": False,
    "basis": "no-observed-openai-crash-cleanup-exchange-response",
}
CONTROL_PLANE_PROVENANCE = {
    "control_plane_mutation_claimed": False,
    "mutation_receipt_obtained": False,
    "attestation_required": False,
}


class OpenAICrashError(RuntimeError):
    """A local precondition or bounded capture operation failed."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        del request, file_pointer, code, message, headers, url
        return None


URL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def load_base_harness() -> types.ModuleType:
    source = BASE_HARNESS_PATH.read_bytes()
    if (
        BASE_HARNESS_PATH.is_symlink()
        or hashlib.sha256(source).hexdigest() != BASE_HARNESS_SHA256
    ):
        raise RuntimeError("qualified lifecycle harness differs from its exact binding")
    module = types.ModuleType("anthropic_wif_lifecycle_openai_crash_base")
    module.__file__ = str(BASE_HARNESS_PATH)
    module.__package__ = None
    exec(
        compile(source, str(BASE_HARNESS_PATH), "exec", dont_inherit=True),
        module.__dict__,
    )
    return module


BASE = load_base_harness()
BASE.STAGING_ROOT = STAGING_ROOT
# A144: the OpenAI tools own their signing-key path, so no surface of the
# loaded base harness may still act on the Anthropic path.
BASE.ACTIVE_SIGNING_KEY = SIGNING_KEY


def credential_free_env() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_ADMIN_KEY",
        "PATCHYARD_OPENAI_ADMIN_KEY",
        "OPENAI_ORGANIZATION",
        "OPENAI_PROJECT",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_IDENTITY_TOKEN",
        "ANTHROPIC_IDENTITY_TOKEN_FILE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        environment.pop(name, None)
    return environment


BASE.credential_free_env = credential_free_env


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def iso_epoch(value: int) -> str:
    return BASE.iso_seconds(datetime.fromtimestamp(value, timezone.utc))


def source_binding() -> dict[str, str]:
    return {
        "policy_sha256": BASE.digest_file(POLICY_PATH),
        "base_harness_sha256": BASE.digest_file(BASE_HARNESS_PATH),
        "crash_adapter_sha256": BASE.digest_file(Path(__file__).resolve()),
    }


def validate_run_id(run_id: str) -> None:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise OpenAICrashError("run ID is malformed")


def require_stage_file(path: Path, stage: Path, label: str) -> None:
    BASE.require_stage_path(path, stage, label)
    if path.name in {".", ".."}:
        raise OpenAICrashError(f"{label} has an invalid name")


def load_bounded_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise OpenAICrashError(f"{label} is not a regular non-symlink file")
    metadata = path.stat()
    if not 1 <= metadata.st_size <= MAX_SCAN_FILE_BYTES:
        raise OpenAICrashError(f"{label} is outside the byte limit")
    value = BASE.load_json_file(path)
    if not isinstance(value, dict):
        raise OpenAICrashError(f"{label} is not a JSON object")
    return value


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    BASE.validate_new_output_path(path)
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        BASE.write_all(descriptor, BASE.encoded_json(value))
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def process_start_ticks(pid: int) -> int | None:
    try:
        record = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return None
    closing = record.rfind(")")
    if closing < 0:
        raise OpenAICrashError("target process stat record is malformed")
    fields = record[closing + 2 :].split()
    if len(fields) <= 19 or not fields[19].isdigit():
        raise OpenAICrashError("target process start time is malformed")
    return int(fields[19])


def target_process_present(pid: int, start_ticks: int) -> bool:
    observed = process_start_ticks(pid)
    return observed is not None and observed == start_ticks


def swap_entry_count() -> int:
    lines = Path("/proc/swaps").read_text().splitlines()
    if not lines or not lines[0].startswith("Filename"):
        raise OpenAICrashError("kernel swap inventory is malformed")
    return len(lines) - 1


def disable_core_dumps() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if resource.getrlimit(resource.RLIMIT_CORE) != (0, 0):
        raise OpenAICrashError("credential scanner core dumps remain enabled")


def load_policy() -> dict[str, Any]:
    if POLICY_PATH.is_symlink() or BASE.digest_file(POLICY_PATH) != POLICY_SHA256:
        raise OpenAICrashError("OpenAI WIF policy differs from its frozen binding")
    policy = BASE.load_json_file(POLICY_PATH)
    observed = {
        "provider": policy.get("provider"),
        "issuer_url": policy.get("issuer", {}).get("issuer_url"),
        "audience": policy.get("rule", {}).get("audience"),
        "identity_provider_id": policy.get("issuer", {}).get("id"),
        "service_account_id": policy.get("service_account", {}).get("id"),
        "subject": policy.get("rule", {}).get("subject"),
        "maximum_lifetime": policy.get("issuer", {}).get(
            "max_jwt_lifetime_seconds"
        ),
    }
    expected = {
        "provider": "openai",
        "issuer_url": "https://factory.example.com/workload-identity",
        "audience": "https://api.openai.com",
        "identity_provider_id": "idp_DlzD7RlQXgXxd1VSG2V93eEU",
        "service_account_id": "user-6tzs2hdFVN7GoYQbWfC0eu7k",
        "subject": "patchyard-control-plane",
        "maximum_lifetime": 300,
    }
    if observed != expected:
        raise OpenAICrashError("OpenAI WIF policy fields differ from the contract")
    return policy


def safe_response_string(value: Any) -> str | None:
    if not isinstance(value, str) or SAFE_RESPONSE_STRING.fullmatch(value) is None:
        return None
    encoded = value.encode(errors="ignore")
    if any(
        pattern.search(encoded)
        for pattern in (JWT_PATTERN, OPENAI_KEY_PATTERN, PRIVATE_KEY_PATTERN)
    ):
        return None
    return value


def json_value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unknown"


def field_descriptors(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    descriptors = []
    for name in sorted(value):
        encoded = name.encode(errors="ignore")
        recorded = (
            SAFE_FIELD_NAME.fullmatch(name) is not None
            and not any(
                pattern.search(encoded) for _, pattern in FILE_MATERIAL_PATTERNS
            )
        )
        descriptors.append(
            {
                "name": name if recorded else None,
                "name_recorded": recorded,
                "value_type": json_value_type(value[name]),
            }
        )
    return descriptors


def response_request_id(headers: Any) -> tuple[str | None, bool]:
    values = [
        headers.get(name)
        for name in ("x-request-id", "request-id", "openai-request-id")
        if headers.get(name) is not None
    ]
    if not values:
        return None, False
    unique = {str(value) for value in values}
    if len(unique) != 1:
        return None, True
    return safe_response_string(unique.pop()), True


def response_provider_date(headers: Any) -> str | None:
    value = headers.get("date")
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return BASE.iso_seconds(parsed)


def response_error_type(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        return safe_response_string(error.get("type"))
    return safe_response_string(error)


def sanitize_response(
    status: int,
    headers: Any,
    raw: bytes,
    payload: dict[str, Any],
    requested_at: str,
    observed_at: str,
) -> dict[str, Any]:
    if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        raise OpenAICrashError("provider HTTP status is outside the bounded contract")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise OpenAICrashError("provider response exceeds the byte limit")
    request_id, request_id_supplied = response_request_id(headers)
    content_type = None
    if hasattr(headers, "get_content_type"):
        content_type = safe_response_string(headers.get_content_type())
    expires_in = payload.get("expires_in")
    if not isinstance(expires_in, int) or isinstance(expires_in, bool):
        expires_in = None
    return {
        "source": "openai_http_response",
        "http_status": status,
        "request_started_at": requested_at,
        "observed_at": observed_at,
        "provider_date": response_provider_date(headers),
        "request_id": request_id,
        "request_id_supplied": request_id_supplied,
        "content_type": content_type,
        "body_bytes": len(raw),
        "body_format": "json_object",
        "response_shape": {
            "body_kind": "json_object",
            "top_level_fields": field_descriptors(payload),
            "error_fields": field_descriptors(payload.get("error")),
        },
        "access_token_supplied": "access_token" in payload,
        "expires_in": expires_in,
        "error_type": response_error_type(payload),
    }


def mint_assertion(
    policy: dict[str, Any], run_id: str, now_epoch: int
) -> tuple[str, dict[str, Any]]:
    base_policy = {
        "issuer": {"issuer_url": policy["issuer"]["issuer_url"]},
        "rule": {
            "subject": policy["rule"]["subject"],
            "audience": policy["rule"]["audience"],
            "claims": policy["rule"]["claims"],
        },
    }
    assertion, key = BASE.mint_assertion(
        base_policy, SIGNING_KEY, run_id, now_epoch
    )
    return assertion, {
        "algorithm": "RS256",
        "kid_derived_from_public_der": True,
        "jwk_thumbprint_sha256": key["jwk_thumbprint_sha256"],
        "issued_at": iso_epoch(now_epoch - 5),
        "minted_at": iso_epoch(now_epoch),
        "expires_at": iso_epoch(now_epoch + 295),
        "lifetime_seconds": 300,
    }


def request_bearer(
    policy: dict[str, Any], assertion: str
) -> tuple[dict[str, Any], bytearray]:
    body = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "subject_token": assertion,
        "identity_provider_id": policy["issuer"]["id"],
        "service_account_id": policy["service_account"]["id"],
    }
    encoded = json.dumps(body, separators=(",", ":")).encode()
    request = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=encoded,
        headers={
            "content-type": "application/json",
            "user-agent": "patchyard-openai-wif-crash-cleanup/1",
        },
        method="POST",
    )
    requested_at = iso_time(utc_now())
    try:
        response = URL_OPENER.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        observed_at = iso_time(utc_now())
        if len(raw) > MAX_RESPONSE_BYTES:
            raise OpenAICrashError("provider response exceeds the byte limit")
        try:
            payload = BASE.load_json_bytes(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise OpenAICrashError("OpenAI crash exchange did not return JSON") from error
        if not isinstance(payload, dict):
            raise OpenAICrashError("OpenAI crash exchange JSON is not an object")
        bearer_value = payload.get("access_token")
        if not isinstance(bearer_value, str) or not bearer_value:
            raise OpenAICrashError("OpenAI crash exchange supplied no bearer")
        bearer = bytearray(bearer_value.encode())
        if not 1 <= len(bearer) <= MAX_CREDENTIAL_BYTES:
            raise OpenAICrashError("OpenAI bearer is outside the byte bound")
        observation = sanitize_response(
            int(response.status), response.headers, raw, payload, requested_at, observed_at
        )
    body["subject_token"] = ""
    body.clear()
    encoded = b""
    raw = b""
    payload = None
    bearer_value = ""
    return observation, bearer


def material_fingerprints(
    assertion: bytearray, bearer: bytearray
) -> list[dict[str, Any]]:
    return [
        {
            "material_class": "jwt_assertion",
            "sha256": BASE.digest_bytes(bytes(assertion)),
            "byte_length": len(assertion),
        },
        {
            "material_class": "openai_bearer",
            "sha256": BASE.digest_bytes(bytes(bearer)),
            "byte_length": len(bearer),
        },
    ]


def create_scan_socket(path: Path) -> socket.socket:
    BASE.validate_new_output_path(path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(path))
        os.chmod(path, 0o600)
        server.listen(1)
        server.settimeout(SUPERVISOR_CEILING_SECONDS)
    except BaseException:
        server.close()
        if path.exists() or path.is_symlink():
            path.unlink()
        raise
    return server


def recv_exact(connection: socket.socket, length: int) -> bytes:
    if not 0 <= length <= MAX_CREDENTIAL_BYTES * 2:
        raise OpenAICrashError("credential scan message is outside the byte bound")
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = connection.recv(min(remaining, 65_536))
        if not chunk:
            raise OpenAICrashError("credential scan message ended early")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def serve_positive_scan(
    server: socket.socket,
    socket_path: Path,
    assertion: bytearray,
    bearer: bytearray,
) -> None:
    try:
        connection, _ = server.accept()
        with connection:
            connection.settimeout(30)
            if recv_exact(connection, 5) != b"SCAN\0":
                raise OpenAICrashError("credential scanner handshake differs")
            connection.sendall(struct.pack("!II", len(assertion), len(bearer)))
            connection.sendall(assertion)
            connection.sendall(bearer)
            if recv_exact(connection, 5) != b"FOUND":
                raise OpenAICrashError("credential scanner did not find live material")
    finally:
        server.close()
        if socket_path.exists() or socket_path.is_symlink():
            socket_path.unlink()


def checkpoint_identity(value: dict[str, Any]) -> tuple[int, int]:
    pid = value.get("target_pid")
    start_ticks = value.get("target_start_ticks")
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 1
        or not isinstance(start_ticks, int)
        or isinstance(start_ticks, bool)
        or start_ticks <= 0
    ):
        raise OpenAICrashError("crash checkpoint process identity is malformed")
    return pid, start_ticks


def search_contract(stage: Path, pid: int, start_ticks: int) -> dict[str, Any]:
    return {
        "version": SEARCH_CONTRACT_VERSION,
        "stage_path": str(stage),
        "target_pid": pid,
        "target_start_ticks": start_ticks,
        "file_scope": "all-recursive-regular-files-no-symlinks",
        "process_image_scope": "target-readable-mappings-when-present",
        "material_classes": SEARCH_MATERIAL_CLASSES,
        "max_files": MAX_SCAN_FILES,
        "max_file_bytes": MAX_SCAN_FILE_BYTES,
        "max_total_file_bytes": MAX_SCAN_TOTAL_BYTES,
        "max_memory_regions": MAX_MEMORY_REGIONS,
        "max_memory_bytes": MAX_MEMORY_BYTES,
    }


def receive_live_material(
    socket_path: Path, expected: list[dict[str, Any]]
) -> tuple[dict[str, bytearray], socket.socket]:
    if len(expected) != 2:
        raise OpenAICrashError("checkpoint material fingerprint count differs")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(30)
        client.connect(str(socket_path))
        client.sendall(b"SCAN\0")
        header = recv_exact(client, 8)
        assertion_length, bearer_length = struct.unpack("!II", header)
        if not 1 <= assertion_length <= MAX_CREDENTIAL_BYTES:
            raise OpenAICrashError("live assertion is outside the byte bound")
        if not 1 <= bearer_length <= MAX_CREDENTIAL_BYTES:
            raise OpenAICrashError("live bearer is outside the byte bound")
        materials = {
            "jwt_assertion": bytearray(recv_exact(client, assertion_length)),
            "openai_bearer": bytearray(recv_exact(client, bearer_length)),
        }
        descriptors = material_fingerprints(
            materials["jwt_assertion"], materials["openai_bearer"]
        )
        if descriptors != expected:
            raise OpenAICrashError("live material differs from checkpoint fingerprints")
        return materials, client
    except BaseException:
        client.close()
        raise


def readable_memory_ranges(pid: int) -> list[tuple[int, int]]:
    try:
        lines = Path(f"/proc/{pid}/maps").read_text().splitlines()
    except OSError as error:
        raise OpenAICrashError(f"cannot read target memory map: {error}") from error
    ranges: list[tuple[int, int]] = []
    for line in lines:
        fields = line.split(maxsplit=5)
        if len(fields) < 2 or not fields[1].startswith("r"):
            continue
        try:
            lower_text, upper_text = fields[0].split("-", 1)
            lower = int(lower_text, 16)
            upper = int(upper_text, 16)
        except (ValueError, TypeError) as error:
            raise OpenAICrashError("target memory map is malformed") from error
        if upper > lower:
            ranges.append((lower, upper))
    if not ranges or len(ranges) > MAX_MEMORY_REGIONS:
        raise OpenAICrashError("target readable-memory region count is outside the bound")
    return ranges


def find_material_in_process(
    pid: int, start_ticks: int, materials: dict[str, bytearray]
) -> tuple[set[str], int, int, int]:
    if not target_process_present(pid, start_ticks):
        raise OpenAICrashError("credential process disappeared before positive search")
    ranges = readable_memory_ranges(pid)
    descriptor = os.open(f"/proc/{pid}/mem", os.O_RDONLY | os.O_CLOEXEC)
    found: set[str] = set()
    bytes_examined = 0
    regions_examined = 0
    unreadable_regions = 0
    maximum_needle = max(len(value) for value in materials.values())
    try:
        for lower, upper in ranges:
            regions_examined += 1
            carry = b""
            position = lower
            while position < upper:
                length = min(MEMORY_CHUNK_BYTES, upper - position)
                if bytes_examined + length > MAX_MEMORY_BYTES:
                    raise OpenAICrashError("process-image search exceeds the byte bound")
                try:
                    chunk = os.pread(descriptor, length, position)
                except OSError as error:
                    if error.errno in {errno.EIO, errno.EFAULT, errno.EPERM}:
                        unreadable_regions += 1
                        break
                    raise
                bytes_examined += len(chunk)
                searchable = carry + chunk
                for material_class, needle in materials.items():
                    if material_class not in found and bytes(needle) in searchable:
                        found.add(material_class)
                if len(found) == len(materials):
                    return found, regions_examined, bytes_examined, unreadable_regions
                carry = searchable[-(maximum_needle - 1) :] if maximum_needle > 1 else b""
                if not chunk:
                    break
                position += len(chunk)
    finally:
        os.close(descriptor)
    return found, regions_examined, bytes_examined, unreadable_regions


def scan_stage_files(
    stage: Path, allow_scan_socket: bool
) -> tuple[int, int, list[dict[str, Any]], bool]:
    files: list[Path] = []
    socket_seen = False
    for path in sorted(stage.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise OpenAICrashError("credential search refuses a symlink")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if stat.S_ISSOCK(metadata.st_mode):
            if not allow_scan_socket or path != stage / SCAN_SOCKET_NAME or socket_seen:
                raise OpenAICrashError("credential search found an unexpected socket")
            socket_seen = True
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise OpenAICrashError("credential search refuses a special file")
        files.append(path)
    if len(files) > MAX_SCAN_FILES:
        raise OpenAICrashError("credential search file count exceeds the bound")
    bytes_examined = 0
    matches: list[dict[str, Any]] = []
    for path in files:
        metadata = path.stat()
        if metadata.st_size > MAX_SCAN_FILE_BYTES:
            raise OpenAICrashError("credential search file exceeds the byte bound")
        bytes_examined += metadata.st_size
        if bytes_examined > MAX_SCAN_TOTAL_BYTES:
            raise OpenAICrashError("credential search surface exceeds the byte bound")
        value = path.read_bytes()
        observed: dict[str, int] = {}
        for material_class, pattern in FILE_MATERIAL_PATTERNS:
            observed[material_class] = observed.get(material_class, 0) + len(
                pattern.findall(value)
            )
        for material_class, occurrences in observed.items():
            if occurrences:
                matches.append(
                    {
                        "material_class": material_class,
                        "surface": "run_stage",
                        "location": path.relative_to(stage).as_posix(),
                        "occurrences": occurrences,
                    }
                )
    return len(files), bytes_examined, matches, socket_seen


def scan_surface(
    stage: Path, checkpoint: dict[str, Any]
) -> dict[str, Any]:
    pid, start_ticks = checkpoint_identity(checkpoint)
    core_limits = resource.getrlimit(resource.RLIMIT_CORE)
    if core_limits != (0, 0):
        raise OpenAICrashError("credential scanner core dumps are not disabled")
    swap_entries = swap_entry_count()
    if swap_entries != 0:
        raise OpenAICrashError("credential scanner refuses a host with swap")
    process_present = target_process_present(pid, start_ticks)
    files, file_bytes, matches, socket_seen = scan_stage_files(
        stage, allow_scan_socket=process_present
    )
    regions = 0
    memory_bytes = 0
    unreadable_regions = 0
    client: socket.socket | None = None
    materials: dict[str, bytearray] = {}
    try:
        if process_present:
            socket_path = stage / SCAN_SOCKET_NAME
            if not socket_seen:
                raise OpenAICrashError("live credential scan socket is missing")
            materials, client = receive_live_material(
                socket_path, checkpoint.get("material_fingerprints", [])
            )
            found, regions, memory_bytes, unreadable_regions = find_material_in_process(
                pid, start_ticks, materials
            )
            if found != {"jwt_assertion", "openai_bearer"}:
                raise OpenAICrashError("positive search did not find both live credentials")
            for material_class in sorted(found):
                matches.append(
                    {
                        "material_class": material_class,
                        "surface": "process_image",
                        "location": "target-process-image",
                        "occurrences": 1,
                    }
                )
            client.sendall(b"FOUND")
            client.close()
            client = None
        matches.sort(
            key=lambda item: (
                item["surface"], item["location"], item["material_class"]
            )
        )
        classes = sorted({item["material_class"] for item in matches})
        result = {
            "schema_version": 1,
            "provider": "openai",
            "event_type": "credential_surface_search",
            "observed_at": iso_time(utc_now()),
            "search_contract": search_contract(stage, pid, start_ticks),
            "search_contract_sha256": BASE.digest_bytes(
                json.dumps(
                    search_contract(stage, pid, start_ticks),
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
            ),
            "files_examined": files,
            "file_bytes_examined": file_bytes,
            "memory_regions_examined": regions,
            "memory_bytes_examined": memory_bytes,
            "unreadable_memory_regions": unreadable_regions,
            "credential_material_found": bool(matches),
            "material_classes_found": classes,
            "matches": matches,
            "target_process_present": process_present,
            "scan_socket_used": process_present,
            "scanner_core_dump_limits": list(core_limits),
            "swap_entries": swap_entries,
            "source": source_binding(),
        }
        return result
    finally:
        if client is not None:
            client.close()
        for material in materials.values():
            material[:] = b"\x00" * len(material)


def validate_positive_search(
    value: dict[str, Any], stage: Path, pid: int, start_ticks: int
) -> None:
    if value.get("event_type") != "credential_surface_search":
        raise OpenAICrashError("positive control is not a credential search")
    if value.get("search_contract") != search_contract(stage, pid, start_ticks):
        raise OpenAICrashError("positive control searched a different surface")
    if value.get("target_process_present") is not True:
        raise OpenAICrashError("positive control did not observe the live process")
    if value.get("scan_socket_used") is not True:
        raise OpenAICrashError("positive control did not use the live scan channel")
    if value.get("scanner_core_dump_limits") != [0, 0] or value.get("swap_entries") != 0:
        raise OpenAICrashError("positive-control scanner persistence guards differ")
    if value.get("credential_material_found") is not True:
        raise OpenAICrashError("positive control found no credential material")
    if value.get("material_classes_found") != ["jwt_assertion", "openai_bearer"]:
        raise OpenAICrashError("positive control did not find both live credentials")
    expected_matches = [
        {
            "material_class": "jwt_assertion",
            "surface": "process_image",
            "location": "target-process-image",
            "occurrences": 1,
        },
        {
            "material_class": "openai_bearer",
            "surface": "process_image",
            "location": "target-process-image",
            "occurrences": 1,
        },
    ]
    expected_matches.sort(key=lambda item: (item["surface"], item["location"], item["material_class"]))
    if value.get("matches") != expected_matches:
        raise OpenAICrashError("positive control found material outside the process image")
    if value.get("memory_regions_examined", 0) <= 0 or value.get(
        "memory_bytes_examined", 0
    ) <= 0:
        raise OpenAICrashError("positive control did not inspect the process image")
    if value.get("source") != source_binding():
        raise OpenAICrashError("positive control source binding differs")


def validate_post_kill_search(
    value: dict[str, Any], stage: Path, pid: int, start_ticks: int
) -> None:
    if value.get("event_type") != "credential_surface_search":
        raise OpenAICrashError("post-kill result is not a credential search")
    if value.get("search_contract") != search_contract(stage, pid, start_ticks):
        raise OpenAICrashError("post-kill search used a different surface")
    if value.get("target_process_present") is not False:
        raise OpenAICrashError("killed credential process remains present")
    if value.get("scan_socket_used") is not False:
        raise OpenAICrashError("post-kill search used a credential channel")
    if value.get("scanner_core_dump_limits") != [0, 0] or value.get("swap_entries") != 0:
        raise OpenAICrashError("post-kill scanner persistence guards differ")
    if value.get("credential_material_found") is not False:
        raise OpenAICrashError("post-kill search recovered credential material")
    if value.get("material_classes_found") != [] or value.get("matches") != []:
        raise OpenAICrashError("post-kill search has credential matches")
    if value.get("memory_regions_examined") != 0 or value.get("memory_bytes_examined") != 0:
        raise OpenAICrashError("post-kill search claims a surviving process image")
    if value.get("source") != source_binding():
        raise OpenAICrashError("post-kill search source binding differs")


def failed_record(
    action: str,
    run_id: str,
    started_at: str,
    phase: str,
    error: BaseException,
    post_failure_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": "openai",
        "status": "failed",
        "action": action,
        "run_id": run_id,
        "started_at": started_at,
        "failed_at": iso_time(utc_now()),
        "failure_type": error.__class__.__name__,
        "failure_reason": safe_failure_reason(error),
        "failure_phase": phase,
        "partial_evidence": {},
        "post_failure_state": post_failure_state or {},
        "provider_response_observed": False,
        "qualification_evidence": False,
        "source": source_binding(),
    }


def run_probe(args: argparse.Namespace) -> int:
    stage = BASE.validate_stage_directory(args.run_id)
    for path, label in (
        (args.attempt_output, "crash attempt output"),
        (args.checkpoint_output, "crash checkpoint output"),
    ):
        require_stage_file(path, stage, label)
    started_at = iso_time(utc_now())
    output = BASE.ReservedOutput(
        args.attempt_output,
        {
            "schema_version": 1,
            "provider": "openai",
            "status": "in_progress",
            "action": "crash-cleanup-probe",
            "run_id": args.run_id,
            "started_at": started_at,
            "source": source_binding(),
        },
    )
    phase = "local_preflight"
    assertion = bytearray()
    bearer = bytearray()
    scan_socket: socket.socket | None = None
    socket_path = stage / SCAN_SOCKET_NAME
    try:
        disable_core_dumps()
        if swap_entry_count() != 0:
            raise OpenAICrashError("credential process refuses a host with swap")
        BASE.validate_root_private_key(SIGNING_KEY)
        policy = load_policy()
        now_epoch = int(time.time())
        assertion_text, assertion_descriptor = mint_assertion(
            policy, args.run_id, now_epoch
        )
        assertion = bytearray(assertion_text.encode())
        assertion_text = ""
        phase = "token_exchange"
        exchange, bearer = request_bearer(policy, assertion.decode())
        phase = "bearer_live_before_terminal_write"
        pid = os.getpid()
        start_ticks = process_start_ticks(pid)
        if start_ticks is None:
            raise OpenAICrashError("credential process identity disappeared")
        scan_socket = create_scan_socket(socket_path)
        checkpoint = {
            "schema_version": 1,
            "provider": "openai",
            "run_id": args.run_id,
            "phase": phase,
            "observed_at": iso_time(utc_now()),
            "target_pid": pid,
            "target_start_ticks": start_ticks,
            "assertion_live": True,
            "bearer_live": True,
            "terminal_record_written": False,
            "core_dump_limits": [0, 0],
            "swap_entries": 0,
            "signing_key": {
                "kid_derived_from_public_der": True,
                "jwk_thumbprint_sha256": assertion_descriptor[
                    "jwk_thumbprint_sha256"
                ],
                "stable_source_preserved": True,
                "copied_to_run_stage": False,
                "private_key_bytes_loaded_by_adapter": False,
            },
            "assertion": {
                "issued_at": assertion_descriptor["issued_at"],
                "minted_at": assertion_descriptor["minted_at"],
                "expires_at": assertion_descriptor["expires_at"],
                "lifetime_seconds": assertion_descriptor["lifetime_seconds"],
            },
            "exchange_request": {
                "endpoint": TOKEN_ENDPOINT,
                "attempt_count": 1,
                "requested_at": exchange["request_started_at"],
            },
            "exchange_response": exchange,
            "material_fingerprints": material_fingerprints(assertion, bearer),
            "attempt_sha256": BASE.digest_file(args.attempt_output),
            "source": source_binding(),
        }
        write_new_json(args.checkpoint_output, checkpoint)
        print(
            f"openai_crash_cleanup_ready pid={pid} checkpoint={args.checkpoint_output}",
            flush=True,
        )
        serve_positive_scan(scan_socket, socket_path, assertion, bearer)
        scan_socket = None
        phase = "positive_search_complete_bearer_live"
        print("openai_crash_cleanup_positive_search_complete", flush=True)
        while assertion and bearer:
            signal.pause()
        raise OpenAICrashError("credential material was released without SIGKILL")
    except BaseException as error:
        if scan_socket is not None:
            scan_socket.close()
        if socket_path.exists() or socket_path.is_symlink():
            socket_path.unlink()
        output.finish(
            failed_record(
                "crash-cleanup-probe",
                args.run_id,
                started_at,
                phase,
                error,
                {"credential_process_exiting": True},
            )
        )
        raise


def remove_scan_socket(stage: Path) -> bool:
    path = stage / SCAN_SOCKET_NAME
    if not path.exists() and not path.is_symlink():
        return False
    metadata = path.lstat()
    if not stat.S_ISSOCK(metadata.st_mode):
        raise OpenAICrashError("scan socket cleanup target is not a socket")
    path.unlink()
    directory = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return True


def run_supervise(args: argparse.Namespace) -> int:
    stage = BASE.validate_stage_directory(args.run_id)
    for path, label in (
        (args.attempt_output, "crash attempt output"),
        (args.checkpoint_output, "crash checkpoint output"),
        (args.positive_control, "positive-control output"),
        (args.kill_output, "kill observation output"),
    ):
        require_stage_file(path, stage, label)
    started_at = iso_time(utc_now())
    output = BASE.ReservedOutput(
        args.kill_output,
        {
            "schema_version": 1,
            "provider": "openai",
            "status": "in_progress",
            "action": "crash-cleanup-supervise",
            "run_id": args.run_id,
            "started_at": started_at,
            "source": source_binding(),
        },
    )
    phase = "credential_process_start"
    child: subprocess.Popen[bytes] | None = None
    try:
        command = [
            sys.executable,
            "-I",
            str(Path(__file__).resolve()),
            "_probe",
            "--run-id",
            args.run_id,
            "--attempt-output",
            str(args.attempt_output),
            "--checkpoint-output",
            str(args.checkpoint_output),
        ]
        child = subprocess.Popen(command, env=credential_free_env())
        print(f"openai_crash_cleanup_supervisor child_pid={child.pid}", flush=True)
        phase = "awaiting_attended_sigkill"
        timed_out = False
        try:
            returncode = child.wait(timeout=SUPERVISOR_CEILING_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            child.kill()
            returncode = child.wait()
        exited_at = iso_time(utc_now())
        socket_removed = remove_scan_socket(stage)
        checkpoint = load_bounded_json(args.checkpoint_output, "crash checkpoint")
        pid, start_ticks = checkpoint_identity(checkpoint)
        if pid != child.pid:
            raise OpenAICrashError("checkpoint names a different credential process")
        positive = load_bounded_json(args.positive_control, "positive control")
        validate_positive_search(positive, stage, pid, start_ticks)
        positive_time = datetime.fromisoformat(
            str(positive["observed_at"]).replace("Z", "+00:00")
        )
        exit_time = datetime.fromisoformat(exited_at.replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(
            str(checkpoint.get("assertion", {}).get("expires_at", "")).replace(
                "Z", "+00:00"
            )
        )
        if positive_time > exit_time:
            raise OpenAICrashError("positive control was captured after process death")
        if not exit_time < expires_at:
            raise OpenAICrashError("SIGKILL did not occur inside the credential lifetime")
        if timed_out:
            raise OpenAICrashError("attended SIGKILL was not observed before the ceiling")
        if returncode != -signal.SIGKILL:
            signal_name = (
                signal.Signals(-returncode).name if returncode < 0 else "not_signaled"
            )
            raise OpenAICrashError(
                f"credential process ended by {signal_name}, not SIGKILL"
            )
        if target_process_present(pid, start_ticks):
            raise OpenAICrashError("SIGKILL target process remains present")
        attempt_sha256 = BASE.digest_file(args.attempt_output)
        if attempt_sha256 != checkpoint.get("attempt_sha256"):
            raise OpenAICrashError("in-progress record changed after checkpoint")
        phase = "terminal_write"
        output.finish(
            {
                "schema_version": 1,
                "provider": "openai",
                "run_id": args.run_id,
                "event_type": "credential_process_sigkill_observed",
                "observed_at": exited_at,
                "target_pid": pid,
                "target_start_ticks": start_ticks,
                "signal_name": "SIGKILL",
                "signal_number": int(signal.SIGKILL),
                "child_returncode": returncode,
                "supervisor_timed_out": False,
                "target_process_present": False,
                "scan_socket_present_after_cleanup": False,
                "scan_socket_cleanup_required": socket_removed,
                "checkpoint_sha256": BASE.digest_file(args.checkpoint_output),
                "positive_control_sha256": BASE.digest_file(args.positive_control),
                "attempt_sha256": attempt_sha256,
                "source": source_binding(),
            }
        )
        return 0
    except BaseException as error:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
        cleanup_error: BaseException | None = None
        try:
            remove_scan_socket(stage)
        except BaseException as observed_cleanup_error:
            cleanup_error = observed_cleanup_error
        if cleanup_error is not None:
            error = OpenAICrashError(
                f"{safe_failure_reason(error)}; scan-socket cleanup failed: "
                f"{safe_failure_reason(cleanup_error)}"
            )
        output.finish(
            failed_record(
                "crash-cleanup-supervise",
                args.run_id,
                started_at,
                phase,
                error,
                {
                    "credential_process_present": (
                        child is not None and child.poll() is None
                    ),
                    "child_returncode": child.returncode if child is not None else None,
                    "scan_socket_present": (stage / SCAN_SOCKET_NAME).exists(),
                },
            )
        )
        raise


def run_scan(args: argparse.Namespace) -> int:
    stage = BASE.validate_stage_directory(args.run_id)
    require_stage_file(args.checkpoint, stage, "crash checkpoint")
    require_stage_file(args.output, stage, "credential search output")
    checkpoint = load_bounded_json(args.checkpoint, "crash checkpoint")
    started_at = iso_time(utc_now())
    output = BASE.ReservedOutput(
        args.output,
        {
            "schema_version": 1,
            "provider": "openai",
            "status": "in_progress",
            "action": "crash-cleanup-scan",
            "run_id": args.run_id,
            "started_at": started_at,
            "source": source_binding(),
        },
    )
    try:
        disable_core_dumps()
        result = scan_surface(stage, checkpoint)
        result["run_id"] = args.run_id
        output.finish(result)
    except BaseException as error:
        output.finish(
            failed_record(
                "crash-cleanup-scan", args.run_id, started_at, "surface_search", error
            )
        )
        raise
    print(
        "openai_crash_cleanup_scan "
        f"credential_material_found={str(result['credential_material_found']).lower()} "
        f"target_process_present={str(result['target_process_present']).lower()}",
        flush=True,
    )
    return 0


def checker_rejections(attempt_path: Path) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for checker in CHECKER_PATHS:
        if checker.is_symlink() or not checker.is_file():
            raise OpenAICrashError(f"qualification checker is missing: {checker.name}")
        completed = subprocess.run(
            [sys.executable, "-I", str(checker), "--evidence", str(attempt_path)],
            check=False,
            capture_output=True,
            timeout=30,
            env=credential_free_env(),
        )
        observations.append(
            {
                "checker": checker.name,
                "checker_sha256": BASE.digest_file(checker),
                "exit_code": completed.returncode,
                "accepted": completed.returncode == 0,
            }
        )
    if any(item["accepted"] for item in observations):
        raise OpenAICrashError("an OpenAI checker accepted the in-progress record")
    if any(item["exit_code"] != 1 for item in observations):
        raise OpenAICrashError("an OpenAI checker returned an unexpected rejection")
    return observations


def contains_credential_material(value: Any) -> bool:
    serialized = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return any(pattern.search(serialized) for _, pattern in FILE_MATERIAL_PATTERNS)


def run_collect(args: argparse.Namespace) -> int:
    stage = BASE.validate_stage_directory(args.run_id)
    inputs = (
        (args.attempt, "in-progress attempt"),
        (args.checkpoint, "crash checkpoint"),
        (args.kill_observation, "kill observation"),
        (args.positive_control, "positive control"),
        (args.post_kill_search, "post-kill search"),
    )
    for path, label in (*inputs, (args.output, "crash-cleanup Result")):
        require_stage_file(path, stage, label)
    started_at = iso_time(utc_now())
    output = BASE.ReservedOutput(
        args.output,
        {
            "schema_version": 1,
            "provider": "openai",
            "status": "in_progress",
            "action": "crash-cleanup-collect",
            "run_id": args.run_id,
            "started_at": started_at,
            "source": source_binding(),
        },
    )
    phase = "input_validation"
    try:
        attempt = load_bounded_json(args.attempt, "in-progress attempt")
        checkpoint = load_bounded_json(args.checkpoint, "crash checkpoint")
        kill = load_bounded_json(args.kill_observation, "kill observation")
        positive = load_bounded_json(args.positive_control, "positive control")
        post = load_bounded_json(args.post_kill_search, "post-kill search")
        pid, start_ticks = checkpoint_identity(checkpoint)
        validate_positive_search(positive, stage, pid, start_ticks)
        validate_post_kill_search(post, stage, pid, start_ticks)
        if positive.get("search_contract") != post.get("search_contract"):
            raise OpenAICrashError("positive and post-kill searches differ")
        if positive.get("search_contract_sha256") != post.get(
            "search_contract_sha256"
        ):
            raise OpenAICrashError("search instrument changed between controls")
        expected_attempt = {
            "schema_version": 1,
            "provider": "openai",
            "status": "in_progress",
            "action": "crash-cleanup-probe",
            "run_id": args.run_id,
            "started_at": attempt.get("started_at"),
            "source": source_binding(),
        }
        if attempt != expected_attempt:
            raise OpenAICrashError("abrupt-death record is not exact in-progress state")
        if TERMINAL_FIELDS.intersection(attempt):
            raise OpenAICrashError("in-progress record carries terminal fields")
        attempt_sha256 = BASE.digest_file(args.attempt)
        if not (
            checkpoint.get("attempt_sha256")
            == kill.get("attempt_sha256")
            == attempt_sha256
        ):
            raise OpenAICrashError("in-progress record was completed or relabelled")
        if kill.get("event_type") != "credential_process_sigkill_observed":
            raise OpenAICrashError("credential process has no SIGKILL observation")
        if kill.get("signal_name") != "SIGKILL" or kill.get("signal_number") != 9:
            raise OpenAICrashError("credential process was not terminated by SIGKILL")
        if kill.get("child_returncode") != -9 or kill.get("supervisor_timed_out") is not False:
            raise OpenAICrashError("SIGKILL wait observation differs")
        if kill.get("target_process_present") is not False:
            raise OpenAICrashError("SIGKILL target remains present")
        if kill.get("scan_socket_present_after_cleanup") is not False:
            raise OpenAICrashError("SIGKILL scan socket remains present")
        if kill.get("target_pid") != pid or kill.get("target_start_ticks") != start_ticks:
            raise OpenAICrashError("SIGKILL observation names a different process")
        if kill.get("checkpoint_sha256") != BASE.digest_file(args.checkpoint):
            raise OpenAICrashError("kill observation binds a different checkpoint")
        if kill.get("positive_control_sha256") != BASE.digest_file(args.positive_control):
            raise OpenAICrashError("kill observation binds a different positive control")
        if kill.get("source") != source_binding():
            raise OpenAICrashError("kill observation source binding differs")
        phase = "checker_rejection_observation"
        rejections = checker_rejections(args.attempt)
        phase = "result_assembly"
        final = {
            "schema_version": 1,
            "provider": "openai",
            "qualification_requirement": "crash-cleanup-local-non-recoverability",
            "authorization_ruling": "A130",
            "run_id": args.run_id,
            "checkpoint": checkpoint,
            "kill": kill,
            "positive_control": positive,
            "post_kill_search": post,
            "in_progress_record": {
                "path": str(args.attempt),
                "record": attempt,
                "sha256_at_checkpoint": checkpoint.get("attempt_sha256"),
                "sha256_after_sigkill": kill.get("attempt_sha256"),
                "sha256_at_collection": attempt_sha256,
                "unchanged": True,
                "terminal_fields_present": [],
            },
            "checker_rejections": rejections,
            "provider_exposure_boundary": {
                "proof_scope": "local-host-non-recoverability-only",
                "provider_side_invalidation_proven": False,
                "provider_denial_observed": False,
                "killed_bearer_may_remain_valid_until": "natural-expiry",
                "maximum_assertion_lifetime_seconds": 300,
                "separate_expiry_requirement": "credential-expiry-denial",
                "stable_signing_identity_preserved": True,
                "stable_signing_identity_in_proof_scope": False,
            },
            "response_predicate": RESPONSE_PREDICATE,
            "control_plane_provenance": CONTROL_PLANE_PROVENANCE,
            "provenance_limitation": "A128-attended-record-not-provider-attestation",
            "provider_response_observed": True,
            "qualification_evidence": False,
            "source": source_binding(),
        }
        if contains_credential_material(final):
            raise OpenAICrashError("assembled Result contains credential material")
        phase = "terminal_write"
        output.finish(final)
    except BaseException as error:
        output.finish(
            failed_record(
                "crash-cleanup-collect", args.run_id, started_at, phase, error
            )
        )
        raise
    print(f"openai_crash_cleanup_result={args.output} run_id={args.run_id}")
    return 0


def safe_failure_reason(error: BaseException) -> str:
    reason = re.sub(r"[^A-Za-z0-9 ._:/?=+,'()\[\]-]", "?", str(error))[:512]
    encoded = reason.encode(errors="ignore")
    if any(pattern.search(encoded) for _, pattern in FILE_MATERIAL_PATTERNS):
        return "credential-bearing diagnostic suppressed"
    return reason or error.__class__.__name__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    probe = subparsers.add_parser("_probe", help=argparse.SUPPRESS)
    probe.add_argument("--run-id", required=True)
    probe.add_argument("--attempt-output", required=True, type=Path)
    probe.add_argument("--checkpoint-output", required=True, type=Path)
    supervise = subparsers.add_parser("supervise")
    supervise.add_argument("--run-id", required=True)
    supervise.add_argument("--attempt-output", required=True, type=Path)
    supervise.add_argument("--checkpoint-output", required=True, type=Path)
    supervise.add_argument("--positive-control", required=True, type=Path)
    supervise.add_argument("--kill-output", required=True, type=Path)
    scan = subparsers.add_parser("scan")
    scan.add_argument("--run-id", required=True)
    scan.add_argument("--checkpoint", required=True, type=Path)
    scan.add_argument("--output", required=True, type=Path)
    collect = subparsers.add_parser("collect")
    collect.add_argument("--run-id", required=True)
    collect.add_argument("--attempt", required=True, type=Path)
    collect.add_argument("--checkpoint", required=True, type=Path)
    collect.add_argument("--kill-observation", required=True, type=Path)
    collect.add_argument("--positive-control", required=True, type=Path)
    collect.add_argument("--post-kill-search", required=True, type=Path)
    collect.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    if os.geteuid() != 0:
        raise OpenAICrashError("OpenAI crash-cleanup harness must run as root")
    os.umask(0o077)
    args = build_parser().parse_args()
    validate_run_id(args.run_id)
    if args.action == "_probe":
        return run_probe(args)
    if args.action == "supervise":
        return run_supervise(args)
    if args.action == "scan":
        return run_scan(args)
    return run_collect(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OpenAICrashError,
        BASE.LifecycleError,
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        urllib.error.URLError,
        KeyboardInterrupt,
    ) as error:
        print(f"OpenAI WIF crash cleanup: {safe_failure_reason(error)}", file=sys.stderr)
        raise SystemExit(1)
