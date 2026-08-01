#!/usr/bin/env python3
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


class ReplaceWorkerOperatorContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        (self.root / "infra" / "ansible").mkdir(parents=True)
        self.operator = self.root / "infra" / "replace-worker.sh"
        shutil.copy2(ROOT / "infra" / "replace-worker.sh", self.operator)
        self.tofu = self.root / "infra" / "tofu.sh"
        self.tofu.write_text(
            r"""#!/usr/bin/env bash
set -euo pipefail
if [[ "${2:-}" == show && "${3:-}" == -json ]]; then
  if [[ "${MOCK_WORKER_ORDER:-create-delete}" == create-delete ]]; then
    worker_actions='["create","delete"]'
  else
    worker_actions='["delete","create"]'
  fi
  if [[ "${MOCK_FIREWALL_ACTION:-update}" == update ]]; then
    firewall_actions='["update"]'
  else
    firewall_actions='["no-op"]'
  fi
  jq -n \
    --argjson worker_actions "$worker_actions" \
    --argjson firewall_actions "$firewall_actions" \
    '{resource_changes:[
      {address:"digitalocean_droplet.worker",change:{actions:$worker_actions}},
      {address:"digitalocean_firewall.worker",change:{actions:$firewall_actions}},
      {address:"digitalocean_droplet.control_plane",change:{actions:["no-op"]}}
    ]}'
elif [[ "${2:-}" == show && "${3:-}" == -no-color ]]; then
  printf '%s\n' reviewed-plan
elif [[ "${2:-}" == apply ]]; then
  printf '%s\n' apply >>"$MOCK_EVENTS"
  exit 73
else
  printf 'unexpected tofu invocation: %s\n' "$*" >&2
  exit 90
fi
"""
        )
        self.tofu.chmod(0o755)
        self.converge = self.root / "infra" / "ansible" / "converge.sh"
        self.converge.write_text(
            r"""#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == --check-inputs ]]; then
  printf '%s\n' preflight >>"$MOCK_EVENTS"
  [[ "${MOCK_PREFLIGHT_FAIL:-}" != yes ]] || exit 74
  printf '%s\n' converge_inputs_valid
  exit 0
fi
exit 91
"""
        )
        self.converge.chmod(0o755)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-qm",
                "fixture",
            ],
            check=True,
        )
        self.revision = self.git("rev-parse", "HEAD")
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "update-ref",
                "refs/remotes/origin/master",
                self.revision,
            ],
            check=True,
        )
        self.plan = Path(self.temp.name) / "worker.tfplan"
        self.plan.write_bytes(b"reviewed worker plan\n")
        self.plan_sha256 = hashlib.sha256(self.plan.read_bytes()).hexdigest()
        self.events = Path(self.temp.name) / "events"

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    def run_apply(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        self.events.unlink(missing_ok=True)
        env = {
            **os.environ,
            "MOCK_EVENTS": str(self.events),
            "PATCHYARD_REPLACE_APPROVED": "yes",
            "PATCHYARD_REPLACE_APPROVED_SHA256": self.plan_sha256,
            "PATCHYARD_REPLACE_APPROVED_REVISION": self.revision,
        }
        env.update(overrides)
        return subprocess.run(
            [str(self.operator), "apply", str(self.plan)],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def observed_events(self) -> list[str]:
        if not self.events.exists():
            return []
        return self.events.read_text().splitlines()

    def test_plan_digest_is_rechecked_after_preflight_before_apply(self) -> None:
        source = (ROOT / "infra" / "replace-worker.sh").read_text()
        digest_call = 'verify_approved_plan_sha256 "$PLAN_FILE"'
        self.assertEqual(source.count(digest_call), 2)
        preflight = source.index(
            '"$REPO_ROOT/infra/ansible/converge.sh" --check-inputs'
        )
        second_digest = source.rindex(digest_call)
        apply = source.index(
            '"$REPO_ROOT/infra/tofu.sh" digitalocean apply "$PLAN_FILE"'
        )
        self.assertLess(preflight, second_digest)
        self.assertLess(second_digest, apply)

    def test_exact_plan_revision_and_preflight_reach_apply_in_order(self) -> None:
        result = self.run_apply()
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertEqual(self.observed_events(), ["preflight", "apply"])

    def test_plan_digest_mismatch_refuses_before_preflight_or_apply(self) -> None:
        result = self.run_apply(PATCHYARD_REPLACE_APPROVED_SHA256="0" * 64)
        self.assertEqual(result.returncode, 2)
        self.assertIn("differs from the reviewed value", result.stderr)
        self.assertEqual(self.observed_events(), [])

    def test_revision_mismatch_refuses_before_preflight_or_apply(self) -> None:
        result = self.run_apply(PATCHYARD_REPLACE_APPROVED_REVISION="f" * 40)
        self.assertEqual(result.returncode, 2)
        self.assertIn("differs from the reviewed revision", result.stderr)
        self.assertEqual(self.observed_events(), [])

    def test_unmerged_revision_requires_explicit_a115_exception(self) -> None:
        marker = self.root / "candidate"
        marker.write_text("candidate\n")
        subprocess.run(["git", "-C", str(self.root), "add", "candidate"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-qm",
                "candidate",
            ],
            check=True,
        )
        self.revision = self.git("rev-parse", "HEAD")

        refused = self.run_apply()
        self.assertEqual(refused.returncode, 2)
        self.assertIn("A115 exception was not approved", refused.stderr)
        self.assertEqual(self.observed_events(), [])

        approved = self.run_apply(PATCHYARD_REPLACE_A115_UNMERGED_APPROVED="yes")
        self.assertEqual(approved.returncode, 73, approved.stderr)
        self.assertEqual(self.observed_events(), ["preflight", "apply"])

    def test_failed_converge_input_preflight_never_reaches_apply(self) -> None:
        result = self.run_apply(MOCK_PREFLIGHT_FAIL="yes")
        self.assertEqual(result.returncode, 74)
        self.assertEqual(self.observed_events(), ["preflight"])

    def test_destroy_first_or_firewall_noop_plan_is_refused(self) -> None:
        destroy_first = self.run_apply(MOCK_WORKER_ORDER="destroy-create")
        self.assertEqual(destroy_first.returncode, 2)
        self.assertEqual(self.observed_events(), [])

        firewall_noop = self.run_apply(MOCK_FIREWALL_ACTION="no-op")
        self.assertEqual(firewall_noop.returncode, 2)
        self.assertEqual(self.observed_events(), [])


if __name__ == "__main__":
    unittest.main()
