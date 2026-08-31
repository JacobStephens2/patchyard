#!/usr/bin/env python3
"""Workflow-rooted source, import, and gate census for A101 readiness."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
import re
import sys
import sysconfig
import types


CHECKER_RUNTIME_PATH = Path(__file__).with_name("factory_checker_runtime.py")
CHECKER_RUNTIME_SHA256 = "fcd9d4c5513d8614e20dc4e2fada3da60326ff85745a989b3d4313497b0622f6"
_checker_runtime_source = CHECKER_RUNTIME_PATH.read_bytes()
if (
    CHECKER_RUNTIME_PATH.is_symlink()
    or hashlib.sha256(_checker_runtime_source).hexdigest()
    != CHECKER_RUNTIME_SHA256
):
    raise RuntimeError(
        "bound A101 source differs: tools/factory_checker_runtime.py"
    )
RUNTIME = types.ModuleType("factory_checker_runtime_check_a101_readiness_root")
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
WORKFLOW = REPO / ".github/workflows/infrastructure.yml"
CENSUS_RELATIVE = "policy/a101-census.sha256"
CENSUS_FILE = REPO / CENSUS_RELATIVE
# Governance is derived, not transcribed. Every file matching a governed class
# is bound the moment it exists, so adding a checker or an Ansible test needs
# no edit here; the census file records what each governed file must hash to,
# and a governed file that is present but uncensused fails closed.
TOOLS_DIRECTORY = "tools"
INFRA_DIRECTORY = "infra"
TEST_DIRECTORY = "infra/ansible/tests"
# The governed classes cover every executable Python source under tools/ and
# infra/. These are the bound files that belong to no class: shell entry
# points, inert data the gates read, and the checker contract fixtures.
BOUND_EXTRA_PATHS = (
    "fixtures/checker-contracts/credential-qualification-conforming.json",
    "fixtures/checker-contracts/credential-qualification-missing-requirements.json",
    "fixtures/checker-contracts/openai-federation-revocation.json",
    "fixtures/checker-contracts/openai-signing-key-rotation.json",
    "infra/ansible/converge.sh",
    "infra/ansible/inventory/tofu.sh",
    "infra/ansible/qualify.sh",
    "infra/ansible/roles/control_plane/files/patchyard-arbiter-seat",
    "infra/ansible/roles/control_plane/files/patchyard-log-secret-scan",
    "infra/ansible/roles/control_plane/files/patchyard-mint-seat-bearer",
    "infra/ansible/roles/control_plane/files/patchyard-request-seat-bearer",
    "infra/ansible/roles/control_plane/files/patchyard-review-seat",
    "infra/ansible/roles/control_plane/files/patchyard-triage-seat",
    "infra/ansible/roles/control_plane/files/qualify-factory-session13",
    "infra/ansible/roles/control_plane/templates/patchyard-management-ssh.j2",
    "infra/replace-worker.sh",
    "infra/tofu.sh",
    "infra/tool-versions.env",
    "infra/wait-do-worker-firewall.sh",
    "tools/check-ansible.sh",
    "tools/check-infra.sh",
    "tools/install-shellcheck.sh",
    "worker/qualification/patchyard-run-openai-spend",
)
# Build output and virtual environments are not repository source; the census
# and the shadow scan both stop at these directory names.
NON_SOURCE_DIRECTORIES = frozenset(
    {".git", ".terraform", ".venv", "__pycache__", "node_modules", "target"}
)
# PyYAML is not stdlib, but the Ansible runtime imports it, so a repository
# file of that name shadows it exactly as a stdlib name would.
SHADOWED_EXTRA_MODULES = ("yaml",)
# Every governed tools/check-*.py is an infrastructure gate unless it is one
# of these: this file runs ahead of the aggregate rather than inside it, and
# the bench and seat checkers are human-run advisories that CI never gates on
# (tools/README.md, docs/bench.md). Naming the exceptions rather than the
# members means a new checker must be gated, and a deleted gate fails.
UNGATED_CHECKERS = frozenset(
    {
        "check-a101-readiness-root.py",
        "check-bench.py",
        "check-seats.py",
    }
)
CHECKER_PREFIX = "check-"
SHA256 = re.compile(r"[0-9a-f]{64}")
INFRA_GATE = re.compile(
    r'(?m)^run_gate python3 -I "\$REPO_ROOT/tools/(?P<checker>[^"/]+)"'
)
STDLIB_MODULES = (hashlib, importlib, re, sysconfig)


CHECKER = RUNTIME.checker_runtime(
    identity="A101 readiness trust root",
    modules=(hashlib, importlib, re, sysconfig, types),
    repo=REPO,
)
is_within = RUNTIME.is_within
digest = RUNTIME.digest
isolation_errors = CHECKER.isolation_errors


def is_repository_source(path: Path) -> bool:
    """A regular file under a directory this repository authors itself."""
    return path.is_file() and not NON_SOURCE_DIRECTORIES.intersection(
        path.relative_to(REPO).parts
    )


def repository_python_files() -> list[Path]:
    return [path for path in REPO.rglob("*.py") if is_repository_source(path)]


def tool_python_files() -> set[str]:
    return {
        str(path.relative_to(REPO))
        for path in (REPO / TOOLS_DIRECTORY).iterdir()
        if path.name.endswith(".py") and is_repository_source(path)
    }


def infra_python_files() -> set[str]:
    return {
        str(path.relative_to(REPO))
        for path in (REPO / INFRA_DIRECTORY).rglob("*.py")
        if is_repository_source(path)
    }


def derived_test_files() -> tuple[str, ...]:
    """The Ansible test census every runner and wrapper must agree with."""
    return tuple(
        sorted(
            relative
            for relative in infra_python_files()
            if relative.startswith(f"{TEST_DIRECTORY}/")
            and Path(relative).name.startswith("test_")
        )
    )


def governed_paths() -> tuple[str, ...]:
    """Every file the trust root binds, derived from its governed classes."""
    return tuple(
        sorted({*BOUND_EXTRA_PATHS, *tool_python_files(), *infra_python_files()})
    )


def shadowed_module_files() -> frozenset[str]:
    return frozenset(
        f"{name}.py"
        for name in (*sys.stdlib_module_names, *SHADOWED_EXTRA_MODULES)
    )


def census_text() -> str:
    """The census this checkout would assert, in sha256sum --check format."""
    rows = []
    for relative in governed_paths():
        path = REPO / relative
        if path.is_file() and not path.is_symlink():
            rows.append(f"{digest(path)}  {relative}\n")
    return "".join(rows)


def censused_digests(errors: list[str]) -> dict[str, str]:
    if not CENSUS_FILE.is_file():
        errors.append(f"A101 census file is missing: {CENSUS_RELATIVE}")
        return {}
    if CENSUS_FILE.is_symlink():
        errors.append(f"A101 census file is a symlink: {CENSUS_RELATIVE}")
        return {}
    censused: dict[str, str] = {}
    for number, line in enumerate(CENSUS_FILE.read_text().splitlines(), start=1):
        expected, separator, relative = line.partition("  ")
        if not separator or not relative or SHA256.fullmatch(expected) is None:
            errors.append(
                f"A101 census row is not sha256sum data: {CENSUS_RELATIVE}:{number}"
            )
            continue
        if relative in censused:
            errors.append(f"A101 census repeats a source: {relative}")
            continue
        censused[relative] = expected
    return censused


# Diagnostics a census rewrite plus the printed workflow re-pin resolve. A
# rewrite can never turn these into a pass on its own - the workflow rows are
# pasted by a human - so they do not block. Everything else does: a rewrite
# must not be able to make a failing tree pass.
REGENERABLE_DIAGNOSTICS = (
    "bound A101 source is uncensused: ",
    "bound A101 source differs: ",
    "censused A101 source is not governed: ",
    "A101 census file is missing: ",
    "A101 census row is not sha256sum data: ",
    "A101 census repeats a source: ",
    "infrastructure workflow does not pin the A101 census",
    "infrastructure workflow does not pin this trust-root checker",
    "infrastructure workflow differs from its exact fail-closed binding",
)


def print_required_pins() -> None:
    """Name the workflow rows a human must paste; never write CI config."""
    root_pin, census_pin = workflow_pins()
    print("  the infrastructure workflow must pin:", file=sys.stderr)
    print(f"    {root_pin}", file=sys.stderr)
    print(f"    {census_pin}", file=sys.stderr)


def report_census_change(rewritten: str) -> None:
    """Name every row the rewrite adds, drops, or re-pins."""
    before = {}
    if CENSUS_FILE.is_file():
        for line in CENSUS_FILE.read_text().splitlines():
            expected, separator, relative = line.partition("  ")
            if separator:
                before[relative] = expected
    after = {}
    for line in rewritten.splitlines():
        expected, separator, relative = line.partition("  ")
        if separator:
            after[relative] = expected
    for relative in sorted(set(after) - set(before)):
        print(f"  census adds {relative}", file=sys.stderr)
    for relative in sorted(set(before) - set(after)):
        print(f"  census drops {relative}", file=sys.stderr)
    for relative in sorted(set(before) & set(after)):
        if before[relative] != after[relative]:
            print(f"  census re-pins {relative}", file=sys.stderr)


def required_infra_gates() -> set[str]:
    """Every governed checker check-infra.sh must run, derived from tools/."""
    return {
        Path(relative).name
        for relative in tool_python_files()
        if Path(relative).name.startswith(CHECKER_PREFIX)
        and Path(relative).name not in UNGATED_CHECKERS
    }


def workflow_pins() -> tuple[str, str]:
    """The two sha256sum rows CI checks before it trusts anything else.

    Deriving the census moved the ledger out of this file, so the workflow
    anchors both halves: the rules (this checker) and the data they assert
    (the census). The workflow belongs to no governed class, so pinning the
    census here binds it without a cycle.
    """
    root_pin = f"{digest(Path(__file__))}  tools/check-a101-readiness-root.py"
    census_digest = digest(CENSUS_FILE) if CENSUS_FILE.is_file() else "0" * 64
    return root_pin, f"{census_digest}  {CENSUS_RELATIVE}"


def expected_workflow(root_pin: str, census_pin: str) -> str:
    return """name: Infrastructure

