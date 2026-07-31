"""Executable proofs for the control-plane bearer log scanner."""

from __future__ import annotations

import hashlib
from pathlib import Path
import types
import unittest


SCRIPT = (
    Path(__file__).parents[1]
    / "roles"
    / "control_plane"
    / "files"
    / "patchyard-log-secret-scan"
)
EXPECTED_SCANNER_SOURCE_SHA256 = (
    "356c4a962a262f4128cd22496b068dbf4b02c8a3867214c7c31f80e1ebb11eb8"
)


def load_exact_source_module(name: str, path: Path, expected: str) -> types.ModuleType:
    source = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(source).hexdigest() != expected:
        raise RuntimeError(f"{path.name} differs from its exact source binding")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = None
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


scan_module = load_exact_source_module(
    "patchyard_log_secret_scan", SCRIPT, EXPECTED_SCANNER_SOURCE_SHA256
)


class LogSecretScanTests(unittest.TestCase):
    def test_planted_secret_and_sentinel_are_counted_separately(self) -> None:
        secret = b"efc1.capability.planted-secret"
        capability = b"capability"
        sentinel = b"patchyard-control-scan-sentinel"
        payload = b"prefix " + secret + b" middle " + sentinel + b" suffix"

        scanned, matches = scan_module.scan(
            ["/usr/bin/printf", "%s", payload.decode()],
            [secret, capability, sentinel],
        )

        self.assertEqual(scanned, len(payload))
        self.assertEqual(matches, [1, 1, 1])

    def test_absent_secret_still_requires_visible_sentinel(self) -> None:
        secret = b"efc1.capability.absent-secret"
        capability = b"absent-capability"
        sentinel = b"patchyard-control-scan-visible"

        scanned, matches = scan_module.scan(
            ["/usr/bin/printf", "%s", sentinel.decode()],
            [secret, capability, sentinel],
        )

        self.assertGreater(scanned, 0)
        self.assertEqual(matches[:2], [0, 0])
        self.assertEqual(matches[2], 1)


if __name__ == "__main__":
    unittest.main()
