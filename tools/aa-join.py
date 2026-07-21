#!/usr/bin/env python3
"""Join AA providers-leaderboard endpoints to bench pairs (the A58/ideas
task-time selection groundwork).

Normalization, in one place:

1. AA's `Model` column embeds three kinds of parenthesized suffix, which get
   classified and split:
     - EFFORT tags   -> the reasoning config the endpoint was measured at
     - PRECISION tags-> serving quantization (endpoint attribute, kept as info)
     - IDENTITY tags -> part of the model's name (kept in the base)
2. Names canonicalize by lowercase alphanumeric squeeze ("GLM-5.2" == "GLM 5.2"
   == "glm52"), plus a small explicit alias map for the leftovers.
3. Bench `host` cells are prose ("**Cerebras** (preferred) / Fireworks"); hosts
   are recognized by scanning for the leaderboard's own provider vocabulary.
4. Effort compatibility is part of the join key: an endpoint measured at
   `high` prices a bench pair running `high` (or "high (requested)", flagged),
   never a pair running `default` - AA numbers are per-config.

Outputs a dated join file beside the leaderboard snapshot and prints:
matched pairs, unpriced bench pairs, probe candidates (allowlisted providers
serving models we never benched), and unknown suffix tags needing taxonomy.

Usage: python3 tools/aa-join.py [--rule-demo]
"""

import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LB_DIR = REPO / "research" / "artificial-analysis" / "providers-leaderboard"
BENCH = REPO / "docs" / "bench.json"

EFFORT_TAGS = {"max", "xhigh", "high", "medium", "low", "minimal", "low effort", "non-reasoning", "thinking disabled"}
PRECISION_TAGS = {"fp4", "fp8", "int4", "int8", "bf16", "mxfp8", "nvfp4", "mxfp4", "nvfp8"}
SURFACE_TAGS = {"ai studio", "vertex"}  # provider serving surface (Google)
IDENTITY_TAGS = {"with fallback", "preview"}  # stay part of the model identity
IDENTITY_INLINE = {"base", "turbo", "vision"}  # fold back into the base name

# Explicit aliases where squeeze-canonicalization isn't enough
MODEL_ALIASES = {
    "nemotron3ultra550ba55b": "nemotron3ultra",
    "fable5": "claudefable5",
    "claudehaiku45": "claude45haiku",
}
# A61 allowlist providers, canonicalized (probe-candidate filter)
ALLOWLIST = {"anthropic", "openai", "xai", "google", "googlevertex", "meta",
             "amazonbedrock", "fireworks", "cerebras", "deepinfra", "novita",
             "openrouter", "blackboxai", "cohere"}


