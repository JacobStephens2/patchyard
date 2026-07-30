from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib.util
import pathlib
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
        with self.assertRaisesRegex(ValueError, "organization cap changed"):
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


if __name__ == "__main__":
    unittest.main()
