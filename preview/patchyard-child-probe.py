#!/usr/bin/env python3
"""Fixed in-child proof that A104 jobs cannot reach factory authority."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys


FORBIDDEN_PATHS = {
    "credential_paths_unreachable": [
        "/etc/patchyard",
        "/root/.ssh",
        "/home/factory-manager/.ssh",
        "/run/secrets",
    ],
    "postgres_socket_unreachable": [
        "/run/patchyard-postgres",
        "/var/run/postgresql",
    ],
    "artifact_tree_unreachable": ["/var/lib/patchyard/artifacts"],
    "sibling_unreachable": ["/review-siblings"],
    "shared_scratch_unreachable": ["/shared-scratch"],
}
FORBIDDEN_ENV_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PRIVATE_KEY",
    "DATABASE_URL",
    "VAULT",
    "GITHUB",
)


def tcp_unreachable(address: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.connect((address, port))
    except OSError:
        return True
    finally:
        sock.close()
    return False


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(2)
    output = Path(sys.argv[1])
    if not output.is_absolute() or output.exists():
        raise SystemExit(2)
    facts = {
        name: all(not Path(path).exists() and not Path(path).is_symlink() for path in paths)
        for name, paths in FORBIDDEN_PATHS.items()
    }
    facts["credential_paths_unreachable"] = facts["credential_paths_unreachable"] and all(
        not any(marker in name.upper() for marker in FORBIDDEN_ENV_MARKERS)
        for name in os.environ
    )
    facts["metadata_unreachable"] = tcp_unreachable("169.254.169.254", 80)
    facts["private_fleet_unreachable"] = all(
        tcp_unreachable(address, port)
        for address, port in [
            ("10.132.0.10", 22),
            ("10.132.0.14", 5432),
            ("172.16.0.1", 22),
            ("192.168.0.1", 80),
        ]
    )
    output.write_text(json.dumps({"schema_version": 1, **facts}, sort_keys=True) + "\n")
    output.chmod(0o600)
    if not all(facts.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
