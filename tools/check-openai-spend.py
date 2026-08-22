#!/usr/bin/env python3
"""Check the OpenAI requirement-2 A132/A125 spend-enforcement contract.

Mirrors tools/check-anthropic-spend.py for the OpenAI provider. Static
preflight always runs: the reviewed provider-qualification binding, the
spend-run driver's required source clauses, and the evidence finalizer's
guards. When the committed Result exists it is validated in full against the
current sources, including the recomputed host contract and the recomputed
qualification-policy projection digest.

Unlike the Anthropic checker, no digest here pins the driver, launcher, or
one-shot client before the run: requirement 2 is not yet Proven, and freezing
pre-run sources would only block the fixes the attended run may still need.
The committed Result's own host_contract_sha256 binds the sources it actually
ran under, and this checker recomputes that binding once the Result lands.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
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
RUNTIME = types.ModuleType("factory_checker_runtime_check_openai_spend")
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
QUALIFICATION_POLICY_PATH = REPO / "policy/provider-qualification.json"
EGRESS_POLICY_PATH = REPO / "policy/provider-egress.json"
RESULT_PATH = REPO / "research/isolation/results/openai-spend-enforcement.json"
PRODUCTION_PARITY_PATH = REPO / "worker/image/production-parity.json"
RUNNER_PATH = REPO / "worker/qualification/patchyard-run-openai-spend"
LAUNCHER_PATH = REPO / "worker/runtime/patchyard-provider-run"
TRANSPORT_PATH = REPO / "worker/runtime/patchyard-openai-one-shot"
EVIDENCE_PATH = REPO / "tools/openai-spend-evidence.py"
PROCEDURE_PATH = REPO / "docs/openai-spend-capture.md"
OPENAI_REQUEST = b"OpenAI provider-side spend enforcement qualification.\n"
OPENAI_PATCH = (
    b"diff --git a/openai-spend-qualified.txt b/openai-spend-qualified.txt\n"
    b"new file mode 100644\n"
    b"index 0000000000000000000000000000000000000000.."
    b"03b57e6ebbefe1e0ae4ea3dd28451e92cbb26d96\n"
    b"--- /dev/null\n"
    b"+++ b/openai-spend-qualified.txt\n"
    b"@@ -0,0 +1 @@\n"
    b"+openai-provider-spend-enforcement-qualified\n"
)
PROVIDER_MODEL = "gpt-5.6-luna"
PROVIDER_ENDPOINT = "/v1/chat/completions"
REFUSAL_UNENFORCED_BASIS = "no-observed-openai-spend-refusal"
CAPTURE_METHOD = "operator_console_readback_bounded_by_control_plane_utc"
SETTLING_FLOOR_SECONDS = 90
ORGANIZATION_ID = "org-000000000000000000000000"
PROJECT_ID = "proj_4zpZhhPPNYCvPRE5vGuRBALH"
# A150: the id policy/openai-wif.json still names. Demoted by meaning to the
# account the banked Results were minted against; the live id is resolved from
# policy/openai-identity-history.json. The frozen policy is not edited because
# every banked OpenAI Result pins its digest as policy_sha256.
ISSUANCE_ERA_SERVICE_ACCOUNT_ID = "user-6tzs2hdFVN7GoYQbWfC0eu7k"
UNSCOPED_SENTINEL = "unscoped"
ISSUER_ID = "idp_DlzD7RlQXgXxd1VSG2V93eEU"
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
EXPECTED_QUALIFICATION_ENTRY = {
    "one_shot_client": "/usr/local/libexec/patchyard-openai-one-shot",
    "authorization_ruling": "A132",
    "phase_spend_cap_cents": {
        "temporary_refusal": 1,
        "operational_acceptance": 10000,
        "restored_acceptance": 10000,
    },
    "capability_field_patterns": {
        "secret": "^[A-Za-z0-9._-]{20,4096}$",
        "scope": "^unscoped$",
        "exchange_request_id": (
            "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        ),
        "service_account_id": "^user-[A-Za-z0-9]{16,48}$",
        "rule_id": "^idp_[A-Za-z0-9]{16,48}$",
        "workspace_id": "^proj_[A-Za-z0-9]{16,48}$",
    },
    "spend_observation": {
        "qualification_requirement": "provider-spend-enforcement",
        "authorization_ruling": "A132",
        "phases": [
            "operational_acceptance",
            "temporary_refusal",
            "restored_acceptance",
        ],
        "endpoint": "/v1/chat/completions",
        "cap_field": "expected_project_cap_cents",
        "request_id_required": False,
        "request_id_pattern": "^req_[A-Za-z0-9]{8,64}$",
        "issuance_field_patterns": {
            "scope": "^unscoped$",
            "exchange_request_id": (
                "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
            ),
            "service_account_id": "^user-[A-Za-z0-9]{16,48}$",
            "rule_id": "^idp_[A-Za-z0-9]{16,48}$",
            "workspace_id": "^proj_[A-Za-z0-9]{16,48}$",
        },
        "accepted_response": {
            "response_type": "chat.completion",
            "model": "gpt-5.6-luna",
            "usage_fields": ["prompt_tokens", "completion_tokens"],
        },
        "refusal_response": {
            "enforced": False,
            "http_status": None,
            "response_type": None,
            "error_type_pattern": None,
            "excluded_error_types": None,
            "unenforced_basis": "no-observed-openai-spend-refusal",
        },
        "work_artifact": {
            "path": "openai-spend-qualified.txt",
            "content": "openai-provider-spend-enforcement-qualified",
        },
        "rationale": (
            "Validated the host-owned A117 one-shot receipt after the bearer "
            "and provider network namespace were removed; the spend guest had "
            "neither credential nor provider allowlist. Per A125 the refusal "
            "predicate is unenforced: the non-200 was recorded as it arrived, "
            "never matched against an expected status or shape."
        ),
    },
}
REQUIRED_RUNNER_CLAUSES = (
    "TOKEN_ENDPOINT=https://auth.openai.com/oauth/token",
    "SIGNING_KEY=/etc/patchyard/openai-wif-signing.pem",
    "grant_type:\"urn:ietf:params:oauth:grant-type:token-exchange\"",
    "subject_token_type:\"urn:ietf:params:oauth:token-type:jwt\"",
    # A150: the driver must READ the scope the provider returned rather than
    # assert one, and must resolve the service-account id from the identity
    # registry rather than from the frozen policy's demoted field.
    "OBSERVED_SCOPE=$(jq -r '.scope // \"unscoped\"' \"$RUN_TEMP/exchange-response.json\")",
    "SERVICE_ACCOUNT_ID=$(jq -r .current_service_account_id \"$IDENTITY_HISTORY\")",
    'IDENTITY_HISTORY="$CHECKOUT_ROOT/policy/openai-identity-history.json"',
    ".providers.openai.trusted_kid == $kid",
    "sudo /usr/local/sbin/patchyard-provider-run",
    "/usr/local/libexec/patchyard-openai-one-shot",
    "OpenAI bearer crossed the accepted evidence boundary",
    "OIDC assertion crossed the control-plane boundary",
    "preserve_failed_evidence",
    "{enforced:false,basis:\"no-observed-openai-spend-refusal\"}",
    ".provider_observation.expected_project_cap_cents == $spend_cap_cents",
    "'(has(\"secret\") | not)'",
    "'(has(\"access_token\") | not)'",
)
REQUIRED_EVIDENCE_CLAUSES = (
    "SETTLING_FLOOR_SECONDS = 90",
    'REFUSAL_UNENFORCED_BASIS = "no-observed-openai-spend-refusal"',
    '"mutation_receipt_obtained": False,',
    'CAPTURE_METHOD = "operator_console_readback_bounded_by_control_plane_utc"',
    'raise ValueError("temporary cap was not lowered below already-settled spend")',
    'raise ValueError("post-restoration settled spend moved backwards")',
    'raise ValueError("A132 qualification crosses a monthly billing boundary")',
    'raise ValueError("A132 phases did not use distinct WIF exchanges")',
    'raise ValueError("A132 provider request bodies are not byte-identical")',
    'raise ValueError("A132 attestation claims independence it cannot have")',
    'ROUTE_AUTHORIZATION_SOURCE = "route authorization"',
    'raise ValueError("authorization source is not a route authorization")',
    'raise ValueError("OpenAI Costs API returned no factory project row")',
    'raise ValueError("OpenAI costs pagination is malformed")',
)
EXPECTED_DO_NOT_PIN_TEXT = (
    "Ship the refusal predicate unenforced, record what arrives, and enforce a "
    "descended predicate in a later reviewed change."
)
PHASES = (
    "operational_acceptance",
    "temporary_refusal",
    "restored_acceptance",
)
REQUEST_ID = re.compile(r"req_[A-Za-z0-9]{8,64}")
EXCHANGE_REQUEST_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
HEX64 = re.compile(r"[0-9a-f]{64}")


CHECKER = RUNTIME.checker_runtime(
    identity="OpenAI spend checker",
    modules=(hashlib, json, re, sysconfig, types),
    repo=REPO,
    secret_names=frozenset({"secret", "access_token", "assertion", "subject_token", "identity_token", "authorization", "private_key", "api_key"}),
    identity_history_path=IDENTITY_HISTORY_PATH,
    issuance_era_service_account_id=ISSUANCE_ERA_SERVICE_ACCOUNT_ID,
    project_id=PROJECT_ID,
)
is_within = RUNTIME.is_within
isolation_errors = CHECKER.isolation_errors
digest = RUNTIME.digest
parse_time = RUNTIME.parse_time
secret_named_key = CHECKER.secret_named_key
roster_service_account_ids = CHECKER.roster_service_account_ids

def host_contract_sha256() -> str:
    records = [
        f"{digest(path)}  {path.relative_to(REPO)}\n"
        for path in (RUNNER_PATH, LAUNCHER_PATH, TRANSPORT_PATH)
    ]
    return hashlib.sha256("".join(records).encode()).hexdigest()


def qualification_policy_sha256(qualification_policy: dict[str, Any]) -> str:
    projection = {
        "schema_version": 1,
        "provider": "openai",
        **qualification_policy["providers"]["openai"]["spend_observation"],
    }
    serialized = (
        json.dumps(projection, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def decimal_value(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("decimal figure is not a string")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("decimal figure is not finite")
    return number


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


def static_errors() -> tuple[list[str], dict[str, Any]]:
    errors = isolation_errors()
    roster_service_account_ids(errors)
    try:
        policy = json.loads(POLICY_PATH.read_text())
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"cannot read OpenAI WIF policy: {error}")
        policy = {}
    for path, expected, label in (
        (("organization", "id"), ORGANIZATION_ID, "organization"),
        (("project", "id"), PROJECT_ID, "project"),
        (
            ("service_account", "id"),
            ISSUANCE_ERA_SERVICE_ACCOUNT_ID,
            "issuance-era service account",
        ),
        (("issuer", "id"), ISSUER_ID, "issuer"),
        (
            ("spend_enforcement", "authorization_ruling"),
            "A132",
            "spend authorization ruling",
        ),
    ):
        value: Any = policy
        for key in path:
            value = value.get(key, {}) if isinstance(value, dict) else {}
        if value != expected:
            errors.append(f"OpenAI {label} differs from the reviewed binding")
    try:
        qualification_policy = json.loads(QUALIFICATION_POLICY_PATH.read_text())
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"cannot read provider qualification policy: {error}")
        qualification_policy = {"providers": {"openai": {"spend_observation": {}}}}
    if (
        qualification_policy.get("providers", {}).get("openai")
        != EXPECTED_QUALIFICATION_ENTRY
    ):
        errors.append(
            "OpenAI qualification policy entry differs from the reviewed binding"
        )
    try:
        egress = json.loads(EGRESS_POLICY_PATH.read_text())["providers"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        errors.append(f"cannot read provider egress policy: {error}")
        egress = {}
    else:
        if len(egress) != 13:
            errors.append("provider egress policy does not contain 13 providers")
    openai_egress = egress.get("openai", {}) if isinstance(egress, dict) else {}
    # The one-shot transport admits exactly one destination; the spend run
    # requires the provider to publish exactly one hostname.
    if openai_egress.get("hostnames") != ["api.openai.com"]:
        errors.append("OpenAI egress hostnames differ from the single-host binding")

    for path, clauses, label in (
        (RUNNER_PATH, REQUIRED_RUNNER_CLAUSES, "spend-run driver"),
        (EVIDENCE_PATH, REQUIRED_EVIDENCE_CLAUSES, "evidence finalizer"),
    ):
        if not path.is_file() or path.is_symlink():
            errors.append(f"OpenAI {label} is missing or a symlink")
            continue
        source = path.read_text()
        for clause in clauses:
            if clause not in source:
                errors.append(f"OpenAI {label} is missing: {clause}")
    if RUNNER_PATH.is_file():
        runner = RUNNER_PATH.read_text()
        if runner.count("https://auth.openai.com/oauth/token") != 1:
            errors.append("spend-run driver does not name exactly one token endpoint")
        if "api.openai.com/v1" in runner:
            errors.append(
                "spend-run driver names a provider API URL; billable calls belong "
                "to the worker one-shot transport"
            )
        if runner.count("curl ") != 1:
            errors.append("spend-run driver contains a second transfer client")
    try:
        procedure = " ".join(PROCEDURE_PATH.read_text().split())
    except OSError as error:
        errors.append(f"cannot read the capture procedure: {error}")
    else:
        if EXPECTED_DO_NOT_PIN_TEXT not in procedure:
            errors.append("A125 unenforced-predicate procedure text is missing")
    return errors, qualification_policy


def validate_phase(
    evidence: Any,
    phase: str,
    reproducible: dict[str, str],
    caps: dict[str, int],
    errors: list[str],
) -> tuple[datetime | None, tuple[datetime, datetime] | None, str, str]:
    """Validate one phase's worker evidence; return observed and bearer times."""
    if not isinstance(evidence, dict):
        errors.append(f"A132 {phase} evidence is not an object")
        return None, None, "", ""
    if evidence.get("qualification_phase") != phase:
        errors.append(f"A132 {phase} evidence has the wrong phase")
    for field, expected in reproducible.items():
        if evidence.get(field) != expected:
            errors.append(f"A132 {phase} {field} differs from current source")
    if (
        not HEX64.fullmatch(str(evidence.get("observed_rootfs_sha256", "")))
        or "rootfs_sha256" in evidence
        or not HEX64.fullmatch(str(evidence.get("image_recipe_sha256", "")))
    ):
        errors.append(f"A132 {phase} rootfs observation is malformed")
    if evidence.get("credential_removed_before_output") is not True:
        errors.append(f"A132 {phase} retained a credential at output")
    if evidence.get("git_remote_count") != 0:
        errors.append(f"A132 {phase} work tree gained a git remote")
    if evidence.get("host_teardown") != {
        "processes": 0,
        "taps": 0,
        "nftables_tables": 0,
        "run_directories": 0,
        "credential_files": 0,
        "guest_provider_egress_packets": 0,
    }:
        errors.append(f"A132 {phase} host teardown is incomplete")
    if evidence.get("delivery") != {
        "worker_host_tmpfs": True,
        "credential_delivered_to_guest": False,
        "credential_removed_before_guest_boot": True,
        "assertion_delivered": False,
        "signing_key_delivered": False,
        "admin_credential_delivered": False,
    }:
        errors.append(f"A117 {phase} credential delivery boundary is malformed")
    if evidence.get("observation_predicate") != {
        "endpoint": PROVIDER_ENDPOINT,
        "refusal_predicate_enforced": False,
    }:
        errors.append(f"A125 {phase} observation predicate record is malformed")
    if evidence.get("provider_transport") != {
        "schema_version": 1,
        "authorization_ruling": "A117",
        "mechanism": "host-one-shot-network-namespace-v1",
        "http_version": "1.0",
        "connection_close": True,
        "client_sha256": digest(TRANSPORT_PATH),
        "admitted_conntrack_ids": 1,
        "admitted_new_connections": 1,
        "rejected_new_connections": 0,
        "rejected_connection_packets": 0,
        "guest_provider_allowlist_entries": 0,
        "namespace_ipv6_disabled": True,
        "credential_removed_before_guest_boot": True,
    }:
        errors.append(f"A117 {phase} one-shot transport receipt is malformed")

    issuance = evidence.get("issuance", {})
    exchange_id = ""
    window: tuple[datetime, datetime] | None = None
    issued: datetime | None = None
    expires: datetime | None = None
    # A150: the id is validated by roster membership, not by equality with the
    # frozen policy's demoted issuance-era id. `scope` stays pinned to the
    # sentinel because it records an ABSENT scope, which is what the frozen
    # one-shot contract and the qualification-policy pattern still require -
    # not because the exchange is claimed to grant none. A run that observes a
    # real scope must fail here and take its own decision.
    if not isinstance(issuance, dict) or (
        issuance.get("workspace_id") != PROJECT_ID
        or issuance.get("service_account_id") not in roster_service_account_ids(errors)
        or issuance.get("rule_id") != ISSUER_ID
        or issuance.get("scope") != UNSCOPED_SENTINEL
        or issuance.get("token_type") != "Bearer"
    ):
        errors.append(f"A132 {phase} principal differs from policy")
    try:
        exchange_id = str(issuance["exchange_request_id"])
        if EXCHANGE_REQUEST_ID.fullmatch(exchange_id) is None:
            raise ValueError
        issued = parse_time(issuance["issued_at"])
        expires = parse_time(issuance["expires_at"])
        if int((expires - issued).total_seconds()) != issuance["expires_in"]:
            raise ValueError
        if not 60 <= issuance["expires_in"] <= 300:
            raise ValueError
        window = (issued, expires)
    except (KeyError, TypeError, ValueError):
        errors.append(f"A132 {phase} issuance window is malformed")

    observation = evidence.get("provider_observation", {})
    if not isinstance(observation, dict):
        errors.append(f"A132 {phase} provider observation is not an object")
        return None, window, exchange_id, ""
    body_hash = str(observation.get("request_body_sha256", ""))
    observed: datetime | None = None
    try:
        observed = parse_time(observation.get("observed_at"))
    except ValueError:
        errors.append(f"A132 {phase} provider time is malformed")
    if (
        observation.get("endpoint") != PROVIDER_ENDPOINT
        or observation.get("request_attempts") != 1
        or observation.get("expected_project_cap_cents") != caps[phase]
        or not HEX64.fullmatch(body_hash)
    ):
        errors.append(f"A132 {phase} provider observation is malformed")
    request_id = observation.get("request_id")
    supplied = observation.get("request_id_supplied")
    if not isinstance(supplied, bool) or supplied != (request_id is not None):
        errors.append(f"A132 {phase} request-id record is inconsistent")
    elif request_id is not None and (
        not isinstance(request_id, str)
        or REQUEST_ID.fullmatch(request_id) is None
    ):
        errors.append(f"A132 {phase} request id is malformed")
    if (
        observed is not None
        and issued is not None
        and expires is not None
        and not issued <= observed < expires
    ):
        errors.append(f"A132 {phase} provider request is outside bearer lifetime")
    if phase == "temporary_refusal":
        # A125: the refusal is recorded as it arrived. Only the unenforcement
        # record and the bounded diagnostic hygiene are required.
        provider_error = observation.get("provider_error", {})
        if (
            observation.get("outcome") != "refused"
            or observation.get("response_predicate")
            != {"enforced": False, "basis": REFUSAL_UNENFORCED_BASIS}
            or not isinstance(observation.get("http_status"), int)
            or isinstance(observation.get("http_status"), bool)
            or not isinstance(provider_error, dict)
            or provider_error.get("message_class")
            not in {"spend_attributable", "unattributed"}
            or not HEX64.fullmatch(str(provider_error.get("message_sha256", "")))
            or set(provider_error.get("shape", {}))
            != {"top_level_keys", "error_keys"}
        ):
            errors.append("A125 refusal is not a recorded bounded observation")
    else:
        usage = observation.get("usage", {})
        if (
            observation.get("outcome") != "accepted"
            or observation.get("http_status") != 200
            or observation.get("response_type") != "chat.completion"
            or observation.get("model") != PROVIDER_MODEL
            or not isinstance(usage, dict)
            or not all(
                isinstance(usage.get(name), int) and usage.get(name, 0) >= 1
                for name in ("prompt_tokens", "completion_tokens")
            )
        ):
            errors.append(f"A132 {phase} positive control was not accepted")
    return observed, window, exchange_id, body_hash


