#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "infra" / "wait-do-worker-firewall.sh"
OPERATOR = ROOT / "infra" / "replace-worker.sh"
ANSIBLE_WRAPPER = ROOT / "tools" / "check-ansible.sh"
EXPECTED_HELPER_SHA256 = (
    "5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba"
)
EXPECTED_OPERATOR_SHA256 = (
    "27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e"
)
EXPECTED_ANSIBLE_WRAPPER_SHA256 = (
    "743f16e371d8672e122402d60d70c53b40b1aec3ef7bd52f71cdec88324d3039"
)


def validate_complete_source_identities(
    helper: str, operator: str, ansible_wrapper: str
) -> None:
    for source, expected, label in (
        (helper, EXPECTED_HELPER_SHA256, "firewall readiness helper"),
        (operator, EXPECTED_OPERATOR_SHA256, "worker replacement operator"),
        (ansible_wrapper, EXPECTED_ANSIBLE_WRAPPER_SHA256, "Ansible gate wrapper"),
    ):
        actual = hashlib.sha256(source.encode()).hexdigest()
        if actual != expected:
            raise ValueError(f"{label} differs from its complete source binding")


def validate_ansible_wrapper_contract(ansible_wrapper: str) -> None:
    for fragment in (
        '  "$REPO_ROOT/infra/replace-worker.sh" \\\n',
        '  "$REPO_ROOT/infra/wait-do-worker-firewall.sh" \\\n',
        "  infra/ansible/tests/test_worker_firewall_readiness.py\n",
        'run_gate python3 -I "$REPO_ROOT/tools/run-isolated-unittest.py" \\\n',
        '    "$REPO_ROOT/$test_file"\n',
    ):
        if ansible_wrapper.count(fragment) != 1:
            raise ValueError(f"Ansible gate membership differs: {fragment}")


