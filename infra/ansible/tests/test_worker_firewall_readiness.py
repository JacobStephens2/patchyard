#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "infra" / "wait-do-worker-firewall.sh"
OPERATOR = ROOT / "infra" / "replace-worker.sh"


def validate_readiness_contract(helper: str, operator: str) -> None:
    required_helper_fragments = (
        "--connect-timeout 3 --max-time 3 --proto '=https'",
        '"https://api.digitalocean.com/v2/firewalls/$FIREWALL_ID"',
        '.id == $firewall_id',
        '.name == "patchyard-worker"',
        '.status == "succeeded"',
        "(.pending_changes | type) == \"array\"",
        "(.pending_changes | length) == 0",
        "(.droplet_ids | type) == \"array\"",
        "(.droplet_ids | length) == 1",
        "(.droplet_ids[0] | tostring) == $worker_id",
        "(.tags | type) == \"array\"",
        "(.tags | length) == 0",
        "worker/firewall state binding is not exact",
        "attempt <= MAX_ATTEMPTS",
    )
    for fragment in required_helper_fragments:
        if helper.count(fragment) != 1:
            raise ValueError(f"readiness binding differs: {fragment}")
    for exact_line in ("MAX_ATTEMPTS=24", "POLL_SECONDS=2"):
        if helper.splitlines().count(exact_line) != 1:
            raise ValueError(f"readiness bound differs: {exact_line}")

    state_attachment = """$firewalls[0].values.droplet_ids[0] | tostring
      ) == (
        $workers[0].values.id | tostring"""
    if helper.count(state_attachment) != 1:
        raise ValueError("OpenTofu worker/firewall state attachment is not exact")

    helper_call = '"$REPO_ROOT/infra/wait-do-worker-firewall.sh"'
    if operator.count(helper_call) != 1:
        raise ValueError("replacement operator readiness call differs")

    apply_call = (
        '"$REPO_ROOT/infra/tofu.sh" digitalocean apply "$PLAN_FILE"'
    )
    converge_call = '"$REPO_ROOT/infra/ansible/converge.sh"\n'
    qualify_call = '"$REPO_ROOT/infra/ansible/qualify.sh"'
    apply_index = operator.index(apply_call)
    converge_indexes: list[int] = []
    offset = 0
    while True:
        found = operator.find(converge_call, offset)
        if found == -1:
            break
        converge_indexes.append(found)
        offset = found + len(converge_call)
    if len(converge_indexes) != 2:
        raise ValueError("replacement operator must converge exactly twice")
    readiness_index = operator.index(helper_call)
    qualify_index = operator.index(qualify_call)
    if not (
        apply_index
        < converge_indexes[0]
        < converge_indexes[1]
        < readiness_index
        < qualify_index
    ):
        raise ValueError("firewall readiness is not between converge and A101")


class WorkerFirewallReadinessContract(unittest.TestCase):
    worker_id = "588900001"
    firewall_id = "01af87da-4951-4441-a1c8-ddfc0214811b"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        (self.root / "infra").mkdir(parents=True)
        self.helper = self.root / "infra" / "wait-do-worker-firewall.sh"
        shutil.copy2(HELPER, self.helper)

        self.state = Path(self.temp.name) / "state.json"
        self.write_state()

        tofu = self.root / "infra" / "tofu.sh"
        tofu.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
[[ "$*" == "digitalocean show -json" ]] || exit 90
cat "$MOCK_STATE"
"""
        )
        tofu.chmod(0o755)

        self.mock_bin = Path(self.temp.name) / "bin"
        self.mock_bin.mkdir()
        curl = self.mock_bin / "curl"
        curl.write_text(
            r"""#!/usr/bin/env bash
set -euo pipefail
[[ "$*" == *"Authorization: Bearer $DO_API_TOKEN"* ]] || exit 91
count=0
[[ ! -f "$MOCK_CURL_CALLS" ]] || read -r count <"$MOCK_CURL_CALLS"
count=$((count + 1))
printf '%s\n' "$count" >"$MOCK_CURL_CALLS"

ready() {
  printf '{"firewall":{"id":"%s","name":"patchyard-worker","status":"succeeded","pending_changes":[],"droplet_ids":[%s],"tags":[]}}\n' \
    "$MOCK_FIREWALL_ID" "$MOCK_WORKER_ID"
}

