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
import re
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


AA_DIR = pathlib.Path(__file__).resolve().parent.parent / "research" / "artificial-analysis"
EFFORT_TAGS = {"max", "xhigh", "high", "medium", "low", "minimal", "low effort", "non-reasoning", "thinking disabled"}


def _parse_aa_name(name):
    base, effort = name.strip(), None
    while True:
        m = re.search(r"\s*\(([^()]*)\)\s*$", base)
        if not m:
            break
        tag = m.group(1).strip().lower()
        if tag in ("with fallback", "preview"):
            break
        base = base[: m.start()].rstrip()
        if tag in EFFORT_TAGS:
            effort = tag
    return base, effort or "default"


def _squeeze(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def refresh_aa(data):
    """Overlay aa_intelligence / aa_coding_index / aa_agentic_index from the
    newest snapshots, effort-matched (a wrong-variant score never beats a
    null). Sources, oldest overlaid first so newer non-null values win:
    aa-snapshots/*.json (API free tier) and homepage-scrapes/*.json (chart
    scrape). Cost columns are aa-join/leaderboard territory - untouched."""
    sources = []
    for sub in ("aa-snapshots", "homepage-scrapes"):
        for f in sorted((AA_DIR / sub).glob("*.json")):
            snap = json.loads(f.read_text(encoding="utf-8"))
            date = re.search(r"(\d{4}-\d{2}-\d{2})", f.name).group(1)
            sources.append((date, snap.get("models", {})))
    sources.sort(key=lambda pair: pair[0])
    index = {}
    for date, models in sources:
        for record in models.values():
            base, effort = _parse_aa_name(record.get("name", ""))
            key = (_squeeze(base), effort)
            merged = index.setdefault(key, {})
            for field in ("intel", "coding", "agentic"):
                if record.get(field) is not None:
                    merged[field] = record[field]
    # chart-name aliases: source (slug, effort) tried for a given bench (slug, effort)
    extra_lookups = {
        ("claudefable5", "max"): [("claudefable5withfallback", "default")],
    }
    filled = 0
    for pair in data["pairs"]:
        b_eff = re.split(r"[\s(]", pair.get("effort", "default").strip().lower(), 1)[0] or "default"
        hit = index.get((_squeeze(pair["model"]), b_eff))
        if not hit:
            base, _ = _parse_aa_name(pair["model"])
            hit = index.get((_squeeze(base), b_eff))
        if not hit:
            for alt in extra_lookups.get((_squeeze(pair["model"]), b_eff), []):
                hit = index.get(alt)
                if hit:
                    break
        if not hit:
            continue
        for src, dst in (("intel", "aa_intelligence"), ("coding", "aa_coding_index"), ("agentic", "aa_agentic_index")):
            if hit.get(src) is not None:
                value = hit[src]
                pair[dst] = int(value) if float(value).is_integer() and dst == "aa_intelligence" else value
                filled += 1
    if sources:
        data["aa_snapshot_date"] = sources[-1][0]
    return filled


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true",
                        help="regenerate the Pairs table in docs/bench.md")
    parser.add_argument("--refresh-aa", action="store_true",
                        help="overlay aa_* index fields from the newest AA snapshots (effort-matched) before validating; combine with --write")
    args = parser.parse_args()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    if args.refresh_aa:
        filled = refresh_aa(data)
        DATA.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"refresh-aa: {filled} field values overlaid from snapshots; aa_snapshot_date={data.get('aa_snapshot_date')}")
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
