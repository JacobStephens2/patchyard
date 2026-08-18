"""The file-driven collector path must be the same instrument, not a second one.

The runner replaces a controlling terminal. Two properties carry the weight:

- Equivalence. Driving `collect()` through the runner's channel must produce
  the same record as driving it with a plain callable, for the same answers.
  If it does not, the web path is a different instrument and its output is not
  the evidence the checkers were written against.
- Sequential integrity. A reading is answered only for the prompt currently
  open. Reading 4 of the revocation collector means "the console state while
  the mapping still carries the sentinel"; answers staged before their prompt opened
  would produce a record that passes every checker while recording nothing live.
"""

import builtins
import grp
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "tools/attended-collector-runner.py"
COLLECTOR = ROOT / "tools/openai-wif-federation-revocation.py"

PROVIDER = "idp_TESTONLYPROVIDER0000000"
SERVICE_ACCOUNT = "user-TESTONLYSERVICEACCOUNT"
CONSOLE = "https://platform.openai.com/settings/organization/security/test"
SUBJECT = "patchyard-control-plane"


def load(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def load_runner():
    return load("attended_collector_runner", RUNNER)


def active_reading() -> str:
    return json.dumps(
        {
            "console_location": CONSOLE,
            "enabled": True,
            "identity_provider_id": PROVIDER,
            "mapped_service_account_id": SERVICE_ACCOUNT,
            "mapping_present": True,
            "subject_mapping_expression": SUBJECT,
            "uploaded_jwks_mode": True,
        }
    )


def sentinel_reading() -> str:
    return json.dumps(
        {
            "console_location": CONSOLE,
            "enabled": True,
            "identity_provider_id": PROVIDER,
            "mapped_service_account_id": SERVICE_ACCOUNT,
            "mapping_present": True,
            "subject_mapping_expression": (
                "sub=patchyard-control-plane-REVOKED-"
                "openai-revocation-20260809-0123456789"
            ),
            "uploaded_jwks_mode": True,
        }
    )


def save_confirmation(expression: str) -> str:
    return json.dumps(
        {
            "product_approval_presented": False,
            "product_approval_completed": False,
            "capture_sha256": None,
            "observed_expression": expression,
        }
    )


# Reload, reading, reload, reading, Save, confirmation, and so on.
# Reading 4 is still the sentinel: it is captured before restoration.
ANSWERS = [
    "RELOADED",
    active_reading(),
    "RELOADED",
    active_reading(),
    "MUTATION COMPLETE",
    save_confirmation(
        "sub=patchyard-control-plane-REVOKED-"
        "openai-revocation-20260809-0123456789"
    ),
    "RELOADED",
    sentinel_reading(),
    "RELOADED",
    sentinel_reading(),
    "RESTORATION COMPLETE",
    save_confirmation(SUBJECT),
    "RELOADED",
    active_reading(),
]


class ChannelTests(unittest.TestCase):
    """The channel in isolation: no collector, no provider, no root."""

    def setUp(self) -> None:
        self.runner = load_runner()
        self.tmp = tempfile.TemporaryDirectory()
        self.session = Path(self.tmp.name) / "session"
        self.session.mkdir(mode=0o700)
        self.channel = self.runner.SessionChannel(self.session)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def answer(self, seq: int, value: str) -> None:
        (self.session / "replies" / f"reply-{seq}.json").write_text(
            json.dumps({"seq": seq, "value": value})
        )

    def drive(self, prompt: str, writer=None) -> dict:
        """Answer a prompt the way an operator does: only once it is open.

        A reply written before `ask()` publishes the prompt is staging, and the
        runner refuses it by design - so every test that wants to reach the
        parse checks has to write from another thread after publication.
        """
        out: dict = {}

        def run() -> None:
            try:
                out["value"] = self.channel.ask(prompt)
            except BaseException as error:  # noqa: BLE001 - recorded, re-raised by caller
                out["error"] = error

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        deadline = time.monotonic() + 10
        while (
            worker.is_alive()
            and not self.channel.prompt_path.exists()
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        if writer is not None and self.channel.prompt_path.exists():
            seq = json.loads(self.channel.prompt_path.read_text())["seq"]
            writer(seq)
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive(), "ask() did not return")
        return out

    def test_a_reply_answers_the_open_prompt(self) -> None:
        """The accepting case: prompt is published, reply is returned verbatim."""
        out = self.drive(
            self.runner.READING_PROMPT, lambda seq: self.answer(seq, active_reading())
        )
        self.assertEqual(out.get("value"), active_reading())

    def test_the_prompt_is_published_before_blocking(self) -> None:
        published = threading.Event()
        result: list[str] = []

        def drive() -> None:
            result.append(self.channel.ask(self.runner.READING_PROMPT))

        worker = threading.Thread(target=drive, daemon=True)
        worker.start()
        # ask() publishes prompt.json and then status.json as two separate
        # atomic writes, so waiting on the prompt alone can observe the gap
        # between them. Wait for the pair to agree, as a front end must.
        while not (
            (self.session / "prompt.json").exists()
            and (self.session / "status.json").exists()
        ):
            published.wait(0.05)
        prompt = json.loads((self.session / "prompt.json").read_text())
        self.assertEqual(prompt["seq"], 1)
        self.assertEqual(prompt["kind"], "console_reading")
        status = json.loads((self.session / "status.json").read_text())
        self.assertEqual(status["state"], "awaiting_input")
        self.assertEqual(status["open_prompt_seq"], 1)
        self.answer(1, active_reading())
        worker.join(timeout=10)
        self.assertEqual(result, [active_reading()])
        self.assertFalse((self.session / "prompt.json").exists())

    def test_a_pause_is_classified_with_its_phrase(self) -> None:
        """A front end renders an acknowledgement control, not a text box."""
        kind, phrase = self.channel._classify(
            "Type 'RESTORATION COMPLETE' after the actor finishes> "
        )
        self.assertEqual(kind, "operator_pause")
        self.assertEqual(phrase, "RESTORATION COMPLETE")
        self.assertEqual(
            self.channel._classify(self.runner.READING_PROMPT),
            ("console_reading", None),
        )

    def test_staged_reply_is_refused(self) -> None:
        """The property this file exists for: answers cannot precede prompts.

        Prompt 1 is answered normally; prompt 2's answer was already on disk
        before prompt 2 opened, which is exactly the pre-staging that would
        forge an attestation.
        """
        self.drive(
            self.runner.READING_PROMPT, lambda seq: self.answer(seq, active_reading())
        )
        self.answer(2, active_reading())
        out = self.drive(self.runner.READING_PROMPT)
        self.assertIsInstance(out.get("error"), self.runner.RunnerError)
        self.assertIn("staged", str(out["error"]))

    def test_reply_seq_must_match_the_open_prompt(self) -> None:
        """A renamed file cannot answer a prompt it was not written for."""
        out = self.drive(
            self.runner.READING_PROMPT,
            lambda seq: (self.session / "replies" / f"reply-{seq}.json").write_text(
                json.dumps({"seq": 7, "value": active_reading()})
            ),
        )
        self.assertIsInstance(out.get("error"), self.runner.RunnerError)
        self.assertIn("seq", str(out["error"]))

    def test_malformed_reply_is_refused(self) -> None:
        out = self.drive(
            self.runner.READING_PROMPT,
            lambda seq: (self.session / "replies" / f"reply-{seq}.json").write_text("{not json"),
        )
        self.assertIsInstance(out.get("error"), self.runner.RunnerError)

    def test_non_string_value_is_refused(self) -> None:
        out = self.drive(
            self.runner.READING_PROMPT,
            lambda seq: (self.session / "replies" / f"reply-{seq}.json").write_text(
                json.dumps({"seq": seq, "value": 5})
            ),
        )
        self.assertIsInstance(out.get("error"), self.runner.RunnerError)

    def test_oversized_reply_is_refused(self) -> None:
        out = self.drive(
            self.runner.READING_PROMPT,
            lambda seq: (self.session / "replies" / f"reply-{seq}.json").write_text(
                json.dumps(
                    {"seq": seq, "value": "x" * (self.runner.MAX_REPLY_BYTES + 10)}
                )
            ),
        )
        self.assertIsInstance(out.get("error"), self.runner.RunnerError)

    def test_symlinked_reply_is_refused(self) -> None:
        target = Path(self.tmp.name) / "elsewhere.json"
        target.write_text(json.dumps({"seq": 1, "value": active_reading()}))
        out = self.drive(
            self.runner.READING_PROMPT,
            lambda seq: (self.session / "replies" / f"reply-{seq}.json").symlink_to(target),
        )
        self.assertIsInstance(out.get("error"), self.runner.RunnerError)

    def test_status_carries_a_pid_so_a_dead_run_is_visible(self) -> None:
        """A crashed run must be distinguishable from a live one: an
        `awaiting_input` status whose pid is gone may have left an open
        mutation window on the control plane."""
        self.channel.write_status("awaiting_input")
        status = json.loads((self.session / "status.json").read_text())
        self.assertEqual(status["pid"], os.getpid())

    def test_state_files_are_not_group_or_world_readable(self) -> None:
        """With no reply group the session is root-only, so state is too."""
        self.channel.write_status("running")
        mode = (self.session / "status.json").stat().st_mode & 0o077
        self.assertEqual(mode, 0)

    def test_state_files_are_group_readable_under_a_reply_group(self) -> None:
        """A front end that cannot read the prompt cannot render a form.

        The session directory and replies inbox are relaxed to the reply group,
        but the state files were published 0600 root-only regardless. The front
        end could submit an answer and never see the question, so a live run
        showed as `unknown` with no form while the collector waited at prompt 1.
        """
        gid = os.getgid()
        group = grp.getgrgid(gid).gr_name
        session = Path(self.tmp.name) / "grouped"
        session.mkdir(mode=0o750)
        channel = self.runner.SessionChannel(session, group)
        channel.write_status("awaiting_input")

        status = session / "status.json"
        self.assertEqual(status.stat().st_gid, gid)
        mode = status.stat().st_mode & 0o777
        self.assertEqual(mode, 0o640, "group must read; world must not")

    def test_state_files_follow_the_prompt_too(self) -> None:
        """The prompt is the file the front end most needs to read."""
        gid = os.getgid()
        group = grp.getgrgid(gid).gr_name
        session = Path(self.tmp.name) / "grouped-prompt"
        session.mkdir(mode=0o750)
        channel = self.runner.SessionChannel(session, group)
        channel._write_json(channel.prompt_path, {"seq": 1, "prompt": "x"})

        mode = channel.prompt_path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o640)
        self.assertEqual(channel.prompt_path.stat().st_gid, gid)


class SessionDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = load_runner()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_existing_directory_is_refused(self) -> None:
        """Reusing a session could answer the wrong window."""
        path = Path(self.tmp.name) / "session"
        path.mkdir()
        with self.assertRaises(self.runner.RunnerError) as caught:
            self.runner.prepare_session(path)
        self.assertIn("already exists", str(caught.exception))

    def test_unknown_reply_group_is_refused(self) -> None:
        with self.assertRaises(self.runner.RunnerError) as caught:
            self.runner.prepare_session(
                Path(self.tmp.name) / "s1", "no-such-group-exists-here"
            )
        self.assertIn("group", str(caught.exception))

    def test_root_reply_group_is_refused(self) -> None:
        """Granting the reply group to gid 0 would hand the front end the very
        privilege this split exists to avoid."""
        with self.assertRaises(self.runner.RunnerError) as caught:
            self.runner.prepare_session(Path(self.tmp.name) / "s2", "root")
        self.assertIn("root", str(caught.exception))

    def test_symlinked_session_is_refused(self) -> None:
        target = Path(self.tmp.name) / "target"
        target.mkdir()
        link = Path(self.tmp.name) / "link"
        link.symlink_to(target)
        with self.assertRaises(self.runner.RunnerError):
            self.runner.prepare_session(link)


