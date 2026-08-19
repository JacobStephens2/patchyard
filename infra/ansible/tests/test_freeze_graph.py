import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "tools/check-freeze-graph.py"
# A144 superseded the OpenAI collectors and checkers by declared digest, so
# their PRE-split bytes leave the byte-frozen set: the Results banked before
# the split bind them through the supersession trail rather than by identity.
#
# Three of them are back, by their post-split bytes. The requirement-4
# revocation Result (run openai-revocation-20260819-6bd96462ce) was produced
# by the split-identity tools and names their current digests in its `source`
# block, so banking it froze exactly what produced it. That is the mechanism
# working, not drift: a Result pins its own instrument.
EXPECTED_FROZEN_PATHS = [
    "policy/anthropic-wif.json",
    "policy/openai-wif.json",
    "tools/anthropic-wif-crash-cleanup.py",
    "tools/anthropic-wif-lifecycle-admin.py",
    "tools/anthropic-wif-lifecycle.py",
    "tools/anthropic-wif-revocation.py",
    "tools/check-openai-wif-federation-revocation.py",
    "tools/control-plane-attestation-v1.py",
    "tools/openai-wif-federation-revocation.py",
    "tools/openai-wif-issuance.py",
    "worker/image/production-parity.json",
    "worker/qualification/hostile-test-manifest.json",
    "worker/runtime/patchyard-anthropic-one-shot",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FreezeGraphContract(unittest.TestCase):
    def run_checker(self, repo: Path, checker: Path = CHECKER):
        return subprocess.run(
            ["python3", "-I", str(checker), "--repo", str(repo)],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_current_repository_is_consistent_and_stable(self) -> None:
        first = self.run_checker(ROOT)
        second = self.run_checker(ROOT)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)

        report = json.loads(first.stdout)
        paths = [row["path"] for row in report["frozen"]]
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["drift"], [])
        self.assertEqual(report["frozen_count"], len(EXPECTED_FROZEN_PATHS))
        self.assertEqual(paths, EXPECTED_FROZEN_PATHS)
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(
            report["neutral"]["artifacts"],
            [
                "worker/image/patchyard-guest-dispatch",
                "worker/image/patchyard-guest-qualify",
                "worker/runtime/patchyard-provider-run",
            ],
        )
        self.assertEqual(report["neutral"]["violations"], [])

    def test_nested_result_and_all_source_constant_shapes_are_reachable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            for relative in (
                "tools",
                "worker",
                "policy",
                "research/isolation/results",
            ):
                (repo / relative).mkdir(parents=True, exist_ok=True)
            checker = repo / "tools/check-freeze-graph.py"
            shutil.copy2(CHECKER, checker)

            targets = {
                "worker/dict-target": "dict target\n",
                "worker/list-target": "list target\n",
                "worker/tuple-target": "tuple target\n",
                "policy/contract.json": "{}\n",
            }
            for relative, content in targets.items():
                (repo / relative).write_text(content)
            source = repo / "tools/root.py"
            source.write_text(
                "PATH_MAP = {\n"
                f"    'worker/dict-target': '{digest(repo / 'worker/dict-target')}',\n"
                "}\n"
                f"STANDALONE = '{digest(repo / 'policy/contract.json')}'\n"
                "SEQUENCE = (\n"
                f"    '{digest(repo / 'worker/tuple-target')}',\n"
                f"    ['{digest(repo / 'worker/list-target')}'],\n"
                ")\n"
            )
            result = {
                "outer": {
                    "checker_rejections": [
                        {
                            "checker_sha256": digest(source),
                        }
                    ]
                },
                "unresolved_observation_sha256": "f" * 64,
            }
            (repo / "research/isolation/results/accepted.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=Freeze Graph Test",
                    "-c",
                    "user.email=freeze-graph@example.invalid",
                    "commit",
                    "-q",
                    "-m",
                    "fixture baseline",
                ],
                check=True,
            )

            first = self.run_checker(repo, checker)
            second = self.run_checker(repo, checker)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            report = json.loads(first.stdout)
            self.assertEqual(
                [row["path"] for row in report["frozen"]],
                [
                    "policy/contract.json",
                    "tools/root.py",
                    "worker/dict-target",
                    "worker/list-target",
                    "worker/tuple-target",
                ],
            )
            self.assertEqual(report["drift"], [])

            drifted_digest = digest(repo / "worker/dict-target")
            (repo / "worker/dict-target").write_text("drifted target\n")
            drift = self.run_checker(repo, checker)
            self.assertEqual(drift.returncode, 1, drift.stderr)
            drift_report = json.loads(drift.stdout)
            self.assertEqual(
                [row["sha256"] for row in drift_report["drift"]],
                [drifted_digest],
            )
            self.assertEqual(
                drift_report["drift"][0]["expected_paths"],
                ["worker/dict-target"],
            )

    def test_checker_requires_isolated_python(self) -> None:
        result = subprocess.run(
            ["python3", str(CHECKER)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires python3 -I", result.stderr)

    def test_valid_supersession_releases_the_replaced_checker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "tools").mkdir()
            (repo / "research/isolation/results").mkdir(parents=True)
            checker = repo / "tools/check-example.py"
            checker.write_text("raise SystemExit(1)\n")
            old_digest = digest(checker)
            result = {
                "checker_rejections": [
                    {
                        "checker": checker.name,
                        "checker_sha256": old_digest,
                        "exit_code": 1,
                        "accepted": False,
                    }
                ]
            }
            (repo / "research/isolation/results/example.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
            shutil.copy2(CHECKER, repo / "tools/check-freeze-graph.py")
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=Freeze Graph Test",
                    "-c",
                    "user.email=freeze-graph@example.invalid",
                    "commit",
                    "-q",
                    "-m",
                    "pinned checker",
                ],
                check=True,
            )

            checker.write_text(
                f'SUPERSEDES_CHECKER_SHA256 = ("{old_digest}",)\n'
                "raise SystemExit(1)\n"
            )
            report = self.run_checker(repo, repo / "tools/check-freeze-graph.py")
            self.assertEqual(report.returncode, 0, report.stderr)
            parsed = json.loads(report.stdout)
            self.assertEqual(parsed["drift"], [])
            self.assertNotIn(
                "tools/check-example.py",
                [row["path"] for row in parsed["frozen"]],
            )

    def build_source_supersession_repo(self, repo: Path) -> tuple[Path, str]:
        (repo / "tools").mkdir()
        (repo / "research/isolation/results").mkdir(parents=True)
        collector = repo / "tools/example-collector.py"
        collector.write_text("ORIGINAL = True\n")
        old_digest = digest(collector)
        result = {"source": {"collector_sha256": old_digest}}
        (repo / "research/isolation/results/example.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        shutil.copy2(CHECKER, repo / "tools/check-freeze-graph.py")
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.name=Freeze Graph Test",
                "-c",
                "user.email=freeze-graph@example.invalid",
                "commit",
                "-q",
                "-m",
                "pinned collector",
            ],
            check=True,
        )
        return collector, old_digest

    def test_valid_source_supersession_releases_the_replaced_collector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            collector, old_digest = self.build_source_supersession_repo(repo)
            collector.write_text("ORIGINAL = False\n")
            (repo / "tools/check-example.py").write_text(
                "SUPERSEDES_SOURCE_SHA256 = {\n"
                f'    "tools/example-collector.py": ("{old_digest}",),\n'
                "}\n"
                "raise SystemExit(1)\n"
            )
            report = self.run_checker(repo, repo / "tools/check-freeze-graph.py")
            self.assertEqual(report.returncode, 0, report.stderr)
            parsed = json.loads(report.stdout)
            self.assertEqual(parsed["drift"], [])
            self.assertNotIn(
                "tools/example-collector.py",
                [row["path"] for row in parsed["frozen"]],
            )

    def test_source_supersession_outside_a_checker_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            collector, old_digest = self.build_source_supersession_repo(repo)
            collector.write_text(
                "SUPERSEDES_SOURCE_SHA256 = {\n"
                f'    "tools/example-collector.py": ("{old_digest}",),\n'
                "}\n"
            )
            report = self.run_checker(repo, repo / "tools/check-freeze-graph.py")
            self.assertNotEqual(report.returncode, 0)
            self.assertIn("permitted only in checker files", report.stderr)

    def test_source_supersession_of_the_current_digest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            _, old_digest = self.build_source_supersession_repo(repo)
            (repo / "tools/check-example.py").write_text(
                "SUPERSEDES_SOURCE_SHA256 = {\n"
                f'    "tools/example-collector.py": ("{old_digest}",),\n'
                "}\n"
                "raise SystemExit(1)\n"
            )
            report = self.run_checker(repo, repo / "tools/check-freeze-graph.py")
            self.assertNotEqual(report.returncode, 0)
            self.assertIn("does not supersede a historical digest", report.stderr)


