from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import base64
import json
import pathlib
import subprocess
import tempfile
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
HARNESS_PATH = ROOT / "tools/anthropic-wif-lifecycle.py"
ADMIN_PATH = ROOT / "tools/anthropic-wif-lifecycle-admin.py"
EXPIRY_CHECKER = ROOT / "tools/check-anthropic-expiry.py"
REVOCATION_CHECKER = ROOT / "tools/check-anthropic-revocation.py"
POLICY_PATH = ROOT / "policy/anthropic-wif.json"
EXPECTED_HARNESS_SOURCE_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
EXPECTED_ADMIN_SOURCE_SHA256 = (
    "9381bbf1fd2d892ac35c60c70262aa6e333b85f6e1c6dbea61ce665398d4fb2d"
)
ERROR_SHAPE = {
    "top_level_keys": ["error", "request_id", "type"],
    "error_value_type": "object",
    "error_object_keys": ["message", "type"],
}
ERROR_SHAPE_WITHOUT_REQUEST_ID = {
    "top_level_keys": ["error", "type"],
    "error_value_type": "object",
    "error_object_keys": ["message", "type"],
}


def load_exact_source_module(
    name: str, path: pathlib.Path, expected: str
) -> types.ModuleType:
    source = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(source).hexdigest() != expected:
        raise RuntimeError(f"{path.name} differs from its exact source binding")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = None
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


HARNESS = load_exact_source_module(
    "anthropic_wif_lifecycle", HARNESS_PATH, EXPECTED_HARNESS_SOURCE_SHA256
)
ADMIN = load_exact_source_module(
    "anthropic_wif_lifecycle_admin", ADMIN_PATH, EXPECTED_ADMIN_SOURCE_SHA256
)


def iso(value: datetime, *, microseconds: bool = True) -> str:
    timespec = "microseconds" if microseconds else "seconds"
    return value.isoformat(timespec=timespec).replace("+00:00", "Z")


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeAdmin:
    def __init__(self, policy: dict[str, object], current: dict[str, object]) -> None:
        self.policy = policy
        self.workspace_ids = [policy["workspace"]["id"]]
        self.issuer_keys = [current]
        self.calls: list[tuple[str, str, object]] = []
        self.counter = 0
        self.start = datetime(2026, 8, 2, tzinfo=timezone.utc)

    def response(self, payload: dict[str, object]) -> dict[str, object]:
        self.counter += 1
        observed = self.start + timedelta(seconds=self.counter)
        return {
            "status": 200,
            "headers": {
                "request-id": f"req_admin{self.counter}",
                "date": observed.strftime("%a, %d %b %Y %H:%M:%S GMT"),
            },
            "payload": payload,
            "observed_at": iso(observed),
        }

    def rule(self) -> dict[str, object]:
        policy = self.policy
        return {
            "id": policy["rule"]["id"],
            "name": policy["rule"]["name"],
            "description": policy["rule"]["description"],
            "issuer_id": policy["issuer"]["id"],
            "archived_at": None,
            "applies_to_all_workspaces": False,
            "workspace_ids": list(self.workspace_ids),
            "oauth_scope": policy["rule"]["oauth_scope"],
            "token_lifetime_seconds": policy["rule"]["token_lifetime_seconds"],
            "target": {
                "type": "service_account",
                "service_account_id": policy["service_account"]["id"],
            },
            "match": {
                "subject_prefix": policy["rule"]["subject"],
                "audience": policy["rule"]["audience"],
                "claims": policy["rule"]["claims"],
                "condition": None,
            },
        }

    def issuer(self) -> dict[str, object]:
        policy = self.policy
        return {
            "id": policy["issuer"]["id"],
            "name": policy["issuer"]["name"],
            "issuer_url": policy["issuer"]["issuer_url"],
            "archived_at": None,
            "check_jti": policy["issuer"]["check_jti"],
            "max_jwt_lifetime_seconds": policy["issuer"][
                "max_jwt_lifetime_seconds"
            ],
            "jwks": {"type": "inline", "keys": deepcopy(self.issuer_keys)},
        }

    def request(
        self, method: str, path: str, body: dict[str, object] | None = None
    ) -> dict[str, object]:
        self.calls.append((method, path, deepcopy(body)))
        rule_path = f"/v1/organizations/federation_rules/{self.policy['rule']['id']}"
        issuer_path = (
            f"/v1/organizations/federation_issuers/{self.policy['issuer']['id']}"
        )
        workspace = self.policy["workspace"]["id"]
        if method == "GET" and path == rule_path:
            return self.response(self.rule())
        if method == "DELETE" and path == f"{rule_path}/workspaces/{workspace}":
            self.workspace_ids = []
            return self.response(
                {
                    "federation_rule_id": self.policy["rule"]["id"],
                    "type": "federation_rule_workspace_deleted",
                    "workspace_id": workspace,
                }
            )
        if method == "POST" and path == f"{rule_path}/workspaces":
            self.workspace_ids = [workspace]
            return self.response(
                {
                    "federation_rule_id": self.policy["rule"]["id"],
                    "type": "federation_rule_workspace",
                    "workspace_id": workspace,
                }
            )
        if method == "GET" and path == issuer_path:
            return self.response(self.issuer())
        if method == "POST" and path == issuer_path:
            assert body is not None
            self.issuer_keys = deepcopy(body["jwks"]["keys"])
            return self.response(self.issuer())
        raise AssertionError((method, path, body))


