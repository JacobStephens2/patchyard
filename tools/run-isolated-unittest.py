#!/usr/bin/env python3
"""Run one exact Ansible test file without importing repository packages."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
import sys
import sysconfig
import tempfile
import types
import unittest


CHECKER_RUNTIME_PATH = Path(__file__).with_name("factory_checker_runtime.py")
CHECKER_RUNTIME_SHA256 = "fcd9d4c5513d8614e20dc4e2fada3da60326ff85745a989b3d4313497b0622f6"
_checker_runtime_source = CHECKER_RUNTIME_PATH.read_bytes()
if (
    CHECKER_RUNTIME_PATH.is_symlink()
    or hashlib.sha256(_checker_runtime_source).hexdigest()
    != CHECKER_RUNTIME_SHA256
):
    raise RuntimeError("factory checker runtime differs from its exact binding")
RUNTIME = types.ModuleType("factory_checker_runtime_run_isolated_unittest")
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
TEST_ROOT = REPO / "infra/ansible/tests"
# The census is the one the A101 readiness trust root derives and binds, read
# from its census file rather than restated here. A test source is runnable
# only once it is censused, so a file dropped into the test root cannot be run
# before the trust root governs it.
CENSUS_FILE = REPO / "policy/a101-census.sha256"
TEST_ROOT_RELATIVE = "infra/ansible/tests"
STDLIB_MODULES = (hashlib, importlib, sysconfig, unittest)


CHECKER = RUNTIME.checker_runtime(
    identity="isolated unittest runner",
    modules=(hashlib, importlib, sysconfig, types, unittest),
    repo=REPO,
)
is_within = RUNTIME.is_within
isolation_errors = CHECKER.isolation_errors


def censused_test_files() -> set[str]:
    if not CENSUS_FILE.is_file() or CENSUS_FILE.is_symlink():
        return set()
    censused = set()
    for line in CENSUS_FILE.read_text().splitlines():
        _, separator, relative = line.partition("  ")
        prefix = f"{TEST_ROOT_RELATIVE}/"
        if separator and relative.startswith(prefix):
            censused.add(relative[len(prefix):])
    return censused


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
            name = relative.as_posix()
            if len(relative.parts) != 1 or name not in censused_test_files():
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
    with tempfile.TemporaryDirectory(prefix="patchyard-unittest-cache-") as cache:
        # Keep every import loader away from repository bytecode, then compile
        # the exact opened test source instead of consulting SourceFileLoader.
        sys.pycache_prefix = cache
        source = test_file.read_bytes()
        code = compile(source, str(test_file), "exec", dont_inherit=True)
        module = types.ModuleType(module_name)
        module.__file__ = str(test_file)
        module.__package__ = None
        module.__loader__ = None
        module.__spec__ = None
        sys.modules[module_name] = module
        try:
            exec(code, module.__dict__)
            suite = unittest.defaultTestLoader.loadTestsFromModule(module)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        finally:
            sys.modules.pop(module_name, None)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
