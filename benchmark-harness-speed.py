#!/usr/bin/env python3
"""Measure OpenCode wall time on the synthetic DOCX-spec workload."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from benchmark_spec_speed import REQUIRED_HEADINGS, acceptance


@dataclass(frozen=True)
class HarnessTarget:
    model: str
    variant: str | None = None


TARGETS = {
    "gpt-oss-120b-high": HarnessTarget("cerebras/gpt-oss-120b", "high"),
    "nemotron-3-ultra": HarnessTarget("blackbox/blackboxai/nvidia/nemotron-3-ultra"),
    "command-a-plus": HarnessTarget("cohere/command-a-plus-05-2026", "high"),
    "glm-5p2-max": HarnessTarget("fireworks/accounts/fireworks/models/glm-5p2", "max"),
    "gemini-3p5-flash-high": HarnessTarget("google/gemini-3.5-flash", "high"),
    "qwen3p7-max": HarnessTarget("novita/qwen/qwen3.7-max"),
}


OPENCODE_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "provider": {
        "blackbox": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Blackbox AI",
            "options": {
                "baseURL": "https://api.blackbox.ai",
                "apiKey": "{env:BLACKBOX_AI_API_KEY}",
            },
            "models": {
                "blackboxai/nvidia/nemotron-3-ultra": {
                    "name": "Nemotron 3 Ultra",
                    "limit": {"context": 1_000_000, "output": 16_384},
                }
            },
        },
        "fireworks": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Fireworks",
            "options": {
                "baseURL": "https://api.fireworks.ai/inference/v1",
                "apiKey": "{env:FIREWORKS_AI_API_KEY}",
            },
            "models": {
                "accounts/fireworks/models/glm-5p2": {
                    "name": "GLM 5.2",
                    "limit": {"context": 1_040_000, "output": 65_536},
                    "variants": {"max": {"reasoningEffort": "max"}},
                }
            },
        },
        "novita": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Novita",
            "options": {
                "baseURL": "https://api.novita.ai/openai",
                "apiKey": "{env:NOVITA_API_KEY}",
            },
            "models": {
                "qwen/qwen3.7-max": {
                    "name": "Qwen3.7 Max",
                    "limit": {"context": 1_000_000, "output": 65_536},
                }
            },
        },
    },
}


def event_metrics(stdout: str) -> dict[str, float | int | None]:
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and "type" in event:
            events.append(event)
    timestamps = [event.get("timestamp") for event in events if event.get("timestamp")]
    finishes = [event for event in events if event.get("type") == "step_finish"]
    tokens = [event.get("part", {}).get("tokens", {}) for event in finishes]
    costs = [event.get("part", {}).get("cost") for event in finishes]
    return {
        "event_count": len(events),
        "event_span_seconds": (
            round((max(timestamps) - min(timestamps)) / 1000, 3) if timestamps else None
        ),
        "reported_output_tokens": sum(item.get("output", 0) for item in tokens),
        "reported_reasoning_tokens": sum(item.get("reasoning", 0) for item in tokens),
        "reported_cost_usd": round(
            sum(float(cost) for cost in costs if cost is not None), 8
        ),
    }


def run_target(
    key: str,
    prompt: str,
    base_dir: Path,
    timeout: float,
) -> dict[str, object]:
    target = TARGETS[key]
    run_dir = base_dir / key
    if run_dir.exists():
        raise FileExistsError(f"refusing to reuse non-fresh run directory: {run_dir}")
    run_dir.mkdir(parents=True)
    command = [
        "opencode",
        "run",
        "--pure",
        "--title",
        f"docx-spec-speed-{key}",
        "--format",
        "json",
        "--dir",
        str(run_dir),
        "--model",
        target.model,
        "--auto",
    ]
    if target.variant:
        command.extend(["--variant", target.variant])
    command.append(prompt)

    env = os.environ.copy()
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(OPENCODE_CONFIG)
    if env.get("GEMINI_API_KEY"):
        env.setdefault("GOOGLE_GENERATIVE_AI_API_KEY", env["GEMINI_API_KEY"])
        env.setdefault("GOOGLE_API_KEY", env["GEMINI_API_KEY"])

    started = time.perf_counter()
    try:
        process = subprocess.run(
            command,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        timed_out = False
        exit_code = process.returncode
        stdout = process.stdout
        stderr = process.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = (
            exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        )
        stderr = (
            exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        )
    ended = time.perf_counter()

    output_file = run_dir / "docx" / "specs.md"
    output_text = output_file.read_text() if output_file.exists() else ""
    other_files = [
        str(path.relative_to(run_dir))
        for path in run_dir.rglob("*")
        if path.is_file() and path != output_file
    ]
    result: dict[str, object] = {
        "target": key,
        "model": target.model,
        "variant": target.variant,
        "wall_seconds": round(ended - started, 3),
        "timed_out": timed_out,
        "exit_code": exit_code,
        "output_exists": output_file.exists(),
        "other_files": other_files,
        **event_metrics(stdout),
    }
    if output_text:
        result["acceptance"] = acceptance(output_text)
        result["headings"] = [
            line for line in output_text.splitlines() if line in REQUIRED_HEADINGS
        ]
    if stderr:
        result["stderr_tail"] = stderr[-2000:]
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prompt",
        type=Path,
        default=Path("fixtures/docx-spec-speed/request.md"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=tuple(TARGETS),
        default=list(TARGETS),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prompt = args.prompt.read_text()
    results = [
        run_target(key, prompt, args.output_dir, args.timeout) for key in args.targets
    ]
    print(
        json.dumps(
            {
                "method": {
                    "harness": "OpenCode 1.18.3",
                    "prompt": str(args.prompt),
                    "timeout_seconds_per_target": args.timeout,
                },
                "runs": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
