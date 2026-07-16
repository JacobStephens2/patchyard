#!/usr/bin/env python3
"""Generate Mermaid diagrams from factory-model.json (the canonical model).

Per stephens.page/blog/the-diagram-is-not-the-model/agents.md: the diagram
is a projection; this script is the projector. Run after editing the model:

    python3 render-model.py

Writes factory-model.mmd and factory-model-diagram.md beside the model.
Run render-model-assets.sh afterward to refresh the standalone web projections.
The build-phase CI check is byte-identical regeneration (blog checklist #4).
"""
import json, pathlib

HERE = pathlib.Path(__file__).parent
m = json.loads((HERE / "factory-model.json").read_text())

nodes = {}
for st in m["stages"]:
    nodes[st["id"]] = (st["name"], st["actor"])
for e in m.get("entities", []):
    nodes[e["id"]] = (e["name"], e["actor"])

ARROW = {"belt": "-->", "exit": "-->", "human-gated": "-.->", "learning": "-.->"}
lines = ["flowchart LR"]
for nid, (name, actor) in nodes.items():
    label = f"{name}<br/><i>{actor}</i>"
    if actor == "human":
        lines.append(f'  {nid}{{{{"{label}"}}}}:::human')
    elif actor == "agent":
        lines.append(f'  {nid}(["{label}"]):::agent')
    else:
        lines.append(f'  {nid}["{label}"]:::det')
for e in m["edges"]:
    arrow = ARROW[e["kind"]]
    lbl = f'|"{e["label"]}"|' if e.get("label") else ""
    lines.append(f'  {e["from"]} {arrow}{lbl} {e["to"]}')
lines += [
  "  classDef human fill:#eaf2fc,stroke:#2a78d6,stroke-width:2.5px,color:#1c5cab",
  "  classDef agent fill:#fdf6ec,stroke:#b07d2b,stroke-dasharray:5 3,color:#7c5200",
  "  classDef det fill:#f4f5f7,stroke:#9aa0a8,color:#4c545f",
]
mmd = "\n".join(lines) + "\n"
(HERE / "factory-model.mmd").write_text(mmd)

doc = f"""# Factory model - generated diagram

*Generated from `factory-model.json` v{m['version']} ({m['updated']}) by
`render-model.py`. Do not edit by hand - edit the model, re-run the
projector. Hexagons = human, dashed rounded = AI agent (non-deterministic),
rectangles = deterministic software. Dashed edges are human-gated.*

```mermaid
{mmd}```
"""
(HERE / "factory-model-diagram.md").write_text(doc)
print(f"wrote factory-model.mmd + factory-model-diagram.md ({len(m['edges'])} edges, {len(nodes)} nodes)")
