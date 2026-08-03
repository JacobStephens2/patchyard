#!/usr/bin/env python3
"""Check A113 Anthropic rule revocation and signing-key rotation evidence."""

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
ADMIN_PATH = REPO / "tools/anthropic-wif-lifecycle-admin.py"
RESULT_PATH = REPO / "research/isolation/results/anthropic-revocation-rotation.json"
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
    "retired_key_exchange_denial",
]
POSITIVE_EVENTS = {
    "rule_enabled_positive": "active",
    "rule_restored_positive": "active",
    "replacement_key_positive": "replacement_staging",
    "replacement_key_final_positive": "active",
}
DENIAL_EVENTS = {
    "rule_disabled_exchange_denial": "active",
    "retired_key_exchange_denial": "retired_staging",
}
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
UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z"
)


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
    else:
        expected = {"policy_sha256", "lifecycle_harness_sha256"}
    if not exact_keys(value, expected, f"{event_type} source", errors):
        return
    if value.get("policy_sha256") != fixture.get("policy_sha256"):
        errors.append(f"{event_type} policy binding differs from the fixture")
    if event_type in ADMIN_EVENTS:
        if value.get("admin_tool_sha256") != fixture.get("admin_tool_sha256"):
            errors.append(f"{event_type} admin binding differs from the fixture")
    elif value.get("lifecycle_harness_sha256") != fixture.get(
        "lifecycle_harness_sha256"
    ):
        errors.append(f"{event_type} harness binding differs from the fixture")


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
    value: Any, policy: dict[str, Any], label: str, errors: list[str]
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
        "service_account_id",
        "rule_id",
        "workspace_id",
    }
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
        value.get("exchange"), policy, event_type, errors
    )
    models_provider, models_observed, models_request_id = validate_models(
        value.get("models"), event_type, errors
    )
    event_observed = parse_time(value.get("observed_at"), f"{event_type} observed_at", errors)
    removed = parse_time(
        value.get("credential_removed_at"), f"{event_type} credential_removed_at", errors
    )
    if models_observed is not None and event_observed is not None and models_observed != event_observed:
        errors.append(f"{event_type} event timestamp is not its Models observation")
    if all(item is not None for item in (exchange_observed, models_observed, removed)):
        assert exchange_observed is not None and models_observed is not None and removed is not None
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
        "provider_date",
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
        if denial.get("http_status") != 400 or denial.get("error_type") != "invalid_grant":
            errors.append(f"{event_type} is not the exact invalid-grant denial")
        request_id = denial.get("request_id")
        if REQUEST_ID.fullmatch(str(request_id or "")) is None:
            errors.append(f"{event_type} request ID is malformed")
        else:
            request_ids.append(request_id)
        if denial.get("response_shape") != EXPECTED_ERROR_SHAPE:
            errors.append(f"{event_type} sanitized response shape differs")
        denial_provider = parse_time(
            denial.get("provider_date"), f"{event_type} provider_date", errors
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
    event_observed = parse_time(value.get("observed_at"), f"{event_type} observed_at", errors)
    removed = parse_time(
        value.get("credential_removed_at"), f"{event_type} credential_removed_at", errors
    )
    if denial_observed is not None and event_observed is not None and denial_observed != event_observed:
        errors.append(f"{event_type} event timestamp is not its provider denial")
    if denial_observed is not None and removed is not None and denial_observed > removed:
        errors.append(f"{event_type} credential cleanup predates its denial")
    validate_source(value.get("source"), event_type, fixture, errors)
    return event_observed, key, request_ids


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
        "source",
    }
    if not exact_keys(value, expected, event_type, errors):
        return None, {}, {}, []
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


def validate_evidence(result: Any, policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_top = {
        "schema_version",
        "provider",
        "qualification_requirement",
        "authorization_ruling",
        "run_id",
        "policy_sha256",
        "lifecycle_harness_sha256",
        "admin_tool_sha256",
        "events",
    }
    if not exact_keys(result, expected_top, "revocation fixture", errors):
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
    if result.get("admin_tool_sha256") != digest(ADMIN_PATH):
        errors.append("revocation fixture is stale for the lifecycle admin tool")
    events = result.get("events")
    if not isinstance(events, list):
        errors.append("revocation fixture events are not an array")
        return errors
    observed_sequence = [event.get("event_type") if isinstance(event, dict) else None for event in events]
    if observed_sequence != EVENT_SEQUENCE:
        errors.append("revocation fixture is missing or reorders a required event")
        return errors
    event_times: list[datetime] = []
    keys: dict[str, tuple[str, str] | None] = {}
    states: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    request_ids: list[str] = []
    provider_times: list[datetime] = []
    for event, event_type in zip(events, EVENT_SEQUENCE):
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
            observed, key, ids = validate_denial_event(event, event_type, result, errors)
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
        request_ids.extend(ids)
        provider_times.extend(event_provider_times(event, event_type, errors))
    if len(event_times) != len(EVENT_SEQUENCE) or any(
        earlier >= later for earlier, later in zip(event_times, event_times[1:])
    ):
        errors.append("revocation fixture event timestamps are not strictly ordered")
    if len(request_ids) != 18 or len(set(request_ids)) != len(request_ids):
        errors.append("revocation fixture does not bind 18 distinct provider requests")
    if len(provider_times) != 18 or any(
        earlier > later for earlier, later in zip(provider_times, provider_times[1:])
    ):
        errors.append("revocation fixture provider timestamps are out of order")
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


def static_errors() -> tuple[list[str], dict[str, Any]]:
    errors = isolation_errors()
    for relative, expected in PROTECTED_SOURCES.items():
        path = REPO / relative
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            errors.append(f"protected host contract differs: {relative}")
    for path, label in ((HARNESS_PATH, "lifecycle harness"), (ADMIN_PATH, "admin tool")):
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
    for source_path in (HARNESS_PATH, ADMIN_PATH):
        if source_path.is_file():
            source = source_path.read_text()
            for forbidden in PROTECTED_SOURCES:
                if forbidden in source:
                    errors.append(
                        f"{source_path.name} invokes protected source: {forbidden}"
                    )
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
            errors.append("committed Anthropic revocation result is missing")
    else:
        try:
            if not evidence_path.is_file() or evidence_path.is_symlink():
                raise EvidenceJsonError("evidence is not a regular non-symlink file")
            result = load_json_file(evidence_path)
        except (OSError, json.JSONDecodeError, EvidenceJsonError) as error:
            errors.append(f"cannot read revocation evidence: {error}")
        else:
            errors.extend(validate_evidence(result, policy))
    if errors:
        print("Anthropic revocation check: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    status = "with live result" if evidence_path.exists() else "static preflight"
    print(f"Anthropic revocation check: pass ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
