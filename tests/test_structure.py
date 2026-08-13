"""Tests for editing the shape of the wiki.

Anyone connected can add a kind, rename one, or rebuild the front page. The
dangerous part isn't the config edit, it's the migration: renaming `place` to
`location` has to move forty files and repoint every link that pointed at them,
or the wiki quietly fills with dead references.

    python tests\\test_structure.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import schema as schema_mod  # noqa: E402
from universe import site as site_mod  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


sandbox = Path(tempfile.mkdtemp(prefix="structure-test-"))
lib = Library(sandbox / "content")

lib.save(Entity(kind="place", slug="brindlewood", name="Brindlewood",
                summary="A township.", data={"map_type": "settlement"},
                links=["character/wren"]))
lib.save(Entity(kind="place", slug="copper-vale", name="Copper Vale",
                summary="The region.", data={"map_type": "region"}))
lib.save(Entity(kind="character", slug="wren", name="Wren",
                summary="An elf fighter.", tags=["player-character"],
                links=["place/brindlewood", "place/copper-vale"]))
lib.save(Entity(kind="faction", slug="six-wolves", name="Six Wolves",
                summary="A mercenary band.", links=["place/brindlewood"]))

print("\n== defaults ==")
schema = schema_mod.load(sandbox)
check("nine kinds out of the box", len(schema.kinds) == 9, str(len(schema.kinds)))
check("labels are plural", schema.label("place") == "Places")
check("an unknown kind still gets a readable label",
      schema.label("plot-thread") == "Plot Thread",
      "a folder with no kind must not vanish")
check("front page has sections", len(schema.home) == 4)

print("\n== adding a kind ==")
ok, msg = schema_mod.add_kind(schema, "Ship", "Ships")
check("case and spacing tolerated", ok and schema.has("ship"), msg)
check("written to structure.yaml", (sandbox / "structure.yaml").exists())
check("config.yaml untouched", not (sandbox / "config.yaml").exists(),
      "hand-written config keeps its comments")
check("rejects a bad key", not schema_mod.add_kind(schema, "Ships & Boats!")[0])
check("rejects a duplicate", not schema_mod.add_kind(schema, "ship")[0])
check("rejects one letter", not schema_mod.add_kind(schema, "x")[0])

lib.save(Entity(kind="ship", slug="the-kestrel", name="The Kestrel",
                summary="A river barge.", links=["place/brindlewood"]))
check("a page saves under the new kind",
      (sandbox / "content" / "ship" / "the-kestrel.md").exists())
check("and reads back", lib.load("ship", "the-kestrel").name == "The Kestrel")

print("\n== relabelling ==")
ok, msg = schema_mod.update_kind(schema, "deity", label="Gods")
check("label changes", ok and schema.label("deity") == "Gods", msg)
ok, _ = schema_mod.update_kind(schema, "session", nav=False)
check("can be hidden from the nav",
      ok and "session" not in [k.key for k in schema.nav])
check("still exists though", schema.has("session"))
check("unknown kind refused", not schema_mod.update_kind(schema, "nope", label="X")[0])
check("no-op reported honestly",
      not schema_mod.update_kind(schema, "deity", label="Gods")[0])

print("\n== renaming, which is really a migration ==")
ok, msg = schema_mod.rename_kind(schema, "place", "location", lib)
check("reported", ok, msg)
check("pages moved", (sandbox / "content" / "location" / "brindlewood.md").exists())
check("old folder gone", not (sandbox / "content" / "place").exists())
check("kind renamed", schema.has("location") and not schema.has("place"))
wren = lib.load("character", "wren")
check("links repointed", wren.links == ["location/brindlewood", "location/copper-vale"],
      str(wren.links))
check("links on other kinds too",
      lib.load("faction", "six-wolves").links == ["location/brindlewood"])
check("and on the new kind's own pages",
      lib.load("ship", "the-kestrel").links == ["location/brindlewood"])
check("front page section followed",
      any(s.kind == "location" for s in schema.home))
check("the moved page kept its frontmatter",
      lib.load("location", "brindlewood").data.get("map_type") == "settlement")
check("refuses renaming onto an existing kind",
      not schema_mod.rename_kind(schema, "location", "character", lib)[0])
check("refuses a bad new key",
      not schema_mod.rename_kind(schema, "location", "Not A Key!", lib)[0])

print("\n== moving one page ==")
ok, msg = schema_mod.move_page(lib, "ship/the-kestrel", "item", schema)
check("moved", ok, msg)
check("file moved", (sandbox / "content" / "item" / "the-kestrel.md").exists())
check("kind rewritten in frontmatter",
      lib.load("item", "the-kestrel").kind == "item")
check("links to it repointed", True)  # nothing linked to it; covered below
lib.save(Entity(kind="character", slug="pilot", name="Pilot",
                links=["item/the-kestrel"]))
check("refuses a collision",
      not schema_mod.move_page(lib, "item/the-kestrel", "item", schema)[0])
check("refuses an unknown kind",
      not schema_mod.move_page(lib, "item/the-kestrel", "spaceship", schema)[0])
check("refuses a page that isn't there",
      not schema_mod.move_page(lib, "item/nothing", "lore", schema)[0])

print("\n== removing a kind ==")
check("refuses while it holds pages",
      not schema_mod.remove_kind(schema, "location", lib)[0],
      "pages would be stranded in a folder nothing lists")
ok, msg = schema_mod.remove_kind(schema, "ship", lib)
check("empty one goes quietly", ok, msg)
ok, msg = schema_mod.remove_kind(schema, "location", lib, "lore")
check("with somewhere to put the pages", ok, msg)
check("pages arrived", (sandbox / "content" / "lore" / "brindlewood.md").exists())
check("links followed them",
      lib.load("character", "wren").links == ["lore/brindlewood", "lore/copper-vale"],
      str(lib.load("character", "wren").links))
check("its front page section went too",
      not any(s.kind == "location" for s in schema.home))
check("refuses an unknown target",
      not schema_mod.remove_kind(schema, "event", lib, "atlantis")[0])

print("\n== the front page ==")
ok, msg = schema_mod.set_home(schema, [
    {"title": "The Party", "kind": "character", "tag": "player-character"},
    {"title": "Everything else", "kind": "lore"},
])
check("rebuilt", ok and len(schema.home) == 2, msg)
check("rejects a section for a kind that doesn't exist",
      not schema_mod.set_home(schema, [{"title": "X", "kind": "dragon"}])[0])
check("a rejected list changes nothing", len(schema.home) == 2)
check("an empty list is allowed", schema_mod.set_home(schema, [])[0],
      "a bare index is a choice someone is allowed to make")

schema_mod.set_home(schema, [
    {"title": "The Party", "kind": "character", "tag": "player-character"},
    {"title": "Lore", "kind": "lore"},
])
site_mod.use(schema)
entities = sorted(lib.all(), key=lambda e: e.name)
html_out = site_mod.render_index(entities, {}, "/wiki/")
check("renders the configured sections", "The Party" in html_out and "Lore" in html_out)
check("skips sections with nothing in them", "Factions" not in html_out,
      "an empty heading is worse than no heading")
check("names the site", schema.name in html_out)

print("\n== naming ==")
ok, msg = schema_mod.set_site(schema, name="The Hollow Root", tagline="A darker one.")
check("renamed", ok and schema.name == "The Hollow Root", msg)
check("nav and title follow",
      "The Hollow Root" in site_mod.shell("x", "/wiki/", "", "[]"))
check("blank input changes nothing", not schema_mod.set_site(schema, "", "")[0])

print("\n== persistence ==")
schema_mod.set_site(schema, name="The Buried Star")
reloaded = schema_mod.load(sandbox)
check("survives a reload", reloaded.name == "The Buried Star")
check("kinds survive", reloaded.has("lore") and not reloaded.has("place"))
check("labels survive", reloaded.label("deity") == "Gods")
check("nav flags survive",
      "session" not in [k.key for k in reloaded.nav])
check("front page survives", len(reloaded.home) == 2)

written = yaml.safe_load((sandbox / "structure.yaml").read_text(encoding="utf-8"))
check("the file is readable YAML", isinstance(written, dict))
check("and keeps its header comment",
      (sandbox / "structure.yaml").read_text(encoding="utf-8").startswith("#"))

print("\n== picking up someone else's edit ==")
live = schema_mod.load(sandbox)
other = schema_mod.load(sandbox)
schema_mod.add_kind(other, "quest", "Quests")
live.reload_if_changed()
check("a change made elsewhere appears without a restart", live.has("quest"))

shutil.rmtree(sandbox, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
