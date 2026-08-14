"""Tests for the thumbnail cache.

The front page shows every settlement, character and faction as a card, and
each card was loading the full-size original: 35MB of art to draw 22 pictures
a few hundred pixels wide. These are the small copies, and the rule that
matters is that a failure here degrades to the original rather than to a
broken image.

    python tests\\test_thumbs.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import thumbs  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


sandbox = Path(tempfile.mkdtemp(prefix="thumbs-test-"))
folder = sandbox / "character" / "wren"
folder.mkdir(parents=True)

from PIL import Image  # noqa: E402

big = folder / "portrait.png"
Image.new("RGB", (1024, 1024), (90, 60, 30)).save(big)
small = folder / "sketch.png"
Image.new("RGB", (120, 120), (30, 60, 90)).save(small)

print("\n== shrinking ==")
card = thumbs.make(big, "card")
check("a thumbnail is produced", card is not None and card != big)
check("it is webp", card.suffix == ".webp", card.name)
check("it lives beside the original, out of the way",
      card.parent.name == ".thumbs" and card.parent.parent == folder)
with Image.open(card) as im:
    check("no wider than the card size", im.width <= thumbs.SIZES["card"], str(im.size))
check("and much smaller on disk",
      card.stat().st_size < big.stat().st_size / 4,
      f"{big.stat().st_size // 1024}KB -> {card.stat().st_size // 1024}KB")

page = thumbs.make(big, "page")
check("a page-size copy is bigger than a card-size one",
      page.stat().st_size > card.stat().st_size)

print("\n== not making work twice ==")
stamp = card.stat().st_mtime_ns
again = thumbs.make(big, "card")
check("a second call reuses the file", again == card and again.stat().st_mtime_ns == stamp)

# Touching the original must invalidate it, or replacing a page's picture
# would leave the old thumbnail showing.
import os  # noqa: E402
import time  # noqa: E402

time.sleep(0.01)
os.utime(big, None)
Image.new("RGB", (1024, 1024), (10, 120, 10)).save(big)
fresh = thumbs.make(big, "card")
check("a changed original is re-shrunk", fresh.stat().st_mtime_ns != stamp)

print("\n== when it should not bother ==")
check("an image already smaller than the target is returned as-is",
      thumbs.make(small, "card") == small,
      "shrinking it would make it bigger, not smaller")
check("an unknown size is refused", thumbs.make(big, "enormous") is None)
check("a missing file is refused", thumbs.make(folder / "nope.png", "card") is None)

broken = folder / "broken.png"
broken.write_bytes(b"\x89PNG\r\n\x1a\nthis is not really a png")
check("a corrupt image falls back to the original",
      thumbs.make(broken, "card") == broken,
      "a picture that will not shrink is still a picture")

print("\n== the cache is disposable ==")
check("sweep removes them", thumbs.sweep(sandbox) >= 2)
check("and the folder goes with them",
      not (folder / ".thumbs").exists())
check("originals are untouched", big.exists() and small.exists())
check("and they come back", thumbs.make(big, "card") is not None)

shutil.rmtree(sandbox, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
