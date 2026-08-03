#!/usr/bin/env python3
"""Plan or apply fail-closed Anthropic WIF lifecycle administration.

The reversible rule operation removes or restores the one reviewed workspace
mapping.  Issuer rotation first overlaps the current and replacement keys,
then removes the explicitly identified retired key.
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
import stat
import subprocess
import sys
from typing import Any, Callable
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy" / "anthropic-wif.json"
BASE_URL = "https://api.anthropic.com"
MAX_RESPONSE_BYTES = 1_000_000
RUN_ID_PATTERN = re.compile(r"anthropic-l3-[0-9]{8}-[0-9a-f]{10}")
REQUEST_ID_PATTERN = re.compile(r"req_[A-Za-z0-9]+")
KID_PATTERN = re.compile(r"patchyard-[0-9a-f]{16}")


class AdminError(RuntimeError):
    """An administrative precondition, request, or readback failed."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        del request, file_pointer, code, message, headers, url
        return None


URL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


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
    raise AdminError(f"JSON contains forbidden numeric constant: {value}")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AdminError(f"JSON contains duplicate key: {key}")
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


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AdminError(
            f"{label} differs: expected {expected!r}, observed {actual!r}"
        )


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


def load_policy() -> dict[str, Any]:
    document = load_json_file(POLICY_PATH)
    require_equal(document.get("schema_version"), 1, "policy schema")
    require_equal(document.get("provider"), "anthropic", "policy provider")
    exact = {
        ("organization", "id"): "aaadc747-869a-42d2-af51-58a5be8e3b7f",
        ("organization", "name"): "Example Company",
        ("workspace", "id"): "wrkspc_000000000000000000000000",
        ("workspace", "name"): "Patchyard Factory",
        ("service_account", "id"): "svac_01BqCdjSqFsWTvfDyCucThZy",
        ("issuer", "id"): "fdis_01A8wjwFPKfutAGtFN3oqF8J",
        ("issuer", "name"): "patchyard-control-plane",
        ("issuer", "issuer_url"): (
            "https://factory.example.com/workload-identity"
        ),
        ("issuer", "check_jti"): True,
        ("issuer", "max_jwt_lifetime_seconds"): 300,
        ("rule", "id"): "fdrl_000000000000000000000000",
        ("rule", "name"): "patchyard-inference",
        ("rule", "description"): (
            "Mint five-minute inference-only bearers for the Patchyard Factory worker."
        ),
        ("rule", "subject"): "patchyard-control-plane",
        ("rule", "audience"): BASE_URL,
        ("rule", "claims"): {"factory_environment": "production"},
        ("rule", "oauth_scope"): "workspace:inference",
        ("rule", "token_lifetime_seconds"): 300,
    }
    for (section, field), expected in exact.items():
        require_equal(document.get(section, {}).get(field), expected, f"policy {section}.{field}")
    return document


def validate_run_id(run_id: str) -> None:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise AdminError("run ID is malformed")


def parse_http_date(value: str | None) -> str:
    if value is None:
        raise AdminError("provider response has no Date header")
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError) as error:
        raise AdminError("provider Date header is malformed") from error
    if parsed.tzinfo is None:
        raise AdminError("provider Date header has no timezone")
    return iso_seconds(parsed)


def receipt(response: dict[str, Any], method: str, path: str) -> dict[str, Any]:
    request_id = response["headers"].get("request-id")
    if REQUEST_ID_PATTERN.fullmatch(str(request_id or "")) is None:
        raise AdminError("provider request ID is absent or malformed")
    payload_request_id = response["payload"].get("request_id")
    if payload_request_id is not None and payload_request_id != request_id:
        raise AdminError("provider header and body request IDs differ")
    return {
        "method": method,
        "endpoint": path,
        "http_status": response["status"],
        "request_id": request_id,
        "provider_date": parse_http_date(response["headers"].get("date")),
        "observed_at": response["observed_at"],
    }


