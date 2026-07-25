#!/usr/bin/env python3
"""Translate one-job factory preview capabilities at Traefik's auth boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets


CAPABILITY = re.compile(r"^efc1\.([0-9a-f]{32})\.([0-9a-f]{64})$")
PREVIEW_HOST = re.compile(r"^(?:[1-9]|[12][0-9]|30)\.preview\.example\.dev$")
STATE = Path("/capabilities")
KEY_FILE = Path("/secret/patchyard-api-key")
MAX_HEADER = 8192


def stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def authorize(capability: str, forwarded_host: str, forwarded_method: str) -> str | None:
    if len(capability) > MAX_HEADER or len(forwarded_host) > 253:
        raise ValueError("header exceeds boundary")
    if forwarded_method not in {"GET", "HEAD"}:
        raise ValueError("capture method is not allowed")
    host = forwarded_host.lower().split(":", 1)[0]
    if not PREVIEW_HOST.fullmatch(host):
        raise ValueError("preview host is not allowed")
    if not capability:
        return None
    if not capability.startswith("efc1."):
        return None
    match = CAPABILITY.fullmatch(capability)
    if match is None:
        raise ValueError("malformed factory capability")
    capability_id = match.group(1)
    path = STATE / f"{capability_id}.json"
    if path.is_symlink():
        raise ValueError("capability state is unsafe")
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        raise ValueError("capability is unavailable") from error
    if (
        len(raw) > 4096
        or value.get("schema_version") != 1
        or value.get("state") != "active"
        or value.get("capability_id") != capability_id
        or value.get("allowed_host") != host
        or not secrets.compare_digest(
            str(value.get("token_sha256", "")),
            sha256(capability.encode()).hexdigest(),
        )
        or stamp(str(value.get("expires_at", ""))) <= datetime.now(timezone.utc)
    ):
        raise ValueError("capability validation failed")
    key = KEY_FILE.read_text().strip()
    if not key or len(key) > MAX_HEADER or "\n" in key or "\r" in key:
        raise RuntimeError("preview authority is unavailable")
    return f"Bearer {key}"


class Handler(BaseHTTPRequestHandler):
    server_version = "patchyard-preview-capability/1"

    def do_GET(self) -> None:
        if self.path != "/auth":
            self.send_error(404)
            return
        try:
            translated = authorize(
                self.headers.get("X-Patchyard-Factory-Capability", ""),
                self.headers.get("X-Forwarded-Host", ""),
                self.headers.get("X-Forwarded-Method", ""),
            )
        except (RuntimeError, ValueError):
            self.send_response(401)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Cache-Control", "no-store")
        if translated is not None:
            # The browser's original Authorization header contains the
            # short-lived factory capability.  Traefik must not ask legacy
            # PHP to overwrite a same-named request header: it can leave that
            # capability visible to the app.  The private auth-boundary header
            # has no name collision, so this is the sole Authorization value
            # forwarded to Fieldbook.
            self.send_header("Authorization", translated)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        # Neither the bearer nor the translated preview authority reaches logs.
        return


def main() -> None:
    os.umask(0o077)
    if not STATE.is_dir() or not KEY_FILE.is_file():
        raise SystemExit("capability state or preview authority is unavailable")
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
