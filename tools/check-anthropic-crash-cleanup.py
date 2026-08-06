#!/usr/bin/env python3
"""Check the A130 Anthropic crash-cleanup source and evidence contract."""

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
POLICY_PATH = REPO / "policy/anthropic-wif.json"
LIFECYCLE_HARNESS_PATH = REPO / "tools/anthropic-wif-lifecycle.py"
CRASH_HARNESS_PATH = REPO / "tools/anthropic-wif-crash-cleanup.py"
RESULT_PATH = REPO / "research/isolation/results/anthropic-crash-cleanup.json"
OBSERVED_ISSUANCE_PATH = (
    REPO / "research/isolation/results/anthropic-revocation-rotation.json"
)
CHECKER_PATHS = (
    REPO / "tools/check-anthropic-expiry.py",
    REPO / "tools/check-anthropic-revocation.py",
    Path(__file__).resolve(),
)
PROTECTED_SOURCES = (
    "worker/qualification/patchyard-run-anthropic-issuance",
    "worker/runtime/patchyard-firecracker-run",
    "worker/runtime/patchyard-anthropic-one-shot",
    "worker/image/patchyard-guest-run",
)
LIFECYCLE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
OBSERVED_ISSUANCE_SHA256 = (
    "cd5552c9d93dcef0616ecd1345177932931ba2b8ccc0e00e79e7b3870356df72"
)
RUN_ID = re.compile(r"anthropic-l3-[0-9]{8}-[0-9a-f]{10}")
REQUEST_ID = re.compile(r"req_[A-Za-z0-9]+")
KID = re.compile(r"patchyard-[0-9a-f]{16}")
HEX64 = re.compile(r"[0-9a-f]{64}")
UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z"
)
DISCARDED_FIELD_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
BEARER = re.compile(r"sk-ant-oat01-[A-Za-z0-9_-]+")
JWT = re.compile(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
SEARCH_CONTRACT_VERSION = "a130-run-stage-regular-files-v1"
SEARCH_MATERIAL_CLASSES = ["anthropic_bearer", "jwt_assertion", "private_key"]
MAX_SCAN_FILES = 128
MAX_SCAN_FILE_BYTES = 1_000_000
MAX_SCAN_TOTAL_BYTES = 8_000_000
TERMINAL_FIELDS = {
    "failed_at",
    "failure_phase",
    "failure_reason",
    "failure_type",
    "partial_evidence",
    "post_failure_state",
}
EVIDENCE_KEYS = {
    "schema_version",
    "provider",
    "qualification_requirement",
    "authorization_ruling",
    "run_id",
    "checkpoint",
    "kill",
    "positive_control",
    "post_kill_search",
    "in_progress_record",
    "checker_rejections",
    "provider_exposure_boundary",
    "provenance_limitation",
    "policy_sha256",
    "lifecycle_harness_sha256",
    "crash_harness_sha256",
}
CONTRACT_METADATA_KEYS = {
    "fixture_kind",
    "provider_response_observed",
    "qualification_evidence",
    "fixture_lineage",
}


class EvidenceJsonError(ValueError):
    """Evidence JSON is ambiguous or outside the strict data contract."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded_digest(value: dict[str, Any]) -> str:
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    return hashlib.sha256(encoded).hexdigest()


def canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


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
        errors.append("Anthropic crash-cleanup checker requires python3 -I")
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    for module in (hashlib, json, re, sysconfig):
        source = getattr(module, "__file__", None)
        if source is None or not is_within(Path(source).resolve(), stdlib):
            errors.append(
                "Anthropic crash-cleanup checker rejected "
                f"{module.__name__} provenance: {source!r}"
            )
    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except OSError:
            continue
        if is_within(resolved, REPO):
            errors.append(
                f"Anthropic crash-cleanup checker has repository import path: {entry}"
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


def valid_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_source(value: Any, result: dict[str, Any], label: str, errors: list[str]) -> None:
    expected = {
        "policy_sha256": result.get("policy_sha256"),
        "lifecycle_harness_sha256": result.get("lifecycle_harness_sha256"),
        "crash_harness_sha256": result.get("crash_harness_sha256"),
    }
    if value != expected:
        errors.append(f"{label} source binding differs from the fixture")


def validate_signing_key(value: Any, errors: list[str]) -> None:
    if not exact_keys(
        value,
        {"kid", "jwk_thumbprint_sha256"},
        "crash signing key",
        errors,
    ):
        return
    if KID.fullmatch(str(value.get("kid", ""))) is None:
        errors.append("crash signing key ID is malformed")
    if HEX64.fullmatch(str(value.get("jwk_thumbprint_sha256", ""))) is None:
        errors.append("crash signing key thumbprint is malformed")


def validate_discarded_fields(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list) or any(
        not isinstance(field, str)
        or DISCARDED_FIELD_NAME.fullmatch(field) is None
        or field.startswith("sk-ant-")
        for field in value
    ):
        errors.append("issuance has unsafe discarded response field names")
        return
    if value != sorted(set(value)):
        errors.append("issuance has unsafe discarded response field names")


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
    if not exact_keys(value, expected, "crash issuance", errors):
        return None, None, None
    if value.get("endpoint") != "/v1/oauth/token" or value.get("http_status") != 200:
        errors.append("crash checkpoint is not after successful issuance")
    if REQUEST_ID.fullmatch(str(value.get("request_id", ""))) is None:
        errors.append("crash issuance request ID is malformed")
    if value.get("token_type") != "Bearer" or value.get("scope") != "workspace:inference":
        errors.append("crash issuance did not return the bounded bearer contract")
    validate_discarded_fields(value.get("discarded_response_fields"), errors)
    for field, section in (
        ("service_account_id", "service_account"),
        ("rule_id", "rule"),
        ("workspace_id", "workspace"),
    ):
        if value.get(field) != policy[section]["id"]:
            errors.append(f"crash issuance {field} differs from policy")
    issued = parse_time(value.get("issued_at"), "crash issuance issued_at", errors)
    expires = parse_time(value.get("expires_at"), "crash issuance expires_at", errors)
    observed = parse_time(value.get("observed_at"), "crash issuance observed_at", errors)
    provider_date = parse_time(
        value.get("provider_date"), "crash issuance provider_date", errors
    )
    lifetime = value.get("expires_in")
    if (
        not isinstance(lifetime, int)
        or isinstance(lifetime, bool)
        or not 60 <= lifetime <= 300
    ):
        errors.append("crash issuance lifetime is not one to five minutes")
    elif issued is not None and expires is not None:
        if int((expires - issued).total_seconds()) != lifetime:
            errors.append("crash issuance timestamps differ from its lifetime")
    if issued is not None and provider_date is not None and issued != provider_date:
        errors.append("crash issuance time is not the provider Date observation")
    if issued is not None and observed is not None and issued > observed:
        errors.append("crash issuance provider Date follows its local observation")
    return issued, expires, observed


def validate_checkpoint(
    value: Any,
    result: dict[str, Any],
    policy: dict[str, Any],
    errors: list[str],
) -> tuple[int | None, int | None, datetime | None, datetime | None, datetime | None]:
    expected = {
        "schema_version",
        "provider",
        "run_id",
        "phase",
        "observed_at",
        "target_pid",
        "target_start_ticks",
        "bearer_live",
        "terminal_record_written",
        "core_dump_limits",
        "swap_entries",
        "signing_key",
        "issuance",
        "attempt_sha256",
        "source",
    }
    if not exact_keys(value, expected, "crash checkpoint", errors):
        return None, None, None, None, None
    if value.get("schema_version") != 1 or value.get("provider") != "anthropic":
        errors.append("crash checkpoint identity differs")
    if value.get("run_id") != result.get("run_id"):
        errors.append("crash checkpoint run ID differs")
    if value.get("phase") != "bearer_live_before_terminal_write":
        errors.append("SIGKILL checkpoint is not the live-bearer boundary")
    if value.get("bearer_live") is not True:
        errors.append("SIGKILL checkpoint does not hold a live bearer")
    if value.get("terminal_record_written") is not False:
        errors.append("SIGKILL checkpoint follows a terminal record")
    if value.get("core_dump_limits") != [0, 0]:
        errors.append("credential process core dumps were not disabled")
    if value.get("swap_entries") != 0:
        errors.append("credential process ran with configured swap")
    pid = value.get("target_pid")
    start_ticks = value.get("target_start_ticks")
    if not valid_positive_int(pid) or not valid_positive_int(start_ticks):
        errors.append("crash checkpoint process identity is malformed")
        pid = start_ticks = None
    if HEX64.fullmatch(str(value.get("attempt_sha256", ""))) is None:
        errors.append("crash checkpoint attempt digest is malformed")
    validate_signing_key(value.get("signing_key"), errors)
    issued, expires, issuance_observed = validate_issuance(
        value.get("issuance"), policy, errors
    )
    checkpoint_observed = parse_time(
        value.get("observed_at"), "crash checkpoint observed_at", errors
    )
    if issuance_observed is not None and checkpoint_observed is not None:
        if issuance_observed > checkpoint_observed:
            errors.append("crash checkpoint predates bearer issuance")
    validate_source(value.get("source"), result, "crash checkpoint", errors)
    return pid, start_ticks, issued, expires, checkpoint_observed


def expected_search_contract(run_id: str, pid: int, start_ticks: int) -> dict[str, Any]:
    return {
        "version": SEARCH_CONTRACT_VERSION,
        "stage_path": f"/run/patchyard-anthropic/{run_id}",
        "target_pid": pid,
        "target_start_ticks": start_ticks,
        "file_scope": "all-recursive-regular-files-no-symlinks",
        "material_classes": SEARCH_MATERIAL_CLASSES,
        "max_files": MAX_SCAN_FILES,
        "max_file_bytes": MAX_SCAN_FILE_BYTES,
        "max_total_bytes": MAX_SCAN_TOTAL_BYTES,
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
    expected = {
        "schema_version",
        "provider",
        "run_id",
        "event_type",
        "observed_at",
        "search_contract",
        "search_contract_sha256",
        "files_examined",
        "bytes_examined",
        "credential_material_found",
        "material_classes_found",
        "matches",
        "target_process_present",
        "scanner_core_dump_limits",
        "swap_entries",
        "source",
    }
    if not exact_keys(value, expected, label, errors):
        return None
    if value.get("schema_version") != 1 or value.get("provider") != "anthropic":
        errors.append(f"{label} identity differs")
    if value.get("run_id") != result.get("run_id"):
        errors.append(f"{label} run ID differs")
    if value.get("event_type") != "credential_surface_search":
        errors.append(f"{label} is not the fixed credential search")
    if pid is not None and start_ticks is not None:
        expected_contract = expected_search_contract(
            str(result.get("run_id")), pid, start_ticks
        )
        if value.get("search_contract") != expected_contract:
            errors.append(f"{label} searched a different host surface")
        elif value.get("search_contract_sha256") != canonical_digest(expected_contract):
            errors.append(f"{label} search instrument digest differs")
    if not valid_positive_int(value.get("files_examined")):
        errors.append(f"{label} examined no files")
    byte_count = value.get("bytes_examined")
    if (
        not isinstance(byte_count, int)
        or isinstance(byte_count, bool)
        or not 1 <= byte_count <= MAX_SCAN_TOTAL_BYTES
    ):
        errors.append(f"{label} byte count is outside the search bound")
    if value.get("swap_entries") != 0:
        errors.append(f"{label} observed configured swap")
    if value.get("scanner_core_dump_limits") != [0, 0]:
        errors.append(f"{label} scanner core dumps were not disabled")
    if positive:
        exact_match = [
            {
                "material_class": "private_key",
                "relative_path": "replacement.pem",
                "occurrences": 1,
            }
        ]
        if value.get("credential_material_found") is not True:
            errors.append("positive control found no credential material")
        if value.get("material_classes_found") != ["private_key"]:
            errors.append("positive control did not isolate private-key material")
        if value.get("matches") != exact_match:
            errors.append("positive control did not find the staged replacement key")
        if value.get("target_process_present") is not True:
            errors.append("positive control did not observe the live credential process")
    else:
        if value.get("credential_material_found") is not False:
            errors.append("post-kill search recovered credential material")
        if value.get("material_classes_found") != [] or value.get("matches") != []:
            errors.append("post-kill search contains credential matches")
        if value.get("target_process_present") is not False:
            errors.append("post-kill search found the credential process")
    validate_source(value.get("source"), result, label, errors)
    return parse_time(value.get("observed_at"), f"{label} observed_at", errors)


def validate_kill(
    value: Any,
    result: dict[str, Any],
    pid: int | None,
    start_ticks: int | None,
    errors: list[str],
) -> tuple[datetime | None, datetime | None]:
    expected = {
        "schema_version",
        "provider",
        "run_id",
        "event_type",
        "observed_at",
        "target_pid",
        "target_start_ticks",
        "signal_name",
        "signal_number",
        "child_returncode",
        "supervisor_timed_out",
        "target_process_present",
        "signing_key_removed",
        "signing_key_present_after_cleanup",
        "signing_key_removed_at",
        "checkpoint_sha256",
        "positive_control_sha256",
        "attempt_sha256",
        "source",
    }
    if not exact_keys(value, expected, "SIGKILL observation", errors):
        return None, None
    if value.get("schema_version") != 1 or value.get("provider") != "anthropic":
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
    if value.get("signing_key_removed") is not True:
        errors.append("SIGKILL supervisor did not remove the staged private key")
    if value.get("signing_key_present_after_cleanup") is not False:
        errors.append("staged private key remains after SIGKILL cleanup")
    for field in ("checkpoint_sha256", "positive_control_sha256", "attempt_sha256"):
        if HEX64.fullmatch(str(value.get(field, ""))) is None:
            errors.append(f"SIGKILL observation {field} is malformed")
    validate_source(value.get("source"), result, "SIGKILL observation", errors)
    observed = parse_time(value.get("observed_at"), "SIGKILL observed_at", errors)
    removed = parse_time(
        value.get("signing_key_removed_at"), "signing key removed_at", errors
    )
    if observed is not None and removed is not None and observed > removed:
        errors.append("staged private key was removed before the observed SIGKILL")
    return observed, removed


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
    expected_path = (
        f"/run/patchyard-anthropic/{result.get('run_id')}/crash-attempt.json"
    )
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
        if record.get("schema_version") != 1 or record.get("provider") != "anthropic":
            errors.append("in-progress record identity differs")
        if record.get("status") != "in_progress":
            errors.append("abrupt-death record was completed or relabelled")
        if record.get("action") != "crash-cleanup-probe":
            errors.append("in-progress record names a different action")
        if record.get("run_id") != result.get("run_id"):
            errors.append("in-progress record run ID differs")
        if TERMINAL_FIELDS.intersection(record):
            errors.append("in-progress record carries terminal fields")
        validate_source(record.get("source"), result, "in-progress record", errors)
        started = parse_time(
            record.get("started_at"), "in-progress record started_at", errors
        )
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
    if value.get("unchanged") is not True:
        errors.append("in-progress record is not unchanged")
    if value.get("terminal_fields_present") != []:
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
        expected = {"checker", "checker_sha256", "exit_code", "accepted"}
        if not exact_keys(item, expected, "in-progress checker observation", errors):
            continue
        if item.get("checker") != checker.name:
            errors.append("in-progress checker name differs")
        if item.get("checker_sha256") != digest(checker):
            errors.append(f"in-progress checker binding differs: {checker.name}")
        if item.get("exit_code") != 1 or item.get("accepted") is not False:
            errors.append(f"a checker accepted in-progress evidence: {checker.name}")


def secret_named_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {
                "secret",
                "access_token",
                "assertion",
                "identity_token",
                "authorization",
                "private_key",
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


def validate_evidence(result: Any, policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if isinstance(result, dict) and result.get("qualification_evidence") is False:
        return ["synthetic crash-cleanup fixture cannot be qualification evidence"]
    if isinstance(result, dict) and result.get("status") == "in_progress":
        return ["in-progress record is inert and cannot qualify"]
    if not exact_keys(result, EVIDENCE_KEYS, "crash-cleanup fixture", errors):
        return errors
    if result.get("schema_version") != 1 or result.get("provider") != "anthropic":
        errors.append("crash-cleanup fixture identity differs")
    if result.get("qualification_requirement") != "crash-cleanup-local-non-recoverability":
        errors.append("crash-cleanup fixture names the wrong requirement")
    if result.get("authorization_ruling") != "A130":
        errors.append("crash-cleanup fixture names the wrong authorization")
    run_id = result.get("run_id")
    if RUN_ID.fullmatch(str(run_id or "")) is None:
        errors.append("crash-cleanup fixture run ID is malformed")
    if result.get("policy_sha256") != digest(POLICY_PATH):
        errors.append("crash-cleanup fixture is stale for the WIF policy")
    if result.get("lifecycle_harness_sha256") != digest(LIFECYCLE_HARNESS_PATH):
        errors.append("crash-cleanup fixture is stale for the lifecycle harness")
    if result.get("crash_harness_sha256") != digest(CRASH_HARNESS_PATH):
        errors.append("crash-cleanup fixture is stale for the crash harness")

    checkpoint = result.get("checkpoint")
    pid, start_ticks, issued, expires, checkpoint_time = validate_checkpoint(
        checkpoint, result, policy, errors
    )
    positive_time = validate_search(
        result.get("positive_control"),
        result,
        pid,
        start_ticks,
        positive=True,
        errors=errors,
    )
    kill = result.get("kill")
    kill_time, key_removed_time = validate_kill(
        kill, result, pid, start_ticks, errors
    )
    post_time = validate_search(
        result.get("post_kill_search"),
        result,
        pid,
        start_ticks,
        positive=False,
        errors=errors,
    )
    positive = result.get("positive_control")
    post = result.get("post_kill_search")
    if isinstance(positive, dict) and isinstance(post, dict):
        if positive.get("search_contract") != post.get("search_contract"):
            errors.append("positive control and post-kill search used different surfaces")
        if positive.get("search_contract_sha256") != post.get(
            "search_contract_sha256"
        ):
            errors.append("positive control and post-kill search used different instruments")
        if isinstance(kill, dict):
            if kill.get("positive_control_sha256") != encoded_digest(positive):
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
        "maximum_bearer_lifetime_seconds": 300,
        "separate_expiry_requirement": "credential-expiry-denial",
    }
    if result.get("provider_exposure_boundary") != boundary:
        errors.append("crash cleanup conflates local cleanup with provider invalidation")
    if result.get("provenance_limitation") != (
        "A128-attended-record-not-provider-attestation"
    ):
        errors.append("crash-cleanup fixture omits the A128 provenance limitation")

    ordered = [
        checkpoint_time,
        positive_time,
        kill_time,
        key_removed_time,
        post_time,
    ]
    if all(value is not None for value in ordered):
        assert all(isinstance(value, datetime) for value in ordered)
        if not all(left <= right for left, right in zip(ordered, ordered[1:])):
            errors.append("crash-cleanup observations are out of order")
    if started is not None and checkpoint_time is not None and started > checkpoint_time:
        errors.append("in-progress record begins after the crash checkpoint")
    if issued is not None and checkpoint_time is not None and issued > checkpoint_time:
        errors.append("crash checkpoint predates provider issuance")
    if expires is not None and kill_time is not None and not kill_time < expires:
        errors.append("SIGKILL did not occur while the bearer was live")

    forbidden = secret_named_key(result)
    if forbidden is not None:
        errors.append(f"crash-cleanup evidence contains forbidden credential field: {forbidden}")
    serialized = json.dumps(result, sort_keys=True)
    if BEARER.search(serialized) or JWT.search(serialized) or PRIVATE_KEY.search(serialized):
        errors.append("crash-cleanup evidence carries credential material")
    return errors


def validate_contract_fixture(result: Any, policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not exact_keys(
        result,
        EVIDENCE_KEYS | CONTRACT_METADATA_KEYS,
        "crash-cleanup contract fixture",
        errors,
    ):
        return errors
    if result.get("fixture_kind") != "synthetic-crash-cleanup-satisfiability":
        errors.append("crash-cleanup contract fixture kind differs")
    if result.get("provider_response_observed") is not False:
        errors.append("crash-cleanup contract fixture claims a provider response")
    if result.get("qualification_evidence") is not False:
        errors.append("crash-cleanup contract fixture claims qualification")
    lineage = {
        "issuance_shape_source": (
            "research/isolation/results/anthropic-revocation-rotation.json"
        ),
        "issuance_shape_source_sha256": OBSERVED_ISSUANCE_SHA256,
        "issuance_shape_event": "replacement_key_positive",
        "local_outcome": "synthetic-sigkill-and-same-surface-observation",
    }
    if result.get("fixture_lineage") != lineage:
        errors.append("crash-cleanup contract fixture lineage differs")
    observed = load_json_file(OBSERVED_ISSUANCE_PATH)
    observed_events = [
        event
        for event in observed.get("events", [])
        if isinstance(event, dict)
        and event.get("event_type") == "replacement_key_positive"
    ]
    checkpoint = result.get("checkpoint")
    if len(observed_events) != 1 or not isinstance(checkpoint, dict):
        errors.append("crash-cleanup fixture has no exact observed issuance lineage")
    else:
        observed_event = observed_events[0]
        expected_exchange = {
            key: value
            for key, value in observed_event.get("exchange", {}).items()
            if key != "request_started_at"
        }
        if (
            checkpoint.get("issuance") != expected_exchange
            or checkpoint.get("signing_key") != observed_event.get("signing_key")
            or result.get("run_id") != observed_event.get("run_id")
        ):
            errors.append("crash-cleanup fixture differs from its observed issuance")
    evidence = {key: result[key] for key in EVIDENCE_KEYS}
    errors.extend(validate_evidence(evidence, policy))
    return errors


def static_errors() -> tuple[list[str], dict[str, Any]]:
    errors = isolation_errors()
    if (
        not LIFECYCLE_HARNESS_PATH.is_file()
        or LIFECYCLE_HARNESS_PATH.is_symlink()
        or digest(LIFECYCLE_HARNESS_PATH) != LIFECYCLE_HARNESS_SHA256
    ):
        errors.append("qualified lifecycle harness differs from its exact binding")
    if (
        not OBSERVED_ISSUANCE_PATH.is_file()
        or OBSERVED_ISSUANCE_PATH.is_symlink()
        or digest(OBSERVED_ISSUANCE_PATH) != OBSERVED_ISSUANCE_SHA256
    ):
        errors.append("observed issuance source differs from its exact binding")
    if not CRASH_HARNESS_PATH.is_file() or CRASH_HARNESS_PATH.is_symlink():
        errors.append("crash-cleanup harness is missing or a symlink")
    else:
        harness = CRASH_HARNESS_PATH.read_text()
        for required in (
            "BASE_HARNESS_SHA256",
            "BASE.ReservedOutput",
            '"status": "in_progress"',
            'phase = "bearer_live_before_terminal_write"',
            "returncode != -signal.SIGKILL",
            '"signal_name": "SIGKILL"',
            "remove_staged_key(args.signing_key, stage)",
            '"signing_key_removed": True',
            '"relative_path": "replacement.pem"',
            "validate_positive_search",
            "validate_post_kill_search",
            '"provider_side_invalidation_proven": False',
            '"killed_bearer_may_remain_valid_until": "natural-expiry"',
            "checker_rejections(args.attempt)",
        ):
            if required not in harness:
                errors.append(f"crash-cleanup harness is missing: {required}")
        for forbidden in PROTECTED_SOURCES:
            if forbidden in harness:
                errors.append(f"crash-cleanup harness invokes protected source: {forbidden}")
    policy = load_json_file(POLICY_PATH)
    providers = load_json_file(REPO / "policy/provider-egress.json")["providers"]
    if len(providers) != 13 or any(
        value.get("credential_qualified") is not False for value in providers.values()
    ):
        errors.append("a provider became credential-qualified before six live fixtures")
    return errors, policy


def main() -> int:
    errors, policy = static_errors()
    evidence_path = RESULT_PATH
    evidence_path_supplied = False
    contract_fixture_path: Path | None = None
    allow_missing = False
    arguments = sys.argv[1:]
    while arguments:
        argument = arguments.pop(0)
        if argument == "--allow-missing-results":
            allow_missing = True
        elif argument == "--evidence" and arguments:
            evidence_path = Path(arguments.pop(0))
            evidence_path_supplied = True
        elif argument == "--contract-fixture" and arguments:
            contract_fixture_path = Path(arguments.pop(0))
        else:
            errors.append(f"unknown checker argument: {argument}")
    if contract_fixture_path is not None:
        if allow_missing or evidence_path_supplied:
            errors.append("contract-fixture mode cannot be combined with evidence options")
        try:
            if not contract_fixture_path.is_file() or contract_fixture_path.is_symlink():
                raise EvidenceJsonError(
                    "contract fixture is not a regular non-symlink file"
                )
            contract = load_json_file(contract_fixture_path)
        except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
            errors.append(f"cannot read crash-cleanup contract fixture: {error}")
        else:
            errors.extend(validate_contract_fixture(contract, policy))
    elif not evidence_path.exists():
        if not allow_missing:
            errors.append("committed Anthropic crash-cleanup result is missing")
    else:
        try:
            if not evidence_path.is_file() or evidence_path.is_symlink():
                raise EvidenceJsonError("evidence is not a regular non-symlink file")
            result = load_json_file(evidence_path)
        except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
            errors.append(f"cannot read crash-cleanup evidence: {error}")
        else:
            errors.extend(validate_evidence(result, policy))
    if errors:
        print("Anthropic crash-cleanup check: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    if contract_fixture_path is not None:
        status = "synthetic contract fixture; not qualification evidence"
    elif evidence_path != RESULT_PATH:
        status = "with supplied evidence"
    else:
        status = (
            "with conforming committed result"
            if evidence_path.exists()
            else "static preflight"
        )
    print(f"Anthropic crash-cleanup check: pass ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