class AnthropicLifecycleAdminContract(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ADMIN.load_policy()
        self.current = {
            "alg": "RS256",
            "e": "AQAB",
            "kid": "patchyard-1111111111111111",
            "kty": "RSA",
            "n": base64.urlsafe_b64encode(b"\x81" + b"c" * 383).decode().rstrip("="),
            "use": "sig",
        }
        self.replacement = {
            "alg": "RS256",
            "e": "AQAB",
            "kid": "patchyard-2222222222222222",
            "kty": "RSA",
            "n": base64.urlsafe_b64encode(b"\x82" + b"r" * 383).decode().rstrip("="),
            "use": "sig",
        }
        self.run_id = "anthropic-l3-20260802-0123456789"

    def test_rule_mapping_disable_and_restore_are_exact_and_read_back(self) -> None:
        api = FakeAdmin(self.policy, self.current)
        disabled = ADMIN.rule_operation(
            api, self.policy, "rule-disable", self.run_id, True
        )
        self.assertEqual(disabled["event_type"], "rule_disabled")
        self.assertEqual(disabled["state_before"]["workspace_ids"], [self.policy["workspace"]["id"]])
        self.assertEqual(disabled["state_after"]["workspace_ids"], [])
        restored = ADMIN.rule_operation(
            api, self.policy, "rule-restore", self.run_id, True
        )
        self.assertEqual(restored["event_type"], "rule_restored")
        self.assertEqual(restored["state_before"]["workspace_ids"], [])
        self.assertEqual(restored["state_after"]["workspace_ids"], [self.policy["workspace"]["id"]])
        methods = [method for method, _, _ in api.calls]
        self.assertEqual(methods, ["GET", "DELETE", "GET", "GET", "POST", "GET"])

    def test_issuer_rotation_overlaps_before_retiring_exact_old_key(self) -> None:
        api = FakeAdmin(self.policy, self.current)
        staged = ADMIN.issuer_operation(
            api,
            self.policy,
            "issuer-stage",
            self.run_id,
            True,
            self.replacement,
            self.current,
        )
        self.assertEqual(staged["event_type"], "issuer_rotation_staged")
        self.assertEqual(len(staged["state_before"]["keys"]), 1)
        self.assertEqual(len(staged["state_after"]["keys"]), 2)
        retired = ADMIN.issuer_operation(
            api,
            self.policy,
            "issuer-retire",
            self.run_id,
            True,
            self.replacement,
            self.current,
        )
        self.assertEqual(retired["event_type"], "issuer_retired_key")
        self.assertEqual(len(retired["state_before"]["keys"]), 2)
        self.assertEqual(retired["state_after"]["keys"], [ADMIN.jwk_descriptor(self.replacement)])

    def test_rotation_has_fail_closed_rollback_paths_on_both_sides_of_retire(self) -> None:
        api = FakeAdmin(self.policy, self.current)
        ADMIN.issuer_operation(
            api,
            self.policy,
            "issuer-stage",
            self.run_id,
            True,
            self.replacement,
            self.current,
        )
        rolled_back = ADMIN.issuer_operation(
            api,
            self.policy,
            "issuer-rollback-stage",
            self.run_id,
            True,
            self.replacement,
            self.current,
        )
        self.assertEqual(rolled_back["state_after"]["keys"], [ADMIN.jwk_descriptor(self.current)])
        ADMIN.issuer_operation(
            api,
            self.policy,
            "issuer-stage",
            self.run_id,
            True,
            self.replacement,
            self.current,
        )
        ADMIN.issuer_operation(
            api,
            self.policy,
            "issuer-retire",
            self.run_id,
            True,
            self.replacement,
            self.current,
        )
        restored = ADMIN.issuer_operation(
            api,
            self.policy,
            "issuer-restore-overlap",
            self.run_id,
            True,
            self.replacement,
            self.current,
        )
        self.assertEqual(len(restored["state_after"]["keys"]), 2)

    def test_admin_refuses_drift_before_any_mutation(self) -> None:
        api = FakeAdmin(self.policy, self.current)
        api.workspace_ids = [self.policy["workspace"]["id"], "wrkspc_unreviewed"]
        with self.assertRaisesRegex(ADMIN.AdminError, "workspace mappings differs"):
            ADMIN.rule_operation(api, self.policy, "rule-disable", self.run_id, True)
        self.assertEqual([call[0] for call in api.calls], ["GET"])

    def test_issuer_update_refuses_key_drift_before_any_mutation(self) -> None:
        api = FakeAdmin(self.policy, self.replacement)
        with self.assertRaisesRegex(ADMIN.AdminError, "expected current issuer key"):
            ADMIN.issuer_operation(
                api,
                self.policy,
                "issuer-stage",
                self.run_id,
                True,
                self.replacement,
                self.current,
            )
        self.assertEqual([call[0] for call in api.calls], ["GET"])

    def test_post_failure_readback_reports_provider_state_after_lost_response(self) -> None:
        class LostDeleteResponse(FakeAdmin):
            def request(self, method, path, body=None):
                if method == "DELETE":
                    self.calls.append((method, path, deepcopy(body)))
                    self.workspace_ids = []
                    raise ADMIN.AdminError("simulated lost mutation response")
                return super().request(method, path, body)

        api = LostDeleteResponse(self.policy, self.current)
        with self.assertRaisesRegex(ADMIN.AdminError, "lost mutation response"):
            ADMIN.rule_operation(
                api, self.policy, "rule-disable", self.run_id, True
            )
        readback = ADMIN.post_failure_readback(
            api, self.policy, "rule-disable"
        )
        self.assertEqual(readback["status"], "observed")
        self.assertEqual(readback["state"]["workspace_ids"], [])

    def test_rule_mutation_discards_benign_provider_fields_by_name(self) -> None:
        class AddedRuleField(FakeAdmin):
            def request(self, method, path, body=None):
                response = super().request(method, path, body)
                if method == "DELETE":
                    response["payload"]["provider_note"] = "rule-value-must-not-cross"
                return response

        event = ADMIN.rule_operation(
            AddedRuleField(self.policy, self.current),
            self.policy,
            "rule-disable",
            self.run_id,
            True,
        )
        self.assertEqual(event["discarded_response_fields"], ["provider_note"])
        self.assertNotIn("rule-value-must-not-cross", json.dumps(event))

    def test_provider_jwk_discards_benign_additional_fields_by_name(self) -> None:
        class AddedJwkField(FakeAdmin):
            def issuer(self):
                issuer = super().issuer()
                for key in issuer["jwks"]["keys"]:
                    key["provider_note"] = "jwk-value-must-not-cross"
                return issuer

        event = ADMIN.issuer_operation(
            AddedJwkField(self.policy, self.current),
            self.policy,
            "issuer-stage",
            self.run_id,
            True,
            self.replacement,
            self.current,
        )
        self.assertEqual(event["discarded_response_fields"], ["provider_note"])
        self.assertNotIn("jwk-value-must-not-cross", json.dumps(event))

    def test_provider_jwk_rejects_credential_shaped_additional_field(self) -> None:
        class CredentialJwkField(FakeAdmin):
            def issuer(self):
                issuer = super().issuer()
                issuer["jwks"]["keys"][0]["provider_note"] = (
                    "sk-ant-oat01-synthetic-rejected-value"
                )
                return issuer

        with self.assertRaisesRegex(ADMIN.AdminError, "credential-shaped") as observed:
            ADMIN.issuer_operation(
                CredentialJwkField(self.policy, self.current),
                self.policy,
                "issuer-stage",
                self.run_id,
                True,
                self.replacement,
                self.current,
            )
        self.assertNotIn("synthetic-rejected-value", str(observed.exception))


class AnthropicLifecycleHarnessContract(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = HARNESS.load_policy()
        self.run_id = "anthropic-l3-20260802-0123456789"
        self.base = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
        self.key = {
            "kid": "patchyard-1111111111111111",
            "jwk_thumbprint_sha256": "1" * 64,
        }

    def response(
        self, status: int, payload: dict[str, object], seconds: int
    ) -> dict[str, object]:
        when = self.base + timedelta(seconds=seconds)
        return {
            "status": status,
            "headers": {
                "request-id": f"req_harness{seconds}",
                "date": when.strftime("%a, %d %b %Y %H:%M:%S GMT"),
            },
            "payload": payload,
            "requested_at": iso(when),
            "observed_at": iso(when + timedelta(microseconds=1)),
        }

    def exchange(self, payload: dict[str, object]):
        with mock.patch.object(
            HARNESS,
            "mint_assertion",
            return_value=("assertion-value", deepcopy(self.key)),
        ):
            return HARNESS.accepted_exchange(
                self.policy,
                pathlib.Path("/not/read"),
                self.run_id,
                request=lambda *args, **kwargs: self.response(200, payload, 0),
            )

    def exchange_payload(self) -> dict[str, object]:
        return {
            "access_token": "sk-ant-oat01-test-bearer",
            "expires_in": 300,
            "scope": "workspace:inference",
            "token_type": "Bearer",
        }

    def test_exchange_discards_real_additional_field_names_without_values(self) -> None:
        payload = self.exchange_payload()
        payload.update(
            {
                "next_challenge": "challenge-value-must-not-cross",
                "next_challenge_expires_in": 271828,
                "workspace_id": "workspace-value-must-not-cross",
            }
        )
        result, token = self.exchange(payload)
        self.assertEqual(token, "sk-ant-oat01-test-bearer")
        self.assertEqual(
            result["exchange"]["discarded_response_fields"],
            ["next_challenge", "next_challenge_expires_in", "workspace_id"],
        )
        serialized = json.dumps(result)
        self.assertNotIn("challenge-value-must-not-cross", serialized)
        self.assertNotIn("workspace-value-must-not-cross", serialized)
        self.assertNotIn("271828", serialized)
        self.assertNotIn("test-bearer", serialized)

    def test_exchange_rejects_anthropic_credential_in_additional_field(self) -> None:
        payload = self.exchange_payload()
        payload["provider_extra"] = "sk-ant-oat01-synthetic-rejected-value"
        with self.assertRaisesRegex(
            HARNESS.LifecycleError, "credential-shaped"
        ) as observed:
            self.exchange(payload)
        self.assertNotIn("synthetic-rejected-value", str(observed.exception))

    def test_exchange_rejects_jwt_in_additional_field(self) -> None:
        payload = self.exchange_payload()
        payload["provider_extra"] = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature"
        with self.assertRaisesRegex(
            HARNESS.LifecycleError, "credential-shaped"
        ) as observed:
            self.exchange(payload)
        self.assertNotIn("eyJhbGci", str(observed.exception))

    def test_exchange_rejects_high_entropy_additional_field(self) -> None:
        payload = self.exchange_payload()
        payload["provider_extra"] = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" * 2
        )
        with self.assertRaisesRegex(HARNESS.LifecycleError, "credential-shaped"):
            self.exchange(payload)

    def test_exchange_rejects_each_missing_documented_field(self) -> None:
        for field in ("access_token", "expires_in", "scope", "token_type"):
            with self.subTest(field=field):
                payload = self.exchange_payload()
                del payload[field]
                with self.assertRaisesRegex(
                    HARNESS.LifecycleError, "missing documented fields"
                ):
                    self.exchange(payload)

    def test_exchange_preserves_every_documented_field_predicate(self) -> None:
        cases = {
            "wrong token type": ("token_type", "Basic", "exchange token type"),
            "wrong scope": ("scope", "workspace:admin", "exchange scope"),
            "short expiry": (
                "expires_in",
                59,
                "exchange lifetime is outside one to five minutes",
            ),
            "long expiry": (
                "expires_in",
                301,
                "exchange lifetime is outside one to five minutes",
            ),
            "boolean expiry": (
                "expires_in",
                True,
                "exchange lifetime is not an integer",
            ),
            "wrong token prefix": (
                "access_token",
                "not-an-anthropic-token",
                "bounded WIF bearer type",
            ),
            "non-string token": (
                "access_token",
                123,
                "bounded WIF bearer type",
            ),
        }
        for name, (field, value, diagnostic) in cases.items():
            with self.subTest(name=name):
                payload = self.exchange_payload()
                payload[field] = value
                with self.assertRaisesRegex(HARNESS.LifecycleError, diagnostic):
                    self.exchange(payload)

    def test_expiry_reuses_one_bearer_once_after_expiry_and_never_records_it(self) -> None:
        calls: list[tuple[str, str, object, object]] = []

        def request(method, path, *, body=None, bearer=None):
            calls.append((method, path, deepcopy(body), bearer))
            if len(calls) == 1:
                return self.response(
                    200,
                    {
                        "access_token": "sk-ant-oat01-test-bearer",
                        "expires_in": 300,
                        "scope": "workspace:inference",
                        "token_type": "Bearer",
                    },
                    0,
                )
            if len(calls) == 2:
                return self.response(
                    200,
                    {"data": [{"id": "claude-opus-5"}], "request_id": "req_harness2"},
                    2,
                )
            denial = self.response(
                401,
                {
                    "type": "error",
                    "error": {"type": "authentication_error", "message": "expired"},
                },
                301,
            )
            del denial["headers"]["request-id"]
            return denial

        waits: list[float] = []
        progress: list[tuple[str, object]] = []
        with mock.patch.object(
            HARNESS,
            "mint_assertion",
            return_value=("assertion-value", deepcopy(self.key)),
        ):
            evidence = HARNESS.expiry_evidence(
                self.policy,
                pathlib.Path("/not/read"),
                self.run_id,
                request=request,
                sleeper=waits.append,
                clock=lambda: self.base.timestamp(),
                progress=lambda phase, observation: progress.append(
                    (phase, deepcopy(observation))
                ),
            )
        self.assertEqual(
            [(method, path) for method, path, _, _ in calls],
            [
                ("POST", "/v1/oauth/token"),
                ("GET", "/v1/models?limit=1"),
                ("GET", "/v1/models?limit=1"),
            ],
        )
        self.assertEqual(calls[1][3], "sk-ant-oat01-test-bearer")
        self.assertEqual(calls[2][3], "sk-ant-oat01-test-bearer")
        self.assertEqual(waits, [301.0])
        self.assertEqual(
            [phase for phase, _ in progress],
            [
                "exchange_requested",
                "exchange_accepted",
                "models_requested",
                "models_accepted",
                "waiting_for_expiry",
                "expiry_denial_requested",
                "expiry_denial_accepted",
            ],
        )
        serialized = json.dumps(evidence)
        self.assertNotIn("test-bearer", serialized)
        self.assertNotIn("assertion-value", serialized)
        self.assertEqual(evidence["expiry_denial"]["http_status"], 401)
        self.assertIsNone(evidence["expiry_denial"]["request_id"])
        self.assertIs(evidence["expiry_denial"]["request_id_supplied"], False)
        self.assertEqual(
            evidence["expiry_denial"]["response_shape"],
            ERROR_SHAPE_WITHOUT_REQUEST_ID,
        )
        self.assertLess(
            evidence["issuance"]["expires_at"],
            evidence["expiry_denial"]["request_started_at"],
        )

    def test_400_exchange_denial_still_requires_and_records_request_id(self) -> None:
        response = self.response(
            400,
            {
                "type": "error",
                "error": {"type": "invalid_grant", "message": "disabled"},
                "request_id": "req_harness3",
            },
            3,
        )
        with mock.patch.object(
            HARNESS,
            "mint_assertion",
            return_value=("assertion-value", deepcopy(self.key)),
        ):
            event = HARNESS.denied_exchange_event(
                "rule_disabled_exchange_denial",
                "active",
                self.policy,
                pathlib.Path("/not/read"),
                self.run_id,
                request=lambda *args, **kwargs: deepcopy(response),
            )
        self.assertEqual(event["exchange_denial"]["request_id"], "req_harness3")

        del response["headers"]["request-id"]
        del response["payload"]["request_id"]
        with (
            mock.patch.object(
                HARNESS,
                "mint_assertion",
                return_value=("assertion-value", deepcopy(self.key)),
            ),
            self.assertRaisesRegex(
                HARNESS.LifecycleError, "request ID is absent or malformed"
            ),
        ):
            HARNESS.denied_exchange_event(
                "rule_disabled_exchange_denial",
                "active",
                self.policy,
                pathlib.Path("/not/read"),
                self.run_id,
                request=lambda *args, **kwargs: deepcopy(response),
            )

    def test_atomic_activation_preserves_old_key_before_installing_replacement(self) -> None:
        current_jwk = {
            "alg": "RS256",
            "e": "AQAB",
            "kid": "patchyard-1111111111111111",
            "kty": "RSA",
            "n": base64.urlsafe_b64encode(b"\x81" + b"c" * 383).decode().rstrip("="),
            "use": "sig",
        }
        replacement_jwk = {
            **current_jwk,
            "kid": "patchyard-2222222222222222",
            "n": base64.urlsafe_b64encode(b"\x82" + b"r" * 383).decode().rstrip("="),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            active = root / "active.pem"
            replacement = root / "replacement.pem"
            expected = root / "current-jwks.json"
            retired = root / "retired.pem"
            active.write_bytes(b"old-private-key")
            replacement.write_bytes(b"new-private-key")
            expected.write_text(json.dumps({"keys": [current_jwk]}))

            def public(path):
                content = pathlib.Path(path).read_bytes()
                if content == b"old-private-key":
                    return deepcopy(current_jwk)
                if content == b"new-private-key":
                    return deepcopy(replacement_jwk)
                raise AssertionError(content)

            with (
                mock.patch.object(HARNESS, "ACTIVE_SIGNING_KEY", active),
                mock.patch.object(HARNESS, "load_public_jwk", side_effect=public),
                mock.patch.object(HARNESS, "validate_root_private_key"),
                mock.patch.object(HARNESS.os, "fchown"),
            ):
                event = HARNESS.activate_replacement(
                    self.policy,
                    replacement,
                    expected,
                    retired,
                    self.run_id,
                )
            self.assertEqual(retired.read_bytes(), b"old-private-key")
            self.assertEqual(active.read_bytes(), b"new-private-key")
            self.assertTrue(event["activation"]["retired_key_staged"])

    def test_reserved_output_is_valid_before_and_after_terminal_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "event.json"
            output = HARNESS.ReservedOutput(path, {"status": "in_progress"})
            self.assertEqual(json.loads(path.read_text()), {"status": "in_progress"})
            output.finish({"status": "failed", "post_failure_state": {}})
            self.assertEqual(json.loads(path.read_text())["status"], "failed")

    def test_private_key_staging_cannot_escape_the_exact_run_directory(self) -> None:
        stage = pathlib.Path("/run/patchyard-anthropic") / self.run_id
        HARNESS.require_stage_path(stage / "retired.pem", stage, "retired key")
        with self.assertRaisesRegex(HARNESS.LifecycleError, "outside the exact"):
            HARNESS.require_stage_path(
                stage.parent / "other-run" / "retired.pem", stage, "retired key"
            )


class EvidenceFixtures:
    def __init__(self) -> None:
        self.policy = json.loads(POLICY_PATH.read_text())
        self.base = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
        self.old = {
            "kid": "patchyard-1111111111111111",
            "jwk_thumbprint_sha256": "1" * 64,
        }
        self.new = {
            "kid": "patchyard-2222222222222222",
            "jwk_thumbprint_sha256": "2" * 64,
        }
        self.run_id = "anthropic-l3-20260802-0123456789"
        self.policy_sha = digest(POLICY_PATH)
        self.harness_sha = digest(HARNESS_PATH)
        self.admin_sha = digest(ADMIN_PATH)
        self.request_counter = 0

    def request_id(self) -> str:
        self.request_counter += 1
        return f"req_fixture{self.request_counter}"

    def issuance(self, event_time: datetime) -> dict[str, object]:
        issued = event_time - timedelta(seconds=2)
        return {
            "endpoint": "/v1/oauth/token",
            "http_status": 200,
            "request_id": self.request_id(),
            "provider_date": iso(issued, microseconds=False),
            "observed_at": iso(event_time - timedelta(seconds=1)),
            "issued_at": iso(issued, microseconds=False),
            "expires_at": iso(issued + timedelta(seconds=300), microseconds=False),
            "expires_in": 300,
            "token_type": "Bearer",
            "scope": "workspace:inference",
            "discarded_response_fields": [],
            "service_account_id": self.policy["service_account"]["id"],
            "rule_id": self.policy["rule"]["id"],
            "workspace_id": self.policy["workspace"]["id"],
        }

    def models(self, event_time: datetime) -> dict[str, object]:
        return {
            "endpoint": "/v1/models?limit=1",
            "http_status": 200,
            "request_id": self.request_id(),
            "provider_date": iso(event_time, microseconds=False),
            "observed_at": iso(event_time),
            "model_id": "claude-opus-5",
        }

    def positive(
        self, event_type: str, event_time: datetime, key: dict[str, str], role: str
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "provider": "anthropic",
            "run_id": self.run_id,
            "event_type": event_type,
            "observed_at": iso(event_time),
            "key_role": role,
            "signing_key": deepcopy(key),
            "exchange": self.issuance(event_time),
            "models": self.models(event_time),
            "credential_removed_at": iso(event_time + timedelta(microseconds=1)),
            "source": {
                "policy_sha256": self.policy_sha,
                "lifecycle_harness_sha256": self.harness_sha,
            },
        }

    def denial(
        self, event_type: str, event_time: datetime, key: dict[str, str], role: str
    ) -> dict[str, object]:
        denial = {
            "source": "anthropic_http_response",
            "endpoint": "/v1/oauth/token",
            "http_status": 400,
            "request_id": self.request_id(),
            "provider_date": iso(event_time, microseconds=False),
            "observed_at": iso(event_time),
            "error_type": "invalid_grant",
            "response_shape": deepcopy(ERROR_SHAPE),
        }
        return {
            "schema_version": 1,
            "provider": "anthropic",
            "run_id": self.run_id,
            "event_type": event_type,
            "observed_at": iso(event_time),
            "key_role": role,
            "signing_key": deepcopy(key),
            "exchange_denial": denial,
            "credential_removed_at": iso(event_time + timedelta(microseconds=1)),
            "source": {
                "policy_sha256": self.policy_sha,
                "lifecycle_harness_sha256": self.harness_sha,
            },
        }

    def receipt(self, method: str, endpoint: str, when: datetime) -> dict[str, object]:
        return {
            "method": method,
            "endpoint": endpoint,
            "http_status": 200,
            "request_id": self.request_id(),
            "provider_date": iso(when, microseconds=False),
            "observed_at": iso(when),
        }

    def rule_state(self, enabled: bool) -> dict[str, object]:
        return {
            "rule_id": self.policy["rule"]["id"],
            "workspace_id": self.policy["workspace"]["id"],
            "workspace_ids": [self.policy["workspace"]["id"]] if enabled else [],
            "applies_to_all_workspaces": False,
            "archived": False,
        }

    def issuer_state(self, keys: list[dict[str, str]]) -> dict[str, object]:
        return {
            "issuer_id": self.policy["issuer"]["id"],
            "jwks_type": "inline",
            "keys": deepcopy(keys),
            "archived": False,
        }

    def admin_event(
        self,
        event_type: str,
        event_time: datetime,
        before: dict[str, object],
        after: dict[str, object],
    ) -> dict[str, object]:
        rule_base = f"/v1/organizations/federation_rules/{self.policy['rule']['id']}"
        issuer_base = f"/v1/organizations/federation_issuers/{self.policy['issuer']['id']}"
        if event_type == "rule_disabled":
            method = "DELETE"
            endpoint = f"{rule_base}/workspaces/{self.policy['workspace']['id']}"
            readback = rule_base
        elif event_type == "rule_restored":
            method = "POST"
            endpoint = f"{rule_base}/workspaces"
            readback = rule_base
        else:
            method = "POST"
            endpoint = issuer_base
            readback = issuer_base
        return {
            "schema_version": 1,
            "provider": "anthropic",
            "run_id": self.run_id,
            "event_type": event_type,
            "observed_at": iso(event_time),
            "mutation": self.receipt(method, endpoint, event_time - timedelta(seconds=1)),
            "readback": self.receipt("GET", readback, event_time),
            "state_before": deepcopy(before),
            "state_after": deepcopy(after),
            "discarded_response_fields": [],
            "source": {
                "policy_sha256": self.policy_sha,
                "admin_tool_sha256": self.admin_sha,
            },
        }

    def expiry(self) -> dict[str, object]:
        issued = self.base
        positive = issued + timedelta(seconds=1)
        expires = issued + timedelta(seconds=300)
        denial_time = expires + timedelta(seconds=1)
        issuance = self.issuance(issued + timedelta(seconds=2))
        issuance["provider_date"] = iso(issued, microseconds=False)
        issuance["issued_at"] = iso(issued, microseconds=False)
        issuance["expires_at"] = iso(expires, microseconds=False)
        issuance["observed_at"] = iso(issued + timedelta(microseconds=1))
        control = self.models(positive)
        denial = {
            "source": "anthropic_http_response",
            "endpoint": "/v1/models?limit=1",
            "http_status": 401,
            "request_id": None,
            "request_id_supplied": False,
            "provider_date": iso(denial_time, microseconds=False),
            "request_started_at": iso(denial_time),
            "observed_at": iso(denial_time + timedelta(microseconds=1)),
            "error_type": "authentication_error",
            "response_shape": deepcopy(ERROR_SHAPE_WITHOUT_REQUEST_ID),
        }
        return {
            "schema_version": 1,
            "provider": "anthropic",
            "qualification_requirement": "credential-expiry-denial",
            "authorization_ruling": "A113",
            "run_id": self.run_id,
            "signing_key": deepcopy(self.old),
            "issuance": issuance,
            "positive_control": control,
            "expiry_denial": denial,
            "credential_removed_at": iso(denial_time + timedelta(microseconds=2)),
            "policy_sha256": self.policy_sha,
            "lifecycle_harness_sha256": self.harness_sha,
        }

    def expiry_with_request_id(self) -> dict[str, object]:
        fixture = self.expiry()
        fixture["expiry_denial"]["request_id"] = self.request_id()
        fixture["expiry_denial"]["request_id_supplied"] = True
        fixture["expiry_denial"]["response_shape"] = deepcopy(ERROR_SHAPE)
        return fixture

    def revocation(self) -> dict[str, object]:
        times = [self.base + timedelta(seconds=10 * index) for index in range(1, 12)]
        enabled = self.rule_state(True)
        disabled = self.rule_state(False)
        old_only = self.issuer_state([self.old])
        overlap = self.issuer_state([self.old, self.new])
        new_only = self.issuer_state([self.new])
        activation = {
            "schema_version": 1,
            "provider": "anthropic",
            "run_id": self.run_id,
            "event_type": "replacement_key_activated",
            "observed_at": iso(times[7]),
            "activation": {
                "source": "local_atomic_key_activation",
                "active_key_path": "/etc/patchyard/anthropic-wif-signing.pem",
                "retired_key": deepcopy(self.old),
                "replacement_key": deepcopy(self.new),
                "retired_key_staged": True,
                "observed_at": iso(times[7]),
            },
            "source": {
                "policy_sha256": self.policy_sha,
                "lifecycle_harness_sha256": self.harness_sha,
            },
        }
        events = [
            self.positive("rule_enabled_positive", times[0], self.old, "active"),
            self.admin_event("rule_disabled", times[1], enabled, disabled),
            self.denial(
                "rule_disabled_exchange_denial", times[2], self.old, "active"
            ),
            self.admin_event("rule_restored", times[3], disabled, enabled),
            self.positive("rule_restored_positive", times[4], self.old, "active"),
            self.admin_event("issuer_rotation_staged", times[5], old_only, overlap),
            self.positive(
                "replacement_key_positive", times[6], self.new, "replacement_staging"
            ),
            activation,
            self.positive(
                "replacement_key_final_positive", times[8], self.new, "active"
            ),
            self.admin_event("issuer_retired_key", times[9], overlap, new_only),
            self.denial(
                "retired_key_exchange_denial", times[10], self.old, "retired_staging"
            ),
        ]
        return {
            "schema_version": 1,
            "provider": "anthropic",
            "qualification_requirement": "federation-revocation-and-key-rotation",
            "authorization_ruling": "A113",
            "run_id": self.run_id,
            "policy_sha256": self.policy_sha,
            "lifecycle_harness_sha256": self.harness_sha,
            "admin_tool_sha256": self.admin_sha,
            "events": events,
        }


class AnthropicLifecycleCheckerContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def check(
        self, checker: pathlib.Path, evidence: dict[str, object]
    ) -> subprocess.CompletedProcess[str]:
        path = self.root / f"{checker.stem}.json"
        path.write_text(json.dumps(evidence))
        return subprocess.run(
            ["python3", "-I", str(checker), "--evidence", str(path)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def check_raw(
        self, checker: pathlib.Path, evidence: str
    ) -> subprocess.CompletedProcess[str]:
        path = self.root / f"{checker.stem}-raw.json"
        path.write_text(evidence)
        return subprocess.run(
            ["python3", "-I", str(checker), "--evidence", str(path)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_expiry_401_without_request_id_fixture_passes_actual_checker(self) -> None:
        fixtures = EvidenceFixtures()
        evidence = fixtures.expiry()
        self.assertIsNone(evidence["expiry_denial"]["request_id"])
        self.assertIs(evidence["expiry_denial"]["request_id_supplied"], False)
        result = self.check(EXPIRY_CHECKER, evidence)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_identified_denials_and_complete_revocation_fixture_pass(self) -> None:
        fixtures = EvidenceFixtures()
        expiry = self.check(EXPIRY_CHECKER, fixtures.expiry_with_request_id())
        self.assertEqual(expiry.returncode, 0, expiry.stderr)

        fixtures = EvidenceFixtures()
        evidence = fixtures.revocation()
        positive_ids = [
            event[section]["request_id"]
            for event in evidence["events"]
            if event["event_type"]
            in {
                "rule_enabled_positive",
                "rule_restored_positive",
                "replacement_key_positive",
                "replacement_key_final_positive",
            }
            for section in ("exchange", "models")
        ]
        admin_ids = [
            event[section]["request_id"]
            for event in evidence["events"]
            if event["event_type"]
            in {
                "rule_disabled",
                "rule_restored",
                "issuer_rotation_staged",
                "issuer_retired_key",
            }
            for section in ("mutation", "readback")
        ]
        denial_ids = [
            event["exchange_denial"]["request_id"]
            for event in evidence["events"]
            if "exchange_denial" in event
        ]
        self.assertEqual((len(positive_ids), len(admin_ids), len(denial_ids)), (8, 8, 2))
        self.assertEqual(len(set(positive_ids + admin_ids + denial_ids)), 18)
        self.assertEqual(
            [
                event["exchange_denial"]["http_status"]
                for event in evidence["events"]
                if "exchange_denial" in event
            ],
            [400, 400],
        )
        revocation = self.check(REVOCATION_CHECKER, evidence)
        self.assertEqual(revocation.returncode, 0, revocation.stderr)

    def test_expiry_absence_claim_with_request_id_is_rejected(self) -> None:
        fixtures = EvidenceFixtures()
        expiry = fixtures.expiry()
        expiry["expiry_denial"]["request_id"] = "req_claimedabsent"
        result = self.check(EXPIRY_CHECKER, expiry)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("claims request-ID absence while carrying an ID", result.stderr)

    def test_missing_request_id_presence_observation_is_rejected(self) -> None:
        fixtures = EvidenceFixtures()
        expiry = fixtures.expiry()
        del expiry["expiry_denial"]["request_id_supplied"]
        result = self.check(EXPIRY_CHECKER, expiry)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expiry denial has an unexpected evidence shape", result.stderr)

    def test_expiry_denial_at_or_before_expiry_is_rejected(self) -> None:
        fixtures = EvidenceFixtures()
        expiry = fixtures.expiry()
        expiry["expiry_denial"]["request_started_at"] = expiry["issuance"][
            "expires_at"
        ]
        result = self.check(EXPIRY_CHECKER, expiry)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not begin strictly after expiry", result.stderr)

    def test_wrong_expiry_denial_status_or_error_type_is_rejected(self) -> None:
        for field, value in (("http_status", 400), ("error_type", "invalid_grant")):
            with self.subTest(field=field):
                fixtures = EvidenceFixtures()
                expiry = fixtures.expiry()
                expiry["expiry_denial"][field] = value
                result = self.check(EXPIRY_CHECKER, expiry)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("exact provider authentication denial", result.stderr)

    def test_missing_exchange_or_positive_control_request_id_is_rejected(self) -> None:
        for section, diagnostic in (
            ("issuance", "issuance request ID is malformed"),
            ("positive_control", "positive-control request ID is malformed"),
        ):
            with self.subTest(section=section):
                fixtures = EvidenceFixtures()
                expiry = fixtures.expiry()
                expiry[section]["request_id"] = None
                result = self.check(EXPIRY_CHECKER, expiry)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stderr)

    def test_revocation_400_denial_without_request_id_is_rejected(self) -> None:
        fixtures = EvidenceFixtures()
        revocation = fixtures.revocation()
        revocation["events"][2]["exchange_denial"]["request_id"] = None
        result = self.check(REVOCATION_CHECKER, revocation)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "rule_disabled_exchange_denial request ID is malformed", result.stderr
        )

    def test_fabricated_denials_are_rejected(self) -> None:
        fixtures = EvidenceFixtures()
        expiry = fixtures.expiry_with_request_id()
        expiry["expiry_denial"]["request_id"] = expiry["positive_control"][
            "request_id"
        ]
        result = self.check(EXPIRY_CHECKER, expiry)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("every distinct identified provider request", result.stderr)

        fixtures = EvidenceFixtures()
        revocation = fixtures.revocation()
        revocation["events"][2]["exchange_denial"]["request_id"] = revocation[
            "events"
        ][0]["exchange"]["request_id"]
        result = self.check(REVOCATION_CHECKER, revocation)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("18 distinct provider requests", result.stderr)

    def test_missing_positive_controls_are_rejected(self) -> None:
        fixtures = EvidenceFixtures()
        expiry = fixtures.expiry()
        del expiry["positive_control"]
        result = self.check(EXPIRY_CHECKER, expiry)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected evidence shape", result.stderr)

        fixtures = EvidenceFixtures()
        revocation = fixtures.revocation()
        del revocation["events"][0]
        result = self.check(REVOCATION_CHECKER, revocation)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing or reorders", result.stderr)

    def test_local_cleanup_never_substitutes_for_provider_denial(self) -> None:
        fixtures = EvidenceFixtures()
        expiry = fixtures.expiry()
        expiry["expiry_denial"]["source"] = "local_cleanup"
        result = self.check(EXPIRY_CHECKER, expiry)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a provider HTTP response", result.stderr)

        fixtures = EvidenceFixtures()
        revocation = fixtures.revocation()
        revocation["events"][2]["exchange_denial"]["source"] = "local_cleanup"
        result = self.check(REVOCATION_CHECKER, revocation)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a provider HTTP denial", result.stderr)

    def test_out_of_order_timestamps_are_rejected(self) -> None:
        fixtures = EvidenceFixtures()
        expiry = fixtures.expiry()
        expiry["expiry_denial"]["provider_date"] = expiry["positive_control"][
            "provider_date"
        ]
        result = self.check(EXPIRY_CHECKER, expiry)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive-before-expiry-before-denial", result.stderr)

        fixtures = EvidenceFixtures()
        revocation = fixtures.revocation()
        before_disable = revocation["events"][0]["observed_at"]
        revocation["events"][2]["observed_at"] = before_disable
        revocation["events"][2]["exchange_denial"]["observed_at"] = before_disable
        result = self.check(REVOCATION_CHECKER, revocation)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not strictly ordered", result.stderr)

    def test_duplicate_json_keys_are_rejected_before_contract_validation(self) -> None:
        duplicate = '{"schema_version":1,"schema_version":1}'
        for checker in (EXPIRY_CHECKER, REVOCATION_CHECKER):
            with self.subTest(checker=checker.name):
                result = self.check_raw(checker, duplicate)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("duplicate JSON key", result.stderr)


if __name__ == "__main__":
    unittest.main()
