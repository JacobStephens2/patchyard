from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[3]
FILES = ROOT / "infra" / "ansible" / "roles" / "control_plane" / "files"
LAUNCHER = FILES / "patchyard-child-launcher"
REAPER = FILES / "patchyard-reap-child"
UNIT = FILES / "patchyard-child@.service"


class ChildLauncherContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = LAUNCHER.read_text()
        cls.reaper = REAPER.read_text()
        cls.unit = UNIT.read_text()

    def test_privileged_scripts_are_valid_bash(self) -> None:
        for name in (
            "patchyard-child-launcher",
            "patchyard-reap-child",
            "patchyard-spawn-child",
            "patchyard-cancel-child",
        ):
            subprocess.run(
                ["/usr/bin/bash", "-n", str(FILES / name)],
                check=True,
                capture_output=True,
            )

    def test_probe_result_is_not_mounted_into_either_untrusted_stage(self) -> None:
        self.assertIn('ISOLATION_DIRECTORY="$JOB/probe"', self.launcher)
        self.assertNotIn('ISOLATION_FILE="$OUTPUT/', self.launcher)
        for prefix in ("REVIEW", "EVIDENCE"):
            close = f"exec {{{prefix}_PROBE_FD}}>&-"
            child_stage = self.launcher.split(close, 1)[1].split("CHILD_PID=$!", 1)[0]
            self.assertNotIn("/isolation-probe", child_stage)
            self.assertNotIn("/probe-output", child_stage)
        self.assertEqual(self.launcher.count("/probe-output/isolation.json"), 2)
        self.assertGreaterEqual(self.launcher.count("chown -R root:root"), 2)

    def test_pinned_hosts_need_no_dns_egress(self) -> None:
        self.assertIn('--ro-bind-fd "$EVIDENCE_HOSTS_FD" /etc/hosts', self.launcher)
        self.assertIn("tcp dport 443", self.launcher)
        self.assertIn(r"transport=tcp/443\ndns=none\n", self.launcher)
        self.assertNotIn("dport 53", self.launcher)
        self.assertNotIn("/etc/resolv.conf", self.launcher)

    def test_dns_change_is_typed_before_any_network_or_browser_setup(self) -> None:
        changed = self.launcher.index('if [[ "$RESOLUTION_STATUS" -eq 42 ]]')
        policy = self.launcher.index("FAILURE_STAGE=evidence_network_policy")
        browser = self.launcher.index("FAILURE_STAGE=evidence_sandbox")
        self.assertLess(changed, policy)
        self.assertLess(policy, browser)
        self.assertIn("STATE=dns_binding_changed", self.launcher[changed:policy])

    def test_teardown_measures_and_reaps_declared_resource_classes(self) -> None:
        self.assertIn("PROCESSES=$(count_child_processes)", self.launcher)
        self.assertIn("MOUNTS=$(count_child_mounts)", self.launcher)
        self.assertNotIn('pgrep -f -- "patchyard-child-$ID"', self.launcher)
        self.assertIn(
            "ExecStopPost=/usr/local/sbin/patchyard-reap-child %i", self.unit
        )
        for command in (
            'nft delete table inet "$NFT_TABLE"',
            'ip link delete "$HOST_VETH"',
            'ip netns delete "$NETNS"',
            "net.ipv4.ip_forward=0",
            'rm -f -- "$JOB/terminal.json"',
        ):
            self.assertIn(command, self.reaper)


if __name__ == "__main__":
    unittest.main()
