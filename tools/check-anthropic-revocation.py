#!/usr/bin/env python3
"""Check A113/A129 Anthropic rule revocation and key-rotation evidence."""

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
HARNESS_PATH = REPO / "tools/anthropic-wif-lifecycle.py"
REVOCATION_HARNESS_PATH = REPO / "tools/anthropic-wif-revocation.py"
ADMIN_PATH = REPO / "tools/anthropic-wif-lifecycle-admin.py"
RESULT_PATH = REPO / "research/isolation/results/anthropic-revocation-rotation.json"
SUPERSEDES_CHECKER_SHA256 = (
    "deeba4038169d466a31bbcf4d263fe8a"
    "c1bdf0aa5bd9365f4449da8e80db085c",
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
EVENT_SEQUENCE = [
    "rule_enabled_positive",
    "rule_disabled",
    "rule_disabled_exchange_denial",
    "rule_restored",
    "rule_restored_positive",
    "issuer_rotation_staged",
    "replacement_key_positive",
    "replacement_key_activated",
    "replacement_key_final_positive",
    "issuer_retired_key",
    "post_retirement_active_positive",
    "retired_key_exchange_denial",
    "post_retirement_active_positive_final",
]
POSITIVE_EVENTS = {
    "rule_enabled_positive": "active",
    "rule_restored_positive": "active",
    "replacement_key_positive": "replacement_staging",
    "replacement_key_final_positive": "active",
    "post_retirement_active_positive": "active",
    "post_retirement_active_positive_final": "active",
}
DENIAL_EVENTS = {
    "rule_disabled_exchange_denial": "active",
    "retired_key_exchange_denial": "retired_staging",
}
OBSERVED_DENIAL_CONTRACTS = {
    "rule_disabled_exchange_denial": (401, "authentication_error"),
    "retired_key_exchange_denial": (401, "authentication_error"),
}
POST_MUTATION_POSITIVE_EVENTS = {
    "rule_restored_positive",
    "replacement_key_positive",
    "post_retirement_active_positive",
    "post_retirement_active_positive_final",
}
SETTLING_PREDECESSORS = {
    "rule_disabled_exchange_denial": (
        "rule_disabled",
        "exchange_denial",
        "denial",
    ),
    "retired_key_exchange_denial": (
        "issuer_retired_key",
        "exchange_denial",
        "denial",
    ),
    "post_retirement_active_positive": (
        "issuer_retired_key",
        "exchange",
        "positive control",
    ),
    "post_retirement_active_positive_final": (
        "issuer_retired_key",
        "exchange",
        "positive control",
    ),
    "rule_restored_positive": ("rule_restored", "exchange", "positive control"),
    "replacement_key_positive": (
        "issuer_rotation_staged",
        "exchange",
        "positive control",
    ),
}
MINIMUM_SETTLING_SECONDS = 90
MAXIMUM_RETIREMENT_BRACKET_SECONDS = 120
MANDATORY_BRACKETING_REQUEST_IDS = 20
EXPECTED_IDENTIFIED_PROVIDER_REQUEST_IDS = 22
EXPECTED_PROVIDER_TIMESTAMPS = 22
QUALIFICATION_BLOCKED_EXIT = 2
ADMIN_EVENTS = {
    "rule_disabled",
    "rule_restored",
    "issuer_rotation_staged",
    "issuer_retired_key",
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
REVOCATION_EVIDENCE_KEYS = {
    "schema_version",
    "provider",
    "qualification_requirement",
    "authorization_ruling",
    "run_id",
    "policy_sha256",
    "lifecycle_harness_sha256",
    "revocation_harness_sha256",
    "admin_tool_sha256",
    "events",
}
CONTRACT_FIXTURE_METADATA = {
    "fixture_kind": "synthetic-thirteen-event-satisfiability",
    "provider_response_observed": False,
    "qualification_evidence": False,
}
UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z"
)
DISCARDED_FIELD_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,128}")


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
        errors.append("Anthropic revocation checker requires python3 -I")
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    for module in (hashlib, json, re, sysconfig):
        source = getattr(module, "__file__", None)
        if source is None or not is_within(Path(source).resolve(), stdlib):
            errors.append(
                f"Anthropic revocation checker rejected {module.__name__} provenance: {source!r}"
            )
    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except OSError:
            continue
        if is_within(resolved, REPO):
            errors.append(
                f"Anthropic revocation checker has repository import path: {entry}"
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


def secret_named_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {
                "secret",
                "access_token",
                "assertion",
                "identity_token",
                "authorization",
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


def validate_key(value: Any, label: str, errors: list[str]) -> tuple[str, str] | None:
    if not exact_keys(value, {"kid", "jwk_thumbprint_sha256"}, label, errors):
        return None
    kid = str(value.get("kid", ""))
    thumbprint = str(value.get("jwk_thumbprint_sha256", ""))
    if KID.fullmatch(kid) is None:
        errors.append(f"{label} key ID is malformed")
    if HEX64.fullmatch(thumbprint) is None:
        errors.append(f"{label} thumbprint is malformed")
    return kid, thumbprint


def validate_source(
    value: Any, event_type: str, fixture: dict[str, Any], errors: list[str]
) -> None:
    if event_type in ADMIN_EVENTS:
        expected = {"policy_sha256", "admin_tool_sha256"}
    elif event_type in DENIAL_EVENTS or event_type in POST_MUTATION_POSITIVE_EVENTS:
        expected = {
            "policy_sha256",
            "lifecycle_harness_sha256",
            "revocation_harness_sha256",
        }
    else:
        expected = {"policy_sha256", "lifecycle_harness_sha256"}
    if not exact_keys(value, expected, f"{event_type} source", errors):
        return
    if value.get("policy_sha256") != fixture.get("policy_sha256"):
        errors.append(f"{event_type} policy binding differs from the fixture")
    if event_type in ADMIN_EVENTS:
        if value.get("admin_tool_sha256") != fixture.get("admin_tool_sha256"):
            errors.append(f"{event_type} admin binding differs from the fixture")
    else:
        if value.get("lifecycle_harness_sha256") != fixture.get(
            "lifecycle_harness_sha256"
        ):
            errors.append(f"{event_type} harness binding differs from the fixture")
        if (
            event_type in DENIAL_EVENTS
            or event_type in POST_MUTATION_POSITIVE_EVENTS
        ) and value.get("revocation_harness_sha256") != fixture.get(
            "revocation_harness_sha256"
        ):
            errors.append(
                f"{event_type} revocation harness binding differs from the fixture"
            )


def validate_receipt(
    value: Any,
    label: str,
    method: str,
    endpoint: str,
    errors: list[str],
) -> tuple[datetime | None, datetime | None, str | None]:
    expected = {
        "method",
        "endpoint",
        "http_status",
        "request_id",
        "provider_date",
        "observed_at",
    }
    if not exact_keys(value, expected, label, errors):
        return None, None, None
    if value.get("method") != method or value.get("endpoint") != endpoint:
        errors.append(f"{label} method or endpoint differs")
    if value.get("http_status") != 200:
        errors.append(f"{label} is not a successful provider response")
    request_id = value.get("request_id")
    if REQUEST_ID.fullmatch(str(request_id or "")) is None:
        errors.append(f"{label} request ID is malformed")
        request_id = None
    provider = parse_time(value.get("provider_date"), f"{label} provider_date", errors)
    observed = parse_time(value.get("observed_at"), f"{label} observed_at", errors)
    if provider is not None and observed is not None and provider > observed:
        errors.append(f"{label} provider Date follows its local observation")
    return provider, observed, request_id


def validate_exchange(
    value: Any,
    policy: dict[str, Any],
    label: str,
    errors: list[str],
    *,
    request_start_required: bool = False,
) -> tuple[datetime | None, datetime | None, datetime | None, str | None]:
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
    if request_start_required:
        expected.add("request_started_at")
    if not exact_keys(value, expected, f"{label} exchange", errors):
        return None, None, None, None
    if value.get("endpoint") != "/v1/oauth/token" or value.get("http_status") != 200:
        errors.append(f"{label} exchange is not a successful provider exchange")
    request_id = value.get("request_id")
    if REQUEST_ID.fullmatch(str(request_id or "")) is None:
        errors.append(f"{label} exchange request ID is malformed")
        request_id = None
    if value.get("token_type") != "Bearer" or value.get("scope") != "workspace:inference":
        errors.append(f"{label} exchange bearer contract differs")
    validate_discarded_fields(
        value.get("discarded_response_fields"), f"{label} exchange", errors
    )
    for field, section in (
        ("service_account_id", "service_account"),
        ("rule_id", "rule"),
        ("workspace_id", "workspace"),
    ):
        if value.get(field) != policy[section]["id"]:
            errors.append(f"{label} exchange {field} differs from policy")
    issued = parse_time(value.get("issued_at"), f"{label} issued_at", errors)
    expires = parse_time(value.get("expires_at"), f"{label} expires_at", errors)
    provider_date = parse_time(
        value.get("provider_date"), f"{label} exchange provider_date", errors
    )
    observed = parse_time(
        value.get("observed_at"), f"{label} exchange observed_at", errors
    )
    requested = None
    if request_start_required:
        requested = parse_time(
            value.get("request_started_at"),
            f"{label} exchange request_started_at",
            errors,
        )
    lifetime = value.get("expires_in")
    if not isinstance(lifetime, int) or isinstance(lifetime, bool) or not 60 <= lifetime <= 300:
        errors.append(f"{label} exchange lifetime is outside one to five minutes")
    elif issued is not None and expires is not None:
        if int((expires - issued).total_seconds()) != lifetime:
            errors.append(f"{label} exchange timestamps differ from lifetime")
    if issued is not None and provider_date is not None and issued != provider_date:
        errors.append(f"{label} issuance is not bound to provider Date")
    if provider_date is not None and observed is not None and provider_date > observed:
        errors.append(f"{label} exchange provider Date follows its local observation")
    if requested is not None and observed is not None and requested > observed:
        errors.append(f"{label} exchange request bracket is reversed")
    return expires, observed, provider_date, request_id


def validate_models(
    value: Any, label: str, errors: list[str]
) -> tuple[datetime | None, datetime | None, str | None]:
    expected = {
        "endpoint",
        "http_status",
        "request_id",
        "provider_date",
        "observed_at",
        "model_id",
    }
    if not exact_keys(value, expected, f"{label} Models", errors):
        return None, None, None
    if value.get("endpoint") != "/v1/models?limit=1" or value.get("http_status") != 200:
        errors.append(f"{label} is not a successful Models call")
    if not isinstance(value.get("model_id"), str) or not value["model_id"]:
        errors.append(f"{label} Models response has no model ID")
    request_id = value.get("request_id")
    if REQUEST_ID.fullmatch(str(request_id or "")) is None:
        errors.append(f"{label} Models request ID is malformed")
        request_id = None
    provider = parse_time(
        value.get("provider_date"), f"{label} Models provider_date", errors
    )
    observed = parse_time(
        value.get("observed_at"), f"{label} Models observed_at", errors
    )
    if provider is not None and observed is not None and provider > observed:
        errors.append(f"{label} Models provider Date follows its local observation")
    return provider, observed, request_id


def validate_positive_event(
    value: dict[str, Any],
    event_type: str,
    policy: dict[str, Any],
    fixture: dict[str, Any],
    errors: list[str],
) -> tuple[datetime | None, tuple[str, str] | None, list[str]]:
    expected = {
        "schema_version",
        "provider",
        "run_id",
        "event_type",
        "observed_at",
        "key_role",
        "signing_key",
        "exchange",
        "models",
        "credential_removed_at",
        "source",
    }
    if not exact_keys(value, expected, event_type, errors):
        return None, None, []
    if value.get("key_role") != POSITIVE_EVENTS[event_type]:
        errors.append(f"{event_type} has the wrong key role")
    key = validate_key(value.get("signing_key"), f"{event_type} signing key", errors)
    expires, exchange_observed, exchange_provider, exchange_request_id = validate_exchange(
        value.get("exchange"),
        policy,
        event_type,
        errors,
        request_start_required=event_type in POST_MUTATION_POSITIVE_EVENTS,
    )
    models_provider, models_observed, models_request_id = validate_models(
        value.get("models"), event_type, errors
    )
    event_observed = parse_time(value.get("observed_at"), f"{event_type} observed_at", errors)
    removed = parse_time(
        value.get("credential_removed_at"), f"{event_type} credential_removed_at", errors
    )
    if (
        models_observed is not None
        and event_observed is not None
        and models_observed != event_observed
    ):
        errors.append(f"{event_type} event timestamp is not its Models observation")
    if all(item is not None for item in (exchange_observed, models_observed, removed)):
        assert exchange_observed is not None
        assert models_observed is not None
        assert removed is not None
        if not exchange_observed < models_observed <= removed:
            errors.append(f"{event_type} capture timestamps are out of order")
    if expires is not None and models_provider is not None and not models_provider < expires:
        errors.append(f"{event_type} Models call did not precede bearer expiry")
    if (
        exchange_provider is not None
        and models_provider is not None
        and exchange_provider > models_provider
    ):
        errors.append(f"{event_type} provider calls are out of order")
    validate_source(value.get("source"), event_type, fixture, errors)
    return event_observed, key, [item for item in (exchange_request_id, models_request_id) if item]


def validate_denial_event(
    value: dict[str, Any],
    event_type: str,
    fixture: dict[str, Any],
    errors: list[str],
    qualification_blockers: list[str],
) -> tuple[datetime | None, tuple[str, str] | None, list[str]]:
    expected = {
        "schema_version",
        "provider",
        "run_id",
        "event_type",
        "observed_at",
        "key_role",
        "signing_key",
        "exchange_denial",
        "credential_removed_at",
        "source",
    }
    if not exact_keys(value, expected, event_type, errors):
        return None, None, []
    if value.get("key_role") != DENIAL_EVENTS[event_type]:
        errors.append(f"{event_type} has the wrong key role")
    key = validate_key(value.get("signing_key"), f"{event_type} signing key", errors)
    denial = value.get("exchange_denial")
    denial_expected = {
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
    request_ids: list[str] = []
    denial_observed = None
    if exact_keys(denial, denial_expected, f"{event_type} denial", errors):
        if denial.get("source") != "anthropic_http_response":
            errors.append(f"{event_type} is not a provider HTTP denial")
        if denial.get("endpoint") != "/v1/oauth/token":
            errors.append(f"{event_type} used the wrong endpoint")
        observed_contract = OBSERVED_DENIAL_CONTRACTS.get(event_type)
        if observed_contract is not None:
            expected_status, expected_error = observed_contract
            if (
                denial.get("http_status") != expected_status
                or denial.get("error_type") != expected_error
            ):
                errors.append(f"{event_type} is not its exact provider denial")
        else:
            if (
                not isinstance(denial.get("http_status"), int)
                or isinstance(denial.get("http_status"), bool)
                or not 400 <= denial["http_status"] <= 499
                or not isinstance(denial.get("error_type"), str)
                or not denial["error_type"]
            ):
                errors.append(f"{event_type} is not a bounded provider HTTP denial")
            else:
                qualification_blockers.append(event_type)
        request_id = denial.get("request_id")
        request_id_supplied = denial.get("request_id_supplied")
        if not isinstance(request_id_supplied, bool):
            errors.append(
                f"{event_type} does not explicitly record request-ID presence"
            )
        elif request_id_supplied:
            if REQUEST_ID.fullmatch(str(request_id or "")) is None:
                errors.append(f"{event_type} request ID is malformed")
            else:
                request_ids.append(request_id)
        elif request_id is not None:
            errors.append(
                f"{event_type} claims request-ID absence while carrying an ID"
            )
        if (
            observed_contract is not None
            and denial.get("response_shape") != EXPECTED_ERROR_SHAPE
        ):
            errors.append(f"{event_type} sanitized response shape differs")
        elif observed_contract is None and not isinstance(
            denial.get("response_shape"), dict
        ):
            errors.append(f"{event_type} sanitized response shape is not an object")
        denial_provider = parse_time(
            denial.get("provider_date"), f"{event_type} provider_date", errors
        )
        denial_requested = parse_time(
            denial.get("request_started_at"),
            f"{event_type} request_started_at",
            errors,
        )
        denial_observed = parse_time(
            denial.get("observed_at"), f"{event_type} denial observed_at", errors
        )
        if (
            denial_provider is not None
            and denial_observed is not None
            and denial_provider > denial_observed
        ):
            errors.append(f"{event_type} provider Date follows its local observation")
        if (
            denial_requested is not None
            and denial_observed is not None
            and denial_requested > denial_observed
        ):
            errors.append(f"{event_type} control-plane UTC bracket is reversed")
    event_observed = parse_time(value.get("observed_at"), f"{event_type} observed_at", errors)
    removed = parse_time(
        value.get("credential_removed_at"), f"{event_type} credential_removed_at", errors
    )
    if (
        denial_observed is not None
        and event_observed is not None
        and denial_observed != event_observed
    ):
        errors.append(f"{event_type} event timestamp is not its provider denial")
    if denial_observed is not None and removed is not None and denial_observed > removed:
        errors.append(f"{event_type} credential cleanup predates its denial")
    validate_source(value.get("source"), event_type, fixture, errors)
    return event_observed, key, request_ids


def validate_settling_intervals(
    events: dict[str, dict[str, Any]], errors: list[str]
) -> None:
    for event_type, (
        predecessor_type,
        request_section,
        request_kind,
    ) in SETTLING_PREDECESSORS.items():
        predecessor = events.get(predecessor_type, {})
        event = events.get(event_type, {})
        readback = predecessor.get("readback", {})
        request = event.get(request_section, {})
        settled_from = parse_time(
            readback.get("observed_at"),
            f"{event_type} settling readback",
            errors,
        )
        requested = parse_time(
            request.get("request_started_at"),
            f"{event_type} settling request",
            errors,
        )
        if settled_from is not None and requested is not None:
            elapsed = (requested - settled_from).total_seconds()
            if elapsed < MINIMUM_SETTLING_SECONDS:
                errors.append(
                    f"{event_type} is inconclusive: {request_kind} began before the "
                    f"{MINIMUM_SETTLING_SECONDS}-second settling interval elapsed"
                )


def validate_retirement_bracket(
    events: dict[str, dict[str, Any]], errors: list[str]
) -> None:
    first = events.get("post_retirement_active_positive", {})
    denial = events.get("retired_key_exchange_denial", {})
    final = events.get("post_retirement_active_positive_final", {})
    values = (
        (
            first.get("exchange", {}).get("request_started_at"),
            "post-retirement first control request",
        ),
        (
            first.get("models", {}).get("observed_at"),
            "post-retirement first control completion",
        ),
        (
            denial.get("exchange_denial", {}).get("request_started_at"),
            "retired-key denial request",
        ),
        (
            denial.get("exchange_denial", {}).get("observed_at"),
            "retired-key denial completion",
        ),
        (
            final.get("exchange", {}).get("request_started_at"),
            "post-retirement final control request",
        ),
        (
            final.get("models", {}).get("observed_at"),
            "post-retirement final control completion",
        ),
    )
    parsed = [parse_time(value, label, errors) for value, label in values]
    if any(value is None for value in parsed):
        return
    (
        first_started,
        first_finished,
        denial_started,
        denial_finished,
        final_started,
        final_finished,
    ) = parsed
    assert all(value is not None for value in parsed)
    if not (
        first_started <= first_finished
        < denial_started
        <= denial_finished
        < final_started
        <= final_finished
    ):
        errors.append(
            "retired-key denial is not bracketed by non-overlapping active-key controls"
        )
        return
    if (
        (final_finished - first_started).total_seconds()
        > MAXIMUM_RETIREMENT_BRACKET_SECONDS
    ):
        errors.append(
            "retirement bracket exceeds the "
            f"{MAXIMUM_RETIREMENT_BRACKET_SECONDS}-second bounded window"
        )


def validate_rule_state(
    value: Any,
    policy: dict[str, Any],
    workspace_ids: list[str],
    label: str,
    errors: list[str],
) -> None:
    expected = {
        "rule_id",
        "workspace_id",
        "workspace_ids",
        "applies_to_all_workspaces",
        "archived",
    }
    if not exact_keys(value, expected, label, errors):
        return
    if value != {
        "rule_id": policy["rule"]["id"],
        "workspace_id": policy["workspace"]["id"],
        "workspace_ids": workspace_ids,
        "applies_to_all_workspaces": False,
        "archived": False,
    }:
        errors.append(f"{label} differs from the exact rule state")


def validate_issuer_state(
    value: Any,
    policy: dict[str, Any],
    count: int,
    label: str,
    errors: list[str],
) -> list[tuple[str, str]]:
    expected = {"issuer_id", "jwks_type", "keys", "archived"}
    if not exact_keys(value, expected, label, errors):
        return []
    if value.get("issuer_id") != policy["issuer"]["id"]:
        errors.append(f"{label} issuer ID differs")
    if value.get("jwks_type") != "inline" or value.get("archived") is not False:
        errors.append(f"{label} issuer mode or archive state differs")
    keys = value.get("keys")
    if not isinstance(keys, list) or len(keys) != count:
        errors.append(f"{label} does not contain exactly {count} key(s)")
        return []
    descriptors = [validate_key(key, f"{label} key", errors) for key in keys]
    present = [descriptor for descriptor in descriptors if descriptor is not None]
    if len(set(present)) != len(present):
        errors.append(f"{label} contains duplicate keys")
    return present


def validate_admin_event(
    value: dict[str, Any],
    event_type: str,
    policy: dict[str, Any],
    fixture: dict[str, Any],
    errors: list[str],
) -> tuple[datetime | None, dict[str, Any], dict[str, Any], list[str]]:
    expected = {
        "schema_version",
        "provider",
        "run_id",
        "event_type",
        "observed_at",
        "mutation",
        "readback",
        "state_before",
        "state_after",
        "discarded_response_fields",
        "source",
    }
    if not exact_keys(value, expected, event_type, errors):
        return None, {}, {}, []
    validate_discarded_fields(
        value.get("discarded_response_fields"), event_type, errors
    )
    rule_base = f"/v1/organizations/federation_rules/{policy['rule']['id']}"
    issuer_base = f"/v1/organizations/federation_issuers/{policy['issuer']['id']}"
    workspace = policy["workspace"]["id"]
    if event_type == "rule_disabled":
        mutation_method, mutation_path = "DELETE", f"{rule_base}/workspaces/{workspace}"
        before_count, after_count = [workspace], []
        readback_path = rule_base
    elif event_type == "rule_restored":
        mutation_method, mutation_path = "POST", f"{rule_base}/workspaces"
        before_count, after_count = [], [workspace]
        readback_path = rule_base
    else:
        mutation_method, mutation_path = "POST", issuer_base
        before_count = 1 if event_type == "issuer_rotation_staged" else 2
        after_count = 2 if event_type == "issuer_rotation_staged" else 1
        readback_path = issuer_base
    mutation_provider, mutation_observed, mutation_id = validate_receipt(
        value.get("mutation"),
        f"{event_type} mutation",
        mutation_method,
        mutation_path,
        errors,
    )
    readback_provider, readback_observed, readback_id = validate_receipt(
        value.get("readback"),
        f"{event_type} readback",
        "GET",
        readback_path,
        errors,
    )
    event_observed = parse_time(value.get("observed_at"), f"{event_type} observed_at", errors)
    if all(item is not None for item in (mutation_observed, readback_observed, event_observed)):
        assert mutation_observed is not None and readback_observed is not None
        assert event_observed is not None
        if not mutation_observed < readback_observed or event_observed != readback_observed:
            errors.append(f"{event_type} mutation/readback timestamps are out of order")
    if (
        mutation_provider is not None
        and readback_provider is not None
        and mutation_provider > readback_provider
    ):
        errors.append(f"{event_type} provider receipts are out of order")
    before = value.get("state_before")
    after = value.get("state_after")
    if event_type.startswith("rule_"):
        validate_rule_state(before, policy, before_count, f"{event_type} state_before", errors)
        validate_rule_state(after, policy, after_count, f"{event_type} state_after", errors)
    else:
        validate_issuer_state(before, policy, before_count, f"{event_type} state_before", errors)
        validate_issuer_state(after, policy, after_count, f"{event_type} state_after", errors)
    validate_source(value.get("source"), event_type, fixture, errors)
    return (
        event_observed,
        before if isinstance(before, dict) else {},
        after if isinstance(after, dict) else {},
        [item for item in (mutation_id, readback_id) if item],
    )


def validate_activation(
    value: dict[str, Any], fixture: dict[str, Any], errors: list[str]
) -> tuple[datetime | None, tuple[str, str] | None, tuple[str, str] | None]:
    event_type = "replacement_key_activated"
    expected = {
        "schema_version",
        "provider",
        "run_id",
        "event_type",
        "observed_at",
        "activation",
        "source",
    }
    if not exact_keys(value, expected, event_type, errors):
        return None, None, None
    activation = value.get("activation")
    activation_expected = {
        "source",
        "active_key_path",
        "retired_key",
        "replacement_key",
        "retired_key_staged",
        "observed_at",
    }
    retired = replacement = None
    if exact_keys(activation, activation_expected, "replacement activation", errors):
        if activation.get("source") != "local_atomic_key_activation":
            errors.append("replacement activation source differs")
        if activation.get("active_key_path") != "/etc/patchyard/anthropic-wif-signing.pem":
            errors.append("replacement activation used the wrong active-key path")
        if activation.get("retired_key_staged") is not True:
            errors.append("replacement activation did not preserve the retired key for denial")
        retired = validate_key(activation.get("retired_key"), "activated retired key", errors)
        replacement = validate_key(
            activation.get("replacement_key"), "activated replacement key", errors
        )
    observed = parse_time(value.get("observed_at"), "replacement activation observed_at", errors)
    nested_observed = parse_time(
        activation.get("observed_at") if isinstance(activation, dict) else None,
        "replacement activation nested observed_at",
        errors,
    )
    if observed is not None and nested_observed is not None and observed != nested_observed:
        errors.append("replacement activation timestamps differ")
    validate_source(value.get("source"), event_type, fixture, errors)
    return observed, retired, replacement


def event_provider_times(
    event: dict[str, Any], event_type: str, errors: list[str]
) -> list[datetime]:
    values: list[tuple[Any, str]] = []
    if event_type in POSITIVE_EVENTS:
        exchange = event.get("exchange", {})
        models = event.get("models", {})
        values = [
            (exchange.get("provider_date"), f"{event_type} exchange chronology"),
            (models.get("provider_date"), f"{event_type} Models chronology"),
        ]
    elif event_type in DENIAL_EVENTS:
        denial = event.get("exchange_denial", {})
        values = [
            (denial.get("provider_date"), f"{event_type} denial chronology")
        ]
    elif event_type in ADMIN_EVENTS:
        mutation = event.get("mutation", {})
        readback = event.get("readback", {})
        values = [
            (mutation.get("provider_date"), f"{event_type} mutation chronology"),
            (readback.get("provider_date"), f"{event_type} readback chronology"),
        ]
    parsed = [parse_time(value, label, errors) for value, label in values]
    return [value for value in parsed if value is not None]


def validate_evidence(
    result: Any,
    policy: dict[str, Any],
    qualification_blockers: list[str],
) -> list[str]:
    errors: list[str] = []
    if isinstance(result, dict) and result.get("qualification_evidence") is False:
        errors.append("revocation evidence explicitly disclaims qualification")
        return errors
    if not exact_keys(result, REVOCATION_EVIDENCE_KEYS, "revocation fixture", errors):
        return errors
    if result.get("schema_version") != 1 or result.get("provider") != "anthropic":
        errors.append("revocation fixture identity differs")
    if result.get("qualification_requirement") != "federation-revocation-and-key-rotation":
        errors.append("revocation fixture names the wrong requirement")
    if result.get("authorization_ruling") != "A113":
        errors.append("revocation fixture names the wrong authorization")
    run_id = result.get("run_id")
    if RUN_ID.fullmatch(str(run_id or "")) is None:
        errors.append("revocation fixture run ID is malformed")
    if result.get("policy_sha256") != digest(POLICY_PATH):
        errors.append("revocation fixture is stale for the WIF policy")
    if result.get("lifecycle_harness_sha256") != digest(HARNESS_PATH):
        errors.append("revocation fixture is stale for the lifecycle harness")
    if result.get("revocation_harness_sha256") != digest(REVOCATION_HARNESS_PATH):
        errors.append("revocation fixture is stale for the revocation harness")
    if result.get("admin_tool_sha256") != digest(ADMIN_PATH):
        errors.append("revocation fixture is stale for the lifecycle admin tool")
    events = result.get("events")
    if not isinstance(events, list):
        errors.append("revocation fixture events are not an array")
        return errors
    observed_sequence = [
        event.get("event_type") if isinstance(event, dict) else None
        for event in events
    ]
    if observed_sequence != EVENT_SEQUENCE:
        errors.append("revocation fixture is missing or reorders a required event")
        return errors
    event_times: list[datetime] = []
    keys: dict[str, tuple[str, str] | None] = {}
    states: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    bracketing_request_ids: list[str] = []
    denial_request_ids: list[str] = []
    provider_times: list[datetime] = []
    events_by_type: dict[str, dict[str, Any]] = {}
    for event, event_type in zip(events, EVENT_SEQUENCE):
        events_by_type[event_type] = event
        if event.get("schema_version") != 1 or event.get("provider") != "anthropic":
            errors.append(f"{event_type} event identity differs")
        if event.get("run_id") != run_id or event.get("event_type") != event_type:
            errors.append(f"{event_type} run or event identity differs")
        if event_type in POSITIVE_EVENTS:
            observed, key, ids = validate_positive_event(
                event, event_type, policy, result, errors
            )
            keys[event_type] = key
        elif event_type in DENIAL_EVENTS:
            observed, key, ids = validate_denial_event(
                event,
                event_type,
                result,
                errors,
                qualification_blockers,
            )
            keys[event_type] = key
        elif event_type in ADMIN_EVENTS:
            observed, before, after, ids = validate_admin_event(
                event, event_type, policy, result, errors
            )
            states[event_type] = (before, after)
        else:
            observed, retired, replacement = validate_activation(event, result, errors)
            keys["activation_retired"] = retired
            keys["activation_replacement"] = replacement
            ids = []
        if observed is not None:
            event_times.append(observed)
        if event_type in DENIAL_EVENTS:
            denial_request_ids.extend(ids)
        else:
            bracketing_request_ids.extend(ids)
        provider_times.extend(event_provider_times(event, event_type, errors))
    if len(event_times) != len(EVENT_SEQUENCE) or any(
        earlier >= later for earlier, later in zip(event_times, event_times[1:])
    ):
        errors.append("revocation fixture event timestamps are not strictly ordered")
    if (
        len(bracketing_request_ids) != MANDATORY_BRACKETING_REQUEST_IDS
        or len(set(bracketing_request_ids)) != MANDATORY_BRACKETING_REQUEST_IDS
    ):
        errors.append(
            "revocation fixture does not bind "
            f"{MANDATORY_BRACKETING_REQUEST_IDS} distinct bracketing provider requests"
        )
    identified_request_ids = bracketing_request_ids + denial_request_ids
    if len(identified_request_ids) != EXPECTED_IDENTIFIED_PROVIDER_REQUEST_IDS:
        errors.append(
            "revocation fixture does not bind "
            f"{EXPECTED_IDENTIFIED_PROVIDER_REQUEST_IDS} identified provider requests"
        )
    if len(set(identified_request_ids)) != len(identified_request_ids):
        errors.append(
            "revocation fixture does not bind every distinct identified provider request"
        )
    if len(provider_times) != EXPECTED_PROVIDER_TIMESTAMPS or any(
        earlier > later for earlier, later in zip(provider_times, provider_times[1:])
    ):
        errors.append("revocation fixture provider timestamps are out of order")
    validate_settling_intervals(events_by_type, errors)
    validate_retirement_bracket(events_by_type, errors)
    current = keys.get("rule_enabled_positive")
    replacement = keys.get("replacement_key_positive")
    if current is None or replacement is None or current == replacement:
        errors.append("rotation does not bind distinct current and replacement keys")
    elif current[0] == replacement[0] or current[1] == replacement[1]:
        errors.append("rotation reuses a key ID or public-key thumbprint")
    if keys.get("rule_restored_positive") != current:
        errors.append("restored positive did not use the original active key")
    if keys.get("rule_disabled_exchange_denial") != current:
        errors.append("disabled-rule denial did not use the positive-control key")
    if keys.get("retired_key_exchange_denial") != current:
        errors.append("retired-key denial did not use the retired key")
    if keys.get("activation_retired") != current:
        errors.append("local activation did not replace the retired key")
    if keys.get("activation_replacement") != replacement:
        errors.append("local activation did not install the provider-proven replacement")
    if keys.get("replacement_key_final_positive") != replacement:
        errors.append("final positive did not use the activated replacement key")
    if keys.get("post_retirement_active_positive") != replacement:
        errors.append("first post-retirement control did not use the active replacement key")
    if keys.get("post_retirement_active_positive_final") != replacement:
        errors.append("final post-retirement control did not use the active replacement key")
    stage_before, stage_after = states.get("issuer_rotation_staged", ({}, {}))
    retire_before, retire_after = states.get("issuer_retired_key", ({}, {}))
    stage_before_keys = [
        validate_key(item, "stage-before continuity key", errors)
        for item in stage_before.get("keys", [])
    ]
    stage_after_keys = [
        validate_key(item, "stage-after continuity key", errors)
        for item in stage_after.get("keys", [])
    ]
    retire_before_keys = [
        validate_key(item, "retire-before continuity key", errors)
        for item in retire_before.get("keys", [])
    ]
    retire_after_keys = [
        validate_key(item, "retire-after continuity key", errors)
        for item in retire_after.get("keys", [])
    ]
    if stage_before_keys != [current]:
        errors.append("issuer stage did not begin from the positive-control key")
    if set(stage_after_keys) != {current, replacement}:
        errors.append("issuer stage did not preserve old plus replacement keys")
    if set(retire_before_keys) != {current, replacement}:
        errors.append("issuer retirement did not begin from the staged overlap")
    if retire_after_keys != [replacement]:
        errors.append("issuer retirement did not leave only the replacement key")
    forbidden = secret_named_key(result)
    if forbidden is not None:
        errors.append(f"revocation fixture contains forbidden credential field: {forbidden}")
    serialized = json.dumps(result, sort_keys=True)
    if re.search(r"sk-ant-[A-Za-z0-9_-]+", serialized):
        errors.append("revocation fixture contains an Anthropic credential")
    if re.search(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", serialized):
        errors.append("revocation fixture contains a JWT assertion")
    return errors


def validate_contract_fixture(
    result: Any,
    policy: dict[str, Any],
    qualification_blockers: list[str],
) -> list[str]:
    errors: list[str] = []
    expected = REVOCATION_EVIDENCE_KEYS | set(CONTRACT_FIXTURE_METADATA)
    if not exact_keys(result, expected, "revocation contract fixture", errors):
        return errors
    if result.get("fixture_kind") != CONTRACT_FIXTURE_METADATA["fixture_kind"]:
        errors.append("revocation contract fixture kind differs")
    if result.get("provider_response_observed") is not False:
        errors.append("revocation contract fixture claims a provider response")
    if result.get("qualification_evidence") is not False:
        errors.append("revocation contract fixture claims qualification")
    if errors:
        return errors
    evidence_shape = {key: result[key] for key in REVOCATION_EVIDENCE_KEYS}
    return validate_evidence(evidence_shape, policy, qualification_blockers)


def validate_observed_rule_denial(result: Any) -> list[str]:
    """Validate the captured A126 terminal record, not qualification evidence."""

    errors: list[str] = []
    expected = {
        "schema_version",
        "provider",
        "status",
        "action",
        "run_id",
        "started_at",
        "failed_at",
        "failure_type",
        "failure_reason",
        "failure_phase",
        "partial_evidence",
        "post_failure_state",
        "source",
    }
    if not exact_keys(result, expected, "observed rule-disabled denial", errors):
        return errors
    if result.get("schema_version") != 1 or result.get("provider") != "anthropic":
        errors.append("observed rule-disabled denial identity differs")
    if result.get("status") != "failed" or result.get("action") != "exchange-denial":
        errors.append("observed rule-disabled denial is not its terminal capture")
    if RUN_ID.fullmatch(str(result.get("run_id") or "")) is None:
        errors.append("observed rule-disabled denial run ID is malformed")
    if (
        result.get("failure_type") != "LifecycleError"
        or result.get("failure_phase") != "denied_exchange_unexpected_response"
        or not isinstance(result.get("failure_reason"), str)
        or not result["failure_reason"]
    ):
        errors.append("observed rule-disabled denial failure provenance differs")

    source = result.get("source")
    if exact_keys(
        source,
        {"policy_sha256", "lifecycle_harness_sha256"},
        "observed rule-disabled denial source",
        errors,
    ):
        if source.get("policy_sha256") != digest(POLICY_PATH):
            errors.append("observed rule-disabled denial policy binding differs")
        if source.get("lifecycle_harness_sha256") != digest(HARNESS_PATH):
            errors.append("observed rule-disabled denial harness binding differs")

    partial = result.get("partial_evidence")
    partial_expected = {
        "endpoint",
        "http_status",
        "request_id",
        "provider_date",
        "observed_at",
        "error_type",
        "response_shape",
    }
    partial_observed = partial_provider = None
    if exact_keys(
        partial,
        partial_expected,
        "observed rule-disabled denial response",
        errors,
    ):
        if partial.get("endpoint") != "/v1/oauth/token":
            errors.append("observed rule-disabled denial used the wrong endpoint")
        if (
            partial.get("http_status") != 401
            or partial.get("error_type") != "authentication_error"
        ):
            errors.append("observed rule-disabled denial is not the provider response")
        if REQUEST_ID.fullmatch(str(partial.get("request_id") or "")) is None:
            errors.append("observed rule-disabled denial request ID is malformed")
        if partial.get("response_shape") != EXPECTED_ERROR_SHAPE:
            errors.append("observed rule-disabled denial response shape differs")
        partial_provider = parse_time(
            partial.get("provider_date"),
            "observed rule-disabled denial provider_date",
            errors,
        )
        partial_observed = parse_time(
            partial.get("observed_at"),
            "observed rule-disabled denial observed_at",
            errors,
        )
        if (
            partial_provider is not None
            and partial_observed is not None
            and partial_provider > partial_observed
        ):
            errors.append(
                "observed rule-disabled denial provider Date follows its observation"
            )

    started = parse_time(
        result.get("started_at"), "observed rule-disabled denial started_at", errors
    )
    failed = parse_time(
        result.get("failed_at"), "observed rule-disabled denial failed_at", errors
    )
    if all(value is not None for value in (started, partial_observed, failed)):
        assert started is not None and partial_observed is not None and failed is not None
        if not started <= partial_observed <= failed:
            errors.append("observed rule-disabled denial UTC bracket is out of order")
    if result.get("post_failure_state") != {"credential_process_exiting": True}:
        errors.append("observed rule-disabled denial cleanup state differs")

    forbidden = secret_named_key(result)
    if forbidden is not None:
        errors.append(
            f"observed rule-disabled denial contains forbidden credential field: {forbidden}"
        )
    serialized = json.dumps(result, sort_keys=True)
    if re.search(r"sk-ant-[A-Za-z0-9_-]+", serialized):
        errors.append("observed rule-disabled denial contains an Anthropic credential")
    if re.search(
        r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", serialized
    ):
        errors.append("observed rule-disabled denial contains a JWT assertion")
    return errors


def static_errors() -> tuple[list[str], dict[str, Any]]:
    errors = isolation_errors()
    for relative, expected in PROTECTED_SOURCES.items():
        path = REPO / relative
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            errors.append(f"protected host contract differs: {relative}")
    for path, label in (
        (HARNESS_PATH, "lifecycle harness"),
        (REVOCATION_HARNESS_PATH, "revocation harness"),
        (ADMIN_PATH, "admin tool"),
    ):
        if not path.is_file() or path.is_symlink():
            errors.append(f"Anthropic {label} is missing or a symlink")
    if HARNESS_PATH.is_file():
        harness = HARNESS_PATH.read_text()
        for required in (
            '"rule_disabled_exchange_denial"',
            '"retired_key_exchange_denial"',
            '"replacement_key_activated"',
            '"source": "anthropic_http_response"',
            '"partial_evidence": partial_evidence',
            'STAGING_ROOT = Path("/run/patchyard-anthropic")',
            'if filesystem != "tmpfs"',
        ):
            if required not in harness:
                errors.append(f"lifecycle harness is missing: {required}")
    if REVOCATION_HARNESS_PATH.is_file():
        revocation_harness = REVOCATION_HARNESS_PATH.read_text()
        for required in (
            '"exchange-positive"',
            'exchange["exchange"]["request_started_at"] = request_started_at',
            "BASE.accepted_exchange = accepted_exchange",
            "BASE.POSITIVE_EVENT_TYPES.update(POST_RETIREMENT_POSITIVE_EVENT_TYPES)",
            '"post_retirement_active_positive"',
            '"post_retirement_active_positive_final"',
            'status == 401 and error_type == "authentication_error"',
            '"request_id_supplied": request_id is not None',
            '"request_started_at": response["requested_at"]',
            '"revocation_harness_sha256"',
            'not 400 <= status <= 499',
        ):
            if required not in revocation_harness:
                errors.append(f"revocation harness is missing: {required}")
    if ADMIN_PATH.is_file():
        admin = ADMIN_PATH.read_text()
        for required in (
            'method = "DELETE"',
            'event_type = "rule_restored"',
            'event_type = "issuer_rotation_staged"',
            'event_type = "issuer_rotation_rolled_back"',
            'event_type = "issuer_retired_key"',
            'event_type = "issuer_retired_key_restored"',
            '{"jwks": {"type": "inline", "keys": target}}',
            "post_failure_readback",
            '"status": "in_progress"',
        ):
            if required not in admin:
                errors.append(f"lifecycle admin tool is missing: {required}")
    for source_path in (HARNESS_PATH, REVOCATION_HARNESS_PATH, ADMIN_PATH):
        if source_path.is_file():
            source = source_path.read_text()
            for forbidden in PROTECTED_SOURCES:
                if forbidden in source:
                    errors.append(
                        f"{source_path.name} invokes protected source: {forbidden}"
                    )
    policy = load_json_file(POLICY_PATH)
    providers = load_json_file(REPO / "policy/provider-egress.json")["providers"]
    if len(providers) != 13:
        errors.append("provider egress policy does not contain 13 providers")
    return errors, policy


def main() -> int:
    errors, policy = static_errors()
    qualification_blockers: list[str] = []
    evidence_path = RESULT_PATH
    evidence_path_supplied = False
    allow_missing = False
    observed_denial_path: Path | None = None
    contract_fixture_path: Path | None = None
    arguments = sys.argv[1:]
    while arguments:
        argument = arguments.pop(0)
        if argument == "--allow-missing-results":
            allow_missing = True
        elif argument == "--evidence" and arguments:
            evidence_path = Path(arguments.pop(0))
            evidence_path_supplied = True
        elif argument == "--observed-denial" and arguments:
            observed_denial_path = Path(arguments.pop(0))
        elif argument == "--contract-fixture" and arguments:
            contract_fixture_path = Path(arguments.pop(0))
        else:
            errors.append(f"unknown checker argument: {argument}")
    if observed_denial_path is not None:
        if allow_missing or evidence_path_supplied or contract_fixture_path:
            errors.append("observed-denial mode cannot be combined with evidence options")
        try:
            if not observed_denial_path.is_file() or observed_denial_path.is_symlink():
                raise EvidenceJsonError(
                    "observed denial is not a regular non-symlink file"
                )
            observation = load_json_file(observed_denial_path)
        except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
            errors.append(f"cannot read observed rule-disabled denial: {error}")
        else:
            errors.extend(validate_observed_rule_denial(observation))
    elif contract_fixture_path is not None:
        if allow_missing or evidence_path_supplied:
            errors.append("contract-fixture mode cannot be combined with evidence options")
        try:
            if not contract_fixture_path.is_file() or contract_fixture_path.is_symlink():
                raise EvidenceJsonError(
                    "contract fixture is not a regular non-symlink file"
                )
            contract_fixture = load_json_file(contract_fixture_path)
        except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
            errors.append(f"cannot read revocation contract fixture: {error}")
        else:
            errors.extend(
                validate_contract_fixture(
                    contract_fixture,
                    policy,
                    qualification_blockers,
                )
            )
    elif not evidence_path.exists():
        if not allow_missing:
            errors.append("committed Anthropic revocation result is missing")
    else:
        try:
            if not evidence_path.is_file() or evidence_path.is_symlink():
                raise EvidenceJsonError("evidence is not a regular non-symlink file")
            result = load_json_file(evidence_path)
        except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
            errors.append(f"cannot read revocation evidence: {error}")
        else:
            errors.extend(
                validate_evidence(result, policy, qualification_blockers)
            )
    if errors:
        print("Anthropic revocation check: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    if qualification_blockers:
        print(
            json.dumps(
                {
                    "checker": "anthropic-revocation",
                    "evidence_status": "accepted",
                    "qualification_status": "blocked",
                    "signals": [
                        {
                            "code": "unpinned_denial_contract",
                            "event_type": event_type,
                            "required_action": "add_observed_contract",
                        }
                        for event_type in sorted(set(qualification_blockers))
                    ],
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return QUALIFICATION_BLOCKED_EXIT
    if observed_denial_path is not None:
        status = "observed rule-disabled denial; not qualification evidence"
    elif contract_fixture_path is not None:
        status = "synthetic contract fixture; not qualification evidence"
    elif evidence_path != RESULT_PATH:
        status = "with supplied evidence"
    else:
        status = (
            "with conforming committed result"
            if evidence_path.exists()
            else "static preflight"
        )
    print(f"Anthropic revocation check: pass ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
