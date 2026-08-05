#!/usr/bin/env python3
"""Run the revocation denial actions without changing the qualified expiry harness."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
BASE_HARNESS_PATH = ROOT / "tools/anthropic-wif-lifecycle.py"
BASE_HARNESS_SHA256 = (
    "10dfc4b3dc0002396f651734ff71f9618c119acde0065d6287193efed492873d"
)
RULE_DENIAL_SHAPE = {
    "top_level_keys": ["error", "request_id", "type"],
    "error_value_type": "object",
    "error_object_keys": ["message", "type"],
}


def load_base_harness() -> types.ModuleType:
    source = BASE_HARNESS_PATH.read_bytes()
    if (
        BASE_HARNESS_PATH.is_symlink()
        or hashlib.sha256(source).hexdigest() != BASE_HARNESS_SHA256
    ):
        raise RuntimeError("qualified expiry harness differs from its exact binding")
    module = types.ModuleType("anthropic_wif_lifecycle_base")
    module.__file__ = str(BASE_HARNESS_PATH)
    module.__package__ = None
    exec(
        compile(source, str(BASE_HARNESS_PATH), "exec", dont_inherit=True),
        module.__dict__,
    )
    return module


BASE = load_base_harness()
BASE_ACCEPTED_EXCHANGE = BASE.accepted_exchange


def source_binding() -> dict[str, str]:
    return {
        "policy_sha256": BASE.digest_file(BASE.POLICY_PATH),
        "lifecycle_harness_sha256": BASE.digest_file(BASE_HARNESS_PATH),
        "revocation_harness_sha256": BASE.digest_file(Path(__file__).resolve()),
    }


def accepted_exchange(
    policy: dict[str, Any],
    signing_key: Path,
    run_id: str,
    request: Callable[..., dict[str, Any]] | None = None,
    progress: BASE.Progress | None = None,
) -> tuple[dict[str, Any], str]:
    """Preserve the qualified exchange while recording when it began."""

    requester = BASE.request_json if request is None else request
    request_started_at: Any = None

    def capture_request(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal request_started_at
        response = requester(*args, **kwargs)
        if "requested_at" not in response:
            raise BASE.LifecycleError(
                "positive exchange response did not record its request start"
            )
        request_started_at = response["requested_at"]
        return response

    exchange, token = BASE_ACCEPTED_EXCHANGE(
        policy, signing_key, run_id, capture_request, progress
    )
    if request_started_at is None:
        raise BASE.LifecycleError("positive exchange did not record its request start")
    exchange["exchange"]["request_started_at"] = request_started_at
    return exchange, token


def denied_exchange_event(
    event_type: str,
    key_role: str,
    policy: dict[str, Any],
    signing_key: Path,
    run_id: str,
    request: Callable[..., dict[str, Any]] | None = None,
    progress: BASE.Progress | None = None,
) -> dict[str, Any]:
    """Capture one provider denial; only the observed rule shape is exact."""

    if event_type not in BASE.DENIAL_EVENT_TYPES:
        raise BASE.LifecycleError("denial event type is not allowlisted")
    requester = BASE.request_json if request is None else request
    assertion, key = BASE.mint_assertion(policy, signing_key, run_id, int(BASE.time.time()))
    if progress is not None:
        progress("denied_exchange_requested", None)
    response = requester(
        "POST", "/v1/oauth/token", body=BASE.exchange_request(policy, assertion)
    )
    assertion = ""
    payload = response["payload"]
    status = response["status"]
    error_type = BASE.provider_error_type(payload)
    shape = BASE.response_shape(payload)
    if event_type == "rule_disabled_exchange_denial":
        exact = status == 401 and error_type == "authentication_error"
        exact = exact and shape == RULE_DENIAL_SHAPE
        if not exact:
            if progress is not None:
                progress(
                    "denied_exchange_unexpected_response",
                    BASE.response_observation(response, "/v1/oauth/token"),
                )
            raise BASE.LifecycleError(
                "provider did not return the observed rule-disabled denial"
            )
    elif (
        not isinstance(status, int)
        or isinstance(status, bool)
        or not 400 <= status <= 499
        or not isinstance(error_type, str)
        or not error_type
    ):
        if progress is not None:
            progress(
                "denied_exchange_unexpected_response",
                BASE.response_observation(response, "/v1/oauth/token"),
            )
        raise BASE.LifecycleError("provider did not return a bounded HTTP denial")

    request_id = BASE.expiry_response_request_id(response["headers"], payload)
    denial = {
        "source": "anthropic_http_response",
        "endpoint": "/v1/oauth/token",
        "http_status": status,
        "request_id": request_id,
        "request_id_supplied": request_id is not None,
        "provider_date": BASE.parse_http_date(response["headers"].get("date")),
        "request_started_at": response["requested_at"],
        "observed_at": response["observed_at"],
        "error_type": error_type,
        "response_shape": shape,
    }
    if progress is not None:
        progress("denied_exchange_accepted", {"exchange_denial": denial})
    return {
        "schema_version": 1,
        "provider": "anthropic",
        "run_id": run_id,
        "event_type": event_type,
        "observed_at": denial["observed_at"],
        "key_role": key_role,
        "signing_key": key,
        "exchange_denial": denial,
        "credential_removed_at": BASE.iso_time(BASE.utc_now()),
        "source": source_binding(),
    }


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in {
        "exchange-denial",
        "exchange-positive",
    }:
        raise BASE.LifecycleError(
            "revocation harness permits only exchange evidence actions"
        )
    BASE.accepted_exchange = accepted_exchange
    BASE.denied_exchange_event = denied_exchange_event
    BASE.source_binding = source_binding
    return BASE.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        BASE.LifecycleError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        KeyboardInterrupt,
    ) as error:
        print(f"anthropic WIF revocation: {error}", file=sys.stderr)
        raise SystemExit(1)
