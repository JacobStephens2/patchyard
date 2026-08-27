from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import runpy


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "patchyard-evidence-child.py"
HELPER_NAMESPACE = runpy.run_path(str(HELPER))
EXCEPTION_BROWSER_DIAGNOSTIC = HELPER_NAMESPACE["exception_browser_diagnostic"]
COMMAND_REJECTION_DIAGNOSTICS = HELPER_NAMESPACE["COMMAND_REJECTION_DIAGNOSTICS"]
BROWSER_START_TIMEOUT_MS = HELPER_NAMESPACE["BROWSER_START_TIMEOUT_MS"]
HOST = "1.preview.example.dev"
CAPABILITY_ID = "a" * 32
LEASE_ID = "b" * 32
TOKEN = f"efc1.{CAPABILITY_ID}.{'d' * 64}"

# The total deadline is derived from its own parts rather than set beside them.
# A state-classification fixture never finds the selector, so it spends the whole
# action allowance before it can classify, and navigation may spend its own, and
# a completed capture then reads the DOM and screenshots under the total alone.
# A total smaller than the sum fires first and reports child_timed_out instead of
# the classification under test.
#
# Browser start is deliberately absent from this sum. The helper arms these
# clocks at its readiness handshake rather than at spawn, and bounds the start
# separately, so no share of the contract's budget is reserved for however slow
# a cold Chromium is on a loaded runner.
NAVIGATION_TIMEOUT_MS = 20_000
ACTION_TIMEOUT_MS = 2_000
OUTPUT_ALLOWANCE_MS = 10_000
TOTAL_TIMEOUT_MS = NAVIGATION_TIMEOUT_MS + ACTION_TIMEOUT_MS + OUTPUT_ALLOWANCE_MS
# The outer subprocess deadline must exceed every inner one, or the harness is
# killed before it can classify and write failure.json, and the assertion sees
# no file rather than the state under test. Browser start precedes the total, so
# it is added rather than assumed to overlap.
SUBPROCESS_TIMEOUT_S = (BROWSER_START_TIMEOUT_MS + TOTAL_TIMEOUT_MS) / 1000 + 10


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "patchyard-evidence-fixture/1"

    def do_GET(self) -> None:
        if self.headers.get("X-Patchyard-Factory-Capability") != TOKEN:
            self.send_response(401)
            self.end_headers()
            return
        if self.headers.get("Authorization"):
            self.send_response(401)
            self.end_headers()
            return
        select = '<select id="sales_person_id"><option value="1">Ada</option></select>'
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/completed")
            self.end_headers()
            return
        if self.path == "/missing":
            select = ""
        if self.path == "/missing-login":
            select = '<form action="/mfieldbook/login.php"><input type="password"></form>'
        if self.path == "/missing-php-error":
            select = "<p>Fatal error</p>"
        if self.path == "/missing-database-error":
            select = "<head><title>Error!: SQLSTATE</title></head>"
        if self.path == "/missing-api-denied":
            select = "<p>API Access Denied: Invalid authentication credentials.</p>"
        if self.path == "/empty-select":
            select = '<select id="sales_person_id"></select>'
        presentation = ""
        if self.path == "/blocked-presentation-dependency":
            presentation = (
                '<link rel="preconnect" href="https://fonts.googleapis.com">'
                '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                '<link rel="stylesheet" '
                'href="https://fonts.googleapis.com/css2?family=Work+Sans">'
            )
        if self.path == "/oversized":
            body = f"<!doctype html>{select}<p>{'x' * 200_000}</p>"
        elif self.path == "/cross-origin":
            body = f'<!doctype html>{select}<img src="https://example.com/disclose">'
        elif self.path == "/popup":
            body = f"<!doctype html>{select}<script>window.open('/other')</script>"
        elif self.path == "/download":
            body = f'<!doctype html>{select}<a download href="/file">file</a>'
        elif self.path == "/bearer":
            body = f"<!doctype html>{select}<p>{TOKEN}</p>"
        else:
            body = f"<!doctype html>{presentation}{select}"
        encoded = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


class EvidenceBrowserControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        key = cls.root / "key.pem"
        certificate = cls.root / "certificate.pem"
        subprocess.run(
            [
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                f"/CN={HOST}",
                "-addext",
                f"subjectAltName=DNS:{HOST}",
                "-keyout",
                str(key),
                "-out",
                str(certificate),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        # Warm Chromium before any assertion runs, so the alphabetically first
        # test does not pay process cold start - paging the binary in, building
        # a fresh profile. Since the helper bounds start separately from the
        # contract's clocks, this is a wall-clock saving rather than the thing
        # keeping the first test from failing; a start slow enough to exhaust
        # the start deadline is named as that wherever it happens. Deliberately
        # unasserted: this is not a test, and a real breakage still surfaces in
        # the cases below.
        try:
            cls.capture("completed")
        except (OSError, subprocess.SubprocessError):
            pass

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temporary.cleanup()

    @classmethod
    def capture(
        cls,
        fixture: str,
        *,
        maximum_dom_bytes: int = 2_000_000,
        navigation_timeout_ms: int = NAVIGATION_TIMEOUT_MS,
        action_timeout_ms: int = ACTION_TIMEOUT_MS,
        total_timeout_ms: int = TOTAL_TIMEOUT_MS,
        browser_start_ms: int | None = None,
        chromium: Path | None = None,
    ) -> tuple[subprocess.CompletedProcess, Path]:
        case = Path(tempfile.mkdtemp(dir=cls.root))
        contract = {
            "allowed_url": f"https://{HOST}:{cls.port}/{fixture}",
            "expected_sha": "c" * 40,
            "actions": [
                {"wait_for": {"selector": "#sales_person_id"}},
                {"extract_select": {"selector": "#sales_person_id"}},
                "screenshot",
            ],
            # State-classification fixtures must not race a cold Chromium start.
            # The timeout fixtures below supply their own narrowed deadlines.
            "navigation_timeout_ms": navigation_timeout_ms,
            "action_timeout_ms": action_timeout_ms,
            "total_timeout_ms": total_timeout_ms,
            "maximum_dom_bytes": maximum_dom_bytes,
            "maximum_screenshot_bytes": 5_000_000,
            "maximum_extract_bytes": 1_048_576,
        }
        bearer = {
            "capability_id": CAPABILITY_ID,
            "lease_id": LEASE_ID,
            "expires_at_unix": int(time.time()) + 60,
            "secret": TOKEN,
        }
        contract_path = case / "contract.json"
        bearer_path = case / "bearer.json"
        output = case / "output"
        contract_path.write_text(json.dumps(contract))
        bearer_path.write_text(json.dumps(bearer))
        environment = {
            "PATH": "/usr/bin:/bin",
            "PATCHYARD_EVIDENCE_TEST": "1",
        }
        if chromium is not None:
            environment["PATCHYARD_EVIDENCE_TEST_CHROMIUM"] = str(chromium)
        if browser_start_ms is not None:
            environment["PATCHYARD_EVIDENCE_TEST_BROWSER_START_MS"] = str(browser_start_ms)
        result = subprocess.run(
            [sys.executable, str(HELPER), str(contract_path), str(bearer_path), str(output)],
            env=environment,
            capture_output=True,
            timeout=SUBPROCESS_TIMEOUT_S,
            check=False,
        )
        return result, output

    def assert_state(
        self,
        fixture: str,
        expected: str,
        diagnostic: str | None = None,
        document_status: int | None = None,
        browser_diagnostic: str | None = None,
        **kwargs: object,
    ) -> None:
        result, output = self.capture(fixture, **kwargs)
        self.assertNotEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        failure = json.loads((output / "failure.json").read_text())
        expected_failure = {"schema_version": 1, "state": expected}
        if diagnostic is not None:
            expected_failure["diagnostic"] = diagnostic
        if document_status is not None:
            expected_failure["document_status"] = document_status
        if browser_diagnostic is not None:
            expected_failure["browser_diagnostic"] = browser_diagnostic
        self.assertEqual(failure, expected_failure)
        self.assertEqual([path.name for path in output.iterdir()], ["failure.json"])

    def test_fixed_browser_completes_and_emits_only_bounded_contract_outputs(self) -> None:
        result, output = self.capture("completed")
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(
            sorted(path.name for path in output.iterdir()),
            ["execution.json", "extract.json", "hashes.json", "page.html", "page.png"],
        )
        execution = json.loads((output / "execution.json").read_text())
        self.assertEqual(execution["expected_sha"], "c" * 40)
        self.assertNotIn(TOKEN, json.dumps(execution))

    def test_redirect_chain_is_named(self) -> None:
        self.assert_state("redirect", "redirect_blocked")

    def test_cross_origin_subresource_is_named(self) -> None:
        self.assert_state("cross-origin", "cross_origin_blocked")

    def test_fixed_presentation_dependency_is_blocked_without_failing_capture(self) -> None:
        result, output = self.capture("blocked-presentation-dependency")
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertTrue((output / "page.png").is_file())

    def test_popup_is_named(self) -> None:
        self.assert_state("popup", "popup_blocked")

    def test_download_is_named(self) -> None:
        self.assert_state("download", "download_blocked")

    def test_oversized_dom_is_named(self) -> None:
        self.assert_state("oversized", "output_limit_exceeded", maximum_dom_bytes=1024)

    def test_bearer_disclosure_is_named(self) -> None:
        self.assert_state("bearer", "bearer_disclosure_blocked")

    def test_browser_crash_is_named(self) -> None:
        browser = self.root / "crash-browser"
        browser.write_text("#!/bin/sh\nexit 42\n")
        browser.chmod(0o700)
        self.assert_state(
            "completed",
            "browser_crashed",
            browser_diagnostic="browser_pipe_closed_nonzero",
            chromium=browser,
        )

    def test_browser_that_never_answers_is_named_a_start_timeout(self) -> None:
        # A browser that never completes its readiness handshake is a slow or
        # wedged start, and is named as one. Before the start had its own
        # deadline this arrived as child_timed_out, indistinguishable from a
        # capture that hung after the browser was up.
        browser = self.root / "silent-browser"
        browser.write_text("#!/bin/sh\nsleep 5\n")
        browser.chmod(0o700)
        self.assert_state(
            "completed", "browser_start_timed_out", chromium=browser, browser_start_ms=250
        )

    def test_browser_timeout_after_start_is_named(self) -> None:
        # Answers the readiness handshake, then stops responding. The start is
        # over, so the contract's own clocks are armed and this is a genuine
        # capture timeout rather than a start that never finished.
        browser = self.root / "stalling-browser"
        browser.write_text(
            "#!/usr/bin/python3\n"
            "import os, time\n"
            "buffer = b''\n"
            "while b'\\0' not in buffer:\n"
            "    buffer += os.read(3, 4096)\n"
            'os.write(4, b\'{"id":1,"result":{}}\\0\')\n'
            "time.sleep(30)\n"
        )
        browser.chmod(0o700)
        self.assert_state(
            "completed", "child_timed_out", chromium=browser, total_timeout_ms=250
        )

    def test_slow_browser_start_does_not_consume_the_classification_budget(self) -> None:
        # A start slower than the whole navigation budget must still leave that
        # budget intact, so the fixture is classified rather than reported as
        # child_timed_out. This is the CI failure that recurred twice: the
        # deadlines were armed at spawn, so cold-start latency on a loaded
        # runner was charged against navigation and action.
        browser = self.root / "slow-start-browser"
        browser.write_text(
            f'#!/bin/sh\nsleep 3\nexec "{HELPER_NAMESPACE["TEST_CHROMIUM"]}" "$@"\n'
        )
        browser.chmod(0o700)
        self.assert_state(
            "missing",
            "contract_rejected",
            "document_2xx",
            200,
            chromium=browser,
            navigation_timeout_ms=3_000,
            action_timeout_ms=500,
        )

    def test_absent_selector_is_a_contract_rejection_not_a_timeout(self) -> None:
        self.assert_state("missing", "contract_rejected", "document_2xx", 200)

    def test_absent_selector_on_login_form_is_classified_without_retaining_dom(self) -> None:
        self.assert_state("missing-login", "contract_rejected", "document_login_form_2xx", 200)

    def test_absent_selector_on_php_error_is_classified_without_retaining_dom(self) -> None:
        self.assert_state("missing-php-error", "contract_rejected", "document_php_error_2xx", 200)

    def test_absent_selector_on_database_error_is_classified_without_retaining_dom(self) -> None:
        self.assert_state(
            "missing-database-error", "contract_rejected", "document_database_error_2xx", 200
        )

    def test_absent_selector_on_api_denial_is_classified_without_retaining_dom(self) -> None:
        self.assert_state("missing-api-denied", "contract_rejected", "document_api_denied_2xx", 200)

    def test_select_without_options_is_a_contract_rejection(self) -> None:
        self.assert_state("empty-select", "contract_rejected")

    def test_unexpected_exception_is_reduced_to_a_non_secret_class(self) -> None:
        self.assertEqual(
            EXCEPTION_BROWSER_DIAGNOSTIC(ValueError("private")),
            "browser_exception_value",
        )
        self.assertEqual(
            EXCEPTION_BROWSER_DIAGNOSTIC(RuntimeError("private")),
            "browser_exception_other",
        )

    def test_command_rejection_diagnostics_are_fixed_and_method_specific(self) -> None:
        self.assertEqual(
            COMMAND_REJECTION_DIAGNOSTICS["Page.captureScreenshot"],
            "browser_command_rejected_screenshot",
        )


if __name__ == "__main__":
    unittest.main()
