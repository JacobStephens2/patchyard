#!/usr/bin/env python3
"""Run root-only Anthropic WIF expiry and lifecycle proof actions.

This is deliberately independent of the issuance runner, Firecracker launcher,
one-shot transport, and guest image.  It never emits an assertion or bearer.
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
import secrets
import stat
import subprocess
import sys
import time
from typing import Any, Callable, Optional
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy" / "anthropic-wif.json"
ACTIVE_SIGNING_KEY = Path("/etc/patchyard/anthropic-wif-signing.pem")
STAGING_ROOT = Path("/run/patchyard-anthropic")
BASE_URL = "https://api.anthropic.com"
MAX_RESPONSE_BYTES = 1_000_000
RUN_ID_PATTERN = re.compile(r"anthropic-l3-[0-9]{8}-[0-9a-f]{10}")
REQUEST_ID_PATTERN = re.compile(r"req_[A-Za-z0-9]+")
KID_PATTERN = re.compile(r"patchyard-[0-9a-f]{16}")
POSITIVE_EVENT_TYPES = {
    "rule_enabled_positive",
    "rule_restored_positive",
    "replacement_key_positive",
    "replacement_key_final_positive",
}
DENIAL_EVENT_TYPES = {
    "rule_disabled_exchange_denial",
    "retired_key_exchange_denial",
}


class LifecycleError(RuntimeError):
    """A fail-closed lifecycle precondition or provider observation failed."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        del request, file_pointer, code, message, headers, url
        return None


