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
        for prefix in ("PROPOSER", "REVIEW", "EVIDENCE"):
            close = f"exec {{{prefix}_PROBE_FD}}>&-"
            child_stage = self.launcher.split(close, 1)[1].split("CHILD_PID=$!", 1)[0]
            self.assertNotIn("/isolation-probe", child_stage)
            self.assertNotIn("/probe-output", child_stage)
        self.assertEqual(self.launcher.count("/probe-output/isolation.json"), 3)
        self.assertGreaterEqual(self.launcher.count("chown -R root:root"), 3)

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
        # Namespace creation lives in one shared helper; each egress branch
        # must verify the non-router baseline before invoking it.
        definition = self.launcher.index("create_child_netns() {")
        self.assertIn('ip netns add "$NETNS"', self.launcher[definition:])
        for stage_marker in (
            "FAILURE_STAGE=review_non_router_baseline",
            "FAILURE_STAGE=evidence_non_router_baseline",
        ):
            stage = self.launcher.index(stage_marker)
            baseline = self.launcher.rindex(
                "BASE_FORWARD=$(sysctl -n net.ipv4.ip_forward)", 0, stage
            )
            required = self.launcher.index('[[ "$BASE_FORWARD" == 0 ]]', baseline)
            network = self.launcher.index("create_child_netns\n", stage)
            self.assertLess(baseline, required)
            self.assertLess(required, network)
        self.assertIn('test "$(sysctl -n net.ipv4.ip_forward)" = 0', self.qualifier)
        self.assertIn("net.ipv4.ip_forward=0", self.reaper)

    def test_cancel_skips_reset_after_systemd_collected_the_unit(self) -> None:
        self.assertIn(
            'if /usr/bin/systemctl is-failed --quiet "$UNIT"; then', self.cancel
        )
        self.assertIn('/usr/bin/systemctl reset-failed "$UNIT"', self.cancel)

    def test_teardown_measures_and_reaps_declared_resource_classes(self) -> None:
        self.assertIn("PROCESSES=$(count_child_processes)", self.launcher)
        self.assertIn("MOUNTS=$(count_child_mounts)", self.launcher)
        self.assertIn('[[ "$pid" == "$$" || "$pid" == "$BASHPID" ]]', self.launcher)
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

    def test_reaper_restores_ownership_a_killed_launcher_left_behind(self) -> None:
        # A SIGKILLed launcher never runs its finish trap, so the root
        # ExecStopPost reaper must restore what the trap would have: manager
        # ownership of the staging directory (or daemon orphan recovery fails
        # closed at startup) and the 0555 review workspace projection (or the
        # manager's git worktree-remove fails). Both count as residue and are
        # re-verified before exit.
        self.assertIn('chown -R "$MANAGER_UID:$MANAGER_GID" -- "$JOB"', self.reaper)
        self.assertIn('find "$JOB" -type d -exec chmod 0700 {} +', self.reaper)
        self.assertIn('find "$JOB" -type f -exec chmod 0600 {} +', self.reaper)
        ownership = self.reaper.index('chown -R "$MANAGER_UID:$MANAGER_GID"')
        self.assertIn(
            "mark_residue",
            self.reaper[self.reaper.rindex("if", 0, ownership) - 400 : ownership],
        )
        # The workspace chmod re-validates the launcher's path contract and
        # never follows a symlink or touches a non-manager-owned path as root.
        workspace = self.reaper.index('chmod 0700 -- "$WORKSPACE"')
        guard = self.reaper[self.reaper.index('REQUEST="$JOB/request.json"') : workspace]
        self.assertIn(".contract.kind == \"review\"", guard)
        self.assertIn("review-worktrees/review-[0-9a-f]{32}", guard)
        self.assertIn('readlink -f -- "$WORKSPACE"', guard)
        self.assertIn('stat -c %U -- "$WORKSPACE"', guard)
        self.assertIn('! -L "$WORKSPACE"', guard)
        # Final verification: no non-manager ownership survives the reap.
        self.assertIn(
            'find "$JOB" ! -user "$MANAGER_USER" -print -quit | grep -q .',
            self.reaper[workspace:],
        )

    def test_teardown_failure_forces_a_nonzero_exit(self) -> None:
        helper = self.launcher.split("final_exit_status() {", 1)[1].split("\n}", 1)[0]
        finish = self.launcher.split("finish() {", 1)[1].split("\n}\n\ntrap finish", 1)[
            0
        ]
        self.assertIn('[[ "$TEARDOWN_COMPLETE" != true', helper)
        self.assertIn('rc=$(final_exit_status "$rc")', finish)
        transition = self.launcher.split("mark_teardown_failed() {", 1)[1].split(
            "\n}", 1
        )[0]
        self.assertIn("STATE=teardown_failed", transition)
        residue = finish.index("PROCESSES=$(count_child_processes)")
        state_transition = finish.index("mark_teardown_failed", residue)
        final_status = finish.index('rc=$(final_exit_status "$rc")')
        self.assertLess(residue, state_transition)
        self.assertLess(state_transition, final_status)

        # Every fallible post-child publication operation either succeeds or
        # turns the terminal state into teardown_failed before exit status is
        # finalized. Unlock precedes terminal publication so its failure is
        # represented in terminal.json rather than hidden after it.
        for guarded_operation in (
            'find "$OUTPUT" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + \\\n'
            "      || mark_teardown_failed",
            'chown -R "$MANAGER_UID:$MANAGER_GID" "$JOB" || mark_teardown_failed',
            'find "$JOB" -type d -exec chmod 0700 {} + || mark_teardown_failed',
            'find "$JOB" -type f -exec chmod 0600 {} + || mark_teardown_failed',
            'flock -u "$NETWORK_LOCK" >/dev/null 2>&1 || mark_teardown_failed',
            "if ! write_terminal; then",
        ):
            self.assertIn(guarded_operation, finish)
        self.assertLess(
            finish.index('flock -u "$NETWORK_LOCK"'),
            finish.index("if ! write_terminal; then"),
        )
        terminal_recovery = finish.split("if ! write_terminal; then", 1)[1].split(
            "fi", 1
        )[0]
        self.assertIn("mark_teardown_failed", terminal_recovery)
        self.assertIn(
            'rm -f -- "$TERMINAL_TEMP" || mark_teardown_failed', terminal_recovery
        )
        self.assertIn("write_terminal || mark_teardown_failed", terminal_recovery)
        write_terminal = self.launcher.split("write_terminal() {", 1)[1].split(
            "\n}\n\nfinish()", 1
        )[0]
        for guarded in (
            "outputs=$(output_claims) || return 1",
            '}\' >"$TERMINAL_TEMP" || return 1',
            'chmod 0600 "$TERMINAL_TEMP" || return 1',
            'chown "$MANAGER_UID:$MANAGER_GID" "$TERMINAL_TEMP" || return 1',
            'mv -T "$TERMINAL_TEMP" "$JOB/terminal.json" || return 1',
        ):
            self.assertIn(guarded, write_terminal)

        probe = subprocess.run(
            [
                "bash",
                "-c",
                "\n".join(
                    [
                        "set -euo pipefail",
                        "final_exit_status() {",
                        helper,
                        "}",
                        "TEARDOWN_COMPLETE=true",
                        '[[ "$(final_exit_status 0)" == 0 ]]',
                        '[[ "$(final_exit_status 7)" == 7 ]]',
                        "TEARDOWN_COMPLETE=false",
                        '[[ "$(final_exit_status 0)" -ne 0 ]]',
                        '[[ "$(final_exit_status 7)" == 7 ]]',
                    ]
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)


if __name__ == "__main__":
    unittest.main()
