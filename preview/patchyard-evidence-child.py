#!/usr/bin/env python3
"""Fixed-contract browser helper for the A104 isolated evidence child."""

from __future__ import annotations

import base64
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import resource
import select
import signal
import shutil
import subprocess
import tempfile
import time
from typing import NoReturn
from urllib.parse import urlsplit


MAX_DOM_BYTES = 2_000_000
MAX_SCREENSHOT_BYTES = 5_000_000
MAX_EXTRACT_BYTES = 1_048_576
MAX_STDERR_BYTES = 1_048_576
PREVIEW_HOST = re.compile(r"^(?:[1-9]|[12][0-9]|30)\.preview\.example\.dev$")
SELECTOR = re.compile(r"^#[A-Za-z][A-Za-z0-9_-]{0,63}$")
BLOCKED_PRESENTATION_DEPENDENCIES = {
    (("https", "fonts.googleapis.com", None), "Other"),
    (("https", "fonts.googleapis.com", None), "Stylesheet"),
    (("https", "fonts.gstatic.com", None), "Other"),
}
FAILURE_STATES = {
    "redirect_blocked",
    "cross_origin_blocked",
    "popup_blocked",
    "download_blocked",
    "output_limit_exceeded",
    "bearer_disclosure_blocked",
    "browser_crashed",
    "child_timed_out",
    "contract_rejected",
}
FAILURE_DIAGNOSTICS = {
    "document_2xx",
    "document_3xx",
    "document_4xx",
    "document_5xx",
    "document_other",
    "document_login_form_2xx",
    "document_php_error_2xx",
    "document_database_error_2xx",
    "document_api_denied_2xx",
}
BROWSER_DIAGNOSTICS = {
    "browser_pipe_write_failed",
    "browser_pipe_closed_running",
    "browser_pipe_closed_clean",
    "browser_pipe_closed_nonzero",
    "browser_pipe_closed_sigtrap",
    "browser_pipe_closed_sigsegv",
    "browser_pipe_closed_sigabrt",
    "browser_pipe_closed_sigkill",
    "browser_pipe_closed_signal",
    "browser_message_invalid",
    "browser_command_rejected",
    "browser_command_rejected_browser_version",
    "browser_command_rejected_target_create",
    "browser_command_rejected_target_attach",
    "browser_command_rejected_page_enable",
    "browser_command_rejected_runtime_enable",
    "browser_command_rejected_network_enable",
    "browser_command_rejected_cache_disable",
    "browser_command_rejected_service_worker_bypass",
    "browser_command_rejected_fetch_enable",
    "browser_command_rejected_download_deny",
    "browser_command_rejected_navigate",
    "browser_command_rejected_runtime_evaluate",
    "browser_command_rejected_screenshot",
    "browser_event_invalid",
    "browser_exception_os",
    "browser_exception_subprocess",
    "browser_exception_value",
    "browser_exception_key",
    "browser_exception_type",
    "browser_exception_other",
    "browser_target_id_invalid",
    "browser_session_id_invalid",
    "browser_action_result_invalid",
    "browser_dom_result_invalid",
    "browser_screenshot_result_invalid",
    "browser_screenshot_base64_invalid",
}
TEST_MODE = os.environ.get("PATCHYARD_EVIDENCE_TEST") == "1"

COMMAND_REJECTION_DIAGNOSTICS = {
    "Browser.getVersion": "browser_command_rejected_browser_version",
    "Target.createTarget": "browser_command_rejected_target_create",
    "Target.attachToTarget": "browser_command_rejected_target_attach",
    "Page.enable": "browser_command_rejected_page_enable",
    "Runtime.enable": "browser_command_rejected_runtime_enable",
    "Network.enable": "browser_command_rejected_network_enable",
    "Network.setCacheDisabled": "browser_command_rejected_cache_disable",
    "Network.setBypassServiceWorker": "browser_command_rejected_service_worker_bypass",
    "Fetch.enable": "browser_command_rejected_fetch_enable",
    "Browser.setDownloadBehavior": "browser_command_rejected_download_deny",
    "Page.navigate": "browser_command_rejected_navigate",
    "Runtime.evaluate": "browser_command_rejected_runtime_evaluate",
    "Page.captureScreenshot": "browser_command_rejected_screenshot",
}


