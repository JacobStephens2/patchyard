"""The repository copy the parallel gates make must survive its neighbours.

`tools/check-ansible.sh` runs every test file in this directory concurrently
against one working tree, and several of them copy that tree in `setUp`. A copy
that walks the tree sees whatever the other gates are doing to it at that
instant, so a temporary file another gate creates and unlinks can kill an
unrelated copy mid-walk.

What the copy contains is therefore pinned against a scratch repository these
tests own outright: an assertion about the exact contents of a copy of the
shared tree would be the very flake this file exists to close, because a
neighbour's scratch file can enter that copy between the copy and the
assertion. Of the shared tree these tests ask only what no neighbour can
change.
"""

import importlib.util
import os
import pathlib
import shutil
import subprocess
import tempfile
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
HELPER = pathlib.Path(__file__).with_name("repository_copy.py")


def load_helper() -> types.ModuleType:
    specification = importlib.util.spec_from_file_location("repository_copy", HELPER)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def git(*arguments: str, cwd: pathlib.Path) -> None:
    subprocess.run(
        ["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True
    )


class ScratchRepositoryTest(unittest.TestCase):
    """A repository of this test's own, so its timing is nobody else's."""

    def setUp(self) -> None:
        self.helper = load_helper()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = pathlib.Path(self.temp.name) / "source"
        (self.source / "nested").mkdir(parents=True)
        (self.source / "kept.txt").write_text("kept\n")
        (self.source / "nested/kept.txt").write_text("nested\n")
        git("init", "--quiet", cwd=self.source)

    def copy(self, name: str = "copy") -> pathlib.Path:
        return self.helper.copy_repository(
            pathlib.Path(self.temp.name) / name, self.source
        )

    def contents(self, root: pathlib.Path) -> set[str]:
        return {
            str(path.relative_to(root))
            for path in root.rglob("*")
            if path.is_file() or path.is_symlink()
        }


class RepositoryCopySurvivesAVanishedPath(ScratchRepositoryTest):
    """The race, run where its timing is ours instead of the scheduler's.

    Losing the race on purpose against the real repository is not something a
    test can arrange, so the source directory here holds what a copy that lost
    it meets: a name the copy is told about which is not there when it is
    reached. `shutil.copytree` - the arrangement these gates used - dies on it,
    which is the failure the infrastructure gate kept reporting against
    whichever gate happened to be copying at the time.
    """

    def test_a_name_that_cannot_be_read_does_not_fail_the_copy(self) -> None:
        # A dangling link is a name that is listed and then is not there when
        # it is read: the same absence a scratch file unlinked mid-copy leaves,
        # arranged so the test does not depend on timing.
        (self.source / "tmp0000000.tmp").symlink_to(self.source / "already-gone")

        with self.assertRaises(shutil.Error):
            shutil.copytree(self.source, pathlib.Path(self.temp.name) / "walked")

        self.assertEqual(self.contents(self.copy()), {"kept.txt", "nested/kept.txt"})

    def test_a_listed_file_deleted_from_the_working_tree_is_skipped(self) -> None:
        vanishing = self.source / "vanishing.tmp"
        vanishing.write_text("listed by the index, gone from the tree\n")
        git("add", "--all", cwd=self.source)
        vanishing.unlink()

        self.assertEqual(self.contents(self.copy()), {"kept.txt", "nested/kept.txt"})

    def test_a_file_that_goes_after_it_is_tested_does_not_fail_the_copy(self) -> None:
        """The other half of the window: gone between the test and the read.

        The unlink can land after the copy has decided a file is there, which
        no arrangement of the source directory can reproduce, so the absence is
        raised where the copy would meet it.
        """
        (self.source / "vanishing.tmp").write_text("gone during the read\n")
        real_copy2 = shutil.copy2

        def copy2(source, target):
            if pathlib.Path(source).name == "vanishing.tmp":
                raise FileNotFoundError(2, "No such file or directory", str(source))
            return real_copy2(source, target)

        self.helper.shutil = types.SimpleNamespace(copy2=copy2)
        self.assertEqual(self.contents(self.copy()), {"kept.txt", "nested/kept.txt"})


class RepositoryCopyIsTheListedTree(ScratchRepositoryTest):
    """What lands in the copy is what git accounts for, and nothing else."""

    def test_tracked_and_untracked_files_are_copied_and_ignored_ones_are_not(
        self,
    ) -> None:
        (self.source / ".gitignore").write_text("build/\n")
        (self.source / "build").mkdir()
        (self.source / "build/product.bin").write_text("expensive\n")
        git("add", "kept.txt", "nested/kept.txt", cwd=self.source)
        (self.source / "untracked.txt").write_text("new source, not committed\n")

        self.assertEqual(
            self.contents(self.copy()),
            {".gitignore", "kept.txt", "nested/kept.txt", "untracked.txt"},
        )

    def test_an_executable_stays_executable(self) -> None:
        script = self.source / "run.sh"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)

        self.assertTrue(os.access(self.copy() / "run.sh", os.X_OK))

    def test_a_directory_git_does_not_account_for_is_not_reproduced(self) -> None:
        """Git lists files, so an empty directory does not survive the copy."""
        (self.source / "empty").mkdir()

        self.assertFalse((self.copy() / "empty").exists())


class RepositoryCopyOfThisRepository(unittest.TestCase):
    """Of the shared tree, only what a neighbouring gate cannot change."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.copy = load_helper().copy_repository(
            pathlib.Path(temp.name) / "repo", ROOT
        )

    def test_the_copy_leaves_out_git_and_ignored_build_state(self) -> None:
        for excluded in (".git", ".venv", "target", ".terraform"):
            self.assertFalse((self.copy / excluded).exists(), excluded)

    def test_the_copy_can_run_the_checkers_it_is_made_for(self) -> None:
        self.assertTrue((self.copy / "tools/check-a101-readiness-root.py").is_file())
        self.assertTrue(os.access(self.copy / "tools/check-ansible.sh", os.X_OK))


if __name__ == "__main__":
    unittest.main()
