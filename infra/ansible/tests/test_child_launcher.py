from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[3]
FILES = ROOT / "infra" / "ansible" / "roles" / "control_plane" / "files"
TASKS = ROOT / "infra" / "ansible" / "roles" / "control_plane" / "tasks" / "main.yml"
LAUNCHER = FILES / "patchyard-child-launcher"
REAPER = FILES / "patchyard-reap-child"
CANCEL = FILES / "patchyard-cancel-child"
UNIT = FILES / "patchyard-child@.service"
QUALIFIER = FILES / "qualify-factory-session13"


class ChildLauncherContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = LAUNCHER.read_text()
        cls.reaper = REAPER.read_text()
        cls.cancel = CANCEL.read_text()
        cls.unit = UNIT.read_text()
        cls.tasks = TASKS.read_text()
        cls.qualifier = QUALIFIER.read_text()

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

    def test_stable_resolution_validates_only_address_members(self) -> None:
        self.assertIn("all(.addresses[]; test(", self.launcher)
        self.assertNotIn("all(.[]; test(", self.launcher)

    def test_evidence_failure_diagnostic_is_allowlisted_before_journaling(self) -> None:
        self.assertIn("patchyard_child_failure_diagnostic", self.launcher)
        self.assertIn("patchyard_child_failure_document_status", self.launcher)
        self.assertIn("patchyard_child_failure_browser_diagnostic", self.launcher)
        self.assertIn(".document_status >= 100", self.launcher)
        self.assertIn(".document_status <= 599", self.launcher)
        for value in (
            "document_2xx",
            "document_3xx",
            "document_4xx",
            "document_5xx",
            "document_other",
            "document_login_form_2xx",
            "document_php_error_2xx",
            "document_database_error_2xx",
            "document_api_denied_2xx",
        ):
            self.assertIn(value, self.launcher)
        for value in (
            "browser_pipe_closed_sigtrap",
            "browser_pipe_closed_sigsegv",
            "browser_pipe_closed_sigabrt",
            "browser_pipe_closed_sigkill",
            "browser_command_rejected",
            "browser_command_rejected_screenshot",
            "browser_exception_os",
            "browser_exception_other",
            "browser_action_result_invalid",
            "browser_dom_result_invalid",
        ):
            self.assertIn(value, self.launcher)

    def test_non_router_baseline_is_desired_qualified_and_required(self) -> None:
        self.assertIn(
            "name: Keep the factory control plane in its non-router baseline",
            self.tasks,
        )
        self.assertIn("name: net.ipv4.ip_forward", self.tasks)
        self.assertIn(
            "sysctl_file: /etc/sysctl.d/90-patchyard-child.conf", self.tasks
        )
        baseline = self.launcher.index(
            'BASE_FORWARD=$(sysctl -n net.ipv4.ip_forward)'
        )
        required = self.launcher.index('[[ "$BASE_FORWARD" == 0 ]]', baseline)
        network = self.launcher.index('ip netns add "$NETNS"', required)
        self.assertLess(baseline, required)
        self.assertLess(required, network)
        self.assertIn(
            'test "$(sysctl -n net.ipv4.ip_forward)" = 0', self.qualifier
        )
        self.assertIn("net.ipv4.ip_forward=0", self.reaper)

    def test_cancel_skips_reset_after_systemd_collected_the_unit(self) -> None:
        self.assertIn(
            'if /usr/bin/systemctl is-failed --quiet "$UNIT"; then', self.cancel
        )
        self.assertIn('/usr/bin/systemctl reset-failed "$UNIT"', self.cancel)

    def test_teardown_measures_and_reaps_declared_resource_classes(self) -> None:
        self.assertIn("PROCESSES=$(count_child_processes)", self.launcher)
        self.assertIn("MOUNTS=$(count_child_mounts)", self.launcher)
        self.assertIn(
            '[[ "$pid" == "$$" || "$pid" == "$BASHPID" ]]', self.launcher
        )
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
