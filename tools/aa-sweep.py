#!/usr/bin/env python3
"""Artificial Analysis sweep: snapshot the model catalog and report moves.

The AA reading ladder (2026-07-17 discussion): AA proposes -> local probes
confirm -> the ledger decides. This tool is the first rung: it detects
*changes worth probing*, it never reseats anything.

Usage: ARTIFICIAL_ANALYSIS_API_KEY=... python3 tools/aa-sweep.py
Snapshots land in research/aa-snapshots/ (dated, committed like any other
world-facing evidence); the report diffs the two most recent snapshots.

Tier note: with a free-tier key the API returns the trailing catalog only
(~200 models; flagship/max-effort configs are Pro-gated). The sweep logic
is tier-agnostic - a Pro key widens coverage with no code change.
"""

import json
import os
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("ARTIFICIAL_ANALYSIS_BASE_URL", "https://artificialanalysis.ai")
KEY = os.environ["ARTIFICIAL_ANALYSIS_API_KEY"]
SNAP_DIR = REPO_ROOT / "research" / "aa-snapshots"

# Trigger thresholds - a report line appears only when a move could change
# a seat assignment. Tune deliberately; noise here costs attention.
INDEX_MOVE = 3.0        # points on any AA index
PRICE_MOVE = 0.5        # fractional change in $/1M output tokens
SPEED_MOVE = 0.5        # fractional change in median output tok/s
NEW_MODEL_MIN_INDEX = 40.0  # new entrants below this intelligence index are ignored


def fetch():
    for path in ("/api/v2/language/models", "/api/v2/language/models/free"):
        req = urllib.request.Request(BASE + path, headers={"x-api-key": KEY})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
        except Exception:
            continue
        models = data.get("data")
        if isinstance(models, list) and models:
            return path, models
    raise SystemExit("no accessible models endpoint")


def digest(models):
    out = {}
    for m in models:
        ev = m.get("evaluations") or {}
        pf = m.get("performance") or {}
        pr = m.get("pricing") or {}
        out[m["slug"]] = {
            "name": m.get("name"),
            "intel": ev.get("artificial_analysis_intelligence_index"),
            "coding": ev.get("artificial_analysis_coding_index"),
            "agentic": ev.get("artificial_analysis_agentic_index"),
            "out_price": pr.get("price_1m_output_tokens"),
            "tok_s": pf.get("median_output_tokens_per_second"),
            "ttft": pf.get("median_time_to_first_token_seconds"),
        }
    return out


def frac_move(old, new):
    if not old or not new:
        return 0.0
    return abs(new - old) / abs(old)


def main():
    from datetime import date, datetime

    path, models = fetch()
    today = digest(models)
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = os.environ.get("AA_SWEEP_DATE") or date.today().isoformat()
    snap_file = SNAP_DIR / f"{stamp}.json"
    prev_files = sorted(f for f in SNAP_DIR.glob("*.json") if f != snap_file)
    snap_file.write_text(json.dumps(
        {"fetched": datetime.now().isoformat(timespec="seconds"),
         "endpoint": path, "models": today}, indent=1))

    print(f"aa-sweep: {len(today)} models via {path}; snapshot {snap_file.name}")
    if not prev_files:
        print("first snapshot - nothing to diff; run again after the next AA update")
        return
    prev = json.loads(prev_files[-1].read_text())["models"]
    print(f"diff vs {prev_files[-1].name}:")

    lines = []
    for slug, cur in today.items():
        if slug not in prev:
            if (cur["intel"] or 0) >= NEW_MODEL_MIN_INDEX:
                lines.append(f"NEW    {slug}: intel={cur['intel']} coding={cur['coding']} "
                             f"${cur['out_price']}/1Mout {cur['tok_s']} tok/s")
            continue
        old = prev[slug]
        for k, label in (("intel", "intelligence"), ("coding", "coding"), ("agentic", "agentic")):
            if old[k] and cur[k] and abs(cur[k] - old[k]) >= INDEX_MOVE:
                lines.append(f"INDEX  {slug}: {label} {old[k]} -> {cur[k]}")
        if frac_move(old["out_price"], cur["out_price"]) >= PRICE_MOVE:
            lines.append(f"PRICE  {slug}: ${old['out_price']} -> ${cur['out_price']} /1Mout")
        if frac_move(old["tok_s"], cur["tok_s"]) >= SPEED_MOVE:
            lines.append(f"SPEED  {slug}: {old['tok_s']} -> {cur['tok_s']} tok/s")
    gone = [s for s in prev if s not in today]
    for s in gone[:10]:
        lines.append(f"GONE   {s}")

    if lines:
        print("\n".join(lines))
        print(f"\n{len(lines)} trigger(s) - candidates for the local probe toll "
              "(smoke matrix / raw timing), never direct reseating.")
    else:
        print("no moves past thresholds - nothing earns a probe")


if __name__ == "__main__":
    main()
