#!/usr/bin/env python3
"""Report the result-rooted transitive closure of repository digest pins."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import sysconfig
from typing import Any
import types


CHECKER_RUNTIME_PATH = Path(__file__).with_name("factory_checker_runtime.py")
CHECKER_RUNTIME_SHA256 = "fcd9d4c5513d8614e20dc4e2fada3da60326ff85745a989b3d4313497b0622f6"
_checker_runtime_source = CHECKER_RUNTIME_PATH.read_bytes()
if (
    CHECKER_RUNTIME_PATH.is_symlink()
    or hashlib.sha256(_checker_runtime_source).hexdigest()
    != CHECKER_RUNTIME_SHA256
):
    raise RuntimeError("factory checker runtime differs from its exact binding")
RUNTIME = types.ModuleType("factory_checker_runtime_check_freeze_graph")
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
SOURCE_ROOTS = ("tools", "worker")
RESULT_ROOT = PurePosixPath("research/isolation/results")
# A133 rules the provider-neutral launcher may contain no provider name, and
# assigns this checker the enforcement. Tokens come from the provider entries
# of the egress policy, so a policy edit extends the ban without a code edit.
# The guest side of the same division: the dispatcher routes by the shape of
# the input drive and the qualification runner validates receipts against a
# projected policy, so neither may name a provider either.
NEUTRAL_ARTIFACTS = (
    "worker/image/patchyard-guest-dispatch",
    "worker/image/patchyard-guest-qualify",
    "worker/runtime/patchyard-provider-run",
)
EGRESS_POLICY = "policy/provider-egress.json"
NEUTRAL_TOKEN_MINIMUM_LENGTH = 3
SHA256 = re.compile(r"[0-9a-fA-F]{64}")
SHA256_TOKEN = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
SUPERSEDES_NAME = "SUPERSEDES_CHECKER_SHA256"
# A144: a Result may bind a collector or checker by a bare digest with no
# path key, so superseding such a file needs its own declaration shape: a
# checker names the replaced file and the exact digests it replaces. Each
# declared digest must be a historical revision of the named file, must not
# be its current digest, and must actually be pinned by a committed Result.
SUPERSEDES_SOURCE_NAME = "SUPERSEDES_SOURCE_SHA256"
STDLIB_MODULES = (
    argparse,
    ast,
    hashlib,
    json,
    os,
    re,
    stat,
    subprocess,
    sysconfig,
)


class FreezeGraphError(RuntimeError):
    """The repository cannot be inspected without ambiguity."""


@dataclass(frozen=True)
class Pin:
    digest: str
    owner: str
    location: str
    target: str | None = None


def pin_sort_key(pin: Pin) -> tuple[str, str, str, str]:
    return (pin.digest, pin.owner, pin.location, pin.target or "")


STRICT_JSON = RUNTIME.strict_json(
    FreezeGraphError,
    constant_template="forbidden JSON numeric constant: {value}",
)
CHECKER = RUNTIME.checker_runtime(
    identity="freeze-graph checker",
    modules=(*STDLIB_MODULES, types),
    repo=REPO,
    json_contract=STRICT_JSON,
)
is_within = RUNTIME.is_within
isolation_errors = CHECKER.isolation_errors
reject_json_constant = STRICT_JSON.reject_json_constant
reject_duplicate_keys = STRICT_JSON.reject_duplicate_keys

def git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_bytes,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise FreezeGraphError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def repository_files(repo: Path) -> list[str]:
    output = git(
        repo,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    )
    names = {os.fsdecode(value) for value in output.split(b"\0") if value}
    return sorted(names)


def read_regular(repo: Path, relative: str) -> bytes:
    path = repo / relative
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise FreezeGraphError(
            f"cannot read repository file {relative}: {error}"
        ) from error
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise FreezeGraphError(f"repository file is not regular: {relative}")
    if not is_within(resolved, repo):
        raise FreezeGraphError(f"repository file escapes its checkout: {relative}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise FreezeGraphError(
            f"cannot read repository file {relative}: {error}"
        ) from error


def load_json(source: bytes, relative: str) -> Any:
    try:
        return json.loads(
            source,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FreezeGraphError(f"invalid JSON in {relative}: {error}") from error


def normalized_digest(value: Any) -> str | None:
    if isinstance(value, bytes):
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError:
            return None
    if isinstance(value, str) and SHA256.fullmatch(value) is not None:
        return value.lower()
    return None


def repository_target(value: Any) -> str | None:
    if not isinstance(value, str) or "\\" in value:
        return None
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or len(candidate.parts) < 2 or ".." in candidate.parts:
        return None
    return candidate.as_posix()


def json_pointer(parts: tuple[str, ...]) -> str:
    encoded = [part.replace("~", "~0").replace("/", "~1") for part in parts]
    return "#/" + "/".join(encoded) if encoded else "#"


def json_pins(
    value: Any,
    owner: str,
    parts: tuple[str, ...] = (),
    *,
    bind_path_keys: bool,
) -> set[Pin]:
    pins: set[Pin] = set()
    digest = normalized_digest(value)
    if digest is not None:
        pins.add(Pin(digest, owner, f"{owner}{json_pointer(parts)}"))
        return pins
    if isinstance(value, dict):
        for key, child in value.items():
            child_parts = (*parts, key)
            pins.update(
                json_pins(
                    child,
                    owner,
                    child_parts,
                    bind_path_keys=bind_path_keys,
                )
            )
            child_digest = normalized_digest(child)
            target = repository_target(key) if bind_path_keys else None
            if child_digest is not None and target is not None:
                pins.add(
                    Pin(
                        child_digest,
                        owner,
                        f"{owner}{json_pointer(child_parts)}",
                        target,
                    )
                )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            pins.update(
                json_pins(
                    child,
                    owner,
                    (*parts, str(index)),
                    bind_path_keys=bind_path_keys,
                )
            )
    return pins


def python_pins(
    source: bytes, owner: str
) -> tuple[set[Pin], set[str], dict[str, set[str]]]:
    try:
        tree = ast.parse(source, filename=owner)
    except (SyntaxError, ValueError) as error:
        raise FreezeGraphError(
            f"cannot parse Python source {owner}: {error}"
        ) from error

    superseded: set[str] = set()
    superseded_sources: dict[str, set[str]] = {}
    excluded_nodes: set[int] = set()
    declarations = 0
    source_declarations = 0
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == SUPERSEDES_NAME
            for target in statement.targets
        ):
            declarations += 1
            try:
                values = ast.literal_eval(statement.value)
            except (ValueError, TypeError, SyntaxError) as error:
                raise FreezeGraphError(
                    f"invalid {SUPERSEDES_NAME} declaration in {owner}"
                ) from error
            if (
                not isinstance(values, tuple)
                or not values
                or any(normalized_digest(value) is None for value in values)
                or len(set(values)) != len(values)
            ):
                raise FreezeGraphError(
                    f"invalid {SUPERSEDES_NAME} declaration in {owner}"
                )
            superseded.update(value.lower() for value in values)
            excluded_nodes.update(id(node) for node in ast.walk(statement.value))
        if any(
            isinstance(target, ast.Name) and target.id == SUPERSEDES_SOURCE_NAME
            for target in statement.targets
        ):
            source_declarations += 1
            try:
                mapping = ast.literal_eval(statement.value)
            except (ValueError, TypeError, SyntaxError) as error:
                raise FreezeGraphError(
                    f"invalid {SUPERSEDES_SOURCE_NAME} declaration in {owner}"
                ) from error
            if (
                not isinstance(mapping, dict)
                or not mapping
                or any(
                    not isinstance(target, str)
                    or repository_target(target) is None
                    or not isinstance(values, tuple)
                    or not values
                    or any(normalized_digest(value) is None for value in values)
                    or len(set(values)) != len(values)
                    for target, values in mapping.items()
                )
            ):
                raise FreezeGraphError(
                    f"invalid {SUPERSEDES_SOURCE_NAME} declaration in {owner}"
                )
            for target, values in mapping.items():
                superseded_sources.setdefault(target, set()).update(
                    value.lower() for value in values
                )
            excluded_nodes.update(id(node) for node in ast.walk(statement.value))
    if declarations > 1:
        raise FreezeGraphError(f"duplicate {SUPERSEDES_NAME} declaration in {owner}")
    if source_declarations > 1:
        raise FreezeGraphError(
            f"duplicate {SUPERSEDES_SOURCE_NAME} declaration in {owner}"
        )

    pins: set[Pin] = set()
    for node in ast.walk(tree):
        if id(node) in excluded_nodes:
            continue
        if isinstance(node, ast.Constant):
            digest = normalized_digest(node.value)
            if digest is not None:
                pins.add(Pin(digest, owner, f"{owner}:{node.lineno}"))
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant) or not isinstance(value, ast.Constant):
                continue
            target = repository_target(key.value)
            digest = normalized_digest(value.value)
            if target is not None and digest is not None:
                pins.add(Pin(digest, owner, f"{owner}:{value.lineno}", target))
    return pins, superseded, superseded_sources


def text_pins(source: bytes, owner: str) -> set[Pin]:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FreezeGraphError(
            f"non-UTF-8 source under tools/ or worker/: {owner}"
        ) from error
    pins: set[Pin] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in SHA256_TOKEN.finditer(line):
            pins.add(Pin(match.group().lower(), owner, f"{owner}:{line_number}"))
    return pins


def source_pins(
    repo: Path, files: list[str]
) -> tuple[
    dict[str, set[Pin]],
    dict[str, set[str]],
    dict[str, dict[str, set[str]]],
]:
    collected: dict[str, set[Pin]] = {}
    supersessions: dict[str, set[str]] = {}
    source_supersessions: dict[str, dict[str, set[str]]] = {}
    for relative in files:
        parts = PurePosixPath(relative).parts
        if not parts or parts[0] not in SOURCE_ROOTS:
            continue
        source = read_regular(repo, relative)
        if relative.endswith(".py"):
            pins, superseded, superseded_sources = python_pins(source, relative)
            if superseded:
                supersessions[relative] = superseded
            if superseded_sources:
                source_supersessions[relative] = superseded_sources
        elif relative.endswith(".json"):
            pins = json_pins(
                load_json(source, relative),
                relative,
                bind_path_keys=True,
            )
        else:
            pins = text_pins(source, relative)
        if pins:
            collected[relative] = pins
    return collected, supersessions, source_supersessions


def checker_result_pins(
    value: Any, owner: str, parts: tuple[str, ...] = ()
) -> set[Pin]:
    pins: set[Pin] = set()
    if isinstance(value, dict):
        checker = value.get("checker")
        digest = normalized_digest(value.get("checker_sha256"))
        if (
            isinstance(checker, str)
            and PurePosixPath(checker).name == checker
            and checker.startswith("check-")
            and checker.endswith(".py")
            and digest is not None
        ):
            pins.add(
                Pin(
                    digest,
                    owner,
                    f"{owner}{json_pointer((*parts, 'checker_sha256'))}",
                    f"tools/{checker}",
                )
            )
        for key, child in value.items():
            pins.update(checker_result_pins(child, owner, (*parts, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            pins.update(checker_result_pins(child, owner, (*parts, str(index))))
    return pins


def result_pins(repo: Path, files: list[str]) -> set[Pin]:
    pins: set[Pin] = set()
    root_parts = RESULT_ROOT.parts
    for relative in files:
        path = PurePosixPath(relative)
        if path.suffix != ".json" or path.parts[: len(root_parts)] != root_parts:
            continue
        if len(path.parts) != len(root_parts) + 1:
            continue
        result = load_json(read_regular(repo, relative), relative)
        generic = json_pins(result, relative, bind_path_keys=False)
        checker_pins = checker_result_pins(result, relative)
        checker_locations = {
            (pin.digest, pin.owner, pin.location) for pin in checker_pins
        }
        pins.update(
            pin
            for pin in generic
            if (pin.digest, pin.owner, pin.location) not in checker_locations
        )
        pins.update(checker_pins)
    return pins


def current_digests(
    repo: Path, files: list[str]
) -> tuple[dict[str, str], dict[str, set[str]]]:
    by_path: dict[str, str] = {}
    by_digest: dict[str, set[str]] = {}
    for relative in files:
        path = repo / relative
        try:
            metadata = path.lstat()
        except OSError:
            continue
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            continue
        source = read_regular(repo, relative)
        digest = hashlib.sha256(source).hexdigest()
        by_path[relative] = digest
        by_digest.setdefault(digest, set()).add(relative)
    return by_path, by_digest


def historical_digest_matches(repo: Path, candidates: set[str]) -> set[str]:
    if not candidates:
        return set()
    object_ids = sorted(
        set(
            git(repo, "rev-list", "--objects", "--no-object-names", "HEAD")
            .decode("ascii")
            .splitlines()
        )
    )
    if not object_ids:
        return set()
    request = ("\n".join(object_ids) + "\n").encode()
    checks = git(
        repo,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype)",
        input_bytes=request,
    )
    blob_ids = [
        line.split()[0]
        for line in checks.decode("ascii").splitlines()
        if line.endswith(" blob")
    ]
    if not blob_ids:
        return set()
    contents = git(
        repo,
        "cat-file",
        "--batch",
        input_bytes=("\n".join(blob_ids) + "\n").encode(),
    )
    matches: set[str] = set()
    offset = 0
    for expected in blob_ids:
        header_end = contents.find(b"\n", offset)
        if header_end < 0:
            raise FreezeGraphError("git cat-file returned a truncated blob header")
        header = contents[offset:header_end].decode("ascii").split()
        if len(header) != 3 or header[0] != expected or header[1] != "blob":
            raise FreezeGraphError("git cat-file returned an unexpected blob header")
        size = int(header[2])
        start = header_end + 1
        end = start + size
        if end >= len(contents) or contents[end : end + 1] != b"\n":
            raise FreezeGraphError("git cat-file returned truncated blob content")
        digest = hashlib.sha256(contents[start:end]).hexdigest()
        if digest in candidates:
            matches.add(digest)
        offset = end + 1
    if offset != len(contents):
        raise FreezeGraphError("git cat-file returned trailing data")
    return matches


def historical_path_digests(repo: Path, relative: str) -> set[str]:
    commits = (
        git(repo, "log", "--format=%H", "HEAD", "--", relative)
        .decode("ascii")
        .splitlines()
    )
    digests: set[str] = set()
    for commit in commits:
        try:
            source = git(repo, "show", f"{commit}:{relative}")
        except FreezeGraphError:
            continue
        digests.add(hashlib.sha256(source).hexdigest())
    return digests


def validated_supersessions(
    repo: Path,
    declarations: dict[str, set[str]],
    results: set[Pin],
    by_path: dict[str, str],
) -> set[tuple[str, str]]:
    result_checker_pins = {
        (pin.digest, pin.target)
        for pin in results
        if pin.target is not None
        and pin.owner.startswith(f"{RESULT_ROOT.as_posix()}/")
    }
    validated: set[tuple[str, str]] = set()
    for path, digests in declarations.items():
        candidate = PurePosixPath(path)
        if (
            candidate.parent != PurePosixPath("tools")
            or not candidate.name.startswith("check-")
            or candidate.suffix != ".py"
        ):
            raise FreezeGraphError(
                f"{SUPERSEDES_NAME} is permitted only in checker files: {path}"
            )
        historical = historical_path_digests(repo, path)
        for digest in digests:
            if by_path.get(path) == digest or digest not in historical:
                raise FreezeGraphError(
                    f"{path} does not replace its declared historical digest: {digest}"
                )
            if (digest, path) not in result_checker_pins:
                raise FreezeGraphError(
                    f"{path} declares an unpinned checker digest: {digest}"
                )
            validated.add((digest, path))
    return validated


def validated_source_supersessions(
    repo: Path,
    declarations: dict[str, dict[str, set[str]]],
    results: set[Pin],
    by_path: dict[str, str],
) -> set[str]:
    result_digests = {
        pin.digest
        for pin in results
        if pin.owner.startswith(f"{RESULT_ROOT.as_posix()}/")
    }
    validated: set[str] = set()
    for path, targets in declarations.items():
        candidate = PurePosixPath(path)
        if (
            candidate.parent != PurePosixPath("tools")
            or not candidate.name.startswith("check-")
            or candidate.suffix != ".py"
        ):
            raise FreezeGraphError(
                f"{SUPERSEDES_SOURCE_NAME} is permitted only in checker files: {path}"
            )
        for target, digests in targets.items():
            historical = historical_path_digests(repo, target)
            for digest in digests:
                if by_path.get(target) == digest or digest not in historical:
                    raise FreezeGraphError(
                        f"{path} does not supersede a historical digest of "
                        f"{target}: {digest}"
                    )
                if digest not in result_digests:
                    raise FreezeGraphError(
                        f"{path} declares an unpinned source digest: {digest}"
                    )
                validated.add(digest)
    return validated


def freeze_closure(
    results: set[Pin],
    sources: dict[str, set[Pin]],
    by_digest: dict[str, set[str]],
) -> tuple[set[str], dict[str, set[str]]]:
    frozen: set[str] = set()
    pinned_by: dict[str, set[str]] = {}
    pending: list[str] = []

    for pin in sorted(results, key=pin_sort_key):
        for target in sorted(by_digest.get(pin.digest, ())):
            pinned_by.setdefault(target, set()).add(pin.owner)
            if target not in frozen:
                frozen.add(target)
                pending.append(target)

    processed: set[str] = set()
    while pending:
        owner = pending.pop()
        if owner in processed:
            continue
        processed.add(owner)
        for pin in sorted(sources.get(owner, ()), key=pin_sort_key):
            targets = by_digest.get(pin.digest, set())
            if pin.target is not None:
                targets = {pin.target} if pin.target in targets else set()
            for target in sorted(targets):
                pinned_by.setdefault(target, set()).add(owner)
                if target not in frozen:
                    frozen.add(target)
                    pending.append(target)
    return frozen, pinned_by


def drift_rows(
    pins: set[Pin],
    by_path: dict[str, str],
    by_digest: dict[str, set[str]],
    historical: set[str],
    superseded: set[tuple[str, str]],
    source_superseded: set[str],
) -> list[dict[str, Any]]:
    drift: dict[str, dict[str, set[str]]] = {}
    for pin in sorted(pins, key=pin_sort_key):
        if (
            pin.target is not None
            and (pin.digest, pin.target) in superseded
            and pin.owner.startswith(f"{RESULT_ROOT.as_posix()}/")
        ):
            continue
        if (
            pin.digest in source_superseded
            and pin.owner.startswith(f"{RESULT_ROOT.as_posix()}/")
        ):
            continue
        expected_path_drift = (
            pin.target is not None and by_path.get(pin.target) != pin.digest
        )
        historical_drift = not by_digest.get(pin.digest) and pin.digest in historical
        if not expected_path_drift and not historical_drift:
            continue
        row = drift.setdefault(
            pin.digest,
            {"locations": set(), "expected_paths": set()},
        )
        row["locations"].add(pin.location)
        if pin.target is not None:
            row["expected_paths"].add(pin.target)
    return [
        {
            "sha256": digest,
            "pin_locations": sorted(values["locations"]),
            "expected_paths": sorted(values["expected_paths"]),
        }
        for digest, values in sorted(drift.items())
    ]


def provider_tokens(repo: Path) -> set[str]:
    policy = load_json(read_regular(repo, EGRESS_POLICY), EGRESS_POLICY)
    providers = policy.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise FreezeGraphError(f"no provider entries in {EGRESS_POLICY}")
    tokens: set[str] = set()
    for key, entry in providers.items():
        if not isinstance(entry, dict):
            raise FreezeGraphError(f"invalid provider entry in {EGRESS_POLICY}: {key}")
        names = [key, entry.get("display_name", "")]
        for name in names:
            if not isinstance(name, str):
                raise FreezeGraphError(
                    f"invalid provider name in {EGRESS_POLICY}: {key}"
                )
            for part in re.split(r"[^a-z0-9]+", name.lower()):
                if len(part) >= NEUTRAL_TOKEN_MINIMUM_LENGTH:
                    tokens.add(part)
        hostnames = entry.get("hostnames", [])
        if not isinstance(hostnames, list):
            raise FreezeGraphError(
                f"invalid provider hostnames in {EGRESS_POLICY}: {key}"
            )
        for hostname in hostnames:
            if not isinstance(hostname, str) or not hostname:
                raise FreezeGraphError(
                    f"invalid provider hostname in {EGRESS_POLICY}: {key}"
                )
            tokens.add(hostname.lower())
    return tokens


def neutrality_rows(
    repo: Path, files: list[str]
) -> tuple[list[str], list[dict[str, str]]]:
    scanned = [artifact for artifact in NEUTRAL_ARTIFACTS if artifact in files]
    if not scanned:
        return [], []
    patterns = {
        token: re.compile(
            r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
        )
        for token in provider_tokens(repo)
    }
    violations: list[dict[str, str]] = []
    for artifact in scanned:
        try:
            text = read_regular(repo, artifact).decode("utf-8")
        except UnicodeDecodeError as error:
            raise FreezeGraphError(
                f"neutral artifact is not UTF-8: {artifact}"
            ) from error
        for line_number, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            for token in sorted(patterns):
                if patterns[token].search(lowered) is not None:
                    violations.append(
                        {
                            "artifact": artifact,
                            "token": token,
                            "location": f"{artifact}:{line_number}",
                        }
                    )
    return scanned, violations


def build_report(repo: Path) -> dict[str, Any]:
    files = repository_files(repo)
    sources, declarations, source_declarations = source_pins(repo, files)
    results = result_pins(repo, files)
    all_pins = set(results)
    for pins in sources.values():
        all_pins.update(pins)
    candidates = {pin.digest for pin in all_pins}
    by_path, by_digest = current_digests(repo, files)
    superseded = validated_supersessions(
        repo, declarations, results, by_path
    )
    source_superseded = validated_source_supersessions(
        repo, source_declarations, results, by_path
    )
    historical = historical_digest_matches(repo, candidates)
    frozen, pinned_by = freeze_closure(results, sources, by_digest)
    drift = drift_rows(
        all_pins, by_path, by_digest, historical, superseded, source_superseded
    )
    frozen_rows = [
        {
            "path": path,
            "sha256": by_path[path],
            "pinned_by": sorted(pinned_by[path]),
        }
        for path in sorted(frozen)
    ]
    neutral_scanned, neutral_violations = neutrality_rows(repo, files)
    return {
        "schema_version": 1,
        "frozen_count": len(frozen_rows),
        "frozen": frozen_rows,
        "drift": drift,
        "neutral": {
            "artifacts": neutral_scanned,
            "violations": neutral_violations,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "report the result-rooted transitive closure of repository digest pins"
        )
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=REPO,
        help="repository checkout to inspect (default: this checkout)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repo = args.repo.resolve(strict=True)
    except OSError as error:
        print(
            f"freeze graph: failed\n  repository is unavailable: {error}",
            file=sys.stderr,
        )
        return 2

    errors = isolation_errors(repo)
    if errors:
        print("freeze graph: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 2
    try:
        report = build_report(repo)
    except (FreezeGraphError, OSError, ValueError) as error:
        print(f"freeze graph: failed\n  {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["drift"] or report["neutral"]["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
