#!/usr/bin/env python3
"""Enforce A144's one-signing-identity-per-provider topology.

Static mode (the default, run in CI) validates policy/signing-identities.json
and refuses any two providers naming the same signing-key path, so the
cross-provider coupling that unqualified Anthropic requirement 1 on 2026-08-13
cannot be reintroduced silently.

--live mode (run on the control plane, credential-free) additionally derives
each provider's kid from the private key at its recorded path - sha256 of the
public-key DER, first 16 hex characters, prefixed patchyard- - and fails
loud when it differs from the recorded trusted kid. It reads key files and
calls openssl only; no credential leaves the host and no provider is called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any
import types


CHECKER_RUNTIME_PATH = Path(__file__).with_name("factory_checker_runtime.py")
CHECKER_RUNTIME_SHA256 = "db4217cdd58d3dc8343f0ba2a9d1842eb07d6356d6aa430a2e3ff9b0be07e9fe"
_checker_runtime_source = CHECKER_RUNTIME_PATH.read_bytes()
if (
    CHECKER_RUNTIME_PATH.is_symlink()
    or hashlib.sha256(_checker_runtime_source).hexdigest()
    != CHECKER_RUNTIME_SHA256
):
    raise RuntimeError("factory checker runtime differs from its exact binding")
RUNTIME = types.ModuleType("factory_checker_runtime_check_signing_identities")
RUNTIME.__file__ = str(CHECKER_RUNTIME_PATH)
RUNTIME.__package__ = None
exec(
    compile(
        _checker_runtime_source,
        str(CHECKER_RUNTIME_PATH),
        "exec",
        dont_inherit=True,
    ),
    RUNTIME.__dict__,
)


REPO = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = REPO / "policy/signing-identities.json"
MAX_POLICY_BYTES = 1_000_000
KEY_DIRECTORY = PurePosixPath("/etc/patchyard")
KID_PATTERN = re.compile(r"patchyard-[0-9a-f]{16}")
PROVIDER_PATTERN = re.compile(r"[a-z][a-z0-9-]{1,63}")
PROVIDER_KEYS = ["signing_key_path", "trusted_kid"]


class SigningIdentityError(ValueError):
    """The signing-identity policy is outside the A144 contract."""


STRICT_JSON = RUNTIME.strict_json(SigningIdentityError)
reject_duplicate_keys = STRICT_JSON.reject_duplicate_keys

def load_policy(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_POLICY_BYTES:
        raise SigningIdentityError("policy file is outside the bounded contract")
    policy = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    if not isinstance(policy, dict):
        raise SigningIdentityError("policy root is not an object")
    for field in ("schema_version", "ruling", "providers"):
        if field not in policy:
            raise SigningIdentityError(f"policy is missing {field}")
    if policy["schema_version"] != 1:
        raise SigningIdentityError("unsupported schema_version")
    if policy["ruling"] != "A144":
        raise SigningIdentityError("policy does not carry the A144 ruling")
    providers = policy["providers"]
    if not isinstance(providers, dict) or not providers:
        raise SigningIdentityError("providers is not a non-empty object")
    return policy


def validate_provider(name: str, entry: Any) -> PurePosixPath:
    if PROVIDER_PATTERN.fullmatch(name) is None:
        raise SigningIdentityError(f"provider name is malformed: {name}")
    if not isinstance(entry, dict) or sorted(entry) != PROVIDER_KEYS:
        raise SigningIdentityError(
            f"provider {name} must carry exactly {PROVIDER_KEYS}"
        )
    kid = entry["trusted_kid"]
    if not isinstance(kid, str) or KID_PATTERN.fullmatch(kid) is None:
        raise SigningIdentityError(f"provider {name} trusted_kid is malformed")
    raw_path = entry["signing_key_path"]
    if not isinstance(raw_path, str):
        raise SigningIdentityError(f"provider {name} signing_key_path is not a string")
    path = PurePosixPath(raw_path)
    if str(path) != raw_path or path.parent != KEY_DIRECTORY:
        raise SigningIdentityError(
            f"provider {name} signing_key_path must be a normalized file"
            f" directly under {KEY_DIRECTORY}"
        )
    if not path.name.endswith(".pem"):
        raise SigningIdentityError(f"provider {name} signing key is not a .pem file")
    return path


def validate_topology(policy: dict[str, Any]) -> dict[str, PurePosixPath]:
    paths: dict[str, PurePosixPath] = {}
    for name, entry in policy["providers"].items():
        path = validate_provider(name, entry)
        for other, other_path in paths.items():
            if other_path == path:
                raise SigningIdentityError(
                    f"providers {other} and {name} share signing key path"
                    f" {path}; A144 requires one signing identity per provider"
                )
        paths[name] = path
    return paths


def derive_live_kid(path: Path) -> str:
    resolved = path.resolve(strict=True)
    if resolved != path:
        raise SigningIdentityError(f"signing key path is indirect: {path}")
    public_der = subprocess.run(
        ["/usr/bin/openssl", "pkey", "-in", str(path), "-pubout", "-outform", "DER"],
        check=True,
        capture_output=True,
        env={"PATH": "/usr/bin:/bin"},
    ).stdout
    return f"patchyard-{hashlib.sha256(public_der).hexdigest()[:16]}"


def assert_live(policy: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for name, entry in sorted(policy["providers"].items()):
        expected = entry["trusted_kid"]
        try:
            live = derive_live_kid(Path(entry["signing_key_path"]))
        except (OSError, subprocess.CalledProcessError) as error:
            mismatches.append(f"{name}: cannot derive live kid: {error}")
            continue
        if live == expected:
            print(f"{name}: live kid {live} matches the trusted kid")
        else:
            mismatches.append(
                f"{name}: live kid {live} does not match trusted kid {expected}"
            )
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument(
        "--live",
        action="store_true",
        help="also derive each provider's kid from its key file on this host",
    )
    arguments = parser.parse_args()
    try:
        policy = load_policy(arguments.policy)
        paths = validate_topology(policy)
    except (OSError, json.JSONDecodeError, SigningIdentityError) as error:
        print(f"signing-identity policy rejected: {error}", file=sys.stderr)
        return 1
    print(
        f"signing-identity topology ok: {len(paths)} providers,"
        " no shared signing-key path"
    )
    if not arguments.live:
        return 0
    mismatches = assert_live(policy)
    for mismatch in mismatches:
        print(f"signing-identity drift: {mismatch}", file=sys.stderr)
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
