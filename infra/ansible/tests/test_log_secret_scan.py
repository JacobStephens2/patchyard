"""Executable proofs for the control-plane bearer log scanner."""

from __future__ import annotations

import importlib.machinery
from pathlib import Path
import sys
import unittest


SCRIPT = (
    Path(__file__).parents[1]
    / "roles"
    / "control_plane"
    / "files"
    / "patchyard-log-secret-scan"
)
sys.dont_write_bytecode = True
loader = importlib.machinery.SourceFileLoader("patchyard_log_secret_scan", str(SCRIPT))
scan_module = loader.load_module()


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
