#!/usr/bin/env python3
"""Forced-command lease manager for the shared Fieldbook preview host."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import hashlib


ROOT = Path("/opt/preview-fieldbooks")
SLOTS = ROOT / "slots.json"
LOCK = ROOT / ".factory-slots.lock"
MAX_SLOTS = 30
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
LEASE = re.compile(r"^[0-9a-f]{32}$")
CAPABILITY = re.compile(r"^[0-9a-f]{32}$")
CAPABILITIES = Path("/var/lib/patchyard-preview/capabilities")
FACTORY_SLOT_COMPOSE = Path("/etc/patchyard-preview/docker-compose.factory-slot.yml")
MAX_LOG_SCAN_BYTES = 16 * 1024 * 1024


def now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@contextmanager
def slot_lock():
    LOCK.touch(mode=0o600, exist_ok=True)
    with LOCK.open("r+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def load_slots() -> dict[str, dict]:
    try:
        value = json.loads(SLOTS.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise RuntimeError("canonical preview slot state is unavailable") from error
    if not isinstance(value, dict):
        raise RuntimeError("canonical preview slot state is not an object")
    return value


def write_slots(value: dict[str, dict]) -> None:
    temporary = SLOTS.with_suffix(".json.factory-tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.chmod(temporary, 0o644)
    os.replace(temporary, SLOTS)


def capability_path(capability_id: str) -> Path:
    return CAPABILITIES / f"{capability_id}.json"


def write_capability(capability_id: str, value: dict) -> None:
    CAPABILITIES.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = capability_path(capability_id)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def remove_lease_capabilities(lease_id: str) -> list[str]:
    errors: list[str] = []
    for path in CAPABILITIES.glob("*.json"):
        try:
            value = json.loads(path.read_text())
            if value.get("lease_id") == lease_id:
                path.unlink()
        except (OSError, json.JSONDecodeError):
            errors.append(path.name)
    return errors


def environment_token() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("GITHUB_TOKEN="):
            value = line.split("=", 1)[1]
            if value:
                return value
    raise RuntimeError("preview GitHub build token is unavailable")


def compose(slot: int, *arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    entry = load_slots().get(str(slot), {})
    branch = entry.get("branch", "factory") if isinstance(entry, dict) else "factory"
    environment = {
        "HOME": "/home/conductor",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PREVIEW_BRANCH": branch,
        "PREVIEW_SLOT": str(slot),
    }
    return subprocess.run(
        [
            "/usr/bin/docker", "compose", "-p", f"preview-{slot}",
            "-f", "docker-compose.editable.yml",
            "-f", str(FACTORY_SLOT_COMPOSE),
            "--env-file", ".env", *arguments,
        ],
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=180,
        check=check,
    )


def lease_entry(slot: int, lease_id: str) -> tuple[dict[str, dict], dict]:
    slots = load_slots()
    entry = slots.get(str(slot))
    if not isinstance(entry, dict):
        raise RuntimeError("lease slot is absent")
    lease = entry.get("factory_lease")
    if not isinstance(lease, dict) or lease.get("lease_id") != lease_id:
        raise RuntimeError("lease ownership does not match")
    return slots, entry


def find_lease(slots: dict[str, dict], lease_id: str) -> tuple[int, dict] | None:
    found: list[tuple[int, dict]] = []
    for slot, entry in slots.items():
        lease = entry.get("factory_lease") if isinstance(entry, dict) else None
        if isinstance(lease, dict) and lease.get("lease_id") == lease_id:
            found.append((int(slot), entry))
    if len(found) > 1:
        raise RuntimeError("lease id is duplicated")
    return found[0] if found else None


def remove_runtime(slot: int) -> list[str]:
    errors: list[str] = []
    try:
        compose(slot, "down", "-v", check=False)
    except (OSError, subprocess.SubprocessError):
        errors.append("compose-down")
    checkout = ROOT / "checkouts" / str(slot)
    try:
        subprocess.run(
            [
                "/usr/bin/docker", "run", "--rm",
                "-v", f"{ROOT / 'checkouts'}:/x", "alpine:3",
                "rm", "-rf", f"/x/{slot}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        errors.append("checkout-remove")
    try:
        containers = subprocess.run(
            [
                "/usr/bin/docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.project=preview-{slot}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout.strip()
        if containers:
            errors.append("compose-residue")
    except (OSError, subprocess.SubprocessError):
        errors.append("compose-inspect")
    if checkout.exists():
        errors.append("checkout-residue")
    return errors


def destroy(slot: int, lease_id: str) -> dict:
    with slot_lock():
        slots = load_slots()
        located = find_lease(slots, lease_id)
        if located is None:
            entry = slots.get(str(slot))
            if isinstance(entry, dict) and entry.get("factory_lease") is not None:
                raise RuntimeError("slot belongs to another lease")
            was_absent = True
        else:
            actual_slot, _ = located
            if actual_slot != slot:
                raise RuntimeError("lease moved to another slot")
            was_absent = False

    errors = remove_runtime(slot)
    with slot_lock():
        slots = load_slots()
        if was_absent:
            entry = slots.get(str(slot))
            if isinstance(entry, dict) and entry.get("factory_lease") is not None:
                raise RuntimeError("slot was acquired while cleanup ran")
            slots.pop(str(slot), None)
        else:
            slots, _ = lease_entry(slot, lease_id)
            del slots[str(slot)]
        write_slots(slots)
        absent = str(slot) not in load_slots()
        capability_errors = remove_lease_capabilities(lease_id)
    errors.extend(f"capability:{name}" for name in capability_errors)
    complete = absent and not errors
    return {
        "slot": slot,
        "lease_id": lease_id,
        "cleanup_complete": complete,
        "cleanup_errors": errors,
        "already_absent": was_absent,
    }


def destroy_by_id(lease_id: str) -> dict:
    with slot_lock():
        located = find_lease(load_slots(), lease_id)
        if located is None:
            capability_errors = remove_lease_capabilities(lease_id)
            return {
                "slot": None,
                "lease_id": lease_id,
                "cleanup_complete": not capability_errors,
                "cleanup_errors": [
                    f"capability:{name}" for name in capability_errors
                ],
                "already_absent": True,
            }
        slot, _ = located
    return destroy(slot, lease_id)


def rev_parse(slot: int) -> tuple[str, str]:
    checkout = ROOT / "checkouts" / str(slot)
    host = subprocess.run(
        ["/usr/bin/git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    ).stdout.strip()
    guest = subprocess.run(
        [
            "/usr/bin/docker", "compose", "-p", f"preview-{slot}",
            "-f", "docker-compose.editable.yml", "--env-file", ".env",
            "exec", "-T", "fieldbook", "git",
            "-c", "safe.directory=/var/www/html",
            "-C", "/var/www/html", "rev-parse", "HEAD",
        ],
        cwd=ROOT,
        env={"HOME": "/home/conductor", "PATH": "/usr/local/bin:/usr/bin:/bin", "PREVIEW_SLOT": str(slot)},
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    ).stdout.strip()
    return host, guest


def acquire(args: argparse.Namespace) -> dict:
    lease_id = args.lease_id
    created = now()
    with slot_lock():
        located = find_lease(load_slots(), lease_id)
    if located is not None:
        existing_slot, existing = located
        lease = existing["factory_lease"]
        if (
            existing.get("branch") != args.branch
            or lease.get("owner") != args.owner
            or lease.get("request_id") != args.request_id
            or lease.get("expected_sha") != args.expected_sha
        ):
            raise RuntimeError("existing lease id belongs to another contract")
        if existing.get("status") == "running":
            host_sha, guest_sha = rev_parse(existing_slot)
            if host_sha != args.expected_sha or guest_sha != args.expected_sha:
                raise RuntimeError("recovered preview HEAD does not match expected SHA")
            return {
                "ok": True,
                "slot": existing_slot,
                "url": f"https://{existing_slot}.preview.example.dev",
                "lease_id": lease_id,
                "owner": args.owner,
                "request_id": args.request_id,
                "expected_sha": args.expected_sha,
                "host_head": host_sha,
                "preview_head": guest_sha,
                "expires_at": lease["expires_at"],
            }
        cleanup = destroy(existing_slot, lease_id)
        if not cleanup["cleanup_complete"]:
            raise RuntimeError("incomplete recovered lease could not be cleaned")

    with slot_lock():
        slots = load_slots()
        slot = next((number for number in range(1, MAX_SLOTS + 1) if str(number) not in slots), None)
        if slot is None:
            raise RuntimeError("all preview slots are occupied")
        slots[str(slot)] = {
            "branch": args.branch,
            "mode": "editable",
            "sha": args.expected_sha,
            "started": stamp(created),
            "status": "starting",
            "factory_lease": {
                "lease_id": lease_id,
                "owner": args.owner,
                "request_id": args.request_id,
                "expected_sha": args.expected_sha,
                "created_at": stamp(created),
                "expires_at": stamp(created + timedelta(seconds=args.ttl_seconds)),
            },
        }
        write_slots(slots)

    try:
        environment = {
            "BUILD_GEN": lease_id,
            "GITHUB_TOKEN": environment_token(),
            "HOME": "/home/conductor",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
        }
        subprocess.run(
            [str(ROOT / "scripts/build-editable.sh"), str(slot), args.branch],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=min(args.ttl_seconds, 1200),
            check=True,
        )
        subprocess.run(
            ["/usr/bin/git", "-C", str(ROOT / "checkouts" / str(slot)),
             "checkout", "--detach", args.expected_sha],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=True,
        )
        compose(slot, "up", "-d")
        host_sha, guest_sha = rev_parse(slot)
        if host_sha != args.expected_sha or guest_sha != args.expected_sha:
            raise RuntimeError("preview HEAD does not match expected SHA")
        with slot_lock():
            slots, entry = lease_entry(slot, lease_id)
            entry["status"] = "running"
            entry["sha"] = args.expected_sha
            write_slots(slots)
        return {
            "ok": True,
            "slot": slot,
            "url": f"https://{slot}.preview.example.dev",
            "lease_id": lease_id,
            "owner": args.owner,
            "request_id": args.request_id,
            "expected_sha": args.expected_sha,
            "host_head": host_sha,
            "preview_head": guest_sha,
            "expires_at": stamp(created + timedelta(seconds=args.ttl_seconds)),
        }
    except Exception as error:
        cleanup = destroy(slot, lease_id)
        return {
            "ok": False,
            "error": str(error),
            "slot": slot,
            "lease_id": lease_id,
            **cleanup,
        }


def verify(args: argparse.Namespace) -> dict:
    with slot_lock():
        _, entry = lease_entry(args.slot, args.lease_id)
        lease = entry["factory_lease"]
    host, guest = rev_parse(args.slot)
    expected = lease["expected_sha"]
    return {
        "ok": host == expected and guest == expected,
        "slot": args.slot,
        "lease_id": args.lease_id,
        "expected_sha": expected,
        "host_head": host,
        "preview_head": guest,
    }


def authorize(args: argparse.Namespace) -> dict:
    host, guest = rev_parse(args.slot)
    with slot_lock():
        _, entry = lease_entry(args.slot, args.lease_id)
        lease = entry["factory_lease"]
        expires_at = parse_stamp(lease["expires_at"])
        expected = lease["expected_sha"]
        if (
            entry.get("status") != "running"
            or expected != args.expected_sha
            or host != expected
            or guest != expected
            or expires_at <= now()
        ):
            raise RuntimeError("capability cannot bind an unverified preview lease")
        path = capability_path(args.capability_id)
        if path.exists():
            raise RuntimeError("capability id was already used")
        expiry = min(expires_at, now() + timedelta(seconds=args.ttl_seconds))
        if expiry <= now():
            raise RuntimeError("capability expiry is not in the future")
        secret = secrets.token_hex(32)
        token = f"efc1.{args.capability_id}.{secret}"
        write_capability(
            args.capability_id,
            {
                "schema_version": 1,
                "state": "active",
                "capability_id": args.capability_id,
                "lease_id": args.lease_id,
                "slot": args.slot,
                "allowed_host": f"{args.slot}.preview.example.dev",
                "expected_sha": expected,
                "expires_at": stamp(expiry),
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            },
        )
    return {
        "ok": True,
        "slot": args.slot,
        "lease_id": args.lease_id,
        "expected_sha": expected,
        "bearer": {
            "capability_id": args.capability_id,
            "lease_id": args.lease_id,
            "expires_at_unix": int(expiry.timestamp()),
            "secret": token,
        },
    }


def revoke(args: argparse.Namespace) -> dict:
    path = capability_path(args.capability_id)
    with slot_lock():
        try:
            value = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise RuntimeError("capability is unavailable") from error
        if value.get("lease_id") != args.lease_id:
            raise RuntimeError("capability lease ownership does not match")
        value["state"] = "revoked"
        value.pop("token_sha256", None)
        write_capability(args.capability_id, value)
    return {
        "ok": True,
        "lease_id": args.lease_id,
        "capability_id": args.capability_id,
        "cleanup_complete": True,
    }


def scan_stream(
    command: list[str],
    environment: dict[str, str],
    needles: list[bytes],
    sentinel: bytes,
) -> tuple[int, int, int]:
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdout is not None
    maximum_needle = max([len(sentinel), *map(len, needles)])
    tail = b""
    scanned = 0
    matches = 0
    sentinel_matches = 0
    while True:
        chunk = process.stdout.read(64 * 1024)
        if not chunk:
            break
        scanned += len(chunk)
        if scanned > MAX_LOG_SCAN_BYTES:
            process.kill()
            process.wait(timeout=10)
            raise RuntimeError("preview log scan exceeded its byte ceiling")
        window = tail + chunk
        matches += sum(needle in window for needle in needles)
        sentinel_matches += window.count(sentinel)
        tail = window[-maximum_needle:]
    process.stdout.close()
    if process.wait(timeout=30) != 0:
        raise RuntimeError("preview log source could not be read")
    return scanned, matches, sentinel_matches


def scan_logs(args: argparse.Namespace) -> dict:
    with slot_lock():
        _, entry = lease_entry(args.slot, args.lease_id)
        lease = entry["factory_lease"]
        capability_ids: list[str] = []
        for path in CAPABILITIES.glob("*.json"):
            try:
                value = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError("capability state is unreadable") from error
            if value.get("lease_id") == args.lease_id:
                capability_ids.append(str(value.get("capability_id", "")))
    if not capability_ids or any(not CAPABILITY.fullmatch(item) for item in capability_ids):
        raise RuntimeError("lease capability set is unavailable")
    needles = [
        needle
        for capability_id in capability_ids
        for needle in (
            capability_id.encode(),
            f"efc1.{capability_id}.".encode(),
        )
    ]
    sentinel = f"patchyard-preview-scan-{secrets.token_hex(16)}"
    subprocess.run(
        ["/usr/bin/logger", "--tag", "patchyard-preview-lease", "--", sentinel],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    environment = {
        "HOME": "/home/conductor",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PREVIEW_BRANCH": entry["branch"],
        "PREVIEW_SLOT": str(args.slot),
    }
    since = lease["created_at"]
    commands = [
        ["/usr/bin/journalctl", "--since", since, "--no-pager", "--output=cat"],
        [
            "/usr/bin/docker", "compose", "-p", f"preview-{args.slot}",
            "-f", "docker-compose.editable.yml",
            "-f", str(FACTORY_SLOT_COMPOSE),
            "--env-file", ".env", "logs", "--no-color",
        ],
    ]
    scanned = 0
    matches = 0
    sentinel_matches = 0
    for command in commands:
        source_bytes, source_matches, source_sentinel_matches = scan_stream(
            command, environment, needles, sentinel.encode()
        )
        scanned += source_bytes
        matches += source_matches
        sentinel_matches += source_sentinel_matches
    return {
        "ok": True,
        "slot": args.slot,
        "lease_id": args.lease_id,
        "sources": len(commands),
        "bytes_scanned": scanned,
        "matches": matches,
        "sentinel_matches": sentinel_matches,
    }


def sweep() -> dict:
    expired: list[tuple[int, str]] = []
    with slot_lock():
        for slot, entry in load_slots().items():
            lease = entry.get("factory_lease") if isinstance(entry, dict) else None
            if isinstance(lease, dict) and parse_stamp(lease["expires_at"]) <= now():
                expired.append((int(slot), lease["lease_id"]))
    results = [destroy(slot, lease_id) for slot, lease_id in expired]
    capability_errors: list[str] = []
    with slot_lock():
        for path in CAPABILITIES.glob("*.json"):
            try:
                value = json.loads(path.read_text())
                if parse_stamp(value["expires_at"]) <= now():
                    path.unlink()
            except (OSError, KeyError, json.JSONDecodeError, ValueError):
                capability_errors.append(path.name)
    return {
        "ok": all(item["cleanup_complete"] for item in results) and not capability_errors,
        "swept": results,
        "capability_errors": capability_errors,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    commands = value.add_subparsers(dest="command", required=True)
    take = commands.add_parser("acquire")
    take.add_argument("--owner", required=True)
    take.add_argument("--request-id", required=True)
    take.add_argument("--branch", required=True)
    take.add_argument("--expected-sha", required=True)
    take.add_argument("--lease-id", required=True)
    take.add_argument("--ttl-seconds", type=int, default=1200)
    for command in (
        commands.add_parser("verify"),
        commands.add_parser("release"),
        commands.add_parser("scan-logs"),
    ):
        command.add_argument("--slot", type=int, required=True)
        command.add_argument("--lease-id", required=True)
    release_id = commands.add_parser("release-id")
    release_id.add_argument("--lease-id", required=True)
    grant = commands.add_parser("authorize")
    grant.add_argument("--slot", type=int, required=True)
    grant.add_argument("--lease-id", required=True)
    grant.add_argument("--expected-sha", required=True)
    grant.add_argument("--capability-id", required=True)
    grant.add_argument("--ttl-seconds", type=int, default=300)
    revoke_command = commands.add_parser("revoke")
    revoke_command.add_argument("--lease-id", required=True)
    revoke_command.add_argument("--capability-id", required=True)
    commands.add_parser("sweep")
    return value


def validate(args: argparse.Namespace) -> None:
    if hasattr(args, "owner") and (not NAME.fullmatch(args.owner) or not NAME.fullmatch(args.request_id)):
        raise ValueError("owner and request-id must be lowercase bounded names")
    if hasattr(args, "branch") and (not BRANCH.fullmatch(args.branch) or ".." in args.branch):
        raise ValueError("invalid branch")
    if hasattr(args, "expected_sha") and not SHA.fullmatch(args.expected_sha):
        raise ValueError("invalid expected SHA")
    if hasattr(args, "ttl_seconds") and not 60 <= args.ttl_seconds <= 3600:
        raise ValueError("TTL must be between 60 and 3600 seconds")
    if hasattr(args, "slot") and not 1 <= args.slot <= MAX_SLOTS:
        raise ValueError("slot is out of range")
    if hasattr(args, "lease_id") and not LEASE.fullmatch(args.lease_id):
        raise ValueError("invalid lease id")
    if hasattr(args, "capability_id") and not CAPABILITY.fullmatch(args.capability_id):
        raise ValueError("invalid capability id")
    if args.command == "authorize" and not 30 <= args.ttl_seconds <= 300:
        raise ValueError("capability TTL must be between 30 and 300 seconds")


def main() -> int:
    arguments = sys.argv[1:]
    if os.environ.get("SSH_ORIGINAL_COMMAND") is not None:
        arguments = shlex.split(os.environ["SSH_ORIGINAL_COMMAND"])
    args = parser().parse_args(arguments)
    validate(args)
    if args.command == "acquire":
        result = acquire(args)
    elif args.command == "verify":
        result = verify(args)
    elif args.command == "release":
        result = destroy(args.slot, args.lease_id)
        result["ok"] = result["cleanup_complete"]
    elif args.command == "release-id":
        result = destroy_by_id(args.lease_id)
        result["ok"] = result["cleanup_complete"]
    elif args.command == "authorize":
        result = authorize(args)
    elif args.command == "revoke":
        result = revoke(args)
    elif args.command == "scan-logs":
        result = scan_logs(args)
    else:
        result = sweep()
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        raise SystemExit(1)
