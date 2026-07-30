from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib.util
import json
import pathlib
import re
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "tools/anthropic-spend-evidence.py"
SPEC = importlib.util.spec_from_file_location("anthropic_spend_evidence", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class AnthropicSpendEvidenceContract(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = {
            "organization": {"id": "org"},
            "workspace": {"id": "workspace"},
            "service_account": {"id": "service"},
            "rule": {"id": "rule"},
            "spend_enforcement": {
                "model": "claude-opus-5",
                "operational_cap_cents": 5000,
                "qualification_cap_cents": 100,
                "organization_monthly_limit_cents": 50000,
                "minimum_settlement_window_seconds": 10260,
            },
        }
        self.start = datetime(2026, 7, 30, tzinfo=timezone.utc)
        self.operational = self.worker("operational_acceptance", 2, "accepted")
        self.refusal = self.worker("temporary_refusal", 183, "refused")
        self.restored = self.worker("restored_acceptance", 361, "accepted")
        self.before = self.snapshot(180, "7.68168")
        self.after = self.snapshot(360, "7.70234")
        self.caps = {
            "schema_version": 2,
            "provider": "anthropic",
            "organization_id": "org",
            "workspace_id": "workspace",
            "operational_acceptance": self.cap(0, "50.00"),
            "temporary_refusal": self.cap(181, "1.00"),
            "restored_acceptance": self.cap(184, "50.00"),
        }

    def timestamp(self, minute: int, second: int = 0) -> str:
        return iso(self.start + timedelta(minutes=minute, seconds=second))

    def snapshot(self, minute: int, amount: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "provider": "anthropic",
            "workspace_id": "workspace",
            "captured_at": self.timestamp(minute),
            "reporting_window": {
                "starting_at": self.timestamp(0),
                "ending_at": self.timestamp(minute, 30),
            },
            "currency": "USD",
            "cost_usd": amount,
        }

    def cap(self, minute: int, workspace_limit: str) -> dict[str, str]:
        return {
            "captured_before_at": self.timestamp(minute),
            "captured_after_at": self.timestamp(minute, 30),
            "workspace_monthly_limit_usd": workspace_limit,
            "organization_monthly_limit_usd": "500.00",
            "capture_method": "operator_console_readback_bounded_by_control_plane_utc",
        }

    def worker(self, phase: str, minute: int, outcome: str) -> dict[str, object]:
        issued = self.start + timedelta(minutes=minute - 1)
        observed = self.start + timedelta(minutes=minute)
        digest = "a" * 64
        observation: dict[str, object] = {
            "outcome": outcome,
            "endpoint": "/v1/messages",
            "http_status": 200 if outcome == "accepted" else 400,
            "observed_at": iso(observed),
            "request_id": f"req_{phase.replace('_', '')}",
            "request_body_sha256": "b" * 64,
            "response_type": "message" if outcome == "accepted" else "error",
            "request_attempts": 1,
            "expected_workspace_cap_cents": 100 if outcome == "refused" else 5000,
        }
        if outcome == "accepted":
            observation.update(
                {
                    "model": "claude-opus-5",
                    "usage": {"input_tokens": 18, "output_tokens": 1},
                }
            )
        else:
            observation["provider_error"] = {
                "error_type": "invalid_request_error",
                "message_class": "unattributed",
                "message_sha256": "c" * 64,
                "shape": {
                    "top_level_keys": ["error", "request_id", "type", "extra"],
                    "error_keys": ["message", "type", "extra"],
                },
            }
        return {
            "schema_version": 1,
            "run_id": f"anthropic-s2-{phase}",
            "base_sha": "d" * 40,
            "request_sha256": digest,
            "provider": "anthropic",
            "qualification_requirement": "provider-spend-enforcement",
            "authorization_ruling": "A115",
            "qualification_phase": phase,
            "patch_sha256": digest,
            "observed_rootfs_sha256": digest,
            "image_recipe_sha256": digest,
            "production_parity_sha256": digest,
            "git_remote_count": 0,
            "host_contract_sha256": digest,
            "credential_removed_before_output": True,
            "issuance": {
                "issued_at": iso(issued),
                "expires_at": iso(issued + timedelta(seconds=300)),
                "expires_in": 300,
                "exchange_request_id": f"req_exchange{phase.replace('_', '')}",
                "token_type": "Bearer",
                "scope": "workspace:inference",
                "service_account_id": "service",
                "rule_id": "rule",
                "workspace_id": "workspace",
            },
            "delivery": deepcopy(EVIDENCE.DELIVERY),
            "provider_transport": {
                "schema_version": 1,
                "authorization_ruling": "A117",
                "mechanism": "host-one-shot-network-namespace-v1",
                "http_version": "1.0",
                "connection_close": True,
                "client_sha256": digest,
                "admitted_conntrack_ids": 1,
                "admitted_new_connections": 1,
                "rejected_new_connections": 0,
                "rejected_connection_packets": 0,
                "guest_provider_allowlist_entries": 0,
                "namespace_ipv6_disabled": True,
                "credential_removed_before_guest_boot": True,
            },
            "provider_observation": observation,
            "host_teardown": deepcopy(EVIDENCE.TEARDOWN),
        }

    def finalize(self) -> dict[str, object]:
        return EVIDENCE.finalize(
            self.operational,
            self.refusal,
            self.restored,
            self.before,
            self.after,
            self.caps,
            self.policy,
        )

    def test_finalizer_separates_preexisting_excess_from_incremental_spend(
        self,
    ) -> None:
        measurement = self.finalize()["cost_measurement"]
        self.assertEqual(measurement["preexisting_excess_at_activation_usd"], "6.68168")
        self.assertEqual(measurement["incremental_spend_before_refusal_usd"], "0.02066")
        self.assertNotIn("ceiling", measurement)

    def test_cost_report_minor_units_are_converted_to_usd(self) -> None:
        self.assertEqual(
            EVIDENCE.minor_units_to_usd(Decimal("768.168")), Decimal("7.68168")
        )

    def test_finalizer_allows_observed_zero_incremental_spend_after_settlement(
        self,
    ) -> None:
        self.after["cost_usd"] = self.before["cost_usd"]
        measurement = self.finalize()["cost_measurement"]
        self.assertEqual(measurement["incremental_spend_before_refusal_usd"], "0.00000")

    def test_finalizer_rejects_baseline_not_above_temporary_cap(self) -> None:
        self.before["cost_usd"] = "0.99"
        with self.assertRaisesRegex(ValueError, "not lowered below"):
            self.finalize()

    def test_finalizer_rejects_incomplete_settlement_window(self) -> None:
        self.after["captured_at"] = self.timestamp(300)
        with self.assertRaisesRegex(ValueError, "settlement window"):
            self.finalize()

    def test_finalizer_rejects_changed_organization_limit(self) -> None:
        self.caps["restored_acceptance"]["organization_monthly_limit_usd"] = "499.00"
        with self.assertRaisesRegex(ValueError, "reviewed .500.00 binding"):
            self.finalize()

    def test_finalizer_rejects_failure_to_restore_operational_cap(self) -> None:
        self.caps["restored_acceptance"]["workspace_monthly_limit_usd"] = "1.00"
        with self.assertRaisesRegex(ValueError, "restored_acceptance workspace cap"):
            self.finalize()

    def test_finalizer_rejects_changed_request_body(self) -> None:
        self.refusal["provider_observation"]["request_body_sha256"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "not byte-identical"):
            self.finalize()

    def test_finalizer_accepts_bounded_extra_provider_error_fields(self) -> None:
        result = self.finalize()
        shape = result["phases"]["temporary_refusal"]["provider_observation"][
            "provider_error"
        ]["shape"]
        self.assertIn("extra", shape["top_level_keys"])

    def test_finalizer_rejects_rate_limit_refusal(self) -> None:
        self.refusal["provider_observation"]["provider_error"][
            "error_type"
        ] = "rate_limit_error"
        with self.assertRaisesRegex(ValueError, "safely diagnostic"):
            self.finalize()

    def test_finalizer_rejects_unbounded_cap_timestamp(self) -> None:
        self.caps["temporary_refusal"]["captured_after_at"] = self.timestamp(190)
        with self.assertRaisesRegex(ValueError, "tightly time-bounded"):
            self.finalize()

    def test_finalizer_rejects_duplicate_wif_exchange(self) -> None:
        self.refusal["issuance"]["exchange_request_id"] = self.operational["issuance"][
            "exchange_request_id"
        ]
        with self.assertRaisesRegex(ValueError, "distinct WIF exchanges"):
            self.finalize()

    def test_finalizer_rejects_pre_activation_under_settlement_floor(self) -> None:
        self.before["captured_at"] = self.timestamp(100)
        self.caps["temporary_refusal"] = self.cap(101, "1.00")
        self.refusal = self.worker("temporary_refusal", 103, "refused")
        with self.assertRaisesRegex(ValueError, "pre-activation cost"):
            self.finalize()

    def test_finalizer_rejects_month_boundary(self) -> None:
        self.start = datetime(2026, 7, 31, 21, tzinfo=timezone.utc)
        self.operational = self.worker("operational_acceptance", 2, "accepted")
        self.before = self.snapshot(180, "7.68168")
        self.caps["operational_acceptance"] = self.cap(0, "50.00")
        self.caps["temporary_refusal"] = self.cap(181, "1.00")
        self.refusal = self.worker("temporary_refusal", 183, "refused")
        self.caps["restored_acceptance"] = self.cap(184, "50.00")
        self.after = self.snapshot(360, "7.70234")
        self.restored = self.worker("restored_acceptance", 361, "accepted")
        with self.assertRaisesRegex(ValueError, "monthly billing boundary"):
            self.finalize()

    def test_post_refusal_spend_has_no_fifty_dollar_ceiling(self) -> None:
        self.after["cost_usd"] = "55.00"
        measurement = self.finalize()["cost_measurement"]
        self.assertEqual(
            measurement["incremental_spend_before_refusal_usd"], "47.31832"
        )


class AnthropicA117TransportContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.transport = (
            ROOT / "worker/runtime/patchyard-anthropic-one-shot"
        ).read_text()
        cls.launcher = (
            ROOT / "worker/runtime/patchyard-firecracker-run"
        ).read_text()
        cls.guest = (ROOT / "worker/image/patchyard-guest-run").read_text()
        cls.checker = (ROOT / "tools/check-anthropic-spend.py").read_text()
        cls.worker_tasks = (
            ROOT / "infra/ansible/roles/worker/tasks/main.yml"
        ).read_text()

    @classmethod
    def function(cls, name: str) -> str:
        body = cls.transport.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]
        return f"{name}() {{{body}\n}}"

    def run_raw_envelope(
        self, value: str, action: str
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as handle:
            handle.write(value)
            handle.flush()
            script = "\n".join(
                (
                    "set -euo pipefail",
                    self.function("anthropic_response_is_single_json_object"),
                    self.function("classify_anthropic_error_shape"),
                    self.function("anthropic_error_envelope_is_compatible"),
                    'PROVIDER_RESPONSE="$1"',
                    action,
                )
            )
            return subprocess.run(
                ["bash", "-c", script, "bash", handle.name],
                check=False,
                capture_output=True,
                text=True,
            )

    @staticmethod
    def envelope(**extra: object) -> dict[str, object]:
        value: dict[str, object] = {
            "type": "error",
            "error": {"type": "invalid_request_error", "message": "denied"},
            "request_id": "req_abc123",
        }
        value.update(extra)
        return value

    def test_transport_predicates_reject_non_single_object_responses(self) -> None:
        for value, descriptor in (
            ("", "empty-body"),
            (" \n\t", "invalid-json-body"),
            ("{", "invalid-json-body"),
            ("{}\n{}", "invalid-json-body"),
            ("[]", "non-object"),
        ):
            with self.subTest(descriptor=descriptor):
                compatible = self.run_raw_envelope(
                    value, "anthropic_error_envelope_is_compatible"
                )
                self.assertNotEqual(compatible.returncode, 0)
                classified = self.run_raw_envelope(
                    value, "classify_anthropic_error_shape"
                )
                self.assertEqual(classified.returncode, 0, classified.stderr)
                self.assertEqual(classified.stdout.strip(), descriptor)

    def test_transport_accepts_bounded_error_extras(self) -> None:
        result = self.run_raw_envelope(
            json.dumps(self.envelope(extra={"compatible": True})),
            "anthropic_error_envelope_is_compatible",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_one_shot_client_is_fixed_to_one_closed_http10_transfer(self) -> None:
        request = self.transport.split(
            "PROVIDER_STATUS=$(\n", 1
        )[1].split("\n) || PROVIDER_CURL_EXIT=$?", 1)[0]
        self.assertEqual(request.count("/usr/bin/curl"), 1)
        self.assertEqual(
            request.count("'https://api.anthropic.com/v1/messages'"), 1
        )
        for required in (
            "/usr/bin/curl -q",
            "/usr/bin/env -i HOME=/var/lib/patchyard-worker PATH=/usr/bin:/bin",
            "--http1.0",
            "--header 'Connection: close'",
            "--ipv4",
            "--proto '=https'",
            "--data-binary",
        ):
            self.assertIn(required, request)
        for forbidden in ("--retry", "--location", "--next", "--parallel"):
            self.assertNotIn(forbidden, request)
        for forbidden in ("--http0.9", "--http1.1", "--http2", "--http3"):
            self.assertNotIn(forbidden, request)
        self.assertIn("EXPECTED_AUTH_CONFIG_BLOCK", self.checker)
        self.assertIn("header-only generator", self.checker)

    def test_spend_guest_has_neither_credential_nor_provider_route(self) -> None:
        self.assertNotIn(
            "https://api.anthropic.com/v1/messages", self.guest
        )
        self.assertNotIn("A115_PROVIDER_REQUEST", self.guest)
        self.assertIn('CREDENTIAL_DELIVERED_TO_GUEST=false', self.guest)
        self.assertIn('provider-spend-enforcement', self.guest)
        self.assertIn('[[ ! -s /input/provider-hosts ]]', self.guest)
        self.assertIn('[[ ! -e /dev/disk/by-label/ETA_CREDENTIAL ]]', self.guest)

    def test_launcher_enforces_and_reads_one_conntrack_id(self) -> None:
        for required in (
            "ct id @admitted counter accept",
            "ip saddr @used add @rejected { ct id } counter name rejected_new reject",
            "add @admitted '{' ct id '}'",
            "add @used '{' ip saddr '}' counter name admitted_new accept",
            "PROVIDER_ADMITTED_NEW=$(provider_counter_packets admitted_new)",
            "PROVIDER_REJECTED_NEW=$(provider_counter_packets rejected_new)",
            '[[ "$PROVIDER_ADMITTED_NEW" -eq 1',
            '&& "$PROVIDER_REJECTED_NEW" -eq 0',
            '&& "$PROVIDER_ADMITTED_IDS" -eq 1',
            '&& "$PROVIDER_REJECTED_IDS" -eq 0',
            '&& "$PROVIDER_USED_SOURCES" -eq 1 ]]',
            "net.ipv6.conf.all.disable_ipv6=1",
            "net.ipv6.conf.default.disable_ipv6=1",
            "assert_provider_transport_preflight",
            "anthropic-spend-transport-cardinality-rejected-%s-%s-%s-%s-%s",
            'if [[ "$ipv6_all" != 1 || "$ipv6_default" != 1 || "$ipv6_eth0" != 1 ]]; then',
        ):
            self.assertIn(required, self.launcher)
        self.assertEqual(
            self.launcher.count(
                '"$ANTHROPIC_ONE_SHOT" "$PROVIDER_NETNS" "$CAPABILITY" "$PROVIDER_STAGE"'
            ),
            1,
        )
        self.assertLess(
            self.launcher.index("net.ipv6.conf.all.disable_ipv6=1"),
            self.launcher.index('ip link add "$PROVIDER_HOST_VETH"'),
        )
        self.assertLess(
            self.launcher.index("  assert_provider_transport_preflight\n"),
            self.launcher.index(
                '  "$ANTHROPIC_ONE_SHOT" "$PROVIDER_NETNS" "$CAPABILITY"'
            ),
        )
        self.assertIn(
            "transport-cardinality-rejected-([0-9]{1,20}-){4}[0-9]{1,20}",
            (
                ROOT
                / "worker/qualification/patchyard-run-anthropic-issuance"
            ).read_text(),
        )
        self.assertIn(
            "efh[0-9a-f]{8}[@:]",
            (
                ROOT
                / "worker/qualification/patchyard-run-anthropic-issuance"
            ).read_text(),
        )
        self.assertIn(
            "EXPECTED_PROVIDER_TRANSPORT_CONTROL_SHA256",
            self.checker,
        )
        self.assertIn(
            "EXPECTED_IPV6_PREFLIGHT_COMPARISON",
            self.checker,
        )

    def test_missing_request_id_retains_status_and_shape(self) -> None:
        response = self.transport.split(
            "PROVIDER_REQUEST_ID=$(awk", 1
        )[1].split("PROVIDER_SERVER_DATE=$(awk", 1)[0]
        self.assertIn('if [[ ! "$PROVIDER_REQUEST_ID" =~', response)
        self.assertIn("RESPONSE_SHAPE=$(classify_anthropic_error_shape)", response)
        self.assertIn(
            "anthropic-spend-provider-response-rejected-%s-missing-request-id-%s",
            response,
        )

    def test_missing_request_id_paths_are_bounded_after_completed_call(self) -> None:
        for status, body, shape in (
            ("403", "<html>denied</html>", "invalid-json-body"),
            ("400", "", "empty-body"),
            ("200", '{"type":"message"}', "type-not-error"),
        ):
            with self.subTest(status=status, shape=shape):
                with tempfile.TemporaryDirectory() as directory:
                    root = pathlib.Path(directory)
                    headers = root / "headers"
                    response = root / "response"
                    headers.write_text("date: Thu, 30 Jul 2026 00:00:00 GMT\r\n")
                    response.write_text(body)
                    script = "\n".join(
                        (
                            "set -euo pipefail",
                            self.function("anthropic_response_is_single_json_object"),
                            self.function("classify_anthropic_error_shape"),
                            self.function("read_provider_request_id"),
                            'PROVIDER_HEADERS="$1"',
                            'PROVIDER_RESPONSE="$2"',
                            'PROVIDER_STATUS="$3"',
                            "read_provider_request_id",
                        )
                    )
                    result = subprocess.run(
                        [
                            "bash",
                            "-c",
                            script,
                            "bash",
                            str(headers),
                            str(response),
                            status,
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(
                        f"response-rejected-{status}-missing-request-id-{shape}",
                        result.stderr,
                    )

    def test_complete_installed_transport_is_host_bound(self) -> None:
        self.assertIn(
            "worker/runtime/patchyard-anthropic-one-shot", self.worker_tasks
        )
        self.assertNotIn(
            "patchyard-anthropic-one-shot",
            (ROOT / "worker/image/build-parity-image").read_text(),
        )
        self.assertIn(
            "TRANSPORT_SOURCE_SHA256", (
                ROOT
                / "worker/qualification/patchyard-run-anthropic-issuance"
            ).read_text()
        )
        self.assertIn("TRANSPORT_PATH", self.checker)

    def run_checker_mutation(
        self, relative: str, before: str, after: str
    ) -> subprocess.CompletedProcess[str]:
        import shutil

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory) / "repo"
            shutil.copytree(
                ROOT,
                root,
                ignore=shutil.ignore_patterns(".git", "target", "node_modules"),
            )
            path = root / relative
            source = path.read_text()
            self.assertIn(before, source)
            path.write_text(source.replace(before, after, 1))
            return subprocess.run(
                [str(root / "tools/check-anthropic-spend.py")],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_checker_behaviorally_rejects_structural_weakening(self) -> None:
        mutations = (
            (
                "worker/runtime/patchyard-anthropic-one-shot",
                "--http1.0 --header",
                "--http1.0 --http2 --header",
            ),
            (
                "worker/runtime/patchyard-anthropic-one-shot",
                "  printf 'header = \"content-type: application/json\"\\n'",
                "  printf 'header = \"content-type: application/json\"\\n'\n"
                "  printf 'next\\n'",
            ),
            (
                "worker/runtime/patchyard-anthropic-one-shot",
                "'https://api.anthropic.com/v1/messages'",
                "'https://api.anthropic.com/v1/messages' "
                "'https://api.anthropic.com/v1/messages'",
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                '"$PROVIDER_ADMITTED_NEW" -eq 1',
                '"$PROVIDER_ADMITTED_NEW" -ge 1',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                'ip daddr "$PROVIDER_TRANSPORT_IP" \\\n    tcp dport 443 ct state new add @admitted',
                'ip daddr 0.0.0.0/0 \\\n    tcp dport 443 ct state new add @admitted',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                "'add rule inet eta_anthropic_one_shot output "
                "counter name rejected_new reject'",
                "'add rule inet eta_anthropic_one_shot output "
                "counter name rejected_new accept'",
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                "net.ipv6.conf.all.disable_ipv6=1",
                "net.ipv6.conf.all.disable_ipv6=0",
            ),
            (
                "worker/qualification/patchyard-run-anthropic-issuance",
                "efh[0-9a-f]{8}[@:]",
                "efh[0-9a-f]{8}:",
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                "anthropic-spend-transport-cardinality-rejected-%s-%s-%s-%s-%s",
                "anthropic-spend-transport-cardinality-rejected",
            ),
            (
                "worker/image/patchyard-guest-run",
                '[[ ! -s /input/provider-hosts ]]',
                'curl https://api.anthropic.com/v1/messages\n'
                '  [[ ! -s /input/provider-hosts ]]',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                "  ip netns exec \"$PROVIDER_NETNS\" nft \\\n"
                "    'add rule inet eta_anthropic_one_shot output "
                "counter name rejected_new reject'\n"
                "}",
                "  ip netns exec \"$PROVIDER_NETNS\" nft \\\n"
                "    'add rule inet eta_anthropic_one_shot output "
                "counter name rejected_new reject'\n"
                "  ip netns exec \"$PROVIDER_NETNS\" nft insert rule inet "
                "eta_anthropic_one_shot output ct state new "
                "add @admitted '{' ct id '}' add @used '{' ip saddr '}' "
                "counter name admitted_new accept\n"
                "}",
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                'iifname "$PROVIDER_HOST_VETH" '
                'ip daddr "$PROVIDER_TRANSPORT_IP"',
                'iifname "$PROVIDER_HOST_VETH" ip daddr 0.0.0.0/0',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                'iifname "$PROVIDER_HOST_VETH" counter reject',
                'iifname "$PROVIDER_HOST_VETH" counter accept',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                'if [[ "$ipv6_all" != 1 || "$ipv6_default" != 1 || '
                '"$ipv6_eth0" != 1 ]]; then',
                'if [[ "$ipv6_all" != 1 && "$ipv6_default" != 1 && '
                '"$ipv6_eth0" != 9 ]]; then',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                '  if [[ "$ipv6_all" != 1 || "$ipv6_default" != 1 ||',
                '  return 0\n'
                '  if [[ "$ipv6_all" != 1 || "$ipv6_default" != 1 ||',
            ),
        )
        for relative, before, after in mutations:
            with self.subTest(relative=relative, before=before):
                result = self.run_checker_mutation(relative, before, after)
                self.assertNotEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
