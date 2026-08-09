#!/usr/bin/env python3
"""Drive an attended collector without a controlling terminal.

The interactive collectors block on stdin. That makes a run only as durable as
the SSH session holding its pseudo-TTY: a dropped connection destroys the pty,
the kernel SIGHUPs the collector, and an A132 mutation window is left open with
the control plane in its mutated state. That has happened once on a live
requirement-4 run.

This runner replaces the terminal, not the collector. It supplies the
collector's existing `input_fn` seam from files in a session directory: the
pending prompt is written to `prompt.json`, and the answer is read from
`reply-<seq>.json`. Nothing about what constitutes valid evidence moves here.

The collector's own `main()` still runs, so the root check, run-ID validation,
stage validation, signing-key checks, reserved output and failure-record
handling are the same code on the same path as an interactive run. The only
substitution is where the operator's line comes from. That is deliberate: the
web path must be a different way to supply the same answers, not a second
instrument.

The substitution works by binding `builtins.input` before the collector module
is imported. Both collectors declare `input_fn: Callable[[str], str] = input`,
and a default is evaluated at definition time, so an import performed after the
bind captures this runner's callable at every one of those call sites. No
collector is edited and no argument is threaded through.

Sequential integrity is the property this file exists to protect. A reading is
answered only for the prompt currently open. Reading 4 of the revocation
collector means "the console state while the mapping is still removed"; a
runner that let an operator stage all the answers up front would produce a
record that passes every checker while attesting to nothing. Staging is
therefore refused structurally, not discouraged.
"""

from __future__ import annotations

import argparse
import builtins
import errno
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
import types
from typing import Any


ROOT = Path(__file__).resolve().parent.parent

# Collectors this runner may drive. Both are interactive because they capture
# A132 attestations, which exist precisely where the provider issues no
# receipt. Every other collector is fully automated and needs no runner.
COLLECTORS = {
    "federation-revocation": "openai-wif-federation-revocation.py",
    "signing-key-rotation": "openai-wif-signing-key-rotation.py",
}

# The collectors' two prompt shapes. `kind` lets a front end render a typed
# form for a reading and a single acknowledgement control for a pause, instead
# of asking an operator to retype a magic phrase. It is a presentation hint
# only: the answer is passed to the collector verbatim either way.
READING_PROMPT = "console reading JSON> "
PAUSE_PROMPT = re.compile(r"^Type '(?P<phrase>[A-Z ]+)' after the actor finishes> $")

POLL_SECONDS = 0.25
REPLY_NAME = re.compile(r"^reply-(?P<seq>[0-9]+)\.json$")
MAX_REPLY_BYTES = 16_384


class RunnerError(Exception):
    """Fatal runner condition. Never carries collector or console content."""


