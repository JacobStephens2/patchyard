from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timezone
from email.message import Message
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
ADAPTER_PATH = ROOT / "tools/openai-wif-issuance.py"
CHECKER_PATH = ROOT / "tools/check-openai-wif-issuance.py"
EXPIRY_ADAPTER_PATH = ROOT / "tools/openai-wif-expiry.py"
EXPIRY_CHECKER_PATH = ROOT / "tools/check-openai-wif-expiry.py"
CRASH_ADAPTER_PATH = ROOT / "tools/openai-wif-crash-cleanup.py"
CRASH_CHECKER_PATH = ROOT / "tools/check-openai-wif-crash-cleanup.py"
POLICY_PATH = ROOT / "policy/openai-wif.json"
FIXTURE_PATH = ROOT / "fixtures/checker-contracts/openai-first-token-exchange.json"
EXPIRY_FIXTURE_PATH = (
    ROOT / "fixtures/checker-contracts/openai-expiry-denial.json"
)
CRASH_FIXTURE_PATH = (
    ROOT / "fixtures/checker-contracts/openai-crash-cleanup.json"
)
EXPECTED_ADAPTER_SHA256 = (
    "63676168101366f50670adf4e06fa5c6841589bfcead4e8813d244f47944469d"
)
EXPECTED_FIXTURE_SHA256 = (
    "a70a8553fe1c74fa37976be4bedb069cd200147891e5c6d56a6beec72f761d55"
)
EXPECTED_EXPIRY_ADAPTER_SHA256 = (
    "0308a6cf7a9b17e194c8856efd69fe94d2b62e7c0184bc2161af0996015f934f"
)
EXPECTED_CRASH_ADAPTER_SHA256 = (
    "9a770c04b91593a304d97edf07f131cbb0c353c0551648537dc6b7dea9bc4cdf"
)
EXPECTED_EXPIRY_FIXTURE_SHA256 = (
    "5425e41f6cc278916ccc075091599acd8564323ba49ab4544b291af160328ad9"
)
EXPECTED_CRASH_FIXTURE_SHA256 = (
    "e082c544dfefc1725922032fc229d85e83e16cd6ec2711a92de16bfe38c40a49"
)
RUN_ID = "openai-wif-20260806-0123456789"
EXPIRY_RUN_ID = "openai-expiry-20260807-0123456789"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_exact_source_module(
    name: str, path: Path, expected: str
) -> types.ModuleType:
    source = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(source).hexdigest() != expected:
        raise RuntimeError(f"{path.name} differs from its exact source binding")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = None
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


ADAPTER = load_exact_source_module(
    "openai_wif_issuance", ADAPTER_PATH, EXPECTED_ADAPTER_SHA256
)
EXPIRY_ADAPTER = load_exact_source_module(
    "openai_wif_expiry", EXPIRY_ADAPTER_PATH, EXPECTED_EXPIRY_ADAPTER_SHA256
)
CRASH_ADAPTER = load_exact_source_module(
    "openai_wif_crash_cleanup",
    CRASH_ADAPTER_PATH,
    EXPECTED_CRASH_ADAPTER_SHA256,
)


def b64json(value: dict[str, object]) -> str:
    encoded = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def fake_mint(
    policy: dict[str, object], signing_key: Path, run_id: str, now_epoch: int
) -> tuple[str, dict[str, str]]:
    del signing_key
    header = {
        "alg": "RS256",
        "kid": "patchyard-39acdfd2bfc0acb0",
        "typ": "JWT",
    }
    claims = {
        "iss": policy["issuer"]["issuer_url"],
        "sub": policy["rule"]["subject"],
        "aud": policy["rule"]["audience"],
        "iat": now_epoch - 5,
        "exp": now_epoch + 295,
        "jti": f"factory-{run_id}-0123456789abcdef",
        "factory_environment": policy["rule"]["claims"]["factory_environment"],
    }
    assertion = f"{b64json(header)}.{b64json(claims)}.c2lnbmF0dXJl"
    return assertion, {
        "kid": "patchyard-39acdfd2bfc0acb0",
        "jwk_thumbprint_sha256": "ab" * 32,
    }


