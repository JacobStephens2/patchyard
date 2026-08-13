#!/usr/bin/env python3
"""Collect one attended OpenAI signing-key rotation observation.

Console control-plane mutations are performed only by the named actor while
this collector is paused. Token exchanges use one digest-fixed lifecycle
instrument. The replacement identifier is always derived as
``patchyard-`` plus the first sixteen hex characters of SHA-256(public DER).
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
CHECKER_PATH = ROOT / "tools/check-openai-wif-signing-key-rotation.py"
SIGNING_KEY = Path("/etc/patchyard/anthropic-wif-signing.pem")
STAGING_ROOT = Path("/run/patchyard-openai")
RUN_ID_PATTERN = re.compile(r"openai-rotation-[0-9]{8}-[0-9a-f]{10}")
HEX64 = re.compile(r"[0-9a-f]{64}")
KID = re.compile(r"patchyard-[0-9a-f]{16}")
JWT = re.compile(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
OPENAI_KEY = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
BEARER = re.compile(r"Bearer [A-Za-z0-9._~-]{16,}", re.IGNORECASE)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
SETTLING_FLOOR_SECONDS = 90
OVERLAP_POSITIVE_MAX_ATTEMPTS = 4
OVERLAP_POSITIVE_RETRY_SECONDS = 90
ROTATION_STATE_KEYS = {
    "identity_provider_id",
    "uploaded_jwks_mode",
    "public_keys",
    "subject_mapping_expression",
    "mapped_service_account_id",
    "subject_mapping_enabled",
    "console_location",
}
PUBLIC_KEY_KEYS = {"kid", "jwk_thumbprint_sha256", "enabled"}
RESPONSE_PREDICATE = {
    "enforced": False,
    "basis": "no-observed-openai-retired-signing-key-response",
}


class RotationCollectorError(RuntimeError):
    """The attended sequence could not produce a conforming observation."""


def load_exact_source(name: str, path: Path, expected: str) -> types.ModuleType:
    source = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(source).hexdigest() != expected:
        raise RotationCollectorError(f"{path.name} differs from its exact binding")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = None
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


INSTRUMENT = load_exact_source(
    "openai_wif_issuance_rotation_instrument",
    LIFECYCLE_INSTRUMENT_PATH,
    LIFECYCLE_INSTRUMENT_SHA256,
)
ATTESTATION = load_exact_source(
    "control_plane_attestation_v1_rotation",
    ATTESTATION_DEFINITION_PATH,
    ATTESTATION_DEFINITION_SHA256,
)
BASE = INSTRUMENT.BASE
BASE.STAGING_ROOT = STAGING_ROOT


def reject_json_constant(value: str) -> None:
    raise RotationCollectorError(f"forbidden numeric constant: {value}")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RotationCollectorError(f"duplicate console-state key: {key}")
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
        raise RotationCollectorError("OpenAI WIF policy differs from its exact binding")
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
        raise RotationCollectorError("OpenAI WIF policy fields differ")
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
        raise RotationCollectorError("run ID is malformed")


def validate_public_descriptor(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != PUBLIC_KEY_KEYS:
        raise RotationCollectorError("public-key descriptor shape differs")
    if KID.fullmatch(str(value.get("kid", ""))) is None:
        raise RotationCollectorError("public-key identifier was not derived")
    if HEX64.fullmatch(str(value.get("jwk_thumbprint_sha256", ""))) is None:
        raise RotationCollectorError("public-key thumbprint is malformed")
    if type(value.get("enabled")) is not bool:
        raise RotationCollectorError("public-key enabled state is not boolean")
    return value


def parse_console_state(raw: str, policy: dict[str, Any]) -> dict[str, Any]:
    if not 1 <= len(raw.encode()) <= 32_768:
        raise RotationCollectorError("console reading is outside the byte limit")
    try:
        state = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_json_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RotationCollectorError("console reading is not strict JSON") from error
    if not isinstance(state, dict) or set(state) != ROTATION_STATE_KEYS:
        raise RotationCollectorError("console reading has an unexpected state shape")
    if state.get("identity_provider_id") != policy["issuer"]["id"]:
        raise RotationCollectorError("console reading names another provider identity")
    if type(state.get("uploaded_jwks_mode")) is not bool:
        raise RotationCollectorError("uploaded-JWKS mode is not boolean")
    if type(state.get("subject_mapping_enabled")) is not bool:
        raise RotationCollectorError("subject-mapping enabled state is not boolean")
    if state.get("mapped_service_account_id") != policy["service_account"]["id"]:
        raise RotationCollectorError("console reading maps another service account")
    expression = state.get("subject_mapping_expression")
    location = state.get("console_location")
    if not bounded_console_text(expression):
        raise RotationCollectorError("subject-mapping expression is not bounded")
    if not bounded_console_text(location):
        raise RotationCollectorError("console location is not safely bounded")
    keys = state.get("public_keys")
    if not isinstance(keys, list) or not 1 <= len(keys) <= 2:
        raise RotationCollectorError("console reading has an invalid public-key set")
    for key in keys:
        validate_public_descriptor(key)
    identities = [(key["kid"], key["jwk_thumbprint_sha256"]) for key in keys]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise RotationCollectorError("public-key membership is not unique and sorted")
    if credential_shaped(state):
        raise RotationCollectorError("console reading contains credential-shaped material")
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
        + ", ".join(sorted(ROTATION_STATE_KEYS)),
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


def descriptor_with_enabled(descriptor: dict[str, str]) -> dict[str, Any]:
    return {**descriptor, "enabled": True}


def require_console_state(
    state: dict[str, Any],
    policy: dict[str, Any],
    expected_keys: list[dict[str, Any]],
) -> None:
    if (
        state["uploaded_jwks_mode"] is not True
        or state["subject_mapping_enabled"] is not True
        or state["mapped_service_account_id"] != policy["service_account"]["id"]
        or not state["subject_mapping_expression"]
        or state["public_keys"] != sorted(
            expected_keys, key=lambda item: (item["kid"], item["jwk_thumbprint_sha256"])
        )
    ):
        raise RotationCollectorError("console reading does not show expected key membership")


def operator_pause(
    instruction: str,
    acknowledgement: str,
    *,
    input_fn: Callable[[str], str] = input,
) -> None:
    print(instruction, file=sys.stderr, flush=True)
    if input_fn(f"Type {acknowledgement!r} after the actor finishes> ") != acknowledgement:
        raise RotationCollectorError("operator did not acknowledge the console mutation")


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    BASE.validate_new_output_path(path)
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        BASE.write_all(descriptor, BASE.encoded_json(value))
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
    finally:
        os.close(descriptor)


def generate_replacement_key(path: Path) -> dict[str, str]:
    BASE.validate_new_output_path(path)
    subprocess.run(
        [
            "/usr/bin/openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:3072",
            "-out",
            str(path),
        ],
        check=True,
        capture_output=True,
        env=INSTRUMENT.credential_free_env(),
    )
    os.chmod(path, 0o400)
    os.chown(path, 0, 0)
    BASE.validate_root_private_key(path)
    return BASE.jwk_descriptor(BASE.load_public_jwk(path))


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
        raise RotationCollectorError("exchange did not use the derived signing key")
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
        raise RotationCollectorError(f"{label} did not supply a bearer")


def overlap_positive_with_retry(
    policy: dict[str, Any],
    replacement_key: Path,
    run_id: str,
    journal: dict[str, Any],
    *,
    exchanger: Callable[[dict[str, Any], Path, str, str], dict[str, Any]],
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Exchange with the replacement key, retrying above the settling floor.

    Every attempt's receipt is journaled before any positivity requirement, so
    a run that never observes a bearer still preserves what the provider said.
    """
    attempts: list[dict[str, Any]] = []
    journal["overlap_positive_attempts"] = attempts
    for attempt in range(1, OVERLAP_POSITIVE_MAX_ATTEMPTS + 1):
        observation = exchanger(
            policy, replacement_key, run_id, "replacement_staging"
        )
        observation["attempt_count"] = attempt
        attempts.append(observation)
        journal["overlap_positive_control"] = observation
        if observation.get("receipt", {}).get("access_token_supplied") is True:
            return observation
        if attempt < OVERLAP_POSITIVE_MAX_ATTEMPTS:
            print(
                f"Overlap positive attempt {attempt} did not supply a bearer; "
                f"waiting {OVERLAP_POSITIVE_RETRY_SECONDS} seconds for JWKS "
                "propagation before retrying.",
                file=sys.stderr,
                flush=True,
            )
            sleeper(float(OVERLAP_POSITIVE_RETRY_SECONDS))
    require_positive(
        journal["overlap_positive_control"],
        "replacement-key overlap positive control",
    )
    raise RotationCollectorError("overlap positive retry loop is inconsistent")


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


