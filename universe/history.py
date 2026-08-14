"""Committing before a change, so it can be undone.

Anyone connected can rename a kind or rebuild the front page, and a rename
touches every file in `content/`. There are no permissions guarding that: the
table shares the shape of the world, and the safety net is git instead. Which
only works if there is a commit to go back to.

The rule this module exists to enforce is narrow. A snapshot records the
*subject* of the change and nothing else. The first version ran `git add -A`,
which swept up whatever else happened to be uncommitted, so a snapshot taken
while someone was midway through editing docs captured those docs too, under a
message that said `before: add_kind`. Two commits in this project's own history
look like that.

So the paths are named. If a caller wants something else snapshotted, it says
so.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# What a structural change can touch. `content/` because a rename moves pages,
# `structure.yaml` because that is the change itself, `people.yaml` because
# adding someone rewrites it.
SUBJECT = ("content", "structure.yaml", "people.yaml")

TIMEOUT = 30


def _git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=str(root), check=False,
            capture_output=True, text=True, timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        # No git, or no repo. The caller's change still goes ahead: the person
        # asked for it, and refusing to work without version control would be
        # a strange place to draw a line.
        return None


def is_repo(root: Path) -> bool:
    result = _git(Path(root), "rev-parse", "--git-dir")
    return bool(result and result.returncode == 0)


def snapshot(root: Path, what: str, who: str = "",
             paths: tuple[str, ...] = SUBJECT) -> bool:
    """Commit the current state of `paths` before something changes them.

    Returns True if a commit was made. False means there was nothing to
    record, or no repo to record it in, both of which are fine: the point is
    that an undo exists when it can, not that every call produces one.
    """
    root = Path(root)
    present = [p for p in paths if (root / p).exists()]
    if not present or not is_repo(root):
        return False

    _git(root, "add", "--", *present)
    # Committing with a pathspec records only these paths, even if something
    # else is already staged. That is the whole point: an unrelated edit
    # sitting in the index must not be swallowed by someone else's rename.
    message = f"before: {what}" + (f" ({who})" if who else "")
    result = _git(root, "commit", "-q", "-m", message, "--", *present)
    return bool(result and result.returncode == 0)
