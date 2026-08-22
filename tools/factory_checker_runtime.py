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
    value: Any,
    expected: set[str] | frozenset[str],
    label: str,
    errors: list[str],
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} is not an object")
        return False
    if set(value) != expected:
        errors.append(f"{label} has an unexpected evidence shape")
        return False
    return True


# One structural declaration per qualification requirement. Values are
# whitespace-separated solely to keep this committed input reviewable; callers
# receive immutable sets through ResultShape rather than parsing these strings.
_RESULT_SHAPE_DECLARATIONS = {
    "openai-first-token-exchange": {
        "result": "schema_version provider observation_kind run_id started_at assertion_descriptor exchange_request exchange_response credential_removed_at response_predicate control_plane_provenance provider_response_observed qualification_evidence source",
        "fixture": "fixture_kind fixture_lineage",
        "assertion": "algorithm kid issuer subject audience issued_at minted_at expires_at lifetime_seconds jti_supplied factory_environment jwk_thumbprint_sha256",
        "request": "endpoint content_type grant_type subject_token_type subject_token_supplied identity_provider_id service_account_id scope_supplied requested_at",
        "response": "source http_status request_started_at observed_at provider_date request_id request_id_supplied content_type body_bytes body_format response_shape access_token_supplied token_type expires_in error_type",
        "source": "policy_sha256 base_harness_sha256 issuance_adapter_sha256",
        "field_descriptor": "name name_recorded value_type",
    },
    "openai-expiry-denial": {
        "result": "schema_version provider qualification_requirement authorization_ruling observation_kind run_id started_at assertion_descriptor exchange_request expiry_denial credential_removed_at response_predicate control_plane_provenance provider_response_observed qualification_evidence source",
        "fixture": "fixture_kind fixture_lineage",
        "assertion": "algorithm kid_derived_from_public_der jwk_thumbprint_sha256 issuer subject audience issued_at minted_at expires_at lifetime_seconds expired_before_mint_seconds jti_supplied factory_environment",
        "request": "endpoint content_type grant_type subject_token_type subject_token_supplied identity_provider_id service_account_id scope_supplied attempt_count requested_at",
        "response": "source http_status request_started_at observed_at provider_date request_id request_id_supplied content_type body_bytes body_format response_shape access_token_supplied error_type",
        "source": "policy_sha256 base_harness_sha256 expiry_adapter_sha256",
        "field_descriptor": "name name_recorded value_type",
    },
    "openai-crash-cleanup": {
        "result": "schema_version provider qualification_requirement authorization_ruling run_id checkpoint kill positive_control post_kill_search in_progress_record checker_rejections provider_exposure_boundary response_predicate control_plane_provenance provenance_limitation provider_response_observed qualification_evidence source",
        "fixture": "fixture_kind fixture_lineage",
        "source": "policy_sha256 base_harness_sha256 crash_adapter_sha256",
        "checkpoint": "schema_version provider run_id phase observed_at target_pid target_start_ticks attempt_sha256 source core_dump_limits swap_entries signing_key assertion exchange_request exchange_response material_fingerprints assertion_live bearer_live terminal_record_written",
        "signing_key": "copied_to_run_stage stable_source_preserved private_key_bytes_loaded_by_adapter kid_derived_from_public_der jwk_thumbprint_sha256",
        "assertion": "issued_at minted_at expires_at lifetime_seconds",
        "exchange_request": "endpoint attempt_count requested_at",
        "response": "source http_status request_started_at observed_at provider_date request_id request_id_supplied content_type body_bytes body_format response_shape access_token_supplied expires_in error_type",
        "field_descriptor": "name name_recorded value_type",
        "fingerprint": "material_class sha256 byte_length",
        "search": "schema_version provider run_id event_type observed_at target_process_present search_contract search_contract_sha256 memory_regions_examined unreadable_memory_regions memory_bytes_examined files_examined file_bytes_examined credential_material_found material_classes_found matches swap_entries scanner_core_dump_limits scan_socket_used source",
        "match": "material_class surface location occurrences",
        "kill": "schema_version provider run_id event_type observed_at target_pid target_start_ticks signal_name signal_number child_returncode supervisor_timed_out target_process_present scan_socket_cleanup_required scan_socket_present_after_cleanup attempt_sha256 checkpoint_sha256 positive_control_sha256 source",
    },
    "openai-federation-revocation": {
        "result": "schema_version provider qualification_requirement authorization_rulings observation_kind run_id bounded_window human_authorization model_identity model_actions model_console_observations baseline_control denial_observation bracketing_control response_predicate mutation_receipt_obtained provider_response_observed qualification_evidence source",
        "fixture": "fixture_kind fixture_lineage",
        "window": "started_at ended_at",
        "human_authorization": "source issue_url comment_id comment_url author_login created_at body attempt extracted human_attestation_obtained human_authorship_mechanically_proven",
        "route_authorization": "source ruling map_url grant_url author_login human_attestation_obtained human_authorship_mechanically_proven",
        "extracted": "run_id pairing codex_task_id policy_sha256 collector_sha256 permitted_mutation permitted_restoration deadline_at",
        "model_identity": "pairing codex_task_id",
        "action": "kind action_id intent confirmation",
        "intent": "console_location intended_expression permitted_mutation recorded_at",
        "confirmation": "save_completed observed_expression product_approval_presented product_approval_completed recorded_at capture_sha256",
        "observation": "step capture_method captured_before_at captured_after_at navigation capture_action_id state",
        "navigation": "url reloaded reload_started_at reload_completed_at",
        "forbidden": "attester actor party_relationship mapping_mutation_attestation restoration_attestation initial_console_reading attestation_definition_sha256 independence corroboration",
        "mapping_state": "console_location identity_provider_id mapped_service_account_id uploaded_jwks_mode mapping_present enabled subject_mapping_expression",
        "exchange": "key_role started_at attempt_count lifecycle_instrument_sha256 assertion_descriptor exchange_request receipt credential_removed_at",
        "assertion": "algorithm kid issuer subject audience issued_at minted_at expires_at lifetime_seconds jti_supplied factory_environment jwk_thumbprint_sha256",
        "request": "endpoint content_type grant_type subject_token_type subject_token_supplied identity_provider_id service_account_id scope_supplied requested_at",
        "receipt": "source http_status request_started_at observed_at provider_date request_id request_id_supplied content_type body_bytes body_format response_shape access_token_supplied token_type expires_in error_type",
        "response_shape": "body_kind top_level_fields error_fields",
        "field_descriptor": "name name_recorded value_type",
        "source": "policy_sha256 base_harness_sha256 lifecycle_instrument_sha256 collector_sha256 checker_sha256",
    },
    "openai-signing-key-rotation": {
        "result": "schema_version provider qualification_requirement authorization_rulings observation_kind run_id bounded_window original_console_reading baseline_control derived_public_key_descriptors overlap_attestation overlap_positive_control local_activation retirement_attestation a129_bracket response_predicate mutation_receipt_obtained provider_response_observed qualification_evidence source",
        "fixture": "fixture_kind fixture_lineage",
        "window": "started_at ended_at",
        "reading": "captured_before_at captured_after_at state",
        "rotation_state": "console_location identity_provider_id mapped_service_account_id uploaded_jwks_mode subject_mapping_enabled subject_mapping_expression public_keys",
        "public_key": "kid jwk_thumbprint_sha256 enabled",
        "derived": "original replacement",
        "descriptor": "kid jwk_thumbprint_sha256",
        "exchange": "key_role started_at attempt_count lifecycle_instrument_sha256 assertion_descriptor exchange_request receipt credential_removed_at",
        "assertion": "algorithm kid issuer subject audience issued_at minted_at expires_at lifetime_seconds jti_supplied factory_environment jwk_thumbprint_sha256",
        "request": "endpoint content_type grant_type subject_token_type subject_token_supplied identity_provider_id service_account_id scope_supplied requested_at",
        "receipt": "source http_status request_started_at observed_at provider_date request_id request_id_supplied content_type body_bytes body_format response_shape access_token_supplied token_type expires_in error_type",
        "response_shape": "body_kind top_level_fields error_fields",
        "field_descriptor": "name name_recorded value_type",
        "activation": "active_key_path original_key replacement_key original_key_preserved_in_root_tmpfs observed_at base_harness_sha256 source",
        "bracket": "bounded_subwindow bracketing_control_before_denial denial_observation bracketing_control_after_denial",
        "source": "policy_sha256 base_harness_sha256 lifecycle_instrument_sha256 collector_sha256 checker_sha256 attestation_definition_sha256",
    },
    "anthropic-crash-cleanup": {
        "result": "schema_version provider qualification_requirement authorization_ruling run_id policy_sha256 lifecycle_harness_sha256 crash_harness_sha256 checkpoint kill positive_control post_kill_search in_progress_record checker_rejections provider_exposure_boundary provenance_limitation",
        "contract_metadata": "fixture_kind fixture_lineage provider_response_observed qualification_evidence",
    },
    "anthropic-revocation": {
        "result": "schema_version provider qualification_requirement authorization_ruling run_id policy_sha256 lifecycle_harness_sha256 admin_tool_sha256 revocation_harness_sha256 events",
        "contract_metadata": "fixture_kind provider_response_observed qualification_evidence",
    },
}