def squeeze(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def canon_model(base):
    c = squeeze(base)
    return MODEL_ALIASES.get(c, c)


def parse_model_cell(cell):
    """'DeepSeek V4 Pro (max, FP4)' -> base, effort, precision, surface, unknown"""
    base, effort, precision, surface, unknown = cell.strip(), None, None, None, []
    while True:
        m = re.search(r"\s*\(([^()]*)\)\s*$", base)
        if not m:
            break
        raw = m.group(1).strip().lower()
        if raw in IDENTITY_TAGS:
            break  # identity tags stay in the base name
        base = base[: m.start()].rstrip()
        for tag in (t.strip() for t in raw.split(",")):
            if tag in EFFORT_TAGS:
                effort = tag
            elif tag in PRECISION_TAGS:
                precision = tag
            elif tag in SURFACE_TAGS:
                surface = tag
            elif tag in IDENTITY_INLINE:
                base = f"{base} {tag}"
            elif re.fullmatch(r"[a-z]+ 20\d\d", tag):
                base = f"{base} {tag}"  # date-pinned identity ("june 2026")
            else:
                unknown.append(tag)
    return base, effort, precision, surface, unknown


def bench_effort(cell):
    """'max (requested)' -> ('max', True); 'default (pin blocked...)' -> ('default', False)"""
    c = cell.strip().lower()
    requested = "requested" in c
    first = re.split(r"[\s(]", c, 1)[0] or "default"
    return first, requested


def effort_match(lb_effort, b_effort, b_requested):
    lb = lb_effort or "default"
    if lb == b_effort:
        return "exact" if not b_requested else "requested"
    if lb == "non-reasoning" and b_effort == "default":
        return "assumed"
    return None


def main():
    tsv = sorted(LB_DIR.glob("*.tsv"))[-1]
    snap_date = re.search(r"(\d{4}-\d{2}-\d{2})", tsv.name).group(1)
    rows = list(csv.DictReader(open(tsv), delimiter="\t"))
    bench = json.load(open(BENCH))["pairs"]

    providers_vocab = {squeeze(r["API Provider"]): r["API Provider"] for r in rows}

    endpoints, unknown_tags = [], set()
    for r in rows:
        base, effort, precision, surface, unk = parse_model_cell(r["Model"])
        unknown_tags.update(unk)
        endpoints.append({
            "provider": r["API Provider"] + (f" ({surface})" if surface else ""),
            "provider_c": squeeze(r["API Provider"] + (surface or "")),
            "surface": surface,
            "model_base": base, "model_c": canon_model(base),
            "effort": effort, "precision": precision,
            "intelligence": float(r["Intelligence Index"]) if r["Intelligence Index"].replace(".", "").isdigit() else None,
            "cost_per_task": float(r["Cost per Task (USD)"].replace("$", "")) if r["Cost per Task (USD)"].startswith("$") else None,
            "tok_s": r["Median Tokens/s"], "first_chunk_s": r["Median First Chunk (s)"],
            "function_calling": r["Function Calling"], "json_mode": r["JSON Mode"],
            "api_id": r["API ID"],
        })

    matches, unpriced = [], []
    benched_models = set()
    for p in bench:
        b_model = canon_model(p["model"])
        benched_models.add(b_model)
        b_eff, b_req = bench_effort(p.get("effort", "default"))
        host_c = squeeze(p.get("host", ""))
        hosts = {h for h in providers_vocab if h in host_c}
        for e_surface in ("aistudio", "vertex"):
            for h in list(hosts):
                if (h + e_surface).replace("aistudio", "aistudio") and e_surface in host_c:
                    hosts.add(h + e_surface)
        found = []
        for e in endpoints:
            if e["model_c"] == b_model and e["provider_c"] in hosts:
                q = effort_match(e["effort"], b_eff, b_req)
                if q:
                    found.append({**e, "effort_match": q})
        if found:
            for f in found:
                matches.append({"bench": {k: p[k] for k in ("model", "effort", "harness", "host")},
                                "floor": p["floor"]["status"], "endpoint": f})
        else:
            unpriced.append(f'{p["model"]} ({p.get("effort")}) × {p["harness"]} @ {p.get("host")}')

    probe = sorted({f'{e["provider"]} | {e["model_base"]} ({e["effort"] or "default"}) intel={e["intelligence"]}'
                    for e in endpoints
                    if e["provider_c"] in ALLOWLIST and e["model_c"] not in benched_models
                    and (e["intelligence"] or 0) >= 40})

    out = LB_DIR / f"bench-join-{snap_date}.json"
    json.dump({"snapshot": tsv.name, "generated_from_bench": str(json.load(open(BENCH))["last_updated"]),
               "matches": matches, "unpriced_bench_pairs": unpriced,
               "probe_candidates_intel40": probe, "unknown_tags": sorted(unknown_tags)},
              open(out, "w"), indent=1)

    print(f"endpoints: {len(endpoints)} | bench pairs: {len(bench)} | matched: {len(matches)} "
          f"| unpriced: {len(unpriced)} | probe candidates (allowlisted, intel>=40, unbenched): {len(probe)}")
    if unknown_tags:
        print("UNKNOWN TAGS (extend taxonomy):", sorted(unknown_tags))
    print("join written:", out.name)

    if "--rule-demo" in sys.argv:
        pool = [m for m in matches if m["floor"] == "pass"
                and m["endpoint"]["intelligence"] and m["endpoint"]["intelligence"] >= 40
                and m["endpoint"]["cost_per_task"] is not None]
        pool.sort(key=lambda m: m["endpoint"]["cost_per_task"])
        print("\nRULE DEMO - cheapest tested pair with intelligence >= 40:")
        for m in pool[:5]:
            b, e = m["bench"], m["endpoint"]
            print(f'  ${e["cost_per_task"]:.2f}  intel={e["intelligence"]}  '
                  f'{b["model"]} ({b["effort"]}) × {b["harness"]} @ {e["provider"]}  [{m["endpoint"]["effort_match"]}]')


if __name__ == "__main__":
    main()
