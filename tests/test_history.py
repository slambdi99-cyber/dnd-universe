"""Tests for the pre-change snapshot.

The safety net for structural edits is git rather than permissions, so this is
about the net actually being there, and about it catching only what it was
aimed at. The original version ran `git add -A` and swept up whatever else was
uncommitted, which is how two commits in this project's history carry unrelated
work under a message that says `before: set_site`.

    python tests\\test_history.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import history  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                          text=True).stdout.strip()


def make_repo() -> Path:
    root = Path(tempfile.mkdtemp(prefix="history-test-"))
    subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root,
                   capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root,
                   capture_output=True)
    (root / "content" / "place").mkdir(parents=True)
    (root / "content" / "place" / "town.md").write_text("Town.", encoding="utf-8")
    (root / "structure.yaml").write_text("site:\n  name: Test\n", encoding="utf-8")
    (root / "README.md").write_text("unrelated\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root,
                   capture_output=True)
    return root


print("\n== a repo with something to record ==")
repo = make_repo()
check("recognised as a repo", history.is_repo(repo))
(repo / "content" / "place" / "town.md").write_text("Town, edited.", encoding="utf-8")
made = history.snapshot(repo, "rename kind place to location", "Wren")
check("commits", made)
check("message says what and who",
      git(repo, "log", "-1", "--pretty=%s")
      == "before: rename kind place to location (Wren)",
      git(repo, "log", "-1", "--pretty=%s"))
check("the change is in it", "Town, edited." in git(repo, "show", "HEAD:content/place/town.md"))

print("\n== it records only what it was aimed at ==")
# The bug this exists for: someone else's half-finished work must not be
# swallowed by a structural change and buried under its message.
(repo / "content" / "place" / "town.md").write_text("Town, again.", encoding="utf-8")
(repo / "README.md").write_text("unrelated, edited\n", encoding="utf-8")
(repo / "notes.txt").write_text("scratch\n", encoding="utf-8")
history.snapshot(repo, "add kind ship", "The DM")
committed = git(repo, "show", "--name-only", "--pretty=", "HEAD").split("\n")
check("the subject is committed", "content/place/town.md" in committed, str(committed))
check("the unrelated edit is not", "README.md" not in committed, str(committed))
check("and it is still sitting there uncommitted",
      "README.md" in git(repo, "status", "--porcelain"))
check("the untracked file is untouched",
      "notes.txt" in git(repo, "status", "--porcelain"))

print("\n== an unrelated edit already staged is still not swept in ==")
(repo / "README.md").write_text("staged by someone else\n", encoding="utf-8")
subprocess.run(["git", "add", "README.md"], cwd=repo, capture_output=True)
(repo / "structure.yaml").write_text("site:\n  name: Renamed\n", encoding="utf-8")
history.snapshot(repo, "set site name", "Wren")
committed = git(repo, "show", "--name-only", "--pretty=", "HEAD").split("\n")
check("the subject went in", "structure.yaml" in committed, str(committed))
check("the staged stranger did not", "README.md" not in committed, str(committed))
check("it is still staged, waiting for its author",
      git(repo, "diff", "--cached", "--name-only") == "README.md")

print("\n== nothing to record ==")
subprocess.run(["git", "checkout", "--", "."], cwd=repo, capture_output=True)
check("a clean tree makes no commit", not history.snapshot(repo, "no change", "Wren"))
before = git(repo, "rev-parse", "HEAD")
history.snapshot(repo, "still no change", "Wren")
check("and does not move HEAD", git(repo, "rev-parse", "HEAD") == before)

print("\n== somewhere that is not a repo ==")
plain = Path(tempfile.mkdtemp(prefix="history-plain-"))
(plain / "content").mkdir()
(plain / "content" / "x.md").write_text("hi", encoding="utf-8")
check("not mistaken for one", not history.is_repo(plain))
check("returns False rather than raising",
      history.snapshot(plain, "something", "Wren") is False,
      "no version control is a reason to skip the net, not to refuse the change")

print("\n== a page edit is credited to whoever made it ==")
# changelog.py builds its "By User" section from the git author. Edits used to
# be committed later, in a batch, by whichever machine ran the sync, so the log
# said one person wrote everything.
(repo / "content" / "wren.md").write_text("Edited.", encoding="utf-8")
check("commits the edit", history.record(repo, "character/wren: edited", "Wren"))
check("author is the editor", git(repo, "log", "-1", "--pretty=%an") == "Wren")
check("address is stable", git(repo, "log", "-1", "--pretty=%ae") == "wren@wiki.local")
check("message survives",
      git(repo, "log", "-1", "--pretty=%s") == "character/wren: edited")

(repo / "content" / "wren.md").write_text("Edited again.", encoding="utf-8")
history.record(repo, "character/wren: edited", "The DM")
check("a second person is a second author",
      git(repo, "log", "-1", "--pretty=%an") == "The DM")
check("and gets their own address",
      git(repo, "log", "-1", "--pretty=%ae") == "the-dm@wiki.local")

check("nothing to commit is not a failure",
      history.record(repo, "character/wren: edited", "Wren") is False)
check("no repo is not a failure",
      history.record(plain, "x: edited", "Wren") is False)
check("a name with no letters still yields an address",
      history.author_for("!!!") == "!!! <someone@wiki.local>")

print("\n== paths that do not exist are skipped ==")
check("no crash when nothing matches",
      history.snapshot(repo, "x", "y", paths=("nothing-here",)) is False)

shutil.rmtree(repo, ignore_errors=True)
shutil.rmtree(plain, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
