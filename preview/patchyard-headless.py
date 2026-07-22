#!/usr/bin/env python3
"""Bounded Chromium DOM capture using a bearer-header extension."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit


MAX_DOM_BYTES = 2_000_000
HOST = re.compile(r"^[1-9]|[12][0-9]|30\.preview\.example\.dev$")
SELECTOR = re.compile(r"^#[A-Za-z][A-Za-z0-9_-]{0,63}$")


class SelectParser(HTMLParser):
    def __init__(self, wanted: set[str]) -> None:
        super().__init__(convert_charrefs=True)
        self.wanted = wanted
        self.current_select: str | None = None
        self.current_option: dict | None = None
        self.text: list[str] = []
        self.selects: dict[str, list[dict]] = {item: [] for item in wanted}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
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
        if tag == "option" and self.current_option is not None and self.current_select is not None:
            label = " ".join("".join(self.text).split())
            option = {
                "label": label,
                **self.current_option,
                "blank_sentinel": label == "" and self.current_option["value"] == "",
            }
            self.selects[self.current_select].append(option)
            self.current_option = None
            self.text = []
        elif tag == "select":
            self.current_select = None


def bounded(value: Path, maximum: int) -> bytes:
    if not value.is_file() or value.is_symlink() or value.stat().st_size > maximum:
        raise RuntimeError(f"bounded capture missing or too large: {value.name}")
    return value.read_bytes()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--bearer-file", type=Path, required=True)
    parser.add_argument("--selector", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    parsed = urlsplit(args.url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise ValueError("capture URL must be a credential-free HTTPS URL")
    if not re.fullmatch(r"(?:[1-9]|[12][0-9]|30)\.preview\.example\.dev", parsed.hostname or ""):
        raise ValueError("capture URL must target one numbered preview host")
    selectors = [value.removeprefix("#") for value in args.selector]
    if len(selectors) > 8 or len(set(selectors)) != len(selectors) or any(not SELECTOR.fullmatch(f"#{value}") for value in selectors):
        raise ValueError("selectors must be unique bounded element IDs")
    if not args.bearer_file.is_absolute() or args.bearer_file.is_symlink():
        raise ValueError("bearer file must be an absolute regular file")
    bearer = args.bearer_file.read_text().strip()
    if not bearer or "\n" in bearer or "\r" in bearer:
        raise ValueError("bearer is unavailable")
    if args.output_dir.exists() or not args.output_dir.is_absolute():
        raise ValueError("output directory must be a new absolute path")
    args.output_dir.mkdir(mode=0o700)

    with tempfile.TemporaryDirectory(prefix="patchyard-browser-") as temporary:
        root = Path(temporary)
        extension = root / "extension"
        profile = root / "profile"
        extension.mkdir(mode=0o700)
        profile.mkdir(mode=0o700)
        origin = f"https://{parsed.hostname}/*"
        (extension / "manifest.json").write_text(json.dumps({
            "manifest_version": 3,
            "name": "Patchyard Factory preview authorization",
            "version": "1.0.0",
            "permissions": ["declarativeNetRequest"],
            "host_permissions": [origin],
            "declarative_net_request": {"rule_resources": [{"id": "rules", "enabled": True, "path": "rules.json"}]},
        }))
        (extension / "rules.json").write_text(json.dumps([{
            "id": 1,
            "priority": 1,
            "action": {"type": "modifyHeaders", "requestHeaders": [{
                "header": "Authorization", "operation": "set", "value": f"Bearer {bearer}",
            }]},
            "condition": {"urlFilter": f"||{parsed.hostname}/", "resourceTypes": ["main_frame", "sub_frame", "xmlhttprequest"]},
        }]))
        os.chmod(extension / "manifest.json", 0o600)
        os.chmod(extension / "rules.json", 0o600)
        screenshot = args.output_dir / "page.png"
        command = [
            "/usr/bin/chromium-browser", "--headless=new", "--no-sandbox",
            "--disable-dev-shm-usage", "--disable-background-networking",
            "--disable-component-update", "--disable-default-apps", "--disable-sync",
            "--metrics-recording-only", "--no-first-run",
            f"--user-data-dir={profile}", f"--load-extension={extension}",
            f"--disable-extensions-except={extension}",
            f"--screenshot={screenshot}", "--window-size=1440,1200",
            "--virtual-time-budget=5000", "--dump-dom", args.url,
        ]
        result = subprocess.run(
            command,
            env={"HOME": str(root), "LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            capture_output=True,
            timeout=45,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Chromium failed with exit {result.returncode}")
        if len(result.stdout) > MAX_DOM_BYTES:
            raise RuntimeError("captured DOM exceeded 2 MB")
        dom_path = args.output_dir / "page.html"
        dom_path.write_bytes(result.stdout)
        os.chmod(dom_path, 0o600)
        bounded(screenshot, 5_000_000)
        os.chmod(screenshot, 0o600)

    dom = bounded(dom_path, MAX_DOM_BYTES).decode("utf-8", errors="strict")
    extractor = SelectParser(set(selectors))
    extractor.feed(dom)
    missing = [name for name, options in extractor.selects.items() if not options]
    if missing:
        raise RuntimeError(f"selected DOM elements were absent: {','.join(missing)}")
    payload = {
        "selects": [{"id": name, "options": extractor.selects[name]} for name in selectors],
    }
    extract_path = args.output_dir / "selects.json"
    extract_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.chmod(extract_path, 0o600)


if __name__ == "__main__":
    main()
