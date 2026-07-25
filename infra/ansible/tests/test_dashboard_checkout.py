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


if __name__ == "__main__":
    unittest.main()
