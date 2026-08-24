"""Behavioural coverage for the Session 13 qualifier's settle contract.

The contract is extracted from the installed qualifier between its markers and
exercised against stub `systemctl`, `ip`, `nft`, `sysctl`, and `sleep` binaries,
so each case is the state a real control plane passes through rather than a
string the script happens to contain. Per A124 the first case is the outcome the
qualifier exists to produce - a converged, quiet control plane - proved to pass.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
FILES = ROOT / "infra" / "ansible" / "roles" / "control_plane" / "files"
QUALIFIER = FILES / "qualify-factory-session13"
OPEN_MARKER = "# >>> settle contract"
CLOSE_MARKER = "# <<< settle contract"

RESOLVE = r"""
resolve() {
  local step best=0 candidate
  step=$(cat "$ETA_STUB_STATE/step")
  for candidate in "$ETA_STUB_STATE"/[0-9]*; do
    [[ -d "$candidate" ]] || continue
    candidate=${candidate##*/}
    if ((candidate <= step && candidate >= best)); then best=$candidate; fi
  done
  printf '%s' "$ETA_STUB_STATE/$best"
}
emit() {
  local file="$(resolve)/$1"
  [[ -f "$file" ]] && cat "$file"
  return 0
}
"""

STUBS = {
    "systemctl": RESOLVE
    + r"""
case "$1" in
  is-failed) [[ "$(emit supervisor_failed)" == yes ]] ;;
  is-active) [[ "$(emit supervisor_active)" == yes ]] ;;
  list-units)
    if [[ "$*" == *--failed* ]]; then emit failed_units; else emit units; fi
    ;;
  *) exit 0 ;;
esac
""",
    "ip": RESOLVE + '\nemit netns\n',
    "nft": RESOLVE + '\nemit tables\n',
    "sysctl": RESOLVE + '\nemit ip_forward\n',
    "sleep": r"""
