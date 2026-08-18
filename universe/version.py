"""Which build is actually running, visible from the page.

The server updates itself by pulling: `repo-sync.sh` fetches every couple of
minutes and restarts the wiki only when code changed. Nothing about that is
visible from the outside, so "is my fix live yet?" had no answer short of
opening a shell on the VM.

That is not a hypothetical. Card thumbnails were requested as `?v=...?size=card`
for as long as the feature existed: a second `?` is not a separator, so the
size was never read and every card served the full-size original. It looked
correct, nothing logged an error, and the only symptom was a slow page. A
version in the footer would not have found that bug, but it answers the
question that follows it, which is whether the machine serving the page has the
fix on it yet.

Read once, at import. Running `git` per request would be a subprocess on the
hot path to tell you something that cannot change while the process lives.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

UNKNOWN = "unknown"

_cache: str | None = None


def _git(root: Path, *args: str) -> str:
    """One git command, or an empty string if git has nothing to say.

    A server deployed from a tarball has no `.git`, and one with a broken git
    is still a server. Neither is worth an exception on a page render, so
    every failure lands on the same empty string.
    """
    try:
        out = subprocess.run(
            ("git", *args), cwd=str(root), capture_output=True,
            text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def describe(root: Path | None = None) -> str:
    """A short, human-readable stamp for the checked-out commit.

    Looks like `a1b2c3d, 18 Aug 2026`, or `a1b2c3d+, 18 Aug 2026` when the
    working tree has edits that are not committed. The `+` matters more than it
    looks: it is the difference between "the server is running what is on
    GitHub" and "somebody edited a file on the VM", and the second one is how a
    deploy quietly stops matching the repo.
    """
    global _cache
    if _cache is not None:
        return _cache

    here = Path(root) if root else Path(__file__).resolve().parent.parent
    sha = _git(here, "rev-parse", "--short", "HEAD")
    if not sha:
        _cache = UNKNOWN
        return _cache

    # %ad with a fixed format rather than %ar: "3 weeks ago" is read relative
    # to whenever the process started, which for a server that stays up for a
    # month is a date that silently drifts.
    when = _git(here, "log", "-1", "--format=%ad", "--date=format:%d %b %Y")
    dirty = "+" if _git(here, "status", "--porcelain") else ""
    _cache = f"{sha}{dirty}" + (f", {when}" if when else "")
    return _cache


def reset() -> None:
    """Forget the cached stamp. For tests, which check several trees."""
    global _cache
    _cache = None
