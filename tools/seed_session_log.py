"""Seed entities from Tobias Goreguts' session log, "The Buried Star".

Source: `dnd-scribe/lore/session-notes/the-buried-star-tobias-log.txt`, a
running log kept from Tobias's point of view, roughly 2025-10 to 2026-08.

Read the caveat before trusting any of this. These are one player's rough
in-session notes: abbreviated, occasionally contradictory, with names spelled
several ways (Shameous/Seamus, Kasbor/Kasboar, Gollub, Goltheas/Gotheus,
Laurelthel/Laurelfell/Laurefall). Where a name varies I've picked the most
frequent spelling and recorded the alternatives in `data.aka`. Anything the
log leaves genuinely unclear is tagged `needs-detail` rather than guessed at.

    python tools\\seed_session_log.py [--force]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

SRC = "session-log:the-buried-star-tobias-log.txt"
COVENANT = "faction/hollow-root-covenant"

NPCS = [
    dict(
        slug="gollub",
        name="Gollub",
        summary="An aboleth. The mastermind behind the goblin and kobold threat to Rumbleshot Quarry.",
        appearance="ancient aboleth, vast eel-like body, three eyes, trailing tentacles, pale slick hide, black underground lake",
        tags=["npc", "antagonist", "creature", "from-session-log"],
        links=["place/rumbleshot-quarry", "place/the-drowned-amphitheater"],
        data={"creature": "Aboleth"},
        body=(
            "Named as an evil mastermind well before the party saw him. Kobolds "
            "represented him with a doll. Kasbor resisted him and helped the "
            "party.\n\n"
            "Found at the bottom of an elevator beneath the kobold warren, in a "
            "huge cavern like an amphitheater around an underground lake.\n\n"
            "Open question from the log: are Gollub and the vampires connected?"
        ),
    ),
    dict(
        slug="myra",
        name="Myra",
        summary="Owner of the inn. Dealt with the Underbelly Mercantile to keep it afloat.",
        appearance="innkeeper, middle-aged, apron, guarded expression",
        tags=["npc", "from-session-log"],
        links=["faction/underbelly-mercantile", "place/enchanters-guild"],
        body=(
            "Her inn was failing. She cut a deal with the Underbelly Mercantile "
            "to profit off the military presence in town, and ended up selling "
            "drugged product for them. The log says the resulting harm was an "
            "accident of the concoction, but that she was the cause of it.\n\n"
            "She was due to be arrested by the Enchanter's Guild, wanted out of "
            "the deal, and later screamed as Elaric killed Lucian."
        ),
    ),
    dict(
        slug="warwick",
        name="Warwick",
        summary="A halfling. Wanted the mining company garrisoned rather than evacuated. Now a business partner of the party.",
        appearance="halfling businessman, well-tailored waistcoat, sharp eyes, neat side-whiskers",
        tags=["npc", "ally", "from-session-log"],
        links=["place/rumbleshot-quarry"],
        body=(
            "Opposed Seamus, who wanted the miners evacuated. The party sided "
            "with Seamus first and failed, then went over to Warwick.\n\n"
            "He likes them and treats them as business partners. They threw a "
            "party for his colleagues on 2026-05-13."
        ),
    ),
    dict(
        slug="seamus",
        name="Seamus",
        summary="A dwarf quest-giver who wanted the mining company evacuated. Later killed by the party.",
        appearance="dwarf foreman, heavy beard, mining leathers, soot-stained hands",
        tags=["npc", "deceased", "from-session-log"],
        links=["place/rumbleshot-quarry", "character/melda"],
        data={"aka": ["Shameous"]},
        body=(
            "Gave the party the quarry job. They eventually killed him, and "
            "recovered a secret letter from Melda signed with an E.\n\n"
            "Tobias no longer trusts Melda because Seamus attacked them, though "
            "a high roll suggested Seamus was not going to betray them."
        ),
    ),
    dict(
        slug="melda",
        name="Melda",
        summary="Suspicious figure working on something in the smithing district. Correspondent of Seamus.",
        appearance="smith in a leather apron, soot-marked, watchful",
        tags=["npc", "from-session-log", "needs-detail"],
        links=["character/seamus"],
        body=(
            "A letter from her was found on Seamus's body, signed S and E. Who E "
            "is remains an open question in the log, possibly her husband.\n\n"
            "A fire came from the smithing district while she was there working "
            "on something suspicious."
        ),
    ),
    dict(
        slug="thog-mossborn",
        name="Thog Mossborn",
        summary="Of the Mossborn tribe, from Korran's past. Held prisoner beneath the quarry.",
        appearance="grey stone-skinned giant-kin, gaunt from captivity, heavy chains, matted hair",
        tags=["npc", "from-session-log"],
        links=["character/korran-mossborn", "faction/mossborn-tribe"],
        body="Met on 2026-03-04. A prison escape was planned for him and the log does not record whether it happened.",
    ),
    dict(
        slug="dante-ironblood",
        name="Dante IronBlood",
        summary="Tobias Goreguts's mentor.",
        appearance="scarred veteran warrior, iron-grey hair, battered plate, greatsword",
        tags=["npc", "from-session-log", "needs-detail"],
        links=["character/tobias-goreguts"],
    ),
    dict(
        slug="kasbor",
        name="Kasbor",
        summary="A kobold who resisted Gollub and guided the party through a secret path.",
        appearance="small blue-scaled kobold, torchlight, wary posture",
        tags=["npc", "ally", "from-session-log"],
        links=["character/gollub"],
        data={"aka": ["Kasboar"]},
        body="He screeched at one point, which the log notes might have brought trouble. Later helped the party out as the kobolds returned to work.",
    ),
    dict(
        slug="foreman-rumbleshot",
        name="Foreman Rumbleshot",
        summary="Leader of the mining operation at Rumbleshot Quarry.",
        appearance="grizzled mine foreman, hard hat, heavy coat, ledger under one arm",
        tags=["npc", "from-session-log"],
        links=["place/rumbleshot-quarry"],
    ),
    dict(
        slug="buster",
        name="Buster",
        summary="An orc. A friend of the party and their route to the Underbelly's leadership.",
        appearance="burly orc, green skin, tusks, worn street clothes, easy grin",
        tags=["npc", "ally", "from-lore", "from-session-log"],
        links=["character/tavin", "faction/underbelly-mercantile", "faction/the-belt"],
        body="Offered to take the party to his boss, which the log suspects is the same house where they killed Myra's people.",
    ),
]

PLACES = [
    dict(
        slug="laurelthel",
        name="Laurelthel",
        summary="A realm with royalty and an active rebellion. Wren is from there.",
        appearance="distant prosperous realm, pale spires, laurel groves, banners",
        tags=["realm", "from-session-log", "needs-detail"],
        links=["character/wren", "faction/the-fallen-heir"],
        data={"map_type": "realm", "aka": ["Laurelfell", "Laurefall"]},
        body=(
            "Spelled three ways in the log. Wren knows about it and is from "
            "there, but has been secretive on the subject, and noticed an aunt "
            "of hers at Warwick's party.\n\n"
            "The party travelled there for festivities in August 2026 and their "
            "carriage was attacked by rebels shouting for the fallen heir."
        ),
    ),
    dict(
        slug="pixie-pint-glass",
        name="The Pixie Pint Glass",
        summary="A secret bar upstairs at the Pincushion Haberdashery, next door to the Enchanter's Guild.",
        appearance="hidden upstairs bar, low beams, coloured glass lamps, crowded booths",
        tags=["site", "from-session-log"],
        links=["place/pincushion-haberdashery", "place/enchanters-guild", "faction/underbelly-mercantile"],
        data={"map_type": "site"},
        body=(
            "Reached by asking for a thimble at the tailor's. A pocket watch "
            "marked 'underbelly' is the token for going up.\n\n"
            "Wren got rich here at a Twig Ball competition."
        ),
    ),
    dict(
        slug="the-drowned-amphitheater",
        name="The Drowned Amphitheater",
        summary="A vast cavern around an underground lake, at the bottom of the kobold elevator. Gollub's seat.",
        appearance="enormous pitch-black cavern, tiered stone like an amphitheater, still underground lake, single torch",
        tags=["site", "from-session-log"],
        links=["character/gollub", "place/rumbleshot-quarry"],
        data={"map_type": "site"},
        body="Descriptive name; the log does not give it one. Rename if the table has its own.",
    ),
    dict(
        slug="goltheas-tree",
        name="Goltheas Tree",
        summary="A tree whose wood, cut into stakes, kills vampires. Roots from the Covenant's chambers lead to one.",
        appearance="immense pale tree, black roots spreading through dark earth, faintly luminous bark",
        tags=["landmark", "from-session-log", "needs-detail"],
        links=[COVENANT],
        data={"map_type": "landmark", "aka": ["Gotheus tree"]},
        body=(
            "Stakes made from it kill vampires and cause them to burst into "
            "black matter roots.\n\n"
            "Under the kobold caves, a captive said the roots there lead to a "
            "Goltheas Tree, and that he himself was born from a stake to the "
            "heart made from that wood. The log flags this as a major research "
            "lead: find one on the surface and see whether it is as "
            "indestructible."
        ),
    ),
    dict(
        slug="everpool",
        name="The Everpool",
        summary="Named only in Lucian's posthumous dream-song, alongside the Buried Star.",
        appearance="still dark water under stone, depthless, faintly lit",
        tags=["from-session-log", "needs-detail"],
        links=["place/buried-star"],
        data={"map_type": "unknown"},
        body=(
            "From the dream on 2026-05-27, in which Lucian appears and sings: "
            "secrets of the buried star revealed, surface of the everpool "
            "concealed."
        ),
    ),
]

FACTIONS = [
    dict(
        slug="the-belt",
        name="The Belt",
        summary="A secret policing group. The party are members, keeping tabs on the Underbelly Mercantile.",
        appearance="discreet badge, a plain leather belt buckle sigil, muted browns",
        tags=["faction", "from-session-log", "needs-detail"],
        links=["faction/underbelly-mercantile", "character/buster"],
    ),
    dict(
        slug="mossborn-tribe",
        name="The Mossborn Tribe",
        summary="Korran Mossborn's people. Swept away by a rockslide during a seasonal migration.",
        appearance="mountain tribe totem, carved grey stone and moss, weathered",
        tags=["faction", "from-lore", "from-session-log"],
        links=["character/korran-mossborn", "character/thog-mossborn"],
        body="Korran believed his tribe lost. Thog Mossborn turning up imprisoned beneath the quarry suggests otherwise.",
    ),
    dict(
        slug="the-fallen-heir",
        name="For the Fallen Heir",
        summary="A rebellion against Laurelthel's current royalty.",
        appearance="rebel banner, torn white cloth, a broken crown device",
        tags=["faction", "from-session-log", "needs-detail"],
        links=["place/laurelthel"],
        body=(
            "Attacked the party's carriage on the road to Laurelthel, shouting "
            "for the fallen heir. Two were captured."
        ),
    ),
    dict(
        slug="eleventh-battalion",
        name="The 11th Battalion",
        summary="Tobias Goreguts's old army unit, nicknamed the Bonewall.",
        appearance="military banner, bone-white wall device on dark ground",
        tags=["faction", "from-session-log", "needs-detail"],
        links=["character/tobias-goreguts"],
    ),
]

ITEMS = [
    dict(
        slug="underbelly-pocket-watch",
        name="Underbelly Pocket Watch",
        summary="A stopwatch marked 'underbelly'. The token for getting up to the Pixie Pint Glass.",
        appearance="worn brass pocket watch, engraved lettering, fine chain",
        links=["place/pixie-pint-glass", "faction/underbelly-mercantile"],
    ),
    dict(
        slug="pincushion-wrist-guards",
        name="Pincushion Wrist Guards",
        summary="Armbands bought at the Pincushion Haberdashery for 10 gold. Grant necrotic resistance.",
        appearance="pair of stitched leather wrist guards, fine embroidery, dark thread",
        links=["place/pincushion-haberdashery"],
        data={"weight_lb": 0.1, "cost_gp": 10, "effect": "Necrotic resistance (half damage)"},
    ),
    dict(
        slug="amalgamated-metal-fragment",
        name="Fragment of Amalgamated Metal",
        summary="Taken from the kobolds. Its strength is unlike anything the party has seen.",
        appearance="fused lump of many metals, rippled surface, dull and bright layers",
        links=["character/korran-mossborn"],
        tags=["magic-item", "from-session-log", "needs-detail"],
    ),
    dict(
        slug="tobias-mancala-set",
        name="Tobias's Mancala Set",
        summary="A board and an assortment of knick-knacks, each a memento of an adventure.",
        appearance="worn wooden mancala board, mismatched stones and trinkets in the pits",
        links=["character/tobias-goreguts"],
        tags=["keepsake", "from-session-log"],
        body="He picked up a small stone for it after nearly drowning Mundus, then saving him.",
    ),
]

# --- corrections to entities the earlier seeds created ---------------------

UPDATES = [
    ("character", "lucian-lovelyre", dict(
        summary="Half-elf bard. Killed by Elaric the Blightwarden in November 2025.",
        tags=["player-character", "bard", "half-elf", "deceased", "from-lore"],
        links=["place/copper-vale", "item/bloomfang-rapier",
               "character/elaric-the-blightwarden"],
        body=(
            "Joined the party 2025-05-09. Killed by Elaric the Blightwarden "
            "around 2025-11-19, in front of Myra.\n\n"
            "The body was found with the neck cut and completely drenched, vomit "
            "around it, and a bloodthirsty anger coming off the artefacts "
            "present.\n\n"
            "The party still lists revenge for Lucian as an open lead. He "
            "returned once in a dream on 2026-05-27, singing: secrets of the "
            "buried star revealed, surface of the everpool concealed."
        ),
    )),
    ("character", "elaric-the-blightwarden", dict(
        summary="An elf with a slithery tongue. Killed Lucian Lovelyre.",
        appearance="tall elf, sleek dark hair, too-wide smile, fine dark clothing, unsettling stillness",
        tags=["npc", "antagonist", "elf", "from-lore", "from-session-log"],
        body=(
            "Killed Lucian Lovelyre in front of Myra around 2025-11-19, and was "
            "later cornered against a wall in a fight at the fake Denny's.\n\n"
            "Sits directly between the party and the Hollow Root Covenant on the "
            "DM's relationship graph. A note in the log reads 'Not elaric "
            "sister', which suggests the party has wondered whether Sister "
            "Lethra is related to him."
        ),
    )),
    ("faction", "hollow-root-covenant", dict(
        summary="A vampire cult. Worships a rock that grants wishes, and curses the land to preserve its own safety.",
        tags=["faction", "antagonist", "vampire-cult", "from-lore", "from-session-log"],
        body=(
            "The session log is blunt about what they are: the Bogwatchers are "
            "active against the Blight, which the log glosses as the vampire "
            "cult.\n\n"
            "A captive beneath the kobold caves explained their logic directly: "
            "safety is preserved when we can curse the land. He was not a "
            "sacrifice, he was born from a stake to the heart made of Goltheas "
            "wood, and the roots in that chamber lead back to a Goltheas Tree.\n\n"
            "They are described as a cult who worship a rock that makes their "
            "wishes come true. Wren has a lot of information about them, which "
            "she has not fully shared.\n\n"
            "Note the shape of the campaign here: Copper Vale's water was "
            "poisoned by mining, and a cult that curses land for safety is "
            "working underneath it."
        ),
    )),
    ("character", "wren", dict(
        summary="Elf spellcaster from Laurelthel. Carries Twigbeard's Lucky Beard Twig and Timothy's staff.",
        tags=["player-character", "elf", "from-lore"],
        links=["place/copper-vale", "item/twigbeards-lucky-beard-twig",
               "character/timothy-tuttle", "place/laurelthel", COVENANT],
        body=(
            "Casts Speak With Dead. The art of her doing it shows her with a "
            "tall wooden staff in a candlelit bedroom, ringed by green "
            "skull-spirits, eyes lit cyan by the spell. The staff is very likely "
            "Timothy's.\n\n"
            "She is from Laurelthel and has been secretive about it. She noticed "
            "an aunt at Warwick's party and behaved oddly enough that Tobias got "
            "suspicious and tried to find out why.\n\n"
            "The log records that Wren has a lot of information on the Hollow "
            "Root Covenant. When a gemstone touched a root in the Covenant's "
            "chamber, a voice spoke in the back of her head."
        ),
    )),
    ("character", "tobias-goreguts", dict(
        summary="Half-orc barbarian, former mercenary of the 11th Battalion. Reckless in a fight and not much calmer outside one.",
        links=["place/copper-vale", "item/bloodroot-greatsword",
               "character/dante-ironblood", "faction/eleventh-battalion",
               "item/tobias-mancala-set"],
        body=(
            "A mercenary in the army before all this, scarred, with tough rough "
            "skin. His unit was the 11th Battalion, nicknamed the Bonewall. His "
            "mentor was Dante IronBlood.\n\n"
            "His mother died in a goblin attack. He presses flowers because of "
            "her last words to him: remember me in the flowers. He recovered "
            "that memory with Eva's help at the Enchanter's Guild.\n\n"
            "His stated flaw: he gets caught up in the moment and throws away "
            "all sense of critical thinking. He has no favourite number, which "
            "the log notes is the sort of simple question he has never had time "
            "to ponder."
        ),
    )),
    ("character", "aelan-viremont", dict(
        summary="Joined the party on the road to Laurelthel in August 2026. The party are suspicious of them.",
        tags=["player-character", "from-lore", "needs-appearance"],
        links=["place/copper-vale", "place/laurelthel"],
        data={"player": "Aelan Viremont", "discord_id": "REDACTED",
              "pronunciation": "Ay-lan VEER-mont"},
        body=(
            "Joined the fray on 2026-08-05 when the party's carriage to "
            "Laurelthel was attacked by rebels shouting for the fallen heir. "
            "The log records the party as suspicious of them.\n\n"
            "This confirms Aelan Viremont as the player, which was previously only an "
            "inference."
        ),
    )),
    ("character", "twigbeard", dict(
        summary="A lonely, friendly figure the party met by the river. Plays Twig Ball for acorns.",
        appearance="mossy bearded woodland figure, twigs and leaves in a long beard, kindly weathered face",
        tags=["npc", "from-lore", "from-session-log"],
        body=(
            "Met on 2025-10-02 walking down the riverside. He seemed nice and "
            "friendly, and was lonely and happy to have company.\n\n"
            "He runs a gambling game the log calls Twig Ball, staked in acorns "
            "and pinecones. Tobias went all in with one pinecone and ten acorns "
            "and lost the lot. Wren gave him her acorns back and he lost those "
            "too.\n\n"
            "Wren carries Twigbeard's Lucky Beard Twig. The DM's graph places "
            "him with the Hollow Root Covenant, which sits oddly with how "
            "harmless he seemed."
        ),
    )),
    ("place", "rumbleshot-quarry", dict(
        summary="Copper mine west of the vale, run by Foreman Rumbleshot. Attacked by goblins and kobolds serving Gollub.",
        tags=["landmark", "from-lore", "from-session-log"],
        links=["place/copper-vale", "character/foreman-rumbleshot",
               "character/gollub", "place/the-drowned-amphitheater"],
        body=(
            "Mining rich copper, with metal deposits that gleam like fire and "
            "exposed copper visible in a waterfall. Conifer trees and brush "
            "around it. The tunnels were damaged by fires.\n\n"
            "Goblins and kobolds planned to burn the mining camp down. The party "
            "stopped it: Tobias pulled civilians out of a burning house, and he "
            "and Korran broke down the burning gate so people could carry "
            "buckets through.\n\n"
            "Below it lies a kobold warren, an elevator, and Gollub."
        ),
    )),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cfg = config_mod.load()
    library = Library(cfg.content_dir)
    created = updated = patched = 0

    def write(kind: str, spec: dict) -> None:
        nonlocal created, updated
        entity = Entity(
            kind=kind,
            slug=spec["slug"],
            name=spec["name"],
            summary=spec.get("summary", ""),
            appearance=spec.get("appearance", ""),
            tags=spec.get("tags", ["from-session-log"]),
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
    for spec in PLACES:
        write("place", spec)
    for spec in FACTIONS:
        write("faction", spec)
    for spec in ITEMS:
        spec.setdefault("tags", ["magic-item", "from-session-log"])
        write("item", spec)

    # Corrections always overwrite the named fields: the session log is later
    # and better evidence than the graph or the level-up posts it supersedes.
    for kind, slug, fields in UPDATES:
        entity = library.load(kind, slug)
        if entity is None:
            print(f"  skip: {kind}/{slug} not found", file=sys.stderr)
            continue
        for key, value in fields.items():
            setattr(entity, key, value)
        if SRC not in entity.sources:
            entity.sources.append(SRC)
        library.save(entity)
        patched += 1

    print(f"{created} created, {updated} updated, {patched} corrected -> {cfg.content_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
