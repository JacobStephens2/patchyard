"""Copy this repository into a scratch tree, for gates that mutate their copy.

Several Ansible gates run a checker against a copy of the repository so they
can mutate it, and `tools/check-ansible.sh` runs those gates concurrently
against one working tree. A copy that walks the tree is therefore reading a
directory its neighbours are writing to: `shutil.copytree` lists a name,
another gate unlinks its temporary file, and the copy dies on a file it was
told existed. The gate that fails is then whichever copy lost the race rather
than one with a defect, which teaches a reviewer to re-run a red gate instead
of reading it.

This copy is driven by an explicit list of paths - what git reports as tracked
or untracked-but-not-ignored, which is the same set the walk used to select -
and a path that has gone by the time it is reached is skipped rather than
fatal. Nothing a neighbouring gate creates or removes can fail the copy.

Git lists files, so the copy is files: an empty directory does not survive it,
and a symlink is not reproduced. Neither has ever been what a gate copies the
tree for, and both are what the walk had to be careful about.

Two other ends were available. `test_merge_refix.py` was the one gate known to
write into the shared root, and stopping it - which this change also does -
removes today's collision but not the class: nothing stops the next gate from
writing there, and the copies would still be walking a directory their
neighbours mutate. Giving each gate its own working tree would end the class
too, at the cost of a tree per gate in the wrapper, which is a large change to
the thing being protected for a race that a robust copy already closes.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[3]


def repository_files(root: Path = ROOT) -> tuple[str, ...]:
    """Every path git accounts for in `root`: tracked, or untracked and not ignored.

    Ignored paths are left out for the reason the walk used to name them one by
    one: gitignored build state (OpenTofu providers alone are ~900MB after
    init) must stay out of the copy or every copy pays for it.
    """
    listing = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
         "--exclude-standard"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return tuple(sorted({entry for entry in listing.split("\0") if entry}))


def copy_repository(destination: Path, root: Path = ROOT) -> Path:
    """Copy the accounted-for files of `root` into `destination`, and return it."""
    destination.mkdir(parents=True, exist_ok=True)
    for relative in repository_files(root):
        source = root / relative
        # A listed path that is not a readable regular file is not this copy's
        # business: a submodule gitlink, a symlink, a file deleted in the
        # working tree, or a neighbouring gate's scratch file that has already
        # gone. The unlink can also land between the test and the read, so the
        # read forgives the same absence rather than only the test.
        if source.is_symlink() or not source.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source, target)
        except FileNotFoundError:
            continue
    return destination
