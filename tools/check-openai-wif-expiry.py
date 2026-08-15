#!/usr/bin/env python3
"""Check the OpenAI expired-assertion source and Result contract."""

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
EXPIRY_ADAPTER_PATH = REPO / "tools/openai-wif-expiry.py"
RESULT_PATH = REPO / "research/isolation/results/openai-expiry-denial.json"
PROVIDER_POLICY_PATH = REPO / "policy/provider-egress.json"
POLICY_SHA256 = "87cf13bb136ed9a365bd14822a14d4808a6ef585ce1c278b926fa173d1152e5f"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
# A144: the signing-identity split re-pointed the adapter's key path without
# re-producing the banked Result, so the pre-split digests stay acceptable.
SUPERSEDES_CHECKER_SHA256 = (
    "b190f6cadd01945153b116225e525a41"
    "0cda412ba875ed64196719f994d77171",
)
SUPERSEDES_SOURCE_SHA256 = {
    "tools/openai-wif-expiry.py": (
        "511b9499b47701138d8d52b87e04f7614be1b8d4938f03714cfdcbbd777976e1",
    ),
}
RUN_ID = re.compile(r"openai-expiry-[0-9]{8}-[0-9a-f]{10}")
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
RESPONSE_PREDICATE = {
    "enforced": False,
    "basis": "no-observed-openai-expired-assertion-response",
}
CONTROL_PLANE_PROVENANCE = {
    "control_plane_mutation_claimed": False,
    "mutation_receipt_obtained": False,
    "attestation_required": False,
}
RESULT_KEYS = {
    "schema_version",
    "provider",
    "qualification_requirement",
    "authorization_ruling",
    "observation_kind",
    "run_id",
    "started_at",
    "assertion_descriptor",
    "exchange_request",
    "expiry_denial",
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
    "kid_derived_from_public_der",
    "issuer",
    "subject",
    "audience",
    "issued_at",
    "minted_at",
    "expires_at",
    "lifetime_seconds",
    "expired_before_mint_seconds",
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
    "attempt_count",
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
    "error_type",
}
SOURCE_KEYS = {"policy_sha256", "base_harness_sha256", "expiry_adapter_sha256"}
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
        errors.append("OpenAI expiry checker requires python3 -I")
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    for module in (hashlib, json, re, sysconfig):
        source = getattr(module, "__file__", None)
        if source is None or not is_within(Path(source).resolve(), stdlib):
            errors.append(
                f"OpenAI expiry checker rejected {module.__name__} provenance: {source!r}"
            )
    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except OSError:
            continue
        if is_within(resolved, REPO):
            errors.append(f"OpenAI expiry checker has repository import path: {entry}")
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


def policy_fields(policy: Any, errors: list[str]) -> dict[str, Any]:
    if not isinstance(policy, dict):
        errors.append("OpenAI WIF policy is not an object")
        return {}
    try:
        observed = {
            "provider": policy["provider"],
            "issuer_url": policy["issuer"]["issuer_url"],
            "audience": policy["rule"]["audience"],
            "identity_provider_id": policy["issuer"]["id"],
            "service_account_id": policy["service_account"]["id"],
            "subject": policy["rule"]["subject"],
            "maximum_lifetime": policy["issuer"]["max_jwt_lifetime_seconds"],
            "factory_environment": policy["rule"]["claims"]["factory_environment"],
        }
    except (KeyError, TypeError):
        errors.append("OpenAI WIF policy lacks required fields")
        return {}
    expected = {
        "provider": "openai",
        "issuer_url": "https://factory.example.com/workload-identity",
        "audience": "https://api.openai.com",
        "identity_provider_id": "idp_DlzD7RlQXgXxd1VSG2V93eEU",
        "service_account_id": "user-6tzs2hdFVN7GoYQbWfC0eu7k",
        "subject": "patchyard-control-plane",
        "maximum_lifetime": 300,
        "factory_environment": "production",
    }
    if observed != expected:
        errors.append("OpenAI WIF policy fields differ from the expiry contract")
    return observed


