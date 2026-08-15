"""Work out which place sits inside which, from what the table already wrote.

The hierarchy was being kept in tags before it was a field: 33 places tagged
`sub-location`, 26 `primary-location`, 18 carrying a bare `lorithal`, 10 a bare
`valeshire`. That is the hierarchy, written down informally, and this reads it.

    python tools\\infer_hierarchy.py            say what it would do
    python tools\\infer_hierarchy.py --write    do it

Three signals, strongest first. Each records how it was reached so the review
page can flag the guesses:

    tag      the place is tagged with another place's name or slug
    name     its slug starts with another place's slug, "valeshire-tavern"
    link     exactly one place links to it and it is marked as a sub-location

Anything else is left alone. A blank parent is a place at the top level, which
is a fair description of a page nobody has said anything about, and much easier
to spot and fix than a confident wrong answer.

It also clears up after itself, because two records of one fact will disagree
eventually: tags that only said where a place was are dropped, and a parent's
manual link to something that is now its child is dropped, since the page lists
its children on its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import config, hierarchy  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

# Said where a place was, and the field says it better. Anything describing
# what a place *is* survives: region, district, site, landmark, wilderness.
POSITION_TAGS = {"sub-location", "primary-location", "sublocation", "subsite"}

# How big a thing is, smaller number meaning it contains the others. The table
# already tags this way, so it is being read rather than imposed.
#
# It exists to fix a direction problem. "One place links to this one" says the
# two are related and nothing about which contains which, and taken alone it
# put The Hollow Root inside the Underground Chamber, and the whole of The
# Lowlands inside Arrowfell. Something can only be inside something bigger.
TIERS = {
    "realm": 0, "region": 0, "surroundings": 0, "wilderness": 0,
    "city": 1, "settlement": 1, "town": 1, "village": 1,
    "district": 2, "residential": 2, "commercial": 2, "industry": 2,
    "site": 3, "landmark": 3, "gate": 3, "green-space": 3, "monastic": 3,
    "lodging": 3, "student-housing": 3, "military": 3, "governance": 3,
}
UNKNOWN_TIER = 99


def tier_of(place: Entity) -> int:
    """The smallest tier any of its tags claims. Unknown sorts last."""
    found = [TIERS[t.strip().lower()] for t in place.tags
             if t.strip().lower() in TIERS]
    return min(found) if found else UNKNOWN_TIER


def infer(places: list[Entity]) -> dict[str, tuple[str, str]]:
    """slug -> (parent ref, how it was reached)."""
    by_slug = {p.slug: p for p in places}
    by_name = {p.name.lower(): p for p in places}
    found: dict[str, tuple[str, str]] = {}

    for place in places:
        if place.within:
            continue  # already set by hand; never second-guess it

        mine = tier_of(place)
        candidates: list[tuple[Entity, str]] = []

        # 1. Tagged with a parent's name or slug. Somebody typed it
        #    deliberately, which makes it the signal to trust.
        for tag in place.tags:
            key = tag.strip().lower()
            parent = by_slug.get(key) or by_name.get(key)
            if parent and parent.slug != place.slug:
                candidates.append((parent, "tag"))

        # 2. Named after the parent: valeshire-tavern, valeshire-blacksmith.
        #    Longest match wins, so "the-hollow-root-shrine" prefers
        #    "the-hollow-root" over "the".
        best = ""
        for slug in by_slug:
            if slug == place.slug:
                continue
            if place.slug.startswith(slug + "-") and len(slug) > len(best):
                best = slug
        if best:
            candidates.append((by_slug[best], "name"))

        # 3. Exactly one bigger place links to it. Two means guessing.
        #
        #    "Bigger" is the whole point. Without it this signal is
        #    directionless and cheerfully puts a region inside a landmark that
        #    happens to mention it.
        linked = [p for p in places
                  if p.slug != place.slug and place.ref in p.links
                  and tier_of(p) < mine]
        if len(linked) == 1:
            candidates.append((linked[0], "link"))

        if not candidates:
            continue

        # The smallest container wins, not the first signal found.
        #
        # Every building in Lorithal is tagged `lorithal`, so the tag alone
        # puts all eighteen directly under the realm and flattens the districts
        # that actually hold them. A university that is tagged `lorithal` and
        # linked from The Ashbright Stretch belongs to the Stretch: both are
        # true, and the narrower one is the more useful fact, because the realm
        # is still reachable by walking up.
        strength = {"tag": 0, "name": 1, "link": 2}
        parent, how = max(
            candidates,
            key=lambda c: (tier_of(c[0]) if tier_of(c[0]) != UNKNOWN_TIER else -1,
                           -strength[c[1]]),
        )
        found[place.slug] = (parent.ref, how)

    return found


def clean_tags(place: Entity, by_slug: dict[str, Entity],
               parent_ref: str) -> list[str]:
    """Drop tags that only said where this place was."""
    parent_slug = parent_ref.split("/", 1)[-1] if parent_ref else ""
    parent_name = by_slug[parent_slug].name.lower() if parent_slug in by_slug else ""
    kept = []
    for tag in place.tags:
        key = tag.strip().lower()
        if key in POSITION_TAGS:
            continue
        if parent_slug and key in (parent_slug, parent_name):
            continue
        kept.append(tag)
    return kept


def main() -> int:
    write = "--write" in sys.argv
    cfg = config.load(ROOT)
    library = Library(cfg.content_dir)
    places = [e for e in library.all(hierarchy.KIND)]
    by_slug = {p.slug: p for p in places}

    found = infer(places)

    # Refuse anything that would make a loop, checking against the shape the
    # run is building rather than the one on disk, or two places that name each
    # other both pass and the result is a cycle nothing can render.
    proposed = {p.ref: p for p in places}
    for slug, (parent, how) in sorted(found.items()):
        trial = Entity(kind="place", slug=slug, name=by_slug[slug].name,
                       within=parent)
        proposed[trial.ref] = trial
    for slug in sorted(found):
        ref = f"place/{slug}"
        if hierarchy.would_cycle(ref, found[slug][0], proposed):
            print(f"  refusing {slug}: would make a loop")
            proposed[ref] = by_slug[slug]
            del found[slug]

    by_how: dict[str, int] = {}
    for _, how in found.values():
        by_how[how] = by_how.get(how, 0) + 1

    print(f"\n{len(places)} places, {len(found)} given a parent")
    for how in ("tag", "name", "link"):
        if by_how.get(how):
            print(f"  {by_how[how]:3} by {how}")
    left = len(places) - len(found) - sum(1 for p in places if p.within)
    print(f"  {left:3} left at the top level")

    print("\nthe shape it would make:")
    shaped = [Entity(kind="place", slug=p.slug, name=p.name,
                     within=found.get(p.slug, (p.within, ""))[0])
              for p in places]
    for depth, place in hierarchy.tree(shaped):
        how = found.get(place.slug, ("", ""))[1]
        mark = f"   [{how}]" if how else ""
        print(f"  {'  ' * depth}{place.name}{mark}")

    if not write:
        print("\nNothing written. Run again with --write.")
        return 0

    changed = 0
    for place in places:
        parent, how = found.get(place.slug, ("", ""))
        fresh = library.load(place.kind, place.slug)
        # Tags are cleaned on every place, not only the ones that gained a
        # parent. `sub-location` and `primary-location` are now said by whether
        # a place has one, so leaving them on the roots would mean the same tag
        # meaning different things in different files, which is the drift this
        # was meant to end.
        cleaned = clean_tags(fresh, by_slug, parent)
        if not parent and cleaned == fresh.tags:
            continue
        fresh.within = parent or fresh.within
        fresh.tags = cleaned
        if parent:
            # How it was reached, so the review page can flag the guesses. Kept
            # in data rather than a tag: it is a note about this migration, not
            # something true of the place.
            fresh.data["within_inferred"] = how
            changed += 1
        library.save(fresh)

    # A parent's manual link to something that is now its child says the same
    # thing the page already shows. Done in a second pass, once every parent is
    # known, or a link would be judged against a half-built hierarchy.
    after = list(library.all(hierarchy.KIND))
    tidied = 0
    dropped = 0
    for place in after:
        # Both directions. A city's link down to its shop and the shop's link
        # back up to the city both say what the page now shows on its own, in
        # the children list and the breadcrumb.
        redundant = {c.ref for c in hierarchy.children(place.ref, after)}
        if place.within:
            redundant.add(place.within)
        # Duplicates too, while every link is being looked at anyway. Some
        # pages carry the same ref twice from earlier imports.
        keep = list(dict.fromkeys(l for l in place.links if l not in redundant))
        if keep != place.links:
            dropped += len(place.links) - len(keep)
            place.links = keep
            library.save(place)
            tidied += 1
    print(f"\nwrote {changed} place(s)")
    print(f"dropped {dropped} link(s) on {tidied} page(s), now shown as children")
    print("Review it at /wiki/places, and correct anything wrong by editing "
          "that place.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