def validate_result(
    result: Any, qualification_policy: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["A132 live result is not a JSON object"]
    if set(result) != {
        "schema_version",
        "provider",
        "qualification_requirement",
        "authorization_ruling",
        "organization_id",
        "project_id",
        "service_account_id",
        "request_binding",
        "refusal_predicate",
        "phases",
        "cap_control",
        "attestation",
        "control_plane_provenance",
        "cost_measurement",
    }:
        errors.append("A132 live result has an unexpected top-level shape")
    if (
        result.get("schema_version") != 1
        or result.get("provider") != "openai"
        or result.get("qualification_requirement") != "provider-spend-enforcement"
        or result.get("authorization_ruling") != "A132"
        or result.get("organization_id") != ORGANIZATION_ID
        or result.get("project_id") != PROJECT_ID
        or result.get("service_account_id") not in roster_service_account_ids(errors)
    ):
        errors.append("A132 live result identity differs from policy")
    if result.get("refusal_predicate") != {
        "enforced": False,
        "basis": REFUSAL_UNENFORCED_BASIS,
    }:
        errors.append("A125 result does not record the unenforced refusal predicate")
    if result.get("control_plane_provenance") != {
        "management_surface": "console-only",
        "mutation_receipt_obtained": False,
        "attestation_required": True,
    }:
        errors.append("A132 result does not carry the console-only provenance mark")
    phases = result.get("phases", {})
    if not isinstance(phases, dict) or set(phases) != set(PHASES):
        errors.append("A132 live result does not contain exactly three phases")
        phases = {}
    caps = {
        phase: EXPECTED_QUALIFICATION_ENTRY["phase_spend_cap_cents"][phase]
        for phase in PHASES
    }
    reproducible = {
        "schema_version": 1,
        "provider": "openai",
        "qualification_requirement": "provider-spend-enforcement",
        "authorization_ruling": "A132",
        "request_sha256": hashlib.sha256(OPENAI_REQUEST).hexdigest(),
        "patch_sha256": hashlib.sha256(OPENAI_PATCH).hexdigest(),
        "production_parity_sha256": digest(PRODUCTION_PARITY_PATH),
        "host_contract_sha256": host_contract_sha256(),
        "qualification_policy_sha256": qualification_policy_sha256(
            qualification_policy
        ),
    }
    provider_times: dict[str, datetime] = {}
    body_hashes: set[str] = set()
    exchange_ids: list[str] = []
    windows: list[tuple[datetime, datetime]] = []
    for phase in PHASES:
        observed, window, exchange_id, body_hash = validate_phase(
            phases.get(phase, {}), phase, reproducible, caps, errors
        )
        if observed is not None:
            provider_times[phase] = observed
        if window is not None:
            windows.append(window)
        exchange_ids.append(exchange_id)
        body_hashes.add(body_hash)
    invariants = (
        "base_sha",
        "observed_rootfs_sha256",
        "image_recipe_sha256",
    )
    for field in invariants:
        if (
            len(
                {
                    str(phases.get(phase, {}).get(field, ""))
                    for phase in PHASES
                }
            )
            != 1
        ):
            errors.append(f"A132 phase {field} values differ")
    if len(set(exchange_ids)) != 3:
        errors.append("A132 phases do not bind three distinct WIF exchanges")
    if len(windows) == 3 and any(
        first[1] > second[0] for first, second in zip(windows, windows[1:])
    ):
        errors.append("A132 phase WIF lifetimes overlap")
    binding = result.get("request_binding", {})
    if binding != {
        "model": PROVIDER_MODEL,
        "endpoint": PROVIDER_ENDPOINT,
        "request_body_sha256": next(iter(body_hashes), ""),
        "byte_identical_across_phases": True,
    } or len(body_hashes) != 1:
        errors.append("A132 request binding does not match the phase evidence")

    cap_control = result.get("cap_control", {})
    cap_intervals: dict[str, tuple[datetime, datetime]] = {}
    if not isinstance(cap_control, dict) or set(cap_control) != {
        "schema_version",
        "provider",
        "organization_id",
        "project_id",
        *PHASES,
    }:
        errors.append("A132 cap control has an unexpected shape")
        cap_control = {}
    elif (
        cap_control.get("schema_version") != 1
        or cap_control.get("provider") != "openai"
        or cap_control.get("organization_id") != ORGANIZATION_ID
        or cap_control.get("project_id") != PROJECT_ID
    ):
        errors.append("A132 cap control identity differs from policy")
    for phase in PHASES:
        cap = cap_control.get(phase, {}) if isinstance(cap_control, dict) else {}
        try:
            before = parse_time(cap["captured_before_at"])
            after = parse_time(cap["captured_after_at"])
            organization_cap = decimal_value(cap["organization_monthly_limit_usd"])
            if (
                set(cap)
                != {
                    "captured_before_at",
                    "captured_after_at",
                    "organization_monthly_limit_usd",
                    "hard_limit_enforced",
                    "capture_method",
                }
                or cap["capture_method"] != CAPTURE_METHOD
                or before > after
                or (after - before).total_seconds() > 300
                or organization_cap != Decimal(caps[phase]) / 100
                or cap["hard_limit_enforced"]
                is not (phase == "temporary_refusal")
            ):
                raise ValueError
            cap_intervals[phase] = (before, after)
        except (KeyError, InvalidOperation, TypeError, ValueError):
            errors.append(f"A132 {phase} cap readback is malformed")

    attestation = result.get("attestation", {})
    if isinstance(attestation, dict) and set(attestation) == ROUTE_ATTESTATION_KEYS:
        if (
            attestation.get("schema_version") != 1
            or attestation.get("provider") != "openai"
            or attestation.get("authorization_ruling") != ROUTE_AUTHORIZATION_RULING
            or attestation.get("mutation_surface") != "organization-limits-console"
            or attestation.get("mutation_receipt_obtained") is not False
        ):
            errors.append("A148 route-authorization record identity is malformed")
        authorization = attestation.get("human_authorization", {})
        if not isinstance(authorization, dict) or set(authorization) != (
            ROUTE_AUTHORIZATION_KEYS
        ):
            errors.append("route authorization has an unexpected shape")
        elif (
            authorization.get("source") != ROUTE_AUTHORIZATION_SOURCE
            or authorization.get("ruling") != ROUTE_AUTHORIZATION_RULING
            or authorization.get("map_url") != ROUTE_AUTHORIZATION_MAP_URL
            or authorization.get("grant_url") != ROUTE_AUTHORIZATION_GRANT_URL
            or authorization.get("author_login") != AUTHORIZATION_AUTHOR
            or authorization.get("human_attestation_obtained") is not False
            or authorization.get("human_authorship_mechanically_proven") is not False
        ):
            if authorization.get("source") != ROUTE_AUTHORIZATION_SOURCE:
                errors.append("authorization source is not a route authorization")
            else:
                errors.append("route authorization identity is malformed")
        mutations = attestation.get("mutations")
        if not isinstance(mutations, list) or [
            item.get("phase") if isinstance(item, dict) else None
            for item in mutations
        ] != ["temporary_refusal", "restored_acceptance"]:
            errors.append("A148 route-authorization record does not record exactly two mutations")
    elif not isinstance(attestation, dict) or set(attestation) != {
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
        errors.append("A132 attestation has an unexpected shape")
    else:
        if (
            attestation.get("schema_version") != 1
            or attestation.get("provider") != "openai"
            or attestation.get("authorization_ruling") != "A132"
            or attestation.get("mutation_surface") != "organization-limits-console"
            or attestation.get("mutation_receipt_obtained") is not False
        ):
            errors.append("A132 attestation identity is malformed")
        actor = attestation.get("actor")
        attester = attestation.get("attester")
        if not isinstance(actor, str) or not isinstance(attester, str):
            errors.append("A132 attestation parties are malformed")
        elif (
            actor == attester
            and attestation.get("independent_attestation") is not False
        ):
            # A136: one person as actor and attester carries no independence.
            errors.append("A132 attestation claims independence it cannot have")
        mutations = attestation.get("mutations")
        if not isinstance(mutations, list) or [
            item.get("phase") if isinstance(item, dict) else None
            for item in mutations
        ] != ["temporary_refusal", "restored_acceptance"]:
            errors.append("A132 attestation does not record exactly two mutations")

    cost = result.get("cost_measurement", {})
    try:
        before_amount = decimal_value(cost["settled_spend_before_activation_usd"])
        after_amount = decimal_value(cost["settled_spend_after_restoration_usd"])
        incremental = decimal_value(cost["incremental_spend_usd"])
        before_time = parse_time(cost["before_captured_at"])
        after_time = parse_time(cost["after_captured_at"])
        window_start = parse_time(cost["reporting_window_starting_at"])
        if (
            set(cost)
            != {
                "source",
                "currency",
                "settled_spend_before_activation_usd",
                "settled_spend_after_restoration_usd",
                "incremental_spend_usd",
                "before_captured_at",
                "after_captured_at",
                "reporting_window_starting_at",
                "settling_floor_seconds",
                "attribution",
            }
            or cost["source"] != "OpenAI Costs API"
            or cost["currency"] != "USD"
            or cost["settling_floor_seconds"] != SETTLING_FLOOR_SECONDS
            or cost["attribution"]
            != "A132_acceptance_refusal_acceptance_organization_cap_change"
            or before_amount <= Decimal(caps["temporary_refusal"]) / 100
            or after_amount < before_amount
            or incremental != after_amount - before_amount
            or window_start > before_time
        ):
            raise ValueError
        if set(provider_times) == set(PHASES) and set(cap_intervals) == set(
            PHASES
        ):
            if not (
                cap_intervals["operational_acceptance"][1]
                <= provider_times["operational_acceptance"]
                <= before_time
                <= cap_intervals["temporary_refusal"][0]
                <= cap_intervals["temporary_refusal"][1]
                <= provider_times["temporary_refusal"]
                <= cap_intervals["restored_acceptance"][0]
                <= cap_intervals["restored_acceptance"][1]
                <= provider_times["restored_acceptance"]
                <= after_time
            ):
                raise ValueError
            for phase in ("temporary_refusal", "restored_acceptance"):
                settling = (
                    provider_times[phase] - cap_intervals[phase][1]
                ).total_seconds()
                if settling < SETTLING_FLOOR_SECONDS:
                    raise ValueError
            event_times = {
                *provider_times.values(),
                before_time,
                after_time,
                *(
                    time
                    for interval in cap_intervals.values()
                    for time in interval
                ),
            }
            if (
                len(
                    {
                        (
                            value.astimezone(timezone.utc).year,
                            value.astimezone(timezone.utc).month,
                        )
                        for value in event_times
                    }
                )
                != 1
            ):
                raise ValueError
    except (KeyError, InvalidOperation, TypeError, ValueError):
        errors.append(
            "A132 cost separation, settling floor, or phase ordering is malformed"
        )
    if contains_forbidden_ceiling(result):
        errors.append("A132 result encodes a forbidden preset overshoot ceiling")
    serialized = json.dumps(result, sort_keys=True)
    if secret_named_key(result) or re.search(
        r"sk-[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_-]+\.eyJ", serialized
    ):
        errors.append("A132 result contains a credential")
    return errors


def main() -> int:
    errors, qualification_policy = static_errors()
    allow_missing = "--allow-missing-results" in sys.argv[1:]
    unknown = [
        argument
        for argument in sys.argv[1:]
        if argument != "--allow-missing-results"
    ]
    for argument in unknown:
        errors.append(f"unknown checker argument: {argument}")
    if not RESULT_PATH.exists():
        if not allow_missing:
            errors.append("OpenAI spend-enforcement result is missing")
    else:
        try:
            result = json.loads(RESULT_PATH.read_text())
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"cannot read OpenAI spend result: {error}")
        else:
            errors.extend(validate_result(result, qualification_policy))
    if errors:
        print("OpenAI spend check: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    status = (
        "with live A132/A125 result"
        if RESULT_PATH.exists()
        else "static preflight"
    )
    print(f"OpenAI spend check: pass ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
