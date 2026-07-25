import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
FILES = ROOT / "infra/ansible/roles/control_plane/files"
ENVIRONMENT = ROOT / "infra/ansible/roles/control_plane/templates/patchyard-supervisor.env.j2"
GROUP_VARS = ROOT / "infra/ansible/group_vars/all.yml"
GRANTS = ROOT / "infra/ansible/roles/control_plane/files/postgresql-grants.sql"


class Session14QualificationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stage = (FILES / "patchyard-stage-session14-qualification").read_text()
        cls.runner = (FILES / "patchyard-run-session14-qualification").read_text()
        cls.unit = (FILES / "factory-session14-qualification.service").read_text()
        cls.environment = ENVIRONMENT.read_text()
        cls.group_vars = GROUP_VARS.read_text()
        cls.grants = GRANTS.read_text()

    def test_form_intake_is_required_before_the_supervisor_stops(self) -> None:
        intake = self.stage.index("JOIN factory.users")
        stop = self.stage.index('systemctl stop "$SUPERVISOR"')
        self.assertLess(intake, stop)
        self.assertIn("requests.source = 'dashboard:' || users.id::text", self.stage)
        self.assertIn("requests.status = 'queued'", self.stage)
        self.assertIn("users.enabled", self.stage)
        self.assertNotIn("factoryctl request new", self.stage)

    def test_claimed_recovery_is_limited_to_the_session14_run_and_holder(self) -> None:
        self.assertIn("requests.status = 'claimed'", self.stage)
        self.assertIn(
            "runs.branch = 'factory/$REQUEST_ID-session14-evidence-lifecycle'",
            self.stage,
        )
        self.assertIn("leases.holder <> 'factory-session14-qualification'", self.stage)
        self.assertIn("runs.state NOT IN", self.stage)

    def test_injected_evidence_rejection_requires_durable_zero_secret_and_cleanup_proof(self) -> None:
        self.assertIn('FACTORY_EVIDENCE_SELECTORS="#session14_qualification_absent"', self.runner)
        self.assertIn('factoryctl run "$REQUEST_ID" --session14-qualification', self.runner)
        self.assertIn('.state == "evidence_failed"', self.stage)
        self.assertIn(".artifact_count == 0", self.stage)
        self.assertIn(".security_proofs == 1", self.stage)
        self.assertIn("evidence.security_checks_completed", self.stage)
        self.assertIn("local_log_scan", self.stage)
        self.assertIn("preview_log_scan", self.stage)
        self.assertEqual(self.stage.count("bytes_scanned"), 2)
        self.assertEqual(self.stage.count("sentinel_matches"), 2)
        self.assertIn("cleanup_complete", self.stage)

    def test_operator_service_is_bounded_and_cancellation_uses_sigint(self) -> None:
        self.assertIn("Conflicts=factory-supervisor.service", self.unit)
        self.assertIn("SupplementaryGroups=factory-manager systemd-journal", self.unit)
        self.assertIn("TimeoutStartSec=7200s", self.unit)
        self.assertIn("TimeoutStopSec=180s", self.unit)
        self.assertIn("KillSignal=SIGINT", self.unit)
        self.assertIn("ProtectSystem=strict", self.unit)

    def test_failed_unit_reset_is_conditional_and_the_daemon_is_restored(self) -> None:
        self.assertEqual(self.stage.count('systemctl reset-failed "$SERVICE"'), 2)
        self.assertEqual(self.stage.count('systemctl is-failed --quiet "$SERVICE"'), 2)
        self.assertIn('trap cleanup EXIT HUP INT TERM', self.stage)
        self.assertIn('systemctl start "$SUPERVISOR"', self.stage)

    def test_real_publisher_base_is_versioned_desired_state_not_a_fixture_sha(self) -> None:
        self.assertIn("FACTORY_BASE_SHA={{ factory_fieldbook_base_sha }}", self.environment)
        self.assertNotIn("session9_target_sha", self.environment)
        self.assertRegex(
            self.group_vars,
            r"(?m)^factory_fieldbook_base_sha: [0-9a-f]{40}$",
        )

    def test_preview_target_is_the_live_php_endpoint_for_the_session7_slice(self) -> None:
        self.assertIn(
            "FACTORY_EVIDENCE_PREVIEW_PATH=/mfieldbook/leads/assign.php?rqst_id=96429",
            self.environment,
        )

    def test_ci_wait_retry_counter_is_granted_to_the_supervisor(self) -> None:
        self.assertRegex(
            self.grants,
            r"(?s)GRANT UPDATE \(.*?lifecycle_attempts.*?\) ON factory\.runs TO patchyard_supervisor;",
        )


if __name__ == "__main__":
    unittest.main()