URL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
Progress = Callable[[str, Optional[dict[str, Any]]], None]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def iso_seconds(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def reject_json_constant(value: str) -> None:
    raise LifecycleError(f"JSON contains forbidden numeric constant: {value}")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LifecycleError(f"JSON contains duplicate key: {key}")
        result[key] = value
    return result


def load_json_bytes(value: bytes) -> Any:
    return json.loads(
        value,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_json_constant,
    )


def load_json_file(path: Path) -> Any:
    return load_json_bytes(path.read_bytes())


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise LifecycleError(
            f"{label} differs: expected {expected!r}, observed {actual!r}"
        )


def load_policy() -> dict[str, Any]:
    document = load_json_file(POLICY_PATH)
    required = {
        "schema_version": 1,
        "provider": "anthropic",
    }
    for field, expected in required.items():
        require_equal(document.get(field), expected, f"policy {field}")
    require_equal(
        document.get("organization", {}).get("id"),
        "aaadc747-869a-42d2-af51-58a5be8e3b7f",
        "organization ID",
    )
    require_equal(
        document.get("workspace", {}).get("id"),
        "wrkspc_000000000000000000000000",
        "workspace ID",
    )
    require_equal(
        document.get("service_account", {}).get("id"),
        "svac_01BqCdjSqFsWTvfDyCucThZy",
        "service-account ID",
    )
    require_equal(
        document.get("issuer", {}).get("id"),
        "fdis_01A8wjwFPKfutAGtFN3oqF8J",
        "issuer ID",
    )
    require_equal(
        document.get("issuer", {}).get("issuer_url"),
        "https://factory.example.com/workload-identity",
        "issuer URL",
    )
    require_equal(document.get("issuer", {}).get("check_jti"), True, "issuer JTI")
    require_equal(
        document.get("issuer", {}).get("max_jwt_lifetime_seconds"),
        300,
        "issuer assertion lifetime",
    )
    require_equal(
        document.get("rule", {}).get("id"),
        "fdrl_000000000000000000000000",
        "rule ID",
    )
    require_equal(
        document.get("rule", {}).get("subject"),
        "patchyard-control-plane",
        "rule subject",
    )
    require_equal(
        document.get("rule", {}).get("audience"),
        BASE_URL,
        "rule audience",
    )
    require_equal(
        document.get("rule", {}).get("claims"),
        {"factory_environment": "production"},
        "rule claims",
    )
    require_equal(
        document.get("rule", {}).get("oauth_scope"),
        "workspace:inference",
        "rule scope",
    )
    require_equal(
        document.get("rule", {}).get("token_lifetime_seconds"),
        300,
        "rule bearer lifetime",
    )
    return document


def validate_run_id(run_id: str) -> None:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise LifecycleError("run ID is malformed")


def stage_directory(run_id: str) -> Path:
    return STAGING_ROOT / run_id


def validate_stage_directory(run_id: str) -> Path:
    stage = stage_directory(run_id)
    try:
        if stage.resolve(strict=True) != stage:
            raise LifecycleError("lifecycle stage path is not canonical")
        metadata = stage.stat()
        run_metadata = Path("/run").stat()
    except OSError as error:
        raise LifecycleError(f"cannot resolve lifecycle stage: {error}") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise LifecycleError("lifecycle stage is not a directory")
    if metadata.st_uid != 0 or metadata.st_gid != 0:
        raise LifecycleError("lifecycle stage is not owned by root:root")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise LifecycleError("lifecycle stage mode is not 0700")
    if metadata.st_dev != run_metadata.st_dev:
        raise LifecycleError("lifecycle stage is not on the /run filesystem")
    filesystem = subprocess.run(
        ["/usr/bin/stat", "-f", "-c", "%T", "/run"],
        check=True,
        capture_output=True,
        text=True,
        env=credential_free_env(),
    ).stdout.strip()
    if filesystem != "tmpfs":
        raise LifecycleError("/run is not a tmpfs filesystem")
    return stage


def require_stage_path(path: Path, stage: Path, label: str) -> None:
    if not path.is_absolute() or path.parent != stage:
        raise LifecycleError(f"{label} is outside the exact lifecycle stage")


def validate_root_private_key(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise LifecycleError("signing key must be an absolute non-symlink path")
    try:
        if path.resolve(strict=True) != path:
            raise LifecycleError("signing key path is not canonical")
    except OSError as error:
        raise LifecycleError(f"cannot resolve signing key: {error}") from error
    try:
        metadata = path.stat()
    except OSError as error:
        raise LifecycleError(f"cannot stat signing key: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise LifecycleError("signing key is not a regular file")
    if metadata.st_uid != 0 or metadata.st_gid != 0:
        raise LifecycleError("signing key is not owned by root:root")
    if stat.S_IMODE(metadata.st_mode) != 0o400:
        raise LifecycleError("signing key mode is not 0400")
    if not 1 <= metadata.st_size <= 32_768:
        raise LifecycleError("signing key size is outside the bounded contract")


def load_public_jwk(path: Path) -> dict[str, str]:
    modulus_record = subprocess.run(
        ["/usr/bin/openssl", "rsa", "-in", str(path), "-noout", "-modulus"],
        check=True,
        capture_output=True,
        text=True,
        env=credential_free_env(),
    ).stdout.strip()
    if re.fullmatch(r"Modulus=[0-9A-F]{768}", modulus_record) is None:
        raise LifecycleError("signing key is not an exact 3072-bit RSA key")
    modulus = bytes.fromhex(modulus_record.removeprefix("Modulus="))
    public_der = subprocess.run(
        ["/usr/bin/openssl", "pkey", "-in", str(path), "-pubout", "-outform", "DER"],
        check=True,
        capture_output=True,
        env=credential_free_env(),
    ).stdout
    kid = f"patchyard-{digest_bytes(public_der)[:16]}"
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": b64url(modulus),
        "e": "AQAB",
    }


def jwk_descriptor(jwk: dict[str, Any]) -> dict[str, str]:
    require_equal(sorted(jwk), ["alg", "e", "kid", "kty", "n", "use"], "JWK fields")
    require_equal(jwk["alg"], "RS256", "JWK algorithm")
    require_equal(jwk["kty"], "RSA", "JWK type")
    require_equal(jwk["use"], "sig", "JWK use")
    require_equal(jwk["e"], "AQAB", "JWK exponent")
    if KID_PATTERN.fullmatch(str(jwk["kid"])) is None:
        raise LifecycleError("JWK key ID is malformed")
    for field in ("e", "n"):
        if not isinstance(jwk[field], str) or not jwk[field]:
            raise LifecycleError(f"JWK {field} is empty")
    if re.fullmatch(r"[A-Za-z0-9_-]+", jwk["n"]) is None:
        raise LifecycleError("JWK modulus is not unpadded base64url")
    try:
        modulus = base64.urlsafe_b64decode(jwk["n"] + "=" * (-len(jwk["n"]) % 4))
    except ValueError as error:
        raise LifecycleError("JWK modulus is not valid base64url") from error
    if len(modulus) != 384 or modulus[0] == 0:
        raise LifecycleError("JWK modulus is not an exact 3072-bit value")
    thumbprint_input = json.dumps(
        {"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return {
        "kid": jwk["kid"],
        "jwk_thumbprint_sha256": digest_bytes(thumbprint_input),
    }


def load_jwks(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or path.is_symlink():
        raise LifecycleError("JWKS must be an absolute non-symlink path")
    try:
        if path.resolve(strict=True) != path:
            raise LifecycleError("JWKS path is not canonical")
    except OSError as error:
        raise LifecycleError(f"cannot resolve JWKS: {error}") from error
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= 65_536:
        raise LifecycleError("JWKS is not a bounded regular file")
    document = load_json_file(path)
    require_equal(sorted(document), ["keys"], "JWKS fields")
    keys = document["keys"]
    if not isinstance(keys, list) or len(keys) != 1:
        raise LifecycleError("JWKS must contain exactly one key")
    jwk_descriptor(keys[0])
    return document


def credential_free_env() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_IDENTITY_TOKEN",
        "ANTHROPIC_IDENTITY_TOKEN_FILE",
    ):
        environment.pop(name, None)
    return environment


def mint_assertion(
    policy: dict[str, Any], signing_key: Path, run_id: str, now_epoch: int
) -> tuple[str, dict[str, str]]:
    jwk = load_public_jwk(signing_key)
    issued_at = now_epoch - 5
    expires_at = now_epoch + 295
    header = b64url(
        json.dumps(
            {"alg": "RS256", "kid": jwk["kid"], "typ": "JWT"},
            separators=(",", ":"),
        ).encode()
    )
    payload = b64url(
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
    return f"{signing_input}.{b64url(signature)}", jwk_descriptor(jwk)


def parse_http_date(value: str | None) -> str:
    if value is None:
        raise LifecycleError("provider response has no Date header")
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError) as error:
        raise LifecycleError("provider Date header is malformed") from error
    if parsed.tzinfo is None:
        raise LifecycleError("provider Date header has no timezone")
    return iso_seconds(parsed)


def response_request_id(headers: Any, payload: dict[str, Any]) -> str:
    request_id = headers.get("request-id")
    if REQUEST_ID_PATTERN.fullmatch(str(request_id or "")) is None:
        raise LifecycleError("provider request ID is absent or malformed")
    payload_request_id = payload.get("request_id")
    if payload_request_id is not None and payload_request_id != request_id:
        raise LifecycleError("provider header and body request IDs differ")
    return str(request_id)


def request_json(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    bearer: str | None = None,
) -> dict[str, Any]:
    if (method, path) not in {
        ("POST", "/v1/oauth/token"),
        ("GET", "/v1/models?limit=1"),
    }:
        raise LifecycleError("provider request is outside the lifecycle allowlist")
    encoded = None
    headers = {
        "anthropic-version": "2023-06-01",
        "user-agent": "patchyard-anthropic-wif-lifecycle/1",
    }
    if body is not None:
        encoded = json.dumps(body, separators=(",", ":")).encode()
        headers["content-type"] = "application/json"
    if bearer is not None:
        headers["authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(
        BASE_URL + path,
        data=encoded,
        headers=headers,
        method=method,
    )
    try:
        response = URL_OPENER.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise LifecycleError("provider response exceeds the byte limit")
        try:
            payload = load_json_bytes(raw)
        except json.JSONDecodeError as error:
            raise LifecycleError("provider response is not JSON") from error
        if not isinstance(payload, dict):
            raise LifecycleError("provider response is not a JSON object")
        return {
            "status": int(response.status),
            "headers": response.headers,
            "payload": payload,
            "observed_at": iso_time(utc_now()),
        }


def response_observation(
    response: dict[str, Any], endpoint: str
) -> dict[str, Any]:
    payload = response["payload"]
    request_id = response["headers"].get("request-id")
    provider_date = response["headers"].get("date")
    parsed_provider_date = None
    if provider_date is not None:
        try:
            parsed_provider_date = parse_http_date(provider_date)
        except LifecycleError:
            pass
    return {
        "endpoint": endpoint,
        "http_status": response["status"],
        "request_id": (
            request_id
            if REQUEST_ID_PATTERN.fullmatch(str(request_id or "")) is not None
            else None
        ),
        "provider_date": parsed_provider_date,
        "observed_at": response["observed_at"],
        "error_type": provider_error_type(payload),
        "response_shape": response_shape(payload),
    }


def response_shape(payload: dict[str, Any]) -> dict[str, Any]:
    error = payload.get("error")
    return {
        "top_level_keys": sorted(payload),
        "error_value_type": "object" if isinstance(error, dict) else type(error).__name__,
        "error_object_keys": sorted(error) if isinstance(error, dict) else [],
    }


def provider_error_type(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict) and isinstance(error.get("type"), str):
        return error["type"]
    return None


def source_binding() -> dict[str, str]:
    return {
        "policy_sha256": digest_file(POLICY_PATH),
        "lifecycle_harness_sha256": digest_file(Path(__file__).resolve()),
    }


def exchange_request(policy: dict[str, Any], assertion: str) -> dict[str, Any]:
    return {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
        "federation_rule_id": policy["rule"]["id"],
        "organization_id": policy["organization"]["id"],
        "service_account_id": policy["service_account"]["id"],
        "workspace_id": policy["workspace"]["id"],
    }


def accepted_exchange(
    policy: dict[str, Any],
    signing_key: Path,
    run_id: str,
    request: Callable[..., dict[str, Any]] = request_json,
    progress: Progress | None = None,
) -> tuple[dict[str, Any], str]:
    assertion, key = mint_assertion(policy, signing_key, run_id, int(time.time()))
    if progress is not None:
        progress("exchange_requested", None)
    response = request(
        "POST", "/v1/oauth/token", body=exchange_request(policy, assertion)
    )
    assertion = ""
    if response["status"] != 200:
        if progress is not None:
            progress(
                "exchange_rejected",
                response_observation(response, "/v1/oauth/token"),
            )
        raise LifecycleError("positive token exchange was denied by the provider")
    payload = response["payload"]
    require_equal(sorted(payload), ["access_token", "expires_in", "scope", "token_type"], "exchange response fields")
    token = payload["access_token"]
    if not isinstance(token, str) or not token.startswith("sk-ant-oat01-"):
        raise LifecycleError("exchange did not return the bounded WIF bearer type")
    if len(token) > 8192:
        raise LifecycleError("exchange bearer exceeds the byte limit")
    expires_in = payload["expires_in"]
    if not isinstance(expires_in, int) or isinstance(expires_in, bool):
        raise LifecycleError("exchange lifetime is not an integer")
    if not 60 <= expires_in <= 300:
        raise LifecycleError("exchange lifetime is outside one to five minutes")
    require_equal(payload["token_type"], "Bearer", "exchange token type")
    require_equal(payload["scope"], "workspace:inference", "exchange scope")
    provider_date = parse_http_date(response["headers"].get("date"))
    issued = datetime.fromisoformat(provider_date.replace("Z", "+00:00"))
    exchange = {
        "endpoint": "/v1/oauth/token",
        "http_status": 200,
        "request_id": response_request_id(response["headers"], payload),
        "provider_date": provider_date,
        "observed_at": response["observed_at"],
        "issued_at": provider_date,
        "expires_at": iso_seconds(
            datetime.fromtimestamp(issued.timestamp() + expires_in, timezone.utc)
        ),
        "expires_in": expires_in,
        "token_type": "Bearer",
        "scope": "workspace:inference",
        "service_account_id": policy["service_account"]["id"],
        "rule_id": policy["rule"]["id"],
        "workspace_id": policy["workspace"]["id"],
    }
    if progress is not None:
        progress(
            "exchange_accepted",
            {"issuance": exchange, "signing_key": key},
        )
    return {"exchange": exchange, "key": key}, token


def accepted_models(
    token: str,
    request: Callable[..., dict[str, Any]] = request_json,
    progress: Progress | None = None,
) -> dict[str, Any]:
    if progress is not None:
        progress("models_requested", None)
    response = request("GET", "/v1/models?limit=1", bearer=token)
    if response["status"] != 200:
        if progress is not None:
            progress(
                "models_rejected",
                response_observation(response, "/v1/models?limit=1"),
            )
        raise LifecycleError("positive Models control was denied by the provider")
    payload = response["payload"]
    models = payload.get("data")
    if not isinstance(models, list) or len(models) != 1:
        raise LifecycleError("Models control did not return exactly one model")
    model_id = models[0].get("id") if isinstance(models[0], dict) else None
    if not isinstance(model_id, str) or not model_id:
        raise LifecycleError("Models control did not identify a model")
    result = {
        "endpoint": "/v1/models?limit=1",
        "http_status": 200,
        "request_id": response_request_id(response["headers"], payload),
        "provider_date": parse_http_date(response["headers"].get("date")),
        "observed_at": response["observed_at"],
        "model_id": model_id,
    }
    if progress is not None:
        progress("models_accepted", {"models": result})
    return result


def positive_event(
    event_type: str,
    key_role: str,
    policy: dict[str, Any],
    signing_key: Path,
    run_id: str,
    request: Callable[..., dict[str, Any]] = request_json,
    progress: Progress | None = None,
) -> dict[str, Any]:
    if event_type not in POSITIVE_EVENT_TYPES:
        raise LifecycleError("positive event type is not allowlisted")
    exchange, token = accepted_exchange(
        policy, signing_key, run_id, request, progress
    )
    try:
        models = accepted_models(token, request, progress)
    finally:
        token = ""
    return {
        "schema_version": 1,
        "provider": "anthropic",
        "run_id": run_id,
        "event_type": event_type,
        "observed_at": models["observed_at"],
        "key_role": key_role,
        "signing_key": exchange["key"],
        "exchange": exchange["exchange"],
        "models": models,
        "credential_removed_at": iso_time(utc_now()),
        "source": source_binding(),
    }


def denied_exchange_event(
    event_type: str,
    key_role: str,
    policy: dict[str, Any],
    signing_key: Path,
    run_id: str,
    request: Callable[..., dict[str, Any]] = request_json,
    progress: Progress | None = None,
) -> dict[str, Any]:
    if event_type not in DENIAL_EVENT_TYPES:
        raise LifecycleError("denial event type is not allowlisted")
    assertion, key = mint_assertion(policy, signing_key, run_id, int(time.time()))
    if progress is not None:
        progress("denied_exchange_requested", None)
    response = request(
        "POST", "/v1/oauth/token", body=exchange_request(policy, assertion)
    )
    assertion = ""
    payload = response["payload"]
    if response["status"] != 400 or provider_error_type(payload) != "invalid_grant":
        if progress is not None:
            progress(
                "denied_exchange_unexpected_response",
                response_observation(response, "/v1/oauth/token"),
            )
        raise LifecycleError("provider did not return the exact invalid-grant denial")
    denial = {
        "source": "anthropic_http_response",
        "endpoint": "/v1/oauth/token",
        "http_status": 400,
        "request_id": response_request_id(response["headers"], payload),
        "provider_date": parse_http_date(response["headers"].get("date")),
        "observed_at": response["observed_at"],
        "error_type": "invalid_grant",
        "response_shape": response_shape(payload),
    }
    if progress is not None:
        progress("denied_exchange_accepted", {"exchange_denial": denial})
    return {
        "schema_version": 1,
        "provider": "anthropic",
        "run_id": run_id,
        "event_type": event_type,
        "observed_at": denial["observed_at"],
        "key_role": key_role,
        "signing_key": key,
        "exchange_denial": denial,
        "credential_removed_at": iso_time(utc_now()),
        "source": source_binding(),
    }


def expiry_evidence(
    policy: dict[str, Any],
    signing_key: Path,
    run_id: str,
    request: Callable[..., dict[str, Any]] = request_json,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
    progress: Progress | None = None,
) -> dict[str, Any]:
    exchange, token = accepted_exchange(
        policy, signing_key, run_id, request, progress
    )
    try:
        positive = accepted_models(token, request, progress)
        expires = datetime.fromisoformat(
            exchange["exchange"]["expires_at"].replace("Z", "+00:00")
        )
        wait_seconds = max(0.0, expires.timestamp() - clock() + 1.0)
        if progress is not None:
            progress(
                "waiting_for_expiry",
                {"recorded_expires_at": exchange["exchange"]["expires_at"]},
            )
        sleeper(wait_seconds)
        if progress is not None:
            progress("expiry_denial_requested", None)
        response = request("GET", "/v1/models?limit=1", bearer=token)
    finally:
        token = ""
    payload = response["payload"]
    if response["status"] != 401 or provider_error_type(payload) != "authentication_error":
        if progress is not None:
            progress(
                "expiry_denial_unexpected_response",
                response_observation(response, "/v1/models?limit=1"),
            )
        raise LifecycleError("provider did not deny the expired bearer exactly once")
    denial = {
        "source": "anthropic_http_response",
        "endpoint": "/v1/models?limit=1",
        "http_status": 401,
        "request_id": response_request_id(response["headers"], payload),
        "provider_date": parse_http_date(response["headers"].get("date")),
        "observed_at": response["observed_at"],
        "error_type": "authentication_error",
        "response_shape": response_shape(payload),
    }
    if progress is not None:
        progress("expiry_denial_accepted", {"expiry_denial": denial})
    return {
        "schema_version": 1,
        "provider": "anthropic",
        "qualification_requirement": "credential-expiry-denial",
        "authorization_ruling": "A113",
        "run_id": run_id,
        "signing_key": exchange["key"],
        "issuance": exchange["exchange"],
        "positive_control": positive,
        "expiry_denial": denial,
        "credential_removed_at": iso_time(utc_now()),
        **source_binding(),
    }


def activate_replacement(
    policy: dict[str, Any],
    replacement_key: Path,
    expected_retired_jwks: Path,
    retired_key_output: Path,
    run_id: str,
    event_type: str = "replacement_key_activated",
    progress: Progress | None = None,
) -> dict[str, Any]:
    del policy
    retired = load_jwks(expected_retired_jwks)["keys"][0]
    active = load_public_jwk(ACTIVE_SIGNING_KEY)
    replacement = load_public_jwk(replacement_key)
    require_equal(jwk_descriptor(active), jwk_descriptor(retired), "active retired key")
    if jwk_descriptor(active) == jwk_descriptor(replacement):
        raise LifecycleError("replacement key is not distinct from the retired key")
    replacement_bytes = replacement_key.read_bytes()
    retired_bytes = ACTIVE_SIGNING_KEY.read_bytes()
    retired_descriptor = os.open(
        retired_key_output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o400,
    )
    try:
        write_all(retired_descriptor, retired_bytes)
        os.fsync(retired_descriptor)
        os.fchmod(retired_descriptor, 0o400)
        os.fchown(retired_descriptor, 0, 0)
    finally:
        os.close(retired_descriptor)
    validate_root_private_key(retired_key_output)
    require_equal(
        jwk_descriptor(load_public_jwk(retired_key_output)),
        jwk_descriptor(retired),
        "staged retired key",
    )
    if progress is not None:
        progress(
            "retired_key_preserved",
            {"retired_key": jwk_descriptor(retired)},
        )
    temporary = ACTIVE_SIGNING_KEY.with_name(
        f".{ACTIVE_SIGNING_KEY.name}.rotation-{secrets.token_hex(8)}"
    )
    descriptor = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o400,
        )
        write_all(descriptor, replacement_bytes)
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
        os.fchown(descriptor, 0, 0)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, ACTIVE_SIGNING_KEY)
        directory = os.open(ACTIVE_SIGNING_KEY.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()
    validate_root_private_key(ACTIVE_SIGNING_KEY)
    require_equal(
        jwk_descriptor(load_public_jwk(ACTIVE_SIGNING_KEY)),
        jwk_descriptor(replacement),
        "activated replacement key",
    )
    if progress is not None:
        progress(
            "replacement_key_installed",
            {"replacement_key": jwk_descriptor(replacement)},
        )
    observed_at = iso_time(utc_now())
    return {
        "schema_version": 1,
        "provider": "anthropic",
        "run_id": run_id,
        "event_type": event_type,
        "observed_at": observed_at,
        "activation": {
            "source": "local_atomic_key_activation",
            "active_key_path": str(ACTIVE_SIGNING_KEY),
            "retired_key": jwk_descriptor(retired),
            "replacement_key": jwk_descriptor(replacement),
            "retired_key_staged": True,
            "observed_at": observed_at,
        },
        "source": source_binding(),
    }


def encoded_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        written = os.write(descriptor, value[offset:])
        if written <= 0:
            raise LifecycleError("short write while preserving lifecycle evidence")
        offset += written


def validate_new_output_path(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink() or path.exists():
        raise LifecycleError("output must be an absolute new non-symlink path")
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise LifecycleError("output parent must be an existing non-symlink directory")
    try:
        if path.parent.resolve(strict=True) != path.parent:
            raise LifecycleError("output parent path is not canonical")
    except OSError as error:
        raise LifecycleError(f"cannot resolve output parent: {error}") from error


class ReservedOutput:
    """Leave a valid started record if a later terminal write cannot land."""

    def __init__(self, path: Path, started: dict[str, Any]) -> None:
        validate_new_output_path(path)
        self.path = path
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        try:
            write_all(descriptor, encoded_json(started))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def finish(self, value: dict[str, Any]) -> None:
        temporary = self.path.with_name(
            f".{self.path.name}.terminal-{secrets.token_hex(8)}"
        )
        descriptor = None
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            write_all(descriptor, encoded_json(value))
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o600)
            os.close(descriptor)
            descriptor = None
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary.exists():
                temporary.unlink()


def safe_failure_reason(error: BaseException) -> str:
    reason = re.sub(r"[^A-Za-z0-9 ._:/?=+,'()\[\]-]", "?", str(error))[:512]
    if re.search(r"sk-ant-|eyJ[A-Za-z0-9_-]+\.eyJ", reason):
        return "credential-bearing diagnostic suppressed"
    return reason or error.__class__.__name__


def failure_state(args: argparse.Namespace) -> dict[str, Any]:
    state: dict[str, Any] = {"credential_process_exiting": True}
    if args.action in {"activate-replacement", "rollback-activation"}:
        try:
            state["active_signing_key"] = jwk_descriptor(
                load_public_jwk(ACTIVE_SIGNING_KEY)
            )
        except (LifecycleError, OSError, subprocess.CalledProcessError) as error:
            state["active_signing_key_readback_error"] = safe_failure_reason(error)
        state["retired_key_output_exists"] = args.retired_key_output.exists()
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)

    jwks = subparsers.add_parser("jwks")
    jwks.add_argument("--run-id", required=True)
    jwks.add_argument("--signing-key", required=True, type=Path)
    jwks.add_argument("--output", required=True, type=Path)

    expiry = subparsers.add_parser("expiry")
    expiry.add_argument("--run-id", required=True)
    expiry.add_argument("--signing-key", type=Path, default=ACTIVE_SIGNING_KEY)
    expiry.add_argument("--output", required=True, type=Path)

    positive = subparsers.add_parser("exchange-positive")
    positive.add_argument("--run-id", required=True)
    positive.add_argument("--event-type", required=True, choices=sorted(POSITIVE_EVENT_TYPES))
    positive.add_argument(
        "--key-role",
        required=True,
        choices=["active", "replacement_staging"],
    )
    positive.add_argument("--signing-key", type=Path, default=ACTIVE_SIGNING_KEY)
    positive.add_argument("--output", required=True, type=Path)

    denied = subparsers.add_parser("exchange-denial")
    denied.add_argument("--run-id", required=True)
    denied.add_argument("--event-type", required=True, choices=sorted(DENIAL_EVENT_TYPES))
    denied.add_argument("--key-role", required=True, choices=["active", "retired_staging"])
    denied.add_argument("--signing-key", type=Path, default=ACTIVE_SIGNING_KEY)
    denied.add_argument("--output", required=True, type=Path)

    for action in ("activate-replacement", "rollback-activation"):
        activate = subparsers.add_parser(action)
        activate.add_argument("--run-id", required=True)
        activate.add_argument("--replacement-key", required=True, type=Path)
        activate.add_argument("--expected-retired-jwks", required=True, type=Path)
        activate.add_argument("--retired-key-output", required=True, type=Path)
        activate.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    if os.geteuid() != 0:
        raise LifecycleError("lifecycle harness must run as root")
    os.umask(0o077)
    args = build_parser().parse_args()
    run_id = getattr(args, "run_id", None)
    validate_run_id(run_id)
    stage = validate_stage_directory(run_id)
    require_stage_path(args.output, stage, "output")
    if args.action == "jwks":
        resolved_signing_key = args.signing_key.resolve(strict=True)
        if resolved_signing_key != ACTIVE_SIGNING_KEY:
            require_equal(
                resolved_signing_key,
                stage / "replacement.pem",
                "replacement signing-key path",
            )
    elif args.action == "expiry":
        require_equal(
            args.signing_key.resolve(strict=True),
            ACTIVE_SIGNING_KEY,
            "expiry signing-key path",
        )
    elif args.action in {"activate-replacement", "rollback-activation"}:
        if args.action == "activate-replacement":
            require_equal(
                args.replacement_key.resolve(strict=True),
                stage / "replacement.pem",
                "replacement private-key path",
            )
            require_equal(
                args.expected_retired_jwks.resolve(strict=True),
                stage / "current-jwks.json",
                "current JWKS path",
            )
            require_equal(
                args.retired_key_output,
                stage / "retired.pem",
                "retired private-key output path",
            )
        else:
            require_equal(
                args.replacement_key.resolve(strict=True),
                stage / "retired.pem",
                "rollback private-key path",
            )
            require_equal(
                args.expected_retired_jwks.resolve(strict=True),
                stage / "replacement-jwks.json",
                "replacement JWKS path",
            )
            require_equal(
                args.retired_key_output,
                stage / "failed-replacement.pem",
                "failed replacement output path",
            )
    elif args.action == "exchange-positive":
        signing_key = args.signing_key.resolve(strict=True)
        expected = (
            stage / "replacement.pem"
            if args.event_type == "replacement_key_positive"
            else ACTIVE_SIGNING_KEY
        )
        require_equal(signing_key, expected, "positive signing-key path")
    elif args.action == "exchange-denial":
        signing_key = args.signing_key.resolve(strict=True)
        expected = (
            stage / "retired.pem"
            if args.event_type == "retired_key_exchange_denial"
            else ACTIVE_SIGNING_KEY
        )
        require_equal(signing_key, expected, "denial signing-key path")
    started_at = iso_time(utc_now())
    output = ReservedOutput(
        args.output,
        {
            "schema_version": 1,
            "provider": "anthropic",
            "status": "in_progress",
            "action": args.action,
            "run_id": run_id,
            "started_at": started_at,
            "source": source_binding(),
        },
    )
    phase = "local_preflight"
    partial_evidence: dict[str, Any] = {}

    def progress(value: str, observation: dict[str, Any] | None) -> None:
        nonlocal phase
        phase = value
        if observation is not None:
            partial_evidence.update(observation)

    try:
        if args.action == "jwks":
            validate_root_private_key(args.signing_key)
            event = {"keys": [load_public_jwk(args.signing_key)]}
        else:
            policy = load_policy()
            if args.action in {"activate-replacement", "rollback-activation"}:
                validate_root_private_key(ACTIVE_SIGNING_KEY)
                validate_root_private_key(args.replacement_key)
                validate_new_output_path(args.retired_key_output)
                event = activate_replacement(
                    policy,
                    args.replacement_key,
                    args.expected_retired_jwks,
                    args.retired_key_output,
                    args.run_id,
                    (
                        "replacement_key_activated"
                        if args.action == "activate-replacement"
                        else "replacement_key_activation_rolled_back"
                    ),
                    progress,
                )
            else:
                validate_root_private_key(args.signing_key)
                signing_key = args.signing_key.resolve(strict=True)
                if args.action == "expiry":
                    event = expiry_evidence(
                        policy, signing_key, args.run_id, progress=progress
                    )
                elif args.action == "exchange-positive":
                    if args.event_type in {
                        "rule_enabled_positive",
                        "rule_restored_positive",
                        "replacement_key_final_positive",
                    }:
                        require_equal(
                            signing_key, ACTIVE_SIGNING_KEY, "active signing-key path"
                        )
                        require_equal(args.key_role, "active", "active key role")
                    if args.event_type == "replacement_key_positive":
                        if signing_key == ACTIVE_SIGNING_KEY:
                            raise LifecycleError(
                                "replacement staging proof used the active-key path"
                            )
                        require_equal(
                            args.key_role,
                            "replacement_staging",
                            "replacement key role",
                        )
                    event = positive_event(
                        args.event_type,
                        args.key_role,
                        policy,
                        signing_key,
                        args.run_id,
                        progress=progress,
                    )
                else:
                    if args.event_type == "rule_disabled_exchange_denial":
                        require_equal(
                            signing_key, ACTIVE_SIGNING_KEY, "active signing-key path"
                        )
                        require_equal(
                            args.key_role, "active", "disabled-rule key role"
                        )
                    if args.event_type == "retired_key_exchange_denial":
                        if signing_key == ACTIVE_SIGNING_KEY:
                            raise LifecycleError(
                                "retired-key denial used the active replacement path"
                            )
                        require_equal(
                            args.key_role, "retired_staging", "retired key role"
                        )
                    event = denied_exchange_event(
                        args.event_type,
                        args.key_role,
                        policy,
                        signing_key,
                        args.run_id,
                        progress=progress,
                    )
        phase = "terminal_write"
        output.finish(event)
    except BaseException as error:
        output.finish(
            {
                "schema_version": 1,
                "provider": "anthropic",
                "status": "failed",
                "action": args.action,
                "run_id": run_id,
                "started_at": started_at,
                "failed_at": iso_time(utc_now()),
                "failure_type": error.__class__.__name__,
                "failure_reason": safe_failure_reason(error),
                "failure_phase": phase,
                "partial_evidence": partial_evidence,
                "post_failure_state": failure_state(args),
                "source": source_binding(),
            }
        )
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        LifecycleError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        KeyboardInterrupt,
    ) as error:
        print(f"anthropic WIF lifecycle: {error}", file=sys.stderr)
        raise SystemExit(1)
