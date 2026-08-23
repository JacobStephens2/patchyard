#!/usr/bin/env python3
"""Check the OpenAI A130 crash-cleanup source and Result contract."""

from __future__ import annotations

import ast
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
CHECKER_RUNTIME_SHA256 = "fcd9d4c5513d8614e20dc4e2fada3da60326ff85745a989b3d4313497b0622f6"
_checker_runtime_source = CHECKER_RUNTIME_PATH.read_bytes()
if (
    CHECKER_RUNTIME_PATH.is_symlink()
    or hashlib.sha256(_checker_runtime_source).hexdigest()
    != CHECKER_RUNTIME_SHA256
):
    raise RuntimeError("factory checker runtime differs from its exact binding")
RUNTIME = types.ModuleType("factory_checker_runtime_check_openai_wif_crash_cleanup")
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
CRASH_ADAPTER_PATH = REPO / "tools/openai-wif-crash-cleanup.py"
RESULT_PATH = REPO / "research/isolation/results/openai-crash-cleanup.json"
PROVIDER_POLICY_PATH = REPO / "policy/provider-egress.json"
OBSERVED_ISSUANCE_PATH = (
    REPO / "research/isolation/results/openai-first-token-exchange.json"
)
POLICY_SHA256 = "87cf13bb136ed9a365bd14822a14d4808a6ef585ce1c278b926fa173d1152e5f"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
OBSERVED_ISSUANCE_SHA256 = (
    "0952e4f7bf693fd412292ce6ee947efdf2a26c590a3b0acc922ea10ca1124891"
)
# A144: the signing-identity split re-pointed the adapter's key path without
# re-producing the banked Result, so the pre-split digests stay acceptable.
SUPERSEDES_CHECKER_SHA256 = (
    "5e5b2c124d3cab03ac6c20418568a044"
    "9d75c1b72ad8b747d57c37fec941e465",
)
SUPERSEDES_SOURCE_SHA256 = {
    "tools/openai-wif-crash-cleanup.py": (
        "6878691254bffdbc40e2b803538b3e775ae892e2fa7602b2e4d2168a4b2d0866",
    ),
}
CHECKER_PATHS = (
    REPO / "tools/check-openai-wif-issuance.py",
    REPO / "tools/check-openai-wif-expiry.py",
    REPO / "tools/check-openai-wif-crash-cleanup.py",
)
RUN_ID = re.compile(r"openai-crash-[0-9]{8}-[0-9a-f]{10}")
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
MAX_INPUT_BYTES = 8_000_000
MAX_SCAN_FILES = 128
MAX_SCAN_FILE_BYTES = 1_000_000
MAX_SCAN_TOTAL_BYTES = 8_000_000
MAX_MEMORY_REGIONS = 1024
MAX_MEMORY_BYTES = 536_870_912
MAX_CREDENTIAL_BYTES = 1_000_000
SEARCH_CONTRACT_VERSION = "a130-openai-run-stage-process-image-v1"
SEARCH_MATERIAL_CLASSES = ["jwt_assertion", "openai_bearer", "private_key"]
RESPONSE_PREDICATE = {
    "enforced": False,
    "basis": "no-observed-openai-crash-cleanup-exchange-response",
}
CONTROL_PLANE_PROVENANCE = {
    "control_plane_mutation_claimed": False,
    "mutation_receipt_obtained": False,
    "attestation_required": False,
}
TERMINAL_FIELDS = {
    "failed_at",
    "failure_phase",
    "failure_reason",
    "failure_type",
    "partial_evidence",
    "post_failure_state",
}
RESULT_SHAPE = RUNTIME.result_shape("openai-crash-cleanup")
RESULT_KEYS = RESULT_SHAPE.keys("result")
FIXTURE_KEYS = RESULT_SHAPE.keys("fixture")
SOURCE_KEYS = RESULT_SHAPE.keys("source")
CHECKPOINT_KEYS = RESULT_SHAPE.keys("checkpoint")
SIGNING_KEY_KEYS = RESULT_SHAPE.keys("signing_key")
ASSERTION_KEYS = RESULT_SHAPE.keys("assertion")
EXCHANGE_REQUEST_KEYS = RESULT_SHAPE.keys("exchange_request")
RESPONSE_KEYS = RESULT_SHAPE.keys("response")
FIELD_DESCRIPTOR_KEYS = RESULT_SHAPE.keys("field_descriptor")
JSON_VALUE_TYPES = {"null", "boolean", "integer", "number", "string", "object", "array"}
FINGERPRINT_KEYS = RESULT_SHAPE.keys("fingerprint")
SEARCH_KEYS = RESULT_SHAPE.keys("search")
MATCH_KEYS = RESULT_SHAPE.keys("match")
KILL_KEYS = RESULT_SHAPE.keys("kill")


