#!/usr/bin/env python3
"""Fixed-contract browser helper for the A104 isolated evidence child."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import tempfile
from typing import NoReturn
from urllib.parse import urlsplit


MAX_DOM_BYTES = 2_000_000
MAX_SCREENSHOT_BYTES = 5_000_000
MAX_EXTRACT_BYTES = 1_048_576
MAX_NETLOG_BYTES = 5_000_000
MAX_STDERR_BYTES = 1_048_576
PREVIEW_HOST = re.compile(r"^(?:[1-9]|[12][0-9]|30)\.preview\.example\.dev$")
SELECTOR = re.compile(r"^#[A-Za-z][A-Za-z0-9_-]{0,63}$")
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


class CaptureFailure(Exception):
    def __init__(self, state: str) -> None:
        if state not in FAILURE_STATES:
            raise ValueError("unknown fixed failure state")
        self.state = state
        super().__init__(state)


class SelectParser(HTMLParser):
    def __init__(self, wanted: set[str]) -> None:
        super().__init__(convert_charrefs=True)
        self.wanted = wanted
        self.current_select: str | None = None
        self.current_option: dict | None = None
        self.text: list[str] = []
        self.selects: dict[str, list[dict]] = {item: [] for item in wanted}
        self.popup_attempted = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("data-patchyard-popup-attempt") == "1":
            self.popup_attempted = True
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


def fail(output: Path, state: str) -> NoReturn:
    output.mkdir(mode=0o700, exist_ok=True)
    failure = output / "failure.json"
    failure.write_text(json.dumps({"schema_version": 1, "state": state}) + "\n")
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


def validate_contract(value: dict) -> tuple[str, str, list[dict], int, dict[str, int]]:
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
        or parsed.port
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
    return value["allowed_url"], expected_sha, actions, value["total_timeout_ms"], limits


def validate_bearer(value: dict) -> tuple[str, str]:
    if set(value) != {"capability_id", "expires_at_unix", "secret"}:
        raise CaptureFailure("contract_rejected")
    capability_id = value["capability_id"]
    secret = value["secret"]
    if (
        not isinstance(capability_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", capability_id)
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


def strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def inspect_netlog(path: Path, allowed_url: str, secret: str, capability_id: str) -> None:
    netlog_bytes = bounded(path, MAX_NETLOG_BYTES)
    if secret.encode() in netlog_bytes or capability_id.encode() in netlog_bytes:
        raise CaptureFailure("bearer_disclosure_blocked")
    netlog = json.loads(netlog_bytes)
    constants = netlog.get("constants", {}).get("logEventTypes", {})
    names = {value: key for key, value in constants.items()}
    allowed_origin = origin(allowed_url)
    for event in netlog.get("events", []):
        name = names.get(event.get("type"), "")
        upper_name = name.upper()
        if "REDIRECT" in upper_name:
            raise CaptureFailure("redirect_blocked")
        if "DOWNLOAD" in upper_name:
            raise CaptureFailure("download_blocked")
        if "WINDOW_OPEN" in upper_name or "POPUP" in upper_name:
            raise CaptureFailure("popup_blocked")
        for value in strings(event.get("params", {})):
            candidate = origin(value)
            if candidate and candidate != allowed_origin:
                raise CaptureFailure("cross_origin_blocked")
            if "content-disposition" in value.lower() and "attachment" in value.lower():
                raise CaptureFailure("download_blocked")


def write_extension(extension: Path, hostname: str, bearer: str) -> None:
    origin_pattern = f"https://{hostname}/*"
    extension.mkdir(mode=0o700)
    manifest = {
        "manifest_version": 3,
        "name": "Patchyard Factory isolated preview authorization",
        "version": "1.0.0",
        "permissions": ["declarativeNetRequest"],
        "host_permissions": [origin_pattern],
        "declarative_net_request": {
            "rule_resources": [{"id": "rules", "enabled": True, "path": "rules.json"}]
        },
        "content_scripts": [
            {
                "matches": [origin_pattern],
                "run_at": "document_start",
                "js": ["guard.js"],
            }
        ],
    }
    rules = [
        {
            "id": 1,
            "priority": 1,
            "action": {"type": "block"},
            "condition": {
                "regexFilter": "^https?://",
                "resourceTypes": [
                    "main_frame",
                    "sub_frame",
                    "stylesheet",
                    "script",
                    "image",
                    "font",
                    "object",
                    "xmlhttprequest",
                    "ping",
                    "media",
                    "websocket",
                    "other",
                ],
            },
        },
        {
            "id": 2,
            "priority": 2,
            "action": {"type": "allow"},
            "condition": {"urlFilter": f"||{hostname}/"},
        },
        {
            "id": 3,
            "priority": 3,
            "action": {
                "type": "modifyHeaders",
                "requestHeaders": [
                    {"header": "Authorization", "operation": "set", "value": f"Bearer {bearer}"}
                ],
            },
            "condition": {
                "urlFilter": f"||{hostname}/",
                "resourceTypes": ["main_frame", "sub_frame", "xmlhttprequest"],
            },
        }
    ]
    guard = """
