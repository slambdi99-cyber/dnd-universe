"""Tests for hover tooltips.

The interesting cases are the ones that would make tooltips worse than nothing:
matching ordinary English words, and leaking a page someone can't see.

    python tests\\test_tooltips.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import access  # noqa: E402
from universe import tooltips as tt  # noqa: E402
from universe.entities import Entity  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


entities = [
    Entity(kind="place", slug="brindlewood", name="Brindlewood",
           summary="A small crossroads township."),
    Entity(kind="character", slug="wren", name="Wren",
           summary="Elf fighter from Laurelthel."),
    Entity(kind="lore", slug="dm-notes", name="DM Notes", summary="Behind the screen.",
           data={"visible_to": ["dm"]}),
]

print("\n== the index ==")
raw = tt.build(entities, access.Viewer.of({"wren", "player"}), ROOT, "/wiki/")
index = json.loads(raw)
by_term = {e["t"].lower(): e for e in index}
check("built something", len(index) > 0, f"{len(index)} entries")
check("includes wiki pages", "brindlewood" in by_term)
check("wiki entries carry a url", by_term["brindlewood"]["u"].endswith("brindlewood.html"))
check("wiki entries carry the summary",
      "crossroads" in by_term["brindlewood"]["d"])

srd = tt.load_srd(ROOT)
if srd:
    check("includes SRD spells", "fireball" in by_term, f"{len(srd)} srd entries")
    if "fireball" in by_term:
        fb = by_term["fireball"]
        check("spell carries level and school", "Evocation" in fb["m"], fb["m"])
        check("spell carries a description", len(fb["d"]) > 50)
        check("spell descriptions are trimmed", len(fb["d"]) <= 700, str(len(fb["d"])))
else:
    print("  SKIP  no data/srd.json yet; run tools/fetch_srd.py")

print("\n== ordinary English words need a capital ==")
for word in ("light", "shield", "command", "fly", "web", "sleep"):
    entry = by_term.get(word)
    if entry:
        check(f"'{word}' is capitalisation-gated", entry["c"] == 1, str(entry))
check("distinctive names are not gated",
      by_term.get("fireball", {}).get("c", 0) == 0 if "fireball" in by_term else True)
check("multi-word names are never gated",
      all(e["c"] == 0 for e in index if " " in e["t"]))

print("\n== visibility ==")
check("a restricted page is absent for a player", "dm notes" not in by_term)
sam_index = {e["t"].lower() for e in
             json.loads(tt.build(entities, access.Viewer.of({"dm", "dm"}), ROOT, "/wiki/"))}
check("but present for the DM", "dm notes" in sam_index)

print("\n== wiki wins name clashes with the SRD ==")
clash = [Entity(kind="item", slug="shield", name="Shield",
                summary="Tobias's dented shield.")]
merged = {e["t"].lower(): e for e in
          json.loads(tt.build(clash, access.Viewer.of({"wren"}), ROOT, "/wiki/"))}
check("wiki entry takes the name", merged["shield"]["k"] == "wiki", merged["shield"]["k"])
check("and keeps its own summary", "Tobias" in merged["shield"]["d"])

print("\n== the client script ==")
js = tt.TOOLTIP_JS
check("skips anchors", "'A'" in js)
check("skips code blocks", "'CODE'" in js and "'PRE'" in js)
check("skips headings", "'H1'" in js)
check("matches longest term first", "sort(" in js)
check("uses word boundaries", "\\\\b" in js)
check("dismisses on escape", "Escape" in js)
check("works on touch", "click" in js)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