class AnthropicAdmin:
    def __init__(self, profile: str) -> None:
        self.token = subprocess.check_output(
            ["ant", "auth", "print-credentials", "--profile", profile, "--access-token"],
            env=credential_free_env(),
            text=True,
        ).strip()
        if not self.token or len(self.token) > 8192:
            raise AdminError("admin OAuth token is empty or oversized")

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        allowed = {
            ("GET", "/v1/organizations/me"),
            ("GET", "/v1/organizations/federation_rules/fdrl_000000000000000000000000"),
            (
                "DELETE",
                "/v1/organizations/federation_rules/"
                "fdrl_000000000000000000000000/workspaces/"
                "wrkspc_000000000000000000000000",
            ),
            (
                "POST",
                "/v1/organizations/federation_rules/"
                "fdrl_000000000000000000000000/workspaces",
            ),
            (
                "GET",
                "/v1/organizations/federation_issuers/"
                "fdis_01A8wjwFPKfutAGtFN3oqF8J",
            ),
            (
                "POST",
                "/v1/organizations/federation_issuers/"
                "fdis_01A8wjwFPKfutAGtFN3oqF8J",
            ),
        }
        if (method, path) not in allowed:
            raise AdminError("provider request is outside the lifecycle-admin allowlist")
        encoded = None
        headers = {
            "anthropic-version": "2023-06-01",
            "authorization": f"Bearer {self.token}",
            "user-agent": "patchyard-anthropic-wif-lifecycle-admin/1",
        }
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":")).encode()
            headers["content-type"] = "application/json"
        request = urllib.request.Request(
            BASE_URL + path, data=encoded, headers=headers, method=method
        )
        try:
            response = URL_OPENER.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            raw = error.read(MAX_RESPONSE_BYTES + 1)
            error_type = "unknown"
            try:
                payload = load_json_bytes(raw)
                detail = payload.get("error")
                if isinstance(detail, dict) and isinstance(detail.get("type"), str):
                    error_type = detail["type"]
            except (json.JSONDecodeError, AttributeError):
                pass
            raise AdminError(
                f"{method} {path}: HTTP {error.code} error_type={error_type}"
            ) from error
        with response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise AdminError("provider response exceeds the byte limit")
            try:
                payload = load_json_bytes(raw)
            except json.JSONDecodeError as error:
                raise AdminError("provider response is not JSON") from error
            if not isinstance(payload, dict):
                raise AdminError("provider response is not a JSON object")
            return {
                "status": int(response.status),
                "headers": response.headers,
                "payload": payload,
                "observed_at": iso_time(utc_now()),
            }


def source_binding() -> dict[str, str]:
    return {
        "policy_sha256": digest_file(POLICY_PATH),
        "admin_tool_sha256": digest_file(Path(__file__).resolve()),
    }


def validate_organization(api: Any, policy: dict[str, Any]) -> None:
    response = api.request("GET", "/v1/organizations/me")
    require_equal(response["status"], 200, "organization read status")
    organization = response["payload"]
    require_equal(organization.get("id"), policy["organization"]["id"], "organization ID")
    require_equal(organization.get("name"), policy["organization"]["name"], "organization name")


def rule_path(policy: dict[str, Any]) -> str:
    return f"/v1/organizations/federation_rules/{policy['rule']['id']}"


def issuer_path(policy: dict[str, Any]) -> str:
    return f"/v1/organizations/federation_issuers/{policy['issuer']['id']}"


def validate_rule(
    value: dict[str, Any], policy: dict[str, Any], expected_workspace_ids: list[str]
) -> None:
    require_equal(value.get("id"), policy["rule"]["id"], "rule ID")
    require_equal(value.get("name"), policy["rule"]["name"], "rule name")
    require_equal(value.get("description"), policy["rule"]["description"], "rule description")
    require_equal(value.get("issuer_id"), policy["issuer"]["id"], "rule issuer")
    require_equal(value.get("archived_at"), None, "rule archived state")
    require_equal(value.get("applies_to_all_workspaces"), False, "rule all-workspaces state")
    require_equal(value.get("workspace_ids"), expected_workspace_ids, "rule workspace mappings")
    require_equal(value.get("oauth_scope"), policy["rule"]["oauth_scope"], "rule scope")
    require_equal(
        value.get("token_lifetime_seconds"),
        policy["rule"]["token_lifetime_seconds"],
        "rule lifetime",
    )
    require_equal(
        value.get("target", {}).get("type"), "service_account", "rule target type"
    )
    require_equal(
        value.get("target", {}).get("service_account_id"),
        policy["service_account"]["id"],
        "rule target",
    )
    match = value.get("match", {})
    require_equal(match.get("subject_prefix"), policy["rule"]["subject"], "rule subject")
    require_equal(match.get("audience"), policy["rule"]["audience"], "rule audience")
    require_equal(match.get("claims"), policy["rule"]["claims"], "rule claims")
    if match.get("condition") is not None:
        raise AdminError("rule has an unexpected CEL condition")


