"""Executable proofs for the issue-208 demonstration run's base.

The demonstration is a live ALPHABETIZE request that ends at a draft pull
request on real Fieldbook. Nothing here performs it. What this module proves is
the one thing about it that is desired state in this repository rather than an
operator action: the commit the run is based on, and the branch the pull
request is opened against.

Both were unsatisfiable when issue 207 flipped the daemon to `pre_publish`.
The production verifier refuses to reach a verdict unless every path in
`FACTORY_VERIFY_TESTS` exists at `FACTORY_BASE_SHA`
(`worker/runtime/patchyard-run-verifier`), and the lane-A caps forbid the
model's patch from adding its own test. `docs/production-cutover.md` recorded
that as "land the test on Fieldbook master". Landing it there turns Fieldbook's
own CI red for as long as it sits unpatched, and the demonstration pull
request is never merged, so "as long as" is forever.

The shape that satisfies both is Session 7's: a dedicated Fieldbook branch that
is master plus the targeted test, pinned as the base SHA and named as the base
branch. Master stays green, the pull request's diff is exactly the model's
patch, and the red-to-green transition the request is about becomes the pull
request's own check run.

That last part is why the branch name is asserted here and not merely written
down. See `test_the_base_branch_name_is_one_fieldbook_ci_runs_on`.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONTROL = ROOT / "infra" / "ansible" / "roles" / "control_plane"
ENVIRONMENT = CONTROL / "templates" / "patchyard-supervisor.env.j2"
GROUP_VARS = ROOT / "infra" / "ansible" / "group_vars" / "all.yml"
OPERATOR_DOC = ROOT / "docs" / "demonstration-run.md"
FIXTURE = ROOT / "fixtures" / "acceptance" / "alphabetize"

# The base SHA issue 207 shipped: Fieldbook master at 2026-07-24, before any
# acceptance test existed anywhere on Fieldbook. Every production run against it
# fails `targeted_test_exists_at_base`, so a demonstration cannot be based on
# it and this module refuses to let it silently come back.
STALE_BASE_SHA = "4ef35181f7a700b02e63808e483d7c23f33b91d8"

# Fieldbook's `.github/workflows/phpunit.yml` triggers on these branch patterns,
# for both `push` and `pull_request`. GitHub matches the `pull_request` filter
# against the pull request's BASE, so a base outside this list gets no checks —
# and no checks is not a pass. `evaluate_checks` in
# `crates/factory-supervisor/src/lifecycle.rs` reads an empty check-run list as
# `checks_not_started` and keeps waiting, so the demonstration would spend its
# full `FACTORY_CI_WAIT_TIMEOUT_SECONDS` and die on `ci_wait_timed_out` with no
# verdict to show for it.
FIELDBOOK_CI_BRANCH_PATTERNS = ("master", "**/staging")


def matches_github_branch_filter(branch: str, pattern: str) -> bool:
    """GitHub's branch-filter glob, restricted to the syntax Fieldbook uses.

    `**` spans path separators; `*` does not. Written out rather than reached
    for from `fnmatch`, whose `*` crosses `/` and would call every branch a
    match for `**/staging`.
    """
    expression = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**", index):
            expression.append(".*")
            index += 2
        elif pattern[index] == "*":
            expression.append("[^/]*")
            index += 1
        else:
            expression.append(re.escape(pattern[index]))
            index += 1
    return re.fullmatch("".join(expression), branch) is not None


class DemonstrationBase(unittest.TestCase):
    """The base commit and base branch the demonstration run is opened from."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.environment = ENVIRONMENT.read_text(encoding="utf-8")
        cls.group_vars = GROUP_VARS.read_text(encoding="utf-8")
        cls.operator_doc = OPERATOR_DOC.read_text(encoding="utf-8")

    def base_branch(self) -> str:
        match = re.search(
            r"(?m)^factory_fieldbook_base_branch: (?P<branch>\S+)$", self.group_vars
        )
        self.assertIsNotNone(match, "group_vars must define the base branch")
        assert match is not None
        return match.group("branch").strip("\"'")

    def section(self, title: str) -> str:
        """One `##` section of the operator doc, by heading, subsections and all."""
        match = re.search(
            rf"(?ms)^## {re.escape(title)}$(?P<body>.*?)(?=^## |\Z)",
            self.operator_doc,
        )
        self.assertIsNotNone(match, f"the doc must carry a `## {title}` section")
        assert match is not None
        return match.group("body")

    def test_the_publisher_base_branch_is_versioned_not_hardcoded_master(self) -> None:
        # The pull request is opened against the branch that carries the test,
        # not against master. Master is where the request's bug still lives.
        self.assertIn(
            "FACTORY_GITHUB_BASE_BRANCH={{ factory_fieldbook_base_branch }}",
            self.environment,
        )
        self.assertNotIn("FACTORY_GITHUB_BASE_BRANCH=master", self.environment)

    def test_the_base_branch_name_is_one_fieldbook_ci_runs_on(self) -> None:
        # The load-bearing assertion of this module. A base branch outside
        # Fieldbook's filter is not a cosmetic naming choice: it silently costs
        # the demonstration its CI evidence and then its whole run.
        branch = self.base_branch()
        self.assertTrue(
            any(
                matches_github_branch_filter(branch, pattern)
                for pattern in FIELDBOOK_CI_BRANCH_PATTERNS
            ),
            f"{branch} is outside Fieldbook CI's {list(FIELDBOOK_CI_BRANCH_PATTERNS)}, "
            "so a pull request into it reports no checks and the run waits "
            "until ci_wait_timed_out",
        )

    def test_the_base_branch_is_not_master_itself(self) -> None:
        # `master` satisfies the CI filter, so the assertion above alone would
        # let the shape collapse back to landing a red test on master.
        self.assertNotEqual(self.base_branch(), "master")

    def test_the_base_branch_cannot_collide_with_a_published_branch(self) -> None:
        # The publisher owns `factory/<request-id>-<suffix>` and refuses a
        # branch it does not own. A base branch shaped like one of its own
        # would be indistinguishable from a run's head branch.
        branch = self.base_branch()
        suffix = re.search(
            r"(?m)^FACTORY_PUBLISH_BRANCH_SUFFIX=(?P<suffix>\S+)$", self.environment
        )
        self.assertIsNotNone(suffix)
        assert suffix is not None
        self.assertFalse(branch.endswith(f"-{suffix.group('suffix')}"))

    def test_the_pinned_base_advanced_off_the_testless_cutover_commit(self) -> None:
        match = re.search(
            r"(?m)^factory_fieldbook_base_sha: (?P<sha>[0-9a-f]{40})$", self.group_vars
        )
        self.assertIsNotNone(match, "the base SHA must be a full 40-hex commit")
        assert match is not None
        self.assertNotEqual(
            match.group("sha"),
            STALE_BASE_SHA,
            "the issue-207 pin carries no acceptance test, so every run based "
            "on it rejects the task with targeted_test_exists_at_base",
        )

    def test_the_operator_doc_names_the_base_the_daemon_will_actually_use(
        self,
    ) -> None:
        # The doc is what the operator reads before the run, and it states the
        # branch and the SHA in prose. Nothing else makes prose wrong when
        # desired state moves, and a run started against a base the operator
        # confirmed from a stale document fails at the far end of the pipeline.
        branch = self.base_branch()
        sha = re.search(
            r"(?m)^factory_fieldbook_base_sha: (?P<sha>[0-9a-f]{40})$", self.group_vars
        )
        assert sha is not None
        self.assertIn(branch, self.operator_doc)
        self.assertIn(sha.group("sha"), self.operator_doc)

    def test_the_run_says_it_is_attended_with_full_stop_reachable(self) -> None:
        # Precondition 4 step 3, the attended kill drill, was not re-performed
        # for this run. Jacob ruled on 2026-08-25 that it is satisfied without
        # a re-drill on two conditions, and one of them is that the
        # demonstration is watched live with `Full stop` available rather than
        # left to run unattended. That condition is what stands in for the
        # drill, so it has to reach the operator where the operator acts — in
        # `## The run`, not only in a note further down. A doc that says
        # "submit, watch, stop" without it reads as permission to walk away,
        # and walking away voids the premise the ruling was given on.
        self.assertIn("Full stop", self.section("The run"))

    def test_the_undrilled_kill_path_names_its_open_questions(self) -> None:
        # The ruling's other condition: the two unresolved things about the
        # dashboard kill path are filed rather than carried in an operator's
        # head. An operator who hits either of them mid-run — a kill that
        # fails on `requests_closed_state_consistent`, or an outcome with no
        # lease disposition — should find them already known and bounded
        # instead of reading them as a new fault during a live Fieldbook run.
        waiver = self.section("What has and has not been performed")
        self.assertIn("Step 3 was ruled satisfied, not re-drilled", waiver)
        self.assertIn(
            "https://github.com/JacobStephens2/patchyard/issues/321",
            waiver,
            "the waiver has to name its open questions where it is granted, "
            "not somewhere else in the document",
        )

    def test_the_record_names_the_first_attempt_and_what_it_left_behind(
        self,
    ) -> None:
        # The first attended submission happened on 2026-08-25 at 19:03 UTC
        # and ended in a Full stop seven minutes later. It left durable state
        # the next attempt inherits: a request stranded at `claimed`, a second
        # body queued the next evening, and `full_stop` still asserted. An
        # operator who reads "no run has been performed" and presses Resume
        # hands the daemon those two rows before the fixture body is ever
        # submitted - on the installed revision, with no claim ceiling. The
        # record therefore has to name both rows where the operator will read
        # it, and the doc must not still claim nothing has happened.
        record = self.section("What has and has not been performed")
        self.assertNotIn("No run has been performed", record)
        self.assertIn("55868a0e-294b-4116-bbbf-db620c4cdead", record)
        self.assertIn("2235d555-59a6-4d61-a329-4ba45c544b1f", record)
        self.assertIn("Full stop", record)

    def test_the_next_attempt_has_its_own_checklist(self) -> None:
        # What the first attempt taught is only useful if it is a step the
        # operator performs before the next one, not a paragraph of history.
        # The two rows left behind get closed before Resume, and the daemon
        # runs a revision that carries the fixes for the two faults that
        # ended 2026-08-25 (`FACTORY_MAX_CLAIM_ATTEMPTS` and the no-screenshot
        # confirm, both in `2d46b61`).
        checklist = self.section("Before the next attempt")
        self.assertIn("factoryctl close", checklist)
        self.assertIn("2d46b61", checklist)
        self.assertIn("Resume", checklist)

    def test_the_base_must_carry_the_exact_path_production_names(self) -> None:
        # The base branch lives in Fieldbook, which this repository cannot read.
        # What it can prove is that the file the operator is told to land is
        # the exact path the daemon will demand, spelled the same way.
        line = next(
            row
            for row in self.environment.splitlines()
            if row.startswith("FACTORY_VERIFY_TESTS=")
        )
        selection = [path for path in line.split("=", 1)[1].split(",") if path]
        self.assertEqual(len(selection), 1)
        self.assertTrue(
            (FIXTURE / Path(selection[0]).name).exists(),
            f"{selection[0]} has no fixture under {FIXTURE}",
        )


if __name__ == "__main__":
    unittest.main()
