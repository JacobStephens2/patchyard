#!/usr/bin/env python3
"""Validate factory-model.json, including its committed model identity."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from model_tools import (
    IDENTITY_PATH,
    MODEL_PATH,
    SCHEMA_PATH,
    load_model,
    model_sha256,
    validate_model,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", nargs="?", type=Path, default=MODEL_PATH)
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    parser.add_argument("--identity", type=Path, default=IDENTITY_PATH)
    parser.add_argument(
        "--skip-identity",
        action="store_true",
        help="validate structure and semantics without checking factory-model.sha256",
    )
    args = parser.parse_args()

    try:
        model = load_model(args.model)
        errors = validate_model(model, args.schema)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"model validation failed: {exc}", file=sys.stderr)
        return 1

    digest = model_sha256(model)
    if not args.skip_identity:
        try:
            recorded = args.identity.read_text().strip()
        except OSError as exc:
            errors.append(f"cannot read model identity {args.identity}: {exc}")
        else:
            if recorded != digest:
                errors.append(
                    f"model identity mismatch: recorded {recorded!r}, calculated {digest!r}"
                )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"{args.model.name}: valid schema v{model['schemaVersion']}, "
        f"model v{model['modelVersion']}, sha256:{digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
