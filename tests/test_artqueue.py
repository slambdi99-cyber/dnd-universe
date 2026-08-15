"""Tests for the art queue.

The site moved to a host with no graphics card, so pressing Art there writes a
request into the repo and the machine at home draws it later. Two things matter:
an impatient refresh must not queue the same picture five times, and a
half-written request must not take a page down with it.

    python tests\\test_artqueue.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import artqueue  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


root = Path(tempfile.mkdtemp(prefix="artqueue-test-"))

print("\n== asking for a picture ==")
item = artqueue.request(root, "place", "gallowmere", "a drowned bell tower",
                        who="Wren")
check("returns the request", item is not None)
check("it is on disk", bool(item and item.path and item.path.exists()))
check("under art-queue/", (root / artqueue.FOLDER).is_dir())
check("carries the page", bool(item and item.page == "place/gallowmere"))
check("carries who asked", bool(item and item.who == "Wren"))
check("stamped with a time", bool(item and item.at))

print("\n== an impatient refresh does not queue it five times ==")
# Twenty minutes of GPU per accidental duplicate is the cost of getting this
# wrong, and a refresh is the most ordinary thing a person does to a slow page.
for _ in range(4):
    artqueue.request(root, "place", "gallowmere", "a drowned bell tower", who="Wren")
check("still one request", len(artqueue.pending(root)) == 1,
      str(len(artqueue.pending(root))))

print("\n== a different prompt is a different request ==")
artqueue.request(root, "place", "gallowmere", "the same tower at noon", who="Sam")
check("now two", len(artqueue.pending(root)) == 2)
artqueue.request(root, "character", "wren", "a woman in a salt-stained coat")
check("and three across pages", len(artqueue.pending(root)) == 3)

print("\n== whitespace is not a different prompt ==")
artqueue.request(root, "place", "gallowmere", "  a drowned   bell tower\n")
check("collapsed to the same request", len(artqueue.pending(root)) == 3,
      str(len(artqueue.pending(root))))

print("\n== asking for one page ==")
check("filters by page", len(artqueue.pending(root, "place", "gallowmere")) == 2)
check("and by a page with one", len(artqueue.pending(root, "character", "wren")) == 1)
check("a page with none is empty", artqueue.pending(root, "place", "nowhere") == [])

print("\n== nothing to say when nothing is waiting ==")
check("no message for a quiet page", artqueue.waiting_for(root, "place", "nowhere") == "")
check("singular reads as one",
      artqueue.waiting_for(root, "character", "wren").startswith("One picture"))
check("plural counts them",
      artqueue.waiting_for(root, "place", "gallowmere").startswith("2 pictures"))

print("\n== an empty prompt is not a request ==")
check("empty refused", artqueue.request(root, "place", "x", "") is None)
check("whitespace refused", artqueue.request(root, "place", "x", "   \n ") is None)
check("nothing was written", len(artqueue.pending(root)) == 3)

print("\n== the count is clamped ==")
big = artqueue.request(root, "place", "harbour", "ships", count=99)
check("four at most", bool(big and big.count == 4), str(big.count if big else None))
small = artqueue.request(root, "place", "harbour", "gulls", count=0)
check("one at least", bool(small and small.count == 1))

print("\n== a half-written request does not take a page down ==")
# pending() is called on every art page render. A file being written by the
# other machine mid-pull is a normal thing to walk into, not an exception.
(root / artqueue.FOLDER / "broken.json").write_text("{not json", encoding="utf-8")
before = len(artqueue.pending(root))
check("the readable ones still come back", before == 5, str(before))

print("\n== drawing one forgets it ==")
first = artqueue.pending(root)[0]
check("removed", artqueue.done(first))
check("one fewer waiting", len(artqueue.pending(root)) == 4)
check("forgetting it twice is not an error", artqueue.done(first) is False)

print("\n== no queue at all ==")
empty = Path(tempfile.mkdtemp(prefix="artqueue-empty-"))
check("returns nothing rather than raising", artqueue.pending(empty) == [])
check("and says nothing", artqueue.waiting_for(empty, "place", "x") == "")

print("\n== a prompt cannot escape the queue folder ==")
sneaky = artqueue.request(root, "../../etc", "../../passwd", "a picture")
check("written inside the queue folder",
      bool(sneaky and sneaky.path.parent == root / artqueue.FOLDER),
      str(sneaky.path if sneaky else None))
check("the filename carries no path at all",
      bool(sneaky and "/" not in sneaky.path.name and "\\" not in sneaky.path.name
           and ".." not in sneaky.path.name),
      str(sneaky.path.name if sneaky else None))
check("the page it names is kept as written, for the drawer to reject",
      bool(sneaky and sneaky.kind == "../../etc"),
      "the queue records the ask; whether the page exists is the drawer's problem")

shutil.rmtree(root, ignore_errors=True)
shutil.rmtree(empty, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
