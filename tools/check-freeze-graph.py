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


REPO = Path(__file__).resolve().parent.parent
SOURCE_ROOTS = ("tools", "worker")
RESULT_ROOT = PurePosixPath("research/isolation/results")
SHA256 = re.compile(r"[0-9a-fA-F]{64}")
SHA256_TOKEN = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
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


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def isolation_errors(repo: Path) -> list[str]:
    errors: list[str] = []
    if not sys.flags.isolated:
        errors.append("freeze-graph checker requires python3 -I")

    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    for module in STDLIB_MODULES:
        source = getattr(module, "__file__", None)
        if source is None or not is_within(Path(source).resolve(), stdlib):
            errors.append(
                "freeze-graph checker rejected "
                f"{module.__name__} provenance: {source!r}"
            )

    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except OSError:
            continue
        if is_within(resolved, repo):
            errors.append(f"freeze-graph checker has repository import path: {entry}")
    return errors


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


def reject_json_constant(value: str) -> None:
    raise FreezeGraphError(f"forbidden JSON numeric constant: {value}")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FreezeGraphError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


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


def python_pins(source: bytes, owner: str) -> set[Pin]:
    try:
        tree = ast.parse(source, filename=owner)
    except (SyntaxError, ValueError) as error:
        raise FreezeGraphError(
            f"cannot parse Python source {owner}: {error}"
        ) from error

    pins: set[Pin] = set()
    for node in ast.walk(tree):
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
    return pins


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


def source_pins(repo: Path, files: list[str]) -> dict[str, set[Pin]]:
    collected: dict[str, set[Pin]] = {}
    for relative in files:
        parts = PurePosixPath(relative).parts
        if not parts or parts[0] not in SOURCE_ROOTS:
            continue
        source = read_regular(repo, relative)
        if relative.endswith(".py"):
            pins = python_pins(source, relative)
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
    return collected


def result_pins(repo: Path, files: list[str]) -> set[Pin]:
    pins: set[Pin] = set()
    root_parts = RESULT_ROOT.parts
    for relative in files:
        path = PurePosixPath(relative)
        if path.suffix != ".json" or path.parts[: len(root_parts)] != root_parts:
            continue
        if len(path.parts) != len(root_parts) + 1:
            continue
        pins.update(
            json_pins(
                load_json(read_regular(repo, relative), relative),
                relative,
                bind_path_keys=False,
            )
        )
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
) -> list[dict[str, Any]]:
    drift: dict[str, dict[str, set[str]]] = {}
    for pin in sorted(pins, key=pin_sort_key):
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


def build_report(repo: Path) -> dict[str, Any]:
    files = repository_files(repo)
    sources = source_pins(repo, files)
    results = result_pins(repo, files)
    all_pins = set(results)
    for pins in sources.values():
        all_pins.update(pins)
    candidates = {pin.digest for pin in all_pins}
    by_path, by_digest = current_digests(repo, files)
    historical = historical_digest_matches(repo, candidates)
    frozen, pinned_by = freeze_closure(results, sources, by_digest)
    drift = drift_rows(all_pins, by_path, by_digest, historical)
    frozen_rows = [
        {
            "path": path,
            "sha256": by_path[path],
            "pinned_by": sorted(pinned_by[path]),
        }
        for path in sorted(frozen)
    ]
    return {
        "schema_version": 1,
        "frozen_count": len(frozen_rows),
        "frozen": frozen_rows,
        "drift": drift,
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
    return 1 if report["drift"] else 0


if __name__ == "__main__":
    sys.exit(main())
