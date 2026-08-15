"""Places inside places.

Copper Vale contains Valeshire, which contains the Peapod Pub. The table had
been saying that with tags -- `sub-location`, `primary-location`, and a bare
`valeshire` on everything in Valeshire -- which worked until two of them
disagreed and nothing noticed.

A place records its one parent in `within`. That is the only stored fact. What
a place *contains* is worked out here by looking at everything, which is why a
district cannot end up inside two cities, and why moving one is a single line
changed in a single file.

Two things this module exists to get right, both of which fail quietly:

**Secrets.** A trail of ancestors is a list of page names, and a name is often
the whole spoiler. `trail_for` stops at the first ancestor the reader may not
see and shows nothing above it, matching the rest of the wiki, where a page you
cannot read is indistinguishable from one that does not exist. A hidden parent
does not hide its visible children: the DM hid the parent, not the world.

**Loops.** Nothing stops someone writing A inside B inside A, and every walker
here would spin forever on it. Rather than defend in each one, `parent_of`
refuses to complete a cycle and `would_cycle` lets a writer check before saving.
"""

from __future__ import annotations

from typing import Iterable

from .access import Viewer, readable
from .entities import Entity

# The kind that nests, as shipped. Only places do: `within` means "is part of",
# and letting a faction sit inside a place would quietly make it mean "is
# located at" too.
#
# It is a default, not a rule. Nothing below compares against it, because the
# kind is renameable -- somebody calling places `location` instead would
# otherwise flatten the entire hierarchy without an error, since every function
# here would stop recognising its own data. What actually nests is "a page with
# `within` set", and what it may nest inside is enforced where writes happen.
KIND = "place"

# A cycle should be impossible, since writes refuse to make one. This is the
# backstop for a file hand-edited into a loop, which is a normal thing to do to
# a git repo full of markdown.
MAX_DEPTH = 24


def parent_ref(entity: Entity) -> str:
    """What this page says it is inside, or empty."""
    return entity.within if entity else ""


def index(entities: Iterable[Entity]) -> dict[str, Entity]:
    return {e.ref: e for e in entities}


def ancestors(entity: Entity, by_ref: dict[str, Entity]) -> list[Entity]:
    """Outermost first: [Copper Vale, Valeshire] for the Peapod Pub.

    Stops at a missing parent rather than raising. A page can name a parent that
    was deleted or renamed out from under it, and a broken trail is a much
    better outcome than a page that will not render.
    """
    out: list[Entity] = []
    seen = {entity.ref}
    current = parent_ref(entity)
    while current and len(out) < MAX_DEPTH:
        if current in seen:
            break  # a loop; stop rather than spin
        parent = by_ref.get(current)
        if parent is None:
            break
        out.append(parent)
        seen.add(current)
        current = parent_ref(parent)
    out.reverse()
    return out


def children(ref: str, entities: Iterable[Entity]) -> list[Entity]:
    """Places directly inside this one, alphabetically.

    Direct only. A city lists its districts, not every shop in every district,
    because the districts list those themselves and a city with sixty entries
    under it is not an index of anything.
    """
    return sorted(
        (e for e in entities if e.within == ref),
        key=lambda e: e.name.lower(),
    )


def descendants(ref: str, entities: Iterable[Entity]) -> list[Entity]:
    """Everything inside this one, at any depth. Used before deleting."""
    everything = list(entities)
    out: list[Entity] = []
    frontier = [ref]
    seen = {ref}
    while frontier and len(out) < 500:
        nxt: list[str] = []
        for parent in frontier:
            for child in children(parent, everything):
                if child.ref in seen:
                    continue
                seen.add(child.ref)
                out.append(child)
                nxt.append(child.ref)
        frontier = nxt
    return out


def would_cycle(ref: str, new_parent: str, by_ref: dict[str, Entity]) -> bool:
    """Would putting `ref` inside `new_parent` make a loop?

    True if the proposed parent is the page itself, or sits anywhere inside it.
    Callers refuse on True; nothing here writes.
    """
    if not new_parent:
        return False
    if new_parent == ref:
        return True
    current = new_parent
    seen = set()
    for _ in range(MAX_DEPTH):
        if current == ref:
            return True
        if not current or current in seen:
            return False
        seen.add(current)
        parent = by_ref.get(current)
        if parent is None:
            return False
        current = parent_ref(parent)
    return False


def trail_for(entity: Entity, by_ref: dict[str, Entity],
              viewer: Viewer) -> list[Entity]:
    """The ancestors this viewer may see, outermost first.

    Cut at the first one they may not, counting from the page outwards, so a
    secret region hides everything above it as well as itself. Returning the
    readable ones from higher up would be worse than showing nothing: it would
    say "there is something here you are not allowed to know about", which is
    the shape of the secret.
    """
    chain = ancestors(entity, by_ref)
    visible: list[Entity] = []
    for place in reversed(chain):
        if not readable(place, viewer):
            break
        visible.append(place)
    visible.reverse()
    return visible


def orphans(entities: Iterable[Entity]) -> list[Entity]:
    """Places naming a parent that is not there, for the review page."""
    everything = list(entities)
    known = {e.ref for e in everything}
    return [e for e in everything if e.within and e.within not in known]


def roots(entities: Iterable[Entity]) -> list[Entity]:
    """Top-level places, alphabetically. Anything with a broken parent counts.

    A place pointing at a parent that no longer exists has to appear somewhere,
    or correcting it means knowing it exists first.
    """
    everything = list(entities)
    known = {e.ref for e in everything}
    return sorted(
        (e for e in everything if not e.within or e.within not in known),
        key=lambda e: e.name.lower(),
    )


def tree(entities: Iterable[Entity]) -> list[tuple[int, Entity]]:
    """Every place as (depth, entity), depth-first, for listing.

    Not used by the Places index, which stays flat on purpose. This is for the
    review page and for anything that wants to show the shape at a glance.
    """
    everything = list(entities)
    out: list[tuple[int, Entity]] = []

    def walk(node: Entity, depth: int, seen: set[str]) -> None:
        if node.ref in seen or depth > MAX_DEPTH:
            return
        seen.add(node.ref)
        out.append((depth, node))
        for child in children(node.ref, everything):
            walk(child, depth + 1, seen)

    seen: set[str] = set()
    for root in roots(everything):
        walk(root, 0, seen)
    return out
