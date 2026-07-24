from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location(
        "patchyard_preview_resolver", ROOT / "patchyard-preview-resolver.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver = load()


class PreviewResolutionBinding(unittest.TestCase):
    def test_same_public_set_is_accepted_in_canonical_order(self) -> None:
        answers = iter(
            [
                ("157.230.1.9", "142.93.1.7"),
                ("142.93.1.7", "157.230.1.9"),
            ]
        )
        actual = resolver.resolve_stable(
            "15.preview.example.dev",
            resolver=lambda _host: tuple(sorted(next(answers))),
            pause=lambda _seconds: None,
        )
        self.assertEqual(actual, ("142.93.1.7", "157.230.1.9"))

    def test_changed_set_reaches_dns_binding_changed(self) -> None:
        answers = iter([("142.93.1.7",), ("157.230.1.9",)])
        with self.assertRaises(resolver.DnsBindingChanged):
            resolver.resolve_stable(
                "15.preview.example.dev",
                resolver=lambda _host: next(answers),
                pause=lambda _seconds: None,
            )

    def test_changed_set_process_contract_is_exit_42_with_named_state(self) -> None:
        output = io.StringIO()
        with (
            patch.object(
                resolver,
                "resolve_stable",
                side_effect=resolver.DnsBindingChanged,
            ),
            patch.object(resolver.sys, "argv", ["resolver", "15.preview.example.dev"]),
            redirect_stdout(output),
        ):
            self.assertEqual(resolver.main(), 42)
        self.assertEqual(
            output.getvalue(),
            '{"schema_version": 1, "state": "dns_binding_changed"}\n',
        )

    def test_non_preview_name_is_rejected_before_resolution(self) -> None:
        with self.assertRaises(ValueError):
            resolver.resolve_stable(
                "metadata.google.internal",
                resolver=lambda _host: ("142.93.1.7",),
                pause=lambda _seconds: None,
            )


if __name__ == "__main__":
    unittest.main()
