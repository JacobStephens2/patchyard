#!/usr/bin/env python3
"""Build the deterministic role-grouped A102 projection from pinned tokei JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROLE_PATHS = {
    "product": ("crates", "migrations", "assets"),
    "infrastructure": ("infra", "worker", "preview"),
    "tooling": (
        "tools",
        "model",
        "fixtures",
        ".github",
        "Cargo.toml",
        "Cargo.lock",
        "rust-toolchain.toml",
    ),
    "governance": (
        "docs",
        "policy",
        "research",
        "reviews",
        "rulings-queue",
        "AGENTS.md",
        "PLAN.md",
        "SPEC.md",
        "README.md",
    ),
}

ROLE_DESCRIPTIONS = {
    "product": "Rust services, server-rendered UI assets, and PostgreSQL migrations.",
    "infrastructure": "OpenTofu, Ansible, worker runtime, and preview-fleet desired state.",
    "tooling": "Checks, generators, model projections, fixtures, and CI orchestration.",
    "governance": "Constitution, specification, rulings, policy, research, and review record.",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokei-version", required=True)
    for role in ROLE_PATHS:
        parser.add_argument(f"--{role}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def language_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    aggregate: dict[str, dict[str, int]] = {}

    def add(name: str, code: int, comments: int, blanks: int, files: int) -> None:
        row = aggregate.setdefault(
            name, {"code": 0, "comments": 0, "blanks": 0, "files": 0}
        )
        row["code"] += code
        row["comments"] += comments
        row["blanks"] += blanks
        row["files"] += files

    for language, metrics in report.items():
        if language == "Total":
            continue
        add(
            language,
            int(metrics["code"]),
            int(metrics["comments"]),
            int(metrics["blanks"]),
            len(metrics.get("reports", [])),
        )
        for child_name, children in metrics.get("children", {}).items():
            add(
                child_name,
                sum(int(child["stats"]["code"]) for child in children),
                sum(int(child["stats"]["comments"]) for child in children),
                sum(int(child["stats"]["blanks"]) for child in children),
                len(children),
            )
    return [
        {"language": name, **aggregate[name]}
        for name in sorted(aggregate, key=lambda value: value.casefold())
    ]


def role_metrics(role: str, report: dict[str, Any]) -> dict[str, Any]:
    total = report["Total"]
    files = sum(
        len(metrics.get("reports", []))
        for language, metrics in report.items()
        if language != "Total"
    )
    return {
        "role": role,
        "description": ROLE_DESCRIPTIONS[role],
        "code": int(total["code"]),
        "comments": int(total["comments"]),
        "blanks": int(total["blanks"]),
        "files": files,
        "languages": language_rows(report),
    }


def main() -> None:
    args = parse_args()
    roles = []
    for role in ROLE_PATHS:
        report_path = getattr(args, role)
        roles.append(role_metrics(role, json.loads(report_path.read_text())))
    projection = {
        "schema_version": 1,
        "generated_by": "tools/check-codebase.sh",
        "tokei_version": args.tokei_version,
        "roles": roles,
    }
    args.output.write_text(json.dumps(projection, indent=2) + "\n")


if __name__ == "__main__":
    main()