def activate_replacement(
    policy: dict[str, Any],
    replacement_key: Path,
    active_jwk: dict[str, Any],
    stage: Path,
    run_id: str,
) -> tuple[dict[str, Any], Path]:
    current_jwks = stage / "current-jwks.json"
    retired_key = stage / "retired.pem"
    write_new_json(current_jwks, {"keys": [active_jwk]})
    event = BASE.activate_replacement(
        policy,
        replacement_key,
        current_jwks,
        retired_key,
        run_id,
    )
    return {
        "source": "local_atomic_key_activation",
        "active_key_path": str(SIGNING_KEY),
        "original_key": event["activation"]["retired_key"],
        "replacement_key": event["activation"]["replacement_key"],
        "original_key_preserved_in_root_tmpfs": True,
        "observed_at": event["observed_at"],
        "base_harness_sha256": BASE_HARNESS_SHA256,
    }, retired_key


def capture_safe_rotation_rollback(
    *,
    actor_name: str,
    actor_kind: str,
    attester_name: str,
    policy: dict[str, Any],
    original_reading: dict[str, Any],
    original_descriptor: dict[str, str],
    replacement_descriptor: dict[str, str],
    retirement_confirmed: bool,
    input_fn: Callable[[str], str] = input,
    clock: Callable[[], datetime] = BASE.utc_now,
) -> dict[str, Any]:
    before = capture_console_reading(
        "the current public-key state before safe rotation rollback",
        policy,
        input_fn=input_fn,
        clock=clock,
    )
    active_descriptor = BASE.jwk_descriptor(BASE.load_public_jwk(SIGNING_KEY))
    if active_descriptor == original_descriptor:
        target_name = "original one-key state"
        target_keys = [descriptor_with_enabled(original_descriptor)]
    elif active_descriptor == replacement_descriptor:
        if retirement_confirmed:
            target_name = "replacement-only state"
            target_keys = [descriptor_with_enabled(replacement_descriptor)]
        else:
            target_name = "two-key overlap state"
            target_keys = [
                descriptor_with_enabled(original_descriptor),
                descriptor_with_enabled(replacement_descriptor),
            ]
    else:
        raise RotationCollectorError(
            "stable active key differs from both run-derived descriptors"
        )
    target_keys = sorted(
        target_keys,
        key=lambda item: (item["kid"], item["jwk_thumbprint_sha256"]),
    )
    expected_state = deepcopy(original_reading["state"])
    expected_state["public_keys"] = target_keys
    if state_without_location(before["state"]) == state_without_location(
        expected_state
    ):
        return {
            "status": "safe_state_already_present",
            "target": target_name,
            "active_key": active_descriptor,
            "bounded_console_reading": before,
            "mutation_receipt_obtained": False,
        }

    identifiers = ", ".join(item["kid"] for item in target_keys)
    operator_pause(
        f"Named actor {actor_name!r} must restore the {target_name}, with exactly "
        f"these derived public-key identifiers: {identifiers}.",
        "SAFE ROLLBACK COMPLETE",
        input_fn=input_fn,
    )
    after = capture_console_reading(
        f"the {target_name} after safe rotation rollback",
        policy,
        input_fn=input_fn,
        clock=clock,
    )
    require_console_state(after["state"], policy, target_keys)
    if state_without_location(after["state"]) != state_without_location(
        expected_state
    ):
        raise RotationCollectorError(
            "safe rotation rollback changed a non-key console field"
        )
    rollback_attestation = ATTESTATION.make_attestation(
        actor_name=actor_name,
        actor_kind=actor_kind,
        attester_name=attester_name,
        before_reading=before,
        after_reading=after,
        mutation_description=(
            f"restore the safe {target_name} on identity provider "
            f"{policy['issuer']['id']} with derived identifiers {identifiers}"
        ),
        lifecycle_instrument_sha256=LIFECYCLE_INSTRUMENT_SHA256,
    )
    return {
        "status": "safe_state_restored",
        "target": target_name,
        "active_key": active_descriptor,
        "rollback_attestation": rollback_attestation,
        "mutation_receipt_obtained": False,
    }


