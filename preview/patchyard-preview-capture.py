#!/usr/bin/env python3
"""Control-plane coordinator for a leased, exact-SHA preview capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


SSH_CONFIG = "/etc/patchyard/preview-ssh.conf"
SSH_HOST = "patchyard-preview"
BEARER = Path("/var/lib/patchyard/preview/bearer")
HEADLESS = "/usr/local/libexec/patchyard-headless"


def remote(*arguments: str, check: bool = True) -> tuple[subprocess.CompletedProcess, dict]:
    result = subprocess.run(
        ["/usr/bin/ssh", "-F", SSH_CONFIG, SSH_HOST, *arguments],
        env={"HOME": "/var/lib/patchyard-manager", "LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=1300,
        check=False,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("preview bridge returned invalid evidence") from error
    if check and (result.returncode != 0 or not payload.get("ok")):
        raise RuntimeError(payload.get("error", "preview bridge failed"))
    return result, payload


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--selector", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--order-by", required=True)
    parser.add_argument("--sort-key", required=True)
    parser.add_argument("--ttl-seconds", type=int, default=1200)
    args = parser.parse_args()
    if not args.output_dir.is_absolute() or args.output_dir.exists():
        raise ValueError("output directory must be a new absolute path")
    if not args.path.startswith("/") or "//" in args.path:
        raise ValueError("path must be absolute")
    args.output_dir.mkdir(mode=0o700)
    lease_id = hashlib.sha256(
        f"{args.owner}\0{args.request_id}\0{args.expected_sha}".encode()
    ).hexdigest()[:32]

    _, acquired = remote(
        "acquire", "--owner", args.owner, "--request-id", args.request_id,
        "--branch", args.branch, "--expected-sha", args.expected_sha,
        "--lease-id", lease_id,
        "--ttl-seconds", str(args.ttl_seconds), check=False,
    )
    if not acquired.get("ok"):
        print(json.dumps({"acquire": acquired, "cleanup": {
            "attempted": True,
            "complete": acquired.get("cleanup_complete", False),
            "path": "acquire-failure",
        }}, indent=2, sort_keys=True))
        raise SystemExit(1)

    slot = acquired["slot"]
    lease_id = acquired["lease_id"]
    cleanup: dict = {"attempted": False, "complete": False, "path": "finally"}
    error: str | None = None
    try:
        _, before = remote("verify", "--slot", str(slot), "--lease-id", lease_id)
        capture = args.output_dir / "capture"
        subprocess.run(
            [
                HEADLESS, "--url", f"{acquired['url']}{args.path}",
                "--bearer-file", str(BEARER), "--output-dir", str(capture),
                *sum((["--selector", value] for value in args.selector), []),
            ],
            env={"HOME": "/var/lib/patchyard-manager", "LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            timeout=60,
            check=True,
        )
        _, after = remote("verify", "--slot", str(slot), "--lease-id", lease_id)
        extracted = json.loads((capture / "selects.json").read_text())
        snapshot = {
            "source": {
                "where_clause": "employeePositions LIKE '%sales%' AND userStatus = 1",
                "order_by": args.order_by,
                "sort_key": args.sort_key,
                "list_order_role": "presentation",
            },
            "callers": ["mfieldbook/leads/assign.php#sales_person_id"],
            "selects": extracted["selects"],
        }
        (capture / "snapshot.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
        evidence = {
            "schema_version": 1,
            "lease": acquired,
            "head_before_capture": before,
            "head_after_capture": after,
            "artifacts": {
                name: {"sha256": file_hash(capture / name), "bytes": (capture / name).stat().st_size}
                for name in ("page.html", "page.png", "selects.json", "snapshot.json")
            },
        }
    except Exception as failure:
        error = str(failure)
        evidence = {"schema_version": 1, "lease": acquired, "error": error}
    finally:
        _, released = remote("release", "--slot", str(slot), "--lease-id", lease_id, check=False)
        cleanup = {"attempted": True, "complete": released.get("cleanup_complete", False), "path": "finally", "release": released}

    evidence["cleanup"] = cleanup
    evidence_path = args.output_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    os.chmod(evidence_path, 0o600)
    if error or not cleanup["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
