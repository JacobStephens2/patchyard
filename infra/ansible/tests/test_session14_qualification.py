import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
FILES = ROOT / "infra/ansible/roles/control_plane/files"


class Session14QualificationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stage = (FILES / "patchyard-stage-session14-qualification").read_text()
        cls.runner = (FILES / "patchyard-run-session14-qualification").read_text()
        cls.unit = (FILES / "factory-session14-qualification.service").read_text()

    def test_form_intake_is_required_before_the_supervisor_stops(self) -> None:
        intake = self.stage.index("JOIN factory.users")
        stop = self.stage.index('systemctl stop "$SUPERVISOR"')
        self.assertLess(intake, stop)
        self.assertIn("requests.status = 'queued'", self.stage)
        self.assertIn("users.enabled", self.stage)
        self.assertNotIn("factoryctl request new", self.stage)

    def test_injected_failure_requires_durable_zero_secret_and_cleanup_proof(self) -> None:
        self.assertIn('FACTORY_EVIDENCE_SELECTORS="#session14_qualification_absent"', self.runner)
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


if __name__ == "__main__":
    unittest.main()
