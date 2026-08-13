from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
import pathlib
import re
import subprocess
import tempfile
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
EXPECTED_LAUNCHER_SOURCE_SHA256 = (
    "60b71fb24ce3c47b9b62bdece7166dd0c622a1830fb21d673db8830acf133e3f"
)
EXPECTED_RUNNER_SOURCE_SHA256 = (
    "91c3fdc09b34d009a02e4f8d1290976c558b0a654e89171dcaa5b3fd037a7608"
)
EXPECTED_GUEST_SOURCE_SHA256 = (
    "229346fb350297b298c1b752188c0f7762ef9d5de77572156843070fecfcc654"
)
EXPECTED_WORKER_TASKS_SOURCE_SHA256 = (
    "cef308d16aab9d414595bb043de8424cb3ded490e0fa63d3b3bc3ee67e67a722"
)
EXPECTED_CHECKER_SOURCE_SHA256 = (
    "e8cc3eaec36dd12a345e92fb0c1579af3ff91e786572780424c50b0f700aba2b"
)
EXPECTED_READINESS_HELPER_SOURCE_SHA256 = (
    "5aa2f71ce014671de08104356d77a5ff210efd56525e7c1ddf85f46770336cba"
)
EXPECTED_REPLACEMENT_OPERATOR_SOURCE_SHA256 = (
    "27f322afc3c3c8d813f18a5003f2e2fdc2c6d75d24b28ed0c19ad215e9ad580e"
)
EXPECTED_ANSIBLE_WRAPPER_SOURCE_SHA256 = (
    "aa1dba9871d2e26c47046be06f2762144c87b193a7dd0c75dce5ffebfd15dbf2"
)
EXPECTED_READINESS_TEST_SOURCE_SHA256 = (
    "512afe3563cb41bd83cdc4ea9c25e2306c1c36d98227659f313da4c68e921b07"
)
MODULE_PATH = ROOT / "tools/anthropic-spend-evidence.py"
EXPECTED_EVIDENCE_SOURCE_SHA256 = (
    "494cba4a628e592004dc975ead283aa32fe1fbfe6236c6d6a4a7c7d7ee733099"
)
A120_CALIBRATION_ITEMS = 16_000
A120_CALIBRATION_COPIES = 2
A120_MINIMUM_UNCACHED_INPUT_TOKENS = 300_000
A120_PROMPT_SHA256 = "9a7a2d6d96cb17ddb78331fcc2a9ee5475310a65e9dc906c2db1548ac1154c21"
A120_BODY_SHA256 = "b3751a164cde71cbca2fe5de05d3fc8a836649e46114c616cdaf4a210bdfccf4"


def load_exact_source_module(name: str, path: pathlib.Path, expected: str) -> types.ModuleType:
    source = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(source).hexdigest() != expected:
        raise RuntimeError(f"{path.name} differs from its exact source binding")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = None
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


