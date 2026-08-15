"""Provider-neutral guest spend-qualification path.

Static half: the dispatcher and qualification runner ship into the image, are
enabled ahead of the pinned general runner, keep every A142-qualified file
byte-identical, and name no provider. Behavioral half: the dispatcher routes on
the shape of the input drive, and the runner's receipt predicates - exercised
here as the jq filters they are - accept a conforming run and reject the
substitutions they exist to catch.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
IMAGE = ROOT / "worker/image"
DISPATCH = IMAGE / "patchyard-guest-dispatch"
DISPATCH_UNIT = IMAGE / "patchyard-guest-dispatch.service"
QUALIFY = IMAGE / "patchyard-guest-qualify"
GUEST_RUN = IMAGE / "patchyard-guest-run"
GUEST_RUN_UNIT = IMAGE / "patchyard-guest-run.service"
BUILDER = IMAGE / "build-parity-image"
LAUNCHER = ROOT / "worker/runtime/patchyard-provider-run"
POLICY = ROOT / "policy/provider-qualification.json"
WORKER_TASKS = ROOT / "infra/ansible/roles/worker/tasks/main.yml"
SPEND_CHECKER = ROOT / "tools/check-anthropic-spend.py"

# The two files the decision on neutralising the guest runner promised would
# stay byte-identical, restated here so this test fails if a later edit reaches
# for them instead of adding a sibling.
PINNED_GUEST_DIGESTS = {
    "patchyard-guest-run": "229346fb350297b298c1b752188c0f7762ef9d5de77572156843070fecfcc654",
    "patchyard-guest-run.service": "30ffb52decb54933600447daac73d4602ee9856fa695afa0dd52c57a1d8467a0",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jq(filter_text: str, document, *args: str) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
        json.dump(document, handle)
        handle.flush()
        return subprocess.run(
            ["jq", "-e", *args, filter_text, handle.name],
            check=False,
            capture_output=True,
            text=True,
        )


def qualify_filter(name: str) -> str:
    """Return one of the runner's jq predicates by the failure stage above it.

    The predicates are the runner's actual validation, so the test exercises
    the shipped text rather than a paraphrase of it.
    """
    source = QUALIFY.read_text()
    marker = f"FAILURE={name}\n"
    start = source.index(marker) + len(marker)
    body = source[start:]
    opening = body.index("jq -e")
    filter_start = body.index("'", opening) + 1
    filter_end = body.index("'", filter_start)
    return body[filter_start:filter_end]


class Wiring(unittest.TestCase):
    def test_pinned_guest_artifacts_are_untouched(self) -> None:
        for name, expected in PINNED_GUEST_DIGESTS.items():
            self.assertEqual(digest(IMAGE / name), expected, name)

    def test_dispatch_unit_is_ordered_ahead_of_the_general_runner(self) -> None:
        unit = DISPATCH_UNIT.read_text()
        self.assertIn("Before=patchyard-guest-run.service", unit)
        self.assertIn("WantedBy=multi-user.target", unit)
        self.assertIn("ExecStart=/usr/local/sbin/patchyard-guest-dispatch", unit)
        self.assertIn("Type=oneshot", unit)
        # The general runner still owns its own boot when the dispatcher
        # declines: its unit is unchanged and still enabled.
        self.assertIn(
            "ExecStart=/usr/local/sbin/patchyard-guest-run",
            GUEST_RUN_UNIT.read_text(),
        )

    def test_builder_installs_and_enables_the_new_artifacts(self) -> None:
        builder = BUILDER.read_text()
        for source, destination, mode in (
            ("patchyard-guest-dispatch", "/usr/local/sbin/patchyard-guest-dispatch", "0755"),
            ("patchyard-guest-qualify", "/usr/local/sbin/patchyard-guest-qualify", "0755"),
            (
                "patchyard-guest-dispatch.service",
                "/etc/systemd/system/patchyard-guest-dispatch.service",
                "0644",
            ),
        ):
            self.assertIn(
                f'install -m {mode} "$RECIPE_ROOT/{source}" \\\n  "$MOUNT_ROOT{destination}"',
                builder,
            )
        self.assertIn(
            'systemctl --root="$MOUNT_ROOT" enable patchyard-guest-dispatch.service',
            builder,
        )

    def test_recipe_modes_are_pinned_for_every_new_file(self) -> None:
        tasks = WORKER_TASKS.read_text()
        for name, mode in (
            ("patchyard-guest-dispatch", "0755"),
            ("patchyard-guest-qualify", "0755"),
            ("patchyard-guest-dispatch.service", "0644"),
        ):
            self.assertIn(f'{{ name: {name}, mode: "{mode}" }}', tasks)

    def test_new_guest_programs_hold_no_transport(self) -> None:
        """A117 keeps the sole transport on the host; A142 re-proves it here."""
        for path in (DISPATCH, QUALIFY):
            source = path.read_text()
            self.assertTrue(source.startswith("#!"), path.name)
            for command in ("curl", "wget", "/dev/tcp", "openssl s_client"):
                self.assertNotIn(command, source, f"{path.name}: {command}")

    def test_qualification_artifacts_are_absent_from_the_qualified_inventory(self) -> None:
        """Additions are permitted; they must not be smuggled into the pins."""
        checker = SPEND_CHECKER.read_text()
        for name in ("patchyard-guest-dispatch", "patchyard-guest-qualify"):
            self.assertNotIn(f'"{name}"', checker)


class PolicyProjection(unittest.TestCase):
    def setUp(self) -> None:
        self.providers = json.loads(POLICY.read_text())["providers"]

    def test_every_provider_entry_carries_an_observation_block(self) -> None:
        for name, entry in self.providers.items():
            with self.subTest(provider=name):
                self.assertIn("spend_observation", entry)
                observation = entry["spend_observation"]
                self.assertEqual(
                    observation["authorization_ruling"], entry["authorization_ruling"]
                )
                self.assertEqual(
                    observation["qualification_requirement"],
                    "provider-spend-enforcement",
                )

    def test_a125_leaves_the_second_provider_refusal_unenforced(self) -> None:
        refusal = self.providers["openai"]["spend_observation"]["refusal_response"]
        self.assertFalse(refusal["enforced"])
        self.assertIsNone(refusal["http_status"])
        self.assertEqual(refusal["unenforced_basis"], "no-observed-openai-spend-refusal")

    def test_the_first_provider_refusal_stays_enforced(self) -> None:
        refusal = self.providers["anthropic"]["spend_observation"]["refusal_response"]
        self.assertTrue(refusal["enforced"])
        self.assertEqual(refusal["http_status"], [400, 403])
        self.assertIsNone(refusal["unenforced_basis"])

    def test_launcher_projects_the_block_under_a_declared_digest(self) -> None:
        launcher = LAUNCHER.read_text()
        self.assertIn(
            '{schema_version: 1, provider: $provider}\n'
            "      + .providers[$provider].spend_observation",
            launcher,
        )
        self.assertIn("jq -S --arg provider", launcher)
        self.assertIn(
            '== "$(jq -r .qualification_policy_sha256 "$MANIFEST")" ]]', launcher
        )

    def test_projection_is_canonical_and_matches_what_the_guest_requires(self) -> None:
        for name in self.providers:
            with self.subTest(provider=name):
                projection = subprocess.run(
                    [
                        "jq",
                        "-S",
                        "--arg",
                        "provider",
                        name,
                        "{schema_version: 1, provider: $provider}"
                        " + .providers[$provider].spend_observation",
                        str(POLICY),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
                document = json.loads(projection)
                self.assertEqual(document["provider"], name)
                result = jq(
                    qualify_filter("qualification-policy-rejected"),
                    document,
                    "--arg",
                    "provider",
                    name,
                    "--arg",
                    "phase",
                    "temporary_refusal",
                )
                self.assertEqual(result.returncode, 0, result.stderr)


class DispatchRouting(unittest.TestCase):
    """The route is decided by the input drive's shape, never by a name."""

    def route(self, present: bool) -> str:
        source = DISPATCH.read_text()
        self.assertIn("qualification-policy.json", source)
        with tempfile.TemporaryDirectory() as directory:
            peek = Path(directory)
            if present:
                (peek / "qualification-policy.json").write_text("{}\n")
            script = (
                'ROUTE=general\n'
                f'PEEK_ROOT={peek}\n'
                'if [[ -f "$PEEK_ROOT/qualification-policy.json" '
                '&& ! -L "$PEEK_ROOT/qualification-policy.json" ]]; then\n'
                "  ROUTE=qualification\n"
                "fi\n"
                'printf %s "$ROUTE"\n'
            )
            # The condition under test is the dispatcher's own, lifted verbatim.
            self.assertIn(
                'if [[ -f "$PEEK_ROOT/qualification-policy.json" \\\n'
                '  && ! -L "$PEEK_ROOT/qualification-policy.json" ]]; then',
                source,
            )
            return subprocess.run(
                ["bash", "-c", script], check=True, capture_output=True, text=True
            ).stdout

    def test_absent_policy_leaves_the_general_runner_in_charge(self) -> None:
        self.assertEqual(self.route(present=False), "general")

    def test_present_policy_claims_the_boot(self) -> None:
        self.assertEqual(self.route(present=True), "qualification")

    def test_dispatcher_defers_a_missing_drive_to_the_general_runner(self) -> None:
        source = DISPATCH.read_text()
        self.assertIn('[[ -e "$INPUT_DEVICE" ]] || exit 0', source)
        self.assertIn("exec \"$QUALIFICATION_RUNNER\"", source)


