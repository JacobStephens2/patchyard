import pathlib
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
            ROOT
            / "worker/qualification/patchyard-run-anthropic-issuance"
        ).read_text()
        cls.launcher = (
            ROOT / "worker/runtime/patchyard-firecracker-run"
        ).read_text()
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
        self.assertIn('remote_ssh sudo /usr/local/sbin/patchyard-firecracker-run', self.runner)
        self.assertIn('<"$RUN_TEMP/capability.json"', self.runner)
        self.assertNotIn('scp "$RUN_TEMP/assertion.jwt"', self.runner)
        self.assertIn('dd if=/dev/stdin of="$CAPABILITY"', self.launcher)
        self.assertIn('mount --bind "$RUN_TMPFS/credential.ext4"', self.launcher)
        self.assertIn('is_read_only:true', self.launcher)

    def test_guest_removes_bearer_before_writing_results(self) -> None:
        branch = self.guest.split(
            'if [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]]',
            1,
        )[1].split('\nif [[ "$MODE" == provider-qualification ]]', 1)[0]
        self.assertLess(
            branch.index('rm -f -- "$AUTH_CONFIG" "$CAPABILITY_FILE"'),
            branch.index('/result/change.patch'),
        )
        self.assertIn("touch /credential/write-probe", self.guest)
        self.assertIn("umount /credential", self.guest)
        self.assertIn("credential_removed_before_output:true", branch)

    def test_live_positive_call_is_non_generative(self) -> None:
        self.assertIn("https://api.anthropic.com/v1/models?limit=1", self.guest)
        self.assertNotIn("/v1/messages", self.guest)

    def test_provider_denial_diagnostic_is_bounded_and_credential_free(self) -> None:
        diagnostic = self.guest.split(
            "PROVIDER_CURL_EXIT=0", 1
        )[1].split("jq -e '.data | type", 1)[0]
        self.assertIn(".error.type", diagnostic)
        self.assertNotIn(".error.message", diagnostic)
        self.assertIn(
            'FAILURE="anthropic-provider-denied-$PROVIDER_STATUS-$PROVIDER_ERROR_TYPE"',
            diagnostic,
        )
        self.assertLess(
            diagnostic.index('rm -f -- "$AUTH_CONFIG" "$CAPABILITY_FILE"'),
            diagnostic.index("PROVIDER_ERROR_TYPE=$(jq -r"),
        )
        self.assertNotIn("secret", diagnostic)
        self.assertNotIn("Authorization", diagnostic)

    def test_exchange_failure_diagnostic_cannot_emit_credentials(self) -> None:
        diagnostic = self.runner.split(
            'if [[ "$EXCHANGE_STATUS" != 200 ]]', 1
        )[1].split('if [[ ! "$EXCHANGE_REQUEST_ID"', 1)[0]
        self.assertIn("anthropic_exchange_denied", diagnostic)
        self.assertIn(".error.type", diagnostic)
        self.assertNotIn(".error.message", diagnostic)
        self.assertNotIn("ASSERTION", diagnostic)
        self.assertNotIn("access_token", diagnostic)

    def test_worker_failure_diagnostic_is_allowlisted(self) -> None:
        diagnostic = self.runner.split(
            'if ! remote_ssh sudo /usr/local/sbin/patchyard-firecracker-run', 1
        )[1].split('; then\n', 1)[1].split(
            'install -d -m 0700 "$RUN_TEMP/result"', 1
        )[0]
        self.assertIn("SANITIZED_WORKER_DIAGNOSTIC", diagnostic)
        self.assertIn("grep -E", diagnostic)
        self.assertIn("result filesystem integrity check failed", diagnostic)
        self.assertIn("factory worker run failed: stage=", diagnostic)
        self.assertNotIn("launcher.stdout", diagnostic)
        self.assertNotIn("ACCESS_TOKEN", diagnostic)
        self.assertNotIn("ASSERTION", diagnostic)


if __name__ == "__main__":
    unittest.main()
