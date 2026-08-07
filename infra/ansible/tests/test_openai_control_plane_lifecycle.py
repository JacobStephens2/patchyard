from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
ATTESTATION_PATH = ROOT / "tools/control-plane-attestation-v1.py"
REVOCATION_COLLECTOR_PATH = ROOT / "tools/openai-wif-federation-revocation.py"
REVOCATION_CHECKER_PATH = ROOT / "tools/check-openai-wif-federation-revocation.py"
ROTATION_COLLECTOR_PATH = ROOT / "tools/openai-wif-signing-key-rotation.py"
ROTATION_CHECKER_PATH = ROOT / "tools/check-openai-wif-signing-key-rotation.py"
REVOCATION_FIXTURE_PATH = (
    ROOT / "fixtures/checker-contracts/openai-federation-revocation.json"
)
ROTATION_FIXTURE_PATH = (
    ROOT / "fixtures/checker-contracts/openai-signing-key-rotation.json"
)
POLICY_PATH = ROOT / "policy/openai-wif.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source(name: str, path: Path) -> types.ModuleType:
    source = path.read_bytes()
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = None
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


class TickingClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        observed = self.value
        self.value += timedelta(microseconds=11_111)
        return observed


class CheckerCase(unittest.TestCase):
    checker: Path
    fixture_path: Path

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = json.loads(self.fixture_path.read_text())

    def run_checker(
        self, *arguments: str, isolated: bool = True
    ) -> subprocess.CompletedProcess[str]:
        command = ["python3"]
        if isolated:
            command.append("-I")
        command.extend([str(self.checker), *arguments])
        return subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write(self, value: dict[str, object], name: str) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value))
        return path

    @staticmethod
    def observed_receipt(receipt: dict[str, object], *, denial: bool) -> None:
        receipt.update(
            {
                "source": "openai_http_response",
                "http_status": 418 if denial else 299,
                "provider_date": "2026-08-07T15:20:25Z",
                "request_id": "req_synthetic_arbitrary",
                "request_id_supplied": True,
                "content_type": "application/json",
                "body_bytes": 2,
                "body_format": "json_object",
                "response_shape": {
                    "body_kind": "json_object",
                    "top_level_fields": [],
                    "error_fields": [],
                },
                "error_type": "arbitrary_unenforced" if denial else None,
            }
        )


class AttestationAndCollectorContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.attestation = load_source("attestation_contract", ATTESTATION_PATH)
        cls.revocation = load_source("revocation_collector_contract", REVOCATION_COLLECTOR_PATH)
        cls.rotation = load_source("rotation_collector_contract", ROTATION_COLLECTOR_PATH)

    def test_both_collectors_load_one_attestation_definition_by_digest(self) -> None:
        expected = digest(ATTESTATION_PATH)
        self.assertEqual(self.revocation.ATTESTATION_DEFINITION_SHA256, expected)
        self.assertEqual(self.rotation.ATTESTATION_DEFINITION_SHA256, expected)
        self.assertEqual(
            self.revocation.LIFECYCLE_INSTRUMENT_SHA256,
            "7f7515d9279116a9daf59e7c5cfee4b4361b64247c44f1899453b754fbb20132",
        )
        self.assertEqual(
            self.rotation.LIFECYCLE_INSTRUMENT_SHA256,
            self.revocation.LIFECYCLE_INSTRUMENT_SHA256,
        )

    def test_one_accountable_human_discloses_no_independence_or_corroboration(self) -> None:
        before = {
            "captured_before_at": "2026-08-07T12:00:00.123457Z",
            "captured_after_at": "2026-08-07T12:00:00.234569Z",
            "state": {"synthetic": True},
        }
        after = {
            "captured_before_at": "2026-08-07T12:00:01.345671Z",
            "captured_after_at": "2026-08-07T12:00:01.456783Z",
            "state": {"synthetic": False},
        }
        value = self.attestation.make_attestation(
            actor_name="Fixture Operator",
            actor_kind="accountable_human",
            attester_name="Fixture Operator",
            before_reading=before,
            after_reading=after,
            mutation_description="synthetic control-plane mutation",
            lifecycle_instrument_sha256=("ab" * 32),
        )
        self.assertEqual(
            value["party_relationship"],
            {
                "same_party": True,
                "independence": False,
                "corroboration": False,
            },
        )
        dishonest = deepcopy(value)
        dishonest["party_relationship"]["same_party"] = False
        self.assertIn(
            "Attestation party relationship does not disclose role occupancy",
            self.attestation.validate_attestation(dishonest, "ab" * 32),
        )
        invented_receipt = deepcopy(value)
        invented_receipt["mutation_receipt_obtained"] = True
        self.assertIn(
            "Attestation provenance mark differs",
            self.attestation.validate_attestation(invented_receipt, "ab" * 32),
        )
        integer_relationship = deepcopy(value)
        integer_relationship["party_relationship"]["independence"] = 0
        self.assertIn(
            "Attestation party relationship is not boolean",
            self.attestation.validate_attestation(integer_relationship, "ab" * 32),
        )

    def test_collectors_pause_and_contain_no_console_transport(self) -> None:
        revocation_source = REVOCATION_COLLECTOR_PATH.read_text()
        rotation_source = ROTATION_COLLECTOR_PATH.read_text()
        for acknowledgement in ("MUTATION COMPLETE", "RESTORATION COMPLETE"):
            self.assertIn(acknowledgement, revocation_source)
        for acknowledgement in (
            "OVERLAP COMPLETE",
            "ACTIVATE LOCALLY",
            "RETIREMENT COMPLETE",
            "SAFE ROLLBACK COMPLETE",
        ):
            self.assertIn(acknowledgement, rotation_source)
        self.assertIn("finally:", revocation_source)
        self.assertIn("def capture_safe_rotation_rollback(", rotation_source)
        self.assertNotIn("urllib", revocation_source)
        self.assertNotIn("urllib", rotation_source)

    def test_party_names_fail_before_either_bounded_window_opens(self) -> None:
        for collector, arguments in (
            (
                self.revocation,
                {
                    "run_id": "openai-revocation-20260807-0123456789",
                    "mutation_kind": "disable",
                    "policy": self.revocation.load_policy(),
                },
            ),
            (
                self.rotation,
                {
                    "run_id": "openai-rotation-20260807-0123456789",
                    "policy": self.rotation.load_policy(),
                    "stage": Path("/unused"),
                },
            ),
        ):
            with self.subTest(collector=collector.__name__):
                with self.assertRaises(collector.ATTESTATION.AttestationShapeError):
                    collector.collect(
                        actor_name="invalid\nactor",
                        actor_kind="accountable_human",
                        attester_name="Fixture Operator",
                        input_fn=lambda unused: self.fail("capture opened"),
                        **arguments,
                    )

    def test_rotation_exchange_uses_a_runtime_derived_identifier(self) -> None:
        policy = json.loads(POLICY_PATH.read_text())
        derived = {
            "kid": "patchyard-bbbbbbbbbbbbbbbb",
            "jwk_thumbprint_sha256": "cd" * 32,
        }
        observed_policy: dict[str, object] = {}

        def exchange(runtime_policy, signing_key, run_id, started_at):
            del signing_key, run_id
            observed_policy.update(runtime_policy)
            return {
                "started_at": started_at,
                "assertion_descriptor": {
                    "kid": derived["kid"],
                    "jwk_thumbprint_sha256": derived["jwk_thumbprint_sha256"],
                },
                "exchange_request": {},
                "exchange_response": {},
                "credential_removed_at": started_at,
            }

        with (
            mock.patch.object(self.rotation.BASE, "load_public_jwk", return_value={}),
            mock.patch.object(self.rotation.BASE, "jwk_descriptor", return_value=derived),
            mock.patch.object(
                self.rotation.INSTRUMENT,
                "exchange_observation",
                side_effect=exchange,
            ),
        ):
            result = self.rotation.exchange_once(
                policy,
                Path("/unused"),
                "openai-rotation-20260807-0123456789",
                "replacement_staging",
            )
        self.assertEqual(observed_policy["issuer"]["jwks_kid"], derived["kid"])
        self.assertEqual(result["assertion_descriptor"]["kid"], derived["kid"])
        active_kid = json.loads(POLICY_PATH.read_text())["issuer"]["jwks_kid"]
        self.assertNotIn(active_kid, ROTATION_COLLECTOR_PATH.read_text())

    def test_signing_key_identifier_is_derived_from_public_der(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "synthetic.pem"
            subprocess.run(
                [
                    "/usr/bin/openssl",
                    "genpkey",
                    "-algorithm",
                    "RSA",
                    "-pkeyopt",
                    "rsa_keygen_bits:3072",
                    "-out",
                    str(key),
                ],
                check=True,
                capture_output=True,
            )
            public_der = subprocess.run(
                [
                    "/usr/bin/openssl",
                    "pkey",
                    "-in",
                    str(key),
                    "-pubout",
                    "-outform",
                    "DER",
                ],
                check=True,
                capture_output=True,
            ).stdout
            descriptor = self.rotation.BASE.load_public_jwk(key)
        expected = "patchyard-" + hashlib.sha256(public_der).hexdigest()[:16]
        self.assertEqual(descriptor["kid"], expected)
        self.assertIn("BASE.load_public_jwk", ROTATION_COLLECTOR_PATH.read_text())

    def test_console_readings_accept_printable_operator_navigation(self) -> None:
        revocation_state = json.loads(REVOCATION_FIXTURE_PATH.read_text())[
            "initial_console_reading"
        ]["state"]
        revocation_state["subject_mapping_expression"] = (
            'assertion.sub == "patchyard-control-plane"'
        )
        revocation_state["console_location"] = (
            "Settings > Organization > Workload identity"
        )
        self.assertEqual(
            self.revocation.parse_console_state(
                json.dumps(revocation_state), self.revocation.load_policy()
            ),
            revocation_state,
        )

        rotation_state = json.loads(ROTATION_FIXTURE_PATH.read_text())[
            "original_console_reading"
        ]["state"]
        rotation_state["subject_mapping_expression"] = (
            'assertion.sub == "patchyard-control-plane"'
        )
        rotation_state["console_location"] = (
            "Settings > Organization > Workload identity"
        )
        self.assertEqual(
            self.rotation.parse_console_state(
                json.dumps(rotation_state), self.rotation.load_policy()
            ),
            rotation_state,
        )

    def test_revocation_failure_after_mutation_still_drives_safe_restoration(self) -> None:
        fixture = json.loads(REVOCATION_FIXTURE_PATH.read_text())
        active = fixture["initial_console_reading"]["state"]
        disabled = fixture["mapping_mutation_attestation"]["console_readings"][
            "after"
        ]["state"]
        inputs = iter(
            (
                json.dumps(active),
                json.dumps(active),
                "MUTATION COMPLETE",
                json.dumps(disabled),
                json.dumps(disabled),
                "RESTORATION COMPLETE",
                json.dumps(active),
            )
        )
        exchange_count = 0

        def exchange(*unused):
            nonlocal exchange_count
            del unused
            exchange_count += 1
            if exchange_count == 1:
                return {"receipt": {"access_token_supplied": True}}
            raise self.revocation.RevocationCollectorError("synthetic exchange failure")

        journal: dict[str, object] = {}
        with self.assertRaises(self.revocation.RevocationCollectorError):
            self.revocation.collect(
                run_id="openai-revocation-20260807-0123456789",
                actor_name="Fixture Operator",
                actor_kind="accountable_human",
                attester_name="Fixture Operator",
                mutation_kind="disable",
                policy=self.revocation.load_policy(),
                input_fn=lambda unused: next(inputs),
                clock=TickingClock(
                    datetime(2026, 8, 7, 14, 3, 11, 123_457, timezone.utc)
                ),
                sleeper=lambda unused: None,
                exchanger=exchange,
                journal=journal,
            )
        self.assertIs(journal["safe_mapping_restored"], True)
        relationship = journal["restoration_attestation"]["party_relationship"]
        self.assertEqual(
            relationship,
            {"same_party": True, "independence": False, "corroboration": False},
        )

    def test_rotation_failure_rollback_uses_the_current_derived_key(self) -> None:
        fixture = json.loads(ROTATION_FIXTURE_PATH.read_text())
        original_reading = fixture["original_console_reading"]
        original = fixture["derived_public_key_descriptors"]["original"]
        replacement = fixture["derived_public_key_descriptors"]["replacement"]
        overlap = fixture["overlap_attestation"]["console_readings"]["after"]["state"]
        original_state = original_reading["state"]
        inputs = iter(
            (
                json.dumps(overlap),
                "SAFE ROLLBACK COMPLETE",
                json.dumps(original_state),
            )
        )
        with (
            mock.patch.object(self.rotation.BASE, "load_public_jwk", return_value={}),
            mock.patch.object(
                self.rotation.BASE, "jwk_descriptor", return_value=original
            ),
        ):
            rollback = self.rotation.capture_safe_rotation_rollback(
                actor_name="Fixture Operator",
                actor_kind="accountable_human",
                attester_name="Fixture Operator",
                policy=self.rotation.load_policy(),
                original_reading=original_reading,
                original_descriptor=original,
                replacement_descriptor=replacement,
                retirement_confirmed=False,
                input_fn=lambda unused: next(inputs),
                clock=TickingClock(
                    datetime(2026, 8, 7, 15, 20, 26, 123_457, timezone.utc)
                ),
            )
        self.assertEqual(rollback["status"], "safe_state_restored")
        self.assertEqual(rollback["active_key"], original)
        self.assertEqual(
            rollback["rollback_attestation"]["party_relationship"],
            {"same_party": True, "independence": False, "corroboration": False},
        )


class FederationRevocationCheckerContract(CheckerCase):
    checker = REVOCATION_CHECKER_PATH
    fixture_path = REVOCATION_FIXTURE_PATH

    def observed(self) -> dict[str, object]:
        value = deepcopy(self.fixture)
        del value["fixture_kind"]
        del value["fixture_lineage"]
        value["provider_response_observed"] = True
        self.observed_receipt(value["baseline_control"]["receipt"], denial=False)
        self.observed_receipt(value["denial_observation"]["receipt"], denial=True)
        self.observed_receipt(value["bracketing_control"]["receipt"], denial=False)
        return value

    def test_realistic_precision_fixture_passes_but_is_not_qualification_evidence(self) -> None:
        self.assertTrue(self.fixture["baseline_control"]["started_at"].endswith(".151337Z"))
        self.assertEqual(
            self.fixture["baseline_control"]["assertion_descriptor"]["minted_at"],
            "2026-08-07T14:03:11Z",
        )
        accepted = self.run_checker("--contract-fixture", str(self.fixture_path))
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        refused = self.run_checker("--evidence", str(self.fixture_path))
        self.assertEqual(refused.returncode, 1)
        self.assertIn("cannot be qualification evidence", refused.stderr)

    def test_arbitrary_observed_denial_shape_is_accepted_while_unenforced(self) -> None:
        result = self.run_checker(
            "--observation", str(self.write(self.observed(), "observed.json"))
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_baseline_or_bracketing_control_is_rejected(self) -> None:
        for field in ("baseline_control", "bracketing_control"):
            value = deepcopy(self.fixture)
            del value[field]
            result = self.run_checker(
                "--contract-fixture", str(self.write(value, f"missing-{field}.json"))
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("unexpected evidence shape", result.stderr)

    def test_denial_inside_settling_floor_is_rejected(self) -> None:
        value = deepcopy(self.fixture)
        value["denial_observation"]["exchange_request"]["requested_at"] = (
            "2026-08-07T14:03:13.309685Z"
        )
        value["denial_observation"]["receipt"]["request_started_at"] = (
            "2026-08-07T14:03:13.309685Z"
        )
        result = self.run_checker(
            "--contract-fixture", str(self.write(value, "early-denial.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("denial attempt falls inside the 90-second settling floor", result.stderr)

    def test_every_console_capture_bound_participates_in_utc_ordering(self) -> None:
        value = deepcopy(self.fixture)
        value["mapping_mutation_attestation"]["console_readings"]["before"][
            "captured_before_at"
        ] = "2026-08-07T14:03:11.200113Z"
        result = self.run_checker(
            "--contract-fixture", str(self.write(value, "misordered-capture.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("UTC observations are out of order", result.stderr)

    def test_undisclosed_single_party_and_premature_enforcement_are_rejected(self) -> None:
        value = deepcopy(self.fixture)
        value["mapping_mutation_attestation"]["party_relationship"]["same_party"] = False
        result = self.run_checker(
            "--contract-fixture", str(self.write(value, "party.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not disclose role occupancy", result.stderr)

        enforced = deepcopy(self.fixture)
        enforced["response_predicate"]["enforced"] = True
        result = self.run_checker(
            "--contract-fixture", str(self.write(enforced, "enforced.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("predicate was enforced before observation", result.stderr)

    def test_exact_keys_credentials_and_isolation_fail_closed(self) -> None:
        extra = deepcopy(self.fixture)
        extra["unexpected"] = False
        result = self.run_checker(
            "--contract-fixture", str(self.write(extra, "extra-key.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected evidence shape", result.stderr)

        type_confused = deepcopy(self.fixture)
        type_confused["baseline_control"]["attempt_count"] = True
        result = self.run_checker(
            "--contract-fixture", str(self.write(type_confused, "boolean-count.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("was not exactly one attempt", result.stderr)

        credential = deepcopy(self.fixture)
        credential["denial_observation"]["receipt"]["request_id"] = (
            "eyJsynthetic.payload.signature"
        )
        result = self.run_checker(
            "--contract-fixture", str(self.write(credential, "credential.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("credential-shaped material", result.stderr)
        result = self.run_checker("--allow-missing-results", isolated=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires python3 -I", result.stderr)


class SigningKeyRotationCheckerContract(CheckerCase):
    checker = ROTATION_CHECKER_PATH
    fixture_path = ROTATION_FIXTURE_PATH

    def exchange_values(self, value: dict[str, object]) -> list[tuple[dict[str, object], bool]]:
        bracket = value["a129_bracket"]
        return [
            (value["baseline_control"], False),
            (value["overlap_positive_control"], False),
            (bracket["bracketing_control_before_denial"], False),
            (bracket["denial_observation"], True),
            (bracket["bracketing_control_after_denial"], False),
        ]

    def observed(self) -> dict[str, object]:
        value = deepcopy(self.fixture)
        del value["fixture_kind"]
        del value["fixture_lineage"]
        value["provider_response_observed"] = True
        for exchange, denial in self.exchange_values(value):
            self.observed_receipt(exchange["receipt"], denial=denial)
        return value

    def test_realistic_precision_fixture_passes_but_is_not_qualification_evidence(self) -> None:
        self.assertTrue(self.fixture["baseline_control"]["started_at"].endswith(".151337Z"))
        self.assertEqual(
            self.fixture["baseline_control"]["assertion_descriptor"]["minted_at"],
            "2026-08-07T15:17:23Z",
        )
        accepted = self.run_checker("--contract-fixture", str(self.fixture_path))
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        refused = self.run_checker("--evidence", str(self.fixture_path))
        self.assertEqual(refused.returncode, 1)
        self.assertIn("cannot be qualification evidence", refused.stderr)

    def test_arbitrary_observed_denial_shape_is_accepted_while_unenforced(self) -> None:
        result = self.run_checker(
            "--observation", str(self.write(self.observed(), "observed.json"))
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_baseline_or_either_bracketing_control_is_rejected(self) -> None:
        baseline = deepcopy(self.fixture)
        del baseline["baseline_control"]
        result = self.run_checker(
            "--contract-fixture", str(self.write(baseline, "missing-baseline.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected evidence shape", result.stderr)

        for field in (
            "bracketing_control_before_denial",
            "bracketing_control_after_denial",
        ):
            value = deepcopy(self.fixture)
            del value["a129_bracket"][field]
            result = self.run_checker(
                "--contract-fixture", str(self.write(value, f"missing-{field}.json"))
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("unexpected evidence shape", result.stderr)

    def test_denial_inside_settling_floor_is_rejected(self) -> None:
        value = deepcopy(self.fixture)
        denial = value["a129_bracket"]["denial_observation"]
        denial["exchange_request"]["requested_at"] = "2026-08-07T15:18:56.624043Z"
        denial["receipt"]["request_started_at"] = "2026-08-07T15:18:56.624043Z"
        result = self.run_checker(
            "--contract-fixture", str(self.write(value, "early-denial.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("denial attempt falls inside the 90-second settling floor", result.stderr)

    def test_every_console_capture_bound_participates_in_utc_ordering(self) -> None:
        value = deepcopy(self.fixture)
        value["overlap_attestation"]["console_readings"]["before"][
            "captured_before_at"
        ] = "2026-08-07T15:17:23.200113Z"
        result = self.run_checker(
            "--contract-fixture", str(self.write(value, "misordered-capture.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("UTC observations are out of order", result.stderr)

    def test_single_party_premature_enforcement_and_credentials_are_rejected(self) -> None:
        extra = deepcopy(self.fixture)
        extra["unexpected"] = False
        result = self.run_checker(
            "--contract-fixture", str(self.write(extra, "extra-key.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected evidence shape", result.stderr)

        type_confused = deepcopy(self.fixture)
        type_confused["baseline_control"]["receipt"]["access_token_supplied"] = 1
        result = self.run_checker(
            "--contract-fixture", str(self.write(type_confused, "integer-bool.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("bearer presence is not boolean", result.stderr)

        party = deepcopy(self.fixture)
        party["retirement_attestation"]["party_relationship"]["same_party"] = False
        result = self.run_checker(
            "--contract-fixture", str(self.write(party, "party.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not disclose role occupancy", result.stderr)

        enforced = deepcopy(self.fixture)
        enforced["response_predicate"]["enforced"] = True
        result = self.run_checker(
            "--contract-fixture", str(self.write(enforced, "enforced.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("predicate was enforced before observation", result.stderr)

        credential = deepcopy(self.fixture)
        credential["a129_bracket"]["denial_observation"]["receipt"]["request_id"] = (
            "sk-syntheticcredentialshapedvalue"
        )
        result = self.run_checker(
            "--contract-fixture", str(self.write(credential, "credential.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("credential-shaped material", result.stderr)

    def test_checker_requires_isolated_python(self) -> None:
        result = self.run_checker("--allow-missing-results", isolated=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires python3 -I", result.stderr)


if __name__ == "__main__":
    unittest.main()