pending() {
  printf '{"firewall":{"id":"%s","name":"patchyard-worker","status":"waiting","pending_changes":[{"droplet_id":%s}],"droplet_ids":[%s],"tags":[]}}\n' \
    "$MOCK_FIREWALL_ID" "$MOCK_WORKER_ID" "$MOCK_WORKER_ID"
}

case "$MOCK_FIREWALL_MODE" in
  ready)
    ready
    ;;
  pending)
    pending
    ;;
  pending-then-ready)
    if ((count == 1)); then pending; else ready; fi
    ;;
  wrong-firewall)
    printf '{"firewall":{"id":"00000000-0000-0000-0000-000000000000","name":"patchyard-worker","status":"succeeded","pending_changes":[],"droplet_ids":[%s],"tags":[]}}\n' \
      "$MOCK_WORKER_ID"
    ;;
  wrong-name)
    printf '{"firewall":{"id":"%s","name":"not-the-worker-firewall","status":"succeeded","pending_changes":[],"droplet_ids":[%s],"tags":[]}}\n' \
      "$MOCK_FIREWALL_ID" "$MOCK_WORKER_ID"
    ;;
  wrong-worker)
    printf '{"firewall":{"id":"%s","name":"patchyard-worker","status":"succeeded","pending_changes":[],"droplet_ids":[999999999],"tags":[]}}\n' \
      "$MOCK_FIREWALL_ID"
    ;;
  tagged)
    printf '{"firewall":{"id":"%s","name":"patchyard-worker","status":"succeeded","pending_changes":[],"droplet_ids":[%s],"tags":["production"]}}\n' \
      "$MOCK_FIREWALL_ID" "$MOCK_WORKER_ID"
    ;;
  malformed)
    printf '{'
    ;;
  http-failure)
    exit 22
    ;;
  *)
    exit 92
    ;;
