#!/usr/bin/env python3
"""Check the Anthropic A-5 requirement-2 A115 successor contract."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


REPO = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO / "policy" / "anthropic-wif.json"
RESULT_PATH = REPO / "research/isolation/results/anthropic-spend-enforcement.json"
INITIAL_FAILURE_PATH = (
    REPO / "research/isolation/results/anthropic-spend-enforcement-initial-failure.json"
)
REPAIR_FAILURE_PATH = (
    REPO / "research/isolation/results/anthropic-spend-enforcement-repair-failure.json"
)
IMAGE_PATH = REPO / "worker/image"
PRODUCTION_PARITY_PATH = IMAGE_PATH / "production-parity.json"
RUNNER_PATH = REPO / "worker/qualification/patchyard-run-anthropic-issuance"
LAUNCHER_PATH = REPO / "worker/runtime/patchyard-firecracker-run"
GUEST_PATH = REPO / "worker/image/patchyard-guest-run"
ANTHROPIC_REQUEST = b"Anthropic provider-side spend enforcement qualification.\n"
ANTHROPIC_PATCH = (
    b"diff --git a/anthropic-spend-qualified.txt b/anthropic-spend-qualified.txt\n"
    b"new file mode 100644\n"
    b"index 0000000000000000000000000000000000000000.."
    b"ce4003a0cb322c6b51e33bc82833fe87d9303b71\n"
    b"--- /dev/null\n"
    b"+++ b/anthropic-spend-qualified.txt\n"
    b"@@ -0,0 +1 @@\n"
    b"+anthropic-provider-spend-enforcement-qualified\n"
)
EXPECTED_PROVIDER_REQUEST_BLOCK = """  # A115_PROVIDER_REQUEST_BEGIN
  PROVIDER_STATUS=$(runuser -u factory-agent -- curl \\
    --config "$AUTH_CONFIG" --silent --show-error \\
    --connect-timeout 10 --max-time 60 \\
    --dump-header "$PROVIDER_HEADERS" \\
    --output "$PROVIDER_RESPONSE" --write-out '%{http_code}' \\
    --data-binary "@$PROVIDER_REQUEST" \\
    'https://api.anthropic.com/v1/messages') || PROVIDER_CURL_EXIT=$?
  # A115_PROVIDER_REQUEST_END"""
