from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "preview/docker-compose.factory-capability.yml"
TASKS = ROOT / "infra/ansible/roles/preview_host/tasks/main.yml"


class PreviewCapabilityDeploymentContract(unittest.TestCase):
    def test_translator_has_an_explicit_traefik_backend_port(self) -> None:
        label = 'traefik.http.services.patchyard-capability.loadbalancer.server.port: "8080"'
        self.assertIn(label, COMPOSE.read_text())
        self.assertIn("traefik.http.services.patchyard-capability.loadbalancer.server.port", TASKS.read_text())


if __name__ == "__main__":
    unittest.main()
