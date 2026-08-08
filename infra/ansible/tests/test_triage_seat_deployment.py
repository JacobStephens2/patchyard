import ast
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONTROL = ROOT / "infra/ansible/roles/control_plane"
SEAT = CONTROL / "files/patchyard-triage-seat"
MINTER = CONTROL / "files/patchyard-mint-seat-bearer"
SUDOERS = CONTROL / "files/patchyard-seat-mint.sudoers"
TMPFILES = CONTROL / "files/patchyard-seat.tmpfiles"
UNIT = CONTROL / "files/factory-supervisor.service"
TASKS = CONTROL / "tasks/main.yml"
ENVIRONMENT = CONTROL / "templates/patchyard-supervisor.env.j2"
QUALIFY = CONTROL / "templates/qualify-factory-control.j2"
BOOTSTRAP = ROOT / "crates/factory-supervisor/src/bootstrap.rs"
STAGES = ROOT / "crates/factory-supervisor/src/stages.rs"
LIFECYCLE = ROOT / "tools/anthropic-wif-lifecycle.py"
ROUTING = ROOT / "policy/routing.json"
PROVIDERS = ROOT / "policy/provider-egress.json"


class TriageSeatDeployment(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.seat = SEAT.read_text()
        cls.minter = MINTER.read_text()
        cls.sudoers = SUDOERS.read_text()
        cls.tmpfiles = TMPFILES.read_text()
        cls.unit = UNIT.read_text()
        cls.tasks = TASKS.read_text()
        cls.environment = ENVIRONMENT.read_text()
        cls.qualify = QUALIFY.read_text()
        cls.bootstrap = BOOTSTRAP.read_text()
        cls.stages = STAGES.read_text()
        cls.routing = json.loads(ROUTING.read_text())
        cls.providers = json.loads(PROVIDERS.read_text())

    def test_runtime_scripts_parse_and_are_installed_with_fixed_roles(self) -> None:
        ast.parse(self.seat)
        ast.parse(self.minter)
        self.assertIn("destination: /usr/local/libexec/patchyard-triage-seat", self.tasks)
        self.assertIn(
            "destination: /usr/local/sbin/patchyard-mint-seat-bearer", self.tasks
        )
        self.assertIn("validate: /usr/sbin/visudo -cf %s", self.tasks)
        self.assertIn("test -x /usr/local/libexec/patchyard-triage-seat", self.qualify)
        self.assertIn("test -x /usr/local/sbin/patchyard-mint-seat-bearer", self.qualify)

    def test_minter_reuses_the_exact_qualified_wif_source(self) -> None:
        observed = hashlib.sha256(LIFECYCLE.read_bytes()).hexdigest()
        match = re.search(r'BASE_HARNESS_SHA256 = \(\n    "([0-9a-f]{64})"', self.minter)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), observed)
        self.assertIn("base.accepted_exchange(", self.minter)
        self.assertNotIn("/v1/oauth/token", self.minter)
        self.assertNotIn("mint_assertion(", self.minter)

    def test_fifth_seat_variable_is_a_path_and_never_a_secret_value(self) -> None:
        self.assertIn('OsString::from("PATCHYARD_BEARER_FILE")', self.stages)
        self.assertIn("path.as_os_str().to_owned()", self.stages)
        self.assertIn('require_environment("PATCHYARD_BEARER_FILE")', self.seat)
        self.assertNotIn("ANTHROPIC_API_KEY", self.seat + self.minter + self.stages)
        self.assertNotIn("OPENAI_API_KEY", self.seat + self.minter + self.stages)
        self.assertNotIn("bearer_auth", self.seat)

    def test_bearer_stage_is_tmpfs_private_and_removed_on_restore_drills(self) -> None:
        self.assertEqual(
            self.tmpfiles,
            "d /run/patchyard-seats 0700 factory-manager factory -\n",
        )
        self.assertIn("FACTORY_SEAT_SCRATCH_ROOT=/run/patchyard-seats", self.environment)
        self.assertIn("ReadWritePaths=", self.unit)
        self.assertIn("/run/patchyard-seats", self.unit)
        self.assertIn("path: /run/patchyard-seats", self.tasks)
        self.assertIn("- /run/patchyard-seats", self.tasks)
        self.assertIn("assert_path /run/patchyard-seats factory-manager factory 700", self.qualify)
        self.assertIn("NoNewPrivileges=true", self.unit)
        self.assertIn("ProtectSystem=strict", self.unit)

    def test_sudo_grant_cannot_select_a_provider_or_non_stage_destination(self) -> None:
        self.assertEqual(
            self.sudoers,
            "Cmnd_Alias PATCHYARD_MINT_SEAT_BEARER = "
            "/usr/local/sbin/patchyard-mint-seat-bearer Anthropic "
            "/run/patchyard-seats/agent-*/bearer\n"
            "factory-manager ALL=(root) NOPASSWD: PATCHYARD_MINT_SEAT_BEARER\n",
        )
        self.assertIn('arguments[0] != "Anthropic"', self.minter)
        self.assertIn("path.parent.parent != SEAT_ROOT", self.minter)
        self.assertIn("STAGE_PATTERN.fullmatch(path.parent.name)", self.minter)

    def test_gate_is_triage_only_and_live_execution_requires_a_qualified_seat(self) -> None:
        """Live execution is permitted only while the triage seat is qualified.

        This assertion previously required `live_provider_execution` to be
        false, which kept seat installation and policy activation in separate
        changes. Activation has now happened, in its own reviewed change, so
        the transitional assertion is replaced by the invariant that outlasts
        it: if live execution is on, the provider triage resolves to must be
        credential_qualified. Turning the flag on for an unqualified seat is
        the thing that must never pass.
        """
        triage_provider = self.routing["rules"]["triage"]["seat"]["provider"]
        if self.routing["live_provider_execution"]:
            entry = next(
                provider
                for provider in self.providers["providers"].values()
                if provider["display_name"] == triage_provider
            )
            self.assertTrue(
                entry["credential_qualified"],
                f"live execution is on but {triage_provider} is not qualified",
            )
        qualified = [
            provider["display_name"]
            for provider in self.providers["providers"].values()
            if provider["credential_qualified"]
        ]
        self.assertEqual(qualified, ["Anthropic"])
        self.assertIn('routing.resolve("triage")', self.bootstrap)
        self.assertIn("credential_qualified is false in policy/provider-egress.json", self.bootstrap)
        self.assertNotIn('commands.insert(\n        "implement"', self.bootstrap)
        self.assertNotIn('commands.insert(\n        "implementation_review"', self.bootstrap)