class NeutralityContract(unittest.TestCase):
    """A133: the neutral launcher may contain no provider name."""

    NEUTRAL_ARTIFACT = "worker/runtime/patchyard-provider-run"

    def run_checker(self, repo: Path):
        return subprocess.run(
            ["python3", "-I", str(repo / "tools/check-freeze-graph.py"), "--repo", str(repo)],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )

    def build_repo(self, repo: Path, *, policy, launcher: str) -> None:
        for relative in ("tools", "worker/runtime", "policy", "research/isolation/results"):
            (repo / relative).mkdir(parents=True, exist_ok=True)
        shutil.copy2(CHECKER, repo / "tools/check-freeze-graph.py")
        if policy is not None:
            (repo / "policy/provider-egress.json").write_text(policy)
        (repo / self.NEUTRAL_ARTIFACT).write_text(launcher)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.name=Freeze Graph Test",
                "-c",
                "user.email=freeze-graph@example.invalid",
                "commit",
                "-q",
                "-m",
                "fixture baseline",
            ],
            check=True,
        )

    def test_provider_tokens_in_the_neutral_artifact_are_violations(self) -> None:
        policy = json.dumps(
            {
                "providers": {
                    "meta": {
                        "display_name": "Meta",
                        "hostnames": ["api.meta.test"],
                    }
                }
            }
        )
        launcher = (
            "metadata stays legal because the token is boundary-guarded\n"
            "a bare meta keyword is a violation\n"
            "curl https://api.meta.test/v1 names the hostname\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.build_repo(repo, policy=policy, launcher=launcher)
            result = self.run_checker(repo)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["neutral"]["artifacts"], [self.NEUTRAL_ARTIFACT])
            self.assertEqual(
                [
                    (row["location"], row["token"])
                    for row in report["neutral"]["violations"]
                ],
                [
                    (f"{self.NEUTRAL_ARTIFACT}:2", "meta"),
                    (f"{self.NEUTRAL_ARTIFACT}:3", "api.meta.test"),
                    (f"{self.NEUTRAL_ARTIFACT}:3", "meta"),
                ],
            )

    def test_a_neutral_artifact_without_an_egress_policy_cannot_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.build_repo(repo, policy=None, launcher="clean\n")
            result = self.run_checker(repo)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("provider-egress.json", result.stderr)


