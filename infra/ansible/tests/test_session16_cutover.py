#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
FILES = ROOT / "infra" / "ansible" / "roles" / "control_plane" / "files"


class Session16CutoverContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backup = (FILES / "patchyard-backup").read_text()
        cls.restore = (FILES / "patchyard-restore").read_text()
        cls.deployed = (FILES / "patchyard-deployed-version").read_text()
        cls.restore_play = (ROOT / "infra" / "ansible" / "restore.yml").read_text()
        cls.restore_operator = (ROOT / "infra" / "restore-drill.sh").read_text()
        cls.rollback_operator = (ROOT / "infra" / "rollback-control.sh").read_text()
        cls.github = (ROOT / "infra" / "github" / "main.tf").read_text()
        cls.spaces = (ROOT / "infra" / "digitalocean" / "backup.tf").read_text()

    def test_backup_quiesces_writers_and_captures_all_durable_state(self) -> None:
        self.assertIn("readonly services=(factory-dashboard.service factory-supervisor.service)", self.backup)
        self.assertIn("systemctl stop", self.backup)
        self.assertIn("pg_dump", self.backup)
        self.assertIn("--exclude-table-data=public._sqlx_migrations", self.backup)
        self.assertIn("artifacts.sha256", self.backup)
        self.assertIn("runtime.sha256", self.backup)
        self.assertIn("table_counts", self.backup)
        self.assertIn("contains a non-regular entry", self.backup)

    def test_backup_is_client_encrypted_before_atomic_off_host_publication(self) -> None:
        encrypt = self.backup.index("age --encrypt")
        upload = self.backup.index("put-object")
        latest = self.backup.index("--key LATEST")
        self.assertLess(encrypt, upload)
        self.assertLess(upload, latest)
        self.assertIn("head-object", self.backup)
        self.assertIn("ciphertext_sha256", self.backup)

    def test_live_host_receives_no_recovery_private_key(self) -> None:
        backup_env = (
            ROOT
            / "infra"
            / "ansible"
            / "roles"
            / "control_plane"
            / "templates"
            / "patchyard-backup.env.j2"
        ).read_text()
        self.assertIn("FACTORY_BACKUP_AGE_RECIPIENT", backup_env)
        self.assertNotIn("IDENTITY", backup_env)
        self.assertIn("factory_backup_age_identity", self.spaces)
        self.assertIn("sensitive = true", self.spaces)

    def test_restore_verifies_ciphertext_payload_rows_and_files(self) -> None:
        for required in (
            "encrypted backup hash mismatch",
            "pg_restore",
            "row count mismatch",
            "sha256sum --check",
            ".artifacts.file_count",
            ".runtime.file_count",
            "migrated database table set differs",
            "migrated database version differs",
        ):
            self.assertIn(required, self.restore)
        self.assertIn("factoryctl", self.restore_play)
        self.assertIn("historical evidence", self.restore_play)

    def test_clean_host_drill_has_reviewed_create_and_destroy_plans(self) -> None:
        self.assertIn("digitalocean_droplet.restore_drill[0]", self.restore_operator)
        self.assertIn("PATCHYARD_RESTORE_APPROVED", self.restore_operator)
        self.assertIn("PATCHYARD_RESTORE_DESTROY_APPROVED", self.restore_operator)
        self.assertIn("factory_restore_drill:true", self.restore_operator)
        self.assertIn('factory_dashboard_accounts_file:"/dev/null"', self.restore_operator)
        self.assertIn('factory_github_app_private_key_file:"/dev/null"', self.restore_operator)

    def test_rollback_binds_live_revision_and_verifies_durable_state(self) -> None:
        self.assertIn('current=$(resolve_reviewed_revision "$(installed_revision', self.rollback_operator)
        self.assertIn("installed revision changed after rollback plan review", self.rollback_operator)
        self.assertIn("capture_durable_state", self.rollback_operator)
        self.assertIn('cmp --silent "$before_state" "$after_state"', self.rollback_operator)
        self.assertIn('durable_state:"verified_equal"', self.rollback_operator)

    def test_spaces_authorities_are_split(self) -> None:
        self.assertIn('name = "patchyard-backup-management"', self.spaces)
        self.assertIn('permission = "fullaccess"', self.spaces)
        self.assertIn('name = "patchyard-backup-runtime"', self.spaces)
        self.assertIn('permission = "readwrite"', self.spaces)
        self.assertIn("versioning", self.spaces)
        self.assertIn("prevent_destroy = true", self.spaces)

    def test_deploy_marker_reader_mints_read_only_fieldbook_scope(self) -> None:
        self.assertIn("heads/deploy/production", self.deployed)
        self.assertIn("repositories\":[\"fieldbook\"]", self.deployed)
        self.assertIn("permissions\":{\"contents\":\"read\"}", self.deployed)
        self.assertIn("unexpected installation scope", self.deployed)

    def test_a109_keeps_factory_approvals_optional_and_marker_human_only(self) -> None:
        self.assertIn("required_approving_review_count = 0", self.github)
        self.assertIn('pattern             = "deploy/production"', self.github)
        self.assertIn('push_allowances  = ["/JacobStephens2", "/example-teammate"]', self.github)


if __name__ == "__main__":
    unittest.main()