CHECKER = RUNTIME.checker_runtime(
    identity="OpenAI crash-cleanup checker",
    modules=(ast, hashlib, json, re, sysconfig, types),
    repo=REPO,
    timestamp_pattern=UTC_TIMESTAMP,
    secret_names=frozenset({"secret", "access_token", "subject_token", "identity_token", "authorization", "private_key", "api_key"}),
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

def encoded_digest(value: dict[str, Any]) -> str:
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    return hashlib.sha256(encoded).hexdigest()


def canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def valid_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def valid_positive_int(value: Any) -> bool:
    return valid_nonnegative_int(value) and value > 0


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
        }
    except (KeyError, TypeError):
        errors.append("OpenAI WIF policy lacks required crash-cleanup fields")
        return {}
    expected = {
        "provider": "openai",
        "issuer_url": "https://factory.example.com/workload-identity",
        "audience": "https://api.openai.com",
        "identity_provider_id": "idp_DlzD7RlQXgXxd1VSG2V93eEU",
        "service_account_id": ISSUANCE_ERA_SERVICE_ACCOUNT_ID,
        "subject": "patchyard-control-plane",
        "maximum_lifetime": 300,
    }
    if observed != expected:
        errors.append("OpenAI WIF policy fields differ from crash-cleanup contract")
    return observed


def validate_source(value: Any, label: str, errors: list[str]) -> None:
    if not exact_keys(value, SOURCE_KEYS, f"{label} source binding", errors):
        return
    accepted_adapter = {digest(CRASH_ADAPTER_PATH)}
    accepted_adapter.update(SUPERSEDES_SOURCE_SHA256["tools/openai-wif-crash-cleanup.py"])
    if (
        value.get("policy_sha256") != digest(POLICY_PATH)
        or value.get("base_harness_sha256") != digest(BASE_HARNESS_PATH)
        or value.get("crash_adapter_sha256") not in accepted_adapter
    ):
        errors.append(f"{label} source binding differs from current sources")


