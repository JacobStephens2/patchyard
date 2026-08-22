#!/usr/bin/env python3
"""Collect one attended OpenAI federation-rule revocation observation.

The collector makes no console request. Under A146 it records a
model-operated run: two Saves, five reloaded console readings, and the
A129 bracket. Remaining runs on this map cite A148's route authorization
as the source and do not require a per-run GitHub comment. Token exchanges
use the one frozen lifecycle instrument loaded by its exact digest.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
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


CHECKER_RUNTIME_PATH = Path(__file__).with_name("factory_checker_runtime.py")
CHECKER_RUNTIME_SHA256 = "db4217cdd58d3dc8343f0ba2a9d1842eb07d6356d6aa430a2e3ff9b0be07e9fe"
_checker_runtime_source = CHECKER_RUNTIME_PATH.read_bytes()
if (
    CHECKER_RUNTIME_PATH.is_symlink()
    or hashlib.sha256(_checker_runtime_source).hexdigest()
    != CHECKER_RUNTIME_SHA256
):
    raise RuntimeError("factory checker runtime differs from its exact binding")
RUNTIME = types.ModuleType("factory_checker_runtime_openai_wif_federation_revocation")
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
POLICY_PATH = ROOT / "policy/openai-wif.json"
IDENTITY_HISTORY_PATH = ROOT / "policy/openai-identity-history.json"
POLICY_SHA256 = "87cf13bb136ed9a365bd14822a14d4808a6ef585ce1c278b926fa173d1152e5f"
BASE_HARNESS_PATH = ROOT / "tools/anthropic-wif-lifecycle.py"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
LIFECYCLE_INSTRUMENT_PATH = ROOT / "tools/openai-wif-issuance.py"
LIFECYCLE_INSTRUMENT_SHA256 = (
    "3547ee7c79226123421027df527183d49a7d887368d0b3c6d234b90eaa6f5f52"
)
CHECKER_PATH = ROOT / "tools/check-openai-wif-federation-revocation.py"
SIGNING_KEY = Path("/etc/patchyard/openai-wif-signing.pem")
STAGING_ROOT = Path("/run/patchyard-openai")
RUN_ID_PATTERN = re.compile(r"openai-revocation-[0-9]{8}-[0-9a-f]{10}")
SERVICE_ACCOUNT_ID_PATTERN = re.compile(r"user-[A-Za-z0-9]{16,48}")
PAIRING_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9.+_-]*/[a-z0-9][a-z0-9.+_-]*/"
    r"[A-Za-z0-9][A-Za-z0-9.+_-]*/[a-z0-9][a-z0-9_+-]*"
)
UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z"
)
HEX64 = re.compile(r"[0-9a-f]{64}")
JWT = re.compile(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
OPENAI_KEY = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
BEARER = re.compile(r"Bearer [A-Za-z0-9._~-]{16,}", re.IGNORECASE)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
SETTLING_FLOOR_SECONDS = 90
AUTHORIZATION_DEADLINE_MINUTES = 45
AUTHORIZATION_ISSUE_URL = (
    "https://github.com/JacobStephens2/patchyard/issues/211"
)
AUTHORIZATION_AUTHOR = "JacobStephens2"
ROUTE_AUTHORIZATION_SOURCE = "route authorization"
ROUTE_AUTHORIZATION_RULING = "A148"
ROUTE_AUTHORIZATION_MAP_URL = (
    "https://github.com/JacobStephens2/patchyard/issues/176"
)
ROUTE_AUTHORIZATION_GRANT_URL = (
    "https://github.com/JacobStephens2/patchyard/issues/253"
)
COMMENT_AUTHORIZATION_RULINGS = ["A129", "A132", "A133", "A136", "A146"]
ROUTE_AUTHORIZATION_RULINGS = ["A129", "A132", "A133", "A136", "A146", "A148"]
CAPTURE_METHOD = "model_console_readback_bounded_by_control_plane_utc"
PERMITTED_MUTATION = "subject-expression Edit to the run-scoped sentinel"
PERMITTED_RESTORATION = "Edit the original expression back"
MAPPING_STATE_KEYS = {
    "identity_provider_id",
    "mapping_present",
    "subject_mapping_expression",
    "mapped_service_account_id",
    "enabled",
    "uploaded_jwks_mode",
    "console_location",
}
HUMAN_AUTHORIZATION_KEYS = {
    "source",
    "issue_url",
    "comment_url",
    "comment_id",
    "created_at",
    "author_login",
    "body",
    "extracted",
    "attempt",
    "human_attestation_obtained",
    "human_authorship_mechanically_proven",
}
ROUTE_AUTHORIZATION_KEYS = {
    "source",
    "ruling",
    "map_url",
    "grant_url",
    "author_login",
    "human_attestation_obtained",
    "human_authorship_mechanically_proven",
}
EXTRACTED_KEYS = {
    "run_id",
    "pairing",
    "codex_task_id",
    "policy_sha256",
    "collector_sha256",
    "permitted_mutation",
    "permitted_restoration",
    "deadline_at",
}
MODEL_IDENTITY_KEYS = {"pairing", "codex_task_id"}
CONFIRMATION_INPUT_KEYS = {
    "product_approval_presented",
    "product_approval_completed",
    "capture_sha256",
    "observed_expression",
}
# A149: the reviewed revocation denial predicate, descended from the A129
# bracket of run openai-revocation-20260819-6bd96462ce. It asserts the wire
# denial only - HTTP 401 with no bearer. Attribution of that denial to the
# subject-expression mutation rides on the bracket and the Attestations, never
# on this predicate.
RESPONSE_PREDICATE = {
    "enforced": True,
    "http_status": 401,
    "access_token_supplied": False,
    "basis": "observed-openai-federation-revocation-response",
}
# A141: the console has no disable affordance, so revocation is a console Edit
# of the subject mapping's claim assertion to this run-scoped sentinel. The
# marker makes crashed-window residue self-describing at the console.
REVOCATION_SENTINEL_MARKER = "-REVOKED-"
OBSERVATION_STEPS = (
    "enabled_mapping_before_baseline",
    "immediate_before_mutation",
    "immediate_after_mutation",
    "before_restoration",
    "after_restoration",
)


def revocation_sentinel(run_id: str) -> str:
    return f"sub=patchyard-control-plane{REVOCATION_SENTINEL_MARKER}{run_id}"


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
BASE = INSTRUMENT.BASE
BASE.STAGING_ROOT = STAGING_ROOT
# A144: the OpenAI tools own their signing-key path, so no surface of the
# loaded base harness may still act on the Anthropic path.
BASE.ACTIVE_SIGNING_KEY = SIGNING_KEY


STRICT_JSON = RUNTIME.strict_json(
    RevocationCollectorError,
    duplicate_template="duplicate console-state key: {key}",
)
reject_json_constant = STRICT_JSON.reject_json_constant
reject_duplicate_keys = STRICT_JSON.reject_duplicate_keys
COLLECTOR_RUNTIME = RUNTIME.openai_collector_runtime(
    load_json_file=BASE.load_json_file,
    policy_path=POLICY_PATH,
    identity_history_path=IDENTITY_HISTORY_PATH,
    service_account_id_pattern=SERVICE_ACCOUNT_ID_PATTERN,
    error_type=RevocationCollectorError,
)
registry_current_service_account_id = COLLECTOR_RUNTIME.registry_current_service_account_id
with_current_service_account = COLLECTOR_RUNTIME.with_current_service_account
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


def bounded_identity_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 128
        and all(character.isprintable() for character in value)
        and "\n" not in value
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
    return with_current_service_account(policy)


def source_binding() -> dict[str, str]:
    return {
        "policy_sha256": BASE.digest_file(POLICY_PATH),
        "base_harness_sha256": BASE.digest_file(BASE_HARNESS_PATH),
        "lifecycle_instrument_sha256": BASE.digest_file(
            LIFECYCLE_INSTRUMENT_PATH
        ),
        "collector_sha256": BASE.digest_file(Path(__file__).resolve()),
        "checker_sha256": BASE.digest_file(CHECKER_PATH),
    }


def validate_run_id(run_id: str) -> None:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise RevocationCollectorError("run ID is malformed")


def parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or UTC_TIMESTAMP.fullmatch(value) is None:
        raise RevocationCollectorError(f"{label} is not a UTC timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise RevocationCollectorError(f"{label} has no timezone")
    return parsed


def extract_single_json_fence(body: str) -> Any:
    openings = list(re.finditer(r"```json[ \t]*\n", body))
    if len(openings) != 1:
        raise RevocationCollectorError(
            "authorization body must contain exactly one fenced JSON object"
        )
    start = openings[0].end()
    end = body.find("\n```", start)
    if end < 0:
        raise RevocationCollectorError("authorization JSON fence is unclosed")
    raw = body[start:end]
    try:
        parsed = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_json_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RevocationCollectorError(
            "authorization fence is not strict JSON"
        ) from error
    if not isinstance(parsed, dict):
        raise RevocationCollectorError("authorization fence is not an object")
    return parsed


def load_authorization(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RevocationCollectorError(
            "authorization file is not a regular non-symlink file"
        )
    try:
        value = json.loads(
            path.read_bytes(),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_json_constant,
        )
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RevocationCollectorError(
            "authorization file is not strict JSON"
        ) from error
    if not isinstance(value, dict):
        raise RevocationCollectorError("authorization file is not an object")
    return value


def is_route_authorization(authorization: dict[str, Any]) -> bool:
    return authorization.get("source") == ROUTE_AUTHORIZATION_SOURCE


def validate_model_identity_shape(model_identity: dict[str, Any]) -> tuple[str, str]:
    if set(model_identity) != MODEL_IDENTITY_KEYS:
        raise RevocationCollectorError("model_identity has an unexpected shape")
    pairing = model_identity.get("pairing")
    task_id = model_identity.get("codex_task_id")
    if not isinstance(pairing, str) or PAIRING_PATTERN.fullmatch(pairing) is None:
        raise RevocationCollectorError("model pairing is not canonical")
    if not bounded_identity_text(task_id):
        raise RevocationCollectorError("model Codex task id is not bounded")
    return pairing, task_id


def validate_route_authorization(
    authorization: dict[str, Any],
    model_identity: dict[str, Any],
) -> None:
    if set(authorization) != ROUTE_AUTHORIZATION_KEYS:
        raise RevocationCollectorError("human_authorization has an unexpected shape")
    if authorization.get("ruling") != ROUTE_AUTHORIZATION_RULING:
        raise RevocationCollectorError("route authorization does not name A148")
    if authorization.get("map_url") != ROUTE_AUTHORIZATION_MAP_URL:
        raise RevocationCollectorError("route authorization does not name the map")
    if authorization.get("grant_url") != ROUTE_AUTHORIZATION_GRANT_URL:
        raise RevocationCollectorError("route authorization does not name the grant")
    if authorization.get("author_login") != AUTHORIZATION_AUTHOR:
        raise RevocationCollectorError("authorization author is not the accountable human")
    if authorization.get("human_attestation_obtained") is not False:
        raise RevocationCollectorError("authorization claims a human attestation")
    if authorization.get("human_authorship_mechanically_proven") is not False:
        raise RevocationCollectorError("authorization claims mechanically proven authorship")
    validate_model_identity_shape(model_identity)
    if credential_shaped(authorization):
        raise RevocationCollectorError("authorization contains credential-shaped material")


def validate_comment_authorization(
    authorization: dict[str, Any],
    run_id: str,
    model_identity: dict[str, Any],
    source: dict[str, str],
) -> None:
    if set(authorization) != HUMAN_AUTHORIZATION_KEYS:
        raise RevocationCollectorError("human_authorization has an unexpected shape")
    if authorization.get("source") != "github_issue_comment":
        raise RevocationCollectorError("authorization source is not a GitHub comment")
    if authorization.get("issue_url") != AUTHORIZATION_ISSUE_URL:
        raise RevocationCollectorError("authorization does not name the requirement-4 ticket")
    comment_id = authorization.get("comment_id")
    if not isinstance(comment_id, int) or isinstance(comment_id, bool) or comment_id <= 0:
        raise RevocationCollectorError("authorization comment id is malformed")
    expected_url = f"{AUTHORIZATION_ISSUE_URL}#issuecomment-{comment_id}"
    if authorization.get("comment_url") != expected_url:
        raise RevocationCollectorError("authorization comment URL does not match its id")
    if authorization.get("author_login") != AUTHORIZATION_AUTHOR:
        raise RevocationCollectorError("authorization author is not the accountable human")
    body = authorization.get("body")
    if not isinstance(body, str) or not 1 <= len(body) <= 16_384:
        raise RevocationCollectorError("authorization body is not bounded")
    extracted = authorization.get("extracted")
    if not isinstance(extracted, dict) or set(extracted) != EXTRACTED_KEYS:
        raise RevocationCollectorError("authorization extracted fields have an unexpected shape")
    fenced = extract_single_json_fence(body)
    if fenced != extracted:
        raise RevocationCollectorError(
            "authorization fence does not match the extracted fields"
        )
    if extracted.get("run_id") != run_id or RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise RevocationCollectorError("authorization run ID does not match this run")
    pairing = extracted.get("pairing")
    task_id = extracted.get("codex_task_id")
    if not isinstance(pairing, str) or PAIRING_PATTERN.fullmatch(pairing) is None:
        raise RevocationCollectorError("authorization pairing is not canonical")
    if not bounded_identity_text(task_id):
        raise RevocationCollectorError("authorization Codex task id is not bounded")
    observed_pairing, observed_task = validate_model_identity_shape(model_identity)
    if observed_pairing != pairing:
        raise RevocationCollectorError("model pairing does not match the authorization")
    if observed_task != task_id:
        raise RevocationCollectorError("model task id does not match the authorization")
    if extracted.get("policy_sha256") != source["policy_sha256"]:
        raise RevocationCollectorError("authorization policy digest differs")
    if extracted.get("collector_sha256") != source["collector_sha256"]:
        raise RevocationCollectorError("authorization collector digest differs")
    if extracted.get("permitted_mutation") != PERMITTED_MUTATION:
        raise RevocationCollectorError("authorization permitted mutation differs")
    if extracted.get("permitted_restoration") != PERMITTED_RESTORATION:
        raise RevocationCollectorError("authorization permitted restoration differs")
    created = parse_utc(authorization.get("created_at"), "authorization created_at")
    deadline = parse_utc(extracted.get("deadline_at"), "authorization deadline")
    if deadline != created + timedelta(minutes=AUTHORIZATION_DEADLINE_MINUTES):
        raise RevocationCollectorError(
            "authorization deadline is not created_at plus 45 minutes"
        )
    if authorization.get("attempt") != 1:
        raise RevocationCollectorError("authorization attempt is not 1")
    if authorization.get("human_attestation_obtained") is not False:
        raise RevocationCollectorError("authorization claims a human attestation")
    if authorization.get("human_authorship_mechanically_proven") is not False:
        raise RevocationCollectorError("authorization claims mechanically proven authorship")
    if credential_shaped(authorization):
        raise RevocationCollectorError("authorization contains credential-shaped material")


def validate_authorization(
    authorization: dict[str, Any],
    run_id: str,
    model_identity: dict[str, Any],
    source: dict[str, str],
) -> None:
    if is_route_authorization(authorization):
        validate_route_authorization(authorization, model_identity)
        return
    validate_comment_authorization(authorization, run_id, model_identity, source)


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


def capture_model_observation(
    step: str,
    label: str,
    policy: dict[str, Any],
    *,
    input_fn: Callable[[str], str] = input,
    clock: Callable[[], datetime] = BASE.utc_now,
) -> dict[str, Any]:
    print(
        f"Reload the live console page, then record {label}.",
        file=sys.stderr,
        flush=True,
    )
    reload_started_at = BASE.iso_time(clock())
    if input_fn("Type 'RELOADED' after reloading the console> ") != "RELOADED":
        raise RevocationCollectorError("console was not reloaded before the reading")
    reload_completed_at = BASE.iso_time(clock())
    reading = capture_console_reading(
        label, policy, input_fn=input_fn, clock=clock
    )
    return {
        "step": step,
        "capture_method": CAPTURE_METHOD,
        "capture_action_id": f"capture-{step}",
        "captured_before_at": reading["captured_before_at"],
        "captured_after_at": reading["captured_after_at"],
        "state": reading["state"],
        "navigation": {
            "url": reading["state"]["console_location"],
            "reloaded": True,
            "reload_started_at": reload_started_at,
            "reload_completed_at": reload_completed_at,
        },
    }


def parse_save_confirmation(raw: str) -> dict[str, Any]:
    if not 1 <= len(raw.encode()) <= 16_384:
        raise RevocationCollectorError("save confirmation is outside the byte limit")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_json_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RevocationCollectorError("save confirmation is not strict JSON") from error
    if not isinstance(value, dict) or set(value) != CONFIRMATION_INPUT_KEYS:
        raise RevocationCollectorError("save confirmation has an unexpected shape")
    for field in ("product_approval_presented", "product_approval_completed"):
        if type(value.get(field)) is not bool:
            raise RevocationCollectorError(f"save confirmation {field} is not boolean")
    if (
        value["product_approval_presented"] is False
        and value["product_approval_completed"] is not False
    ):
        raise RevocationCollectorError(
            "save confirmation completed a product approval that was not presented"
        )
    capture = value.get("capture_sha256")
    if capture is not None and (
        not isinstance(capture, str) or HEX64.fullmatch(capture) is None
    ):
        raise RevocationCollectorError("save confirmation capture digest is malformed")
    if not bounded_console_text(value.get("observed_expression")):
        raise RevocationCollectorError(
            "save confirmation observed expression is not bounded"
        )
    if credential_shaped(value):
        raise RevocationCollectorError(
            "save confirmation contains credential-shaped material"
        )
    return value


def record_save_action(
    kind: str,
    *,
    console_location: str,
    intended_expression: str,
    permitted_mutation: str,
    acknowledgement: str,
    instruction: str,
    input_fn: Callable[[str], str],
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    intent = {
        "recorded_at": BASE.iso_time(clock()),
        "console_location": console_location,
        "intended_expression": intended_expression,
        "permitted_mutation": permitted_mutation,
    }
    print(instruction, file=sys.stderr, flush=True)
    if input_fn(f"Type {acknowledgement!r} after the actor finishes> ") != acknowledgement:
        raise RevocationCollectorError("operator did not acknowledge the console mutation")
    recorded_at = BASE.iso_time(clock())
    confirmation_input = parse_save_confirmation(input_fn("save confirmation JSON> "))
    if confirmation_input["observed_expression"] != intended_expression:
        raise RevocationCollectorError(
            "save confirmation observed expression does not match the intent"
        )
    return {
        "kind": kind,
        "action_id": f"save-{kind}",
        "intent": intent,
        "confirmation": {
            "recorded_at": recorded_at,
            "save_completed": True,
            "product_approval_presented": confirmation_input[
                "product_approval_presented"
            ],
            "product_approval_completed": confirmation_input[
                "product_approval_completed"
            ],
            "capture_sha256": confirmation_input["capture_sha256"],
            "observed_expression": confirmation_input["observed_expression"],
        },
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
    if REVOCATION_SENTINEL_MARKER in state["subject_mapping_expression"]:
        raise RevocationCollectorError(
            "mapping expression carries revocation-sentinel residue"
        )


def require_mutated_mapping(
    before: dict[str, Any], after: dict[str, Any], mutation_kind: str, run_id: str
) -> None:
    if before["identity_provider_id"] != after["identity_provider_id"]:
        raise RevocationCollectorError("mapping mutation changed provider identity")
    if after["uploaded_jwks_mode"] is not True:
        raise RevocationCollectorError("mapping mutation changed uploaded-JWKS mode")
    if mutation_kind != "subject-expression":
        raise RevocationCollectorError(f"unknown mapping mutation: {mutation_kind}")
    valid = (
        after["mapping_present"] is True
        and after["enabled"] is True
        and after["subject_mapping_expression"] == revocation_sentinel(run_id)
        and after["mapped_service_account_id"]
        == before["mapped_service_account_id"]
    )
    if not valid:
        raise RevocationCollectorError("console reading does not show the named mutation")


def exchange_once(
    policy: dict[str, Any], signing_key: Path, run_id: str, key_role: str
) -> dict[str, Any]:
    derived = BASE.jwk_descriptor(BASE.load_public_jwk(signing_key))
    started_at = BASE.iso_time(BASE.utc_now())
    # A145: the collector owns the transitional kid mid-run, so it supplies
    # the expected kid explicitly instead of the instrument's steady-state
    # signing-identity registry authority.
    observation = INSTRUMENT.exchange_observation(
        policy, signing_key, run_id, started_at, expected_kid=derived["kid"]
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


def collect(
    *,
    run_id: str,
    authorization: dict[str, Any],
    model_identity: dict[str, Any],
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
    source = source_binding()
    validate_authorization(authorization, run_id, model_identity, source)
    if mutation_kind != "subject-expression":
        raise RevocationCollectorError(f"unknown mapping mutation: {mutation_kind}")
    window_started_at = BASE.iso_time(clock())
    if not is_route_authorization(authorization):
        created = parse_utc(authorization["created_at"], "authorization created_at")
        window_start = parse_utc(window_started_at, "bounded window start")
        if created >= window_start:
            raise RevocationCollectorError(
                "authorization comment is not before the bounded window"
            )
    observations: dict[str, Any] = {}
    actions: list[dict[str, Any]] = []

    initial = capture_model_observation(
        OBSERVATION_STEPS[0],
        "the enabled mapping before the baseline control",
        policy,
        input_fn=input_fn,
        clock=clock,
    )
    require_active_mapping(initial["state"], policy)
    observations[OBSERVATION_STEPS[0]] = initial
    journal["model_console_observations"] = observations
    baseline = exchanger(policy, SIGNING_KEY, run_id, "active")
    require_positive(baseline, "baseline control")
    journal["baseline_control"] = baseline

    mutation_before = capture_model_observation(
        OBSERVATION_STEPS[1],
        "the immediate mapping state before the control-plane mutation",
        policy,
        input_fn=input_fn,
        clock=clock,
    )
    if state_without_location(mutation_before["state"]) != state_without_location(
        initial["state"]
    ):
        raise RevocationCollectorError("mapping changed between baseline and mutation")
    observations[OBSERVATION_STEPS[1]] = mutation_before
    mutation_after: dict[str, Any] | None = None
    mutation_may_be_active = True
    journal["control_plane_mutation_started"] = True
    sentinel = revocation_sentinel(run_id)
    try:
        edit = record_save_action(
            "subject_expression_edit_save",
            console_location=mutation_before["state"]["console_location"],
            intended_expression=sentinel,
            permitted_mutation=PERMITTED_MUTATION,
            acknowledgement="MUTATION COMPLETE",
            instruction=(
                "Named model must now Edit only the subject mapping's claim "
                f"assertion to {sentinel!r}. Do not change the service account "
                "or uploaded JWK."
            ),
            input_fn=input_fn,
            clock=clock,
        )
        if not is_route_authorization(authorization):
            deadline = parse_utc(
                authorization["extracted"]["deadline_at"], "authorization deadline"
            )
            intent_at = parse_utc(edit["intent"]["recorded_at"], "mutation Save intent")
            if intent_at > deadline:
                raise RevocationCollectorError(
                    "mutation Save intent is after the authorization deadline"
                )
        actions.append(edit)
        journal["model_actions"] = actions
        mutation_after = capture_model_observation(
            OBSERVATION_STEPS[2],
            "the immediate mapping state after the control-plane mutation",
            policy,
            input_fn=input_fn,
            clock=clock,
        )
        require_mutated_mapping(
            mutation_before["state"], mutation_after["state"], mutation_kind, run_id
        )
        if (
            mutation_after["state"]["subject_mapping_expression"]
            != edit["confirmation"]["observed_expression"]
        ):
            raise RevocationCollectorError(
                "post-mutation reading does not match the Save confirmation"
            )
        observations[OBSERVATION_STEPS[2]] = mutation_after

        mutation_completed = datetime.fromisoformat(
            mutation_after["captured_after_at"].replace("Z", "+00:00")
        )
        wait_settling_floor(mutation_completed, clock=clock, sleeper=sleeper)
        denial = exchanger(policy, SIGNING_KEY, run_id, "active")
        journal["denial_observation"] = denial
    finally:
        if mutation_may_be_active:
            restoration_before = capture_model_observation(
                OBSERVATION_STEPS[3],
                "the current mapping before safe restoration",
                policy,
                input_fn=input_fn,
                clock=clock,
            )
            observations[OBSERVATION_STEPS[3]] = restoration_before
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
                restore = record_save_action(
                    "subject_expression_restore_save",
                    console_location=restoration_before["state"]["console_location"],
                    intended_expression=initial["state"]["subject_mapping_expression"],
                    permitted_mutation=PERMITTED_RESTORATION,
                    acknowledgement="RESTORATION COMPLETE",
                    instruction=(
                        "Named model must now restore the exact original subject "
                        "mapping. This restoration is required even when an earlier "
                        "step failed."
                    ),
                    input_fn=input_fn,
                    clock=clock,
                )
                actions.append(restore)
                journal["model_actions"] = actions
                restoration_after = capture_model_observation(
                    OBSERVATION_STEPS[4],
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
                if (
                    restoration_after["state"]["subject_mapping_expression"]
                    != restore["confirmation"]["observed_expression"]
                ):
                    raise RevocationCollectorError(
                        "post-restoration reading does not match the Save confirmation"
                    )
                observations[OBSERVATION_STEPS[4]] = restoration_after
                mutation_may_be_active = False
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
        "authorization_rulings": (
            ROUTE_AUTHORIZATION_RULINGS
            if is_route_authorization(authorization)
            else COMMENT_AUTHORIZATION_RULINGS
        ),
        "observation_kind": "federation-rule-revocation",
        "run_id": run_id,
        "bounded_window": {
            "started_at": window_started_at,
            "ended_at": window_ended_at,
        },
        "human_authorization": authorization,
        "model_identity": model_identity,
        "model_actions": actions,
        "model_console_observations": [
            observations[step] for step in OBSERVATION_STEPS
        ],
        "baseline_control": baseline,
        "denial_observation": denial,
        "bracketing_control": bracket,
        "response_predicate": RESPONSE_PREDICATE,
        "mutation_receipt_obtained": False,
        "provider_response_observed": True,
        "qualification_evidence": True,
        "source": source,
    }


def safe_failure_reason(error: BaseException) -> str:
    reason = re.sub(r"[^A-Za-z0-9 ._:/?=+,'()\[\]-]", "?", str(error))[:512]
    if credential_shaped(reason):
        return "credential-bearing diagnostic suppressed"
    return reason or error.__class__.__name__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--authorization-file", required=True, type=Path)
    parser.add_argument("--model-pairing", required=True)
    parser.add_argument("--codex-task-id", required=True)
    parser.add_argument(
        "--mapping-mutation", required=True, choices=["subject-expression"]
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
            authorization=load_authorization(args.authorization_file),
            model_identity={
                "pairing": args.model_pairing,
                "codex_task_id": args.codex_task_id,
            },
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
        BASE.LifecycleError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        KeyboardInterrupt,
    ) as error:
        print(f"OpenAI federation-rule revocation: {safe_failure_reason(error)}", file=sys.stderr)
        raise SystemExit(1)
