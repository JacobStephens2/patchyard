#!/usr/bin/env python3
"""Validate docs/bench.json and keep the generated Pairs table in
docs/bench.md in sync with it.

docs/bench.json is the source of truth for the Pairs table; the markdown
table between the BEGIN/END GENERATED markers in docs/bench.md is a
projection of it, as is docs/bench.html. Everything else in bench.md
(seat orders, probes, rules) stays hand-edited prose.

Usage, from the repository root (or anywhere - paths resolve from this
script's location):

    python3 tools/check-bench.py            # validate + fail on drift
    python3 tools/check-bench.py --write    # validate + regenerate the table
"""
import argparse
import difflib
import json
import pathlib
import sys

import jsonschema

REPO = pathlib.Path(__file__).resolve().parent.parent
DATA = REPO / "docs" / "bench.json"
SCHEMA = REPO / "docs" / "bench.schema.json"
BENCH_MD = REPO / "docs" / "bench.md"

BEGIN = "<!-- BEGIN GENERATED pairs table: edit docs/bench.json, then run `python3 tools/check-bench.py --write` -->"
END = "<!-- END GENERATED pairs table -->"

FLOOR_ICON = {"pass": "✅", "fail": "❌", "untested": "-"}
IMAGE_ICON = {"yes": "✅", "no": "❌", "unknown": "?"}


def fail(message):
    sys.exit(f"check-bench: {message}")


def check_invariants(data):
    problems = []
    seen = {}
    preferred = {}
    for i, pair in enumerate(data["pairs"]):
        key = (pair["model"], pair["effort"], pair["harness"], pair["host"])
        if key in seen:
            problems.append(f"pairs[{i}]: duplicate row {key} (first at pairs[{seen[key]}])")
        seen[key] = i
        if pair["floor"]["status"] == "untested" and pair["floor"]["detail"]:
            problems.append(f"pairs[{i}] {pair['model']}: floor.detail must be empty when status is untested")
        if pair["preferred_harness"]:
            preferred.setdefault(pair["model"], set()).add(pair["harness"])
    for model, harnesses in preferred.items():
        if len(harnesses) > 1:
            problems.append(
                f"{model}: preferred_harness=true on more than one harness ({', '.join(sorted(harnesses))}); "
                "the preference is model-specific - at most one harness per model"
            )
    return problems


def escape_cell(value):
    return value.replace("|", "\\|")


def icon_cell(icons, field):
    icon = icons[field["status"]]
    return f"{icon} {field['detail']}" if field["detail"] else icon


def render_table(data):
    headers = [
        "Model", "Effort", "Harness", "Preferred Harness", "Host", "Floor",
        "Img-in", "Provenance", "Current standing", "Visible t/s",
        "Long-spec wall", f"AA Intelligence (v{data['aa_index_version']})",
        "AA Coding", "AA Agentic",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join([":--"] * len(headers)) + " |",
    ]
    for pair in data["pairs"]:
        cells = [
            pair["model"],
            pair["effort"],
            pair["harness"],
            "Yes" if pair["preferred_harness"] else "No",
            pair["host"],
            icon_cell(FLOOR_ICON, pair["floor"]),
            icon_cell(IMAGE_ICON, pair["image_input"]),
            pair["provenance"],
            pair["standing"],
            pair["visible_tps"],
            pair["long_spec_wall"],
            "" if pair["aa_intelligence"] is None else str(pair["aa_intelligence"]),
            "" if pair.get("aa_coding_index") is None else str(pair["aa_coding_index"]),
            "" if pair.get("aa_agentic_index") is None else str(pair["aa_agentic_index"]),
        ]
        lines.append("| " + " | ".join(escape_cell(c) for c in cells) + " |")
    return lines


def generated_span(md_lines):
    try:
        begin = md_lines.index(BEGIN)
        end = md_lines.index(END)
    except ValueError:
        fail(f"{BENCH_MD.name} is missing the BEGIN/END GENERATED pairs table markers")
    if end <= begin:
        fail(f"{BENCH_MD.name}: END marker precedes BEGIN marker")
    return begin, end


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true",
                        help="regenerate the Pairs table in docs/bench.md")
    args = parser.parse_args()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as error:
        fail(f"{DATA.name} fails schema: {error.message} (at {'/'.join(str(p) for p in error.absolute_path)})")

    problems = check_invariants(data)
    if problems:
        fail(f"{DATA.name} invariant violations:\n  " + "\n  ".join(problems))

    md_lines = BENCH_MD.read_text(encoding="utf-8").splitlines()
    begin, end = generated_span(md_lines)
    current = md_lines[begin + 1:end]
    rendered = render_table(data)

    if args.write:
        if current == rendered:
            print(f"check-bench: OK ({len(data['pairs'])} pairs; table already in sync)")
            return
        new_lines = md_lines[:begin + 1] + rendered + md_lines[end:]
        BENCH_MD.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print(f"check-bench: wrote {len(data['pairs'])} pairs to {BENCH_MD.name}")
        return

    if current != rendered:
        diff = "\n".join(difflib.unified_diff(
            current, rendered, "bench.md (current)", "bench.json (rendered)", lineterm=""))
        fail(f"{BENCH_MD.name} Pairs table is out of sync with {DATA.name} - "
             f"run `python3 tools/check-bench.py --write`\n{diff}")
    print(f"check-bench: OK ({len(data['pairs'])} pairs; schema, invariants, and table in sync)")


if __name__ == "__main__":
    main()
