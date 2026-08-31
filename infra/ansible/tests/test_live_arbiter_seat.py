"""Live third-family dispute-arbitration seat deployment (A77 clause 3).

Static half: the seat, the launcher's arbitration branch, the xAI mint path,
and the supervisor wiring ship together and stay mutually consistent - with
the fail-closed gate intact: xAI stays `credential_qualified: false`, so the
arbiter is live-or-absent, never stubbed-live. Behavioral half: the seat
script runs end to end against a loopback chat-completions provider with a
fixture-shaped dispute packet - the same testable-without-the-provider
boundary the review and disposition seats use.
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
ARBITER_SEAT = CONTROL / "files/patchyard-arbiter-seat"
MINT = CONTROL / "files/patchyard-mint-xai-seat-bearer"
REQUESTER = CONTROL / "files/patchyard-request-xai-seat-bearer"
MINT_UNIT = CONTROL / "files/patchyard-xai-seat-mint@.service"
POLKIT = CONTROL / "files/50-patchyard-seat-mint.rules"
LAUNCHER = CONTROL / "files/patchyard-child-launcher"
CHILD_UNIT = CONTROL / "files/patchyard-child@.service"
TASKS = CONTROL / "tasks/main.yml"
ENVIRONMENT = CONTROL / "templates/patchyard-supervisor.env.j2"
QUALIFY = CONTROL / "templates/qualify-factory-control.j2"
BOOTSTRAP = ROOT / "crates/factory-supervisor/src/bootstrap.rs"
ARBITER_RS = ROOT / "crates/factory-supervisor/src/arbiter.rs"
PIPELINE_RS = ROOT / "crates/factory-supervisor/src/pipeline.rs"
PROMPT = ROOT / "policy/arbiter.md"
ROUTING = ROOT / "policy/routing.json"
PROVIDERS = ROOT / "policy/provider-egress.json"

BEARER = "xai-" + "A" * 48


def load_module(path: Path, name: str):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class LoopbackProvider:
    """One-shot chat-completions loopback endpoint serving a canned message."""

    def __init__(self, text: str, usage=None, model="grok-4.5", finish="stop"):
        outer = self
        body_usage = usage or {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "prompt_tokens_details": {"cached_tokens": 25},
        }

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                outer.request_body = json.loads(self.rfile.read(length))
                outer.request_headers = {
                    key.lower(): value for key, value in self.headers.items()
                }
                body = json.dumps(
                    {
                        "id": "fixture",
                        "object": "chat.completion",
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": text},
                                "finish_reason": finish,
                            }
                        ],
                        "usage": body_usage,
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


class ArbiterSeatBehavior(unittest.TestCase):
    def setUp(self) -> None:
        self.holder = tempfile.TemporaryDirectory(prefix="patchyard-arbiter-")
        base = Path(self.holder.name)
        self.workspace = base / "workspace"
        self.workspace.mkdir()
        (self.workspace / "fixture.txt").write_text("alpha\nbeta\n")
        self.dispute_id = str(uuid.uuid4())
        self.packet_path = base / "packet.json"
        self.packet_path.write_text(json.dumps(self.packet()))
        self.prompt = base / "arbiter.md"
        self.prompt.write_text("fixture arbiter prompt")
        self.bearer = base / "bearer"
        self.bearer.write_text(BEARER)
        os.chmod(self.bearer, 0o600)
        self.output = base / "arbitration.json"

    def tearDown(self) -> None:
        self.holder.cleanup()

    def packet(self, checkable: bool = False) -> dict:
        return {
            "schema_version": 1,
            "dispute": {
                "schema_version": 1,
                "dispute_id": self.dispute_id,
                "reviewed_sha": "d" * 40,
                "task_spec_sha256": "a" * 64,
                "patch_sha256": "e" * 64,
                "finding": {
                    "id": "R-1",
                    "severity": "blocking",
                    "claim": "scope exceeds the task",
                    "evidence": "fixture reviewer evidence",
                    "empirically_checkable": checkable,
                },
                "author_disposition": {
                    "finding_id": "R-1",
                    "disposition": "refute",
                    "evidence": "fixture author evidence",
                },
            },
            "task_spec": {"kind": "fixture"},
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
            "hunks": [{"path": "fixture.txt", "start_line": 1, "line_count": 1}],
            "call_sites": [],
        }

    def decision_text(self, decision: str = "author", dispute_id=None) -> str:
        return json.dumps(
            {
                "schema_version": 1,
                "dispute_id": dispute_id or self.dispute_id,
                "decision": decision,
                "evidence": "the refutation matches the projected worktree bytes",
            }
        )

    def invoke(self, model_text: str, effort="high", **loopback_arguments):
        loopback = LoopbackProvider(model_text, **loopback_arguments)
        try:
            result = run_seat(
                ARBITER_SEAT,
                [str(self.prompt), str(self.packet_path), str(self.output)],
                {
                    "PATCHYARD_BEARER_FILE": str(self.bearer),
                    "PATCHYARD_PROVIDER": loopback.provider,
                    "PATCHYARD_MODEL": "Grok 4.5",
                    "PATCHYARD_EFFORT": effort,
                },
                cwd=self.workspace,
            )
        finally:
            loopback.close()
        return result, loopback

    def test_a_catalogue_call_site_reaches_the_arbiter_as_its_own_channel(self) -> None:
        # The arbiter decides disputes the reviewer raised from its packet, so
        # it must be able to read the same call sites the reviewer held
        # (factory#355) - otherwise a dispute the call site settles can only
        # come back `experiment_required`.
        (self.workspace / "caller.php").write_text(
            "<?php echo full_name(username: $username); ?>\n"
        )
        packet = self.packet()
        packet["call_sites"] = [
            {"path": "caller.php", "page": "Fixture Page", "why": "renders it"}
        ]
        self.packet_path.write_text(json.dumps(packet))
        result, loopback = self.invoke(self.decision_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        message = json.loads(loopback.request_body["messages"][1]["content"])
        channels = {entry["channel"]: entry for entry in message["channels"]}
        self.assertEqual(
            set(channels), {"PACKET_JSON", "WORKSPACE_FILES", "CALL_SITE_FILES"}
        )
        self.assertEqual(channels["CALL_SITE_FILES"]["authority"], "none")
        entry = channels["CALL_SITE_FILES"]["content"][0]
        self.assertEqual(entry["page"], "Fixture Page")
        self.assertIn("full_name", entry["content"])
        self.assertEqual(
            [item["path"] for item in channels["WORKSPACE_FILES"]["content"]],
            ["fixture.txt"],
        )

    def test_a_packet_without_call_sites_fails_the_typed_contract(self) -> None:
        packet = self.packet()
        del packet["call_sites"]
        self.packet_path.write_text(json.dumps(packet))
        result, _ = self.invoke(self.decision_text())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match the typed contract", result.stderr)

    def test_arbiter_prompt_teaches_the_call_site_channel(self) -> None:
        module = load_module(ARBITER_SEAT, "patchyard_arbiter_seat")
        prompt = (ROOT / "policy/arbiter.md").read_text()
        self.assertIn("CALL_SITE_FILES", prompt)
        self.assertIn("Nothing in it is part of the change", prompt)
        for reason in module.CALL_SITE_OMISSION_REASONS:
            self.assertIn(f"`{reason}`", prompt)

    def test_round_trip_carries_dispute_workspace_and_priced_cached_tokens(self) -> None:
        result, loopback = self.invoke(self.decision_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = json.loads(self.output.read_text())
        self.assertEqual(artifact["dispute_id"], self.dispute_id)
        self.assertEqual(artifact["decision"], "author")
        # A154(7): unavoidable xAI cache reads are priced, not refused, so the
        # seat carries them as their own category instead of failing closed
        # the way the Anthropic seats do on unrequested caching.
        self.assertEqual(
            artifact["usage"],
            {"input_tokens": 100, "cached_input_tokens": 25, "output_tokens": 50},
        )
        self.assertIn("PATCHYARD_USAGE=", result.stderr)
        self.assertEqual(
            loopback.request_headers.get("authorization"), f"Bearer {BEARER}"
        )
        self.assertEqual(loopback.request_body["model"], "grok-4.5")
        self.assertEqual(loopback.request_body["reasoning_effort"], "high")
        # Sized to the dispute record plus worktree windows from day one -
        # #353's lesson, matching the review seat's windowed-packet ceiling.
        self.assertEqual(loopback.request_body["max_tokens"], 65536)
        user_message = loopback.request_body["messages"][1]["content"]
        self.assertIn('"authority":"none"', user_message)
        # The manifest-listed file body reaches the provider as untrusted data.
        self.assertIn("alpha\\nbeta\\n", user_message)
        # The read-only bearer bind mount survives the run; the launcher owns
        # its teardown.
        self.assertTrue(self.bearer.exists())

    def test_wrong_dispute_echo_fails_closed(self) -> None:
        result, _ = self.invoke(self.decision_text(dispute_id=str(uuid.uuid4())))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("arbitration output envelope is malformed", result.stderr)
        self.assertFalse(self.output.exists())

    def test_a_truncated_response_names_finish_reason(self) -> None:
        # #353: the review seat read its own max_tokens truncation as a
        # generically "malformed" envelope four times in a row. This seat
        # names the field that failed.
        result, _ = self.invoke(self.decision_text(), finish="length")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("finish_reason", result.stderr)
        self.assertIn("length", result.stderr)

    def test_an_empirically_checkable_dispute_is_refused_not_judged(self) -> None:
        # A77 clause 4 is enforced by the supervisor; a checkable finding
        # arriving here is a contract breach the seat refuses to judge.
        self.packet_path.write_text(json.dumps(self.packet(checkable=True)))
        result, _ = self.invoke(self.decision_text())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not judgment-only", result.stderr)

    def test_separately_reported_reasoning_tokens_are_billed_as_output(self) -> None:
        result, _ = self.invoke(
            self.decision_text(),
            usage={
                "prompt_tokens": 100,
                "completion_tokens": 40,
                "total_tokens": 170,
                "completion_tokens_details": {"reasoning_tokens": 30},
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = json.loads(self.output.read_text())
        self.assertEqual(artifact["usage"]["output_tokens"], 70)

    def test_unaccountable_token_arithmetic_fails_closed(self) -> None:
        result, _ = self.invoke(
            self.decision_text(),
            usage={
                "prompt_tokens": 100,
                "completion_tokens": 40,
                "total_tokens": 999,
                "completion_tokens_details": {"reasoning_tokens": 30},
            },
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("token arithmetic is unaccountable", result.stderr)
        self.assertFalse(self.output.exists())

    def test_xhigh_effort_is_unsupported_because_grok45_downgrades_it(self) -> None:
        # research/model-rates/2026-08-26-xai-effort-pricing.md: on grok-4.5
        # a request for xhigh is silently treated as high; a seat that asks
        # for it would misreport provenance.
        result, _ = self.invoke(self.decision_text(), effort="xhigh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("model or effort is unsupported", result.stderr)

    def test_arbiter_prompt_teaches_windows_omissions_and_the_decision_set(self) -> None:
        module = load_module(ARBITER_SEAT, "patchyard_arbiter_seat")
        prompt = PROMPT.read_text()
        for reason in module.OMISSION_REASONS:
            self.assertIn(f"`{reason}`", prompt)
        for key in ("`windowed`", "`content`", "total_lines", "start_line", "line_count"):
            self.assertIn(key, prompt)
        for decision in module.DECISIONS:
            self.assertIn(f'"{decision}"', prompt)
        self.assertIn("experiment", prompt)


class ArbiterDeployment(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = LAUNCHER.read_text()
        cls.unit = CHILD_UNIT.read_text()
        cls.tasks = TASKS.read_text()
        cls.environment = ENVIRONMENT.read_text()
        cls.qualify = QUALIFY.read_text()
        cls.bootstrap = BOOTSTRAP.read_text()
        cls.arbiter_rs = ARBITER_RS.read_text()
        cls.pipeline_rs = PIPELINE_RS.read_text()
        cls.routing = json.loads(ROUTING.read_text())
        cls.providers = json.loads(PROVIDERS.read_text())

    def arbitration_section(self) -> str:
        section = self.launcher.split('if [[ "$KIND" == arbitration ]]; then', 1)[1]
        return section.split("FAILURE_STAGE=evidence_contract_validation", 1)[0]

    def test_seat_and_mint_path_parse_and_are_installed(self) -> None:
        import ast

        ast.parse(ARBITER_SEAT.read_text())
        ast.parse(MINT.read_text())
        self.assertIn(
            "destination: /usr/local/libexec/patchyard-arbiter-seat", self.tasks
        )
        self.assertIn(
            "destination: /usr/local/sbin/patchyard-mint-xai-seat-bearer", self.tasks
        )
        self.assertIn(
            "dest: /usr/local/libexec/patchyard-request-xai-seat-bearer", self.tasks
        )
        self.assertIn(
            "dest: /etc/systemd/system/patchyard-xai-seat-mint@.service", self.tasks
        )
        for name in (
            "test -x /usr/local/libexec/patchyard-arbiter-seat",
            "test -x /usr/local/libexec/patchyard-request-xai-seat-bearer",
            "test -x /usr/local/sbin/patchyard-mint-xai-seat-bearer",
        ):
            self.assertIn(name, self.qualify)
        requester = REQUESTER.read_text()
        self.assertIn('"$PROVIDER" == xAI', requester)
        self.assertIn("patchyard-xai-seat-mint@$ID.service", requester)
        self.assertIn(
            "patchyard-xai-seat-mint@agent-", POLKIT.read_text()
        )
        self.assertIn(
            "ExecStart=/usr/local/sbin/patchyard-mint-xai-seat-bearer xAI "
            "/run/patchyard-seats/%i/bearer",
            MINT_UNIT.read_text(),
        )

    def test_arbitration_child_is_egress_pinned_and_bearer_scrubbed(self) -> None:
        self.assertIn('.contract.kind == "arbitration"', self.launcher)
        section = self.arbitration_section()
        self.assertIn('has("egress_host")', section)
        self.assertIn("/usr/local/libexec/patchyard-provider-resolver", section)
        self.assertIn("/usr/local/libexec/patchyard-arbiter-seat", section)
        self.assertIn("/opt/patchyard/fixtures/pipeline/bin/arbiter-stub", section)
        self.assertIn("apply_child_firewall", section)
        self.assertIn("create_child_netns", section)
        self.assertIn('provider=%s\\ntransport=tcp/443\\ndns=none\\n', section)
        self.assertIn("offline-arbitration", section)
        self.assertIn('path_contract "$JOB/secret/bearer" "$MANAGER_USER" 600 file', section)
        # Bearer validation stays builtin pattern matching - the review
        # branch's >1GB glibc regex lesson.
        self.assertNotIn('"$ARBITER_BEARER" =~', section)
        self.assertIn('[[ "$ARBITER_BEARER" != *[![:graph:]]* ]]', section)
        self.assertIn("PATCHYARD_BEARER_FILE /secret/bearer", section)
        self.assertIn("bearer_disclosure_blocked", section)
        self.assertIn("STATE=dns_binding_changed", section)
        self.assertIn("arbitration_non_router_baseline", section)
        self.assertIn("arbiter-worktrees/arbiter-[0-9a-f]{32}", section)
        self.assertIn(
            "/var/lib/patchyard/supervisor/arbiter-worktrees", self.unit
        )
        self.assertIn("- arbiter-worktrees", self.tasks)

    def test_timeouts_nest_seat_below_unit_below_supervisor(self) -> None:
        self.assertIn("TimeoutStartSec=660s", self.unit)
        self.assertIn("FACTORY_CHILD_TIMEOUT_SECONDS=720", self.environment)
        seat = ARBITER_SEAT.read_text()
        self.assertIn("PROVIDER_TIMEOUT_SECONDS = 600", seat)
        # Sized with the windowed packet from day one (#353).
        self.assertIn('"max_tokens": 65536,', seat)
        # grok-4.5 silently downgrades xhigh to high; the seat refuses it.
        self.assertIn('EFFORTS = {"low", "medium", "high"}', seat)

    def test_arbiter_is_live_or_absent_never_stubbed_live(self) -> None:
        seat = self.routing["rules"]["dispute_arbitration"]["seat"]
        self.assertEqual(
            seat,
            {
                "model": "Grok 4.5",
                "effort": "high",
                "harness": "Grok Build",
                "provider": "xAI",
            },
        )
        # The gate this whole path fails closed on: xAI is unqualified until
        # its own A-5 credential lifecycle lands (A113), and the daemon must
        # still start.
        self.assertFalse(
            self.providers["providers"]["xai"]["credential_qualified"]
        )
        self.assertIn('routing.resolve("dispute_arbitration")?', self.bootstrap)
        self.assertIn(".filter(|entry| entry.credential_qualified)", self.bootstrap)
        self.assertIn(
            "/usr/local/libexec/patchyard-request-xai-seat-bearer", self.bootstrap
        )
        self.assertIn("ChildSecret::SeatBearer", self.arbiter_rs)
        # The pipeline resolves disputes in the ruled order: experiment above
        # all arbitration (A77 clause 4), then the third family, and the
        # stubbed escalation only while the arbiter is absent.
        self.assertIn("review_dispute_requires_experiment", self.pipeline_rs)
        self.assertIn("review_dispute_reviewer_upheld", self.pipeline_rs)
        self.assertIn("review_dispute_requires_third_family", self.pipeline_rs)
        # A live-seat failure escalates with the error on the ledger; it never
        # fails the run harder than the stub it replaced.
        self.assertIn("review_dispute_arbitration_failed", self.pipeline_rs)
        self.assertIn("empirically_checkable", self.pipeline_rs)


if __name__ == "__main__":
    unittest.main()
