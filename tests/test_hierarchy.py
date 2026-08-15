"""Tests for places inside places.

Two of the rules here fail quietly if they are wrong, which is why they get the
most attention: a breadcrumb that names a secret place leaks it to everyone who
walks into a room, and a loop in the data hangs whatever is rendering.

    python tests\\test_hierarchy.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import hierarchy  # noqa: E402
from universe.access import Viewer  # noqa: E402
from universe.entities import Entity  # noqa: E402
from universe.people import Person  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


def place(slug: str, name: str, within: str = "", visible_to=None) -> Entity:
    return Entity(kind="place", slug=slug, name=name, within=within,
                  visible_to=list(visible_to or []))


# Copper Vale > Valeshire > the pub and the tavern, plus a second branch.
VALE = place("copper-vale", "Copper Vale")
SHIRE = place("valeshire", "Valeshire", "place/copper-vale")
PUB = place("peapod-pub", "The Peapod Pub", "place/valeshire")
TAVERN = place("valeshire-tavern", "Valeshire Tavern", "place/valeshire")
LORITHAL = place("lorithal", "Lorithal")
HEIGHTS = place("the-broadheights", "The Broadheights", "place/lorithal")
WORLD = [VALE, SHIRE, PUB, TAVERN, LORITHAL, HEIGHTS]
BY_REF = hierarchy.index(WORLD)

print("\n== walking up ==")
check("a room knows its city and its region",
      [e.name for e in hierarchy.ancestors(PUB, BY_REF)]
      == ["Copper Vale", "Valeshire"],
      str([e.name for e in hierarchy.ancestors(PUB, BY_REF)]))
check("outermost comes first",
      hierarchy.ancestors(PUB, BY_REF)[0].name == "Copper Vale")
check("a top level place has none", hierarchy.ancestors(VALE, BY_REF) == [])
check("a second branch does not bleed into the first",
      [e.name for e in hierarchy.ancestors(HEIGHTS, BY_REF)] == ["Lorithal"])

print("\n== walking down ==")
check("a city lists its own places",
      [e.name for e in hierarchy.children("place/valeshire", WORLD)]
      == ["The Peapod Pub", "Valeshire Tavern"])
check("alphabetically",
      hierarchy.children("place/valeshire", WORLD)[0].name == "The Peapod Pub")
check("direct children only, not grandchildren",
      [e.name for e in hierarchy.children("place/copper-vale", WORLD)] == ["Valeshire"],
      "a region listing every shop in every town is not an index of anything")
check("everything inside, at any depth",
      sorted(e.name for e in hierarchy.descendants("place/copper-vale", WORLD))
      == ["The Peapod Pub", "Valeshire", "Valeshire Tavern"])
check("a leaf contains nothing", hierarchy.descendants("place/peapod-pub", WORLD) == [])

print("\n== the top of the world ==")
check("roots are the ones inside nothing",
      [e.name for e in hierarchy.roots(WORLD)] == ["Copper Vale", "Lorithal"])

print("\n== a parent that is not there ==")
# Deleted or renamed out from under the child. The page still has to render.
LOST = place("east-post", "East Post", "place/nowhere")
world2 = WORLD + [LOST]
check("no crash walking up from it",
      hierarchy.ancestors(LOST, hierarchy.index(world2)) == [])
check("it is reported as an orphan",
      [e.name for e in hierarchy.orphans(world2)] == ["East Post"])
check("and it still appears at the top level, so it can be found and fixed",
      "East Post" in [e.name for e in hierarchy.roots(world2)])

print("\n== loops ==")
# Nothing stops a hand-edited file from saying A is inside B is inside A, and
# every walker here would spin on it forever.
A = place("a", "A", "place/b")
B = place("b", "B", "place/a")
loop = hierarchy.index([A, B])
check("walking up a loop terminates", len(hierarchy.ancestors(A, loop)) <= 2)
check("listing a loop terminates", len(hierarchy.descendants("place/a", [A, B])) <= 2)
check("and so does the tree", len(hierarchy.tree([A, B])) <= 2)

check("a place cannot be put inside itself",
      hierarchy.would_cycle("place/valeshire", "place/valeshire", BY_REF))
check("nor inside its own child",
      hierarchy.would_cycle("place/valeshire", "place/peapod-pub", BY_REF),
      "Valeshire inside the pub that is inside Valeshire")
check("nor inside its own grandchild",
      hierarchy.would_cycle("place/copper-vale", "place/peapod-pub", BY_REF))
check("an ordinary move is fine",
      not hierarchy.would_cycle("place/peapod-pub", "place/lorithal", BY_REF))
check("clearing the parent is fine",
      not hierarchy.would_cycle("place/peapod-pub", "", BY_REF))

print("\n== the trail stops at a secret ==")
# The rule that fails silently. A page name is often the whole spoiler, so a
# reader who may not see a region must not learn it exists from a breadcrumb
# on a room they may see.
def person(key: str) -> Viewer:
    return Viewer.person(Person(key=key, name=key.title()))


SECRET = place("the-hollow-root", "The Hollow Root", "place/copper-vale",
               visible_to=["dm"])
CHAMBER = place("underground-chamber", "Underground Chamber",
                "place/the-hollow-root")
secret_world = [VALE, SECRET, CHAMBER]
secret_ref = hierarchy.index(secret_world)

dm, player = person("dm"), person("wren")

check("the DM sees the whole trail",
      [e.name for e in hierarchy.trail_for(CHAMBER, secret_ref, dm)]
      == ["Copper Vale", "The Hollow Root"])
check("a player sees none of it",
      hierarchy.trail_for(CHAMBER, secret_ref, player) == [],
      "not even Copper Vale: showing it says something is hidden in between")
check("the readable child is still readable",
      hierarchy.trail_for(CHAMBER, secret_ref, player) is not None)
check("an ordinary trail is unaffected",
      [e.name for e in hierarchy.trail_for(PUB, BY_REF, player)]
      == ["Copper Vale", "Valeshire"])
check("nobody signed in sees nothing secret",
      hierarchy.trail_for(CHAMBER, secret_ref, Viewer.nobody()) == [])

# The DM hid the region, not the world. Hiding a parent must not silently
# remove every room inside it from the people who were told about them.
check("hiding a parent does not hide the child",
      hierarchy.children("place/the-hollow-root", secret_world)[0].name
      == "Underground Chamber")

print("\n== the shape of it ==")
shape = hierarchy.tree(WORLD)
check("every place appears once", len(shape) == len(WORLD), str(len(shape)))
check("depth counts from the top",
      dict((e.name, d) for d, e in shape)["The Peapod Pub"] == 2)
check("roots are at zero", dict((e.name, d) for d, e in shape)["Copper Vale"] == 0)

print("\n== the field itself ==")
check("a bare slug is taken as a place",
      Entity(kind="place", slug="x", name="X", within="valeshire").within
      == "place/valeshire",
      "nobody types the prefix, and only places nest, so it is never ambiguous")
check("a full ref is left alone",
      Entity(kind="place", slug="x", name="X", within="place/valeshire").within
      == "place/valeshire")
check("it survives a round trip through the file",
      Entity.parse(
          Entity(kind="place", slug="x", name="X", within="place/valeshire").render(),
          kind="place", slug="x").within == "place/valeshire")
check("stray within in data is lifted out",
      Entity(kind="place", slug="x", name="X",
             data={"within": "place/valeshire"}).within == "place/valeshire")
check("and does not stay behind in data",
      "within" not in Entity(kind="place", slug="x", name="X",
                             data={"within": "place/valeshire"}).data)
print("\n== renaming the kind does not switch the hierarchy off ==")
# Nothing here compares against the string "place". Somebody renaming the kind
# to `location` through the Structure page would otherwise flatten the entire
# world without a single error, because every function would stop recognising
# its own data.
L_VALE = Entity(kind="location", slug="copper-vale", name="Copper Vale")
L_SHIRE = Entity(kind="location", slug="valeshire", name="Valeshire",
                 within="location/copper-vale")
renamed = [L_VALE, L_SHIRE]
check("children still found",
      [e.name for e in hierarchy.children("location/copper-vale", renamed)]
      == ["Valeshire"])
check("ancestors still walked",
      [e.name for e in hierarchy.ancestors(L_SHIRE, hierarchy.index(renamed))]
      == ["Copper Vale"])
check("and the tree still has a shape", len(hierarchy.tree(renamed)) == 2)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
