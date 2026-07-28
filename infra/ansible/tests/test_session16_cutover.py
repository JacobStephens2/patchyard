#!/usr/bin/env python3
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
FILES = ROOT / "infra" / "ansible" / "roles" / "control_plane" / "files"
TEMPLATES = (
    ROOT / "infra" / "ansible" / "roles" / "control_plane" / "templates"
)


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
        cls.converge_operator = (ROOT / "infra" / "ansible" / "converge.sh").read_text()
        cls.rollback_operator = (ROOT / "infra" / "rollback-control.sh").read_text()
        cls.rollback_function_prelude = cls.rollback_operator.split(
            "\ncontrol_target() {", maxsplit=1
        )[0]
        cls.rollback_boundary = (
            ROOT / "infra" / "ansible" / "rollback-boundary.yml"
        ).read_text()
        cls.qualifier = (TEMPLATES / "qualify-factory-control.j2").read_text()
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
        cls.rpm_mirror_sync = (
            ROOT
            / "infra"
            / "ansible"
            / "roles"
            / "control_plane"
            / "templates"
            / "patchyard-sync-rpm-mirror.j2"
        ).read_text()
        cls.chromium_visual_baseline = json.loads(
            (ROOT / "fixtures" / "visual" / "chromium-baseline.json").read_text()
        )
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

    def test_backup_service_lifecycle_binds_dependency_propagation(self) -> None:
        lifecycle_start = self.backup.index("active_services=()")
        lifecycle_end = self.backup.index("\ncleanup_on_exit()", lifecycle_start)
        lifecycle = self.backup[lifecycle_start:lifecycle_end]
        self.assertIn(
            "\nquiesce_prior_active_services\n", self.backup[lifecycle_end:]
        )

        dependency_fixture = r'''
set -euo pipefail
declare -A state=(
  [factory-dashboard.service]=1
  [caddy.service]=1
  [factory-supervisor.service]=1
)
events=()
systemctl() {
  case "$1" in
    is-active)
      events+=("is-active:$3")
      [[ "${state[$3]}" == 1 ]]
      ;;
    stop)
      events+=("stop:$2")
      state["$2"]=0
      if [[ "$2" == factory-dashboard.service ]]; then
        state[caddy.service]=0
      fi
      ;;
    *) return 2 ;;
  esac
}
''' + lifecycle + r'''
services=(factory-dashboard.service caddy.service factory-supervisor.service)
quiesce_prior_active_services
printf '%s\n' "${events[@]}"
printf 'prior-active:%s\n' "${active_services[*]}"
'''
        dependency = subprocess.run(
            ["bash", "-c", dependency_fixture],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(dependency.returncode, 0, dependency.stderr)
        self.assertEqual(
            dependency.stdout.splitlines(),
            [
                "is-active:factory-dashboard.service",
                "is-active:caddy.service",
                "is-active:factory-supervisor.service",
                "stop:factory-dashboard.service",
                "stop:caddy.service",
                "stop:factory-supervisor.service",
                "prior-active:factory-dashboard.service caddy.service "
                "factory-supervisor.service",
            ],
        )

        with tempfile.TemporaryDirectory() as temporary:
            silent_start_fixture = r'''
set -uo pipefail
declare -A state=(
  [factory-dashboard.service]=0
  [caddy.service]=0
  [factory-supervisor.service]=0
)
events=()
systemctl() {
  case "$1" in
    start)
      events+=("start:$2")
      if [[ "$2" != caddy.service ]]; then
        state["$2"]=1
      fi
      return 0
      ;;
    is-active)
      events+=("is-active:$3")
      [[ "${state[$3]}" == 1 ]]
      ;;
    *) return 2 ;;
  esac
}
''' + lifecycle + r'''
services=(caddy.service factory-dashboard.service factory-supervisor.service)
active_services=(caddy.service factory-dashboard.service factory-supervisor.service)
generation_root="$1"
payload_root="$1/missing-payload"
cleanup_and_restart true
rc=$?
printf '%s\n' "${events[@]}"
exit "$rc"
'''
            silent_start = subprocess.run(
                ["bash", "-c", silent_start_fixture, "backup-test", temporary],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(silent_start.returncode, 28, silent_start.stdout)
        self.assertIn("start:caddy.service", silent_start.stdout)
        self.assertIn("is-active:caddy.service", silent_start.stdout)
        self.assertIn("service_resume_failed", silent_start.stderr)

    def test_rollback_boundary_inventory_resolves_only_the_reviewed_host(self) -> None:
        operator = ROOT / "infra" / "rollback-control.sh"
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "boundary.json"
            command = r'''
source <(sed '/^case "$MODE" in/,$d' "$0")
write_boundary_inventory factory-control.example.com 209.97.148.52 "$1"
validate_boundary_inventory \
  "$1" factory-control.example.com 209.97.148.52
if validate_boundary_inventory \
  "$1" factory-control.example.com 192.0.2.1 >/dev/null 2>&1; then
  exit 1
fi
'''
            subprocess.run(
                ["bash", "-c", command, str(operator), str(inventory)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

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
        declared_total = re.search(
            r"^factory_grafana_column_privilege_count:\s*(\d+)$",
            self.group_vars,
            re.MULTILINE,
        )
        self.assertIsNotNone(declared_total)
        self.assertEqual(int(declared_total.group(1)), expected_total)
        self.assertIn(
            "grantee = 'grafana_ro'\")\" = "
            "{{ factory_grafana_column_privilege_count }}",
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
            'test "$(rpm -q chromium)" = {{ chromium_nevra | quote }}',
            self.qualifier,
        )
        self.assertNotIn(chromium_nevra.group(1), self.qualifier)

    def test_qualification_environment_constants_have_one_declared_source(self) -> None:
        self.assertIn("ansible.builtin.template:", self.tasks)
        self.assertIn("src: qualify-factory-control.j2", self.tasks)
        self.assertIn("{{ factory_migration_count }}", self.qualifier)
        self.assertIn(
            "{{ factory_grafana_column_privilege_count }}", self.qualifier
        )
        self.assertNotRegex(
            self.qualifier,
            r"SELECT count\(\*\) FROM public\._sqlx_migrations[^\n]*\)\" = 11$",
        )

    def test_chromium_pin_uses_immutable_mirrored_object_versions(self) -> None:
        declared_nevras = dict(
            re.findall(
                r"^(chromium(?:_common)?_nevra):\s*(\S+)$",
                self.group_vars,
                re.MULTILINE,
            )
        )
        mirror_block = self.group_vars.split(
            "chromium_rpm_mirror:\n", maxsplit=1
        )[1].split("\nage_nevra:", maxsplit=1)[0]
        mirror_filenames = re.findall(
            r"^\s+- filename:\s*(\S+)$", mirror_block, re.MULTILINE
        )
        expected_filenames = {
            f"{declared_nevras[name]}.rpm"
            for name in ("chromium_nevra", "chromium_common_nevra")
        }
        self.assertEqual(len(mirror_filenames), len(expected_filenames))
        self.assertSetEqual(set(mirror_filenames), expected_filenames)

        for required in (
            "chromium_common_nevra: chromium-common-150.0.7871.181-1.el9.x86_64",
            "version_id: 9k88XXeRJzRUTRwYOFcTu2ICMqWR3iJ",
            "version_id: Gfh5nef193tTyupbpfhjGMofEJmg0-v",
            "05bda830ab035517ee6388c1a0d963d6de67eadb03c68cdd6ff90e8f888fd086",
            "b2f46d0d00cb47e4fd6a5b73b7edc02e196feb7d683fbfa5007e0a34cfb45202",
        ):
            self.assertIn(required, self.group_vars)
        self.assertNotIn('- "{{ chromium_nevra }}"', self.tasks)
        filename_binding = self.tasks.split(
            "- name: Bind mirrored Chromium filenames to the declared NEVRAs",
            maxsplit=1,
        )[1].split("\n- name:", maxsplit=1)[0]
        self.assertIn("chromium_nevra ~ '.rpm'", filename_binding)
        self.assertIn("chromium_common_nevra ~ '.rpm'", filename_binding)
        self.assertIn("chromium_rpm_mirror | map(attribute='filename')", filename_binding)
        self.assertIn("Synchronize the exact Chromium RPM object versions", self.tasks)
        package_task = self.tasks.split(
            "- name: Install Chromium from the immutable RPM mirror", maxsplit=1
        )[1].split("\n- name:", maxsplit=1)[0]
        self.assertIn("disable_gpg_check: false", package_task)
        self.assertNotIn("disable_gpg_check: true", package_task)
        self.assertIn("s3api head-object", self.rpm_mirror_sync)
        self.assertIn("--version-id", self.rpm_mirror_sync)
        self.assertIn("Metadata.sha256", self.rpm_mirror_sync)
        self.assertIn("s3api get-object", self.rpm_mirror_sync)
        self.assertIn("sha256sum --check --status", self.rpm_mirror_sync)
        self.assertIn('mv -f -- "$TEMP_FILE" "$destination"', self.rpm_mirror_sync)
        self.assertIn("patchyard-sync-rpm-mirror", self.qualifier)
        self.assertIn("{% for rpm in chromium_rpm_mirror %}", self.qualifier)
        self.assertIn("{{ rpm.sha256 | quote }}", self.qualifier)
        self.assertIn("sha256sum --check --status", self.qualifier)
        self.assertEqual(
            self.chromium_visual_baseline["before"]["dom_sha256"],
            self.chromium_visual_baseline["after"]["dom_sha256"],
        )
        self.assertEqual(
            self.chromium_visual_baseline["before"]["screenshot_sha256"],
            self.chromium_visual_baseline["after"]["screenshot_sha256"],
        )
        self.assertEqual(self.chromium_visual_baseline["result"], "byte-identical")

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
        declared_cookies = set()
        for constant in ("LOGIN_COOKIE", "SESSION_COOKIE"):
            match = re.search(
                rf'^pub const {constant}: &str = "([^"]+)";$',
                self.auth,
                re.MULTILINE,
            )
            self.assertIsNotNone(match)
            declared_cookies.add(match.group(1))
            self.assertIn(match.group(1), self.restore_evidence_probe)
        probe_cookies = set(
            re.findall(r"__Host-[A-Za-z0-9_-]+", self.restore_evidence_probe)
        )
        self.assertSetEqual(probe_cookies, declared_cookies)

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
        self.assertIn("--username=restore-drill@example.com", reset_task)
        self.assertNotIn("--password", reset_task)
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
        self.assertEqual(
            self.rollback_operator.count(
                "mktemp --suffix=.json /tmp/patchyard-rollback-boundary.XXXXXX"
            ),
            2,
        )
        self.assertIn("ansible-inventory", self.rollback_operator)
        self.assertIn(
            'validate_boundary_inventory "$boundary_inventory" "$control_host" "$address"',
            self.rollback_operator,
        )
        self.assertIn(
            "rollback boundary inventory did not resolve the reviewed control host",
            self.rollback_operator,
        )
        self.assertIn(
            "(.control_plane.hosts // []) == [$host]",
            self.rollback_operator,
        )
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
        self.assertIn("qualification_environment_inventory", self.rollback_operator)
        self.assertIn("schema_version:3", self.rollback_operator)
        self.assertIn("chromium_nevra", self.rollback_operator)
        self.assertIn("factory_grafana_column_privilege_count", self.rollback_operator)
        self.assertIn(
            "A112 application-under-current-contract rollback is not implemented",
            self.rollback_operator,
        )
        deploy = self.rollback_operator[
            self.rollback_operator.index("deploy_and_qualify_revision()") :
            self.rollback_operator.index("stable_durable_state()")
        ]
        self.assertGreaterEqual(deploy.count('cd "$rollback_root" &&'), 2)
        self.assertIn(
            'cd "$REPO_ROOT/infra/ansible" &&',
            self.rollback_operator,
        )
        self.assertIn("./infra/ansible/converge.sh", deploy)
        self.assertIn("./infra/ansible/qualify.sh", deploy)
        self.assertLess(
            deploy.index('cd "$rollback_root" &&'),
            deploy.index("./infra/ansible/converge.sh"),
        )
        self.assertIn(
            '--manifest-path "$REPO_ROOT/Cargo.toml"',
            self.converge_operator,
        )
        input_check = (
            '"$REPO_ROOT/infra/ansible/converge.sh" --check-inputs'
        )
        self.assertIn(input_check, self.rollback_operator)
        self.assertLess(
            self.rollback_operator.index(input_check),
            self.rollback_operator.index("set_rollback_boundary enter"),
        )
        self.assertIn("qualification_migration_count", self.rollback_operator)
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

    def test_rollback_preflight_compares_the_complete_qualification_environment(
        self,
    ) -> None:
        def inventory(revision: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    "bash",
                    "-c",
                    self.rollback_function_prelude
                    + '\nqualification_environment_inventory "$1"',
                    "qualification-environment-test",
                    revision,
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        interim_target = inventory(
            "02c9e2da1f2ebdd877a5e867351da1f500eeaa45"
        )
        interim_return = inventory(
            "9941eb233a2ddf61dc4e0dd8c2c76e6482c48bc3"
        )
        stale_environment = inventory(
            "7b032c7c7ceb7c427cf5e73c43e2116acaf5614a"
        )
        inconsistent_migrations = inventory(
            "84708ba8a1e0c6786a9b934f110a5f6b8adfde3b"
        )
        declared_inventory = inventory("HEAD")

        for result in (
            interim_target,
            interim_return,
            stale_environment,
            declared_inventory,
        ):
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(interim_target.stdout, interim_return.stdout)
        self.assertNotEqual(stale_environment.stdout, interim_return.stdout)
        self.assertNotEqual(inconsistent_migrations.returncode, 0)

        interim = json.loads(interim_return.stdout)
        stale = json.loads(stale_environment.stdout)
        self.assertNotEqual(stale["chromium_nevra"], interim["chromium_nevra"])
        self.assertNotEqual(
            stale["grafana_column_privilege_count"],
            interim["grafana_column_privilege_count"],
        )
        current = json.loads(declared_inventory.stdout)
        self.assertEqual(current["grafana_column_privilege_count"], 20)
        self.assertEqual(current["migration_count"], 11)
        self.assertEqual(current["qualification_migration_count"], 11)
        self.assertRegex(current["mirror_sha256"], r"^[0-9a-f]{64}$")

    def test_converge_input_check_refuses_absent_secret_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            private_key = root / "github-app.pem"
            accounts = root / "dashboard-accounts.json"
            private_key.write_text("test-key\n")
            accounts.write_text(
                json.dumps(
                    [
                        {
                            "username": "admin-one@example.com",
                            "display_name": "Admin One",
                            "role": "factory_admin",
                            "password": "test-password-one",
                        },
                        {
                            "username": "admin-two@example.com",
                            "display_name": "Admin Two",
                            "role": "factory_admin",
                            "password": "test-password-two",
                        },
                        {
                            "username": "submit@example.com",
                            "display_name": "Submit",
                            "role": "factory_submit",
                            "password": "test-password-three",
                        },
                    ]
                )
            )
            private_key.chmod(0o600)
            accounts.chmod(0o600)
            env = os.environ | {
                "GH_PATCHYARD_APP_ID": "123",
                "GH_PATCHYARD_APP_INSTALLATION_ID": "456",
                "GH_PATCHYARD_APP_PRIVATE_KEY_FILE": str(private_key),
                "FACTORY_DASHBOARD_ACCOUNTS_FILE": str(accounts),
            }
            command = [
                str(ROOT / "infra" / "ansible" / "converge.sh"),
                "--check-inputs",
            ]
            self.assertEqual(
                subprocess.run(
                    command,
                    env=env,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ).returncode,
                0,
            )
            for variable in (
                "GH_PATCHYARD_APP_PRIVATE_KEY_FILE",
                "FACTORY_DASHBOARD_ACCOUNTS_FILE",
            ):
                missing = env.copy()
                missing.pop(variable)
                self.assertNotEqual(
                    subprocess.run(
                        command,
                        env=missing,
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    ).returncode,
                    0,
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


class Session16DuplicatedContractBindings(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = ROOT / "infra" / "ansible" / "roles" / "control_plane" / "files"
        cls.probe = (cls.files / "patchyard-restore-evidence-probe").read_text()
        cls.operator = (ROOT / "infra" / "rollback-control.sh").read_text()
        cls.boundary = (ROOT / "infra" / "ansible" / "rollback-boundary.yml").read_text()
        cls.restore_play = (ROOT / "infra" / "ansible" / "restore.yml").read_text()
        cls.restore_operator = (ROOT / "infra" / "restore-drill.sh").read_text()
        cls.tasks = (
            ROOT / "infra" / "ansible" / "roles" / "control_plane" / "tasks" / "main.yml"
        ).read_text()
        cls.common_tasks = (
            ROOT / "infra" / "ansible" / "roles" / "common" / "tasks" / "main.yml"
        ).read_text()
        cls.group_vars = (ROOT / "infra" / "ansible" / "group_vars" / "all.yml").read_text()
        cls.web = (ROOT / "crates" / "factory-web" / "src" / "lib.rs").read_text()
        cls.web_main = (ROOT / "crates" / "factory-web" / "src" / "main.rs").read_text()
        cls.factoryctl = (ROOT / "crates" / "factoryctl" / "src" / "main.rs").read_text()
        cls.digitalocean = (ROOT / "infra" / "digitalocean" / "main.tf").read_text()
        cls.inventory_output = (
            ROOT / "infra" / "digitalocean" / "outputs.tf"
        ).read_text()
        cls.qualifier = (
            ROOT
            / "infra"
            / "ansible"
            / "roles"
            / "control_plane"
            / "templates"
            / "qualify-factory-control.j2"
        ).read_text()
        cls.migrations = "\n".join(
            path.read_text() for path in sorted((ROOT / "migrations").glob("*.sql"))
        )

    def _restore_target_contract(self):
        target_values = dict(
            re.findall(
                r"(factory_restore_(?:drill|expected_[a-z_]+)):"
                r"(true|\$[a-z_][a-z0-9_]*)",
                self.restore_operator,
            )
        )
        jq_arguments = dict(
            re.findall(
                r'^\s+--arg ([a-z_][a-z0-9_]*) "\$([a-z_][a-z0-9_]*)"',
                self.restore_operator,
                re.MULTILINE,
            )
        )
        expected_targets = {
            name for name, value in target_values.items() if value.startswith("$")
        }
        target_sources = {
            name: jq_arguments[value.removeprefix("$")]
            for name, value in target_values.items()
            if value.startswith("$")
        }
        inventory_builder = self.restore_operator.split(
            'inventory_file="$drill_root/inventory.json"', maxsplit=1
        )[1].split('>"$inventory_file"', maxsplit=1)[0]
        inventory_fields = set(
            re.findall(
                r"\b([a-z_][a-z0-9_]*):\$([a-z_][a-z0-9_]*)",
                inventory_builder,
            )
        )
        host_bindings = {
            (field, target)
            for field, source in inventory_fields
            for target, target_source in target_sources.items()
            if source == target_source
        }
        drill_flags = {
            name for name, value in target_values.items() if value == "true"
        }
        self.assertTrue(drill_flags)
        self.assertTrue(expected_targets)
        self.assertTrue(host_bindings)
        return drill_flags, expected_targets, target_sources, host_bindings

    def test_restore_inventory_guard_matches_generated_target_bindings(self) -> None:
        drill_flags, expected_targets, _, host_bindings = self._restore_target_contract()
        guard = self.restore_play.split(
            "    - name: Refuse restore outside the generated drill inventory",
            maxsplit=1,
        )[1].split("\n    - name:", maxsplit=1)[0]
        condition_block = guard.split("that:", maxsplit=1)[1].split(
            "fail_msg:", maxsplit=1
        )[0]
        conditions = re.findall(r"^\s+- (.+)$", condition_block, re.MULTILINE)
        asserted_flags = {
            match.group(1)
            for condition in conditions
            if (
                match := re.fullmatch(
                    r"([a-z_][a-z0-9_]*) \| default\(false\) \| bool",
                    condition,
                )
            )
        }
        asserted_definitions = {
            match.group(1)
            for condition in conditions
            if (match := re.fullmatch(r"([a-z_][a-z0-9_]*) is defined", condition))
        }
        asserted_host_bindings = {
            (match.group(1), match.group(2))
            for condition in conditions
            if (
                match := re.fullmatch(
                    r"([a-z_][a-z0-9_]*) == ([a-z_][a-z0-9_]*)",
                    condition,
                )
            )
        }
        self.assertSetEqual(asserted_flags, drill_flags)
        self.assertSetEqual(asserted_definitions, expected_targets)
        self.assertSetEqual(asserted_host_bindings, host_bindings)
        self.assertEqual(
            len(conditions),
            len(asserted_flags) + len(asserted_definitions) + len(asserted_host_bindings),
        )

        first_play = self.restore_play.split(
            "\n- name: Provision and restore the clean recovery host", maxsplit=1
        )[0]
        task_names = re.findall(r"^    - name: (.+)$", first_play, re.MULTILINE)
        self.assertEqual(
            task_names[0], "Refuse restore outside the generated drill inventory"
        )
        self.assertIn("gather_facts: false", first_play)

    def test_restore_droplet_guard_matches_metadata_and_remaining_target(self) -> None:
        _, expected_targets, target_sources, host_bindings = (
            self._restore_target_contract()
        )
        host_targets = {target for _, target in host_bindings}
        output_blocks = dict(
            re.findall(
                r'output "([a-z_][a-z0-9_]*)" \{(.*?)\n\}',
                self.inventory_output,
                re.DOTALL,
            )
        )
        declared_id_outputs = {
            name
            for name, body in output_blocks.items()
            if re.search(r"digitalocean_droplet\.[^\n]+\.id : null", body)
        }
        output_reads = dict(
            re.findall(
                r'^\s+([a-z_][a-z0-9_]*)=\$\("[^"\n]*tofu\.sh" digitalocean '
                r"output -raw ([a-z_][a-z0-9_]*)\)$",
                self.restore_operator,
                re.MULTILINE,
            )
        )
        droplet_sources = {
            variable
            for variable, output in output_reads.items()
            if output in declared_id_outputs
        }
        droplet_targets = {
            target
            for target, source in target_sources.items()
            if source in droplet_sources
        }
        self.assertEqual(len(droplet_targets), 1)
        self.assertSetEqual(expected_targets, host_targets | droplet_targets)

        metadata = self.restore_play.split(
            "    - name: Read the target DigitalOcean droplet identity", maxsplit=1
        )[1].split("\n    - name:", maxsplit=1)[0]
        metadata_result = re.search(
            r"^\s+register:\s*([a-z_][a-z0-9_]*)$", metadata, re.MULTILINE
        )
        self.assertIsNotNone(metadata_result)

        guard_name = "Bind restore to the planned ephemeral droplet"
        guard = self.restore_play.split(f"    - name: {guard_name}", maxsplit=1)[
            1
        ].split("\n- name:", maxsplit=1)[0]
        condition_block = guard.split("that:", maxsplit=1)[1].split(
            "fail_msg:", maxsplit=1
        )[0]
        condition_lines = [
            line.strip() for line in condition_block.splitlines() if line.strip()
        ]
        self.assertEqual(condition_lines[0], "- >-")
        self.assertEqual(sum(line.startswith("- ") for line in condition_lines), 1)
        condition = " ".join(condition_lines[1:])
        asserted_binding = re.fullmatch(
            r"([a-z_][a-z0-9_]*)\.content \| trim == "
            r"\(([a-z_][a-z0-9_]*) \| string\)",
            condition,
        )
        self.assertIsNotNone(asserted_binding)
        self.assertEqual(asserted_binding.group(1), metadata_result.group(1))
        self.assertSetEqual({asserted_binding.group(2)}, droplet_targets)

        first_play = self.restore_play.split(
            "\n- name: Provision and restore the clean recovery host", maxsplit=1
        )[0]
        task_names = re.findall(r"^    - name: (.+)$", first_play, re.MULTILINE)
        metadata_index = task_names.index("Read the target DigitalOcean droplet identity")
        self.assertEqual(task_names[metadata_index + 1], guard_name)

    def test_restore_probe_form_fields_match_login_form(self) -> None:
        form = re.search(r"struct LoginForm \{(.*?)\n\}", self.web, re.DOTALL)
        self.assertIsNotNone(form)
        declared_fields = set(
            re.findall(r"^\s+([a-z_][a-z0-9_]*): .+$", form.group(1), re.MULTILINE)
        )
        submitted = dict(
            re.findall(
                r'^data-urlencode = "([a-z_][a-z0-9_]*)=\$([a-z_][a-z0-9_]*)"$',
                self.probe,
                re.MULTILINE,
            )
        )
        self.assertSetEqual(set(submitted), declared_fields)

        login = self.web.split("async fn login(", maxsplit=1)[1].split(
            "struct CsrfForm", maxsplit=1
        )[0]
        csrf_field = re.search(
            r"login_challenge_valid\(.*?,\s*&form\.([a-z_][a-z0-9_]*)\)",
            login,
            re.DOTALL,
        )
        csrf_capture = re.search(
            r'(?m)^([a-z_][a-z0-9_]*)=\$\(sed -n .*name=\"([a-z_][a-z0-9_]*)\" value=',
            self.probe,
        )
        self.assertIsNotNone(csrf_field)
        self.assertIsNotNone(csrf_capture)
        self.assertEqual(csrf_capture.group(2), csrf_field.group(1))
        self.assertEqual(submitted[csrf_field.group(1)], csrf_capture.group(1))

        for local, field in re.findall(
            r"let ([a-z_][a-z0-9_]*) = (?:normalize_username\(&)?form\.([a-z_][a-z0-9_]*)",
            login,
        ):
            self.assertEqual(submitted[field], local)

    def test_restore_probe_login_route_and_status_match_application(self) -> None:
        from http import HTTPStatus

        route = re.search(
            r'\.route\("([^"]+)", get\(login_form\)\.post\(login\)\)', self.web
        )
        self.assertIsNotNone(route)
        probe_urls = re.findall(r'http://localhost([^\s"]+)', self.probe)
        self.assertSetEqual({url for url in probe_urls if "$" not in url}, {route.group(1)})

        login = self.web.split("async fn login(", maxsplit=1)[1].split(
            "struct CsrfForm", maxsplit=1
        )[0]
        redirect = re.search(r"let mut response = ([a-z_][a-z0-9_]*)\(", login)
        self.assertIsNotNone(redirect)
        redirect_body = self.web.split(
            f"fn {redirect.group(1)}(", maxsplit=1
        )[1].split("\n}", maxsplit=1)[0]
        status_name = re.search(r"StatusCode::([A-Z_]+)", redirect_body)
        probe_status = re.search(r'\[\[ "\$login_status" == ([0-9]{3}) \]\]', self.probe)
        self.assertIsNotNone(status_name)
        self.assertIsNotNone(probe_status)
        self.assertEqual(int(probe_status.group(1)), HTTPStatus[status_name.group(1)].value)

    def test_restore_probe_runtime_paths_match_declared_defaults(self) -> None:
        declared = {}
        for name, environment in (
            ("socket", "FACTORY_DASHBOARD_SOCKET"),
            ("artifact_root", "FACTORY_ARTIFACT_ROOT"),
        ):
            match = re.search(
                rf'env = "{environment}",\s+default_value = "([^"]+)"',
                self.web_main,
            )
            self.assertIsNotNone(match)
            declared[name] = match.group(1)
        socket = re.search(
            r"^postgresql_socket_directory:\s*(\S+)$", self.group_vars, re.MULTILINE
        )
        self.assertIsNotNone(socket)
        declared["database_socket"] = socket.group(1)
        probe_paths = {
            name: quoted or unquoted
            for name, quoted, unquoted in re.findall(
                r"^readonly ([a-z_][a-z0-9_]*)=(?:'([^']+)'|(/\S+))$",
                self.probe,
                re.MULTILINE,
            )
        }
        self.assertSetEqual(set(probe_paths), set(declared))
        for name, value in declared.items():
            self.assertEqual(probe_paths[name], value)

        database_task = self.tasks.split(
            "- name: Create the factory database under the schema owner", maxsplit=1
        )[1].split("\n- name:", maxsplit=1)[0]
        createdb_argv = re.findall(r'^\s+- "?([^"\n]+)"?$', database_task, re.MULTILINE)
        createdb_index = createdb_argv.index("createdb")
        database = next(
            argument
            for argument in createdb_argv[createdb_index + 1 :]
            if not argument.startswith("-")
        )
        self.assertSetEqual(
            set(re.findall(r"--dbname=([a-z][a-z0-9_]*)", self.probe)), {database}
        )

    def test_restore_probe_artifact_query_matches_schema(self) -> None:
        query = re.search(r'--command="\n(.*?)\n  "', self.probe, re.DOTALL)
        self.assertIsNotNone(query)
        table = re.search(r"\bFROM\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)", query.group(1))
        self.assertIsNotNone(table)
        declared_table = re.search(
            rf"CREATE TABLE {re.escape(table.group(1))} \((.*?)\n\);",
            self.migrations,
            re.DOTALL,
        )
        self.assertIsNotNone(declared_table)
        declared_columns = set(
            re.findall(
                r"^\s{4}([a-z_][a-z0-9_]*)\s+",
                declared_table.group(1),
                re.MULTILINE,
            )
        )

        select = re.search(r"\bSELECT\s+(.*?)\s+FROM\b", query.group(1), re.DOTALL)
        self.assertIsNotNone(select)
        expression = re.sub(r"'[^']*'|::[a-z_][a-z0-9_]*", "", select.group(1))
        functions = set(re.findall(r"\b([a-z_][a-z0-9_]*)\s*\(", expression))
        selected_columns = set(re.findall(r"\b[a-z_][a-z0-9_]*\b", expression)) - functions
        predicate_columns = set(
            re.findall(r"\b([a-z_][a-z0-9_]*)\s+IS\b", query.group(1))
        )
        predicate_columns.update(
            re.findall(r"\bregexp_replace\(\s*([a-z_][a-z0-9_]*)", query.group(1))
        )
        predicate_columns.update(
            re.findall(r"\bORDER BY\s+([a-z_][a-z0-9_]*)", query.group(1))
        )
        self.assertLessEqual(selected_columns | predicate_columns, declared_columns)

    def test_restore_probe_evidence_route_and_name_policy_match_application(self) -> None:
        route = re.search(r'\.route\("([^"]+)", get\(evidence\)\)', self.web)
        self.assertIsNotNone(route)
        dynamic_urls = {
            re.sub(r"\$([a-z_][a-z0-9_]*)", r"{\1}", url)
            for url in re.findall(r'http://localhost([^\s"]+)', self.probe)
            if "$" in url
        }
        self.assertSetEqual(dynamic_urls, {route.group(1)})

        policy = self.web.split("fn safe_evidence_name(", maxsplit=1)[1].split(
            "\n}", maxsplit=1
        )[0]
        maximum = re.search(r"value\.len\(\) <= ([0-9]+)", policy)
        allowed = re.search(r"matches!\(byte, ([^)]+)\)", policy)
        probe_pattern = re.search(
            r"regexp_replace\(path, '[^']+', ''\) ~ '\^\[([^]]+)\]"
            r"\{([0-9]+),([0-9]+)\}\$'",
            self.probe,
        )
        self.assertIsNotNone(maximum)
        self.assertIsNotNone(allowed)
        self.assertIsNotNone(probe_pattern)
        alphanumeric_class = "A-Za-z0-9"
        source_is_alphanumeric = "byte.is_ascii_alphanumeric()" in policy
        probe_is_alphanumeric = alphanumeric_class in probe_pattern.group(1)
        self.assertEqual(probe_is_alphanumeric, source_is_alphanumeric)
        probe_literals = probe_pattern.group(1).replace(alphanumeric_class, "")
        self.assertSetEqual(
            set(probe_literals), set(re.findall(r"b'(.)'", allowed.group(1)))
        )
        self.assertEqual(int(probe_pattern.group(2)), int("!value.is_empty()" in policy))
        self.assertEqual(int(probe_pattern.group(3)), int(maximum.group(1)))

        evidence = self.web.split("async fn evidence(", maxsplit=1)[1].split(
            "\nasync fn ", maxsplit=1
        )[0]
        source_digest = re.search(r"([A-Za-z0-9_]+)::digest\(", evidence)
        stored_digest = re.search(r"encode\(([a-z0-9_]+), 'hex'\)", self.probe)
        probe_digest = re.search(r"\b([a-z0-9_]+)sum \"\$probe_root/evidence\"", self.probe)
        self.assertIsNotNone(source_digest)
        self.assertIsNotNone(stored_digest)
        self.assertIsNotNone(probe_digest)
        self.assertSetEqual(
            {source_digest.group(1).lower()},
            {stored_digest.group(1), probe_digest.group(1)},
        )

    def test_rollback_inventory_identity_matches_tofu_output(self) -> None:
        group = re.search(
            r"(?m)^    ([a-z_][a-z0-9_]*) = \{\n"
            r"      hosts = \[digitalocean_droplet\.control_plane\.name\]",
            self.inventory_output,
        )
        role = re.search(
            r"\(digitalocean_droplet\.control_plane\.name\) = \{.*?"
            r'factory_role\s*=\s*"([^"]+)"',
            self.inventory_output,
            re.DOTALL,
        )
        user = re.search(r'ansible_user\s*=\s*"([^"]+)"', self.inventory_output)
        key = re.search(
            r'ansible_ssh_private_key_file\s*=\s*"([^"]+)"', self.inventory_output
        )
        for match in (group, role, user, key):
            self.assertIsNotNone(match)

        consumer_groups = set(re.findall(r"\.([a-z_][a-z0-9_]*)\.hosts", self.operator))
        consumer_groups.update(
            re.findall(r"children:\{([a-z_][a-z0-9_]*):\{hosts", self.operator)
        )
        consumer_groups.update(
            re.findall(
                r"^\s+hosts:\s*([a-z_][a-z0-9_]*)$",
                self.boundary,
                re.MULTILINE,
            )
        )
        self.assertSetEqual(consumer_groups, {group.group(1)})

        consumer_roles = set(re.findall(r'factory_role:\s*"([^"]+)"', self.operator))
        consumer_roles.update(re.findall(r'factory_role == "([^"]+)"', self.operator))
        self.assertSetEqual(consumer_roles, {role.group(1)})
        consumer_users = set(re.findall(r'ansible_user:"([^"]+)"', self.operator))
        consumer_users.update(re.findall(r'"([a-z][a-z0-9_-]*)@\$address"', self.operator))
        self.assertSetEqual(consumer_users, {user.group(1)})
        consumer_keys = set(re.findall(r"SSH_ARGS=\(-i (\S+)", self.operator))
        consumer_keys.update(
            re.findall(r'ansible_ssh_private_key_file:"([^"]+)"', self.operator)
        )
        self.assertSetEqual(consumer_keys, {key.group(1)})
        common_args = re.search(r'ansible_ssh_common_args:"([^"]+)"', self.operator)
        ssh_args = re.search(r"^SSH_ARGS=\(([^)]+)\)$", self.operator, re.MULTILINE)
        self.assertIsNotNone(common_args)
        self.assertIsNotNone(ssh_args)
        self.assertSetEqual(
            set(re.findall(r"-o ([^ )]+)", ssh_args.group(1))),
            set(re.findall(r"-o ([^ ]+)", common_args.group(1))),
        )

    def test_rollback_boundary_transitions_match_operator(self) -> None:
        transition_task = self.boundary.split(
            "- name: Require an explicit rollback-boundary transition", maxsplit=1
        )[1].split("\n    - name:", maxsplit=1)[0]
        declaration = re.search(
            r"([a-z_][a-z0-9_]*) in \[([^]]+)\]", transition_task
        )
        self.assertIsNotNone(declaration)
        declared_states = set(re.findall(r"'([^']+)'", declaration.group(2)))
        condition_states = set(
            re.findall(
                rf"{re.escape(declaration.group(1))} == '([^']+)'", self.boundary
            )
        )
        operator_states = set(
            re.findall(r"\bset_rollback_boundary\s+([a-z-]+)\b", self.operator)
        )
        self.assertSetEqual(condition_states, declared_states)
        self.assertSetEqual(operator_states, declared_states)
        passed_variable = re.search(r'-e "([a-z_][a-z0-9_]*)=\$state"', self.operator)
        self.assertIsNotNone(passed_variable)
        self.assertEqual(passed_variable.group(1), declaration.group(1))

    def test_rollback_firewall_ports_match_public_edge(self) -> None:
        firewall = re.search(
            r'(?ms)^resource "digitalocean_firewall" "control_plane" \{\n(.*?)^\}$',
            self.digitalocean,
        )
        self.assertIsNotNone(firewall)
        public_blocks = []
        for block in re.findall(
            r"inbound_rule \{(.*?)^  \}", firewall.group(1), re.DOTALL | re.MULTILINE
        ):
            addresses = re.search(r"source_addresses\s*=\s*\[([^]]+)\]", block)
            if addresses is None:
                continue
            networks = re.findall(r'"([^"]+)"', addresses.group(1))
            if networks and all(network.endswith("/0") for network in networks):
                public_blocks.append(block)
        source_ports = {
            re.search(r'port_range\s*=\s*"([^"]+)"', block).group(1)
            for block in public_blocks
        }
        source_protocols = {
            re.search(r'protocol\s*=\s*"([^"]+)"', block).group(1)
            for block in public_blocks
        }
        boundary_port_loops = re.findall(
            r"(?m)^\s+loop:\n((?:\s+- \"[0-9]+\"\n)+)", self.boundary
        )
        self.assertGreater(len(boundary_port_loops), 0)
        for loop in boundary_port_loops:
            self.assertSetEqual(set(re.findall(r'"([0-9]+)"', loop)), source_ports)
        self.assertSetEqual(
            set(re.findall(r'protocol=\"([^\"]+)\"', self.boundary)),
            source_protocols,
        )
        public_zone_task = self.common_tasks.split(
            "- name: Make the public zone fail closed", maxsplit=1
        )[1].split("\n- name:", maxsplit=1)[0]
        source_zone = re.search(r"^\s+zone:\s*(\S+)$", public_zone_task, re.MULTILINE)
        self.assertIsNotNone(source_zone)
        self.assertSetEqual(
            set(re.findall(r"^\s+zone:\s*(\S+)$", self.boundary, re.MULTILINE)),
            {source_zone.group(1)},
        )

    def test_rollback_boundary_sentinel_and_dropin_paths_are_consistent(self) -> None:
        sentinel_task = self.boundary.split(
            "- name: Create the persistent rollback-boundary sentinel", maxsplit=1
        )[1].split("\n        - name:", maxsplit=1)[0]
        sentinel = re.search(r"^\s+path:\s*(\S+)$", sentinel_task, re.MULTILINE)
        dropin_task = self.boundary.split(
            "- name: Install the reboot-durable rollback backup exclusion", maxsplit=1
        )[1].split("\n        - name:", maxsplit=1)[0]
        dropin = re.search(r"^\s+dest:\s*(\S+)$", dropin_task, re.MULTILINE)
        self.assertIsNotNone(sentinel)
        self.assertIsNotNone(dropin)
        condition = re.search(r"ConditionPathExists=!(\S+)", self.boundary)
        self.assertIsNotNone(condition)
        self.assertEqual(condition.group(1), sentinel.group(1))
        for task_name in (
            "Remove any partial reboot-durable backup exclusion",
            "Remove the reboot-durable rollback backup exclusion",
        ):
            cleanup = self.boundary.split(f"- name: {task_name}", maxsplit=1)[1].split(
                "\n    - name:" if task_name.startswith("Remove the") else "\n        - name:",
                maxsplit=1,
            )[0]
            self.assertSetEqual(
                set(re.findall(r"^\s+- (/\S+)$", cleanup, re.MULTILINE)),
                {sentinel.group(1), dropin.group(1)},
            )

    def test_rollback_service_names_are_declared_on_control_plane(self) -> None:
        declared_units = {
            path.name
            for path in self.files.iterdir()
            if path.suffix in {".service", ".socket", ".timer"}
        }
        for block in re.findall(
            r"(?m)^  ansible\.builtin\.systemd:\n((?:^    .*\n)+)", self.tasks
        ):
            if "enabled: true" in block:
                unit = re.search(r"^\s+name:\s*([A-Za-z0-9@_.-]+)$", block, re.MULTILINE)
                if unit is not None:
                    declared_units.add(unit.group(1))

        consumers = self.operator + self.boundary
        consumed_units = set(
            re.findall(r"\b[a-z][a-z0-9@-]*\.(?:service|socket|timer)\b", consumers)
        )
        for arguments in re.findall(
            r"systemctl (?:stop|is-active --quiet) ([^&'\n]+)", self.operator
        ):
            for unit in arguments.split():
                consumed_units.add(unit if "." in unit else f"{unit}.service")
        self.assertGreater(len(consumed_units), 0)
        self.assertLessEqual(consumed_units, declared_units)

    def test_rollback_runtime_paths_match_declared_sources(self) -> None:
        socket = re.search(
            r"^postgresql_socket_directory:\s*(\S+)$", self.group_vars, re.MULTILINE
        )
        dashboard_socket = re.search(
            r'env = "FACTORY_DASHBOARD_SOCKET",\s+default_value = "([^"]+)"',
            self.web_main,
        )
        checkout_task = self.tasks.split(
            "- name: Read the installed desired-state revision", maxsplit=1
        )[1].split("\n- name:", maxsplit=1)[0]
        checkout = re.search(
            r"^\s+- -C\n\s+- (/\S+)\n\s+- rev-parse\n\s+- HEAD$",
            checkout_task,
            re.MULTILINE,
        )
        manager = re.search(
            r"^factory_manager_user:\s*(\S+)$", self.group_vars, re.MULTILINE
        )
        for match in (socket, dashboard_socket, checkout, manager):
            self.assertIsNotNone(match)
        scoped = self.operator + self.boundary
        self.assertSetEqual(
            set(
                re.findall(
                    r"(?:^socket=|--host=)(/[A-Za-z0-9_./-]+)",
                    scoped,
                    re.MULTILINE,
                )
            ),
            {socket.group(1)},
        )
        self.assertSetEqual(
            set(re.findall(r"--unix-socket (/[A-Za-z0-9_./-]+)", self.operator)),
            {dashboard_socket.group(1)},
        )
        self.assertSetEqual(
            set(re.findall(r"git -C (/[A-Za-z0-9_./-]+)", self.operator)),
            {checkout.group(1)},
        )
        self.assertSetEqual(
            set(
                re.findall(
                    r"runuser -u ([a-z][a-z0-9_-]*) -- git -C", self.operator
                )
            ),
            {manager.group(1)},
        )
        sentinel_task = self.boundary.split(
            "- name: Create the persistent rollback-boundary sentinel", maxsplit=1
        )[1].split("\n        - name:", maxsplit=1)[0]
        self.assertSetEqual(
            set(
                re.findall(
                    r"^\s+(?:owner|group):\s*([^\s]+)$",
                    sentinel_task,
                    re.MULTILINE,
                )
            ),
            {manager.group(1)},
        )

        health_route = re.search(r'\.route\("([^"]+)", get\(health\)\)', self.web)
        self.assertIsNotNone(health_route)
        self.assertSetEqual(
            set(re.findall(r"http://localhost([^\s']+)", self.operator)),
            {health_route.group(1)},
        )

        database_task = self.tasks.split(
            "- name: Create the factory database under the schema owner", maxsplit=1
        )[1].split("\n- name:", maxsplit=1)[0]
        createdb_argv = re.findall(r'^\s+- "?([^"\n]+)"?$', database_task, re.MULTILINE)
        createdb_index = createdb_argv.index("createdb")
        database = next(
            argument
            for argument in createdb_argv[createdb_index + 1 :]
            if not argument.startswith("-")
        )
        database_literals = set(re.findall(r"--dbname=([a-z][a-z0-9_]*)", scoped))
        database_literals.update(
            re.findall(
                r"^database=([a-z][a-z0-9_]*)$", self.operator, re.MULTILINE
            )
        )
        self.assertSetEqual(database_literals, {database})

        source_roots = set()
        for task_name in (
            "Create the dashboard-readable artifact root",
            "Create the traversable manager-owned proposer runtime root",
        ):
            task = self.tasks.split(f"- name: {task_name}", maxsplit=1)[1].split(
                "\n- name:", maxsplit=1
            )[0]
            path = re.search(r"^\s+path:\s*(\S+)$", task, re.MULTILINE)
            self.assertIsNotNone(path)
            source_roots.add(path.group(1))
        root_loop = re.search(
            r"for root in ([^;]+); do.*?find \"([^\"]+)/\$root\"",
            self.operator,
            re.DOTALL,
        )
        stripped_root = re.search(
            r'relative=\$\{path#"([^"]+)/\$root/"\}', self.operator
        )
        self.assertIsNotNone(root_loop)
        self.assertIsNotNone(stripped_root)
        self.assertEqual(stripped_root.group(1), root_loop.group(2))
        self.assertSetEqual(
            {f"{root_loop.group(2)}/{name}" for name in root_loop.group(1).split()},
            source_roots,
        )

    def test_rollback_inventory_qualifier_reads_declared_migration_source(
        self,
    ) -> None:
        inventory_branch = self.operator.split(
            'if revision_uses_inventory_qualifier "$revision"; then', maxsplit=1
        )[1].split("\n  else", maxsplit=1)[0]
        self.assertIn("qualified_migrations=$migration_count", inventory_branch)
        self.assertRegex(
            self.group_vars,
            r"(?m)^factory_migration_count:\s*[0-9]+$",
        )
        self.assertRegex(
            self.qualifier,
            r"(?m)--command='SELECT count\(\*\) FROM public\._sqlx_migrations "
            r"WHERE success'\)\" = \{\{ factory_migration_count \}\}$",
        )

    def test_rollback_active_state_sets_match_declared_contracts(self) -> None:
        terminal = re.search(
            r"const TERMINAL_STATES:.*?= &\[(.*?)\];", self.web, re.DOTALL
        )
        boundary_terminal = re.search(
            r"factory\.runs WHERE state NOT IN\s*\((.*?)\)\s*\+", self.boundary, re.DOTALL
        )
        proposer_constraint = re.search(
            r"CONSTRAINT proposer_runs_terminal_shape CHECK \(\s*"
            r"\(state IN \((.*?)\)\s*AND finished_at IS NULL",
            self.migrations,
            re.DOTALL,
        )
        boundary_proposer = re.search(
            r"factory\.proposer_runs WHERE state IN\s*\((.*?)\)\)",
            self.boundary,
            re.DOTALL,
        )
        for match in (terminal, boundary_terminal, proposer_constraint, boundary_proposer):
            self.assertIsNotNone(match)
        self.assertSetEqual(
            set(re.findall(r'"([^"]+)"', terminal.group(1))),
            set(re.findall(r"'([^']+)'", boundary_terminal.group(1))),
        )
        self.assertSetEqual(
            set(re.findall(r"'([^']+)'", proposer_constraint.group(1))),
            set(re.findall(r"'([^']+)'", boundary_proposer.group(1))),
        )
        self.assertLessEqual(
            set(
                re.findall(
                    r"\bFROM\s+(factory\.[a-z_][a-z0-9_]*)", self.boundary
                )
            ),
            set(re.findall(r"CREATE TABLE (factory\.[a-z_][a-z0-9_]*)", self.migrations)),
        )
        declared_columns = set()
        for table, body in re.findall(
            r"CREATE TABLE (factory\.[a-z_][a-z0-9_]*) \((.*?)\n\);",
            self.migrations,
            re.DOTALL,
        ):
            declared_columns.update(
                (table, column)
                for column in re.findall(
                    r"^\s{4}([a-z_][a-z0-9_]*)\s+", body, re.MULTILINE
                )
            )
        boundary_command = re.search(
            r"--command=SELECT concat\((.*?)\n\s+become_user:",
            self.boundary,
            re.DOTALL,
        )
        self.assertIsNotNone(boundary_command)
        boundary_columns = set(
            re.findall(
                r"FROM (factory\.[a-z_][a-z0-9_]*) WHERE "
                r"([a-z_][a-z0-9_]*)",
                boundary_command.group(1),
            )
        )
        supervisor_table = re.findall(
            r"FROM (factory\.[a-z_][a-z0-9_]*) WHERE",
            boundary_command.group(1),
        )
        selected_column = re.search(
            r"CASE WHEN ([a-z_][a-z0-9_]*) THEN", boundary_command.group(1)
        )
        self.assertTrue(supervisor_table)
        self.assertIsNotNone(selected_column)
        boundary_columns.add((supervisor_table[-1], selected_column.group(1)))
        self.assertLessEqual(boundary_columns, declared_columns)

    def test_rollback_special_tables_and_audit_allowance_match_sources(self) -> None:
        special_tables = set(
            re.findall(
                r'\[\[ "\$schema\.\$table" == ([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*) \]\]',
                self.operator,
            )
        )
        excluded_tables = set(
            re.findall(
                r'\$2 == "([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)"',
                self.operator,
            )
        )
        declared_tables = set(
            re.findall(
                r"CREATE TABLE ([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)",
                self.migrations,
            )
        )
        self.assertSetEqual(special_tables, excluded_tables)
        self.assertLessEqual(special_tables, declared_tables)

        source_allowance = re.search(
            r"INSERT INTO ([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*) .*?"
            r"VALUES \(\$1,'([^']+)',\$2,'([^']+)'\)",
            self.factoryctl,
        )
        consumer_allowance = re.search(
            r"FROM ([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*) WHERE .*?"
            r"action <> '([^']+)' OR client_key <> '([^']+)'",
            self.operator,
        )
        self.assertIsNotNone(source_allowance)
        self.assertIsNotNone(consumer_allowance)
        self.assertEqual(consumer_allowance.groups(), source_allowance.groups())

    def test_rollback_manifest_literals_match_the_apply_validator(self) -> None:
        plan = self.operator.split("  plan)", maxsplit=1)[1].split(
            "\n  apply)", maxsplit=1
        )[0]
        apply = self.operator.split("  apply)", maxsplit=1)[1].split(
            "\n  release-boundary)", maxsplit=1
        )[0]
        producer = re.search(
            r'\{schema_version:([0-9]+),.*?scope:"([^"]+)",'
            r'durable_state:"([^"]+)"\}',
            plan,
            re.DOTALL,
        )
        validator = re.search(
            r'\.schema_version == ([0-9]+) and \.scope == "([^"]+)"'
            r' and \.durable_state == "([^"]+)"',
            apply,
        )
        self.assertIsNotNone(producer)
        self.assertIsNotNone(validator)
        self.assertEqual(validator.groups(), producer.groups())

    def test_rollback_consumed_durable_labels_are_emitted(self) -> None:
        capture = self.operator.split("capture_durable_state() {", maxsplit=1)[1].split(
            "\nstable_durable_state() {", maxsplit=1
        )[0]
        consumers = self.operator.split("stable_durable_state() {", maxsplit=1)[1]
        emitted = set(
            re.findall(r"printf '([a-z][a-z0-9-]*)\\t", capture)
        )
        emitted.update(
            re.findall(
                r'--command="SELECT \'([a-z][a-z0-9-]*)\' \|\|', capture
            )
        )
        consumed = set(
            re.findall(r'\$1\s*(?:==|!=)\s*"([a-z][a-z0-9-]*)"', consumers)
        )
        self.assertGreater(len(emitted), 0)
        self.assertGreater(len(consumed), 0)
        self.assertLessEqual(consumed, emitted)


if __name__ == "__main__":
    unittest.main()
