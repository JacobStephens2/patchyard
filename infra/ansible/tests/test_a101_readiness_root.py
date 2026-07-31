from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
ROOT_CHECKER = ROOT / "tools/check-a101-readiness-root.py"
PIN_READER = ROOT / "tools/read-infra-tool-version.py"
BOUND_SOURCE_PATHS = (
    "infra/wait-do-worker-firewall.sh",
    "infra/replace-worker.sh",
    "infra/tofu.sh",
    "infra/ansible/converge.sh",
    "infra/ansible/qualify.sh",
    "infra/ansible/inventory/tofu.sh",
    "infra/tool-versions.env",
    "tools/read-infra-tool-version.py",
    "tools/install-shellcheck.sh",
    "tools/check-infra.sh",
    "tools/check-ansible.sh",
    "tools/check-anthropic-spend.py",
    "infra/ansible/tests/test_a101_readiness_root.py",
    "infra/ansible/tests/test_worker_firewall_readiness.py",
    "infra/ansible/tests/test_anthropic_spend.py",
)


class A101ReadinessTrustRootContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        shutil.copytree(
            ROOT,
            self.repo,
            ignore=shutil.ignore_patterns(
                ".git", ".terraform", ".venv", "target", "node_modules", "__pycache__"
            ),
        )

    def run_root(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(self.repo / "tools/check-a101-readiness-root.py")],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_every_bound_source_mutation_fails(self) -> None:
        baseline = self.run_root()
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        for relative in BOUND_SOURCE_PATHS:
            with self.subTest(relative=relative):
                path = self.repo / relative
                original = path.read_bytes()
                path.write_bytes(original + b"\n# A101 source mutation\n")
                try:
                    result = self.run_root()
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn(f"bound A101 source differs: {relative}", result.stderr)
                finally:
                    path.write_bytes(original)

    def test_tool_version_file_is_data_not_shell(self) -> None:
        marker = Path(self.temp.name) / "executed"
        pins = self.repo / "infra/tool-versions.env"
        pins.write_text(
            pins.read_text()
            + f"\npython3() {{ touch {marker}; }}\n"
            + f"touch {marker}\n"
        )
        result = subprocess.run(
            [
                "python3",
                str(self.repo / "tools/read-infra-tool-version.py"),
                "SHELLCHECK_VERSION",
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not inert KEY=VALUE data", result.stderr)
        self.assertFalse(marker.exists())

    def test_each_security_module_gets_a_fresh_python_process(self) -> None:
        issuance = self.repo / "infra/ansible/tests/test_anthropic_issuance.py"
        issuance.write_text(
            """import hashlib
import unittest

class PoisonHashlib(unittest.TestCase):
    def test_poison_only_this_process(self):
        hashlib.sha256 = lambda *args, **kwargs: None
"""
        )
        poison = subprocess.run(
            [
                "python3",
                "-m",
                "unittest",
                "infra.ansible.tests.test_anthropic_issuance",
                "-v",
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(poison.returncode, 0, poison.stderr)
        readiness = subprocess.run(
            [
                "python3",
                "-m",
                "unittest",
                "infra.ansible.tests.test_worker_firewall_readiness",
                "-v",
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(readiness.returncode, 0, readiness.stderr)


if __name__ == "__main__":
    unittest.main()
