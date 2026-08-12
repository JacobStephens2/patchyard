#!/usr/bin/env python3
"""Check the OpenAI first-exchange source and observation contract."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import sysconfig
from typing import Any


REPO = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO / "policy/openai-wif.json"
BASE_HARNESS_PATH = REPO / "tools/anthropic-wif-lifecycle.py"
ISSUANCE_ADAPTER_PATH = REPO / "tools/openai-wif-issuance.py"
RESULT_PATH = REPO / "research/isolation/results/openai-first-token-exchange.json"
PROVIDER_POLICY_PATH = REPO / "policy/provider-egress.json"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
RUN_ID = re.compile(r"openai-wif-[0-9]{8}-[0-9a-f]{10}")
KID = re.compile(r"patchyard-[0-9a-f]{16}")
HEX64 = re.compile(r"[0-9a-f]{64}")
UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z"
)
SAFE_RESPONSE_STRING = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/+;-]{0,127}")
SAFE_FIELD_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
JWT = re.compile(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
OPENAI_KEY = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
BEARER = re.compile(r"Bearer [A-Za-z0-9._~-]{16,}", re.IGNORECASE)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
MAX_RESPONSE_BYTES = 1_000_000
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
OBSERVATION_KEYS = {
    "schema_version",
    "provider",
    "observation_kind",
    "run_id",
    "started_at",
    "assertion_descriptor",
    "exchange_request",
    "exchange_response",
    "credential_removed_at",
    "response_predicate",
    "control_plane_provenance",
    "provider_response_observed",
    "qualification_evidence",
    "source",
}
FIXTURE_KEYS = {"fixture_kind", "fixture_lineage"}
ASSERTION_KEYS = {
    "algorithm",
    "kid",
    "issuer",
    "subject",
    "audience",
    "issued_at",
    "minted_at",
    "expires_at",
    "lifetime_seconds",
    "jti_supplied",
    "factory_environment",
    "jwk_thumbprint_sha256",
}
REQUEST_KEYS = {
    "endpoint",
    "content_type",
    "grant_type",
    "subject_token_type",
    "subject_token_supplied",
    "identity_provider_id",
    "service_account_id",
    "scope_supplied",
    "requested_at",
}
RESPONSE_KEYS = {
    "source",
    "http_status",
    "request_started_at",
    "observed_at",
    "provider_date",
    "request_id",
    "request_id_supplied",
    "content_type",
    "body_bytes",
    "body_format",
    "response_shape",
    "access_token_supplied",
    "token_type",
    "expires_in",
    "error_type",
}
SOURCE_KEYS = {
    "policy_sha256",
    "base_harness_sha256",
    "issuance_adapter_sha256",
}
FIELD_DESCRIPTOR_KEYS = {"name", "name_recorded", "value_type"}
JSON_VALUE_TYPES = {"null", "boolean", "integer", "number", "string", "object", "array"}


class EvidenceJsonError(ValueError):
    """Evidence JSON is ambiguous or outside the strict data contract."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_json_constant(value: str) -> None:
    raise EvidenceJsonError(f"forbidden numeric constant: {value}")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceJsonError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_file(path: Path) -> Any:
    return json.loads(
        path.read_bytes(),
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_json_constant,
    )


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def isolation_errors() -> list[str]:
    errors: list[str] = []
    if not sys.flags.isolated:
        errors.append("OpenAI WIF issuance checker requires python3 -I")
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    for module in (hashlib, json, re, sysconfig):
        source = getattr(module, "__file__", None)
        if source is None or not is_within(Path(source).resolve(), stdlib):
            errors.append(
                "OpenAI WIF issuance checker rejected "
                f"{module.__name__} provenance: {source!r}"
            )
    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except OSError:
            continue
        if is_within(resolved, REPO):
            errors.append(
                f"OpenAI WIF issuance checker has repository import path: {entry}"
            )
    return errors


def exact_keys(value: Any, expected: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} is not an object")
        return False
    if set(value) != expected:
        errors.append(f"{label} has an unexpected evidence shape")
        return False
    return True


