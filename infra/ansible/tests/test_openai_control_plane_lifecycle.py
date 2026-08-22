from __future__ import annotations

import contextlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock
import urllib.error


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


class AdvancingClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        observed = self.value
        self.value += timedelta(seconds=1)
        return observed

    def sleep(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


def iso_time(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def retime_exchange(
    template: dict[str, object],
    *,
    key_role: str,
    denial: bool,
    request_id: str,
    clock: AdvancingClock,
) -> dict[str, object]:
    value = deepcopy(template)
    started = clock()
    issued = started.replace(microsecond=0)
    requested = started + timedelta(milliseconds=100)
    observed = started + timedelta(milliseconds=200)
    removed = started + timedelta(milliseconds=300)
    value["key_role"] = key_role
    value["started_at"] = iso_time(started)
    value["assertion_descriptor"].update(
        {
            "issued_at": iso_time(issued),
            "minted_at": iso_time(issued),
            "expires_at": iso_time(issued + timedelta(seconds=300)),
        }
    )
    value["exchange_request"]["requested_at"] = iso_time(requested)
    value["receipt"].update(
        {
            "source": "openai_http_response",
            "http_status": 401 if denial else 200,
            "request_started_at": iso_time(requested),
            "observed_at": iso_time(observed),
            "provider_date": iso_time(issued),
            "request_id": request_id,
            "request_id_supplied": True,
            "content_type": "application/json",
            "body_bytes": 2,
            "body_format": "json_object",
            "response_shape": {
                "body_kind": "json_object",
                "top_level_fields": [],
                "error_fields": [],
            },
            "access_token_supplied": not denial,
            "token_type": None if denial else "Bearer",
            "expires_in": None if denial else 300,
            "error_type": "synthetic_denial" if denial else None,
        }
    )
    value["credential_removed_at"] = iso_time(removed)
    return value


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
                "http_status": 401 if denial else 299,
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

    def test_rotation_loads_attestation_and_revocation_does_not(self) -> None:
        expected = digest(ATTESTATION_PATH)
        self.assertEqual(self.rotation.ATTESTATION_DEFINITION_SHA256, expected)
        self.assertFalse(hasattr(self.revocation, "ATTESTATION_DEFINITION_SHA256"))
        self.assertEqual(
            self.revocation.LIFECYCLE_INSTRUMENT_SHA256,
            "88117660a2717ecd2c9b6eef4704066700e4989e1010d508769bf928fec18c8b",
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

    def test_party_names_fail_before_the_rotation_window_opens(self) -> None:
        with self.assertRaises(self.rotation.ATTESTATION.AttestationShapeError):
            self.rotation.collect(
                run_id="openai-rotation-20260807-0123456789",
                actor_name="invalid\nactor",
                actor_kind="accountable_human",
                attester_name="Fixture Operator",
                policy=self.rotation.load_policy(),
                stage=Path("/unused"),
                input_fn=lambda unused: self.fail("capture opened"),
            )

    def authorization_for(self, run_id: str) -> dict[str, object]:
        fixture = json.loads(REVOCATION_FIXTURE_PATH.read_text())
        authorization = deepcopy(fixture["human_authorization"])
        extracted = dict(authorization["extracted"])
        extracted["run_id"] = run_id
        extracted["collector_sha256"] = digest(REVOCATION_COLLECTOR_PATH)
        extracted["policy_sha256"] = digest(POLICY_PATH)
        fence = json.dumps(extracted, indent=2, sort_keys=True)
        authorization["extracted"] = extracted
        authorization["body"] = (
            "Authorize one OpenAI requirement-4 attended run.\n\n"
            f"```json\n{fence}\n```\n"
        )
        return authorization

    def test_revocation_authorization_fails_before_the_window_opens(self) -> None:
        authorization = self.authorization_for(
            "openai-revocation-20260807-0123456789"
        )
        authorization["author_login"] = "not-jacob"
        with self.assertRaises(self.revocation.RevocationCollectorError) as caught:
            self.revocation.collect(
                run_id="openai-revocation-20260807-0123456789",
                authorization=authorization,
                model_identity={
                    "pairing": authorization["extracted"]["pairing"],
                    "codex_task_id": authorization["extracted"]["codex_task_id"],
                },
                mutation_kind="subject-expression",
                policy=self.revocation.load_policy(),
                input_fn=lambda unused: self.fail("capture opened"),
            )
        self.assertIn("author is not the accountable human", str(caught.exception))

    def route_authorization(self) -> dict[str, object]:
        return {
            "source": "route authorization",
            "ruling": "A148",
            "map_url": (
                "https://github.com/JacobStephens2/patchyard/issues/176"
            ),
            "grant_url": (
                "https://github.com/JacobStephens2/patchyard/issues/253"
            ),
            "author_login": "JacobStephens2",
            "human_attestation_obtained": False,
            "human_authorship_mechanically_proven": False,
        }

    def test_route_authorization_is_accepted_before_the_window_opens(self) -> None:
        opened: list[str] = []

        def input_fn(prompt: str) -> str:
            opened.append(prompt)
            raise self.revocation.RevocationCollectorError("capture opened")

        with self.assertRaises(self.revocation.RevocationCollectorError) as caught:
            self.revocation.collect(
                run_id="openai-revocation-20260807-0123456789",
                authorization=self.route_authorization(),
                model_identity={
                    "pairing": "openai/codex/gpt-5.6-sol/xhigh",
                    "codex_task_id": "task_synthetic_req4_0001",
                },
                mutation_kind="subject-expression",
                policy=self.revocation.load_policy(),
                input_fn=input_fn,
            )
        self.assertEqual(str(caught.exception), "capture opened")
        self.assertTrue(opened)

    def test_route_authorization_rejects_a_human_attestation_claim(self) -> None:
        authorization = self.route_authorization()
        authorization["human_attestation_obtained"] = True
        with self.assertRaises(self.revocation.RevocationCollectorError) as caught:
            self.revocation.collect(
                run_id="openai-revocation-20260807-0123456789",
                authorization=authorization,
                model_identity={
                    "pairing": "openai/codex/gpt-5.6-sol/xhigh",
                    "codex_task_id": "task_synthetic_req4_0001",
                },
                mutation_kind="subject-expression",
                policy=self.revocation.load_policy(),
                input_fn=lambda unused: self.fail("capture opened"),
            )
        self.assertIn("claims a human attestation", str(caught.exception))

    def test_revocation_collector_result_passes_its_checker(self) -> None:
        fixture = json.loads(REVOCATION_FIXTURE_PATH.read_text())
        states = iter(
            observation["state"]
            for observation in fixture["model_console_observations"]
        )
        actions = iter(fixture["model_actions"])

        def input_fn(prompt: str) -> str:
            if "RELOADED" in prompt:
                return "RELOADED"
            if "console reading JSON" in prompt:
                return json.dumps(next(states))
            if "MUTATION COMPLETE" in prompt:
                return "MUTATION COMPLETE"
            if "RESTORATION COMPLETE" in prompt:
                return "RESTORATION COMPLETE"
            if "save confirmation JSON" in prompt:
                confirmation = next(actions)["confirmation"]
                return json.dumps(
                    {
                        key: confirmation[key]
                        for key in (
                            "product_approval_presented",
                            "product_approval_completed",
                            "capture_sha256",
                            "observed_expression",
                        )
                    }
                )
            self.fail(f"unexpected collector prompt: {prompt}")

        clock = AdvancingClock(
            datetime(2026, 8, 7, 14, 0, 0, tzinfo=timezone.utc)
        )
        templates = iter(
            (
                (fixture["baseline_control"], False),
                (fixture["denial_observation"], True),
                (fixture["bracketing_control"], False),
            )
        )
        exchange_count = 0

        def exchange(unused_policy, unused_key, unused_run_id, key_role):
            nonlocal exchange_count
            del unused_policy, unused_key, unused_run_id
            exchange_count += 1
            template, denial = next(templates)
            return retime_exchange(
                template,
                key_role=key_role,
                denial=denial,
                request_id=f"req_roundtrip_revocation_{exchange_count}",
                clock=clock,
            )

        result = self.revocation.collect(
            run_id=fixture["run_id"],
            authorization=self.route_authorization(),
            model_identity={
                "pairing": "openai/codex/gpt-5.6-sol/xhigh",
                "codex_task_id": "task_synthetic_req4_0001",
            },
            mutation_kind="subject-expression",
            policy=self.revocation.load_policy(),
            input_fn=input_fn,
            clock=clock,
            sleeper=clock.sleep,
            exchanger=exchange,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "revocation-collector-result.json"
            path.write_text(json.dumps(result))
            checked = subprocess.run(
                [
                    "python3",
                    "-I",
                    str(REVOCATION_CHECKER_PATH),
                    "--evidence",
                    str(path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_rotation_collector_result_passes_its_checker(self) -> None:
        fixture = json.loads(ROTATION_FIXTURE_PATH.read_text())
        original = fixture["derived_public_key_descriptors"]["original"]
        replacement = fixture["derived_public_key_descriptors"]["replacement"]
        states = iter(
            (
                fixture["original_console_reading"]["state"],
                fixture["overlap_attestation"]["console_readings"]["before"]["state"],
                fixture["overlap_attestation"]["console_readings"]["after"]["state"],
                fixture["retirement_attestation"]["console_readings"]["before"]["state"],
                fixture["retirement_attestation"]["console_readings"]["after"]["state"],
            )
        )

        def input_fn(prompt: str) -> str:
            if "console reading JSON" in prompt:
                return json.dumps(next(states))
            for acknowledgement in (
                "OVERLAP COMPLETE",
                "ACTIVATE LOCALLY",
                "RETIREMENT COMPLETE",
            ):
                if acknowledgement in prompt:
                    return acknowledgement
            self.fail(f"unexpected collector prompt: {prompt}")

        clock = AdvancingClock(
            datetime(2026, 8, 7, 15, 0, 0, tzinfo=timezone.utc)
        )
        bracket = fixture["a129_bracket"]
        templates = iter(
            (
                (fixture["baseline_control"], False),
                (fixture["overlap_positive_control"], False),
                (bracket["bracketing_control_before_denial"], False),
                (bracket["denial_observation"], True),
                (bracket["bracketing_control_after_denial"], False),
            )
        )
        exchange_count = 0

        def exchange(unused_policy, unused_key, unused_run_id, key_role):
            nonlocal exchange_count
            del unused_policy, unused_key, unused_run_id
            exchange_count += 1
            template, denial = next(templates)
            return retime_exchange(
                template,
                key_role=key_role,
                denial=denial,
                request_id=f"req_roundtrip_rotation_{exchange_count}",
                clock=clock,
            )

        def activate(*unused):
            del unused
            activation = deepcopy(fixture["local_activation"])
            activation["observed_at"] = iso_time(clock())
            return activation, Path("/unused-retired")

        with (
            mock.patch.object(self.rotation.BASE, "load_public_jwk", return_value={}),
            mock.patch.object(
                self.rotation.BASE, "jwk_descriptor", return_value=original
            ),
        ):
            result = self.rotation.collect(
                run_id=fixture["run_id"],
                actor_name="Fixture Operator",
                actor_kind="accountable_human",
                attester_name="Fixture Operator",
                policy=self.rotation.load_policy(),
                stage=Path("/unused"),
                input_fn=input_fn,
                clock=clock,
                sleeper=clock.sleep,
                exchanger=exchange,
                key_generator=lambda unused: deepcopy(replacement),
                activator=activate,
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rotation-collector-result.json"
            path.write_text(json.dumps(result))
            checked = subprocess.run(
                [
                    "python3",
                    "-I",
                    str(ROTATION_CHECKER_PATH),
                    "--observation",
                    str(path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_rotation_exchange_supplies_the_transitional_kid(self) -> None:
        """A145: the collector passes the derived kid explicitly and the
        frozen policy flows through unpatched."""
        policy = json.loads(POLICY_PATH.read_text())
        derived = {
            "kid": "patchyard-bbbbbbbbbbbbbbbb",
            "jwk_thumbprint_sha256": "cd" * 32,
        }
        observed: dict[str, object] = {}

        def exchange(
            runtime_policy, signing_key, run_id, started_at, expected_kid=None
        ):
            del signing_key, run_id
            observed["policy"] = runtime_policy
            observed["expected_kid"] = expected_kid
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
        self.assertEqual(observed["expected_kid"], derived["kid"])
        self.assertEqual(observed["policy"], policy)
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
            "model_console_observations"
        ][0]["state"]
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

    def test_rotation_readings_canonicalise_public_key_order(self) -> None:
        overlap = json.loads(ROTATION_FIXTURE_PATH.read_text())[
            "overlap_attestation"
        ]["console_readings"]["after"]["state"]
        self.assertEqual(len(overlap["public_keys"]), 2)
        reversed_reading = deepcopy(overlap)
        reversed_reading["public_keys"] = list(
            reversed(reversed_reading["public_keys"])
        )
        parsed = self.rotation.parse_console_state(
            json.dumps(reversed_reading), self.rotation.load_policy()
        )
        self.assertEqual(parsed, overlap)

        duplicated = deepcopy(overlap)
        duplicated["public_keys"] = [
            overlap["public_keys"][0],
            deepcopy(overlap["public_keys"][0]),
        ]
        with self.assertRaises(self.rotation.RotationCollectorError) as caught:
            self.rotation.parse_console_state(
                json.dumps(duplicated), self.rotation.load_policy()
            )
        self.assertIn("not unique", str(caught.exception))

    def test_rollback_reading_is_reprompted_on_malformed_input(self) -> None:
        fixture = json.loads(ROTATION_FIXTURE_PATH.read_text())
        original_reading = fixture["original_console_reading"]
        original = fixture["derived_public_key_descriptors"]["original"]
        replacement = fixture["derived_public_key_descriptors"]["replacement"]
        overlap = fixture["overlap_attestation"]["console_readings"]["after"]["state"]
        original_state = original_reading["state"]
        inputs = iter(
            (
                "not even JSON",
                json.dumps(overlap),
                "SAFE ROLLBACK COMPLETE",
                '{"wrong_shape": true}',
                json.dumps(original_state),
            )
        )
        stderr = io.StringIO()
        with (
            mock.patch.object(self.rotation.BASE, "load_public_jwk", return_value={}),
            mock.patch.object(
                self.rotation.BASE, "jwk_descriptor", return_value=original
            ),
            contextlib.redirect_stderr(stderr),
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
        self.assertEqual(
            stderr.getvalue().count("Reading not accepted during recovery"), 2
        )

    def test_upload_material_is_printed_and_public_only(self) -> None:
        fixture = json.loads(ROTATION_FIXTURE_PATH.read_text())
        descriptors = fixture["derived_public_key_descriptors"]
        active_jwk = {"kid": descriptors["original"]["kid"], "kty": "RSA"}
        replacement_jwk = {"kid": descriptors["replacement"]["kid"], "kty": "RSA"}
        stderr = io.StringIO()
        with (
            mock.patch.object(
                self.rotation.BASE,
                "load_public_jwk",
                return_value=replacement_jwk,
            ),
            contextlib.redirect_stderr(stderr),
        ):
            self.rotation.print_upload_material(
                active_jwk, Path("/unused"), descriptors
            )
        printed = stderr.getvalue()
        self.assertIn(descriptors["original"]["kid"], printed)
        self.assertIn(descriptors["replacement"]["kid"], printed)
        self.assertIn(
            descriptors["replacement"]["jwk_thumbprint_sha256"], printed
        )
        self.assertIn("Two-key overlap JWKS", printed)
        self.assertNotIn("PRIVATE KEY", printed)

    def test_revocation_failure_after_mutation_still_drives_safe_restoration(self) -> None:
        fixture = json.loads(REVOCATION_FIXTURE_PATH.read_text())
        run_id = "openai-revocation-20260807-0123456789"
        active = fixture["model_console_observations"][0]["state"]
        revoked = deepcopy(active)
        revoked["subject_mapping_expression"] = self.revocation.revocation_sentinel(
            run_id
        )
        confirmation = json.dumps(
            {
                "product_approval_presented": False,
                "product_approval_completed": False,
                "capture_sha256": None,
                "observed_expression": revoked["subject_mapping_expression"],
            }
        )
        restore_confirmation = json.dumps(
            {
                "product_approval_presented": False,
                "product_approval_completed": False,
                "capture_sha256": None,
                "observed_expression": active["subject_mapping_expression"],
            }
        )
        inputs = iter(
            (
                "RELOADED",
                json.dumps(active),
                "RELOADED",
                json.dumps(active),
                "MUTATION COMPLETE",
                confirmation,
                "RELOADED",
                json.dumps(revoked),
                "RELOADED",
                json.dumps(revoked),
                "RESTORATION COMPLETE",
                restore_confirmation,
                "RELOADED",
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
        authorization = self.authorization_for(run_id)
        with self.assertRaises(self.revocation.RevocationCollectorError):
            self.revocation.collect(
                run_id=run_id,
                authorization=authorization,
                model_identity={
                    "pairing": authorization["extracted"]["pairing"],
                    "codex_task_id": authorization["extracted"]["codex_task_id"],
                },
                mutation_kind="subject-expression",
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
        self.assertEqual(len(journal["model_actions"]), 2)
        self.assertEqual(
            journal["model_actions"][1]["kind"],
            "subject_expression_restore_save",
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

    def test_overlap_positive_retry_journals_every_receipt(self) -> None:
        supplied = iter((False, True))
        roles: list[str] = []

        def exchange(policy, signing_key, run_id, key_role):
            del policy, signing_key, run_id
            roles.append(key_role)
            return {
                "receipt": {"access_token_supplied": next(supplied)},
                "attempt_count": 1,
            }

        journal: dict[str, object] = {}
        sleeps: list[float] = []
        result = self.rotation.overlap_positive_with_retry(
            self.rotation.load_policy(),
            Path("/unused"),
            "openai-rotation-20260807-0123456789",
            journal,
            exchanger=exchange,
            sleeper=sleeps.append,
        )
        self.assertEqual(result["attempt_count"], 2)
        self.assertIs(journal["overlap_positive_control"], result)
        self.assertEqual(
            [attempt["attempt_count"] for attempt in journal["overlap_positive_attempts"]],
            [1, 2],
        )
        self.assertIs(
            journal["overlap_positive_attempts"][0]["receipt"][
                "access_token_supplied"
            ],
            False,
        )
        self.assertEqual(sleeps, [90.0])
        self.assertEqual(roles, ["replacement_staging", "replacement_staging"])

    def test_exhausted_overlap_positive_retry_preserves_the_failing_receipt(self) -> None:
        def exchange(policy, signing_key, run_id, key_role):
            del policy, signing_key, run_id, key_role
            return {
                "receipt": {"access_token_supplied": False, "http_status": 401},
                "attempt_count": 1,
            }

        journal: dict[str, object] = {}
        sleeps: list[float] = []
        with self.assertRaises(self.rotation.RotationCollectorError) as caught:
            self.rotation.overlap_positive_with_retry(
                self.rotation.load_policy(),
                Path("/unused"),
                "openai-rotation-20260807-0123456789",
                journal,
                exchanger=exchange,
                sleeper=sleeps.append,
            )
        self.assertIn("did not supply a bearer", str(caught.exception))
        bound = self.rotation.OVERLAP_POSITIVE_MAX_ATTEMPTS
        self.assertEqual(len(journal["overlap_positive_attempts"]), bound)
        self.assertEqual(
            journal["overlap_positive_control"]["receipt"]["http_status"], 401
        )
        self.assertEqual(sleeps, [90.0] * (bound - 1))

    def test_failed_baseline_receipt_is_journaled_before_the_requirement(self) -> None:
        fixture = json.loads(ROTATION_FIXTURE_PATH.read_text())
        original_reading = fixture["original_console_reading"]
        original = fixture["derived_public_key_descriptors"]["original"]
        inputs = iter((json.dumps(original_reading["state"]),))

        def exchange(*unused):
            del unused
            return {"receipt": {"access_token_supplied": False, "http_status": 401}}

        journal: dict[str, object] = {}
        with (
            mock.patch.object(self.rotation.BASE, "load_public_jwk", return_value={}),
            mock.patch.object(
                self.rotation.BASE, "jwk_descriptor", return_value=original
            ),
        ):
            with self.assertRaises(self.rotation.RotationCollectorError) as caught:
                self.rotation.collect(
                    run_id="openai-rotation-20260807-0123456789",
                    actor_name="Fixture Operator",
                    actor_kind="accountable_human",
                    attester_name="Fixture Operator",
                    policy=self.rotation.load_policy(),
                    stage=Path("/unused"),
                    input_fn=lambda unused: next(inputs),
                    clock=TickingClock(
                        datetime(2026, 8, 7, 15, 17, 23, 123_457, timezone.utc)
                    ),
                    sleeper=lambda unused: None,
                    exchanger=exchange,
                    journal=journal,
                )
        self.assertIn("baseline control did not supply a bearer", str(caught.exception))
        self.assertEqual(
            journal["baseline_control"]["receipt"]["http_status"], 401
        )

    def test_failed_bracket_receipts_are_journaled_before_the_requirement(self) -> None:
        fixture = json.loads(ROTATION_FIXTURE_PATH.read_text())
        original = fixture["derived_public_key_descriptors"]["original"]
        replacement = fixture["derived_public_key_descriptors"]["replacement"]
        original_state = fixture["original_console_reading"]["state"]
        overlap_before = fixture["overlap_attestation"]["console_readings"][
            "before"
        ]["state"]
        overlap_after = fixture["overlap_attestation"]["console_readings"][
            "after"
        ]["state"]
        retirement_before = fixture["retirement_attestation"]["console_readings"][
            "before"
        ]["state"]
        retirement_after = fixture["retirement_attestation"]["console_readings"][
            "after"
        ]["state"]
        inputs = iter(
            (
                json.dumps(original_state),
                json.dumps(overlap_before),
                "OVERLAP COMPLETE",
                json.dumps(overlap_after),
                "ACTIVATE LOCALLY",
                json.dumps(retirement_before),
                "RETIREMENT COMPLETE",
                json.dumps(retirement_after),
            )
        )
        supplied = iter((True, True, True, False, False))

        def exchange(policy, signing_key, run_id, key_role):
            del policy, signing_key, run_id
            return {
                "key_role": key_role,
                "receipt": {"access_token_supplied": next(supplied)},
                "attempt_count": 1,
            }

        journal: dict[str, object] = {}
        with (
            mock.patch.object(self.rotation.BASE, "load_public_jwk", return_value={}),
            mock.patch.object(
                self.rotation.BASE, "jwk_descriptor", return_value=original
            ),
        ):
            with self.assertRaises(self.rotation.RotationCollectorError) as caught:
                self.rotation.collect(
                    run_id="openai-rotation-20260807-0123456789",
                    actor_name="Fixture Operator",
                    actor_kind="accountable_human",
                    attester_name="Fixture Operator",
                    policy=self.rotation.load_policy(),
                    stage=Path("/unused"),
                    input_fn=lambda unused: next(inputs),
                    clock=TickingClock(
                        datetime(2026, 8, 7, 15, 17, 23, 123_457, timezone.utc)
                    ),
                    sleeper=lambda unused: None,
                    exchanger=exchange,
                    key_generator=lambda unused: deepcopy(replacement),
                    activator=lambda *unused: (
                        {"synthetic": True},
                        Path("/unused-retired"),
                    ),
                    journal=journal,
                )
        self.assertIn(
            "post-denial bracketing control did not supply a bearer",
            str(caught.exception),
        )
        bracket = journal["a129_bracket"]
        self.assertEqual(
            set(bracket),
            {
                "bracketing_control_before_denial",
                "denial_observation",
                "bracketing_control_after_denial",
            },
        )
        self.assertEqual(bracket["denial_observation"]["key_role"], "original_retired")
        self.assertIs(
            bracket["bracketing_control_after_denial"]["receipt"][
                "access_token_supplied"
            ],
            False,
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
        # A149's reviewed predicate: an observed revocation denial is HTTP 401
        # with no bearer. The error type stays arbitrary here on purpose - it is
        # deliberately not pinned.
        value["denial_observation"]["receipt"]["http_status"] = 401
        value["denial_observation"]["receipt"]["access_token_supplied"] = False
        value["response_predicate"] = {
            "enforced": True,
            "http_status": 401,
            "access_token_supplied": False,
            "basis": "observed-openai-federation-revocation-response",
        }
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

    def test_reviewed_predicate_accepts_401_without_a_bearer(self) -> None:
        value = self.observed()
        result = self.run_checker(
            "--observation", str(self.write(value, "observed.json"))
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        value["qualification_evidence"] = True
        evidenced = self.run_checker(
            "--evidence", str(self.write(value, "evidence.json"))
        )
        self.assertEqual(evidenced.returncode, 0, evidenced.stderr)

    def test_reviewed_predicate_rejects_non_401_or_a_bearer(self) -> None:
        wrong_status = self.observed()
        wrong_status["denial_observation"]["receipt"]["http_status"] = 418
        result = self.run_checker(
            "--observation", str(self.write(wrong_status, "wrong-status.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("was not HTTP 401", result.stderr)

        with_bearer = self.observed()
        with_bearer["denial_observation"]["receipt"]["access_token_supplied"] = True
        result = self.run_checker(
            "--observation", str(self.write(with_bearer, "bearer.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("supplied a bearer", result.stderr)

    def test_unenforced_predicate_is_refused_on_an_observation(self) -> None:
        value = self.observed()
        value["response_predicate"] = {
            "enforced": False,
            "basis": "no-observed-openai-federation-revocation-response",
        }
        result = self.run_checker(
            "--observation", str(self.write(value, "unenforced.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "predicate does not match the reviewed revocation denial", result.stderr
        )

    def test_banked_result_is_qualification_evidence(self) -> None:
        defaulted = self.run_checker()
        self.assertEqual(defaulted.returncode, 0, defaulted.stderr)
        self.assertIn("qualification evidence", defaulted.stdout)
        evidenced = self.run_checker(
            "--evidence",
            str(ROOT / "research/isolation/results/openai-federation-revocation.json"),
        )
        self.assertEqual(evidenced.returncode, 0, evidenced.stderr)
        self.assertIn("qualification evidence", evidenced.stdout)

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
        value["model_console_observations"][1]["captured_before_at"] = (
            "2026-08-07T14:03:11.200113Z"
        )
        result = self.run_checker(
            "--contract-fixture", str(self.write(value, "misordered-capture.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("UTC observations are out of order", result.stderr)

    def test_attestation_keys_operator_capture_and_enforcement_are_rejected(self) -> None:
        value = deepcopy(self.fixture)
        value["attester"] = {"kind": "accountable_human", "name": "nobody"}
        result = self.run_checker(
            "--contract-fixture", str(self.write(value, "attester.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected evidence shape", result.stderr)

        capture = deepcopy(self.fixture)
        capture["model_console_observations"][0]["capture_method"] = (
            "operator_console_readback_bounded_by_control_plane_utc"
        )
        result = self.run_checker(
            "--contract-fixture", str(self.write(capture, "operator-capture.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("operator capture method", result.stderr)

        authored = deepcopy(self.fixture)
        authored["human_authorization"]["human_attestation_obtained"] = True
        result = self.run_checker(
            "--contract-fixture", str(self.write(authored, "attested.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("claims a human attestation", result.stderr)

        enforced = deepcopy(self.fixture)
        enforced["response_predicate"]["enforced"] = True
        result = self.run_checker(
            "--contract-fixture", str(self.write(enforced, "enforced.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("predicate was enforced before observation", result.stderr)

        unloaded = deepcopy(self.fixture)
        unloaded["model_console_observations"][0]["navigation"]["reloaded"] = False
        result = self.run_checker(
            "--contract-fixture", str(self.write(unloaded, "no-reload.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("was not reloaded", result.stderr)

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

    def route_authorized(self, value: dict[str, object]) -> dict[str, object]:
        authorized = deepcopy(value)
        authorized["human_authorization"] = {
            "source": "route authorization",
            "ruling": "A148",
            "map_url": (
                "https://github.com/JacobStephens2/patchyard/issues/176"
            ),
            "grant_url": (
                "https://github.com/JacobStephens2/patchyard/issues/253"
            ),
            "author_login": "JacobStephens2",
            "human_attestation_obtained": False,
            "human_authorship_mechanically_proven": False,
        }
        authorized["authorization_rulings"] = [
            "A129",
            "A132",
            "A133",
            "A136",
            "A146",
            "A148",
        ]
        return authorized

    def test_route_authorization_fixture_passes(self) -> None:
        result = self.run_checker(
            "--contract-fixture",
            str(self.write(self.route_authorized(self.fixture), "route-auth.json")),
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_route_authorization_that_claims_attestation_is_rejected(self) -> None:
        value = self.route_authorized(self.fixture)
        value["human_authorization"]["human_attestation_obtained"] = True
        result = self.run_checker(
            "--contract-fixture",
            str(self.write(value, "route-attested.json")),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("claims a human attestation", result.stderr)


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
        value["response_predicate"] = {
            "enforced": True,
            "http_status": 401,
            "access_token_supplied": False,
            "basis": "observed-openai-retired-signing-key-response",
        }
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

    def test_reviewed_predicate_accepts_401_without_a_bearer(self) -> None:
        value = self.observed()
        result = self.run_checker(
            "--observation", str(self.write(value, "observed.json"))
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        value["qualification_evidence"] = True
        evidenced = self.run_checker(
            "--evidence", str(self.write(value, "evidence.json"))
        )
        self.assertEqual(evidenced.returncode, 0, evidenced.stderr)

    def test_reviewed_predicate_rejects_non_401_or_a_bearer(self) -> None:
        wrong_status = self.observed()
        wrong_status["a129_bracket"]["denial_observation"]["receipt"][
            "http_status"
        ] = 418
        result = self.run_checker(
            "--observation", str(self.write(wrong_status, "wrong-status.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("was not HTTP 401", result.stderr)

        with_bearer = self.observed()
        with_bearer["a129_bracket"]["denial_observation"]["receipt"][
            "access_token_supplied"
        ] = True
        result = self.run_checker(
            "--observation", str(self.write(with_bearer, "bearer.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("supplied a bearer", result.stderr)

    def test_banked_result_is_qualification_evidence(self) -> None:
        defaulted = self.run_checker()
        self.assertEqual(defaulted.returncode, 0, defaulted.stderr)
        self.assertIn("qualification evidence", defaulted.stdout)
        evidenced = self.run_checker(
            "--evidence",
            str(ROOT / "research/isolation/results/openai-signing-key-rotation.json"),
        )
        self.assertEqual(evidenced.returncode, 0, evidenced.stderr)
        self.assertIn("qualification evidence", evidenced.stdout)

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

    def test_overlap_positive_control_accepts_only_a_bounded_retry(self) -> None:
        retried = deepcopy(self.fixture)
        retried["overlap_positive_control"]["attempt_count"] = 4
        result = self.run_checker(
            "--contract-fixture", str(self.write(retried, "retried.json"))
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        exhausted = deepcopy(self.fixture)
        exhausted["overlap_positive_control"]["attempt_count"] = 5
        result = self.run_checker(
            "--contract-fixture", str(self.write(exhausted, "exhausted.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("attempt count is outside the bounded retry", result.stderr)

        baseline = deepcopy(self.fixture)
        baseline["baseline_control"]["attempt_count"] = 2
        result = self.run_checker(
            "--contract-fixture", str(self.write(baseline, "retried-baseline.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("baseline control was not exactly one attempt", result.stderr)

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


class SpendRouteAuthorizationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = load_source(
            "openai_spend_evidence_contract",
            ROOT / "tools/openai-spend-evidence.py",
        )

    def route_attestation(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "provider": "openai",
            "authorization_ruling": "A148",
            "human_authorization": {
                "source": "route authorization",
                "ruling": "A148",
                "map_url": (
                    "https://github.com/JacobStephens2/patchyard/issues/176"
                ),
                "grant_url": (
                    "https://github.com/JacobStephens2/patchyard/issues/253"
                ),
                "author_login": "JacobStephens2",
                "human_attestation_obtained": False,
                "human_authorship_mechanically_proven": False,
            },
            "mutation_surface": "organization-limits-console",
            "mutation_receipt_obtained": False,
            "mutations": [
                {"phase": "temporary_refusal", "change": "Set monthly limit to $0.01 and enforce ON"},
                {"phase": "restored_acceptance", "change": "Restore monthly limit to $100.00 and enforce OFF"},
            ],
        }

    def test_route_authorization_is_accepted(self) -> None:
        accepted = self.evidence.validate_attestation(self.route_attestation())
        self.assertEqual(accepted["authorization_ruling"], "A148")
        self.assertEqual(
            accepted["human_authorization"]["source"], "route authorization"
        )

    def test_route_authorization_rejects_a_human_attestation_claim(self) -> None:
        value = self.route_attestation()
        value["human_authorization"]["human_attestation_obtained"] = True
        with self.assertRaises(ValueError) as caught:
            self.evidence.validate_attestation(value)
        self.assertIn("claims a human attestation", str(caught.exception))

    def test_a132_attestation_still_requires_no_false_independence(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.evidence.validate_attestation(
                {
                    "schema_version": 1,
                    "provider": "openai",
                    "authorization_ruling": "A132",
                    "actor": "Jacob Stephens",
                    "attester": "Jacob Stephens",
                    "independent_attestation": True,
                    "mutation_surface": "organization-limits-console",
                    "mutation_receipt_obtained": False,
                    "mutations": [
                        {"phase": "temporary_refusal", "change": "Set monthly limit to $0.01"},
                        {"phase": "restored_acceptance", "change": "Restore monthly limit to $100.00"},
                    ],
                }
            )
        self.assertIn("claims independence it cannot have", str(caught.exception))


# ---------------------------------------------------------------------------
# A150 OpenAI service-account liveness detector (issue #269).
#
# The failure it exists for: the mapped account ceased to exist between
# 2026-08-12 and 2026-08-18 with no recorded mutation, the token exchange
# returned 200 throughout, and the organization audit log holds zero events.
# So the assertion must be the per-project Administration API listing, it must
# fail closed, and it must never be satisfied by anything cheaper.
# ---------------------------------------------------------------------------

LIVENESS_DETECTOR_PATH = ROOT / "tools/check-openai-identity-liveness.py"
IDENTITY_REGISTRY_PATH = ROOT / "policy/openai-identity-history.json"
CONTROL_PLANE_TASKS_PATH = ROOT / "infra/ansible/roles/control_plane/tasks/main.yml"
CONTROL_PLANE_FILES = ROOT / "infra/ansible/roles/control_plane/files"
QUALIFY_TEMPLATE_PATH = (
    ROOT / "infra/ansible/roles/control_plane/templates/qualify-factory-control.j2"
)
DETECTOR = load_source("check_openai_identity_liveness", LIVENESS_DETECTOR_PATH)

PROJECT = "proj_4zpZhhPPNYCvPRE5vGuRBALH"
CURRENT = "user-1UnalMTUg8XaoKcNDHpcsqZU"
HISTORICAL = "user-6tzs2hdFVN7GoYQbWfC0eu7k"


def registry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "ruling": "A150",
        "provider": "openai",
        "project_id": PROJECT,
        "current_service_account_id": CURRENT,
        "service_accounts": [
            {
                "id": HISTORICAL,
                "status": "historical",
                "project_id": PROJECT,
                "administration_api_verified": False,
            },
            {
                "id": CURRENT,
                "status": "current",
                "project_id": PROJECT,
                "administration_api_verified": True,
            },
        ],
    }
    base.update(overrides)
    return base


class RegistryContract(unittest.TestCase):
    """The roster is the detector's only source for what to assert."""

    def test_the_committed_registry_satisfies_the_contract(self) -> None:
        loaded = DETECTOR.load_registry(IDENTITY_REGISTRY_PATH)
        project, current = DETECTOR.validate_registry(loaded)
        self.assertEqual(project, PROJECT)
        self.assertEqual(current, CURRENT)

    def test_two_current_entries_are_refused(self) -> None:
        malformed = registry()
        malformed["service_accounts"][0]["status"] = "current"
        with self.assertRaisesRegex(
            DETECTOR.IdentityRegistryError, "no single current entry"
        ):
            DETECTOR.validate_registry(malformed)

    def test_an_unverified_current_account_is_refused(self) -> None:
        """#267's whole lesson: the console said the old account was live and
        it was not. Only the Administration API listing may promote an id."""
        malformed = registry()
        malformed["service_accounts"][1]["administration_api_verified"] = False
        with self.assertRaisesRegex(
            DETECTOR.IdentityRegistryError, "never verified"
        ):
            DETECTOR.validate_registry(malformed)

    def test_a_repeated_id_is_refused(self) -> None:
        malformed = registry()
        malformed["service_accounts"][0]["id"] = CURRENT
        with self.assertRaisesRegex(DETECTOR.IdentityRegistryError, "repeats"):
            DETECTOR.validate_registry(malformed)

    def test_an_entry_in_another_project_is_refused(self) -> None:
        malformed = registry()
        malformed["service_accounts"][0]["project_id"] = "proj_0000000000000000"
        with self.assertRaisesRegex(
            DETECTOR.IdentityRegistryError, "another project"
        ):
            DETECTOR.validate_registry(malformed)

    def test_a_foreign_ruling_is_refused(self) -> None:
        with mock.patch.object(
            Path, "read_bytes", return_value=json.dumps(registry(ruling="A144")).encode()
        ):
            with self.assertRaisesRegex(DETECTOR.IdentityRegistryError, "A150"):
                DETECTOR.load_registry(Path("registry.json"))


class ListingContract(unittest.TestCase):
    """The assertion is the per-project listing, read to exhaustion."""

    @staticmethod
    def page(ids: list[str], has_more: bool = False) -> bytes:
        body: dict[str, object] = {
            "object": "list",
            "data": [{"id": i, "role": "member"} for i in ids],
            "has_more": has_more,
        }
        if ids:
            body["last_id"] = ids[-1]
        return json.dumps(body).encode()

    def urlopen(self, pages: list[bytes]) -> mock.MagicMock:
        replies = []
        for payload in pages:
            reply = mock.MagicMock()
            reply.status = 200
            reply.read.return_value = payload
            reply.__enter__.return_value = reply
            replies.append(reply)
        return mock.MagicMock(side_effect=replies)

    def test_a_listed_account_is_live(self) -> None:
        with mock.patch.object(
            DETECTOR.urllib.request, "urlopen", self.urlopen([self.page([CURRENT])])
        ):
            live, detail = DETECTOR.assert_live(PROJECT, CURRENT, "sk-admin-testtesttest")
        self.assertTrue(live)
        self.assertIn(CURRENT, detail)

    def test_an_unlisted_account_is_not_live(self) -> None:
        with mock.patch.object(
            DETECTOR.urllib.request, "urlopen", self.urlopen([self.page([HISTORICAL])])
        ):
            live, detail = DETECTOR.assert_live(PROJECT, CURRENT, "sk-admin-testtesttest")
        self.assertFalse(live)
        self.assertIn("NOT listed", detail)

    def test_pagination_is_followed_before_reporting_a_miss(self) -> None:
        """A truncated read would report a live account missing."""
        opener = self.urlopen(
            [self.page([HISTORICAL], has_more=True), self.page([CURRENT])]
        )
        with mock.patch.object(DETECTOR.urllib.request, "urlopen", opener):
            live, _ = DETECTOR.assert_live(PROJECT, CURRENT, "sk-admin-testtesttest")
        self.assertTrue(live)
        self.assertEqual(opener.call_count, 2)

    def test_more_pages_without_a_cursor_fails_closed(self) -> None:
        opener = self.urlopen([self.page([], has_more=True)])
        with mock.patch.object(DETECTOR.urllib.request, "urlopen", opener):
            with self.assertRaisesRegex(DETECTOR.LivenessError, "no cursor"):
                DETECTOR.assert_live(PROJECT, CURRENT, "sk-admin-testtesttest")

    def test_an_http_error_fails_closed_and_never_echoes_the_key(self) -> None:
        key = "sk-admin-supersecrettoken"
        error = urllib.error.HTTPError(
            "https://api.openai.com", 401, "Unauthorized", {},
            io.BytesIO(f'{{"error":"bad key {key}"}}'.encode()),
        )
        with mock.patch.object(
            DETECTOR.urllib.request, "urlopen", mock.MagicMock(side_effect=error)
        ):
            with self.assertRaises(DETECTOR.LivenessError) as raised:
                DETECTOR.assert_live(PROJECT, CURRENT, key)
        message = str(raised.exception)
        self.assertIn("HTTP 401", message)
        self.assertNotIn(key, message)
        self.assertIn("[redacted]", message)

    def test_a_non_json_body_fails_closed(self) -> None:
        with mock.patch.object(
            DETECTOR.urllib.request, "urlopen", self.urlopen([b"<html>"])
        ):
            with self.assertRaisesRegex(DETECTOR.LivenessError, "not JSON"):
                DETECTOR.assert_live(PROJECT, CURRENT, "sk-admin-testtesttest")


class MetricContract(unittest.TestCase):
    def test_the_gauge_carries_the_reading_and_its_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "patchyard_openai_identity.prom"
            DETECTOR.publish_metric(target, PROJECT, CURRENT, False)
            body = target.read_text()
        self.assertIn(
            f'{DETECTOR.METRIC}{{project="{PROJECT}",service_account="{CURRENT}"}} 0',
            body,
        )
        self.assertIn(DETECTOR.TIMESTAMP_METRIC, body)


class CheaperSignalsStayRuledOut(unittest.TestCase):
    """Three signals returned the wrong answer from primary source. None of
    them may reappear in the detector."""

    def test_the_detector_calls_only_the_per_project_listing(self) -> None:
        source = LIVENESS_DETECTOR_PATH.read_text()
        self.assertIn("/v1/organization/projects/", source)
        for forbidden in (
            "/v1/organization/users/",
            "/v1/organization/audit_logs",
            "token-exchange",
            "/v1/chat/completions",
        ):
            self.assertNotIn(f'"{forbidden}', source)
        self.assertEqual(source.count("BASE_URL = "), 1)


class DeploymentContract(unittest.TestCase):
    def test_the_units_drive_the_detector_against_the_converged_paths(self) -> None:
        service = (CONTROL_PLANE_FILES / "patchyard-openai-identity-metric.service").read_text()
        self.assertIn("/usr/local/sbin/check-openai-identity-liveness.py", service)
        self.assertIn("--registry /etc/patchyard/openai-identity-history.json", service)
        self.assertIn(
            "--admin-key-file /etc/patchyard/openai-admin-readonly.key", service
        )
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn(
            "ReadWritePaths=/var/lib/node_exporter/textfile_collector", service
        )

    def test_the_timer_fires_daily_and_catches_up(self) -> None:
        timer = (CONTROL_PLANE_FILES / "patchyard-openai-identity-metric.timer").read_text()
        self.assertIn("OnCalendar=*-*-* 06:25:00 UTC", timer)
        self.assertIn("Persistent=true", timer)

    def test_converge_asserts_now_and_never_reinjects_the_key(self) -> None:
        tasks = CONTROL_PLANE_TASKS_PATH.read_text()
        self.assertIn("Assert the mapped OpenAI service account now", tasks)
        self.assertIn("Enforce the OpenAI read-only Administration key boundary", tasks)
        self.assertIn(
            "../../tools/factory_checker_runtime.py",
            tasks,
        )
        self.assertIn("dest: /usr/local/sbin/factory_checker_runtime.py", tasks)
        self.assertLess(
            tasks.index("Install the shared qualification checker runtime"),
            tasks.index("Install the OpenAI service-account liveness assertion"),
        )
        # state: file preserves and verifies; it must never become a copy task.
        boundary = tasks.split(
            "Enforce the OpenAI read-only Administration key boundary"
        )[1].split("- name:")[0]
        self.assertIn("state: file", boundary)
        self.assertIn('mode: "0400"', boundary)
        self.assertNotIn("content:", boundary)

    def test_the_key_is_kept_off_restore_drills(self) -> None:
        tasks = CONTROL_PLANE_TASKS_PATH.read_text()
        drill = tasks.split("Keep the live Anthropic signing identity off restore drills")[1]
        self.assertIn("/etc/patchyard/openai-admin-readonly.key", drill)

    def test_qualification_requires_the_timer(self) -> None:
        self.assertIn(
            "systemctl is-active --quiet patchyard-openai-identity-metric.timer",
            QUALIFY_TEMPLATE_PATH.read_text(),
        )


if __name__ == "__main__":
    unittest.main()