def validate_assertion(
    value: Any, policy: dict[str, Any], errors: list[str]
) -> tuple[datetime | None, datetime | None, datetime | None]:
    if not exact_keys(value, ASSERTION_KEYS, "expired assertion descriptor", errors):
        return None, None, None
    if value.get("algorithm") != "RS256":
        errors.append("expired assertion algorithm differs")
    if value.get("kid_derived_from_public_der") is not True:
        errors.append("expired assertion key ID was not derived from public DER")
    for field, expected in (
        ("issuer", policy.get("issuer_url")),
        ("subject", policy.get("subject")),
        ("audience", policy.get("audience")),
        ("factory_environment", policy.get("factory_environment")),
    ):
        if value.get(field) != expected:
            errors.append(f"expired assertion {field} differs from policy")
    if value.get("lifetime_seconds") != 300:
        errors.append("expired assertion lifetime differs")
    if value.get("expired_before_mint_seconds") != 5:
        errors.append("assertion was not minted with exp already five seconds past")
    if value.get("jti_supplied") is not True:
        errors.append("expired assertion does not record a single-use JTI")
    if HEX64.fullmatch(str(value.get("jwk_thumbprint_sha256", ""))) is None:
        errors.append("expired assertion JWK thumbprint is malformed")
    issued = parse_time(value.get("issued_at"), "expired assertion issued_at", errors)
    minted = parse_time(value.get("minted_at"), "expired assertion minted_at", errors)
    expires = parse_time(value.get("expires_at"), "expired assertion expires_at", errors)
    if issued is not None and expires is not None:
        if int((expires - issued).total_seconds()) != 300:
            errors.append("expired assertion timestamps do not encode five minutes")
    if expires is not None and minted is not None:
        if int((minted - expires).total_seconds()) != 5:
            errors.append("assertion exp was not already past when minted")
    return issued, minted, expires


def validate_request(
    value: Any, policy: dict[str, Any], errors: list[str]
) -> datetime | None:
    if not exact_keys(value, REQUEST_KEYS, "expiry exchange request", errors):
        return None
    expected = {
        "endpoint": "https://auth.openai.com/oauth/token",
        "content_type": "application/json",
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "subject_token_supplied": True,
        "identity_provider_id": policy.get("identity_provider_id"),
        "service_account_id": policy.get("service_account_id"),
        "scope_supplied": False,
        "attempt_count": 1,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            errors.append(f"expiry exchange request {field} differs")
    return parse_time(value.get("requested_at"), "expiry exchange requested_at", errors)


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
        "expiry response shape",
        errors,
    ):
        return
    if value.get("body_kind") != body_format:
        errors.append("expiry body kind differs from its response shape")
    validate_field_descriptors(
        value.get("top_level_fields"), "top-level expiry response shape", errors
    )
    validate_field_descriptors(value.get("error_fields"), "expiry error shape", errors)


def validate_observed_response(
    value: Any, errors: list[str]
) -> tuple[datetime | None, datetime | None]:
    if not exact_keys(value, RESPONSE_KEYS, "expiry denial", errors):
        return None, None
    if value.get("source") != "openai_http_response":
        errors.append("expiry denial is not an OpenAI HTTP observation")
    status = value.get("http_status")
    if not valid_int(status) or not 100 <= status <= 599:
        errors.append("expiry denial HTTP status is malformed")
    requested = parse_time(value.get("request_started_at"), "expiry request start", errors)
    observed = parse_time(value.get("observed_at"), "expiry observed_at", errors)
    provider_date = value.get("provider_date")
    if provider_date is not None:
        parse_time(provider_date, "expiry provider date", errors)
    supplied = value.get("request_id_supplied")
    request_id = value.get("request_id")
    if supplied is not True and supplied is not False:
        errors.append("expiry request-ID presence is not boolean")
    if supplied is False and request_id is not None:
        errors.append("expiry response retained an absent request ID")
    if not safe_optional_string(request_id):
        errors.append("expiry request ID is not safely bounded")
    if not safe_optional_string(value.get("content_type")):
        errors.append("expiry content type is not safely bounded")
    body_bytes = value.get("body_bytes")
    if not valid_int(body_bytes) or not 0 <= body_bytes <= MAX_RESPONSE_BYTES:
        errors.append("expiry response byte count is outside the bound")
    body_format = value.get("body_format")
    allowed_formats = {"non_json"} | {
        f"json_{value_type}" for value_type in JSON_VALUE_TYPES
    }
    if body_format not in allowed_formats:
        errors.append("expiry response body format is malformed")
    validate_response_shape(value.get("response_shape"), body_format, errors)
    if value.get("access_token_supplied") not in {True, False}:
        errors.append("expiry access-token presence is not boolean")
    if not safe_optional_string(value.get("error_type")):
        errors.append("expiry error type is not safely bounded")
    if requested is not None and observed is not None and requested > observed:
        errors.append("expiry response was observed before its request")
    return requested, observed


def validate_unobserved_response(
    value: Any, errors: list[str]
) -> tuple[datetime | None, datetime | None]:
    if not exact_keys(value, RESPONSE_KEYS, "synthetic expiry response", errors):
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
        "error_type": None,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            errors.append(f"synthetic expiry response {field} invents an observation")
    requested = parse_time(
        value.get("request_started_at"), "synthetic expiry request start", errors
    )
    observed = parse_time(
        value.get("observed_at"), "synthetic expiry observed_at", errors
    )
    if requested is not None and observed is not None and requested > observed:
        errors.append("synthetic expiry response is out of order")
    return requested, observed


