#!/usr/bin/env python3
"""Shared, digest-loaded runtime for factory qualification tooling.

The callers execute this source into a synthetic module after checking its
exact digest.  Keeping the runtime off ``sys.path`` preserves A101's isolated
execution contract while giving repeated validation behaviour one owner.
"""

from __future__ import annotations

import datetime as datetime_module
import hashlib
import json
import pathlib
from pathlib import Path
import sys
import sysconfig
from typing import Any, Callable, Pattern


DEFAULT_SECRET_NAMES = frozenset(
    {
        "access_token",
        "api_key",
        "assertion",
        "authorization",
        "identity_token",
        "private_key",
        "secret",
        "subject_token",
    }
)
RUNTIME_STDLIB_MODULES = (datetime_module, hashlib, json, pathlib, sysconfig)


class EvidenceJsonError(ValueError):
    """Evidence JSON is ambiguous or outside the strict data contract."""


class StrictJson:
    """Strict JSON callbacks and loaders with a caller-selected error type."""

    def __init__(
        self,
        error_type: type[Exception] = EvidenceJsonError,
        *,
        duplicate_template: str = "duplicate JSON key: {key}",
        constant_template: str = "forbidden numeric constant: {value}",
    ) -> None:
        self._error_type = error_type
        self._duplicate_template = duplicate_template
        self._constant_template = constant_template

    @property
    def error_type(self) -> type[Exception]:
        return self._error_type

    def reject_json_constant(self, value: str) -> None:
        raise self._error_type(self._constant_template.format(value=value))

    def reject_duplicate_keys(
        self, pairs: list[tuple[str, Any]]
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise self._error_type(self._duplicate_template.format(key=key))
            result[key] = value
        return result

    def loads(self, value: str | bytes | bytearray) -> Any:
        return json.loads(
            value,
            object_pairs_hook=self.reject_duplicate_keys,
            parse_constant=self.reject_json_constant,
        )

    def load_file(self, path: Path) -> Any:
        return self.loads(path.read_bytes())


def strict_json(
    error_type: type[Exception] = EvidenceJsonError,
    *,
    duplicate_template: str = "duplicate JSON key: {key}",
    constant_template: str = "forbidden numeric constant: {value}",
) -> StrictJson:
    return StrictJson(
        error_type,
        duplicate_template=duplicate_template,
        constant_template=constant_template,
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def exact_keys(
    value: Any, expected: set[str], label: str, errors: list[str]
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} is not an object")
        return False
    if set(value) != expected:
        errors.append(f"{label} has an unexpected evidence shape")
        return False
    return True


def parse_time(value: Any) -> datetime_module.datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime_module.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed


def secret_named_key(
    value: Any, secret_names: frozenset[str] = DEFAULT_SECRET_NAMES
) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in secret_names:
                return key
            found = secret_named_key(child, secret_names)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = secret_named_key(child, secret_names)
            if found is not None:
                return found
    return None


class CheckerRuntime:
    """Configured validation behaviour shared by one isolated caller."""

    def __init__(
        self,
        *,
        identity: str,
        modules: tuple[Any, ...],
        repo: Path,
        timestamp_pattern: Pattern[str] | None = None,
        secret_names: frozenset[str] = DEFAULT_SECRET_NAMES,
        identity_history_path: Path | None = None,
        issuance_era_service_account_id: str | None = None,
        project_id: str | None = None,
        json_contract: StrictJson | None = None,
    ) -> None:
        self._identity = identity
        self._modules = modules
        self._repo = repo
        self._timestamp_pattern = timestamp_pattern
        self._secret_names = secret_names
        self._identity_history_path = identity_history_path
        self._issuance_era_service_account_id = issuance_era_service_account_id
        self._project_id = project_id
        self._json = json_contract or strict_json()

    @property
    def json_error_type(self) -> type[Exception]:
        return self._json.error_type

    def load_json_file(self, path: Path) -> Any:
        return self._json.load_file(path)

    def reject_json_constant(self, value: str) -> None:
        self._json.reject_json_constant(value)

    def reject_duplicate_keys(
        self, pairs: list[tuple[str, Any]]
    ) -> dict[str, Any]:
        return self._json.reject_duplicate_keys(pairs)

    def isolation_errors(self, repo: Path | None = None) -> list[str]:
        errors: list[str] = []
        if not sys.flags.isolated:
            errors.append(f"{self._identity} requires python3 -I")

        stdlib = Path(sysconfig.get_path("stdlib")).resolve()
        modules = {module.__name__: module for module in RUNTIME_STDLIB_MODULES}
        modules.update({module.__name__: module for module in self._modules})
        for module in modules.values():
            source = getattr(module, "__file__", None)
            if source is None or not is_within(Path(source).resolve(), stdlib):
                errors.append(
                    f"{self._identity} rejected {module.__name__} provenance: "
                    f"{source!r}"
                )

        repository = (repo or self._repo).resolve()
        for entry in sys.path:
            try:
                resolved = Path(entry).resolve()
            except OSError:
                continue
            if is_within(resolved, repository):
                errors.append(
                    f"{self._identity} has repository import path: {entry}"
                )
        return errors

    def parse_time(
        self, value: Any, label: str, errors: list[str]
    ) -> datetime_module.datetime | None:
        if (
            not isinstance(value, str)
            or self._timestamp_pattern is None
            or self._timestamp_pattern.fullmatch(value) is None
        ):
            errors.append(f"{label} is not a UTC timestamp")
            return None
        try:
            parsed = datetime_module.datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except ValueError:
            errors.append(f"{label} is malformed")
            return None
        if parsed.tzinfo is None:
            errors.append(f"{label} has no timezone")
            return None
        return parsed

    def secret_named_key(self, value: Any) -> str | None:
        return secret_named_key(value, self._secret_names)

    def roster_service_account_ids(self, errors: list[str]) -> frozenset[str]:
        if (
            self._identity_history_path is None
            or self._issuance_era_service_account_id is None
        ):
            raise RuntimeError("OpenAI identity roster is not configured")
        try:
            registry = self.load_json_file(self._identity_history_path)
            identifiers = frozenset(
                entry["id"] for entry in registry["service_accounts"]
            )
            current = registry["current_service_account_id"]
            project = registry.get("project_id")
        except (
            OSError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
            self._json.error_type,
        ) as error:
            errors.append(f"cannot read the OpenAI identity registry: {error}")
            return frozenset()
        if self._project_id is not None and project != self._project_id:
            errors.append("OpenAI identity registry names another project")
        if current not in identifiers:
            errors.append("OpenAI identity registry current id is not in its roster")
        if self._issuance_era_service_account_id not in identifiers:
            errors.append("OpenAI identity registry lacks the issuance-era id")
        return identifiers


def checker_runtime(**configuration: Any) -> CheckerRuntime:
    return CheckerRuntime(**configuration)


class OpenAICollectorRuntime:
    """Steady-state OpenAI service-account resolution for live collectors."""

    def __init__(
        self,
        *,
        load_json_file: Callable[[Path], Any],
        policy_path: Path,
        identity_history_path: Path,
        service_account_id_pattern: Pattern[str],
        error_type: type[Exception],
    ) -> None:
        self._load_json_file = load_json_file
        self._policy_path = policy_path
        self._identity_history_path = identity_history_path
        self._service_account_id_pattern = service_account_id_pattern
        self._error_type = error_type

    def registry_current_service_account_id(self) -> str:
        """Resolve A150's current id while retaining the frozen policy cross-check."""
        frozen = self._load_json_file(self._policy_path)
        registry = self._load_json_file(self._identity_history_path)
        try:
            project = registry["project_id"]
            current = registry["current_service_account_id"]
            roster = registry["service_accounts"]
            identifiers = [entry["id"] for entry in roster]
            marked_current = [
                entry["id"] for entry in roster if entry["status"] == "current"
            ]
            frozen_project = frozen["project"]["id"]
            frozen_account = frozen["service_account"]["id"]
        except (KeyError, TypeError) as error:
            raise self._error_type("OpenAI identity registry is malformed") from error
        if project != frozen_project:
            raise self._error_type("OpenAI identity registry names another project")
        if not isinstance(current, str) or (
            self._service_account_id_pattern.fullmatch(current) is None
        ):
            raise self._error_type("OpenAI identity registry current id is malformed")
        if len(identifiers) != len(set(identifiers)):
            raise self._error_type("OpenAI identity registry repeats an id")
        if marked_current != [current]:
            raise self._error_type(
                "OpenAI identity registry has no single current entry"
            )
        if frozen_account not in identifiers:
            raise self._error_type("OpenAI identity registry lacks the frozen policy id")
        return current

    def with_current_service_account(self, policy: dict[str, Any]) -> dict[str, Any]:
        current = self.registry_current_service_account_id()
        policy = dict(policy)
        policy["service_account"] = dict(policy["service_account"], id=current)
        if isinstance(policy.get("rule"), dict):
            policy["rule"] = dict(policy["rule"], service_account_id=current)
        return policy


def openai_collector_runtime(**configuration: Any) -> OpenAICollectorRuntime:
    return OpenAICollectorRuntime(**configuration)
