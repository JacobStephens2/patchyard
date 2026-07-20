#!/usr/bin/env python3
"""Cross-check bench.md's § Seat preference orders against docs/bench.json.

The seat tables stay hand-edited: seatings include judgment calls the
data alone cannot reproduce (the A58 method - e.g. Kimi K2.6 keeping its
seat on content quality despite losing the speed A/B). This checker
verifies what IS mechanical and flags contradictions between the
operative roster and the benched pairs.

Errors (exit 1):
  - a seat row's model does not resolve to exactly one bench.json model
  - no benched pair exists for the row's (model, harness)
  - rank column is not 1..n, or the rank metric is not monotonic
    (Index non-increasing; $/task non-decreasing; long-spec wall
    non-decreasing)
  - a provider is off the A61 allowlist (parsed from bench.md's
    Standing rules bullet - the ruled roster is not duplicated here)
  - a speed-table t/s or wall value disagrees numerically with the
    matched pair's bench.json measurement

Warnings (exit 0; --strict raises them to errors):
  - a seat row uses a non-preferred harness treatment
  - the matched pair's floor is not a pass
  - the row's provider has no benched pair on that host
  - an allowlist provider backs no seat row

AA-chart-sourced columns (Index, $/task) get ordering checks only:
their values live on the Artificial Analysis charts (refreshed via
tools/aa-sweep.py), not in bench.json.

Usage: python3 tools/check-seats.py [--strict]
"""
import argparse
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DATA = REPO / "docs" / "bench.json"
BENCH_MD = REPO / "docs" / "bench.md"

WALL_TOLERANCE_S = 0.5


def split_row(line):
    cells, cell, escaped = [], "", False
    for ch in line.strip():
        if escaped:
            cell += ch
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "|":
            cells.append(cell.strip())
            cell = ""
        else:
            cell += ch
    cells.append(cell.strip())
    if cells and cells[0] == "":
        cells.pop(0)
    if cells and cells[-1] == "":
        cells.pop()
    return cells


def strip_parens(value):
    previous = None
    while previous != value:
        previous = value
        value = re.sub(r"\([^()]*\)", "", value)
    return value


def base(value):
    value = strip_parens(value)
    value = re.sub(r"[`*_]", "", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    return value.strip(" -")


def key(value):
    return re.sub(r"[^a-z0-9]", "", base(value).lower())


def numbers(value):
    return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", value.replace(",", ""))]


def seat_section(md_text):
    lines = md_text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## Seat preference orders"))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return lines[start:end]


def parse_tables(section_lines):
    """Yield (label, kind, headers, rows) for each markdown table in the section."""
    tables = []
    subsection, variant = "", ""
    i = 0
    while i < len(section_lines):
        line = section_lines[i]
        if line.startswith("### "):
            subsection, variant = line[4:].strip(), ""
        elif re.match(r"^Text.*input.*:\s*$", line):
            variant = line.strip().rstrip(":")
        elif line.lstrip().startswith("|"):
            block = []
            while i < len(section_lines) and section_lines[i].lstrip().startswith("|"):
                block.append(section_lines[i])
                i += 1
            headers = split_row(block[0])
            rows = [split_row(l) for l in block[2:]]
            if "Index" in headers:
                kind = "index"
            elif any(h.startswith("$") for h in headers):
                kind = "cost"
            elif "Long-spec wall" in headers:
                kind = "speed"
            else:
                kind = "unknown"
            label = subsection + (f" / {variant}" if variant else "")
            tables.append((label, kind, headers, rows))
            continue
        i += 1
    return tables


def parse_allowlist(md_text):
    flat = re.sub(r"\s+", " ", md_text)
    match = re.search(r"provider allowlist.*?union\s*-\s*(.*?)\.", flat)
    if not match:
        return None
    entries = [base(e) for e in match.group(1).split(",") if base(e)]
    return entries if len(entries) >= 5 else None


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, message):
        if message not in self.errors:
            self.errors.append(message)

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)


def resolve_model(seat_model, models, report, where):
    k = key(seat_model)
    matches = [m for m in models if key(m) == k or k in key(m) or key(m) in k]
    if len(matches) != 1:
        detail = f"matches {matches}" if matches else "no match in bench.json"
        report.error(f"{where}: model {seat_model!r} - {detail}")
        return None
    return matches[0]