class ResultShape:
    """Immutable structural declaration shared by an emitter and its checker."""

    def __init__(self, requirement: str, nodes: dict[str, str]) -> None:
        self._requirement = requirement
        parsed: dict[str, frozenset[str]] = {}
        for name, declaration in nodes.items():
            keys = declaration.split()
            if not keys or len(keys) != len(set(keys)):
                raise RuntimeError(
                    f"Result shape {requirement}/{name} is empty or repeats a key"
                )
            parsed[name] = frozenset(keys)
        self._nodes = parsed

    def keys(self, node: str) -> frozenset[str]:
        try:
            return self._nodes[node]
        except KeyError as error:
            raise KeyError(
                f"unknown Result shape node: {self._requirement}/{node}"
            ) from error

    def emitted(self, value: Any, node: str = "result") -> dict[str, Any]:
        """Fail closed when an emitter's object differs from its declaration."""
        expected = self.keys(node)
        if not isinstance(value, dict):
            raise EvidenceJsonError(
                f"emitted {self._requirement}/{node} is not an object"
            )
        observed = set(value)
        if observed != expected:
            missing = sorted(expected - observed)
            unexpected = sorted(observed - expected)
            raise EvidenceJsonError(
                f"emitted {self._requirement}/{node} differs: "
                f"missing={missing}, unexpected={unexpected}"
            )
        return value

    def fixture_result(
        self, value: Any, metadata_node: str = "fixture"
    ) -> dict[str, Any]:
        """Derive a checker Result from a contract Fixture declaration."""
        if not isinstance(value, dict):
            raise EvidenceJsonError(
                f"fixture for {self._requirement} is not an object"
            )
        result_keys = self.keys("result")
        metadata_keys = self.keys(metadata_node)
        observed = set(value)
        expected = result_keys | metadata_keys
        if observed != expected:
            missing = sorted(expected - observed)
            unexpected = sorted(observed - expected)
            raise EvidenceJsonError(
                f"fixture for {self._requirement} differs: "
                f"missing={missing}, unexpected={unexpected}"
            )
        return self.emitted({key: value[key] for key in result_keys})


def result_shape(requirement: str) -> ResultShape:
    try:
        declaration = _RESULT_SHAPE_DECLARATIONS[requirement]
    except KeyError as error:
        raise KeyError(f"unknown Result shape: {requirement}") from error
    return ResultShape(requirement, declaration)


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