class CaptureFailure(Exception):
    def __init__(
        self,
        state: str,
        diagnostic: str | None = None,
        document_status: int | None = None,
        browser_diagnostic: str | None = None,
    ) -> None:
        if state not in FAILURE_STATES:
            raise ValueError("unknown fixed failure state")
        if diagnostic is not None and diagnostic not in FAILURE_DIAGNOSTICS:
            raise ValueError("unknown fixed failure diagnostic")
        if document_status is not None and not 100 <= document_status <= 599:
            raise ValueError("invalid document response status")
        if browser_diagnostic is not None and browser_diagnostic not in BROWSER_DIAGNOSTICS:
            raise ValueError("unknown fixed browser diagnostic")
        self.state = state
        self.diagnostic = diagnostic
        self.document_status = document_status
        self.browser_diagnostic = browser_diagnostic
        super().__init__(state)


class SelectParser(HTMLParser):
    def __init__(self, wanted: set[str]) -> None:
        super().__init__(convert_charrefs=True)
        self.wanted = wanted
        self.current_select: str | None = None
        self.current_option: dict | None = None
        self.text: list[str] = []
        self.selects: dict[str, list[dict]] = {item: [] for item in wanted}
        self.present: set[str] = set()
        self.popup_attempted = False
        self.cross_origin_attempted = False
        self.download_attempted = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("data-patchyard-popup-attempt") == "1":
            self.popup_attempted = True
        if values.get("data-patchyard-cross-origin-attempt") == "1":
            self.cross_origin_attempted = True
        if values.get("data-patchyard-download-attempt") == "1":
            self.download_attempted = True
        if values.get("id") in self.wanted:
            self.present.add(values["id"])
        if tag == "select" and values.get("id") in self.wanted:
            self.current_select = values["id"]
        elif tag == "option" and self.current_select is not None:
            self.current_option = {
                "value": values.get("value", ""),
                "selected": "selected" in values,
            }
            self.text = []

    def handle_data(self, data: str) -> None:
        if self.current_option is not None:
            self.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self.current_option is not None and self.current_select:
            label = " ".join("".join(self.text).split())
            self.selects[self.current_select].append(
                {
                    "label": label,
                    **self.current_option,
                    "blank_sentinel": label == "" and self.current_option["value"] == "",
                }
            )
            self.current_option = None
            self.text = []
        elif tag == "select":
            self.current_select = None


def fail(
    output: Path,
    state: str,
    diagnostic: str | None = None,
    document_status: int | None = None,
    browser_diagnostic: str | None = None,
) -> NoReturn:
    output.mkdir(mode=0o700, exist_ok=True)
    for path in output.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    failure = output / "failure.json"
    value: dict[str, object] = {"schema_version": 1, "state": state}
    if diagnostic is not None:
        value["diagnostic"] = diagnostic
    if document_status is not None:
        value["document_status"] = document_status
    if browser_diagnostic is not None:
        value["browser_diagnostic"] = browser_diagnostic
    failure.write_text(json.dumps(value) + "\n")
    failure.chmod(0o600)
    raise SystemExit(1)


def read_json(path: Path, maximum: int) -> dict:
    metadata = path.lstat()
    if not path.is_file() or path.is_symlink() or metadata.st_size > maximum:
        raise CaptureFailure("contract_rejected")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise CaptureFailure("contract_rejected")
    return value


