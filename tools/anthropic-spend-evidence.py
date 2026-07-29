#!/usr/bin/env python3
"""Capture Anthropic workspace cost and finalize sanitized spend evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import subprocess
from typing import Any
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy" / "anthropic-wif.json"
BASE_URL = "https://api.anthropic.com"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def admin_token(profile: str) -> str:
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return subprocess.check_output(
        [
            "ant",
            "auth",
            "print-credentials",
            "--profile",
            profile,
            "--access-token",
        ],
        env=env,
        text=True,
    ).strip()


def fetch_workspace_cost(profile: str, workspace_id: str) -> dict[str, Any]:
    token = admin_token(profile)
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = now + timedelta(minutes=1)
    params = {
        "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "group_by[]": "workspace_id",
    }
    amount = Decimal(0)
    page: str | None = None
    while True:
        query = dict(params)
        if page is not None:
            query["page"] = page
        request = urllib.request.Request(
            BASE_URL
            + "/v1/organizations/cost_report?"
            + urllib.parse.urlencode(query),
            headers={
                "authorization": f"Bearer {token}",
                "anthropic-version": "2023-06-01",
                "user-agent": "patchyard-anthropic-spend-evidence/1",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        for bucket in payload.get("data", []):
            for result in bucket.get("results", []):
                if result.get("workspace_id") != workspace_id:
                    continue
                if result.get("currency") != "USD":
                    raise ValueError("Anthropic returned a non-USD Factory cost")
                amount += Decimal(result["amount"])
        page = payload.get("next_page")
        if not payload.get("has_more"):
            break
        if not isinstance(page, str) or not page:
            raise ValueError("Anthropic cost report pagination is malformed")
    return {
        "schema_version": 1,
        "provider": "anthropic",
        "workspace_id": workspace_id,
        "captured_at": iso_now(),
        "reporting_window": {
            "starting_at": params["starting_at"],
            "ending_at": params["ending_at"],
        },
        "currency": "USD",
        "cost_usd": decimal_text(amount),
    }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def validate_snapshot(
    snapshot: dict[str, Any], workspace_id: str
) -> tuple[Decimal, datetime]:
    if set(snapshot) != {
        "schema_version",
        "provider",
        "workspace_id",
        "captured_at",
        "reporting_window",
        "currency",
        "cost_usd",
    }:
        raise ValueError("cost snapshot has an unexpected shape")
    if (
        snapshot["schema_version"] != 1
        or snapshot["provider"] != "anthropic"
        or snapshot["workspace_id"] != workspace_id
        or snapshot["currency"] != "USD"
    ):
        raise ValueError("cost snapshot identity differs from policy")
    try:
        amount = Decimal(snapshot["cost_usd"])
        captured = parse_time(snapshot["captured_at"])
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("cost snapshot amount or time is malformed") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError("cost snapshot amount is invalid")
    return amount, captured


def validate_cap_readbacks(
    readbacks: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    expected_top = {
        "schema_version",
        "provider",
        "organization_id",
        "workspace_id",
        "before",
        "qualification",
        "restored",
    }
    if set(readbacks) != expected_top:
        raise ValueError("cap readbacks have an unexpected shape")
    if (
        readbacks["schema_version"] != 1
        or readbacks["provider"] != "anthropic"
        or readbacks["organization_id"] != policy["organization"]["id"]
        or readbacks["workspace_id"] != policy["workspace"]["id"]
    ):
        raise ValueError("cap readback identity differs from policy")
    operational = Decimal(policy["spend_enforcement"]["operational_cap_cents"]) / 100
    qualification = (
        Decimal(policy["spend_enforcement"]["qualification_cap_cents"]) / 100
    )
    organization_limits: list[Decimal] = []
    for name, expected_workspace in (
        ("before", operational),
        ("qualification", qualification),
        ("restored", operational),
    ):
        observed = readbacks[name]
        if set(observed) != {
            "observed_at",
            "workspace_monthly_limit_usd",
            "organization_monthly_limit_usd",
            "enforcement",
        }:
            raise ValueError(f"{name} cap readback has an unexpected shape")
        if observed["enforcement"] != "notify_and_pause":
            raise ValueError(f"{name} cap is not provider-enforced pause")
        parse_time(observed["observed_at"])
        workspace_limit = Decimal(observed["workspace_monthly_limit_usd"])
        organization_limit = Decimal(observed["organization_monthly_limit_usd"])
        if workspace_limit != expected_workspace:
            raise ValueError(f"{name} workspace cap differs from policy")
        if not organization_limit.is_finite() or organization_limit <= operational:
            raise ValueError("organization cap is not safely above the workspace cap")
        organization_limits.append(organization_limit)
    if len(set(organization_limits)) != 1:
        raise ValueError("organization cap changed during qualification")
    return readbacks


def finalize(
    worker: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    readbacks: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    workspace_id = policy["workspace"]["id"]
    before_amount, before_time = validate_snapshot(before, workspace_id)
    after_amount, after_time = validate_snapshot(after, workspace_id)
    readbacks = validate_cap_readbacks(readbacks, policy)
    denial = worker.get("spend_enforcement", {}).get("denial", {})
    denied_at = parse_time(denial.get("denied_at", ""))
    qualification_time = parse_time(readbacks["qualification"]["observed_at"])
    restored_time = parse_time(readbacks["restored"]["observed_at"])
    if not before_time <= qualification_time <= denied_at <= restored_time <= after_time:
        raise ValueError("cost, cap, denial, and restoration observations are out of order")
    cap = Decimal(policy["spend_enforcement"]["qualification_cap_cents"]) / 100
    if before_amount >= cap:
        raise ValueError("Factory workspace was already at the qualification cap")
    if after_amount <= before_amount:
        raise ValueError("cost report does not yet show the successful paid calls")
    overshoot = max(after_amount - cap, Decimal(0))
    result = dict(worker)
    result["cost_measurement"] = {
        "source": "Anthropic Cost Report API",
        "currency": "USD",
        "spend_before_usd": decimal_text(before_amount),
        "observed_spend_at_denial_usd": decimal_text(after_amount),
        "measured_overshoot_usd": decimal_text(overshoot),
        "observed_at": after["captured_at"],
        "attribution": "isolated_workspace_with_no_calls_after_provider_denial",
    }
    result["cap_control"] = readbacks
    return result


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="patchyard-admin")
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--output", required=True, type=Path)
    final = subparsers.add_parser("finalize")
    final.add_argument("--worker-evidence", required=True, type=Path)
    final.add_argument("--before-cost", required=True, type=Path)
    final.add_argument("--after-cost", type=Path)
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
    after = (
        load_json(args.after_cost)
        if args.after_cost
        else fetch_workspace_cost(args.profile, policy["workspace"]["id"])
    )
    result = finalize(
        load_json(args.worker_evidence),
        load_json(args.before_cost),
        after,
        load_json(args.cap_readbacks),
        policy,
    )
    write_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
