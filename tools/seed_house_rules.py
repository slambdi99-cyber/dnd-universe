"""Seed the table's own rules: The DM's rulings, and what supplements are in use.

Careful line here. The DM's Discord posts quote a lot of rulebook text around his
actual decisions, and that text isn't his to republish. What's captured is the
ruling itself, in his words, with the surrounding rules referenced rather than
reproduced. Anyone who needs the full rule has it on D&D Beyond already:
content sharing is enabled on the campaign.

Same reason the Dungeoneering supplement gets a page describing what it is and
who wrote it, rather than its contents.

    python tools\\seed_house_rules.py [--force]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

SRC_CRAFT = "discord:dnd-campaign:2025-05-08-crafting"
SRC_TABLE = "discord:dnd-campaign:2025-07-24-table-rules"
SRC_PDF = "discord:dnd-campaign:Dungeoneering_1.01.pdf"

PAGES = [
    dict(
        slug="house-rules",
        name="House Rules",
        summary="The DM's rulings for this table, where they differ from the book.",
        appearance="worn notebook page of handwritten table rules, ink, coffee ring",
        tags=["rules", "from-lore"],
        links=["lore/dungeoneering"],
        sources=[SRC_CRAFT, SRC_TABLE],
        body=(
            "## Crafting is five times faster\n\n"
            "The standard rule gives you 5 gp of progress per day of downtime, "
            "which makes a 50 gp potion a ten day job. The DM's ruling:\n\n"
            "> we could speed that to say, 25g per day of downtime. So you "
            "would need to be living in a town or city for 2 days, and spend "
            "half of its cost on raw materials.\n\n"
            "> 1 healing potion = 2 days of downtime + 25g\n\n"
            "So: **25 gp of progress per day**, you must be staying in a town "
            "or city, and raw materials cost half the item's market value.\n\n"
            "## Camera on earns inspiration\n\n"
            "> If you have your camera on, you will get an inspiration point "
            "for that session (D20 re-roll)\n\n"
            "## Roleplay is turn-based\n\n"
            "The DM directs conversation round the table rather than letting it "
            "free-for-all, so quieter players get the same airtime. His own "
            "example:\n\n"
            "> GM: NPC says such and such, Lucian, how do you respond?\n"
            "> Lucian: I draw my blade and say ...\n"
            "> GM: Mundus, you see this happening across the room. Do you react?\n\n"
            "This came out of a session-zero style discussion where Tobias Goreguts said "
            "the hard part was knowing when to listen and when to ask "
            "questions, and that he didn't want to take the spotlight from "
            "anyone.\n\n"
            "## Weapon masteries\n\n"
            "Melee characters get weapon mastery properties from level 1. You "
            "know **two at a time**, and can swap one by practising with a "
            "different weapon during a long rest.\n\n"
            "## Feats\n\n"
            "A feat at level 1, and another every few levels. The level 1 list "
            "The DM offered was: Alert, Crafter, Healer, Lucky, Magic Initiate, "
            "Musician, Savage Attacker, Skilled, Tavern Brawler, Tough.\n\n"
            "The full text of each is on D&D Beyond, which everyone has "
            "through The DM's content sharing.\n\n"
            "## Scheduling\n\n"
            "Sessions aim for 7:30 to 8pm Pacific, balancing people finishing "
            "work on the west coast against mountain-time players wanting an "
            "early night."
        ),
    ),
    dict(
        slug="dungeoneering",
        name="Dungeoneering",
        summary="Third-party supplement the table uses for dungeon crawls, by Magnus Fr.",
        appearance="slim rules supplement, dungeon cross-section diagram, muted print",
        tags=["rules", "supplement", "third-party", "from-lore"],
        links=["lore/house-rules"],
        sources=[SRC_PDF],
        data={"author": "Magnus Fr.", "version": "1.01",
              "srd_basis": "SRD 5.2.1 (CC BY 4.0)"},
        body=(
            "A supplement The DM shared on 2026-02-12 for running classic dungeon "
            "crawls in 5th Edition.\n\n"
            "What it covers, from its own contents page: exploring dungeons, "
            "**stretches**, 10-minute activities, wandering monsters, and a "
            "stretch tracking sheet. Its central idea is a second kind of "
            "round: combat stays on 6-second rounds, and crawling uses "
            "10-minute stretches. Before a crawl the GM collects the party's "
            "crawl strategy: marching order, default initiative, how they are "
            "handling visibility and light sources, and each character's "
            "passive perception.\n\n"
            "## Why there is no rules text here\n\n"
            "It is a commercial product, credited to Magnus Fr. as lead "
            "designer and marked all rights reserved, so its contents are not "
            "ours to republish. The PDF is in the Discord archive at "
            "`lore/dnd-campaign/attachments/`, and this page exists so the "
            "wiki records that the table uses it and roughly what it does."
        ),
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cfg = config_mod.load()
    library = Library(cfg.content_dir)
    created = updated = 0

    for spec in PAGES:
        entity = Entity(
            kind="lore",
            slug=spec["slug"],
            name=spec["name"],
            summary=spec["summary"],
            appearance=spec.get("appearance", ""),
            tags=spec.get("tags", []),
            links=spec.get("links", []),
            sources=spec.get("sources", []),
            data=spec.get("data", {}),
            body=spec["body"],
        )
        if args.force:
            _, is_new = library.replace(entity)
        else:
            _, is_new = library.upsert(entity)
        created, updated = (created + 1, updated) if is_new else (created, updated + 1)
        print(f"  {entity.name}")

    print(f"\n{created} created, {updated} updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
