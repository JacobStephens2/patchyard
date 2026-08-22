from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[3]
RUNTIME_PATH = ROOT / "tools/factory_checker_runtime.py"
RUNTIME_SHA256 = "db4217cdd58d3dc8343f0ba2a9d1842eb07d6356d6aa430a2e3ff9b0be07e9fe"
MOVED_HELPERS = {
    "EvidenceJsonError",
    "digest",
    "exact_keys",
    "is_within",
    "isolation_errors",
    "load_json_file",
    "parse_time",
    "registry_current_service_account_id",
    "reject_duplicate_keys",
    "reject_json_constant",
    "roster_service_account_ids",
    "secret_named_key",
    "with_current_service_account",
}
# These sources are immutable because committed Results root their exact
# digests. Their helpers describe the historical instruments; live tooling
# must not copy them again.
FROZEN_HELPERS = {
    "tools/anthropic-wif-lifecycle.py": {
        "load_json_file",
        "reject_duplicate_keys",
        "reject_json_constant",
    },
    "tools/anthropic-wif-lifecycle-admin.py": {
        "load_json_file",
        "reject_duplicate_keys",
        "reject_json_constant",
    },
    # This is an Artificial Analysis model projection, not a file digest.
    "tools/aa-sweep.py": {"digest"},
}
MIGRATED_CALLERS = {
    "tools/anthropic-spend-evidence.py",
    "tools/check-a101-readiness-root.py",
    "tools/check-anthropic-crash-cleanup.py",
    "tools/check-anthropic-expiry.py",
    "tools/check-anthropic-issuance.py",
    "tools/check-anthropic-revocation.py",
    "tools/check-anthropic-spend.py",
    "tools/check-credential-qualification.py",
    "tools/check-freeze-graph.py",
    "tools/check-openai-identity-liveness.py",
    "tools/check-openai-spend.py",
    "tools/check-openai-wif-crash-cleanup.py",
    "tools/check-openai-wif-expiry.py",
    "tools/check-openai-wif-federation-revocation.py",
    "tools/check-openai-wif-issuance.py",
    "tools/check-openai-wif-signing-key-rotation.py",
    "tools/check-signing-identities.py",
    "tools/openai-spend-evidence.py",
    "tools/openai-wif-crash-cleanup.py",
    "tools/openai-wif-expiry.py",
    "tools/openai-wif-federation-revocation.py",
    "tools/openai-wif-issuance.py",
    "tools/openai-wif-signing-key-rotation.py",
    "tools/run-isolated-unittest.py",
}


def load_runtime() -> types.ModuleType:
    source = RUNTIME_PATH.read_bytes()
    if (
        RUNTIME_PATH.is_symlink()
        or hashlib.sha256(source).hexdigest() != RUNTIME_SHA256
    ):
        raise RuntimeError("factory checker runtime differs from its exact binding")
    module = types.ModuleType("factory_checker_runtime_test_subject")
    module.__file__ = str(RUNTIME_PATH)
    module.__package__ = None
    exec(compile(source, str(RUNTIME_PATH), "exec", dont_inherit=True), module.__dict__)
    return module


RUNTIME = load_runtime()