def headers() -> Message:
    value = Message()
    value["Content-Type"] = "application/json"
    value["Date"] = "Thu, 06 Aug 2026 12:00:05 GMT"
    value["X-Request-Id"] = "req_synthetic"
    return value


class OpenAIWifIssuanceAdapterContract(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(POLICY_PATH.read_text())

    def test_policy_binds_openai_audience_and_five_minute_assertion(self) -> None:
        self.assertEqual(self.policy, ADAPTER.EXPECTED_POLICY)
        self.assertEqual(
            self.policy["issuer"]["issuer_url"],
            "https://factory.example.com/workload-identity",
        )
        self.assertEqual(
            self.policy["issuer"]["audience"], "https://api.openai.com"
        )
        self.assertEqual(self.policy["rule"]["audience"], "https://api.openai.com")
        self.assertEqual(self.policy["issuer"]["max_jwt_lifetime_seconds"], 300)
        self.assertEqual(self.policy["rule"]["token_lifetime_seconds"], 300)

    def test_adapter_loads_the_frozen_harness_by_exact_digest(self) -> None:
        self.assertEqual(
            digest(ADAPTER.BASE_HARNESS_PATH), ADAPTER.BASE_HARNESS_SHA256
        )
        with mock.patch.object(
            ADAPTER.BASE_HARNESS_PATH.__class__,
            "read_bytes",
            return_value=b"changed",
        ):
            with self.assertRaisesRegex(RuntimeError, "exact binding"):
                ADAPTER.load_base_harness()

    def test_minted_assertion_carries_openai_claims(self) -> None:
        now_epoch = 1786017605
        with mock.patch.object(ADAPTER.BASE, "mint_assertion", side_effect=fake_mint):
            assertion, descriptor = ADAPTER.mint_openai_assertion(
                self.policy, Path("/unused"), RUN_ID, now_epoch
            )
        self.assertRegex(assertion, r"^[^.]+\.[^.]+\.[^.]+$")
        self.assertEqual(descriptor["audience"], "https://api.openai.com")
        self.assertEqual(descriptor["subject"], "patchyard-control-plane")
        self.assertEqual(descriptor["lifetime_seconds"], 300)
        self.assertIs(descriptor["jti_supplied"], True)

    def test_exchange_request_is_exact_and_never_adds_scope(self) -> None:
        request = ADAPTER.exchange_request(self.policy, "synthetic-subject-token")
        self.assertEqual(
            request,
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                "subject_token": "synthetic-subject-token",
                "identity_provider_id": "idp_DlzD7RlQXgXxd1VSG2V93eEU",
                "service_account_id": "user-6tzs2hdFVN7GoYQbWfC0eu7k",
            },
        )
        self.assertNotIn("scope", request)

    def test_success_response_is_sanitized_without_pinning_success(self) -> None:
        synthetic_token = "eyJ" + "x" * 30 + "." + "y" * 30 + "." + "z" * 30
        raw = json.dumps(
            {
                "access_token": synthetic_token,
                "token_type": "Bearer",
                "expires_in": 295,
                "issued_token_type": (
                    "urn:ietf:params:oauth:token-type:access_token"
                ),
            }
        ).encode()
        result = ADAPTER.sanitize_response(
            200,
            headers(),
            raw,
            "2026-08-06T12:00:05.100000Z",
            "2026-08-06T12:00:05.200000Z",
        )
        self.assertIs(result["access_token_supplied"], True)
        self.assertEqual(result["token_type"], "Bearer")
        self.assertEqual(result["expires_in"], 295)
        self.assertNotIn(synthetic_token, json.dumps(result, sort_keys=True))
        names = {
            field["name"] for field in result["response_shape"]["top_level_fields"]
        }
        self.assertEqual(
            names,
            {"access_token", "expires_in", "issued_token_type", "token_type"},
        )

    def test_denial_and_non_json_responses_are_bounded_observations(self) -> None:
        denial = ADAPTER.sanitize_response(
            401,
            headers(),
            b'{"error":{"type":"synthetic_denial","message":"not retained"}}',
            "2026-08-06T12:00:05.100000Z",
            "2026-08-06T12:00:05.200000Z",
        )
        self.assertEqual(denial["http_status"], 401)
        self.assertEqual(denial["error_type"], "synthetic_denial")
        self.assertNotIn("not retained", json.dumps(denial, sort_keys=True))

        non_json = ADAPTER.sanitize_response(
            503,
            headers(),
            b"synthetic non-JSON response",
            "2026-08-06T12:00:05.100000Z",
            "2026-08-06T12:00:05.200000Z",
        )
        self.assertEqual(non_json["body_format"], "non_json")
        self.assertEqual(non_json["response_shape"]["top_level_fields"], [])

    def test_exchange_observation_accepts_any_sanitized_http_outcome(self) -> None:
        response = {
            "source": "openai_http_response",
            "http_status": 418,
            "request_started_at": "2026-08-06T12:00:05.100000Z",
            "observed_at": "2026-08-06T12:00:05.200000Z",
            "provider_date": None,
            "request_id": None,
            "request_id_supplied": False,
            "content_type": "application/json",
            "body_bytes": 2,
            "body_format": "json_object",
            "response_shape": {
                "body_kind": "json_object",
                "top_level_fields": [],
                "error_fields": [],
            },
            "access_token_supplied": False,
            "token_type": None,
            "expires_in": None,
            "error_type": None,
        }

        def request(body: dict[str, object]) -> dict[str, object]:
            self.assertEqual(body["identity_provider_id"], self.policy["issuer"]["id"])
            return deepcopy(response)

        with mock.patch.object(ADAPTER.BASE, "mint_assertion", side_effect=fake_mint):
            result = ADAPTER.exchange_observation(
                self.policy,
                Path("/unused"),
                RUN_ID,
                "2026-08-06T12:00:05.000000Z",
                request=request,
            )
        self.assertEqual(result["exchange_response"]["http_status"], 418)
        self.assertEqual(result["response_predicate"], ADAPTER.RESPONSE_PREDICATE)
        self.assertIs(result["provider_response_observed"], True)
        self.assertIs(result["qualification_evidence"], False)

    def test_ambient_openai_credentials_and_proxies_are_removed(self) -> None:
        environment = {
            "PATH": "/usr/bin",
            "OPENAI_API_KEY": "synthetic",
            "PATCHYARD_OPENAI_ADMIN_KEY": "synthetic",
            "HTTPS_PROXY": "http://proxy.invalid",
        }
        with mock.patch.object(ADAPTER.os, "environ", environment):
            cleaned = ADAPTER.credential_free_env()
        self.assertEqual(cleaned, {"PATH": "/usr/bin"})


class OpenAIWifIssuanceCheckerContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = json.loads(FIXTURE_PATH.read_text())

    def run_checker(
        self, *arguments: str, isolated: bool = True
    ) -> subprocess.CompletedProcess[str]:
        command = ["python3"]
        if isolated:
            command.append("-I")
        command.extend([str(CHECKER_PATH), *arguments])
        return subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write(self, value: dict[str, object], name: str = "input.json") -> Path:
        path = self.root / name
        path.write_text(json.dumps(value))
        return path

    def observed(self) -> dict[str, object]:
        value = deepcopy(self.fixture)
        del value["fixture_kind"]
        del value["fixture_lineage"]
        value["provider_response_observed"] = True
        value["exchange_response"] = {
            "source": "openai_http_response",
            "http_status": 418,
            "request_started_at": "2026-08-06T12:00:05.200000Z",
            "observed_at": "2026-08-06T12:00:05.300000Z",
            "provider_date": "2026-08-06T12:00:05Z",
            "request_id": "req_synthetic",
            "request_id_supplied": True,
            "content_type": "application/json",
            "body_bytes": 42,
            "body_format": "json_object",
            "response_shape": {
                "body_kind": "json_object",
                "top_level_fields": [
                    {
                        "name": "error",
                        "name_recorded": True,
                        "value_type": "object",
                    }
                ],
                "error_fields": [
                    {
                        "name": "type",
                        "name_recorded": True,
                        "value_type": "string",
                    }
                ],
            },
            "access_token_supplied": False,
            "token_type": None,
            "expires_in": None,
            "error_type": "synthetic_denial",
        }
        return value

    def test_conforming_fixture_passes_actual_checker(self) -> None:
        self.assertEqual(digest(FIXTURE_PATH), EXPECTED_FIXTURE_SHA256)
        self.assertEqual(
            self.fixture["fixture_kind"],
            "synthetic-openai-first-exchange-satisfiability",
        )
        self.assertIs(self.fixture["provider_response_observed"], False)
        self.assertIs(self.fixture["qualification_evidence"], False)
        result = self.run_checker("--contract-fixture", str(FIXTURE_PATH))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not qualification evidence", result.stdout)

    def test_synthetic_fixture_is_refused_as_qualification_evidence(self) -> None:
        result = self.run_checker("--evidence", str(FIXTURE_PATH))
        self.assertEqual(result.returncode, 1)
        self.assertIn("synthetic OpenAI fixture cannot be qualification", result.stderr)

    def test_arbitrary_observed_http_shape_passes_unenforced_predicate(self) -> None:
        result = self.run_checker("--observation", str(self.write(self.observed())))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("non-qualifying provider observation", result.stdout)

    def test_checker_rejects_extra_keys_and_out_of_order_utc(self) -> None:
        extra = self.observed()
        extra["unexpected"] = True
        result = self.run_checker("--observation", str(self.write(extra, "extra.json")))
        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected evidence shape", result.stderr)

        out_of_order = self.observed()
        out_of_order["credential_removed_at"] = "2026-08-06T11:59:59Z"
        result = self.run_checker(
            "--observation", str(self.write(out_of_order, "order.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("UTC observations are out of order", result.stderr)

    def test_checker_rejects_credential_shaped_values_and_names(self) -> None:
        credential = self.observed()
        credential["exchange_response"]["request_id"] = "eyJsynthetic.payload.signature"
        result = self.run_checker(
            "--observation", str(self.write(credential, "credential.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("credential-shaped material", result.stderr)

        forbidden = self.observed()
        forbidden["exchange_response"]["access_token"] = "not-a-token"
        result = self.run_checker(
            "--observation", str(self.write(forbidden, "forbidden.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("forbidden credential field: access_token", result.stderr)

    def test_checker_rejects_premature_predicate_enforcement(self) -> None:
        observed = self.observed()
        observed["response_predicate"]["enforced"] = True
        result = self.run_checker(
            "--observation", str(self.write(observed, "predicate.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("predicate was enforced before an observation", result.stderr)

    def test_checker_requires_isolated_python(self) -> None:
        result = self.run_checker("--allow-missing-results", isolated=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires python3 -I", result.stderr)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        path = self.root / "duplicate.json"
        path.write_text('{"schema_version":1,"schema_version":1}')
        result = self.run_checker("--observation", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate JSON key", result.stderr)


class OpenAIWifExpiryAdapterContract(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(POLICY_PATH.read_text())

    def test_adapter_loads_frozen_base_and_derives_the_active_key_id(self) -> None:
        self.assertEqual(
            digest(EXPIRY_ADAPTER.BASE_HARNESS_PATH),
            EXPIRY_ADAPTER.BASE_HARNESS_SHA256,
        )
        derived = (
            "patchyard-"
            + hashlib.sha256(b"synthetic-public-der").hexdigest()[:16]
        )
        fake_jwk = {
            "kid": derived,
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "n": "synthetic-modulus",
            "e": "AQAB",
        }
        completed = types.SimpleNamespace(stdout=b"synthetic-signature")
        with (
            mock.patch.object(
                EXPIRY_ADAPTER.BASE, "load_public_jwk", return_value=fake_jwk
            ),
            mock.patch.object(
                EXPIRY_ADAPTER.BASE,
                "jwk_descriptor",
                return_value={
                    "kid": derived,
                    "jwk_thumbprint_sha256": "ab" * 32,
                },
            ),
            mock.patch.object(
                EXPIRY_ADAPTER.subprocess, "run", return_value=completed
            ),
        ):
            assertion, descriptor = EXPIRY_ADAPTER.mint_expired_assertion(
                self.policy, Path("/unused"), EXPIRY_RUN_ID, 1786104000
            )
        header = json.loads(
            base64.urlsafe_b64decode(
                assertion.split(".")[0] + "=" * (-len(assertion.split(".")[0]) % 4)
            )
        )
        self.assertEqual(header["kid"], derived)
        self.assertIs(descriptor["kid_derived_from_public_der"], True)
        self.assertNotIn("kid", descriptor)

    def test_assertion_is_expired_before_mint_and_exchange_is_attempted_once(self) -> None:
        fixture = json.loads(EXPIRY_FIXTURE_PATH.read_text())
        descriptor = deepcopy(fixture["assertion_descriptor"])
        response = deepcopy(fixture["expiry_denial"])
        response.update(
            {
                "source": "openai_http_response",
                "http_status": 418,
                "body_format": "json_object",
                "response_shape": {
                    "body_kind": "json_object",
                    "top_level_fields": [],
                    "error_fields": [],
                },
            }
        )
        calls = []

        def request(body: dict[str, object]) -> dict[str, object]:
            calls.append(deepcopy(body))
            return deepcopy(response)

        with mock.patch.object(
            EXPIRY_ADAPTER,
            "mint_expired_assertion",
            return_value=("synthetic.assertion.signature", descriptor),
        ):
            result = EXPIRY_ADAPTER.expiry_observation(
                self.policy,
                Path("/unused"),
                EXPIRY_RUN_ID,
                fixture["started_at"],
                request=request,
                clock=lambda: 1786104000,
            )
        minted = datetime.fromisoformat(
            descriptor["minted_at"].replace("Z", "+00:00")
        )
        expires = datetime.fromisoformat(
            descriptor["expires_at"].replace("Z", "+00:00")
        )
        self.assertLess(expires, minted)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("scope", calls[0])
        self.assertEqual(result["exchange_request"]["attempt_count"], 1)
        self.assertEqual(result["response_predicate"], EXPIRY_ADAPTER.RESPONSE_PREDICATE)
        self.assertIs(result["qualification_evidence"], False)


class OpenAIWifExpiryCheckerContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = json.loads(EXPIRY_FIXTURE_PATH.read_text())

    def run_checker(
        self, *arguments: str, isolated: bool = True
    ) -> subprocess.CompletedProcess[str]:
        command = ["python3"]
        if isolated:
            command.append("-I")
        command.extend([str(EXPIRY_CHECKER_PATH), *arguments])
        return subprocess.run(
            command, cwd=ROOT, check=False, capture_output=True, text=True
        )

    def write(self, value: dict[str, object], name: str) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value))
        return path

    def observed(self) -> dict[str, object]:
        value = deepcopy(self.fixture)
        del value["fixture_kind"]
        del value["fixture_lineage"]
        value["provider_response_observed"] = True
        value["expiry_denial"] = {
            "source": "openai_http_response",
            "http_status": 418,
            "request_started_at": "2026-08-07T12:00:00.100000Z",
            "observed_at": "2026-08-07T12:00:00.200000Z",
            "provider_date": "2026-08-07T12:00:00Z",
            "request_id": "synthetic-request-id",
            "request_id_supplied": True,
            "content_type": "application/json",
            "body_bytes": 42,
            "body_format": "json_object",
            "response_shape": {
                "body_kind": "json_object",
                "top_level_fields": [],
                "error_fields": [],
            },
            "access_token_supplied": False,
            "error_type": "synthetic-unenforced",
        }
        return value

    def test_fixture_passes_but_is_refused_as_qualification_evidence(self) -> None:
        self.assertEqual(digest(EXPIRY_FIXTURE_PATH), EXPECTED_EXPIRY_FIXTURE_SHA256)
        self.assertIs(self.fixture["provider_response_observed"], False)
        self.assertIs(self.fixture["qualification_evidence"], False)
        accepted = self.run_checker(
            "--contract-fixture", str(EXPIRY_FIXTURE_PATH)
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        refused = self.run_checker("--evidence", str(EXPIRY_FIXTURE_PATH))
        self.assertEqual(refused.returncode, 1)
        self.assertIn("cannot be qualification evidence", refused.stderr)

    def test_unenforced_arbitrary_response_is_accepted_as_observation(self) -> None:
        result = self.run_checker(
            "--observation", str(self.write(self.observed(), "observed.json"))
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exact_keys_utc_and_credential_hygiene_fail_closed(self) -> None:
        extra = self.observed()
        extra["unexpected"] = True
        result = self.run_checker(
            "--observation", str(self.write(extra, "extra.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected evidence shape", result.stderr)

        order = self.observed()
        order["credential_removed_at"] = "2026-08-07T11:59:59Z"
        result = self.run_checker(
            "--observation", str(self.write(order, "order.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("UTC observations are out of order", result.stderr)

        credential = self.observed()
        credential["expiry_denial"]["request_id"] = (
            "eyJsynthetic.payload.signature"
        )
        result = self.run_checker(
            "--observation", str(self.write(credential, "credential.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("credential-shaped material", result.stderr)

    def test_premature_enforcement_and_nonisolated_execution_are_rejected(self) -> None:
        enforced = self.observed()
        enforced["response_predicate"]["enforced"] = True
        result = self.run_checker(
            "--observation", str(self.write(enforced, "enforced.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("predicate was enforced", result.stderr)
        result = self.run_checker("--allow-missing-results", isolated=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires python3 -I", result.stderr)



    def test_second_precision_mint_in_the_start_second_is_accepted(self) -> None:
        """A real run mints inside the second it starts, and must still pass.

        The frozen base harness writes `minted_at` at whole-second precision
        while `started_at` carries microseconds. Ordering minted against the
        start therefore compares a truncated value with an untruncated one and
        no live run can satisfy it. The first attended requirement 3 run failed
        exactly here, on a valid OpenAI 401, and the committed requirement 1
        Result carries the same inversion.
        """
        observed = self.observed()
        observed["started_at"] = "2026-08-07T12:00:00.005868Z"
        observed["assertion_descriptor"]["minted_at"] = "2026-08-07T12:00:00Z"
        path = self.write(observed, "mint-in-start-second.json")
        result = self.run_checker("--observation", str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_mint_after_the_exchange_request_is_refused(self) -> None:
        """Signed-before-sent is the one ordering minted genuinely contributed.

        Truncation moves minted earlier, never later, so this direction stays
        sound at second precision and is kept after minted left the chain.
        """
        observed = self.observed()
        observed["assertion_descriptor"]["minted_at"] = "2026-08-07T12:00:01Z"
        path = self.write(observed, "mint-after-request.json")
        result = self.run_checker("--observation", str(path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("minted after the exchange request", result.stderr)

class OpenAIWifCrashAdapterContract(unittest.TestCase):
    def test_adapter_binds_base_and_scans_process_image_without_a_worker(self) -> None:
        self.assertEqual(
            digest(CRASH_ADAPTER.BASE_HARNESS_PATH),
            CRASH_ADAPTER.BASE_HARNESS_SHA256,
        )
        contract = CRASH_ADAPTER.search_contract(
            Path("/run/patchyard-openai/openai-crash-20260807-0123456789"),
            42420,
            12345678,
        )
        self.assertEqual(
            contract["process_image_scope"],
            "target-readable-mappings-when-present",
        )
        self.assertNotIn("worker", json.dumps(contract, sort_keys=True))
        self.assertEqual(CRASH_ADAPTER.RESPONSE_PREDICATE["enforced"], False)

    def test_process_image_positive_control_finds_exact_live_material(self) -> None:
        assertion = bytearray(b"synthetic-assertion-material")
        bearer = bytearray(b"synthetic-bearer-material")
        blob = b"prefix" + bytes(assertion) + b"middle" + bytes(bearer) + b"suffix"
        materials = {"jwt_assertion": assertion, "openai_bearer": bearer}
        with (
            mock.patch.object(
                CRASH_ADAPTER, "target_process_present", return_value=True
            ),
            mock.patch.object(
                CRASH_ADAPTER,
                "readable_memory_ranges",
                return_value=[(4096, 4096 + len(blob))],
            ),
            mock.patch.object(CRASH_ADAPTER.os, "open", return_value=77),
            mock.patch.object(CRASH_ADAPTER.os, "pread", return_value=blob),
            mock.patch.object(CRASH_ADAPTER.os, "close"),
        ):
            found, regions, examined, _ = CRASH_ADAPTER.find_material_in_process(
                42420, 12345678, materials
            )
        self.assertEqual(found, {"jwt_assertion", "openai_bearer"})
        self.assertEqual(regions, 1)
        self.assertEqual(examined, len(blob))

    def test_material_fingerprints_never_retain_the_values(self) -> None:
        assertion = bytearray(b"synthetic-assertion-material")
        bearer = bytearray(b"synthetic-bearer-material")
        result = CRASH_ADAPTER.material_fingerprints(assertion, bearer)
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn(assertion.decode(), encoded)
        self.assertNotIn(bearer.decode(), encoded)
        self.assertEqual(
            [item["material_class"] for item in result],
            ["jwt_assertion", "openai_bearer"],
        )


class OpenAIWifCrashCheckerContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = json.loads(CRASH_FIXTURE_PATH.read_text())

    def run_checker(
        self, *arguments: str, isolated: bool = True
    ) -> subprocess.CompletedProcess[str]:
        command = ["python3"]
        if isolated:
            command.append("-I")
        command.extend([str(CRASH_CHECKER_PATH), *arguments])
        return subprocess.run(
            command, cwd=ROOT, check=False, capture_output=True, text=True
        )

    def write(self, value: dict[str, object], name: str) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value))
        return path

    @staticmethod
    def encoded_digest(value: dict[str, object]) -> str:
        encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
        return hashlib.sha256(encoded).hexdigest()

    def observed(self) -> dict[str, object]:
        value = deepcopy(self.fixture)
        del value["fixture_kind"]
        del value["fixture_lineage"]
        value["provider_response_observed"] = True
        value["checkpoint"]["exchange_response"]["source"] = (
            "openai_http_response"
        )
        value["kill"]["checkpoint_sha256"] = self.encoded_digest(
            value["checkpoint"]
        )
        return value

    def test_fixture_passes_but_is_refused_as_qualification_evidence(self) -> None:
        self.assertEqual(digest(CRASH_FIXTURE_PATH), EXPECTED_CRASH_FIXTURE_SHA256)
        self.assertIs(self.fixture["provider_response_observed"], False)
        self.assertIs(self.fixture["qualification_evidence"], False)
        accepted = self.run_checker(
            "--contract-fixture", str(CRASH_FIXTURE_PATH)
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        refused = self.run_checker("--evidence", str(CRASH_FIXTURE_PATH))
        self.assertEqual(refused.returncode, 1)
        self.assertIn("cannot be qualification evidence", refused.stderr)

    def test_conforming_local_observation_is_accepted(self) -> None:
        result = self.run_checker(
            "--observation", str(self.write(self.observed(), "observed.json"))
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exact_keys_utc_and_credential_hygiene_fail_closed(self) -> None:
        extra = self.observed()
        extra["unexpected"] = True
        result = self.run_checker(
            "--observation", str(self.write(extra, "extra.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected evidence shape", result.stderr)

        order = self.observed()
        order["post_kill_search"]["observed_at"] = (
            "2026-08-07T11:59:59Z"
        )
        result = self.run_checker(
            "--observation", str(self.write(order, "order.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("observations are out of order", result.stderr)

        credential = self.observed()
        credential["checkpoint"]["exchange_response"]["request_id"] = (
            "eyJsynthetic.payload.signature"
        )
        result = self.run_checker(
            "--observation", str(self.write(credential, "credential.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("credential-shaped material", result.stderr)

    def test_sigterm_vacuous_search_and_premature_enforcement_are_rejected(self) -> None:
        sigterm = self.observed()
        sigterm["kill"].update(
            {"signal_name": "SIGTERM", "signal_number": 15, "child_returncode": -15}
        )
        result = self.run_checker(
            "--observation", str(self.write(sigterm, "sigterm.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("not terminated by SIGKILL", result.stderr)

        vacuous = self.observed()
        vacuous["positive_control"].update(
            {
                "credential_material_found": False,
                "material_classes_found": [],
                "matches": [],
            }
        )
        result = self.run_checker(
            "--observation", str(self.write(vacuous, "vacuous.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("positive control found no credential material", result.stderr)

        enforced = self.observed()
        enforced["response_predicate"]["enforced"] = True
        result = self.run_checker(
            "--observation", str(self.write(enforced, "enforced.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("predicate was enforced prematurely", result.stderr)

    def test_checker_requires_isolated_python(self) -> None:
        result = self.run_checker("--allow-missing-results", isolated=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires python3 -I", result.stderr)


if __name__ == "__main__":
    unittest.main()
