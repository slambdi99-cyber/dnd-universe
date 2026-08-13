"""Seed the universe from the Copper Vale Discord lore.

Everything here was extracted from `dnd-scribe/lore/dnd-campaign/`, chiefly:

  * dm.serif_'s 2025-11-22 region write-up (ecology and settlements)
  * the hand-drawn regional map, Copper_Vale_Map_1.jpg
  * the Valeshire city map, Valeshire_Map.jpg
  * character level-up posts, which name each PC's class and Discord ID
  * Korran Mossborn's backstory post by Korran's player, 2025-10-11
  * the magic item inventory post, 2025-10-15

Re-running is safe. `Library.upsert` fills empty fields and merges lists but
never overwrites prose a human has written, so once you start editing these
pages by hand the seed stops touching them.

    python tools\\seed_copper_vale.py

`appearance` fields are what the art pipeline draws. Where the source material
described something, that description is used. Where it didn't (most of the
player characters), the appearance is a conservative guess built only from
class and known equipment, and is flagged in the entity's tags as
`needs-appearance` so you can find and fix them:

    python cli.py ls --tag needs-appearance
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

SRC_REGION = "discord:dnd-campaign:2025-11-22-region-writeup"
SRC_MAP = "discord:dnd-campaign:Copper_Vale_Map_1.jpg"
SRC_CITY = "discord:dnd-campaign:Valeshire_Map.jpg"
SRC_ART = "discord:dnd-campaign:copper-vale.png"
SRC_ITEMS = "discord:dnd-campaign:2025-10-15-magic-items"
SRC_LEVELS = "discord:dnd-campaign:2025-05-22-level-2"
SRC_KORRAN = "discord:dnd-campaign:2025-10-11-korran-backstory"

VALE = "place/copper-vale"

PLACES = [
    dict(
        slug="copper-vale",
        name="Copper Vale",
        summary="A low-lying region where scattered civilization clings to dwindling natural resources.",
        appearance="parched golden grassland, cracked dry earth, bare ruddy mountains, wide pale sky",
        tags=["region", "from-lore"],
        links=[
            "place/valeshire",
            "place/brindlewood",
            "place/copper-ridge",
            "place/dire-foothills",
            "place/shallow-bog",
        ],
        sources=[SRC_REGION, SRC_MAP, SRC_ART],
        data={"map_type": "region"},
        body=(
            "Mining at Copper Ridge has torn open sulfide-rich seams, and blasting in "
            "the Dire Foothills has fractured the watershed. Groundwater now bleeds "
            "into the mines instead of the plains, leaving Copper Vale to dry out.\n\n"
            "The abundance of exposed sulfide-rich copper produces highly acidic "
            "runoff, etching vivid streaks of green patina along the ruddy mountain "
            "cliffs of the Verdigris Teeth. With fresh water dwindling, the remaining "
            "lowlands stagnate, giving rise to the Shallow Bog.\n\n"
            "The through-line of the region is water: who has it, who took it, and "
            "what is left living in what remains."
        ),
    ),
    dict(
        slug="valeshire",
        name="Valeshire",
        summary="An established city with access to the single remaining river in the region.",
        appearance="walled river city on an island, stone bridges, tiled roofs, green water meadows",
        tags=["settlement", "city", "from-lore"],
        links=[VALE, "place/the-last-run"],
        sources=[SRC_REGION, SRC_MAP, SRC_CITY],
        data={"map_type": "settlement"},
        body=(
            "Built across islands in the Last Run, the only river still running in "
            "Copper Vale. Bridges connect the districts; the Enchanter's Guild keeps "
            "its own island to the west.\n\n"
            "Whoever holds Valeshire holds the region's water."
        ),
    ),
    dict(
        slug="brindlewood",
        name="Brindlewood",
        summary="A small crossroads township on the outskirts of the foothills.",
        appearance="small crossroads township, timber buildings and tents, dry scrub, foothills behind",
        tags=["settlement", "town", "from-lore"],
        links=[VALE, "place/dire-foothills"],
        sources=[SRC_REGION, SRC_MAP],
        data={"map_type": "settlement"},
        body=(
            "Where the road out of the Dire Foothills meets the way south. A place "
            "where secrets flow as freely as ale, per Korran Mossborn, who tends bar "
            "here and listens."
        ),
    ),
    dict(
        slug="copper-ridge",
        name="Copper Ridge",
        summary="The mining range whose torn-open seams started the region's collapse.",
        appearance="scarred mining mountains, open sulfide seams, spoil heaps, acid-stained rock",
        tags=["mountains", "from-lore"],
        links=[VALE, "place/verdigris-teeth"],
        sources=[SRC_REGION, SRC_MAP],
        data={"map_type": "range"},
        body="Mining here tore open sulfide-rich seams. The groundwater now drains into the workings instead of the plains.",
    ),
    dict(
        slug="verdigris-teeth",
        name="Verdigris Teeth",
        summary="Ruddy cliffs streaked vivid green by acidic runoff.",
        appearance="jagged red rock cliffs streaked with vivid green patina, sharp peaks, thin cold lakes",
        tags=["mountains", "landmark", "from-lore"],
        links=[VALE, "place/copper-ridge"],
        sources=[SRC_REGION, SRC_MAP],
        data={"map_type": "range"},
        body="The most visible symptom of the region's poisoning, and the reason the range is named for teeth.",
    ),
    dict(
        slug="dire-foothills",
        name="Dire Foothills",
        summary="Forested hills west of the vale, where blasting fractured the watershed.",
        appearance="dense pine foothills, blasted rock faces, fallen timber, low grey mist",
        tags=["wilderness", "from-lore"],
        links=[VALE, "place/brindlewood"],
        sources=[SRC_REGION, SRC_MAP],
        data={"map_type": "wilderness"},
    ),
    dict(
        slug="shallow-bog",
        name="Shallow Bog",
        summary="Stagnant wetland formed as the lowlands stopped draining.",
        appearance="stagnant shallow wetland, drowned scrub willows, still brown water, reed banks",
        tags=["wilderness", "from-lore"],
        links=[VALE],
        sources=[SRC_REGION, SRC_MAP],
        data={"map_type": "wilderness"},
        body="Not an old marsh. It is standing water with nowhere to go, and it appeared within living memory.",
    ),
    dict(
        slug="cutter-gulch",
        name="Cutter Gulch",
        summary="The dusty scar left where Cutter Creek used to run.",
        appearance="dry cracked riverbed, dust, bleached stones, sparse dead scrub",
        tags=["landmark", "from-lore"],
        links=[VALE, "place/cutter-creek"],
        sources=[SRC_REGION, SRC_MAP],
        data={"map_type": "landmark"},
        body="Once the artery of a thriving lumber trade. Now a dry channel across the south of the vale.",
    ),
    dict(
        slug="cutter-creek",
        name="Cutter Creek",
        summary="The vanished river that carried Copper Vale's lumber trade.",
        appearance="remembered river, timber rafts on fast green water, crowded log booms",
        tags=["historical", "river", "from-lore"],
        links=[VALE, "place/cutter-gulch"],
        sources=[SRC_REGION],
        data={"map_type": "river", "status": "gone"},
        body="Collapsed into Cutter Gulch when the watershed fractured. Kept as its own page because what it was matters to who lost it.",
    ),
    dict(
        slug="the-last-run",
        name="The Last Run",
        summary="The single river still flowing in Copper Vale.",
        appearance="wide slow river between green banks, the only living water in a dry land",
        tags=["river", "from-lore"],
        links=[VALE, "place/valeshire"],
        sources=[SRC_MAP],
        data={"map_type": "river"},
        body="Runs down out of the northeast mountains and past Valeshire. The name is not subtle and was presumably not meant to be.",
    ),
    dict(
        slug="peapod-pub",
        name="Peapod Pub",
        summary="The pub in Brindlewood where Korran Mossborn tends bar and listens.",
        appearance="low timber roadside pub, painted sign, lantern light in small windows, benches and a hitching rail outside",
        tags=["site", "from-lore"],
        links=[VALE, "place/brindlewood", "character/korran-mossborn"],
        sources=[SRC_KORRAN, SRC_MAP],
        data={"map_type": "site"},
        body=(
            "Marked 'PPP' on the regional map, beside the military encampment "
            "on Brindlewood's eastern edge. Where secrets flow as freely as ale."
        ),
    ),
    dict(
        slug="underbelly-safehouse",
        name="Underbelly Safehouse",
        summary="The safehouse where the party found the map of Copper Vale.",
        appearance="cramped hidden cellar room, crates and hanging lanterns, maps pinned to stone walls, low beams",
        tags=["site", "from-lore", "needs-appearance"],
        links=[VALE],
        sources=[SRC_MAP],
        data={"map_type": "site"},
        body=(
            "Named only in passing, as the place the regional map was recovered "
            "from on 2025-11-22. Location within Copper Vale is unrecorded."
        ),
    ),
    dict(
        slug="copperwash-pass",
        name="Copperwash Pass",
        summary="The pass through the northern mountains.",
        appearance="high narrow mountain pass, bare switchback trail, wind-scoured stone",
        tags=["landmark", "from-lore"],
        links=[VALE, "place/copper-ridge"],
        sources=[SRC_MAP],
        data={"map_type": "landmark"},
    ),
    dict(
        slug="rumbleshot-quarry",
        name="Rumbleshot Quarry",
        summary="A quarry west of the vale, off the edge of the regional map.",
        appearance="stepped stone quarry, blasting rubble, cut faces, dust haze",
        tags=["landmark", "from-lore", "off-map"],
        links=[VALE],
        sources=[SRC_MAP],
        data={"map_type": "landmark"},
        body="Marked with a directional arrow on the map rather than a location, so it lies somewhere west beyond the drawn edge.",
    ),
    dict(
        slug="arrowfell",
        name="Arrowfell",
        summary="Somewhere south-east beyond the mapped edge of Copper Vale.",
        appearance="unknown territory beyond the map edge",
        tags=["from-lore", "off-map", "needs-appearance"],
        links=[VALE],
        sources=[SRC_MAP],
        data={"map_type": "unknown"},
        body="Named only by a road arrow leaving the bottom-right of the regional map. Nothing else is known from the imported lore.",
    ),
]

# Locations inside Valeshire, from the city map.
VALESHIRE_SITES = [
    ("enchanters-guild", "Enchanter's Guild",
     "Arcane guild holding its own island west of the city.",
     "arcane guild hall on a river island, purple domed roofs, walled garden, standing stones"),
    ("sourstout-brewery", "Sourstout Brewery",
     "Brewery south of the river crossing.",
     "riverside brewery, barrels and vats in the yard, blue slate roof, hop fields behind"),
    ("pincushion-haberdashery", "Pincushion Haberdashery",
     "The city tailor, in the north-east district.",
     "narrow tailor's shopfront, bolts of cloth in the window, painted sign, cobbled street"),
    ("valeshire-cathedral", "Valeshire Cathedral",
     "The cathedral on the city's eastern edge.",
     "stone cathedral with steep blue roof, tall windows, riverside close, old trees"),
    ("valeshire-tavern", "The Valeshire Tavern",
     "The tavern at the western end of the island.",
     "busy stone-and-timber tavern, lantern light, benches outside, worn cobbles"),
    ("valeshire-inn", "The Valeshire Inn",
     "The inn on the island's southern row.",
     "two-storey timbered inn, red tile roof, stable yard, hanging sign"),
    ("valeshire-lumber-mill", "Valeshire Lumber Mill",
     "Mill on the north bank, working what timber still comes down.",
     "riverside lumber mill, log booms in the water, stacked timber, waterwheel"),
    ("valeshire-blacksmith", "Valeshire Blacksmith",
     "The smithy south of the river.",
     "open-fronted smithy, forge glow, anvil and racked tools, charcoal piles"),
    ("valeshire-carpenter", "Valeshire Carpenter",
     "Carpenter's workshop in the north of the island.",
     "carpenter's workshop, sawn planks stacked outside, shavings, timber frames"),
    ("valeshire-military-encampment", "Valeshire Military Encampment",
     "A standing camp on the south-east approach to the city.",
     "ordered military camp, canvas tents in rows, banners, palisade line, cook fires"),
]

for slug, name, summary, appearance in VALESHIRE_SITES:
    PLACES.append(
        dict(
            slug=slug,
            name=name,
            summary=summary,
            appearance=appearance,
            tags=["site", "valeshire", "from-lore"],
            links=["place/valeshire"],
            sources=[SRC_CITY],
            data={"map_type": "site"},
        )
    )

# Appearances below are transcribed from the character art each player posted,
# not invented. Note that they avoid D&D race words: SDXL has never heard of a
# tortle or a goliath and silently ignores them, which is how the first pass
# produced a human monk for Korran. Physique and colour, not jargon.
SRC_PORTRAITS = "discord:dnd-campaign:character-art-posts"
SRC_GRAPH = "discord:dnd-campaign:2025-11-06-relationship-graph"

CHARACTERS = [
    dict(
        slug="tobias-goreguts",
        name="Tobias Goreguts",
        summary="Half-orc barbarian. Reckless in a fight and not much calmer outside one.",
        appearance="huge half-orc warrior, green skin with darker green markings, jutting lower tusks, heavy brow, dark topknot, bare muscular arms, enormous greatsword",
        tags=["player-character", "barbarian", "half-orc", "from-lore"],
        links=[VALE, "item/bloodroot-greatsword"],
        sources=[SRC_LEVELS, SRC_ITEMS, SRC_PORTRAITS, SRC_GRAPH],
        data={"class": "Barbarian", "race": "Half-orc", },
        body="Fights with a greatsword and a javelin. Known for Reckless Attack, which is on-brand.",
    ),
    dict(
        slug="lucian-lovelyre",
        name="Lucian Lovelyre",
        summary="Half-elf bard. Carries the Bloomfang Rapier.",
        appearance="handsome half-elf man, tousled dark hair, pointed ears, glowing violet eyes, scarred cheek, warm ochre patterned tunic, lute",
        tags=["player-character", "bard", "half-elf", "from-lore"],
        links=[VALE, "item/bloomfang-rapier"],
        sources=[SRC_LEVELS, SRC_ITEMS, SRC_PORTRAITS],
        data={"class": "Bard", "race": "Half-elf", },
        body="Joined the party 2025-05-09.",
    ),
    dict(
        slug="eva-silverstream",
        name="Eva Silverstream",
        summary="Half-drow cleric of the Tempest domain and a devotee of Selune. The party's first character. No longer with the party.",
        appearance="pale lavender-skinned elf woman, long wavy white-blonde hair, violet-blue eyes, crescent moon mark on her brow, deep purple and gold robes, moonlight",
        tags=["former-party-member", "cleric", "half-drow", "from-lore"],
        links=[VALE, "deity/selune"],
        sources=[SRC_LEVELS, SRC_PORTRAITS],
        # Eva's player has no Discord ID on record: she doesn't post in either of the
        # imported channels, so the scribe can't label her speech yet.
        data={"class": "Cleric", "subclass": "Tempest Domain", "race": "Half-drow",
              "deity": "Selune", },
        body=(
            "The first character created for the campaign, on 2025-05-05. She "
            "has since left the party.\n\n"
            "Channel Divinity: Destructive Wrath. Was the party's practical "
            "healer, per the crafting discussion about healing potions.\n\n"
            "Kept as a page rather than deleted: she is on the DM's relationship "
            "graph and appears throughout the campaign's first year, so the "
            "history stops making sense without her."
        ),
    ),
    dict(
        slug="timothy-tuttle",
        name="Timothy Tuttle",
        summary="Tortle druid. All-natural vibes, per his introduction.",
        appearance="green scaled turtle-folk druid, domed shell on his back, round brass spectacles, antler circlet, brown leather tunic, circular wooden medallion, tall wooden staff",
        tags=["player-character", "druid", "tortle", "from-lore"],
        links=[VALE],
        sources=[SRC_LEVELS, SRC_PORTRAITS],
        data={"class": "Druid", "race": "Tortle", },
        body="Has turned into a giant frog and a giant wolf spider. Wren may have his staff.",
    ),
    dict(
        slug="mundus-decepi",
        name="Mundus Decepi",
        summary="Rogue, most likely of the Soulknife subclass. Dagger specialist.",
        appearance="lean figure in dark leathers, hood up, twin daggers, light crossbow on the back",
        tags=["player-character", "rogue", "from-lore", "needs-appearance"],
        links=[VALE, "item/rootbound-dagger", "faction/hollow-root-covenant"],
        sources=[SRC_LEVELS, SRC_ITEMS, SRC_GRAPH],
        data={"class": "Rogue", },
        body=(
            "An Avrae lookup for 'Rogue: Soulknife' appears in the channel, "
            "which given the party's class list is most likely his.\n\n"
            "On the DM's relationship graph he has his own edge to the Hollow "
            "Root Covenant, separate from the party's. Worth asking about."
        ),
    ),
    dict(
        slug="wren",
        name="Wren",
        summary="Spellcaster carrying Twigbeard's Lucky Beard Twig and Timothy's staff. Casts Speak With Dead.",
        appearance="young elf woman, short dark bob, pointed ears, dark green sleeveless tunic with lacing, hooded cloak, leather belt, arm wraps, tall wooden staff",
        tags=["player-character", "elf", "from-lore"],
        links=[VALE, "item/twigbeards-lucky-beard-twig", "character/timothy-tuttle"],
        sources=[SRC_ITEMS, SRC_PORTRAITS],
        data={},
        body=(
            "Class not recorded in the imported lore, but she casts Speak With "
            "Dead, so some flavour of caster.\n\n"
            "The art of her casting it shows her wielding a tall wooden staff in "
            "a candlelit bedroom, ringed by green skull-spirits, her eyes lit "
            "cyan by the spell. The staff is very likely Timothy's, which the DM "
            "asked about and which was never answered in the channel."
        ),
    ),
    dict(
        slug="korran-mossborn",
        name="Korran Mossborn",
        summary="Goliath monk of the Bogwatchers Sanctum, known as the Still Hand. Tends bar at the Peapod Pub.",
        appearance="enormous bald man with grey stone-mottled skin and darker vein markings, heavy muscular build, sleeveless olive and ochre monk wrap, brown sash, barefoot, tall wooden staff",
        tags=["player-character", "monk", "goliath", "from-lore"],
        links=[VALE, "place/brindlewood", "place/peapod-pub", "faction/bogwatchers-sanctum"],
        sources=[SRC_KORRAN, SRC_PORTRAITS],
        data={"class": "Monk", "race": "Goliath", "epithet": "the Still Hand"},
        body=(
            "Born not among his people's peaks but in the lowland marshes, after a "
            "rockslide swept his tribe away during a seasonal migration. Found as a "
            "child by a wandering hermit of the Bogwatchers Sanctum and raised in "
            "their hidden temple amid the mists and moss.\n\n"
            "His masters taught him to channel power without aggression, and to "
            "strike only when harmony was broken. He earned the name the Still Hand "
            "for staying calm when violence loomed.\n\n"
            "When the Sanctum's seers sensed corruption spreading in nearby towns, "
            "deforestation and poisoned waters and whispers of greed, Korran "
            "volunteered to go out. He took work as a bartender in Brindlewood to "
            "blend in, and listens from behind the counter for word of hunters, "
            "loggers and merchants who might threaten the balance.\n\n"
            "He drinks little and speaks less. Occasionally he disappears for a few "
            "days and returns with bruised knuckles and bog water on his robes. A "
            "quiet storm sits under the calm: the goliath urge to prove his worth "
            "against the monk's burden to preserve harmony."
        ),
    ),
    dict(
        slug="aelan-viremont",
        name="Aelan Viremont",
        summary="Name mentioned in party chat. Nothing else recorded.",
        appearance="",
        tags=["unresolved", "from-lore", "needs-appearance"],
        links=[VALE],
        sources=["discord:Party-Chat-voice"],
        data={},
        body="Appears once in the voice channel chat with no context. Left as a stub so the name isn't lost.",
    ),
]

FACTIONS = [
    dict(
        slug="bogwatchers-sanctum",
        name="Bogwatchers Sanctum",
        summary="An order of monks who hold that enlightenment comes only through deep connection with the living world.",
        appearance="moss and water motifs, still pond sigil, muted green and grey heraldry",
        tags=["order", "from-lore"],
        links=[VALE, "character/korran-mossborn"],
        sources=[SRC_KORRAN],
        data={},
        body=(
            "They keep a hidden temple amid mists and moss, and teach that every drop "
            "of water, every root and every whisper of wind carries a lesson.\n\n"
            "Their seers have sensed corruption spreading through the nearby towns: "
            "deforestation, poisoned waters, and greed. Given what mining at Copper "
            "Ridge has done to the region's water, the Sanctum's interests and the "
            "vale's collapse are the same story."
        ),
    ),
]

DEITIES = [
    dict(
        slug="selune",
        name="Selune",
        summary="Goddess of the moon. Eva Silverstream's patron.",
        appearance="moon goddess icon, silver crescent above a circle of seven stars, deep blue and silver",
        tags=["deity", "from-lore"],
        links=["character/eva-silverstream"],
        sources=[SRC_PORTRAITS],
        data={"domain": "Moon"},
        body=(
            "Named in Eva Silverstream's introduction on 2025-05-05, which "
            "describes her as a Selune devotee. The campaign also references the "
            "Forgotten Realms Mountains of Copper, so the wider setting is "
            "presumably the Realms."
        ),
    ),
]

ITEMS = [
    dict(
        slug="bloodroot-greatsword",
        name="Bloodroot Greatsword",
        summary="Tobias's greatsword.",
        appearance="heavy greatsword, dark root-veined blade, wrapped grip, red sap sheen",
        links=["character/tobias-goreguts"],
    ),
    dict(
        slug="bloomfang-rapier",
        name="Bloomfang Rapier",
        summary="Lucian Lovelyre's rapier.",
        appearance="slender rapier, blossom-etched guard, thorn-wound hilt, pale steel",
        links=["character/lucian-lovelyre"],
    ),
    dict(
        slug="rootbound-dagger",
        name="Rootbound Dagger",
        summary="Mundus's dagger.",
        appearance="short dagger bound in living root, dark iron blade, knotted wooden grip",
        links=["character/mundus-decepi"],
    ),
    dict(
        slug="twigbeards-lucky-beard-twig",
        name="Twigbeard's Lucky Beard Twig",
        summary="Wren's charm.",
        appearance="small gnarled twig charm on a leather cord, worn smooth, faintly green",
        links=["character/wren"],
    ),
]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing entities instead of merging into them. Use "
        "when the seed itself has been corrected: the normal merge protects "
        "whatever is already on disk, so a fixed description here would "
        "otherwise never reach a page that already has one.",
    )
    args = parser.parse_args()

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
            tags=spec.get("tags", []),
            links=spec.get("links", []),
            sources=spec.get("sources", []),
            data=spec.get("data", {}),
            body=spec.get("body", ""),
        )
        if args.force:
            _, is_new = library.replace(entity)
        else:
            _, is_new = library.upsert(entity)
        if is_new:
            created += 1
        else:
            updated += 1

    for spec in PLACES:
        write("place", spec)
    for spec in CHARACTERS:
        write("character", spec)
    for spec in FACTIONS:
        write("faction", spec)
    for spec in DEITIES:
        write("deity", spec)
    for spec in ITEMS:
        spec.setdefault("tags", ["magic-item", "from-lore"])
        spec.setdefault("sources", [SRC_ITEMS])
        write("item", spec)

    print(f"{created} created, {updated} updated -> {cfg.content_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

