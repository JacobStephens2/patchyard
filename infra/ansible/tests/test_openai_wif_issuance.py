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
    "88117660a2717ecd2c9b6eef4704066700e4989e1010d508769bf928fec18c8b"
)
EXPECTED_FIXTURE_SHA256 = (
    "a1963e0bfac56be44e47ccbe9fe233e1179a79ef7775b00ad43f7358dfaec970"
)
EXPECTED_EXPIRY_ADAPTER_SHA256 = (
    "42042f1d8940a7c7a9bea560246813f22d25bf2238909f35980277d70911a24b"
)
EXPECTED_CRASH_ADAPTER_SHA256 = (
    "6214024e5788b53530273573415f2e9f679069ab6934b19250a269204de50655"
)
EXPECTED_EXPIRY_FIXTURE_SHA256 = (
    "d02e68c63f988da1e149f1f7139c6d1c6a534715ce72728278e2aa57a865bac4"
)
EXPECTED_CRASH_FIXTURE_SHA256 = (
    "e082c544dfefc1725922032fc229d85e83e16cd6ec2711a92de16bfe38c40a49"
)
RUN_ID = "openai-wif-20260806-0123456789"
EXPIRY_RUN_ID = "openai-expiry-20260807-0123456789"
SIGNING_IDENTITIES_PATH = ROOT / "policy/signing-identities.json"
IDENTITY_HISTORY_PATH = ROOT / "policy/openai-identity-history.json"
REGISTRY_SERVICE_ACCOUNT = json.loads(IDENTITY_HISTORY_PATH.read_text())[
    "current_service_account_id"
]
REGISTRY_KID = json.loads(SIGNING_IDENTITIES_PATH.read_text())["providers"][
    "openai"
]["trusted_kid"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_collector_result(
    checker: Path, result: dict[str, object], *, mode: str = "--observation"
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "collector-result.json"
        path.write_text(json.dumps(result))
        return subprocess.run(
            ["python3", "-I", str(checker), mode, str(path)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )


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


def fake_mint_with(kid: str):
    def fake_mint(
        policy: dict[str, object], signing_key: Path, run_id: str, now_epoch: int
    ) -> tuple[str, dict[str, str]]:
        del signing_key
        header = {"alg": "RS256", "kid": kid, "typ": "JWT"}
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
        return assertion, {"kid": kid, "jwk_thumbprint_sha256": "ab" * 32}

    return fake_mint


fake_mint = fake_mint_with(REGISTRY_KID)


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

    def test_minting_kid_authority_is_the_signing_identity_registry(self) -> None:
        """A145: the registry, not the frozen policy, names the expected kid."""
        self.assertNotEqual(REGISTRY_KID, self.policy["issuer"]["jwks_kid"])
        with mock.patch.object(ADAPTER.BASE, "mint_assertion", side_effect=fake_mint):
            _, descriptor = ADAPTER.mint_openai_assertion(
                self.policy, Path("/unused"), RUN_ID, 1786017605
            )
        self.assertEqual(descriptor["kid"], REGISTRY_KID)

    def test_frozen_policy_kid_no_longer_mints(self) -> None:
        stale = fake_mint_with(self.policy["issuer"]["jwks_kid"])
        with mock.patch.object(ADAPTER.BASE, "mint_assertion", side_effect=stale):
            with self.assertRaisesRegex(
                ADAPTER.OpenAIWifError, "signing-identity registry"
            ):
                ADAPTER.mint_openai_assertion(
                    self.policy, Path("/unused"), RUN_ID, 1786017605
                )

    def test_collector_supplied_transitional_kid_overrides_the_registry(self) -> None:
        transitional = "patchyard-" + "ab" * 8
        minted = fake_mint_with(transitional)
        with mock.patch.object(ADAPTER.BASE, "mint_assertion", side_effect=minted):
            _, descriptor = ADAPTER.mint_openai_assertion(
                self.policy,
                Path("/unused"),
                RUN_ID,
                1786017605,
                expected_kid=transitional,
            )
        self.assertEqual(descriptor["kid"], transitional)

    def test_registry_entry_must_name_the_openai_key_path(self) -> None:
        registry = json.loads(SIGNING_IDENTITIES_PATH.read_text())
        registry["providers"]["openai"]["signing_key_path"] = (
            "/etc/patchyard/anthropic-wif-signing.pem"
        )
        with mock.patch.object(
            ADAPTER.BASE, "load_json_file", return_value=registry
        ):
            with self.assertRaisesRegex(
                ADAPTER.OpenAIWifError, "key path"
            ):
                ADAPTER.registry_trusted_kid()

    def test_exchange_request_is_exact_and_never_adds_scope(self) -> None:
        # A150: load_policy substitutes the registry's current id for the
        # frozen policy's demoted issuance-era one, so the wire carries the
        # live account. Reading the frozen file directly must not.
        request = ADAPTER.exchange_request(
            ADAPTER.load_policy(), "synthetic-subject-token"
        )
        self.assertEqual(
            request,
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                "subject_token": "synthetic-subject-token",
                "identity_provider_id": "idp_DlzD7RlQXgXxd1VSG2V93eEU",
                "service_account_id": REGISTRY_SERVICE_ACCOUNT,
            },
        )
        self.assertNotIn("scope", request)

    def test_load_policy_substitutes_the_registry_service_account(self) -> None:
        """A150: the frozen policy keeps the issuance-era id as a record; no
        collector may mint against it once the account has been replaced."""
        frozen = json.loads(POLICY_PATH.read_text())
        self.assertNotEqual(
            frozen["service_account"]["id"], REGISTRY_SERVICE_ACCOUNT
        )
        self.assertEqual(
            frozen["rule"]["service_account_id"], frozen["service_account"]["id"]
        )
        resolved = ADAPTER.load_policy()
        self.assertEqual(
            resolved["service_account"]["id"], REGISTRY_SERVICE_ACCOUNT
        )
        self.assertEqual(
            resolved["rule"]["service_account_id"], REGISTRY_SERVICE_ACCOUNT
        )
        # The roster must keep the issuance-era id, or the banked Results stop
        # being checkable against a rostered identity.
        roster = json.loads(IDENTITY_HISTORY_PATH.read_text())
        self.assertIn(
            frozen["service_account"]["id"],
            [entry["id"] for entry in roster["service_accounts"]],
        )

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

        with (
            mock.patch.object(ADAPTER.BASE, "mint_assertion", side_effect=fake_mint),
            mock.patch.object(ADAPTER.time, "time", return_value=1786017605),
            mock.patch.object(
                ADAPTER.BASE,
                "utc_now",
                return_value=datetime(2026, 8, 6, 12, 0, 5, 300000, timezone.utc),
            ),
        ):
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
        checked = check_collector_result(CHECKER_PATH, result)
        self.assertEqual(checked.returncode, 0, checked.stderr)

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

    def test_banked_era_observation_keeps_the_frozen_policy_kid(self) -> None:
        """The banked Result names a superseded adapter digest, so its kid
        stays the frozen policy's issuance-era value (A145)."""
        observed = self.observed()
        self.assertEqual(
            observed["assertion_descriptor"]["kid"], "patchyard-39acdfd2bfc0acb0"
        )
        result = self.run_checker(
            "--observation", str(self.write(observed, "banked-era.json"))
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_current_adapter_observation_must_carry_the_registry_kid(self) -> None:
        stale = self.observed()
        stale["source"]["issuance_adapter_sha256"] = digest(ADAPTER_PATH)
        result = self.run_checker(
            "--observation", str(self.write(stale, "era-stale.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("trusted signing identity", result.stderr)

        current = self.observed()
        current["source"]["issuance_adapter_sha256"] = digest(ADAPTER_PATH)
        current["assertion_descriptor"]["kid"] = REGISTRY_KID
        result = self.run_checker(
            "--observation", str(self.write(current, "era-current.json"))
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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
                "http_status": 401,
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

        with (
            mock.patch.object(
                EXPIRY_ADAPTER,
                "mint_expired_assertion",
                return_value=("synthetic.assertion.signature", descriptor),
            ),
            mock.patch.object(
                EXPIRY_ADAPTER.BASE,
                "utc_now",
                return_value=datetime(2026, 8, 7, 12, 0, 0, 300000, timezone.utc),
            ),
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
        self.assertEqual(
            result["response_predicate"],
            {
                "enforced": True,
                "http_status": 401,
                "access_token_supplied": False,
                "basis": "observed-openai-expired-assertion-response",
            },
        )
        self.assertIs(result["qualification_evidence"], False)
        checked = check_collector_result(EXPIRY_CHECKER_PATH, result)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        relabelled = deepcopy(result)
        relabelled["qualification_evidence"] = True
        refused = check_collector_result(
            EXPIRY_CHECKER_PATH, relabelled, mode="--evidence"
        )
        self.assertEqual(refused.returncode, 1)
        self.assertIn("A151 liveness preflight", refused.stderr)


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
        value["response_predicate"] = {
            "enforced": True,
            "http_status": 401,
            "access_token_supplied": False,
            "basis": "observed-openai-expired-assertion-response",
        }
        value["expiry_denial"] = {
            "source": "openai_http_response",
            "http_status": 401,
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
        wrong_status["expiry_denial"]["http_status"] = 418
        result = self.run_checker(
            "--observation", str(self.write(wrong_status, "wrong-status.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("was not HTTP 401", result.stderr)

        with_bearer = self.observed()
        with_bearer["expiry_denial"]["access_token_supplied"] = True
        result = self.run_checker(
            "--observation", str(self.write(with_bearer, "bearer.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("supplied a bearer", result.stderr)

    def test_unenforced_predicate_is_refused_on_an_observation(self) -> None:
        value = self.observed()
        value["response_predicate"] = {
            "enforced": False,
            "basis": "no-observed-openai-expired-assertion-response",
        }
        result = self.run_checker(
            "--observation", str(self.write(value, "unenforced.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "predicate does not match the reviewed expired-assertion denial",
            result.stderr,
        )

    def test_banked_result_is_qualification_evidence(self) -> None:
        defaulted = self.run_checker()
        self.assertEqual(defaulted.returncode, 0, defaulted.stderr)
        self.assertIn("qualification evidence", defaulted.stdout)
        evidenced = self.run_checker(
            "--evidence",
            str(ROOT / "research/isolation/results/openai-expiry-denial.json"),
        )
        self.assertEqual(evidenced.returncode, 0, evidenced.stderr)
        self.assertIn("qualification evidence", evidenced.stdout)

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

    def test_checker_requires_isolated_python(self) -> None:
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

    def test_observation_accepts_false_but_evidence_requires_true(self) -> None:
        value = self.observed()
        result = self.run_checker(
            "--observation", str(self.write(value, "observed.json"))
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        refused = self.run_checker(
            "--evidence", str(self.write(value, "nonqualifying.json"))
        )
        self.assertEqual(refused.returncode, 1)
        self.assertIn("is not qualification evidence", refused.stderr)

        value["qualification_evidence"] = "true"
        malformed = self.run_checker(
            "--observation", str(self.write(value, "malformed-boolean.json"))
        )
        self.assertEqual(malformed.returncode, 1)
        self.assertIn("is not boolean", malformed.stderr)

    def test_evidence_mode_rejects_in_progress_and_failed_inputs(self) -> None:
        for status, message in (
            ("in_progress", "in-progress"),
            ("failed", "failed"),
        ):
            with self.subTest(status=status):
                value = {"status": status, "qualification_evidence": True}
                result = self.run_checker(
                    "--evidence", str(self.write(value, f"{status}.json"))
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)

    def test_banked_result_is_qualification_evidence(self) -> None:
        defaulted = self.run_checker()
        self.assertEqual(defaulted.returncode, 0, defaulted.stderr)
        self.assertIn("qualification evidence", defaulted.stdout)
        evidenced = self.run_checker(
            "--evidence",
            str(ROOT / "research/isolation/results/openai-crash-cleanup.json"),
        )
        self.assertEqual(evidenced.returncode, 0, evidenced.stderr)
        self.assertIn("qualification evidence", evidenced.stdout)

    def test_crash_collector_result_passes_its_checker(self) -> None:
        observed = self.observed()
        in_progress = observed["in_progress_record"]
        result = CRASH_ADAPTER.assemble_result(
            run_id=observed["run_id"],
            attempt_path=Path(in_progress["path"]),
            attempt=deepcopy(in_progress["record"]),
            attempt_sha256=in_progress["sha256_at_collection"],
            checkpoint=deepcopy(observed["checkpoint"]),
            kill=deepcopy(observed["kill"]),
            positive=deepcopy(observed["positive_control"]),
            post=deepcopy(observed["post_kill_search"]),
            rejections=deepcopy(observed["checker_rejections"]),
        )
        checked = self.run_checker(
            "--evidence", str(self.write(result, "collector-result.json"))
        )
        self.assertIs(result["qualification_evidence"], True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_exact_keys_utc_and_credential_hygiene_fail_closed(self) -> None:
        extra = self.observed()
        extra["qualification_evidence"] = True
        extra["unexpected"] = True
        result = self.run_checker(
            "--evidence", str(self.write(extra, "extra.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected evidence shape", result.stderr)

        order = self.observed()
        order["qualification_evidence"] = True
        order["post_kill_search"]["observed_at"] = (
            "2026-08-07T11:59:59Z"
        )
        result = self.run_checker(
            "--evidence", str(self.write(order, "order.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("observations are out of order", result.stderr)

        credential = self.observed()
        credential["qualification_evidence"] = True
        credential["checkpoint"]["exchange_response"]["request_id"] = (
            "eyJsynthetic.payload.signature"
        )
        result = self.run_checker(
            "--evidence", str(self.write(credential, "credential.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("credential-shaped material", result.stderr)

    def test_sigterm_vacuous_search_and_premature_enforcement_are_rejected(self) -> None:
        sigterm = self.observed()
        sigterm["qualification_evidence"] = True
        sigterm["kill"].update(
            {"signal_name": "SIGTERM", "signal_number": 15, "child_returncode": -15}
        )
        result = self.run_checker(
            "--evidence", str(self.write(sigterm, "sigterm.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("not terminated by SIGKILL", result.stderr)

        vacuous = self.observed()
        vacuous["qualification_evidence"] = True
        vacuous["positive_control"].update(
            {
                "credential_material_found": False,
                "material_classes_found": [],
                "matches": [],
            }
        )
        result = self.run_checker(
            "--evidence", str(self.write(vacuous, "vacuous.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("positive control found no credential material", result.stderr)

        enforced = self.observed()
        enforced["qualification_evidence"] = True
        enforced["response_predicate"]["enforced"] = True
        result = self.run_checker(
            "--evidence", str(self.write(enforced, "enforced.json"))
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("predicate was enforced prematurely", result.stderr)

    def test_evidence_mode_rechecks_instrument_record_and_exposure_boundary(self) -> None:
        for field, nested, message in (
            ("post_kill_search", "search_contract_sha256", "different instruments"),
            ("in_progress_record", "unchanged", "terminal relabelling path"),
            (
                "provider_exposure_boundary",
                "provider_side_invalidation_proven",
                "conflates local cleanup",
            ),
        ):
            with self.subTest(field=field):
                value = self.observed()
                value["qualification_evidence"] = True
                value[field][nested] = False if nested == "unchanged" else True
                result = self.run_checker(
                    "--evidence", str(self.write(value, f"{field}.json"))
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)

    def test_checker_requires_isolated_python(self) -> None:
        result = self.run_checker("--allow-missing-results", isolated=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires python3 -I", result.stderr)


if __name__ == "__main__":
    unittest.main()