on:
  pull_request:
  push:
    branches:
      - master

permissions:
  contents: read

jobs:
  infrastructure:
    name: infrastructure
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Check out the reviewed revision
        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          # Session 16 rollback contracts execute against exact merged anchors.
          fetch-depth: 0

      - name: Verify A101 readiness trust root
        run: |
          printf '%s\\n' \\
            '__ROOT_PIN__' \\
            '__CENSUS_PIN__' \\
            | sha256sum --check
          python3 -I tools/check-a101-readiness-root.py

      - name: Install pinned OpenTofu
        uses: opentofu/setup-opentofu@9d84900f3238fab8cd84ce47d658d25dd008be2f # v1.0.8
        with:
          tofu_version: 1.12.0

      - name: Prepare Python 3.11
        uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: infra/ansible/requirements.txt

      - name: Warm the Rust cache for Session 1
        uses: Swatinem/rust-cache@c19371144df3bb44fab255c43d04cbc2ab54d1c4 # v2.9.1

      - name: Install pinned Ansible runtime
        run: |
          python -m pip install --requirement infra/ansible/requirements.txt
          ansible-galaxy collection install --requirements-file infra/ansible/requirements.yml

      - name: Install pinned ShellCheck
        run: |
          SHELLCHECK_BIN_DIR="$RUNNER_TEMP/shellcheck-bin" tools/install-shellcheck.sh
          echo "$RUNNER_TEMP/shellcheck-bin" >> "$GITHUB_PATH"

      - name: Validate OpenTofu and stack doctrine
        run: tools/check-infra.sh

      - name: Lint and syntax-check Ansible
        if: ${{ always() }}
        run: tools/check-ansible.sh
