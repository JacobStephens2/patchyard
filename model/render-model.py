#!/usr/bin/env python3
"""Project the canonical factory model to Mermaid and Markdown.

Edit factory-model.json, run model/model-id.py --write, then run this projector.
Use --check in automation to require byte-identical committed projections.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from model_tools import (
    IDENTITY_PATH,
    MODEL_PATH,
    load_model,
    model_sha256,
    validate_model,
)


HERE = Path(__file__).resolve().parent
MMD_PATH = HERE / "factory-model.mmd"
DOC_PATH = HERE / "factory-model-diagram.md"

ARROW = {"belt": "-->", "exit": "-->", "human-gated": "-.->", "learning": "-.->"}


def mermaid_text(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;")


def projections(model: dict, digest: str) -> tuple[str, str]:
    nodes = {}
    for stage in model["stages"]:
        nodes[stage["id"]] = (stage["name"], stage["actor"])
    for entity in model["entities"]:
        nodes[entity["id"]] = (entity["name"], entity["actor"])

    lines = [
        f"%% factory-model schema v{model['schemaVersion']}, model v{model['modelVersion']}",
        f"%% canonical sha256:{digest}",
        "flowchart LR",
    ]
    for node_id, (name, actor) in nodes.items():
        label = f"{mermaid_text(name)}<br/><i>{mermaid_text(actor)}</i>"
        if actor == "human":
            lines.append(f'  {node_id}{{{{"{label}"}}}}:::human')
        elif actor == "agent":
            lines.append(f'  {node_id}(["{label}"]):::agent')
        else:
            lines.append(f'  {node_id}["{label}"]:::det')

    for edge in model["edges"]:
        arrow = ARROW[edge["kind"]]
        label = (
            f'|"{mermaid_text(edge["label"])}"|'
            if edge.get("label")
            else ""
        )
        lines.append(f'  {edge["from"]} {arrow}{label} {edge["to"]}')

    lines += [
        "  classDef human fill:#eaf2fc,stroke:#2a78d6,stroke-width:2.5px,color:#1c5cab",
        "  classDef agent fill:#fdf6ec,stroke:#b07d2b,stroke-dasharray:5 3,color:#7c5200",
        "  classDef det fill:#f4f5f7,stroke:#9aa0a8,color:#4c545f",
    ]
    mermaid = "\n".join(lines) + "\n"

    document = f"""# Factory model - generated diagram

*Generated from `factory-model.json` schema v{model['schemaVersion']}, model
v{model['modelVersion']} ({model['updated']}), canonical identity
`sha256:{digest}`. Do not edit by hand - edit the model, update its identity,
and re-run the projector. Hexagons = human; dashed rounded nodes = AI agent;
rectangles = deterministic software. Dotted edges are decision or feedback
paths; inspect their labels and endpoints to distinguish human gates from the
learning loop.*

```mermaid
{mermaid}```
"""
    return mermaid, document


def check_or_write(path: Path, expected: str, check: bool) -> bool:
    if check:
        try:
            actual = path.read_text()
        except OSError as exc:
            print(f"ERROR: cannot read generated projection {path}: {exc}", file=sys.stderr)
            return False
        if actual != expected:
            print(f"ERROR: generated projection is stale: {path.name}", file=sys.stderr)
            return False
        return True
    path.write_text(expected)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail unless committed text projections are byte-identical",
    )
    args = parser.parse_args()

    try:
        model = load_model(MODEL_PATH)
        errors = validate_model(model)
        digest = model_sha256(model)
        recorded = IDENTITY_PATH.read_text().strip()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: cannot load model: {exc}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if recorded != digest:
        print(
            "ERROR: factory-model.sha256 is stale; run python3 model/model-id.py --write",
            file=sys.stderr,
        )
        return 1

    mermaid, document = projections(model, digest)
    ok = check_or_write(MMD_PATH, mermaid, args.check)
    ok = check_or_write(DOC_PATH, document, args.check) and ok
    if not ok:
        return 1

    action = "verified" if args.check else "wrote"
    print(
        f"{action} factory-model.mmd + factory-model-diagram.md "
        f"({len(model['edges'])} edges, {len(model['stages']) + len(model['entities'])} nodes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