def rule_state(value: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": value["id"],
        "workspace_id": policy["workspace"]["id"],
        "workspace_ids": value["workspace_ids"],
        "applies_to_all_workspaces": value["applies_to_all_workspaces"],
        "archived": value.get("archived_at") is not None,
    }


def read_rule(
    api: Any, policy: dict[str, Any], expected_workspace_ids: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = rule_path(policy)
    response = api.request("GET", path)
    require_equal(response["status"], 200, "rule read status")
    validate_rule(response["payload"], policy, expected_workspace_ids)
    return response["payload"], receipt(response, "GET", path)


def validate_jwk(value: dict[str, Any]) -> None:
    require_equal(sorted(value), ["alg", "e", "kid", "kty", "n", "use"], "JWK fields")
    require_equal(value["alg"], "RS256", "JWK algorithm")
    require_equal(value["kty"], "RSA", "JWK type")
    require_equal(value["use"], "sig", "JWK use")
    require_equal(value["e"], "AQAB", "JWK exponent")
    if KID_PATTERN.fullmatch(str(value["kid"])) is None:
        raise AdminError("JWK key ID is malformed")
    for field in ("e", "n"):
        if not isinstance(value[field], str) or not value[field]:
            raise AdminError(f"JWK {field} is empty")
    if re.fullmatch(r"[A-Za-z0-9_-]+", value["n"]) is None:
        raise AdminError("JWK modulus is not unpadded base64url")
    try:
        modulus = base64.urlsafe_b64decode(
            value["n"] + "=" * (-len(value["n"]) % 4)
        )
    except ValueError as error:
        raise AdminError("JWK modulus is not valid base64url") from error
    if len(modulus) != 384 or modulus[0] == 0:
        raise AdminError("JWK modulus is not an exact 3072-bit value")


def jwk_descriptor(value: dict[str, Any]) -> dict[str, str]:
    validate_jwk(value)
    encoded = json.dumps(
        {"e": value["e"], "kty": value["kty"], "n": value["n"]},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return {
        "kid": value["kid"],
        "jwk_thumbprint_sha256": digest_bytes(encoded),
    }


def canonical_keys(keys: Any, expected_count: int) -> list[dict[str, Any]]:
    if not isinstance(keys, list) or len(keys) != expected_count:
        raise AdminError(f"inline JWKS must contain exactly {expected_count} key(s)")
    for key in keys:
        if not isinstance(key, dict):
            raise AdminError("inline JWKS contains a non-object key")
        validate_jwk(key)
    ordered = sorted(keys, key=lambda item: item["kid"])
    if len({item["kid"] for item in ordered}) != len(ordered):
        raise AdminError("inline JWKS contains a duplicate key ID")
    if len({jwk_descriptor(item)["jwk_thumbprint_sha256"] for item in ordered}) != len(ordered):
        raise AdminError("inline JWKS contains a duplicate public key")
    return ordered


def load_replacement_jwk(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or path.is_symlink():
        raise AdminError("replacement JWKS must be an absolute non-symlink path")
    try:
        if path.resolve(strict=True) != path:
            raise AdminError("replacement JWKS path is not canonical")
    except OSError as error:
        raise AdminError(f"cannot resolve replacement JWKS: {error}") from error
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= 65_536:
        raise AdminError("replacement JWKS is not a bounded regular file")
    document = load_json_file(path)
    require_equal(sorted(document), ["keys"], "replacement JWKS fields")
    return canonical_keys(document["keys"], 1)[0]


def validate_issuer(
    value: dict[str, Any], policy: dict[str, Any], expected_keys: list[dict[str, Any]]
) -> None:
    require_equal(value.get("id"), policy["issuer"]["id"], "issuer ID")
    require_equal(value.get("name"), policy["issuer"]["name"], "issuer name")
    require_equal(value.get("issuer_url"), policy["issuer"]["issuer_url"], "issuer URL")
    require_equal(value.get("archived_at"), None, "issuer archived state")
    require_equal(value.get("check_jti"), policy["issuer"]["check_jti"], "issuer JTI")
    require_equal(
        value.get("max_jwt_lifetime_seconds"),
        policy["issuer"]["max_jwt_lifetime_seconds"],
        "issuer assertion lifetime",
    )
    jwks = value.get("jwks")
    if not isinstance(jwks, dict):
        raise AdminError("issuer JWKS is not an object")
    require_equal(jwks.get("type"), "inline", "issuer JWKS type")
    require_equal(
        canonical_keys(jwks.get("keys"), len(expected_keys)),
        canonical_keys(expected_keys, len(expected_keys)),
        "issuer inline keys",
    )


def issuer_state(value: dict[str, Any]) -> dict[str, Any]:
    keys = canonical_keys(value["jwks"]["keys"], len(value["jwks"]["keys"]))
    return {
        "issuer_id": value["id"],
        "jwks_type": "inline",
        "keys": [jwk_descriptor(key) for key in keys],
        "archived": value.get("archived_at") is not None,
    }


def read_issuer(
    api: Any, policy: dict[str, Any], expected_keys: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = issuer_path(policy)
    response = api.request("GET", path)
    require_equal(response["status"], 200, "issuer read status")
    validate_issuer(response["payload"], policy, expected_keys)
    return response["payload"], receipt(response, "GET", path)


def plan_result(action: str, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": "anthropic",
        "mode": "plan",
        "action": action,
        "ready": True,
        "state_before": before,
        "state_after": after,
    }


def admin_event(
    event_type: str,
    run_id: str,
    mutation: dict[str, Any],
    readback: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": "anthropic",
        "run_id": run_id,
        "event_type": event_type,
        "observed_at": readback["observed_at"],
        "mutation": mutation,
        "readback": readback,
        "state_before": before,
        "state_after": after,
        "source": source_binding(),
    }


def rule_operation(
    api: Any,
    policy: dict[str, Any],
    action: str,
    run_id: str,
    apply: bool,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    workspace = policy["workspace"]["id"]
    if action == "rule-disable":
        expected_before, expected_after = [workspace], []
        method = "DELETE"
        path = f"{rule_path(policy)}/workspaces/{workspace}"
        body = None
        response_contract = {
            "federation_rule_id": policy["rule"]["id"],
            "type": "federation_rule_workspace_deleted",
            "workspace_id": workspace,
        }
        event_type = "rule_disabled"
    elif action == "rule-restore":
        expected_before, expected_after = [], [workspace]
        method = "POST"
        path = f"{rule_path(policy)}/workspaces"
        body = {"workspace_id": workspace}
        response_contract = None
        event_type = "rule_restored"
    else:
        raise AdminError("unsupported rule action")
    if progress is not None:
        progress("provider_preflight")
    before_value, _ = read_rule(api, policy, expected_before)
    before = rule_state(before_value, policy)
    after = dict(before)
    after["workspace_ids"] = expected_after
    if not apply:
        return plan_result(action, before, after)
    if progress is not None:
        progress("provider_mutation_requested")
    response = api.request(method, path, body)
    require_equal(response["status"], 200, "rule mutation status")
    payload = response["payload"]
    if response_contract is not None:
        require_equal(payload, response_contract, "rule-disable response")
    else:
        require_equal(payload.get("federation_rule_id"), policy["rule"]["id"], "restore rule ID")
        require_equal(payload.get("workspace_id"), workspace, "restore workspace ID")
        require_equal(payload.get("type"), "federation_rule_workspace", "restore response type")
    mutation = receipt(response, method, path)
    if progress is not None:
        progress("provider_mutation_accepted")
    after_value, readback = read_rule(api, policy, expected_after)
    if progress is not None:
        progress("provider_readback_accepted")
    return admin_event(
        event_type,
        run_id,
        mutation,
        readback,
        before,
        rule_state(after_value, policy),
    )


def issuer_operation(
    api: Any,
    policy: dict[str, Any],
    action: str,
    run_id: str,
    apply: bool,
    replacement_jwk: dict[str, Any],
    expected_current_jwk: dict[str, Any],
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    path = issuer_path(policy)
    if progress is not None:
        progress("provider_preflight")
    initial_response = api.request("GET", path)
    require_equal(initial_response["status"], 200, "issuer read status")
    value = initial_response["payload"]
    jwks = value.get("jwks", {})
    require_equal(jwks.get("type"), "inline", "issuer JWKS type")
    if action == "issuer-stage":
        current = canonical_keys(jwks.get("keys"), 1)
        validate_issuer(value, policy, current)
        require_equal(current, [expected_current_jwk], "expected current issuer key")
        if jwk_descriptor(current[0]) == jwk_descriptor(replacement_jwk):
            raise AdminError("replacement key is not distinct from the current key")
        target = canonical_keys([current[0], replacement_jwk], 2)
        event_type = "issuer_rotation_staged"
    elif action == "issuer-rollback-stage":
        current = canonical_keys(jwks.get("keys"), 2)
        validate_issuer(value, policy, current)
        require_equal(
            current,
            canonical_keys([expected_current_jwk, replacement_jwk], 2),
            "expected staged issuer keys",
        )
        target = [expected_current_jwk]
        event_type = "issuer_rotation_rolled_back"
    elif action == "issuer-retire":
        current = canonical_keys(jwks.get("keys"), 2)
        validate_issuer(value, policy, current)
        require_equal(
            current,
            canonical_keys([expected_current_jwk, replacement_jwk], 2),
            "expected staged issuer keys",
        )
        matching = [
            key
            for key in current
            if jwk_descriptor(key) == jwk_descriptor(replacement_jwk)
        ]
        if len(matching) != 1:
            raise AdminError("staged issuer does not contain the one replacement key")
        target = [matching[0]]
        event_type = "issuer_retired_key"
    elif action == "issuer-restore-overlap":
        current = canonical_keys(jwks.get("keys"), 1)
        validate_issuer(value, policy, current)
        require_equal(current, [replacement_jwk], "expected replacement-only issuer key")
        target = canonical_keys([expected_current_jwk, replacement_jwk], 2)
        event_type = "issuer_retired_key_restored"
    else:
        raise AdminError("unsupported issuer action")
    before = issuer_state(value)
    after = {
        "issuer_id": policy["issuer"]["id"],
        "jwks_type": "inline",
        "keys": [jwk_descriptor(key) for key in target],
        "archived": False,
    }
    if not apply:
        return plan_result(action, before, after)
    if progress is not None:
        progress("provider_mutation_requested")
    response = api.request("POST", path, {"jwks": {"type": "inline", "keys": target}})
    require_equal(response["status"], 200, "issuer mutation status")
    validate_issuer(response["payload"], policy, target)
    mutation = receipt(response, "POST", path)
    if progress is not None:
        progress("provider_mutation_accepted")
    after_value, readback = read_issuer(api, policy, target)
    if progress is not None:
        progress("provider_readback_accepted")
    return admin_event(
        event_type,
        run_id,
        mutation,
        readback,
        before,
        issuer_state(after_value),
    )


def encoded_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        written = os.write(descriptor, value[offset:])
        if written <= 0:
            raise AdminError("short write while preserving admin evidence")
        offset += written


def validate_new_output_path(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink() or path.exists():
        raise AdminError("output must be an absolute new non-symlink path")
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise AdminError("output parent must be an existing non-symlink directory")
    try:
        if path.parent.resolve(strict=True) != path.parent:
            raise AdminError("output parent path is not canonical")
    except OSError as error:
        raise AdminError(f"cannot resolve output parent: {error}") from error


class ReservedOutput:
    """Reserve the terminal path before any provider operation can start."""

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
            f".{self.path.name}.terminal-{os.getpid()}-{os.urandom(8).hex()}"
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


def post_failure_readback(
    api: Any, policy: dict[str, Any], action: str
) -> dict[str, Any]:
    """Read the mutated object again without claiming it is in an expected state."""
    try:
        if action.startswith("rule-"):
            path = rule_path(policy)
            response = api.request("GET", path)
            require_equal(response["status"], 200, "failure rule readback status")
            value = response["payload"]
            workspace_ids = value.get("workspace_ids")
            if (
                not isinstance(workspace_ids, list)
                or len(workspace_ids) > 16
                or any(not isinstance(item, str) or len(item) > 128 for item in workspace_ids)
            ):
                raise AdminError("failure rule readback has invalid workspace IDs")
            validate_rule(value, policy, workspace_ids)
            return {
                "status": "observed",
                "receipt": receipt(response, "GET", path),
                "state": rule_state(value, policy),
            }
        path = issuer_path(policy)
        response = api.request("GET", path)
        require_equal(response["status"], 200, "failure issuer readback status")
        value = response["payload"]
        keys = value.get("jwks", {}).get("keys")
        if not isinstance(keys, list) or not 1 <= len(keys) <= 2:
            raise AdminError("failure issuer readback has an unsafe key count")
        canonical = canonical_keys(keys, len(keys))
        validate_issuer(value, policy, canonical)
        return {
            "status": "observed",
            "receipt": receipt(response, "GET", path),
            "state": issuer_state(value),
        }
    except (AdminError, OSError, json.JSONDecodeError) as error:
        return {
            "status": "readback_failed",
            "failure_type": error.__class__.__name__,
            "failure_reason": safe_failure_reason(error),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="patchyard-admin")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("rule-disable", "rule-restore"):
        child = subparsers.add_parser(action)
        child.add_argument("--run-id", required=True)
    subparsers.add_parser("issuer-export-current-jwks")
    for action in (
        "issuer-stage",
        "issuer-rollback-stage",
        "issuer-retire",
        "issuer-restore-overlap",
    ):
        child = subparsers.add_parser(action)
        child.add_argument("--run-id", required=True)
        child.add_argument("--replacement-jwks", required=True, type=Path)
        child.add_argument("--expected-current-jwks", required=True, type=Path)
    return parser


def main() -> int:
    os.umask(0o077)
    args = build_parser().parse_args()
    if args.action != "issuer-export-current-jwks":
        validate_run_id(args.run_id)
    if args.action == "issuer-export-current-jwks":
        if args.apply or args.output is None:
            raise AdminError("issuer export requires --output and forbids --apply")
    elif args.apply != (args.output is not None):
        raise AdminError("--apply and --output must be supplied together")
    run_id = getattr(args, "run_id", None)
    started_at = iso_time(utc_now())
    output = None
    if args.output is not None:
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
    policy: dict[str, Any] | None = None
    api: AnthropicAdmin | None = None
    phase = "local_preflight"

    def progress(value: str) -> None:
        nonlocal phase
        phase = value

    try:
        policy = load_policy()
        replacement = None
        expected_current = None
        if args.action in {
            "issuer-stage",
            "issuer-rollback-stage",
            "issuer-retire",
            "issuer-restore-overlap",
        }:
            replacement = load_replacement_jwk(args.replacement_jwks)
            expected_current = load_replacement_jwk(args.expected_current_jwks)
        phase = "admin_authentication"
        api = AnthropicAdmin(args.profile)
        phase = "organization_preflight"
        validate_organization(api, policy)
        if args.action == "issuer-export-current-jwks":
            phase = "issuer_export_read"
            path = issuer_path(policy)
            response = api.request("GET", path)
            require_equal(response["status"], 200, "issuer read status")
            issuer = response["payload"]
            jwks = issuer.get("jwks", {})
            current = canonical_keys(jwks.get("keys"), 1)
            validate_issuer(issuer, policy, current)
            result = {"keys": current}
        elif args.action.startswith("rule-"):
            result = rule_operation(
                api,
                policy,
                args.action,
                args.run_id,
                args.apply,
                progress,
            )
        else:
            assert replacement is not None and expected_current is not None
            phase = "enabled_rule_preflight"
            enabled_rule, _ = read_rule(api, policy, [policy["workspace"]["id"]])
            del enabled_rule
            result = issuer_operation(
                api,
                policy,
                args.action,
                args.run_id,
                args.apply,
                replacement,
                expected_current,
                progress,
            )
        phase = "terminal_write"
        if output is None:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            output.finish(result)
    except BaseException as error:
        if output is not None:
            readback: dict[str, Any] = {"status": "not_attempted"}
            if api is not None and policy is not None and args.apply:
                readback = post_failure_readback(api, policy, args.action)
            output.finish(
                {
                    "schema_version": 1,
                    "provider": "anthropic",
                    "status": "failed",
                    "action": args.action,
                    "run_id": run_id,
                    "started_at": started_at,
                    "failed_at": iso_time(utc_now()),
                    "failure_phase": phase,
                    "failure_type": error.__class__.__name__,
                    "failure_reason": safe_failure_reason(error),
                    "post_failure_readback": readback,
                    "source": source_binding(),
                }
            )
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        AdminError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        KeyboardInterrupt,
    ) as error:
        print(f"anthropic WIF lifecycle admin: {error}", file=sys.stderr)
        raise SystemExit(1)
