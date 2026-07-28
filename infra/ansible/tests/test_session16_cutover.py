#!/usr/bin/env python3
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
FILES = ROOT / "infra" / "ansible" / "roles" / "control_plane" / "files"


class Session16CutoverContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backup = (FILES / "patchyard-backup").read_text()
        cls.restore = (FILES / "patchyard-restore").read_text()
        cls.restore_evidence_probe = (
            FILES / "patchyard-restore-evidence-probe"
        ).read_text()
        cls.deployed = (FILES / "patchyard-deployed-version").read_text()
        cls.postgresql_grants = (FILES / "postgresql-grants.sql").read_text()
        cls.restore_play = (ROOT / "infra" / "ansible" / "restore.yml").read_text()
        cls.restore_operator = (ROOT / "infra" / "restore-drill.sh").read_text()
        cls.plan_operator = (ROOT / "infra" / "plan.sh").read_text()
        cls.replace_operator = (ROOT / "infra" / "replace-worker.sh").read_text()
        cls.tofu_operator = (ROOT / "infra" / "tofu.sh").read_text()
        cls.rollback_operator = (ROOT / "infra" / "rollback-control.sh").read_text()
        cls.rollback_boundary = (
            ROOT / "infra" / "ansible" / "rollback-boundary.yml"
        ).read_text()
        cls.qualifier = (FILES / "qualify-factory-control").read_text()
        cls.tasks = (
            ROOT
            / "infra"
            / "ansible"
            / "roles"
            / "control_plane"
            / "tasks"
            / "main.yml"
        ).read_text()
        cls.worker_tasks = (
            ROOT
            / "infra"
            / "ansible"
            / "roles"
            / "worker"
            / "tasks"
            / "main.yml"
        ).read_text()
        cls.group_vars = (
            ROOT / "infra" / "ansible" / "group_vars" / "all.yml"
        ).read_text()
        cls.github = (ROOT / "infra" / "github" / "main.tf").read_text()
        cls.digitalocean = (ROOT / "infra" / "digitalocean" / "main.tf").read_text()
        cls.spaces = (ROOT / "infra" / "digitalocean" / "backup.tf").read_text()
        cls.restore_plan_change_count = (
            ROOT / "infra" / "restore-plan-change-count.jq"
        )
        cls.publisher = (
            ROOT / "crates" / "factory-supervisor" / "src" / "publisher.rs"
        ).read_text()
        cls.observability = (
            ROOT / "crates" / "factory-supervisor" / "src" / "observability.rs"
        ).read_text()
        cls.auth = (
            ROOT / "crates" / "factory-web" / "src" / "auth.rs"
        ).read_text()

    def test_backup_quiesces_writers_and_captures_all_durable_state(self) -> None:
        self.assertIn(
            "readonly services=(caddy.service factory-dashboard.service "
            "factory-supervisor.service)",
            self.backup,
        )
        self.assertIn("systemctl stop", self.backup)
        self.assertIn("pg_dump", self.backup)
        self.assertIn("--exclude-table-data=public._sqlx_migrations", self.backup)
        self.assertIn("artifacts.sha256", self.backup)
        self.assertIn("runtime.sha256", self.backup)
        self.assertIn("table_counts", self.backup)
        self.assertIn("contains a non-regular entry", self.backup)
        self.assertIn("backup_busy active_work=", self.backup)
        self.assertIn("service_resume_failed", self.backup)
        self.assertIn("cleanup_and_restart true || exit 28", self.backup)
        self.assertIn('>"$payload_root/database.dump"', self.backup)
        self.assertNotIn('--file="$payload_root/database.dump"', self.backup)

    def test_backup_is_client_encrypted_before_atomic_off_host_publication(self) -> None:
        encrypt = self.backup.index("age --encrypt")
        upload = self.backup.index("put-object")
        latest = self.backup.rindex("--key LATEST")
        self.assertLess(encrypt, upload)
        self.assertLess(upload, latest)
        self.assertIn("head-object", self.backup)
        self.assertIn("ciphertext_sha256", self.backup)
        self.assertIn("--verify-latest", self.backup)
        self.assertIn("LATEST generation receipt differs", self.backup)
        self.assertIn("get-bucket-versioning", self.backup)
        self.assertIn("backup_bucket_versioning_failed", self.backup)

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
        for variable in (
            "factory_backup_runtime_access_key",
            "factory_backup_runtime_secret_key",
            "factory_backup_bucket",
            "factory_backup_endpoint",
            "factory_backup_age_recipient",
        ):
            self.assertIn(f"{{{{ {variable} | quote }}}}", backup_env)
        self.assertNotIn("IDENTITY", backup_env)
        self.assertIn("factory_backup_age_identity", self.spaces)
        self.assertIn("sensitive = true", self.spaces)

    def test_restore_drill_receives_no_persistent_backup_delete_key(self) -> None:
        backup_environment_task = self.tasks.split(
            "- name: Install the bucket-scoped backup environment", maxsplit=1
        )[1].split("\n- name:", maxsplit=1)[0]
        self.assertIn(
            "when: not (factory_restore_drill | default(false) | bool)",
            backup_environment_task,
        )
        drill_absence_task = self.tasks.split(
            "- name: Keep the delete-capable backup key off restore-drill disk",
            maxsplit=1,
        )[1].split("\n- name:", maxsplit=1)[0]
        self.assertIn("path: /etc/patchyard/backup.env", drill_absence_task)
        self.assertIn("state: absent", drill_absence_task)
        self.assertIn(
            "when: factory_restore_drill | default(false) | bool",
            drill_absence_task,
        )

    def test_qualification_rejects_all_checkout_runtime_state(self) -> None:
        self.assertIn(
            "git -C /opt/patchyard status --porcelain --untracked-files=all --ignored",
            self.qualifier,
        )
        self.assertIn('test -z "$checkout_runtime_state"', self.qualifier)
        converge_hosts = (
            FILES / "patchyard-converge-hosts"
        ).read_text()
        self.assertIn(
            "status --porcelain --untracked-files=all --ignored",
            converge_hosts,
        )

    def test_qualification_inspects_an_instantiated_child_unit(self) -> None:
        self.assertNotIn(
            "systemctl show patchyard-child@.service", self.qualifier
        )
        self.assertEqual(
            self.qualifier.count(
                "systemctl show "
                "patchyard-child@00000000000000000000000000000000.service"
            ),
            2,
        )

    def test_qualification_tracks_the_exact_grafana_projection_grants(self) -> None:
        blocks = {
            view: [column.strip().rstrip(",") for column in columns.splitlines()]
            for columns, view in re.findall(
                r"GRANT SELECT \(\n(.*?)\n\) ON factory\."
                r"(grafana_(?:request_summary|run_metrics)) TO grafana_ro;",
                self.postgresql_grants,
                re.DOTALL,
            )
        }
        self.assertEqual(set(blocks), {"grafana_request_summary", "grafana_run_metrics"})
        self.assertIn("run_class", blocks["grafana_run_metrics"])
        expected_total = sum(len(columns) for columns in blocks.values())
        self.assertEqual(expected_total, 20)
        self.assertIn(
            f"grantee = 'grafana_ro'\")\" = {expected_total}",
            self.qualifier,
        )

    def test_qualification_proves_idle_supervisor_metrics(self) -> None:
        self.assertIn(
            'describe_gauge!(\n        "factory_supervisor_up",',
            self.observability,
        )
        self.assertIn('gauge!("factory_supervisor_up").set(1.0)', self.observability)
        self.assertIn(
            "# HELP factory_supervisor_up Supervisor process is running and "
            "exporting metrics.",
            self.qualifier,
        )
        self.assertIn("^factory_supervisor_up 1(\\.0)?$", self.qualifier)
        self.assertNotIn("# HELP factory_runs_total", self.qualifier)

    def test_qualification_tracks_the_exact_chromium_package_pin(self) -> None:
        chromium_nevra = re.search(
            r"^chromium_nevra:\s*(\S+)$", self.group_vars, re.MULTILINE
        )
        self.assertIsNotNone(chromium_nevra)
        self.assertIn(
            f'test "$(rpm -q chromium)" = {chromium_nevra.group(1)}',
            self.qualifier,
        )

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
        self.assertIn("--disable-triggers", self.restore)
        self.assertIn('<"$restore_root/payload/database.dump"', self.restore)
        self.assertIn("RESTORE_GRAFANA_REQUEST_CANARY", self.restore_play)
        self.assertIn("restored_grafana_canary.rc != 0", self.restore_play)
        self.assertIn("production restore requires inactive writer", self.restore)
        self.assertIn("production restore requires zero active work", self.restore)
        self.assertIn("assert_production_clean_baseline", self.restore)
        self.assertIn("assert_production_database_clean_baseline", self.restore)
        self.assertIn("production database contains durable pipeline state", self.restore)
        for table in ("requests", "runs", "events", "artifacts", "pr_state", "leases"):
            self.assertIn(f"factory.{table}", self.restore)
        self.assertIn("production ideas seed differs from reviewed desired state", self.restore)
        destructive = self.restore.rindex('rm -r -- "$artifact_root" "$runtime_root"')
        self.assertLess(
            self.restore.index("migrated database version differs"), destructive
        )
        self.assertLess(
            self.restore.rindex("assert_production_database_clean_baseline"),
            destructive,
        )
        self.assertLess(destructive, self.restore.index("TRUNCATE TABLE"))

    def test_restore_evidence_selector_drains_query_output_before_selection(
        self,
    ) -> None:
        function_body = self.restore_evidence_probe.split(
            "select_artifact_row() {", maxsplit=1
        )[1].split("\n}", maxsplit=1)[0]
        selector = (
            "set -euo pipefail\nselect_artifact_row() {"
            + function_body
            + '\n}\nselect_artifact_row "$1" "$2"'
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "artifacts"
            real_artifact = root / "run" / "evidence.json"
            real_artifact.parent.mkdir(parents=True)
            real_artifact.write_text("evidence")
            rows = Path(temporary) / "rows.tsv"
            valid = "00000000-0000-4000-8000-000000000002\trun/evidence.json\tbbb"
            rows.write_text(
                "00000000-0000-4000-8000-000000000001\tmissing.json\taaa\n"
                + valid
                + "\n"
                + "\n".join(
                    f"00000000-0000-4000-8000-{index:012d}\tmissing-{index}.json\tccc"
                    for index in range(3, 1003)
                )
                + "\n"
            )
            result = subprocess.run(
                ["bash", "-c", selector, "selector-test", str(rows), str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), valid)
        self.assertNotIn("| while", self.restore_evidence_probe)

    def test_restore_evidence_probe_uses_application_cookie_contract(self) -> None:
        for constant in ("LOGIN_COOKIE", "SESSION_COOKIE"):
            match = re.search(
                rf'^pub const {constant}: &str = "([^"]+)";$',
                self.auth,
                re.MULTILINE,
            )
            self.assertIsNotNone(match)
            self.assertIn(match.group(1), self.restore_evidence_probe)
        self.assertNotIn("__Host-factory_login", self.restore_evidence_probe)
        self.assertNotIn("__Host-factory_session", self.restore_evidence_probe)

    def test_restore_probe_refreshes_the_password_on_every_attempt(self) -> None:
        provision = self.restore_play.index(
            "- name: Create a drill-only admin after count verification"
        )
        reset = self.restore_play.index(
            "- name: Set the drill-only admin password for this probe attempt"
        )
        probe = self.restore_play.index(
            "- name: Install the historical evidence recovery probe"
        )
        self.assertLess(provision, reset)
        self.assertLess(reset, probe)
        reset_task = self.restore_play[reset:probe]
        self.assertIn("- reset-password", reset_task)
        self.assertIn("stdin: \"{{ factory_restore_probe_password }}\"", reset_task)
        self.assertIn("no_log: true", reset_task)

    def test_clean_host_drill_has_reviewed_create_and_destroy_plans(self) -> None:
        self.assertIn("digitalocean_droplet.restore_drill[0]", self.restore_operator)
        self.assertIn("PATCHYARD_RESTORE_APPROVED", self.restore_operator)
        self.assertIn("PATCHYARD_RESTORE_DESTROY_APPROVED", self.restore_operator)
        self.assertIn("factory_restore_drill:true", self.restore_operator)
        self.assertIn('factory_dashboard_accounts_file:"/dev/null"', self.restore_operator)
        self.assertIn('factory_github_app_private_key_file:"/dev/null"', self.restore_operator)
        guard = self.restore_play.index("Refuse restore outside the generated drill inventory")
        roles = self.restore_play.index("roles:")
        self.assertLess(guard, roles)
        self.assertIn("factory_restore_expected_host", self.restore_operator)
        self.assertIn("factory_restore_expected_droplet_id", self.restore_operator)
        self.assertIn("restore_drill_id", self.restore_operator)
        self.assertIn("metadata/v1/id", self.restore_play)
        self.assertLess(
            self.restore_play.index("Wait for SSH after drill-host creation"),
            self.restore_play.index("Read the target DigitalOcean droplet identity"),
        )
        self.assertNotIn("Remove only the clean recovery artifact targets", self.restore_play)
        self.assertIn("restore_target_refused", self.restore)
        self.assertIn('lookup(\\"env\\", \\"ETA_RESTORE_IDENTITY\\")', self.restore_operator)
        self.assertNotIn("factory_backup_age_identity_file", self.restore_operator)
        self.assertIn("routine DigitalOcean plan refused while the restore drill exists", self.plan_operator)
        self.assertIn("state_list=", self.plan_operator)
        self.assertIn("grep -Fxq", self.plan_operator)
        self.assertIn("DigitalOcean apply refused while the restore drill exists", self.tofu_operator)
        self.assertIn("PATCHYARD_RESTORE_APPROVED_SHA256", self.restore_operator)
        self.assertIn("skipping apply", self.restore_operator)
        self.assertIn("PATCHYARD_RESTORE_DRILL_APPLY=destroy", self.restore_operator)

    def test_restore_plan_change_count_fails_closed_and_counts_mutations(self) -> None:
        def count(plan: dict[str, object]) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["jq", "-er", "-f", str(self.restore_plan_change_count)],
                input=json.dumps(plan),
                text=True,
                capture_output=True,
                check=False,
            )

        no_op = count(
            {
                "resource_changes": [
                    {"change": {"actions": ["no-op"]}},
                ],
                "output_changes": {"restore_drill_id": {"actions": ["no-op"]}},
            }
        )
        self.assertEqual(no_op.returncode, 0)
        self.assertEqual(no_op.stdout.strip(), "0")

        resource_create = count(
            {
                "resource_changes": [
                    {"change": {"actions": ["no-op"]}},
                    {"change": {"actions": ["create"]}},
                ],
                "output_changes": {"restore_drill_id": {"actions": ["no-op"]}},
            }
        )
        self.assertEqual(resource_create.returncode, 0)
        self.assertEqual(resource_create.stdout.strip(), "1")

        output_update = count(
            {
                "resource_changes": [],
                "output_changes": {"restore_drill_id": {"actions": ["update"]}},
            }
        )
        self.assertEqual(output_update.returncode, 0)
        self.assertEqual(output_update.stdout.strip(), "1")

        for malformed in (
            {},
            {"resource_changes": None, "output_changes": {}},
            {"resource_changes": [], "output_changes": None},
        ):
            self.assertNotEqual(count(malformed).returncode, 0)

    def test_worker_replacement_plan_is_mechanically_address_pinned(self) -> None:
        self.assertIn("verify_worker_plan", self.replace_operator)
        self.assertIn("digitalocean_droplet.worker", self.replace_operator)
        self.assertIn("digitalocean_firewall.worker", self.replace_operator)
        self.assertIn("changes an out-of-scope resource", self.replace_operator)
        self.assertGreaterEqual(
            self.replace_operator.count('verify_worker_plan "$PLAN_FILE"'), 2
        )
        self.assertGreaterEqual(
            self.replace_operator.count("require_clean_revision"), 3
        )
        self.assertIn("committed, clean operator checkout", self.plan_operator)

    def test_clean_worker_imports_the_pinned_remi_signing_key(self) -> None:
        bootstrap = self.worker_tasks.index(
            "- name: Install the checksum-pinned Remi repository bootstrap"
        )
        key_import = self.worker_tasks.index(
            "- name: Import the fingerprint-pinned Remi package signing key"
        )
        packages = self.worker_tasks.index(
            "- name: Install checksum-pinned targeted-PHPUnit runtime packages"
        )
        self.assertLess(bootstrap, key_import)
        self.assertLess(key_import, packages)
        self.assertIn("ansible.builtin.rpm_key:", self.worker_tasks[key_import:packages])
        self.assertIn(
            "key: /etc/pki/rpm-gpg/RPM-GPG-KEY-remi.el9",
            self.worker_tasks[key_import:packages],
        )
        self.assertIn(
            'fingerprint: "{{ remi_signing_key_fingerprint }}"',
            self.worker_tasks[key_import:packages],
        )
        self.assertIn(
            "remi_signing_key_fingerprint: "
            "B1ABF71E14C9D74897E198A8B19527F1478F8947",
            self.group_vars,
        )
        package_task = self.worker_tasks[packages:].split("\n- name:", 1)[0]
        self.assertIn("disable_gpg_check: false", package_task)

    def test_rollback_binds_live_revision_and_verifies_durable_state(self) -> None:
        self.assertIn('current=$(resolve_reviewed_revision "$(installed_revision', self.rollback_operator)
        self.assertIn("installed revision changed after rollback plan review", self.rollback_operator)
        self.assertIn("capture_durable_state", self.rollback_operator)
        self.assertIn("table-sha256", self.rollback_operator)
        self.assertIn("ORDER BY row_to_json(t)::text", self.rollback_operator)
        self.assertIn("audit-row-sha256", self.rollback_operator)
        self.assertIn("changed or removed an existing audit event", self.rollback_operator)
        self.assertIn("rollback target emitted an audit action outside", self.rollback_operator)
        self.assertIn("login-challenge-sha256", self.rollback_operator)
        self.assertIn("changed or removed an existing login challenge", self.rollback_operator)
        self.assertIn("target_challenge_delta <= 4", self.rollback_operator)
        self.assertIn("total_challenge_delta <= 8", self.rollback_operator)
        self.assertIn(
            'cmp --silent "$before_stable" "$target_stable"',
            self.rollback_operator,
        )
        self.assertIn(
            'cmp --silent "$before_stable" "$recovered_stable"',
            self.rollback_operator,
        )
        self.assertIn(
            'durable_state:"verified_rollback_and_recovery_equal_except_declared_account_audits_and_qualification_login_challenges"',
            self.rollback_operator,
        )
        self.assertIn("unexpected_rollback_audits", self.rollback_operator)
        self.assertIn("sudo -n runuser -u factory-manager -- git", self.rollback_operator)
        self.assertIn("set_rollback_boundary enter", self.rollback_operator)
        self.assertIn("set_rollback_boundary exit", self.rollback_operator)
        self.assertIn("dashboard Full stop", self.rollback_boundary)
        self.assertIn("factory.proposer_runs", self.rollback_boundary)
        self.assertIn('port="{{ item }}" protocol="tcp" reject', self.rollback_boundary)
        self.assertIn("patchyard-backup.service", self.rollback_boundary)
        self.assertIn(
            "ConditionPathExists=!/var/lib/patchyard/control/rollback-boundary",
            self.rollback_boundary,
        )
        self.assertIn("path: /var/lib/patchyard/control", self.tasks)
        self.assertIn(
            "assert_path /var/lib/patchyard/control root factory 750",
            self.qualifier,
        )
        self.assertGreaterEqual(
            self.rollback_boundary.count(
                "/var/lib/patchyard/control/rollback-boundary"
            ),
            3,
        )
        self.assertIn('deploy_and_qualify_revision "$target"', self.rollback_operator)
        self.assertIn(
            'deploy_and_qualify_revision "$return_revision"',
            self.rollback_operator,
        )
        self.assertIn("rollback-emergency-recovery", self.rollback_operator)
        self.assertIn("qualification_migration_count", self.rollback_operator)
        self.assertIn("schema_version:2", self.rollback_operator)
        self.assertIn("control_address", self.rollback_operator)
        self.assertIn("release-boundary", self.rollback_operator)
        self.assertIn("PATCHYARD_ROLLBACK_RELEASE_APPROVED", self.rollback_operator)
        self.assertIn("StrictHostKeyChecking=yes", self.rollback_operator)
        rollback_deploy = self.rollback_operator.split(
            "deploy_and_qualify_revision() {", maxsplit=1
        )[1].split("stable_durable_state() {", maxsplit=1)[0]
        self.assertGreaterEqual(rollback_deploy.count("|| return"), 6)
        self.assertIn(
            "public boundary and reboot-durable backup exclusion remain in force",
            self.rollback_operator,
        )
        self.assertIn("evidence_verification_pending=true", self.rollback_operator)
        target_audit_refusal = self.rollback_operator.split(
            "rollback target emitted an audit action", maxsplit=1
        )[1].split("deploy_and_qualify_revision", maxsplit=1)[0]
        self.assertIn("evidence_verification_pending=true", target_audit_refusal)
        self.assertIn(
            "rollback evidence did not verify; public boundary and reboot-durable backup exclusion remain in force for explicit release",
            self.rollback_operator,
        )

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
        self.assertIn("curl --config -", self.deployed)
        self.assertIn("--connect-timeout 10 --max-time 30", self.deployed)
        self.assertNotIn('--header "Authorization: Bearer', self.deployed)

    def test_a111_keeps_factory_approvals_optional_and_marker_human_only(self) -> None:
        self.assertIn("required_approving_review_count = 0", self.github)
        self.assertIn("A111 keeps approvals optional", self.github)
        master = self.github.split('data "github_repository" "fieldbook"', maxsplit=1)[0]
        self.assertIn('push_allowances  = ["/JacobStephens2", "/example-teammate"]', master)
        self.assertIn('pattern             = "deploy/production"', self.github)
        marker = self.github.split(
            'resource "github_branch_protection" "fieldbook_deploy_production"',
            maxsplit=1,
        )[1]
        self.assertIn('push_allowances  = ["/JacobStephens2", "/example-teammate"]', marker)
        self.assertIn("blocks_creations = true", marker)
        self.assertIn("allows_force_pushes = true", marker)

    def test_ipv4_rollback_boundary_is_coupled_to_disabled_droplet_ipv6(self) -> None:
        self.assertEqual(3, self.digitalocean.count("ipv6          = false"))
        self.assertIn('family="ipv4"', self.rollback_boundary)

    def test_installed_parent_and_deployed_version_operator_env_are_repaired(self) -> None:
        self.assertIn("path: /var/lib/patchyard/proposer-inbox", self.tasks)
        self.assertIn("src: patchyard-deployed-version.env.j2", self.tasks)
        self.assertIn("patchyard-deployed-version-unconfigured", self.tasks)
        self.assertIn('OsString::from("XDG_STATE_HOME")', self.publisher)
        self.assertIn('OsString::from("GH_CONFIG_DIR")', self.publisher)


if __name__ == "__main__":
    unittest.main()
