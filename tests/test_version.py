"""Tests for the visible build stamp.

The server updates by pulling and restarts itself only when code changed, so
nothing about a deploy is visible from outside. This is the bit that answers
"is my fix live yet?" from the footer of any page, which means it has to be
right about a tree that is dirty and honest about a tree it cannot read.

    python tests/test_version.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import version  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


def git(root: Path, *args: str) -> None:
    subprocess.run(("git", *args), cwd=str(root), capture_output=True, check=True)


sandbox = Path(tempfile.mkdtemp(prefix="version-test-"))
git(sandbox, "init", "-q")
git(sandbox, "config", "user.email", "t@t.local")
git(sandbox, "config", "user.name", "t")
(sandbox / "a.txt").write_text("one\n")
git(sandbox, "add", "a.txt")
git(sandbox, "commit", "-q", "-m", "first")

print("\n== a clean checkout ==")
version.reset()
clean = version.describe(sandbox)
head = subprocess.run(("git", "rev-parse", "--short", "HEAD"), cwd=str(sandbox),
                      capture_output=True, text=True).stdout.strip()
check("names the commit that is checked out", clean.startswith(head), clean)
check("carries a date", "," in clean, clean)
check("is not marked dirty", "+" not in clean, clean)

print("\n== an edited checkout ==")
# The `+` is the difference between "running what is on GitHub" and "somebody
# edited a file on the VM", which is how a deploy quietly stops matching.
(sandbox / "a.txt").write_text("two\n")
version.reset()
dirty = version.describe(sandbox)
check("is marked dirty", "+" in dirty, dirty)
check("still names the same commit", dirty.startswith(head), dirty)

print("\n== a tree with no git ==")
bare = Path(tempfile.mkdtemp(prefix="version-nogit-"))
version.reset()
check("says so rather than raising", version.describe(bare) == version.UNKNOWN,
      version.describe(bare))

print("\n== read once ==")
version.reset()
first = version.describe(sandbox)
(sandbox / "b.txt").write_text("new\n")
git(sandbox, "add", "b.txt")
git(sandbox, "commit", "-q", "-m", "second")
check("a second call does not re-run git",
      version.describe(sandbox) == first,
      "the stamp is fixed for the life of the process")
version.reset()
check("and reset picks the new commit up", version.describe(sandbox) != first)

print("\n== it reaches the page ==")
check("the shell renders it", "footer class=\"build\"" in
      (ROOT / "universe" / "site.py").read_text(encoding="utf-8"))

print("\n" + ("all checks passed" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
raise SystemExit(1 if FAIL else 0)