def validate_source(value: Any, errors: list[str]) -> None:
    if not exact_keys(value, SOURCE_KEYS, "OpenAI expiry source binding", errors):
        return
    accepted_adapter = {digest(EXPIRY_ADAPTER_PATH)}
    accepted_adapter.update(SUPERSEDES_SOURCE_SHA256["tools/openai-wif-expiry.py"])
    if (
        value.get("policy_sha256") != digest(POLICY_PATH)
        or value.get("base_harness_sha256") != digest(BASE_HARNESS_PATH)
        or value.get("expiry_adapter_sha256") not in accepted_adapter
    ):
        errors.append("OpenAI expiry source binding differs from current sources")


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
        errors.append(f"OpenAI expiry Result contains forbidden credential field: {forbidden}")
    serialized = json.dumps(value, sort_keys=True)
    if (
        JWT.search(serialized)
        or OPENAI_KEY.search(serialized)
        or BEARER.search(serialized)
        or PRIVATE_KEY.search(serialized)
    ):
        errors.append("OpenAI expiry Result carries credential-shaped material")
    return errors


def validate_common(result: Any, policy: dict[str, Any], *, synthetic: bool) -> list[str]:
    errors: list[str] = []
    expected_keys = RESULT_KEYS | (FIXTURE_KEYS if synthetic else set())
    if not exact_keys(result, expected_keys, "OpenAI expiry Result", errors):
        return errors
    if result.get("schema_version") != 1 or result.get("provider") != "openai":
        errors.append("OpenAI expiry Result identity differs")
    if result.get("qualification_requirement") != "credential-expiry-denial":
        errors.append("OpenAI expiry Result names the wrong requirement")
    if result.get("authorization_ruling") != "A131":
        errors.append("OpenAI expiry Result names the wrong authorization ruling")
    if result.get("observation_kind") != "expired-assertion-token-exchange":
        errors.append("OpenAI expiry Result has the wrong observation kind")
    if RUN_ID.fullmatch(str(result.get("run_id", ""))) is None:
        errors.append("OpenAI expiry Result run ID is malformed")
    started = parse_time(result.get("started_at"), "expiry started_at", errors)
    issued, minted, expires = validate_assertion(
        result.get("assertion_descriptor"), policy, errors
    )
    request_time = validate_request(result.get("exchange_request"), policy, errors)
    if synthetic:
        response_request, response_time = validate_unobserved_response(
            result.get("expiry_denial"), errors
        )
    else:
        response_request, response_time = validate_observed_response(
            result.get("expiry_denial"), errors
        )
    removed = parse_time(result.get("credential_removed_at"), "credential_removed_at", errors)
    if result.get("response_predicate") != RESPONSE_PREDICATE:
        errors.append("OpenAI expiry predicate was enforced before an observation")
    if result.get("control_plane_provenance") != CONTROL_PLANE_PROVENANCE:
        errors.append("OpenAI expiry Result misstates control-plane provenance")
    validate_source(result.get("source"), errors)
    if request_time is not None and response_request is not None:
        if request_time != response_request:
            errors.append("expiry request and response name different start times")
    # `minted_at` is deliberately absent from this chain. The frozen base
    # harness writes it at whole-second precision while every other stamp
    # carries microseconds, so a mint completing in the second it started
    # records as EARLIER than the start, and no real run can satisfy
    # `started <= minted`. The committed requirement 1 Result shows the
    # same inversion and is valid. This was an unsatisfiable constraint,
    # not a property of the run.
    ordered = [started, request_time, response_time, removed]
    if all(value is not None for value in ordered):
        assert all(isinstance(value, datetime) for value in ordered)
        if not all(left <= right for left, right in zip(ordered, ordered[1:])):
            errors.append("OpenAI expiry UTC observations are out of order")
    # Truncation moves minted earlier, so signed-before-sent stays sound at
    # second precision and is the one ordering minted genuinely contributed.
    if minted is not None and request_time is not None and minted > request_time:
        errors.append("expiry assertion was minted after the exchange request")
    if issued is not None and expires is not None and not issued < expires:
        errors.append("expired assertion issued_at is not before exp")
    if expires is not None and minted is not None and not expires < minted:
        errors.append("assertion exp was not already past at mint")
    if expires is not None and request_time is not None and not expires < request_time:
        errors.append("OpenAI expiry exchange did not use an already expired assertion")
    errors.extend(credential_errors(result))
    return errors


