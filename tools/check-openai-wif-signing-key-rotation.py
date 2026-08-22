#!/usr/bin/env python3
"""Check an OpenAI signing-key rotation Result or contract Fixture."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import sysconfig
import types
from typing import Any


CHECKER_RUNTIME_PATH = Path(__file__).with_name("factory_checker_runtime.py")
CHECKER_RUNTIME_SHA256 = "fcd9d4c5513d8614e20dc4e2fada3da60326ff85745a989b3d4313497b0622f6"
_checker_runtime_source = CHECKER_RUNTIME_PATH.read_bytes()
if (
    CHECKER_RUNTIME_PATH.is_symlink()
    or hashlib.sha256(_checker_runtime_source).hexdigest()
    != CHECKER_RUNTIME_SHA256
):
    raise RuntimeError("factory checker runtime differs from its exact binding")
RUNTIME = types.ModuleType("factory_checker_runtime_check_openai_wif_signing_key_rotation")
RUNTIME.__file__ = str(CHECKER_RUNTIME_PATH)
RUNTIME.__package__ = None
exec(
    compile(
        _checker_runtime_source,
        str(CHECKER_RUNTIME_PATH),
        "exec",
        dont_inherit=True,
    ),
    RUNTIME.__dict__,
)


REPO = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO / "policy/openai-wif.json"
IDENTITY_HISTORY_PATH = REPO / "policy/openai-identity-history.json"
# A150: the id policy/openai-wif.json still names. Demoted by meaning to the
# account the banked Results were minted against; the live id is resolved from
# the identity registry. The frozen policy is not edited because every banked
# OpenAI Result pins its digest as policy_sha256.
ISSUANCE_ERA_SERVICE_ACCOUNT_ID = "user-6tzs2hdFVN7GoYQbWfC0eu7k"
BASE_HARNESS_PATH = REPO / "tools/anthropic-wif-lifecycle.py"
LIFECYCLE_INSTRUMENT_PATH = REPO / "tools/openai-wif-issuance.py"
ATTESTATION_DEFINITION_PATH = REPO / "tools/control-plane-attestation-v1.py"
COLLECTOR_PATH = REPO / "tools/openai-wif-signing-key-rotation.py"
RESULT_PATH = REPO / "research/isolation/results/openai-signing-key-rotation.json"
PROVIDER_POLICY_PATH = REPO / "policy/provider-egress.json"
POLICY_SHA256 = "87cf13bb136ed9a365bd14822a14d4808a6ef585ce1c278b926fa173d1152e5f"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
LIFECYCLE_INSTRUMENT_SHA256 = (
    "88117660a2717ecd2c9b6eef4704066700e4989e1010d508769bf928fec18c8b"
)
ATTESTATION_DEFINITION_SHA256 = "0d32e80b980c334977e51eb706783896a687d29faef46d50e53f3ee56e8e4d47"
# A144: the signing-identity split re-pointed the collector's key path (and the
# lifecycle instrument it embeds) without re-producing the banked Result, so
# the pre-split digests recorded there stay acceptable alongside the current
# bytes. The superseded files are named with the exact digests they replace.
SUPERSEDES_SOURCE_SHA256 = {
    "tools/openai-wif-signing-key-rotation.py": (
        "530df38bcaf7cd66eec6054c419665877adcd7dbb59fed50a42911091c447347",
    ),
    "tools/openai-wif-issuance.py": (
        "739396b9982218e909d933a74674cfc53c4ec76f7e202e08418a1d0910867923",
    ),
    "tools/check-openai-wif-signing-key-rotation.py": (
        "52eae885fd4d84be36252bc8566aea8664b173d54bef5e26cf594676866cc4e0",
    ),
}
ACCEPTED_LIFECYCLE_INSTRUMENT_SHA256 = frozenset(
    (LIFECYCLE_INSTRUMENT_SHA256,)
    + SUPERSEDES_SOURCE_SHA256["tools/openai-wif-issuance.py"]
)
# The banked Result's local activation ran before A144 moved the OpenAI tools
# to their own stable key path; both paths therefore validate.
ACCEPTED_ACTIVE_KEY_PATHS = frozenset(
    (
        "/etc/patchyard/openai-wif-signing.pem",
        "/etc/patchyard/anthropic-wif-signing.pem",
    )
)
RUN_ID = re.compile(r"openai-rotation-[0-9]{8}-[0-9a-f]{10}")
HEX64 = re.compile(r"[0-9a-f]{64}")
KID = re.compile(r"patchyard-[0-9a-f]{16}")
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
MAX_INPUT_BYTES = 3_000_000
MAX_RESPONSE_BYTES = 1_000_000
SETTLING_FLOOR_SECONDS = 90
OVERLAP_POSITIVE_MAX_ATTEMPTS = 4
UNOBSERVED_RESPONSE_PREDICATE = {
    "enforced": False,
    "basis": "no-observed-openai-retired-signing-key-response",
}
RESPONSE_PREDICATE = {
    "enforced": True,
    "http_status": 401,
    "access_token_supplied": False,
    "basis": "observed-openai-retired-signing-key-response",
}
RESULT_SHAPE = RUNTIME.result_shape("openai-signing-key-rotation")
RESULT_KEYS = RESULT_SHAPE.keys("result")
FIXTURE_KEYS = RESULT_SHAPE.keys("fixture")
WINDOW_KEYS = RESULT_SHAPE.keys("window")
READING_KEYS = RESULT_SHAPE.keys("reading")
ROTATION_STATE_KEYS = RESULT_SHAPE.keys("rotation_state")
PUBLIC_KEY_KEYS = RESULT_SHAPE.keys("public_key")
DERIVED_KEYS = RESULT_SHAPE.keys("derived")
DESCRIPTOR_KEYS = RESULT_SHAPE.keys("descriptor")
EXCHANGE_KEYS = RESULT_SHAPE.keys("exchange")
ASSERTION_KEYS = RESULT_SHAPE.keys("assertion")
REQUEST_KEYS = RESULT_SHAPE.keys("request")
RECEIPT_KEYS = RESULT_SHAPE.keys("receipt")
RESPONSE_SHAPE_KEYS = RESULT_SHAPE.keys("response_shape")
FIELD_DESCRIPTOR_KEYS = RESULT_SHAPE.keys("field_descriptor")
JSON_VALUE_TYPES = {"null", "boolean", "integer", "number", "string", "object", "array"}
ACTIVATION_KEYS = RESULT_SHAPE.keys("activation")
BRACKET_KEYS = RESULT_SHAPE.keys("bracket")
SOURCE_KEYS = RESULT_SHAPE.keys("source")


CHECKER = RUNTIME.checker_runtime(
    identity="OpenAI signing-key-rotation checker",
    modules=(hashlib, json, re, sysconfig, types),
    repo=REPO,
    timestamp_pattern=UTC_TIMESTAMP,
    secret_names=frozenset({"secret", "access_token", "assertion", "subject_token", "identity_token", "authorization", "private_key", "api_key"}),
    identity_history_path=IDENTITY_HISTORY_PATH,
    issuance_era_service_account_id=ISSUANCE_ERA_SERVICE_ACCOUNT_ID,
)
EvidenceJsonError = RUNTIME.EvidenceJsonError
digest = RUNTIME.digest
load_json_file = CHECKER.load_json_file
reject_json_constant = CHECKER.reject_json_constant
reject_duplicate_keys = CHECKER.reject_duplicate_keys
roster_service_account_ids = CHECKER.roster_service_account_ids
is_within = RUNTIME.is_within
isolation_errors = CHECKER.isolation_errors
exact_keys = RUNTIME.exact_keys
parse_time = CHECKER.parse_time
secret_named_key = CHECKER.secret_named_key

def load_attestation_definition(errors: list[str]) -> types.ModuleType | None:
    try:
        source = ATTESTATION_DEFINITION_PATH.read_bytes()
    except OSError as error:
        errors.append(f"cannot read Attestation definition: {error}")
        return None
    observed = hashlib.sha256(source).hexdigest()
    if ATTESTATION_DEFINITION_PATH.is_symlink() or observed != ATTESTATION_DEFINITION_SHA256:
        errors.append(
            "Attestation definition digest differs: expected "
            f"{ATTESTATION_DEFINITION_SHA256}, observed {observed}"
        )
        return None
    module = types.ModuleType("control_plane_attestation_v1_rotation_checker")
    module.__file__ = str(ATTESTATION_DEFINITION_PATH)
    module.__package__ = None
    exec(
        compile(source, str(ATTESTATION_DEFINITION_PATH), "exec", dont_inherit=True),
        module.__dict__,
    )
    return module


def valid_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def same_json_value(observed: Any, expected: Any) -> bool:
    return type(observed) is type(expected) and observed == expected


def safe_optional_string(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and SAFE_RESPONSE_STRING.fullmatch(value) is not None
    )


def bounded_console_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 1024
        and all(character.isprintable() for character in value)
    )


def policy_fields(policy: Any, errors: list[str]) -> dict[str, Any]:
    try:
        fields = {
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
        "service_account_id": ISSUANCE_ERA_SERVICE_ACCOUNT_ID,
        "subject": "patchyard-control-plane",
        "maximum_lifetime": 300,
        "factory_environment": "production",
    }
    if fields != expected:
        errors.append("OpenAI WIF policy differs from the signing-key-rotation contract")
    return fields


def validate_field_descriptors(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{label} is not a list")
        return
    names: list[str] = []
    for item in value:
        if not exact_keys(item, FIELD_DESCRIPTOR_KEYS, f"{label} field", errors):
            continue
        if item.get("name_recorded") is True:
            name = item.get("name")
            if not isinstance(name, str) or SAFE_FIELD_NAME.fullmatch(name) is None:
                errors.append(f"{label} has an unsafe recorded field name")
            else:
                names.append(name)
        elif item.get("name_recorded") is False:
            if item.get("name") is not None:
                errors.append(f"{label} retained an unsafe field name")
        else:
            errors.append(f"{label} field-name provenance is not boolean")
        if item.get("value_type") not in JSON_VALUE_TYPES:
            errors.append(f"{label} has an unknown JSON value type")
    if names != sorted(names) or len(names) != len(set(names)):
        errors.append(f"{label} field names are not unique and sorted")


def validate_receipt(
    value: Any, label: str, errors: list[str], *, synthetic: bool
) -> tuple[datetime | None, datetime | None]:
    if not exact_keys(value, RECEIPT_KEYS, label, errors):
        return None, None
    requested = parse_time(value.get("request_started_at"), f"{label} request start", errors)
    observed = parse_time(value.get("observed_at"), f"{label} observed_at", errors)
    if requested is not None and observed is not None and requested > observed:
        errors.append(f"{label} was observed before its request")
    if synthetic:
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
            "token_type": None,
            "expires_in": None,
            "error_type": None,
        }
        for field, expected_value in expected.items():
            if not same_json_value(value.get(field), expected_value):
                errors.append(f"{label} invents an unobserved response field: {field}")
    else:
        if value.get("source") != "openai_http_response":
            errors.append(f"{label} is not an OpenAI Receipt")
        status = value.get("http_status")
        if not valid_int(status) or not 100 <= status <= 599:
            errors.append(f"{label} HTTP status is malformed")
        provider_date = value.get("provider_date")
        if provider_date is not None:
            parse_time(provider_date, f"{label} provider date", errors)
        if type(value.get("request_id_supplied")) is not bool:
            errors.append(f"{label} request-ID presence is not boolean")
        if value.get("request_id_supplied") is False and value.get("request_id") is not None:
            errors.append(f"{label} retained an absent request ID")
        if not safe_optional_string(value.get("request_id")):
            errors.append(f"{label} request ID is not safely bounded")
        if not safe_optional_string(value.get("content_type")):
            errors.append(f"{label} content type is not safely bounded")
        body_bytes = value.get("body_bytes")
        if not valid_int(body_bytes) or not 0 <= body_bytes <= MAX_RESPONSE_BYTES:
            errors.append(f"{label} byte count is outside the bound")
        allowed_formats = {"non_json"} | {
            f"json_{kind}" for kind in JSON_VALUE_TYPES
        }
        if value.get("body_format") not in allowed_formats:
            errors.append(f"{label} body format is malformed")
        shape = value.get("response_shape")
        if exact_keys(shape, RESPONSE_SHAPE_KEYS, f"{label} response shape", errors):
            if shape.get("body_kind") != value.get("body_format"):
                errors.append(f"{label} body kind differs")
            validate_field_descriptors(
                shape.get("top_level_fields"), f"{label} top-level shape", errors
            )
            validate_field_descriptors(
                shape.get("error_fields"), f"{label} error shape", errors
            )
        if not safe_optional_string(value.get("token_type")):
            errors.append(f"{label} token type is not safely bounded")
        expires = value.get("expires_in")
        if expires is not None and not valid_int(expires):
            errors.append(f"{label} expires_in is malformed")
        if not safe_optional_string(value.get("error_type")):
            errors.append(f"{label} error type is not safely bounded")
    if type(value.get("access_token_supplied")) is not bool:
        errors.append(f"{label} bearer presence is not boolean")
    return requested, observed


def validate_exchange(
    value: Any,
    label: str,
    expected_role: str,
    policy: dict[str, Any],
    errors: list[str],
    *,
    synthetic: bool,
    positive: bool,
    max_attempts: int = 1,
) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    if not exact_keys(value, EXCHANGE_KEYS, label, errors):
        return facts
    if value.get("key_role") != expected_role:
        errors.append(f"{label} key role differs")
    attempt_count = value.get("attempt_count")
    if not valid_int(attempt_count) or not 1 <= attempt_count <= max_attempts:
        if max_attempts == 1:
            errors.append(f"{label} was not exactly one attempt")
        else:
            errors.append(
                f"{label} attempt count is outside the bounded retry"
            )
    if value.get("lifecycle_instrument_sha256") not in ACCEPTED_LIFECYCLE_INSTRUMENT_SHA256:
        errors.append(f"{label} lifecycle instrument differs")
    started = parse_time(value.get("started_at"), f"{label} started_at", errors)
    assertion = value.get("assertion_descriptor")
    issued = minted = expires = None
    if exact_keys(assertion, ASSERTION_KEYS, f"{label} assertion", errors):
        expected_assertion = {
            "algorithm": "RS256",
            "issuer": policy.get("issuer_url"),
            "subject": policy.get("subject"),
            "audience": policy.get("audience"),
            "lifetime_seconds": 300,
            "jti_supplied": True,
            "factory_environment": policy.get("factory_environment"),
        }
        for field, expected in expected_assertion.items():
            if not same_json_value(assertion.get(field), expected):
                errors.append(f"{label} assertion {field} differs")
        if KID.fullmatch(str(assertion.get("kid", ""))) is None:
            errors.append(f"{label} key identifier was not derived from public DER")
        if HEX64.fullmatch(str(assertion.get("jwk_thumbprint_sha256", ""))) is None:
            errors.append(f"{label} JWK thumbprint is malformed")
        issued = parse_time(assertion.get("issued_at"), f"{label} issued_at", errors)
        minted = parse_time(assertion.get("minted_at"), f"{label} minted_at", errors)
        expires = parse_time(assertion.get("expires_at"), f"{label} expires_at", errors)
        if issued is not None and expires is not None and int(
            (expires - issued).total_seconds()
        ) != 300:
            errors.append(f"{label} assertion timestamps do not encode five minutes")
    request = value.get("exchange_request")
    request_time = None
    if exact_keys(request, REQUEST_KEYS, f"{label} request", errors):
        expected_request = {
            "endpoint": "https://auth.openai.com/oauth/token",
            "content_type": "application/json",
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
            "subject_token_supplied": True,
            "identity_provider_id": policy.get("identity_provider_id"),
            "scope_supplied": False,
        }
        for field, expected in expected_request.items():
            if not same_json_value(request.get(field), expected):
                errors.append(f"{label} request {field} differs")
        # A150: roster membership, not equality with the frozen policy's
        # demoted id.
        if request.get("service_account_id") not in roster_service_account_ids(errors):
            errors.append(f"{label} request service_account_id is not rostered")
        request_time = parse_time(
            request.get("requested_at"), f"{label} requested_at", errors
        )
    receipt_request, receipt_time = validate_receipt(
        value.get("receipt"), f"{label} Receipt", errors, synthetic=synthetic
    )
    removed = parse_time(
        value.get("credential_removed_at"), f"{label} credential_removed_at", errors
    )
    if request_time is not None and receipt_request is not None and request_time != receipt_request:
        errors.append(f"{label} request and Receipt name different start times")
    ordered = [started, request_time, receipt_time, removed]
    if all(item is not None for item in ordered) and not all(
        left <= right for left, right in zip(ordered, ordered[1:])
    ):
        errors.append(f"{label} UTC observations are out of order")
    # The frozen instrument writes minted_at at whole-second precision. Do not
    # compare it to a microsecond started_at; retain only signed-before-sent.
    if minted is not None and request_time is not None and minted > request_time:
        errors.append(f"{label} assertion was minted after its request")
    if issued is not None and expires is not None and not issued < expires:
        errors.append(f"{label} assertion issued_at is not before expires_at")
    if positive and isinstance(value.get("receipt"), dict) and value["receipt"].get(
        "access_token_supplied"
    ) is not True:
        errors.append(f"{label} did not supply a bearer")
    if (
        not positive
        and not synthetic
        and isinstance(value.get("receipt"), dict)
    ):
        receipt = value["receipt"]
        if receipt.get("http_status") != RESPONSE_PREDICATE["http_status"]:
            errors.append(f"{label} was not HTTP 401")
        if receipt.get("access_token_supplied") is not False:
            errors.append(f"{label} supplied a bearer")
    facts.update(
        {
            "started": started,
            "request_time": request_time,
            "receipt_time": receipt_time,
            "removed": removed,
            "surface": {
                key: request.get(key) if isinstance(request, dict) else None
                for key in REQUEST_KEYS - {"requested_at"}
            },
            "descriptor": {
                "kid": assertion.get("kid") if isinstance(assertion, dict) else None,
                "jwk_thumbprint_sha256": (
                    assertion.get("jwk_thumbprint_sha256")
                    if isinstance(assertion, dict)
                    else None
                ),
            },
        }
    )
    return facts


def validate_descriptor(value: Any, label: str, errors: list[str], *, enabled: bool) -> dict[str, Any]:
    expected_keys = PUBLIC_KEY_KEYS if enabled else DESCRIPTOR_KEYS
    if not exact_keys(value, expected_keys, label, errors):
        return {}
    if KID.fullmatch(str(value.get("kid", ""))) is None:
        errors.append(f"{label} key identifier was not derived")
    if HEX64.fullmatch(str(value.get("jwk_thumbprint_sha256", ""))) is None:
        errors.append(f"{label} thumbprint is malformed")
    if enabled and value.get("enabled") is not True:
        errors.append(f"{label} is not enabled")
    return {
        "kid": value.get("kid"),
        "jwk_thumbprint_sha256": value.get("jwk_thumbprint_sha256"),
    }


def validate_rotation_state(
    value: Any, policy: dict[str, Any], label: str, errors: list[str]
) -> list[dict[str, Any]]:
    if not exact_keys(value, ROTATION_STATE_KEYS, label, errors):
        return []
    if value.get("identity_provider_id") != policy.get("identity_provider_id"):
        errors.append(f"{label} names another provider identity")
    if value.get("uploaded_jwks_mode") is not True:
        errors.append(f"{label} is not uploaded-JWKS mode")
    if value.get("subject_mapping_enabled") is not True:
        errors.append(f"{label} subject mapping is not enabled")
    if value.get("mapped_service_account_id") not in roster_service_account_ids(errors):
        errors.append(f"{label} maps an unrostered service account")
    for field in ("subject_mapping_expression", "console_location"):
        item = value.get(field)
        if not bounded_console_text(item):
            errors.append(f"{label} {field} is not bounded")
    keys = value.get("public_keys")
    if not isinstance(keys, list) or not 1 <= len(keys) <= 2:
        errors.append(f"{label} public-key membership is not one or two keys")
        return []
    descriptors = [
        validate_descriptor(item, f"{label} public key", errors, enabled=True)
        for item in keys
    ]
    if descriptors != sorted(
        descriptors, key=lambda item: (str(item.get("kid")), str(item.get("jwk_thumbprint_sha256")))
    ) or len({(item.get("kid"), item.get("jwk_thumbprint_sha256")) for item in descriptors}) != len(
        descriptors
    ):
        errors.append(f"{label} public-key membership is not unique and sorted")
    return descriptors


def validate_reading(
    value: Any, policy: dict[str, Any], label: str, errors: list[str]
) -> tuple[datetime | None, datetime | None, dict[str, Any], list[dict[str, Any]]]:
    if not exact_keys(value, READING_KEYS, label, errors):
        return None, None, {}, []
    before = parse_time(value.get("captured_before_at"), f"{label} captured_before_at", errors)
    after = parse_time(value.get("captured_after_at"), f"{label} captured_after_at", errors)
    if before is not None and after is not None and before > after:
        errors.append(f"{label} UTC bounds are out of order")
    state = value.get("state")
    descriptors = validate_rotation_state(state, policy, f"{label} state", errors)
    return before, after, state if isinstance(state, dict) else {}, descriptors


def state_without_location(state: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in state.items() if key != "console_location"}


def validate_activation(
    value: Any,
    original: dict[str, Any],
    replacement: dict[str, Any],
    errors: list[str],
) -> datetime | None:
    if not exact_keys(value, ACTIVATION_KEYS, "local activation", errors):
        return None
    if value.get("source") != "local_atomic_key_activation":
        errors.append("local activation source differs")
    if value.get("active_key_path") not in ACCEPTED_ACTIVE_KEY_PATHS:
        errors.append("local activation used another stable key path")
    if value.get("original_key") != original:
        errors.append("local activation original key differs")
    if value.get("replacement_key") != replacement:
        errors.append("local activation replacement key differs")
    if value.get("original_key_preserved_in_root_tmpfs") is not True:
        errors.append("local activation did not preserve the original in root tmpfs")
    if value.get("base_harness_sha256") != BASE_HARNESS_SHA256:
        errors.append("local activation base harness differs")
    return parse_time(value.get("observed_at"), "local activation observed_at", errors)


def validate_source(value: Any, errors: list[str]) -> None:
    if not exact_keys(value, SOURCE_KEYS, "signing-key-rotation source", errors):
        return
    accepted = {
        "policy_sha256": {digest(POLICY_PATH)},
        "base_harness_sha256": {digest(BASE_HARNESS_PATH)},
        "lifecycle_instrument_sha256": {digest(LIFECYCLE_INSTRUMENT_PATH)}
        | set(SUPERSEDES_SOURCE_SHA256["tools/openai-wif-issuance.py"]),
        "attestation_definition_sha256": {digest(ATTESTATION_DEFINITION_PATH)},
        "collector_sha256": {digest(COLLECTOR_PATH)}
        | set(SUPERSEDES_SOURCE_SHA256["tools/openai-wif-signing-key-rotation.py"]),
        "checker_sha256": {digest(Path(__file__).resolve())}
        | set(
            SUPERSEDES_SOURCE_SHA256["tools/check-openai-wif-signing-key-rotation.py"]
        ),
    }
    for field, acceptable in accepted.items():
        supplied = value.get(field)
        if supplied not in acceptable:
            errors.append(
                f"signing-key-rotation {field} differs: expected {supplied}, observed {sorted(acceptable)}"
            )


def credential_errors(value: Any) -> list[str]:
    errors: list[str] = []
    forbidden = secret_named_key(value)
    if forbidden is not None:
        errors.append(
            "OpenAI signing-key-rotation Result contains forbidden credential field: "
            f"{forbidden}"
        )
    serialized = json.dumps(value, sort_keys=True)
    if JWT.search(serialized) or OPENAI_KEY.search(serialized) or BEARER.search(
        serialized
    ) or PRIVATE_KEY.search(serialized):
        errors.append("OpenAI signing-key-rotation Result carries credential-shaped material")
    return errors


def validate_common(
    result: Any,
    policy: dict[str, Any],
    attestation: types.ModuleType,
    *,
    synthetic: bool,
) -> list[str]:
    errors: list[str] = []
    expected_keys = RESULT_KEYS | (FIXTURE_KEYS if synthetic else set())
    if not exact_keys(result, expected_keys, "OpenAI signing-key-rotation Result", errors):
        return errors
    if (
        not valid_int(result.get("schema_version"))
        or result.get("schema_version") != 1
        or result.get("provider") != "openai"
    ):
        errors.append("OpenAI signing-key-rotation Result identity differs")
    if result.get("qualification_requirement") != "signing-key-rotation":
        errors.append("OpenAI signing-key-rotation Result names another Requirement")
    if result.get("authorization_rulings") != ["A129", "A132", "A133", "A136"]:
        errors.append("OpenAI signing-key-rotation authorization rulings differ")
    if result.get("observation_kind") != "signing-key-rotation":
        errors.append("OpenAI signing-key-rotation observation kind differs")
    if RUN_ID.fullmatch(str(result.get("run_id", ""))) is None:
        errors.append("OpenAI signing-key-rotation run ID is malformed")
    window = result.get("bounded_window")
    window_start = window_end = None
    if exact_keys(window, WINDOW_KEYS, "signing-key-rotation bounded window", errors):
        window_start = parse_time(window.get("started_at"), "bounded window start", errors)
        window_end = parse_time(window.get("ended_at"), "bounded window end", errors)
        if window_start is not None and window_end is not None and window_start > window_end:
            errors.append("signing-key-rotation bounded window is reversed")

    descriptors = result.get("derived_public_key_descriptors")
    original_descriptor = replacement_descriptor = {}
    if exact_keys(descriptors, DERIVED_KEYS, "derived public-key descriptors", errors):
        original_descriptor = validate_descriptor(
            descriptors.get("original"), "derived original key", errors, enabled=False
        )
        replacement_descriptor = validate_descriptor(
            descriptors.get("replacement"), "derived replacement key", errors, enabled=False
        )
        if original_descriptor == replacement_descriptor:
            errors.append("derived replacement key is not distinct")
    original_before, original_after, original_state, original_keys = validate_reading(
        result.get("original_console_reading"),
        policy,
        "original console reading",
        errors,
    )
    if original_keys and original_keys != [original_descriptor]:
        errors.append("original console reading does not show only the derived original key")

    baseline = validate_exchange(
        result.get("baseline_control"),
        "baseline control",
        "original_active",
        policy,
        errors,
        synthetic=synthetic,
        positive=True,
    )
    overlap_positive = validate_exchange(
        result.get("overlap_positive_control"),
        "overlap positive control",
        "replacement_staging",
        policy,
        errors,
        synthetic=synthetic,
        positive=True,
        max_attempts=OVERLAP_POSITIVE_MAX_ATTEMPTS,
    )

    overlap = result.get("overlap_attestation")
    retirement = result.get("retirement_attestation")
    for value, label in (
        (overlap, "overlap Attestation"),
        (retirement, "retirement Attestation"),
    ):
        # The frozen attestation definition accepts exactly one instrument
        # digest, so resolve the A144-accepted digest first: the recorded
        # value when it is an accepted one, else the current binding, which
        # keeps the definition's own rejection message for anything else.
        recorded = value.get("lifecycle_instrument_sha256") if isinstance(
            value, dict
        ) else None
        expected_instrument = (
            recorded
            if recorded in ACCEPTED_LIFECYCLE_INSTRUMENT_SHA256
            else LIFECYCLE_INSTRUMENT_SHA256
        )
        for error in attestation.validate_attestation(
            value, expected_instrument
        ):
            errors.append(f"{label}: {error}")
    overlap_before_started = overlap_before_ended = None
    overlap_after_started = overlap_after_ended = None
    retirement_before_started = retirement_before_ended = None
    retirement_after_started = retirement_after_ended = None
    overlap_before_state = overlap_after_state = {}
    retirement_before_state = retirement_after_state = {}
    overlap_before_keys: list[dict[str, Any]] = []
    overlap_after_keys: list[dict[str, Any]] = []
    retirement_before_keys: list[dict[str, Any]] = []
    retirement_after_keys: list[dict[str, Any]] = []
    if isinstance(overlap, dict) and isinstance(overlap.get("console_readings"), dict):
        (
            overlap_before_started,
            overlap_before_ended,
            overlap_before_state,
            overlap_before_keys,
        ) = validate_reading(
            overlap["console_readings"].get("before"),
            policy,
            "overlap before reading",
            errors,
        )
        (
            overlap_after_started,
            overlap_after_ended,
            overlap_after_state,
            overlap_after_keys,
        ) = validate_reading(
            overlap["console_readings"].get("after"),
            policy,
            "overlap after reading",
            errors,
        )
    if isinstance(retirement, dict) and isinstance(retirement.get("console_readings"), dict):
        (
            retirement_before_started,
            retirement_before_ended,
            retirement_before_state,
            retirement_before_keys,
        ) = validate_reading(
            retirement["console_readings"].get("before"),
            policy,
            "retirement before reading",
            errors,
        )
        (
            retirement_after_started,
            retirement_after_ended,
            retirement_after_state,
            retirement_after_keys,
        ) = validate_reading(
            retirement["console_readings"].get("after"),
            policy,
            "retirement after reading",
            errors,
        )
    expected_overlap = sorted(
        [original_descriptor, replacement_descriptor],
        key=lambda item: (str(item.get("kid")), str(item.get("jwk_thumbprint_sha256"))),
    )
    if original_state and overlap_before_state and state_without_location(
        original_state
    ) != state_without_location(overlap_before_state):
        errors.append("key membership changed before overlap")
    if overlap_before_keys and overlap_before_keys != [original_descriptor]:
        errors.append("overlap before reading is not the original one-key state")
    if overlap_after_keys and overlap_after_keys != expected_overlap:
        errors.append("overlap Attestation does not show both derived public keys")
    if overlap_after_state and retirement_before_state and state_without_location(
        overlap_after_state
    ) != state_without_location(retirement_before_state):
        errors.append("key membership changed before retirement")
    if retirement_before_keys and retirement_before_keys != expected_overlap:
        errors.append("retirement before reading is not the two-key overlap")
    if retirement_after_keys and retirement_after_keys != [replacement_descriptor]:
        errors.append("retirement Attestation does not leave only the replacement key")
    if original_state and retirement_after_state:
        for field in (
            "identity_provider_id",
            "uploaded_jwks_mode",
            "subject_mapping_expression",
            "mapped_service_account_id",
            "subject_mapping_enabled",
        ):
            if original_state.get(field) != retirement_after_state.get(field):
                errors.append(f"rotation changed non-key console field: {field}")
    if isinstance(overlap, dict) and isinstance(retirement, dict):
        for field in ("actor", "attester", "party_relationship"):
            if overlap.get(field) != retirement.get(field):
                errors.append(f"Attestations name different {field}")

    activation_time = validate_activation(
        result.get("local_activation"),
        original_descriptor,
        replacement_descriptor,
        errors,
    )
    bracket = result.get("a129_bracket")
    subwindow_start = subwindow_end = None
    before_denial = denial = after_denial = {}
    if exact_keys(bracket, BRACKET_KEYS, "A129 bracket", errors):
        subwindow = bracket.get("bounded_subwindow")
        if exact_keys(subwindow, WINDOW_KEYS, "A129 bounded subwindow", errors):
            subwindow_start = parse_time(
                subwindow.get("started_at"), "A129 subwindow start", errors
            )
            subwindow_end = parse_time(
                subwindow.get("ended_at"), "A129 subwindow end", errors
            )
        before_denial = validate_exchange(
            bracket.get("bracketing_control_before_denial"),
            "bracketing control before denial",
            "replacement_active",
            policy,
            errors,
            synthetic=synthetic,
            positive=True,
        )
        denial = validate_exchange(
            bracket.get("denial_observation"),
            "retired-key denial observation",
            "original_retired",
            policy,
            errors,
            synthetic=synthetic,
            positive=False,
        )
        after_denial = validate_exchange(
            bracket.get("bracketing_control_after_denial"),
            "bracketing control after denial",
            "replacement_active",
            policy,
            errors,
            synthetic=synthetic,
            positive=True,
        )

    exchanges = [baseline, overlap_positive, before_denial, denial, after_denial]
    if all(item.get("surface") for item in exchanges) and not all(
        item["surface"] == exchanges[0]["surface"] for item in exchanges[1:]
    ):
        errors.append("rotation exchanges do not use one token-exchange surface")
    expected_event_descriptors = [
        original_descriptor,
        replacement_descriptor,
        replacement_descriptor,
        original_descriptor,
        replacement_descriptor,
    ]
    for fact, expected, label in zip(
        exchanges,
        expected_event_descriptors,
        (
            "baseline control",
            "overlap positive control",
            "bracketing control before denial",
            "retired-key denial observation",
            "bracketing control after denial",
        ),
    ):
        if fact.get("descriptor") and fact["descriptor"] != expected:
            errors.append(f"{label} used another derived key")

    if overlap_after_ended is not None and overlap_positive.get("request_time") is not None:
        if (
            overlap_positive["request_time"] - overlap_after_ended
        ).total_seconds() < SETTLING_FLOOR_SECONDS:
            errors.append("overlap positive falls inside the 90-second settling floor")
    if retirement_after_ended is not None:
        for fact, label in (
            (before_denial, "first bracketing control"),
            (denial, "denial attempt"),
        ):
            if fact.get("request_time") is not None and (
                fact["request_time"] - retirement_after_ended
            ).total_seconds() < SETTLING_FLOOR_SECONDS:
                errors.append(f"{label} falls inside the 90-second settling floor")

    sequence = [
        window_start,
        original_before,
        original_after,
        baseline.get("started"),
        baseline.get("removed"),
        overlap_before_started,
        overlap_before_ended,
        overlap_after_started,
        overlap_after_ended,
        overlap_positive.get("started"),
        overlap_positive.get("removed"),
        activation_time,
        retirement_before_started,
        retirement_before_ended,
        retirement_after_started,
        retirement_after_ended,
        subwindow_start,
        before_denial.get("started"),
        before_denial.get("removed"),
        denial.get("started"),
        denial.get("removed"),
        after_denial.get("started"),
        after_denial.get("removed"),
        subwindow_end,
        window_end,
    ]
    if all(item is not None for item in sequence) and not all(
        left <= right for left, right in zip(sequence, sequence[1:])
    ):
        errors.append("signing-key-rotation UTC observations are out of order")
    expected_predicate = (
        UNOBSERVED_RESPONSE_PREDICATE if synthetic else RESPONSE_PREDICATE
    )
    if result.get("response_predicate") != expected_predicate:
        if synthetic:
            errors.append("signing-key-rotation predicate was enforced before observation")
        else:
            errors.append(
                "signing-key-rotation predicate does not match the reviewed retired-key denial"
            )
    if result.get("mutation_receipt_obtained") is not False:
        errors.append("signing-key-rotation Result provenance mark differs")
    validate_source(result.get("source"), errors)
    errors.extend(credential_errors(result))
    return errors


def validate_observation(
    result: Any, policy: dict[str, Any], attestation: types.ModuleType
) -> list[str]:
    if isinstance(result, dict) and result.get("status") in {"in_progress", "failed"}:
        return ["non-terminal signing-key-rotation record is not a Result"]
    errors = validate_common(result, policy, attestation, synthetic=False)
    if isinstance(result, dict):
        if result.get("provider_response_observed") is not True:
            errors.append("signing-key-rotation observation lacks provider responses")
        if result.get("qualification_evidence") not in {True, False}:
            errors.append("signing-key-rotation qualification_evidence is not boolean")
    return errors


def validate_contract_fixture(
    result: Any, policy: dict[str, Any], attestation: types.ModuleType
) -> list[str]:
    errors = validate_common(result, policy, attestation, synthetic=True)
    if not isinstance(result, dict):
        return errors
    if result.get("fixture_kind") != "synthetic-openai-signing-key-rotation-satisfiability":
        errors.append("signing-key-rotation Fixture kind differs")
    if result.get("fixture_lineage") != {
        "console_readings": "synthetic-bounded-operator-input",
        "provider_responses": "unobserved-placeholders",
        "key_material": "synthetic-public-descriptors-only",
    }:
        errors.append("signing-key-rotation Fixture lineage differs")
    if result.get("provider_response_observed") is not False:
        errors.append("signing-key-rotation Fixture claims a provider response")
    if result.get("qualification_evidence") is not False:
        errors.append("signing-key-rotation Fixture claims qualification")
    return errors


def validate_qualification_evidence(
    result: Any, policy: dict[str, Any], attestation: types.ModuleType
) -> list[str]:
    if isinstance(result, dict) and result.get("fixture_kind") is not None:
        return ["synthetic signing-key-rotation Fixture cannot be qualification evidence"]
    errors = validate_observation(result, policy, attestation)
    if isinstance(result, dict) and result.get("qualification_evidence") is not True:
        errors.append("signing-key-rotation Result is not qualification evidence")
    return errors


def static_errors() -> tuple[list[str], dict[str, Any], types.ModuleType | None]:
    errors = isolation_errors()
    # A150: the identity registry is gated on every CI cycle, not only when
    # a Result is present, so a roster that lost its current or issuance-era
    # entry fails closed here.
    roster_service_account_ids(errors)
    attestation = load_attestation_definition(errors) if not errors else None
    try:
        policy = load_json_file(POLICY_PATH)
    except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
        errors.append(f"cannot read OpenAI WIF policy: {error}")
        policy = {}
    fields = policy_fields(policy, errors)
    for path, expected, label in (
        (POLICY_PATH, POLICY_SHA256, "OpenAI WIF policy"),
        (BASE_HARNESS_PATH, BASE_HARNESS_SHA256, "base lifecycle harness"),
        (
            LIFECYCLE_INSTRUMENT_PATH,
            LIFECYCLE_INSTRUMENT_SHA256,
            "OpenAI lifecycle instrument",
        ),
    ):
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            errors.append(f"{label} differs from its exact binding")
    if not COLLECTOR_PATH.is_file() or COLLECTOR_PATH.is_symlink():
        errors.append("OpenAI signing-key-rotation collector is missing or a symlink")
    else:
        source = COLLECTOR_PATH.read_text()
        for required in (
            "LIFECYCLE_INSTRUMENT_SHA256",
            "ATTESTATION_DEFINITION_SHA256",
            "def load_exact_source(",
            '"OVERLAP COMPLETE"',
            '"RETIREMENT COMPLETE"',
            '"ACTIVATE LOCALLY"',
            '"SAFE ROLLBACK COMPLETE"',
            "def capture_safe_rotation_rollback(",
            '"observed-openai-retired-signing-key-response"',
            "rsa_keygen_bits:3072",
            "SETTLING_FLOOR_SECONDS = 90",
            "OVERLAP_POSITIVE_MAX_ATTEMPTS = 4",
            "def overlap_positive_with_retry(",
        ):
            if required not in source:
                errors.append(f"signing-key-rotation collector is missing: {required}")
    try:
        providers = load_json_file(PROVIDER_POLICY_PATH)["providers"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError, EvidenceJsonError) as error:
        errors.append(f"cannot read provider egress policy: {error}")
    else:
        if len(providers) != 13:
            errors.append("provider egress policy does not contain 13 providers")
    return errors, fields, attestation


def read_bounded_input(path: Path, label: str, errors: list[str]) -> Any:
    try:
        if not path.is_file() or path.is_symlink():
            raise EvidenceJsonError(f"{label} is not a regular non-symlink file")
        if not 1 <= path.stat().st_size <= MAX_INPUT_BYTES:
            raise EvidenceJsonError(f"{label} is outside the byte limit")
        return load_json_file(path)
    except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
        errors.append(f"cannot read {label}: {error}")
        return None


def main() -> int:
    errors, policy, attestation = static_errors()
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
                errors.append("signing-key-rotation checker accepts only one input mode")
            mode = argument.removeprefix("--")
            path = Path(arguments.pop(0))
        else:
            errors.append(f"unknown checker argument: {argument}")
    if allow_missing and (mode != "default" or path != RESULT_PATH):
        errors.append("allow-missing-results cannot be combined with supplied input")
    qualification = False
    if not path.exists():
        if not allow_missing:
            errors.append("OpenAI signing-key-rotation Result is missing")
    elif attestation is not None:
        result = read_bounded_input(path, "OpenAI signing-key-rotation input", errors)
        if result is not None:
            if mode == "contract-fixture":
                errors.extend(validate_contract_fixture(result, policy, attestation))
            elif mode == "evidence":
                errors.extend(validate_qualification_evidence(result, policy, attestation))
            else:
                errors.extend(validate_observation(result, policy, attestation))
            qualification = (
                isinstance(result, dict) and result.get("qualification_evidence") is True
            )
        else:
            qualification = False
    else:
        qualification = False
    if errors:
        print("OpenAI signing-key rotation check: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    if mode == "contract-fixture":
        status = "synthetic contract Fixture; not qualification evidence"
    elif path.exists() and qualification:
        status = "qualification evidence"
    elif path.exists():
        status = "non-qualifying provider observation"
    else:
        status = "static preflight"
    print(f"OpenAI signing-key rotation check: pass ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
