#!/usr/bin/env python3
"""Read one infrastructure tool pin without executing the pin file."""

from __future__ import annotations

from pathlib import Path
import re
import sys


REPO = Path(__file__).resolve().parent.parent
PIN_FILE = REPO / "infra/tool-versions.env"
EXPECTED_KEYS = {
    "OPENTOFU_VERSION",
    "ANSIBLE_CORE_VERSION",
    "ANSIBLE_LINT_VERSION",
    "ANSIBLE_POSIX_VERSION",
    "SHELLCHECK_VERSION",
    "SHELLCHECK_URL",
    "SHELLCHECK_SHA256",
    "NODE_EXPORTER_VERSION",
    "POSTGRES_EXPORTER_VERSION",
    "CADDY_VERSION",
}
VERSION_KEYS = EXPECTED_KEYS - {"SHELLCHECK_URL", "SHELLCHECK_SHA256"}
KEY_VALUE = re.compile(r"([A-Z][A-Z0-9_]*)=([^\s]+)")
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){1,2}")
SHA256 = re.compile(r"[0-9a-f]{64}")


def fail(message: str) -> "NoReturn":
    raise ValueError(f"{PIN_FILE.relative_to(REPO)}: {message}")


def read_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for number, raw_line in enumerate(PIN_FILE.read_text().splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = KEY_VALUE.fullmatch(line)
        if match is None:
            fail(f"line {number} is not inert KEY=VALUE data")
        key, value = match.groups()
        if key not in EXPECTED_KEYS:
            fail(f"line {number} has unexpected key {key}")
        if key in pins:
            fail(f"line {number} duplicates {key}")
        pins[key] = value

    missing = EXPECTED_KEYS - pins.keys()
    if missing:
        fail(f"missing keys: {', '.join(sorted(missing))}")
    for key in VERSION_KEYS:
        if VERSION.fullmatch(pins[key]) is None:
            fail(f"{key} is not a dotted numeric version")
    if SHA256.fullmatch(pins["SHELLCHECK_SHA256"]) is None:
        fail("SHELLCHECK_SHA256 is not 64 lowercase hexadecimal characters")
    version = pins["SHELLCHECK_VERSION"]
    expected_url = (
        "https://github.com/koalaman/shellcheck/releases/download/"
        f"v{version}/shellcheck-v{version}.linux.x86_64.tar.xz"
    )
    if pins["SHELLCHECK_URL"] != expected_url:
        fail("SHELLCHECK_URL does not match the pinned ShellCheck version")
    return pins


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in EXPECTED_KEYS:
        print(f"usage: {sys.argv[0]} <known infrastructure tool key>", file=sys.stderr)
        return 2
    try:
        pins = read_pins()
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(pins[sys.argv[1]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