PHASES = (
    "operational_acceptance",
    "temporary_refusal",
    "restored_acceptance",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_recipe_sha256() -> str:
    records = []
    for path in sorted(path for path in IMAGE_PATH.rglob("*") if path.is_file()):
        records.append(f"{digest(path)}  {path.relative_to(IMAGE_PATH)}\n")
    return hashlib.sha256("".join(records).encode()).hexdigest()


def host_contract_sha256() -> str:
    records = [
        f"{digest(path)}  {path.relative_to(REPO)}\n"
        for path in (RUNNER_PATH, LAUNCHER_PATH)
    ]
    return hashlib.sha256("".join(records).encode()).hexdigest()


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed


def decimal_value(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("decimal figure is not a string")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("decimal figure is not finite")
    return number


def secret_named_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"secret", "access_token", "assertion", "identity_token"}:
                return key
            found = secret_named_key(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = secret_named_key(child)
            if found:
                return found
    return None


def contains_forbidden_ceiling(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            "ceiling" in key
            or "max_overshoot" in key
            or contains_forbidden_ceiling(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(contains_forbidden_ceiling(child) for child in value)
    return False


errors: list[str] = []
policy = json.loads(POLICY_PATH.read_text())
expected_spend_policy = {
    "currency": "USD",
    "model": "claude-opus-5",
    "operational_cap_cents": 5000,
    "qualification_cap_cents": 100,
    "organization_monthly_limit_cents": 50000,
    "authorization_ruling": "A115",
    "minimum_settlement_window_seconds": 10260,
    "qualification_phases": list(PHASES),
}
if policy.get("spend_enforcement") != expected_spend_policy:
    errors.append("Anthropic spend policy differs from the exact A115 binding")
organization_id = "aaadc747-869a-42d2-af51-58a5be8e3b7f"
workspace_id = "wrkspc_000000000000000000000000"
service_account_id = "svac_01BqCdjSqFsWTvfDyCucThZy"
if policy.get("organization", {}).get("id") != organization_id:
    errors.append("Anthropic organization differs from the reviewed binding")
if policy.get("workspace") != {"id": workspace_id, "name": "Patchyard Factory"}:
    errors.append("Anthropic Factory workspace differs from the reviewed binding")
if policy.get("service_account", {}).get("id") != service_account_id:
    errors.append("Anthropic Factory principal differs from the reviewed binding")

providers = json.loads((REPO / "policy/provider-egress.json").read_text())["providers"]
if len(providers) != 13 or any(
    item.get("credential_qualified") is not False for item in providers.values()
):
    errors.append("all 13 provider credential qualification flags must remain false")

# Source-only A115 bindings. This deliberately rejects shell constructs that can
# turn the single curl expression into retries or a request loop.
runner = RUNNER_PATH.read_text()
launcher = LAUNCHER_PATH.read_text()
guest = GUEST_PATH.read_text()
spend_marker = (
    'if [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]] \\\n'
    "  && jq -e '.qualification_requirement == \"provider-spend-enforcement\"'"
)
if spend_marker not in guest:
    errors.append("guest has no distinct A115 spend-enforcement branch")
    spend_branch = ""
else:
    spend_branch = guest.split(spend_marker, 1)[1].split(
        '\nif [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]]',
        1,
    )[0]

required_sources = (
    (runner, "run-spend-operational)"),
    (runner, "run-spend-refusal)"),
    (runner, "run-spend-restored)"),
    (runner, "QUALIFICATION_PHASE=operational_acceptance"),
    (runner, "QUALIFICATION_PHASE=temporary_refusal"),
    (runner, "QUALIFICATION_PHASE=restored_acceptance"),
    (runner, 'authorization_ruling "$(jq -r .spend_enforcement.authorization_ruling'),
    (launcher, '.authorization_ruling == "A115"'),
    (launcher, '.qualification_phase == "temporary_refusal"'),
    (launcher, ".spend_cap_cents == 5000"),
    (spend_branch, 'and .authorization_ruling == "A115"'),
    (guest, 'has("type") and .type == "error"'),
    (guest, 'and (.error | has("type")) and (.error | has("message"))'),
    (spend_branch, "anthropic_error_envelope_is_compatible"),
    (spend_branch, "MESSAGE_CLASS=unattributed"),
    (spend_branch, "shape:{$top_level_keys,$error_keys}"),
    (spend_branch, "$request_body_sha256"),
    (spend_branch, "request_attempts:1"),
    (spend_branch, "remove_provider_credential"),
    (spend_branch, "anthropic-spend-provider-response-rejected"),
    (spend_branch, "anthropic-spend-temporary-cap-refusal-not-observed"),
    (spend_branch, "classify_anthropic_error_shape"),
    (spend_branch, "missing-date"),
    (spend_branch, "invalid-date"),
)
for source, required in required_sources:
    if required not in source:
        errors.append(f"Anthropic A115 source binding is missing: {required}")
if "run-spend)" in runner:
    errors.append("superseded single-probe runner action remains callable")
if spend_branch:
    if spend_branch.count(EXPECTED_PROVIDER_REQUEST_BLOCK) != 1:
        errors.append(
            "A115 provider request block differs from the exact one-call binding"
        )
        non_request_source = spend_branch
    else:
        non_request_source = spend_branch.replace(EXPECTED_PROVIDER_REQUEST_BLOCK, "")
    if re.search(
        r"(?<![-A-Za-z0-9_.])(curl|wget|netcat|nc)(?=\s)|"
        r"/dev/(?:tcp|udp)|openssl\s+s_client",
        non_request_source,
    ):
        errors.append(
            "spend branch contains a provider-capable call outside its exact block"
        )
    forbidden_request_controls = (
        r"(^|[;&|[:space:]])(for|while|until|select)[[:space:]]",
        r"--retry(?:[=[:space:]]|$)",
        r"--retry-all-errors",
        r"(^|[;&|[:space:]])xargs([[:space:]]|$)",
        r"(^|[;&|[:space:]])seq([[:space:]]|$)",
    )
    for expression in forbidden_request_controls:
        if re.search(
            expression.replace("[:space:]", r"\s"), spend_branch, re.MULTILINE
        ):
            errors.append(f"spend branch permits repeated provider calls: {expression}")
    call = spend_branch.find("https://api.anthropic.com/v1/messages")
    cleanup = spend_branch.find("remove_provider_credential", call)
    evidence = spend_branch.find(">/result/evidence.json", cleanup)
    if not 0 <= call < cleanup < evidence:
        errors.append("A115 credential is not removed before evidence publication")
finish = guest.split("finish() {", 1)[1].split("\n}", 1)[0]
if not (
    "remove_provider_credential || credential_cleanup_failed=1" in finish
    and finish.find("remove_provider_credential")
    < finish.find("printf '%s\\n' \"$FAILURE\"")
    and "find /result -mindepth 1" in finish
):
    errors.append("guest failure publication is not downstream of credential deletion")
for source in (runner, launcher, guest):
    if "overshoot_ceiling" in source or "max_overshoot" in source:
        errors.append("source encodes a forbidden preset overshoot ceiling")

# The two failed July attempts are permanent history, not mutually exclusive
# with a future A115 success.
try:
    initial = json.loads(INITIAL_FAILURE_PATH.read_text())
except FileNotFoundError:
    errors.append("initial July failure record is missing")
    initial = {}
if set(initial) != {
    "schema_version",
    "provider",
    "qualification_requirement",
    "outcome",
    "workspace_id",
    "service_account_id",
    "cap_control",
    "fixture",
    "usage_measurement",
    "cost_measurement",
    "containment",
}:
    errors.append("initial July failure record has an unexpected shape")
if (
    initial.get("schema_version") != 1
    or initial.get("provider") != "anthropic"
    or initial.get("qualification_requirement") != "provider-spend-enforcement"
    or initial.get("outcome") != "denial_not_observed"
    or initial.get("workspace_id") != workspace_id
    or initial.get("service_account_id") != service_account_id
):
    errors.append("initial July failure identity differs from the observed attempt")
if initial.get("fixture") != {
    "model": "claude-opus-5",
    "request_attempts": 8,
    "accepted_requests": 8,
    "denial_observed": False,
    "diagnostic": [
        "incomplete guest result: file_count=1 expected_mask=s",
        "guest returned incomplete status=anthropic-spend-denial-not-observed",
        "factory worker run failed: stage=result-filesystem-validation line=470 status=1",
    ],
}:
    errors.append("initial July fixture record differs from the live failure")
initial_cost = initial.get("cost_measurement", {})
if initial_cost != {
    "source": "Anthropic Cost Report API",
    "currency": "USD",
    "observed_at": "2026-07-30T01:17:29Z",
    "billed_cost_usd": "7.68168",
}:
    errors.append("initial July settled cost differs from the live report")
initial_containment = initial.get("containment", {})
if (
    initial_containment.get("boundary_tainted") is not True
    or initial_containment.get("marker")
    != "run=anthropic-s2-20260729-412f8a1777 reason=containment-qualification-failed stage=result-filesystem-validation line=470 detected_at=2026-07-29T22:25:26Z"
    or initial_containment.get("tainted_worker")
    != {"worker_id": 588324505, "disposition": "destroyed"}
    or initial_containment.get("reviewed_replacement", {}).get(
        "copied_state_from_tainted_worker"
    )
    is not False
):
    errors.append("initial failure omits taint or reviewed clean-replacement history")

try:
    repair = json.loads(REPAIR_FAILURE_PATH.read_text())
except FileNotFoundError:
    errors.append("A9 repair failure record is missing")
    repair = {}
if set(repair) != {
    "schema_version",
    "provider",
    "qualification_requirement",
    "outcome",
    "workspace_id",
    "service_account_id",
    "run_id",
    "cap_control",
    "fixture",
    "cost_measurement",
    "containment",
    "repair_loop",
}:
    errors.append("A9 repair failure record has an unexpected shape")
if (
    repair.get("outcome") != "repair_failed_unattributed_http_400"
    or repair.get("run_id") != "anthropic-s2-20260730-4d80267abf"
    or repair.get("workspace_id") != workspace_id
    or repair.get("service_account_id") != service_account_id
):
    errors.append("A9 repair failure identity differs from the observed attempt")
repair_cost = repair.get("cost_measurement", {})
if (
    repair_cost.get("incremental_repair_cost_status")
    != "unproved_due_to_incomplete_settlement_window"
    or repair_cost.get("latest_recheck_seconds_after_repair") != 2543
    or repair_cost.get("initial_spend_above_displayed_cap_usd") != "6.68168"
    or repair_cost.get("denial_overshoot_status") != "not_observed"
    or "incremental_repair_cost_usd" in repair_cost
    or "measured_initial_attempt_overshoot_usd" in repair_cost
):
    errors.append("A9 repair cost record still claims an unproved denial overshoot")
observations = repair_cost.get("observations", [])
if [item.get("billed_cost_usd") for item in observations] != [
    "7.68168",
    "7.68168",
    "7.68168",
] or [item.get("observed_at") for item in observations] != [
    "2026-07-30T01:17:29Z",
    "2026-07-30T02:26:10Z",
    "2026-07-30T03:04:16Z",
]:
    errors.append("A9 repair cost observations differ from the historical reports")
if repair.get("containment", {}).get("tainted_worker") != {
    "worker_id": 588590370,
    "disposition": "quarantined_pending_reviewed_replacement",
}:
    errors.append("A9 repair record does not identify the quarantined worker")
if repair.get("repair_loop") != {
    "consumed": True,
    "further_provider_requests_permitted": False,
    "disposition": "escalated_under_A9",
    "successor_authorization": "A115",
}:
    errors.append(
        "historical A9 stop and A115 successor authorization are not distinct"
    )

for name, record in (("initial", initial), ("repair", repair)):
    serialized = json.dumps(record, sort_keys=True)
    if secret_named_key(record) or re.search(
        r"sk-ant-|eyJ[A-Za-z0-9_-]+\.eyJ", serialized
    ):
        errors.append(f"{name} failure record contains a credential")

if RESULT_PATH.exists():
    result = json.loads(RESULT_PATH.read_text())
    if set(result) != {
        "schema_version",
        "provider",
        "qualification_requirement",
        "authorization_ruling",
        "organization_id",
        "workspace_id",
        "service_account_id",
        "request_binding",
        "phases",
        "cap_control",
        "cost_measurement",
    }:
        errors.append("A115 live result has an unexpected top-level shape")
    if (
        result.get("schema_version") != 2
        or result.get("provider") != "anthropic"
        or result.get("qualification_requirement") != "provider-spend-enforcement"
        or result.get("authorization_ruling") != "A115"
        or result.get("organization_id") != organization_id
        or result.get("workspace_id") != workspace_id
        or result.get("service_account_id") != service_account_id
    ):
        errors.append("A115 live result identity differs from policy")
    phases = result.get("phases", {})
    if set(phases) != set(PHASES):
        errors.append("A115 live result does not contain exactly three phases")
    reproducible = {
        "request_sha256": hashlib.sha256(ANTHROPIC_REQUEST).hexdigest(),
        "patch_sha256": hashlib.sha256(ANTHROPIC_PATCH).hexdigest(),
        "production_parity_sha256": digest(PRODUCTION_PARITY_PATH),
        "image_recipe_sha256": image_recipe_sha256(),
        "host_contract_sha256": host_contract_sha256(),
    }
    provider_body_hashes: set[str] = set()
    provider_times: dict[str, datetime] = {}
    exchange_ids: list[str] = []
    issuance_windows: list[tuple[datetime, datetime]] = []
    for phase in PHASES:
        evidence = phases.get(phase, {}) if isinstance(phases, dict) else {}
        if evidence.get("qualification_phase") != phase:
            errors.append(f"A115 {phase} evidence has the wrong phase")
        for field, expected in reproducible.items():
            if evidence.get(field) != expected:
                errors.append(f"A115 {phase} {field} differs from current source")
        if (
            not re.fullmatch(
                r"[0-9a-f]{64}", str(evidence.get("observed_rootfs_sha256", ""))
            )
            or "rootfs_sha256" in evidence
        ):
            errors.append(f"A115 {phase} rootfs observation is malformed")
        if evidence.get("credential_removed_before_output") is not True:
            errors.append(f"A115 {phase} retained a credential at output")
        if evidence.get("host_teardown") != {
            "processes": 0,
            "taps": 0,
            "nftables_tables": 0,
            "run_directories": 0,
            "credential_files": 0,
        }:
            errors.append(f"A115 {phase} host teardown is incomplete")
        issuance = evidence.get("issuance", {})
        try:
            exchange_id = issuance["exchange_request_id"]
            if not re.fullmatch(r"req_[A-Za-z0-9]+", exchange_id):
                raise ValueError
            exchange_ids.append(exchange_id)
            issuance_windows.append(
                (parse_time(issuance["issued_at"]), parse_time(issuance["expires_at"]))
            )
        except (KeyError, TypeError, ValueError):
            errors.append(f"A115 {phase} issuance window is malformed")
        observation = evidence.get("provider_observation", {})
        provider_body_hashes.add(str(observation.get("request_body_sha256", "")))
        try:
            provider_times[phase] = parse_time(observation.get("observed_at"))
        except ValueError:
            errors.append(f"A115 {phase} provider time is malformed")
        if (
            observation.get("endpoint") != "/v1/messages"
            or observation.get("request_attempts") != 1
            or not re.fullmatch(
                r"req_[A-Za-z0-9]+", str(observation.get("request_id", ""))
            )
        ):
            errors.append(f"A115 {phase} provider observation is malformed")
        if phase == "temporary_refusal":
            provider_error = observation.get("provider_error", {})
            if (
                observation.get("outcome") != "refused"
                or observation.get("http_status") not in {400, 403}
                or observation.get("response_type") != "error"
                or provider_error.get("error_type")
                in {"rate_limit_error", "overloaded_error"}
                or set(provider_error.get("shape", {}))
                != {"top_level_keys", "error_keys"}
            ):
                errors.append("A115 refusal is not a bounded provider denial")
        elif (
            observation.get("outcome") != "accepted"
            or observation.get("http_status") != 200
            or observation.get("response_type") != "message"
            or observation.get("model") != "claude-opus-5"
        ):
            errors.append(f"A115 {phase} is not an accepted positive control")
    if len(provider_body_hashes) != 1 or not all(
        re.fullmatch(r"[0-9a-f]{64}", value) for value in provider_body_hashes
    ):
        errors.append("A115 phase request bodies are not byte-identical")
    if len(set(exchange_ids)) != 3 or len(issuance_windows) != 3:
        errors.append("A115 phases do not bind three distinct WIF exchanges")
    elif any(
        first[1] > second[0]
        for first, second in zip(issuance_windows, issuance_windows[1:])
    ):
        errors.append("A115 phase WIF lifetimes overlap")
    binding = result.get("request_binding", {})
    if binding != {
        "model": "claude-opus-5",
        "endpoint": "/v1/messages",
        "request_body_sha256": next(iter(provider_body_hashes), ""),
        "byte_identical_across_phases": True,
    }:
        errors.append("A115 request binding does not match the phase evidence")

    cap_control = result.get("cap_control", {})
    cap_intervals: dict[str, tuple[datetime, datetime]] = {}
    organization_limits: list[Decimal] = []
    for phase, expected in (
        ("operational_acceptance", Decimal(50)),
        ("temporary_refusal", Decimal(1)),
        ("restored_acceptance", Decimal(50)),
    ):
        cap = cap_control.get(phase, {}) if isinstance(cap_control, dict) else {}
        try:
            before = parse_time(cap["captured_before_at"])
            after = parse_time(cap["captured_after_at"])
            workspace_cap = decimal_value(cap["workspace_monthly_limit_usd"])
            organization_cap = decimal_value(cap["organization_monthly_limit_usd"])
            if (
                set(cap)
                != {
                    "captured_before_at",
                    "captured_after_at",
                    "workspace_monthly_limit_usd",
                    "organization_monthly_limit_usd",
                    "capture_method",
                }
                or cap["capture_method"]
                != "operator_console_readback_bounded_by_control_plane_utc"
                or before > after
                or (after - before).total_seconds() > 300
                or workspace_cap != expected
                or organization_cap != Decimal(500)
            ):
                raise ValueError
            cap_intervals[phase] = (before, after)
            organization_limits.append(organization_cap)
        except (KeyError, InvalidOperation, TypeError, ValueError):
            errors.append(f"A115 {phase} cap readback is malformed")
    if organization_limits and len(set(organization_limits)) != 1:
        errors.append("organization cap changed during A115 qualification")

    cost = result.get("cost_measurement", {})
    try:
        before_amount = decimal_value(cost["settled_spend_before_activation_usd"])
        preexisting = decimal_value(cost["preexisting_excess_at_activation_usd"])
        after_amount = decimal_value(cost["settled_spend_after_refusal_usd"])
        incremental = decimal_value(cost["incremental_spend_before_refusal_usd"])
        before_time = parse_time(cost["before_captured_at"])
        after_time = parse_time(cost["after_captured_at"])
        if (
            set(cost)
            != {
                "source",
                "currency",
                "settled_spend_before_activation_usd",
                "preexisting_excess_at_activation_usd",
                "settled_spend_after_refusal_usd",
                "incremental_spend_before_refusal_usd",
                "before_captured_at",
                "after_captured_at",
                "settlement_window_seconds",
                "pre_activation_settlement_window_seconds",
                "attribution",
            }
            or cost["source"] != "Anthropic Cost Report API"
            or cost["currency"] != "USD"
            or before_amount <= Decimal(1)
            or before_amount >= Decimal(50)
            or preexisting != before_amount - Decimal(1)
            or incremental != after_amount - before_amount
            or incremental < 0
            or cost["settlement_window_seconds"]
            != int((after_time - provider_times["temporary_refusal"]).total_seconds())
            or cost["settlement_window_seconds"] < 10260
            or cost["pre_activation_settlement_window_seconds"]
            != int(
                (before_time - provider_times["operational_acceptance"]).total_seconds()
            )
            or cost["pre_activation_settlement_window_seconds"] < 10260
            or cost["attribution"]
            != "A115_acceptance_refusal_acceptance_workspace_only_cap_change"
            or not (
                cap_intervals["operational_acceptance"][1]
                <= provider_times["operational_acceptance"]
                <= before_time
                <= cap_intervals["temporary_refusal"][0]
                <= cap_intervals["temporary_refusal"][1]
                <= provider_times["temporary_refusal"]
                <= cap_intervals["restored_acceptance"][0]
                <= cap_intervals["restored_acceptance"][1]
                <= after_time
                <= provider_times["restored_acceptance"]
            )
        ):
            raise ValueError
        event_times = {
            *provider_times.values(),
            before_time,
            after_time,
            *(time for interval in cap_intervals.values() for time in interval),
        }
        if len({(value.year, value.month) for value in event_times}) != 1:
            raise ValueError
    except (KeyError, InvalidOperation, TypeError, ValueError):
        errors.append(
            "A115 cost separation, settlement, or phase ordering is malformed"
        )
    if contains_forbidden_ceiling(result):
        errors.append("A115 result encodes a forbidden preset overshoot ceiling")
    serialized = json.dumps(result, sort_keys=True)
    if secret_named_key(result) or re.search(
        r"sk-ant-|eyJ[A-Za-z0-9_-]+\.eyJ", serialized
    ):
        errors.append("A115 result contains a credential")

if errors:
    print("Anthropic spend check: failed", file=sys.stderr)
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    raise SystemExit(1)

status = "with live A115 result" if RESULT_PATH.exists() else "A115 successor preflight"
print(f"Anthropic spend check: pass ({status}; historical failures retained)")
