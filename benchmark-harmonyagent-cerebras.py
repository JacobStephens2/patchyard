#!/usr/bin/env python3
"""Run upstream HarmonyAgent against Cerebras' raw Completions endpoint.

Example:
    uv run --with \
      'harmonyagent @ git+https://github.com/borislavmavrin/harmonyagent.git@175dda4a212193b79e5d860186c5043fd9cdc8e1' \
      benchmark-harmonyagent-cerebras.py WORKDIR PROMPT_FILE

The upstream VllmRawModel is hardcoded to localhost and sends vLLM-only request
fields. This transport keeps HarmonyAgent's prompt, parser, tools, and stop-token
semantics while mapping the request onto Cerebras-supported fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from openai_harmony import HarmonyEncodingName, load_harmony_encoding

from harmonyagent.agents.agent_config import AgentConfig
from harmonyagent.agents.harmony_agent import HarmonyAgent
from harmonyagent.environments.local import LocalEnvironment, LocalEnvironmentConfig


MODEL_ID = "gpt-oss-120b"
ENDPOINT = "https://api.cerebras.ai/v1/completions"


@dataclass
class CerebrasRawConfig:
    model_name: str = MODEL_ID
    temperature: float = 1.0
    top_p: float = 1.0


class CerebrasRawModel:
    """HarmonyAgent model protocol backed by Cerebras raw Completions."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.config = CerebrasRawConfig()
        self.cost = 0.0
        self.n_calls = 0
        self.requests: list[dict] = []
        self.encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)

    def query(
        self, prompt_text: str, stop_token_ids: list[int], max_tokens: int
    ) -> dict:
        stop_strings = [self.encoding.decode([token]) for token in stop_token_ids]
        payload = {
            "model": self.config.model_name,
            "prompt": prompt_text,
            "stop": stop_strings,
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        }
        started = time.monotonic()
        response = requests.post(
            ENDPOINT,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "patchyard-harmonyagent-cerebras/0.1",
            },
            json=payload,
            timeout=180,
        )
        elapsed = time.monotonic() - started
        response.raise_for_status()
        result = response.json()
        self.n_calls += 1
        self.requests.append(
            {
                "endpoint": ENDPOINT,
                "model": self.config.model_name,
                "prompt_sha256": hashlib.sha256(prompt_text.encode()).hexdigest(),
                "prompt_chars": len(prompt_text),
                "reasoning_high_marker": "Reasoning: high" in prompt_text,
                "stop_strings": stop_strings,
                "max_tokens": max_tokens,
                "elapsed_seconds": round(elapsed, 3),
                "finish_reason": result.get("choices", [{}])[0].get(
                    "finish_reason"
                ),
                "usage": result.get("usage"),
                "provider_time_info": result.get("time_info"),
            }
        )
        return result

    def get_template_vars(self) -> dict:
        return {
            "n_model_calls": self.n_calls,
            "model_cost": self.cost,
            "model_name": self.config.model_name,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("workdir", type=Path)
    parser.add_argument("prompt_file", type=Path)
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--max-new-tokens", type=int, default=65_536)
    parser.add_argument("--step-limit", type=int, default=1_000)
    return parser.parse_args()


def artifact_record(path: Path, workdir: Path) -> dict:
    size = path.stat().st_size if path.is_file() else None
    return {
        "name": str(path.relative_to(workdir)),
        "type": "file" if path.is_file() else "directory",
        "bytes": size,
        "content_hex": path.read_bytes().hex()
        if path.is_file() and size is not None and size <= 64
        else None,
    }


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        raise SystemExit("CEREBRAS_API_KEY is not set")
    workdir = args.workdir.resolve()
    if not workdir.is_dir():
        raise SystemExit(f"workdir is not a directory: {workdir}")

    model = CerebrasRawModel(api_key)
    environment = LocalEnvironment(
        LocalEnvironmentConfig(cwd=str(workdir), timeout=300)
    )
    config = AgentConfig(
        reasoning_effort=args.reasoning_effort,
        step_limit=args.step_limit,
        cost_limit=0,
        max_new_tokens=args.max_new_tokens,
        max_context_window=131_070,
        log_verbosity=4_000,
    )
    agent = HarmonyAgent(
        model=model,
        env=environment,
        task_id=workdir.name,
        config=config,
    )
    started = time.monotonic()
    status, final = agent.run(args.prompt_file.read_text())
    wall = time.monotonic() - started
    artifacts = [
        artifact_record(path, workdir) for path in sorted(workdir.rglob("*"))
    ]
    print(
        json.dumps(
            {
                "harness": "borislavmavrin/harmonyagent",
                "harness_commit": (
                    "175dda4a212193b79e5d860186c5043fd9cdc8e1"
                ),
                "model": MODEL_ID,
                "provider": "Cerebras",
                "reasoning_effort": args.reasoning_effort,
                "tools": config.tools,
                "step_limit": config.step_limit,
                "max_new_tokens": config.max_new_tokens,
                "workdir": str(workdir),
                "wall_seconds": round(wall, 3),
                "status": status,
                "final": final,
                "model_calls": model.n_calls,
                "requests": model.requests,
                "artifacts": artifacts,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
