#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "infra" / "digitalocean" / "cloud-init.yaml.tftpl"
EXPECTED_COMMAND = (
    "dnf -y --nobest install firewalld python3 sudo; "
    "rpm -q firewalld python3 sudo; "
    "systemctl enable --now firewalld"
)


def validated_bootstrap_command(source: str) -> str:
    config = yaml.safe_load(
        source.replace("${management_public_key}", "ssh-ed25519 test")
    )
    if config.get("package_update") is not True:
        raise ValueError("bootstrap must refresh package metadata")
    if "packages" in config:
        raise ValueError("cloud-init package module bypasses the coherent solver")
    if config.get("runcmd") != [["bash", "-ceu", EXPECTED_COMMAND]]:
        raise ValueError("bootstrap transaction or fail-fast boundary differs")
    return config["runcmd"][0][2]


class CloudInitBootstrapContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = TEMPLATE.read_text()
        cls.command = validated_bootstrap_command(cls.source)

    def test_bootstrap_uses_one_fail_fast_coherent_package_transaction(self) -> None:
        self.assertEqual(self.command, EXPECTED_COMMAND)

    def test_source_weakening_mutations_are_rejected(self) -> None:
        mutations = {
            "best-only solver": self.source.replace(" --nobest", ""),
            "dependency erasure": self.source.replace(
                "--nobest", "--allowerasing"
            ),
            "non-fail-fast shell": self.source.replace("bash, -ceu", "bash, -cu"),
            "missing RPM assertion": self.source.replace(
                "rpm -q firewalld python3 sudo; ", ""
            ),
            "firewall before assertion": self.source.replace(
                "rpm -q firewalld python3 sudo; "
                "systemctl enable --now firewalld",
                "systemctl enable --now firewalld; "
                "rpm -q firewalld python3 sudo",
            ),
            "cloud-init package module": self.source.replace(
                "runcmd:\n", "packages: [firewalld, python3, sudo]\nruncmd:\n"
            ),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                self.assertNotEqual(mutation, self.source)
                with self.assertRaises(ValueError):
                    validated_bootstrap_command(mutation)

    def test_bootstrap_stops_at_each_failed_boundary(self) -> None:
        expected_success = [
            "dnf|-y|--nobest|install|firewalld|python3|sudo",
            "rpm|-q|firewalld|python3|sudo",
            "systemctl|enable|--now|firewalld",
        ]
        for failed_command, expected_events in (
            ("", expected_success),
            ("dnf", expected_success[:1]),
            ("rpm", expected_success[:2]),
            ("systemctl", expected_success),
        ):
            with self.subTest(failed_command=failed_command or "none"):
                with tempfile.TemporaryDirectory() as temp_name:
                    temp = Path(temp_name)
                    events = temp / "events"
                    for executable in ("dnf", "rpm", "systemctl"):
                        mock = temp / executable
                        mock.write_text(
                            "#!/bin/bash\n"
                            "printf '%s' \"$(basename \"$0\")\" >>\"$MOCK_EVENTS\"\n"
                            "printf '|%s' \"$@\" >>\"$MOCK_EVENTS\"\n"
                            "printf '\\n' >>\"$MOCK_EVENTS\"\n"
                            "[[ \"$(basename \"$0\")\" != \"$MOCK_FAIL\" ]]\n"
                        )
                        mock.chmod(0o755)
                    result = subprocess.run(
                        ["/bin/bash", "-ceu", self.command],
                        text=True,
                        capture_output=True,
                        check=False,
                        env={
                            **os.environ,
                            "PATH": f"{temp}:/usr/bin:/bin",
                            "MOCK_EVENTS": str(events),
                            "MOCK_FAIL": failed_command,
                        },
                    )
                    self.assertEqual(events.read_text().splitlines(), expected_events)
                    self.assertEqual(result.returncode == 0, failed_command == "")


if __name__ == "__main__":
    unittest.main()
