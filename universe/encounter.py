"""What the table has encountered: places visited, people met, factions known.

One concept wearing a different verb per kind. A place is *visited*, a
character *met*, a faction *known*, an item *seen* -- but the question each
flag answers is the same one: has the party actually come across this yet?
Before this module the question was answered only for places (`visited`) and
only indirectly for everything else (`revealed_by` pointing at a place), so
"hide this NPC until the party meets them" had no first-class spelling.

The flag is tri-state on purpose:

  * **absent** -- the page was never tracked. It renders for everyone, which
    is how every page behaved before this concept existed, so nothing old
    changes meaning.
  * **False** -- the DM is holding the page back. It does not exist for
    anyone but the DM, exactly like a `visible_to` page for the wrong reader.
  * **True** -- the table has been there, met them, seen it. The page is
    public and its `:::visited` sections open.

Cascades ride the existing `revealed_by` field: a page that names sources is
carried along when any of them is encountered -- visit the shop and you have
met the shopkeeper. The cascade writes the derived `revealed` flag rather
than the target's own verb flag, so un-visiting the shop retracts exactly
what the visit granted and never erases a flag the DM set by hand. Cascades
deliberately do not chain: a page revealed by cascade is not itself a source,
because "visited the district" should not quietly mean "met everyone every
shop in it reveals". A DM who wants the chain marks the middle page directly.

Everything here is pure per-entity computation except `recompute`, which is
the single writer of the derived `revealed` flag, called whenever any verb
flag or `revealed_by` list moves.
"""

from __future__ import annotations

from .entities import Entity

# The verb each kind conjugates the concept with. Doubles as the data key in
# the page's frontmatter, so the DM hand-editing a file writes `met: false`
# on a character and `seen: true` on an item -- the file says what happened.
FLAGS = {
    "place": "visited",
    "character": "met",
    "faction": "known",
    "item": "seen",
    "creature": "encountered",
    "lore": "learned",
}
# Kinds without an entry (deities, sessions, anything added later) still get
# the concept; "known" reads acceptably for nearly anything.
DEFAULT_FLAG = "known"


def flag_key(kind: str) -> str:
    """The data key -- and the verb -- this kind tracks encounters under."""
    return FLAGS.get(kind, DEFAULT_FLAG)


def flag_of(entity: Entity) -> bool | None:
    """The page's own flag: True, False, or None when never tracked."""
    raw = entity.data.get(flag_key(entity.kind))
    return None if raw is None else bool(raw)


def mark(entity: Entity, value: bool | None) -> None:
    """Set the page's flag, or clear it back to untracked with None.

    Cleared rather than written False so the metadata table doesn't carry a
    "met: False" row on every page nobody ever hid.
    """
    if value is None:
        entity.data.pop(flag_key(entity.kind), None)
    else:
        entity.data[flag_key(entity.kind)] = bool(value)


def sources_of(entity: Entity) -> frozenset[str]:
    """The pages whose encounter carries this one with it, or empty.

    `revealed_by` in a page's data names sources as 'kind/slug'; a bare slug
    is taken as a place, which is what it always meant before characters and
    factions could be sources too.
    """
    raw = entity.data.get("revealed_by")
    if not raw:
        return frozenset()
    if isinstance(raw, str):
        raw = [raw]
    refs = set()
    for r in raw:
        r = str(r).strip().lower()
        if r:
            refs.add(r if "/" in r else f"place/{r}")
    return frozenset(refs)


def encountered(entity: Entity) -> bool:
    """Has the party come across this page -- by its own flag or by cascade?"""
    if flag_of(entity):
        return True
    return bool(entity.data.get("revealed"))


def tracked(entity: Entity) -> bool:
    """Does this page participate in the concept at all?"""
    return flag_of(entity) is not None or bool(sources_of(entity))


def concealed(entity: Entity) -> bool:
    """Tracked but not yet encountered: the page is the DM's alone."""
    return tracked(entity) and not encountered(entity)


def recompute(library) -> list[str]:
    """Bring every cascade target's `revealed` flag in line with the flags.

    The sources that count are pages whose own verb flag is True -- derived
    reveals do not propagate (see the module note on chaining). The flag is
    derived state written to disk so `encountered` can stay a pure per-entity
    check; this function is the single place that derives it. Returns the
    refs whose visibility just changed.
    """
    flagged = {e.ref for e in library.all() if flag_of(e)}
    changed = []
    for entity in list(library.all()):
        req = sources_of(entity)
        if not req:
            continue
        want = bool(req & flagged)
        have = bool(entity.data.get("revealed"))
        if want == have:
            continue
        if want:
            entity.data["revealed"] = True
        else:
            entity.data.pop("revealed", None)
        library.save(entity)
        changed.append(entity.ref)
    return changed
