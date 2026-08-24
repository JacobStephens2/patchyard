from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import py_compile
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
ROOT_CHECKER = ROOT / "tools/check-a101-readiness-root.py"
ISOLATED_RUNNER = ROOT / "tools/run-isolated-unittest.py"
PIN_READER = ROOT / "tools/read-infra-tool-version.py"
MANAGEMENT_SSH_TEMPLATE = (
    ROOT
    / "infra/ansible/roles/control_plane/templates/patchyard-management-ssh.j2"
)
CENSUS_FILE = ROOT / "policy/a101-census.sha256"


def census_rows(census: Path) -> tuple[tuple[str, str], ...]:
    """Read a sha256sum-format census into (path, digest) rows."""
    rows = []
    for line in census.read_text().splitlines():
        digest, separator, relative = line.partition("  ")
        if not separator or len(digest) != 64:
            raise ValueError(f"census row is not sha256sum data: {line}")
        rows.append((relative, digest))
    return tuple(rows)


BOUND_SOURCE_PATHS = tuple(relative for relative, _ in census_rows(CENSUS_FILE))


def validate_management_probe_contract(source: str) -> None:
    required_once = (
        "readonly PROBE_MAX_ATTEMPTS=5",
        "readonly PROBE_RETRY_SECONDS=5",
        "-o ConnectTimeout=5",
        "for ((attempt = 1; attempt <= PROBE_MAX_ATTEMPTS; attempt++)); do",
        "if ((attempt < PROBE_MAX_ATTEMPTS)); then",
        '/usr/bin/sleep "$PROBE_RETRY_SECONDS"',
        "outcome=exhausted attempts=%d total_elapsed_seconds=%d",
        "\n    probe_private_path\n",
    )
    for fragment in required_once:
        if source.count(fragment) != 1:
            raise ValueError(f"management probe contract differs: {fragment}")

    try:
        probe = source.split("probe_private_path() {\n", 1)[1].split(
            "\n}\n\nBREAKGLASS_RULE", 1
        )[0]
    except IndexError as error:
        raise ValueError("management probe function boundary differs") from error
    if probe.count("return 0") != 1 or probe.count("return 1") != 1:
        raise ValueError("management probe does not pass once and fail exhaustion once")
    if "|| true" in probe or "while true" in probe:
        raise ValueError("management probe can bypass or unbound readiness")


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

    def write_census(self) -> subprocess.CompletedProcess[str]:
        """The operator flow: regenerate the census, then re-pin the workflow."""
        written = subprocess.run(
            [
                "python3",
                "-I",
                str(self.repo / "tools/check-a101-readiness-root.py"),
                "--write-census",
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        # Exit 2 is a refusal with nothing written; anything else rewrote the
        # census and printed the workflow pins a human then pastes in.
        if written.returncode != 2:
            self.repin_workflow()
        return written

    def repin_workflow(self) -> None:
        workflow = self.repo / ".github/workflows/infrastructure.yml"
        source = workflow.read_text()
        for relative in (
            "tools/check-a101-readiness-root.py",
            "policy/a101-census.sha256",
        ):
            digest = hashlib.sha256((self.repo / relative).read_bytes()).hexdigest()
            source = re.sub(
                rf"[0-9a-f]{{64}}(  {re.escape(relative)}')",
                rf"{digest}\1",
                source,
            )
        workflow.write_text(source)

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
        self.assertIn("bound A101 source is uncensused: infra/__init__.py", root.stderr)
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
        self.assertIn("workflow differs from its exact fail-closed binding", result.stderr)

    def test_workflow_gate_failures_cannot_be_masked(self) -> None:
        workflow = self.repo / ".github/workflows/infrastructure.yml"
        source = workflow.read_text()
        mutations = {
            "infrastructure shell suffix": source.replace(
                "        run: tools/check-infra.sh\n",
                "        run: tools/check-infra.sh || true\n",
                1,
            ),
            "job-level continuation": source.replace(
                "    timeout-minutes: 20\n",
                "    timeout-minutes: 20\n    continue-on-error: true\n",
                1,
            ),
            "job-level skip": source.replace(
                "    timeout-minutes: 20\n",
                "    timeout-minutes: 20\n    if: ${{ false }}\n",
                1,
            ),
            "job-level masking shell": source.replace(
                "    timeout-minutes: 20\n",
                "    timeout-minutes: 20\n"
                "    defaults:\n"
                "      run:\n"
                "        shell: bash -c '{0} || true'\n",
                1,
            ),
            "Ansible continuation": source.replace(
                "        if: ${{ always() }}\n",
                "        if: ${{ always() }}\n        continue-on-error: true\n",
                1,
            ),
            "Ansible shell suffix": source.replace(
                "        run: tools/check-ansible.sh\n",
                "        run: tools/check-ansible.sh || true\n",
                1,
            ),
            "trust-root shell suffix": source.replace(
                "          python3 -I tools/check-a101-readiness-root.py\n",
                "          python3 -I tools/check-a101-readiness-root.py || true\n",
                1,
            ),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                self.assertNotEqual(mutation, source)
                workflow.write_text(mutation)
                try:
                    result = self.run_root()
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                finally:
                    workflow.write_text(source)

    def test_runner_executes_source_not_unchecked_hash_bytecode(self) -> None:
        target = self.repo / "infra/ansible/tests/test_session14_qualification.py"
        target.write_text(
            "import unittest\n\n"
            "class ExactSource(unittest.TestCase):\n"
            "    def test_source_failure(self):\n"
            "        self.fail('exact source executed')\n"
        )
        marker = Path(self.temp.name) / "forged-bytecode-executed"
        forged_source = Path(self.temp.name) / "forged.py"
        forged_source.write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).touch()\n"
            "import unittest\n\n"
            "class ForgedPass(unittest.TestCase):\n"
            "    def test_forged_pass(self):\n"
            "        self.assertTrue(True)\n"
        )
        cache = Path(importlib.util.cache_from_source(str(target)))
        cache.parent.mkdir(parents=True)
        py_compile.compile(
            str(forged_source),
            cfile=str(cache),
            doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
        )

        result = self.run_test("infra/ansible/tests/test_session14_qualification.py")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("exact source executed", result.stderr)
        self.assertFalse(marker.exists())

    def test_import_executed_sources_are_independently_bound(self) -> None:
        cases = (
            (
                "tools/anthropic-spend-evidence.py",
                "infra/ansible/tests/test_anthropic_spend.py",
                "anthropic-spend-evidence.py differs from its exact source binding",
            ),
            (
                "tools/anthropic-wif-admin.py",
                "infra/ansible/tests/test_anthropic_wif_admin.py",
                "anthropic-wif-admin.py differs from its exact source binding",
            ),
            (
                "tools/anthropic-wif-lifecycle.py",
                "infra/ansible/tests/test_anthropic_lifecycle.py",
                "anthropic-wif-lifecycle.py differs from its exact source binding",
            ),
            (
                "tools/anthropic-wif-crash-cleanup.py",
                "infra/ansible/tests/test_anthropic_lifecycle.py",
                "anthropic-wif-crash-cleanup.py differs from its exact source binding",
            ),
            (
                "tools/anthropic-wif-lifecycle-admin.py",
                "infra/ansible/tests/test_anthropic_lifecycle.py",
                "anthropic-wif-lifecycle-admin.py differs from its exact source binding",
            ),
            (
                "tools/openai-wif-issuance.py",
                "infra/ansible/tests/test_openai_wif_issuance.py",
                "openai-wif-issuance.py differs from its exact source binding",
            ),
            (
                "tools/openai-wif-expiry.py",
                "infra/ansible/tests/test_openai_wif_issuance.py",
                "openai-wif-expiry.py differs from its exact source binding",
            ),
            (
                "tools/openai-wif-crash-cleanup.py",
                "infra/ansible/tests/test_openai_wif_issuance.py",
                "openai-wif-crash-cleanup.py differs from its exact source binding",
            ),
            (
                "infra/ansible/roles/control_plane/files/patchyard-log-secret-scan",
                "infra/ansible/tests/test_log_secret_scan.py",
                "patchyard-log-secret-scan differs from its exact source binding",
            ),
        )
        for source, test, diagnostic in cases:
            with self.subTest(source=source):
                path = self.repo / source
                original = path.read_bytes()
                path.write_bytes(original + b"\n# executable source mutation\n")
                try:
                    result = self.run_test(test)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn(diagnostic, result.stderr)
                finally:
                    path.write_bytes(original)

    def test_tools_python_census_rejects_new_executable_source(self) -> None:
        unexpected = self.repo / "tools/unbound-executable.py"
        unexpected.write_text("raise RuntimeError('must never execute')\n")
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "bound A101 source is uncensused: tools/unbound-executable.py",
            result.stderr,
        )

    def test_dropping_a_census_row_fails_closed(self) -> None:
        census = self.repo / "policy/a101-census.sha256"
        rows = census.read_text().splitlines(keepends=True)
        dropped = next(
            row for row in rows if row.endswith("  tools/check-infra.sh\n")
        )
        census.write_text("".join(row for row in rows if row is not dropped))
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "bound A101 source is uncensused: tools/check-infra.sh", result.stderr
        )

    def test_census_row_without_a_governed_file_fails_closed(self) -> None:
        census = self.repo / "policy/a101-census.sha256"
        census.write_text(
            census.read_text() + f"{'0' * 64}  docs/decision-log.md\n"
        )
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "censused A101 source is not governed: docs/decision-log.md",
            result.stderr,
        )

    def test_malformed_census_data_fails_closed(self) -> None:
        census = self.repo / "policy/a101-census.sha256"
        census.write_text(census.read_text() + "not-a-census-row\n")
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("A101 census row is not sha256sum data", result.stderr)

    def test_missing_census_file_fails_closed(self) -> None:
        (self.repo / "policy/a101-census.sha256").unlink()
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("A101 census file is missing", result.stderr)

    def test_write_regenerates_the_census_for_a_declared_change(self) -> None:
        helper = self.repo / "infra/wait-do-worker-firewall.sh"
        helper.write_bytes(helper.read_bytes() + b"\n# declared change\n")
        stale = self.run_root()
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn(
            "bound A101 source differs: infra/wait-do-worker-firewall.sh",
            stale.stderr,
        )

        written = self.write_census()
        self.assertNotEqual(written.returncode, 2, written.stderr)
        self.assertIn(
            "census re-pins infra/wait-do-worker-firewall.sh", written.stderr
        )
        rebound = self.run_root()
        self.assertEqual(rebound.returncode, 0, rebound.stderr)

    def test_new_tool_source_is_governed_by_the_census_it_joins(self) -> None:
        added = self.repo / "tools/added-helper.py"
        added.write_text("#!/usr/bin/env python3\n")
        written = self.write_census()
        self.assertNotEqual(written.returncode, 2, written.stderr)
        self.assertIn("census adds tools/added-helper.py", written.stderr)
        self.assertEqual(self.run_root().returncode, 0)

        added.write_text("#!/usr/bin/env python3\n# weakened after census\n")
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "bound A101 source differs: tools/added-helper.py", result.stderr
        )

    def test_removing_an_infrastructure_gate_fails_closed(self) -> None:
        wrapper = self.repo / "tools/check-infra.sh"
        source = wrapper.read_text()
        gate = 'run_gate python3 -I "$REPO_ROOT/tools/check-stack.py"\n'
        self.assertIn(gate, source)
        wrapper.write_text(source.replace(gate, "", 1))
        # Even a fully regenerated census cannot launder a dropped gate.
        self.write_census()
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "infrastructure wrapper lacks one isolated aggregate call: "
            "check-stack.py",
            result.stderr,
        )

    def test_a_new_checker_must_be_gated_before_it_can_pass(self) -> None:
        added = self.repo / "tools/check-added-gate.py"
        added.write_text("#!/usr/bin/env python3\n")
        blocked = self.write_census()
        self.assertEqual(blocked.returncode, 2, blocked.stdout)
        self.assertIn(
            "infrastructure wrapper lacks one isolated aggregate call: "
            "check-added-gate.py",
            blocked.stderr,
        )
        self.assertIn("refusing to rewrite the census", blocked.stderr)

        wrapper = self.repo / "tools/check-infra.sh"
        wrapper.write_text(
            wrapper.read_text().replace(
                'run_gate python3 -I "$REPO_ROOT/tools/check-stack.py"',
                'run_gate python3 -I "$REPO_ROOT/tools/check-added-gate.py"\n'
                'run_gate python3 -I "$REPO_ROOT/tools/check-stack.py"',
                1,
            )
        )
        written = self.write_census()
        self.assertNotEqual(written.returncode, 2, written.stderr)
        self.assertEqual(self.run_root().returncode, 0)

    def test_workflow_must_pin_the_census(self) -> None:
        workflow = self.repo / ".github/workflows/infrastructure.yml"
        source = workflow.read_text()
        self.assertIn("  policy/a101-census.sha256'", source)
        workflow.write_text(
            re.sub(r"[0-9a-f]{64}(  policy/a101-census\.sha256')", r"\g<0>", source)
            .replace(
                hashlib.sha256(
                    (self.repo / "policy/a101-census.sha256").read_bytes()
                ).hexdigest(),
                "0" * 64,
                1,
            )
        )
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "infrastructure workflow does not pin the A101 census", result.stderr
        )

    def test_write_census_refuses_to_launder_a_shadowed_module(self) -> None:
        (self.repo / "tools/hashlib.py").write_text("raise RuntimeError('shadow')\n")
        census = self.repo / "policy/a101-census.sha256"
        before = census.read_text()
        blocked = self.write_census()
        self.assertEqual(blocked.returncode, 2, blocked.stdout)
        self.assertIn(
            "repository shadows a protected Python module: tools/hashlib.py",
            blocked.stderr,
        )
        self.assertEqual(census.read_text(), before)

    def test_census_covers_every_governed_python_source(self) -> None:
        """Derive the classes independently of the checker that wrote them."""
        censused = set(BOUND_SOURCE_PATHS)
        governed = {
            str(path.relative_to(ROOT))
            for path in ROOT.glob("tools/*.py")
        } | {
            str(path.relative_to(ROOT))
            for path in ROOT.glob("infra/**/*.py")
        }
        self.assertTrue(governed)
        self.assertEqual(governed - censused, set())

    def test_isolated_runner_refuses_an_uncensused_test_file(self) -> None:
        added = self.repo / "infra/ansible/tests/test_uncensused.py"
        added.write_text(
            "import unittest\n\n"
            "class Sneaks(unittest.TestCase):\n"
            "    def test_runs(self):\n"
            "        self.assertTrue(True)\n"
        )
        result = self.run_test("infra/ansible/tests/test_uncensused.py")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("refuses an uncensused test file", result.stderr)

    def test_ansible_wrapper_test_census_must_match_the_derived_census(self) -> None:
        wrapper = self.repo / "tools/check-ansible.sh"
        source = wrapper.read_text()
        wrapper.write_text(
            source.replace(
                "  infra/ansible/tests/test_freeze_graph.py\n", "", 1
            )
        )
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ansible wrapper TEST_FILES census differs", result.stderr)

    def test_infrastructure_gate_may_not_be_duplicated(self) -> None:
        wrapper = self.repo / "tools/check-infra.sh"
        source = wrapper.read_text()
        gate = 'run_gate python3 -I "$REPO_ROOT/tools/check-stack.py"\n'
        self.assertIn(gate, source)
        wrapper.write_text(source.replace(gate, gate * 2, 1))
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "infrastructure wrapper repeats an isolated aggregate call: "
            "check-stack.py",
            result.stderr,
        )

    def test_infrastructure_gate_must_name_a_governed_checker(self) -> None:
        wrapper = self.repo / "tools/check-infra.sh"
        source = wrapper.read_text()
        wrapper.write_text(
            source.replace(
                'run_gate python3 -I "$REPO_ROOT/tools/check-stack.py"',
                'run_gate python3 -I "$REPO_ROOT/tools/check-absent.py"',
                1,
            )
        )
        result = self.run_root()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "infrastructure wrapper gate is not a governed checker: "
            "check-absent.py",
            result.stderr,
        )

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


class ManagementSshReadinessContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = MANAGEMENT_SSH_TEMPLATE.read_text()
        validate_management_probe_contract(self.source)

        self.mock_ssh = self.root / "mock-ssh"
        self.mock_ssh.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "count=0\n"
            '[[ ! -f "$MOCK_SSH_COUNT" ]] || count=$(<"$MOCK_SSH_COUNT")\n'
            "count=$((count + 1))\n"
            'printf \'%d\\n\' "$count" >"$MOCK_SSH_COUNT"\n'
            'case "$MOCK_SSH_MODE" in\n'
            "  ready) printf 'factory-manager\\n' ;;\n"
            "  delayed)\n"
            "    if ((count < 3)); then\n"
            "      echo 'ssh: connect to host 10.132.0.11 port 22: Connection timed out' >&2\n"
            "      exit 255\n"
            "    fi\n"
            "    printf 'factory-manager\\n'\n"
            "    ;;\n"
            "  dead)\n"
            "    echo 'ssh: connect to host 10.132.0.11 port 22: Connection timed out' >&2\n"
            "    exit 255\n"
            "    ;;\n"
            "  wrong-identity) printf 'root\\n' ;;\n"
            "  *) exit 97 ;;\n"
            "esac\n"
        )
        self.mock_ssh.chmod(0o700)
        self.mock_sleep = self.root / "mock-sleep"
        self.mock_sleep.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'printf \'%s\\n\' "$1" >>"$MOCK_SLEEP_CALLS"\n'
        )
        self.mock_sleep.chmod(0o700)

    def render(self, source: str | None = None) -> Path:
        rendered = self.source if source is None else source
        replacements = {
            "{{ hostvars[groups['control_plane'][0]].private_ip }}": "10.132.0.17",
            "{{ hostvars[groups['worker'][0]].private_ip }}": "10.132.0.11",
            "{{ factory_manager_private_key }}": "/tmp/factory-manager-key",
            "{{ factory_manager_home }}": "/tmp/factory-manager",
            "{{ factory_manager_user }}": "factory-manager",
            "{{ orchestration_public_cidr }}": "142.93.121.94/32",
            "{{ control_plane_private_cidr }}": "10.132.0.17/32",
            "{{ worker_image_recipe_sha256 }}": "a" * 64,
        }
        for token, value in replacements.items():
            rendered = rendered.replace(token, value)
        self.assertNotIn("{{", rendered)
        rendered = rendered.replace("/usr/bin/ssh", str(self.mock_ssh), 1)
        rendered = rendered.replace("/usr/bin/sleep", str(self.mock_sleep), 1)
        script = self.root / "patchyard-management-ssh"
        script.write_text(rendered)
        script.chmod(0o700)
        return script

    def run_probe(
        self, mode: str
    ) -> tuple[subprocess.CompletedProcess[str], int, list[str]]:
        counter = self.root / f"{mode}-ssh-count"
        sleeps = self.root / f"{mode}-sleep-calls"
        environment = os.environ.copy()
        environment.update(
            MOCK_SSH_MODE=mode,
            MOCK_SSH_COUNT=str(counter),
            MOCK_SLEEP_CALLS=str(sleeps),
        )
        result = subprocess.run(
            [str(self.render()), "worker", "probe"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        count = int(counter.read_text().strip()) if counter.exists() else 0
        sleep_calls = sleeps.read_text().splitlines() if sleeps.exists() else []
        return result, count, sleep_calls

    def test_first_attempt_pass_is_observable_without_delay(self) -> None:
        result, count, sleeps = self.run_probe("ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(count, 1)
        self.assertEqual(sleeps, [])
        self.assertRegex(
            result.stderr,
            r"target=worker attempt=1/5 outcome=pass "
            r"attempt_elapsed_seconds=\d+ total_elapsed_seconds=\d+ "
            r"ssh_exit_status=0",
        )
        self.assertNotIn("attempt=2/5", result.stderr)

    def test_later_success_preserves_each_failed_attempt(self) -> None:
        result, count, sleeps = self.run_probe("delayed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(count, 3)
        self.assertEqual(sleeps, ["5", "5"])
        self.assertIn("attempt=1/5 outcome=ssh-failed", result.stderr)
        self.assertIn("attempt=2/5 outcome=ssh-failed", result.stderr)
        self.assertIn("attempt=3/5 outcome=pass", result.stderr)
        self.assertEqual(result.stderr.count("Connection\\ timed\\ out"), 2)
        self.assertNotIn("outcome=exhausted", result.stderr)

    def test_dead_path_and_wrong_identity_exhaust_and_fail_closed(self) -> None:
        for mode, outcome in (("dead", "ssh-failed"), ("wrong-identity", "identity-mismatch")):
            with self.subTest(mode=mode):
                result, count, sleeps = self.run_probe(mode)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(count, 5)
                self.assertEqual(sleeps, ["5"] * 4)
                for attempt in range(1, 6):
                    self.assertIn(
                        f"attempt={attempt}/5 outcome={outcome}", result.stderr
                    )
                self.assertIn(
                    "target=worker outcome=exhausted attempts=5", result.stderr
                )

    def test_unbounded_and_exhaustion_pass_mutations_are_rejected(self) -> None:
        mutations = {
            "removed attempt bound": self.source.replace(
                "attempt <= PROBE_MAX_ATTEMPTS", "", 1
            ),
            "exhaustion returns success": self.source.replace(
                '  return 1\n}\n\nBREAKGLASS_RULE=',
                '  return 0\n}\n\nBREAKGLASS_RULE=',
                1,
            ),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                self.assertNotEqual(mutation, self.source)
                with self.assertRaises(ValueError):
                    validate_management_probe_contract(mutation)


if __name__ == "__main__":
    unittest.main()