def validate_contract(
    value: dict,
) -> tuple[str, str, list[dict], int, int, int, dict[str, int]]:
    if set(value) != {
        "allowed_url",
        "expected_sha",
        "actions",
        "navigation_timeout_ms",
        "action_timeout_ms",
        "total_timeout_ms",
        "maximum_dom_bytes",
        "maximum_screenshot_bytes",
        "maximum_extract_bytes",
    }:
        raise CaptureFailure("contract_rejected")
    parsed = urlsplit(value["allowed_url"])
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or (parsed.port and not TEST_MODE)
        or not PREVIEW_HOST.fullmatch(parsed.hostname or "")
        or parsed.fragment
    ):
        raise CaptureFailure("contract_rejected")
    expected_sha = value["expected_sha"]
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise CaptureFailure("contract_rejected")
    actions = value["actions"]
    if not isinstance(actions, list) or not 1 <= len(actions) <= 16:
        raise CaptureFailure("contract_rejected")
    selectors: set[str] = set()
    for action in actions:
        if action == "screenshot":
            continue
        if not isinstance(action, dict) or len(action) != 1:
            raise CaptureFailure("contract_rejected")
        name, argument = next(iter(action.items()))
        if name in {"wait_for", "extract_select"}:
            if not isinstance(argument, dict) or set(argument) != {"selector"}:
                raise CaptureFailure("contract_rejected")
            selector = argument["selector"]
            if not isinstance(selector, str) or not SELECTOR.fullmatch(selector):
                raise CaptureFailure("contract_rejected")
            selectors.add(selector)
        else:
            raise CaptureFailure("contract_rejected")
    if len(selectors) > 8:
        raise CaptureFailure("contract_rejected")
    limits = {
        "dom": value["maximum_dom_bytes"],
        "screenshot": value["maximum_screenshot_bytes"],
        "extract": value["maximum_extract_bytes"],
    }
    if not (
        isinstance(value["navigation_timeout_ms"], int)
        and 0 < value["navigation_timeout_ms"] <= 30_000
        and isinstance(value["action_timeout_ms"], int)
        and 0 < value["action_timeout_ms"] <= 10_000
        and isinstance(value["total_timeout_ms"], int)
        and 0 < value["total_timeout_ms"] <= 60_000
        and isinstance(limits["dom"], int)
        and 0 < limits["dom"] <= MAX_DOM_BYTES
        and isinstance(limits["screenshot"], int)
        and 0 < limits["screenshot"] <= MAX_SCREENSHOT_BYTES
        and isinstance(limits["extract"], int)
        and 0 < limits["extract"] <= MAX_EXTRACT_BYTES
    ):
        raise CaptureFailure("contract_rejected")
    return (
        value["allowed_url"],
        expected_sha,
        actions,
        value["navigation_timeout_ms"],
        value["action_timeout_ms"],
        value["total_timeout_ms"],
        limits,
    )