def declared_supersessions(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(), filename=str(path))
    values = []
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or not any(
            isinstance(target, ast.Name)
            and target.id == "SUPERSEDES_CHECKER_SHA256"
            for target in statement.targets
        ):
            continue
        values.extend(ast.literal_eval(statement.value))
    return tuple(values)


class SupersededCheckerReplay(unittest.TestCase):
    RESULTS = (
        ROOT / "research/isolation/results/anthropic-crash-cleanup.json",
        ROOT / "research/isolation/results/openai-crash-cleanup.json",
    )

    def test_each_successor_preserves_its_recorded_rejection(self) -> None:
        for result_path in self.RESULTS:
            with self.subTest(result=result_path.name):
                result = json.loads(result_path.read_text())
                embedded = result["in_progress_record"]
                reconstructed = (
                    json.dumps(embedded["record"], indent=2) + "\n"
                ).encode()
                self.assertEqual(
                    hashlib.sha256(reconstructed).hexdigest(),
                    embedded["sha256_at_collection"],
                )
                self.assertEqual(len(result["checker_rejections"]), 3)
                with tempfile.TemporaryDirectory() as directory:
                    artifact = Path(directory) / "in-progress.json"
                    artifact.write_bytes(reconstructed)
                    for recorded in result["checker_rejections"]:
                        checker = ROOT / "tools" / recorded["checker"]
                        with self.subTest(checker=checker.name):
                            self.assertIn(
                                recorded["checker_sha256"],
                                declared_supersessions(checker),
                            )
                            replay = subprocess.run(
                                [
                                    "python3",
                                    "-I",
                                    str(checker),
                                    "--evidence",
                                    str(artifact),
                                ],
                                cwd=ROOT,
                                check=False,
                                capture_output=True,
                                text=True,
                            )
                            self.assertEqual(
                                replay.returncode,
                                recorded["exit_code"],
                                replay.stdout + replay.stderr,
                            )
                            self.assertEqual(
                                replay.returncode == 0,
                                recorded["accepted"],
                            )


class CredentialQualificationContract(unittest.TestCase):
    CHECKER = ROOT / "tools/check-credential-qualification.py"
    FIXTURES = ROOT / "fixtures/checker-contracts"

    def run_checker(self, fixture: str):
        return subprocess.run(
            [
                "python3",
                "-I",
                str(self.CHECKER),
                "--policy",
                str(self.FIXTURES / fixture),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_conforming_policy_is_accepted(self) -> None:
        result = self.run_checker("credential-qualification-conforming.json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "six Requirements proven by five committed Results", result.stdout
        )

    def test_qualified_provider_without_six_is_rejected(self) -> None:
        result = self.run_checker(
            "credential-qualification-missing-requirements.json"
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "openai: no complete A131 Result mapping is committed", result.stderr
        )


if __name__ == "__main__":
    unittest.main()
