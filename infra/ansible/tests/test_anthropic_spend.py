from copy import deepcopy
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


class AnthropicSpendEvidenceContract(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = {
            "organization": {"id": "org"},
            "workspace": {"id": "workspace"},
            "spend_enforcement": {
                "operational_cap_cents": 5000,
                "qualification_cap_cents": 100,
            },
        }
        self.before = {
            "schema_version": 1,
            "provider": "anthropic",
            "workspace_id": "workspace",
            "captured_at": "2026-07-29T19:00:00Z",
            "reporting_window": {
                "starting_at": "2026-07-01T00:00:00Z",
                "ending_at": "2026-07-29T19:01:00Z",
            },
            "currency": "USD",
            "cost_usd": "0",
        }
        self.after = deepcopy(self.before)
        self.after["captured_at"] = "2026-07-29T19:04:00Z"
        self.after["cost_usd"] = "1.1375"
        self.worker = {
            "spend_enforcement": {
                "denial": {"denied_at": "2026-07-29T19:02:00Z"}
            }
        }
        self.caps = {
            "schema_version": 1,
            "provider": "anthropic",
            "organization_id": "org",
            "workspace_id": "workspace",
            "before": self.cap("2026-07-29T19:00:30Z", "50.00"),
            "qualification": self.cap("2026-07-29T19:01:00Z", "1.00"),
            "restored": self.cap("2026-07-29T19:03:00Z", "50.00"),
        }

    @staticmethod
    def cap(observed_at: str, workspace_limit: str) -> dict[str, str]:
        return {
            "observed_at": observed_at,
            "workspace_monthly_limit_usd": workspace_limit,
            "organization_monthly_limit_usd": "1000.00",
            "enforcement": "notify_and_pause",
        }

    def test_finalizer_records_the_exact_observed_overshoot(self) -> None:
        result = EVIDENCE.finalize(
            self.worker, self.before, self.after, self.caps, self.policy
        )

        measurement = result["cost_measurement"]
        self.assertEqual(measurement["observed_spend_at_denial_usd"], "1.1375")
        self.assertEqual(measurement["measured_overshoot_usd"], "0.1375")
        self.assertEqual(Decimal(measurement["measured_overshoot_usd"]), Decimal("0.1375"))
        self.assertNotIn("ceiling", measurement)

    def test_finalizer_records_zero_if_denial_prevents_crossing(self) -> None:
        self.after["cost_usd"] = "0.6400"
        result = EVIDENCE.finalize(
            self.worker, self.before, self.after, self.caps, self.policy
        )
        self.assertEqual(result["cost_measurement"]["measured_overshoot_usd"], "0")

    def test_finalizer_rejects_cost_without_the_successful_paid_calls(self) -> None:
        self.after["cost_usd"] = "0"
        with self.assertRaisesRegex(ValueError, "successful paid calls"):
            EVIDENCE.finalize(
                self.worker, self.before, self.after, self.caps, self.policy
            )

    def test_finalizer_rejects_a_changed_organization_limit(self) -> None:
        self.caps["restored"]["organization_monthly_limit_usd"] = "999.00"
        with self.assertRaisesRegex(ValueError, "organization cap changed"):
            EVIDENCE.finalize(
                self.worker, self.before, self.after, self.caps, self.policy
            )

    def test_finalizer_rejects_failure_to_restore_operational_cap(self) -> None:
        self.caps["restored"]["workspace_monthly_limit_usd"] = "1.00"
        with self.assertRaisesRegex(ValueError, "restored workspace cap"):
            EVIDENCE.finalize(
                self.worker, self.before, self.after, self.caps, self.policy
            )

    def test_finalizer_rejects_notify_only_limit(self) -> None:
        self.caps["qualification"]["enforcement"] = "notify_only"
        with self.assertRaisesRegex(ValueError, "provider-enforced pause"):
            EVIDENCE.finalize(
                self.worker, self.before, self.after, self.caps, self.policy
            )


if __name__ == "__main__":
    unittest.main()
