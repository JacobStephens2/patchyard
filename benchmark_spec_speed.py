#!/usr/bin/env python3
"""Compare raw-provider delivery on the synthetic DOCX-spec workload.

This deliberately measures direct APIs separately from harness wall time. It
prints credential-free JSON to stdout and can optionally retain generated text
under an output directory for acceptance inspection.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Target:
    name: str
    provider: str
    model: str
    base_url: str
    key_env: str
    reasoning_effort: str | None = None
    api_kind: str = "chat"


TARGETS = {
    "gpt-oss-120b-high": Target(
        name="gpt-oss-120b (high)",
        provider="Cerebras",
        model="gpt-oss-120b",
        base_url="https://api.cerebras.ai/v1",
        key_env="CEREBRAS_API_KEY",
        reasoning_effort="high",
    ),
    "nemotron-3-ultra": Target(
        name="Nemotron 3 Ultra",
        provider="Blackbox AI",
        model="blackboxai/nvidia/nemotron-3-ultra",
        base_url="https://api.blackbox.ai",
        key_env="BLACKBOX_AI_API_KEY",
    ),
    "command-a-plus": Target(
        name="Command A+",
        provider="Cohere",
        model="command-a-plus-05-2026",
        base_url="https://api.cohere.ai/compatibility/v1",
        key_env="COHERE_API_KEY",
    ),
    "glm-5p2-max": Target(
        name="GLM 5.2 (max)",
        provider="Fireworks",
        model="accounts/fireworks/models/glm-5p2",
        base_url="https://api.fireworks.ai/inference/v1",
        key_env="FIREWORKS_AI_API_KEY",
        reasoning_effort="max",
    ),
    "gemini-3p5-flash-high": Target(
        name="Gemini 3.5 Flash (high)",
        provider="Google AI Studio",
        model="gemini-3.5-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        key_env="GEMINI_API_KEY",
        reasoning_effort="high",
    ),
    "qwen3p7-max": Target(
        name="Qwen3.7 Max",
        provider="Novita",
        model="qwen/qwen3.7-max",
        base_url="https://api.novita.ai/openai",
        key_env="NOVITA_API_KEY",
    ),
    "gpt-5p6-luna-max": Target(
        name="GPT-5.6 Luna (max)",
        provider="OpenAI",
        model="gpt-5.6-luna",
        base_url="https://api.openai.com/v1",
        key_env="OPENAI_API_KEY",
        reasoning_effort="max",
        api_kind="responses",
    ),
}

REQUIRED_HEADINGS = (
    "## Purpose and scope",
    "## Inputs and outputs",
    "## Architecture",
    "## Rendering contract",
    "## Validation and acceptance",
    "## Failure handling and retries",
    "## Security and isolation",
    "## Rollout plan",
)


def value(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def common_token_count(text: str) -> int:
    import tiktoken

    return len(tiktoken.get_encoding("cl100k_base").encode(text))


def acceptance(text: str) -> dict[str, Any]:
    heading_positions = [text.find(heading) for heading in REQUIRED_HEADINGS]
    all_headings_present = all(position >= 0 for position in heading_positions)
    word_count = len(text.split())
    return {
        "word_count": word_count,
        "all_headings_present": all_headings_present,
        "headings_in_order": (
            all_headings_present and heading_positions == sorted(heading_positions)
        ),
        "within_requested_word_range": 1400 <= word_count <= 1800,
        "placeholder_free": "TODO" not in text and "TBD" not in text,
    }


@contextlib.contextmanager
def hard_timeout(seconds: float):
    def expire(_signum: int, _frame: object) -> None:
        raise TimeoutError(f"request exceeded {seconds:g}-second wall-clock cap")

    previous_handler = signal.signal(signal.SIGALRM, expire)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


def run_once(
    target_key: str,
    target: Target,
    prompt: str,
    round_number: int,
    max_tokens: int,
    timeout: float,
    output_dir: Path | None,
) -> dict[str, Any]:
    from openai import OpenAI

    started = time.perf_counter()
    first_event: float | None = None
    first_reasoning: float | None = None
    first_content: float | None = None
    last_content: float | None = None
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    usage: Any = None
    finish_reason: str | None = None

    try:
        client = OpenAI(
            api_key=os.environ[target.key_env],
            base_url=target.base_url,
            timeout=timeout,
            max_retries=0,
        )
        extra_body: dict[str, Any] = {}
        if target.reasoning_effort:
            extra_body["reasoning_effort"] = target.reasoning_effort

        with hard_timeout(timeout):
            if target.api_kind == "responses":
                response_stream = client.responses.create(
                    model=target.model,
                    input=[
                        {
                            "role": "system",
                            "content": (
                                "Return only the requested file's Markdown content. "
                                "Do not call tools or add a preamble."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    reasoning={"effort": target.reasoning_effort},
                    max_output_tokens=max_tokens,
                    stream=True,
                )
                for event in response_stream:
                    now = time.perf_counter()
                    if first_event is None:
                        first_event = now
                    event_type = value(event, "type", "")
                    if event_type == "response.output_text.delta":
                        content = value(event, "delta", "")
                        if content:
                            if first_content is None:
                                first_content = now
                            last_content = now
                            content_parts.append(content)
                    elif event_type == "response.reasoning_summary_text.delta":
                        reasoning = value(event, "delta", "")
                        if reasoning:
                            if first_reasoning is None:
                                first_reasoning = now
                            reasoning_parts.append(reasoning)
                    elif event_type in {
                        "response.completed",
                        "response.incomplete",
                        "response.failed",
                    }:
                        response = value(event, "response")
                        finish_reason = value(response, "status")
                        response_usage = value(response, "usage")
                        output_details = value(response_usage, "output_tokens_details")
                        usage = {
                            "prompt_tokens": value(response_usage, "input_tokens"),
                            "completion_tokens": value(response_usage, "output_tokens"),
                            "total_tokens": value(response_usage, "total_tokens"),
                            "completion_tokens_details": {
                                "reasoning_tokens": value(
                                    output_details, "reasoning_tokens"
                                )
                            },
                        }
            else:
                request: dict[str, Any] = {
                    "model": target.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Return only the requested file's Markdown content. "
                                "Do not call tools or add a preamble."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "stream": True,
                    "stream_options": {"include_usage": True},
                    "extra_body": extra_body or None,
                }
                request["max_tokens"] = max_tokens

                stream = client.chat.completions.create(**request)

                for chunk in stream:
                    now = time.perf_counter()
                    if first_event is None:
                        first_event = now
                    if value(chunk, "usage") is not None:
                        usage = value(chunk, "usage")
                    choices = value(chunk, "choices", []) or []
                    if not choices:
                        continue
                    choice = choices[0]
                    if value(choice, "finish_reason"):
                        finish_reason = value(choice, "finish_reason")
                    delta = value(choice, "delta")
                    content = value(delta, "content") or ""
                    reasoning = (
                        value(delta, "reasoning")
                        or value(delta, "reasoning_content")
                        or value(value(delta, "model_extra", {}), "reasoning")
                        or value(value(delta, "model_extra", {}), "reasoning_content")
                        or ""
                    )
                    if reasoning:
                        if first_reasoning is None:
                            first_reasoning = now
                        reasoning_parts.append(reasoning)
                    if content:
                        if first_content is None:
                            first_content = now
                        last_content = now
                        content_parts.append(content)

        ended = time.perf_counter()
        text = "".join(content_parts)
        reasoning_text = "".join(reasoning_parts)
        common_tokens = common_token_count(text)
        content_span = (
            last_content - first_content
            if first_content is not None and last_content is not None
            else None
        )
        result: dict[str, Any] = {
            "target": target_key,
            "round": round_number,
            "status": "ok",
            "finish_reason": finish_reason,
            "wall_seconds": round(ended - started, 3),
            "time_to_first_event_seconds": (
                round(first_event - started, 3) if first_event is not None else None
            ),
            "time_to_first_reasoning_seconds": (
                round(first_reasoning - started, 3)
                if first_reasoning is not None
                else None
            ),
            "time_to_first_content_seconds": (
                round(first_content - started, 3) if first_content is not None else None
            ),
            "content_span_seconds": round(content_span, 3) if content_span else None,
            "common_visible_tokens": common_tokens,
            "common_visible_tokens_per_second": (
                round(common_tokens / content_span, 1) if content_span else None
            ),
            "reasoning_characters_observed": len(reasoning_text),
            "api_prompt_tokens": value(usage, "prompt_tokens"),
            "api_completion_tokens": value(usage, "completion_tokens"),
            "api_total_tokens": value(usage, "total_tokens"),
            "acceptance": acceptance(text),
        }
        completion_details = value(usage, "completion_tokens_details")
        if completion_details:
            result["api_reasoning_tokens"] = value(
                completion_details, "reasoning_tokens"
            )
        if output_dir:
            target_dir = output_dir / target_key
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / f"round-{round_number}.md").write_text(text)
        return result
    except Exception as exc:  # retain other targets after a provider failure
        return {
            "target": target_key,
            "round": round_number,
            "status": "error",
            "wall_seconds": round(time.perf_counter() - started, 3),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def median(values: list[float | int | None]) -> float | None:
    usable = [float(item) for item in values if item is not None]
    return round(statistics.median(usable), 3) if usable else None


def summarize(
    results: list[dict[str, Any]], target_keys: list[str]
) -> list[dict[str, Any]]:
    summaries = []
    for target_key in target_keys:
        rows = [row for row in results if row["target"] == target_key]
        passed = [row for row in rows if row["status"] == "ok"]
        summaries.append(
            {
                "target": target_key,
                "successful_runs": len(passed),
                "attempted_runs": len(rows),
                "median_wall_seconds": median(
                    [row.get("wall_seconds") for row in passed]
                ),
                "median_time_to_first_content_seconds": median(
                    [row.get("time_to_first_content_seconds") for row in passed]
                ),
                "median_common_visible_tokens_per_second": median(
                    [row.get("common_visible_tokens_per_second") for row in passed]
                ),
                "median_common_visible_tokens": median(
                    [row.get("common_visible_tokens") for row in passed]
                ),
                "acceptance_passes": sum(
                    all(row["acceptance"].values()) for row in passed
                ),
            }
        )
    return summaries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prompt",
        type=Path,
        default=Path("fixtures/docx-spec-speed/request.md"),
    )
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=3000)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=tuple(TARGETS),
        default=list(TARGETS),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prompt = args.prompt.read_text()
    missing = [
        TARGETS[key].key_env
        for key in args.targets
        if not os.environ.get(TARGETS[key].key_env)
    ]
    if missing:
        raise SystemExit(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    selected = {key: asdict(TARGETS[key]) for key in args.targets}
    for target in selected.values():
        target.pop("base_url")
        target.pop("key_env")

    results = []
    for round_number in range(1, args.rounds + 1):
        for target_key in args.targets:  # interleave providers each round
            results.append(
                run_once(
                    target_key,
                    TARGETS[target_key],
                    prompt,
                    round_number,
                    args.max_tokens,
                    args.timeout,
                    args.output_dir,
                )
            )

    print(
        json.dumps(
            {
                "method": {
                    "prompt": str(args.prompt),
                    "rounds": args.rounds,
                    "max_tokens": args.max_tokens,
                    "timeout_seconds": args.timeout,
                    "common_tokenizer": "cl100k_base",
                    "targets": selected,
                },
                "summary": summarize(results, args.targets),
                "runs": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
