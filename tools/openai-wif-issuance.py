#!/usr/bin/env python3
"""Record one attended OpenAI workload-identity token exchange.

The qualified Anthropic lifecycle harness is loaded by exact digest and is
never modified.  This adapter reuses its signing and durable-output hygiene,
but supplies an OpenAI policy, audience, token request, and response sanitizer.
No assertion or bearer is written to the result.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import types
from typing import Any, Callable
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy/openai-wif.json"
SIGNING_IDENTITIES_PATH = ROOT / "policy/signing-identities.json"
BASE_HARNESS_PATH = ROOT / "tools/anthropic-wif-lifecycle.py"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
SIGNING_KEY = Path("/etc/patchyard/openai-wif-signing.pem")
STAGING_ROOT = Path("/run/patchyard-openai")
TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
MAX_RESPONSE_BYTES = 1_000_000
RUN_ID_PATTERN = re.compile(r"openai-wif-[0-9]{8}-[0-9a-f]{10}")
KID_PATTERN = re.compile(r"patchyard-[0-9a-f]{16}")
SAFE_RESPONSE_STRING = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/+;-]{0,127}")
SAFE_FIELD_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
JWT_PATTERN = re.compile(
    r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
)
OPENAI_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
EXPECTED_POLICY = {
    "schema_version": 1,
    "provider": "openai",
    "organization": {
        "id": "org-000000000000000000000000",
        "name": "Example Company",
    },
    "project": {
        "id": "proj_4zpZhhPPNYCvPRE5vGuRBALH",
        "name": "patchyard",
    },
    "spend_enforcement": {
        "currency": "USD",
        "project_monthly_limit_cents": 5000,
        "whole_dollar_granularity": True,
        "control_plane_provenance": "attestation",
        "authorization_ruling": "A132",
    },
    "service_account": {
        "id": "user-6tzs2hdFVN7GoYQbWfC0eu7k",
        "name": "patchyard-worker",
        "api_key_count": 0,
    },
    "issuer": {
        "id": "idp_DlzD7RlQXgXxd1VSG2V93eEU",
        "name": "patchyard",
        "issuer_url": "https://factory.example.com/workload-identity",
        "audience": "https://api.openai.com",
        "uploaded_jwks": True,
        "oidc_discovery": False,
        "jwks_kid": "patchyard-39acdfd2bfc0acb0",
        "max_jwt_lifetime_seconds": 300,
    },
    "rule": {
        "name": "patchyard-control-plane-to-worker",
        "subject": "patchyard-control-plane",
        "audience": "https://api.openai.com",
        "claims": {"factory_environment": "production"},
        "service_account_id": "user-6tzs2hdFVN7GoYQbWfC0eu7k",
        "token_lifetime_seconds": 300,
    },
}
RESPONSE_PREDICATE = {
    "enforced": False,
    "basis": "no-observed-openai-token-exchange-response",
}
CONTROL_PLANE_PROVENANCE = {
    "management_surface": "console-only",
    "mutation_receipt_obtained": False,
    "attestation_required": True,
}


class OpenAIWifError(RuntimeError):
    """A local precondition or bounded capture operation failed."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        del request, file_pointer, code, message, headers, url
        return None


URL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def load_base_harness() -> types.ModuleType:
    source = BASE_HARNESS_PATH.read_bytes()
    if (
        BASE_HARNESS_PATH.is_symlink()
        or hashlib.sha256(source).hexdigest() != BASE_HARNESS_SHA256
    ):
        raise RuntimeError("qualified expiry harness differs from its exact binding")
    module = types.ModuleType("anthropic_wif_lifecycle_openai_base")
    module.__file__ = str(BASE_HARNESS_PATH)
    module.__package__ = None
    exec(
        compile(source, str(BASE_HARNESS_PATH), "exec", dont_inherit=True),
        module.__dict__,
    )
    return module


BASE = load_base_harness()
BASE.STAGING_ROOT = STAGING_ROOT
# A144: the OpenAI tools own their signing-key path, so no surface of the
# loaded base harness may still act on the Anthropic path.
BASE.ACTIVE_SIGNING_KEY = SIGNING_KEY


def credential_free_env() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_ADMIN_KEY",
        "PATCHYARD_OPENAI_ADMIN_KEY",
        "OPENAI_ORGANIZATION",
        "OPENAI_PROJECT",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_IDENTITY_TOKEN",
        "ANTHROPIC_IDENTITY_TOKEN_FILE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        environment.pop(name, None)
    return environment


BASE.credential_free_env = credential_free_env


