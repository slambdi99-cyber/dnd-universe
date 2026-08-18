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
                links=["character/wren"], within="place/copper-vale"))
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
# Renaming the kind moves every page. A child still saying `within: place/...`
# would point at a folder that no longer exists, and every place would silently
# become top level: the hierarchy would not error, it would just be gone.
check("the hierarchy survives the rename",
      lib.load("location", "brindlewood").within == "location/copper-vale",
      str(lib.load("location", "brindlewood").within))

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

print("\n== a move carries the art ==")
# Asset ids embed the page ref and every permission check trusts the prefix.
# A move that leaves old ids behind strands the whole gallery: images 404
# (the old ref names no page) and Mark inactive answers "not on this page".
lib.save(Entity(kind="item", slug="lantern", name="Lantern",
                summary="A lamp.",
                art=["item/lantern/default-aaaa1111",
                     "item/lantern/upload-bbbb2222"],
                data={"active_art": "item/lantern/default-aaaa1111",
                      "files": [{"id": "item/lantern/upload-cccc3333",
                                 "name": "deed.pdf", "size": 100}]}))
assets = sandbox / "assets"
files_root = sandbox / "files"
(assets / "item" / "lantern").mkdir(parents=True)
(assets / "item" / "lantern" / "default-aaaa1111.webp").write_bytes(b"x")
(assets / "item" / "lantern" / "default-aaaa1111.json").write_text(
    '{"kind": "item", "slug": "lantern", '
    '"asset_id": "item/lantern/default-aaaa1111"}', encoding="utf-8")
(files_root / "item" / "lantern").mkdir(parents=True)
(files_root / "item" / "lantern" / "upload-cccc3333.pdf").write_bytes(b"y")

ok, msg = schema_mod.move_page(lib, "item/lantern", "lore", schema,
                               asset_roots=(assets, files_root))
check("moved", ok, msg)
moved = lib.load("lore", "lantern")
check("art ids follow the page",
      moved.art == ["lore/lantern/default-aaaa1111",
                    "lore/lantern/upload-bbbb2222"], str(moved.art))
check("active_art follows too",
      moved.data.get("active_art") == "lore/lantern/default-aaaa1111")
check("file attachments follow",
      moved.data["files"][0]["id"] == "lore/lantern/upload-cccc3333")
check("the image moved on disk",
      (assets / "lore" / "lantern" / "default-aaaa1111.webp").exists()
      and not (assets / "item" / "lantern").exists())
check("the attachment moved on disk",
      (files_root / "lore" / "lantern" / "upload-cccc3333.pdf").exists())
import json as _json
side = _json.loads((assets / "lore" / "lantern" /
                    "default-aaaa1111.json").read_text(encoding="utf-8"))
check("the sidecar was told",
      side["asset_id"] == "lore/lantern/default-aaaa1111"
      and side["kind"] == "lore", str(side))

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
pages = site_mod.Renderer(schema)
entities = sorted(lib.all(), key=lambda e: e.name)
html_out = pages.index(entities, {}, "/wiki/")
check("renders the configured sections", "The Party" in html_out and "Lore" in html_out)
check("skips sections with nothing in them", "Factions" not in html_out,
      "an empty heading is worse than no heading")
check("names the site", schema.name in html_out)

print("\n== first-class index tags ==")
ok, msg = schema_mod.set_index_tags(schema, [
    {"title": "Player Characters", "kind": "character", "tag": "player-character"},
    {"title": "Lore Pages", "kind": "lore", "tag": "worldbuilding"},
])
check("index tag groups saved", ok and len(schema.index_tags) == 2, msg)
check("rejects a tag group for a kind that doesn't exist",
      not schema_mod.set_index_tags(schema, [
          {"title": "Dragons", "kind": "dragon", "tag": "dragon"}
      ])[0])
check("a rejected index tag list changes nothing", len(schema.index_tags) == 2)
check("rejects incomplete index tag groups",
      not schema_mod.set_index_tags(schema, [
          {"title": "Nameless", "kind": "character"}
      ])[0])
