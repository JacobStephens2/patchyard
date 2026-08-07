import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools/merge-refix.py"

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def load_tool():
    specification = importlib.util.spec_from_file_location("merge_refix", TOOL)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def conflict(ours: str, theirs: str) -> str:
    return f"<<<<<<< ours\n{ours}\n=======\n{theirs}\n>>>>>>> theirs\n"


class ConflictClassification(unittest.TestCase):
    """The rule that decides whether a conflict may be resolved by machine.

    Two branches that each ran the pin cascade produce hunks differing only in
    hex, and taking either side is safe because the cascade recomputes them. A
    hunk that differs structurally is a different thing entirely: when one branch
    pins a file the other does not know about, taking a side drops it from the
    pin set and no later check notices, because the pin set is the thing doing
    the checking.
    """

    def setUp(self):
        self.tool = load_tool()

    def classify(self, body: str) -> bool:
        with tempfile.NamedTemporaryFile(
            "w", dir=self.tool.REPO, suffix=".tmp", delete=False
        ) as handle:
            handle.write(body)
            name = Path(handle.name).name
        try:
            return self.tool.conflict_is_digest_only(name)
        finally:
            (self.tool.REPO / name).unlink()

    def test_hunk_differing_only_in_digests_is_resolvable(self):
        body = conflict(f'    "a": "{DIGEST_A}",', f'    "a": "{DIGEST_B}",')
        self.assertTrue(self.classify(body))

    def test_hunk_adding_a_pinned_entry_is_refused(self):
        body = conflict(
            f'    "a": "{DIGEST_A}",',
            f'    "a": "{DIGEST_B}",\n    "b": "{DIGEST_B}",',
        )
        self.assertFalse(self.classify(body))

    def test_hunk_removing_a_pinned_entry_is_refused(self):
        body = conflict(
            f'    "a": "{DIGEST_A}",\n    "b": "{DIGEST_A}",',
            f'    "a": "{DIGEST_B}",',
        )
        self.assertFalse(self.classify(body))

    def test_hunk_changing_prose_beside_a_digest_is_refused(self):
        body = conflict(
            f'    # keep this pin\n    "a": "{DIGEST_A}",',
            f'    # drop this pin later\n    "a": "{DIGEST_B}",',
        )
        self.assertFalse(self.classify(body))

    def test_file_with_no_conflict_markers_is_not_resolvable(self):
        self.assertFalse(self.classify(f'    "a": "{DIGEST_A}",\n'))

    def test_every_hunk_must_qualify_not_merely_the_first(self):
        body = conflict(f'    "a": "{DIGEST_A}",', f'    "a": "{DIGEST_B}",') + conflict(
            f'    "b": "{DIGEST_A}",',
            f'    "b": "{DIGEST_B}",\n    "c": "{DIGEST_B}",',
        )
        self.assertFalse(self.classify(body))


class GeneratedFileSet(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def test_both_generated_files_are_declared(self):
        """Both files a merge routinely collides on are regenerated, not merged.

        The workflow was missing from this set when the tool was first written,
        and the omission only appeared when a stale branch was merged for real.
        """
        self.assertIn("docs/codebase-metrics.json", self.tool.GENERATED)
        self.assertIn(".github/workflows/infrastructure.yml", self.tool.GENERATED)

    def test_committed_results_are_never_digest_rewrite_targets(self):
        self.assertFalse(
            any(
                path.startswith("research/isolation/results/")
                for path in self.tool.tracked_text_files()
            )
        )


class DigestReportParsing(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def test_unittest_actual_and_expected_digest_are_oriented_for_replacement(self):
        actual = "1" * 64
        expected = "2" * 64
        report = f"AssertionError: '{actual}' != '{expected}'\n"
        self.assertEqual(
            self.tool.digest_substitutions(report),
            {expected: actual},
        )


if __name__ == "__main__":
    unittest.main()
