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
import shlex
import subprocess
import sys
import uuid


ROOT = Path("/opt/preview-fieldbooks")
SLOTS = ROOT / "slots.json"
LOCK = ROOT / ".factory-slots.lock"
MAX_SLOTS = 30
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
LEASE = re.compile(r"^[0-9a-f]{32}$")


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


def environment_token() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("GITHUB_TOKEN="):
            value = line.split("=", 1)[1]
            if value:
                return value
    raise RuntimeError("preview GitHub build token is unavailable")


def compose(slot: int, *arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    environment = {
        "HOME": "/home/conductor",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PREVIEW_SLOT": str(slot),
    }
    return subprocess.run(
        [
            "/usr/bin/docker", "compose", "-p", f"preview-{slot}",
            "-f", "docker-compose.editable.yml", "--env-file", ".env", *arguments,
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


def destroy(slot: int, lease_id: str) -> dict:
    with slot_lock():
        lease_entry(slot, lease_id)

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
    with slot_lock():
        slots, _ = lease_entry(slot, lease_id)
        del slots[str(slot)]
        write_slots(slots)
        absent = str(slot) not in load_slots()
    complete = absent and not checkout.exists()
    if not complete:
        errors.append("residue")
    return {
        "slot": slot,
        "lease_id": lease_id,
        "cleanup_complete": complete,
        "cleanup_errors": errors,
    }


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
            "exec", "-T", "fieldbook", "git", "-C", "/var/www/html", "rev-parse", "HEAD",
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
    lease_id = uuid.uuid4().hex
    created = now()
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


def sweep() -> dict:
    expired: list[tuple[int, str]] = []
    with slot_lock():
        for slot, entry in load_slots().items():
            lease = entry.get("factory_lease") if isinstance(entry, dict) else None
            if isinstance(lease, dict) and parse_stamp(lease["expires_at"]) <= now():
                expired.append((int(slot), lease["lease_id"]))
    results = [destroy(slot, lease_id) for slot, lease_id in expired]
    return {"ok": all(item["cleanup_complete"] for item in results), "swept": results}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    commands = value.add_subparsers(dest="command", required=True)
    take = commands.add_parser("acquire")
    take.add_argument("--owner", required=True)
    take.add_argument("--request-id", required=True)
    take.add_argument("--branch", required=True)
    take.add_argument("--expected-sha", required=True)
    take.add_argument("--ttl-seconds", type=int, default=1200)
    for command in (commands.add_parser("verify"), commands.add_parser("release")):
        command.add_argument("--slot", type=int, required=True)
        command.add_argument("--lease-id", required=True)
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
