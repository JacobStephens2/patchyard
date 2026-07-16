#!/usr/bin/env python3
"""Shared loading, validation, and identity helpers for the factory model."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, deque
from pathlib import Path
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
MODEL_PATH = HERE / "factory-model.json"
SCHEMA_PATH = HERE / "factory-model.schema.json"
IDENTITY_PATH = HERE / "factory-model.sha256"
DECISION_LOG_PATH = HERE / "docs" / "decision-log.md"

SUPPORTED_EDGE_KINDS = {"belt", "exit", "human-gated", "learning"}
RULING_ROW = re.compile(r"^\|\s*([ADR]\d+)\s*\|")


class DuplicateKeyError(ValueError):
    """Raised when a JSON object repeats a key."""


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    """Load strict JSON and reject duplicate object keys."""

    return json.loads(path.read_text(), object_pairs_hook=_reject_duplicate_keys)


def load_model(path: Path = MODEL_PATH) -> dict[str, Any]:
    model = load_json(path)
    if not isinstance(model, dict):
        raise ValueError("factory model root must be a JSON object")
    return model


def canonical_json_bytes(model: dict[str, Any]) -> bytes:
    """Return stable UTF-8 JSON bytes for model identity.

    The model schema permits only ordinary JSON values and finite numbers, so
    sorted keys plus compact separators provide one stable representation for
    the repository's supported data domain.
    """

    encoded = json.dumps(
        model,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return encoded.encode("utf-8")


def model_sha256(model: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(model)).hexdigest()


def _json_path(parts: Iterable[Any]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"
    return result


def schema_errors(
    model: dict[str, Any], schema_path: Path = SCHEMA_PATH
) -> list[str]:
    """Validate the model against its checked-in Draft 7 JSON Schema."""

    try:
        from jsonschema import Draft7Validator, FormatChecker
    except ImportError as exc:  # pragma: no cover - depends on host packaging
        raise RuntimeError(
            "jsonschema is required; install requirements-model.txt"
        ) from exc

    schema = load_json(schema_path)
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(model), key=lambda error: _json_path(error.path))
    return [f"{_json_path(error.path)}: {error.message}" for error in errors]


def _duplicates(values: Iterable[Any]) -> list[Any]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _reachable(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for target in adjacency.get(current, set()):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def load_ruling_ids(path: Path = DECISION_LOG_PATH) -> list[str]:
    """Return ruling identifiers defined by decision-log table rows."""

    return [
        match.group(1)
        for line in path.read_text().splitlines()
        if (match := RULING_ROW.match(line))
    ]


def _ruling_references(value: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "rulings" and isinstance(child, list):
                for index, ruling_id in enumerate(child):
                    if isinstance(ruling_id, str):
                        yield f"{child_path}[{index}]", ruling_id
            else:
                yield from _ruling_references(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _ruling_references(child, f"{path}[{index}]")


def semantic_errors(
    model: dict[str, Any], decision_log_path: Path = DECISION_LOG_PATH
) -> list[str]:
    """Check graph and cross-reference rules JSON Schema cannot express."""

    errors: list[str] = []

    stages = model.get("stages", [])
    entities = model.get("entities", [])
    lanes = model.get("lanes", [])
    phases = model.get("phases", [])
    edges = model.get("edges", [])
    macro_stages = model.get("macroStages", [])
    actor_types = set(model.get("actorTypes", {}))

    ruling_ids = load_ruling_ids(decision_log_path)
    duplicate_rulings = _duplicates(ruling_ids)
    if duplicate_rulings:
        errors.append(f"duplicate ruling id(s) in decision log: {duplicate_rulings}")
    defined_rulings = set(ruling_ids)
    for path, ruling_id in _ruling_references(model):
        if ruling_id not in defined_rulings:
            errors.append(
                f"{path} references ruling {ruling_id!r} absent from "
                f"{decision_log_path.name}"
            )

    stage_ids = [stage.get("id") for stage in stages]
    entity_ids = [entity.get("id") for entity in entities]
    node_ids = stage_ids + entity_ids
    lane_ids = [lane.get("id") for lane in lanes]
    phase_ids = [phase.get("id") for phase in phases]

    for label, values in (
        ("stage id", stage_ids),
        ("entity id", entity_ids),
        ("node id", node_ids),
        ("lane id", lane_ids),
        ("phase id", phase_ids),
        ("macro-stage id", [item.get("id") for item in macro_stages]),
    ):
        duplicates = _duplicates(values)
        if duplicates:
            errors.append(f"duplicate {label}(s): {duplicates}")

    if set(lane_ids) != {"A", "B", "C", "D"}:
        errors.append("lanes must define exactly A, B, C, and D")

    stage_numbers = [stage.get("num") for stage in stages]
    if stage_numbers != list(range(len(stages))):
        errors.append("stage numbers must be ordered and contiguous from 0")
    if phase_ids != list(range(len(phases))):
        errors.append("phase ids must be ordered and contiguous from 0")

    for collection_name, collection in (("stage", stages), ("entity", entities)):
        for item in collection:
            if item.get("actor") not in actor_types:
                errors.append(
                    f"{collection_name} {item.get('id')!r} uses undefined actor "
                    f"{item.get('actor')!r}"
                )

    for stage in stages:
        for lane_id in stage.get("lanes", []):
            if lane_id not in lane_ids:
                errors.append(
                    f"stage {stage.get('id')!r} references undefined lane {lane_id!r}"
                )
        source_ids = [source.get("id") for source in stage.get("sources", [])]
        duplicates = _duplicates(source_ids)
        if duplicates:
            errors.append(
                f"stage {stage.get('id')!r} has duplicate source id(s): {duplicates}"
            )
        for source in stage.get("sources", []):
            if source.get("actor") not in actor_types:
                errors.append(
                    f"source {source.get('id')!r} uses undefined actor "
                    f"{source.get('actor')!r}"
                )

    node_set = set(node_ids)
    actor_by_node = {
        item["id"]: item["actor"] for item in stages + entities if "id" in item
    }
    edge_keys: list[tuple[Any, Any, Any, Any]] = []
    adjacency = {node_id: set() for node_id in node_ids}
    reverse = {node_id: set() for node_id in node_ids}
    for edge in edges:
        source = edge.get("from")
        target = edge.get("to")
        kind = edge.get("kind")
        edge_keys.append((source, target, kind, edge.get("label")))
        if source not in node_set:
            errors.append(f"edge references undefined source node {source!r}")
        if target not in node_set:
            errors.append(f"edge references undefined target node {target!r}")
        if kind not in SUPPORTED_EDGE_KINDS:
            errors.append(f"projector does not support edge kind {kind!r}")
        if source in node_set and target in node_set:
            adjacency[source].add(target)
            reverse[target].add(source)
        if kind == "human-gated" and actor_by_node.get(source) != "human":
            errors.append(
                f"human-gated edge {source!r} -> {target!r} must start at a human node"
            )

    duplicate_edges = _duplicates(edge_keys)
    if duplicate_edges:
        errors.append(f"duplicate edge(s): {duplicate_edges}")

    if "intake" not in node_set:
        errors.append("graph must contain the intake node")
    elif node_set:
        unreachable = sorted(node_set - _reachable("intake", adjacency))
        if unreachable:
            errors.append(f"nodes unreachable from intake: {unreachable}")

    if "ledger" not in node_set:
        errors.append("graph must contain the ledger node")
    elif node_set:
        cannot_close = sorted(node_set - _reachable("ledger", reverse))
        if cannot_close:
            errors.append(f"nodes with no path to ledger: {cannot_close}")

    macro_members: list[str] = []
    for macro in macro_stages:
        for member in macro.get("members", []):
            macro_members.append(member)
            if member not in node_set:
                errors.append(
                    f"macro-stage {macro.get('id')!r} references undefined node {member!r}"
                )
    duplicate_members = _duplicates(macro_members)
    if duplicate_members:
        errors.append(f"nodes repeated across macro-stages: {duplicate_members}")
    missing_stages = sorted(set(stage_ids) - set(macro_members))
    if missing_stages:
        errors.append(f"stages missing from macro-stage grouping: {missing_stages}")

    approval = model.get("approval", {})
    gate_id = approval.get("humanGateStage")
    gate = next((stage for stage in stages if stage.get("id") == gate_id), None)
    if gate is None:
        errors.append(f"approval.humanGateStage references undefined stage {gate_id!r}")
    elif gate.get("actor") != "human" or gate.get("gate") is not True:
        errors.append("approval.humanGateStage must be a human stage with gate=true")

    return errors


def validate_model(
    model: dict[str, Any], schema_path: Path = SCHEMA_PATH,
    decision_log_path: Path = DECISION_LOG_PATH,
) -> list[str]:
    errors = schema_errors(model, schema_path)
    if not errors:
        errors.extend(semantic_errors(model, decision_log_path))
    return errors
