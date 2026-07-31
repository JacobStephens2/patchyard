#!/usr/bin/env python3
"""Run one exact Ansible test file without importing repository packages."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
from pathlib import Path
import sys
import sysconfig
import unittest


REPO = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO / "infra/ansible/tests"
EXPECTED_TEST_FILES = (
    "test_a101_readiness_root.py",
    "test_worker_firewall_readiness.py",
    "test_anthropic_spend.py",
    "test_anthropic_issuance.py",
    "test_anthropic_wif_admin.py",
    "test_child_launcher.py",
    "test_cloud_init_bootstrap.py",
    "test_dashboard_checkout.py",
    "test_log_secret_scan.py",
    "test_preview_capability_deployment.py",
    "test_replace_worker.py",
    "test_session14_qualification.py",
    "test_session15_proposer.py",
    "test_session16_cutover.py",
)
STDLIB_MODULES = (hashlib, importlib, sysconfig, unittest)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def isolation_errors() -> list[str]:
    errors: list[str] = []
    if not sys.flags.isolated:
        errors.append("isolated unittest runner requires python3 -I")

    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    for module in STDLIB_MODULES:
        source = getattr(module, "__file__", None)
        if source is None or not is_within(Path(source).resolve(), stdlib):
            errors.append(
                f"isolated unittest runner rejected {module.__name__} provenance: "
                f"{source!r}"
            )

    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except OSError:
            continue
        if is_within(resolved, REPO):
            errors.append(f"isolated unittest runner has repository import path: {entry}")
    return errors


def main() -> int:
    errors = isolation_errors()
    if len(sys.argv) != 2:
        errors.append(f"usage: {sys.argv[0]} <exact Ansible test file>")
        test_file = None
    else:
        test_file = Path(sys.argv[1])
        if test_file.is_symlink():
            errors.append("isolated unittest runner refuses a symlinked test file")
        try:
            relative = test_file.resolve().relative_to(TEST_ROOT.resolve())
        except (OSError, ValueError):
            errors.append("isolated unittest runner refuses a test outside its root")
        else:
            if len(relative.parts) != 1 or relative.as_posix() not in EXPECTED_TEST_FILES:
                errors.append("isolated unittest runner refuses an uncensused test file")
            if not test_file.is_file():
                errors.append("isolated unittest runner test file is missing")

    if errors:
        print("isolated unittest runner: failed", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 2

    assert test_file is not None
    sys.dont_write_bytecode = True
    module_name = "_patchyard_bound_test"
    spec = importlib.util.spec_from_file_location(module_name, test_file)
    if spec is None or spec.loader is None:
        print("isolated unittest runner: could not load test file", file=sys.stderr)
        return 2
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise

    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
