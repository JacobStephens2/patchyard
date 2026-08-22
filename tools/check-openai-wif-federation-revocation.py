#!/usr/bin/env python3
"""Check an OpenAI federation-rule revocation Result or contract Fixture."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
import sysconfig
import types
from typing import Any


CHECKER_RUNTIME_PATH = Path(__file__).with_name("factory_checker_runtime.py")
CHECKER_RUNTIME_SHA256 = "db4217cdd58d3dc8343f0ba2a9d1842eb07d6356d6aa430a2e3ff9b0be07e9fe"
_checker_runtime_source = CHECKER_RUNTIME_PATH.read_bytes()
if (
    CHECKER_RUNTIME_PATH.is_symlink()
    or hashlib.sha256(_checker_runtime_source).hexdigest()
    != CHECKER_RUNTIME_SHA256
):
    raise RuntimeError("factory checker runtime differs from its exact binding")
RUNTIME = types.ModuleType("factory_checker_runtime_check_openai_wif_federation_revocation")
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
COLLECTOR_PATH = REPO / "tools/openai-wif-federation-revocation.py"
RESULT_PATH = REPO / "research/isolation/results/openai-federation-revocation.json"
PROVIDER_POLICY_PATH = REPO / "policy/provider-egress.json"
POLICY_SHA256 = "87cf13bb136ed9a365bd14822a14d4808a6ef585ce1c278b926fa173d1152e5f"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
LIFECYCLE_INSTRUMENT_SHA256 = (
    "3547ee7c79226123421027df527183d49a7d887368d0b3c6d234b90eaa6f5f52"
)
# A149 completed the two deferred fields on the banked Result without touching
# its Receipts or its `source` block, so the digests that block names are the
# pre-A149 collector and checker. They stay acceptable here, exactly as A144
# taught this family to carry historical bindings.
# A150 moved the service-account id out of the lifecycle instrument's inline
# constant and into the identity registry, so the instrument digest this
# Result names is now historical too.
SUPERSEDES_SOURCE_SHA256 = {
    "tools/openai-wif-federation-revocation.py": (
        "7ba44eb3151e1eb61e9ae42a48b2d0d34248e7c70ae108752168eeb4b9f0b079",
    ),
    "tools/check-openai-wif-federation-revocation.py": (
        "9e1fdc60ee3c4240e1c30385f4a092c29b8d58b4ab2dfd8a55c19a42ed8439d8",
    ),
    "tools/openai-wif-issuance.py": (
        "efbd1229f7a1042d564aacb1c706fb916468d305c99f83989ea88c33b742ee0e",
    ),
}
ACCEPTED_LIFECYCLE_INSTRUMENT_SHA256 = frozenset(
    (LIFECYCLE_INSTRUMENT_SHA256,)
    + SUPERSEDES_SOURCE_SHA256["tools/openai-wif-issuance.py"]
)
RUN_ID = re.compile(r"openai-revocation-[0-9]{8}-[0-9a-f]{10}")
PAIRING = re.compile(
    r"[a-z0-9][a-z0-9.+_-]*/[a-z0-9][a-z0-9.+_-]*/"
    r"[A-Za-z0-9][A-Za-z0-9.+_-]*/[a-z0-9][a-z0-9_+-]*"
)
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
MAX_INPUT_BYTES = 2_000_000
MAX_RESPONSE_BYTES = 1_000_000
SETTLING_FLOOR_SECONDS = 90
AUTHORIZATION_DEADLINE_MINUTES = 45
AUTHORIZATION_ISSUE_URL = (
    "https://github.com/JacobStephens2/patchyard/issues/211"
)
AUTHORIZATION_AUTHOR = "JacobStephens2"
ROUTE_AUTHORIZATION_SOURCE = "route authorization"
ROUTE_AUTHORIZATION_RULING = "A148"
ROUTE_AUTHORIZATION_MAP_URL = (
    "https://github.com/JacobStephens2/patchyard/issues/176"
)
ROUTE_AUTHORIZATION_GRANT_URL = (
    "https://github.com/JacobStephens2/patchyard/issues/253"
)
COMMENT_AUTHORIZATION_RULINGS = ["A129", "A132", "A133", "A136", "A146"]
ROUTE_AUTHORIZATION_RULINGS = ["A129", "A132", "A133", "A136", "A146", "A148"]
CAPTURE_METHOD = "model_console_readback_bounded_by_control_plane_utc"
OPERATOR_CAPTURE_METHOD = "operator_console_readback_bounded_by_control_plane_utc"
PERMITTED_MUTATION = "subject-expression Edit to the run-scoped sentinel"
PERMITTED_RESTORATION = "Edit the original expression back"
REVOCATION_SENTINEL_MARKER = "-REVOKED-"
UNOBSERVED_RESPONSE_PREDICATE = {
    "enforced": False,
    "basis": "no-observed-openai-federation-revocation-response",
}
RESPONSE_PREDICATE = {
    "enforced": True,
    "http_status": 401,
    "access_token_supplied": False,
    "basis": "observed-openai-federation-revocation-response",
}
RESULT_KEYS = {
    "schema_version",
    "provider",
    "qualification_requirement",
    "authorization_rulings",
    "observation_kind",
    "run_id",
    "bounded_window",
    "human_authorization",
    "model_identity",
    "model_actions",
    "model_console_observations",
    "baseline_control",
    "denial_observation",
    "bracketing_control",
    "response_predicate",
    "mutation_receipt_obtained",
    "provider_response_observed",
    "qualification_evidence",
    "source",
}
FIXTURE_KEYS = {"fixture_kind", "fixture_lineage"}
WINDOW_KEYS = {"started_at", "ended_at"}
HUMAN_AUTHORIZATION_KEYS = {
    "source",
    "issue_url",
    "comment_url",
    "comment_id",
    "created_at",
    "author_login",
    "body",
    "extracted",
    "attempt",
    "human_attestation_obtained",
    "human_authorship_mechanically_proven",
}
ROUTE_AUTHORIZATION_KEYS = {
    "source",
    "ruling",
    "map_url",
    "grant_url",
    "author_login",
    "human_attestation_obtained",
    "human_authorship_mechanically_proven",
}
EXTRACTED_KEYS = {
    "run_id",
    "pairing",
    "codex_task_id",
    "policy_sha256",
    "collector_sha256",
    "permitted_mutation",
    "permitted_restoration",
    "deadline_at",
}
MODEL_IDENTITY_KEYS = {"pairing", "codex_task_id"}
ACTION_KINDS = (
    "subject_expression_edit_save",
    "subject_expression_restore_save",
)
ACTION_KEYS = {"kind", "action_id", "intent", "confirmation"}
INTENT_KEYS = {
    "recorded_at",
    "console_location",
    "intended_expression",
    "permitted_mutation",
}
CONFIRMATION_KEYS = {
    "recorded_at",
    "save_completed",
    "product_approval_presented",
    "product_approval_completed",
    "capture_sha256",
    "observed_expression",
}
OBSERVATION_STEPS = (
    "enabled_mapping_before_baseline",
    "immediate_before_mutation",
    "immediate_after_mutation",
    "before_restoration",
    "after_restoration",
)
OBSERVATION_KEYS = {
    "step",
    "capture_method",
    "capture_action_id",
    "captured_before_at",
    "captured_after_at",
    "state",
    "navigation",
}
NAVIGATION_KEYS = {
    "url",
    "reloaded",
    "reload_started_at",
    "reload_completed_at",
}
FORBIDDEN_KEYS = {
    "attester",
    "actor",
    "party_relationship",
    "mapping_mutation_attestation",
    "restoration_attestation",
    "initial_console_reading",
    "independence",
    "corroboration",
    "attestation_definition_sha256",
}
MAPPING_STATE_KEYS = {
    "identity_provider_id",
    "mapping_present",
    "subject_mapping_expression",
    "mapped_service_account_id",
    "enabled",
    "uploaded_jwks_mode",
    "console_location",
}
EXCHANGE_KEYS = {
    "key_role",
    "attempt_count",
    "started_at",
    "assertion_descriptor",
    "exchange_request",
    "receipt",
    "credential_removed_at",
    "lifecycle_instrument_sha256",
}
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
RECEIPT_KEYS = {
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
RESPONSE_SHAPE_KEYS = {"body_kind", "top_level_fields", "error_fields"}
FIELD_DESCRIPTOR_KEYS = {"name", "name_recorded", "value_type"}
JSON_VALUE_TYPES = {"null", "boolean", "integer", "number", "string", "object", "array"}
SOURCE_KEYS = {
    "policy_sha256",
    "base_harness_sha256",
    "lifecycle_instrument_sha256",
    "collector_sha256",
    "checker_sha256",
}


CHECKER = RUNTIME.checker_runtime(
    identity="OpenAI federation-revocation checker",
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
        errors.append("OpenAI WIF policy differs from the federation-revocation contract")
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
    policy: dict[str, Any],
    errors: list[str],
    *,
    synthetic: bool,
    positive: bool,
) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    if not exact_keys(value, EXCHANGE_KEYS, label, errors):
        return facts
    if value.get("key_role") != "active":
        errors.append(f"{label} did not use the active key role")
    if not valid_int(value.get("attempt_count")) or value.get("attempt_count") != 1:
        errors.append(f"{label} was not exactly one attempt")
    # A150: the banked Result's exchanges name the pre-registry instrument, so
    # the superseded digest is accepted here exactly as it is in `source`.
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
    if all(item is not None for item in ordered):
        if not all(left <= right for left, right in zip(ordered, ordered[1:])):
            errors.append(f"{label} UTC observations are out of order")
    # minted_at is whole-second precision in the frozen instrument. It can be
    # earlier than a microsecond started_at in the same second, so only the
    # sound signed-before-sent comparison belongs here.
    if minted is not None and request_time is not None and minted > request_time:
        errors.append(f"{label} assertion was minted after its request")
    if issued is not None and expires is not None and not issued < expires:
        errors.append(f"{label} assertion issued_at is not before expires_at")
    if positive and isinstance(value.get("receipt"), dict) and value["receipt"].get(
        "access_token_supplied"
    ) is not True:
        errors.append(f"{label} did not supply a bearer")
    if not positive and not synthetic and isinstance(value.get("receipt"), dict):
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
            "kid": assertion.get("kid") if isinstance(assertion, dict) else None,
            "thumbprint": (
                assertion.get("jwk_thumbprint_sha256")
                if isinstance(assertion, dict)
                else None
            ),
        }
    )
    return facts


def validate_mapping_state(value: Any, policy: dict[str, Any], label: str, errors: list[str]) -> bool:
    if not exact_keys(value, MAPPING_STATE_KEYS, label, errors):
        return False
    if value.get("identity_provider_id") != policy.get("identity_provider_id"):
        errors.append(f"{label} names another provider identity")
    for field in ("mapping_present", "enabled", "uploaded_jwks_mode"):
        if type(value.get(field)) is not bool:
            errors.append(f"{label} {field} is not boolean")
    for field in ("subject_mapping_expression", "mapped_service_account_id"):
        item = value.get(field)
        if item is not None and not bounded_console_text(item):
            errors.append(f"{label} {field} is not bounded")
    if not bounded_console_text(value.get("console_location")):
        errors.append(f"{label} console location is not bounded")
    if value.get("mapping_present") is False and (
        value.get("subject_mapping_expression") is not None
        or value.get("mapped_service_account_id") is not None
        or value.get("enabled") is not False
    ):
        errors.append(f"{label} absent mapping retained state")
    return True


def state_core(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "console_location"}


def validate_source(value: Any, errors: list[str]) -> None:
    if not exact_keys(value, SOURCE_KEYS, "federation-revocation source", errors):
        return
    accepted = {
        "policy_sha256": {digest(POLICY_PATH)},
        "base_harness_sha256": {digest(BASE_HARNESS_PATH)},
        "lifecycle_instrument_sha256": {digest(LIFECYCLE_INSTRUMENT_PATH)}
        | set(SUPERSEDES_SOURCE_SHA256["tools/openai-wif-issuance.py"]),
        "collector_sha256": {digest(COLLECTOR_PATH)}
        | set(SUPERSEDES_SOURCE_SHA256["tools/openai-wif-federation-revocation.py"]),
        "checker_sha256": {digest(Path(__file__).resolve())}
        | set(
            SUPERSEDES_SOURCE_SHA256["tools/check-openai-wif-federation-revocation.py"]
        ),
    }
    for field, acceptable in accepted.items():
        supplied = value.get(field)
        if supplied not in acceptable:
            errors.append(
                f"federation-revocation {field} differs: expected {supplied}, observed {sorted(acceptable)}"
            )


def revocation_sentinel(run_id: str) -> str:
    return f"sub=patchyard-control-plane{REVOCATION_SENTINEL_MARKER}{run_id}"


def bounded_identity_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 128
        and all(character.isprintable() for character in value)
        and "\n" not in value
    )


def walk_forbidden(value: Any, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                errors.append(
                    f"federation-revocation Result contains forbidden key: {key}"
                )
            walk_forbidden(child, errors)
    elif isinstance(value, list):
        for child in value:
            walk_forbidden(child, errors)
    elif isinstance(value, str):
        if value == OPERATOR_CAPTURE_METHOD:
            errors.append(
                "federation-revocation Result uses the operator capture method"
            )


def extract_single_json_fence(body: str, errors: list[str]) -> Any:
    openings = list(re.finditer(r"```json[ \t]*\n", body))
    if len(openings) != 1:
        errors.append("authorization body must contain exactly one fenced JSON object")
        return None
    start = openings[0].end()
    end = body.find("\n```", start)
    if end < 0:
        errors.append("authorization JSON fence is unclosed")
        return None
    try:
        parsed = json.loads(
            body[start:end],
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_json_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, EvidenceJsonError):
        errors.append("authorization fence is not strict JSON")
        return None
    if not isinstance(parsed, dict):
        errors.append("authorization fence is not an object")
        return None
    return parsed


def validate_route_authorization(
    value: Any, errors: list[str]
) -> tuple[datetime | None, str | None, str | None]:
    if not exact_keys(value, ROUTE_AUTHORIZATION_KEYS, "human_authorization", errors):
        return None, None, None
    if value.get("ruling") != ROUTE_AUTHORIZATION_RULING:
        errors.append("route authorization does not name A148")
    if value.get("map_url") != ROUTE_AUTHORIZATION_MAP_URL:
        errors.append("route authorization does not name the map")
    if value.get("grant_url") != ROUTE_AUTHORIZATION_GRANT_URL:
        errors.append("route authorization does not name the grant")
    if value.get("author_login") != AUTHORIZATION_AUTHOR:
        errors.append("authorization author is not the accountable human")
    if value.get("human_attestation_obtained") is not False:
        errors.append("authorization claims a human attestation")
    if value.get("human_authorship_mechanically_proven") is not False:
        errors.append("authorization claims mechanically proven authorship")
    return None, None, None


def validate_authorization(
    value: Any,
    run_id: str,
    source: Any,
    window_start: datetime | None,
    errors: list[str],
) -> tuple[datetime | None, str | None, str | None]:
    if isinstance(value, dict) and value.get("source") == ROUTE_AUTHORIZATION_SOURCE:
        return validate_route_authorization(value, errors)
    if not exact_keys(value, HUMAN_AUTHORIZATION_KEYS, "human_authorization", errors):
        return None, None, None
    if value.get("source") != "github_issue_comment":
        errors.append("authorization source is not a GitHub comment")
    if value.get("issue_url") != AUTHORIZATION_ISSUE_URL:
        errors.append("authorization does not name the requirement-4 ticket")
    comment_id = value.get("comment_id")
    if not valid_int(comment_id) or comment_id <= 0:
        errors.append("authorization comment id is malformed")
    else:
        expected_url = f"{AUTHORIZATION_ISSUE_URL}#issuecomment-{comment_id}"
        if value.get("comment_url") != expected_url:
            errors.append("authorization comment URL does not match its id")
    if value.get("author_login") != AUTHORIZATION_AUTHOR:
        errors.append("authorization author is not the accountable human")
    body = value.get("body")
    if not isinstance(body, str) or not 1 <= len(body) <= 16_384:
        errors.append("authorization body is not bounded")
        body = ""
    extracted = value.get("extracted")
    if not exact_keys(extracted, EXTRACTED_KEYS, "authorization extracted fields", errors):
        extracted = {}
    fenced = extract_single_json_fence(body, errors) if body else None
    if fenced is not None and extracted and fenced != extracted:
        errors.append("authorization fence does not match the extracted fields")
    if extracted.get("run_id") != run_id:
        errors.append("authorization run ID does not match the Result")
    pairing = extracted.get("pairing")
    task_id = extracted.get("codex_task_id")
    if not isinstance(pairing, str) or PAIRING.fullmatch(pairing) is None:
        errors.append("authorization pairing is not canonical")
        pairing = None
    if not bounded_identity_text(task_id):
        errors.append("authorization Codex task id is not bounded")
        task_id = None
    if isinstance(source, dict):
        if extracted.get("policy_sha256") != source.get("policy_sha256"):
            errors.append("authorization policy digest differs")
        if extracted.get("collector_sha256") != source.get("collector_sha256"):
            errors.append("authorization collector digest differs")
    if extracted.get("permitted_mutation") != PERMITTED_MUTATION:
        errors.append("authorization permitted mutation differs")
    if extracted.get("permitted_restoration") != PERMITTED_RESTORATION:
        errors.append("authorization permitted restoration differs")
    created = parse_time(value.get("created_at"), "authorization created_at", errors)
    deadline = parse_time(extracted.get("deadline_at"), "authorization deadline", errors)
    if (
        created is not None
        and deadline is not None
        and deadline != created + timedelta(minutes=AUTHORIZATION_DEADLINE_MINUTES)
    ):
        errors.append("authorization deadline is not created_at plus 45 minutes")
    if created is not None and window_start is not None and created >= window_start:
        errors.append("authorization comment is not before the bounded window")
    if value.get("attempt") != 1:
        errors.append("authorization attempt is not 1")
    if value.get("human_attestation_obtained") is not False:
        errors.append("authorization claims a human attestation")
    if value.get("human_authorship_mechanically_proven") is not False:
        errors.append("authorization claims mechanically proven authorship")
    return deadline, pairing, task_id


def validate_model_identity(
    value: Any, pairing: str | None, task_id: str | None, errors: list[str]
) -> None:
    if not exact_keys(value, MODEL_IDENTITY_KEYS, "model_identity", errors):
        return
    observed_pairing = value.get("pairing")
    observed_task = value.get("codex_task_id")
    if not isinstance(observed_pairing, str) or PAIRING.fullmatch(observed_pairing) is None:
        errors.append("model pairing is not canonical")
    if not bounded_identity_text(observed_task):
        errors.append("model Codex task id is not bounded")
    if pairing is not None and observed_pairing != pairing:
        errors.append("model pairing does not match the authorization")
    if task_id is not None and observed_task != task_id:
        errors.append("model task id does not match the authorization")


def validate_action(
    value: Any,
    expected_kind: str,
    intended_expression: str,
    permitted_mutation: str,
    label: str,
    errors: list[str],
) -> tuple[datetime | None, datetime | None, str | None]:
    if not exact_keys(value, ACTION_KEYS, label, errors):
        return None, None, None
    if value.get("kind") != expected_kind:
        errors.append(f"{label} kind differs")
    action_id = value.get("action_id")
    if not bounded_identity_text(action_id):
        errors.append(f"{label} action id is not bounded")
        action_id = None
    intent = value.get("intent")
    confirmation = value.get("confirmation")
    intent_at = None
    confirmed_at = None
    if exact_keys(intent, INTENT_KEYS, f"{label} intent", errors):
        intent_at = parse_time(
            intent.get("recorded_at"), f"{label} intent recorded_at", errors
        )
        if not bounded_console_text(intent.get("console_location")):
            errors.append(f"{label} intent console location is not bounded")
        if intent.get("intended_expression") != intended_expression:
            errors.append(f"{label} intended expression differs")
        if intent.get("permitted_mutation") != permitted_mutation:
            errors.append(f"{label} permitted mutation differs")
    if exact_keys(confirmation, CONFIRMATION_KEYS, f"{label} confirmation", errors):
        confirmed_at = parse_time(
            confirmation.get("recorded_at"), f"{label} confirmation recorded_at", errors
        )
        if confirmation.get("save_completed") is not True:
            errors.append(f"{label} Save did not complete")
        presented = confirmation.get("product_approval_presented")
        completed = confirmation.get("product_approval_completed")
        if type(presented) is not bool or type(completed) is not bool:
            errors.append(f"{label} product-approval fields are not boolean")
        elif presented is False and completed is not False:
            errors.append(
                f"{label} completed a product approval that was not presented"
            )
        capture = confirmation.get("capture_sha256")
        if capture is not None and (
            not isinstance(capture, str) or HEX64.fullmatch(capture) is None
        ):
            errors.append(f"{label} capture digest is malformed")
        if confirmation.get("observed_expression") != intended_expression:
            errors.append(f"{label} observed expression does not match the intent")
        if intent_at is not None and confirmed_at is not None and intent_at > confirmed_at:
            errors.append(f"{label} confirmation precedes its intent")
    return intent_at, confirmed_at, action_id


def validate_model_observation(
    value: Any, policy: dict[str, Any], expected_step: str, label: str, errors: list[str]
) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    if not exact_keys(value, OBSERVATION_KEYS, label, errors):
        return facts
    if value.get("step") != expected_step:
        errors.append(f"{label} step differs")
    if value.get("capture_method") != CAPTURE_METHOD:
        errors.append(f"{label} capture method differs")
    action_id = value.get("capture_action_id")
    if not bounded_identity_text(action_id):
        errors.append(f"{label} capture action id is not bounded")
        action_id = None
    before = parse_time(value.get("captured_before_at"), f"{label} captured_before_at", errors)
    after = parse_time(value.get("captured_after_at"), f"{label} captured_after_at", errors)
    if before is not None and after is not None and before > after:
        errors.append(f"{label} UTC bounds are out of order")
    state = value.get("state")
    validate_mapping_state(state, policy, f"{label} state", errors)
    navigation = value.get("navigation")
    reload_started = reload_completed = None
    if exact_keys(navigation, NAVIGATION_KEYS, f"{label} navigation", errors):
        if navigation.get("reloaded") is not True:
            errors.append(f"{label} was not reloaded")
        if not bounded_console_text(navigation.get("url")):
            errors.append(f"{label} navigation url is not bounded")
        elif isinstance(state, dict) and navigation.get("url") != state.get(
            "console_location"
        ):
            errors.append(f"{label} navigation url differs from the console location")
        reload_started = parse_time(
            navigation.get("reload_started_at"), f"{label} reload start", errors
        )
        reload_completed = parse_time(
            navigation.get("reload_completed_at"), f"{label} reload end", errors
        )
        if (
            reload_started is not None
            and reload_completed is not None
            and reload_started > reload_completed
        ):
            errors.append(f"{label} reload timestamps are out of order")
        if (
            reload_completed is not None
            and before is not None
            and reload_completed > before
        ):
            errors.append(f"{label} reading started before its reload completed")
    facts.update(
        {
            "before": before,
            "after": after,
            "reload_started": reload_started,
            "reload_completed": reload_completed,
            "state": state if isinstance(state, dict) else {},
            "action_id": action_id,
        }
    )
    return facts


def credential_errors(value: Any) -> list[str]:
    errors: list[str] = []
    forbidden = secret_named_key(value)
    if forbidden is not None:
        errors.append(
            "OpenAI federation-revocation Result contains forbidden credential field: "
            f"{forbidden}"
        )
    serialized = json.dumps(value, sort_keys=True)
    if JWT.search(serialized) or OPENAI_KEY.search(serialized) or BEARER.search(
        serialized
    ) or PRIVATE_KEY.search(serialized):
        errors.append("OpenAI federation-revocation Result carries credential-shaped material")
    return errors


def validate_common(
    result: Any,
    policy: dict[str, Any],
    *,
    synthetic: bool,
) -> list[str]:
    errors: list[str] = []
    expected_keys = RESULT_KEYS | (FIXTURE_KEYS if synthetic else set())
    if not exact_keys(result, expected_keys, "OpenAI federation-revocation Result", errors):
        return errors
    walk_forbidden(result, errors)
    if (
        not valid_int(result.get("schema_version"))
        or result.get("schema_version") != 1
        or result.get("provider") != "openai"
    ):
        errors.append("OpenAI federation-revocation Result identity differs")
    if result.get("qualification_requirement") != "federation-rule-revocation":
        errors.append("OpenAI federation-revocation Result names another Requirement")
    authorization = result.get("human_authorization")
    expected_rulings = (
        ROUTE_AUTHORIZATION_RULINGS
        if isinstance(authorization, dict)
        and authorization.get("source") == ROUTE_AUTHORIZATION_SOURCE
        else COMMENT_AUTHORIZATION_RULINGS
    )
    if result.get("authorization_rulings") != expected_rulings:
        errors.append("OpenAI federation-revocation authorization rulings differ")
    if result.get("observation_kind") != "federation-rule-revocation":
        errors.append("OpenAI federation-revocation observation kind differs")
    run_id = str(result.get("run_id", ""))
    if RUN_ID.fullmatch(run_id) is None:
        errors.append("OpenAI federation-revocation run ID is malformed")
    window = result.get("bounded_window")
    window_start = window_end = None
    if exact_keys(window, WINDOW_KEYS, "federation-revocation bounded window", errors):
        window_start = parse_time(window.get("started_at"), "bounded window start", errors)
        window_end = parse_time(window.get("ended_at"), "bounded window end", errors)
        if window_start is not None and window_end is not None and window_start > window_end:
            errors.append("federation-revocation bounded window is reversed")

    deadline, pairing, task_id = validate_authorization(
        result.get("human_authorization"),
        run_id,
        result.get("source"),
        window_start,
        errors,
    )
    validate_model_identity(result.get("model_identity"), pairing, task_id, errors)

    observations_raw = result.get("model_console_observations")
    observations: list[dict[str, Any]] = []
    if not isinstance(observations_raw, list) or len(observations_raw) != 5:
        errors.append("model_console_observations must contain exactly five readings")
        observations_raw = []
    for index, step in enumerate(OBSERVATION_STEPS):
        item = observations_raw[index] if index < len(observations_raw) else {}
        observations.append(
            validate_model_observation(
                item, policy, step, f"model console observation {step}", errors
            )
        )

    actions_raw = result.get("model_actions")
    if not isinstance(actions_raw, list) or len(actions_raw) != 2:
        errors.append("model_actions must contain exactly two Saves")
        actions_raw = [{}, {}]
    original_expression = ""
    if observations and observations[0].get("state"):
        original_expression = str(
            observations[0]["state"].get("subject_mapping_expression") or ""
        )
    sentinel = revocation_sentinel(run_id)
    edit_intent, edit_confirmed, edit_id = validate_action(
        actions_raw[0],
        ACTION_KINDS[0],
        sentinel,
        PERMITTED_MUTATION,
        "subject-expression edit Save",
        errors,
    )
    restore_intent, restore_confirmed, restore_id = validate_action(
        actions_raw[1],
        ACTION_KINDS[1],
        original_expression,
        PERMITTED_RESTORATION,
        "subject-expression restore Save",
        errors,
    )
    if deadline is not None and edit_intent is not None and edit_intent > deadline:
        errors.append("mutation Save intent is after the authorization deadline")

    first = observations[0] if observations else {}
    second = observations[1] if len(observations) > 1 else {}
    third = observations[2] if len(observations) > 2 else {}
    fourth = observations[3] if len(observations) > 3 else {}
    fifth = observations[4] if len(observations) > 4 else {}
    first_state = first.get("state") or {}
    active_state = (
        first_state.get("mapping_present") is True
        and first_state.get("enabled") is True
        and first_state.get("uploaded_jwks_mode") is True
        and first_state.get("mapped_service_account_id")
        in roster_service_account_ids(errors)
        and bool(first_state.get("subject_mapping_expression"))
        and REVOCATION_SENTINEL_MARKER not in str(
            first_state.get("subject_mapping_expression") or ""
        )
    )
    if not active_state:
        errors.append("enabled-mapping-before-baseline is not the enabled mapping")
    if first_state and second.get("state") and state_core(first_state) != state_core(
        second["state"]
    ):
        errors.append("mapping changed between baseline and mutation")
    if third.get("state"):
        mutated = third["state"]
        if (
            mutated.get("mapping_present") is not True
            or mutated.get("enabled") is not True
            or mutated.get("uploaded_jwks_mode") is not True
            or mutated.get("subject_mapping_expression") != sentinel
            or mutated.get("mapped_service_account_id")
            != first_state.get("mapped_service_account_id")
        ):
            errors.append("immediate-after-mutation is not the exact sentinel")
    if third.get("state") and fourth.get("state") and state_core(third["state"]) != state_core(
        fourth["state"]
    ):
        errors.append("mapping changed between denial and restoration")
    if first_state and fifth.get("state") and state_core(first_state) != state_core(
        fifth["state"]
    ):
        errors.append("after-restoration did not recover the original mapping")

    action_ids = [
        observation.get("action_id")
        for observation in observations
        if observation.get("action_id")
    ]
    action_ids.extend(item for item in (edit_id, restore_id) if item)
    if len(action_ids) != len(set(action_ids)):
        errors.append("federation-revocation action IDs are not pairwise distinct")

    for observation in observations:
        state = observation.get("state") or {}
        if state and (
            state.get("identity_provider_id") != policy.get("identity_provider_id")
            or state.get("mapped_service_account_id")
            not in roster_service_account_ids(errors)
            or state.get("uploaded_jwks_mode") is not True
        ):
            errors.append("console reading drifted from the provider or JWKS binding")

    baseline = validate_exchange(
        result.get("baseline_control"),
        "baseline control",
        policy,
        errors,
        synthetic=synthetic,
        positive=True,
    )
    denial = validate_exchange(
        result.get("denial_observation"),
        "denial observation",
        policy,
        errors,
        synthetic=synthetic,
        positive=False,
    )
    bracket = validate_exchange(
        result.get("bracketing_control"),
        "bracketing control",
        policy,
        errors,
        synthetic=synthetic,
        positive=True,
    )

    facts = [baseline, denial, bracket]
    if all(fact.get("surface") for fact in facts) and not all(
        fact["surface"] == facts[0]["surface"] for fact in facts[1:]
    ):
        errors.append("baseline, denial, and bracketing control use different surfaces")
    identities = [(fact.get("kid"), fact.get("thumbprint")) for fact in facts]
    if all(all(item is not None for item in identity) for identity in identities) and len(
        set(identities)
    ) != 1:
        errors.append("baseline, denial, and bracketing control use different keys")
    if third.get("after") is not None and denial.get("request_time") is not None:
        if (denial["request_time"] - third["after"]).total_seconds() < SETTLING_FLOOR_SECONDS:
            errors.append("denial attempt falls inside the 90-second settling floor")
    if fifth.get("after") is not None and bracket.get("request_time") is not None:
        if (bracket["request_time"] - fifth["after"]).total_seconds() < SETTLING_FLOOR_SECONDS:
            errors.append("bracketing control falls inside the 90-second settling floor")

    sequence = [
        window_start,
        first.get("reload_started"),
        first.get("reload_completed"),
        first.get("before"),
        first.get("after"),
        baseline.get("started"),
        baseline.get("removed"),
        second.get("reload_started"),
        second.get("reload_completed"),
        second.get("before"),
        second.get("after"),
        edit_intent,
        edit_confirmed,
        third.get("reload_started"),
        third.get("reload_completed"),
        third.get("before"),
        third.get("after"),
        denial.get("started"),
        denial.get("removed"),
        fourth.get("reload_started"),
        fourth.get("reload_completed"),
        fourth.get("before"),
        fourth.get("after"),
        restore_intent,
        restore_confirmed,
        fifth.get("reload_started"),
        fifth.get("reload_completed"),
        fifth.get("before"),
        fifth.get("after"),
        bracket.get("started"),
        bracket.get("removed"),
        window_end,
    ]
    if all(item is not None for item in sequence) and not all(
        left <= right for left, right in zip(sequence, sequence[1:])
    ):
        errors.append("federation-revocation UTC observations are out of order")
    expected_predicate = (
        UNOBSERVED_RESPONSE_PREDICATE if synthetic else RESPONSE_PREDICATE
    )
    if result.get("response_predicate") != expected_predicate:
        if synthetic:
            errors.append(
                "federation-revocation predicate was enforced before observation"
            )
        else:
            errors.append(
                "federation-revocation predicate does not match the reviewed "
                "revocation denial"
            )
    if result.get("mutation_receipt_obtained") is not False:
        errors.append("federation-revocation Result provenance mark differs")
    validate_source(result.get("source"), errors)
    errors.extend(credential_errors(result))
    return errors


def validate_observation(result: Any, policy: dict[str, Any]) -> list[str]:
    if isinstance(result, dict) and result.get("status") in {"in_progress", "failed"}:
        return ["non-terminal federation-revocation record is not a Result"]
    errors = validate_common(result, policy, synthetic=False)
    if isinstance(result, dict):
        if result.get("provider_response_observed") is not True:
            errors.append("federation-revocation observation lacks provider responses")
        if result.get("qualification_evidence") not in {True, False}:
            errors.append(
                "federation-revocation qualification_evidence is not boolean"
            )
    return errors


def validate_contract_fixture(result: Any, policy: dict[str, Any]) -> list[str]:
    errors = validate_common(result, policy, synthetic=True)
    if not isinstance(result, dict):
        return errors
    if result.get("fixture_kind") != "synthetic-openai-federation-revocation-satisfiability":
        errors.append("federation-revocation Fixture kind differs")
    if result.get("fixture_lineage") != {
        "console_readings": "synthetic-bounded-model-console-input",
        "provider_responses": "unobserved-placeholders",
    }:
        errors.append("federation-revocation Fixture lineage differs")
    if result.get("provider_response_observed") is not False:
        errors.append("federation-revocation Fixture claims a provider response")
    if result.get("qualification_evidence") is not False:
        errors.append("federation-revocation Fixture claims qualification")
    return errors


def validate_qualification_evidence(result: Any, policy: dict[str, Any]) -> list[str]:
    if isinstance(result, dict) and result.get("fixture_kind") is not None:
        return ["synthetic federation-revocation Fixture cannot be qualification evidence"]
    errors = validate_observation(result, policy)
    if isinstance(result, dict) and result.get("qualification_evidence") is not True:
        errors.append("federation-revocation Result is not qualification evidence")
    return errors


def static_errors() -> tuple[list[str], dict[str, Any]]:
    errors = isolation_errors()
    # A150: the identity registry is gated on every CI cycle, not only when
    # a Result is present, so a roster that lost its current or issuance-era
    # entry fails closed here.
    roster_service_account_ids(errors)
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
        errors.append("OpenAI federation-revocation collector is missing or a symlink")
    else:
        source = COLLECTOR_PATH.read_text()
        for required in (
            "LIFECYCLE_INSTRUMENT_SHA256",
            "def load_exact_source(",
            '"MUTATION COMPLETE"',
            '"RESTORATION COMPLETE"',
            '"RELOADED"',
            "human_authorization",
            "route authorization",
            "model_console_readback_bounded_by_control_plane_utc",
            '"observed-openai-federation-revocation-response"',
            "SETTLING_FLOOR_SECONDS = 90",
        ):
            if required not in source:
                errors.append(f"federation-revocation collector is missing: {required}")
        if "ATTESTATION_DEFINITION_SHA256" in source:
            errors.append(
                "federation-revocation collector still binds the Attestation definition"
            )
        if "operator_console_readback_bounded_by_control_plane_utc" in source:
            errors.append(
                "federation-revocation collector still uses the operator capture method"
            )
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
        if not 1 <= path.stat().st_size <= MAX_INPUT_BYTES:
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
                errors.append("federation-revocation checker accepts only one input mode")
            mode = argument.removeprefix("--")
            path = Path(arguments.pop(0))
        else:
            errors.append(f"unknown checker argument: {argument}")
    if allow_missing and (mode != "default" or path != RESULT_PATH):
        errors.append("allow-missing-results cannot be combined with supplied input")
    qualification = False
    if not path.exists():
        if not allow_missing:
            errors.append("OpenAI federation-revocation Result is missing")
    else:
        result = read_bounded_input(path, "OpenAI federation-revocation input", errors)
        if result is not None:
            if mode == "contract-fixture":
                errors.extend(validate_contract_fixture(result, policy))
            elif mode == "evidence":
                errors.extend(validate_qualification_evidence(result, policy))
            else:
                errors.extend(validate_observation(result, policy))
            qualification = (
                isinstance(result, dict)
                and result.get("qualification_evidence") is True
            )
    if errors:
        print("OpenAI federation-rule revocation check: failed", file=sys.stderr)
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
    print(f"OpenAI federation-rule revocation check: pass ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