def validate_field_descriptors(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{label} is not a list")
        return
    names = []
    for item in value:
        if not exact_keys(item, FIELD_DESCRIPTOR_KEYS, f"{label} field", errors):
            continue
        recorded = item.get("name_recorded")
        name = item.get("name")
        if recorded is True:
            if not isinstance(name, str) or SAFE_FIELD_NAME.fullmatch(name) is None:
                errors.append(f"{label} contains an unsafe field name")
            else:
                names.append(name)
        elif recorded is False:
            if name is not None:
                errors.append(f"{label} retained an unsafe field name")
        else:
            errors.append(f"{label} field-name provenance is not boolean")
        if item.get("value_type") not in JSON_VALUE_TYPES:
            errors.append(f"{label} contains an unknown JSON value type")
    if names != sorted(names) or len(names) != len(set(names)):
        errors.append(f"{label} field names are not unique and sorted")


def validate_response(
    value: Any, *, synthetic: bool, errors: list[str]
) -> tuple[datetime | None, datetime | None]:
    if not exact_keys(value, RESPONSE_KEYS, "crash exchange response", errors):
        return None, None
    expected_source = (
        "synthetic_observed_response_shape" if synthetic else "openai_http_response"
    )
    if value.get("source") != expected_source:
        errors.append("crash exchange response source differs")
    status = value.get("http_status")
    if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        errors.append("crash exchange HTTP status is malformed")
    requested = parse_time(
        value.get("request_started_at"), "crash exchange request start", errors
    )
    observed = parse_time(value.get("observed_at"), "crash exchange observed_at", errors)
    provider_date = value.get("provider_date")
    if provider_date is not None:
        parse_time(provider_date, "crash exchange provider date", errors)
    supplied = value.get("request_id_supplied")
    request_id = value.get("request_id")
    if supplied is not True and supplied is not False:
        errors.append("crash exchange request-ID presence is not boolean")
    if supplied is False and request_id is not None:
        errors.append("crash exchange retained an absent request ID")
    if not safe_optional_string(request_id):
        errors.append("crash exchange request ID is not safely bounded")
    if not safe_optional_string(value.get("content_type")):
        errors.append("crash exchange content type is not safely bounded")
    body_bytes = value.get("body_bytes")
    if not valid_nonnegative_int(body_bytes) or body_bytes > 1_000_000:
        errors.append("crash exchange byte count is outside the bound")
    if value.get("body_format") != "json_object":
        errors.append("crash exchange did not record a JSON object")
    shape = value.get("response_shape")
    if exact_keys(
        shape,
        {"body_kind", "top_level_fields", "error_fields"},
        "crash exchange response shape",
        errors,
    ):
        if shape.get("body_kind") != "json_object":
            errors.append("crash exchange body kind differs")
        validate_field_descriptors(
            shape.get("top_level_fields"), "crash top-level response shape", errors
        )
        validate_field_descriptors(
            shape.get("error_fields"), "crash error response shape", errors
        )
    if value.get("access_token_supplied") is not True:
        errors.append("crash checkpoint does not establish a live bearer")
    expires_in = value.get("expires_in")
    if expires_in is not None and not valid_nonnegative_int(expires_in):
        errors.append("crash exchange lifetime observation is malformed")
    if not safe_optional_string(value.get("error_type")):
        errors.append("crash exchange error type is not safely bounded")
    if requested is not None and observed is not None and requested > observed:
        errors.append("crash exchange response predates its request")
    return requested, observed


def validate_checkpoint(
    value: Any,
    result: dict[str, Any],
    *,
    synthetic: bool,
    errors: list[str],
) -> tuple[int | None, int | None, datetime | None, datetime | None]:
    if not exact_keys(value, CHECKPOINT_KEYS, "crash checkpoint", errors):
        return None, None, None, None
    if value.get("schema_version") != 1 or value.get("provider") != "openai":
        errors.append("crash checkpoint identity differs")
    if value.get("run_id") != result.get("run_id"):
        errors.append("crash checkpoint run ID differs")
    if value.get("phase") != "bearer_live_before_terminal_write":
        errors.append("SIGKILL checkpoint is not the live-credential boundary")
    if value.get("assertion_live") is not True or value.get("bearer_live") is not True:
        errors.append("SIGKILL checkpoint does not hold both live credentials")
    if value.get("terminal_record_written") is not False:
        errors.append("SIGKILL checkpoint follows a terminal record")
    if value.get("core_dump_limits") != [0, 0] or value.get("swap_entries") != 0:
        errors.append("credential process persistence guards differ")
    pid = value.get("target_pid")
    start_ticks = value.get("target_start_ticks")
    if not valid_positive_int(pid) or not valid_positive_int(start_ticks):
        errors.append("crash checkpoint process identity is malformed")
        pid = start_ticks = None
    signing_key = value.get("signing_key")
    if exact_keys(signing_key, SIGNING_KEY_KEYS, "crash signing key", errors):
        expected_key = {
            "kid_derived_from_public_der": True,
            "stable_source_preserved": True,
            "copied_to_run_stage": False,
            "private_key_bytes_loaded_by_adapter": False,
        }
        for field, expected in expected_key.items():
            if signing_key.get(field) != expected:
                errors.append(f"crash signing-key {field} differs")
        if HEX64.fullmatch(str(signing_key.get("jwk_thumbprint_sha256", ""))) is None:
            errors.append("crash signing-key thumbprint is malformed")
    assertion = value.get("assertion")
    issued = minted = expires = None
    if exact_keys(assertion, ASSERTION_KEYS, "crash assertion", errors):
        if assertion.get("lifetime_seconds") != 300:
            errors.append("crash assertion lifetime differs")
        issued = parse_time(assertion.get("issued_at"), "crash assertion issued_at", errors)
        minted = parse_time(assertion.get("minted_at"), "crash assertion minted_at", errors)
        expires = parse_time(assertion.get("expires_at"), "crash assertion expires_at", errors)
        if issued is not None and expires is not None:
            if int((expires - issued).total_seconds()) != 300:
                errors.append("crash assertion timestamps do not encode five minutes")
        if issued is not None and minted is not None and issued > minted:
            errors.append("crash assertion issued_at follows mint")
        if minted is not None and expires is not None and not minted < expires:
            errors.append("crash assertion was not live at mint")
    request = value.get("exchange_request")
    request_time = None
    if exact_keys(request, EXCHANGE_REQUEST_KEYS, "crash exchange request", errors):
        if request.get("endpoint") != "https://auth.openai.com/oauth/token":
            errors.append("crash exchange endpoint differs")
        if request.get("attempt_count") != 1:
            errors.append("crash path did not attempt exactly one exchange")
        request_time = parse_time(
            request.get("requested_at"), "crash exchange requested_at", errors
        )
    response_request, response_time = validate_response(
        value.get("exchange_response"), synthetic=synthetic, errors=errors
    )
    if request_time is not None and response_request is not None:
        if request_time != response_request:
            errors.append("crash request and response name different start times")
    fingerprints = value.get("material_fingerprints")
    if not isinstance(fingerprints, list) or len(fingerprints) != 2:
        errors.append("crash material fingerprint set differs")
    else:
        classes = []
        digests = []
        for fingerprint in fingerprints:
            if not exact_keys(
                fingerprint, FINGERPRINT_KEYS, "credential fingerprint", errors
            ):
                continue
            classes.append(fingerprint.get("material_class"))
            digests.append(fingerprint.get("sha256"))
            if HEX64.fullmatch(str(fingerprint.get("sha256", ""))) is None:
                errors.append("credential fingerprint digest is malformed")
            length = fingerprint.get("byte_length")
            if not valid_positive_int(length) or length > MAX_CREDENTIAL_BYTES:
                errors.append("credential fingerprint byte length is outside the bound")
        if classes != ["jwt_assertion", "openai_bearer"]:
            errors.append("crash material fingerprint classes differ")
        if len(digests) == 2 and len(set(digests)) != 2:
            errors.append("assertion and bearer fingerprints are not distinct")
    if HEX64.fullmatch(str(value.get("attempt_sha256", ""))) is None:
        errors.append("crash checkpoint attempt digest is malformed")
    checkpoint_time = parse_time(
        value.get("observed_at"), "crash checkpoint observed_at", errors
    )
    ordered = [minted, request_time, response_time, checkpoint_time]
    if all(item is not None for item in ordered):
        assert all(isinstance(item, datetime) for item in ordered)
        if not all(left <= right for left, right in zip(ordered, ordered[1:])):
            errors.append("crash checkpoint UTC observations are out of order")
    if expires is not None and checkpoint_time is not None and not checkpoint_time < expires:
        errors.append("crash checkpoint was not inside the credential lifetime")
    validate_source(value.get("source"), "crash checkpoint", errors)
    return pid, start_ticks, expires, checkpoint_time


def expected_search_contract(run_id: str, pid: int, start_ticks: int) -> dict[str, Any]:
    return {
        "version": SEARCH_CONTRACT_VERSION,
        "stage_path": f"/run/patchyard-openai/{run_id}",
        "target_pid": pid,
        "target_start_ticks": start_ticks,
        "file_scope": "all-recursive-regular-files-no-symlinks",
        "process_image_scope": "target-readable-mappings-when-present",
        "material_classes": SEARCH_MATERIAL_CLASSES,
        "max_files": MAX_SCAN_FILES,
        "max_file_bytes": MAX_SCAN_FILE_BYTES,
        "max_total_file_bytes": MAX_SCAN_TOTAL_BYTES,
        "max_memory_regions": MAX_MEMORY_REGIONS,
        "max_memory_bytes": MAX_MEMORY_BYTES,
    }


def validate_search(
    value: Any,
    result: dict[str, Any],
    pid: int | None,
    start_ticks: int | None,
    *,
    positive: bool,
    errors: list[str],
) -> datetime | None:
    label = "positive control" if positive else "post-kill search"
    if not exact_keys(value, SEARCH_KEYS, label, errors):
        return None
    if value.get("schema_version") != 1 or value.get("provider") != "openai":
        errors.append(f"{label} identity differs")
    if value.get("run_id") != result.get("run_id"):
        errors.append(f"{label} run ID differs")
    if value.get("event_type") != "credential_surface_search":
        errors.append(f"{label} is not the fixed credential search")
    if pid is not None and start_ticks is not None:
        contract = expected_search_contract(str(result.get("run_id")), pid, start_ticks)
        if value.get("search_contract") != contract:
            errors.append(f"{label} searched a different host surface")
        elif value.get("search_contract_sha256") != canonical_digest(contract):
            errors.append(f"{label} search instrument digest differs")
    for field, maximum in (
        ("files_examined", MAX_SCAN_FILES),
        ("file_bytes_examined", MAX_SCAN_TOTAL_BYTES),
        ("memory_regions_examined", MAX_MEMORY_REGIONS),
        ("memory_bytes_examined", MAX_MEMORY_BYTES),
        ("unreadable_memory_regions", MAX_MEMORY_REGIONS),
    ):
        observed = value.get(field)
        if not valid_nonnegative_int(observed) or observed > maximum:
            errors.append(f"{label} {field} is outside the search bound")
    if value.get("swap_entries") != 0 or value.get("scanner_core_dump_limits") != [0, 0]:
        errors.append(f"{label} scanner persistence guards differ")
    matches = value.get("matches")
    if not isinstance(matches, list):
        errors.append(f"{label} matches are not a list")
        matches = []
    for match in matches:
        if not exact_keys(match, MATCH_KEYS, f"{label} match", errors):
            continue
        if match.get("material_class") not in SEARCH_MATERIAL_CLASSES:
            errors.append(f"{label} match has an unknown material class")
        if match.get("surface") not in {"process_image", "run_stage"}:
            errors.append(f"{label} match has an unknown surface")
        if not isinstance(match.get("location"), str) or not match.get("location"):
            errors.append(f"{label} match location is malformed")
        if not valid_positive_int(match.get("occurrences")):
            errors.append(f"{label} match count is malformed")
    if positive:
        expected_matches = [
            {
                "material_class": "jwt_assertion",
                "surface": "process_image",
                "location": "target-process-image",
                "occurrences": 1,
            },
            {
                "material_class": "openai_bearer",
                "surface": "process_image",
                "location": "target-process-image",
                "occurrences": 1,
            },
        ]
        expected_matches.sort(
            key=lambda item: (
                item["surface"], item["location"], item["material_class"]
            )
        )
        if value.get("credential_material_found") is not True:
            errors.append("positive control found no credential material")
        if value.get("material_classes_found") != ["jwt_assertion", "openai_bearer"]:
            errors.append("positive control did not find assertion and bearer")
        if matches != expected_matches:
            errors.append("positive control did not isolate the live process image")
        if value.get("target_process_present") is not True:
            errors.append("positive control did not observe the credential process")
        if value.get("scan_socket_used") is not True:
            errors.append("positive control did not use the live scan channel")
        if not valid_positive_int(value.get("memory_regions_examined")) or not valid_positive_int(
            value.get("memory_bytes_examined")
        ):
            errors.append("positive control did not inspect the process image")
    else:
        if value.get("credential_material_found") is not False:
            errors.append("post-kill search recovered credential material")
        if value.get("material_classes_found") != [] or matches != []:
            errors.append("post-kill search contains credential matches")
        if value.get("target_process_present") is not False:
            errors.append("post-kill search found the credential process")
        if value.get("scan_socket_used") is not False:
            errors.append("post-kill search used a credential channel")
        if value.get("memory_regions_examined") != 0 or value.get(
            "memory_bytes_examined"
        ) != 0:
            errors.append("post-kill search claims a surviving process image")
    validate_source(value.get("source"), label, errors)
    return parse_time(value.get("observed_at"), f"{label} observed_at", errors)


def validate_kill(
    value: Any,
    result: dict[str, Any],
    pid: int | None,
    start_ticks: int | None,
    errors: list[str],
) -> datetime | None:
    if not exact_keys(value, KILL_KEYS, "SIGKILL observation", errors):
        return None
    if value.get("schema_version") != 1 or value.get("provider") != "openai":
        errors.append("SIGKILL observation identity differs")
    if value.get("run_id") != result.get("run_id"):
        errors.append("SIGKILL observation run ID differs")
    if value.get("event_type") != "credential_process_sigkill_observed":
        errors.append("credential process has no SIGKILL observation")
    if value.get("target_pid") != pid or value.get("target_start_ticks") != start_ticks:
        errors.append("SIGKILL targeted a different process identity")
    if (
        value.get("signal_name") != "SIGKILL"
        or value.get("signal_number") != 9
        or value.get("child_returncode") != -9
    ):
        errors.append("credential process was not terminated by SIGKILL")
    if value.get("supervisor_timed_out") is not False:
        errors.append("SIGKILL came from the supervisor timeout path")
    if value.get("target_process_present") is not False:
        errors.append("SIGKILL target remains present")
    if value.get("scan_socket_present_after_cleanup") is not False:
        errors.append("credential scan socket remains after SIGKILL")
    if value.get("scan_socket_cleanup_required") not in {True, False}:
        errors.append("scan socket cleanup observation is not boolean")
    for field in ("checkpoint_sha256", "positive_control_sha256", "attempt_sha256"):
        if HEX64.fullmatch(str(value.get(field, ""))) is None:
            errors.append(f"SIGKILL observation {field} is malformed")
    validate_source(value.get("source"), "SIGKILL observation", errors)
    return parse_time(value.get("observed_at"), "SIGKILL observed_at", errors)


def validate_in_progress(
    value: Any, result: dict[str, Any], checkpoint: Any, kill: Any, errors: list[str]
) -> datetime | None:
    expected = {
        "path",
        "record",
        "sha256_at_checkpoint",
        "sha256_after_sigkill",
        "sha256_at_collection",
        "unchanged",
        "terminal_fields_present",
    }
    if not exact_keys(value, expected, "in-progress record observation", errors):
        return None
    expected_path = f"/run/patchyard-openai/{result.get('run_id')}/crash-attempt.json"
    if value.get("path") != expected_path:
        errors.append("in-progress record path differs from the exact run stage")
    record = value.get("record")
    record_keys = {
        "schema_version",
        "provider",
        "status",
        "action",
        "run_id",
        "started_at",
        "source",
    }
    started = None
    if exact_keys(record, record_keys, "in-progress record", errors):
        if record.get("schema_version") != 1 or record.get("provider") != "openai":
            errors.append("in-progress record identity differs")
        if record.get("status") != "in_progress":
            errors.append("abrupt-death record was completed or relabelled")
        if record.get("action") != "crash-cleanup-probe":
            errors.append("in-progress record names a different action")
        if record.get("run_id") != result.get("run_id"):
            errors.append("in-progress record run ID differs")
        if TERMINAL_FIELDS.intersection(record):
            errors.append("in-progress record carries terminal fields")
        validate_source(record.get("source"), "in-progress record", errors)
        started = parse_time(record.get("started_at"), "in-progress started_at", errors)
        expected_digest = encoded_digest(record)
        digests = [
            value.get("sha256_at_checkpoint"),
            value.get("sha256_after_sigkill"),
            value.get("sha256_at_collection"),
        ]
        if digests != [expected_digest, expected_digest, expected_digest]:
            errors.append("in-progress record was completed or relabelled")
        if isinstance(checkpoint, dict) and checkpoint.get("attempt_sha256") != expected_digest:
            errors.append("checkpoint binds a different in-progress record")
        if isinstance(kill, dict) and kill.get("attempt_sha256") != expected_digest:
            errors.append("SIGKILL observation binds a different in-progress record")
    if value.get("unchanged") is not True or value.get("terminal_fields_present") != []:
        errors.append("in-progress record exposes a terminal relabelling path")
    return started


def validate_checker_rejections(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list) or len(value) != len(CHECKER_PATHS):
        errors.append("in-progress checker rejection set differs")
        return
    expected_names = [path.name for path in CHECKER_PATHS]
    if [item.get("checker") for item in value if isinstance(item, dict)] != expected_names:
        errors.append("in-progress checker rejection set differs")
    for item, checker in zip(value, CHECKER_PATHS):
        if not exact_keys(
            item,
            {"checker", "checker_sha256", "exit_code", "accepted"},
            "in-progress checker observation",
            errors,
        ):
            continue
        if item.get("checker") != checker.name:
            errors.append("in-progress checker name differs")
        if item.get("checker_sha256") not in checker_binding_digests(
            checker, errors
        ):
            errors.append(f"in-progress checker binding differs: {checker.name}")
        if item.get("exit_code") != 1 or item.get("accepted") is not False:
            errors.append(f"a checker accepted in-progress input: {checker.name}")


def checker_binding_digests(path: Path, errors: list[str]) -> set[str]:
    accepted = {digest(path)}
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except (OSError, SyntaxError, ValueError) as error:
        errors.append(f"cannot inspect checker supersession: {path.name}: {error}")
        return accepted
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or not any(
            isinstance(target, ast.Name)
            and target.id == "SUPERSEDES_CHECKER_SHA256"
            for target in statement.targets
        ):
            continue
        try:
            declared = ast.literal_eval(statement.value)
        except (ValueError, TypeError, SyntaxError):
            errors.append(f"checker supersession is malformed: {path.name}")
            continue
        if not isinstance(declared, tuple) or any(
            not isinstance(value, str) or HEX64.fullmatch(value) is None
            for value in declared
        ):
            errors.append(f"checker supersession is malformed: {path.name}")
            continue
        accepted.update(declared)
    return accepted


def credential_errors(value: Any) -> list[str]:
    errors: list[str] = []
    forbidden = secret_named_key(value)
    if forbidden is not None:
        errors.append(
            f"OpenAI crash-cleanup Result contains forbidden credential field: {forbidden}"
        )
    serialized = json.dumps(value, sort_keys=True)
    if (
        JWT.search(serialized)
        or OPENAI_KEY.search(serialized)
        or BEARER.search(serialized)
        or PRIVATE_KEY.search(serialized)
    ):
        errors.append("OpenAI crash-cleanup Result carries credential-shaped material")
    return errors


def validate_common(result: Any, *, synthetic: bool) -> list[str]:
    errors: list[str] = []
    expected_keys = RESULT_KEYS | (FIXTURE_KEYS if synthetic else set())
    if not exact_keys(result, expected_keys, "OpenAI crash-cleanup Result", errors):
        return errors
    if result.get("schema_version") != 1 or result.get("provider") != "openai":
        errors.append("OpenAI crash-cleanup Result identity differs")
    if result.get("qualification_requirement") != "crash-cleanup-local-non-recoverability":
        errors.append("OpenAI crash-cleanup Result names the wrong requirement")
    if result.get("authorization_ruling") != "A130":
        errors.append("OpenAI crash-cleanup Result names the wrong authorization")
    if RUN_ID.fullmatch(str(result.get("run_id", ""))) is None:
        errors.append("OpenAI crash-cleanup Result run ID is malformed")
    validate_source(result.get("source"), "crash-cleanup Result", errors)
    checkpoint = result.get("checkpoint")
    pid, start_ticks, expires, checkpoint_time = validate_checkpoint(
        checkpoint, result, synthetic=synthetic, errors=errors
    )
    positive = result.get("positive_control")
    positive_time = validate_search(
        positive, result, pid, start_ticks, positive=True, errors=errors
    )
    kill = result.get("kill")
    kill_time = validate_kill(kill, result, pid, start_ticks, errors)
    post = result.get("post_kill_search")
    post_time = validate_search(
        post, result, pid, start_ticks, positive=False, errors=errors
    )
    if isinstance(positive, dict) and isinstance(post, dict):
        if positive.get("search_contract") != post.get("search_contract"):
            errors.append("positive control and post-kill search used different surfaces")
        if positive.get("search_contract_sha256") != post.get("search_contract_sha256"):
            errors.append("positive control and post-kill search used different instruments")
        if isinstance(kill, dict) and kill.get("positive_control_sha256") != encoded_digest(
            positive
        ):
            errors.append("SIGKILL observation binds a different positive control")
    if isinstance(checkpoint, dict) and isinstance(kill, dict):
        if kill.get("checkpoint_sha256") != encoded_digest(checkpoint):
            errors.append("SIGKILL observation binds a different checkpoint")
    started = validate_in_progress(
        result.get("in_progress_record"), result, checkpoint, kill, errors
    )
    validate_checker_rejections(result.get("checker_rejections"), errors)
    boundary = {
        "proof_scope": "local-host-non-recoverability-only",
        "provider_side_invalidation_proven": False,
        "provider_denial_observed": False,
        "killed_bearer_may_remain_valid_until": "natural-expiry",
        "maximum_assertion_lifetime_seconds": 300,
        "separate_expiry_requirement": "credential-expiry-denial",
        "stable_signing_identity_preserved": True,
        "stable_signing_identity_in_proof_scope": False,
    }
    if result.get("provider_exposure_boundary") != boundary:
        errors.append("crash cleanup conflates local cleanup with provider invalidation")
    if result.get("response_predicate") != RESPONSE_PREDICATE:
        errors.append("OpenAI crash response predicate was enforced prematurely")
    if result.get("control_plane_provenance") != CONTROL_PLANE_PROVENANCE:
        errors.append("OpenAI crash Result misstates control-plane provenance")
    if result.get("provenance_limitation") != "A128-attended-record-not-provider-attestation":
        errors.append("OpenAI crash Result omits the A128 provenance limitation")
    ordered = [checkpoint_time, positive_time, kill_time, post_time]
    if all(item is not None for item in ordered):
        assert all(isinstance(item, datetime) for item in ordered)
        if not all(left <= right for left, right in zip(ordered, ordered[1:])):
            errors.append("OpenAI crash-cleanup observations are out of order")
    if started is not None and checkpoint_time is not None and started > checkpoint_time:
        errors.append("in-progress record begins after the crash checkpoint")
    if expires is not None and kill_time is not None and not kill_time < expires:
        errors.append("SIGKILL did not occur inside the credential lifetime")
    errors.extend(credential_errors(result))
    return errors


def validate_observation(result: Any) -> list[str]:
    if isinstance(result, dict) and result.get("status") == "in_progress":
        return ["in-progress OpenAI crash-cleanup record is inert"]
    if isinstance(result, dict) and result.get("status") == "failed":
        return ["failed OpenAI crash-cleanup record is not a Result"]
    errors = validate_common(result, synthetic=False)
    if isinstance(result, dict):
        if result.get("provider_response_observed") is not True:
            errors.append("OpenAI crash observation does not record its exchange")
        if type(result.get("qualification_evidence")) is not bool:
            errors.append("OpenAI crash qualification_evidence is not boolean")
    return errors


def validate_contract_fixture(result: Any) -> list[str]:
    errors = validate_common(result, synthetic=True)
    if not isinstance(result, dict):
        return errors
    if result.get("fixture_kind") != "synthetic-openai-crash-cleanup-satisfiability":
        errors.append("OpenAI crash-cleanup Fixture kind differs")
    lineage = {
        "issuance_shape_source": (
            "research/isolation/results/openai-first-token-exchange.json"
        ),
        "issuance_shape_source_sha256": OBSERVED_ISSUANCE_SHA256,
        "provider_response_shape": "exchange_response.response_shape",
        "local_outcome": "synthetic-sigkill-and-same-surface-observation",
    }
    if result.get("fixture_lineage") != lineage:
        errors.append("OpenAI crash-cleanup Fixture lineage differs")
    if result.get("provider_response_observed") is not False:
        errors.append("OpenAI crash-cleanup Fixture claims a provider response")
    if result.get("qualification_evidence") is not False:
        errors.append("OpenAI crash-cleanup Fixture claims qualification")
    try:
        observed = load_json_file(OBSERVED_ISSUANCE_PATH)
        expected_shape = observed["exchange_response"]["response_shape"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError, EvidenceJsonError):
        errors.append("cannot read observed OpenAI issuance shape")
    else:
        checkpoint = result.get("checkpoint")
        response = checkpoint.get("exchange_response") if isinstance(checkpoint, dict) else None
        if not isinstance(response, dict) or response.get("response_shape") != expected_shape:
            errors.append("OpenAI crash Fixture differs from its observed response shape")
    return errors


def validate_qualification_evidence(result: Any) -> list[str]:
    if isinstance(result, dict) and result.get("fixture_kind") is not None:
        return ["synthetic OpenAI crash-cleanup Fixture cannot be qualification evidence"]
    errors = validate_observation(result)
    if isinstance(result, dict) and result.get("qualification_evidence") is not True:
        errors.append("OpenAI crash-cleanup Result is not qualification evidence")
    return errors


def static_errors() -> None | list[str]:
    errors = isolation_errors()
    # A150: the identity registry is gated on every CI cycle, not only when
    # a Result is present, so a roster that lost its current or issuance-era
    # entry fails closed here.
    roster_service_account_ids(errors)
    for path, expected, label in (
        (POLICY_PATH, POLICY_SHA256, "OpenAI WIF policy"),
        (BASE_HARNESS_PATH, BASE_HARNESS_SHA256, "qualified lifecycle harness"),
        (OBSERVED_ISSUANCE_PATH, OBSERVED_ISSUANCE_SHA256, "observed OpenAI issuance"),
    ):
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            errors.append(f"{label} differs from its exact binding")
    try:
        policy = load_json_file(POLICY_PATH)
    except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
        errors.append(f"cannot read OpenAI WIF policy: {error}")
    else:
        policy_fields(policy, errors)
    if not CRASH_ADAPTER_PATH.is_file() or CRASH_ADAPTER_PATH.is_symlink():
        errors.append("OpenAI crash-cleanup adapter is missing or a symlink")
    else:
        adapter = CRASH_ADAPTER_PATH.read_text()
        for required in (
            "BASE_HARNESS_SHA256",
            "def load_base_harness()",
            "BASE.ReservedOutput",
            'phase = "bearer_live_before_terminal_write"',
            'os.open(f"/proc/{pid}/mem"',
            '"surface": "process_image"',
            "returncode != -signal.SIGKILL",
            '"signal_name": "SIGKILL"',
            '"provider_side_invalidation_proven": False',
            '"stable_signing_identity_preserved": True',
            '"enforced": False',
            "checker_rejections(args.attempt)",
        ):
            if required not in adapter:
                errors.append(f"OpenAI crash-cleanup adapter is missing: {required}")
    try:
        providers = load_json_file(PROVIDER_POLICY_PATH)["providers"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError, EvidenceJsonError) as error:
        errors.append(f"cannot read provider egress policy: {error}")
    else:
        if len(providers) != 13:
            errors.append("provider egress policy does not contain 13 providers")
    return errors


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
    errors = static_errors()
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
                errors.append("OpenAI crash-cleanup checker accepts only one input mode")
            mode = argument.removeprefix("--")
            path = Path(arguments.pop(0))
        else:
            errors.append(f"unknown checker argument: {argument}")
    if allow_missing and (mode != "default" or path != RESULT_PATH):
        errors.append("allow-missing-results cannot be combined with supplied input")
    qualification = False
    if not path.exists():
        if not allow_missing:
            errors.append("OpenAI crash-cleanup Result is missing")
    else:
        result = read_bounded_input(path, "OpenAI crash-cleanup input", errors)
        if result is not None:
            if mode == "contract-fixture":
                errors.extend(validate_contract_fixture(result))
            elif mode == "evidence":
                errors.extend(validate_qualification_evidence(result))
            else:
                errors.extend(validate_observation(result))
            qualification = (
                isinstance(result, dict)
                and result.get("qualification_evidence") is True
            )
    if errors:
        print("OpenAI WIF crash-cleanup check: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    if mode == "contract-fixture":
        status = "synthetic contract Fixture; not qualification evidence"
    elif path.exists() and qualification:
        status = "qualification evidence"
    elif path.exists():
        status = "with non-qualifying local observation"
    else:
        status = "static preflight"
    print(f"OpenAI WIF crash-cleanup check: pass ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
