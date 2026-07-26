from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "preview/docker-compose.factory-capability.yml"
SLOT_COMPOSE = ROOT / "preview/docker-compose.factory-slot.yml"
AUTHORIZATION_CONF = ROOT / "preview/patchyard-authorization.conf"
TASKS = ROOT / "infra/ansible/roles/preview_host/tasks/main.yml"


class PreviewCapabilityDeploymentContract(unittest.TestCase):
    def test_translator_has_an_explicit_traefik_backend_port(self) -> None:
        label = 'traefik.http.services.patchyard-capability.loadbalancer.server.port: "8080"'
        self.assertIn(label, COMPOSE.read_text())
        self.assertIn("traefik.http.services.patchyard-capability.loadbalancer.server.port", TASKS.read_text())

    def test_preview_router_orders_capability_strip_after_forward_auth(self) -> None:
        capability = COMPOSE.read_text()
        slot = SLOT_COMPOSE.read_text()
        self.assertIn(
            "traefik.http.middlewares.patchyard-capability-strip.headers.customrequestheaders.X-Patchyard-Factory-Capability",
            capability,
        )
        self.assertIn(
            '"patchyard-capability@docker,patchyard-capability-strip@docker"',
            slot,
        )
        tasks = TASKS.read_text()
        self.assertIn(
            '"traefik.http.middlewares.patchyard-capability-strip.headers.customrequestheaders.X-Patchyard-Factory-Capability" == ""',
            tasks,
        )
        self.assertIn("docker-compose.factory-slot.yml", tasks)

    def test_legacy_php_receives_only_the_translated_authorization(self) -> None:
        authorization = AUTHORIZATION_CONF.read_text()
        slot = SLOT_COMPOSE.read_text()
        tasks = TASKS.read_text()
        self.assertIn(
            'SetEnvIfNoCase Authorization "^(.+)$" HTTP_AUTHORIZATION=$1',
            authorization,
        )
        self.assertIn(
            "/etc/patchyard-preview/patchyard-authorization.conf:"
            "/etc/httpd/conf.d/99-patchyard-authorization.conf:ro,Z",
            slot,
        )
        self.assertIn("patchyard-authorization.conf", tasks)


if __name__ == "__main__":
    unittest.main()
