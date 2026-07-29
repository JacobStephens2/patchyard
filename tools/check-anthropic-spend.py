#!/usr/bin/env python3
"""Check the Anthropic A-5 provider-side spend-enforcement contract."""

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
RESULT_PATH = (
    REPO
    / "research"
    / "isolation"
    / "results"
    / "anthropic-spend-enforcement.json"
)
INITIAL_FAILURE_PATH = (
    REPO
    / "research"
    / "isolation"
    / "results"
    / "anthropic-spend-enforcement-initial-failure.json"
)
IMAGE_PATH = REPO / "worker" / "image"
PRODUCTION_PARITY_PATH = IMAGE_PATH / "production-parity.json"
HOST_CONTRACT_PATHS = (
    REPO / "worker" / "qualification" / "patchyard-run-anthropic-issuance",
    REPO / "worker" / "runtime" / "patchyard-firecracker-run",
)
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


def image_recipe_sha256() -> str:
    records = []
    for path in sorted(path for path in IMAGE_PATH.rglob("*") if path.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(f"{digest}  {path.relative_to(IMAGE_PATH)}\n")
    return hashlib.sha256("".join(records).encode()).hexdigest()


def host_contract_sha256() -> str:
    records = []
    for path in HOST_CONTRACT_PATHS:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(f"{digest}  {path.relative_to(REPO)}\n")
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


errors: list[str] = []
policy = json.loads(POLICY_PATH.read_text())
if policy.get("spend_enforcement") != {
    "currency": "USD",
    "model": "claude-opus-5",
    "operational_cap_cents": 5000,
    "qualification_cap_cents": 100,
}:
    errors.append("Anthropic spend policy differs from the reviewed exact binding")
organization_id = "aaadc747-869a-42d2-af51-58a5be8e3b7f"
workspace_id = "wrkspc_000000000000000000000000"
if policy.get("organization", {}).get("id") != organization_id:
    errors.append("Anthropic organization differs from the reviewed binding")
if policy.get("workspace") != {"id": workspace_id, "name": "Patchyard Factory"}:
    errors.append("Anthropic Factory workspace differs from the reviewed binding")

providers = json.loads((REPO / "policy" / "provider-egress.json").read_text())[
    "providers"
]
if any(item.get("credential_qualified") is not False for item in providers.values()):
    errors.append("a provider became credential-qualified before its six live fixtures")

runner = (
    REPO / "worker" / "qualification" / "patchyard-run-anthropic-issuance"
).read_text()
launcher = (REPO / "worker" / "runtime" / "patchyard-firecracker-run").read_text()
guest = (REPO / "worker" / "image" / "patchyard-guest-run").read_text()
spend_branch_start = (
    'if [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]] \\\n'
    '  && jq -e \'.qualification_requirement == "provider-spend-enforcement"\''
)
if spend_branch_start not in guest:
    errors.append("guest has no distinct Anthropic spend-enforcement branch")
    spend_branch = ""
else:
    spend_branch = guest.split(spend_branch_start, 1)[1].split(
        '\nif [[ "$MODE" == provider-qualification && "$PROVIDER" == anthropic ]]',
        1,
    )[0]
for source, required in (
    (runner, "run-spend)"),
    (runner, "QUALIFICATION_REQUIREMENT=provider-spend-enforcement"),
    (runner, "SPEND_CAP_CENTS=$(jq -r .spend_enforcement.qualification_cap_cents"),
    (launcher, '.qualification_requirement == "provider-spend-enforcement"'),
    (launcher, ".spend_cap_cents == 100"),
    (spend_branch, 'and .spend_cap_cents == 100'),
    (spend_branch, 'model:"claude-opus-5"'),
    (spend_branch, "Patchyard Factory spend-cap denial probe. Reply with one character."),
    (spend_branch, "probe_attempts:1"),
    (spend_branch, 'test("(spend|credit|billing|monthly (spend|usage) limit)"; "i")'),
    (spend_branch, 'https://api.anthropic.com/v1/messages'),
    (spend_branch, 'rm -f -- "$AUTH_CONFIG" "$CAPABILITY_FILE"'),
    (spend_branch, '== "$PROVIDER_REQUEST_ID"'),
    (spend_branch, "anthropic-provider-spend-enforcement-qualified"),
):
    if required not in source:
        errors.append(f"Anthropic spend source binding is missing: {required}")
if spend_branch:
    mount_guard = spend_branch.find("if mountpoint -q /credential")
    provider_call = spend_branch.find("https://api.anthropic.com/v1/messages")
    credential_delete = spend_branch.find('rm -f -- "$AUTH_CONFIG" "$CAPABILITY_FILE"')
    evidence_output = spend_branch.find(">/result/evidence.json")
    if not 0 <= mount_guard < provider_call < credential_delete < evidence_output:
        errors.append("spend credential lifecycle order is not fail-closed")
    if spend_branch.count("https://api.anthropic.com/v1/messages") != 1:
        errors.append("spend qualification is not exactly one provider probe")
    if "for ATTEMPT" in spend_branch or "sleep " in spend_branch:
        errors.append("spend qualification contains a repeated or delayed probe")
for source in (runner, launcher, guest):
    if "overshoot_ceiling" in source or "max_overshoot" in source:
        errors.append("source encodes a forbidden preset overshoot ceiling")

allow_missing = "--allow-missing-results" in sys.argv[1:]
initial_failure: dict[str, Any] | None = None
initial_failure_cost: Decimal | None = None
if INITIAL_FAILURE_PATH.exists():
    initial_failure = json.loads(INITIAL_FAILURE_PATH.read_text())
    expected_failure_keys = {
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
    }
    if set(initial_failure) != expected_failure_keys:
        errors.append("initial spend failure record has an unexpected shape")
    if (
        initial_failure.get("schema_version") != 1
        or initial_failure.get("provider") != "anthropic"
        or initial_failure.get("qualification_requirement")
        != "provider-spend-enforcement"
        or initial_failure.get("outcome") != "denial_not_observed"
        or initial_failure.get("workspace_id") != workspace_id
        or initial_failure.get("service_account_id")
        != policy.get("service_account", {}).get("id")
    ):
        errors.append("initial spend failure identity differs from policy")
    initial_caps = initial_failure.get("cap_control", {})
    if initial_caps != {
        "organization_monthly_limit_usd": "500.00",
        "qualification_workspace_limit_usd": "1.00",
        "qualification_observed_at": "2026-07-29T22:03Z",
        "restored_workspace_limit_usd": "50.00",
        "restored_observed_at": "2026-07-29T22:27Z",
    }:
        errors.append("initial spend failure cap history differs from live readbacks")
    initial_fixture = initial_failure.get("fixture", {})
    if initial_fixture != {
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
        errors.append("initial spend failure diagnostic differs from observed failure")
    usage = initial_failure.get("usage_measurement", {})
    buckets = usage.get("buckets", []) if isinstance(usage, dict) else []
    expected_buckets = [
        {
            "starting_at": "2026-07-29T22:24:00Z",
            "ending_at": "2026-07-29T22:25:00Z",
            "uncached_input_tokens": 960185,
            "output_tokens": 5,
        },
        {
            "starting_at": "2026-07-29T22:25:00Z",
            "ending_at": "2026-07-29T22:26:00Z",
            "uncached_input_tokens": 576111,
            "output_tokens": 3,
        },
    ]
    if (
        not isinstance(usage, dict)
        or set(usage)
        != {
            "source",
            "observed_at",
            "model",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "buckets",
            "total_uncached_input_tokens",
            "total_output_tokens",
        }
        or usage.get("source") != "Anthropic Usage Report API"
        or usage.get("model") != "claude-opus-5"
        or usage.get("cache_read_input_tokens") != 0
        or usage.get("cache_creation_input_tokens") != 0
        or buckets != expected_buckets
        or usage.get("total_uncached_input_tokens")
        != sum(bucket["uncached_input_tokens"] for bucket in expected_buckets)
        or usage.get("total_output_tokens")
        != sum(bucket["output_tokens"] for bucket in expected_buckets)
    ):
        errors.append("initial spend failure usage differs from the live report")
    else:
        try:
            parse_time(usage["observed_at"])
        except (KeyError, TypeError, ValueError):
            errors.append("initial spend failure usage observation time is malformed")
    failure_cost = initial_failure.get("cost_measurement", {})
    try:
        if set(failure_cost) != {"source", "currency", "observed_at", "billed_cost_usd"}:
            raise ValueError("unexpected cost shape")
        initial_failure_cost = decimal_value(failure_cost["billed_cost_usd"])
        parse_time(failure_cost["observed_at"])
        if (
            failure_cost["source"] != "Anthropic Cost Report API"
            or failure_cost["currency"] != "USD"
            or initial_failure_cost <= Decimal(1)
        ):
            raise ValueError("unexpected cost value")
    except (KeyError, InvalidOperation, TypeError, ValueError):
        errors.append("initial spend failure billed cost is malformed")
    serialized_failure = json.dumps(initial_failure, sort_keys=True)
    if secret_named_key(initial_failure) or re.search(
        r"sk-ant-|eyJ[A-Za-z0-9_-]+\.eyJ", serialized_failure
    ):
        errors.append("initial spend failure record contains a credential")
elif RESULT_PATH.exists():
    errors.append("initial spend failure record is missing")

if not RESULT_PATH.exists():
    if not allow_missing:
        errors.append("committed live Anthropic spend result is missing")
else:
    result = json.loads(RESULT_PATH.read_text())
    expected_keys = {
        "base_sha",
        "cap_control",
        "cost_measurement",
        "credential_removed_before_output",
        "delivery",
        "git_remote_count",
        "host_contract_sha256",
        "host_teardown",
        "image_recipe_sha256",
        "issuance",
        "observed_rootfs_sha256",
        "patch_sha256",
        "production_parity_sha256",
        "provider",
        "qualification_requirement",
        "request_sha256",
        "run_id",
        "schema_version",
        "spend_enforcement",
    }
    if set(result) != expected_keys:
        errors.append("live spend result has an unexpected top-level evidence shape")
    reproducible = {
        "request_sha256": hashlib.sha256(ANTHROPIC_REQUEST).hexdigest(),
        "patch_sha256": hashlib.sha256(ANTHROPIC_PATCH).hexdigest(),
        "production_parity_sha256": hashlib.sha256(
            PRODUCTION_PARITY_PATH.read_bytes()
        ).hexdigest(),
        "image_recipe_sha256": image_recipe_sha256(),
        "host_contract_sha256": host_contract_sha256(),
    }
    for field, expected in reproducible.items():
        if result.get(field) != expected:
            errors.append(f"live spend result {field} differs from current source")
    if not re.fullmatch(r"[0-9a-f]{64}", str(result.get("observed_rootfs_sha256", ""))):
        errors.append("live spend rootfs observation is malformed")
    if "rootfs_sha256" in result:
        errors.append("non-reproducible rootfs is represented as a binding")
    if (
        result.get("schema_version") != 1
        or result.get("provider") != "anthropic"
        or result.get("qualification_requirement") != "provider-spend-enforcement"
    ):
        errors.append("live result is not Anthropic spend requirement 2")
    if result.get("git_remote_count") != 0:
        errors.append("live spend guest received a Git remote")
    if result.get("credential_removed_before_output") is not True:
        errors.append("live spend guest retained the credential at output")
    if result.get("host_teardown") != {
        "processes": 0,
        "taps": 0,
        "nftables_tables": 0,
        "run_directories": 0,
        "credential_files": 0,
    }:
        errors.append("live spend result does not prove exact host teardown")

    issuance = result.get("issuance", {})
    try:
        issued = parse_time(issuance["issued_at"])
        expires = parse_time(issuance["expires_at"])
        if int((expires - issued).total_seconds()) != issuance["expires_in"]:
            raise ValueError("issuance lifetime mismatch")
        if not 60 <= issuance["expires_in"] <= 300:
            raise ValueError("issuance lifetime outside policy")
    except (KeyError, TypeError, ValueError):
        errors.append("live spend issuance time is malformed")
    if (
        issuance.get("workspace_id") != workspace_id
        or issuance.get("scope") != "workspace:inference"
        or issuance.get("token_type") != "Bearer"
    ):
        errors.append("live spend bearer identity or scope differs from policy")
    delivery = result.get("delivery")
    if delivery != {
        "capability_drive_read_only": True,
        "capability_drive_unmounted_before_provider_call": True,
        "credential_removed_before_output": True,
        "assertion_delivered": False,
        "signing_key_delivered": False,
        "admin_credential_delivered": False,
    }:
        errors.append("live spend delivery boundary differs from the exact contract")

    spend = result.get("spend_enforcement", {})
    if set(spend) != {"cap_cents", "model", "probe_attempts", "denial"}:
        errors.append("live spend provider proof has an unexpected shape")
    if (
        spend.get("cap_cents") != 100
        or spend.get("model") != "claude-opus-5"
        or spend.get("probe_attempts") != 1
    ):
        errors.append("live spend provider proof used an unexpected cap, model, or probe count")
    denial = spend.get("denial", {})
    provider_error = denial.get("provider_error", {})
    if set(denial) != {"endpoint", "http_status", "denied_at", "provider_error"}:
        errors.append("live spend denial has an unexpected shape")
    if denial.get("endpoint") != "/v1/messages" or denial.get("http_status") not in {
        400,
        403,
        429,
    }:
        errors.append("live spend denial is not a provider refusal")
    if set(provider_error) != {"type", "error", "request_id"}:
        errors.append("live provider error has an unexpected shape")
    nested_error = provider_error.get("error", {})
    if (
        provider_error.get("type") != "error"
        or not isinstance(nested_error, dict)
        or set(nested_error) != {"type", "message"}
        or not re.fullmatch(r"[a-z_]{1,64}", str(nested_error.get("type", "")))
    ):
        errors.append("live provider error envelope is malformed")
    message = nested_error.get("message", "") if isinstance(nested_error, dict) else ""
    if not isinstance(message, str) or not re.search(
        r"spend|credit|billing|monthly (?:spend|usage) limit", message, re.IGNORECASE
    ):
        errors.append("live provider error is not attributable to spend enforcement")
    if not re.fullmatch(r"req_[A-Za-z0-9]+", str(provider_error.get("request_id", ""))):
        errors.append("live provider denial request ID is malformed")
    try:
        parse_time(denial.get("denied_at"))
    except (TypeError, ValueError):
        errors.append("live provider denial time is malformed")

    cap_control = result.get("cap_control", {})
    if set(cap_control) != {
        "schema_version",
        "provider",
        "organization_id",
        "workspace_id",
        "before",
        "qualification",
        "restored",
    }:
        errors.append("live cap-control evidence has an unexpected shape")
    if (
        cap_control.get("provider") != "anthropic"
        or cap_control.get("organization_id") != organization_id
        or cap_control.get("workspace_id") != workspace_id
    ):
        errors.append("live cap-control identity differs from policy")
    organization_limits = []
    cap_times: dict[str, datetime] = {}
    for name, expected in (("before", Decimal(50)), ("qualification", Decimal(1)), ("restored", Decimal(50))):
        observed = cap_control.get(name, {})
        try:
            cap_times[name] = parse_time(observed["observed_at"])
            workspace_limit = decimal_value(observed["workspace_monthly_limit_usd"])
            organization_limit = decimal_value(observed["organization_monthly_limit_usd"])
            if set(observed) != {
                "observed_at",
                "workspace_monthly_limit_usd",
                "organization_monthly_limit_usd",
                "enforcement",
            }:
                raise ValueError("unexpected readback shape")
            if workspace_limit != expected or organization_limit <= Decimal(50):
                raise ValueError("cap values differ")
            if observed["enforcement"] != "notify_and_pause":
                raise ValueError("cap does not pause")
            organization_limits.append(organization_limit)
        except (KeyError, InvalidOperation, TypeError, ValueError):
            errors.append(f"live {name} cap readback is malformed")
    if organization_limits and len(set(organization_limits)) != 1:
        errors.append("organization limit changed during workspace qualification")

    cost = result.get("cost_measurement", {})
    if set(cost) != {
        "source",
        "currency",
        "spend_before_usd",
        "observed_spend_at_denial_usd",
        "measured_overshoot_usd",
        "observed_at",
        "attribution",
    }:
        errors.append("live cost measurement has an unexpected shape")
    try:
        before = decimal_value(cost["spend_before_usd"])
        at_denial = decimal_value(cost["observed_spend_at_denial_usd"])
        overshoot = decimal_value(cost["measured_overshoot_usd"])
        cost_time = parse_time(cost["observed_at"])
        denial_time = parse_time(denial["denied_at"])
        if before < 0 or before >= Decimal(1):
            raise ValueError("baseline was not below cap")
        if at_denial <= before or overshoot != max(at_denial - Decimal(1), Decimal(0)):
            raise ValueError("overshoot arithmetic does not bind to the cap")
        if initial_failure_cost is not None and at_denial != initial_failure_cost:
            raise ValueError("final cost differs from the isolated accepted-call record")
        if cost.get("source") != "Anthropic Cost Report API" or cost.get("currency") != "USD":
            raise ValueError("cost source differs")
        if cost.get("attribution") != "isolated_workspace_with_no_calls_after_provider_denial":
            raise ValueError("cost attribution differs")
        if cap_times and not (
            cap_times["before"]
            <= cap_times["qualification"]
            <= denial_time
            <= cap_times["restored"]
            <= cost_time
        ):
            raise ValueError("cap and cost evidence is out of order")
    except (KeyError, InvalidOperation, TypeError, ValueError):
        errors.append("live cost and overshoot figures are malformed")

    serialized = json.dumps(result, sort_keys=True)
    forbidden_key = secret_named_key(result)
    if forbidden_key:
        errors.append(f"committed evidence contains forbidden key: {forbidden_key}")
    if re.search(r"sk-ant-[A-Za-z0-9_-]+", serialized):
        errors.append("committed evidence contains an Anthropic credential")
    if re.search(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", serialized):
        errors.append("committed evidence contains a JWT assertion")
    if any("ceiling" in key or "max_overshoot" in key for key in result):
        errors.append("live result encodes a forbidden preset overshoot ceiling")

if errors:
    print("Anthropic spend check: failed", file=sys.stderr)
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    raise SystemExit(1)

status = "with live result" if RESULT_PATH.exists() else "static preflight"
print(f"Anthropic spend check: pass ({status})")