""".replace("__ROOT_PIN__", root_pin).replace("__CENSUS_PIN__", census_pin)


def validate() -> list[str]:
    errors = isolation_errors()
    censused = censused_digests(errors)
    governed = governed_paths()
    for relative in sorted(set(censused) - set(governed)):
        errors.append(f"censused A101 source is not governed: {relative}")
    for relative in governed:
        path = REPO / relative
        if not path.is_file():
            errors.append(f"bound A101 source is missing: {relative}")
            continue
        if path.is_symlink():
            errors.append(f"bound A101 source is a symlink: {relative}")
            continue
        expected = censused.get(relative)
        if expected is None:
            errors.append(f"bound A101 source is uncensused: {relative}")
            continue
        actual = digest(path)
        if actual != expected:
            errors.append(
                f"bound A101 source differs: {relative} "
                f"(expected {expected}, observed {actual})"
            )

    shadowed = shadowed_module_files()
    for path in repository_python_files():
        relative = path.relative_to(REPO)
        if path.name == "__init__.py":
            errors.append(
                f"repository package initializer is forbidden: {relative}"
            )
        elif path.name in shadowed:
            errors.append(
                f"repository shadows a protected Python module: {relative}"
            )

    wrapper_path = REPO / "tools/check-ansible.sh"
    if wrapper_path.is_file():
        wrapper = wrapper_path.read_text()
        file_block_match = re.search(
            r"(?ms)^TEST_FILES=\(\n(?P<body>.*?)^\)\n",
            wrapper,
        )
        if file_block_match is None:
            errors.append("Ansible wrapper has no explicit TEST_FILES census")
        else:
            observed_files = tuple(
                line.strip()
                for line in file_block_match.group("body").splitlines()
                if line.strip()
            )
            if observed_files != derived_test_files():
                errors.append("Ansible wrapper TEST_FILES census differs")
        if wrapper.count(
            'run_gate python3 -I "$REPO_ROOT/tools/check-anthropic-spend.py"'
        ) != 1:
            errors.append("Ansible wrapper lacks one isolated spend-checker process")
        if wrapper.count(
            'python3 -I "$REPO_ROOT/tools/check-a101-readiness-root.py"'
        ) != 2:
            errors.append("Ansible wrapper lacks two isolated trust-root checks")
        if wrapper.count(
            'python3 -I "$REPO_ROOT/tools/run-isolated-unittest.py"'
        ) != 1:
            errors.append("Ansible wrapper lacks its isolated file runner")
        if "unittest discover" in wrapper or "-m unittest" in wrapper:
            errors.append("Ansible wrapper still imports tests as repository packages")

    infra_wrapper_path = REPO / "tools/check-infra.sh"
    if infra_wrapper_path.is_file():
        infra_wrapper = infra_wrapper_path.read_text()
        if infra_wrapper.count(
            'python3 -I "$REPO_ROOT/tools/check-a101-readiness-root.py"'
        ) != 1:
            errors.append("infrastructure wrapper lacks its isolated trust-root check")
        gates = INFRA_GATE.findall(infra_wrapper)
        governed_tools = tool_python_files()
        for checker in sorted(set(gates)):
            if gates.count(checker) != 1:
                errors.append(
                    "infrastructure wrapper repeats an isolated aggregate call: "
                    f"{checker}"
                )
            if f"{TOOLS_DIRECTORY}/{checker}" not in governed_tools:
                errors.append(
                    "infrastructure wrapper gate is not a governed checker: "
                    f"{checker}"
                )
        for missing in sorted(required_infra_gates() - set(gates)):
            errors.append(
                f"infrastructure wrapper lacks one isolated aggregate call: {missing}"
            )
        if infra_wrapper.splitlines()[-1:] != ['exit "$gate_status"']:
            errors.append("infrastructure wrapper does not preserve aggregate failure")

    for relative in (
        "tools/check-infra.sh",
        "tools/check-ansible.sh",
        "tools/install-shellcheck.sh",
    ):
        path = REPO / relative
        if path.is_file() and "source \"$REPO_ROOT/infra/tool-versions.env\"" in path.read_text():
            errors.append(f"{relative} executes infrastructure tool-version data")
        if path.is_file() and re.search(
            r'(?m)^\s*python3\s+"\$REPO_ROOT/tools/(?:check-|read-infra)',
            path.read_text(),
        ):
            errors.append(f"{relative} contains a non-isolated Python gate")

    install = REPO / "tools/install-shellcheck.sh"
    if install.is_file() and install.read_text().count(
        'python3 -I "$REPO_ROOT/tools/read-infra-tool-version.py"'
    ) != 3:
        errors.append("ShellCheck installer does not isolate all three pin reads")
    qualify = REPO / "infra/ansible/qualify.sh"
    if qualify.is_file() and qualify.read_text().count(
        'python3 -I "$REPO_ROOT/tools/check-independence.py"'
    ) != 1:
        errors.append("live qualifier does not isolate its independence checker")

    if WORKFLOW.is_file():
        workflow = WORKFLOW.read_text()
        root_pin, census_pin = workflow_pins()
        if workflow.count(root_pin) != 1:
            errors.append("infrastructure workflow does not pin this trust-root checker")
        if workflow.count(census_pin) != 1:
            errors.append("infrastructure workflow does not pin the A101 census")
        if workflow != expected_workflow(root_pin, census_pin):
            errors.append("infrastructure workflow differs from its exact fail-closed binding")
    else:
        errors.append("infrastructure workflow is missing")

    return errors


def main() -> int:
    """Exit 0 when the tree is bound, 1 when it is not, 2 when refused.

    Under --write-census, 2 means nothing was written: the tree fails for a
    reason the census does not own. 1 means the census was rewritten and the
    workflow pins printed above still have to be pasted in by a human.
    """
    write_census = sys.argv[1:] == ["--write-census"]
    if sys.argv[1:] and not write_census:
        print(
            f"usage: {sys.argv[0]} [--write-census]",
            file=sys.stderr,
        )
        return 2
    if write_census:
        # Regenerate only what the census itself owns. Anything else the trust
        # root rejects - a missing bound file, a stdlib shadow, an ungated
        # checker, a workflow that no longer matches its binding - is a real
        # failure, and rewriting the census must not launder it into a pass.
        blocking = [
            error
            for error in validate()
            if not error.startswith(REGENERABLE_DIAGNOSTICS)
        ]
        if blocking:
            print("A101 readiness trust root: failed", file=sys.stderr)
            for error in blocking:
                print(f"  {error}", file=sys.stderr)
            print(
                "  refusing to rewrite the census while these stand",
                file=sys.stderr,
            )
            print_required_pins()
            return 2
        report_census_change(census_text())
        CENSUS_FILE.write_text(census_text())
        print("A101 census written.", file=sys.stderr)
        print_required_pins()

    errors = validate()
    if errors:
        print("A101 readiness trust root: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    print("A101 readiness trust root: pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