class EquivalenceTests(unittest.TestCase):
    """The whole claim: same answers in, same record out.

    Drives the real revocation `collect()` twice with a stubbed exchanger and
    clock - once with a plain list-backed callable standing in for the
    interactive path, once through the runner's file channel - and compares the
    records. No provider is contacted and no signing key is read, because
    `collect()` takes the exchanger as a parameter.
    """

    def setUp(self) -> None:
        self.runner = load_runner()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def policy(self) -> dict:
        return {
            "issuer": {"id": PROVIDER, "jwks_kid": "unused"},
            "service_account": {"id": SERVICE_ACCOUNT},
        }

    def collector(self):
        return load("collector_under_test", COLLECTOR)

    def fake_exchange(self, _policy, _key, run_id, key_role) -> dict:
        return {
            "key_role": key_role,
            "attempt_count": 1,
            "started_at": "2026-08-09T12:00:00.000000Z",
            "assertion_descriptor": {"kid": "k", "jwk_thumbprint_sha256": "t"},
            "exchange_request": {"run_id": run_id},
            "receipt": {"http_status": 200, "access_token_supplied": True},
            "credential_removed_at": "2026-08-09T12:00:01.000000Z",
            "lifecycle_instrument_sha256": "0" * 64,
        }

    def run_collect(self, module, input_fn) -> dict:
        # A monotonic clock keeps the two runs comparable without sleeping;
        # the settling floor is satisfied by advancing it, not by waiting.
        state = {"t": 0}

        def clock():
            from datetime import datetime, timedelta, timezone

            state["t"] += 100
            return datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc) + timedelta(
                seconds=state["t"]
            )

        run_id = "openai-revocation-20260809-0123456789"
        pairing = "openai/codex/gpt-5.6-sol/xhigh"
        task_id = "task_synthetic_runner_0001"
        policy_sha256 = module.source_binding()["policy_sha256"]
        collector_sha256 = module.source_binding()["collector_sha256"]
        extracted = {
            "run_id": run_id,
            "pairing": pairing,
            "codex_task_id": task_id,
            "policy_sha256": policy_sha256,
            "collector_sha256": collector_sha256,
            "permitted_mutation": module.PERMITTED_MUTATION,
            "permitted_restoration": module.PERMITTED_RESTORATION,
            "deadline_at": "2026-08-09T12:45:00Z",
        }
        fence = json.dumps(extracted, indent=2, sort_keys=True)
        authorization = {
            "source": "github_issue_comment",
            "issue_url": module.AUTHORIZATION_ISSUE_URL,
            "comment_url": (
                f"{module.AUTHORIZATION_ISSUE_URL}#issuecomment-5328162490"
            ),
            "comment_id": 5328162490,
            "created_at": "2026-08-09T12:00:00Z",
            "author_login": module.AUTHORIZATION_AUTHOR,
            "body": (
                "Authorize one OpenAI requirement-4 attended run.\n\n"
                f"```json\n{fence}\n```\n"
            ),
            "extracted": extracted,
            "attempt": 1,
            "human_attestation_obtained": False,
            "human_authorship_mechanically_proven": False,
        }
        return module.collect(
            run_id=run_id,
            authorization=authorization,
            model_identity={"pairing": pairing, "codex_task_id": task_id},
            mutation_kind="subject-expression",
            policy=self.policy(),
            input_fn=input_fn,
            clock=clock,
            sleeper=lambda _seconds: None,
            exchanger=self.fake_exchange,
        )

    @staticmethod
    def normalize(record: dict) -> str:
        """Strip wall-clock-derived fields; compare everything else exactly."""
        blob = json.dumps(record, sort_keys=True, default=str)
        import re

        return re.sub(r"\d{4}-\d{2}-\d{2}T[0-9:.]+Z", "<TS>", blob)

    def test_file_driven_run_matches_the_interactive_run(self) -> None:
        answers = list(ANSWERS)
        interactive = self.run_collect(self.collector(), lambda _p: answers.pop(0))

        session = Path(self.tmp.name) / "session"
        session.mkdir(mode=0o700)
        channel = self.runner.SessionChannel(session)

        # An operator answering each prompt only once it is open. Writing from
        # a separate thread is what the console does over SSH.
        def operator() -> None:
            """Answer whichever prompt is currently open, once each.

            Self-correcting rather than lock-step: a thread that assumed the
            order and guessed wrong would leave collect() blocked forever and
            hang the suite instead of failing it.
            """
            answered = 0
            deadline = time.monotonic() + 60
            while answered < len(ANSWERS) and time.monotonic() < deadline:
                try:
                    published = json.loads(channel.prompt_path.read_text())
                except (FileNotFoundError, json.JSONDecodeError):
                    time.sleep(0.02)
                    continue
                seq = published["seq"]
                if seq <= answered or seq > len(ANSWERS):
                    time.sleep(0.02)
                    continue
                (session / "replies" / f"reply-{seq}.json").write_text(
                    json.dumps({"seq": seq, "value": ANSWERS[seq - 1]})
                )
                answered = seq

        worker = threading.Thread(target=operator, daemon=True)
        worker.start()
        file_driven = self.run_collect(self.collector(), channel.ask)
        worker.join(timeout=30)

        self.assertEqual(self.normalize(interactive), self.normalize(file_driven))
        self.assertTrue(file_driven["bracketing_control"])
        self.assertFalse(file_driven["mutation_receipt_obtained"])

    def test_builtins_binding_reaches_the_collector_defaults(self) -> None:
        """The substitution mechanism itself: a module imported after the bind
        must pick the channel up at its `input_fn` defaults, with no argument
        threaded through. If this stops holding, the runner silently falls back
        to reading stdin."""
        session = Path(self.tmp.name) / "bind"
        session.mkdir(mode=0o700)
        channel = self.runner.SessionChannel(session)

        def operator() -> None:
            deadline = time.monotonic() + 10
            while not channel.prompt_path.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            if channel.prompt_path.exists():
                seq = json.loads(channel.prompt_path.read_text())["seq"]
                (session / "replies" / f"reply-{seq}.json").write_text(
                    json.dumps({"seq": seq, "value": active_reading()})
                )

        worker = threading.Thread(target=operator, daemon=True)
        worker.start()
        real = builtins.input
        builtins.input = channel.ask
        try:
            module = self.collector()
            captured = module.capture_console_reading(
                "test reading", self.policy(), clock=module.BASE.utc_now
            )
        finally:
            builtins.input = real
            worker.join(timeout=10)
        self.assertEqual(captured["state"]["identity_provider_id"], PROVIDER)


