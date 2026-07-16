#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_tools import (  # noqa: E402
    DuplicateKeyError,
    canonical_json_bytes,
    load_json,
    load_model,
    semantic_errors,
    validate_model,
)


class FactoryModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = load_model()

    def test_canonical_model_is_valid(self) -> None:
        self.assertEqual(validate_model(self.model), [])

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"modelVersion": 4, "modelVersion": 5}')
            with self.assertRaises(DuplicateKeyError):
                load_json(path)

    def test_unknown_edge_endpoint_is_rejected(self) -> None:
        model = copy.deepcopy(self.model)
        model["edges"][0]["to"] = "missing"
        self.assertTrue(
            any("undefined target node" in error for error in semantic_errors(model))
        )

    def test_human_gate_must_start_at_human_node(self) -> None:
        model = copy.deepcopy(self.model)
        model["edges"][0]["kind"] = "human-gated"
        self.assertTrue(
            any("must start at a human node" in error for error in semantic_errors(model))
        )

    def test_every_node_must_have_a_path_to_the_ledger(self) -> None:
        model = copy.deepcopy(self.model)
        model["edges"] = [
            edge
            for edge in model["edges"]
            if not (edge["from"] == "close" and edge["to"] == "ledger")
        ]
        self.assertTrue(
            any("nodes with no path to ledger" in error for error in semantic_errors(model))
        )

    def test_stage_numbers_are_contiguous(self) -> None:
        model = copy.deepcopy(self.model)
        model["stages"][1]["num"] = 8
        self.assertIn(
            "stage numbers must be ordered and contiguous from 0",
            semantic_errors(model),
        )

    def test_canonical_bytes_ignore_object_key_order(self) -> None:
        left = {"b": 2, "a": {"d": 4, "c": 3}}
        right = json.loads('{"a":{"c":3,"d":4},"b":2}')
        self.assertEqual(canonical_json_bytes(left), canonical_json_bytes(right))


if __name__ == "__main__":
    unittest.main()