def validate_bearer(value: dict) -> tuple[str, str]:
    if set(value) != {"capability_id", "lease_id", "expires_at_unix", "secret"}:
        raise CaptureFailure("contract_rejected")
    capability_id = value["capability_id"]
    secret = value["secret"]
    if (
        not isinstance(capability_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", capability_id)
        or not isinstance(value["lease_id"], str)
        or not re.fullmatch(r"[0-9a-f]{32}", value["lease_id"])
        or not isinstance(secret, str)
        or not 16 <= len(secret) <= 8192
        or "\n" in secret
        or "\r" in secret
        or not isinstance(value["expires_at_unix"], int)
    ):
        raise CaptureFailure("contract_rejected")
    return capability_id, secret


def bounded(path: Path, maximum: int) -> bytes:
    metadata = path.lstat()
    if (
        not path.is_file()
        or path.is_symlink()
        or metadata.st_nlink != 1
        or metadata.st_size > maximum
    ):
        raise CaptureFailure("output_limit_exceeded")
    return path.read_bytes()


def origin(value: str) -> tuple[str, str, int | None] | None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return parsed.scheme, parsed.hostname, parsed.port


def document_diagnostic(status: int | None) -> str:
    if status is None:
        return "document_other"
    return f"document_{status // 100}xx" if 2 <= status // 100 <= 5 else "document_other"


def missing_selector_diagnostic(status: int | None, page_kind: object) -> str:
    """Return one fixed, response-content-free clue for an absent selector.

    The child may inspect the DOM while deciding whether it is safe to retain.
    On failure it must retain neither that DOM nor a substring from it.  These
    two fixed classifications make a live preview's auth or PHP failure
    distinguishable from an ordinary stale selector without widening the
    bounded child output contract.
    """
    if status is not None and 200 <= status < 300:
        if page_kind == "login_form":
            return "document_login_form_2xx"
        if page_kind == "php_error":
            return "document_php_error_2xx"
        if page_kind == "database_error":
            return "document_database_error_2xx"
        if page_kind == "api_denied":
            return "document_api_denied_2xx"
    return document_diagnostic(status)


def exception_browser_diagnostic(error: Exception) -> str:
    """Reduce an unexpected child exception to a fixed, non-secret class."""
    if isinstance(error, OSError):
        return "browser_exception_os"
    if isinstance(error, subprocess.SubprocessError):
        return "browser_exception_subprocess"
    if isinstance(error, ValueError):
        return "browser_exception_value"
    if isinstance(error, KeyError):
        return "browser_exception_key"
    if isinstance(error, TypeError):
        return "browser_exception_type"
    return "browser_exception_other"


class Cdp:
    """Minimal bounded Chrome DevTools Protocol client over anonymous pipes."""

    def __init__(self, process: subprocess.Popen, write_fd: int, read_fd: int) -> None:
        self.process = process
        self.write_fd = write_fd
        self.read_fd = read_fd
        self.sequence = 0
        self.buffer = b""

    def send(
        self, method: str, params: dict | None = None, session_id: str | None = None
    ) -> int:
        self.sequence += 1
        message: dict[str, object] = {"id": self.sequence, "method": method}
        if params:
            message["params"] = params
        if session_id:
            message["sessionId"] = session_id
        encoded = json.dumps(message, separators=(",", ":")).encode() + b"\0"
        if len(encoded) > 128 * 1024:
            raise CaptureFailure("contract_rejected")
        try:
            os.write(self.write_fd, encoded)
        except OSError as error:
            raise CaptureFailure(
                "browser_crashed", browser_diagnostic="browser_pipe_write_failed"
            ) from error
        return self.sequence

    def closed_diagnostic(self) -> str:
        returncode = self.process.poll()
        if returncode is None:
            return "browser_pipe_closed_running"
        if returncode == 0:
            return "browser_pipe_closed_clean"
        if returncode > 0:
            return "browser_pipe_closed_nonzero"
        return {
            -signal.SIGTRAP: "browser_pipe_closed_sigtrap",
            -signal.SIGSEGV: "browser_pipe_closed_sigsegv",
            -signal.SIGABRT: "browser_pipe_closed_sigabrt",
            -signal.SIGKILL: "browser_pipe_closed_sigkill",
        }.get(returncode, "browser_pipe_closed_signal")

    def receive(self, deadline: float) -> dict:
        while b"\0" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CaptureFailure("child_timed_out")
            readable, _, _ = select.select([self.read_fd], [], [], remaining)
            if not readable:
                raise CaptureFailure("child_timed_out")
            chunk = os.read(self.read_fd, 128 * 1024)
            if not chunk:
                raise CaptureFailure(
                    "browser_crashed", browser_diagnostic=self.closed_diagnostic()
                )
            self.buffer += chunk
            if len(self.buffer) > 2 * 1024 * 1024:
                raise CaptureFailure("output_limit_exceeded")
        encoded, self.buffer = self.buffer.split(b"\0", 1)
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError as error:
            raise CaptureFailure(
                "browser_crashed", browser_diagnostic="browser_message_invalid"
            ) from error
        if not isinstance(value, dict):
            raise CaptureFailure(
                "browser_crashed", browser_diagnostic="browser_message_invalid"
            )
        return value

    def call(
        self,
        method: str,
        params: dict | None,
        session_id: str | None,
        deadline: float,
        handler,
    ) -> dict:
        request_id = self.send(method, params, session_id)
        while True:
            message = self.receive(deadline)
            if message.get("id") == request_id:
                if "error" in message or not isinstance(message.get("result"), dict):
                    raise CaptureFailure(
                        "browser_crashed",
                        browser_diagnostic=COMMAND_REJECTION_DIAGNOSTICS.get(
                            method, "browser_command_rejected"
                        ),
                    )
                return message["result"]
            if "method" in message:
                handler(message)


def run_controlled_browser(
    allowed_url: str,
    navigation_timeout_ms: int,
    action_timeout_ms: int,
    total_timeout_ms: int,
    selectors: list[str],
    bearer: str,
    profile: Path,
    stderr: Path,
) -> tuple[bytes, bytes]:
    browser = (
        os.environ.get("PATCHYARD_EVIDENCE_TEST_CHROMIUM", "/opt/google/chrome/chrome")
        if TEST_MODE
        else "/usr/lib64/chromium-browser/chromium-browser"
    )
    command = [
        browser,
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-first-run",
        "--block-new-web-contents",
        "--disable-breakpad",
        "--remote-debugging-pipe",
        f"--user-data-dir={profile}",
        "--window-size=1440,1200",
        "about:blank",
    ]
    if TEST_MODE:
        command[1:1] = [
            "--ignore-certificate-errors",
            "--disable-gpu",
            "--host-resolver-rules=MAP 1.preview.example.dev 127.0.0.1",
            "--proxy-server=http://127.0.0.1:9",
            "--proxy-bypass-list=1.preview.example.dev",
        ]

    raw_to_read, raw_to_write = os.pipe()
    raw_from_read, raw_from_write = os.pipe()
    child_read = os.dup(raw_to_read)
    child_write = os.dup(raw_from_write)
    to_browser_write = os.dup(raw_to_write)
    from_browser_read = os.dup(raw_from_read)
    saved_targets: dict[int, int] = {}
    for target in (3, 4):
        try:
            saved_targets[target] = os.dup(target)
        except OSError:
            pass
    for descriptor in (raw_to_read, raw_to_write, raw_from_read, raw_from_write):
        os.close(descriptor)
    os.dup2(child_read, 3, inheritable=True)
    os.dup2(child_write, 4, inheritable=True)
    if child_read not in {3, 4}:
        os.close(child_read)
    if child_write not in {3, 4}:
        os.close(child_write)

    def child_setup() -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with stderr.open("wb") as error_file:
        process = subprocess.Popen(
            command,
            env={"HOME": str(profile.parent), "LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=error_file,
            start_new_session=True,
            preexec_fn=child_setup,
            pass_fds=(3, 4),
        )
    for target in (3, 4):
        if target in saved_targets:
            os.dup2(saved_targets[target], target)
            os.close(saved_targets[target])
        else:
            os.close(target)
    cdp = Cdp(process, to_browser_write, from_browser_read)
    total_deadline = time.monotonic() + total_timeout_ms / 1000
    navigation_deadline = min(
        total_deadline, time.monotonic() + navigation_timeout_ms / 1000
    )
    allowed_origin = origin(allowed_url)
    if allowed_origin is None:
        raise CaptureFailure("contract_rejected")
    loaded = False
    document_status: int | None = None

    def handle(message: dict) -> None:
        nonlocal loaded, document_status
        method = message.get("method")
        params = message.get("params", {})
        session_id = message.get("sessionId")
        if not isinstance(params, dict):
            raise CaptureFailure(
                "browser_crashed", browser_diagnostic="browser_event_invalid"
            )
        if method == "Fetch.requestPaused":
            request = params.get("request", {})
            request_id = params.get("requestId")
            url = request.get("url") if isinstance(request, dict) else None
            resource_type = params.get("resourceType")
            if not isinstance(request_id, str) or not isinstance(url, str):
                raise CaptureFailure(
                    "browser_crashed", browser_diagnostic="browser_event_invalid"
                )
            if origin(url) != allowed_origin:
                cdp.send(
                    "Fetch.failRequest",
                    {"requestId": request_id, "errorReason": "BlockedByClient"},
                    session_id if isinstance(session_id, str) else None,
                )
                # The live Session 14 page declares this fixed web-font CSS.
                # Abort it before any network transmission and retain the
                # evidence capture; the screenshot may use a fallback font.
                # Every other cross-origin subresource remains a named,
                # fail-closed exfiltration attempt.
                if (origin(url), resource_type) in BLOCKED_PRESENTATION_DEPENDENCIES:
                    return
                raise CaptureFailure("cross_origin_blocked")
            headers = request.get("headers", {})
            if not isinstance(headers, dict):
                raise CaptureFailure(
                    "browser_crashed", browser_diagnostic="browser_event_invalid"
                )
            forwarded = [
                {"name": str(name), "value": str(value)}
                for name, value in headers.items()
                if str(name).lower()
                not in {"authorization", "x-patchyard-capability"}
            ]
            forwarded.append({"name": "X-Patchyard-Factory-Capability", "value": bearer})
            cdp.send(
                "Fetch.continueRequest",
                {"requestId": request_id, "headers": forwarded},
                session_id if isinstance(session_id, str) else None,
            )
        elif method == "Network.requestWillBeSent" and "redirectResponse" in params:
            raise CaptureFailure("redirect_blocked")
        elif method == "Page.windowOpen":
            raise CaptureFailure("popup_blocked")
        elif method == "Browser.downloadWillBegin":
            raise CaptureFailure("download_blocked")
        elif method == "Network.responseReceived":
            response = params.get("response", {})
            headers = response.get("headers", {}) if isinstance(response, dict) else {}
            response_url = response.get("url") if isinstance(response, dict) else None
            status = response.get("status") if isinstance(response, dict) else None
            if (
                params.get("type") == "Document"
                and isinstance(response_url, str)
                and origin(response_url) == allowed_origin
                and isinstance(status, (int, float))
            ):
                document_status = int(status)
            if isinstance(headers, dict) and any(
                str(name).lower() == "content-disposition"
                and "attachment" in str(value).lower()
                for name, value in headers.items()
            ):
                raise CaptureFailure("download_blocked")
        elif method == "Page.loadEventFired":
            loaded = True

    try:
        cdp.call("Browser.getVersion", None, None, navigation_deadline, handle)
        created = cdp.call(
            "Target.createTarget",
            {"url": "about:blank"},
            None,
            navigation_deadline,
            handle,
        )
        target_id = created.get("targetId")
        if not isinstance(target_id, str):
            raise CaptureFailure(
                "browser_crashed", browser_diagnostic="browser_target_id_invalid"
            )
        attached = cdp.call(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
            None,
            navigation_deadline,
            handle,
        )
        session_id = attached.get("sessionId")
        if not isinstance(session_id, str):
            raise CaptureFailure(
                "browser_crashed", browser_diagnostic="browser_session_id_invalid"
            )
        for method, params in [
            ("Page.enable", None),
            ("Runtime.enable", None),
            ("Network.enable", {"maxTotalBufferSize": 1024 * 1024}),
            ("Network.setCacheDisabled", {"cacheDisabled": True}),
            ("Network.setBypassServiceWorker", {"bypass": True}),
            (
                "Fetch.enable",
                {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]},
            ),
        ]:
            cdp.call(method, params, session_id, navigation_deadline, handle)
        cdp.call(
            "Browser.setDownloadBehavior",
            {"behavior": "deny", "eventsEnabled": True},
            None,
            navigation_deadline,
            handle,
        )
        cdp.call(
            "Page.navigate",
            {"url": allowed_url},
            session_id,
            navigation_deadline,
            handle,
        )
        while not loaded:
            handle(cdp.receive(navigation_deadline))

        selector_json = json.dumps(selectors, separators=(",", ":"))
        action_deadline = min(
            total_deadline, time.monotonic() + action_timeout_ms / 1000
        )
        # The browser-side poll must leave bounded time for CDP to deliver its
        # settled promise.  Otherwise a genuinely absent selector consumes the
        # full action budget and is misclassified as a transport timeout rather
        # than the typed contract rejection it is.
        selector_poll_timeout_ms = max(action_timeout_ms - 250, 0)
        expression = f"""
(async () => {{
  const selectors = {selector_json};
  const deadline = Date.now() + {selector_poll_timeout_ms};
  while (Date.now() < deadline &&
         selectors.some(selector => !document.querySelector(selector))) {{
    await new Promise(resolve => setTimeout(resolve, 25));
  }}
  return {{
    missing: selectors.filter(selector => !document.querySelector(selector)),
    popup: !!document.querySelector('a[target="_blank" i]'),
    download: !!document.querySelector('a[download]'),
    pageKind: (() => {{
      // A legacy PHP include can emit its bounded error before <body> exists,
      // so inspect the document root rather than body-only text.  This text
      // never leaves the child; only an allowlisted classification can.
      const text = (document.documentElement?.textContent || '').slice(0, 8192);
      if (document.querySelector('input[type="password"], form[action*="login" i]')) {{
        return 'login_form';
      }}
      if (/Error!:\s*(?:SQLSTATE|could not find driver|connection (?:refused|failed))/i.test(text)) {{
        return 'database_error';
      }}
      if (/API Access Denied: Invalid authentication credentials\./i.test(text)) {{
        return 'api_denied';
      }}
      if (/(?:Fatal error|Parse error|Uncaught (?:Error|Exception)|PDOException)/i.test(text)) {{
        return 'php_error';
      }}
      return 'unknown';
    }})()
  }};
}})()
"""
        action = cdp.call(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
            session_id,
            action_deadline,
            handle,
        )
        result = action.get("result", {})
        value = result.get("value", {}) if isinstance(result, dict) else {}
        if not isinstance(value, dict):
            raise CaptureFailure(
                "browser_crashed", browser_diagnostic="browser_action_result_invalid"
            )
        if value.get("popup"):
            raise CaptureFailure("popup_blocked")
        if value.get("download"):
            raise CaptureFailure("download_blocked")
        if value.get("missing"):
            raise CaptureFailure(
                "contract_rejected",
                missing_selector_diagnostic(document_status, value.get("pageKind")),
                document_status,
            )
        dom_result = cdp.call(
            "Runtime.evaluate",
            {
                "expression": "document.documentElement.outerHTML",
                "returnByValue": True,
            },
            session_id,
            total_deadline,
            handle,
        )
        remote = dom_result.get("result", {})
        dom_value = remote.get("value") if isinstance(remote, dict) else None
        if not isinstance(dom_value, str):
            raise CaptureFailure(
                "browser_crashed", browser_diagnostic="browser_dom_result_invalid"
            )
        screenshot_result = cdp.call(
            "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": False},
            session_id,
            total_deadline,
            handle,
        )
        encoded = screenshot_result.get("data")
        if not isinstance(encoded, str):
            raise CaptureFailure(
                "browser_crashed", browser_diagnostic="browser_screenshot_result_invalid"
            )
        try:
            screenshot = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise CaptureFailure(
                "browser_crashed", browser_diagnostic="browser_screenshot_base64_invalid"
            ) from error
        return dom_value.encode(), screenshot
    except CaptureFailure:
        raise
    except Exception as error:
        raise CaptureFailure(
            "browser_crashed", browser_diagnostic=exception_browser_diagnostic(error)
        ) from error
    finally:
        try:
            cdp.send("Browser.close")
        except (CaptureFailure, OSError):
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        os.close(to_browser_write)
        os.close(from_browser_read)