esac
"""
        )
        curl.chmod(0o755)

        sleep = self.mock_bin / "sleep"
        sleep.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"$MOCK_SLEEP_CALLS"
"""
        )
        sleep.chmod(0o755)

        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.curl_calls = Path(self.temp.name) / "curl-calls"
        self.sleep_calls = Path(self.temp.name) / "sleep-calls"

    def write_state(
        self,
        *,
        worker_id: str | None = None,
        firewall_worker_id: int | None = None,
        duplicate_firewall: bool = False,
    ) -> None:
        worker_id = worker_id or self.worker_id
        if firewall_worker_id is None:
            firewall_worker_id = (
                int(worker_id) if worker_id.isdigit() else int(self.worker_id)
            )
        resources: list[dict[str, object]] = [
            {
                "address": "digitalocean_droplet.worker",
                "values": {"id": worker_id},
            },
            {
                "address": "digitalocean_firewall.worker",
                "values": {
                    "id": self.firewall_id,
                    "droplet_ids": [firewall_worker_id],
                },
            },
        ]
        if duplicate_firewall:
            resources.append(resources[-1])
        self.state.write_text(
            json.dumps({"values": {"root_module": {"resources": resources}}})
        )

    def run_helper(self, mode: str) -> subprocess.CompletedProcess[str]:
        self.curl_calls.unlink(missing_ok=True)
        self.sleep_calls.unlink(missing_ok=True)
        return subprocess.run(
            [str(self.helper)],
            cwd=self.root,
            env={
                **os.environ,
                "PATH": f"{self.mock_bin}:/usr/bin:/bin",
                "DO_API_TOKEN": "test-token",
                "MOCK_STATE": str(self.state),
                "MOCK_CURL_CALLS": str(self.curl_calls),
                "MOCK_SLEEP_CALLS": str(self.sleep_calls),
                "MOCK_FIREWALL_MODE": mode,
                "MOCK_FIREWALL_ID": self.firewall_id,
                "MOCK_WORKER_ID": self.worker_id,
            },
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def count_file(path: Path) -> int:
        if not path.exists():
            return 0
        return len(path.read_text().splitlines())

    @staticmethod
    def read_counter(path: Path) -> int:
        if not path.exists():
            return 0
        return int(path.read_text().strip())

    def test_exact_provider_desired_state_passes_without_sleep(self) -> None:
        result = self.run_helper("ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("worker firewall readiness: pass", result.stdout)
        self.assertEqual(self.read_counter(self.curl_calls), 1)
        self.assertEqual(self.count_file(self.sleep_calls), 0)

    def test_pending_state_is_polled_until_exact_state_is_ready(self) -> None:
        result = self.run_helper("pending-then-ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_counter(self.curl_calls), 2)
        self.assertEqual(self.count_file(self.sleep_calls), 1)

    def test_each_provider_binding_mismatch_exhausts_and_refuses(self) -> None:
        for mode in (
            "pending",
            "wrong-firewall",
            "wrong-name",
            "wrong-worker",
            "tagged",
            "malformed",
            "http-failure",
        ):
            with self.subTest(mode=mode):
                result = self.run_helper(mode)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("did not reach provider desired state", result.stderr)
                self.assertEqual(self.read_counter(self.curl_calls), 24)
                self.assertEqual(self.count_file(self.sleep_calls), 23)

    def test_inexact_state_binding_refuses_before_provider_poll(self) -> None:
        cases = (
            {"worker_id": "not-a-droplet"},
            {"firewall_worker_id": 588900002},
            {"duplicate_firewall": True},
        )
        for case in cases:
            with self.subTest(case=case):
                self.write_state(**case)
                result = self.run_helper("ready")
                self.assertEqual(result.returncode, 2)
                self.assertIn("does not bind one firewall to one worker", result.stderr)
                self.assertEqual(self.read_counter(self.curl_calls), 0)

    def test_source_and_operator_bind_every_readiness_predicate(self) -> None:
        validate_readiness_contract(HELPER.read_text(), OPERATOR.read_text())

    def test_source_only_weakening_mutations_fail_the_contract(self) -> None:
        helper = HELPER.read_text()
        operator = OPERATOR.read_text()
        helper_mutations = {
            "unbounded attempt expansion": helper.replace(
                "MAX_ATTEMPTS=24", "MAX_ATTEMPTS=240", 1
            ),
            "curl timeout removal": helper.replace(" --max-time 3", "", 1),
            "firewall identity weakening": helper.replace(
                ".id == $firewall_id", ".id != $firewall_id", 1
            ),
            "firewall name weakening": helper.replace(
                '.name == "patchyard-worker"',
                '.name != "patchyard-worker"',
                1,
            ),
            "provider status weakening": helper.replace(
                '.status == "succeeded"', '.status != "succeeded"', 1
            ),
            "pending-change weakening": helper.replace(
                "(.pending_changes | length) == 0",
                "(.pending_changes | length) >= 0",
                1,
            ),
            "worker identity weakening": helper.replace(
                "(.droplet_ids[0] | tostring) == $worker_id",
                "(.droplet_ids[0] | tostring) != $worker_id",
                1,
            ),
            "tag attachment weakening": helper.replace(
                "(.tags | length) == 0", "(.tags | length) >= 0", 1
            ),
            "state attachment weakening": helper.replace(
                """$firewalls[0].values.droplet_ids[0] | tostring
      ) == (
        $workers[0].values.id | tostring""",
                """$firewalls[0].values.droplet_ids[0] | tostring
      ) != (
        $workers[0].values.id | tostring""",
                1,
            ),
        }
        for name, mutation in helper_mutations.items():
            with self.subTest(name=name):
                self.assertNotEqual(mutation, helper)
                with self.assertRaises(ValueError):
                    validate_readiness_contract(mutation, operator)

        helper_call = '    "$REPO_ROOT/infra/wait-do-worker-firewall.sh"\n'
        qualify_call = '    "$REPO_ROOT/infra/ansible/qualify.sh"\n'
        removed = operator.replace(helper_call, "", 1)
        moved_after_a101 = operator.replace(
            helper_call + qualify_call,
            qualify_call + helper_call,
            1,
        )
        for name, mutation in (
            ("readiness call removal", removed),
            ("readiness after A101", moved_after_a101),
        ):
            with self.subTest(name=name):
                self.assertNotEqual(mutation, operator)
                with self.assertRaises((ValueError, IndexError)):
                    validate_readiness_contract(helper, mutation)


if __name__ == "__main__":
    unittest.main()