def load_policy() -> dict[str, Any]:
    policy = BASE.load_json_file(POLICY_PATH)
    if policy != EXPECTED_POLICY:
        raise OpenAIWifError("OpenAI WIF policy differs from its exact binding")
    return policy


def registry_trusted_kid() -> str:
    """A145: the per-provider signing-identity registry is the steady-state
    kid authority. The frozen policy's issuer.jwks_kid is the historical
    issuance-era kid and is no longer read for minting."""
    registry = BASE.load_json_file(SIGNING_IDENTITIES_PATH)
    try:
        entry = registry["providers"]["openai"]
        key_path = entry["signing_key_path"]
        kid = entry["trusted_kid"]
    except (KeyError, TypeError) as error:
        raise OpenAIWifError(
            "signing-identity registry lacks the OpenAI entry"
        ) from error
    if key_path != str(SIGNING_KEY):
        raise OpenAIWifError(
            "signing-identity registry names another OpenAI key path"
        )
    if not isinstance(kid, str) or KID_PATTERN.fullmatch(kid) is None:
        raise OpenAIWifError("signing-identity registry kid is malformed")
    return kid


def source_binding() -> dict[str, str]:
    return {
        "policy_sha256": BASE.digest_file(POLICY_PATH),
        "base_harness_sha256": BASE.digest_file(BASE_HARNESS_PATH),
        "issuance_adapter_sha256": BASE.digest_file(Path(__file__).resolve()),
    }


def validate_run_id(run_id: str) -> None:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise OpenAIWifError("run ID is malformed")


def decode_jwt_part(value: str) -> Any:
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        return BASE.load_json_bytes(decoded)
    except (ValueError, json.JSONDecodeError) as error:
        raise OpenAIWifError("minted assertion is not decodable JSON") from error


def iso_epoch(value: int) -> str:
    return BASE.iso_seconds(datetime.fromtimestamp(value, timezone.utc))


def mint_openai_assertion(
    policy: dict[str, Any],
    signing_key: Path,
    run_id: str,
    now_epoch: int,
    expected_kid: str | None = None,
) -> tuple[str, dict[str, Any]]:
    if expected_kid is None:
        expected_kid = registry_trusted_kid()
    base_policy = {
        "issuer": {"issuer_url": policy["issuer"]["issuer_url"]},
        "rule": {
            "subject": policy["rule"]["subject"],
            "audience": policy["rule"]["audience"],
            "claims": policy["rule"]["claims"],
        },
    }
    assertion, signing_key_descriptor = BASE.mint_assertion(
        base_policy, signing_key, run_id, now_epoch
    )
    parts = assertion.split(".")
    if len(parts) != 3:
        raise OpenAIWifError("minted assertion is not a compact JWT")
    header = decode_jwt_part(parts[0])
    claims = decode_jwt_part(parts[1])
    expected_header = {
        "alg": "RS256",
        "kid": expected_kid,
        "typ": "JWT",
    }
    if header != expected_header:
        raise OpenAIWifError(
            "minted assertion header differs from the signing-identity registry"
        )
    if not isinstance(claims, dict) or set(claims) != {
        "iss",
        "sub",
        "aud",
        "iat",
        "exp",
        "jti",
        "factory_environment",
    }:
        raise OpenAIWifError("minted assertion claim shape differs")
    for field, expected in (
        ("iss", policy["issuer"]["issuer_url"]),
        ("sub", policy["rule"]["subject"]),
        ("aud", policy["rule"]["audience"]),
        ("factory_environment", policy["rule"]["claims"]["factory_environment"]),
    ):
        if claims.get(field) != expected:
            raise OpenAIWifError(f"minted assertion {field} differs from OpenAI policy")
    issued_at = claims.get("iat")
    expires_at = claims.get("exp")
    if any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in (issued_at, expires_at)
    ):
        raise OpenAIWifError("minted assertion times are not integers")
    assert isinstance(issued_at, int) and isinstance(expires_at, int)
    if expires_at - issued_at != policy["issuer"]["max_jwt_lifetime_seconds"]:
        raise OpenAIWifError("minted assertion lifetime differs from OpenAI policy")
    expected_jti = rf"factory-{re.escape(run_id)}-[0-9a-f]{{16}}"
    if re.fullmatch(expected_jti, str(claims.get("jti", ""))) is None:
        raise OpenAIWifError("minted assertion JTI is malformed")
    expected_key = {
        "kid": expected_kid,
        "jwk_thumbprint_sha256": signing_key_descriptor.get(
            "jwk_thumbprint_sha256"
        ),
    }
    if signing_key_descriptor != expected_key:
        raise OpenAIWifError("signing key differs from the uploaded OpenAI JWKS")
    return assertion, {
        "algorithm": "RS256",
        "kid": header["kid"],
        "issuer": claims["iss"],
        "subject": claims["sub"],
        "audience": claims["aud"],
        "issued_at": iso_epoch(issued_at),
        "minted_at": iso_epoch(now_epoch),
        "expires_at": iso_epoch(expires_at),
        "lifetime_seconds": expires_at - issued_at,
        "jti_supplied": True,
        "factory_environment": claims["factory_environment"],
        "jwk_thumbprint_sha256": signing_key_descriptor["jwk_thumbprint_sha256"],
    }