def collect(
    *,
    run_id: str,
    actor_name: str,
    actor_kind: str,
    attester_name: str,
    policy: dict[str, Any],
    stage: Path,
    input_fn: Callable[[str], str] = input,
    clock: Callable[[], datetime] = BASE.utc_now,
    sleeper: Callable[[float], None] = time.sleep,
    exchanger: Callable[[dict[str, Any], Path, str, str], dict[str, Any]] = exchange_once,
    key_generator: Callable[[Path], dict[str, str]] = generate_replacement_key,
    activator: Callable[
        [dict[str, Any], Path, dict[str, Any], Path, str],
        tuple[dict[str, Any], Path],
    ] = activate_replacement,
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
    active_jwk = BASE.load_public_jwk(SIGNING_KEY)
    active_descriptor = BASE.jwk_descriptor(active_jwk)
    original = capture_console_reading(
        "the original one-key state before any replacement upload",
        policy,
        input_fn=input_fn,
        clock=clock,
    )
    require_console_state(
        original["state"], policy, [descriptor_with_enabled(active_descriptor)]
    )
    journal["original_console_reading"] = original
    journal["original_descriptor"] = active_descriptor
    baseline = exchanger(policy, SIGNING_KEY, run_id, "original_active")
    journal["baseline_control"] = baseline
    require_positive(baseline, "baseline control")

    replacement_key = stage / "replacement.pem"
    replacement_descriptor = key_generator(replacement_key)
    if replacement_descriptor == active_descriptor:
        raise RotationCollectorError("replacement key is not distinct")
    journal["replacement_descriptor"] = replacement_descriptor
    descriptors = {
        "original": active_descriptor,
        "replacement": replacement_descriptor,
    }

    overlap_before = capture_console_reading(
        "the immediate one-key state before the overlap upload",
        policy,
        input_fn=input_fn,
        clock=clock,
    )
    if state_without_location(overlap_before["state"]) != state_without_location(
        original["state"]
    ):
        raise RotationCollectorError("key membership changed before overlap")
    journal["control_plane_mutation_started"] = True
    operator_pause(
        f"Named actor {actor_name!r} must upload the two-key overlap using only the "
        "public JWKs derived in this run. No private key crosses to the console.",
        "OVERLAP COMPLETE",
        input_fn=input_fn,
    )
    overlap_after = capture_console_reading(
        "the immediate two-key overlap state",
        policy,
        input_fn=input_fn,
        clock=clock,
    )
    require_console_state(
        overlap_after["state"],
        policy,
        [
            descriptor_with_enabled(active_descriptor),
            descriptor_with_enabled(replacement_descriptor),
        ],
    )
    overlap_attestation = ATTESTATION.make_attestation(
        actor_name=actor_name,
        actor_kind=actor_kind,
        attester_name=attester_name,
        before_reading=overlap_before,
        after_reading=overlap_after,
        mutation_description=(
            "upload a two-key public-JWK overlap containing derived identifiers "
            f"{active_descriptor['kid']} and {replacement_descriptor['kid']} on "
            f"identity provider {policy['issuer']['id']}"
        ),
        lifecycle_instrument_sha256=LIFECYCLE_INSTRUMENT_SHA256,
    )
    journal["overlap_attestation"] = overlap_attestation
    overlap_completed = datetime.fromisoformat(
        overlap_after["captured_after_at"].replace("Z", "+00:00")
    )
    wait_settling_floor(overlap_completed, clock=clock, sleeper=sleeper)
    overlap_positive = overlap_positive_with_retry(
        policy,
        replacement_key,
        run_id,
        journal,
        exchanger=exchanger,
        sleeper=sleeper,
    )

    operator_pause(
        "The collector is ready to atomically activate the replacement locally while "
        "preserving the original only in the root tmpfs stage.",
        "ACTIVATE LOCALLY",
        input_fn=input_fn,
    )
    local_activation, retired_key = activator(
        policy, replacement_key, active_jwk, stage, run_id
    )
    journal["local_activation"] = local_activation

    retirement_before = capture_console_reading(
        "the two-key overlap immediately before original-key retirement",
        policy,
        input_fn=input_fn,
        clock=clock,
    )
    if state_without_location(retirement_before["state"]) != state_without_location(
        overlap_after["state"]
    ):
        raise RotationCollectorError("key membership changed before retirement")
    operator_pause(
        f"Named actor {actor_name!r} must remove only the original public JWK "
        f"with derived identifier {active_descriptor['kid']}.",
        "RETIREMENT COMPLETE",
        input_fn=input_fn,
    )
    retirement_after = capture_console_reading(
        "the immediate replacement-only state after retirement",
        policy,
        input_fn=input_fn,
        clock=clock,
    )
    require_console_state(
        retirement_after["state"],
        policy,
        [descriptor_with_enabled(replacement_descriptor)],
    )
    retirement_attestation = ATTESTATION.make_attestation(
        actor_name=actor_name,
        actor_kind=actor_kind,
        attester_name=attester_name,
        before_reading=retirement_before,
        after_reading=retirement_after,
        mutation_description=(
            "remove original public JWK with derived identifier "
            f"{active_descriptor['kid']} from identity provider "
            f"{policy['issuer']['id']}, leaving only replacement "
            f"{replacement_descriptor['kid']}"
        ),
        lifecycle_instrument_sha256=LIFECYCLE_INSTRUMENT_SHA256,
    )
    journal["retirement_attestation"] = retirement_attestation
    journal["retirement_confirmed"] = True
    retirement_completed = datetime.fromisoformat(
        retirement_after["captured_after_at"].replace("Z", "+00:00")
    )
    wait_settling_floor(retirement_completed, clock=clock, sleeper=sleeper)

    subwindow_started_at = BASE.iso_time(clock())
    bracket_journal: dict[str, Any] = {}
    journal["a129_bracket"] = bracket_journal
    bracket_before = exchanger(policy, SIGNING_KEY, run_id, "replacement_active")
    bracket_journal["bracketing_control_before_denial"] = bracket_before
    require_positive(bracket_before, "pre-denial bracketing control")
    denial = exchanger(policy, retired_key, run_id, "original_retired")
    bracket_journal["denial_observation"] = denial
    bracket_after = exchanger(policy, SIGNING_KEY, run_id, "replacement_active")
    bracket_journal["bracketing_control_after_denial"] = bracket_after
    require_positive(bracket_after, "post-denial bracketing control")
    subwindow_ended_at = BASE.iso_time(clock())
    window_ended_at = BASE.iso_time(clock())
    return {
        "schema_version": 1,
        "provider": "openai",
        "qualification_requirement": "signing-key-rotation",
        "authorization_rulings": ["A129", "A132", "A133", "A136"],
        "observation_kind": "signing-key-rotation",
        "run_id": run_id,
        "bounded_window": {
            "started_at": window_started_at,
            "ended_at": window_ended_at,
        },
        "original_console_reading": original,
        "baseline_control": baseline,
        "derived_public_key_descriptors": descriptors,
        "overlap_attestation": overlap_attestation,
        "overlap_positive_control": overlap_positive,
        "local_activation": local_activation,
        "retirement_attestation": retirement_attestation,
        "a129_bracket": {
            "bounded_subwindow": {
                "started_at": subwindow_started_at,
                "ended_at": subwindow_ended_at,
            },
            "bracketing_control_before_denial": bracket_before,
            "denial_observation": denial,
            "bracketing_control_after_denial": bracket_after,
        },
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
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    if os.geteuid() != 0:
        raise RotationCollectorError("rotation collector must run as root")
    os.umask(0o077)
    args = build_parser().parse_args()
    validate_run_id(args.run_id)
    stage = BASE.validate_stage_directory(args.run_id)
    BASE.require_stage_path(args.output, stage, "output")
    signing_key = SIGNING_KEY.resolve(strict=True)
    if signing_key != SIGNING_KEY:
        raise RotationCollectorError("signing key path differs from the active identity")
    BASE.validate_root_private_key(signing_key)
    started_at = BASE.iso_time(BASE.utc_now())
    output = BASE.ReservedOutput(
        args.output,
        {
            "schema_version": 1,
            "provider": "openai",
            "status": "in_progress",
            "action": "signing-key-rotation",
            "run_id": args.run_id,
            "started_at": started_at,
            "mutation_receipt_obtained": False,
            "qualification_evidence": False,
            "source": source_binding(),
        },
    )
    journal: dict[str, Any] = {
        "control_plane_mutation_started": False,
        "retirement_confirmed": False,
    }
    policy: dict[str, Any] | None = None
    try:
        policy = load_policy()
        result = collect(
            run_id=args.run_id,
            actor_name=args.actor,
            actor_kind=args.actor_kind,
            attester_name=args.attester,
            policy=policy,
            stage=stage,
            journal=journal,
        )
        output.finish(result)
    except BaseException as error:
        if (
            journal.get("control_plane_mutation_started") is True
            and policy is not None
            and isinstance(journal.get("original_console_reading"), dict)
            and isinstance(journal.get("original_descriptor"), dict)
            and isinstance(journal.get("replacement_descriptor"), dict)
        ):
            try:
                journal["safe_rotation_rollback"] = capture_safe_rotation_rollback(
                    actor_name=args.actor,
                    actor_kind=args.actor_kind,
                    attester_name=args.attester,
                    policy=policy,
                    original_reading=journal["original_console_reading"],
                    original_descriptor=journal["original_descriptor"],
                    replacement_descriptor=journal["replacement_descriptor"],
                    retirement_confirmed=(
                        journal.get("retirement_confirmed") is True
                    ),
                )
            except BaseException as rollback_error:
                journal["safe_rotation_rollback"] = {
                    "status": "rollback_failed",
                    "failure_type": rollback_error.__class__.__name__,
                    "failure_reason": safe_failure_reason(rollback_error),
                    "mutation_receipt_obtained": False,
                }
        rollback_status = journal.get("safe_rotation_rollback", {}).get("status")
        output.finish(
            {
                "schema_version": 1,
                "provider": "openai",
                "status": "failed",
                "action": "signing-key-rotation",
                "run_id": args.run_id,
                "started_at": started_at,
                "failed_at": BASE.iso_time(BASE.utc_now()),
                "failure_type": error.__class__.__name__,
                "failure_reason": safe_failure_reason(error),
                "safe_rotation_rollback_required": (
                    journal.get("control_plane_mutation_started") is True
                    and rollback_status
                    not in {"safe_state_already_present", "safe_state_restored"}
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
        RotationCollectorError,
        ATTESTATION.AttestationShapeError,
        BASE.LifecycleError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        KeyboardInterrupt,
    ) as error:
        print(f"OpenAI signing-key rotation: {safe_failure_reason(error)}", file=sys.stderr)
        raise SystemExit(1)