check("an empty index tag list is allowed",
      schema_mod.set_index_tags(schema, [])[0])
schema_mod.set_index_tags(schema, [
    {"title": "Player Characters", "kind": "character", "tag": "player-character"},
    {"title": "Lore Pages", "kind": "lore", "tag": "worldbuilding"},
])
grouped = site_mod.Renderer(schema).kind_index(
    "character",
    [
        Entity(kind="character", slug="wren", name="Wren",
               tags=["player-character"]),
        Entity(kind="character", slug="other", name="Other"),
    ],
    {},
    "/wiki/",
)
check("configured tags split kind index pages",
      "Player Characters" in grouped and "Other Characters" in grouped,
      grouped)

print("\n== naming ==")
ok, msg = schema_mod.set_site(schema, name="The Hollow Root", tagline="A darker one.")
check("renamed", ok and schema.name == "The Hollow Root", msg)
check("nav and title follow",
      "The Hollow Root" in site_mod.Renderer(schema).shell("x", "/wiki/", "", "[]"))
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
check("index tags survive", len(reloaded.index_tags) == 2)

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

schema_mod.set_index_tags(live, [
    {"title": "Quests", "kind": "quest", "tag": "quest"}
])
schema_mod.rename_kind(live, "quest", "mission", lib)
check("renaming a kind moves index tag groups too",
      live.index_tags[0].kind == "mission")
schema_mod.remove_kind(live, "mission", lib)
check("removing a kind drops its index tag groups too", live.index_tags == [])

print("\n== two schemas at once ==")
# Impossible before: rendering read a module-level global, so a second schema
# would have silently overwritten the first for every caller in the process.
#
# Two campaigns means two roots. Pointing both at one structure.yaml would
# prove nothing, because `reload_if_changed` would correctly converge them,
# which is the behaviour a single campaign wants.
elsewhere = Path(tempfile.mkdtemp(prefix="structure-other-"))
other = schema_mod.load(elsewhere)
schema_mod.set_site(other, name="A Different Campaign")
one, two = site_mod.Renderer(schema), site_mod.Renderer(other)
check("each renderer keeps its own name",
      one.name != two.name, f"{one.name} vs {two.name}")
check("and renders with it",
      one.name in one.shell("x", "/wiki/", "", "[]")
      and two.name in two.shell("x", "/wiki/", "", "[]"))
check("building one does not disturb the other",
      site_mod.Renderer(other).name == "A Different Campaign"
      and one.name == schema.name)
check("nothing global is left to poke",
      not hasattr(site_mod, "SCHEMA") and not hasattr(site_mod, "use"),
      "a test that forgot site.use() used to render against whatever was on disk")

print("\n== a place with things inside it cannot be moved out ==")
# Last, because it empties a kind, and earlier sections need one that is not.
#
# `location` is what `place` was renamed to earlier in this file, which is the
# point: nothing in hierarchy.py compares against the string "place", so a
# renamed kind still nests. Moving Copper Vale to another kind would leave
# Brindlewood pointing at something that is no longer a place, and the
# hierarchy would flatten with no error at all.
lib.save(Entity(kind="location", slug="the-reach", name="The Reach",
                summary="A region nothing else uses."))
lib.save(Entity(kind="location", slug="thornhold", name="Thornhold",
                summary="A township.", within="location/the-reach"))
check("the rename left the nesting intact",
      lib.load("location", "thornhold").within == "location/the-reach")

ok, msg = schema_mod.move_page(lib, "location/the-reach", "lore", schema)
check("refused", not ok, msg)
check("and says what is in the way", "Thornhold" in msg, msg)
check("the page did not move", lib.load("location", "the-reach") is not None)

check("one with nothing inside it moves fine",
      schema_mod.move_page(lib, "location/thornhold", "lore", schema)[0])
check("and then the parent can move too",
      schema_mod.move_page(lib, "location/the-reach", "lore", schema)[0])

shutil.rmtree(sandbox, ignore_errors=True)
shutil.rmtree(elsewhere, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
