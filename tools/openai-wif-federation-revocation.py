#!/usr/bin/env python3
"""Collect one attended OpenAI federation-rule revocation observation.

The collector makes no console request. It pauses for a named actor, bounds
each operator console reading in control-plane UTC, and records two A132
Attestations. Token exchanges use the one frozen lifecycle instrument loaded
by its exact digest.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import types
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "policy/openai-wif.json"
POLICY_SHA256 = "87cf13bb136ed9a365bd14822a14d4808a6ef585ce1c278b926fa173d1152e5f"
BASE_HARNESS_PATH = ROOT / "tools/anthropic-wif-lifecycle.py"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
LIFECYCLE_INSTRUMENT_PATH = ROOT / "tools/openai-wif-issuance.py"
LIFECYCLE_INSTRUMENT_SHA256 = (
    "739396b9982218e909d933a74674cfc53c4ec76f7e202e08418a1d0910867923"
)
ATTESTATION_DEFINITION_PATH = ROOT / "tools/control-plane-attestation-v1.py"
ATTESTATION_DEFINITION_SHA256 = "0d32e80b980c334977e51eb706783896a687d29faef46d50e53f3ee56e8e4d47"
CHECKER_PATH = ROOT / "tools/check-openai-wif-federation-revocation.py"
SIGNING_KEY = Path("/etc/patchyard/anthropic-wif-signing.pem")
STAGING_ROOT = Path("/run/patchyard-openai")
RUN_ID_PATTERN = re.compile(r"openai-revocation-[0-9]{8}-[0-9a-f]{10}")
JWT = re.compile(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
OPENAI_KEY = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
BEARER = re.compile(r"Bearer [A-Za-z0-9._~-]{16,}", re.IGNORECASE)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
SETTLING_FLOOR_SECONDS = 90
MAPPING_STATE_KEYS = {
    "identity_provider_id",
    "mapping_present",
    "subject_mapping_expression",
    "mapped_service_account_id",
    "enabled",
    "uploaded_jwks_mode",
    "console_location",
}
RESPONSE_PREDICATE = {
    "enforced": False,
    "basis": "no-observed-openai-federation-revocation-response",
}


class RevocationCollectorError(RuntimeError):
    """The attended sequence could not produce a conforming observation."""


def load_exact_source(name: str, path: Path, expected: str) -> types.ModuleType:
    source = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(source).hexdigest() != expected:
        raise RevocationCollectorError(f"{path.name} differs from its exact binding")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = None
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


INSTRUMENT = load_exact_source(
    "openai_wif_issuance_revocation_instrument",
    LIFECYCLE_INSTRUMENT_PATH,
    LIFECYCLE_INSTRUMENT_SHA256,
)
ATTESTATION = load_exact_source(
    "control_plane_attestation_v1_revocation",
    ATTESTATION_DEFINITION_PATH,
    ATTESTATION_DEFINITION_SHA256,
)
BASE = INSTRUMENT.BASE
BASE.STAGING_ROOT = STAGING_ROOT


def reject_json_constant(value: str) -> None:
    raise RevocationCollectorError(f"forbidden numeric constant: {value}")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RevocationCollectorError(f"duplicate console-state key: {key}")
        result[key] = value
    return result


def credential_shaped(value: Any) -> bool:
    serialized = json.dumps(value, sort_keys=True)
    return bool(
        JWT.search(serialized)
        or OPENAI_KEY.search(serialized)
        or BEARER.search(serialized)
        or PRIVATE_KEY.search(serialized)
    )


def bounded_console_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 1024
        and all(character.isprintable() for character in value)
    )


def load_policy() -> dict[str, Any]:
    if POLICY_PATH.is_symlink() or BASE.digest_file(POLICY_PATH) != POLICY_SHA256:
        raise RevocationCollectorError("OpenAI WIF policy differs from its exact binding")
    policy = BASE.load_json_file(POLICY_PATH)
    expected = {
        "provider": "openai",
        "identity_provider_id": "idp_DlzD7RlQXgXxd1VSG2V93eEU",
        "service_account_id": "user-6tzs2hdFVN7GoYQbWfC0eu7k",
        "maximum_lifetime": 300,
    }
    observed = {
        "provider": policy.get("provider"),
        "identity_provider_id": policy.get("issuer", {}).get("id"),
        "service_account_id": policy.get("service_account", {}).get("id"),
        "maximum_lifetime": policy.get("issuer", {}).get(
            "max_jwt_lifetime_seconds"
        ),
    }
    if observed != expected:
        raise RevocationCollectorError("OpenAI WIF policy fields differ")
    return policy


def source_binding() -> dict[str, str]:
    return {
        "policy_sha256": BASE.digest_file(POLICY_PATH),
        "base_harness_sha256": BASE.digest_file(BASE_HARNESS_PATH),
        "lifecycle_instrument_sha256": BASE.digest_file(
            LIFECYCLE_INSTRUMENT_PATH
        ),
        "attestation_definition_sha256": BASE.digest_file(
            ATTESTATION_DEFINITION_PATH
        ),
        "collector_sha256": BASE.digest_file(Path(__file__).resolve()),
        "checker_sha256": BASE.digest_file(CHECKER_PATH),
    }


def validate_run_id(run_id: str) -> None:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise RevocationCollectorError("run ID is malformed")


def parse_console_state(raw: str, policy: dict[str, Any]) -> dict[str, Any]:
    if not 1 <= len(raw.encode()) <= 16_384:
        raise RevocationCollectorError("console reading is outside the byte limit")
    try:
        state = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_json_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RevocationCollectorError("console reading is not strict JSON") from error
    if not isinstance(state, dict) or set(state) != MAPPING_STATE_KEYS:
        raise RevocationCollectorError("console reading has an unexpected state shape")
    if state.get("identity_provider_id") != policy["issuer"]["id"]:
        raise RevocationCollectorError("console reading names another provider identity")
    if type(state.get("mapping_present")) is not bool:
        raise RevocationCollectorError("mapping presence is not boolean")
    if type(state.get("enabled")) is not bool:
        raise RevocationCollectorError("mapping enabled state is not boolean")
    if type(state.get("uploaded_jwks_mode")) is not bool:
        raise RevocationCollectorError("uploaded-JWKS mode is not boolean")
    for field in ("subject_mapping_expression", "mapped_service_account_id"):
        value = state.get(field)
        if value is not None and not bounded_console_text(value):
            raise RevocationCollectorError(f"console reading {field} is not bounded")
    location = state.get("console_location")
    if not bounded_console_text(location):
        raise RevocationCollectorError("console location is not safely bounded")
    if state["mapping_present"] is False and (
        state["subject_mapping_expression"] is not None
        or state["mapped_service_account_id"] is not None
        or state["enabled"] is not False
    ):
        raise RevocationCollectorError("absent mapping retained mapping state")
    if credential_shaped(state):
        raise RevocationCollectorError("console reading contains credential-shaped material")
    return state


def capture_console_reading(
    label: str,
    policy: dict[str, Any],
    *,
    input_fn: Callable[[str], str] = input,
    clock: Callable[[], datetime] = BASE.utc_now,
) -> dict[str, Any]:
    print(
        f"Capture {label}. Paste one line of credential-free JSON with exact keys: "
        + ", ".join(sorted(MAPPING_STATE_KEYS)),
        file=sys.stderr,
        flush=True,
    )
    captured_before_at = BASE.iso_time(clock())
    raw = input_fn("console reading JSON> ")
    captured_after_at = BASE.iso_time(clock())
    return {
        "captured_before_at": captured_before_at,
        "captured_after_at": captured_after_at,
        "state": parse_console_state(raw, policy),
    }


def state_without_location(state: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in state.items() if key != "console_location"}


def require_active_mapping(state: dict[str, Any], policy: dict[str, Any]) -> None:
    if (
        state.get("mapping_present") is not True
        or state.get("enabled") is not True
        or state.get("uploaded_jwks_mode") is not True
        or state.get("mapped_service_account_id")
        != policy["service_account"]["id"]
        or not state.get("subject_mapping_expression")
    ):
        raise RevocationCollectorError("console reading is not the enabled mapping")


def require_mutated_mapping(
    before: dict[str, Any], after: dict[str, Any], mutation_kind: str
) -> None:
    if before["identity_provider_id"] != after["identity_provider_id"]:
        raise RevocationCollectorError("mapping mutation changed provider identity")
    if after["uploaded_jwks_mode"] is not True:
        raise RevocationCollectorError("mapping mutation changed uploaded-JWKS mode")
    if mutation_kind == "remove":
        valid = after["mapping_present"] is False
    elif mutation_kind == "disable":
        valid = (
            after["mapping_present"] is True
            and after["enabled"] is False
            and after["subject_mapping_expression"]
            == before["subject_mapping_expression"]
            and after["mapped_service_account_id"]
            == before["mapped_service_account_id"]
        )
    else:
        valid = (
            after["mapping_present"] is True
            and after["enabled"] is True
            and after["subject_mapping_expression"]
            != before["subject_mapping_expression"]
            and after["mapped_service_account_id"]
            == before["mapped_service_account_id"]
        )
    if not valid:
        raise RevocationCollectorError("console reading does not show the named mutation")


def operator_pause(
    instruction: str,
    acknowledgement: str,
    *,
    input_fn: Callable[[str], str] = input,
) -> None:
    print(instruction, file=sys.stderr, flush=True)
    if input_fn(f"Type {acknowledgement!r} after the actor finishes> ") != acknowledgement:
        raise RevocationCollectorError("operator did not acknowledge the console mutation")


def exchange_once(
    policy: dict[str, Any], signing_key: Path, run_id: str, key_role: str
) -> dict[str, Any]:
    derived = BASE.jwk_descriptor(BASE.load_public_jwk(signing_key))
    runtime_policy = deepcopy(policy)
    runtime_policy["issuer"]["jwks_kid"] = derived["kid"]
    started_at = BASE.iso_time(BASE.utc_now())
    observation = INSTRUMENT.exchange_observation(
        runtime_policy, signing_key, run_id, started_at
    )
    descriptor = observation["assertion_descriptor"]
    if (
        descriptor.get("kid") != derived["kid"]
        or descriptor.get("jwk_thumbprint_sha256")
        != derived["jwk_thumbprint_sha256"]
    ):
        raise RevocationCollectorError("exchange did not use the derived signing key")
    return {
        "key_role": key_role,
        "attempt_count": 1,
        "started_at": observation["started_at"],
        "assertion_descriptor": descriptor,
        "exchange_request": observation["exchange_request"],
        "receipt": observation["exchange_response"],
        "credential_removed_at": observation["credential_removed_at"],
        "lifecycle_instrument_sha256": LIFECYCLE_INSTRUMENT_SHA256,
    }


def require_positive(control: dict[str, Any], label: str) -> None:
    if control.get("receipt", {}).get("access_token_supplied") is not True:
        raise RevocationCollectorError(f"{label} did not supply a bearer")


def wait_settling_floor(
    anchor: datetime,
    *,
    clock: Callable[[], datetime] = BASE.utc_now,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    elapsed = (clock() - anchor).total_seconds()
    remaining = max(0.0, SETTLING_FLOOR_SECONDS - elapsed)
    if remaining:
        print(
            f"Waiting {remaining:.3f} seconds for the settling floor.",
            file=sys.stderr,
            flush=True,
        )
        sleeper(remaining)


def mutation_description(kind: str, before: dict[str, Any], after: dict[str, Any]) -> str:
    return (
        f"{kind} only the subject mapping on identity provider "
        f"{before['identity_provider_id']}; mapping_present changed from "
        f"{str(before['mapping_present']).lower()} to "
        f"{str(after['mapping_present']).lower()} and enabled changed from "
        f"{str(before['enabled']).lower()} to {str(after['enabled']).lower()}"
    )


def collect(
    *,
    run_id: str,
    actor_name: str,
    actor_kind: str,
    attester_name: str,
    mutation_kind: str,
    policy: dict[str, Any],
    input_fn: Callable[[str], str] = input,
    clock: Callable[[], datetime] = BASE.utc_now,
    sleeper: Callable[[float], None] = time.sleep,
    exchanger: Callable[[dict[str, Any], Path, str, str], dict[str, Any]] = exchange_once,
    journal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if journal is None:
        journal = {}
    party_errors = ATTESTATION.validate_party_names(
        actor_name, actor_kind, attester_name
    )
    if party_errors:
        raise ATTESTATION.AttestationShapeError("; ".join(party_errors))
    window_started_at = BASE.iso_time(clock())
    initial = capture_console_reading(
        "the enabled mapping before the baseline control",
        policy,
        input_fn=input_fn,
        clock=clock,
    )
    require_active_mapping(initial["state"], policy)
    journal["initial_console_reading"] = initial
    baseline = exchanger(policy, SIGNING_KEY, run_id, "active")
    require_positive(baseline, "baseline control")
    journal["baseline_control"] = baseline

    mutation_before = capture_console_reading(
        "the immediate mapping state before the control-plane mutation",
        policy,
        input_fn=input_fn,
        clock=clock,
    )
    if state_without_location(mutation_before["state"]) != state_without_location(
        initial["state"]
    ):
        raise RevocationCollectorError("mapping changed between baseline and mutation")
    mutation_after: dict[str, Any] | None = None
    mutation_may_be_active = True
    journal["control_plane_mutation_started"] = True
    try:
        operator_pause(
            f"Named actor {actor_name!r} must now {mutation_kind} only the subject mapping. "
            "Do not change the service account or uploaded JWK.",
            "MUTATION COMPLETE",
            input_fn=input_fn,
        )
        mutation_after = capture_console_reading(
            "the immediate mapping state after the control-plane mutation",
            policy,
            input_fn=input_fn,
            clock=clock,
        )
        require_mutated_mapping(
            mutation_before["state"], mutation_after["state"], mutation_kind
        )
        mutation_attestation = ATTESTATION.make_attestation(
            actor_name=actor_name,
            actor_kind=actor_kind,
            attester_name=attester_name,
            before_reading=mutation_before,
            after_reading=mutation_after,
            mutation_description=mutation_description(
                mutation_kind, mutation_before["state"], mutation_after["state"]
            ),
            lifecycle_instrument_sha256=LIFECYCLE_INSTRUMENT_SHA256,
        )
        journal["mapping_mutation_attestation"] = mutation_attestation

        mutation_completed = datetime.fromisoformat(
            mutation_after["captured_after_at"].replace("Z", "+00:00")
        )
        wait_settling_floor(mutation_completed, clock=clock, sleeper=sleeper)
        denial = exchanger(policy, SIGNING_KEY, run_id, "active")
        journal["denial_observation"] = denial
    finally:
        if mutation_may_be_active:
            restoration_before = capture_console_reading(
                "the current mapping before safe restoration",
                policy,
                input_fn=input_fn,
                clock=clock,
            )
            already_safe = state_without_location(
                restoration_before["state"]
            ) == state_without_location(initial["state"])
            if already_safe:
                mutation_may_be_active = False
                journal["safe_mapping_reading"] = restoration_before
                journal["safe_mapping_restored"] = True
                if sys.exc_info()[0] is None:
                    raise RevocationCollectorError(
                        "mapping returned to its original state before captured restoration"
                    )
            else:
                mapping_changed_before_restoration = (
                    mutation_after is not None
                    and state_without_location(restoration_before["state"])
                    != state_without_location(mutation_after["state"])
                )
                operator_pause(
                    f"Named actor {actor_name!r} must now restore the exact original "
                    "subject mapping. This restoration is required even when an earlier "
                    "step failed.",
                    "RESTORATION COMPLETE",
                    input_fn=input_fn,
                )
                restoration_after = capture_console_reading(
                    "the safely restored mapping",
                    policy,
                    input_fn=input_fn,
                    clock=clock,
                )
                require_active_mapping(restoration_after["state"], policy)
                if state_without_location(
                    restoration_after["state"]
                ) != state_without_location(initial["state"]):
                    raise RevocationCollectorError(
                        "restoration did not recover the original mapping"
                    )
                restoration_attestation = ATTESTATION.make_attestation(
                    actor_name=actor_name,
                    actor_kind=actor_kind,
                    attester_name=attester_name,
                    before_reading=restoration_before,
                    after_reading=restoration_after,
                    mutation_description=(
                        "restore the exact original subject mapping on identity provider "
                        f"{policy['issuer']['id']}"
                    ),
                    lifecycle_instrument_sha256=LIFECYCLE_INSTRUMENT_SHA256,
                )
                mutation_may_be_active = False
                journal["restoration_attestation"] = restoration_attestation
                journal["safe_mapping_restored"] = True
                if mapping_changed_before_restoration:
                    raise RevocationCollectorError("mapping changed before restoration")

    restoration_completed = datetime.fromisoformat(
        restoration_after["captured_after_at"].replace("Z", "+00:00")
    )
    wait_settling_floor(restoration_completed, clock=clock, sleeper=sleeper)
    bracket = exchanger(policy, SIGNING_KEY, run_id, "active")
    require_positive(bracket, "bracketing control")
    window_ended_at = BASE.iso_time(clock())
    return {
        "schema_version": 1,
        "provider": "openai",
        "qualification_requirement": "federation-rule-revocation",
        "authorization_rulings": ["A129", "A132", "A133", "A136"],
        "observation_kind": "federation-rule-revocation",
        "run_id": run_id,
        "bounded_window": {
            "started_at": window_started_at,
            "ended_at": window_ended_at,
        },
        "initial_console_reading": initial,
        "baseline_control": baseline,
        "mapping_mutation_attestation": mutation_attestation,
        "denial_observation": denial,
        "restoration_attestation": restoration_attestation,
        "bracketing_control": bracket,
        "response_predicate": RESPONSE_PREDICATE,
        "mutation_receipt_obtained": False,
        "provider_response_observed": True,
        "qualification_evidence": False,
        "source": source_binding(),
    }


def safe_failure_reason(error: BaseException) -> str:
    reason = re.sub(r"[^A-Za-z0-9 ._:/?=+,'()\[\]-]", "?", str(error))[:512]
    if credential_shaped(reason):
        return "credential-bearing diagnostic suppressed"
    return reason or error.__class__.__name__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument(
        "--actor-kind", required=True, choices=["accountable_human", "model"]
    )
    parser.add_argument("--attester", required=True)
    parser.add_argument(
        "--mapping-mutation", required=True, choices=["remove", "disable", "alter"]
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    if os.geteuid() != 0:
        raise RevocationCollectorError("revocation collector must run as root")
    os.umask(0o077)
    args = build_parser().parse_args()
    validate_run_id(args.run_id)
    stage = BASE.validate_stage_directory(args.run_id)
    BASE.require_stage_path(args.output, stage, "output")
    signing_key = SIGNING_KEY.resolve(strict=True)
    if signing_key != SIGNING_KEY:
        raise RevocationCollectorError("signing key path differs from the active identity")
    BASE.validate_root_private_key(signing_key)
    started_at = BASE.iso_time(BASE.utc_now())
    output = BASE.ReservedOutput(
        args.output,
        {
            "schema_version": 1,
            "provider": "openai",
            "status": "in_progress",
            "action": "federation-rule-revocation",
            "run_id": args.run_id,
            "started_at": started_at,
            "mutation_receipt_obtained": False,
            "qualification_evidence": False,
            "source": source_binding(),
        },
    )
    journal: dict[str, Any] = {
        "control_plane_mutation_started": False,
        "safe_mapping_restored": False,
    }
    try:
        result = collect(
            run_id=args.run_id,
            actor_name=args.actor,
            actor_kind=args.actor_kind,
            attester_name=args.attester,
            mutation_kind=args.mapping_mutation,
            policy=load_policy(),
            journal=journal,
        )
        output.finish(result)
    except BaseException as error:
        output.finish(
            {
                "schema_version": 1,
                "provider": "openai",
                "status": "failed",
                "action": "federation-rule-revocation",
                "run_id": args.run_id,
                "started_at": started_at,
                "failed_at": BASE.iso_time(BASE.utc_now()),
                "failure_type": error.__class__.__name__,
                "failure_reason": safe_failure_reason(error),
                "safe_mapping_restoration_required": (
                    journal.get("control_plane_mutation_started") is True
                    and journal.get("safe_mapping_restored") is not True
                ),
                "partial_observations": journal,
                "mutation_receipt_obtained": False,
                "qualification_evidence": False,
                "source": source_binding(),
            }
        )
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        RevocationCollectorError,
        ATTESTATION.AttestationShapeError,
        BASE.LifecycleError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        KeyboardInterrupt,
    ) as error:
        print(f"OpenAI federation-rule revocation: {safe_failure_reason(error)}", file=sys.stderr)
        raise SystemExit(1)
