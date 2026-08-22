#!/usr/bin/env python3
"""Enforce A113's per-provider credential-qualification conditional."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import sysconfig
from typing import Any
import hashlib
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
RUNTIME = types.ModuleType("factory_checker_runtime_check_credential_qualification")
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
DEFAULT_POLICY = REPO / "policy/provider-egress.json"
RESULT_ROOT = PurePosixPath("research/isolation/results")
MAX_POLICY_BYTES = 1_000_000
REQUIREMENT_NAMES = {
    1: "issuance and delivery",
    2: "provider-side spend enforcement",
    3: "credential expiry denial",
    4: "federation-rule revocation",
    5: "signing-key rotation",
    6: "crash cleanup",
}


@dataclass(frozen=True)
class ResultBinding:
    requirements: tuple[int, ...]
    result: str
    checker: str
    qualification_requirement: str


# A131 has six Requirements but five Results because Requirements 4 and 5 share
# the revocation-and-rotation Result. Subprocess replay deliberately delegates
# evidence semantics to each Result's checker instead of reproducing them here.
PROVIDER_RESULTS = {
    "anthropic": (
        ResultBinding(
            (1,),
            "research/isolation/results/anthropic-issuance-delivery.json",
            "tools/check-anthropic-issuance.py",
            "issuance-delivery",
        ),
        ResultBinding(
            (2,),
            "research/isolation/results/anthropic-spend-enforcement.json",
            "tools/check-anthropic-spend.py",
            "provider-spend-enforcement",
        ),
        ResultBinding(
            (3,),
            "research/isolation/results/anthropic-expiry-denial.json",
            "tools/check-anthropic-expiry.py",
            "credential-expiry-denial",
        ),
        ResultBinding(
            (4, 5),
            "research/isolation/results/anthropic-revocation-rotation.json",
            "tools/check-anthropic-revocation.py",
            "federation-revocation-and-key-rotation",
        ),
        ResultBinding(
            (6,),
            "research/isolation/results/anthropic-crash-cleanup.json",
            "tools/check-anthropic-crash-cleanup.py",
            "crash-cleanup-local-non-recoverability",
        ),
    ),
}


class StrictJsonError(ValueError):
    """JSON input is ambiguous or outside the strict contract."""


STRICT_JSON = RUNTIME.strict_json(StrictJsonError)
CHECKER = RUNTIME.checker_runtime(
    identity="credential qualification checker",
    modules=(argparse, json, subprocess, sysconfig, types),
    repo=REPO,
    json_contract=STRICT_JSON,
)
reject_json_constant = STRICT_JSON.reject_json_constant
reject_duplicate_keys = STRICT_JSON.reject_duplicate_keys
is_within = RUNTIME.is_within
isolation_errors = CHECKER.isolation_errors

def load_json(path: Path) -> Any:
    if not path.is_file() or path.is_symlink():
        raise StrictJsonError("input is not a regular non-symlink file")
    if not 1 <= path.stat().st_size <= MAX_POLICY_BYTES:
        raise StrictJsonError("input is outside the byte limit")
    return json.loads(
        path.read_bytes(),
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_json_constant,
    )


def tracked_unchanged_result(relative: str) -> str | None:
    tracked = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--error-unmatch", "--", relative],
        check=False,
        capture_output=True,
        text=True,
    )
    if tracked.returncode != 0:
        return "is not a committed Result"
    unchanged = subprocess.run(
        ["git", "-C", str(REPO), "diff", "--quiet", "HEAD", "--", relative],
        check=False,
    )
    if unchanged.returncode != 0:
        return "differs from the committed Result"
    return None


def validate_binding(provider: str, binding: ResultBinding) -> list[str]:
    errors: list[str] = []
    result_relative = PurePosixPath(binding.result)
    checker_relative = PurePosixPath(binding.checker)
    if (
        result_relative.parts[: len(RESULT_ROOT.parts)] != RESULT_ROOT.parts
        or len(result_relative.parts) != len(RESULT_ROOT.parts) + 1
        or result_relative.suffix != ".json"
        or ".." in result_relative.parts
    ):
        return [f"{provider}: Result binding escapes the committed Result root"]
    if (
        len(checker_relative.parts) != 2
        or checker_relative.parts[0] != "tools"
        or not checker_relative.name.startswith("check-")
        or checker_relative.suffix != ".py"
    ):
        return [f"{provider}: checker binding is not a repository checker"]

    committed_error = tracked_unchanged_result(binding.result)
    if committed_error is not None:
        errors.append(f"{provider}: {binding.result} {committed_error}")
        return errors
    try:
        result = load_json(REPO / binding.result)
    except (OSError, json.JSONDecodeError, StrictJsonError) as error:
        errors.append(f"{provider}: cannot read {binding.result}: {error}")
        return errors
    if not isinstance(result, dict):
        errors.append(f"{provider}: {binding.result} is not a Result object")
        return errors
    if result.get("provider") != provider:
        errors.append(f"{provider}: {binding.result} names a different provider")
    if result.get("qualification_requirement") != binding.qualification_requirement:
        errors.append(
            f"{provider}: {binding.result} names a different Requirement"
        )

    checker = REPO / binding.checker
    if not checker.is_file() or checker.is_symlink():
        errors.append(f"{provider}: checker is unavailable: {binding.checker}")
        return errors
    try:
        completed = subprocess.run(
            ["python3", "-I", str(checker)],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        errors.append(f"{provider}: checker timed out: {binding.checker}")
        return errors
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        errors.append(
            f"{provider}: Result did not pass {binding.checker}{suffix}"
        )
    return errors


def validate_provider(provider: str) -> tuple[list[str], list[str]]:
    bindings = PROVIDER_RESULTS.get(provider)
    if bindings is None:
        return [f"{provider}: no complete A131 Result mapping is committed"], []
    covered = [requirement for binding in bindings for requirement in binding.requirements]
    if sorted(covered) != list(REQUIREMENT_NAMES):
        return [f"{provider}: Result mapping does not cover Requirements 1 through 6"], []

    errors: list[str] = []
    details: list[str] = []
    for binding in bindings:
        errors.extend(validate_binding(provider, binding))
        names = ", ".join(
            f"{number} ({REQUIREMENT_NAMES[number]})"
            for number in binding.requirements
        )
        details.append(f"Requirements {names}: {binding.result} via {binding.checker}")
    return errors, details


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="enforce per-provider A113 credential qualification"
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY,
        help="provider-egress policy or a checker Fixture",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = isolation_errors()
    qualified_details: dict[str, list[str]] = {}
    try:
        policy = load_json(args.policy)
    except (OSError, json.JSONDecodeError, StrictJsonError) as error:
        errors.append(f"cannot read provider policy: {error}")
        policy = None
    providers = policy.get("providers") if isinstance(policy, dict) else None
    if not isinstance(providers, dict) or not providers:
        errors.append("provider policy has no provider roster")
    else:
        for provider, entry in providers.items():
            if not isinstance(entry, dict) or type(entry.get("credential_qualified")) is not bool:
                errors.append(f"{provider}: credential_qualified is not boolean")
                continue
            if entry["credential_qualified"]:
                provider_errors, details = validate_provider(provider)
                errors.extend(provider_errors)
                qualified_details[provider] = details

    if errors:
        print("Credential qualification check: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    print("Credential qualification check: pass")
    for provider, details in qualified_details.items():
        print(
            f"  {provider}: qualified; six Requirements proven by five committed Results"
        )
        for detail in details:
            print(f"    {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
