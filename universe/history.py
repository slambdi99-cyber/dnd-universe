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

import re
import subprocess
from pathlib import Path

# What a structural change can touch. `content/` because a rename moves pages,
# `structure.yaml` because that is the change itself, `people.yaml` because
# adding someone rewrites it.
SUBJECT = ("content", "structure.yaml", "people.yaml")

# Where a page edit lands. Narrower than SUBJECT on purpose: recording who
# wrote a page must not sweep up a structure change someone else is midway
# through.
PAGES = ("content",)

TIMEOUT = 30

# Authors need an address or git rejects the commit. Nobody here has one --
# people are identified by the name they picked -- so the domain is a marker
# that this is a wiki identity rather than a mailbox.
AUTHOR_DOMAIN = "wiki.local"
_NOT_NAME = re.compile(r"[^a-z0-9]+")


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


def author_for(who: str) -> str:
    """`Name <handle@wiki.local>`, stable for the same person.

    The changelog groups by this string, so it has to come out identical every
    time or one person becomes several rows.
    """
    handle = _NOT_NAME.sub("-", who.strip().lower()).strip("-") or "someone"
    return f"{who.strip()} <{handle}@{AUTHOR_DOMAIN}>"


def record(root: Path, what: str, who: str,
           paths: tuple[str, ...] = PAGES) -> bool:
    """Commit a finished page edit, crediting the person who made it.

    The mirror of `snapshot`: that one commits the state *before* a change so
    it can be undone, this one commits the change *after* so it is attributed.

    Attribution is the point. `changelog.py` builds its "By User" section from
    the git author, and until now every edit made through the site or over MCP
    was committed later, in a batch, by whichever machine ran the sync. So the
    log said one person wrote everything. Passing `--author` here puts the
    actual editor in the commit; the committer stays the server, which is a
    truthful description of what happened.

    Returns False when there was nothing to commit or no repo, both fine.
    """
    root = Path(root)
    present = [p for p in paths if (root / p).exists()]
    if not present or not is_repo(root):
        return False

    _git(root, "add", "--", *present)
    result = _git(
        root,
        # The server may have no git identity of its own -- a fresh container
        # usually doesn't -- and without a committer git refuses the commit
        # even though --author is set. These only apply to this one command.
        "-c", f"user.name={AUTHOR_DOMAIN}",
        "-c", f"user.email=server@{AUTHOR_DOMAIN}",
        "commit", "-q", "-m", what, f"--author={author_for(who)}",
        "--", *present,
    )
    return bool(result and result.returncode == 0)
