#!/usr/bin/env python3
"""Record one attended OpenAI expired-assertion token exchange.

The frozen Anthropic lifecycle harness is loaded by exact digest and is never
imported or modified.  This sibling adapter reserves a root-only tmpfs output,
mints one assertion whose ``exp`` is already past, attempts exactly one OpenAI
exchange, and records only a bounded sanitized response.  It never writes the
assertion, response body, bearer, or signing key.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
import types
from typing import Any, Callable
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy/openai-wif.json"
POLICY_SHA256 = "14d2b8be570163f331de22adec382252f286a53b117f7311a0448479edff1ef2"
BASE_HARNESS_PATH = ROOT / "tools/anthropic-wif-lifecycle.py"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
SIGNING_KEY = Path("/etc/patchyard/anthropic-wif-signing.pem")
STAGING_ROOT = Path("/run/patchyard-openai")
TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
MAX_RESPONSE_BYTES = 1_000_000
RUN_ID_PATTERN = re.compile(r"openai-expiry-[0-9]{8}-[0-9a-f]{10}")
SAFE_RESPONSE_STRING = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/+;-]{0,127}")
SAFE_FIELD_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
JWT_PATTERN = re.compile(
    r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
)
OPENAI_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
RESPONSE_PREDICATE = {
    "enforced": False,
    "basis": "no-observed-openai-expired-assertion-response",
}
CONTROL_PLANE_PROVENANCE = {
    "control_plane_mutation_claimed": False,
    "mutation_receipt_obtained": False,
    "attestation_required": False,
}


class OpenAIExpiryError(RuntimeError):
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
        raise RuntimeError("qualified lifecycle harness differs from its exact binding")
    module = types.ModuleType("anthropic_wif_lifecycle_openai_expiry_base")
    module.__file__ = str(BASE_HARNESS_PATH)
    module.__package__ = None
    exec(
        compile(source, str(BASE_HARNESS_PATH), "exec", dont_inherit=True),
        module.__dict__,
    )
    return module


BASE = load_base_harness()
BASE.STAGING_ROOT = STAGING_ROOT


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
    if POLICY_PATH.is_symlink() or BASE.digest_file(POLICY_PATH) != POLICY_SHA256:
        raise OpenAIExpiryError("OpenAI WIF policy differs from its frozen binding")
    policy = BASE.load_json_file(POLICY_PATH)
    expected = {
        "provider": "openai",
        "issuer_url": "https://factory.example.com/workload-identity",
        "audience": "https://api.openai.com",
        "identity_provider_id": "idp_DlzD7RlQXgXxd1VSG2V93eEU",
        "service_account_id": "user-ibYSGwJI5TPOPeJ3ioADcfDH",
        "subject": "patchyard-control-plane",
        "maximum_lifetime": 300,
    }
    observed = {
        "provider": policy.get("provider"),
        "issuer_url": policy.get("issuer", {}).get("issuer_url"),
        "audience": policy.get("rule", {}).get("audience"),
        "identity_provider_id": policy.get("issuer", {}).get("id"),
        "service_account_id": policy.get("service_account", {}).get("id"),
        "subject": policy.get("rule", {}).get("subject"),
        "maximum_lifetime": policy.get("issuer", {}).get(
            "max_jwt_lifetime_seconds"
        ),
    }
    if observed != expected:
        raise OpenAIExpiryError("OpenAI WIF policy fields differ from the contract")
    return policy


def source_binding() -> dict[str, str]:
    return {
        "policy_sha256": BASE.digest_file(POLICY_PATH),
        "base_harness_sha256": BASE.digest_file(BASE_HARNESS_PATH),
        "expiry_adapter_sha256": BASE.digest_file(Path(__file__).resolve()),
    }


def validate_run_id(run_id: str) -> None:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise OpenAIExpiryError("run ID is malformed")


def iso_epoch(value: int) -> str:
    return BASE.iso_seconds(datetime.fromtimestamp(value, timezone.utc))


def mint_expired_assertion(
    policy: dict[str, Any], signing_key: Path, run_id: str, now_epoch: int
) -> tuple[str, dict[str, Any]]:
    """Mint a 300-second assertion that expired five seconds before minting."""

    jwk = BASE.load_public_jwk(signing_key)
    key_descriptor = BASE.jwk_descriptor(jwk)
    issued_at = now_epoch - 305
    expires_at = now_epoch - 5
    header = BASE.b64url(
        json.dumps(
            {"alg": "RS256", "kid": jwk["kid"], "typ": "JWT"},
            separators=(",", ":"),
        ).encode()
    )
    payload = BASE.b64url(
        json.dumps(
            {
                "iss": policy["issuer"]["issuer_url"],
                "sub": policy["rule"]["subject"],
                "aud": policy["rule"]["audience"],
                "iat": issued_at,
                "exp": expires_at,
                "jti": f"factory-{run_id}-{secrets.token_hex(8)}",
                "factory_environment": policy["rule"]["claims"][
                    "factory_environment"
                ],
            },
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}"
    signature = subprocess.run(
        ["/usr/bin/openssl", "dgst", "-sha256", "-sign", str(signing_key)],
        input=signing_input.encode(),
        check=True,
        capture_output=True,
        env=credential_free_env(),
    ).stdout
    assertion = f"{signing_input}.{BASE.b64url(signature)}"
    return assertion, {
        "algorithm": "RS256",
        "kid_derived_from_public_der": True,
        "issuer": policy["issuer"]["issuer_url"],
        "subject": policy["rule"]["subject"],
        "audience": policy["rule"]["audience"],
        "issued_at": iso_epoch(issued_at),
        "minted_at": iso_epoch(now_epoch),
        "expires_at": iso_epoch(expires_at),
        "lifetime_seconds": expires_at - issued_at,
        "expired_before_mint_seconds": now_epoch - expires_at,
        "jti_supplied": True,
        "factory_environment": policy["rule"]["claims"]["factory_environment"],
        "jwk_thumbprint_sha256": key_descriptor["jwk_thumbprint_sha256"],
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
        raise OpenAIExpiryError("provider HTTP status is outside the bounded contract")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise OpenAIExpiryError("provider response exceeds the byte limit")
    payload: Any = None
    try:
        payload = BASE.load_json_bytes(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        body_kind = "non_json"
    else:
        body_kind = f"json_{json_value_type(payload)}"
    error = payload.get("error") if isinstance(payload, dict) else None
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
        "access_token_supplied": isinstance(payload, dict) and "access_token" in payload,
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
            "user-agent": "patchyard-openai-wif-expiry/1",
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
            int(response.status), response.headers, raw, requested_at, observed_at
        )
    encoded = b""
    raw = b""
    return observation


def expiry_observation(
    policy: dict[str, Any],
    signing_key: Path,
    run_id: str,
    started_at: str,
    request: Callable[[dict[str, Any]], dict[str, Any]] = request_token,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    now_epoch = int(clock())
    assertion, descriptor = mint_expired_assertion(
        policy, signing_key, run_id, now_epoch
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
        raise OpenAIExpiryError("exchange requester returned no bounded HTTP observation")
    return {
        "schema_version": 1,
        "provider": "openai",
        "qualification_requirement": "credential-expiry-denial",
        "authorization_ruling": "A131",
        "observation_kind": "expired-assertion-token-exchange",
        "run_id": run_id,
        "started_at": started_at,
        "assertion_descriptor": descriptor,
        "exchange_request": {
            "endpoint": TOKEN_ENDPOINT,
            "content_type": "application/json",
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
            "subject_token_supplied": True,
            "identity_provider_id": policy["issuer"]["id"],
            "service_account_id": policy["service_account"]["id"],
            "scope_supplied": False,
            "attempt_count": 1,
            "requested_at": response.get("request_started_at"),
        },
        "expiry_denial": response,
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
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    if os.geteuid() != 0:
        raise OpenAIExpiryError("OpenAI expiry adapter must run as root")
    os.umask(0o077)
    args = build_parser().parse_args()
    validate_run_id(args.run_id)
    stage = BASE.validate_stage_directory(args.run_id)
    BASE.require_stage_path(args.output, stage, "output")
    try:
        signing_key = SIGNING_KEY.resolve(strict=True)
    except OSError as error:
        raise OpenAIExpiryError(f"cannot resolve signing key: {error}") from error
    if signing_key != SIGNING_KEY:
        raise OpenAIExpiryError("signing key path differs from the active identity")
    started_at = BASE.iso_time(BASE.utc_now())
    output = BASE.ReservedOutput(
        args.output,
        {
            "schema_version": 1,
            "provider": "openai",
            "status": "in_progress",
            "action": "expiry-denial",
            "run_id": args.run_id,
            "started_at": started_at,
            "source": source_binding(),
        },
    )
    phase = "local_preflight"
    try:
        policy = load_policy()
        BASE.validate_root_private_key(signing_key)
        phase = "expired_assertion_exchange"
        result = expiry_observation(policy, signing_key, args.run_id, started_at)
        phase = "terminal_write"
        output.finish(result)
    except BaseException as error:
        output.finish(
            {
                "schema_version": 1,
                "provider": "openai",
                "status": "failed",
                "action": "expiry-denial",
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
        OpenAIExpiryError,
        BASE.LifecycleError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        urllib.error.URLError,
        KeyboardInterrupt,
    ) as error:
        print(f"OpenAI WIF expiry: {safe_failure_reason(error)}", file=sys.stderr)
        raise SystemExit(1)
