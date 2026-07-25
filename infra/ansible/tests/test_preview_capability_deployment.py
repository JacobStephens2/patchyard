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

    def test_preview_router_orders_capability_strip_after_forward_auth(self) -> None:
        capability = COMPOSE.read_text()
        slot = (ROOT / "preview/docker-compose.factory-slot.yml").read_text()
        self.assertIn(
            "traefik.http.middlewares.patchyard-capability-strip.headers.customrequestheaders.X-Patchyard-Factory-Capability",
            capability,
        )
        self.assertIn(
            '"patchyard-capability@docker,patchyard-capability-strip@docker"',
            slot,
        )


if __name__ == "__main__":
    unittest.main()
