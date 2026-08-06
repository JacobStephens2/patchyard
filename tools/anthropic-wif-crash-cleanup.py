#!/usr/bin/env python3
"""Run and collect the A130 Anthropic crash-cleanup proof.

The qualified expiry harness is loaded by exact digest and is never modified.
This adapter holds a live bearer in a child process until an attended SIGKILL,
searches one fixed run-scoped tmpfs surface, and assembles only sanitized local
evidence.  It never claims or attempts provider-side bearer invalidation.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys
import types
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
BASE_HARNESS_PATH = ROOT / "tools/anthropic-wif-lifecycle.py"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
CHECKER_PATHS = (
    ROOT / "tools/check-anthropic-expiry.py",
    ROOT / "tools/check-anthropic-revocation.py",
    ROOT / "tools/check-anthropic-crash-cleanup.py",
)
SUPERVISOR_CEILING_SECONDS = 360
MAX_SCAN_FILES = 128
MAX_SCAN_FILE_BYTES = 1_000_000
MAX_SCAN_TOTAL_BYTES = 8_000_000
MATERIAL_PATTERNS = (
    (
        "anthropic_bearer",
        re.compile(rb"sk-ant-oat01-[A-Za-z0-9_-]+"),
    ),
    (
        "jwt_assertion",
        re.compile(rb"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    ),
    (
        "private_key",
        re.compile(
            rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"
        ),
    ),
)
SEARCH_CONTRACT_VERSION = "a130-run-stage-regular-files-v1"
TERMINAL_FIELDS = {
    "failed_at",
    "failure_phase",
    "failure_reason",
    "failure_type",
    "partial_evidence",
    "post_failure_state",
}


def load_base_harness() -> types.ModuleType:
    source = BASE_HARNESS_PATH.read_bytes()
    if (
        BASE_HARNESS_PATH.is_symlink()
        or hashlib.sha256(source).hexdigest() != BASE_HARNESS_SHA256
    ):
        raise RuntimeError("qualified expiry harness differs from its exact binding")
    module = types.ModuleType("anthropic_wif_lifecycle_crash_base")
    module.__file__ = str(BASE_HARNESS_PATH)
    module.__package__ = None
    exec(
        compile(source, str(BASE_HARNESS_PATH), "exec", dont_inherit=True),
        module.__dict__,
    )
    return module


BASE = load_base_harness()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def source_binding() -> dict[str, str]:
    return {
        "policy_sha256": BASE.digest_file(BASE.POLICY_PATH),
        "lifecycle_harness_sha256": BASE.digest_file(BASE_HARNESS_PATH),
        "crash_harness_sha256": BASE.digest_file(Path(__file__).resolve()),
    }


def require_stage_file(path: Path, stage: Path, label: str) -> None:
    BASE.require_stage_path(path, stage, label)
    if path.name in {".", ".."}:
        raise BASE.LifecycleError(f"{label} has an invalid name")


def load_bounded_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise BASE.LifecycleError(f"{label} is not a regular non-symlink file")
    metadata = path.stat()
    if not 1 <= metadata.st_size <= MAX_SCAN_FILE_BYTES:
        raise BASE.LifecycleError(f"{label} is outside the byte limit")
    value = BASE.load_json_file(path)
    if not isinstance(value, dict):
        raise BASE.LifecycleError(f"{label} is not a JSON object")
    return value


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    BASE.validate_new_output_path(path)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    try:
        BASE.write_all(descriptor, BASE.encoded_json(value))
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def process_start_ticks(pid: int) -> int | None:
    try:
        record = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return None
    closing = record.rfind(")")
    if closing < 0:
        raise BASE.LifecycleError("target process stat record is malformed")
    fields = record[closing + 2 :].split()
    if len(fields) <= 19 or not fields[19].isdigit():
        raise BASE.LifecycleError("target process start time is malformed")
    return int(fields[19])


def target_process_present(pid: int, start_ticks: int) -> bool:
    observed = process_start_ticks(pid)
    return observed is not None and observed == start_ticks


def remove_staged_key(path: Path, stage: Path) -> str:
    """Remove the run-scoped key and durably record the directory mutation."""

    require_stage_file(path, stage, "crash signing key")
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise BASE.LifecycleError("crash signing key is not a regular non-symlink file")
    path.unlink()
    directory = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    if path.exists() or path.is_symlink():
        raise BASE.LifecycleError("crash signing key remains after cleanup")
    return iso_time(utc_now())


def swap_entry_count() -> int:
    lines = Path("/proc/swaps").read_text().splitlines()
    if not lines or not lines[0].startswith("Filename"):
        raise BASE.LifecycleError("kernel swap inventory is malformed")
    return len(lines) - 1


def disable_core_dumps() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if resource.getrlimit(resource.RLIMIT_CORE) != (0, 0):
        raise BASE.LifecycleError("credential scanner core dumps remain enabled")


def search_contract(stage: Path, pid: int, start_ticks: int) -> dict[str, Any]:
    return {
        "version": SEARCH_CONTRACT_VERSION,
        "stage_path": str(stage),
        "target_pid": pid,
        "target_start_ticks": start_ticks,
        "file_scope": "all-recursive-regular-files-no-symlinks",
        "material_classes": [name for name, _ in MATERIAL_PATTERNS],
        "max_files": MAX_SCAN_FILES,
        "max_file_bytes": MAX_SCAN_FILE_BYTES,
        "max_total_bytes": MAX_SCAN_TOTAL_BYTES,
    }


def scan_stage(stage: Path, pid: int, start_ticks: int) -> dict[str, Any]:
    """Search one exact surface without recording matched credential bytes."""

    contract = search_contract(stage, pid, start_ticks)
    core_limits = resource.getrlimit(resource.RLIMIT_CORE)
    if core_limits != (0, 0):
        raise BASE.LifecycleError("credential scanner core dumps are not disabled")
    swap_entries = swap_entry_count()
    if swap_entries != 0:
        raise BASE.LifecycleError("credential scanner refuses a host with swap")
    files: list[Path] = []
    for path in sorted(stage.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise BASE.LifecycleError("credential search refuses a symlink")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise BASE.LifecycleError("credential search refuses a special file")
        files.append(path)
    if len(files) > MAX_SCAN_FILES:
        raise BASE.LifecycleError("credential search file count exceeds the bound")

    bytes_examined = 0
    matches: list[dict[str, Any]] = []
    for path in files:
        metadata = path.stat()
        if metadata.st_size > MAX_SCAN_FILE_BYTES:
            raise BASE.LifecycleError("credential search file exceeds the byte bound")
        bytes_examined += metadata.st_size
        if bytes_examined > MAX_SCAN_TOTAL_BYTES:
            raise BASE.LifecycleError("credential search surface exceeds the byte bound")
        value = path.read_bytes()
        for material_class, pattern in MATERIAL_PATTERNS:
            occurrences = len(pattern.findall(value))
            if occurrences:
                matches.append(
                    {
                        "material_class": material_class,
                        "relative_path": path.relative_to(stage).as_posix(),
                        "occurrences": occurrences,
                    }
                )

    matches.sort(key=lambda item: (item["relative_path"], item["material_class"]))
    classes = sorted({item["material_class"] for item in matches})
    return {
        "schema_version": 1,
        "provider": "anthropic",
        "event_type": "credential_surface_search",
        "observed_at": iso_time(utc_now()),
        "search_contract": contract,
        "search_contract_sha256": BASE.digest_bytes(
            json.dumps(contract, separators=(",", ":"), sort_keys=True).encode()
        ),
        "files_examined": len(files),
        "bytes_examined": bytes_examined,
        "credential_material_found": bool(matches),
        "material_classes_found": classes,
        "matches": matches,
        "target_process_present": target_process_present(pid, start_ticks),
        "scanner_core_dump_limits": list(core_limits),
        "swap_entries": swap_entries,
        "source": source_binding(),
    }


def checkpoint_identity(value: dict[str, Any]) -> tuple[int, int]:
    pid = value.get("target_pid")
    start_ticks = value.get("target_start_ticks")
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 1
        or not isinstance(start_ticks, int)
        or isinstance(start_ticks, bool)
        or start_ticks <= 0
    ):
        raise BASE.LifecycleError("crash checkpoint process identity is malformed")
    return pid, start_ticks


def validate_positive_search(
    value: dict[str, Any], stage: Path, pid: int, start_ticks: int
) -> None:
    if value.get("event_type") != "credential_surface_search":
        raise BASE.LifecycleError("positive control is not a credential search")
    if value.get("search_contract") != search_contract(stage, pid, start_ticks):
        raise BASE.LifecycleError("positive control searched a different surface")
    if value.get("target_process_present") is not True:
        raise BASE.LifecycleError("positive control did not observe the live process")
    if value.get("scanner_core_dump_limits") != [0, 0]:
        raise BASE.LifecycleError("positive-control scanner core dumps were enabled")
    if value.get("swap_entries") != 0:
        raise BASE.LifecycleError("positive control observed configured swap")
    if value.get("credential_material_found") is not True:
        raise BASE.LifecycleError("positive control found no credential material")
    if value.get("material_classes_found") != ["private_key"]:
        raise BASE.LifecycleError("positive control did not isolate the staged private key")
    if value.get("matches") != [
        {
            "material_class": "private_key",
            "relative_path": "replacement.pem",
            "occurrences": 1,
        }
    ]:
        raise BASE.LifecycleError("positive control did not find the exact staged key")
    if value.get("source") != source_binding():
        raise BASE.LifecycleError("positive control source binding differs")


def validate_post_kill_search(
    value: dict[str, Any], stage: Path, pid: int, start_ticks: int
) -> None:
    if value.get("event_type") != "credential_surface_search":
        raise BASE.LifecycleError("post-kill result is not a credential search")
    if value.get("search_contract") != search_contract(stage, pid, start_ticks):
        raise BASE.LifecycleError("post-kill search used a different surface")
    if value.get("target_process_present") is not False:
        raise BASE.LifecycleError("killed credential process remains present")
    if value.get("scanner_core_dump_limits") != [0, 0]:
        raise BASE.LifecycleError("post-kill scanner core dumps were enabled")
    if value.get("swap_entries") != 0:
        raise BASE.LifecycleError("post-kill search observed configured swap")
    if value.get("credential_material_found") is not False:
        raise BASE.LifecycleError("post-kill search recovered credential material")
    if value.get("material_classes_found") != [] or value.get("matches") != []:
        raise BASE.LifecycleError("post-kill search has credential matches")
    if value.get("source") != source_binding():
        raise BASE.LifecycleError("post-kill search source binding differs")


def failed_record(
    action: str,
    run_id: str,
    started_at: str,
    phase: str,
    error: BaseException,
    post_failure_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": "anthropic",
        "status": "failed",
        "action": action,
        "run_id": run_id,
        "started_at": started_at,
        "failed_at": iso_time(utc_now()),
        "failure_type": error.__class__.__name__,
        "failure_reason": BASE.safe_failure_reason(error),
        "failure_phase": phase,
        "partial_evidence": {},
        "post_failure_state": post_failure_state or {},
        "source": source_binding(),
    }


def run_probe(args: argparse.Namespace) -> int:
    run_id = args.run_id
    stage = BASE.validate_stage_directory(run_id)
    for path, label in (
        (args.signing_key, "crash signing key"),
        (args.attempt_output, "crash attempt output"),
        (args.checkpoint_output, "crash checkpoint output"),
    ):
        require_stage_file(path, stage, label)
    BASE.require_equal(
        args.signing_key.resolve(strict=True),
        stage / "replacement.pem",
        "crash signing-key path",
    )
    started_at = iso_time(utc_now())
    output = BASE.ReservedOutput(
        args.attempt_output,
        {
            "schema_version": 1,
            "provider": "anthropic",
            "status": "in_progress",
            "action": "crash-cleanup-probe",
            "run_id": run_id,
            "started_at": started_at,
            "source": source_binding(),
        },
    )
    phase = "local_preflight"
    try:
        disable_core_dumps()
        if swap_entry_count() != 0:
            raise BASE.LifecycleError("credential process refuses a host with swap")
        BASE.validate_root_private_key(args.signing_key)
        active = BASE.jwk_descriptor(BASE.load_public_jwk(BASE.ACTIVE_SIGNING_KEY))
        staged = BASE.jwk_descriptor(BASE.load_public_jwk(args.signing_key))
        if active == staged:
            raise BASE.LifecycleError("crash proof key is not distinct from the active key")
        policy = BASE.load_policy()

        def progress(value: str, observation: dict[str, Any] | None) -> None:
            del observation
            nonlocal phase
            phase = value

        exchange, token = BASE.accepted_exchange(
            policy,
            args.signing_key,
            run_id,
            progress=progress,
        )
        phase = "bearer_live_before_terminal_write"
        pid = os.getpid()
        start_ticks = process_start_ticks(pid)
        if start_ticks is None:
            raise BASE.LifecycleError("credential process identity disappeared")
        checkpoint = {
            "schema_version": 1,
            "provider": "anthropic",
            "run_id": run_id,
            "phase": phase,
            "observed_at": iso_time(utc_now()),
            "target_pid": pid,
            "target_start_ticks": start_ticks,
            "bearer_live": True,
            "terminal_record_written": False,
            "core_dump_limits": [0, 0],
            "swap_entries": 0,
            "signing_key": exchange["key"],
            "issuance": exchange["exchange"],
            "attempt_sha256": BASE.digest_file(args.attempt_output),
            "source": source_binding(),
        }
        write_new_json(args.checkpoint_output, checkpoint)
        print(
            f"anthropic_crash_cleanup_ready pid={pid} checkpoint={args.checkpoint_output}",
            flush=True,
        )
        while token:
            signal.pause()
        raise BASE.LifecycleError("credential bearer was released without SIGKILL")
    except BaseException as error:
        output.finish(
            failed_record(
                "crash-cleanup-probe",
                run_id,
                started_at,
                phase,
                error,
                {"credential_process_exiting": True},
            )
        )
        raise


def run_supervise(args: argparse.Namespace) -> int:
    run_id = args.run_id
    stage = BASE.validate_stage_directory(run_id)
    for path, label in (
        (args.signing_key, "crash signing key"),
        (args.attempt_output, "crash attempt output"),
        (args.checkpoint_output, "crash checkpoint output"),
        (args.positive_control, "positive-control output"),
        (args.kill_output, "kill observation output"),
    ):
        require_stage_file(path, stage, label)
    started_at = iso_time(utc_now())
    output = BASE.ReservedOutput(
        args.kill_output,
        {
            "schema_version": 1,
            "provider": "anthropic",
            "status": "in_progress",
            "action": "crash-cleanup-supervise",
            "run_id": run_id,
            "started_at": started_at,
            "source": source_binding(),
        },
    )
    phase = "credential_process_start"
    child: subprocess.Popen[bytes] | None = None
    signing_key_cleanup_succeeded = False
    try:
        command = [
            sys.executable,
            "-I",
            str(Path(__file__).resolve()),
            "_probe",
            "--run-id",
            run_id,
            "--signing-key",
            str(args.signing_key),
            "--attempt-output",
            str(args.attempt_output),
            "--checkpoint-output",
            str(args.checkpoint_output),
        ]
        child = subprocess.Popen(command, env=BASE.credential_free_env())
        print(f"anthropic_crash_cleanup_supervisor child_pid={child.pid}", flush=True)
        phase = "awaiting_attended_sigkill"
        timed_out = False
        try:
            returncode = child.wait(timeout=SUPERVISOR_CEILING_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            child.kill()
            returncode = child.wait()
        exited_at = iso_time(utc_now())
        signing_key_removed_at = remove_staged_key(args.signing_key, stage)
        signing_key_cleanup_succeeded = True
        phase = "kill_observation_validation"
        checkpoint = load_bounded_json(args.checkpoint_output, "crash checkpoint")
        pid, start_ticks = checkpoint_identity(checkpoint)
        if pid != child.pid:
            raise BASE.LifecycleError("checkpoint names a different credential process")
        positive = load_bounded_json(args.positive_control, "positive control")
        validate_positive_search(positive, stage, pid, start_ticks)
        positive_time = datetime.fromisoformat(
            str(positive["observed_at"]).replace("Z", "+00:00")
        )
        exit_time = datetime.fromisoformat(exited_at.replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(
            str(checkpoint.get("issuance", {}).get("expires_at", "")).replace(
                "Z", "+00:00"
            )
        )
        if positive_time > exit_time:
            raise BASE.LifecycleError("positive control was captured after process death")
        if not exit_time < expires_at:
            raise BASE.LifecycleError("SIGKILL did not occur while the bearer was live")
        if timed_out:
            raise BASE.LifecycleError("attended SIGKILL was not observed before the ceiling")
        if returncode != -signal.SIGKILL:
            signal_name = (
                signal.Signals(-returncode).name if returncode < 0 else "not_signaled"
            )
            raise BASE.LifecycleError(
                f"credential process ended by {signal_name}, not SIGKILL"
            )
        if target_process_present(pid, start_ticks):
            raise BASE.LifecycleError("SIGKILL target process remains present")
        attempt_sha256 = BASE.digest_file(args.attempt_output)
        if attempt_sha256 != checkpoint.get("attempt_sha256"):
            raise BASE.LifecycleError("in-progress record changed after checkpoint")
        phase = "terminal_write"
        output.finish(
            {
                "schema_version": 1,
                "provider": "anthropic",
                "run_id": run_id,
                "event_type": "credential_process_sigkill_observed",
                "observed_at": exited_at,
                "target_pid": pid,
                "target_start_ticks": start_ticks,
                "signal_name": "SIGKILL",
                "signal_number": int(signal.SIGKILL),
                "child_returncode": returncode,
                "supervisor_timed_out": False,
                "target_process_present": False,
                "signing_key_removed": True,
                "signing_key_present_after_cleanup": False,
                "signing_key_removed_at": signing_key_removed_at,
                "checkpoint_sha256": BASE.digest_file(args.checkpoint_output),
                "positive_control_sha256": BASE.digest_file(args.positive_control),
                "attempt_sha256": attempt_sha256,
                "source": source_binding(),
            }
        )
        return 0
    except BaseException as error:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
        cleanup_error: BaseException | None = None
        if args.signing_key.exists() or args.signing_key.is_symlink():
            try:
                remove_staged_key(args.signing_key, stage)
                signing_key_cleanup_succeeded = True
            except BaseException as observed_cleanup_error:
                cleanup_error = observed_cleanup_error
        key_present = args.signing_key.exists() or args.signing_key.is_symlink()
        if cleanup_error is not None:
            error = BASE.LifecycleError(
                f"{BASE.safe_failure_reason(error)}; signing-key cleanup failed: "
                f"{BASE.safe_failure_reason(cleanup_error)}"
            )
        output.finish(
            failed_record(
                "crash-cleanup-supervise",
                run_id,
                started_at,
                phase,
                error,
                {
                    "credential_process_present": (
                        child is not None and child.poll() is None
                    ),
                    "child_returncode": (
                        child.returncode if child is not None else None
                    ),
                    "signing_key_present": key_present,
                    "signing_key_cleanup_succeeded": signing_key_cleanup_succeeded,
                },
            )
        )
        raise


def run_scan(args: argparse.Namespace) -> int:
    run_id = args.run_id
    stage = BASE.validate_stage_directory(run_id)
    require_stage_file(args.checkpoint, stage, "crash checkpoint")
    require_stage_file(args.output, stage, "credential search output")
    checkpoint = load_bounded_json(args.checkpoint, "crash checkpoint")
    pid, start_ticks = checkpoint_identity(checkpoint)
    started_at = iso_time(utc_now())
    output = BASE.ReservedOutput(
        args.output,
        {
            "schema_version": 1,
            "provider": "anthropic",
            "status": "in_progress",
            "action": "crash-cleanup-scan",
            "run_id": run_id,
            "started_at": started_at,
            "source": source_binding(),
        },
    )
    try:
        disable_core_dumps()
        result = scan_stage(stage, pid, start_ticks)
        result["run_id"] = run_id
        output.finish(result)
    except BaseException as error:
        output.finish(
            failed_record(
                "crash-cleanup-scan", run_id, started_at, "surface_search", error
            )
        )
        raise
    print(
        "anthropic_crash_cleanup_scan "
        f"credential_material_found={str(result['credential_material_found']).lower()} "
        f"target_process_present={str(result['target_process_present']).lower()}",
        flush=True,
    )
    return 0


def checker_rejections(attempt_path: Path) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for checker in CHECKER_PATHS:
        if checker.is_symlink() or not checker.is_file():
            raise BASE.LifecycleError(f"qualification checker is missing: {checker.name}")
        completed = subprocess.run(
            [sys.executable, "-I", str(checker), "--evidence", str(attempt_path)],
            check=False,
            capture_output=True,
            timeout=30,
            env=BASE.credential_free_env(),
        )
        observations.append(
            {
                "checker": checker.name,
                "checker_sha256": BASE.digest_file(checker),
                "exit_code": completed.returncode,
                "accepted": completed.returncode == 0,
            }
        )
    if any(item["accepted"] for item in observations):
        raise BASE.LifecycleError("an Anthropic checker accepted the in-progress record")
    if any(item["exit_code"] != 1 for item in observations):
        raise BASE.LifecycleError("an Anthropic checker returned an unexpected rejection")
    return observations


def contains_credential_material(value: Any) -> bool:
    serialized = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return any(pattern.search(serialized) for _, pattern in MATERIAL_PATTERNS)


def run_collect(args: argparse.Namespace) -> int:
    run_id = args.run_id
    stage = BASE.validate_stage_directory(run_id)
    inputs = (
        (args.attempt, "in-progress attempt"),
        (args.checkpoint, "crash checkpoint"),
        (args.kill_observation, "kill observation"),
        (args.positive_control, "positive control"),
        (args.post_kill_search, "post-kill search"),
    )
    for path, label in (*inputs, (args.output, "crash-cleanup result")):
        require_stage_file(path, stage, label)
    started_at = iso_time(utc_now())
    output = BASE.ReservedOutput(
        args.output,
        {
            "schema_version": 1,
            "provider": "anthropic",
            "status": "in_progress",
            "action": "crash-cleanup-collect",
            "run_id": run_id,
            "started_at": started_at,
            "source": source_binding(),
        },
    )
    phase = "input_validation"
    try:
        attempt = load_bounded_json(args.attempt, "in-progress attempt")
        checkpoint = load_bounded_json(args.checkpoint, "crash checkpoint")
        kill = load_bounded_json(args.kill_observation, "kill observation")
        positive = load_bounded_json(args.positive_control, "positive control")
        post = load_bounded_json(args.post_kill_search, "post-kill search")
        pid, start_ticks = checkpoint_identity(checkpoint)
        validate_positive_search(positive, stage, pid, start_ticks)
        validate_post_kill_search(post, stage, pid, start_ticks)
        if positive.get("search_contract") != post.get("search_contract"):
            raise BASE.LifecycleError("positive and post-kill searches differ")
        if positive.get("search_contract_sha256") != post.get(
            "search_contract_sha256"
        ):
            raise BASE.LifecycleError("search instrument changed between controls")
        expected_attempt = {
            "schema_version": 1,
            "provider": "anthropic",
            "status": "in_progress",
            "action": "crash-cleanup-probe",
            "run_id": run_id,
            "started_at": attempt.get("started_at"),
            "source": source_binding(),
        }
        if attempt != expected_attempt:
            raise BASE.LifecycleError("abrupt-death record is not exact in-progress state")
        if TERMINAL_FIELDS.intersection(attempt):
            raise BASE.LifecycleError("in-progress record carries terminal fields")
        attempt_sha256 = BASE.digest_file(args.attempt)
        if not (
            checkpoint.get("attempt_sha256")
            == kill.get("attempt_sha256")
            == attempt_sha256
        ):
            raise BASE.LifecycleError("in-progress record was completed or relabelled")
        if kill.get("event_type") != "credential_process_sigkill_observed":
            raise BASE.LifecycleError("credential process has no SIGKILL observation")
        if kill.get("signal_name") != "SIGKILL" or kill.get("signal_number") != 9:
            raise BASE.LifecycleError("credential process was not terminated by SIGKILL")
        if (
            kill.get("child_returncode") != -9
            or kill.get("supervisor_timed_out") is not False
        ):
            raise BASE.LifecycleError("SIGKILL wait observation differs")
        if kill.get("target_process_present") is not False:
            raise BASE.LifecycleError("SIGKILL target remains present")
        if (
            kill.get("target_pid") != pid
            or kill.get("target_start_ticks") != start_ticks
        ):
            raise BASE.LifecycleError("SIGKILL observation names a different process")
        if kill.get("signing_key_removed") is not True or kill.get(
            "signing_key_present_after_cleanup"
        ) is not False:
            raise BASE.LifecycleError("SIGKILL supervisor did not remove the staged key")
        if kill.get("checkpoint_sha256") != BASE.digest_file(args.checkpoint):
            raise BASE.LifecycleError("kill observation binds a different checkpoint")
        if kill.get("positive_control_sha256") != BASE.digest_file(args.positive_control):
            raise BASE.LifecycleError("kill observation binds a different positive control")
        if kill.get("source") != source_binding():
            raise BASE.LifecycleError("kill observation source binding differs")
        phase = "checker_rejection_observation"
        rejections = checker_rejections(args.attempt)
        phase = "evidence_assembly"
        final = {
            "schema_version": 1,
            "provider": "anthropic",
            "qualification_requirement": "crash-cleanup-local-non-recoverability",
            "authorization_ruling": "A130",
            "run_id": run_id,
            "checkpoint": checkpoint,
            "kill": kill,
            "positive_control": positive,
            "post_kill_search": post,
            "in_progress_record": {
                "path": str(args.attempt),
                "record": attempt,
                "sha256_at_checkpoint": checkpoint.get("attempt_sha256"),
                "sha256_after_sigkill": kill.get("attempt_sha256"),
                "sha256_at_collection": attempt_sha256,
                "unchanged": True,
                "terminal_fields_present": [],
            },
            "checker_rejections": rejections,
            "provider_exposure_boundary": {
                "proof_scope": "local-host-non-recoverability-only",
                "provider_side_invalidation_proven": False,
                "provider_denial_observed": False,
                "killed_bearer_may_remain_valid_until": "natural-expiry",
                "maximum_bearer_lifetime_seconds": 300,
                "separate_expiry_requirement": "credential-expiry-denial",
            },
            "provenance_limitation": "A128-attended-record-not-provider-attestation",
            **source_binding(),
        }
        if contains_credential_material(final):
            raise BASE.LifecycleError("assembled evidence contains credential material")
        phase = "terminal_write"
        output.finish(final)
    except BaseException as error:
        output.finish(
            failed_record(
                "crash-cleanup-collect", run_id, started_at, phase, error
            )
        )
        raise
    print(f"anthropic_crash_cleanup_result={args.output} run_id={run_id}")
    return 0


def add_common_probe_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--signing-key", required=True, type=Path)
    parser.add_argument("--attempt-output", required=True, type=Path)
    parser.add_argument("--checkpoint-output", required=True, type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)

    probe = subparsers.add_parser("_probe", help=argparse.SUPPRESS)
    add_common_probe_arguments(probe)

    supervise = subparsers.add_parser("supervise")
    add_common_probe_arguments(supervise)
    supervise.add_argument("--positive-control", required=True, type=Path)
    supervise.add_argument("--kill-output", required=True, type=Path)

    scan = subparsers.add_parser("scan")
    scan.add_argument("--run-id", required=True)
    scan.add_argument("--checkpoint", required=True, type=Path)
    scan.add_argument("--output", required=True, type=Path)

    collect = subparsers.add_parser("collect")
    collect.add_argument("--run-id", required=True)
    collect.add_argument("--attempt", required=True, type=Path)
    collect.add_argument("--checkpoint", required=True, type=Path)
    collect.add_argument("--kill-observation", required=True, type=Path)
    collect.add_argument("--positive-control", required=True, type=Path)
    collect.add_argument("--post-kill-search", required=True, type=Path)
    collect.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    if os.geteuid() != 0:
        raise BASE.LifecycleError("crash-cleanup harness must run as root")
    os.umask(0o077)
    args = build_parser().parse_args()
    BASE.validate_run_id(args.run_id)
    if args.action == "_probe":
        return run_probe(args)
    if args.action == "supervise":
        return run_supervise(args)
    if args.action == "scan":
        return run_scan(args)
    return run_collect(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        BASE.LifecycleError,
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        KeyboardInterrupt,
    ) as error:
        print(f"anthropic WIF crash cleanup: {BASE.safe_failure_reason(error)}", file=sys.stderr)
        raise SystemExit(1)
