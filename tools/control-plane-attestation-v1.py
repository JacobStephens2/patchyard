#!/usr/bin/env python3
"""A132 control-plane Attestation shape, version 1.

Consumers load this source only after checking its exact SHA-256 digest.  The
state inside each console reading remains requirement-specific; this file
defines the shared Attestation envelope and A136 party disclosure once.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any


CAPTURE_METHOD = "operator_console_readback_bounded_by_control_plane_utc"
HEX64 = re.compile(r"[0-9a-f]{64}")
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .,'()+_/-]{0,127}")
UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?Z"
)
ATTESTATION_KEYS = {
    "schema_version",
    "actor",
    "attester",
    "party_relationship",
    "capture_method",
    "console_readings",
    "mutation_description",
    "lifecycle_instrument_sha256",
    "mutation_receipt_obtained",
}
PARTY_KEYS = {"name", "kind"}
RELATIONSHIP_KEYS = {"same_party", "independence", "corroboration"}
READINGS_KEYS = {"before", "after"}
READING_KEYS = {"captured_before_at", "captured_after_at", "state"}


class AttestationShapeError(ValueError):
    """An Attestation is incomplete or overclaims its party relationship."""


def _parse_time(value: Any, label: str, errors: list[str]) -> datetime | None:
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


def _exact_keys(
    value: Any, expected: set[str], label: str, errors: list[str]
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} is not an object")
        return False
    if set(value) != expected:
        errors.append(f"{label} has an unexpected Attestation shape")
        return False
    return True


def party_relationship(actor: dict[str, str], attester: dict[str, str]) -> dict[str, bool]:
    same_party = (
        actor["kind"] == "accountable_human"
        and actor["name"] == attester["name"]
    )
    return {
        "same_party": same_party,
        # Distinct names alone do not establish either claim. A136 requires
        # the one-human case to state both negatives explicitly.
        "independence": False,
        "corroboration": False,
    }


def validate_party_names(
    actor_name: Any,
    actor_kind: Any,
    attester_name: Any,
    attester_kind: Any = "accountable_human",
) -> list[str]:
    errors: list[str] = []
    if actor_kind not in {"accountable_human", "model"}:
        errors.append("Attestation actor kind differs")
    if not isinstance(actor_name, str) or SAFE_NAME.fullmatch(actor_name) is None:
        errors.append("Attestation actor name is not safely bounded")
    if attester_kind != "accountable_human":
        errors.append("Attestation attester is not an accountable human")
    if not isinstance(attester_name, str) or SAFE_NAME.fullmatch(attester_name) is None:
        errors.append("Attestation attester name is not safely bounded")
    return errors


def make_attestation(
    *,
    actor_name: str,
    actor_kind: str,
    attester_name: str,
    before_reading: dict[str, Any],
    after_reading: dict[str, Any],
    mutation_description: str,
    lifecycle_instrument_sha256: str,
) -> dict[str, Any]:
    actor = {"name": actor_name, "kind": actor_kind}
    attester = {"name": attester_name, "kind": "accountable_human"}
    value = {
        "schema_version": 1,
        "actor": actor,
        "attester": attester,
        "party_relationship": party_relationship(actor, attester),
        "capture_method": CAPTURE_METHOD,
        "console_readings": {
            "before": before_reading,
            "after": after_reading,
        },
        "mutation_description": mutation_description,
        "lifecycle_instrument_sha256": lifecycle_instrument_sha256,
        "mutation_receipt_obtained": False,
    }
    errors = validate_attestation(value, lifecycle_instrument_sha256)
    if errors:
        raise AttestationShapeError("; ".join(errors))
    return value


def validate_attestation(
    value: Any, expected_instrument_sha256: str
) -> list[str]:
    errors: list[str] = []
    if not _exact_keys(value, ATTESTATION_KEYS, "Attestation", errors):
        return errors
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
    ):
        errors.append("Attestation schema version differs")

    actor = value.get("actor")
    attester = value.get("attester")
    actor_valid = _exact_keys(actor, PARTY_KEYS, "Attestation actor", errors)
    attester_valid = _exact_keys(
        attester, PARTY_KEYS, "Attestation attester", errors
    )
    if actor_valid:
        if actor.get("kind") not in {"accountable_human", "model"}:
            errors.append("Attestation actor kind differs")
        if not isinstance(actor.get("name"), str) or SAFE_NAME.fullmatch(
            actor["name"]
        ) is None:
            errors.append("Attestation actor name is not safely bounded")
    if attester_valid:
        if attester.get("kind") != "accountable_human":
            errors.append("Attestation attester is not an accountable human")
        if not isinstance(attester.get("name"), str) or SAFE_NAME.fullmatch(
            attester["name"]
        ) is None:
            errors.append("Attestation attester name is not safely bounded")

    relationship = value.get("party_relationship")
    if _exact_keys(
        relationship, RELATIONSHIP_KEYS, "Attestation party relationship", errors
    ):
        if any(type(relationship.get(field)) is not bool for field in RELATIONSHIP_KEYS):
            errors.append("Attestation party relationship is not boolean")
        if actor_valid and attester_valid:
            expected = party_relationship(actor, attester)
            if any(
                relationship.get(field) is not expected[field]
                for field in RELATIONSHIP_KEYS
            ):
                errors.append(
                    "Attestation party relationship does not disclose role occupancy"
                )
        if relationship.get("same_party") is True and (
            relationship.get("independence") is not False
            or relationship.get("corroboration") is not False
        ):
            errors.append(
                "one-person Attestation must disclaim independence and corroboration"
            )

    if value.get("capture_method") != CAPTURE_METHOD:
        errors.append("Attestation capture method differs")
    readings = value.get("console_readings")
    parsed: list[datetime | None] = []
    if _exact_keys(readings, READINGS_KEYS, "Attestation console readings", errors):
        for position in ("before", "after"):
            reading = readings.get(position)
            if not _exact_keys(
                reading, READING_KEYS, f"Attestation {position} console reading", errors
            ):
                parsed.extend((None, None))
                continue
            if not isinstance(reading.get("state"), dict):
                errors.append(f"Attestation {position} console state is not an object")
            parsed.extend(
                (
                    _parse_time(
                        reading.get("captured_before_at"),
                        f"Attestation {position} captured_before_at",
                        errors,
                    ),
                    _parse_time(
                        reading.get("captured_after_at"),
                        f"Attestation {position} captured_after_at",
                        errors,
                    ),
                )
            )
    if len(parsed) == 4 and all(item is not None for item in parsed):
        ordered = [item for item in parsed if item is not None]
        if not all(left <= right for left, right in zip(ordered, ordered[1:])):
            errors.append("Attestation console-reading UTC bounds are out of order")

    description = value.get("mutation_description")
    if (
        not isinstance(description, str)
        or not 1 <= len(description) <= 1024
        or any(character in description for character in "\r\n\0")
    ):
        errors.append("Attestation mutation description is not exactly bounded")
    instrument = value.get("lifecycle_instrument_sha256")
    if (
        not isinstance(instrument, str)
        or HEX64.fullmatch(instrument) is None
        or instrument != expected_instrument_sha256
    ):
        errors.append("Attestation lifecycle instrument digest differs")
    if value.get("mutation_receipt_obtained") is not False:
        errors.append("Attestation provenance mark differs")
    return errors
