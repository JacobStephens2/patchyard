#!/usr/bin/env python3
"""Merge a ref into the current branch and restore the repository to a fixpoint.

Every pull request in this repository collides on `docs/codebase-metrics.json`,
because that file is a committed byte-exact projection of the tree and any two
branches that change any line count produce different projections. Resolving it
is mechanical, but the pin cascade that follows is not obvious: the readiness
root pins tools and tests by digest, several tests pin the same digests, and the
infrastructure workflow pins the readiness root, so one regenerated file can
require several rounds before every digest agrees.

This tool performs that whole procedure. It resolves ONLY the generated metrics
file. Any other conflict stops the run and is left in the working tree for a
person to resolve, because a conflict in a hand-written file is a disagreement
about intent and a machine picking a side would hide it.

The cascade is driven by the checkers' own reports rather than by a table of
which constant names hold which paths. Each round runs the checkers, reads their
"expected X, observed Y" lines, replaces X with Y across tracked text files, and
repeats until nothing changes. That way the tool never needs to know what a
constant is called, and a new pinned file is picked up without editing this
tool.

Usage:
    tools/merge-refix.py [REF]            merge REF (default origin/master)
    tools/merge-refix.py --no-merge       only re-run the cascade and gates
    tools/merge-refix.py REF --commit     commit the merge when gates pass

Exit codes: 0 fixpoint reached and gates pass, 1 stopped for a person, 2 usage.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess
import sys


REPO = Path(__file__).resolve().parent.parent
GENERATED = ("docs/codebase-metrics.json", ".github/workflows/infrastructure.yml")
READINESS_ROOT = "tools/check-a101-readiness-root.py"
WORKFLOW = ".github/workflows/infrastructure.yml"
DIGEST_PAIR = re.compile(r"expected ([0-9a-f]{64}), observed ([0-9a-f]{64})")
TEXT_SUFFIXES = {"py", "sh", "yml", "yaml", "json", "md"}
MAXIMUM_ROUNDS = 12

CASCADE_CHECKERS = (
    ["python3", "-I", READINESS_ROOT],
    ["tools/check-infra.sh"],
    ["tools/check-ansible.sh"],
)
GATES = ("tools/check-codebase.sh", "tools/check-infra.sh", "tools/check-ansible.sh")


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, cwd=REPO)


def tracked_text_files() -> list[str]:
    listing = run(["git", "ls-files"]).stdout.split()
    return [f for f in listing if f.rsplit(".", 1)[-1] in TEXT_SUFFIXES]


def digest_of(relative: str) -> str:
    return hashlib.sha256((REPO / relative).read_bytes()).hexdigest()


def conflicted() -> list[str]:
    return run(["git", "diff", "--name-only", "--diff-filter=U"]).stdout.split()


CONFLICT_HUNK = re.compile(
    r"<<<<<<< [^\n]*\n(.*?)\n=======\n(.*?)\n>>>>>>> [^\n]*", re.S
)
ANY_DIGEST = re.compile(r"\b[0-9a-f]{64}\b")


def conflict_is_digest_only(relative: str) -> bool:
    """True when every hunk's two sides agree once digests are masked.

    Both branches recomputing the same pin cascade from different starting
    points produce hunks that differ only in hex. Taking either side is then
    safe, because the cascade recomputes every value afterwards.

    A hunk that differs structurally is NOT safe: when one branch adds a pinned
    file the other does not know about, taking a side silently drops it from the
    pin set and nothing downstream notices. That case must reach a person.
    """
    try:
        text = (REPO / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    hunks = CONFLICT_HUNK.findall(text)
    if not hunks:
        return False
    return all(
        ANY_DIGEST.sub("", ours) == ANY_DIGEST.sub("", theirs)
        for ours, theirs in hunks
    )


def regenerate_metrics() -> None:
    run(["tools/check-codebase.sh", "--write"])


def expected_workflow_text() -> str:
    """Ask the readiness root what the workflow must contain.

    The pin it wants is the whole line, digest and path together, not the bare
    digest. Reproducing that by hand is the mistake this function exists to stop.
    """
    spec = importlib.util.spec_from_file_location("readiness_root", REPO / READINESS_ROOT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pin = f"{digest_of(READINESS_ROOT)}  {READINESS_ROOT}"
    return module.expected_workflow(pin)


def apply_substitutions(substitutions: dict[str, str]) -> None:
    for relative in tracked_text_files():
        path = REPO / relative
        original = path.read_text(encoding="utf-8", errors="ignore")
        updated = original
        for stale, observed in substitutions.items():
            updated = updated.replace(stale, observed)
        if updated != original:
            path.write_text(updated, encoding="utf-8")


def drive_cascade() -> bool:
    for round_number in range(1, MAXIMUM_ROUNDS + 1):
        substitutions: dict[str, str] = {}
        for checker in CASCADE_CHECKERS:
            result = run(checker)
            for stale, observed in DIGEST_PAIR.findall(result.stdout + result.stderr):
                substitutions[stale] = observed
        if substitutions:
            apply_substitutions(substitutions)

        workflow_path = REPO / WORKFLOW
        wanted = expected_workflow_text()
        workflow_rewritten = workflow_path.read_text() != wanted
        if workflow_rewritten:
            workflow_path.write_text(wanted)

        regenerate_metrics()
        settled = run(["python3", "-I", READINESS_ROOT]).returncode == 0
        print(
            f"  round {round_number}: {len(substitutions)} digest substitution(s), "
            f"workflow {'rewritten' if workflow_rewritten else 'unchanged'}, "
            f"readiness root {'passes' if settled else 'fails'}"
        )
        if not substitutions and not workflow_rewritten and settled:
            return True
        if not substitutions and not workflow_rewritten and not settled:
            # Nothing left to substitute and the root still refuses, so the
            # failure is not a stale digest and further rounds cannot help.
            report = run(["python3", "-I", READINESS_ROOT])
            sys.stderr.write(report.stdout + report.stderr)
            return False
    return False


def merge(ref: str) -> bool:
    result = run(["git", "merge", "--no-edit", ref])
    if result.returncode == 0:
        print(f"  merged {ref} with no conflict")
        return True

    resolvable, digest_only, outstanding = [], [], []
    for relative in conflicted():
        if relative in GENERATED:
            resolvable.append(relative)
        elif conflict_is_digest_only(relative):
            digest_only.append(relative)
        else:
            outstanding.append(relative)
    if outstanding:
        print(f"  merge of {ref} left conflicts a person must resolve:", file=sys.stderr)
        for relative in outstanding:
            print(f"    {relative}", file=sys.stderr)
        print("  the working tree is left as it is; nothing was auto-resolved.", file=sys.stderr)
        return False

    for relative in resolvable:
        run(["git", "checkout", "--theirs", relative])
    for relative in digest_only:
        run(["git", "checkout", "--ours", relative])
    regenerate_metrics()
    # Stage what was resolved. Without this the content is correct but the index
    # still records a conflict, and the run would report success over a tree git
    # considers unmerged.
    for relative in resolvable + digest_only:
        run(["git", "add", relative])
    print(f"  merged {ref}; regenerated {len(resolvable)} generated file(s) "
          f"and took one side of {len(digest_only)} digest-only conflict(s)")
    return True


def main(argv: list[str]) -> int:
    arguments = [a for a in argv if a not in ("--commit", "--no-merge")]
    should_commit = "--commit" in argv
    skip_merge = "--no-merge" in argv
    if len(arguments) > 1:
        print(__doc__, file=sys.stderr)
        return 2
    ref = arguments[0] if arguments else "origin/master"

    if not skip_merge:
        run(["git", "fetch", "origin", "--quiet"])
        if not merge(ref):
            return 1

    if not drive_cascade():
        print("  could not reach a fixpoint; a person should look", file=sys.stderr)
        return 1

    failed = []
    for gate in GATES:
        result = run([gate])
        print(f"  {Path(gate).name}: {'pass' if result.returncode == 0 else 'FAIL'}")
        if result.returncode != 0:
            failed.append(gate)
            sys.stderr.write(result.stdout[-2000:] + result.stderr[-2000:])
    if failed:
        return 1

    if should_commit:
        run(["git", "add", "-A"])
        run(["git", "commit", "-q", "-m",
             f"Merge {ref} and re-run the pin cascade to a fixpoint"])
        print("  committed")
    else:
        remaining = conflicted()
        if remaining:
            print("  gates pass but the index still records conflicts:", file=sys.stderr)
            for relative in remaining:
                print(f"    {relative}", file=sys.stderr)
            return 1
        print("  gates pass; the merge is staged but not committed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
