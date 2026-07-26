from __future__ import annotations

from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_COMPOSE = (ROOT / "docker-compose.factory-capability.yml").read_text()
SLOT_COMPOSE = (ROOT / "docker-compose.factory-slot.yml").read_text()
TRAEFIK_DYNAMIC = (ROOT / "patchyard-traefik-dynamic.yml").read_text()
TRAEFIK_IMAGE = (
    "traefik@sha256:66b901df20c5b92a43ac79d92d14bd0a1fda50fdb3cae8f77d562aa8f279f748"
)


def unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.server.records.put(dict(self.headers.items()))  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Authorization", "Bearer translated-preview-authority")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


class BackendHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.server.records.put(dict(self.headers.items()))  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:
        return


@unittest.skipUnless(
    os.environ.get("FACTORY_TRAEFIK_INTEGRATION") == "1",
    "set FACTORY_TRAEFIK_INTEGRATION=1 on a Linux Docker runner",
)
class TraefikCapabilityBoundary(unittest.TestCase):
    """Exercise the production middleware order through a real Traefik proxy."""

    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("docker") is None:
            raise RuntimeError("Docker is required for the Traefik integration test")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.auth = ThreadingHTTPServer(("127.0.0.1", 0), AuthHandler)
        cls.auth.records = Queue()  # type: ignore[attr-defined]
        cls.backend = ThreadingHTTPServer(("127.0.0.1", 0), BackendHandler)
        cls.backend.records = Queue()  # type: ignore[attr-defined]
        cls.auth_thread = threading.Thread(target=cls.auth.serve_forever, daemon=True)
        cls.backend_thread = threading.Thread(
            target=cls.backend.serve_forever, daemon=True
        )
        cls.auth_thread.start()
        cls.backend_thread.start()
        cls.traefik_port = unused_port()
        cls.write_configuration()
        cls.traefik = subprocess.Popen(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "host",
                "--mount",
                f"type=bind,source={cls.root},target=/etc/traefik,readonly",
                TRAEFIK_IMAGE,
                "--configFile=/etc/traefik/static.yml",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.traefik.poll() is None:
            cls.traefik.terminate()
            try:
                cls.traefik.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.traefik.kill()
                cls.traefik.wait(timeout=10)
        cls.auth.shutdown()
        cls.backend.shutdown()
        cls.auth.server_close()
        cls.backend.server_close()
        cls.auth_thread.join(timeout=5)
        cls.backend_thread.join(timeout=5)
        cls.temporary.cleanup()

    @classmethod
    def write_configuration(cls) -> None:
        auth_port = cls.auth.server_address[1]
        backend_port = cls.backend.server_address[1]
        (cls.root / "static.yml").write_text(
            "\n".join(
                [
                    "entryPoints:",
                    "  web:",
                    f'    address: "127.0.0.1:{cls.traefik_port}"',
                    "providers:",
                    "  file:",
                    "    filename: /etc/traefik/dynamic.yml",
                    "log:",
                    "  level: ERROR",
                    "",
                ]
            )
        )
        (cls.root / "dynamic.yml").write_text(
            "\n".join(
                [
                    "http:",
                    "  routers:",
                    "    preview:",
                    "      entryPoints: [web]",
                    '      rule: "PathPrefix(`/`)"',
                    "      middlewares:",
                    "        - patchyard-capability",
                    "        - patchyard-capability-strip",
                    "      service: fieldbook",
                    "  middlewares:",
                    "    patchyard-capability:",
                    "      forwardAuth:",
                    f'        address: "http://127.0.0.1:{auth_port}/auth"',
                    "        authResponseHeaders: [Authorization]",
                    "        trustForwardHeader: false",
                    "    patchyard-capability-strip:",
                    "      headers:",
                    "        customRequestHeaders:",
                    '          X-Patchyard-Factory-Capability: ""',
                    "  services:",
                    "    fieldbook:",
                    "      loadBalancer:",
                    "        servers:",
                    f'          - url: "http://127.0.0.1:{backend_port}"',
                    "",
                ]
            )
        )

    def request_until_ready(self) -> int:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.traefik.poll() is not None:
                output = self.traefik.stderr.read() if self.traefik.stderr else ""
                self.fail(f"Traefik stopped before accepting the request: {output}")
            try:
                connection = HTTPConnection("127.0.0.1", self.traefik_port, timeout=1)
                connection.request(
                    "GET",
                    "/mfieldbook/leads/assign.php",
                    headers={"X-Patchyard-Factory-Capability": "integration-capability"},
                )
                response = connection.getresponse()
                response.read()
                connection.close()
                if response.status == 200:
                    return response.status
            except OSError:
                pass
            time.sleep(0.2)
        self.fail("Traefik did not proxy the capability request before the deadline")

    def test_auth_service_receives_capability_and_backend_does_not(self) -> None:
        self.assertIn(
            "TRAEFIK_PROVIDERS_FILE_FILENAME: /etc/traefik/patchyard-dynamic.yml",
            CAPABILITY_COMPOSE,
        )
        self.assertIn(
            'X-Patchyard-Factory-Capability: ""',
            TRAEFIK_DYNAMIC,
        )
        self.assertIn(
            '"patchyard-capability@file,patchyard-capability-strip@file"',
            SLOT_COMPOSE,
        )

        self.assertEqual(self.request_until_ready(), 200)
        auth_headers = self.auth.records.get(timeout=5)  # type: ignore[attr-defined]
        backend_headers = self.backend.records.get(timeout=5)  # type: ignore[attr-defined]
        auth_lower = {name.lower(): value for name, value in auth_headers.items()}
        backend_lower = {name.lower(): value for name, value in backend_headers.items()}

        self.assertEqual(
            auth_lower.get("x-patchyard-capability"), "integration-capability"
        )
        self.assertNotIn("x-patchyard-capability", backend_lower)
        self.assertEqual(
            backend_lower.get("authorization"), "Bearer translated-preview-authority"
        )


if __name__ == "__main__":
    unittest.main()
