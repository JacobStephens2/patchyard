from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "preview/docker-compose.factory-capability.yml"
SLOT_COMPOSE = ROOT / "preview/docker-compose.factory-slot.yml"
AUTHORIZATION_CONF = ROOT / "preview/patchyard-authorization.conf"
TRAEFIK_DYNAMIC = ROOT / "preview/patchyard-traefik-dynamic.yml"
TASKS = ROOT / "infra/ansible/roles/preview_host/tasks/main.yml"


class PreviewCapabilityDeploymentContract(unittest.TestCase):
    def test_traefik_loads_the_file_provider_capability_chain(self) -> None:
        compose = COMPOSE.read_text()
        dynamic = TRAEFIK_DYNAMIC.read_text()
        self.assertIn(
            '"--providers.file.filename=/etc/traefik/patchyard-dynamic.yml"',
            compose,
        )
        self.assertIn(
            "/etc/patchyard-preview/patchyard-traefik-dynamic.yml:"
            "/etc/traefik/patchyard-dynamic.yml:ro,Z",
            compose,
        )
        self.assertIn('address: "http://factory-capability:8080/auth"', dynamic)
        self.assertIn("patchyard-traefik-dynamic.yml", TASKS.read_text())
        for inherited_static_flag in (
            '"--providers.docker.endpoint=tcp://socket-proxy:2375"',
            '"--providers.docker.network=preview-net"',
            '"--entrypoints.websecure.address=:443"',
            '"--entrypoints.websecure.http.tls.certresolver=letsencrypt"',
            '"--certificatesresolvers.letsencrypt.acme.dnschallenge.provider=digitalocean"',
        ):
            self.assertIn(inherited_static_flag, compose)

    def test_forward_auth_replaces_the_private_capability_at_the_boundary(self) -> None:
        slot = SLOT_COMPOSE.read_text()
        dynamic = TRAEFIK_DYNAMIC.read_text()
        self.assertIn(
            'authResponseHeadersRegex: "^X-Patchyard-Factory-Capability$"',
            dynamic,
        )
        self.assertIn("- X-Patchyard-Factory-Preview-Authorization", dynamic)
        self.assertIn(
            '"patchyard-capability@file"',
            slot,
        )
        tasks = TASKS.read_text()
        self.assertIn(
            '--providers.file.filename=/etc/traefik/patchyard-dynamic.yml',
            tasks,
        )
        self.assertIn("docker-compose.factory-slot.yml", tasks)

    def test_legacy_php_receives_only_the_projected_application_header(self) -> None:
        authorization = AUTHORIZATION_CONF.read_text()
        slot = SLOT_COMPOSE.read_text()
        tasks = TASKS.read_text()
        self.assertIn(
            'RequestHeader set Authorization '
            '"expr=%{req:X-Patchyard-Factory-Preview-Authorization}"',
            authorization,
        )
        self.assertIn(
            "RequestHeader unset X-Patchyard-Factory-Preview-Authorization",
            authorization,
        )
        self.assertIn("CGIPassAuth On", authorization)
        self.assertIn(
            "/etc/patchyard-preview/patchyard-authorization.conf:"
            "/etc/httpd/conf.d/99-patchyard-authorization.conf:ro,Z",
            slot,
        )
        self.assertIn("patchyard-authorization.conf", tasks)


if __name__ == "__main__":
    unittest.main()
