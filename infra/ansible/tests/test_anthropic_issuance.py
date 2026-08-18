import hashlib
import json
import pathlib
import shlex
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
        cls.control_qualifier = (
            ROOT
            / "infra/ansible/roles/control_plane/templates/qualify-factory-control.j2"
        ).read_text()
        cls.runner = (
            ROOT / "worker/qualification/patchyard-run-anthropic-issuance"
        ).read_text()
        cls.launcher = (ROOT / "worker/runtime/patchyard-firecracker-run").read_text()
        cls.guest = (ROOT / "worker/image/patchyard-guest-run").read_text()

    def assert_private_needle_scans(self, runner: str, launcher: str) -> None:
        runner_scan = runner.split(
            '[[ "$(find "$RUN_TEMP/result"', 1
        )[1].split("\njq -e \\", 1)[0]
        self.assertIn(
            'grep -R -F -q -f "$ACCESS_TOKEN_NEEDLE" --', runner_scan
        )
        self.assertIn(
            'grep -R -F -q -f "$RUN_TEMP/assertion.jwt" --', runner_scan
        )
        self.assertNotIn('$ACCESS_TOKEN"', runner_scan)
        self.assertNotIn('-- "$ASSERTION"', runner_scan)

        launcher_scan = launcher.split(
            "FAILURE_STAGE=result-filesystem-validation", 1
        )[1].split("FAILURE_STAGE=guest-result-status", 1)[0]
        self.assertIn(
            'grep -R -F -q -f "$CAPABILITY_NEEDLE" --', launcher_scan
        )
        self.assertNotIn("CAPABILITY_SECRET", launcher_scan)

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
        self.assertIn("anthropic-worker-ip", task)
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

    def test_residue_scans_keep_credentials_out_of_process_argv(self) -> None:
        self.assert_private_needle_scans(self.runner, self.launcher)
        self.assertIn(
            "stat -c '%U:%G:%a' \"$ACCESS_TOKEN_NEEDLE\"", self.runner
        )
        self.assertIn(
            "stat -c '%U:%G:%a' \"$RUN_TEMP/assertion.jwt\"", self.runner
        )
        self.assertIn(
            "stat -c '%U:%G:%a' \"$CAPABILITY_NEEDLE\"", self.launcher
        )
        self.assertNotIn("ACCESS_TOKEN=", self.runner)
        self.assertNotIn("CAPABILITY_SECRET", self.launcher)

    def test_argv_secret_scan_mutations_are_rejected(self) -> None:
        mutations = (
            (
                self.runner.replace(
                    '-f "$ACCESS_TOKEN_NEEDLE" --', '-- "$ACCESS_TOKEN"', 1
                ),
                self.launcher,
            ),
            (
                self.runner.replace(
                    '-f "$RUN_TEMP/assertion.jwt" --', '-- "$ASSERTION"', 1
                ),
                self.launcher,
            ),
            (
                self.runner,
                self.launcher.replace(
                    '-f "$CAPABILITY_NEEDLE" -- "$RESULT_EXTRACT"',
                    '-- "$CAPABILITY_SECRET" "$RESULT_EXTRACT"',
                    1,
                ),
            ),
        )
        for runner, launcher in mutations:
            with self.subTest():
                with self.assertRaises(AssertionError):
                    self.assert_private_needle_scans(runner, launcher)

    def test_guest_proves_the_credential_block_device_is_read_only(self) -> None:
        block_probe = self.guest.index('blockdev --getro "$CREDENTIAL_DEVICE"')
        mount = self.guest.index('mount -o ro,nosuid,nodev,noexec "$CREDENTIAL_DEVICE"')
        self.assertLess(block_probe, mount)

    def test_issuance_checker_rejects_an_extra_guest_network_client(self) -> None:
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory) / "repo"
            shutil.copytree(
                ROOT,
                root,
                # Gitignored build state (OpenTofu providers alone are ~900MB
                # after init) must stay out of the copy or the copy pays for it.
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".terraform",
                    ".venv",
                    "target",
                    "node_modules",
                    "__pycache__",
                ),
            )
            result_path = (
                root
                / "research/isolation/results/anthropic-issuance-delivery.json"
            )
            result_path.unlink()
            checker = root / "tools/check-anthropic-issuance.py"
            baseline = subprocess.run(
                [str(checker), "--allow-missing-results"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(baseline.returncode, 0, baseline.stderr)

            guest = root / "worker/image/patchyard-guest-run"
            guest.write_text(
                guest.read_text()
                + "\ncurl https://api.anthropic.com/v1/models?limit=1\n"
            )
            mutated = subprocess.run(
                [str(checker), "--allow-missing-results"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(mutated.returncode, 0)
            self.assertIn(
                "network-capable call outside exact blocks", mutated.stderr
            )

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
        self.assertIn(
            'cmp --silent -- "$RUNNER_EXECUTABLE" "$EXPECTED_RUNNER_SOURCE"',
            self.runner,
        )
        self.assertIn("LAUNCHER_HASH_RECORD=$(remote_ssh sudo sha256sum", self.runner)
        self.assertIn(
            '[[ "$LAUNCHER_SOURCE_SHA256" == "$EXPECTED_LAUNCHER_SHA256" ]]',
            self.runner,
        )
        self.assertLess(
            self.runner.index(
                '[[ "$LAUNCHER_SOURCE_SHA256" == "$EXPECTED_LAUNCHER_SHA256" ]]'
            ),
            self.runner.index("https://api.anthropic.com/v1/oauth/token"),
        )

    def test_durable_digests_are_bound_or_explicitly_observed(self) -> None:
        evidence = json.loads(
            (
                ROOT / "research/isolation/results/anthropic-issuance-delivery.json"
            ).read_text()
        )
        request = b"Anthropic issuance and delivery qualification.\n"
        patch = (
            b"diff --git a/anthropic-qualified.txt b/anthropic-qualified.txt\n"
            b"new file mode 100644\n"
            b"index 0000000000000000000000000000000000000000.."
            b"2f27dfcaa039397a95cb44d6e0fc4dcdb53e85cf\n"
            b"--- /dev/null\n"
            b"+++ b/anthropic-qualified.txt\n"
            b"@@ -0,0 +1 @@\n"
            b"+anthropic-issuance-delivery-qualified\n"
        )
        self.assertEqual(
            evidence["request_sha256"], hashlib.sha256(request).hexdigest()
        )
        self.assertEqual(evidence["patch_sha256"], hashlib.sha256(patch).hexdigest())
        self.assertEqual(
            evidence["production_parity_sha256"],
            hashlib.sha256(
                (ROOT / "worker/image/production-parity.json").read_bytes()
            ).hexdigest(),
        )
        self.assertRegex(evidence["observed_rootfs_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("rootfs_sha256", evidence)

        branch = self.guest.split(
            'if [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]]; then',
            1,
        )[1].split('\nif [[ "$MODE" == provider-qualification ]]', 1)[0]
        self.assertIn('--arg observed_rootfs_sha256 "$ROOTFS_SHA"', branch)
        self.assertNotIn('--arg rootfs_sha256 "$ROOTFS_SHA"', branch)
        self.assertIn(
            ".observed_rootfs_sha256 == $rootfs_sha256", self.launcher
        )

    def test_worker_address_is_root_only_non_executable_data(self) -> None:
        address_task = self.control_tasks.split(
            "- name: Install the Anthropic qualification worker address", 1
        )[1].split("\n- name:", 1)[0]
        runner_task = self.control_tasks.split(
            "- name: Install the Anthropic issuance-and-delivery qualification runner",
            1,
        )[1].split("\n- name:", 1)[0]
        self.assertIn("ansible.builtin.copy", address_task)
        self.assertIn("hostvars[groups['worker'][0]].private_ip", address_task)
        self.assertIn("dest: /etc/patchyard/anthropic-worker-ip", address_task)
        self.assertIn('mode: "0400"', address_task)
        self.assertIn("ansible.builtin.copy", runner_task)
        self.assertNotIn("ansible.builtin.template", runner_task)
        self.assertNotIn("{{", self.runner)
        self.assertIn(
            '[[ "$(stat -c \'%U:%G:%a\' "$WORKER_IP_FILE")" == root:root:400 ]]',
            self.runner,
        )
        self.assertIn('mapfile -t WORKER_IP_LINES <"$WORKER_IP_FILE"', self.runner)
        self.assertIn('[[ "${#WORKER_IP_LINES[@]}" -eq 1 ]]', self.runner)
        self.assertIn('WORKER_IP=${WORKER_IP_LINES[0]}', self.runner)
        self.assertIn('IPv4Network("10.0.0.0/8")', self.runner)
        self.assertIn(
            "assert_path /etc/patchyard/anthropic-worker-ip root root 400",
            self.control_qualifier,
        )
        self.assertLess(
            self.runner.index('mapfile -t WORKER_IP_LINES <"$WORKER_IP_FILE"'),
            self.runner.index("https://api.anthropic.com/v1/oauth/token"),
        )

        validator = self.runner.split(
            'python3 - "$WORKER_IP" <<\'PY\'\n', 1
        )[1].split("\nPY", 1)[0]
        valid = subprocess.run(
            ["python3", "-", "10.124.0.3"],
            input=validator,
            text=True,
            capture_output=True,
            check=False,
        )
        injected = subprocess.run(
            ["python3", "-", "$(printf reviewer-controlled)"],
            input=validator,
            text=True,
            capture_output=True,
            check=False,
        )
        public = subprocess.run(
            ["python3", "-", "8.8.8.8"],
            input=validator,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(valid.returncode, 0)
        self.assertNotEqual(injected.returncode, 0)
        self.assertNotEqual(public.returncode, 0)

    def test_guest_removes_bearer_before_writing_results(self) -> None:
        credential_start = self.guest.index(
            'if [[ "$CREDENTIAL_DELIVERED_TO_GUEST" == true ]]'
        )
        credential_unmount = self.guest.index("  umount /credential", credential_start)
        branch = self.guest.split(
            'if [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]]; then',
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
        branch = self.guest.split(
            'if [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]]; then',
            1,
        )[1].split('\nif [[ "$MODE" == provider-qualification ]]', 1)[0]
        self.assertIn("https://api.anthropic.com/v1/models?limit=1", branch)
        self.assertNotIn("/v1/messages", branch)

    def test_provider_denial_diagnostic_is_bounded_and_credential_free(self) -> None:
        issuance = self.guest.split(
            'if [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]]; then',
            1,
        )[1].split('\nif [[ "$MODE" == provider-qualification ]]', 1)[0]
        diagnostic = issuance.split("PROVIDER_CURL_EXIT=0", 1)[1].split(
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
            'if [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]]; then',
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

    def test_runner_err_trap_names_a_failed_bare_assertion(self) -> None:
        import tempfile

        original = (
            '[[ -f "$CONFIG" && ! -L "$CONFIG" && -f "$SIGNING_KEY" '
            '&& ! -L "$SIGNING_KEY" ]]'
        )
        forced = "[[ forced-bare-assertion == pass ]]"
        self.assertEqual(self.runner.count(original), 1)
        mutated = self.runner.replace(original, forced, 1)
        forced_line = mutated[: mutated.index(forced)].count("\n") + 1

        with tempfile.TemporaryDirectory() as directory:
            runner = pathlib.Path(directory) / "runner"
            runner.write_text(mutated)
            runner.chmod(0o700)
            result = subprocess.run(
                ["bash", str(runner), "jwks"],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr,
            "anthropic_qualification_runner_failed "
            f"status=1 line={forced_line} "
            "command=\\[\\[\\ forced-bare-assertion\\ ==\\ pass\\ \\]\\]\n",
        )

    def test_validation_names_clause_and_preserves_boundary_checked_evidence(
        self,
    ) -> None:
        import tempfile

        bearer_scan = self.runner.index(
            'if grep -R -F -q -f "$ACCESS_TOKEN_NEEDLE" --'
        )
        assertion_scan = self.runner.index(
            'if grep -R -F -q -f "$RUN_TEMP/assertion.jwt" --'
        )
        needle_removal = self.runner.index(
            'rm -f -- "$ACCESS_TOKEN_NEEDLE" "$RUN_TEMP/assertion.jwt"'
        )
        preservation = self.runner.index(
            "FAILED_EVIDENCE_ROOT=/run/patchyard-anthropic/failed"
        )
        self.assertLess(bearer_scan, assertion_scan)
        self.assertLess(assertion_scan, needle_removal)
        self.assertLess(needle_removal, preservation)
        self.assertIn(
            'install -d -m 0700 -o root -g root --', self.runner[preservation:]
        )
        self.assertIn(
            'install -m 0600 -o root -g root --', self.runner[preservation:]
        )

        issuance_fixture = json.loads(
            (
                ROOT / "research/isolation/results/anthropic-issuance-delivery.json"
            ).read_text()
        )
        spend_fixture = json.loads(json.dumps(issuance_fixture))
        spend_fixture["qualification_requirement"] = "provider-spend-enforcement"
        spend_fixture["qualification_phase"] = "operational_acceptance"
        spend_fixture["authorization_ruling"] = "A115"
        spend_fixture.pop("provider_call")
        spend_fixture["delivery"] = {
            "worker_host_tmpfs": True,
            "credential_delivered_to_guest": False,
            "credential_removed_before_guest_boot": True,
            "assertion_delivered": False,
            "signing_key_delivered": False,
            "admin_credential_delivered": False,
        }
        spend_fixture["provider_transport"] = {
            "schema_version": 1,
            "authorization_ruling": "A117",
            "mechanism": "host-one-shot-network-namespace-v1",
            "http_version": "1.0",
            "connection_close": True,
            "admitted_conntrack_ids": 1,
            "admitted_new_connections": 1,
            "rejected_new_connections": 0,
            "rejected_connection_packets": 0,
            "guest_provider_allowlist_entries": 0,
            "namespace_ipv6_disabled": True,
            "credential_removed_before_guest_boot": True,
            "client_sha256": "a" * 64,
        }
        spend_fixture["provider_observation"] = {
            "expected_workspace_cap_cents": 5000,
            "request_attempts": 1,
            "endpoint": "/v1/messages",
            "request_id": "req_Synthetic",
            "outcome": "accepted",
            "http_status": 200,
        }
        spend_fixture["host_teardown"] = {
            "processes": 0,
            "taps": 0,
            "nftables_tables": 0,
            "run_directories": 0,
            "credential_files": 0,
            "guest_provider_egress_packets": 0,
        }
        preamble = self.runner.split(
            "\nCONFIG=/etc/patchyard/anthropic-wif.json", 1
        )[0]
        validation = "FAILED_EVIDENCE_ROOT=" + self.runner.split(
            "FAILED_EVIDENCE_ROOT=", 1
        )[1].split("\n\nremote_ssh rm", 1)[0]

        with tempfile.TemporaryDirectory() as directory:
            temporary = pathlib.Path(directory)
            run_temp = temporary / "run"
            result_dir = run_temp / "result"
            result_dir.mkdir(parents=True)
            evidence_path = result_dir / "evidence.json"
            policy_path = temporary / "anthropic-wif.json"
            policy_path.write_text(
                json.dumps({"spend_enforcement": {"authorization_ruling": "A115"}})
                + "\n"
            )
            failed_root = temporary / "failed"
            validation = validation.replace(
                "FAILED_EVIDENCE_ROOT=/run/patchyard-anthropic/failed",
                f"FAILED_EVIDENCE_ROOT={shlex.quote(str(failed_root))}",
                1,
            ).replace(" -o root -g root", "", 2)
            harness = temporary / "validation-harness"

            def run_validation(
                evidence: dict[str, object], spend_cap_cents: int
            ) -> subprocess.CompletedProcess[str]:
                evidence_path.write_text(json.dumps(evidence) + "\n")
                assignments = {
                    "CONFIG": policy_path,
                    "RUN_TEMP": run_temp,
                    "RUN_ID": evidence["run_id"],
                    "ISSUED_AT": evidence["issuance"]["issued_at"],
                    "EXPIRES_AT": evidence["issuance"]["expires_at"],
                    "EXCHANGE_REQUEST_ID": evidence["issuance"][
                        "exchange_request_id"
                    ],
                    "HOST_CONTRACT_SHA256": evidence["host_contract_sha256"],
                    "QUALIFICATION_REQUIREMENT": evidence[
                        "qualification_requirement"
                    ],
                    "QUALIFICATION_PHASE": evidence["qualification_phase"],
                    "SPEND_CAP_CENTS": spend_cap_cents,
                }
                harness.write_text(
                    preamble
                    + "\n"
                    + "\n".join(
                        f"{name}={shlex.quote(str(value))}"
                        for name, value in assignments.items()
                    )
                    + "\n"
                    + validation
                    + "\n"
                )
                harness.chmod(0o700)
                return subprocess.run(
                    ["bash", str(harness)],
                    check=False,
                    capture_output=True,
                    text=True,
                )

            passing = run_validation(issuance_fixture, 0)
            self.assertEqual(passing.returncode, 0, passing.stderr)
            self.assertEqual(passing.stdout, "")
            self.assertEqual(passing.stderr, "")
            self.assertFalse(failed_root.exists())

            spend_passing = run_validation(spend_fixture, 5000)
            self.assertEqual(spend_passing.returncode, 0, spend_passing.stderr)
            self.assertEqual(spend_passing.stdout, "")
            self.assertEqual(spend_passing.stderr, "")
            self.assertFalse(failed_root.exists())

            spend_with_capability_flags = json.loads(json.dumps(spend_fixture))
            spend_with_capability_flags["delivery"].update(
                {
                    "capability_drive_read_only": True,
                    "capability_drive_unmounted_before_provider_call": True,
                    "credential_removed_before_output": True,
                }
            )
            rejected = run_validation(spend_with_capability_flags, 5000)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(
                rejected.stderr.splitlines()[0],
                "anthropic_evidence_validation_failed "
                "clause=delivery.spend_contract jq_status=1",
            )

            without_capability_flags = json.loads(json.dumps(issuance_fixture))
            for field in (
                "capability_drive_read_only",
                "capability_drive_unmounted_before_provider_call",
                "credential_removed_before_output",
            ):
                without_capability_flags["delivery"].pop(field)
            rejected = run_validation(without_capability_flags, 0)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(
                rejected.stderr.splitlines()[0],
                "anthropic_evidence_validation_failed "
                "clause=delivery.capability_drive_read_only jq_status=1",
            )

            for field in (
                "capability_drive_read_only",
                "capability_drive_unmounted_before_provider_call",
                "credential_removed_before_output",
            ):
                with self.subTest(missing_issuance_delivery_field=field):
                    mutated = json.loads(json.dumps(issuance_fixture))
                    mutated["delivery"].pop(field)
                    rejected = run_validation(mutated, 0)
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertEqual(
                        rejected.stderr.splitlines()[0],
                        "anthropic_evidence_validation_failed "
                        f"clause=delivery.{field} jq_status=1",
                    )

            endpoint_mutation = json.loads(json.dumps(issuance_fixture))
            endpoint_mutation["provider_call"]["endpoint"] = "/v1/messages"
            mutated_bytes = (json.dumps(endpoint_mutation) + "\n").encode()
            failing = run_validation(endpoint_mutation, 0)
            preserved = failed_root / issuance_fixture["run_id"] / "evidence.json"

            self.assertNotEqual(failing.returncode, 0)
            self.assertEqual(failing.stdout, "")
            diagnostics = failing.stderr.splitlines()
            self.assertEqual(
                diagnostics[0],
                "anthropic_evidence_validation_failed "
                "clause=provider_call.endpoint jq_status=1",
            )
            self.assertEqual(
                diagnostics[1], f"anthropic_evidence_preserved path={preserved}"
            )
            self.assertRegex(
                diagnostics[2],
                r"^anthropic_qualification_runner_failed status=1 line=[0-9]+ "
                r"command=return\\ \\\"\\\$jq_status\\\"$",
            )
            self.assertEqual(preserved.read_bytes(), mutated_bytes)
            self.assertEqual(failed_root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(preserved.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(preserved.stat().st_mode & 0o777, 0o600)

    def test_existing_output_directory_precondition_is_named(self) -> None:
        import tempfile

        block = self.runner.split('if [[ -e "$OUTPUT_DIR" ]]; then', 1)[1].split(
            "\nfi", 1
        )[0]
        self.assertIn("anthropic_qualification_output_directory_exists", block)
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "already-there"
            output.mkdir()
            probe = subprocess.run(
                [
                    "bash",
                    "-c",
                    "set -euo pipefail\n"
                    f"OUTPUT_DIR={shlex.quote(str(output))}\n"
                    'if [[ -e "$OUTPUT_DIR" ]]; then\n'
                    + block
                    + "\nfi\n",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(probe.returncode, 1)
        self.assertEqual(probe.stdout, "")
        self.assertEqual(
            probe.stderr,
            f"anthropic_qualification_output_directory_exists path={output}\n",
        )


if __name__ == "__main__":
    unittest.main()
