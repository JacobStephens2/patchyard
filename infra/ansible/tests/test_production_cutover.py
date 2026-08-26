"""Executable proofs for the issue-207 production cutover.

The resident daemon stops running against the synthetic Session 9 target and
starts running against real Fieldbook in `pre_publish`, which is the mode that
opens a draft pull request and stops. Two things have to be true for that flip
to be safe, and both are proven here rather than described.

First, the daemon's environment names production programs: the real worker
transport, the real verifier, the live daily caps, and no fixture path.

Second, the verifier it now names honours the rejection contract in
`docs/factory-verify.md`. The fixture stub did; `patchyard-run-verifier` did
not, and a production rejection that states no reason spends no repair attempt
and tells the ledger nothing. This module executes the rendered runner against
mocked hosts, so every gate below is a program that ran.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONTROL = ROOT / "infra" / "ansible" / "roles" / "control_plane"
ENVIRONMENT = CONTROL / "templates" / "patchyard-supervisor.env.j2"
RUNNER = ROOT / "worker" / "runtime" / "patchyard-run-verifier"

# The pinned PHPUnit PHAR digest recorded in docs/session-7-preview-verifier.md.
PHPUNIT_SHA256 = "3160398ef3e1ac041866fab0e88bdbc46349c7420824b750d2ede9a58ead1ba8"
TEST_PATH = "tests/Unit/AlphabetizeSalespeopleTest.php"

CLEAN_TEARDOWN = {
    "run_directories": 0,
    "processes": 0,
    "taps": 0,
    "nftables_tables": 0,
    "credential_files": 0,
}
CLEAN_WORKER_EVIDENCE = {
    "verifier_identity": "factory-worker",
    "clean_environment": True,
    "tree_hash_equal": True,
    "agent_worker_terminated_before_verify": True,
    "phpunit_exit_code": 0,
}


class SupervisorEnvironmentCutover(unittest.TestCase):
    """The daemon's own environment, which is what the flip actually is."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.environment = ENVIRONMENT.read_text(encoding="utf-8")

    def test_resident_daemon_runs_in_the_publishing_mode(self) -> None:
        # `pre_publish` is this codebase's production mode: it publishes a
        # draft PR and stops at the one human gate. There is no third mode;
        # `dry_run` is the fixture loop the cutover leaves behind.
        self.assertIn("FACTORY_RUN_MODE=pre_publish", self.environment)
        self.assertNotIn("FACTORY_RUN_MODE=dry_run", self.environment)

    def test_dry_run_fixture_wiring_is_inert_but_kept_for_rollback(self) -> None:
        # Both variables are read only in `dry_run`. They stay so that a
        # rollback is one line in this file rather than a code change, and
        # the comment above them is what stops the fixture path being read as
        # what production runs against.
        self.assertIn(
            "FACTORY_TARGET_REPOSITORY=/var/lib/patchyard/session9-target",
            self.environment,
        )
        self.assertIn("read only in dry_run", self.environment)

    def test_publisher_base_and_repository_are_real_fieldbook(self) -> None:
        self.assertIn("FACTORY_BASE_SHA={{ factory_fieldbook_base_sha }}", self.environment)
        self.assertIn("FACTORY_GITHUB_REPOSITORY_NAME=fieldbook", self.environment)
        # The base branch became the demonstration base in issue 208.
        # Its shape is proven in tests/test_demonstration_run.py.
        self.assertIn(
            "FACTORY_GITHUB_BASE_BRANCH={{ factory_fieldbook_base_branch }}",
            self.environment,
        )

    def test_worker_verifier_and_disposition_programs_are_the_real_ones(self) -> None:
        for variable, program in (
            ("FACTORY_WORKER_PROGRAM", "/usr/local/sbin/patchyard-invoke-worker"),
            ("FACTORY_WORKER_CLEANUP", "/usr/local/sbin/patchyard-cleanup-worker"),
            ("FACTORY_VERIFIER_PROGRAM", "/usr/local/sbin/patchyard-run-verifier"),
            ("FACTORY_TRIAGE_HARNESS", "/usr/local/libexec/patchyard-triage-seat"),
            (
                "FACTORY_DISPOSITION_HARNESS",
                "/usr/local/libexec/patchyard-disposition-seat",
            ),
        ):
            with self.subTest(variable=variable):
                self.assertIn(f"{variable}={program}", self.environment)
        self.assertNotIn("fixtures/", self.environment)
        self.assertNotIn("-stub", self.environment)

    def test_targeted_phpunit_selection_is_named_and_well_formed(self) -> None:
        # `FACTORY_VERIFY_TESTS` is comma-separated and the worker runtime
        # accepts only `tests/**Test.php`. An empty value is not a soft
        # default: the runner takes at least six arguments, so production runs
        # would die in usage.
        line = next(
            row
            for row in self.environment.splitlines()
            if row.startswith("FACTORY_VERIFY_TESTS=")
        )
        selection = line.split("=", 1)[1].split(",")
        self.assertTrue(selection)
        for test_path in selection:
            with self.subTest(test_path=test_path):
                self.assertTrue(test_path.startswith("tests/"))
                self.assertTrue(test_path.endswith("Test.php"))

    def test_daily_caps_are_the_ruled_production_pair(self) -> None:
        self.assertIn("FACTORY_DAILY_PER_SUBMITTER=5", self.environment)
        self.assertIn("FACTORY_DAILY_GLOBAL=25", self.environment)

    def test_a_request_that_cannot_progress_is_bounded(self) -> None:
        # The daily caps do not bound this: a recovery claim is exempt from
        # them by design, so a deterministically failing stage re-ran forever.
        line = next(
            row
            for row in self.environment.splitlines()
            if row.startswith("FACTORY_MAX_CLAIM_ATTEMPTS=")
        )
        ceiling = int(line.split("=", 1)[1])
        # The supervisor rejects anything outside this range at bootstrap.
        self.assertGreaterEqual(ceiling, 2)
        self.assertLessEqual(ceiling, 20)


