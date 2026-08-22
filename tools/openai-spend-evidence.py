#!/usr/bin/env python3
"""Capture OpenAI project cost and finalize sanitized A132 requirement-2 evidence.

Mirrors tools/anthropic-spend-evidence.py for the OpenAI spend-enforcement
qualification. Two commands:

- ``snapshot`` reads the OpenAI Costs API (a receipt-backed measurement
  independent of the console) with the standing Administration key and writes a
  bounded cost snapshot for the factory project.
- ``finalize`` validates the three phase evidence files emitted by
  worker/qualification/patchyard-run-openai-spend, the before/after cost
  snapshots, the organization-cap console readbacks, and the mutation
  authorization (A148 route authorization for remaining runs on this map, or
  an A132 human-attested record), then assembles the committable Result.

Requirement 2's causal chain runs through a console-only mutation (the
organization spend limit has no Administration API surface), so the Result
carries ``mutation_receipt_obtained: false`` permanently. Per A125 the refusal
predicate is unenforced: the temporary_refusal response is recorded as it
arrived and this finalizer requires the observation to say so.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
from typing import Any
import urllib.parse
import urllib.request
import hashlib
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
RUNTIME = types.ModuleType("factory_checker_runtime_openai_spend_evidence")
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


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy" / "openai-wif.json"
QUALIFICATION_POLICY_PATH = ROOT / "policy" / "provider-qualification.json"
BASE_URL = "https://api.openai.com"
ADMIN_KEY_ENVIRONMENT_VARIABLE = "PATCHYARD_OPENAI_ADMIN_KEY"
COST_BUCKET_LIMIT = 31
SETTLING_FLOOR_SECONDS = 90
CAPTURE_METHOD = "operator_console_readback_bounded_by_control_plane_utc"
REFUSAL_UNENFORCED_BASIS = "no-observed-openai-spend-refusal"
MUTATION_SURFACE = "organization-limits-console"
PROVIDER_MODEL = "gpt-5.6-luna"
PROVIDER_ENDPOINT = "/v1/chat/completions"
REQUEST_ID_PATTERN = re.compile(r"req_[A-Za-z0-9]{8,64}")
EXCHANGE_REQUEST_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
BOUNDED_STRING = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:-]{0,63}")
BOUNDED_CHANGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .,$'()_:-]{0,255}")
PHASES = (
    "operational_acceptance",
    "temporary_refusal",
    "restored_acceptance",
)
TEARDOWN = {
    "processes": 0,
    "taps": 0,
    "nftables_tables": 0,
    "run_directories": 0,
    "credential_files": 0,
    "guest_provider_egress_packets": 0,
}
DELIVERY = {
    "worker_host_tmpfs": True,
    "credential_delivered_to_guest": False,
    "credential_removed_before_guest_boot": True,
    "assertion_delivered": False,
    "signing_key_delivered": False,
    "admin_credential_delivered": False,
}
CONTROL_PLANE_PROVENANCE = {
    "management_surface": "console-only",
    "mutation_receipt_obtained": False,
    "attestation_required": True,
}
ROUTE_AUTHORIZATION_SOURCE = "route authorization"
ROUTE_AUTHORIZATION_RULING = "A148"
ROUTE_AUTHORIZATION_MAP_URL = (
    "https://github.com/JacobStephens2/patchyard/issues/176"
)
ROUTE_AUTHORIZATION_GRANT_URL = (
    "https://github.com/JacobStephens2/patchyard/issues/253"
)
AUTHORIZATION_AUTHOR = "JacobStephens2"
ROUTE_AUTHORIZATION_KEYS = {
    "source",
    "ruling",
    "map_url",
    "grant_url",
    "author_login",
    "human_attestation_obtained",
    "human_authorship_mechanically_proven",
}
ROUTE_ATTESTATION_KEYS = {
    "schema_version",
    "provider",
    "authorization_ruling",
    "human_authorization",
    "mutation_surface",
    "mutation_receipt_obtained",
    "mutations",
}


def iso_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


parse_time = RUNTIME.parse_time

def utc_day(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


def decimal_value(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("decimal figure is not a string")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("decimal figure is not finite")
    return number


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def cost_amount(value: Any) -> Decimal:
    """Convert a Costs API amount value (USD) without a float round trip."""
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int) and not isinstance(value, bool):
        number = Decimal(value)
    else:
        raise ValueError("OpenAI cost amount is not numeric")
    if not number.is_finite() or number < 0:
        raise ValueError("OpenAI cost amount is not a finite non-negative value")
    return number


def admin_key() -> str:
    value = os.environ.get(ADMIN_KEY_ENVIRONMENT_VARIABLE, "")
    if not value:
        raise ValueError(
            f"{ADMIN_KEY_ENVIRONMENT_VARIABLE} is empty; launch through va"
        )
    return value


def fetch_project_cost(policy: dict[str, Any]) -> dict[str, Any]:
    key = admin_key()
    project_id = policy["project"]["id"]
    captured_at = datetime.now(timezone.utc).replace(microsecond=0)
    start = captured_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    params: dict[str, Any] = {
        "start_time": int(start.timestamp()),
        "limit": COST_BUCKET_LIMIT,
        "group_by": "project_id",
    }
    amount = Decimal(0)
    matched_project = False
    project_cost_utc_days: set[str] = set()
    page: str | None = None
    while True:
        query = dict(params)
        if page is not None:
            query["page"] = page
        request = urllib.request.Request(
            BASE_URL + "/v1/organization/costs?" + urllib.parse.urlencode(query),
            headers={
                "authorization": f"Bearer {key}",
                "user-agent": "patchyard-openai-spend-evidence/1",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(
                response.read().decode(), parse_float=Decimal
            )
        for bucket in payload.get("data", []):
            bucket_start = bucket.get("start_time")
            if not isinstance(bucket_start, int) or isinstance(bucket_start, bool):
                raise ValueError("OpenAI Costs API returned a malformed bucket")
            bucket_day = utc_day(
                datetime.fromtimestamp(bucket_start, timezone.utc)
            )
            for result in bucket.get("results", []):
                if result.get("project_id") != project_id:
                    continue
                matched_project = True
                project_cost_utc_days.add(bucket_day)
                bucket_amount = result.get("amount", {})
                if not isinstance(bucket_amount, dict) or str(
                    bucket_amount.get("currency", "")
                ).upper() != "USD":
                    raise ValueError("OpenAI returned a non-USD factory cost")
                amount += cost_amount(bucket_amount.get("value"))
        page = payload.get("next_page")
        if not payload.get("has_more"):
            break
        if not isinstance(page, str) or not page:
            raise ValueError("OpenAI costs pagination is malformed")
    if not matched_project:
        raise ValueError("OpenAI Costs API returned no factory project row")
    return {
        "schema_version": 1,
        "provider": "openai",
        "organization_id": policy["organization"]["id"],
        "project_id": project_id,
        "captured_at": iso_time(captured_at),
        "reporting_window": {
            "starting_at": iso_time(start),
            "ending_at": iso_time(captured_at),
        },
        "currency": "USD",
        "cost_usd": decimal_text(amount),
        "project_cost_utc_days": sorted(project_cost_utc_days),
    }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def phase_cap_cents(qualification_policy: dict[str, Any], phase: str) -> int:
    caps = qualification_policy["providers"]["openai"]["phase_spend_cap_cents"]
    value = caps[phase]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{phase} spend cap is malformed in policy")
    return value


def validate_snapshot(
    snapshot: dict[str, Any], policy: dict[str, Any]
) -> tuple[Decimal, datetime, datetime]:
    if set(snapshot) != {
        "schema_version",
        "provider",
        "organization_id",
        "project_id",
        "captured_at",
        "reporting_window",
        "currency",
        "cost_usd",
        "project_cost_utc_days",
    }:
        raise ValueError("cost snapshot has an unexpected shape")
    if (
        snapshot["schema_version"] != 1
        or snapshot["provider"] != "openai"
        or snapshot["organization_id"] != policy["organization"]["id"]
        or snapshot["project_id"] != policy["project"]["id"]
        or snapshot["currency"] != "USD"
    ):
        raise ValueError("cost snapshot identity differs from policy")
    try:
        amount = decimal_value(snapshot["cost_usd"])
        captured = parse_time(snapshot["captured_at"])
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("cost snapshot amount or time is malformed") from error
    if amount < 0:
        raise ValueError("cost snapshot amount is negative")
    window = snapshot["reporting_window"]
    if not isinstance(window, dict) or set(window) != {"starting_at", "ending_at"}:
        raise ValueError("cost snapshot reporting window is malformed")
    try:
        window_start = parse_time(window["starting_at"])
        window_end = parse_time(window["ending_at"])
    except (TypeError, ValueError) as error:
        raise ValueError("cost snapshot reporting window is malformed") from error
    if window_start >= window_end or window_start > captured:
        raise ValueError("cost snapshot reporting window is malformed")
    days = snapshot["project_cost_utc_days"]
    if not isinstance(days, list) or days != sorted(set(days)):
        raise ValueError("cost snapshot project UTC days are malformed")
    for day in days:
        if datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d") != day:
            raise ValueError("cost snapshot project UTC days are malformed")
    return amount, captured, window_start


def validate_cap_readbacks(
    readbacks: dict[str, Any],
    policy: dict[str, Any],
    qualification_policy: dict[str, Any],
) -> dict[str, tuple[datetime, datetime]]:
    if set(readbacks) != {
        "schema_version",
        "provider",
        "organization_id",
        "project_id",
        *PHASES,
    }:
        raise ValueError("cap readbacks have an unexpected shape")
    if (
        readbacks["schema_version"] != 1
        or readbacks["provider"] != "openai"
        or readbacks["organization_id"] != policy["organization"]["id"]
        or readbacks["project_id"] != policy["project"]["id"]
    ):
        raise ValueError("cap readback identity differs from policy")
    intervals: dict[str, tuple[datetime, datetime]] = {}
    for phase in PHASES:
        observed = readbacks[phase]
        if set(observed) != {
            "captured_before_at",
            "captured_after_at",
            "organization_monthly_limit_usd",
            "hard_limit_enforced",
            "capture_method",
        }:
            raise ValueError(f"{phase} cap readback has an unexpected shape")
        before = parse_time(observed["captured_before_at"])
        after = parse_time(observed["captured_after_at"])
        if before > after or (after - before).total_seconds() > 300:
            raise ValueError(f"{phase} cap readback is not tightly time-bounded")
        if observed["capture_method"] != CAPTURE_METHOD:
            raise ValueError(f"{phase} cap readback lacks an independent UTC bound")
        expected_limit = Decimal(
            phase_cap_cents(qualification_policy, phase)
        ) / 100
        if decimal_value(observed["organization_monthly_limit_usd"]) != (
            expected_limit
        ):
            raise ValueError(f"{phase} organization cap differs from policy")
        if observed["hard_limit_enforced"] is not (
            phase == "temporary_refusal"
        ):
            raise ValueError(f"{phase} hard-limit enforcement differs from the plan")
        intervals[phase] = (before, after)
    return intervals


def validate_mutations(mutations: Any, label: str) -> None:
    if (
        not isinstance(mutations, list)
        or [item.get("phase") for item in mutations if isinstance(item, dict)]
        != ["temporary_refusal", "restored_acceptance"]
    ):
        raise ValueError(f"{label} does not record exactly two mutations")
    for item in mutations:
        if set(item) != {"phase", "change"}:
            raise ValueError(f"{label} mutation has an unexpected shape")
        change = item["change"]
        if not isinstance(change, str) or BOUNDED_CHANGE.fullmatch(change) is None:
            raise ValueError(f"{label} change is not a bounded description")


def validate_route_authorization(authorization: Any) -> None:
    if not isinstance(authorization, dict) or set(authorization) != (
        ROUTE_AUTHORIZATION_KEYS
    ):
        raise ValueError("route authorization has an unexpected shape")
    if authorization.get("source") != ROUTE_AUTHORIZATION_SOURCE:
        raise ValueError("authorization source is not a route authorization")
    if authorization.get("ruling") != ROUTE_AUTHORIZATION_RULING:
        raise ValueError("route authorization does not name A148")
    if authorization.get("map_url") != ROUTE_AUTHORIZATION_MAP_URL:
        raise ValueError("route authorization does not name the map")
    if authorization.get("grant_url") != ROUTE_AUTHORIZATION_GRANT_URL:
        raise ValueError("route authorization does not name the grant")
    if authorization.get("author_login") != AUTHORIZATION_AUTHOR:
        raise ValueError("authorization author is not the accountable human")
    if authorization.get("human_attestation_obtained") is not False:
        raise ValueError("authorization claims a human attestation")
    if authorization.get("human_authorship_mechanically_proven") is not False:
        raise ValueError("authorization claims mechanically proven authorship")


def validate_attestation(attestation: dict[str, Any]) -> dict[str, Any]:
    if set(attestation) == ROUTE_ATTESTATION_KEYS:
        if (
            attestation["schema_version"] != 1
            or attestation["provider"] != "openai"
            or attestation["authorization_ruling"] != ROUTE_AUTHORIZATION_RULING
            or attestation["mutation_surface"] != MUTATION_SURFACE
            or attestation["mutation_receipt_obtained"] is not False
        ):
            raise ValueError("A148 route-authorization record identity is malformed")
        validate_route_authorization(attestation["human_authorization"])
        validate_mutations(attestation["mutations"], "A148 route-authorization record")
        return attestation
    if set(attestation) != {
        "schema_version",
        "provider",
        "authorization_ruling",
        "actor",
        "attester",
        "independent_attestation",
        "mutation_surface",
        "mutation_receipt_obtained",
        "mutations",
    }:
        raise ValueError("A132 attestation has an unexpected shape")
    if (
        attestation["schema_version"] != 1
        or attestation["provider"] != "openai"
        or attestation["authorization_ruling"] != "A132"
        or attestation["mutation_surface"] != MUTATION_SURFACE
        or attestation["mutation_receipt_obtained"] is not False
    ):
        raise ValueError("A132 attestation identity is malformed")
    actor = attestation["actor"]
    attester = attestation["attester"]
    for name in (actor, attester):
        if not isinstance(name, str) or BOUNDED_STRING.fullmatch(name) is None:
            raise ValueError("A132 attestation party is not a bounded name")
    # A136: when one person is both actor and attester the record carries no
    # independence and must never be read as corroboration.
    if actor == attester and attestation["independent_attestation"] is not False:
        raise ValueError("A132 attestation claims independence it cannot have")
    if not isinstance(attestation["independent_attestation"], bool):
        raise ValueError("A132 attestation independence is not boolean")
    validate_mutations(attestation["mutations"], "A132 attestation")
    return attestation


def validate_phase(
    evidence: dict[str, Any],
    phase: str,
    policy: dict[str, Any],
    qualification_policy: dict[str, Any],
) -> datetime:
    expected_keys = {
        "schema_version",
        "run_id",
        "base_sha",
        "request_sha256",
        "provider",
        "qualification_requirement",
        "authorization_ruling",
        "qualification_phase",
        "patch_sha256",
        "observed_rootfs_sha256",
        "image_recipe_sha256",
        "production_parity_sha256",
        "git_remote_count",
        "host_contract_sha256",
        "qualification_policy_sha256",
        "credential_removed_before_output",
        "issuance",
        "delivery",
        "provider_transport",
        "provider_observation",
        "observation_predicate",
        "host_teardown",
    }
    if set(evidence) != expected_keys:
        raise ValueError(f"{phase} worker evidence has an unexpected shape")
    if (
        evidence["schema_version"] != 1
        or evidence["provider"] != "openai"
        or evidence["qualification_requirement"] != "provider-spend-enforcement"
        or evidence["authorization_ruling"] != "A132"
        or evidence["qualification_phase"] != phase
        or evidence["git_remote_count"] != 0
        or evidence["credential_removed_before_output"] is not True
        or evidence["delivery"] != DELIVERY
        or evidence["host_teardown"] != TEARDOWN
        or evidence["observation_predicate"]
        != {"endpoint": PROVIDER_ENDPOINT, "refusal_predicate_enforced": False}
    ):
        raise ValueError(f"{phase} worker boundary differs from the A133 contract")
    for name in (
        "request_sha256",
        "patch_sha256",
        "observed_rootfs_sha256",
        "image_recipe_sha256",
        "production_parity_sha256",
        "host_contract_sha256",
        "qualification_policy_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(evidence[name])):
            raise ValueError(f"{phase} {name} is malformed")

    issuance = evidence["issuance"]
    if set(issuance) != {
        "issued_at",
        "expires_at",
        "expires_in",
        "exchange_request_id",
        "token_type",
        "scope",
        "service_account_id",
        "rule_id",
        "workspace_id",
    }:
        raise ValueError(f"{phase} issuance has an unexpected shape")
    if (
        issuance["workspace_id"] != policy["project"]["id"]
        or issuance["service_account_id"] != policy["service_account"]["id"]
        or issuance["rule_id"] != policy["issuer"]["id"]
        or issuance["scope"] != "unscoped"
        or issuance["token_type"] != "Bearer"
        or EXCHANGE_REQUEST_ID_PATTERN.fullmatch(
            str(issuance["exchange_request_id"])
        )
        is None
    ):
        raise ValueError(f"{phase} principal differs from policy")
    issued = parse_time(issuance["issued_at"])
    expires = parse_time(issuance["expires_at"])
    if int((expires - issued).total_seconds()) != issuance["expires_in"]:
        raise ValueError(f"{phase} bearer lifetime is malformed")
    if not 60 <= issuance["expires_in"] <= 300:
        raise ValueError(f"{phase} bearer lifetime is outside policy")

    transport = evidence["provider_transport"]
    if (
        set(transport)
        != {
            "schema_version",
            "authorization_ruling",
            "mechanism",
            "http_version",
            "connection_close",
            "client_sha256",
            "admitted_conntrack_ids",
            "admitted_new_connections",
            "rejected_new_connections",
            "rejected_connection_packets",
            "guest_provider_allowlist_entries",
            "namespace_ipv6_disabled",
            "credential_removed_before_guest_boot",
        }
        or transport["schema_version"] != 1
        or transport["authorization_ruling"] != "A117"
        or transport["mechanism"] != "host-one-shot-network-namespace-v1"
        or transport["http_version"] != "1.0"
        or transport["connection_close"] is not True
        or not re.fullmatch(r"[0-9a-f]{64}", str(transport["client_sha256"]))
        or transport["admitted_conntrack_ids"] != 1
        or transport["admitted_new_connections"] != 1
        or transport["rejected_new_connections"] != 0
        or transport["rejected_connection_packets"] != 0
        or transport["guest_provider_allowlist_entries"] != 0
        or transport["namespace_ipv6_disabled"] is not True
        or transport["credential_removed_before_guest_boot"] is not True
    ):
        raise ValueError(f"{phase} provider transport differs from A117")

    observation = evidence["provider_observation"]
    expected_cap = phase_cap_cents(qualification_policy, phase)
    common = {
        "endpoint",
        "http_status",
        "observed_at",
        "request_id",
        "request_id_supplied",
        "request_body_sha256",
        "request_attempts",
        "expected_project_cap_cents",
        "outcome",
    }
    if (
        observation.get("endpoint") != PROVIDER_ENDPOINT
        or observation.get("request_attempts") != 1
        or observation.get("expected_project_cap_cents") != expected_cap
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(observation.get("request_body_sha256", ""))
        )
    ):
        raise ValueError(f"{phase} provider request differs from the A133 contract")
    request_id = observation.get("request_id")
    supplied = observation.get("request_id_supplied")
    if not isinstance(supplied, bool) or supplied != (request_id is not None):
        raise ValueError(f"{phase} request-id record is inconsistent")
    if request_id is not None and (
        not isinstance(request_id, str)
        or REQUEST_ID_PATTERN.fullmatch(request_id) is None
    ):
        raise ValueError(f"{phase} request id is malformed")
    observed = parse_time(observation.get("observed_at"))
    if not issued <= observed < expires:
        raise ValueError(f"{phase} provider request is outside bearer lifetime")
    if phase == "temporary_refusal":
        # A125: no OpenAI spend refusal has been observed, so nothing about the
        # response body or status is required beyond the recorded hygiene
        # bounds - but the observation must say the predicate was unenforced.
        if set(observation) != common | {"response_predicate", "provider_error"}:
            raise ValueError("temporary refusal has an unexpected shape")
        if observation.get("outcome") != "refused" or observation.get(
            "response_predicate"
        ) != {"enforced": False, "basis": REFUSAL_UNENFORCED_BASIS}:
            raise ValueError("temporary refusal does not record A125 unenforcement")
        status = observation.get("http_status")
        if not isinstance(status, int) or isinstance(status, bool):
            raise ValueError("temporary refusal status is not recorded")
        error = observation.get("provider_error")
        shape = error.get("shape", {}) if isinstance(error, dict) else {}
        if (
            not isinstance(error, dict)
            or set(error)
            != {
                "error_type",
                "error_code",
                "message_class",
                "message_sha256",
                "body_shape",
                "shape",
            }
            or error.get("message_class")
            not in {"spend_attributable", "unattributed"}
            or not re.fullmatch(
                r"[0-9a-f]{64}", str(error.get("message_sha256", ""))
            )
            or set(shape) != {"top_level_keys", "error_keys"}
            or not all(
                isinstance(keys, list)
                and len(keys) <= 16
                and all(
                    isinstance(key, str)
                    and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key)
                    for key in keys
                )
                for keys in shape.values()
            )
        ):
            raise ValueError("temporary refusal response is not safely diagnostic")
    else:
        if set(observation) != common | {"response_type", "model", "usage"}:
            raise ValueError(f"{phase} acceptance has an unexpected shape")
        usage = observation.get("usage", {})
        if (
            observation.get("outcome") != "accepted"
            or observation.get("http_status") != 200
            or observation.get("response_type") != "chat.completion"
            or observation.get("model") != PROVIDER_MODEL
            or set(usage) != {"prompt_tokens", "completion_tokens", "cached_tokens"}
            or not all(
                isinstance(usage[name], int) and usage[name] >= 1
                for name in ("prompt_tokens", "completion_tokens")
            )
            or not isinstance(usage["cached_tokens"], int)
            or usage["cached_tokens"] < 0
        ):
            raise ValueError(f"{phase} positive control was not accepted")
    return observed


def finalize(
    operational: dict[str, Any],
    refusal: dict[str, Any],
    restored: dict[str, Any],
    settled_before: dict[str, Any],
    settled_after: dict[str, Any],
    readbacks: dict[str, Any],
    attestation: dict[str, Any],
    policy: dict[str, Any],
    qualification_policy: dict[str, Any],
) -> dict[str, Any]:
    phases = {
        "operational_acceptance": operational,
        "temporary_refusal": refusal,
        "restored_acceptance": restored,
    }
    observed = {
        phase: validate_phase(evidence, phase, policy, qualification_policy)
        for phase, evidence in phases.items()
    }
    invariant_fields = (
        "base_sha",
        "request_sha256",
        "patch_sha256",
        "observed_rootfs_sha256",
        "image_recipe_sha256",
        "production_parity_sha256",
        "host_contract_sha256",
        "qualification_policy_sha256",
    )
    for field in invariant_fields:
        if len({phases[phase][field] for phase in PHASES}) != 1:
            raise ValueError(f"A132 phase {field} values differ")
    if (
        len(
            {
                phases[phase]["provider_observation"]["request_body_sha256"]
                for phase in PHASES
            }
        )
        != 1
    ):
        raise ValueError("A132 provider request bodies are not byte-identical")
    exchange_ids = [
        phases[phase]["issuance"]["exchange_request_id"] for phase in PHASES
    ]
    if len(set(exchange_ids)) != len(PHASES):
        raise ValueError("A132 phases did not use distinct WIF exchanges")
    issuance_windows = [
        (
            parse_time(phases[phase]["issuance"]["issued_at"]),
            parse_time(phases[phase]["issuance"]["expires_at"]),
        )
        for phase in PHASES
    ]
    if any(
        first[1] > second[0]
        for first, second in zip(issuance_windows, issuance_windows[1:])
    ):
        raise ValueError("A132 phase bearer lifetimes overlap")

    before_amount, before_time, before_window_start = validate_snapshot(
        settled_before, policy
    )
    after_amount, after_time, after_window_start = validate_snapshot(
        settled_after, policy
    )
    cap_times = validate_cap_readbacks(readbacks, policy, qualification_policy)
    attestation = validate_attestation(attestation)
    temporary_cap = Decimal(
        phase_cap_cents(qualification_policy, "temporary_refusal")
    ) / 100

    if before_window_start != after_window_start:
        raise ValueError("cost snapshots do not share a reporting-window start")
    if not (
        cap_times["operational_acceptance"][1]
        <= observed["operational_acceptance"]
        <= before_time
        <= cap_times["temporary_refusal"][0]
        <= cap_times["temporary_refusal"][1]
        <= observed["temporary_refusal"]
        <= cap_times["restored_acceptance"][0]
        <= cap_times["restored_acceptance"][1]
        <= observed["restored_acceptance"]
        <= after_time
    ):
        raise ValueError("A132 cost, cap, and provider observations are out of order")
    for phase in ("temporary_refusal", "restored_acceptance"):
        settling = (observed[phase] - cap_times[phase][1]).total_seconds()
        if settling < SETTLING_FLOOR_SECONDS:
            raise ValueError(
                f"{phase} provider call is inside the {SETTLING_FLOOR_SECONDS}s"
                " console settling floor"
            )
    month_keys = {
        (
            value.astimezone(timezone.utc).year,
            value.astimezone(timezone.utc).month,
        )
        for value in (
            *observed.values(),
            before_time,
            after_time,
            *(time for interval in cap_times.values() for time in interval),
        )
    }
    if len(month_keys) != 1:
        raise ValueError("A132 qualification crosses a monthly billing boundary")
    if before_amount <= temporary_cap:
        raise ValueError("temporary cap was not lowered below already-settled spend")
    if after_amount < before_amount:
        raise ValueError("post-restoration settled spend moved backwards")

    return {
        "schema_version": 1,
        "provider": "openai",
        "qualification_requirement": "provider-spend-enforcement",
        "authorization_ruling": "A132",
        "organization_id": policy["organization"]["id"],
        "project_id": policy["project"]["id"],
        "service_account_id": policy["service_account"]["id"],
        "request_binding": {
            "model": PROVIDER_MODEL,
            "endpoint": PROVIDER_ENDPOINT,
            "request_body_sha256": operational["provider_observation"][
                "request_body_sha256"
            ],
            "byte_identical_across_phases": True,
        },
        "refusal_predicate": {
            "enforced": False,
            "basis": REFUSAL_UNENFORCED_BASIS,
        },
        "phases": phases,
        "cap_control": readbacks,
        "attestation": attestation,
        "control_plane_provenance": CONTROL_PLANE_PROVENANCE,
        "cost_measurement": {
            "source": "OpenAI Costs API",
            "currency": "USD",
            "settled_spend_before_activation_usd": decimal_text(before_amount),
            "settled_spend_after_restoration_usd": decimal_text(after_amount),
            "incremental_spend_usd": decimal_text(after_amount - before_amount),
            "before_captured_at": settled_before["captured_at"],
            "after_captured_at": settled_after["captured_at"],
            "reporting_window_starting_at": settled_before["reporting_window"][
                "starting_at"
            ],
            "settling_floor_seconds": SETTLING_FLOOR_SECONDS,
            "attribution": (
                "A132_acceptance_refusal_acceptance_organization_cap_change"
            ),
        },
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--output", required=True, type=Path)
    final = subparsers.add_parser("finalize")
    final.add_argument("--operational-evidence", required=True, type=Path)
    final.add_argument("--refusal-evidence", required=True, type=Path)
    final.add_argument("--restored-evidence", required=True, type=Path)
    final.add_argument("--settled-before", required=True, type=Path)
    final.add_argument("--settled-after", required=True, type=Path)
    final.add_argument("--cap-readbacks", required=True, type=Path)
    final.add_argument("--attestation", required=True, type=Path)
    final.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    policy = load_json(POLICY_PATH)
    qualification_policy = load_json(QUALIFICATION_POLICY_PATH)
    if args.command == "snapshot":
        write_json(args.output, fetch_project_cost(policy))
        return 0
    result = finalize(
        load_json(args.operational_evidence),
        load_json(args.refusal_evidence),
        load_json(args.restored_evidence),
        load_json(args.settled_before),
        load_json(args.settled_after),
        load_json(args.cap_readbacks),
        load_json(args.attestation),
        policy,
        qualification_policy,
    )
    write_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