def check_row(label, kind, headers, cells, pairs, allowlist, report):
    where = f"[{label}] row {cells[0] if cells else '?'}"
    if len(cells) != len(headers):
        report.error(f"{where}: {len(cells)} cells, header has {len(headers)}")
        return
    seat_model, seat_harness, seat_provider = cells[1], cells[2], cells[3]

    model = resolve_model(seat_model, sorted({p["model"] for p in pairs}), report, where)
    if model is None:
        return
    where = f"[{label}] #{cells[0]} {model}"

    harness_rows = [p for p in pairs
                    if p["model"] == model and key(p["harness"]) == key(seat_harness)]
    if not harness_rows:
        benched = sorted({p["harness"] for p in pairs if p["model"] == model})
        report.error(f"{where}: no benched pair with harness {base(seat_harness)!r} (benched: {benched})")
        return

    prov_key = key(seat_provider)
    if allowlist and not any(prov_key.startswith(key(a)) or key(a).startswith(prov_key) for a in allowlist):
        report.error(f"{where}: provider {base(seat_provider)!r} is not on the A61 allowlist")

    host_rows = [p for p in harness_rows
                 if key(p["host"]).startswith(prov_key) or prov_key.startswith(key(p["host"]))]
    if not host_rows:
        hosts = sorted({base(p["host"]) for p in harness_rows})
        report.warn(f"{where}: provider {base(seat_provider)!r} has no benched pair on that host (benched host: {hosts})")
    matched = host_rows or harness_rows

    if not any(p["preferred_harness"] for p in matched):
        report.warn(f"{where}: {base(seat_harness)!r} is not the preferred harness treatment")
    floor_states = {p["floor"]["status"] for p in matched}
    if "pass" not in floor_states:
        report.warn(f"{where}: floor is {'/'.join(sorted(floor_states))}, not a pass")

    if kind == "speed" and host_rows:
        pair = host_rows[0]
        seat_tps, seat_wall = cells[headers.index("Visible t/s")], cells[headers.index("Long-spec wall")]
        pair_tps_max = max(numbers(pair["visible_tps"]), default=None)
        seat_tps_max = max(numbers(seat_tps), default=None)
        if seat_tps_max is not None and seat_tps_max != pair_tps_max:
            report.error(f"{where}: seat t/s {seat_tps_max} vs bench.json {pair_tps_max}")
        seat_wall_n, pair_wall_n = numbers(seat_wall)[:1], numbers(pair["long_spec_wall"])[:1]
        if seat_wall_n and (not pair_wall_n or abs(seat_wall_n[0] - pair_wall_n[0]) > WALL_TOLERANCE_S):
            report.error(f"{where}: seat wall {seat_wall} vs bench.json {pair['long_spec_wall'] or '(unmeasured)'}")


def check_ordering(label, kind, headers, rows, report):
    ranks = [cells[0] for cells in rows if cells]
    if ranks != [str(n) for n in range(1, len(ranks) + 1)]:
        report.error(f"[{label}]: rank column is {ranks}, expected 1..{len(ranks)}")
    if kind == "index":
        values = [max(numbers(cells[headers.index("Index")]), default=None) for cells in rows]
        bad = any(a is not None and b is not None and b > a for a, b in zip(values, values[1:]))
        rule = "Index must be non-increasing"
    elif kind == "cost":
        col = next(i for i, h in enumerate(headers) if h.startswith("$"))
        values = [max(numbers(cells[col]), default=None) for cells in rows]
        bad = any(a is not None and b is not None and b < a for a, b in zip(values, values[1:]))
        rule = "$/task must be non-decreasing"
    elif kind == "speed":
        values = [(numbers(cells[headers.index("Long-spec wall")]) or [None])[0] for cells in rows]
        bad = any(a is not None and b is not None and b < a for a, b in zip(values, values[1:]))
        rule = "long-spec wall must be non-decreasing"
    else:
        report.error(f"[{label}]: unrecognized table shape (headers: {headers})")
        return
    if bad:
        report.error(f"[{label}]: {rule} (got {values})")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true", help="warnings also fail the run")
    args = parser.parse_args()

    pairs = json.loads(DATA.read_text(encoding="utf-8"))["pairs"]
    md_text = BENCH_MD.read_text(encoding="utf-8")
    report = Report()

    allowlist = parse_allowlist(md_text)
    if allowlist is None:
        report.error("could not parse the A61 provider allowlist from bench.md's Standing rules bullet")

    tables = parse_tables(seat_section(md_text))
    if len(tables) < 3:
        report.error(f"found only {len(tables)} seat tables under § Seat preference orders")

    seated_provider_keys = set()
    for label, kind, headers, rows in tables:
        check_ordering(label, kind, headers, rows, report)
        for cells in rows:
            check_row(label, kind, headers, cells, pairs, allowlist, report)
            if len(cells) == len(headers):
                seated_provider_keys.add(key(cells[3]))
    for entry in allowlist or []:
        if not any(k.startswith(key(entry)) or key(entry).startswith(k) for k in seated_provider_keys):
            report.warn(f"allowlist provider {entry!r} backs no seat row (A61: seating admits, unseating removes)")

    for message in report.errors:
        print(f"ERROR   {message}")
    for message in report.warnings:
        print(f"WARNING {message}")
    seat_count = sum(len(rows) for _, _, _, rows in tables)
    print(f"check-seats: {len(tables)} tables, {seat_count} seat rows, "
          f"{len(report.errors)} errors, {len(report.warnings)} warnings")
    sys.exit(1 if report.errors or (args.strict and report.warnings) else 0)


if __name__ == "__main__":
    main()