class FactoryCheckerRuntimeContract(unittest.TestCase):
    def test_strict_json_rejects_ambiguous_inputs(self) -> None:
        contract = RUNTIME.strict_json()
        with self.assertRaisesRegex(RUNTIME.EvidenceJsonError, "duplicate JSON key: a"):
            contract.loads('{"a": 1, "a": 2}')
        with self.assertRaisesRegex(
            RUNTIME.EvidenceJsonError, "forbidden numeric constant: NaN"
        ):
            contract.loads('{"a": NaN}')

    def test_custom_json_errors_preserve_caller_vocabulary(self) -> None:
        class CollectorError(RuntimeError):
            pass

        contract = RUNTIME.strict_json(
            CollectorError,
            duplicate_template="duplicate console-state key: {key}",
        )
        with self.assertRaisesRegex(
            CollectorError, "duplicate console-state key: state"
        ):
            contract.loads('{"state": 1, "state": 2}')

    def test_checker_configuration_owns_isolation_time_and_secret_checks(self) -> None:
        checker = RUNTIME.checker_runtime(
            identity="runtime contract",
            modules=(ast, hashlib, json, re),
            repo=ROOT,
            timestamp_pattern=re.compile(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
                r"[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
            ),
            secret_names=frozenset({"private_key"}),
        )
        self.assertEqual(checker.isolation_errors(), [])
        errors: list[str] = []
        parsed = checker.parse_time("2026-08-21T23:00:00Z", "time", errors)
        self.assertEqual(errors, [])
        self.assertEqual(parsed.isoformat(), "2026-08-21T23:00:00+00:00")
        self.assertEqual(checker.secret_named_key({"nested": {"private_key": "x"}}), "private_key")
        self.assertIsNone(checker.secret_named_key({"nested": {"api_key": "x"}}))

    def test_evidence_time_errors_and_exact_shape_are_stable(self) -> None:
        checker = RUNTIME.checker_runtime(
            identity="runtime contract",
            modules=(hashlib, json, re),
            repo=ROOT,
            timestamp_pattern=re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}Z"),
        )
        errors: list[str] = []
        self.assertIsNone(checker.parse_time("yesterday", "captured_at", errors))
        self.assertEqual(errors, ["captured_at is not a UTC timestamp"])
        self.assertTrue(RUNTIME.exact_keys({"a": 1}, {"a"}, "result", errors))
        self.assertFalse(RUNTIME.exact_keys({"b": 1}, {"a"}, "result", errors))
        self.assertIn("result has an unexpected evidence shape", errors)

    def test_roster_validation_uses_the_configured_registry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry_path = Path(directory) / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "project_id": "project",
                        "current_service_account_id": "user-current",
                        "service_accounts": [
                            {"id": "user-historical"},
                            {"id": "user-current"},
                        ],
                    }
                )
            )
            checker = RUNTIME.checker_runtime(
                identity="runtime contract",
                modules=(hashlib, json),
                repo=ROOT,
                identity_history_path=registry_path,
                issuance_era_service_account_id="user-historical",
                project_id="project",
            )
            errors: list[str] = []
            self.assertEqual(
                checker.roster_service_account_ids(errors),
                frozenset({"user-historical", "user-current"}),
            )
            self.assertEqual(errors, [])

    def test_collector_runtime_resolves_and_substitutes_the_current_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "policy.json"
            registry = root / "registry.json"
            policy.write_text(
                json.dumps(
                    {
                        "project": {"id": "project"},
                        "service_account": {"id": "user-historical"},
                        "rule": {"service_account_id": "user-historical"},
                    }
                )
            )
            registry.write_text(
                json.dumps(
                    {
                        "project_id": "project",
                        "current_service_account_id": "user-current",
                        "service_accounts": [
                            {"id": "user-historical", "status": "historical"},
                            {"id": "user-current", "status": "current"},
                        ],
                    }
                )
            )
            collector = RUNTIME.openai_collector_runtime(
                load_json_file=RUNTIME.strict_json().load_file,
                policy_path=policy,
                identity_history_path=registry,
                service_account_id_pattern=re.compile(r"user-[a-z]+"),
                error_type=RuntimeError,
            )
            rewritten = collector.with_current_service_account(
                RUNTIME.strict_json().load_file(policy)
            )
            self.assertEqual(rewritten["service_account"]["id"], "user-current")
            self.assertEqual(rewritten["rule"]["service_account_id"], "user-current")

    def test_runtime_is_the_only_live_owner_of_moved_helpers(self) -> None:
        unexpected: list[str] = []
        for path in sorted((ROOT / "tools").glob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if path == RUNTIME_PATH:
                continue
            allowed = FROZEN_HELPERS.get(relative, set())
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in tree.body:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    if node.name in MOVED_HELPERS and node.name not in allowed:
                        unexpected.append(f"{relative}:{node.lineno}:{node.name}")
        self.assertEqual(unexpected, [])

    def test_every_migrated_caller_pins_the_runtime_bytes(self) -> None:
        pin = f'CHECKER_RUNTIME_SHA256 = "{RUNTIME_SHA256}"'
        for relative in sorted(MIGRATED_CALLERS):
            source = (ROOT / relative).read_text()
            with self.subTest(caller=relative):
                self.assertIn(pin, source)
                self.assertIn("CHECKER_RUNTIME_PATH.is_symlink()", source)
                self.assertIn("hashlib.sha256(_checker_runtime_source)", source)


if __name__ == "__main__":
    unittest.main()