def validate_readiness_contract(helper: str, operator: str) -> None:
    required_helper_fragments = (
        '[[ "$DO_API_TOKEN" =~ ^[A-Za-z0-9._-]+$ ]]',
        "curl -q --config -",
        "--fail --silent --show-error",
        "--connect-timeout 3 --max-time 3 --proto '=https'",
        "--output \"$RESPONSE_FILE\" --write-out '%{http_code}'",
        '"https://api.digitalocean.com/v2/firewalls/$FIREWALL_ID"',
        "($workers | length) == 1",
        "($firewalls | length) == 1",
        "($firewalls[0].values.droplet_ids | length) == 1",
        '[[ -n "${response//[[:space:]]/}" ]] || return 1',
        "verdict=$(jq -cer",
        '\' <<<"$response" 2>/dev/null) || return 1',
        '(type == "object")',
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
        '[[ "$verdict" == true ]]',
        '[[ "$HTTP_STATUS" == 200 ]]',
        "worker/firewall state binding is not exact",
        "attempt <= MAX_ATTEMPTS",
    )
    for fragment in required_helper_fragments:
        if helper.count(fragment) != 1:
            raise ValueError(f"readiness binding differs: {fragment}")
    for exact_line in (
        "MAX_ATTEMPTS=24",
        "POLL_SECONDS=2",
        '    sleep "$POLL_SECONDS"',
    ):
        if helper.splitlines().count(exact_line) != 1:
            raise ValueError(f"readiness bound differs: {exact_line}")
    for singular_fragment in (
        "MAX_ATTEMPTS=",
        "POLL_SECONDS=",
        "--connect-timeout",
        "--max-time",
        "https://api.digitalocean.com/v2/firewalls/",
    ):
        if helper.count(singular_fragment) != 1:
            raise ValueError(
                f"readiness bound is not singular: {singular_fragment}"
            )

    if helper.count("sleep") != 1:
        raise ValueError("readiness sleep command is not singular")

    normalized_executors = helper.replace("''", "").replace('""', "")
    normalized_executors = re.sub(
        r"\\(?=[A-Za-z0-9_./-])",
        "",
        normalized_executors,
    )
    curl_executors = re.findall(
        r"(?<![A-Za-z0-9_])curl(?![A-Za-z0-9_])",
        normalized_executors,
    )
    if len(curl_executors) != 1:
        raise ValueError("readiness curl executor is not singular")

    if re.search(r"(?m)^[ \t]*(?:source|\.)[ \t]+", helper):
        raise ValueError("readiness helper may not source another file")
    for builtin_network in ("/dev/tcp", "/dev/udp"):
        if builtin_network in helper:
            raise ValueError("readiness helper contains Bash builtin networking")

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
    readiness_block = operator[
        converge_indexes[1] + len(converge_call) : qualify_index
    ]
    if readiness_block != f"    {helper_call}\n    ":
        raise ValueError("replacement readiness call must be direct and fatal")
    for operator_network in ("curl", "wget", "/dev/tcp", "/dev/udp", "urllib"):
        if operator_network in operator:
            raise ValueError("replacement operator contains an unreviewed network client")


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
        self.curl_calls = Path(self.temp.name) / "curl-calls"
        self.curl_total = Path(self.temp.name) / "curl-total"
        self.sleep_calls = Path(self.temp.name) / "sleep-calls"

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
        curl_source = r"""#!/usr/bin/env bash
set -euo pipefail

private_total=__PRIVATE_CURL_TOTAL__
private_accepted=__PRIVATE_CURL_ACCEPTED__
total=0
[[ ! -f "$private_total" ]] || read -r total <"$private_total"
total=$((total + 1))
printf '%s\n' "$total" >"$private_total"

actual_args=("$@")
[[ ${#actual_args[@]} -eq 17 ]] || exit 90
output=${actual_args[13]}
[[ "$output" == "$MOCK_RESPONSE_DIR"/tmp.* ]] || exit 91
expected_args=(
  -q
  --config
  -
  --fail
  --silent
  --show-error
  --connect-timeout
  3
  --max-time
  3
  --proto
  =https
  --output
  "$output"
  --write-out
  '%{http_code}'
  "https://api.digitalocean.com/v2/firewalls/$MOCK_FIREWALL_ID"
)
for index in "${!expected_args[@]}"; do
  [[ "${actual_args[$index]}" == "${expected_args[$index]}" ]] || exit 92
done
[[ " $* " != *" $DO_API_TOKEN "* ]] || exit 93
config=$(cat)
[[ "$config" == "header = \"Authorization: Bearer $DO_API_TOKEN\"" ]] || exit 94
: >"$output"

count=0
[[ ! -f "$private_accepted" ]] || read -r count <"$private_accepted"
count=$((count + 1))
printf '%s\n' "$count" >"$private_accepted"

ready() {
  printf '{"firewall":{"id":"%s","name":"patchyard-worker","status":"succeeded","pending_changes":[],"droplet_ids":[%s],"tags":[]}}\n' \
    "$MOCK_FIREWALL_ID" "$MOCK_WORKER_ID" >"$output"
}

pending() {
  printf '{"firewall":{"id":"%s","name":"patchyard-worker","status":"waiting","pending_changes":[],"droplet_ids":[%s],"tags":[]}}\n' \
    "$MOCK_FIREWALL_ID" "$MOCK_WORKER_ID" >"$output"
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
      "$MOCK_WORKER_ID" >"$output"
    ;;
  wrong-name)
    printf '{"firewall":{"id":"%s","name":"not-the-worker-firewall","status":"succeeded","pending_changes":[],"droplet_ids":[%s],"tags":[]}}\n' \
      "$MOCK_FIREWALL_ID" "$MOCK_WORKER_ID" >"$output"
    ;;
  wrong-worker)
    printf '{"firewall":{"id":"%s","name":"patchyard-worker","status":"succeeded","pending_changes":[],"droplet_ids":[999999999],"tags":[]}}\n' \
      "$MOCK_FIREWALL_ID" >"$output"
    ;;
  extra-worker)
    printf '{"firewall":{"id":"%s","name":"patchyard-worker","status":"succeeded","pending_changes":[],"droplet_ids":[%s,999999999],"tags":[]}}\n' \
      "$MOCK_FIREWALL_ID" "$MOCK_WORKER_ID" >"$output"
    ;;
  succeeded-pending)
    printf '{"firewall":{"id":"%s","name":"patchyard-worker","status":"succeeded","pending_changes":[{"droplet_id":%s}],"droplet_ids":[%s],"tags":[]}}\n' \
      "$MOCK_FIREWALL_ID" "$MOCK_WORKER_ID" "$MOCK_WORKER_ID" >"$output"
    ;;
  tagged)
    printf '{"firewall":{"id":"%s","name":"patchyard-worker","status":"succeeded","pending_changes":[],"droplet_ids":[%s],"tags":["production"]}}\n' \
      "$MOCK_FIREWALL_ID" "$MOCK_WORKER_ID" >"$output"
    ;;
  empty)
    :
    ;;
  whitespace)
    printf ' \n\t\n' >"$output"
    ;;
  multiple-ready)
    ready
    ready_payload=$(<"$output")
    printf '%s\n%s\n' "$ready_payload" "$ready_payload" >"$output"
    ;;
  malformed)
    printf '{' >"$output"
    ;;
  redirect-ready)
    ready
    printf '302'
    exit 0
    ;;
  http-failure)
    printf '{"message":"provider failure"}\n' >"$output"
    printf '500'
    exit 22
    ;;
  *)
    exit 95
    ;;
esac
printf '200'
"""
        curl.write_text(
            curl_source.replace(
                "__PRIVATE_CURL_TOTAL__", shlex.quote(str(self.curl_total))
            ).replace(
                "__PRIVATE_CURL_ACCEPTED__", shlex.quote(str(self.curl_calls))
            )
        )
        curl.chmod(0o755)

        sleep = self.mock_bin / "sleep"
        sleep_source = """#!/usr/bin/env bash
set -euo pipefail
private_sleep_calls=__PRIVATE_SLEEP_CALLS__
printf '%s\n' "$*" >>"$private_sleep_calls"
"""
        sleep.write_text(
            sleep_source.replace(
                "__PRIVATE_SLEEP_CALLS__", shlex.quote(str(self.sleep_calls))
            )
        )
        sleep.chmod(0o755)

        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def write_state(
        self,
        *,
        worker_id: str | None = None,
        firewall_worker_id: int | None = None,
        duplicate_firewall: bool = False,
        duplicate_worker: bool = False,
        extra_firewall_worker: bool = False,
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
        if duplicate_worker:
            resources.insert(1, resources[0])
        if extra_firewall_worker:
            firewall = next(
                resource
                for resource in resources
                if resource["address"] == "digitalocean_firewall.worker"
            )
            firewall["values"]["droplet_ids"].append(588900002)
        self.state.write_text(
            json.dumps({"values": {"root_module": {"resources": resources}}})
        )

    def run_helper(
        self, mode: str, *, token: str = "test-token"
    ) -> subprocess.CompletedProcess[str]:
        self.curl_calls.unlink(missing_ok=True)
        self.curl_total.unlink(missing_ok=True)
        self.sleep_calls.unlink(missing_ok=True)
        return subprocess.run(
            [str(self.helper)],
            cwd=self.root,
            env={
                **os.environ,
                "PATH": f"{self.mock_bin}:/usr/bin:/bin",
                "DO_API_TOKEN": token,
                "MOCK_STATE": str(self.state),
                "MOCK_RESPONSE_DIR": self.temp.name,
                "MOCK_FIREWALL_MODE": mode,
                "MOCK_FIREWALL_ID": self.firewall_id,
                "MOCK_WORKER_ID": self.worker_id,
                "TMPDIR": self.temp.name,
            },
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def read_lines(path: Path) -> list[str]:
        if not path.exists():
            return []
        return path.read_text().splitlines()

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
        self.assertEqual(self.read_counter(self.curl_total), 1)
        self.assertEqual(self.read_lines(self.sleep_calls), [])

    def test_pending_state_is_polled_until_exact_state_is_ready(self) -> None:
        result = self.run_helper("pending-then-ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_counter(self.curl_calls), 2)
        self.assertEqual(self.read_counter(self.curl_total), 2)
        self.assertEqual(self.read_lines(self.sleep_calls), ["2"])

    def test_each_provider_binding_mismatch_exhausts_and_refuses(self) -> None:
        for mode in (
            "pending",
            "wrong-firewall",
            "wrong-name",
            "wrong-worker",
            "extra-worker",
            "succeeded-pending",
            "tagged",
            "empty",
            "whitespace",
            "multiple-ready",
            "malformed",
            "redirect-ready",
            "http-failure",
        ):
            with self.subTest(mode=mode):
                result = self.run_helper(mode)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("did not reach provider desired state", result.stderr)
                self.assertEqual(self.read_counter(self.curl_calls), 24)
                self.assertEqual(self.read_counter(self.curl_total), 24)
                self.assertEqual(self.read_lines(self.sleep_calls), ["2"] * 23)

    def test_inexact_state_binding_refuses_before_provider_poll(self) -> None:
        cases = (
            {"worker_id": "not-a-droplet"},
            {"firewall_worker_id": 588900002},
            {"duplicate_firewall": True},
            {"duplicate_worker": True},
            {"extra_firewall_worker": True},
        )
        for case in cases:
            with self.subTest(case=case):
                self.write_state(**case)
                result = self.run_helper("ready")
                self.assertEqual(result.returncode, 2)
                self.assertIn("does not bind one firewall to one worker", result.stderr)
                self.assertEqual(self.read_counter(self.curl_calls), 0)
                self.assertEqual(self.read_counter(self.curl_total), 0)

    def test_malformed_bearer_refuses_before_provider_poll(self) -> None:
        result = self.run_helper("ready", token='unsafe"\nurl = "https://example.test')
        self.assertEqual(result.returncode, 2)
        self.assertIn("refused a malformed DigitalOcean provider token", result.stderr)
        self.assertEqual(self.read_counter(self.curl_calls), 0)
        self.assertEqual(self.read_counter(self.curl_total), 0)

    def test_source_and_operator_bind_every_readiness_predicate(self) -> None:
        helper = HELPER.read_text()
        operator = OPERATOR.read_text()
        ansible_wrapper = ANSIBLE_WRAPPER.read_text()
        validate_complete_source_identities(helper, operator, ansible_wrapper)
        validate_readiness_contract(helper, operator)
        validate_ansible_wrapper_contract(ansible_wrapper)

    def test_source_only_weakening_mutations_fail_the_contract(self) -> None:
        helper = HELPER.read_text()
        operator = OPERATOR.read_text()
        ansible_wrapper = ANSIBLE_WRAPPER.read_text()
        helper_mutations = {
            "unbounded attempt expansion": helper.replace(
                "MAX_ATTEMPTS=24", "MAX_ATTEMPTS=240", 1
            ),
            "later maximum-attempt override": helper.replace(
                "MAX_ATTEMPTS=24\n",
                "MAX_ATTEMPTS=24\nMAX_ATTEMPTS=240\n",
                1,
            ),
            "curl timeout removal": helper.replace(" --max-time 3", "", 1),
            "curl HTTP failure acceptance": helper.replace(
                "--fail --silent --show-error",
                "--silent --show-error",
                1,
            ),
            "discarded extra timeout and retry curl": helper.replace(
                "  HTTP_STATUS=\n",
                "  curl -q -sS -m 900 --retry 100 --retry-delay 60 "
                "-o /dev/null \\\n"
                '    "https://api.digitalocean.com/v2/firewalls/'
                '${FIREWALL_ID}" || true\n'
                "  HTTP_STATUS=\n",
                1,
            ),
            "discarded response overwrite curl": helper.replace(
                '    "https://api.digitalocean.com/v2/firewalls/'
                '$FIREWALL_ID"); then\n',
                '    "https://api.digitalocean.com/v2/firewalls/'
                '$FIREWALL_ID"); then\n'
                '    curl -q -sS -o "$RESPONSE_FILE" '
                '"file:///var/tmp/firewall-ready.json" || true\n',
                1,
            ),
            "absolute-path curl executor": helper.replace(
                "  HTTP_STATUS=\n",
                "  /nonexistent/curl -q -m 900 \\\n"
                '    "https://api.digitalocean.com/v2/firewalls/'
                '${FIREWALL_ID}" || true\n'
                "  HTTP_STATUS=\n",
                1,
            ),
            "empty-quote assembled curl executor": helper.replace(
                "  HTTP_STATUS=\n",
                '  cu""rl -q -m 900 "file:///var/tmp/'
                'firewall-ready.json" || true\n'
                "  HTTP_STATUS=\n",
                1,
            ),
            "non-200 HTTP acceptance": helper.replace(
                '[[ "$HTTP_STATUS" == 200 ]]',
                '[[ "$HTTP_STATUS" =~ ^[234] ]]',
                1,
            ),
            "empty-body acceptance": helper.replace(
                '  [[ -n "${response//[[:space:]]/}" ]] || return 1\n',
                "",
                1,
            ),
            "jq status-only acceptance": helper.replace(
                '  [[ "$verdict" == true ]]\n',
                "  return 0\n",
                1,
            ),
            "provider object-type weakening": helper.replace(
                '(type == "object")',
                "(type != \"object\")",
                1,
            ),
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
            "state worker-cardinality weakening": helper.replace(
                "($workers | length) == 1",
                "($workers | length) >= 1",
                1,
            ),
            "state firewall-cardinality weakening": helper.replace(
                "($firewalls | length) == 1",
                "($firewalls | length) >= 1",
                1,
            ),
            "state attachment-cardinality weakening": helper.replace(
                "($firewalls[0].values.droplet_ids | length) == 1",
                "($firewalls[0].values.droplet_ids | length) >= 1",
                1,
            ),
            "provider attachment-cardinality weakening": helper.replace(
                "(.droplet_ids | length) == 1",
                "(.droplet_ids | length) >= 1",
                1,
            ),
            "bearer argv exposure": helper.replace(
                '| curl -q --config - "$@"',
                '| curl -q -H "Authorization: Bearer $bearer" "$@"',
                1,
            ),
            "bearer alphabet weakening": helper.replace(
                '[[ "$DO_API_TOKEN" =~ ^[A-Za-z0-9._-]+$ ]]',
                '[[ "$DO_API_TOKEN" =~ .+ ]]',
                1,
            ),
            "multi-value last-result filtering": helper.replace(
                '\' <<<"$response" 2>/dev/null) || return 1',
                '\' <<<"$response" 2>/dev/null | tail -n1) || return 1',
                1,
            ),
            "later curl timeout overrides": helper.replace(
                "    --connect-timeout 3 --max-time 3 --proto '=https' \\\n",
                "    --connect-timeout 3 --max-time 3 --proto '=https' \\\n"
                "    --connect-timeout 900 --max-time 900 \\\n",
                1,
            ),
            "later poll interval override": helper.replace(
                "POLL_SECONDS=2\n",
                "POLL_SECONDS=2\nPOLL_SECONDS=600\n",
                1,
            ),
            "absolute extra sleep": helper.replace(
                '    sleep "$POLL_SECONDS"\n',
                '    sleep "$POLL_SECONDS"\n    /bin/sleep 0.02\n',
                1,
            ),
        }
        for name, mutation in helper_mutations.items():
            with self.subTest(name=name):
                self.assertNotEqual(mutation, helper)
                with self.assertRaises(ValueError):
                    validate_readiness_contract(mutation, operator)

        curl_argv_mutations = {
            "short-form curl timeout override": helper.replace(
                "    --connect-timeout 3 --max-time 3 --proto '=https' \\\n",
                "    --connect-timeout 3 --max-time 3 --proto '=https' \\\n"
                "    -m 900 \\\n",
                1,
            ),
            "curl alias timeout wrapper": helper.replace(
                "curl_with_bearer() {\n",
                "shopt -s expand_aliases\n"
                "alias curl='curl -m 900'\n\n"
                "curl_with_bearer() {\n",
                1,
            ),
            "curl function timeout wrapper": helper.replace(
                "curl_with_bearer() {\n",
                "curl() { command curl -m 900 \"$@\"; }\n\n"
                "curl_with_bearer() {\n",
                1,
            ),
            "additional curl config": helper.replace(
                "    --connect-timeout 3 --max-time 3 --proto '=https' \\\n",
                "    --connect-timeout 3 --max-time 3 --proto '=https' \\\n"
                "    --config <(printf 'max-time = 900\\n') \\\n",
                1,
            ),
            "curl retry expansion": helper.replace(
                "    --connect-timeout 3 --max-time 3 --proto '=https' \\\n",
                "    --connect-timeout 3 --max-time 3 --proto '=https' \\\n"
                "    --retry 100 --retry-delay 60 --retry-all-errors \\\n",
                1,
            ),
        }
        for name, mutation in curl_argv_mutations.items():
            with self.subTest(name=name):
                self.assertNotEqual(mutation, helper)
                self.helper.write_text(mutation)
                try:
                    result = self.run_helper("ready")
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertEqual(self.read_counter(self.curl_calls), 0)
                    self.assertEqual(self.read_counter(self.curl_total), 24)
                finally:
                    self.helper.write_text(helper)

        extra_rejected_wrapper_call = helper.replace(
            "  HTTP_STATUS=\n",
            '  curl_with_bearer "$DO_API_TOKEN" -m 900 '
            '"https://example.invalid/" || true\n'
            "  HTTP_STATUS=\n",
            1,
        )
        self.assertNotEqual(extra_rejected_wrapper_call, helper)
        validate_readiness_contract(extra_rejected_wrapper_call, operator)
        self.helper.write_text(extra_rejected_wrapper_call)
        try:
            result = self.run_helper("ready")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.read_counter(self.curl_calls), 1)
            self.assertEqual(self.read_counter(self.curl_total), 2)
        finally:
            self.helper.write_text(helper)

        identity_mutations = (
            (
                "alternate absolute network client",
                helper.replace(
                    "  HTTP_STATUS=\n",
                    "  /nonexistent/wget --timeout=900 --tries=100 -O /dev/null "
                    '"https://api.digitalocean.com/v2/droplets/'
                    '${WORKER_ID}" || true\n'
                    "  HTTP_STATUS=\n",
                    1,
                ),
                operator,
                ansible_wrapper,
            ),
            (
                "parameter-assembled absolute network client",
                helper.replace(
                    "  HTTP_STATUS=\n",
                    "  A101_CLIENT=/nonexistent/cur\n"
                    '  "${A101_CLIENT}l" -m 900 --retry 100 '
                    '"https://api.digitalocean.com/v2/droplets/'
                    '${WORKER_ID}" || true\n'
                    "  HTTP_STATUS=\n",
                    1,
                ),
                operator,
                ansible_wrapper,
            ),
            (
                "guarded repository sibling source",
                helper.replace(
                    "for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do\n",
                    '[[ ! -f "$REPO_ROOT/infra/lib/readiness-extra.sh" ]] '
                    '|| . "$REPO_ROOT/infra/lib/readiness-extra.sh"\n\n'
                    "for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do\n",
                    1,
                ),
                operator,
                ansible_wrapper,
            ),
            (
                "guarded Bash builtin networking",
                helper.replace(
                    "for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do\n",
                    '[[ -z "${PATCHYARD_DEBUG_PROBE:-}" ]] '
                    "|| exec 3<>/dev/tcp/api.digitalocean.com/443\n\n"
                    "for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do\n",
                    1,
                ),
                operator,
                ansible_wrapper,
            ),
            (
                "operator-wide extra network client",
                helper,
                operator.replace(
                    '    "$REPO_ROOT/infra/tofu.sh" digitalocean apply '
                    '"$PLAN_FILE"\n',
                    '    "$REPO_ROOT/infra/tofu.sh" digitalocean apply '
                    '"$PLAN_FILE"\n'
                    "    curl -sS -m 900 --retry 100 -o /dev/null "
                    '"https://api.digitalocean.com/v2/droplets" || true\n',
                    1,
                ),
                ansible_wrapper,
            ),
            (
                "Ansible helper ShellCheck membership removal",
                helper,
                operator,
                ansible_wrapper.replace(
                    '  "$REPO_ROOT/infra/wait-do-worker-firewall.sh" \\\n',
                    "",
                    1,
                ),
            ),
            (
                "Ansible readiness census removal",
                helper,
                operator,
                ansible_wrapper.replace(
                    "  infra/ansible/tests/test_worker_firewall_readiness.py\n",
                    "",
                    1,
                ),
            ),
            (
                "helper-controlled attempted-counter redirection",
                helper.replace(
                    "  HTTP_STATUS=\n",
                    '  MOCK_CURL_TOTAL=/dev/null cu"r"l -q -m 900 '
                    '"https://api.digitalocean.com/v2/droplets/'
                    '${WORKER_ID}" || true\n'
                    "  HTTP_STATUS=\n",
                    1,
                ),
                operator,
                ansible_wrapper,
            ),
        )
        for name, mutated_helper, mutated_operator, mutated_wrapper in (
            identity_mutations
        ):
            with self.subTest(name=name):
                self.assertNotEqual(
                    (mutated_helper, mutated_operator, mutated_wrapper),
                    (helper, operator, ansible_wrapper),
                )
                with self.assertRaises(ValueError):
                    validate_complete_source_identities(
                        mutated_helper, mutated_operator, mutated_wrapper
                    )

        helper_call = '    "$REPO_ROOT/infra/wait-do-worker-firewall.sh"\n'
        qualify_call = '    "$REPO_ROOT/infra/ansible/qualify.sh"\n'
        removed = operator.replace(helper_call, "", 1)
        moved_after_a101 = operator.replace(
            helper_call + qualify_call,
            qualify_call + helper_call,
            1,
        )
        conditional = operator.replace(
            helper_call,
            '    if [[ "${PATCHYARD_SKIP_READINESS:-}" != yes ]]; then\n'
            + helper_call
            + "    fi\n",
            1,
        )
        nonfatal = operator.replace(
            helper_call,
            '    "$REPO_ROOT/infra/wait-do-worker-firewall.sh" || true\n',
            1,
        )
        for name, mutation in (
            ("readiness call removal", removed),
            ("readiness after A101", moved_after_a101),
            ("conditional readiness bypass", conditional),
            ("nonfatal readiness call", nonfatal),
        ):
            with self.subTest(name=name):
                self.assertNotEqual(mutation, operator)
                with self.assertRaises((ValueError, IndexError)):
                    validate_readiness_contract(helper, mutation)


class AnsibleGateAggregationContract(unittest.TestCase):
    @staticmethod
    def run_aggregate(gates: str) -> subprocess.CompletedProcess[str]:
        wrapper = ANSIBLE_WRAPPER.read_text()
        aggregate_start = wrapper.index("gate_status=0\n")
        aggregate_end = wrapper.index(
            "\n\nACTUAL_SHELLCHECK_VERSION", aggregate_start
        )
        aggregate = wrapper[aggregate_start:aggregate_end]
        terminal_call = (
            'run_gate python3 -I '
            '"$REPO_ROOT/tools/check-a101-readiness-root.py"\n'
        )
        footer = wrapper.split(terminal_call, 1)[1]
        return subprocess.run(
            ["bash", "-c", f"set -euo pipefail\n{aggregate}\n{gates}\n{footer}"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def test_failure_tail_names_gate_after_later_passes(self) -> None:
        result = self.run_aggregate(
            "failing_unit_test() { echo 'unit test: fail'; return 1; }\n"
            "later_gate() { echo 'playbook: rollback-boundary.yml'; }\n"
            "run_gate failing_unit_test\n"
            "run_gate later_gate"
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stdout.splitlines()[-3:],
            [
                "playbook: rollback-boundary.yml",
                "Failed Ansible gates:",
                "  failing_unit_test",
            ],
        )

    def test_passing_aggregate_emits_no_summary_bytes(self) -> None:
        result = self.run_aggregate(
            "first_gate() { echo 'first gate: pass'; }\n"
            "final_gate() { echo 'final gate: pass'; }\n"
            "run_gate first_gate\n"
            "run_gate final_gate"
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "first gate: pass\nfinal gate: pass\n")


if __name__ == "__main__":
    unittest.main()