(() => {
  const mark = () => document.documentElement?.setAttribute(
    "data-patchyard-popup-attempt", "1");
  Object.defineProperty(window, "open", {value: () => { mark(); return null; }});
  addEventListener("click", event => {
    const link = event.target?.closest?.("a[target]");
    if (link && link.target.toLowerCase() === "_blank") {
      mark();
      event.preventDefault();
    }
  }, true);
})();
"""
    for name, value in [
        ("manifest.json", json.dumps(manifest, separators=(",", ":"))),
        ("rules.json", json.dumps(rules, separators=(",", ":"))),
        ("guard.js", guard),
    ]:
        path = extension / name
        path.write_text(value)
        path.chmod(0o600)


def run_browser(
    allowed_url: str,
    total_timeout_ms: int,
    maximum_file: int,
    extension: Path,
    profile: Path,
    dom: Path,
    screenshot: Path,
    netlog: Path,
    stderr: Path,
) -> None:
    command = [
        "/usr/bin/chromium-browser",
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
        f"--user-data-dir={profile}",
        f"--load-extension={extension}",
        f"--disable-extensions-except={extension}",
        f"--screenshot={screenshot}",
        "--window-size=1440,1200",
        f"--virtual-time-budget={min(total_timeout_ms, 10_000)}",
        f"--log-net-log={netlog}",
        "--net-log-capture-mode=Default",
        "--dump-dom",
        allowed_url,
    ]

    def limits() -> None:
        resource.setrlimit(resource.RLIMIT_FSIZE, (maximum_file, maximum_file))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with dom.open("wb") as dom_file, stderr.open("wb") as error_file:
        process = subprocess.Popen(
            command,
            env={"HOME": str(profile.parent), "LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL,
            stdout=dom_file,
            stderr=error_file,
            start_new_session=True,
            preexec_fn=limits,
        )
        try:
            code = process.wait(timeout=total_timeout_ms / 1000)
        except subprocess.TimeoutExpired as error:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise CaptureFailure("child_timed_out") from error
    if code != 0:
        raise CaptureFailure("browser_crashed")


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
        allowed_url, expected_sha, actions, total_timeout_ms, limits = validate_contract(contract)
        capability_id, secret = validate_bearer(bearer)
        if output.exists() or not output.is_absolute():
            raise CaptureFailure("contract_rejected")
        output.mkdir(mode=0o700)
        with tempfile.TemporaryDirectory(prefix="patchyard-evidence-") as temporary:
            temporary_path = Path(temporary)
            extension = temporary_path / "extension"
            profile = temporary_path / "profile"
            profile.mkdir(mode=0o700)
            write_extension(extension, urlsplit(allowed_url).hostname or "", secret)
            dom = output / "page.html"
            screenshot = output / "page.png"
            netlog = temporary_path / "netlog.json"
            stderr = temporary_path / "chromium.stderr"
            run_browser(
                allowed_url,
                total_timeout_ms,
                max(MAX_SCREENSHOT_BYTES, MAX_NETLOG_BYTES),
                extension,
                profile,
                dom,
                screenshot,
                netlog,
                stderr,
            )
            if stderr.stat().st_size > MAX_STDERR_BYTES:
                raise CaptureFailure("output_limit_exceeded")
            inspect_netlog(netlog, allowed_url, secret, capability_id)
            dom_bytes = bounded(dom, limits["dom"])
            bounded(screenshot, limits["screenshot"])
            if secret.encode() in dom_bytes or capability_id.encode() in dom_bytes:
                raise CaptureFailure("bearer_disclosure_blocked")
            parser = SelectParser(
                {
                    action["extract_select"]["selector"].removeprefix("#")
                    for action in actions
                    if "extract_select" in action
                }
            )
            parser.feed(dom_bytes.decode("utf-8", errors="strict"))
            if parser.popup_attempted:
                raise CaptureFailure("popup_blocked")
            missing = [name for name, options in parser.selects.items() if not options]
            if missing:
                raise CaptureFailure("contract_rejected")
            extract = output / "extract.json"
            extract.write_text(
                json.dumps(
                    {
                        "selects": [
                            {"id": name, "options": parser.selects[name]}
                            for name in sorted(parser.selects)
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
        fail(output, error.state)
    except Exception:
        fail(output, "browser_crashed")


if __name__ == "__main__":
    main()
