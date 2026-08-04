#!/usr/bin/env python3
"""Capture Anthropic workspace cost and finalize sanitized A115 evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy" / "anthropic-wif.json"
BASE_URL = "https://api.anthropic.com"
COST_REPORT_DAILY_LIMIT = 31
A121_LEGACY_PRE_ACTIVATION_UTC_DAY = "2026-08-02"
A121_LEGACY_PRE_ACTIVATION_COST_USD = Decimal("3.84074")
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


def iso_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed


def utc_day(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


def utc_day_closed(request_at: datetime, captured_at: datetime) -> bool:
    return utc_day(captured_at) > utc_day(request_at)


def completely_covered_utc_days(
    starting_at: datetime, ending_at: datetime, captured_at: datetime
) -> list[str]:
    """Return closed UTC days whose complete extent is inside the report window."""
    start = starting_at.astimezone(timezone.utc)
    end = ending_at.astimezone(timezone.utc)
    captured = captured_at.astimezone(timezone.utc)
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    if day < start:
        day += timedelta(days=1)
    coverage_end = min(end, captured)
    complete: list[str] = []
    while day + timedelta(days=1) <= coverage_end:
        complete.append(day.date().isoformat())
        day += timedelta(days=1)
    return complete


def cost_bucket_utc_day(bucket: dict[str, Any]) -> str:
    try:
        return utc_day(parse_time(bucket["starting_at"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "Anthropic Cost Report returned a malformed daily bucket"
        ) from error


def decimal_value(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("decimal figure is not a string")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("decimal figure is not finite")
    return number


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def minor_units_to_usd(value: Decimal) -> Decimal:
    """Convert Anthropic Cost Report amounts (USD cents) to USD."""
    return value / Decimal(100)


def admin_token(profile: str) -> str:
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return subprocess.check_output(
        ["ant", "auth", "print-credentials", "--profile", profile, "--access-token"],
        env=env,
        text=True,
    ).strip()


def fetch_workspace_cost(profile: str, workspace_id: str) -> dict[str, Any]:
    token = admin_token(profile)
    # Bind closure to query start so a midnight-crossing read cannot promote an
    # open day to complete after its response was assembled.
    captured_at = datetime.now(timezone.utc).replace(microsecond=0)
    now = captured_at
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = now + timedelta(minutes=1)
    params = {
        "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "group_by[]": "workspace_id",
        "limit": COST_REPORT_DAILY_LIMIT,
    }
    amount_minor_units = Decimal(0)
    matched_workspace = False
    workspace_cost_utc_days: set[str] = set()
    page: str | None = None
    while True:
        query = dict(params)
        if page is not None:
            query["page"] = page
        request = urllib.request.Request(
            BASE_URL + "/v1/organizations/cost_report?" + urllib.parse.urlencode(query),
            headers={
                "authorization": f"Bearer {token}",
                "anthropic-version": "2023-06-01",
                "user-agent": "patchyard-anthropic-spend-evidence/3",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        for bucket in payload.get("data", []):
            bucket_day = cost_bucket_utc_day(bucket)
            for result in bucket.get("results", []):
                if result.get("workspace_id") != workspace_id:
                    continue
                matched_workspace = True
                workspace_cost_utc_days.add(bucket_day)
                if result.get("currency") != "USD":
                    raise ValueError("Anthropic returned a non-USD Factory cost")
                amount_minor_units += Decimal(result["amount"])
        page = payload.get("next_page")
        if not payload.get("has_more"):
            break
        if not isinstance(page, str) or not page:
            raise ValueError("Anthropic cost report pagination is malformed")
    if not matched_workspace:
        raise ValueError("Anthropic Cost Report returned no Factory workspace row")
    return {
        "schema_version": 3,
        "provider": "anthropic",
        "workspace_id": workspace_id,
        "captured_at": iso_time(captured_at),
        "reporting_window": {
            "starting_at": params["starting_at"],
            "ending_at": params["ending_at"],
        },
        "currency": "USD",
        "cost_usd": decimal_text(minor_units_to_usd(amount_minor_units)),
        "workspace_cost_utc_days": sorted(workspace_cost_utc_days),
        "complete_utc_days": completely_covered_utc_days(
            parse_time(params["starting_at"]),
            parse_time(params["ending_at"]),
            captured_at,
        ),
    }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def validate_snapshot(
    snapshot: dict[str, Any], workspace_id: str
) -> tuple[
    Decimal,
    datetime,
    frozenset[str] | None,
    frozenset[str] | None,
    datetime,
    datetime,
]:
    common_keys = {
        "schema_version",
        "provider",
        "workspace_id",
        "captured_at",
        "reporting_window",
        "currency",
        "cost_usd",
    }
    schema_version = snapshot.get("schema_version")
    expected_keys = {
        1: common_keys,
        2: common_keys | {"workspace_cost_utc_days"},
        3: common_keys | {"workspace_cost_utc_days", "complete_utc_days"},
    }.get(schema_version)
    if expected_keys is None or set(snapshot) != expected_keys:
        raise ValueError("cost snapshot has an unexpected shape")
    if (
        snapshot["provider"] != "anthropic"
        or snapshot["workspace_id"] != workspace_id
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
    if schema_version == 1:
        return amount, captured, None, None, window_start, window_end

    covered_days = frozenset(
        completely_covered_utc_days(window_start, window_end, captured)
    )

    raw_days = snapshot["workspace_cost_utc_days"]
    if not isinstance(raw_days, list) or not raw_days:
        raise ValueError("cost snapshot has no workspace-attributed UTC day")
    try:
        parsed_days = [datetime.strptime(day, "%Y-%m-%d") for day in raw_days]
    except (TypeError, ValueError) as error:
        raise ValueError("cost snapshot has a malformed workspace UTC day") from error
    if (
        raw_days != sorted(set(raw_days))
        or any(
            day != parsed.strftime("%Y-%m-%d")
            for day, parsed in zip(raw_days, parsed_days)
        )
    ):
        raise ValueError("cost snapshot workspace UTC days are not unique and ordered")
    if schema_version == 3:
        raw_complete_days = snapshot["complete_utc_days"]
        if not isinstance(raw_complete_days, list):
            raise ValueError("cost snapshot complete UTC days are malformed")
        try:
            parsed_complete_days = [
                datetime.strptime(day, "%Y-%m-%d") for day in raw_complete_days
            ]
        except (TypeError, ValueError) as error:
            raise ValueError("cost snapshot complete UTC days are malformed") from error
        if (
            raw_complete_days != sorted(set(raw_complete_days))
            or any(
                day != parsed.strftime("%Y-%m-%d")
                for day, parsed in zip(raw_complete_days, parsed_complete_days)
            )
            or frozenset(raw_complete_days) != covered_days
        ):
            raise ValueError(
                "cost snapshot complete UTC days differ from its closed reporting window"
            )
    return (
        amount,
        captured,
        frozenset(raw_days),
        covered_days,
        window_start,
        window_end,
    )


def validate_cap_readbacks(
    readbacks: dict[str, Any], policy: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, tuple[datetime, datetime]]]:
    if set(readbacks) != {
        "schema_version",
        "provider",
        "organization_id",
        "workspace_id",
        *PHASES,
    }:
        raise ValueError("cap readbacks have an unexpected shape")
    if (
        readbacks["schema_version"] != 2
        or readbacks["provider"] != "anthropic"
        or readbacks["organization_id"] != policy["organization"]["id"]
        or readbacks["workspace_id"] != policy["workspace"]["id"]
    ):
        raise ValueError("cap readback identity differs from policy")

    operational = Decimal(policy["spend_enforcement"]["operational_cap_cents"]) / 100
    temporary = Decimal(policy["spend_enforcement"]["qualification_cap_cents"]) / 100
    organization_expected = (
        Decimal(policy["spend_enforcement"]["organization_monthly_limit_cents"]) / 100
    )
    intervals: dict[str, tuple[datetime, datetime]] = {}
    organization_limits: list[Decimal] = []
    for phase, expected_workspace in (
        ("operational_acceptance", operational),
        ("temporary_refusal", temporary),
        ("restored_acceptance", operational),
    ):
        observed = readbacks[phase]
        if set(observed) != {
            "captured_before_at",
            "captured_after_at",
            "workspace_monthly_limit_usd",
            "organization_monthly_limit_usd",
            "capture_method",
        }:
            raise ValueError(f"{phase} cap readback has an unexpected shape")
        before = parse_time(observed["captured_before_at"])
        after = parse_time(observed["captured_after_at"])
        if before > after or (after - before).total_seconds() > 300:
            raise ValueError(f"{phase} cap readback is not tightly time-bounded")
        if (
            observed["capture_method"]
            != "operator_console_readback_bounded_by_control_plane_utc"
        ):
            raise ValueError(f"{phase} cap readback lacks an independent UTC bound")
        workspace_limit = decimal_value(observed["workspace_monthly_limit_usd"])
        organization_limit = decimal_value(observed["organization_monthly_limit_usd"])
        if workspace_limit != expected_workspace:
            raise ValueError(f"{phase} workspace cap differs from policy")
        if organization_limit != organization_expected:
            raise ValueError("organization cap differs from reviewed $500.00 binding")
        intervals[phase] = (before, after)
        organization_limits.append(organization_limit)
    if len(set(organization_limits)) != 1:
        raise ValueError("organization cap changed during qualification")
    return readbacks, intervals


def validate_phase(
    evidence: dict[str, Any], phase: str, policy: dict[str, Any]
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
        "credential_removed_before_output",
        "issuance",
        "delivery",
        "provider_transport",
        "provider_observation",
        "host_teardown",
    }
    if set(evidence) != expected_keys:
        raise ValueError(f"{phase} worker evidence has an unexpected shape")
    if (
        evidence["schema_version"] != 1
        or evidence["provider"] != "anthropic"
        or evidence["qualification_requirement"] != "provider-spend-enforcement"
        or evidence["authorization_ruling"] != "A115"
        or evidence["qualification_phase"] != phase
        or evidence["git_remote_count"] != 0
        or evidence["credential_removed_before_output"] is not True
        or evidence["delivery"] != DELIVERY
        or evidence["host_teardown"] != TEARDOWN
    ):
        raise ValueError(f"{phase} worker boundary differs from A115")
    for name in (
        "request_sha256",
        "patch_sha256",
        "observed_rootfs_sha256",
        "image_recipe_sha256",
        "production_parity_sha256",
        "host_contract_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(evidence[name])):
            raise ValueError(f"{phase} {name} is malformed")

    issuance = evidence["issuance"]
    if (
        issuance.get("workspace_id") != policy["workspace"]["id"]
        or issuance.get("service_account_id") != policy["service_account"]["id"]
        or issuance.get("rule_id") != policy["rule"]["id"]
        or issuance.get("scope") != "workspace:inference"
        or issuance.get("token_type") != "Bearer"
    ):
        raise ValueError(f"{phase} principal differs from policy")
    issued = parse_time(issuance.get("issued_at"))
    expires = parse_time(issuance.get("expires_at"))
    if int((expires - issued).total_seconds()) != issuance.get("expires_in"):
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
    expected_cap = (
        policy["spend_enforcement"]["qualification_cap_cents"]
        if phase == "temporary_refusal"
        else policy["spend_enforcement"]["operational_cap_cents"]
    )
    common = {
        "endpoint",
        "http_status",
        "observed_at",
        "request_id",
        "request_body_sha256",
        "response_type",
        "request_attempts",
        "expected_workspace_cap_cents",
        "outcome",
    }
    if (
        observation.get("endpoint") != "/v1/messages"
        or observation.get("request_attempts") != 1
        or observation.get("expected_workspace_cap_cents") != expected_cap
        or not re.fullmatch(r"req_[A-Za-z0-9]+", str(observation.get("request_id", "")))
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(observation.get("request_body_sha256", ""))
        )
    ):
        raise ValueError(f"{phase} provider request differs from A115")
    observed = parse_time(observation.get("observed_at"))
    if not issued <= observed < expires:
        raise ValueError(f"{phase} provider request is outside bearer lifetime")
    if phase == "temporary_refusal":
        if set(observation) != common | {"provider_error"}:
            raise ValueError("temporary refusal has an unexpected shape")
        error = observation["provider_error"]
        shape = error.get("shape", {}) if isinstance(error, dict) else {}
        if (
            observation.get("outcome") != "refused"
            or observation.get("http_status") not in {400, 403}
            or observation.get("response_type") != "error"
            or set(error) != {"error_type", "message_class", "message_sha256", "shape"}
            or not re.fullmatch(r"[a-z_]{1,64}", str(error.get("error_type", "")))
            or error.get("error_type") in {"rate_limit_error", "overloaded_error"}
            or error.get("message_class") not in {"spend_attributable", "unattributed"}
            or not re.fullmatch(r"[0-9a-f]{64}", str(error.get("message_sha256", "")))
            or set(shape) != {"top_level_keys", "error_keys"}
            or not all(
                isinstance(keys, list)
                and len(keys) <= 16
                and all(
                    isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key)
                    for key in keys
                )
                for keys in shape.values()
            )
        ):
            raise ValueError("temporary refusal response is not safely diagnostic")
    else:
        if set(observation) != common | {"model", "usage"}:
            raise ValueError(f"{phase} acceptance has an unexpected shape")
        usage = observation.get("usage", {})
        if (
            observation.get("outcome") != "accepted"
            or observation.get("http_status") != 200
            or observation.get("response_type") != "message"
            or observation.get("model") != policy["spend_enforcement"]["model"]
            or set(usage) != {"input_tokens", "output_tokens"}
            or not all(
                isinstance(value, int) and value >= 1 for value in usage.values()
            )
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
    policy: dict[str, Any],
) -> dict[str, Any]:
    phases = {
        "operational_acceptance": operational,
        "temporary_refusal": refusal,
        "restored_acceptance": restored,
    }
    observed = {
        phase: validate_phase(evidence, phase, policy)
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
    )
    for field in invariant_fields:
        if len({phases[phase][field] for phase in PHASES}) != 1:
            raise ValueError(f"A115 phase {field} values differ")
    if (
        len(
            {
                phases[phase]["provider_observation"]["request_body_sha256"]
                for phase in PHASES
            }
        )
        != 1
    ):
        raise ValueError("A115 provider request bodies are not byte-identical")
    exchange_ids = [
        phases[phase]["issuance"]["exchange_request_id"] for phase in PHASES
    ]
    if len(set(exchange_ids)) != len(PHASES):
        raise ValueError("A115 phases did not use distinct WIF exchanges")
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
        raise ValueError("A115 phase bearer lifetimes overlap")

    workspace_id = policy["workspace"]["id"]
    (
        before_amount,
        before_time,
        before_workspace_days,
        _before_complete_days,
        before_window_start,
        _before_window_end,
    ) = validate_snapshot(settled_before, workspace_id)
    (
        after_amount,
        after_time,
        after_workspace_days,
        after_complete_days,
        after_window_start,
        _after_window_end,
    ) = validate_snapshot(settled_after, workspace_id)
    readbacks, cap_times = validate_cap_readbacks(readbacks, policy)
    operational_cap = (
        Decimal(policy["spend_enforcement"]["operational_cap_cents"]) / 100
    )
    temporary_cap = (
        Decimal(policy["spend_enforcement"]["qualification_cap_cents"]) / 100
    )
    minimum_window = policy["spend_enforcement"]["minimum_settlement_window_seconds"]

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
        <= after_time
        <= observed["restored_acceptance"]
    ):
        raise ValueError("A115 cost, cap, and provider observations are out of order")
    settlement_window = int(
        (after_time - observed["temporary_refusal"]).total_seconds()
    )
    pre_activation_settlement_window = int(
        (before_time - observed["operational_acceptance"]).total_seconds()
    )
    pre_activation_utc_day = utc_day(observed["operational_acceptance"])
    post_refusal_utc_day = utc_day(observed["temporary_refusal"])
    if not utc_day_closed(observed["operational_acceptance"], before_time):
        raise ValueError(
            "pre-activation snapshot was captured before the request UTC day closed"
        )
    if before_workspace_days is None:
        if (
            pre_activation_utc_day != A121_LEGACY_PRE_ACTIVATION_UTC_DAY
            or before_amount != A121_LEGACY_PRE_ACTIVATION_COST_USD
        ):
            raise ValueError(
                "legacy pre-activation snapshot is not the measured A121 snapshot"
            )
    elif pre_activation_utc_day not in before_workspace_days:
        raise ValueError(
            "pre-activation Cost Report lacks the Factory row for the request UTC day"
        )
    if not utc_day_closed(observed["temporary_refusal"], after_time):
        raise ValueError(
            "post-refusal snapshot was captured before the request UTC day closed"
        )
    if after_complete_days is None or post_refusal_utc_day not in after_complete_days:
        raise ValueError(
            "post-refusal Cost Report does not completely cover the request UTC day"
        )
    if (
        after_workspace_days is None
        or pre_activation_utc_day not in after_workspace_days
    ):
        raise ValueError(
            "post-refusal Cost Report lacks the Factory row for the "
            "pre-activation UTC day"
        )
    if pre_activation_settlement_window < minimum_window:
        raise ValueError("pre-activation cost has not completed the settlement window")
    if settlement_window < minimum_window:
        raise ValueError("post-refusal cost has not completed the settlement window")
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
        raise ValueError("A115 qualification crosses a monthly billing boundary")
    if before_amount <= temporary_cap:
        raise ValueError("temporary cap was not lowered below already-settled spend")
    if before_amount >= operational_cap:
        raise ValueError(
            "pre-activation spend makes the $50 positive control ambiguous"
        )
    if after_amount < before_amount:
        raise ValueError("post-refusal settled spend moved backwards")

    preexisting = before_amount - temporary_cap
    incremental = after_amount - before_amount
    return {
        "schema_version": 4,
        "provider": "anthropic",
        "qualification_requirement": "provider-spend-enforcement",
        "authorization_ruling": "A115",
        "organization_id": policy["organization"]["id"],
        "workspace_id": workspace_id,
        "service_account_id": policy["service_account"]["id"],
        "request_binding": {
            "model": policy["spend_enforcement"]["model"],
            "endpoint": "/v1/messages",
            "request_body_sha256": operational["provider_observation"][
                "request_body_sha256"
            ],
            "byte_identical_across_phases": True,
        },
        "phases": phases,
        "cap_control": readbacks,
        "cost_measurement": {
            "source": "Anthropic Cost Report API",
            "currency": "USD",
            "settled_spend_before_activation_usd": decimal_text(before_amount),
            "preexisting_excess_at_activation_usd": decimal_text(preexisting),
            "settled_spend_after_refusal_usd": decimal_text(after_amount),
            "incremental_spend_before_refusal_usd": decimal_text(incremental),
            "before_captured_at": settled_before["captured_at"],
            "after_captured_at": settled_after["captured_at"],
            "pre_activation_workspace_cost_utc_day": pre_activation_utc_day,
            "post_refusal_workspace_cost_utc_day": post_refusal_utc_day,
            "post_refusal_cost_report_window": settled_after["reporting_window"],
            "post_refusal_complete_utc_days": sorted(after_complete_days),
            "post_refusal_workspace_cost_utc_days": sorted(after_workspace_days),
            "settlement_window_seconds": settlement_window,
            "pre_activation_settlement_window_seconds": pre_activation_settlement_window,
            "attribution": "A115_acceptance_refusal_acceptance_workspace_only_cap_change",
        },
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="patchyard-admin")
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
    final.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    policy = load_json(POLICY_PATH)
    if args.command == "snapshot":
        write_json(
            args.output,
            fetch_workspace_cost(args.profile, policy["workspace"]["id"]),
        )
        return 0
    result = finalize(
        load_json(args.operational_evidence),
        load_json(args.refusal_evidence),
        load_json(args.restored_evidence),
        load_json(args.settled_before),
        load_json(args.settled_after),
        load_json(args.cap_readbacks),
        policy,
    )
    write_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
