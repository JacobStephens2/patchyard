import hashlib
import json
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]


class AnthropicIssuanceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.control_tasks = (
            ROOT / "infra/ansible/roles/control_plane/tasks/main.yml"
        ).read_text()
        cls.worker_tasks = (
            ROOT / "infra/ansible/roles/worker/tasks/main.yml"
        ).read_text()
        cls.worker_qualifier = (
            ROOT / "infra/ansible/roles/worker/files/qualify-factory-worker"
        ).read_text()
        cls.runner = (
            ROOT / "worker/qualification/patchyard-run-anthropic-issuance"
        ).read_text()
        cls.launcher = (ROOT / "worker/runtime/patchyard-firecracker-run").read_text()
        cls.guest = (ROOT / "worker/image/patchyard-guest-run").read_text()

    def test_signing_key_exists_only_on_the_control_plane(self) -> None:
        self.assertIn("rsa_keygen_bits:3072", self.control_tasks)
        self.assertIn('mode: "0400"', self.control_tasks)
        self.assertNotIn("anthropic-wif-signing.pem", self.worker_tasks)
        self.assertIn(
            "test ! -e /etc/patchyard/anthropic-wif-signing.pem",
            self.worker_qualifier,
        )

    def test_restore_drill_receives_no_live_signing_identity(self) -> None:
        task = self.control_tasks.split(
            "- name: Keep the live Anthropic signing identity off restore drills", 1
        )[1].split("\n- name:", 1)[0]
        self.assertIn("anthropic-wif-signing.pem", task)
        self.assertIn("anthropic-wif.json", task)
        self.assertIn("patchyard-run-anthropic-issuance", task)
        self.assertIn("factory_restore_drill", task)

    def test_only_the_bearer_crosses_the_worker_boundary(self) -> None:
        self.assertIn(
            "remote_ssh sudo /usr/local/sbin/patchyard-firecracker-run", self.runner
        )
        self.assertIn('<"$RUN_TEMP/capability.json"', self.runner)
        self.assertNotIn('scp "$RUN_TEMP/assertion.jwt"', self.runner)
        self.assertIn(
            'dd if=/dev/stdin of="$CAPABILITY" bs=65536 count=1 iflag=fullblock',
            self.launcher,
        )
        self.assertIn('mount --bind "$RUN_TMPFS/credential.ext4"', self.launcher)
        self.assertIn("is_read_only:true", self.launcher)

    def test_guest_proves_the_credential_block_device_is_read_only(self) -> None:
        block_probe = self.guest.index('blockdev --getro "$CREDENTIAL_DEVICE"')
        mount = self.guest.index('mount -o ro,nosuid,nodev,noexec "$CREDENTIAL_DEVICE"')
        self.assertLess(block_probe, mount)

    def test_teardown_cannot_publish_after_a_failed_assertion(self) -> None:
        cleanup = self.launcher.split("remove_runtime() {", 1)[1].split("\n}", 1)[0]
        teardown = self.launcher.split("FAILURE_STAGE=teardown", 1)[1]
        self.assertIn("local -\n  set +e", cleanup)
        self.assertIn("assert_runtime_removed", self.launcher)
        self.assertLess(
            teardown.index("assert_runtime_removed"),
            teardown.index("trap - EXIT"),
        )

        option_lines = [
            line
            for line in cleanup.splitlines()
            if line.strip() in {"local -", "set +e"}
        ]
        probe = subprocess.run(
            [
                "bash",
                "-c",
                "\n".join(
                    [
                        "set -e",
                        "remove_runtime() {",
                        *option_lines,
                        "  false",
                        "  true",
                        "}",
                        "remove_runtime",
                        "false",
                        "printf 'published-after-failed-assertion\\n'",
                    ]
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(probe.returncode, 0)
        self.assertNotIn("published-after-failed-assertion", probe.stdout)

    def test_live_evidence_binds_current_guest_image_recipe(self) -> None:
        image = ROOT / "worker/image"
        records = []
        for path in sorted(path for path in image.rglob("*") if path.is_file()):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            records.append(f"{digest}  {path.relative_to(image)}\n")
        expected = hashlib.sha256("".join(records).encode()).hexdigest()
        evidence = json.loads(
            (
                ROOT / "research/isolation/results/anthropic-issuance-delivery.json"
            ).read_text()
        )
        self.assertEqual(evidence["image_recipe_sha256"], expected)

    def test_live_evidence_binds_current_host_contract(self) -> None:
        paths = (
            ROOT / "worker/qualification/patchyard-run-anthropic-issuance",
            ROOT / "worker/runtime/patchyard-firecracker-run",
        )
        records = []
        for path in paths:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            records.append(f"{digest}  {path.relative_to(ROOT)}\n")
        expected = hashlib.sha256("".join(records).encode()).hexdigest()
        evidence = json.loads(
            (
                ROOT / "research/isolation/results/anthropic-issuance-delivery.json"
            ).read_text()
        )
        self.assertEqual(evidence["host_contract_sha256"], expected)
        self.assertIn("LAUNCHER_HASH_RECORD=$(remote_ssh sudo sha256sum", self.runner)
        self.assertLess(
            self.runner.index("LAUNCHER_HASH_RECORD=$(remote_ssh sudo sha256sum"),
            self.runner.index("https://api.anthropic.com/v1/oauth/token"),
        )

    def test_guest_removes_bearer_before_writing_results(self) -> None:
        credential_start = self.guest.index('if [[ "$CREDENTIAL_REQUIRED" == true ]]')
        credential_unmount = self.guest.index("  umount /credential", credential_start)
        branch = self.guest.split(
            'if [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]]',
            1,
        )[1].split('\nif [[ "$MODE" == provider-qualification ]]', 1)[0]
        self.assertLess(
            branch.index('rm -f -- "$AUTH_CONFIG" "$CAPABILITY_FILE"'),
            branch.index("/result/change.patch"),
        )
        self.assertIn("touch /credential/write-probe", self.guest)
        self.assertLess(
            credential_unmount,
            self.guest.index("https://api.anthropic.com/v1/models?limit=1"),
        )
        self.assertLess(
            branch.index("if mountpoint -q /credential"),
            branch.index("https://api.anthropic.com/v1/models?limit=1"),
        )
        self.assertIn("credential_removed_before_output:true", branch)

    def test_exchange_and_worker_ingress_are_bounded(self) -> None:
        self.assertIn("--connect-timeout 10 --max-time 30", self.runner)
        self.assertIn("count=1 iflag=fullblock", self.launcher)

    def test_worker_residue_checks_fail_closed(self) -> None:
        self.assertIn('remote_ssh sudo test -d "$runtime_root"', self.runner)
        self.assertIn("runtime_residue=$(remote_ssh sudo find", self.runner)
        self.assertNotIn('[[ -z "$(remote_ssh sudo find', self.runner)
        self.assertIn("if remote_ssh sudo pgrep", self.runner)
        self.assertIn('[[ "$process_status" -eq 1 ]]', self.runner)
        self.assertIn("worker_links=$(remote_ssh sudo ip -o link show)", self.runner)
        self.assertIn(
            "worker_nft_tables=$(remote_ssh sudo nft list tables)", self.runner
        )

    def test_live_positive_call_is_non_generative(self) -> None:
        self.assertIn("https://api.anthropic.com/v1/models?limit=1", self.guest)
        self.assertNotIn("/v1/messages", self.guest)

    def test_provider_denial_diagnostic_is_bounded_and_credential_free(self) -> None:
        diagnostic = self.guest.split("PROVIDER_CURL_EXIT=0", 1)[1].split(
            "jq -e '.data | type", 1
        )[0]
        self.assertIn(".error.type", diagnostic)
        self.assertNotIn(".error.message", diagnostic)
        self.assertIn(
            'FAILURE="anthropic-provider-denied-$PROVIDER_STATUS-$PROVIDER_ERROR_TYPE"',
            diagnostic,
        )
        self.assertIn(
            'FAILURE="anthropic-provider-transport-failed-$PROVIDER_CURL_EXIT"',
            diagnostic,
        )
        self.assertLess(
            diagnostic.index('rm -f -- "$AUTH_CONFIG" "$CAPABILITY_FILE"'),
            diagnostic.index("PROVIDER_ERROR_TYPE=$(jq -r"),
        )
        self.assertNotIn("secret", diagnostic)
        self.assertNotIn("Authorization", diagnostic)

    def test_unprivileged_provider_call_has_a_private_writable_directory(self) -> None:
        branch = self.guest.split(
            'if [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]]',
            1,
        )[1].split('\nif [[ "$MODE" == provider-qualification ]]', 1)[0]
        self.assertIn(
            'install -d -m 0700 -o factory-agent -g factory-agent "$PROVIDER_TEMP"',
            branch,
        )
        self.assertIn('--dump-header "$PROVIDER_HEADERS"', branch)
        self.assertIn('--output "$PROVIDER_RESPONSE"', branch)
        self.assertNotIn("--dump-header /run/", branch)
        self.assertNotIn("--output /run/", branch)

    def test_exchange_failure_diagnostic_cannot_emit_credentials(self) -> None:
        diagnostic = self.runner.split('if [[ "$EXCHANGE_STATUS" != 200 ]]', 1)[
            1
        ].split('if [[ ! "$EXCHANGE_REQUEST_ID"', 1)[0]
        self.assertIn("anthropic_exchange_denied", diagnostic)
        self.assertIn(".error.type", diagnostic)
        self.assertNotIn(".error.message", diagnostic)
        self.assertNotIn("ASSERTION", diagnostic)
        self.assertNotIn("access_token", diagnostic)

    def test_worker_failure_diagnostic_is_allowlisted(self) -> None:
        diagnostic = (
            self.runner.split(
                "if ! remote_ssh sudo /usr/local/sbin/patchyard-firecracker-run", 1
            )[1]
            .split("; then\n", 1)[1]
            .split('install -d -m 0700 "$RUN_TEMP/result"', 1)[0]
        )
        self.assertIn("SANITIZED_WORKER_DIAGNOSTIC", diagnostic)
        self.assertIn("grep -E", diagnostic)
        self.assertIn("result filesystem integrity check failed", diagnostic)
        self.assertIn("factory worker run failed: stage=", diagnostic)
        self.assertNotIn("launcher.stdout", diagnostic)
        self.assertNotIn("ACCESS_TOKEN", diagnostic)
        self.assertNotIn("ASSERTION", diagnostic)


if __name__ == "__main__":
    unittest.main()