EVIDENCE = load_exact_source_module(
    "anthropic_spend_evidence", MODULE_PATH, EXPECTED_EVIDENCE_SOURCE_SHA256
)


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
        self.start = datetime(2026, 8, 2, 14, 51, tzinfo=timezone.utc)
        self.operational = self.worker("operational_acceptance", 2, "accepted")
        self.refusal = self.worker("temporary_refusal", 563, "refused")
        self.restored = self.worker("restored_acceptance", 2001, "accepted")
        self.before = self.snapshot(560, "3.84074", 2)
        self.after = self.snapshot(2000, "3.86140", 2, 563)
        self.caps = {
            "schema_version": 2,
            "provider": "anthropic",
            "organization_id": "org",
            "workspace_id": "workspace",
            "operational_acceptance": self.cap(0, "50.00"),
            "temporary_refusal": self.cap(561, "1.00"),
            "restored_acceptance": self.cap(564, "50.00"),
        }

    def timestamp(self, minute: int, second: int = 0) -> str:
        return iso(self.start + timedelta(minutes=minute, seconds=second))

    def snapshot(
        self,
        minute: int,
        amount: str,
        *workspace_minutes: int,
        legacy: bool = False,
        schema_version: int = 3,
    ) -> dict[str, object]:
        if legacy:
            schema_version = 1
        captured = self.start + timedelta(minutes=minute)
        window_start = self.start.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        window_end = captured + timedelta(seconds=30)
        snapshot: dict[str, object] = {
            "schema_version": schema_version,
            "provider": "anthropic",
            "workspace_id": "workspace",
            "captured_at": iso(captured),
            "reporting_window": {
                "starting_at": iso(window_start),
                "ending_at": iso(window_end),
            },
            "currency": "USD",
            "cost_usd": amount,
        }
        if schema_version >= 2:
            snapshot["workspace_cost_utc_days"] = sorted(
                {
                    (self.start + timedelta(minutes=workspace_minute))
                    .date()
                    .isoformat()
                    for workspace_minute in workspace_minutes
                }
            )
        if schema_version >= 3:
            snapshot["complete_utc_days"] = EVIDENCE.completely_covered_utc_days(
                window_start, window_end, captured
            )
        return snapshot

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
                    "usage": {"input_tokens": 300000, "output_tokens": 1},
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
        self.assertEqual(measurement["preexisting_excess_at_activation_usd"], "2.84074")
        self.assertEqual(measurement["incremental_spend_before_refusal_usd"], "0.02066")
        self.assertEqual(
            measurement["pre_activation_workspace_cost_utc_day"], "2026-08-02"
        )
        self.assertEqual(
            measurement["post_refusal_workspace_cost_utc_day"], "2026-08-03"
        )
        self.assertNotIn("ceiling", measurement)

    def test_cost_report_minor_units_are_converted_to_usd(self) -> None:
        self.assertEqual(
            EVIDENCE.minor_units_to_usd(Decimal("768.168")), Decimal("7.68168")
        )

    def test_complete_utc_days_require_full_window_and_closed_day(self) -> None:
        complete = EVIDENCE.completely_covered_utc_days(
            datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
            datetime(2026, 8, 4, 0, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 4, 0, 0, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(complete, ["2026-08-02", "2026-08-03"])
        ends_early = EVIDENCE.completely_covered_utc_days(
            datetime(2026, 8, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 3, 23, 59, 59, tzinfo=timezone.utc),
            datetime(2026, 8, 4, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(ends_early, ["2026-08-01", "2026-08-02"])

    def test_snapshot_rejects_claimed_complete_day_outside_full_window(self) -> None:
        self.after["complete_utc_days"].append("2026-08-04")
        with self.assertRaisesRegex(ValueError, "differ from its closed reporting window"):
            self.finalize()

    def test_snapshot_rejects_absent_workspace_cost_row(self) -> None:
        payload = {
            "data": [
                {
                    "starting_at": "2026-08-01T00:00:00Z",
                    "ending_at": "2026-08-02T00:00:00Z",
                    "results": [
                        {"workspace_id": None, "currency": "USD", "amount": "12.3"}
                    ]
                }
            ],
            "has_more": False,
            "next_page": None,
        }
        original_token = EVIDENCE.admin_token
        original_open = EVIDENCE.urllib.request.urlopen
        try:
            EVIDENCE.admin_token = lambda _profile: "test-token"
            EVIDENCE.urllib.request.urlopen = lambda *_args, **_kwargs: io.StringIO(
                json.dumps(payload)
            )
            with self.assertRaisesRegex(ValueError, "no Factory workspace row"):
                EVIDENCE.fetch_workspace_cost("test-profile", "workspace")
        finally:
            EVIDENCE.admin_token = original_token
            EVIDENCE.urllib.request.urlopen = original_open

    def test_snapshot_exhausts_default_sized_pages_before_deciding_no_row(
        self,
    ) -> None:
        first_page = {
            "data": [
                {
                    "starting_at": iso(
                        datetime(2026, 7, 25, tzinfo=timezone.utc)
                        + timedelta(days=offset)
                    ),
                    "ending_at": iso(
                        datetime(2026, 7, 26, tzinfo=timezone.utc)
                        + timedelta(days=offset)
                    ),
                    "results": [
                        {
                            "workspace_id": "another-workspace",
                            "currency": "USD",
                            "amount": "1",
                        }
                    ],
                }
                for offset in range(7)
            ],
            "has_more": True,
            "next_page": "after-default-seven",
        }
        second_page = {
            "data": [
                {
                    "starting_at": "2026-08-02T00:00:00Z",
                    "ending_at": "2026-08-03T00:00:00Z",
                    "results": [
                        {
                            "workspace_id": "workspace",
                            "currency": "USD",
                            "amount": "384.074",
                        }
                    ],
                },
                {
                    "starting_at": "2026-08-03T00:00:00Z",
                    "ending_at": "2026-08-04T00:00:00Z",
                    "results": [
                        {
                            "workspace_id": "workspace",
                            "currency": "USD",
                            "amount": "2.066",
                        }
                    ],
                },
            ],
            "has_more": False,
            "next_page": None,
        }
        pages = [first_page, second_page]
        requests: list[str] = []

        def urlopen(request: object, **_kwargs: object) -> io.StringIO:
            requests.append(request.full_url)
            return io.StringIO(json.dumps(pages.pop(0)))

        original_token = EVIDENCE.admin_token
        original_open = EVIDENCE.urllib.request.urlopen
        try:
            EVIDENCE.admin_token = lambda _profile: "test-token"
            EVIDENCE.urllib.request.urlopen = urlopen
            snapshot = EVIDENCE.fetch_workspace_cost("test-profile", "workspace")
        finally:
            EVIDENCE.admin_token = original_token
            EVIDENCE.urllib.request.urlopen = original_open

        self.assertEqual(pages, [])
        self.assertEqual(len(requests), 2)
        first_query = EVIDENCE.urllib.parse.parse_qs(
            EVIDENCE.urllib.parse.urlparse(requests[0]).query
        )
        second_query = EVIDENCE.urllib.parse.parse_qs(
            EVIDENCE.urllib.parse.urlparse(requests[1]).query
        )
        self.assertEqual(first_query["limit"], ["31"])
        self.assertNotIn("page", first_query)
        self.assertEqual(second_query["page"], ["after-default-seven"])
        self.assertEqual(Decimal(snapshot["cost_usd"]), Decimal("3.86140"))
        self.assertEqual(
            snapshot["workspace_cost_utc_days"], ["2026-08-02", "2026-08-03"]
        )
        self.assertEqual(snapshot["schema_version"], 3)
        expected_complete = EVIDENCE.completely_covered_utc_days(
            EVIDENCE.parse_time(snapshot["reporting_window"]["starting_at"]),
            EVIDENCE.parse_time(snapshot["reporting_window"]["ending_at"]),
            EVIDENCE.parse_time(snapshot["captured_at"]),
        )
        self.assertEqual(snapshot["complete_utc_days"], expected_complete)
        self.assertNotIn(
            EVIDENCE.utc_day(EVIDENCE.parse_time(snapshot["captured_at"])),
            snapshot["complete_utc_days"],
        )

    def test_finalizer_allows_observed_zero_incremental_spend_after_settlement(
        self,
    ) -> None:
        self.after["workspace_cost_utc_days"] = ["2026-08-02"]
        self.after["cost_usd"] = self.before["cost_usd"]
        measurement = self.finalize()["cost_measurement"]
        self.assertEqual(measurement["incremental_spend_before_refusal_usd"], "0.00000")

    def test_finalizer_accepts_actual_schema_2_closed_refusal_day_without_row(
        self,
    ) -> None:
        self.before = self.snapshot(560, "3.84074", legacy=True)
        self.after = self.snapshot(
            2000,
            "3.84074",
            2,
            schema_version=2,
        )
        measurement = self.finalize()["cost_measurement"]
        self.assertEqual(measurement["settled_spend_after_refusal_usd"], "3.84074")
        self.assertEqual(measurement["incremental_spend_before_refusal_usd"], "0.00000")
        self.assertEqual(
            measurement["post_refusal_cost_report_window"],
            self.after["reporting_window"],
        )
        self.assertEqual(
            measurement["post_refusal_complete_utc_days"],
            ["2026-08-01", "2026-08-02", "2026-08-03"],
        )
        self.assertEqual(
            measurement["post_refusal_workspace_cost_utc_days"], ["2026-08-02"]
        )

    def test_finalizer_rejects_no_factory_rows_even_when_refusal_day_is_complete(
        self,
    ) -> None:
        self.after["workspace_cost_utc_days"] = []
        with self.assertRaisesRegex(ValueError, "no workspace-attributed UTC day"):
            self.finalize()

    def test_finalizer_rejects_pre_activation_day_without_factory_row(self) -> None:
        self.before["workspace_cost_utc_days"] = ["2026-08-01"]
        with self.assertRaisesRegex(ValueError, "pre-activation Cost Report lacks"):
            self.finalize()

    def test_finalizer_rejects_after_snapshot_missing_pre_activation_row(
        self,
    ) -> None:
        self.after["workspace_cost_utc_days"] = ["2026-08-03"]
        self.after["cost_usd"] = "7.00000"
        with self.assertRaisesRegex(
            ValueError, "post-refusal Cost Report lacks.*pre-activation UTC day"
        ):
            self.finalize()

    def test_finalizer_rejects_mismatched_reporting_window_starts(self) -> None:
        self.after["reporting_window"]["starting_at"] = "2026-08-02T00:00:00Z"
        self.after["complete_utc_days"] = ["2026-08-02", "2026-08-03"]
        with self.assertRaisesRegex(
            ValueError, "do not share a reporting-window start"
        ):
            self.finalize()

    def test_finalizer_sums_present_refusal_day_row_into_overshoot(self) -> None:
        self.after["complete_utc_days"] = [
            "2026-08-01",
            "2026-08-02",
            "2026-08-03",
        ]
        self.assertIn("2026-08-03", self.after["workspace_cost_utc_days"])
        measurement = self.finalize()["cost_measurement"]
        self.assertEqual(measurement["incremental_spend_before_refusal_usd"], "0.02066")

    def test_finalizer_rejects_baseline_not_above_temporary_cap(self) -> None:
        self.before["cost_usd"] = "0.99"
        with self.assertRaisesRegex(ValueError, "not lowered below"):
            self.finalize()

    def test_finalizer_rejects_open_refusal_utc_day_without_factory_row(self) -> None:
        self.after = self.snapshot(800, "3.86140", 2)
        with self.assertRaisesRegex(ValueError, "before the request UTC day closed"):
            self.finalize()

    def test_finalizer_rejects_closed_refusal_day_outside_reporting_window(
        self,
    ) -> None:
        self.after = self.snapshot(2000, "3.84074", 2, schema_version=2)
        self.after["reporting_window"]["ending_at"] = "2026-08-03T23:00:00Z"
        with self.assertRaisesRegex(
            ValueError, "does not completely cover the request UTC day"
        ):
            self.finalize()

    def test_finalizer_accepts_measured_legacy_pre_activation_snapshot(self) -> None:
        self.before = self.snapshot(560, "3.84074", legacy=True)
        self.assertEqual(self.finalize()["schema_version"], 4)

    def test_finalizer_rejects_other_legacy_pre_activation_snapshot(self) -> None:
        self.before = self.snapshot(560, "3.84075", legacy=True)
        with self.assertRaisesRegex(ValueError, "not the measured A121 snapshot"):
            self.finalize()

    def test_finalizer_rejects_post_refusal_under_elapsed_floor_after_day_close(
        self,
    ) -> None:
        self.refusal = self.worker("temporary_refusal", 1988, "refused")
        self.caps["restored_acceptance"] = self.cap(1989, "50.00")
        self.after = self.snapshot(1990, "3.86140", 2, 1988)
        self.restored = self.worker("restored_acceptance", 1993, "accepted")
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
        self.caps["operational_acceptance"] = self.cap(546, "50.00")
        self.operational = self.worker("operational_acceptance", 548, "accepted")
        self.before = self.snapshot(550, "3.84074", 548)
        self.caps["temporary_refusal"] = self.cap(551, "1.00")
        self.refusal = self.worker("temporary_refusal", 553, "refused")
        self.caps["restored_acceptance"] = self.cap(554, "50.00")
        self.after = self.snapshot(2000, "3.86140", 548, 553)
        with self.assertRaisesRegex(ValueError, "pre-activation cost"):
            self.finalize()

    def test_finalizer_rejects_month_boundary(self) -> None:
        self.start = datetime(2026, 8, 30, 14, 51, tzinfo=timezone.utc)
        self.operational = self.worker("operational_acceptance", 2, "accepted")
        self.before = self.snapshot(560, "3.84074", 2)
        self.caps["operational_acceptance"] = self.cap(0, "50.00")
        self.caps["temporary_refusal"] = self.cap(561, "1.00")
        self.refusal = self.worker("temporary_refusal", 563, "refused")
        self.caps["restored_acceptance"] = self.cap(564, "50.00")
        self.after = self.snapshot(2000, "3.86140", 2, 563)
        self.restored = self.worker("restored_acceptance", 2001, "accepted")
        with self.assertRaisesRegex(ValueError, "monthly billing boundary"):
            self.finalize()

    def test_post_refusal_spend_has_no_fifty_dollar_ceiling(self) -> None:
        self.after["cost_usd"] = "55.00"
        measurement = self.finalize()["cost_measurement"]
        self.assertEqual(
            measurement["incremental_spend_before_refusal_usd"], "51.15926"
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

    def test_a120_body_is_fixed_above_the_reviewed_uncached_cost_floor(self) -> None:
        prompt = (
            "Synthetic Patchyard Factory provider spend-enforcement input.\n"
            + "".join(
                f"patchyard-spend-{index:06d} "
                for index in range(A120_CALIBRATION_ITEMS)
            )
            + "\nReply with one character.\n"
        )
        body = (
            json.dumps(
                {
                    "model": "claude-opus-5",
                    "max_tokens": 1,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt}
                                for _ in range(A120_CALIBRATION_COPIES)
                            ],
                        }
                    ],
                },
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        self.assertEqual(len(prompt.encode()), 400083)
        self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), A120_PROMPT_SHA256)
        self.assertEqual(len(body), 800306)
        self.assertEqual(hashlib.sha256(body).hexdigest(), A120_BODY_SHA256)
        self.assertNotIn(b"cache_control", body)
        self.assertIn(
            f"readonly PROMPT_CALIBRATION_COPIES={A120_CALIBRATION_COPIES}",
            self.transport,
        )
        self.assertIn(
            f"readonly MINIMUM_UNCACHED_INPUT_TOKENS="
            f"{A120_MINIMUM_UNCACHED_INPUT_TOKENS}",
            self.transport,
        )

    def test_a120_acceptance_requires_uncached_tokens_at_the_floor(self) -> None:
        predicate = self.function("anthropic_acceptance_meets_a120_floor")
        for input_tokens, cache_creation, cache_read, expected in (
            (300000, 0, 0, 0),
            (299999, 0, 0, 1),
            (300000, 1, 0, 1),
            (300000, 0, 1, 1),
        ):
            with self.subTest(
                input_tokens=input_tokens,
                cache_creation=cache_creation,
                cache_read=cache_read,
            ):
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as handle:
                    json.dump(
                        {
                            "usage": {
                                "input_tokens": input_tokens,
                                "cache_creation_input_tokens": cache_creation,
                                "cache_read_input_tokens": cache_read,
                            }
                        },
                        handle,
                    )
                    handle.flush()
                    script = "\n".join(
                        (
                            "set -euo pipefail",
                            f"MINIMUM_UNCACHED_INPUT_TOKENS="
                            f"{A120_MINIMUM_UNCACHED_INPUT_TOKENS}",
                            predicate,
                            'PROVIDER_RESPONSE="$1"',
                            "anthropic_acceptance_meets_a120_floor",
                        )
                    )
                    result = subprocess.run(
                        ["bash", "-c", script, "bash", handle.name],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_a120_temporary_acceptance_is_a_terminal_qualified_negative(self) -> None:
        stop = '''  if [[ "$QUALIFICATION_PHASE" == temporary_refusal ]]; then
    echo 'anthropic-spend-provider-response-rejected-200-provider-accepted-workspace-scope-qualified-negative' >&2
    exit 1
  fi'''
        self.assertEqual(self.transport.count(stop), 1)
        self.assertLess(
            self.transport.index(stop),
            self.transport.index("  if ! anthropic_acceptance_meets_a120_floor; then"),
        )

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
        self.assertEqual(
            hashlib.sha256(
                (ROOT / "worker/runtime/patchyard-firecracker-run").read_bytes()
            ).hexdigest(),
            EXPECTED_LAUNCHER_SOURCE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (
                    ROOT
                    / "worker/qualification/patchyard-run-anthropic-issuance"
                ).read_bytes()
            ).hexdigest(),
            EXPECTED_RUNNER_SOURCE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (ROOT / "worker/image/patchyard-guest-run").read_bytes()
            ).hexdigest(),
            EXPECTED_GUEST_SOURCE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (
                    ROOT / "infra/ansible/roles/worker/tasks/main.yml"
                ).read_bytes()
            ).hexdigest(),
            EXPECTED_WORKER_TASKS_SOURCE_SHA256,
        )
        self.assertIn("EXPECTED_LAUNCHER_SOURCE_SHA256", self.checker)
        self.assertIn(EXPECTED_LAUNCHER_SOURCE_SHA256, self.checker)
        self.assertIn("EXPECTED_RUNNER_SOURCE_SHA256", self.checker)
        self.assertIn(EXPECTED_RUNNER_SOURCE_SHA256, self.checker)
        self.assertIn("EXPECTED_GUEST_SOURCE_SHA256", self.checker)
        self.assertIn(EXPECTED_GUEST_SOURCE_SHA256, self.checker)
        self.assertIn("EXPECTED_WORKER_TASKS_SOURCE_SHA256", self.checker)
        self.assertIn(EXPECTED_WORKER_TASKS_SOURCE_SHA256, self.checker)
        self.assertEqual(
            hashlib.sha256(
                (ROOT / "tools/check-anthropic-spend.py").read_bytes()
            ).hexdigest(),
            EXPECTED_CHECKER_SOURCE_SHA256,
        )
        self.assertIn("EXPECTED_PROVIDER_CALL_SEQUENCE", self.checker)
        self.assertIn("EXPECTED_RUN_ROOT_STAGING", self.checker)
        self.assertIn(
            "EXPECTED_IPV6_PREFLIGHT_COMPARISON",
            self.checker,
        )

    def test_a101_readiness_sources_are_independently_bound(self) -> None:
        for relative, expected, constant in (
            (
                "infra/wait-do-worker-firewall.sh",
                EXPECTED_READINESS_HELPER_SOURCE_SHA256,
                "EXPECTED_READINESS_HELPER_SOURCE_SHA256",
            ),
            (
                "infra/replace-worker.sh",
                EXPECTED_REPLACEMENT_OPERATOR_SOURCE_SHA256,
                "EXPECTED_REPLACEMENT_OPERATOR_SOURCE_SHA256",
            ),
            (
                "tools/check-ansible.sh",
                EXPECTED_ANSIBLE_WRAPPER_SOURCE_SHA256,
                "EXPECTED_ANSIBLE_WRAPPER_SOURCE_SHA256",
            ),
            (
                "infra/ansible/tests/test_worker_firewall_readiness.py",
                EXPECTED_READINESS_TEST_SOURCE_SHA256,
                "EXPECTED_READINESS_TEST_SOURCE_SHA256",
            ),
        ):
            with self.subTest(relative=relative):
                actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                self.assertEqual(actual, expected)
                self.assertIn(constant, self.checker)
                self.assertIn(expected, self.checker)

    def test_spend_run_root_grants_only_required_traversal(self) -> None:
        exact = '''if $SPEND_MODE; then
  # The one-shot request runs as factory-worker. Grant that identity traversal of
  # this exact run root without directory read or write access; the capability
  # itself remains root:root 0600 and the worker-owned raw directory is 0700.
  install -d -m 0710 -o root -g factory-worker "$RUN_TMPFS"
  [[ "$(stat -c '%U:%G:%a' -- "$RUN_TMPFS")" == root:factory-worker:710 ]]
  /usr/sbin/runuser -u factory-worker -- /usr/bin/test -x "$RUN_TMPFS"
else
  install -d -m 0700 -o root -g root "$RUN_TMPFS"
  [[ "$(stat -c '%U:%G:%a' -- "$RUN_TMPFS")" == root:root:700 ]]
fi'''
        self.assertEqual(self.launcher.count(exact), 1)
        staging_index = self.launcher.index(exact)
        self.assertLess(
            self.launcher.index("FAILURE_STAGE=runtime-staging"), staging_index
        )
        self.assertLess(
            staging_index,
            self.launcher.index(
                'install -d -m 0700 -o factory-worker -g factory-worker '
                '"$RESULT_EXTRACT"'
            ),
        )
        self.assertLess(
            staging_index,
            self.launcher.index('CAPABILITY="$RUN_TMPFS/capability.json"'),
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
                ["python3", "-I", str(root / "tools/check-anthropic-spend.py")],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

    def checker_ready_result(self) -> dict[str, object]:
        fixture = AnthropicSpendEvidenceContract()
        fixture.setUp()
        result = deepcopy(fixture.finalize())
        policy = json.loads((ROOT / "policy/anthropic-wif.json").read_text())
        organization_id = policy["organization"]["id"]
        workspace_id = policy["workspace"]["id"]
        service_account_id = policy["service_account"]["id"]
        rule_id = policy["rule"]["id"]

        def digest(path: pathlib.Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        image_path = ROOT / "worker/image"
        image_records = [
            f"{digest(path)}  {path.relative_to(image_path)}\n"
            for path in sorted(path for path in image_path.rglob("*") if path.is_file())
        ]
        image_recipe = hashlib.sha256("".join(image_records).encode()).hexdigest()
        host_paths = (
            ROOT / "worker/qualification/patchyard-run-anthropic-issuance",
            ROOT / "worker/runtime/patchyard-firecracker-run",
            ROOT / "worker/runtime/patchyard-anthropic-one-shot",
        )
        host_records = [
            f"{digest(path)}  {path.relative_to(ROOT)}\n" for path in host_paths
        ]
        host_contract = hashlib.sha256("".join(host_records).encode()).hexdigest()
        reproducible = {
            "request_sha256": (
                "ce878144cf842b99bab3cea547ce8c64ed0386c17e8d12fecee6dc2ad59ca6e2"
            ),
            "patch_sha256": (
                "909c2d57670e517581e7a56de08db6947973027a96d295793dc4a1b5c6168e1f"
            ),
            "production_parity_sha256": digest(
                ROOT / "worker/image/production-parity.json"
            ),
            "image_recipe_sha256": image_recipe,
            "host_contract_sha256": host_contract,
        }
        transport_digest = digest(
            ROOT / "worker/runtime/patchyard-anthropic-one-shot"
        )

        result["organization_id"] = organization_id
        result["workspace_id"] = workspace_id
        result["service_account_id"] = service_account_id
        result["request_binding"]["request_body_sha256"] = A120_BODY_SHA256
        for evidence in result["phases"].values():
            for field, value in reproducible.items():
                evidence[field] = value
            evidence["issuance"]["service_account_id"] = service_account_id
            evidence["issuance"]["rule_id"] = rule_id
            evidence["issuance"]["workspace_id"] = workspace_id
            evidence["provider_transport"]["client_sha256"] = transport_digest
            evidence["provider_observation"][
                "request_body_sha256"
            ] = A120_BODY_SHA256
        return result

    def test_checker_validates_durable_a122_result_without_snapshots(self) -> None:
        import shutil

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory) / "repo"
            shutil.copytree(
                ROOT,
                root,
                ignore=shutil.ignore_patterns(".git", "target", "node_modules"),
            )
            result_path = (
                root
                / "research/isolation/results/anthropic-spend-enforcement.json"
            )
            result = self.checker_ready_result()
            result_path.write_text(json.dumps(result, indent=2) + "\n")
            command = [
                "python3",
                "-I",
                str(root / "tools/check-anthropic-spend.py"),
            ]
            baseline = subprocess.run(
                command, cwd=root, check=False, capture_output=True, text=True
            )
            self.assertEqual(baseline.returncode, 0, baseline.stderr)

            result["cost_measurement"]["post_refusal_complete_utc_days"].remove(
                "2026-08-03"
            )
            result_path.write_text(json.dumps(result, indent=2) + "\n")
            mutation = subprocess.run(
                command, cwd=root, check=False, capture_output=True, text=True
            )
            self.assertNotEqual(mutation.returncode, 0)
            self.assertIn(
                "A122 cost separation, day-close settlement, or phase ordering "
                "is malformed",
                mutation.stderr,
            )

    def test_checker_rejects_required_a120_a121_a122_mutations(self) -> None:
        mutations = (
            (
                "body below cost floor",
                "worker/runtime/patchyard-anthropic-one-shot",
                "readonly PROMPT_CALIBRATION_COPIES=2",
                "readonly PROMPT_CALIBRATION_COPIES=1",
                "  A120 request body falls below or differs from the cost-floor binding",
            ),
            (
                "second request in one phase",
                "worker/runtime/patchyard-anthropic-one-shot",
                '      --data-binary "@$PROVIDER_REQUEST" \\\n'
                "      'https://api.anthropic.com/v1/messages'",
                '      --data-binary "@$PROVIDER_REQUEST" \\\n'
                "      'https://api.anthropic.com/v1/messages' \\\n"
                '      --next --data-binary "@$PROVIDER_REQUEST" \\\n'
                "      'https://api.anthropic.com/v1/messages'",
                "  A117 one-shot transfer permits another transfer: --next",
            ),
            (
                "removed pre-activation settlement floor",
                "tools/anthropic-spend-evidence.py",
                "    if pre_activation_settlement_window < minimum_window:\n",
                "    if False and pre_activation_settlement_window < minimum_window:\n",
                "  A120 pre-activation settlement floor guard is missing",
            ),
            (
                "removed post-refusal UTC-day-close condition",
                "tools/anthropic-spend-evidence.py",
                '    if not utc_day_closed(observed["temporary_refusal"], after_time):\n',
                "    if False and not utc_day_closed(\n"
                '        observed["temporary_refusal"], after_time\n'
                "    ):\n",
                "  A121 post-refusal UTC-day-close guard is missing",
            ),
            (
                "single-page Cost Report read",
                "tools/anthropic-spend-evidence.py",
                '        if not payload.get("has_more"):\n',
                '        if True or not payload.get("has_more"):\n',
                "  A121 Cost Report query can silently truncate daily buckets",
            ),
            (
                "snapshot with no Factory rows",
                "tools/anthropic-spend-evidence.py",
                "    if not matched_workspace:\n",
                "    if False and not matched_workspace:\n",
                "  A122 snapshot no-rows fail-closed guard is missing",
            ),
            (
                "pre-activation day without a Factory row",
                "tools/anthropic-spend-evidence.py",
                "    elif pre_activation_utc_day not in before_workspace_days:\n",
                "    elif False and pre_activation_utc_day not in before_workspace_days:\n",
                "  A122 pre-activation Factory-row guard is missing",
            ),
            (
                "post-refusal day without complete coverage",
                "tools/anthropic-spend-evidence.py",
                "    if after_complete_days is None or post_refusal_utc_day not in after_complete_days:\n",
                "    if False and (\n"
                "        after_complete_days is None\n"
                "        or post_refusal_utc_day not in after_complete_days\n"
                "    ):\n",
                "  A122 post-refusal complete-day guard is missing",
            ),
            (
                "mismatched cost reporting windows",
                "tools/anthropic-spend-evidence.py",
                "    if before_window_start != after_window_start:\n",
                "    if False and before_window_start != after_window_start:\n",
                "  A122 cost snapshots can use different reporting windows",
            ),
            (
                "post-refusal aggregate without the billed baseline row",
                "tools/anthropic-spend-evidence.py",
                "    if (\n"
                "        after_workspace_days is None\n"
                "        or pre_activation_utc_day not in after_workspace_days\n"
                "    ):\n",
                "    if False and (\n"
                "        after_workspace_days is None\n"
                "        or pre_activation_utc_day not in after_workspace_days\n"
                "    ):\n",
                "  A122 post-refusal aggregate baseline-row guard is missing",
            ),
            (
                "missing qualified-negative stop",
                "worker/runtime/patchyard-anthropic-one-shot",
                '''  if [[ "$QUALIFICATION_PHASE" == temporary_refusal ]]; then
    echo 'anthropic-spend-provider-response-rejected-200-provider-accepted-workspace-scope-qualified-negative' >&2
    exit 1
  fi''',
                '''  if [[ "$QUALIFICATION_PHASE" == temporary_refusal ]]; then
    echo 'anthropic-spend-provider-response-rejected-200-provider-accepted-workspace-scope-qualified-negative' >&2
    :
  fi''',
                "  A120 provider-acceptance qualified-negative stop is missing",
            ),
            (
                "missing first-acceptance settled-cost stop",
                "docs/anthropic-spend-enforcement.md",
                "If the settled\n   amount is $1.00 or less, stop.",
                "If the settled\n   amount is $1.00 or less, continue.",
                "  A120 first-acceptance settled-cost stop is missing from the procedure",
            ),
        )
        for name, relative, before, after, diagnostic in mutations:
            with self.subTest(name=name):
                result = self.run_checker_mutation(relative, before, after)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(
                    result.stderr.splitlines()[0], "Anthropic spend check: failed"
                )
                self.assertIn(diagnostic, result.stderr.splitlines()[1:])

    def test_checker_rejects_a101_f1_f6_structural_mutations(self) -> None:
        mutations = (
            (
                "F1 alternate client",
                "infra/wait-do-worker-firewall.sh",
                "  HTTP_STATUS=\n",
                "  /nonexistent/wget --timeout=900 --tries=100 -O /dev/null "
                '"https://api.digitalocean.com/v2/droplets/'
                '${WORKER_ID}" || true\n'
                "  HTTP_STATUS=\n",
                "  A101 firewall readiness helper differs from its complete source binding",
            ),
            (
                "F2 parameter assembly",
                "infra/wait-do-worker-firewall.sh",
                "  HTTP_STATUS=\n",
                "  A101_CLIENT=/nonexistent/cur\n"
                '  "${A101_CLIENT}l" -m 900 --retry 100 '
                '"https://api.digitalocean.com/v2/droplets/'
                '${WORKER_ID}" || true\n'
                "  HTTP_STATUS=\n",
                "  A101 firewall readiness helper differs from its complete source binding",
            ),
            (
                "F3 sourced sibling",
                "infra/wait-do-worker-firewall.sh",
                "for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do\n",
                '[[ ! -f "$REPO_ROOT/infra/lib/readiness-extra.sh" ]] '
                '|| . "$REPO_ROOT/infra/lib/readiness-extra.sh"\n\n'
                "for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do\n",
                "  A101 firewall readiness helper differs from its complete source binding",
            ),
            (
                "F3 Bash builtin networking",
                "infra/wait-do-worker-firewall.sh",
                "for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do\n",
                '[[ -z "${PATCHYARD_DEBUG_PROBE:-}" ]] '
                "|| exec 3<>/dev/tcp/api.digitalocean.com/443\n\n"
                "for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do\n",
                "  A101 firewall readiness helper differs from its complete source binding",
            ),
            (
                "F4 operator-wide client",
                "infra/replace-worker.sh",
                '    "$REPO_ROOT/infra/tofu.sh" digitalocean apply "$PLAN_FILE"\n',
                '    "$REPO_ROOT/infra/tofu.sh" digitalocean apply "$PLAN_FILE"\n'
                "    curl -sS -m 900 --retry 100 -o /dev/null "
                '"https://api.digitalocean.com/v2/droplets" || true\n',
                "  A101 worker replacement operator differs from its complete source binding",
            ),
            (
                "F5 ShellCheck census",
                "tools/check-ansible.sh",
                '  "$REPO_ROOT/infra/wait-do-worker-firewall.sh" \\\n',
                "",
                "  A101 Ansible wrapper differs from its complete source binding",
            ),
            (
                "F5 readiness test census",
                "infra/ansible/tests/test_worker_firewall_readiness.py",
                "class WorkerFirewallReadinessContract(unittest.TestCase):",
                "class WorkerFirewallReadinessContract(object):",
                "  A101 readiness test census differs from its complete source binding",
            ),
            (
                "F6 redirected attempted counter",
                "infra/wait-do-worker-firewall.sh",
                "  HTTP_STATUS=\n",
                '  MOCK_CURL_TOTAL=/dev/null cu"r"l -q -m 900 '
                '"https://api.digitalocean.com/v2/droplets/'
                '${WORKER_ID}" || true\n'
                "  HTTP_STATUS=\n",
                "  A101 firewall readiness helper differs from its complete source binding",
            ),
        )
        for name, relative, before, after, diagnostic in mutations:
            with self.subTest(name=name):
                result = self.run_checker_mutation(relative, before, after)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                diagnostics = result.stderr.splitlines()
                self.assertTrue(diagnostics, result.stdout)
                self.assertEqual(diagnostics[0], "Anthropic spend check: failed")
                self.assertIn(diagnostic, diagnostics[1:])

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
                '  install -d -m 0710 -o root -g factory-worker "$RUN_TMPFS"',
                '  install -d -m 0700 -o root -g root "$RUN_TMPFS"',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                '  install -d -m 0710 -o root -g factory-worker "$RUN_TMPFS"',
                '  install -d -m 0770 -o root -g factory-worker "$RUN_TMPFS"',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                '  install -d -m 0700 -o root -g root "$RUN_TMPFS"',
                '  install -d -m 0710 -o root -g factory-worker "$RUN_TMPFS"',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                '  [[ "$(stat -c \'%U:%G:%a\' -- "$RUN_TMPFS")" '
                "== root:factory-worker:710 ]]",
                '  [[ "$(stat -c \'%U:%G:%a\' -- "$RUN_TMPFS")" '
                "== root:factory-worker:770 ]]",
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                "  /usr/sbin/runuser -u factory-worker -- /usr/bin/test -x "
                '"$RUN_TMPFS"',
                "  /usr/sbin/runuser -u root -- /usr/bin/test -x "
                '"$RUN_TMPFS"',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                "  /usr/sbin/runuser -u factory-worker -- /usr/bin/test -x "
                '"$RUN_TMPFS"',
                "  /usr/sbin/runuser -u factory-worker -- /usr/bin/test -e "
                '"$RUN_TMPFS"',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                '  [[ "$(stat -c \'%U:%G:%a\' -- "$RUN_TMPFS")" '
                "== root:root:700 ]]",
                '  [[ "$(stat -c \'%U:%G:%a\' -- "$RUN_TMPFS")" '
                "== root:root:710 ]]",
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                "FAILURE_STAGE=runtime-staging",
                "FAILURE_STAGE=runtime-preparation",
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                'install -d -m 0700 -o factory-worker -g factory-worker '
                '"$RESULT_EXTRACT"',
                'install -d -m 0700 -o factory-worker -g factory-worker '
                '-- "$RESULT_EXTRACT"',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                'CAPABILITY="$RUN_TMPFS/capability.json"',
                'CAPABILITY="${RUN_TMPFS}/capability.json"',
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
            (
                "worker/runtime/patchyard-firecracker-run",
                "      | if length == 1 then .[0] else error(\"counter cardinality\") end'\n"
                "}\n\nprovider_set_elements() {",
                "      | if length == 1 then .[0] else error(\"counter cardinality\") end'\n"
                "}\n\nsetup_provider_transport()\n"
                "{\n"
                "  return 0\n"
                "}\n\n"
                "assert_provider_transport_preflight() {\n"
                "  return 0\n"
                "}\n\n"
                "provider_set_elements() {",
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                "  setup_provider_transport\n"
                "  assert_provider_transport_preflight\n"
                '  "$ANTHROPIC_ONE_SHOT" "$PROVIDER_NETNS" '
                '"$CAPABILITY" "$PROVIDER_STAGE"',
                "  setup_provider_transport\n"
                "  if false; then\n"
                "    assert_provider_transport_preflight\n"
                "  fi\n"
                '  "$ANTHROPIC_ONE_SHOT" "$PROVIDER_NETNS" '
                '"$CAPABILITY" "$PROVIDER_STAGE"',
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                "provider_counter_packets() {\n  local name=$1",
                "provider_counter_packets() {\n"
                "  local name=$1\n"
                "  if [[ \"$name\" == admitted_new ]]; then\n"
                "    printf '1\\n'\n"
                "  else\n"
                "    printf '0\\n'\n"
                "  fi\n"
                "  return 0",
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                "provider_set_elements() {\n  local name=$1",
                "provider_set_elements() {\n"
                "  local name=$1\n"
                "  if [[ \"$name\" == rejected ]]; then\n"
                "    printf '0\\n'\n"
                "  else\n"
                "    printf '1\\n'\n"
                "  fi\n"
                "  return 0",
            ),
            (
                "worker/runtime/patchyard-firecracker-run",
                "  setup_provider_transport\n"
                "  assert_provider_transport_preflight",
                "  setup_provider_transport\n"
                "  nft insert rule inet \"$PROVIDER_NFT_TABLE\" forward \\\n"
                "    iifname \"$PROVIDER_HOST_VETH\" counter accept\n"
                "  assert_provider_transport_preflight",
            ),
            (
                "worker/qualification/patchyard-run-anthropic-issuance",
                "LAUNCHER_SOURCE_SHA256=${BASH_REMATCH[1]}\n"
                '[[ "$LAUNCHER_SOURCE_SHA256" == "$EXPECTED_LAUNCHER_SHA256" ]]',
                "LAUNCHER_SOURCE_SHA256=${BASH_REMATCH[1]}\n"
                "if false; then\n"
                '  [[ "$LAUNCHER_SOURCE_SHA256" == "$EXPECTED_LAUNCHER_SHA256" ]]\n'
                "fi",
            ),
            (
                "worker/qualification/patchyard-run-anthropic-issuance",
                "LAUNCHER_SOURCE_SHA256=${BASH_REMATCH[1]}\n"
                '[[ "$LAUNCHER_SOURCE_SHA256" == "$EXPECTED_LAUNCHER_SHA256" ]]',
                "LAUNCHER_SOURCE_SHA256=${BASH_REMATCH[1]}\n"
                "EXPECTED_LAUNCHER_SHA256=$LAUNCHER_SOURCE_SHA256\n"
                '[[ "$LAUNCHER_SOURCE_SHA256" == "$EXPECTED_LAUNCHER_SHA256" ]]',
            ),
            (
                "worker/qualification/patchyard-run-anthropic-issuance",
                '  [[ "$TRANSPORT_SOURCE_SHA256" == "$EXPECTED_TRANSPORT_SHA256" ]]',
                "  : # removed transport comparison",
            ),
            (
                "infra/ansible/roles/worker/tasks/main.yml",
                "- name: Install the explicit supervisor worker-teardown operation",
                "- name: Overwrite the production launcher from a different source\n"
                "  ansible.builtin.copy:\n"
                '    src: "{{ playbook_dir }}/../../worker/runtime/patchyard-run-fixture"\n'
                "    dest: /usr/local/sbin/patchyard-firecracker-run\n"
                "    owner: root\n"
                "    group: root\n"
                '    mode: "0750"\n\n'
                "- name: Install the explicit supervisor worker-teardown operation",
            ),
            (
                "worker/image/patchyard-guest-run",
                "  [[ ! -e /dev/disk/by-label/ETA_CREDENTIAL ]]\n"
                "  [[ ! -s /input/provider-hosts ]]",
                "  if false; then\n"
                "    [[ ! -e /dev/disk/by-label/ETA_CREDENTIAL ]]\n"
                "    [[ ! -s /input/provider-hosts ]]\n"
                "  fi",
            ),
            (
                "worker/image/patchyard-guest-run",
                "    and .schema_version == 1 and .authorization_ruling == \"A117\"\n"
                "    and .mechanism == \"host-one-shot-network-namespace-v1\"\n"
                "    and .http_version == \"1.0\" and .connection_close == true\n"
                "    and .admitted_conntrack_ids == 1 and .admitted_new_connections == 1\n"
                "    and .rejected_new_connections == 0 and .rejected_connection_packets == 0\n"
                "    and .guest_provider_allowlist_entries == 0\n"
                "    and .namespace_ipv6_disabled == true\n"
                "    and .credential_removed_before_guest_boot == true",
                "    and (true or (\n"
                "      .schema_version == 1 and .authorization_ruling == \"A117\"\n"
                "      and .mechanism == \"host-one-shot-network-namespace-v1\"\n"
                "      and .http_version == \"1.0\" and .connection_close == true\n"
                "      and .admitted_conntrack_ids == 1 and .admitted_new_connections == 1\n"
                "      and .rejected_new_connections == 0 and .rejected_connection_packets == 0\n"
                "      and .guest_provider_allowlist_entries == 0\n"
                "      and .namespace_ipv6_disabled == true\n"
                "      and .credential_removed_before_guest_boot == true\n"
                "    ))",
            ),
        )
        expected_diagnostic = {
            "worker/runtime/patchyard-anthropic-one-shot": (
                "  A120 one-shot transport differs from its complete source binding"
            ),
            "worker/runtime/patchyard-firecracker-run": (
                "  post-A118 launcher differs from its complete source binding"
            ),
            "worker/qualification/patchyard-run-anthropic-issuance": (
                "  A117 host-contract binding is missing: efh[0-9a-f]{8}[@:]"
            ),
            "worker/image/patchyard-guest-run": (
                "  A117 spend guest still contains the provider destination"
            ),
            "infra/ansible/roles/worker/tasks/main.yml": (
                "  post-A118 installed launcher path is not singular"
            ),
        }
        complete_source_diagnostic = {
            (
                "worker/runtime/patchyard-firecracker-run",
                '  install -d -m 0710 -o root -g factory-worker "$RUN_TMPFS"',
            ): "  A115 spend run-root traversal differs from its exact binding",
            (
                "worker/runtime/patchyard-firecracker-run",
                '  install -d -m 0700 -o root -g root "$RUN_TMPFS"',
            ): "  A115 spend run-root traversal differs from its exact binding",
            (
                "worker/runtime/patchyard-firecracker-run",
                '  [[ "$(stat -c \'%U:%G:%a\' -- "$RUN_TMPFS")" '
                "== root:factory-worker:710 ]]",
            ): "  A115 spend run-root traversal differs from its exact binding",
            (
                "worker/runtime/patchyard-firecracker-run",
                "  /usr/sbin/runuser -u factory-worker -- /usr/bin/test -x "
                '"$RUN_TMPFS"',
            ): "  A115 spend run-root traversal differs from its exact binding",
            (
                "worker/runtime/patchyard-firecracker-run",
                '  [[ "$(stat -c \'%U:%G:%a\' -- "$RUN_TMPFS")" '
                "== root:root:700 ]]",
            ): "  A115 spend run-root traversal differs from its exact binding",
            (
                "worker/runtime/patchyard-firecracker-run",
                "FAILURE_STAGE=runtime-staging",
            ): "  A115 spend run-root traversal is outside runtime staging",
            (
                "worker/runtime/patchyard-firecracker-run",
                'install -d -m 0700 -o factory-worker -g factory-worker '
                '"$RESULT_EXTRACT"',
            ): "  A115 spend run-root traversal is outside runtime staging",
            (
                "worker/runtime/patchyard-firecracker-run",
                'CAPABILITY="$RUN_TMPFS/capability.json"',
            ): "  A115 spend run-root traversal is outside runtime staging",
            (
                "worker/qualification/patchyard-run-anthropic-issuance",
                "LAUNCHER_SOURCE_SHA256=${BASH_REMATCH[1]}\n"
                '[[ "$LAUNCHER_SOURCE_SHA256" == "$EXPECTED_LAUNCHER_SHA256" ]]',
            ): "  post-A118 issuance runner differs from its complete source binding",
            (
                "worker/qualification/patchyard-run-anthropic-issuance",
                '  [[ "$TRANSPORT_SOURCE_SHA256" == "$EXPECTED_TRANSPORT_SHA256" ]]',
            ): "  post-A118 issuance runner differs from its complete source binding",
            (
                "worker/image/patchyard-guest-run",
                "  [[ ! -e /dev/disk/by-label/ETA_CREDENTIAL ]]\n"
                "  [[ ! -s /input/provider-hosts ]]",
            ): "  post-A118 spend guest differs from its complete source binding",
            (
                "worker/image/patchyard-guest-run",
                "    and .schema_version == 1 and .authorization_ruling == \"A117\"\n"
                "    and .mechanism == \"host-one-shot-network-namespace-v1\"\n"
                "    and .http_version == \"1.0\" and .connection_close == true\n"
                "    and .admitted_conntrack_ids == 1 and .admitted_new_connections == 1\n"
                "    and .rejected_new_connections == 0 and .rejected_connection_packets == 0\n"
                "    and .guest_provider_allowlist_entries == 0\n"
                "    and .namespace_ipv6_disabled == true\n"
                "    and .credential_removed_before_guest_boot == true",
            ): "  post-A118 spend guest differs from its complete source binding",
        }
        for relative, before, after in mutations:
            with self.subTest(relative=relative, before=before):
                result = self.run_checker_mutation(relative, before, after)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                diagnostics = result.stderr.splitlines()
                self.assertTrue(diagnostics, result.stdout)
                self.assertEqual(diagnostics[0], "Anthropic spend check: failed")
                self.assertIn(
                    complete_source_diagnostic.get(
                        (relative, before), expected_diagnostic[relative]
                    ),
                    diagnostics[1:],
                )


if __name__ == "__main__":
    unittest.main()
