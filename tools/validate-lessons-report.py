#!/usr/bin/env python3
"""Validate one factoryctl lessons-report JSON document."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import jsonschema


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("policy/lessons-report.schema.json"),
    )
    arguments = parser.parse_args()
    schema = json.loads(arguments.schema.read_text(encoding="utf-8"))
    report = json.loads(arguments.report.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(validator.iter_errors(report), key=lambda error: list(error.path))
    if errors:
        for error in errors:
            location = ".".join(str(part) for part in error.path) or "<root>"
            print(f"{location}: {error.message}")
        return 1
    print("lessons-report schema: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