step=$(cat "$ETA_STUB_STATE/step")
printf '%s' "$((step + 1))" >"$ETA_STUB_STATE/step"
printf 'x' >>"$ETA_STUB_STATE/sleeps"
""",
}

DEFAULT_STATE = {
    "supervisor_failed": "no",
    "supervisor_active": "yes",
    "units": "",
    "failed_units": "",
    "netns": "",
    "tables": "",
    "ip_forward": "0",
}


def _extract_contract() -> str:
    text = QUALIFIER.read_text()
    return text.split(OPEN_MARKER, 1)[1].split(CLOSE_MARKER, 1)[0]


class SettleContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = _extract_contract()
        cls.qualifier = QUALIFIER.read_text()

    def run_settle(self, states, children=(), evidence=(), timeout_seconds=6):
        """Run both settle calls against a scripted sequence of host states.

        `states` is one dict per step; each step inherits nothing, so give every
        step a complete picture. `children` names entries under the child
        runtime root - a name ending in `/.network-active` creates that marker
        inside its child's directory.
        """
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            state = tmp / "state"
            binaries = tmp / "bin"
            child_root = tmp / "children"
            evidence_root = tmp / "evidence"
            for directory in (state, binaries, child_root, evidence_root):
                directory.mkdir()
            (state / "step").write_text("0")
            for index, overrides in enumerate(states):
                step = state / str(index)
                step.mkdir()
                values = dict(DEFAULT_STATE)
                values.update(overrides)
                for key, value in values.items():
                    (step / key).write_text(value)
            for entry in children:
                path = child_root / entry
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.name.startswith("."):
                    path.write_text("")
                else:
                    path.mkdir(exist_ok=True)
            for entry in evidence:
                (evidence_root / entry).write_text("")
            for name, body in STUBS.items():
                stub = binaries / name
                stub.write_text("#!/usr/bin/env bash\nset -uo pipefail\n" + body)
                stub.chmod(0o755)
            contract = tmp / "contract.bash"
            contract.write_text(self.contract)
            driver = "\n".join(
                [
                    "set -euo pipefail",
                    f"source {contract}",
                    f"SETTLE_TIMEOUT_SECONDS={timeout_seconds}",
                    "SETTLE_INTERVAL_SECONDS=2",
                    f'CHILD_RUNTIME_ROOT="{child_root}"',
                    f'EVIDENCE_RUNTIME_ROOT="{evidence_root}"',
                    "settle 'the supervisor to be running' supervisor_is_running",
                    "settle 'isolated-child teardown' child_isolation_is_settled",
                ]
            )
            completed = subprocess.run(
                ["/usr/bin/env", "bash", "-c", driver],
                capture_output=True,
                text=True,
                env={
                    "PATH": f"{binaries}:/usr/bin:/bin",
                    "ETA_STUB_STATE": str(state),
                },
                check=False,
            )
            sleeps = (state / "sleeps").read_text() if (state / "sleeps").exists() else ""
            return completed, len(sleeps)

    # A124: the outcome the qualifier exists to produce, proved to pass.
    def test_a_quiet_converged_control_plane_qualifies_without_waiting(self) -> None:
        completed, sleeps = self.run_settle([{}])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(sleeps, 0)

    def test_a_supervisor_still_restarting_is_waited_for(self) -> None:
        completed, sleeps = self.run_settle(
            [{"supervisor_active": "no"}, {"supervisor_active": "yes"}]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(sleeps, 1)

    def test_a_failed_supervisor_is_refused_without_waiting(self) -> None:
        completed, sleeps = self.run_settle(
            [{"supervisor_failed": "yes", "supervisor_active": "no"}]
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(sleeps, 0)
        self.assertIn("factory-supervisor.service has failed", completed.stderr)

    def test_a_child_in_flight_qualifies_without_waiting_for_the_queue(self) -> None:
        identifier = "a1b2c3d4" + "e" * 24
        completed, sleeps = self.run_settle(
            [
                {
                    "units": f"patchyard-child@{identifier}.service loaded active running\n",
                    "netns": "efna1b2c3d4 (id: 0)\n",
                    "tables": "table inet eta_child_a1b2c3d4\n",
                    "ip_forward": "1",
                }
            ],
            children=[f"{identifier}/.network-active"],
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(sleeps, 0)

    def test_a_failed_child_unit_is_refused_without_waiting(self) -> None:
        identifier = "b" * 32
        completed, sleeps = self.run_settle(
            [
                {
                    "units": f"patchyard-child@{identifier}.service loaded failed failed\n",
                    "failed_units": f"patchyard-child@{identifier}.service loaded failed failed\n",
                }
            ]
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(sleeps, 0)
        self.assertIn("isolated-child units have failed", completed.stderr)

    def test_an_unrecognized_child_unit_is_refused_without_waiting(self) -> None:
        completed, sleeps = self.run_settle(
            [{"units": "patchyard-child@intruder.service loaded active running\n"}]
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(sleeps, 0)
        self.assertIn("unrecognized isolated-child unit", completed.stderr)

    def test_the_reaper_window_is_waited_out_rather_than_failed(self) -> None:
        completed, sleeps = self.run_settle(
            [
                {"netns": "efnc0ffee01 (id: 0)\n", "ip_forward": "1"},
                {},
            ]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(sleeps, 1)

    def test_residue_no_child_owns_fails_at_the_deadline(self) -> None:
        completed, sleeps = self.run_settle(
            [{"tables": "table inet eta_child_deadbeef\n"}], timeout_seconds=4
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(sleeps, 2)
        self.assertIn("without a live owner", completed.stderr)
        self.assertIn("eta_child_deadbeef", completed.stderr)
        # The reason is reported once, when the wait ends - not on every sample,
        # which would bury the finding under sixty identical lines.
        self.assertEqual(completed.stderr.count("eta_child_deadbeef"), 1)
        self.assertIn("qualification waited 4s for isolated-child teardown", completed.stderr)

    def test_an_orphaned_child_directory_fails_at_the_deadline(self) -> None:
        completed, _ = self.run_settle(
            [{}], children=["f" * 32], timeout_seconds=4
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("without a live owner", completed.stderr)

    def test_forwarding_left_on_with_no_live_child_fails_at_the_deadline(self) -> None:
        completed, _ = self.run_settle([{"ip_forward": "1"}], timeout_seconds=4)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("net.ipv4.ip_forward is 1", completed.stderr)

    def test_evidence_staging_residue_fails_at_the_deadline(self) -> None:
        completed, _ = self.run_settle(
            [{}], evidence=["request.json"], timeout_seconds=4
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("evidence qualification staging is not empty", completed.stderr)

    def test_the_qualifier_samples_no_racing_state_once(self) -> None:
        # The single-sample forms this ticket removed must not come back.
        for sampled in (
            "systemctl is-active --quiet factory-supervisor.service\n",
            "test -z \"$(systemctl list-units 'patchyard-child@*' --all --no-legend)\"",
            'test "$(sysctl -n net.ipv4.ip_forward)" = 0',
        ):
            self.assertNotIn(sampled, self.qualifier)
        for waited in (
            "settle 'the factory supervisor to be running' supervisor_is_running",
            "settle 'isolated-child teardown' child_isolation_is_settled",
        ):
            self.assertIn(waited, self.qualifier)

    def test_the_qualifier_requires_a_finite_child_lifetime_bound(self) -> None:
        # Refusing to wait for an in-flight child is only safe because systemd
        # turns a stuck one into a failed unit within a declared bound, which
        # the qualifier must therefore require rather than assume.
        for assertion in (
            "grep -Eq '^TimeoutStartSec=[0-9]+(s|min)$'",
            "grep -Eq '^TimeoutStopSec=[0-9]+(s|min)$'",
        ):
            self.assertIn(assertion, self.qualifier)
        # The installed unit satisfies exactly what the qualifier requires.
        unit = (FILES / "patchyard-child@.service").read_text()
        for directive in ("TimeoutStartSec", "TimeoutStopSec"):
            self.assertRegex(unit, rf"(?m)^{directive}=[0-9]+(s|min)$")

    def test_the_installed_qualifier_is_valid_bash(self) -> None:
        subprocess.run(
            ["/usr/bin/env", "bash", "-n", str(QUALIFIER)], check=True, capture_output=True
        )


if __name__ == "__main__":
    unittest.main()
