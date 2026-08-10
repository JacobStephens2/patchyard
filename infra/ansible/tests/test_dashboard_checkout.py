"""Desired-state proof for dashboard checkout projections."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
TASKS = ROOT / "infra/ansible/roles/control_plane/tasks/main.yml"
SERVICE = ROOT / "infra/ansible/roles/control_plane/files/factory-dashboard.service"


class DashboardCheckoutContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = TASKS.read_text()
        cls.service = SERVICE.read_text()

    def test_dashboard_can_only_traverse_the_credential_free_checkout(self) -> None:
        task_name = "- name: Grant the dashboard read-only checkout traversal"
        start = self.tasks.index(task_name)
        end = self.tasks.find("\n- name:", start + len(task_name))
        task = self.tasks[start:] if end == -1 else self.tasks[start:end]

        self.assertIn("path: /opt/patchyard", task)
        self.assertIn('owner: "{{ factory_manager_user }}"', task)
        self.assertIn("group: factory", task)
        self.assertIn('mode: "0750"', task)
        self.assertNotIn("recurse:", task)
        self.assertIn("SupplementaryGroups=factory", self.service)

    def test_checkout_transfer_does_not_fight_the_dashboard_root_group(self) -> None:
        task_name = "- name: Transfer the existing checkout to the factory management identity"
        start = self.tasks.index(task_name)
        end = self.tasks.find("\n- name:", start + len(task_name))
        task = self.tasks[start:] if end == -1 else self.tasks[start:end]

        self.assertIn("path: /opt/patchyard", task)
        self.assertIn('owner: "{{ factory_manager_user }}"', task)
        self.assertIn("recurse: true", task)
        self.assertNotIn("group:", task)

    def test_dashboard_umask_preserves_private_upload_directories(self) -> None:
        setting = next(
            line for line in self.service.splitlines() if line.startswith("UMask=")
        )
        umask = int(setting.removeprefix("UMask="), 8)

        self.assertEqual(0o700 & ~umask, 0o700)
        self.assertEqual(0o600 & ~umask, 0o600)

    def test_root_validation_cannot_take_ownership_of_the_caddy_access_log(self) -> None:
        task_name = "- name: Precreate the Caddy access log for the service identity"
        start = self.tasks.index(task_name)
        validate = self.tasks.index("- name: Validate the factory Caddy vhost", start)
        task = self.tasks[start:validate]

        self.assertIn("path: /var/log/caddy/factory-access.json", task)
        self.assertIn("state: touch", task)
        self.assertIn("owner: caddy", task)
        self.assertIn("group: caddy", task)
        self.assertIn('mode: "0640"', task)
        self.assertIn("access_time: preserve", task)
        self.assertIn("modification_time: preserve", task)


if __name__ == "__main__":
    unittest.main()