def parse_time(value: Any, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or UTC_TIMESTAMP.fullmatch(value) is None:
        errors.append(f"{label} is not a UTC timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label} is malformed")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{label} has no timezone")
        return None
    return parsed


def valid_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def safe_optional_string(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and SAFE_RESPONSE_STRING.fullmatch(value) is not None
    )


def validate_assertion(
    value: Any, policy: dict[str, Any], errors: list[str]
) -> tuple[datetime | None, datetime | None, datetime | None]:
    if not exact_keys(value, ASSERTION_KEYS, "assertion descriptor", errors):
        return None, None, None
    if value.get("algorithm") != "RS256":
        errors.append("assertion algorithm differs")
    if value.get("kid") != policy["issuer"]["jwks_kid"]:
        errors.append("assertion key ID differs from the uploaded JWKS")
    if KID.fullmatch(str(value.get("kid", ""))) is None:
        errors.append("assertion key ID is malformed")
    for field, expected in (
        ("issuer", policy["issuer"]["issuer_url"]),
        ("subject", policy["rule"]["subject"]),
        ("audience", policy["rule"]["audience"]),
        ("factory_environment", policy["rule"]["claims"]["factory_environment"]),
    ):
        if value.get(field) != expected:
            errors.append(f"assertion {field} differs from policy")
    if value.get("lifetime_seconds") != policy["issuer"]["max_jwt_lifetime_seconds"]:
        errors.append("assertion lifetime differs from policy")
    if value.get("jti_supplied") is not True:
        errors.append("assertion does not record a single-use JTI")
    if HEX64.fullmatch(str(value.get("jwk_thumbprint_sha256", ""))) is None:
        errors.append("assertion JWK thumbprint is malformed")
    issued = parse_time(value.get("issued_at"), "assertion issued_at", errors)
    minted = parse_time(value.get("minted_at"), "assertion minted_at", errors)
    expires = parse_time(value.get("expires_at"), "assertion expires_at", errors)
    if issued is not None and expires is not None:
        if int((expires - issued).total_seconds()) != 300:
            errors.append("assertion timestamps do not encode five minutes")
    if issued is not None and minted is not None and not issued <= minted:
        errors.append("assertion was minted before its issued-at claim")
    if minted is not None and expires is not None and not minted < expires:
        errors.append("assertion was already expired when minted")
    return issued, minted, expires


def validate_request(
    value: Any, policy: dict[str, Any], errors: list[str]
) -> datetime | None:
    if not exact_keys(value, REQUEST_KEYS, "exchange request", errors):
        return None
    expected = {
        "endpoint": "https://auth.openai.com/oauth/token",
        "content_type": "application/json",
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "subject_token_supplied": True,
        "identity_provider_id": policy["issuer"]["id"],
        "service_account_id": policy["service_account"]["id"],
        "scope_supplied": False,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            errors.append(f"exchange request {field} differs")
    return parse_time(value.get("requested_at"), "exchange requested_at", errors)


def validate_field_descriptors(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{label} is not a list")
        return
    recorded_names = []
    for item in value:
        if not exact_keys(item, FIELD_DESCRIPTOR_KEYS, f"{label} field", errors):
            continue
        recorded = item.get("name_recorded")
        name = item.get("name")
        if recorded is True:
            if not isinstance(name, str) or SAFE_FIELD_NAME.fullmatch(name) is None:
                errors.append(f"{label} contains an unsafe recorded field name")
            else:
                recorded_names.append(name)
        elif recorded is False:
            if name is not None:
                errors.append(f"{label} retained an unsafe field name")
        else:
            errors.append(f"{label} field-name provenance is not boolean")
        if item.get("value_type") not in JSON_VALUE_TYPES:
            errors.append(f"{label} contains an unknown JSON value type")
    if recorded_names != sorted(recorded_names) or len(recorded_names) != len(
        set(recorded_names)
    ):
        errors.append(f"{label} field names are not unique and sorted")


def validate_response_shape(value: Any, body_format: Any, errors: list[str]) -> None:
    if not exact_keys(
        value,
        {"body_kind", "top_level_fields", "error_fields"},
        "exchange response shape",
        errors,
    ):
        return
    if value.get("body_kind") != body_format:
        errors.append("exchange body kind differs from its response shape")
    validate_field_descriptors(
        value.get("top_level_fields"), "top-level response shape", errors
    )
    validate_field_descriptors(value.get("error_fields"), "error response shape", errors)


def validate_observed_response(
    value: Any, errors: list[str]
) -> tuple[datetime | None, datetime | None]:
    if not exact_keys(value, RESPONSE_KEYS, "exchange response", errors):
        return None, None
    if value.get("source") != "openai_http_response":
        errors.append("exchange response is not an OpenAI HTTP observation")
    status = value.get("http_status")
    if not valid_int(status) or not 100 <= status <= 599:
        errors.append("exchange response HTTP status is malformed")
    requested = parse_time(
        value.get("request_started_at"), "exchange response request start", errors
    )
    observed = parse_time(value.get("observed_at"), "exchange response observed_at", errors)
    provider_date = value.get("provider_date")
    if provider_date is not None:
        parse_time(provider_date, "exchange response provider date", errors)
    supplied = value.get("request_id_supplied")
    request_id = value.get("request_id")
    if supplied is not True and supplied is not False:
        errors.append("exchange request-ID presence is not boolean")
    if supplied is False and request_id is not None:
        errors.append("exchange response retained an absent request ID")
    if not safe_optional_string(request_id):
        errors.append("exchange response request ID is not safely bounded")
    if not safe_optional_string(value.get("content_type")):
        errors.append("exchange response content type is not safely bounded")
    body_bytes = value.get("body_bytes")
    if not valid_int(body_bytes) or not 0 <= body_bytes <= MAX_RESPONSE_BYTES:
        errors.append("exchange response byte count is outside the bound")
    body_format = value.get("body_format")
    allowed_formats = {"non_json"} | {
        f"json_{value_type}" for value_type in JSON_VALUE_TYPES
    }
    if body_format not in allowed_formats:
        errors.append("exchange response body format is malformed")
    validate_response_shape(value.get("response_shape"), body_format, errors)
    access_token_supplied = value.get("access_token_supplied")
    if access_token_supplied is not True and access_token_supplied is not False:
        errors.append("access-token presence is not boolean")
    if not safe_optional_string(value.get("token_type")):
        errors.append("exchange token type is not safely bounded")
    expires_in = value.get("expires_in")
    if expires_in is not None and not valid_int(expires_in):
        errors.append("exchange lifetime observation is not an integer")
    if not safe_optional_string(value.get("error_type")):
        errors.append("exchange error type is not safely bounded")
    if requested is not None and observed is not None and requested > observed:
        errors.append("exchange response was observed before its request")
    return requested, observed


def validate_unobserved_response(
    value: Any, errors: list[str]
) -> tuple[datetime | None, datetime | None]:
    if not exact_keys(value, RESPONSE_KEYS, "synthetic exchange response", errors):
        return None, None
    expected = {
        "source": "synthetic_unobserved_response",
        "http_status": None,
        "provider_date": None,
        "request_id": None,
        "request_id_supplied": False,
        "content_type": None,
        "body_bytes": 0,
        "body_format": "unobserved",
        "response_shape": {
            "body_kind": "unobserved",
            "top_level_fields": [],
            "error_fields": [],
        },
        "access_token_supplied": False,
        "token_type": None,
        "expires_in": None,
        "error_type": None,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            errors.append(f"synthetic exchange response {field} invents an observation")
    requested = parse_time(
        value.get("request_started_at"), "synthetic exchange request start", errors
    )
    observed = parse_time(
        value.get("observed_at"), "synthetic exchange observed_at", errors
    )
    if requested is not None and observed is not None and requested > observed:
        errors.append("synthetic exchange response is out of order")
    return requested, observed


def validate_source(value: Any, errors: list[str]) -> None:
    if not exact_keys(value, SOURCE_KEYS, "OpenAI source binding", errors):
        return
    expected = {
        "policy_sha256": digest(POLICY_PATH),
        "base_harness_sha256": digest(BASE_HARNESS_PATH),
        "issuance_adapter_sha256": digest(ISSUANCE_ADAPTER_PATH),
    }
    if value != expected:
        errors.append("OpenAI source binding differs from the current sources")


def secret_named_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {
                "secret",
                "access_token",
                "assertion",
                "subject_token",
                "identity_token",
                "authorization",
                "private_key",
                "api_key",
            }:
                return key
            found = secret_named_key(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = secret_named_key(child)
            if found is not None:
                return found
    return None


def credential_errors(value: Any) -> list[str]:
    errors: list[str] = []
    forbidden = secret_named_key(value)
    if forbidden is not None:
        errors.append(f"OpenAI evidence contains forbidden credential field: {forbidden}")
    serialized = json.dumps(value, sort_keys=True)
    if (
        JWT.search(serialized)
        or OPENAI_KEY.search(serialized)
        or BEARER.search(serialized)
        or PRIVATE_KEY.search(serialized)
    ):
        errors.append("OpenAI evidence carries credential-shaped material")
    return errors


def validate_common(
    result: Any,
    policy: dict[str, Any],
    *,
    synthetic: bool,
) -> list[str]:
    errors: list[str] = []
    expected_keys = OBSERVATION_KEYS | (FIXTURE_KEYS if synthetic else set())
    if not exact_keys(result, expected_keys, "OpenAI exchange result", errors):
        return errors
    if result.get("schema_version") != 1 or result.get("provider") != "openai":
        errors.append("OpenAI exchange result identity differs")
    if result.get("observation_kind") != "first-token-exchange":
        errors.append("OpenAI exchange result has the wrong observation kind")
    if RUN_ID.fullmatch(str(result.get("run_id", ""))) is None:
        errors.append("OpenAI exchange result run ID is malformed")
    started = parse_time(result.get("started_at"), "exchange started_at", errors)
    issued, minted, expires = validate_assertion(
        result.get("assertion_descriptor"), policy, errors
    )
    request_time = validate_request(result.get("exchange_request"), policy, errors)
    if synthetic:
        response_request, response_time = validate_unobserved_response(
            result.get("exchange_response"), errors
        )
    else:
        response_request, response_time = validate_observed_response(
            result.get("exchange_response"), errors
        )
    removed = parse_time(
        result.get("credential_removed_at"), "credential_removed_at", errors
    )
    if result.get("response_predicate") != RESPONSE_PREDICATE:
        errors.append("OpenAI response predicate was enforced before an observation")
    if result.get("control_plane_provenance") != CONTROL_PLANE_PROVENANCE:
        errors.append("OpenAI result misstates console-mutation provenance")
    validate_source(result.get("source"), errors)
    if request_time is not None and response_request is not None:
        if request_time != response_request:
            errors.append("exchange request and response name different start times")
    ordered = [started, request_time, response_time, removed]
    if all(value is not None for value in ordered):
        assert all(isinstance(value, datetime) for value in ordered)
        if not all(left <= right for left, right in zip(ordered, ordered[1:])):
            errors.append("OpenAI exchange UTC observations are out of order")
    if issued is not None and started is not None and issued > started:
        errors.append("OpenAI run began before the backdated assertion issued-at claim")
    if minted is not None and request_time is not None and minted > request_time:
        errors.append("OpenAI exchange began before the assertion was minted")
    if expires is not None and request_time is not None and request_time >= expires:
        errors.append("OpenAI exchange began with an expired assertion")
    errors.extend(credential_errors(result))
    return errors


def validate_observation(result: Any, policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if isinstance(result, dict) and result.get("status") == "in_progress":
        return ["in-progress OpenAI exchange record is inert"]
    if isinstance(result, dict) and result.get("status") == "failed":
        return ["failed OpenAI exchange record is not a provider observation"]
    errors.extend(validate_common(result, policy, synthetic=False))
    if isinstance(result, dict):
        if result.get("provider_response_observed") is not True:
            errors.append("OpenAI observation does not record a provider response")
        if result.get("qualification_evidence") is not False:
            errors.append("first OpenAI exchange observation claims qualification")
    return errors


def validate_contract_fixture(result: Any, policy: dict[str, Any]) -> list[str]:
    errors = validate_common(result, policy, synthetic=True)
    if not isinstance(result, dict):
        return errors
    if result.get("fixture_kind") != "synthetic-openai-first-exchange-satisfiability":
        errors.append("OpenAI contract fixture kind differs")
    if result.get("fixture_lineage") != {
        "assertion_contract": "policy/openai-wif.json",
        "provider_response": "unobserved-placeholder",
    }:
        errors.append("OpenAI contract fixture lineage differs")
    if result.get("provider_response_observed") is not False:
        errors.append("OpenAI contract fixture claims a provider response")
    if result.get("qualification_evidence") is not False:
        errors.append("OpenAI contract fixture claims qualification")
    return errors


def validate_qualification_evidence(result: Any, policy: dict[str, Any]) -> list[str]:
    if isinstance(result, dict) and result.get("fixture_kind") is not None:
        return ["synthetic OpenAI fixture cannot be qualification evidence"]
    errors = validate_observation(result, policy)
    if isinstance(result, dict) and result.get("qualification_evidence") is not True:
        errors.append("OpenAI first-exchange observation is not qualification evidence")
    errors.append("OpenAI qualification predicate is unenforced pending an observed response")
    return errors


def static_errors() -> tuple[list[str], dict[str, Any]]:
    errors = isolation_errors()
    try:
        policy = load_json_file(POLICY_PATH)
    except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
        errors.append(f"cannot read OpenAI WIF policy: {error}")
        policy = {}
    if policy != EXPECTED_POLICY:
        errors.append("OpenAI WIF policy differs from its exact binding")
    if (
        not BASE_HARNESS_PATH.is_file()
        or BASE_HARNESS_PATH.is_symlink()
        or digest(BASE_HARNESS_PATH) != BASE_HARNESS_SHA256
    ):
        errors.append("qualified expiry harness differs from its exact binding")
    if not ISSUANCE_ADAPTER_PATH.is_file() or ISSUANCE_ADAPTER_PATH.is_symlink():
        errors.append("OpenAI issuance adapter is missing or a symlink")
    else:
        adapter = ISSUANCE_ADAPTER_PATH.read_text()
        for required in (
            "BASE_HARNESS_SHA256",
            "BASE.mint_assertion",
            'TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"',
            '"grant_type": "urn:ietf:params:oauth:grant-type:token-exchange"',
            '"subject_token_type": "urn:ietf:params:oauth:token-type:jwt"',
            '"identity_provider_id": policy["issuer"]["id"]',
            '"service_account_id": policy["service_account"]["id"]',
            '"scope_supplied": False',
            '"provider_response_observed": True',
            '"qualification_evidence": False',
            '"mutation_receipt_obtained": False',
            'urllib.request.ProxyHandler({})',
            '"OPENAI_API_KEY"',
            "BASE.ReservedOutput",
        ):
            if required not in adapter:
                errors.append(f"OpenAI issuance adapter is missing: {required}")
    try:
        providers = load_json_file(PROVIDER_POLICY_PATH)["providers"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError, EvidenceJsonError) as error:
        errors.append(f"cannot read provider egress policy: {error}")
    else:
        if len(providers) != 13:
            errors.append("provider egress policy does not contain 13 providers")
    return errors, policy


def read_bounded_input(path: Path, label: str, errors: list[str]) -> Any:
    try:
        if not path.is_file() or path.is_symlink():
            raise EvidenceJsonError(f"{label} is not a regular non-symlink file")
        if not 1 <= path.stat().st_size <= MAX_RESPONSE_BYTES:
            raise EvidenceJsonError(f"{label} is outside the byte limit")
        return load_json_file(path)
    except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
        errors.append(f"cannot read {label}: {error}")
        return None


def main() -> int:
    errors, policy = static_errors()
    allow_missing = False
    mode = "default"
    path = RESULT_PATH
    arguments = sys.argv[1:]
    while arguments:
        argument = arguments.pop(0)
        if argument == "--allow-missing-results":
            allow_missing = True
        elif argument in {"--observation", "--evidence", "--contract-fixture"} and arguments:
            if mode != "default" or path != RESULT_PATH:
                errors.append("OpenAI checker accepts only one evidence mode")
            mode = argument.removeprefix("--")
            path = Path(arguments.pop(0))
        else:
            errors.append(f"unknown checker argument: {argument}")
    if allow_missing and (mode != "default" or path != RESULT_PATH):
        errors.append("allow-missing-results cannot be combined with supplied evidence")
    if not path.exists():
        if not allow_missing:
            errors.append("OpenAI first-exchange result is missing")
    else:
        result = read_bounded_input(path, "OpenAI exchange input", errors)
        if result is not None:
            if mode == "contract-fixture":
                errors.extend(validate_contract_fixture(result, policy))
            elif mode == "evidence":
                errors.extend(validate_qualification_evidence(result, policy))
            else:
                errors.extend(validate_observation(result, policy))
    if errors:
        print("OpenAI WIF issuance check: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    if mode == "contract-fixture":
        status = "synthetic contract fixture; not qualification evidence"
    elif path.exists():
        status = "with non-qualifying provider observation"
    else:
        status = "static preflight"
    print(f"OpenAI WIF issuance check: pass ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
