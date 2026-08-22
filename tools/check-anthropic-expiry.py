#!/usr/bin/env python3
"""Check the source and evidence contract for A113 Anthropic expiry denial."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import sysconfig
from typing import Any
import types


CHECKER_RUNTIME_PATH = Path(__file__).with_name("factory_checker_runtime.py")
CHECKER_RUNTIME_SHA256 = "db4217cdd58d3dc8343f0ba2a9d1842eb07d6356d6aa430a2e3ff9b0be07e9fe"
_checker_runtime_source = CHECKER_RUNTIME_PATH.read_bytes()
if (
    CHECKER_RUNTIME_PATH.is_symlink()
    or hashlib.sha256(_checker_runtime_source).hexdigest()
    != CHECKER_RUNTIME_SHA256
):
    raise RuntimeError("factory checker runtime differs from its exact binding")
RUNTIME = types.ModuleType("factory_checker_runtime_check_anthropic_expiry")
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
POLICY_PATH = REPO / "policy/anthropic-wif.json"
HARNESS_PATH = REPO / "tools/anthropic-wif-lifecycle.py"
RESULT_PATH = REPO / "research/isolation/results/anthropic-expiry-denial.json"
SUPERSEDES_CHECKER_SHA256 = (
    "41904ee87d54c362c9714c3c06853e5f"
    "67047365847edc9431620d62bc5a9c54",
)
PROTECTED_SOURCES = {
    "worker/qualification/patchyard-run-anthropic-issuance": (
        "91c3fdc09b34d009a02e4f8d1290976c558b0a654e89171dcaa5b3fd037a7608"
    ),
    "worker/runtime/patchyard-firecracker-run": (
        "60b71fb24ce3c47b9b62bdece7166dd0c622a1830fb21d673db8830acf133e3f"
    ),
    "worker/runtime/patchyard-anthropic-one-shot": (
        "41a5416acb2df277f7268d24f51fc4569b539ffe408df73ad6c6468bdb7bcd36"
    ),
    "worker/image/patchyard-guest-run": (
        "229346fb350297b298c1b752188c0f7762ef9d5de77572156843070fecfcc654"
    ),
}
HEX64 = re.compile(r"[0-9a-f]{64}")
REQUEST_ID = re.compile(r"req_[A-Za-z0-9]+")
RUN_ID = re.compile(r"anthropic-l3-[0-9]{8}-[0-9a-f]{10}")
KID = re.compile(r"patchyard-[0-9a-f]{16}")
EXPECTED_ERROR_SHAPE = {
    "top_level_keys": ["error", "request_id", "type"],
    "error_value_type": "object",
    "error_object_keys": ["message", "type"],
}
UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z"
)
DISCARDED_FIELD_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,128}")


CHECKER = RUNTIME.checker_runtime(
    identity="Anthropic expiry checker",
    modules=(hashlib, json, re, sysconfig, types),
    repo=REPO,
    timestamp_pattern=UTC_TIMESTAMP,
    secret_names=frozenset({"secret", "access_token", "assertion", "identity_token", "authorization"}),
)
EvidenceJsonError = RUNTIME.EvidenceJsonError
digest = RUNTIME.digest
load_json_file = CHECKER.load_json_file
reject_json_constant = CHECKER.reject_json_constant
reject_duplicate_keys = CHECKER.reject_duplicate_keys
is_within = RUNTIME.is_within
isolation_errors = CHECKER.isolation_errors
parse_time = CHECKER.parse_time
exact_keys = RUNTIME.exact_keys
secret_named_key = CHECKER.secret_named_key

def validate_discarded_fields(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, list) or any(
        not isinstance(field, str)
        or DISCARDED_FIELD_NAME.fullmatch(field) is None
        or field.startswith("sk-ant-")
        for field in value
    ):
        errors.append(f"{label} has unsafe discarded response field names")
        return
    if value != sorted(set(value)):
        errors.append(f"{label} has unsafe discarded response field names")


def validate_key(value: Any, errors: list[str]) -> None:
    if not exact_keys(value, {"kid", "jwk_thumbprint_sha256"}, "signing key", errors):
        return
    if KID.fullmatch(str(value.get("kid", ""))) is None:
        errors.append("signing key ID is malformed")
    if HEX64.fullmatch(str(value.get("jwk_thumbprint_sha256", ""))) is None:
        errors.append("signing key thumbprint is malformed")


def validate_issuance(
    value: Any, policy: dict[str, Any], errors: list[str]
) -> tuple[datetime | None, datetime | None, datetime | None]:
    expected = {
        "endpoint",
        "http_status",
        "request_id",
        "provider_date",
        "observed_at",
        "issued_at",
        "expires_at",
        "expires_in",
        "token_type",
        "scope",
        "discarded_response_fields",
        "service_account_id",
        "rule_id",
        "workspace_id",
    }
    if not exact_keys(value, expected, "issuance", errors):
        return None, None, None
    if value.get("endpoint") != "/v1/oauth/token" or value.get("http_status") != 200:
        errors.append("issuance is not a successful provider exchange")
    if REQUEST_ID.fullmatch(str(value.get("request_id", ""))) is None:
        errors.append("issuance request ID is malformed")
    if value.get("token_type") != "Bearer" or value.get("scope") != "workspace:inference":
        errors.append("issuance did not return the bounded bearer contract")
    validate_discarded_fields(
        value.get("discarded_response_fields"), "issuance", errors
    )
    for field, section in (
        ("service_account_id", "service_account"),
        ("rule_id", "rule"),
        ("workspace_id", "workspace"),
    ):
        if value.get(field) != policy[section]["id"]:
            errors.append(f"issuance {field} differs from policy")
    issued = parse_time(value.get("issued_at"), "issuance issued_at", errors)
    expires = parse_time(value.get("expires_at"), "issuance expires_at", errors)
    observed = parse_time(value.get("observed_at"), "issuance observed_at", errors)
    provider_date = parse_time(value.get("provider_date"), "issuance provider_date", errors)
    lifetime = value.get("expires_in")
    if not isinstance(lifetime, int) or isinstance(lifetime, bool) or not 60 <= lifetime <= 300:
        errors.append("issuance lifetime is not one to five minutes")
    elif issued is not None and expires is not None:
        if int((expires - issued).total_seconds()) != lifetime:
            errors.append("issuance timestamps differ from the recorded lifetime")
    if issued is not None and provider_date is not None and issued != provider_date:
        errors.append("issuance time is not the provider Date observation")
    if issued is not None and observed is not None and issued > observed:
        errors.append("issuance provider Date follows its local observation")
    return issued, expires, observed


def validate_positive(value: Any, errors: list[str]) -> tuple[datetime | None, datetime | None]:
    expected = {
        "endpoint",
        "http_status",
        "request_id",
        "provider_date",
        "observed_at",
        "model_id",
    }
    if not exact_keys(value, expected, "positive control", errors):
        return None, None
    if value.get("endpoint") != "/v1/models?limit=1" or value.get("http_status") != 200:
        errors.append("positive control is not a successful Models call")
    if REQUEST_ID.fullmatch(str(value.get("request_id", ""))) is None:
        errors.append("positive-control request ID is malformed")
    if not isinstance(value.get("model_id"), str) or not value["model_id"]:
        errors.append("positive control did not identify a model")
    provider = parse_time(value.get("provider_date"), "positive provider_date", errors)
    observed = parse_time(value.get("observed_at"), "positive observed_at", errors)
    if provider is not None and observed is not None and provider > observed:
        errors.append("positive provider Date follows its local observation")
    return provider, observed


def validate_denial(
    value: Any, errors: list[str]
) -> tuple[datetime | None, datetime | None, datetime | None, bool | None]:
    expected = {
        "source",
        "endpoint",
        "http_status",
        "request_id",
        "request_id_supplied",
        "provider_date",
        "request_started_at",
        "observed_at",
        "error_type",
        "response_shape",
    }
    if not exact_keys(value, expected, "expiry denial", errors):
        return None, None, None, None
    if value.get("source") != "anthropic_http_response":
        errors.append("expiry denial is not a provider HTTP response")
    if value.get("endpoint") != "/v1/models?limit=1":
        errors.append("expiry denial used the wrong endpoint")
    if value.get("http_status") != 401 or value.get("error_type") != "authentication_error":
        errors.append("expiry denial is not the exact provider authentication denial")
    request_id = value.get("request_id")
    request_id_supplied = value.get("request_id_supplied")
    if not isinstance(request_id_supplied, bool):
        errors.append("expiry denial does not explicitly record request-ID presence")
        request_id_supplied = None
    elif request_id_supplied:
        if REQUEST_ID.fullmatch(str(request_id or "")) is None:
            errors.append("expiry-denial request ID is malformed")
    elif request_id is not None:
        errors.append("expiry denial claims request-ID absence while carrying an ID")
    if value.get("response_shape") != EXPECTED_ERROR_SHAPE:
        errors.append("expiry denial has an unexpected sanitized response shape")
    provider = parse_time(value.get("provider_date"), "denial provider_date", errors)
    requested = parse_time(
        value.get("request_started_at"), "denial request_started_at", errors
    )
    observed = parse_time(value.get("observed_at"), "denial observed_at", errors)
    if provider is not None and observed is not None and provider > observed:
        errors.append("denial provider Date follows its local observation")
    if requested is not None and observed is not None and requested > observed:
        errors.append("denial control-plane UTC bracket is reversed")
    return provider, requested, observed, request_id_supplied


def validate_evidence(result: Any, policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_top = {
        "schema_version",
        "provider",
        "qualification_requirement",
        "authorization_ruling",
        "run_id",
        "signing_key",
        "issuance",
        "positive_control",
        "expiry_denial",
        "credential_removed_at",
        "policy_sha256",
        "lifecycle_harness_sha256",
    }
    if not exact_keys(result, expected_top, "expiry fixture", errors):
        return errors
    if result.get("schema_version") != 1 or result.get("provider") != "anthropic":
        errors.append("expiry fixture identity differs")
    if result.get("qualification_requirement") != "credential-expiry-denial":
        errors.append("expiry fixture names the wrong requirement")
    if result.get("authorization_ruling") != "A113":
        errors.append("expiry fixture names the wrong authorization")
    if RUN_ID.fullmatch(str(result.get("run_id", ""))) is None:
        errors.append("expiry fixture run ID is malformed")
    if result.get("policy_sha256") != digest(POLICY_PATH):
        errors.append("expiry fixture is stale for the WIF policy")
    if result.get("lifecycle_harness_sha256") != digest(HARNESS_PATH):
        errors.append("expiry fixture is stale for the lifecycle harness")
    validate_key(result.get("signing_key"), errors)
    issued, expires, exchange_observed = validate_issuance(
        result.get("issuance"), policy, errors
    )
    positive_provider, positive_observed = validate_positive(
        result.get("positive_control"), errors
    )
    denial_provider, denial_requested, denial_observed, denial_has_request_id = (
        validate_denial(result.get("expiry_denial"), errors)
    )
    removed = parse_time(result.get("credential_removed_at"), "credential_removed_at", errors)
    if all(value is not None for value in (issued, expires, positive_provider, denial_provider)):
        assert issued is not None and expires is not None
        assert positive_provider is not None and denial_provider is not None
        if not issued <= positive_provider < expires <= denial_provider:
            errors.append("provider timestamps do not order positive-before-expiry-before-denial")
    if expires is not None and denial_requested is not None:
        if not expires < denial_requested:
            errors.append(
                "denial control-plane UTC bracket does not begin strictly after expiry"
            )
    if all(
        value is not None
        for value in (
            exchange_observed,
            positive_observed,
            denial_requested,
            denial_observed,
            removed,
        )
    ):
        assert exchange_observed is not None and positive_observed is not None
        assert denial_requested is not None and denial_observed is not None
        assert removed is not None
        if not (
            exchange_observed
            < positive_observed
            < denial_requested
            <= denial_observed
            <= removed
        ):
            errors.append("capture timestamps are out of lifecycle order")
    request_ids = []
    sections = ["issuance", "positive_control"]
    if denial_has_request_id is True:
        sections.append("expiry_denial")
    for section in sections:
        value = result.get(section)
        if isinstance(value, dict) and isinstance(value.get("request_id"), str):
            request_ids.append(value["request_id"])
    expected_request_ids = 3 if denial_has_request_id is True else 2
    if (
        len(request_ids) != expected_request_ids
        or len(set(request_ids)) != expected_request_ids
    ):
        errors.append(
            "expiry fixture does not bind every distinct identified provider request"
        )
    forbidden = secret_named_key(result)
    if forbidden is not None:
        errors.append(f"expiry fixture contains forbidden credential field: {forbidden}")
    serialized = json.dumps(result, sort_keys=True)
    if re.search(r"sk-ant-[A-Za-z0-9_-]+", serialized):
        errors.append("expiry fixture contains an Anthropic credential")
    if re.search(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", serialized):
        errors.append("expiry fixture contains a JWT assertion")
    return errors


def static_errors() -> tuple[list[str], dict[str, Any]]:
    errors = isolation_errors()
    for relative, expected in PROTECTED_SOURCES.items():
        path = REPO / relative
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            errors.append(f"protected host contract differs: {relative}")
    if not HARNESS_PATH.is_file() or HARNESS_PATH.is_symlink():
        errors.append("root-only lifecycle harness is missing or a symlink")
    else:
        harness = HARNESS_PATH.read_text()
        for required in (
            "provider did not deny the expired bearer exactly once",
            '"source": "anthropic_http_response"',
            '"request_id_supplied": request_id is not None',
            '"request_started_at": response["requested_at"]',
            '"expires_in": expires_in',
            'token = ""',
            "os.O_EXCL | os.O_NOFOLLOW",
            '"status": "in_progress"',
            '"partial_evidence": partial_evidence',
            'STAGING_ROOT = Path("/run/patchyard-anthropic")',
            'if filesystem != "tmpfs"',
        ):
            if required not in harness:
                errors.append(f"expiry harness is missing: {required}")
        for forbidden in PROTECTED_SOURCES:
            if forbidden in harness:
                errors.append(f"expiry harness invokes protected source: {forbidden}")
    policy = load_json_file(POLICY_PATH)
    providers = load_json_file(REPO / "policy/provider-egress.json")["providers"]
    if len(providers) != 13:
        errors.append("provider egress policy does not contain 13 providers")
    return errors, policy


def main() -> int:
    errors, policy = static_errors()
    evidence_path = RESULT_PATH
    allow_missing = False
    arguments = sys.argv[1:]
    while arguments:
        argument = arguments.pop(0)
        if argument == "--allow-missing-results":
            allow_missing = True
        elif argument == "--evidence" and arguments:
            evidence_path = Path(arguments.pop(0))
        else:
            errors.append(f"unknown checker argument: {argument}")
    if not evidence_path.exists():
        if not allow_missing:
            errors.append("committed Anthropic expiry result is missing")
    else:
        try:
            if not evidence_path.is_file() or evidence_path.is_symlink():
                raise EvidenceJsonError("evidence is not a regular non-symlink file")
            result = load_json_file(evidence_path)
        except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
            errors.append(f"cannot read expiry evidence: {error}")
        else:
            errors.extend(validate_evidence(result, policy))
    if errors:
        print("Anthropic expiry check: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    status = "with live result" if evidence_path.exists() else "static preflight"
    print(f"Anthropic expiry check: pass ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
