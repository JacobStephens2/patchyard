from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from http.client import HTTPConnection
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_COMPOSE = (ROOT / "docker-compose.factory-capability.yml").read_text()
SLOT_COMPOSE = (ROOT / "docker-compose.factory-slot.yml").read_text()
TRAEFIK_DYNAMIC = (ROOT / "patchyard-traefik-dynamic.yml").read_text()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capability = load("patchyard_preview_capability", ROOT / "patchyard-preview-capability.py")
lease = load("patchyard_preview_lease", ROOT / "patchyard-preview-lease.py")


def utc_stamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


class CapabilityBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.state = root / "capabilities"
        self.state.mkdir(mode=0o700)
        self.key = root / "patchyard-api-key"
        self.key.write_text("preview-static-authority\n")
        self.key.chmod(0o400)
        self.state_patch = mock.patch.object(capability, "STATE", self.state)
        self.key_patch = mock.patch.object(capability, "KEY_FILE", self.key)
        self.state_patch.start()
        self.key_patch.start()

    def tearDown(self) -> None:
        self.key_patch.stop()
        self.state_patch.stop()
        self.temporary.cleanup()

    def activate(self, token: str, host: str = "1.preview.example.dev") -> str:
        capability_id = token.split(".")[1]
        (self.state / f"{capability_id}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "state": "active",
                    "capability_id": capability_id,
                    "lease_id": "b" * 32,
                    "slot": 1,
                    "allowed_host": host,
                    "expected_sha": "c" * 40,
                    "expires_at": utc_stamp(datetime.now(timezone.utc) + timedelta(minutes=2)),
                    "token_sha256": sha256(token.encode()).hexdigest(),
                }
            )
        )
        return capability_id

    def test_active_capability_translates_only_for_bound_get(self) -> None:
        token = f"efc1.{'a' * 32}.{'d' * 64}"
        self.activate(token)
        translated = capability.authorize(token, "1.preview.example.dev", "GET")
        self.assertEqual(translated, "preview-static-authority")
        self.assertIsNone(capability.authorize("", "1.preview.example.dev", "GET"))
        with self.assertRaises(ValueError):
            capability.authorize(token, "2.preview.example.dev", "GET")
        with self.assertRaises(ValueError):
            capability.authorize(token, "1.preview.example.dev", "POST")
        self.assertIsNone(
            capability.authorize(f"Bearer {token}", "1.preview.example.dev", "GET")
        )

    def test_http_boundary_returns_only_the_application_header(self) -> None:
        token = f"efc1.{'a' * 32}.{'d' * 64}"
        self.activate(token)
        server = capability.ThreadingHTTPServer(("127.0.0.1", 0), capability.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection(*server.server_address, timeout=2)
            connection.request(
                "GET",
                "/auth",
                headers={
                    "X-Patchyard-Factory-Capability": token,
                    "X-Forwarded-Host": "1.preview.example.dev",
                    "X-Forwarded-Method": "GET",
                },
            )
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("ETA_API_KEY"), "preview-static-authority")
            self.assertIsNone(response.getheader("X-Patchyard-Factory-Capability"))
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_revoked_expired_and_symlinked_capabilities_fail_closed(self) -> None:
        token = f"efc1.{'a' * 32}.{'d' * 64}"
        capability_id = self.activate(token)
        path = self.state / f"{capability_id}.json"
        value = json.loads(path.read_text())
        value["state"] = "revoked"
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            capability.authorize(token, "1.preview.example.dev", "GET")
        value["state"] = "active"
        value["expires_at"] = utc_stamp(datetime.now(timezone.utc) - timedelta(seconds=1))
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            capability.authorize(token, "1.preview.example.dev", "GET")
        path.unlink()
        path.symlink_to(self.key)
        with self.assertRaises(ValueError):
            capability.authorize(token, "1.preview.example.dev", "GET")

    def test_traefik_loads_the_file_provider_capability_chain(self) -> None:
        self.assertIn(
            '"--providers.file.filename=/etc/traefik/patchyard-dynamic.yml"',
            CAPABILITY_COMPOSE,
        )
        self.assertIn('address: "http://factory-capability:8080/auth"', TRAEFIK_DYNAMIC)

    def test_traefik_replaces_the_private_capability_header(self) -> None:
        self.assertIn(
            'authResponseHeadersRegex: "^X-Patchyard-Factory-Capability$"',
            TRAEFIK_DYNAMIC,
        )
        self.assertIn("- ETA_API_KEY", TRAEFIK_DYNAMIC)
        self.assertIn(
            '"patchyard-capability@file"',
            SLOT_COMPOSE,
        )


class LeaseCapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.root = root
        self.slots = root / "slots.json"
        self.lock = root / "slots.lock"
        self.capabilities = root / "capabilities"
        self.capabilities.mkdir(mode=0o700)
        expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
        self.slots.write_text(
            json.dumps(
                {
                    "1": {
                        "branch": "factory/example",
                        "status": "running",
                        "sha": "c" * 40,
                        "factory_lease": {
                            "lease_id": "b" * 32,
                            "owner": "factory-supervisor",
                            "request_id": "request-1",
                            "expected_sha": "c" * 40,
                            "created_at": utc_stamp(datetime.now(timezone.utc)),
                            "expires_at": utc_stamp(expiry),
                        },
                    }
                }
            )
        )
        self.patches = [
            mock.patch.object(lease, "SLOTS", self.slots),
            mock.patch.object(lease, "LOCK", self.lock),
            mock.patch.object(lease, "CAPABILITIES", self.capabilities),
            mock.patch.object(lease, "ROOT", root),
            mock.patch.object(lease, "rev_parse", return_value=("c" * 40, "c" * 40)),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self) -> None:
        for patch in reversed(self.patches):
            patch.stop()
        self.temporary.cleanup()

    def test_issue_is_sha_and_lease_bound_then_revocation_burns_id(self) -> None:
        arguments = SimpleNamespace(
            slot=1,
            lease_id="b" * 32,
            expected_sha="c" * 40,
            capability_id="a" * 32,
            ttl_seconds=120,
        )
        issued = lease.authorize(arguments)
        self.assertTrue(issued["ok"])
        self.assertEqual(issued["bearer"]["lease_id"], "b" * 32)
        self.assertLessEqual(
            issued["bearer"]["expires_at_unix"],
            int(datetime.now(timezone.utc).timestamp()) + 120,
        )
        revoked = lease.revoke(
            SimpleNamespace(lease_id="b" * 32, capability_id="a" * 32)
        )
        self.assertTrue(revoked["cleanup_complete"])
        state = json.loads((self.capabilities / f"{'a' * 32}.json").read_text())
        self.assertEqual(state["state"], "revoked")
        self.assertNotIn("token_sha256", state)
        with self.assertRaises(RuntimeError):
            lease.authorize(arguments)

    def test_recovered_acquire_is_idempotent_for_the_exact_contract(self) -> None:
        result = lease.acquire(
            SimpleNamespace(
                owner="factory-supervisor",
                request_id="request-1",
                branch="factory/example",
                expected_sha="c" * 40,
                lease_id="b" * 32,
                ttl_seconds=1200,
            )
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["slot"], 1)
        self.assertEqual(result["lease_id"], "b" * 32)
        self.assertEqual(result["host_head"], "c" * 40)

    def test_new_acquire_fetches_the_recorded_sha_before_detaching(self) -> None:
        self.slots.write_text("{}")
        expected_sha = "c" * 40
        arguments = SimpleNamespace(
            owner="factory-supervisor",
            request_id="request-1",
            branch="factory/example",
            expected_sha=expected_sha,
            lease_id="b" * 32,
            ttl_seconds=1200,
        )
        completed = SimpleNamespace(stdout="")
        with mock.patch.object(lease, "environment_token", return_value="token"), mock.patch.object(
            lease, "compose"
        ), mock.patch.object(lease, "require_route_ready") as route_ready, mock.patch.object(
            lease.subprocess, "run", return_value=completed
        ) as run:
            result = lease.acquire(arguments)

        self.assertTrue(result["ok"])
        commands = [call.args[0] for call in run.call_args_list]
        fetch = [
            "/usr/bin/git", "-C", str(self.root / "checkouts" / "1"),
            "fetch", "--no-tags", "--depth=1", "origin", expected_sha,
        ]
        checkout = [
            "/usr/bin/git", "-C", str(self.root / "checkouts" / "1"),
            "checkout", "--detach", expected_sha,
        ]
        self.assertIn(fetch, commands)
        self.assertIn(checkout, commands)
        self.assertLess(commands.index(fetch), commands.index(checkout))
        route_ready.assert_called_once_with(1)

    def test_route_readiness_is_local_and_bearer_free(self) -> None:
        completed = SimpleNamespace(stdout="302")
        with mock.patch.object(lease.subprocess, "run", return_value=completed) as run:
            lease.require_route_ready(7)
        command = run.call_args.args[0]
        self.assertIn("--resolve", command)
        self.assertIn("7.preview.example.dev:443:127.0.0.1", command)
        self.assertNotIn("Authorization", command)
        self.assertNotIn("Bearer", command)

    def test_route_readiness_retries_before_the_bounded_success(self) -> None:
        responses = [SimpleNamespace(stdout="404"), SimpleNamespace(stdout="302")]
        with mock.patch.object(lease.subprocess, "run", side_effect=responses) as run, mock.patch.object(
            lease.time, "sleep"
        ) as sleep:
            lease.require_route_ready(8)
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_log_scan_reports_matches_as_typed_output(self) -> None:
        capability_id = "a" * 32
        (self.capabilities / f"{capability_id}.json").write_text(
            json.dumps(
                {
                    "capability_id": capability_id,
                    "lease_id": "b" * 32,
                }
            )
        )
        with mock.patch.object(
            lease,
            "scan_stream",
            side_effect=[(100, 0, 1), (200, 1, 0)],
        ) as scan_stream, mock.patch.object(lease.subprocess, "run"):
            result = lease.scan_logs(
                SimpleNamespace(slot=1, lease_id="b" * 32)
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["sources"], 2)
        self.assertEqual(result["bytes_scanned"], 300)
        self.assertEqual(result["matches"], 1)
        self.assertEqual(result["sentinel_matches"], 1)
        created_at = json.loads(self.slots.read_text())["1"]["factory_lease"]["created_at"]
        self.assertEqual(
            scan_stream.call_args_list[0].args[0][:3],
            [
                "/usr/bin/journalctl",
                "--since",
                f"@{int(lease.parse_stamp(created_at).timestamp())}",
            ],
        )

    def test_log_scan_stream_detects_planted_bearer_and_visible_sentinel(self) -> None:
        bearer = b"efc1.capability.planted-preview-secret"
        sentinel = b"patchyard-preview-scan-visible"
        payload = b"before " + bearer + b" between " + sentinel + b" after"

        scanned, matches, sentinel_matches = lease.scan_stream(
            ["/usr/bin/printf", "%s", payload.decode()],
            {},
            [bearer],
            sentinel,
        )

        self.assertEqual(scanned, len(payload))
        self.assertEqual(matches, 1)
        self.assertEqual(sentinel_matches, 1)

    def test_absent_release_still_removes_capability_residue(self) -> None:
        capability_id = "a" * 32
        (self.capabilities / f"{capability_id}.json").write_text(
            json.dumps({"lease_id": "b" * 32})
        )
        self.slots.write_text("{}")
        completed = SimpleNamespace(stdout="")
        with mock.patch.object(lease, "compose"), mock.patch.object(
            lease.subprocess, "run", return_value=completed
        ):
            result = lease.destroy(1, "b" * 32)
        self.assertTrue(result["cleanup_complete"])
        self.assertTrue(result["already_absent"])
        self.assertFalse((self.capabilities / f"{capability_id}.json").exists())

    def test_release_by_id_locates_handle_lost_after_acquire(self) -> None:
        with mock.patch.object(
            lease,
            "destroy",
            return_value={
                "slot": 1,
                "lease_id": "b" * 32,
                "cleanup_complete": True,
                "cleanup_errors": [],
                "already_absent": False,
            },
        ) as destroy:
            result = lease.destroy_by_id("b" * 32)

        self.assertTrue(result["cleanup_complete"])
        destroy.assert_called_once_with(1, "b" * 32)


if __name__ == "__main__":
    unittest.main()
