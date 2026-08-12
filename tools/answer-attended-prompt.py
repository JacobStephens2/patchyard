#!/usr/bin/env python3
"""Answer the open prompt of an attended collector run, from one terminal.

`attended-collector-runner.py` replaces the collector's terminal with a session
directory: the open prompt in `prompt.json`, the answer in
`replies/reply-<seq>.json`. That is the right shape for a durable run, but it
leaves the operator hand-assembling two layers of JSON - the console reading,
and the envelope it travels in - usually by copying a wrapped line between two
panes on two hosts. A live run on 2026-08-10 spent an hour on that, and an
earlier one was rejected outright for sending the string "Uploaded JWKS" where
`true` was required.

This is the terminal equivalent of the `/collectors` form: it reads the open
prompt, asks for one field at a time, parses `true` into a boolean rather than
a string, shows the exact JSON before anything is written, and publishes the
reply atomically under the sequence number the run is actually waiting on.

What it deliberately does not do
--------------------------------
**It never offers a previous answer as a default.** Reading 4 of the revocation
collector means "the console state while the mapping is still removed", and its
whole evidentiary value is that a human looked again. A tool that pre-filled
from reading 3 would make a record that passes every checker while attesting to
nothing, which is the exact failure `_refuse_staged_replies` exists to prevent.
Convenience stops where the attestation begins.

**It cannot answer a prompt that is not open.** The sequence number comes from
`prompt.json`, never from an argument, so there is no way to stage an answer
ahead or to reply to a window that has already closed.

**It does not validate readings.** Shape help is guidance; the collector is the
instrument and judges what it is given. Passing the parse here means the JSON is
well-formed, not that the reading is acceptable.

Reading `prompt.json` needs either root or membership of the run's reply group.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
STAGING_ROOT = Path("/run/patchyard-openai")

# The key set for a reading is a constant in the collector that will consume it.
# It is read with `ast`, not by importing: importing a collector runs its
# module body, which rebinds the lifecycle staging root and digest-checks its
# own dependencies. Nothing here should have those side effects.
COLLECTOR_KEY_SETS = {
    "openai-wif-federation-revocation.py": "MAPPING_STATE_KEYS",
    "openai-wif-signing-key-rotation.py": "ROTATION_STATE_KEYS",
}

LEGEND = """\
  true / false   -> boolean        (not the string "true")
  (blank)        -> null           (not an empty string)
  [ ... / { ...  -> parsed as JSON (for list or object fields)
  anything else  -> string
"""


class AnswerError(RuntimeError):
    """The prompt could not be answered. Nothing has been written."""


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise AnswerError(f"{path} does not exist") from None
    except PermissionError:
        raise AnswerError(
            f"cannot read {path}; run as root, or as a member of the run's "
            "reply group once the group-readable state fix is deployed"
        ) from None
    except json.JSONDecodeError as error:
        raise AnswerError(f"{path} is not valid JSON: {error.msg}") from None


def collector_keys(collector_file: str) -> list[str] | None:
    """Return the reading keys a collector requires, or None if unknown.

    Unknown is not fatal: a collector this tool has not been taught about can
    still be answered, just without per-field prompting.
    """
    constant = COLLECTOR_KEY_SETS.get(collector_file)
    if constant is None:
        return None
    source = (ROOT / "tools" / collector_file).read_text()
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == constant:
                return sorted(ast.literal_eval(node.value))
    raise AnswerError(f"{constant} not found in {collector_file}")


def parse_field(raw: str) -> Any:
    """Turn one typed line into a JSON value, per LEGEND."""
    text = raw.strip()
    if text == "":
        return None
    if text in {"true", "false"}:
        return text == "true"
    if text[0] in "[{":
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise AnswerError(f"value looks like JSON but is not: {error.msg}") from None
    return text


def discover_session(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    waiting = []
    for entry in sorted(STAGING_ROOT.glob("*/")):
        status_path = entry / "status.json"
        if not status_path.exists():
            continue
        try:
            status = json.loads(status_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if status.get("state") == "awaiting_input":
            waiting.append(entry)
    if not waiting:
        raise AnswerError(
            "no session under /run/patchyard-openai is awaiting input; "
            "pass --session if you know the path"
        )
    if len(waiting) > 1:
        names = ", ".join(entry.name for entry in waiting)
        raise AnswerError(f"more than one session is awaiting input: {names}")
    return waiting[0]


def compose_reading(keys: list[str] | None) -> str:
    """Ask for one field at a time and return the reading as a JSON string."""
    print("\nRead the console now. Every field is a fresh reading.")
    print("Parsing:")
    print(LEGEND)
    if keys is None:
        print("This collector's key set is unknown here. Paste the whole reading.")
        return input("reading JSON> ").strip()

    reading: dict[str, Any] = {}
    for key in keys:
        reading[key] = parse_field(input(f"  {key}> "))
    return json.dumps(reading)


def publish(session: Path, seq: int, value: str) -> Path:
    """Write the reply atomically, refusing to overwrite an answered prompt."""
    final = session / "replies" / f"reply-{seq}.json"
    if final.exists():
        raise AnswerError(f"{final} already exists; that prompt is answered")
    tmp = final.with_suffix(".json.tmp")
    # The runner polls on existence, so a partially written file would be read
    # and fail the run. Rename is atomic within the directory.
    tmp.write_text(json.dumps({"seq": seq, "value": value}))
    os.replace(tmp, final)
    return final


def confirm(question: str) -> bool:
    return input(f"{question} [type yes to continue] ").strip() == "yes"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Answer the open prompt of an attended collector run."
    )
    parser.add_argument("--session", type=Path, default=None)
    parser.add_argument(
        "--collector-file",
        default="openai-wif-federation-revocation.py",
        choices=sorted(COLLECTOR_KEY_SETS),
        help="which collector is running; selects the reading key set",
    )
    args = parser.parse_args()

    session = discover_session(args.session)
    status = read_json(session / "status.json")
    if status.get("state") != "awaiting_input":
        raise AnswerError(f"run state is {status.get('state')!r}, not awaiting_input")

    prompt = read_json(session / "prompt.json")
    seq = prompt["seq"]
    if seq != status.get("open_prompt_seq"):
        raise AnswerError("prompt.json and status.json disagree about the open prompt")

    print(f"session : {session.name}")
    print(f"prompt  : seq {seq}, opened {prompt['opened_at']}, kind {prompt['kind']}")

    acknowledgement = prompt.get("expected_acknowledgement")
    if acknowledgement:
        print(f"\nThis is an acknowledgement, not a reading.")
        print(f"It sends: {acknowledgement}")
        print("Complete the console change FIRST. Acknowledging before the actor")
        print("has finished records a mutation that has not happened.")
        if not confirm("Has the console change been made?"):
            print("nothing written")
            return 1
        value = acknowledgement
    else:
        value = compose_reading(collector_keys(args.collector_file))
        print("\nExact JSON to be submitted:")
        print(f"  {value}")
        if not confirm("Submit this reading?"):
            print("nothing written")
            return 1

    written = publish(session, seq, value)
    print(f"submitted seq={seq} -> {written}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AnswerError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
    except (KeyboardInterrupt, EOFError):
        print("\naborted; nothing written", file=sys.stderr)
        sys.exit(130)