class ObservationPredicates(unittest.TestCase):
    """The runner's receipt validation, exercised as the jq it ships."""

    ISSUED_AT = "2026-08-14T12:00:00Z"
    OBSERVED_AT = "2026-08-14T12:01:00Z"
    EXPIRES_AT = "2026-08-14T12:05:00Z"

    def setUp(self) -> None:
        self.filter = qualify_filter("qualification-observation-receipt-rejected")
        providers = json.loads(POLICY.read_text())["providers"]
        self.policies = {
            name: {"schema_version": 1, "provider": name, **entry["spend_observation"]}
            for name, entry in providers.items()
        }

    def check(self, observation, provider: str, phase: str, cap: int = 100):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as policy:
            json.dump(self.policies[provider], policy)
            policy.flush()
            return jq(
                self.filter,
                observation,
                "--slurpfile",
                "policy",
                policy.name,
                "--arg",
                "phase",
                phase,
                "--argjson",
                "cap",
                str(cap),
            )

    def accepted(self, provider: str):
        if provider == "anthropic":
            return {
                "outcome": "accepted",
                "endpoint": "/v1/messages",
                "http_status": 200,
                "observed_at": self.OBSERVED_AT,
                "request_id": "req_" + "A" * 16,
                "request_body_sha256": "0" * 64,
                "response_type": "message",
                "model": "claude-opus-5",
                "expected_workspace_cap_cents": 5000,
                "request_attempts": 1,
                "usage": {"input_tokens": 300000, "output_tokens": 1},
            }
        return {
            "outcome": "accepted",
            "endpoint": "/v1/chat/completions",
            "http_status": 200,
            "observed_at": self.OBSERVED_AT,
            "request_id": "req_" + "a" * 16,
            "request_id_supplied": True,
            "request_body_sha256": "0" * 64,
            "response_type": "chat.completion",
            "model": "gpt-5.6-luna",
            "expected_project_cap_cents": 5000,
            "request_attempts": 1,
            "usage": {"prompt_tokens": 64021, "completion_tokens": 1, "cached_tokens": 0},
        }

    def refused(self, provider: str):
        if provider == "anthropic":
            return {
                "outcome": "refused",
                "endpoint": "/v1/messages",
                "http_status": 400,
                "observed_at": self.OBSERVED_AT,
                "request_id": "req_" + "A" * 16,
                "request_body_sha256": "0" * 64,
                "response_type": "error",
                "expected_workspace_cap_cents": 100,
                "request_attempts": 1,
                "provider_error": {"error_type": "invalid_request_error"},
            }
        return {
            "outcome": "refused",
            "endpoint": "/v1/chat/completions",
            "http_status": 429,
            "observed_at": self.OBSERVED_AT,
            "request_id": None,
            "request_id_supplied": False,
            "request_body_sha256": "0" * 64,
            "expected_project_cap_cents": 100,
            "request_attempts": 1,
            "response_predicate": {
                "enforced": False,
                "basis": "no-observed-openai-spend-refusal",
            },
            "provider_error": {"error_type": "unrecorded"},
        }

    def test_conforming_receipts_pass_for_both_providers(self) -> None:
        for provider in ("anthropic", "openai"):
            with self.subTest(provider=provider, phase="operational_acceptance"):
                result = self.check(
                    self.accepted(provider), provider, "operational_acceptance", 5000
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            with self.subTest(provider=provider, phase="temporary_refusal"):
                result = self.check(
                    self.refused(provider), provider, "temporary_refusal", 100
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_endpoint_from_another_provider_is_rejected(self) -> None:
        observation = self.accepted("anthropic")
        observation["endpoint"] = "/v1/chat/completions"
        self.assertNotEqual(
            self.check(observation, "anthropic", "operational_acceptance", 5000).returncode,
            0,
        )

    def test_cap_must_match_the_authorized_phase_cap(self) -> None:
        observation = self.accepted("anthropic")
        observation["expected_workspace_cap_cents"] = 100
        self.assertNotEqual(
            self.check(observation, "anthropic", "operational_acceptance", 5000).returncode,
            0,
        )

    def test_more_than_one_request_is_rejected(self) -> None:
        observation = self.accepted("openai")
        observation["request_attempts"] = 2
        self.assertNotEqual(
            self.check(observation, "openai", "operational_acceptance", 5000).returncode, 0
        )

    def test_first_provider_refusal_keeps_its_observed_shape(self) -> None:
        """A115's refusal was observed, so its shape stays enforced."""
        for mutation in (
            {"http_status": 429},
            {"response_type": "message"},
            {"provider_error": {"error_type": "rate_limit_error"}},
            {"provider_error": {"error_type": "overloaded_error"}},
        ):
            with self.subTest(mutation=sorted(mutation)[0]):
                observation = {**self.refused("anthropic"), **mutation}
                self.assertNotEqual(
                    self.check(observation, "anthropic", "temporary_refusal", 100).returncode,
                    0,
                )

    def test_second_provider_refusal_records_the_status_as_it_arrived(self) -> None:
        """A125: an unobserved refusal shape is recorded, never matched."""
        for status in (400, 403, 429, 503):
            with self.subTest(status=status):
                observation = self.refused("openai")
                observation["http_status"] = status
                self.assertEqual(
                    self.check(observation, "openai", "temporary_refusal", 100).returncode,
                    0,
                )

    def test_an_unenforced_predicate_may_not_read_as_a_met_one(self) -> None:
        for mutation in (
            {"response_predicate": {"enforced": True, "basis": "no-observed-openai-spend-refusal"}},
            {"response_predicate": {"enforced": False, "basis": "observed"}},
            {"outcome": "accepted"},
        ):
            with self.subTest(mutation=sorted(mutation)[0]):
                observation = {**self.refused("openai"), **mutation}
                self.assertNotEqual(
                    self.check(observation, "openai", "temporary_refusal", 100).returncode,
                    0,
                )

    def test_missing_request_id_is_rejected_where_it_was_observed(self) -> None:
        observation = self.accepted("anthropic")
        observation["request_id"] = None
        self.assertNotEqual(
            self.check(observation, "anthropic", "operational_acceptance", 5000).returncode,
            0,
        )

    def test_unsupplied_request_id_must_say_so(self) -> None:
        observation = self.accepted("openai")
        observation["request_id"] = None
        self.assertNotEqual(
            self.check(observation, "openai", "operational_acceptance", 5000).returncode, 0
        )


class IssuanceWindow(unittest.TestCase):
    def test_observation_must_fall_inside_the_bearer_lifetime(self) -> None:
        source = QUALIFY.read_text()
        start = source.index("--slurpfile issuance /input/issuance.json")
        filter_start = source.index("'", start) + 1
        window = source[filter_start : source.index("'", filter_start)]
        issuance = {
            "issued_at": "2026-08-14T12:00:00Z",
            "expires_at": "2026-08-14T12:05:00Z",
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump(issuance, handle)
            handle.flush()
            for observed_at, expected in (
                ("2026-08-14T12:01:00Z", 0),
                ("2026-08-14T11:59:59Z", 1),
                ("2026-08-14T12:05:00Z", 1),
            ):
                with self.subTest(observed_at=observed_at):
                    result = jq(
                        window,
                        {"observed_at": observed_at},
                        "--slurpfile",
                        "issuance",
                        handle.name,
                    )
                    self.assertEqual(
                        0 if result.returncode == 0 else 1, expected, result.stderr
                    )


if __name__ == "__main__":
    unittest.main()
