import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "tools/check-freeze-graph.py"
EXPECTED_FROZEN_PATHS = [
    "policy/anthropic-wif.json",
    "policy/openai-wif.json",
    "research/isolation/results/anthropic-revocation-rotation.json",
    "tools/anthropic-wif-crash-cleanup.py",
    "tools/anthropic-wif-lifecycle-admin.py",
    "tools/anthropic-wif-lifecycle.py",
    "tools/anthropic-wif-revocation.py",
    "tools/check-anthropic-crash-cleanup.py",
    "tools/check-anthropic-expiry.py",
    "tools/check-anthropic-revocation.py",
    "tools/openai-wif-issuance.py",
    "worker/image/patchyard-guest-run",
    "worker/image/production-parity.json",
    "worker/qualification/patchyard-run-anthropic-issuance",
    "worker/qualification/hostile-test-manifest.json",
    "worker/runtime/patchyard-anthropic-one-shot",
    "worker/runtime/patchyard-firecracker-run",
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


if __name__ == "__main__":
    unittest.main()