class AnswerPromptTests(unittest.TestCase):
    """The one-terminal front end for answering an open prompt."""

    def setUp(self) -> None:
        self.tool = load("answer_attended_prompt", ROOT / "tools/answer-attended-prompt.py")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_true_parses_to_a_boolean_not_a_string(self) -> None:
        """A live run was rejected for a string where a boolean was required."""
        self.assertIs(self.tool.parse_field("true"), True)
        self.assertIs(self.tool.parse_field("false"), False)
        self.assertIs(self.tool.parse_field(" true "), True)

    def test_prose_stays_a_string(self) -> None:
        self.assertEqual(self.tool.parse_field("Uploaded JWKS"), "Uploaded JWKS")

    def test_blank_is_null_not_empty_string(self) -> None:
        self.assertIsNone(self.tool.parse_field(""))
        self.assertIsNone(self.tool.parse_field("   "))

    def test_structured_values_parse_as_json(self) -> None:
        self.assertEqual(self.tool.parse_field('["a", "b"]'), ["a", "b"])
        self.assertEqual(self.tool.parse_field('{"kid": "x"}'), {"kid": "x"})

    def test_malformed_structured_value_is_refused(self) -> None:
        with self.assertRaises(self.tool.AnswerError):
            self.tool.parse_field("{not json")

    def test_reading_keys_come_from_the_collector_not_a_copy(self) -> None:
        """Hardcoding the key set here would let the tool drift from the instrument."""
        keys = self.tool.collector_keys("openai-wif-federation-revocation.py")
        collector = load("collector_for_keys", COLLECTOR)
        self.assertEqual(set(keys), collector.MAPPING_STATE_KEYS)

    def test_publish_writes_the_envelope_the_runner_expects(self) -> None:
        session = Path(self.tmp.name) / "s"
        (session / "replies").mkdir(parents=True)
        self.tool.publish(session, 4, '{"a": 1}')

        payload = json.loads((session / "replies" / "reply-4.json").read_text())
        self.assertEqual(payload, {"seq": 4, "value": '{"a": 1}'})

    def test_publish_refuses_to_overwrite_an_answered_prompt(self) -> None:
        session = Path(self.tmp.name) / "s2"
        (session / "replies").mkdir(parents=True)
        self.tool.publish(session, 1, "x")
        with self.assertRaises(self.tool.AnswerError):
            self.tool.publish(session, 1, "y")

    def test_publish_leaves_no_temporary_file_behind(self) -> None:
        """A stray .tmp in the inbox would trip the staged-reply refusal."""
        session = Path(self.tmp.name) / "s3"
        (session / "replies").mkdir(parents=True)
        self.tool.publish(session, 2, "x")
        names = sorted(entry.name for entry in (session / "replies").iterdir())
        self.assertEqual(names, ["reply-2.json"])


if __name__ == "__main__":
    unittest.main()
