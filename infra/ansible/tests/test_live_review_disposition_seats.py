"""Live implementation-review and author-disposition seat deployment.

Static half: the seats, resolver, launcher egress path, and supervisor wiring
ship together and stay mutually consistent. Behavioral half: both seat scripts
run end to end against a loopback provider with fixture-shaped packets - the
same testable-without-OpenAI boundary the triage seat used.
"""

import http.server
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[3]
CONTROL = ROOT / "infra/ansible/roles/control_plane"
REVIEW_SEAT = CONTROL / "files/patchyard-review-seat"
DISPOSITION_SEAT = CONTROL / "files/patchyard-disposition-seat"
RESOLVER = CONTROL / "files/patchyard-provider-resolver"
LAUNCHER = CONTROL / "files/patchyard-child-launcher"
CHILD_UNIT = CONTROL / "files/patchyard-child@.service"
TASKS = CONTROL / "tasks/main.yml"
ENVIRONMENT = CONTROL / "templates/patchyard-supervisor.env.j2"
QUALIFY = CONTROL / "templates/qualify-factory-control.j2"
BOOTSTRAP = ROOT / "crates/factory-supervisor/src/bootstrap.rs"
REVIEW_RS = ROOT / "crates/factory-supervisor/src/review.rs"
ROUTING = ROOT / "policy/routing.json"
PROVIDERS = ROOT / "policy/provider-egress.json"

BEARER = "sk-ant-oat01-" + "A" * 48


