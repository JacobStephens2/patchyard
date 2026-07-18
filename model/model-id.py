#!/usr/bin/env python3
"""Print, check, or update the canonical JSON identity of the factory model."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from model_tools import IDENTITY_PATH, MODEL_PATH, load_model, model_sha256


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", nargs="?", type=Path, default=MODEL_PATH)
    parser.add_argument("--identity", type=Path, default=IDENTITY_PATH)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    try:
        digest = model_sha256(load_model(args.model))
    except (OSError, ValueError) as exc:
        print(f"cannot identify model: {exc}", file=sys.stderr)
        return 1

    if args.write:
        args.identity.write_text(digest + "\n")
        print(f"wrote {args.identity.name}: {digest}")
        return 0

    if args.check:
        try:
            recorded = args.identity.read_text().strip()
        except OSError as exc:
            print(f"cannot read {args.identity}: {exc}", file=sys.stderr)
            return 1
        if recorded != digest:
            print(
                f"identity mismatch: recorded {recorded!r}, calculated {digest!r}",
                file=sys.stderr,
            )
            return 1

    print(f"sha256:{digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