def validate_observation(result: Any, policy: dict[str, Any]) -> list[str]:
    if isinstance(result, dict) and result.get("status") == "in_progress":
        return ["in-progress OpenAI expiry record is inert"]
    if isinstance(result, dict) and result.get("status") == "failed":
        return ["failed OpenAI expiry record is not a provider observation"]
    errors = validate_common(result, policy, synthetic=False)
    if isinstance(result, dict):
        if result.get("provider_response_observed") is not True:
            errors.append("OpenAI expiry observation does not record a provider response")
        if result.get("qualification_evidence") is not False:
            errors.append("OpenAI expiry observation claims qualification")
    return errors


def validate_contract_fixture(result: Any, policy: dict[str, Any]) -> list[str]:
    errors = validate_common(result, policy, synthetic=True)
    if not isinstance(result, dict):
        return errors
    if result.get("fixture_kind") != "synthetic-openai-expiry-satisfiability":
        errors.append("OpenAI expiry Fixture kind differs")
    if result.get("fixture_lineage") != {
        "assertion_contract": "synthetic-expired-assertion",
        "provider_response": "unobserved-placeholder",
    }:
        errors.append("OpenAI expiry Fixture lineage differs")
    if result.get("provider_response_observed") is not False:
        errors.append("OpenAI expiry Fixture claims a provider response")
    if result.get("qualification_evidence") is not False:
        errors.append("OpenAI expiry Fixture claims qualification")
    return errors


def validate_qualification_evidence(result: Any, policy: dict[str, Any]) -> list[str]:
    if isinstance(result, dict) and result.get("fixture_kind") is not None:
        return ["synthetic OpenAI expiry Fixture cannot be qualification evidence"]
    errors = validate_observation(result, policy)
    errors.append("OpenAI expiry qualification predicate is unenforced pending observation")
    return errors


def static_errors() -> tuple[list[str], dict[str, Any]]:
    errors = isolation_errors()
    try:
        policy = load_json_file(POLICY_PATH)
    except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
        errors.append(f"cannot read OpenAI WIF policy: {error}")
        policy = {}
    fields = policy_fields(policy, errors)
    if POLICY_PATH.is_symlink() or not POLICY_PATH.is_file() or digest(POLICY_PATH) != POLICY_SHA256:
        errors.append("OpenAI WIF policy differs from its frozen binding")
    if (
        not BASE_HARNESS_PATH.is_file()
        or BASE_HARNESS_PATH.is_symlink()
        or digest(BASE_HARNESS_PATH) != BASE_HARNESS_SHA256
    ):
        errors.append("qualified lifecycle harness differs from its exact binding")
    if not EXPIRY_ADAPTER_PATH.is_file() or EXPIRY_ADAPTER_PATH.is_symlink():
        errors.append("OpenAI expiry adapter is missing or a symlink")
    else:
        adapter = EXPIRY_ADAPTER_PATH.read_text()
        for required in (
            "BASE_HARNESS_SHA256",
            "def load_base_harness()",
            "BASE.load_public_jwk(signing_key)",
            "issued_at = now_epoch - 305",
            "expires_at = now_epoch - 5",
            'TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"',
            '"attempt_count": 1',
            '"enforced": False',
            '"basis": "no-observed-openai-expired-assertion-response"',
            'urllib.request.ProxyHandler({})',
            "BASE.ReservedOutput",
        ):
            if required not in adapter:
                errors.append(f"OpenAI expiry adapter is missing: {required}")
    try:
        providers = load_json_file(PROVIDER_POLICY_PATH)["providers"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError, EvidenceJsonError) as error:
        errors.append(f"cannot read provider egress policy: {error}")
    else:
        if len(providers) != 13:
            errors.append("provider egress policy does not contain 13 providers")
    return errors, fields


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
                errors.append("OpenAI expiry checker accepts only one input mode")
            mode = argument.removeprefix("--")
            path = Path(arguments.pop(0))
        else:
            errors.append(f"unknown checker argument: {argument}")
    if allow_missing and (mode != "default" or path != RESULT_PATH):
        errors.append("allow-missing-results cannot be combined with supplied input")
    if not path.exists():
        if not allow_missing:
            errors.append("OpenAI expiry Result is missing")
    else:
        result = read_bounded_input(path, "OpenAI expiry input", errors)
        if result is not None:
            if mode == "contract-fixture":
                errors.extend(validate_contract_fixture(result, policy))
            elif mode == "evidence":
                errors.extend(validate_qualification_evidence(result, policy))
            else:
                errors.extend(validate_observation(result, policy))
    if errors:
        print("OpenAI WIF expiry check: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    if mode == "contract-fixture":
        status = "synthetic contract Fixture; not qualification evidence"
    elif path.exists():
        status = "with non-qualifying provider observation"
    else:
        status = "static preflight"
    print(f"OpenAI WIF expiry check: pass ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