def digest(path: Path) -> dict:
    content = path.read_bytes()
    return {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def main() -> None:
    if len(os.sys.argv) != 4:
        raise SystemExit(2)
    capture_path = Path(os.sys.argv[1])
    bearer_path = Path(os.sys.argv[2])
    output = Path(os.sys.argv[3])
    try:
        contract = read_json(capture_path, 128 * 1024)
        bearer = read_json(bearer_path, 16 * 1024)
        (
            allowed_url,
            expected_sha,
            actions,
            navigation_timeout_ms,
            action_timeout_ms,
            total_timeout_ms,
            limits,
        ) = validate_contract(contract)
        capability_id, secret = validate_bearer(bearer)
        if output.exists() or not output.is_absolute():
            raise CaptureFailure("contract_rejected")
        output.mkdir(mode=0o700)
        with tempfile.TemporaryDirectory(prefix="patchyard-evidence-") as temporary:
            temporary_path = Path(temporary)
            profile = temporary_path / "profile"
            profile.mkdir(mode=0o700)
            dom = output / "page.html"
            screenshot = output / "page.png"
            stderr = temporary_path / "chromium.stderr"
            selectors = sorted(
                action[next(iter(action))]["selector"]
                for action in actions
                if isinstance(action, dict)
            )
            dom_bytes, screenshot_bytes = run_controlled_browser(
                allowed_url,
                navigation_timeout_ms,
                action_timeout_ms,
                total_timeout_ms,
                selectors,
                secret,
                profile,
                stderr,
            )
            if stderr.stat().st_size > MAX_STDERR_BYTES:
                raise CaptureFailure("output_limit_exceeded")
            if len(dom_bytes) > limits["dom"] or len(screenshot_bytes) > limits["screenshot"]:
                raise CaptureFailure("output_limit_exceeded")
            if secret.encode() in dom_bytes or capability_id.encode() in dom_bytes:
                raise CaptureFailure("bearer_disclosure_blocked")
            dom.write_bytes(dom_bytes)
            screenshot.write_bytes(screenshot_bytes)
            dom.chmod(0o600)
            screenshot.chmod(0o600)
            parser = SelectParser(
                {
                    action[next(iter(action))]["selector"].removeprefix("#")
                    for action in actions
                    if isinstance(action, dict)
                }
            )
            parser.feed(dom_bytes.decode("utf-8", errors="strict"))
            if parser.cross_origin_attempted:
                raise CaptureFailure("cross_origin_blocked")
            if parser.popup_attempted:
                raise CaptureFailure("popup_blocked")
            if parser.download_attempted:
                raise CaptureFailure("download_blocked")
            missing = sorted(parser.wanted - parser.present)
            missing.extend(
                sorted(
                    action["extract_select"]["selector"].removeprefix("#")
                    for action in actions
                    if isinstance(action, dict)
                    and "extract_select" in action
                    and not parser.selects[
                        action["extract_select"]["selector"].removeprefix("#")
                    ]
                )
            )
            if missing:
                # This is an extraction-contract failure after a successful
                # retained DOM parse (for example, a select with no options).
                # Network status and page classification are intentionally
                # confined to the browser helper, so do not fabricate either
                # from this later parsing phase.
                raise CaptureFailure("contract_rejected")
            extract = output / "extract.json"
            extract.write_text(
                json.dumps(
                    {
                        "selects": [
                            {"id": name, "options": parser.selects[name]}
                            for name in sorted(
                                action["extract_select"]["selector"].removeprefix("#")
                                for action in actions
                                if isinstance(action, dict) and "extract_select" in action
                            )
                        ]
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            extract.chmod(0o600)
            bounded(extract, limits["extract"])

        execution = output / "execution.json"
        execution.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "allowed_url": allowed_url,
                    "expected_sha": expected_sha,
                    "final_url": allowed_url,
                    "redirects": 0,
                    "cross_origin_requests": 0,
                    "popup_attempts": 0,
                    "download_attempts": 0,
                    "bearer_disclosures": 0,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        execution.chmod(0o600)
        hashes = output / "hashes.json"
        artifacts = []
        for name in ("page.html", "page.png", "extract.json", "execution.json"):
            artifacts.append({"name": name, **digest(output / name)})
        hashes.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "expected_sha": expected_sha,
                    "artifacts": artifacts,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        hashes.chmod(0o600)
    except CaptureFailure as error:
        fail(
            output,
            error.state,
            error.diagnostic,
            error.document_status,
            error.browser_diagnostic,
        )
    except Exception as error:
        fail(
            output,
            "browser_crashed",
            browser_diagnostic=exception_browser_diagnostic(error),
        )


if __name__ == "__main__":
    main()