def load_collector(name: str) -> types.ModuleType:
    """Import a collector by path, after `builtins.input` is already bound.

    Collector filenames contain hyphens, so they are not importable by name.
    """
    path = ROOT / "tools" / COLLECTORS[name]
    if path.is_symlink() or not path.is_file():
        raise RunnerError("collector path is not a regular file")
    spec = importlib.util.spec_from_file_location(f"collector_{name}", path)
    if spec is None or spec.loader is None:
        raise RunnerError("collector could not be loaded")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so a collector importing itself resolves.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SessionChannel:
    """The file-backed replacement for a controlling terminal.

    One prompt is open at a time, numbered from 1. The runner writes the open
    prompt and blocks until the matching reply appears; anything else is
    refused.
    """

    def __init__(self, session: Path) -> None:
        self.session = session
        self.seq = 0
        self.prompt_path = session / "prompt.json"
        self.status_path = session / "status.json"

    # -- state files -----------------------------------------------------

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        """Publish atomically: a reader must never see a half-written file."""
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.chmod(tmp, 0o600)
        tmp.replace(path)

    def write_status(self, state: str, **extra: Any) -> None:
        """Record run state.

        `pid` is included so a reader can tell a live run from a crashed one
        without parsing a transcript: a status of `awaiting_input` whose pid is
        gone from the process table is a dead run, and its window may still be
        open on the control plane.
        """
        self._write_json(
            self.status_path,
            {
                "state": state,
                "pid": os.getpid(),
                "open_prompt_seq": self.seq if state == "awaiting_input" else None,
                **extra,
            },
        )

    # -- the input_fn ----------------------------------------------------

    def _refuse_staged_replies(self, opening: int) -> None:
        """Fail closed if any reply for this prompt or a later one already exists.

        This is what makes pre-staging impossible rather than merely
        discouraged. An operator who wrote every answer before the window
        opened would otherwise produce a conforming-looking record whose
        readings were never read.
        """
        for entry in self.session.iterdir():
            match = REPLY_NAME.match(entry.name)
            if match and int(match.group("seq")) >= opening:
                raise RunnerError(
                    f"reply for prompt {match.group('seq')} existed before that "
                    "prompt was opened; readings cannot be staged in advance"
                )

    def _classify(self, prompt: str) -> tuple[str, str | None]:
        if prompt == READING_PROMPT:
            return "console_reading", None
        pause = PAUSE_PROMPT.match(prompt)
        if pause:
            return "operator_pause", pause.group("phrase")
        # An unrecognized prompt is still answerable as free text; the
        # collector, not this runner, decides whether the answer is acceptable.
        return "text", None

    def _read_reply(self, path: Path) -> str:
        if path.is_symlink():
            raise RunnerError("reply is a symlink")
        if path.stat().st_size > MAX_REPLY_BYTES:
            raise RunnerError("reply exceeds the byte limit")
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            raise RunnerError(f"reply is not valid JSON: {error.msg}") from None
        if not isinstance(payload, dict):
            raise RunnerError("reply is not a JSON object")
        # The seq inside the file must agree with the filename, so a renamed
        # file cannot answer a prompt it was not written for.
        if payload.get("seq") != self.seq:
            raise RunnerError("reply seq does not match the open prompt")
        value = payload.get("value")
        if not isinstance(value, str):
            raise RunnerError("reply value is not a string")
        return value

    def ask(self, prompt: str) -> str:
        """Block until the operator answers the prompt now being opened.

        The collector stamps `captured_before_at` immediately before calling
        this and `captured_after_at` immediately after, so the operator's real
        think time is what ends up bracketing each reading. Nothing here
        pre-fills, caches or auto-answers; a slow reading is truthful.
        """
        self.seq += 1
        self._refuse_staged_replies(self.seq)
        kind, phrase = self._classify(prompt)
        self._write_json(
            self.prompt_path,
            {
                "seq": self.seq,
                "prompt_text": prompt,
                "kind": kind,
                "expected_acknowledgement": phrase,
                "opened_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        self.write_status("awaiting_input")
        reply_path = self.session / f"reply-{self.seq}.json"
        while not reply_path.exists():
            time.sleep(POLL_SECONDS)
        value = self._read_reply(reply_path)
        self.prompt_path.unlink(missing_ok=True)
        self.write_status("running")
        return value


def prepare_session(path: Path) -> Path:
    """Create a fresh root-owned 0700 session directory.

    Refuses to reuse one: a second run writing into a directory that already
    holds a prompt or replies could answer the wrong window.
    """
    if path.is_symlink():
        raise RunnerError("session directory is a symlink")
    try:
        path.mkdir(mode=0o700, parents=False)
    except FileExistsError:
        raise RunnerError("session directory already exists") from None
    except OSError as error:
        if error.errno == errno.ENOENT:
            raise RunnerError("session directory parent does not exist") from None
        raise
    os.chown(path, 0, 0)
    os.chmod(path, 0o700)
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Drive an attended collector from files instead of a terminal."
    )
    parser.add_argument("--collector", required=True, choices=sorted(COLLECTORS))
    parser.add_argument("--session-dir", required=True, type=Path)
    parser.add_argument(
        "collector_args",
        nargs=argparse.REMAINDER,
        help="arguments passed to the collector unchanged, after --",
    )
    return parser


def main() -> int:
    if os.geteuid() != 0:
        raise RunnerError("attended collector runner must run as root")
    os.umask(0o077)
    args = build_parser().parse_args()

    passthrough = list(args.collector_args)
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    if not passthrough:
        raise RunnerError("no collector arguments supplied")

    session = prepare_session(args.session_dir.resolve())
    channel = SessionChannel(session)
    channel.write_status("running")

    # Bind before import: the collectors' `input_fn` defaults are evaluated at
    # definition time, so this is what makes every call site use the channel.
    real_input = builtins.input
    builtins.input = channel.ask
    try:
        module = load_collector(args.collector)
        collector_name = COLLECTORS[args.collector]
        sys.argv = [collector_name, *passthrough]
        code = module.main()
    except RunnerError as error:
        channel.write_status("failed", reason=str(error))
        raise
    except BaseException as error:
        # The collector writes its own terminal record on the failure path,
        # including the restoration prompt. Record only that the runner saw a
        # non-clean exit; the collector's record is the authority on why.
        channel.write_status("failed", reason=error.__class__.__name__)
        raise
    finally:
        builtins.input = real_input
        channel.prompt_path.unlink(missing_ok=True)

    channel.write_status("complete" if code == 0 else "failed", exit_code=code)
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as error:
        print(f"attended collector runner: {error}", file=sys.stderr)
        raise SystemExit(2) from None