class WorkerQualificationInvariant(unittest.TestCase):
    """A138's invariant lives in one checker, and the worker is not it.

    A135 recorded that credential_qualified is read at ten sites, nine of which
    assert every flag is false. PR 130 narrowed the nine Python checkers and
    missed this one, an Ansible-deployed shell script - which A135 also names as
    the only site that actually gates anything. The first converge after
    Anthropic qualified shipped a correct policy to the worker and its own
    qualification then refused it.
    """

    SCRIPT = (
        Path(__file__).resolve().parents[3]
        / "infra/ansible/roles/worker/files/qualify-factory-worker"
    )
    POLICY = (
        Path(__file__).resolve().parents[3] / "policy/provider-egress.json"
    )

    def test_worker_does_not_assert_that_no_provider_is_qualified(self) -> None:
        source = self.SCRIPT.read_text()
        self.assertNotIn("all(. == false)", source)
        self.assertNotIn("[.providers[].credential_qualified]", source)

    def test_worker_shape_assertion_accepts_a_qualified_provider(self) -> None:
        """The live policy has one qualified provider and must still qualify."""
        policy = json.loads(self.POLICY.read_text())
        qualified = [
            name
            for name, entry in policy["providers"].items()
            if entry.get("credential_qualified")
        ]
        self.assertTrue(qualified, "expected at least one qualified provider")
        self.assertEqual(policy["schema_version"], 1)
        self.assertEqual(len(policy["providers"]), 13)
        for entry in policy["providers"].values():
            self.assertIsInstance(entry["credential_qualified"], bool)
            self.assertGreaterEqual(len(entry["hostnames"]), 1)


if __name__ == "__main__":
    unittest.main()
