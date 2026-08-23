import ast
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONTROL = ROOT / "infra/ansible/roles/control_plane"
SEAT = CONTROL / "files/patchyard-triage-seat"
MINTER = CONTROL / "files/patchyard-mint-seat-bearer"
REQUESTER = CONTROL / "files/patchyard-request-seat-bearer"
MINT_UNIT = CONTROL / "files/patchyard-seat-mint@.service"
POLKIT = CONTROL / "files/50-patchyard-seat-mint.rules"
TMPFILES = CONTROL / "files/patchyard-seat.tmpfiles"
PROBE_TMPFILES = CONTROL / "files/patchyard-seat-mint-probe.tmpfiles"
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
        cls.requester = REQUESTER.read_text()
        cls.mint_unit = MINT_UNIT.read_text()
        cls.polkit = POLKIT.read_text()
        cls.tmpfiles = TMPFILES.read_text()
        cls.probe_tmpfiles = PROBE_TMPFILES.read_text()
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
        syntax = subprocess.run(
            ["/usr/bin/bash", "-n", str(REQUESTER)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        self.assertIn("destination: /usr/local/libexec/patchyard-triage-seat", self.tasks)
        self.assertIn(
            "destination: /usr/local/sbin/patchyard-mint-seat-bearer", self.tasks
        )
        self.assertIn(
            "dest: /usr/local/libexec/patchyard-request-seat-bearer",
            self.tasks,
        )
        self.assertIn(
            "dest: /etc/systemd/system/patchyard-seat-mint@.service",
            self.tasks,
        )
        self.assertIn(
            "dest: /etc/polkit-1/rules.d/50-patchyard-seat-mint.rules",
            self.tasks,
        )
        self.assertIn("test -x /usr/local/libexec/patchyard-triage-seat", self.qualify)
        self.assertIn(
            "test -x /usr/local/libexec/patchyard-request-seat-bearer",
            self.qualify,
        )
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
        self.assertEqual(
            self.probe_tmpfiles,
            "d /run/patchyard-seat-mint-probes 0700 root root -\n",
        )
        self.assertIn("FACTORY_SEAT_SCRATCH_ROOT=/run/patchyard-seats", self.environment)
        self.assertIn("ReadWritePaths=", self.unit)
        self.assertIn("/run/patchyard-seats", self.unit)
        self.assertIn("path: /run/patchyard-seats", self.tasks)
        self.assertIn("- /run/patchyard-seats", self.tasks)
        self.assertIn("assert_path /run/patchyard-seats factory-manager factory 700", self.qualify)
        self.assertIn("NoNewPrivileges=true", self.unit)
        self.assertIn("ProtectSystem=strict", self.unit)

    def test_root_service_cannot_select_a_provider_or_non_stage_destination(self) -> None:
        self.assertIn(
            "ExecStart=/usr/local/sbin/patchyard-mint-seat-bearer Anthropic "
            "/run/patchyard-seats/%i/bearer",
            self.mint_unit,
        )
        self.assertIn('[[ $# -eq 2 && "$PROVIDER" == Anthropic ]]', self.requester)
        self.assertIn('[[ "$OUTPUT" == "$ROOT/$ID/bearer" ]]', self.requester)
        self.assertIn('arguments[0] != "Anthropic"', self.minter)
        self.assertIn("path.parent.parent != SEAT_ROOT", self.minter)
        self.assertIn("STAGE_PATTERN.fullmatch(path.parent.name)", self.minter)
        self.assertIn("state: absent", self.tasks.split(
            "Remove the superseded seat-mint sudo grant", 1
        )[1].split("- name:", 1)[0])

    def test_root_activation_preserves_supervisor_hardening(self) -> None:
        self.assertIn("NoNewPrivileges=true", self.unit)
        self.assertIn("ProtectSystem=strict", self.unit)
        self.assertIn("User=root", self.mint_unit)
        self.assertIn("NoNewPrivileges=true", self.mint_unit)
        self.assertIn("ProtectSystem=strict", self.mint_unit)
        self.assertIn(
            "CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE", self.mint_unit
        )
        self.assertIn("ReadWritePaths=/run/patchyard-seats", self.mint_unit)
        self.assertNotIn("/usr/bin/sudo", self.bootstrap)
        self.assertIn(
            '/usr/local/libexec/patchyard-request-seat-bearer', self.bootstrap
        )

    def test_polkit_delegation_is_uuid_only_start_and_carries_no_bearer(self) -> None:
        self.assertIn('subject.user == "factory-manager"', self.polkit)
        self.assertIn("^patchyard-seat-mint@agent-", self.polkit)
        self.assertIn('action.lookup("verb") == "start"', self.polkit)
        self.assertNotIn('action.lookup("verb") == "stop"', self.polkit)
        self.assertNotIn("bearer", self.polkit)

    def test_hardened_caller_probe_has_accepting_and_rejection_cases(self) -> None:
        self.assertIn(
            "Only root can create the one-use marker that selects this path",
            self.qualify,
        )
        self.assertEqual(
            self.qualify.count(
                "/usr/local/libexec/patchyard-request-seat-bearer"
            ),
            3,
        )
        self.assertIn("/usr/bin/setpriv --no-new-privs", self.qualify)
        self.assertIn(
            "Anthropic \"$SEAT_MINT_PROBE_STAGE/bearer\"", self.qualify
        )
        self.assertIn("patchyard-providerless-seat-mint-probe", self.qualify)
        self.assertIn(
            "OpenAI \"$SEAT_MINT_PROBE_STAGE/bearer\"", self.qualify
        )
        self.assertIn('test ! -e "$SEAT_MINT_PROBE_STAGE/bearer"', self.qualify)
        self.assertIn("consume_providerless_probe(output)", self.minter)
        self.assertIn("base.load_public_jwk(base.ACTIVE_SIGNING_KEY)", self.minter)
        self.assertIn("marker_metadata.st_uid != 0", self.minter)
        self.assertIn("marker_metadata.st_gid != 0", self.minter)

    def test_caller_runs_with_no_new_privileges_and_rejects_other_providers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="patchyard-seat-request-") as temporary:
            fixture = Path(temporary)
            seat_root = fixture / "seats"
            stage_id = "agent-00000000-0000-4000-8000-000000000000"
            stage = seat_root / stage_id
            stage.mkdir(parents=True, mode=0o700)
            stub = fixture / "systemctl"
            calls = fixture / "systemctl.calls"
            stub.write_text(
                "#!/usr/bin/bash\n"
                "set -euo pipefail\n"
                f"printf '%s\\n' \"$*\" >> {calls}\n"
                'unit=${!#}\n'
                'id=${unit#patchyard-seat-mint@}\n'
                'id=${id%.service}\n'
                f"printf '%s' patchyard-providerless-seat-mint-probe > "
                f'"{seat_root}/$id/bearer"\n'
                f'chmod 0600 "{seat_root}/$id/bearer"\n'
            )
            stub.chmod(0o700)
            user = pwd.getpwuid(os.getuid()).pw_name
            group = grp.getgrgid(os.getgid()).gr_name
            requester = fixture / "requester"
            requester.write_text(
                self.requester.replace(
                    "ROOT=/run/patchyard-seats", f"ROOT={seat_root}"
                )
                .replace("/usr/bin/systemctl", str(stub))
                .replace("factory-manager:factory", f"{user}:{group}")
            )
            requester.chmod(0o700)
            bearer = stage / "bearer"
            accepted = subprocess.run(
                [
                    "/usr/bin/setpriv",
                    "--no-new-privs",
                    "--",
                    str(requester),
                    "Anthropic",
                    str(bearer),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(
                bearer.read_text(), "patchyard-providerless-seat-mint-probe"
            )
            self.assertEqual(bearer.stat().st_mode & 0o777, 0o600)
            accepted_calls = calls.read_text()
            self.assertIn(f"patchyard-seat-mint@{stage_id}.service", accepted_calls)

            bearer.unlink()
            rejected = subprocess.run(
                [
                    "/usr/bin/setpriv",
                    "--no-new-privs",
                    "--",
                    str(requester),
                    "OpenAI",
                    str(bearer),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse(bearer.exists())
            self.assertEqual(calls.read_text(), accepted_calls)

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
        """The live policy has qualified providers and must still qualify."""
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



class RequesterReachableByTheRealCaller(unittest.TestCase):
    """The requester must be executable by the identity that actually calls it.

    The supervisor's primary group is factory; factory-manager reaches it only as
    a supplementary group. Installing the requester group-owned by
    factory-manager at 0750 left it executable by the running service but NOT by
    `runuser --user factory-manager --group factory`, which drops supplementary
    groups - so the qualification probe added to catch unreachable-callers was
    itself unable to reach the requester, and blocked every qualification.

    Granting to factory removes the dependency on a supplementary group and makes
    the probe a faithful stand-in for the caller rather than a stricter one.
    """

    def test_requester_is_group_owned_by_the_supervisor_primary_group(self) -> None:
        block = TASKS.read_text().split(
            "Install the hardened supervisor seat-mint requester"
        )[1]
        block = block.split("- name:")[0]
        self.assertIn("group: factory\n", block)
        self.assertNotIn("group: \"{{ factory_manager_user }}\"", block)
        self.assertIn('mode: "0750"', block)


if __name__ == "__main__":
    unittest.main()