class VerifierCase(unittest.TestCase):
    """A temporary control plane: a real Git repository and mocked hosts."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.repository = self.root / "fieldbook.git"
        self.output = self.root / "verify-out"
        self.patch = self.root / "change.patch"
        self.patch.write_text("--- a/x\n+++ b/x\n")
        self.implement_evidence = self.root / "implement-evidence.json"
        self.write_implement_evidence()
        self.worker_evidence = self.root / "worker-evidence.json"
        self.write_worker_evidence()
        self.base_sha = self.build_repository()
        self.install_mocks()

    # ---- fixtures -----------------------------------------------------

    def write_implement_evidence(self, **overrides: object) -> None:
        teardown = dict(CLEAN_TEARDOWN)
        teardown.update(overrides)
        self.implement_evidence.write_text(
            json.dumps({"schema_version": 1, "host_teardown": teardown})
        )

    def write_worker_evidence(self, **overrides: object) -> None:
        evidence = dict(CLEAN_WORKER_EVIDENCE)
        evidence.update(overrides)
        self.worker_evidence.write_text(json.dumps(evidence))

    def build_repository(self, with_test: bool = True) -> str:
        """A real repository, because the runner resolves the base SHA in it."""
        work = self.root / "work"
        if work.exists():
            subprocess.run(["rm", "-rf", str(work)], check=True)
        if self.repository.exists():
            subprocess.run(["rm", "-rf", str(self.repository)], check=True)
        work.mkdir()
        git = ["git", "-C", str(work)]
        subprocess.run(git + ["init", "--quiet", "-b", "master"], check=True)
        (work / "mfieldbook").mkdir()
        (work / "mfieldbook" / "common_functions.php").write_text("<?php\n")
        if with_test:
            (work / "tests" / "Unit").mkdir(parents=True)
            (work / "tests" / "Unit" / "AlphabetizeSalespeopleTest.php").write_text(
                "<?php\n"
            )
        subprocess.run(git + ["add", "--all"], check=True)
        subprocess.run(
            git
            + [
                "-c",
                "user.name=Gate",
                "-c",
                "user.email=gate@invalid.example",
                "commit",
                "--quiet",
                "-m",
                "base",
            ],
            check=True,
            env={**os.environ, "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
                 "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z"},
        )
        subprocess.run(
            ["git", "clone", "--quiet", "--bare", str(work), str(self.repository)],
            check=True,
        )
        return subprocess.run(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def install_mocks(self) -> None:
        """`sudo` drops to the caller; `ssh`/`scp` are driven by the case."""
        # `sudo` drops to the caller. Ownership is the one thing a test host
        # cannot reproduce - `factory-manager` and `factory-web` exist only on
        # the control plane - so those flags are stripped rather than faked.
        self.write_mock(
            "sudo",
            "case ${1:-} in\n"
            "  chown|find) exit 0 ;;\n"
            "  install)\n"
            "    shift\n"
            '    if [[ -n "${MOCK_STAGE_FAILURE:-}" && "$* " == *"$MOCK_STAGE_FAILURE"* ]]; then\n'
            "      exit 1\n"
            "    fi\n"
            # Staging is what makes the artifact store readable here, so the
            # substitute proves which copy the gates downstream actually read.
            '    if [[ -n "${MOCK_STAGE_SUBSTITUTE:-}" && "$* " == *implement-evidence.json* ]]; then\n'
            '      cp -- "$MOCK_STAGE_SUBSTITUTE" "${@: -1}"\n'
            "      exit 0\n"
            "    fi\n"
            "    arguments=()\n"
            "    while (($#)); do\n"
            "      case $1 in\n"
            "        -o|-g) shift 2 ;;\n"
            '        *) arguments+=("$1"); shift ;;\n'
            "      esac\n"
            "    done\n"
            '    exec install "${arguments[@]}" ;;\n'
            "esac\n"
            'exec "$@"\n',
        )
        self.write_mock(
            "ssh",
            'for argument in "$@"; do\n'
            '  case $argument in\n'
            '    */patchyard-verify-runtime) exit "${MOCK_RUNTIME_EXIT:-0}" ;;\n'
            "  esac\n"
            "done\n"
            'exit "${MOCK_SSH_EXIT:-0}"\n',
        )
        self.write_mock(
            "scp",
            'if [[ "${MOCK_SCP_EXIT:-0}" -ne 0 ]]; then exit "$MOCK_SCP_EXIT"; fi\n'
            'for argument in "$@"; do\n'
            "  case $argument in\n"
            '    *:*/evidence.json) cp -- "$MOCK_WORKER_EVIDENCE" "${@: -1}" ;;\n'
            "  esac\n"
            "done\n",
        )
        if shutil.which("sha256sum") is None:
            # The control plane is Linux; a developer host may only have the
            # BSD tool. The digest is identical either way.
            self.write_mock("sha256sum", 'exec shasum -a 256 "$@"\n')
        share = self.root / "share"
        share.mkdir()
        self.phpunit_pin = share / "phpunit.sha256"
        self.phpunit_pin.write_text(PHPUNIT_SHA256 + "\n")

    def write_mock(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text("#!/usr/bin/env bash\nset -uo pipefail\n" + body)
        path.chmod(0o755)

    # ---- execution ----------------------------------------------------

    def render(self) -> Path:
        rendered = RUNNER.read_text(encoding="utf-8")
        for token, value in {
            "{{ hostvars[groups['worker'][0]].private_ip }}": "10.132.0.11",
            "{{ factory_manager_private_key }}": str(self.root / "key"),
            "{{ factory_manager_home }}": str(self.root / "home"),
            "{{ factory_manager_user }}": "factory-manager",
        }.items():
            rendered = rendered.replace(token, value)
        self.assertNotIn("{{", rendered)
        rendered = rendered.replace(
            "/usr/local/share/patchyard/phpunit.sha256", str(self.phpunit_pin)
        )
        script = self.root / "patchyard-run-verifier"
        script.write_text(rendered)
        script.chmod(0o755)
        return script

    def run_verifier(
        self,
        *,
        base_sha: str | None = None,
        tests: list[str] | None = None,
        **environment: str,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.bin}{os.pathsep}{env['PATH']}"
        env["MOCK_WORKER_EVIDENCE"] = str(self.worker_evidence)
        env.update(environment)
        return subprocess.run(
            [
                str(self.render()),
                str(self.repository),
                base_sha if base_sha is not None else self.base_sha,
                str(self.patch),
                str(self.implement_evidence),
                str(self.output),
                *(tests if tests is not None else [TEST_PATH]),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def verdict(self) -> dict[str, object]:
        return json.loads((self.output / "evidence.json").read_text())

    def assertRejected(
        self, result: subprocess.CompletedProcess[str], gate: str, rejects: str
    ) -> list[dict[str, str]]:
        self.assertNotEqual(result.returncode, 0, result.stdout)
        verdict = self.verdict()
        self.assertEqual(verdict["schema_version"], 1)
        self.assertEqual(verdict["status"], "failed")
        self.assertEqual(verdict["gate"], gate)
        self.assertEqual(verdict["rejects"], rejects)
        self.assertIs(verdict["publish_invoked"], False)
        failures = verdict["failures"]
        self.assertTrue(failures, "a rejection with no stated assertion is the breach")
        for entry in failures:
            self.assertEqual(set(entry), {"assertion", "expected", "observed"})
            for value in entry.values():
                self.assertTrue(value)
        return failures

    def assertions(self, failures: list[dict[str, str]]) -> set[str]:
        return {entry["assertion"] for entry in failures}


class ProductionVerifierContract(VerifierCase):
    def test_a_clean_run_passes_and_carries_the_worker_evidence(self) -> None:
        result = self.run_verifier()
        self.assertEqual(result.returncode, 0, result.stderr)
        verdict = self.verdict()
        self.assertEqual(verdict["status"], "passed")
        self.assertEqual(verdict["gate"], "targeted-phpunit")
        self.assertIs(verdict["publish_invoked"], False)
        self.assertEqual(
            verdict["worker_evidence"]["verifier_identity"], "factory-worker"
        )
        self.assertEqual(
            json.loads((self.output / "worker-evidence.json").read_text()),
            CLEAN_WORKER_EVIDENCE,
        )

    def test_a_failing_targeted_test_rejects_the_patch_and_is_repairable(self) -> None:
        self.write_worker_evidence(phpunit_exit_code=2)
        result = self.run_verifier()
        failures = self.assertRejected(result, "targeted-phpunit", "patch")
        self.assertIn("phpunit_exit_code", self.assertions(failures))

    def test_a_tree_mutated_by_the_tests_rejects_the_patch(self) -> None:
        self.write_worker_evidence(tree_hash_equal=False)
        result = self.run_verifier()
        failures = self.assertRejected(result, "targeted-phpunit", "patch")
        self.assertIn("tree_hash_equal", self.assertions(failures))

    def test_every_patch_assertion_is_collected_not_just_the_first(self) -> None:
        self.write_worker_evidence(tree_hash_equal=False, phpunit_exit_code=1)
        result = self.run_verifier()
        failures = self.assertRejected(result, "targeted-phpunit", "patch")
        self.assertEqual(
            self.assertions(failures), {"tree_hash_equal", "phpunit_exit_code"}
        )

    def test_a_targeted_test_absent_at_base_rejects_the_task(self) -> None:
        # The lane-A caps forbid the patch from adding its own test, so no
        # repair attempt can answer this. It ends the run and says why.
        self.base_sha = self.build_repository(with_test=False)
        result = self.run_verifier()
        failures = self.assertRejected(result, "verifier-inputs", "task")
        self.assertIn("targeted_test_exists_at_base", self.assertions(failures))
        self.assertIn(TEST_PATH, failures[0]["observed"])

    def test_a_base_sha_absent_from_the_repository_rejects_the_task(self) -> None:
        result = self.run_verifier(base_sha="0" * 40)
        failures = self.assertRejected(result, "verifier-inputs", "task")
        self.assertIn(
            "base_sha_is_a_commit_in_the_repository", self.assertions(failures)
        )

    def test_an_unreadable_implement_evidence_is_named_not_read_as_residue(
        self,
    ) -> None:
        # The artifact store is not this program's identity. If staging fails
        # and the teardown gate reads the original anyway, a permission fault
        # arrives as "host_teardown_processes observed absent" - worker residue
        # that never happened.
        result = self.run_verifier(MOCK_STAGE_FAILURE="implement-evidence.json")
        failures = self.assertRejected(result, "verifier-inputs", "task")
        self.assertIn("implement_evidence_is_readable", self.assertions(failures))
        self.assertNotIn("host_teardown_processes", self.assertions(failures))

    def test_the_teardown_gate_reads_the_staged_copy_not_the_original(self) -> None:
        # The original carries residue; the staged copy does not. A run that
        # completes proves the gate read the copy it was given, which is the
        # only one its identity can open.
        self.write_implement_evidence(processes=1)
        staged = self.root / "staged-implement-evidence.json"
        staged.write_text(json.dumps({"schema_version": 1, "host_teardown": CLEAN_TEARDOWN}))
        result = self.run_verifier(MOCK_STAGE_SUBSTITUTE=str(staged))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.verdict()["status"], "passed")

    def test_an_unreadable_patch_is_named(self) -> None:
        result = self.run_verifier(MOCK_STAGE_FAILURE="change.patch")
        failures = self.assertRejected(result, "verifier-inputs", "task")
        self.assertIn("patch_is_readable", self.assertions(failures))

    def test_a_malformed_base_sha_rejects_the_task(self) -> None:
        result = self.run_verifier(base_sha="not-a-sha")
        failures = self.assertRejected(result, "verifier-inputs", "task")
        self.assertIn("base_sha_is_40_hex", self.assertions(failures))

    def test_a_missing_phpunit_pin_rejects_the_task(self) -> None:
        self.phpunit_pin.unlink()
        result = self.run_verifier()
        failures = self.assertRejected(result, "verifier-inputs", "task")
        self.assertIn("phpunit_binary_pin_is_64_hex", self.assertions(failures))

    def test_implement_residue_rejects_the_task_field_by_field(self) -> None:
        self.write_implement_evidence(processes=1, taps=2)
        result = self.run_verifier()
        failures = self.assertRejected(result, "implement-teardown", "task")
        self.assertEqual(
            self.assertions(failures), {"host_teardown_processes", "host_teardown_taps"}
        )
        observed = {entry["assertion"]: entry["observed"] for entry in failures}
        self.assertEqual(observed["host_teardown_taps"], "2")

    def test_teardown_evidence_that_says_nothing_still_rejects(self) -> None:
        self.implement_evidence.write_text("{}")
        result = self.run_verifier()
        failures = self.assertRejected(result, "implement-teardown", "task")
        self.assertEqual(len(failures), len(CLEAN_TEARDOWN))
        self.assertEqual({entry["observed"] for entry in failures}, {"null"})

    def test_an_unreachable_worker_rejects_the_task_with_its_exit_code(self) -> None:
        result = self.run_verifier(MOCK_SSH_EXIT="255")
        failures = self.assertRejected(result, "worker-runtime-transport", "task")
        self.assertIn("worker_runtime_completed", self.assertions(failures))
        self.assertIn("255", failures[0]["observed"])

    def test_a_failing_worker_runtime_rejects_the_task(self) -> None:
        result = self.run_verifier(MOCK_RUNTIME_EXIT="1")
        failures = self.assertRejected(result, "worker-runtime-transport", "task")
        self.assertIn("worker_runtime_completed", self.assertions(failures))

    def test_a_wrong_verifier_identity_rejects_the_task(self) -> None:
        self.write_worker_evidence(verifier_identity="root", clean_environment=False)
        result = self.run_verifier()
        failures = self.assertRejected(result, "worker-runtime-isolation", "task")
        self.assertEqual(
            self.assertions(failures), {"verifier_identity", "clean_environment"}
        )

    def test_an_implement_worker_still_alive_rejects_the_task(self) -> None:
        self.write_worker_evidence(agent_worker_terminated_before_verify=False)
        result = self.run_verifier()
        failures = self.assertRejected(result, "worker-runtime-isolation", "task")
        self.assertIn(
            "agent_worker_terminated_before_verify", self.assertions(failures)
        )

    def test_isolation_is_decided_before_the_test_result_is_read(self) -> None:
        # Fail-closed order: a breached environment is never reported as a
        # patch problem, because a repair attempt would be spent on it.
        self.write_worker_evidence(clean_environment=False, phpunit_exit_code=1)
        result = self.run_verifier()
        failures = self.assertRejected(result, "worker-runtime-isolation", "task")
        self.assertNotIn("phpunit_exit_code", self.assertions(failures))

    @unittest.skipIf(shutil.which("shellcheck") is None, "shellcheck not installed")
    def test_the_rendered_runner_is_shellcheck_clean(self) -> None:
        # The file on disk is a Jinja template, so `tools/check-ansible.sh`
        # cannot lint it the way it lints its unrendered neighbours. This gate
        # already renders it, so the lint happens where the rendering does.
        result = subprocess.run(
            ["shellcheck", "--shell=bash", "--exclude=SC2029", str(self.render())],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_too_few_arguments_is_a_usage_error_not_a_verdict(self) -> None:
        env = os.environ.copy()
        env["PATH"] = f"{self.bin}{os.pathsep}{env['PATH']}"
        result = subprocess.run(
            [str(self.render()), str(self.repository), self.base_sha],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)
        self.assertFalse(self.output.exists())

    def test_an_existing_output_directory_says_what_was_wrong(self) -> None:
        self.output.mkdir()
        result = self.run_verifier()
        self.assertEqual(result.returncode, 2)
        self.assertIn("output directory already exists", result.stderr)


if __name__ == "__main__":
    unittest.main()
