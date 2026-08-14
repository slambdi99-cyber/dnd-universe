"""Tests for the generated changelog.

    python tests/test_changelog.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import changelog  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def commit(root: Path, message: str, author: str) -> None:
    git(root, "add", "content")
    git(root, "-c", f"user.name={author}", "-c", "user.email=test@example.com",
        "commit", "-m", message, "--author", f"{author} <test@example.com>")


sandbox = Path(tempfile.mkdtemp(prefix="changelog-test-"))
git(sandbox, "init")
lib = Library(sandbox / "content")

lib.save(Entity(kind="character", slug="wren", name="Wren",
                summary="An elf fighter.", appearance="an elf",
                body="First draft."))
commit(sandbox, "Create Wren", "Sam")

entity = lib.load("character", "wren")
entity.summary = "An elf fighter, revised."
lib.save(entity)
commit(sandbox, "Revise Wren", "Wren")

print("\n== changelog ==")
log = changelog.load(sandbox, lib)
check("reads git history", not log.error, log.error)
check("finds both content changes", len(log.changes) == 2, str(log.changes))
check("uses page names", all(c.name == "Wren" for c in log.changes))
check("records authors", {c.author for c in log.changes} == {
    "Sam <test@example.com>",
    "Wren <test@example.com>",
})
check("newest first", log.changes[0].subject == "Revise Wren")

html = changelog.render(log, "/wiki/")
check("renders recent changes", "Recent Changes" in html and "Revise Wren" in html)
check("renders page grouping", "By Page" in html and "/wiki/character/wren.html" in html)
check("renders user grouping", "By User" in html and "Sam &lt;test@example.com&gt;" in html)
check("can restrict visible pages",
      changelog.restrict(log, frozenset({"place/brindlewood"})).changes == [])

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