def exchange_request(policy: dict[str, Any], assertion: str) -> dict[str, Any]:
    return {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "subject_token": assertion,
        "identity_provider_id": policy["issuer"]["id"],
        "service_account_id": policy["service_account"]["id"],
    }


def json_value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unknown"


def credential_shaped_string(value: str) -> bool:
    return bool(
        JWT_PATTERN.search(value)
        or OPENAI_KEY_PATTERN.search(value)
        or PRIVATE_KEY_PATTERN.search(value)
    )


def field_descriptors(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    descriptors = []
    for name in sorted(value):
        recorded = (
            SAFE_FIELD_NAME.fullmatch(name) is not None
            and not credential_shaped_string(name)
        )
        descriptors.append(
            {
                "name": name if recorded else None,
                "name_recorded": recorded,
                "value_type": json_value_type(value[name]),
            }
        )
    return descriptors


def safe_response_string(value: Any) -> str | None:
    if not isinstance(value, str) or SAFE_RESPONSE_STRING.fullmatch(value) is None:
        return None
    if credential_shaped_string(value):
        return None
    return value


def response_error_type(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        return safe_response_string(error.get("type"))
    return safe_response_string(error)


def response_request_id(headers: Any) -> tuple[str | None, bool]:
    values = [
        headers.get(name)
        for name in ("x-request-id", "request-id", "openai-request-id")
        if headers.get(name) is not None
    ]
    if not values:
        return None, False
    unique = {str(value) for value in values}
    if len(unique) != 1:
        return None, True
    return safe_response_string(unique.pop()), True


def response_provider_date(headers: Any) -> str | None:
    value = headers.get("date")
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return BASE.iso_seconds(parsed)


def sanitize_response(
    status: int,
    headers: Any,
    raw: bytes,
    requested_at: str,
    observed_at: str,
) -> dict[str, Any]:
    if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        raise OpenAIWifError("provider HTTP status is outside the bounded contract")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise OpenAIWifError("provider response exceeds the byte limit")
    payload: Any = None
    try:
        payload = BASE.load_json_bytes(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        body_kind = "non_json"
    else:
        body_kind = f"json_{json_value_type(payload)}"
    error = payload.get("error") if isinstance(payload, dict) else None
    token_type = (
        safe_response_string(payload.get("token_type"))
        if isinstance(payload, dict)
        else None
    )
    expires_in_value = payload.get("expires_in") if isinstance(payload, dict) else None
    expires_in = (
        expires_in_value
        if isinstance(expires_in_value, int) and not isinstance(expires_in_value, bool)
        else None
    )
    request_id, request_id_supplied = response_request_id(headers)
    content_type = None
    if hasattr(headers, "get_content_type"):
        content_type = safe_response_string(headers.get_content_type())
    observation = {
        "source": "openai_http_response",
        "http_status": status,
        "request_started_at": requested_at,
        "observed_at": observed_at,
        "provider_date": response_provider_date(headers),
        "request_id": request_id,
        "request_id_supplied": request_id_supplied,
        "content_type": content_type,
        "body_bytes": len(raw),
        "body_format": body_kind,
        "response_shape": {
            "body_kind": body_kind,
            "top_level_fields": field_descriptors(payload),
            "error_fields": field_descriptors(error),
        },
        "access_token_supplied": (
            isinstance(payload, dict) and "access_token" in payload
        ),
        "token_type": token_type,
        "expires_in": expires_in,
        "error_type": response_error_type(payload),
    }
    raw = b""
    payload = None
    return observation


def request_token(body: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(body, separators=(",", ":")).encode()
    request = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=encoded,
        headers={
            "content-type": "application/json",
            "user-agent": "patchyard-openai-wif-issuance/1",
        },
        method="POST",
    )
    requested_at = BASE.iso_time(BASE.utc_now())
    try:
        response = URL_OPENER.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        observed_at = BASE.iso_time(BASE.utc_now())
        observation = sanitize_response(
            int(response.status),
            response.headers,
            raw,
            requested_at,
            observed_at,
        )
    encoded = b""
    raw = b""
    return observation


def exchange_observation(
    policy: dict[str, Any],
    signing_key: Path,
    run_id: str,
    started_at: str,
    request: Callable[[dict[str, Any]], dict[str, Any]] = request_token,
    expected_kid: str | None = None,
) -> dict[str, Any]:
    now_epoch = int(time.time())
    assertion, assertion_descriptor = mint_openai_assertion(
        policy, signing_key, run_id, now_epoch, expected_kid
    )
    body = exchange_request(policy, assertion)
    try:
        response = request(body)
    finally:
        assertion = ""
        body["subject_token"] = ""
        body.clear()
    credential_removed_at = BASE.iso_time(BASE.utc_now())
    if not isinstance(response, dict) or response.get("source") != "openai_http_response":
        raise OpenAIWifError("exchange requester returned no bounded HTTP observation")
    return {
        "schema_version": 1,
        "provider": "openai",
        "observation_kind": "first-token-exchange",
        "run_id": run_id,
        "started_at": started_at,
        "assertion_descriptor": assertion_descriptor,
        "exchange_request": {
            "endpoint": TOKEN_ENDPOINT,
            "content_type": "application/json",
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
            "subject_token_supplied": True,
            "identity_provider_id": policy["issuer"]["id"],
            "service_account_id": policy["service_account"]["id"],
            "scope_supplied": False,
            "requested_at": response.get("request_started_at"),
        },
        "exchange_response": response,
        "credential_removed_at": credential_removed_at,
        "response_predicate": RESPONSE_PREDICATE,
        "control_plane_provenance": CONTROL_PLANE_PROVENANCE,
        "provider_response_observed": True,
        "qualification_evidence": False,
        "source": source_binding(),
    }


def safe_failure_reason(error: BaseException) -> str:
    reason = re.sub(r"[^A-Za-z0-9 ._:/?=+,'()\[\]-]", "?", str(error))[:512]
    if (
        JWT_PATTERN.search(reason)
        or OPENAI_KEY_PATTERN.search(reason)
        or PRIVATE_KEY_PATTERN.search(reason)
    ):
        return "credential-bearing diagnostic suppressed"
    return reason or error.__class__.__name__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    exchange = subparsers.add_parser("exchange")
    exchange.add_argument("--run-id", required=True)
    exchange.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    if os.geteuid() != 0:
        raise OpenAIWifError("OpenAI WIF issuance adapter must run as root")
    os.umask(0o077)
    args = build_parser().parse_args()
    validate_run_id(args.run_id)
    stage = BASE.validate_stage_directory(args.run_id)
    BASE.require_stage_path(args.output, stage, "output")
    try:
        signing_key = SIGNING_KEY.resolve(strict=True)
    except OSError as error:
        raise OpenAIWifError(f"cannot resolve signing key: {error}") from error
    if signing_key != SIGNING_KEY:
        raise OpenAIWifError("signing key path differs from the active identity")
    started_at = BASE.iso_time(BASE.utc_now())
    output = BASE.ReservedOutput(
        args.output,
        {
            "schema_version": 1,
            "provider": "openai",
            "status": "in_progress",
            "action": "exchange",
            "run_id": args.run_id,
            "started_at": started_at,
            "source": source_binding(),
        },
    )
    phase = "local_preflight"
    try:
        policy = load_policy()
        BASE.validate_root_private_key(signing_key)
        phase = "token_exchange"
        result = exchange_observation(
            policy, signing_key, args.run_id, started_at
        )
        phase = "terminal_write"
        output.finish(result)
    except BaseException as error:
        output.finish(
            {
                "schema_version": 1,
                "provider": "openai",
                "status": "failed",
                "action": "exchange",
                "run_id": args.run_id,
                "started_at": started_at,
                "failed_at": BASE.iso_time(BASE.utc_now()),
                "failure_type": error.__class__.__name__,
                "failure_reason": safe_failure_reason(error),
                "failure_phase": phase,
                "provider_response_observed": False,
                "qualification_evidence": False,
                "source": source_binding(),
            }
        )
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OpenAIWifError,
        BASE.LifecycleError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        urllib.error.URLError,
        KeyboardInterrupt,
    ) as error:
        print(f"OpenAI WIF issuance: {safe_failure_reason(error)}", file=sys.stderr)
        raise SystemExit(1)
