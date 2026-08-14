"""Offline tests. No GPU, no network, no model downloads.

    python tests\\test_universe.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import schema as schema_mod  # noqa: E402
from universe import site, style  # noqa: E402
from universe.assets import AssetSpec, AssetStore  # noqa: E402
from universe.entities import Entity, Library, slugify  # noqa: E402
from universe.worldmap import azgaar  # noqa: E402

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


tmp = Path(tempfile.mkdtemp(prefix="universe-test-"))

print("\n== slugs ==")
check("spaces become hyphens", slugify("The Drowned Lantern") == "the-drowned-lantern")
check("punctuation stripped", slugify("Kira's Ale-House!") == "kira-s-ale-house",
      slugify("Kira's Ale-House!"))
check("empty falls back", slugify("!!!") == "unnamed", slugify("!!!"))

print("\n== entity round trip ==")
original = Entity(
    kind="place",
    slug="drowned-lantern",
    name="The Drowned Lantern",
    summary="A tavern built into a wrecked hull.",
    appearance="tilted ship hull tavern, green lanterns, wet timber",
    tags=["tavern", "landmark"],
    links=["place/saltmere"],
    sources=["discord:12345"],
    body="Regulars say the bell still rings at low tide.",
)
text = original.render()
parsed = Entity.parse(text, kind="place", slug="drowned-lantern")
check("name survives", parsed.name == original.name)
check("appearance survives", parsed.appearance == original.appearance)
check("tags survive", parsed.tags == original.tags, str(parsed.tags))
check("links survive", parsed.links == original.links)
check("body survives", parsed.body == original.body, parsed.body)
check("frontmatter is yaml", text.startswith("---\n"))

print("\n== entity parse without frontmatter ==")
loose = Entity.parse("# Old Notes\n\nSome lore.", kind="lore", slug="old-notes")
check("bare markdown still loads", loose.name == "Old Notes", loose.name)
check("body kept intact", "Some lore." in loose.body)

print("\n== library save and load ==")
lib = Library(tmp / "content")
lib.save(original)
loaded = lib.load("place", "drowned-lantern")
check("loads back", loaded is not None and loaded.name == "The Drowned Lantern")
check("file on disk", (tmp / "content" / "place" / "drowned-lantern.md").exists())

print("\n== upsert never eats human prose ==")
lib.save(
    Entity(
        kind="place",
        slug="saltmere",
        name="Saltmere",
        summary="A human-written summary.",
        appearance="human-written appearance",
        body="Careful worldbuilding nobody should overwrite.",
        tags=["city"],
        links=["place/drowned-lantern"],
    )
)
merged, created = lib.upsert(
    Entity(
        kind="place",
        slug="saltmere",
        name="Saltmere",
        summary="AUTOMATED SUMMARY",
        appearance="AUTOMATED APPEARANCE",
        body="AUTOMATED BODY",
        tags=["from-map", "settlement"],
        links=["place/thornwatch"],
        data={"population": 4200},
    )
)
check("recognised as existing", created is False)
check("human summary kept", merged.summary == "A human-written summary.", merged.summary)
check("human appearance kept", merged.appearance == "human-written appearance")
check("human body kept", merged.body.startswith("Careful worldbuilding"))
check("tags merged not replaced", set(merged.tags) == {"city", "from-map", "settlement"},
      str(merged.tags))
check("links merged", set(merged.links) == {"place/drowned-lantern", "place/thornwatch"})
check("new structured data added", merged.data.get("population") == 4200)

print("\n== upsert fills genuine gaps ==")
lib.save(Entity(kind="place", slug="thornwatch", name="Thornwatch"))
filled, _ = lib.upsert(
    Entity(kind="place", slug="thornwatch", name="Thornwatch",
           summary="Filled in.", appearance="stone watchtower on a ridge")
)
check("empty summary gets filled", filled.summary == "Filled in.")
check("empty appearance gets filled", filled.appearance == "stone watchtower on a ridge")

print("\n== listing, search, backlinks ==")
places = list(lib.all("place"))
check("three places", len(places) == 3, str(len(places)))
check("search finds by body", any(e.slug == "drowned-lantern"
                                 for e in lib.search("low tide")))
check("search is case insensitive", len(lib.search("SALTMERE")) >= 1)
check("empty search returns nothing", lib.search("   ") == [])

# Callers truncate, so order is the whole game. `all()` yields alphabetically,
# which used to put a page that merely mentions the term above the page named
# after it.
ranked = Library(tmp / "ranked")
ranked.save(Entity(kind="place", slug="anchor-house", name="Anchor House",
                   summary="An inn.", body="The road to Whitecliff is long."))
ranked.save(Entity(kind="place", slug="whitecliff", name="Whitecliff",
                   summary="A chalk headland."))
order = [e.slug for e in ranked.search("whitecliff")]
check("exact name outranks a body mention", order == ["whitecliff", "anchor-house"],
      str(order))
back = lib.backlinks("place/drowned-lantern")
check("backlink found", [e.slug for e in back] == ["saltmere"], str([e.slug for e in back]))

print("\n== asset addressing ==")
base = dict(kind="place", slug="saltmere", variant="wide", prompt="a city",
            negative="text", seed=42,
            model="stabilityai/stable-diffusion-xl-base-1.0",
            width=1024, height=1024, steps=30)
a = AssetSpec(**base)
b = AssetSpec(**base)
check("same inputs, same id", a.asset_id == b.asset_id, a.asset_id)
c = AssetSpec(**{**base, "prompt": "a different city"})
check("prompt change gives new id", a.asset_id != c.asset_id)
d = AssetSpec(**{**base, "seed": 43})
check("seed change gives new id", a.asset_id != d.asset_id)
e = AssetSpec(**{**base, "steps": 40})
check("steps change gives new id", a.asset_id != e.asset_id)
check("id is namespaced by entity", a.asset_id.startswith("place/saltmere/wide-"), a.asset_id)

store = AssetStore(tmp / "assets")
check("not present before generation", store.has(a) is False)
check("resolve round trips the path",
      store.resolve(a.asset_id) == store.path_for(a),
      str(store.resolve(a.asset_id)))

print("\n== prompt building ==")
HOUSE = "fantasy illustration, painterly, muted earthy palette"
tavern = lib.load("place", "drowned-lantern")
p = style.build(tavern, house_style=HOUSE, negative="text", variant="interior",
                max_words=60, library=lib)
print(f"    -> {p.text}")
check("house style leads", p.text.startswith("fantasy illustration"))
check("variant template applied", "interior view" in p.text, p.text)
check("appearance included", "green lanterns" in p.text)
check("within budget", len(p.text.split()) <= 60, str(len(p.text.split())))

p2 = style.build(tavern, house_style=HOUSE, negative="text", variant="interior",
                 max_words=60, library=lib)
check("seed is stable across calls", p.seed == p2.seed, str(p.seed))
p3 = style.build(tavern, house_style=HOUSE, negative="text", variant="wide",
                 max_words=60, library=lib)
check("different variant, different seed", p.seed != p3.seed)

char = Entity(kind="character", slug="kira", name="Kira",
              appearance="half-elf rogue, silver hair, twin daggers")
pc = style.build(char, house_style=HOUSE, negative="", variant="portrait", max_words=60)
check("character uses portrait framing", "head and shoulders" in pc.text, pc.text)

bare = Entity(kind="place", slug="nowhere", name="Nowhere",
              summary="Settlement of roughly 24,000 people.")
pb = style.build(bare, house_style=HOUSE, negative="", max_words=60)
check("falls back to the bare name", "Nowhere" in pb.text, pb.text)
check("summary never leaks into the prompt", "24,000" not in pb.text, pb.text)

tight = style.build(tavern, house_style=HOUSE, negative="", variant="interior",
                    max_words=10, library=lib)
check("hard word cap respected", len(tight.text.split()) <= 10, str(len(tight.text.split())))
check("truncation never leaves a dangling conjunction",
      not tight.text.rstrip().endswith(("and", "with", "of", "the", ",")), tight.text)

print("\n== context inheritance direction ==")
region = Entity(kind="place", slug="the-vale", name="The Vale",
                appearance="parched golden grassland, cracked dry earth, bare mountains",
                tags=["primary-location"], data={"map_type": "region"}, links=["place/rivertown"])
town = Entity(kind="place", slug="rivertown", name="Rivertown",
              appearance="walled river city, stone bridges, tiled roofs",
              tags=["sub-location"], data={"map_type": "settlement"}, links=["place/the-vale"])
uncategorized = Entity(kind="place", slug="old-road", name="Old Road",
                       summary="An uncategorized road.")
lib.save(region); lib.save(town); lib.save(uncategorized)

pr = style.build(region, house_style=HOUSE, negative="", max_words=60, library=lib)
check("a region does not inherit its cities' look", "walled river city" not in pr.text,
      pr.text)
pt = style.build(town, house_style=HOUSE, negative="", max_words=60, library=lib)
check("a town does inherit its region's look", "parched golden grassland" in pt.text,
      pt.text)
check("town keeps its own appearance first",
      pt.text.index("walled river city") < pt.text.index("parched golden"), pt.text)

pc2 = style.build(
    Entity(kind="character", slug="monk", name="Monk",
           appearance="tall grey goliath monk, bog-stained robes",
           links=["place/the-vale"]),
    house_style=HOUSE, negative="", variant="portrait", max_words=60, library=lib)
check("a portrait gets no landscape glued on", "grassland" not in pc2.text, pc2.text)

print("\n== place index grouping ==")
schema = schema_mod.load(tmp)
schema_mod.set_index_tags(schema, [
    {"title": "Primary Locations", "kind": "place", "tag": "primary-location"},
    {"title": "Sub-Locations", "kind": "place", "tag": "sub-location"},
    {"title": "Player Characters", "kind": "character", "tag": "player-character"},
    {"title": "NPC Main", "kind": "character", "tag": "npc-main"},
    {"title": "NPC Side", "kind": "character", "tag": "npc-side"},
    {"title": "Player Characters Retired", "kind": "character",
     "tag": "former-party-member"},
    {"title": "Primary Factions", "kind": "faction", "tag": "primary-faction"},
    {"title": "Non-Primary Factions", "kind": "faction",
     "tag": "non-primary-faction"},
])
place_index = site.render_kind_index(schema, "place", list(lib.all("place")), {}, "/wiki/")
check("primary locations come first",
      place_index.index("Primary Locations") < place_index.index("Sub-Locations"),
      place_index)
check("uncategorized locations still show",
      "Other Places" in place_index and "Old Road" in place_index,
      place_index)
check("ordinary indexes stay ungrouped",
      "Primary Locations" not in site.render_kind_index(
          schema, "item",
          [Entity(kind="item", slug="coin", name="Coin")], {}, "/wiki/"))

print("\n== character index grouping ==")
characters = [
    Entity(kind="character", slug="wren", name="Wren", tags=["player-character"]),
    Entity(kind="character", slug="melda", name="Melda", tags=["npc-main"]),
    Entity(kind="character", slug="tavin", name="Tavin", tags=["npc-side"]),
    Entity(kind="character", slug="lucian", name="Lucian", tags=["former-party-member"]),
    Entity(kind="character", slug="stranger", name="Stranger"),
]
character_index = site.render_kind_index(schema, "character", characters, {}, "/wiki/")
check("character groups are ordered",
      character_index.index("Player Characters") < character_index.index("NPC Main")
      < character_index.index("NPC Side")
      < character_index.index("Player Characters Retired")
      < character_index.index("Other Characters"),
      character_index)
check("untagged characters still show",
      "Stranger" in character_index and "Other Characters" in character_index,
      character_index)

print("\n== faction index grouping ==")
factions = [
    Entity(kind="faction", slug="underbelly", name="Underbelly", tags=["primary-faction"]),
    Entity(kind="faction", slug="belt", name="The Belt", tags=["non-primary-faction"]),
    Entity(kind="faction", slug="unknown", name="Unknown Faction"),
]
faction_index = site.render_kind_index(schema, "faction", factions, {}, "/wiki/")
check("faction groups are ordered",
      faction_index.index("Primary Factions") < faction_index.index("Non-Primary Factions")
      < faction_index.index("Other Factions"),
      faction_index)
check("untagged factions still show",
      "Unknown Faction" in faction_index and "Other Factions" in faction_index,
      faction_index)

print("\n== clause-safe trimming ==")
check("cuts on a comma", style.trim_to_words("aaa bb, ccc dd, eee ff", 4) == "aaa bb, ccc dd",
      style.trim_to_words("aaa bb, ccc dd, eee ff", 4))
check("keeps one over-long clause rather than nothing",
      style.trim_to_words("one two three four five", 3) == "one two three",
      style.trim_to_words("one two three four five", 3))

print("\n== azgaar import ==")
fixture = {
    "info": {"version": "1.99", "mapName": "Test World"},
    "biomesData": {"name": ["Marine", "Temperate rainforest", "Cold desert"]},
    "pack": {
        "cells": {"biome": [0, 1, 1, 2]},
        "states": [
            {"i": 0, "name": "Neutrals"},
            {"i": 1, "name": "Aldmere", "fullName": "Kingdom of Aldmere",
             "formName": "Kingdom", "capital": 1, "area": 900,
             "urban": 12.0, "rural": 40.0, "color": "#a33"},
            {"i": 2, "name": "Gone", "removed": True},
        ],
        "provinces": [
            {"i": 0},
            {"i": 1, "name": "Thornmarch", "fullName": "Duchy of Thornmarch",
             "state": 1},
        ],
        "burgs": [
            {},
            {"i": 1, "name": "Saltmere Keep", "cell": 1, "x": 100, "y": 200,
             "state": 1, "province": 1, "population": 24.0, "capital": 1,
             "port": 1, "citadel": 1, "walls": 1, "temple": 1, "plaza": 1},
            {"i": 2, "name": "Millbrook", "cell": 3, "x": 300, "y": 400,
             "state": 1, "population": 0.6},
            {"i": 3, "name": "Vanished", "removed": True},
        ],
        "cultures": [
            {"i": 0, "name": "Wildlands"},
            {"i": 1, "name": "Hollowfolk", "type": "Highland"},
        ],
        "religions": [
            {"i": 0, "name": "No religion"},
            {"i": 1, "name": "The Tidewatch", "type": "Organized"},
        ],
    },
    "notes": [
        {"id": "burg1", "name": "Saltmere Keep",
         "legend": "The old seat of the Aldmere line."},
    ],
}
fixture_path = tmp / "world.json"
fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

entities, report = azgaar.parse(fixture_path)
by_slug = {e.slug: e for e in entities}
check("no warnings on a good map", report.warnings == [], str(report.warnings))
check("neutrals excluded", "neutrals" not in by_slug)
check("removed state excluded", "gone" not in by_slug)
check("removed burg excluded", "vanished" not in by_slug)
check("realm imported", "kingdom-of-aldmere" in by_slug, str(sorted(by_slug)))
check("province imported", "duchy-of-thornmarch" in by_slug)
check("burgs imported", "saltmere-keep" in by_slug and "millbrook" in by_slug)
check("wildlands culture excluded", "wildlands" not in by_slug)
check("real culture imported", "hollowfolk" in by_slug)
check("religion imported", "the-tidewatch" in by_slug)

keep = by_slug["saltmere-keep"]
check("burg links to its realm", "place/kingdom-of-aldmere" in keep.links, str(keep.links))
check("burg links to its province", "place/duchy-of-thornmarch" in keep.links)
check("population scaled to people", keep.data["population"] == 24000,
      str(keep.data["population"]))
check("biome resolved from cells", keep.data["biome"] == "Temperate rainforest",
      str(keep.data["biome"]))
check("legend note became body", "old seat of the Aldmere" in keep.body, keep.body)
check("tagged as capital and port", "capital" in keep.tags and "port" in keep.tags)
print(f"    appearance -> {keep.appearance}")
check("appearance reflects size", "large walled city" in keep.appearance, keep.appearance)
check("appearance mentions harbor", "harbor" in keep.appearance)
check("appearance mentions citadel", "citadel" in keep.appearance)
check("appearance mentions biome", "temperate rainforest" in keep.appearance)

mill = by_slug["millbrook"]
check("small burg reads as village", "village" in mill.appearance, mill.appearance)
check("village has no harbor", "harbor" not in mill.appearance)

realm = by_slug["kingdom-of-aldmere"]
check("realm links to its capital", "place/saltmere-keep" in realm.links, str(realm.links))
check("realm keeps its form", realm.data["form"] == "Kingdom")
check("sources recorded", realm.sources == ["azgaar:state:1"], str(realm.sources))

print("\n== every imported entity is drawable ==")
for entity in entities:
    if not entity.appearance.strip():
        check(f"{entity.name} has an appearance", False)
check("all imported entities have an appearance",
      all(e.appearance.strip() for e in entities))
faction = by_slug["hollowfolk"]
check("faction appearance is heraldic", "sigil" in faction.appearance,
      faction.appearance)
pf = style.build(faction, house_style=HOUSE, negative="", max_words=60)
check("faction prompt has no boilerplate", "recorded on the world map" not in pf.text,
      pf.text)

print("\n== azgaar import writes entities ==")
lib2 = Library(tmp / "content2")
r1 = azgaar.import_map(fixture_path, lib2)
check("first run creates", r1.created == len(entities), f"{r1.created} vs {len(entities)}")
r2 = azgaar.import_map(fixture_path, lib2)
check("second run updates, creates nothing", r2.created == 0 and r2.updated > 0,
      r2.summary())

print("\n== azgaar rejects the wrong file ==")
bad = tmp / "bad.map"
bad.write_text("not json at all", encoding="utf-8")
try:
    azgaar.parse(bad)
    check("bad file raises", False)
except ValueError as exc:
    check("bad file raises a helpful error", "Save as JSON" in str(exc), str(exc)[:60])

empty = tmp / "empty.json"
empty.write_text("{}", encoding="utf-8")
_, empty_report = azgaar.parse(empty)
check("empty map warns instead of crashing", len(empty_report.warnings) == 1)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
