"""Seed the NPCs, factions and places from the DM's relationship graph.

Source: dm.serif_'s node graph posted 2025-11-06
(`Screenshot_2025-11-06_at_4.21.00_PM.png`). It is the DM's own map of who and
what connects to what, and it named a whole antagonist faction that appears
nowhere in the channel text.

Everything here is transcribed from node labels and the edges between them.
Where the graph gives a name and nothing else, the entity is a deliberate stub
tagged `needs-detail` rather than invented detail:

    python cli.py ls --tag needs-detail

Appearances are marked `needs-appearance` for the same reason. A name on a
graph tells you a character exists, not what they look like.

    python tools\\seed_relationships.py [--force]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

SRC = "discord:dnd-campaign:2025-11-06-relationship-graph"
STUB = ["from-lore", "needs-detail", "needs-appearance"]

# --- NPCs -----------------------------------------------------------------

NPCS = [
    dict(
        slug="elaric-the-blightwarden",
        name="Elaric the Blightwarden",
        summary="Connected both to the party and to the Hollow Root Covenant.",
        tags=["npc", "from-lore", "needs-appearance"],
        links=["faction/hollow-root-covenant", "character/kept", "character/sister-lethra"],
        body=(
            "One of the most connected figures on the DM's graph, sitting "
            "directly between the party and the Covenant. 'Blightwarden' and the "
            "Blighted Bog share a root, which is unlikely to be an accident."
        ),
    ),
    dict(
        slug="sister-lethra",
        name="Sister Lethra",
        summary="Linked to Elaric the Blightwarden, the Kept and the Hollow Root Covenant.",
        tags=["npc", "from-lore", "needs-appearance"],
        links=["faction/hollow-root-covenant", "character/kept"],
    ),
    dict(
        slug="kept",
        name="The Kept",
        summary="Linked to Sister Lethra, the Buried Star and the Hollow Root Covenant.",
        tags=["npc", "from-lore", "needs-detail", "needs-appearance"],
        links=["faction/hollow-root-covenant", "place/buried-star", "character/sister-lethra"],
        body="Whether this is a person, a group or a condition is not clear from the graph alone.",
    ),
    dict(
        slug="twigbeard",
        name="Twigbeard",
        summary="Linked to the Hollow Root Covenant. Namesake of Wren's lucky charm.",
        tags=["npc", "from-lore", "needs-appearance"],
        links=["faction/hollow-root-covenant", "item/twigbeards-lucky-beard-twig"],
        body=(
            "Wren carries Twigbeard's Lucky Beard Twig, so the party has met him "
            "or at least his beard. The graph places him with the Covenant."
        ),
    ),
    dict(
        slug="rooted-one",
        name="The Rooted One",
        summary="Linked to the Blighted Bog and the Underground Chamber.",
        tags=["npc", "from-lore", "needs-detail", "needs-appearance"],
        links=["place/blighted-bog", "place/underground-chamber"],
    ),
    dict(
        slug="maera-broadkettle",
        name="Maera Broadkettle",
        summary="Connects the Enchanter's Guild, the Underbelly Mercantile, Korran and the Peapod Public House.",
        tags=["npc", "from-lore", "needs-appearance"],
        links=[
            "place/enchanters-guild",
            "faction/underbelly-mercantile",
            "character/korran-mossborn",
            "place/peapod-pub",
        ],
        body="A hub on the graph: she touches both the guild and the pub, which makes her a likely broker or fixer.",
    ),
    dict(
        slug="barnaby-thistlewick",
        name="Barnaby Thistlewick",
        summary="Linked to the Enchanter's Guild.",
        tags=["npc", "from-lore", "needs-appearance"],
        links=["place/enchanters-guild"],
    ),
    dict(
        slug="buster",
        name="Buster",
        summary="Linked to Tavin and the Underbelly Mercantile.",
        tags=["npc", "from-lore", "needs-appearance"],
        links=["character/tavin", "faction/underbelly-mercantile"],
    ),
    dict(
        slug="tavin",
        name="Tavin",
        summary="Linked to Buster.",
        tags=["npc", "from-lore", "needs-appearance"],
        links=["character/buster"],
    ),
]

# --- Factions -------------------------------------------------------------

FACTIONS = [
    dict(
        slug="hollow-root-covenant",
        name="Hollow Root Covenant",
        summary="The campaign's antagonist faction, tying together Elaric, Sister Lethra, the Kept, Twigbeard and the Buried Star.",
        appearance="hollow twisted root sigil, black and sickly green heraldry, ring of thorns",
        tags=["faction", "antagonist", "from-lore"],
        links=[
            "character/elaric-the-blightwarden",
            "character/sister-lethra",
            "character/kept",
            "character/twigbeard",
            "place/buried-star",
            "character/mundus-decepi",
        ],
        body=(
            "The densest cluster on the DM's graph and the only one the party "
            "connects to through several different threads at once.\n\n"
            "Note the shape of it: hollow roots, a blighted bog, a Blightwarden, "
            "a Rooted One, an underground chamber. Copper Vale's water was "
            "poisoned by mining, and something under the ground appears to be "
            "answering. Mundus Decepi has his own edge to the Covenant, which is "
            "worth asking him about."
        ),
    ),
    dict(
        slug="underbelly-mercantile",
        name="Underbelly Mercantile",
        summary="A trading concern linking Buster, Tavin and Maera Broadkettle.",
        appearance="merchant guild mark, crossed keys over a coin, worn brass and deep red",
        tags=["faction", "from-lore"],
        links=["character/buster", "character/tavin", "character/maera-broadkettle"],
        body="Presumably connected to the Underbelly Safehouse, where the party found the map of Copper Vale.",
    ),
]

# --- Places ---------------------------------------------------------------

PLACES = [
    dict(
        slug="blighted-bog",
        name="Blighted Bog",
        summary="Bog linked to Brindlewood, the Underground Chamber and the Rooted One.",
        appearance="sickly wetland, black standing water, dead pale trees, creeping root mats",
        tags=["wilderness", "from-lore"],
        links=["place/brindlewood", "place/underground-chamber", "character/rooted-one"],
        body=(
            "Possibly the same water as the Shallow Bog on the regional map, "
            "under a name the party earned the hard way. A third name, Willow "
            "Bog, appears on the Brindlewood area map. Worth confirming whether "
            "these are one bog or three."
        ),
    ),
    dict(
        slug="underground-chamber",
        name="Underground Chamber",
        summary="Chamber below the Blighted Bog, linked to the party, the Rooted One and the Hollow Root Covenant.",
        appearance="root-choked underground chamber, wet stone, pale hanging tendrils, still black water",
        tags=["site", "from-lore"],
        links=["place/blighted-bog", "character/rooted-one", "faction/hollow-root-covenant"],
    ),
    dict(
        slug="buried-star",
        name="The Buried Star",
        summary="Linked to the Kept and the Hollow Root Covenant.",
        appearance="buried radiance under dark earth, cracked ground bleeding pale light",
        tags=["from-lore", "needs-detail"],
        links=["faction/hollow-root-covenant", "character/kept"],
        data={"map_type": "unknown"},
        body=(
            "Also mentioned once in the voice channel chat. Whether it is a "
            "place, an artifact or an event is unclear; filed as a place "
            "provisionally."
        ),
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="Overwrite instead of merging")
    args = ap.parse_args()

    cfg = config_mod.load()
    library = Library(cfg.content_dir)
    created = updated = 0

    def write(kind: str, spec: dict) -> None:
        nonlocal created, updated
        entity = Entity(
            kind=kind,
            slug=spec["slug"],
            name=spec["name"],
            summary=spec.get("summary", ""),
            appearance=spec.get("appearance", ""),
            tags=spec.get("tags", STUB),
            links=spec.get("links", []),
            sources=spec.get("sources", [SRC]),
            data=spec.get("data", {}),
            body=spec.get("body", ""),
        )
        if args.force:
            _, is_new = library.replace(entity)
        else:
            _, is_new = library.upsert(entity)
        created, updated = (created + 1, updated) if is_new else (created, updated + 1)

    for spec in NPCS:
        write("character", spec)
    for spec in FACTIONS:
        write("faction", spec)
    for spec in PLACES:
        write("place", spec)

    print(f"{created} created, {updated} updated -> {cfg.content_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
