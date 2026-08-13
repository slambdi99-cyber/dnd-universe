"""Seed from the DM's own wiki pages.

Source: wiki entries supplied directly by the table (Obsidian-style, with
[[wikilinks]]). This is the most authoritative source in the project: it
supersedes the relationship graph, the session log, and anything I inferred
from images, because it is the DM writing the world down deliberately.

Where this contradicts an earlier seed, this wins.

    python tools\\seed_wiki.py [--force]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

SRC = "dm-wiki"
VALE = "place/copper-vale"

NEW = [
    # -- places ------------------------------------------------------------
    ("place", dict(
        slug="bogwatchers-sanctum-temple",
        name="Bogwatchers' Sanctum",
        summary="The hidden temple of the Bogwatchers, and a notable location of Copper Vale.",
        appearance="hidden temple among mists and moss, low mossy stone halls, still pools, drooping trees",
        tags=["site", "from-wiki"],
        links=[VALE, "faction/bogwatchers-sanctum", "character/korran-mossborn"],
        data={"map_type": "site"},
        body=(
            "Listed by the DM among Copper Vale's notable locations, so the "
            "Sanctum is a place on the map as well as an order of monks. This "
            "page is the building; `faction/bogwatchers-sanctum` is the order."
        ),
    )),
    ("place", dict(
        slug="goreguts-village",
        name="Tobias Goreguts' Village",
        summary="Tobias's home village, on Cutter Creek before it ran dry.",
        appearance="abandoned riverside village, dry channel where the water was, empty timber houses, dust",
        tags=["settlement", "from-wiki", "needs-detail"],
        links=[VALE, "place/cutter-creek", "character/tobias-goreguts"],
        data={"map_type": "settlement"},
        body=(
            "The DM's page for Cutter Creek lists this village as its notable "
            "location, in the period before the creek ran dry.\n\n"
            "Tobias's mother died in a goblin attack, and he presses flowers "
            "because of her last words. Whether that happened here is not "
            "recorded."
        ),
    )),
    ("place", dict(
        slug="the-hollow-root",
        name="The Hollow Root",
        summary="What the Underground Chamber beneath the Shallow Bog led the party to discover.",
        appearance="vast hollow root cavity, walls of dead pale wood, deep dark hollow",
        tags=["site", "from-wiki", "needs-detail"],
        links=["place/underground-chamber", "faction/hollow-root-covenant"],
        data={"map_type": "site"},
        body=(
            "Named as the discovery the chamber led to. Distinct from the "
            "Hollow Root Covenant, which presumably takes its name from this."
        ),
    )),
    # -- items -------------------------------------------------------------
    ("item", dict(
        slug="misenchanted-lavender-mead",
        name="Misenchanted Lavender Mead",
        summary="Maera Broadkettle's attempt at a night of unforgettable euphoria. It gave the original party near-total amnesia.",
        appearance="tall glass of pale lavender mead, faint shimmer, sprig of dried flower, tavern lamplight",
        tags=["item", "plot-critical", "from-wiki"],
        links=["character/maera-broadkettle", "place/peapod-pub",
               "place/enchanters-guild", "character/tobias-goreguts",
               "character/lucian-lovelyre", "character/timothy-tuttle",
               "character/eva-silverstream", "character/mundus-decepi"],
        data={"ingredients": ["Hearthsalt", "Joyroot tincture", "Sunpetal Honey",
                              "Laughter Resin", "Memory Lace"]},
        body=(
            "This is the answer to the party's amnesia.\n\n"
            "Brewed by Maera Broadkettle at the Peapod Public House. It caused "
            "near-total memory loss in Tobias Goreguts, Lucian Lovelyre, "
            "Timothy Tuttle, Eva Silverstream and Mundus Decepi, who were "
            "extremely intoxicated at the time, and landed Maera in legal "
            "trouble.\n\n"
            "## The recipe notes\n\n"
            "Found in her desk with a handful of dirtied glass vessels, half a "
            "page of shorthand:\n\n"
            "- 1/1 Hearthsalt / Joyroot tincture. Euphoric, perhaps too dazed.\n"
            "- 1/2 Hearthsalt / Sunpetal Honey. Intense focus, jittery edge.\n"
            "- 1/3 Laughter Resin / Sunpetal Honey. Heavenly high, hellish comedown.\n"
            "- 1/4 Still recovering from previous test.\n"
            "- 1/5 Laughter Resin / Memory Lace. Dare I say a success.\n"
            "- 1/6 Laughter Resin / Memory Lace. A success indeed.\n\n"
            "## The Guild's assessment\n\n"
            "The Enchanters' Guild of Valeshire wrote to her:\n\n"
            "> This appears to be enchanted with a weak magical effect to "
            "obscure memories. However, due to the imprecise nature of this "
            "enchantment, it's possible that a novice magician was attempting "
            "to invoke the opposite effect. Please note that enchanting food or "
            "drink without consent is a serious violation of our magical "
            "policies. We require that you disclose the identity of anyone "
            "suspected to practice these forbidden enchantments.\n\n"
            "Her unfinished reply, also on the desk:\n\n"
            "> Thank you for your assessment. We are confident that we know who "
            "the culprit is, and we are taking action to ensure that they may "
            "never return to this establishment.\n\n"
            "Note what the Guild is really saying: someone may have been trying "
            "to do the opposite, meaning restore memory rather than obscure it. "
            "And Maera's reply names no one."
        ),
    )),
    ("lore", dict(
        slug="twigball",
        name="Twigball",
        summary="A dice game everyone knows and everyone wants to play. The goal is to get the biggest numba.",
        appearance="tavern table, scattered dice, stakes of acorns and pinecones, lamplight",
        tags=["game", "from-wiki"],
        links=["character/twigbeard", "place/pixie-pint-glass"],
        data={"dice": ["d8", "d6", "d4"]},
        body=(
            "Requires a d8, a d6, and one or more d4s.\n\n"
            "1. Players ante, then roll their d8.\n"
            "2. Players call or raise the bet, then roll their d6.\n"
            "3. Players call or raise the bet, then roll their d4.\n"
            "4. Roll an additional d4 for each pair among the initial d4/d6/d8 rolls.\n"
            "5. The highest total sum wins.\n\n"
            "Tobias went all in against Twigbeard with one pinecone and ten "
            "acorns and lost everything, then lost Wren's acorns too. Wren later "
            "got rich at a Twigball competition in the Pixie Pint Glass."
        ),
    )),
]

UPDATES = [
    ("place", "copper-vale", dict(
        links=["place/brindlewood", "place/valeshire", "place/shallow-bog",
               "place/bogwatchers-sanctum-temple", "place/cutter-gulch",
               "place/copper-ridge", "place/dire-foothills"],
    )),
    ("place", "cutter-creek", dict(
        summary="The vanished river that carried Copper Vale's lumber trade. Tobias Goreguts' village stood on it.",
        links=[VALE, "place/cutter-gulch", "place/goreguts-village"],
    )),
    ("place", "brindlewood", dict(
        links=[VALE, "place/dire-foothills", "place/peapod-pub", "place/shallow-bog"],
    )),
    ("place", "peapod-pub", dict(
        name="Peapod Public House",
        summary="The public house in Brindlewood where Korran Mossborn tends bar, and where the Misenchanted Lavender Mead was served.",
        links=[VALE, "place/brindlewood", "character/korran-mossborn",
               "character/maera-broadkettle", "item/misenchanted-lavender-mead"],
        data={"map_type": "site", "aka": ["Peapod Pub", "PPP"]},
        body=(
            "Marked 'PPP' on the regional map, beside the military encampment "
            "on Brindlewood's eastern edge. Where secrets flow as freely as "
            "ale.\n\n"
            "Maera Broadkettle served the Misenchanted Lavender Mead here, which "
            "is how the original party lost their memories."
        ),
    )),
    ("place", "rumbleshot-quarry", dict(
        summary="Mining operation in the Dire Foothills of Copper Ridge. It ultimately benefits the Underbelly Mercantile.",
        tags=["landmark", "from-wiki", "from-session-log"],
        links=[VALE, "place/dire-foothills", "place/copper-ridge",
               "faction/underbelly-mercantile", "character/foreman-rumbleshot",
               "character/gollub", "place/the-drowned-amphitheater"],
        body=(
            "The DM's wiki places it in the Dire Foothills of Copper Ridge, and "
            "states plainly who profits: the Underbelly Mercantile.\n\n"
            "Mining rich copper, with deposits that gleam like fire and exposed "
            "copper visible in a waterfall. Goblins and kobolds serving Gollub "
            "planned to burn the camp down; the party stopped it. Tobias pulled "
            "civilians from a burning house, and he and Korran broke down the "
            "burning gate.\n\n"
            "Below it lies a kobold warren, an elevator, and Gollub."
        ),
    )),
    ("place", "underground-chamber", dict(
        summary="Chamber beneath the Shallow Bog holding a ritual altar and a hoard of ancient weapons. It led the party to the Hollow Root.",
        appearance="chamber packed with thick gnarled roots, stone ritual altar, racks of ancient weapons, a throne",
        tags=["site", "plot-critical", "from-wiki"],
        links=["place/shallow-bog", "place/the-hollow-root", "character/rooted-one",
               "character/elaric-the-blightwarden", "character/barnaby-thistlewick",
               "item/bloodroot-greatsword", "item/bloomfang-rapier",
               "item/rootbound-dagger"],
        body=(
            "## Discovery\n\n"
            "At a circular clearing in the bog, near a perfectly round puddle, "
            "Barnaby Thistlewick identified a magical inscription on the bark of "
            "a tree:\n\n"
            "> Looking down toward the skies\n"
            "> A passage lies for open eyes\n\n"
            "Noticing that the surface of the water reflected the sky, Lucian "
            "took his clothes off and lay face-down in the puddle. When he "
            "opened his eyes, a passageway was revealed beneath the surface.\n\n"
            "## Contents\n\n"
            "Thick gnarled roots from the trees above the bog. A ritual altar "
            "and a great many ancient weapons. The Rooted One was seated on a "
            "throne nearby.\n\n"
            "Touching more than one piece of equipment at a time inflicts "
            "psychic damage. Once a weapon makes contact with the wielder's "
            "blood it unlocks additional benefits through attunement, and the "
            "items seem vaguely bloodthirsty once that psychic connection "
            "forms.\n\n"
            "The cobbled rear wall was illusory. As the party stepped through, "
            "Elaric sealed it behind them, before Eva and Barnaby could follow."
        ),
    )),
    ("character", "maera-broadkettle", dict(
        summary="Brewer at the Peapod Public House. Her Misenchanted Lavender Mead wiped the original party's memories.",
        appearance="tavern brewer, sleeves rolled, apron stained lavender, sharp practical manner",
        tags=["npc", "from-wiki", "from-lore"],
        links=["place/peapod-pub", "item/misenchanted-lavender-mead",
               "place/enchanters-guild", "faction/underbelly-mercantile",
               "character/korran-mossborn"],
        body=(
            "She set out to create a night of unforgettable euphoria and "
            "produced the opposite, inflicting near-total amnesia on Tobias, "
            "Lucian, Timothy, Eva and Mundus, and landing herself in legal "
            "trouble with the Enchanters' Guild of Valeshire.\n\n"
            "Her desk held the dirtied test vessels, her shorthand recipe notes, "
            "the Guild's assessment letter, and an unfinished reply claiming she "
            "knew who the culprit was. She named no one."
        ),
    )),
    ("item", "bloodroot-greatsword", dict(
        summary="Tobias Goreguts' greatsword, taken from the ritual chamber beneath the Shallow Bog.",
        links=["character/tobias-goreguts", "place/underground-chamber"],
        body=(
            "One of the ancient weapons from the Underground Chamber. Attuned "
            "through contact with the wielder's blood, and vaguely bloodthirsty "
            "once the psychic connection forms."
        ),
    )),
    ("item", "bloomfang-rapier", dict(
        summary="Lucian Lovelyre's rapier, taken from the ritual chamber beneath the Shallow Bog.",
        links=["character/lucian-lovelyre", "place/underground-chamber"],
        body="One of the ancient weapons from the Underground Chamber. Its bearer is dead.",
    )),
    ("item", "rootbound-dagger", dict(
        summary="Mundus Decepi's dagger, taken from the ritual chamber beneath the Shallow Bog.",
        links=["character/mundus-decepi", "place/underground-chamber"],
        body="One of the ancient weapons from the Underground Chamber, attuned through blood.",
    )),
    ("place", "shallow-bog", dict(
        links=[VALE, "place/brindlewood", "place/underground-chamber"],
        body=(
            "Not an old marsh. It is standing water with nowhere to go, and it "
            "appeared within living memory.\n\n"
            "The Underground Chamber lies beneath it, reached through a "
            "perfectly round puddle in a circular clearing.\n\n"
            "The DM's wiki places the chamber under the Shallow Bog, which "
            "strongly suggests the Blighted Bog of the relationship graph is "
            "this same water under a later name. Not merged yet, pending "
            "confirmation."
        ),
    )),
    ("character", "barnaby-thistlewick", dict(
        summary="Identified the inscription that revealed the passage beneath the Shallow Bog. Sealed out of the chamber by Elaric.",
        appearance="fussy scholarly figure, spectacles, ink-stained fingers, travelling coat",
        tags=["npc", "from-wiki", "from-lore"],
        links=["place/enchanters-guild", "place/underground-chamber",
               "character/elaric-the-blightwarden"],
        body=(
            "Read the magical inscription on the tree bark at the circular "
            "clearing. He and Eva were shut out when Elaric sealed the illusory "
            "wall behind the party."
        ),
    )),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cfg = config_mod.load()
    library = Library(cfg.content_dir)
    created = updated = patched = missing = 0

    for kind, spec in NEW:
        entity = Entity(
            kind=kind,
            slug=spec["slug"],
            name=spec["name"],
            summary=spec.get("summary", ""),
            appearance=spec.get("appearance", ""),
            tags=spec.get("tags", ["from-wiki"]),
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

    # The DM's wiki outranks everything else, so corrections overwrite.
    for kind, slug, fields in UPDATES:
        entity = library.load(kind, slug)
        if entity is None:
            print(f"  skip: {kind}/{slug} not found", file=sys.stderr)
            missing += 1
            continue
        for key, value in fields.items():
            setattr(entity, key, value)
        if SRC not in entity.sources:
            entity.sources.append(SRC)
        library.save(entity)
        patched += 1

    print(
        f"{created} created, {updated} updated, {patched} corrected"
        + (f", {missing} missing" if missing else "")
        + f" -> {cfg.content_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
