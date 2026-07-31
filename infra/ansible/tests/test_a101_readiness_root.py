from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
ROOT_CHECKER = ROOT / "tools/check-a101-readiness-root.py"
ISOLATED_RUNNER = ROOT / "tools/run-isolated-unittest.py"
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
    "tools/run-isolated-unittest.py",
    "tools/check-anthropic-spend.py",
    "tools/check-anthropic-issuance.py",
    "tools/check-independence.py",
    "tools/check-preview-runtime.py",
    "tools/check-stack.py",
    "tools/check-worker-qualification.py",
    "tools/check-worker-runtime.py",
    "infra/ansible/tests/test_a101_readiness_root.py",
    "infra/ansible/tests/test_worker_firewall_readiness.py",
    "infra/ansible/tests/test_anthropic_spend.py",
    "infra/ansible/tests/test_anthropic_issuance.py",
    "infra/ansible/tests/test_anthropic_wif_admin.py",
    "infra/ansible/tests/test_child_launcher.py",
    "infra/ansible/tests/test_cloud_init_bootstrap.py",
    "infra/ansible/tests/test_dashboard_checkout.py",
    "infra/ansible/tests/test_log_secret_scan.py",
    "infra/ansible/tests/test_preview_capability_deployment.py",
    "infra/ansible/tests/test_replace_worker.py",
    "infra/ansible/tests/test_session14_qualification.py",
    "infra/ansible/tests/test_session15_proposer.py",
    "infra/ansible/tests/test_session16_cutover.py",
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

    def run_root(self, *, isolated: bool = True) -> subprocess.CompletedProcess[str]:
        command = ["python3"]
        if isolated:
            command.append("-I")
        command.append(str(self.repo / "tools/check-a101-readiness-root.py"))
        return subprocess.run(
            command,
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )

    def run_test(self, relative: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                "-I",
                str(self.repo / "tools/run-isolated-unittest.py"),
                str(self.repo / relative),
            ],
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

    def test_root_runner_and_spend_checker_refuse_nonisolated_python(self) -> None:
        root = self.run_root(isolated=False)
        self.assertNotEqual(root.returncode, 0)
        self.assertIn("requires python3 -I", root.stderr)

        runner = subprocess.run(
            [
                "python3",
                str(self.repo / "tools/run-isolated-unittest.py"),
                str(self.repo / "infra/ansible/tests/test_session14_qualification.py"),
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(runner.returncode, 0)
        self.assertIn("requires python3 -I", runner.stderr)

        spend = subprocess.run(
            ["python3", str(self.repo / "tools/check-anthropic-spend.py")],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(spend.returncode, 0)
        self.assertIn("requires python3 -I", spend.stderr)

    def test_repository_stdlib_shadow_and_source_mutation_both_fail(self) -> None:
        (self.repo / "tools/hashlib.py").write_text(
            "raise RuntimeError('repository hashlib shadow executed')\n"
        )
        helper = self.repo / "infra/wait-do-worker-firewall.sh"
        helper.write_bytes(helper.read_bytes() + b"\n# weakened helper\n")
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("repository shadows a protected Python module: tools/hashlib.py", result.stderr)
        self.assertIn(
            "bound A101 source differs: infra/wait-do-worker-firewall.sh",
            result.stderr,
        )

    def test_package_initializers_are_rejected_and_never_executed(self) -> None:
        marker = Path(self.temp.name) / "initializer-executed"
        for relative in (
            "infra/__init__.py",
            "infra/ansible/__init__.py",
            "infra/ansible/tests/__init__.py",
        ):
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")

        test_file = self.repo / "infra/ansible/tests/test_session14_qualification.py"
        test_file.write_text(
            "import unittest\n\n"
            "class BoundFile(unittest.TestCase):\n"
            "    def test_loaded_without_package_import(self):\n"
            "        self.assertTrue(True)\n"
        )
        run = self.run_test("infra/ansible/tests/test_session14_qualification.py")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(marker.exists())

        root = self.run_root()
        self.assertNotEqual(root.returncode, 0)
        self.assertIn("unexpected infrastructure Python source: infra/__init__.py", root.stderr)
        self.assertIn(
            "repository package initializer is forbidden: infra/ansible/tests/__init__.py",
            root.stderr,
        )

    def test_each_security_file_gets_a_fresh_python_process(self) -> None:
        first = self.repo / "infra/ansible/tests/test_anthropic_issuance.py"
        first.write_text(
            "import hashlib\n"
            "import unittest\n\n"
            "class PoisonHashlib(unittest.TestCase):\n"
            "    def test_poison_only_this_process(self):\n"
            "        hashlib.sha256 = lambda *args, **kwargs: None\n"
        )
        second = self.repo / "infra/ansible/tests/test_session14_qualification.py"
        second.write_text(
            "import hashlib\n"
            "import unittest\n\n"
            "class CleanHashlib(unittest.TestCase):\n"
            "    def test_real_hashlib(self):\n"
            "        self.assertEqual(hashlib.sha256(b'x').hexdigest(), "
            "'2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881')\n"
        )
        poison = self.run_test("infra/ansible/tests/test_anthropic_issuance.py")
        self.assertEqual(poison.returncode, 0, poison.stderr)
        clean = self.run_test("infra/ansible/tests/test_session14_qualification.py")
        self.assertEqual(clean.returncode, 0, clean.stderr)

    def test_workflow_must_continue_to_ansible_after_infra_failure(self) -> None:
        workflow = self.repo / ".github/workflows/infrastructure.yml"
        source = workflow.read_text()
        self.assertIn("        if: ${{ always() }}\n", source)
        workflow.write_text(source.replace("        if: ${{ always() }}\n", "", 1))
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ansible step does not run after infrastructure failure", result.stderr)

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
                "-I",
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


if __name__ == "__main__":
    unittest.main()