def load_module(path: Path, name: str):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class LoopbackProvider:
    """One-shot Anthropic-shaped loopback endpoint serving a canned message."""

    def __init__(self, text: str):
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                outer.request_body = json.loads(self.rfile.read(length))
                outer.request_headers = {
                    key.lower(): value for key, value in self.headers.items()
                }
                body = json.dumps(
                    {
                        "type": "message",
                        "model": "claude-opus-5",
                        "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": text}],
                        "usage": {"input_tokens": 100, "output_tokens": 50},
                    }
                ).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *arguments):
                del arguments

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.request_body = None
        self.request_headers = None
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def provider(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def run_seat(script: Path, arguments: list[str], environment: dict, cwd=None):
    merged = {"PATH": "/usr/bin:/bin", **environment}
    return subprocess.run(
        ["/usr/bin/python3", "-I", str(script), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=merged,
        cwd=cwd,
        timeout=60,
    )


class DispositionSeatBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.stage_holder = tempfile.TemporaryDirectory(prefix="patchyard-disposition-")
        self.stage = Path(self.stage_holder.name) / "agent-stage"
        self.stage.mkdir(mode=0o700)
        self.review_id = str(uuid.uuid4())
        self.packet = {
            "schema_version": 1,
            "review": {
                "schema_version": 1,
                "review_id": self.review_id,
                "reviewed_sha": "b" * 40,
                "findings": [
                    {
                        "id": "finding-1",
                        "severity": "major",
                        "claim": "fixture claim",
                        "evidence": "fixture evidence",
                        "empirically_checkable": True,
                    }
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1, "cost_microusd": 0},
            },
            "task_spec": {"kind": "fixture"},
            "patch_sha256": "c" * 64,
        }
        (self.stage / "input.json").write_text(json.dumps(self.packet))
        os.chmod(self.stage / "input.json", 0o600)
        (self.stage / "bearer").write_text(BEARER)
        os.chmod(self.stage / "bearer", 0o600)
        self.prompt = Path(self.stage_holder.name) / "disposition.md"
        self.prompt.write_text("fixture disposition prompt")

    def tearDown(self) -> None:
        self.stage_holder.cleanup()

    def invoke(self, model_text: str):
        loopback = LoopbackProvider(model_text)
        try:
            result = run_seat(
                DISPOSITION_SEAT,
                [
                    str(self.prompt),
                    str(self.stage / "input.json"),
                    str(self.stage / "output.json"),
                ],
                {
                    "PATCHYARD_BEARER_FILE": str(self.stage / "bearer"),
                    "PATCHYARD_PROVIDER": loopback.provider,
                    "PATCHYARD_MODEL": "Claude Opus 5",
                    "PATCHYARD_EFFORT": "max",
                },
            )
        finally:
            loopback.close()
        return result, loopback

    def test_valid_disposition_round_trip_reports_tokens_and_removes_bearer(self) -> None:
        text = json.dumps(
            {
                "schema_version": 1,
                "review_id": self.review_id,
                "dispositions": [
                    {
                        "finding_id": "finding-1",
                        "disposition": "refute",
                        "evidence": "the claim contradicts the fixture file",
                    }
                ],
            }
        )
        result, loopback = self.invoke(text)
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = json.loads((self.stage / "output.json").read_text())
        self.assertEqual(artifact["review_id"], self.review_id)
        self.assertEqual(
            artifact["usage"],
            {"input_tokens": 100, "output_tokens": 50},
        )
        self.assertIn("PATCHYARD_USAGE=", result.stderr)
        self.assertFalse((self.stage / "bearer").exists())
        self.assertEqual(
            loopback.request_headers.get("authorization"), f"Bearer {BEARER}"
        )
        self.assertEqual(loopback.request_body["model"], "claude-opus-5")
        self.assertEqual(loopback.request_body["output_config"], {"effort": "max"})

    def test_refutation_without_evidence_fails_closed(self) -> None:
        text = json.dumps(
            {
                "schema_version": 1,
                "review_id": self.review_id,
                "dispositions": [
                    {"finding_id": "finding-1", "disposition": "refute", "evidence": None}
                ],
            }
        )
        result, _ = self.invoke(text)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refutation carries no bounded evidence", result.stderr)
        self.assertFalse((self.stage / "output.json").exists())
        self.assertFalse((self.stage / "bearer").exists())


class ReviewSeatBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.holder = tempfile.TemporaryDirectory(prefix="patchyard-review-")
        base = Path(self.holder.name)
        self.workspace = base / "workspace"
        self.workspace.mkdir()
        (self.workspace / "fixture.txt").write_text("alpha\nbeta\n")
        self.review_id = str(uuid.uuid4())
        self.reviewed_sha = "d" * 40
        self.packet_path = base / "packet.json"
        self.packet_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "review_id": self.review_id,
                    "reviewed_sha": self.reviewed_sha,
                    "task_spec": {"kind": "fixture"},
                    "patch_sha256": "e" * 64,
                    "manifest": {
                        "base_sha": "f" * 40,
                        "files": [
                            {
                                "path": "fixture.txt",
                                "change": "modified",
                                "additions": 1,
                                "deletions": 0,
                            }
                        ],
                    },
                    "hunks": [
                        {"path": "fixture.txt", "start_line": 1, "line_count": 1}
                    ],
                }
            )
        )
        self.prompt = base / "review.md"
        self.prompt.write_text("fixture review prompt")
        self.bearer = base / "bearer"
        self.bearer.write_text(BEARER)
        os.chmod(self.bearer, 0o600)
        self.output = base / "review.json"

    def tearDown(self) -> None:
        self.holder.cleanup()

    def invoke(self, model_text: str):
        loopback = LoopbackProvider(model_text)
        try:
            result = run_seat(
                REVIEW_SEAT,
                [str(self.prompt), str(self.packet_path), str(self.output)],
                {
                    "PATCHYARD_BEARER_FILE": str(self.bearer),
                    "PATCHYARD_PROVIDER": loopback.provider,
                    "PATCHYARD_MODEL": "Claude Opus 5",
                    "PATCHYARD_EFFORT": "max",
                },
                cwd=self.workspace,
            )
        finally:
            loopback.close()
        return result, loopback

    def test_review_round_trip_carries_workspace_bytes_and_typed_artifact(self) -> None:
        text = json.dumps(
            {
                "schema_version": 1,
                "review_id": self.review_id,
                "reviewed_sha": self.reviewed_sha,
                "findings": [
                    {
                        "id": "ordering",
                        "severity": "minor",
                        "claim": "fixture ordering claim",
                        "evidence": "fixture.txt line 1",
                        "empirically_checkable": True,
                    }
                ],
            }
        )
        result, loopback = self.invoke(text)
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = json.loads(self.output.read_text())
        self.assertEqual(artifact["review_id"], self.review_id)
        self.assertEqual(artifact["reviewed_sha"], self.reviewed_sha)
        self.assertEqual(len(artifact["findings"]), 1)
        self.assertEqual(
            artifact["usage"],
            {"input_tokens": 100, "output_tokens": 50},
        )
        # The manifest-listed file body reaches the provider as untrusted data.
        self.assertIn("alpha\\nbeta\\n", loopback.request_body["messages"][0]["content"])
        # The read-only bearer bind mount survives the run; the launcher owns
        # its teardown, unlike the stage-owned disposition bearer.
        self.assertTrue(self.bearer.exists())

    def test_wrong_review_id_echo_fails_closed(self) -> None:
        text = json.dumps(
            {
                "schema_version": 1,
                "review_id": str(uuid.uuid4()),
                "reviewed_sha": self.reviewed_sha,
                "findings": [],
            }
        )
        result, _ = self.invoke(text)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("review output envelope is malformed", result.stderr)
        self.assertFalse(self.output.exists())

    def project(self, entries: list[dict], hunks=None) -> list[dict]:
        """Run one round trip and return the WORKSPACE_FILES channel entries."""
        packet = json.loads(self.packet_path.read_text())
        packet["manifest"]["files"] = entries
        packet["hunks"] = [] if hunks is None else hunks
        self.packet_path.write_text(json.dumps(packet))
        result, loopback = self.invoke(
            json.dumps(
                {
                    "schema_version": 1,
                    "review_id": self.review_id,
                    "reviewed_sha": self.reviewed_sha,
                    "findings": [],
                }
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        message = json.loads(loopback.request_body["messages"][0]["content"])
        channel = next(
            entry
            for entry in message["channels"]
            if entry["channel"] == "WORKSPACE_FILES"
        )
        return channel["content"]

    def test_oversize_body_is_named_omitted_rather_than_projected_as_empty(self) -> None:
        # factory#322: a 1.4 MB core file projected as content "" while the
        # manifest said deletions=0, and the reviewer read the two channels as
        # a contradiction it could not certify.
        (self.workspace / "big.php").write_text("x" * (262_144 + 1))
        entries = self.project(
            [
                {
                    "path": "big.php",
                    "change": "modified",
                    "additions": 1,
                    "deletions": 0,
                    "binary": False,
                }
            ]
        )
        self.assertEqual(entries[0]["path"], "big.php")
        self.assertEqual(entries[0]["content"], "")
        self.assertEqual(entries[0]["omitted"], "oversize")

    def test_observed_empty_body_carries_no_omission_marker(self) -> None:
        (self.workspace / "empty.txt").write_text("")
        entries = self.project(
            [
                {
                    "path": "empty.txt",
                    "change": "modified",
                    "additions": 0,
                    "deletions": 1,
                    "binary": False,
                }
            ]
        )
        self.assertEqual(entries[0]["content"], "")
        self.assertNotIn("omitted", entries[0])

    def test_projected_body_carries_no_omission_marker(self) -> None:
        entries = self.project(
            [
                {
                    "path": "fixture.txt",
                    "change": "modified",
                    "additions": 1,
                    "deletions": 0,
                    "binary": False,
                }
            ]
        )
        self.assertEqual(entries[0]["content"], "alpha\nbeta\n")
        self.assertNotIn("omitted", entries[0])

    def test_every_unprojectable_case_names_its_own_reason(self) -> None:
        (self.workspace / "blob.dat").write_bytes(b"\xff\xfe\x00")
        (self.workspace / "logo.png").write_bytes(b"\x89PNG\r\n")
        entries = self.project(
            [
                {"path": "logo.png", "change": "modified", "binary": True},
                {"path": "gone.php", "change": "deleted", "binary": False},
                {"path": "blob.dat", "change": "modified", "binary": False},
                {"path": "absent.php", "change": "modified", "binary": False},
            ]
        )
        self.assertEqual(
            {entry["path"]: entry["omitted"] for entry in entries},
            {
                "logo.png": "binary",
                "gone.php": "deleted",
                "blob.dat": "undecodable",
                "absent.php": "unreadable",
            },
        )
        self.assertEqual({entry["content"] for entry in entries}, {""})

    def test_review_prompt_teaches_every_omission_reason(self) -> None:
        # An omitted body is only safe if the prompt says what omission means;
        # otherwise the reviewer keeps reading "" as evidence.
        module = load_module(REVIEW_SEAT, "patchyard_review_seat")
        prompt = (ROOT / "policy/review.md").read_text()
        self.assertIn("omitted", prompt)
        for reason in module.OMISSION_REASONS:
            self.assertIn(f"`{reason}`", prompt)

    def test_oversize_body_is_windowed_around_the_packets_hunk_ranges(self) -> None:
        # factory#325: the acceptance case. A three-line change to a file 5.7x
        # the per-file cap must reach the reviewer as the changed lines, not as
        # an omission it can only escalate.
        lines = [f"line {number}\n" for number in range(1, 40_001)]
        lines[19_999] = "CHANGED marker\n"
        (self.workspace / "common_functions.php").write_text("".join(lines))
        self.assertGreater(
            (self.workspace / "common_functions.php").stat().st_size, 262_144
        )
        entries = self.project(
            [
                {
                    "path": "common_functions.php",
                    "change": "modified",
                    "additions": 1,
                    "deletions": 1,
                    "binary": False,
                }
            ],
            [{"path": "common_functions.php", "start_line": 20_000, "line_count": 1}],
        )
        self.assertNotIn("omitted", entries[0])
        self.assertNotIn("content", entries[0])
        window = entries[0]["windowed"]
        self.assertEqual(window["total_lines"], 40_000)
        self.assertEqual(len(window["segments"]), 1)
        segment = window["segments"][0]
        # 40 lines of context each side of the one changed line.
        self.assertEqual(segment["start_line"], 19_960)
        self.assertEqual(segment["line_count"], 81)
        self.assertIn("CHANGED marker\n", segment["content"])
        self.assertTrue(segment["content"].startswith("line 19960\n"))
        self.assertTrue(segment["content"].endswith("line 20040\n"))
        # The reviewer can quote the changed line; the 1.4 MB body never rides.
        self.assertLess(len(segment["content"]), 4096)

    def test_adjacent_hunks_merge_into_one_segment_and_distant_ones_do_not(self) -> None:
        (self.workspace / "big.php").write_text(
            "".join(f"line {number}\n" for number in range(1, 40_001))
        )
        entries = self.project(
            [
                {
                    "path": "big.php",
                    "change": "modified",
                    "additions": 2,
                    "deletions": 0,
                    "binary": False,
                }
            ],
            [
                {"path": "big.php", "start_line": 100, "line_count": 1},
                {"path": "big.php", "start_line": 150, "line_count": 1},
                {"path": "big.php", "start_line": 30_000, "line_count": 1},
            ],
        )
        segments = entries[0]["windowed"]["segments"]
        self.assertEqual(
            [(segment["start_line"], segment["line_count"]) for segment in segments],
            [(60, 131), (29_960, 81)],
        )

    def test_oversize_file_with_no_hunk_range_is_still_named_omitted(self) -> None:
        # A window is only honest where the packet says the change is. With no
        # range for the path, the #322 marker is still the correct projection.
        (self.workspace / "big.php").write_text("x" * (262_144 + 1))
        entries = self.project(
            [
                {
                    "path": "big.php",
                    "change": "modified",
                    "additions": 1,
                    "deletions": 0,
                    "binary": False,
                }
            ],
            [{"path": "other.php", "start_line": 1, "line_count": 1}],
        )
        self.assertEqual(entries[0]["omitted"], "oversize")
        self.assertEqual(entries[0]["content"], "")
        self.assertNotIn("windowed", entries[0])

    def test_a_window_that_cannot_decode_is_named_undecodable_not_oversize(self) -> None:
        (self.workspace / "big.dat").write_bytes(
            b"header\n" + b"\xff\xfe\n" + b"x" * 262_144
        )
        entries = self.project(
            [
                {
                    "path": "big.dat",
                    "change": "modified",
                    "additions": 1,
                    "deletions": 0,
                    "binary": False,
                }
            ],
            [{"path": "big.dat", "start_line": 2, "line_count": 1}],
        )
        self.assertEqual(entries[0]["omitted"], "undecodable")

    def test_a_file_too_large_to_scan_is_named_oversize(self) -> None:
        module = load_module(REVIEW_SEAT, "patchyard_review_seat")
        target = self.workspace / "huge.php"
        with target.open("wb") as handle:
            handle.write(b"line\n" * ((module.MAX_WORKSPACE_SCAN_BYTES // 5) + 1))
        entries = self.project(
            [
                {
                    "path": "huge.php",
                    "change": "modified",
                    "additions": 1,
                    "deletions": 0,
                    "binary": False,
                }
            ],
            [{"path": "huge.php", "start_line": 2, "line_count": 1}],
        )
        self.assertEqual(entries[0]["omitted"], "oversize")

    def test_malformed_hunk_ranges_fail_closed(self) -> None:
        for hunk in (
            {"path": "fixture.txt", "start_line": 0, "line_count": 1},
            {"path": "fixture.txt", "start_line": 1, "line_count": 0},
            {"path": "../escape.txt", "start_line": 1, "line_count": 1},
            {"path": "fixture.txt", "start_line": 1},
            {"path": "fixture.txt", "start_line": True, "line_count": 1},
        ):
            with self.subTest(hunk=hunk):
                packet = json.loads(self.packet_path.read_text())
                packet["hunks"] = [hunk]
                self.packet_path.write_text(json.dumps(packet))
                result, _ = self.invoke("{}")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("hunk is malformed", result.stderr)

    def test_packet_without_hunks_fails_the_typed_contract(self) -> None:
        packet = json.loads(self.packet_path.read_text())
        del packet["hunks"]
        self.packet_path.write_text(json.dumps(packet))
        result, _ = self.invoke("{}")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match the typed contract", result.stderr)

    def test_review_prompt_teaches_the_windowed_shape(self) -> None:
        # A window is only safe if the prompt says a window is not the file;
        # otherwise it trades #322's silent misreading for a new one.
        prompt = (ROOT / "policy/review.md").read_text()
        for key in ("`windowed`", "`content`", "total_lines", "start_line", "line_count"):
            self.assertIn(key, prompt)

    def test_manifest_path_escapes_are_rejected(self) -> None:
        packet = json.loads(self.packet_path.read_text())
        packet["manifest"]["files"][0]["path"] = "../outside.txt"
        self.packet_path.write_text(json.dumps(packet))
        result, _ = self.invoke("{}")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the workspace contract", result.stderr)


class ProviderResolverContract(unittest.TestCase):
    def test_allowlist_is_qualified_providers_only(self) -> None:
        module = load_module(RESOLVER, "patchyard_provider_resolver")
        hosts = module.qualified_hosts(PROVIDERS)
        self.assertIn("api.anthropic.com", hosts)
        self.assertIn("api.openai.com", hosts)
        self.assertNotIn("api.x.ai", hosts)
        addresses = ("140.82.1.1",)
        resolved = module.resolve_stable(
            "api.anthropic.com",
            allowed=hosts,
            resolver=lambda host: addresses,
            pause=lambda seconds: None,
        )
        self.assertEqual(resolved, addresses)
        with self.assertRaises(ValueError):
            module.resolve_stable(
                "api.x.ai",
                allowed=hosts,
                resolver=lambda host: addresses,
                pause=lambda seconds: None,
            )
        with self.assertRaises(module.DnsBindingChanged):
            flapping = iter((("1.2.3.4",), ("5.6.7.8",)))
            module.resolve_stable(
                "api.anthropic.com",
                allowed=hosts,
                resolver=lambda host: next(flapping),
                pause=lambda seconds: None,
            )


class LiveSeatDeployment(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = LAUNCHER.read_text()
        cls.unit = CHILD_UNIT.read_text()
        cls.tasks = TASKS.read_text()
        cls.environment = ENVIRONMENT.read_text()
        cls.qualify = QUALIFY.read_text()
        cls.bootstrap = BOOTSTRAP.read_text()
        cls.review_rs = REVIEW_RS.read_text()
        cls.routing = json.loads(ROUTING.read_text())
        cls.providers = json.loads(PROVIDERS.read_text())

    def review_section(self) -> str:
        section = self.launcher.split('if [[ "$KIND" == review ]]; then', 1)[1]
        return section.split("FAILURE_STAGE=evidence_contract_validation", 1)[0]

    def test_seats_parse_and_are_installed_with_the_qualify_probe(self) -> None:
        import ast

        ast.parse(REVIEW_SEAT.read_text())
        ast.parse(DISPOSITION_SEAT.read_text())
        ast.parse(RESOLVER.read_text())
        for name in (
            "patchyard-disposition-seat",
            "patchyard-review-seat",
            "patchyard-provider-resolver",
        ):
            self.assertIn(
                f"destination: /usr/local/libexec/{name}", self.tasks
            )
            self.assertIn(f"test -x /usr/local/libexec/{name}", self.qualify)

    def test_disposition_seat_is_wired_with_credential_plumbing(self) -> None:
        self.assertIn(
            "FACTORY_DISPOSITION_HARNESS=/usr/local/libexec/patchyard-disposition-seat",
            self.environment,
        )
        self.assertIn(
            "FACTORY_DISPOSITION_CLI_VERSION=patchyard-disposition-seat/1",
            self.environment,
        )
        disposition_block = self.bootstrap.split(
            '"author_disposition".to_owned()', 1
        )[1].split("commands.insert", 1)[0]
        self.assertIn("credential: seat_credential.clone()", disposition_block)

    def test_live_review_child_is_egress_pinned_and_bearer_scrubbed(self) -> None:
        section = self.review_section()
        self.assertIn('has("egress_host")', section)
        self.assertIn("/usr/local/libexec/patchyard-provider-resolver", section)
        self.assertIn("/usr/local/libexec/patchyard-review-seat", section)
        self.assertIn("/opt/patchyard/fixtures/pipeline/bin/review-stub", section)
        self.assertIn("apply_child_firewall", section)
        self.assertIn("create_child_netns", section)
        self.assertIn('provider=%s\\ntransport=tcp/443\\ndns=none\\n', section)
        self.assertIn("offline-review", section)
        self.assertIn('path_contract "$JOB/secret/bearer" "$MANAGER_USER" 600 file', section)
        # Bearer validation must stay builtin pattern matching: a bounded
        # regex repetition ({16,8192}) made glibc allocate >1GB and tripped
        # the child unit's MemoryMax before the seat ran.
        self.assertNotIn('"$REVIEW_BEARER" =~', section)
        self.assertIn('[[ "$REVIEW_BEARER" != *[![:graph:]]* ]]', section)
        # Both worktree roots in the unit's ReadWritePaths are provisioned,
        # not left to appear lazily at first use.
        self.assertIn(
            "Create the reviewer worktree roots the child unit projects", self.tasks
        )
        self.assertIn("- review-worktrees", self.tasks)
        self.assertIn("- proposer-review-worktrees", self.tasks)
        self.assertIn("PATCHYARD_BEARER_FILE /secret/bearer", section)
        self.assertIn("bearer_disclosure_blocked", section)
        self.assertIn("STATE=dns_binding_changed", section)
        self.assertIn("review_non_router_baseline", section)
        # The evidence branch shares the same network helpers instead of a fork.
        evidence = self.launcher.split("FAILURE_STAGE=evidence_contract_validation", 1)[1]
        self.assertIn("create_child_netns", evidence)
        self.assertIn("apply_child_firewall", evidence)

    def test_timeouts_nest_seat_below_unit_below_supervisor(self) -> None:
        self.assertIn("TimeoutStartSec=240s", self.unit)
        self.assertIn("FACTORY_CHILD_TIMEOUT_SECONDS=270", self.environment)
        self.assertIn("PROVIDER_TIMEOUT_SECONDS = 180", REVIEW_SEAT.read_text())
        self.assertIn("PROVIDER_TIMEOUT_SECONDS = 170", DISPOSITION_SEAT.read_text())

    def test_live_seats_resolve_to_a_qualified_provider(self) -> None:
        qualified = {
            provider["display_name"]
            for provider in self.providers["providers"].values()
            if provider["credential_qualified"]
        }
        for task_class in ("triage", "author_disposition", "implementation_review"):
            seat = self.routing["rules"][task_class]["seat"]
            self.assertIn(
                seat["provider"],
                qualified,
                f"{task_class} routes to an unqualified provider",
            )
        self.assertEqual(
            self.routing["rules"]["implementation_review"]["seat"]["model"],
            "Claude Opus 5",
        )
        # A119 pins the reviewer tier to [max].
        self.assertEqual(
            self.routing["rules"]["implementation_review"]["seat"]["effort"], "max"
        )
        self.assertIn("require_qualified_seat", self.bootstrap)
        self.assertIn('routing.resolve("author_disposition")?', self.bootstrap)
        self.assertIn('routing.resolve("implementation_review")?', self.bootstrap)
        # The proposer reviewer stays offline: exactly one live reviewer wiring.
        self.assertEqual(self.bootstrap.count("live: None"), 1)
        self.assertIn("live: reviewer_live", self.bootstrap)
        self.assertIn("ChildSecret::SeatBearer", self.review_rs)


if __name__ == "__main__":
    unittest.main()
