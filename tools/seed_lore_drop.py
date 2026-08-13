"""Seed from the #lore-drop channel: the DM's wiki pages, posted wholesale.

Source: `dnd-scribe/lore/lore-drop/`, 23 pages posted 2026-08-13.

This is the highest-authority source in the project and it overrides everything
before it. Several earlier entities were wrong in ways that mattered:

  * Lucian Lovelyre is an Aasimar, not a half-elf.
  * "Myra" and Maera Broadkettle are the same person. Tobias's player's session log
    spelled her Myra; she owns the Peapod Public House.
  * Warwick and Seamus have surnames and are both Underbelly Mercantile
    consorts: Worrick Thistleby and Seamus Stonebuckle.
  * Gollub is spelled Goluub, and lives in the Everpool.
  * "The Kept" is a rank within the Hollow Root Covenant, not a person.
  * The Hollow Root Covenant describes itself as a society of peace and
    scientific progress. The vampire-cult framing came from a player's notes,
    which is a different thing from what they are.

    python tools\\seed_lore_drop.py [--force]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

SRC = "discord:lore-drop:2026-08-13"
VALE = "place/copper-vale"
COVENANT = "faction/hollow-root-covenant"
UNDERBELLY = "faction/underbelly-mercantile"
PEAPOD = "place/peapod-pub"

# (kind, old_slug, new_slug). Old pages are deleted and every link that
# referenced them is rewritten.
RENAMES = [
    ("character", "warwick", "worrick-thistleby"),
    ("character", "seamus", "seamus-stonebuckle"),
    ("character", "gollub", "goluub"),
]

# (kind, slug) -> merged into (kind, slug). Old page deleted, links rewritten.
MERGES = [
    (("character", "myra"), ("character", "maera-broadkettle")),
]

NEW = [
    ("character", dict(
        slug="dak-patterson",
        name="Dak Patterson",
        summary="Regional Operator of the Underbelly Mercantile for Copper Vale. Always accompanied by an entourage.",
        appearance="well-dressed operator, fur-collared coat, heavy rings, flanked by bodyguards",
        tags=["npc", "antagonist", "from-wiki"],
        links=[UNDERBELLY, VALE],
        body="Top of the Underbelly's regional hierarchy, above the consorts. The tier above him is unrecorded.",
    )),
    ("character", dict(
        slug="darius-vell",
        name="Darius Vell",
        summary="Copper Vale Regional Consort of the Underbelly Mercantile. Buster's former boss, Tavin's uncle. Killed by the party.",
        appearance="sharp-featured merchant, dark tailored coat, cold expression",
        tags=["npc", "antagonist", "deceased", "from-wiki"],
        links=[UNDERBELLY, "character/buster", "character/tavin"],
    )),
    ("character", dict(
        slug="worrick-thistleby",
        name="Worrick Thistleby",
        summary="Copper Vale Regional Consort of the Underbelly Mercantile. A halfling. Now a business partner of the party.",
        appearance="halfling businessman, well-tailored waistcoat, sharp eyes, neat side-whiskers",
        tags=["npc", "halfling", "from-wiki", "from-session-log"],
        links=[UNDERBELLY, "character/seamus-stonebuckle", "place/rumbleshot-quarry"],
        data={"aka": ["Warwick"]},
        body=(
            "Wanted the mining company garrisoned rather than evacuated, "
            "against Seamus Stonebuckle. The party sided with Seamus first and "
            "failed, then went over to Worrick, who now treats them as business "
            "partners. They threw a party for his colleagues on 2026-05-13."
        ),
    )),
    ("character", dict(
        slug="seamus-stonebuckle",
        name="Seamus Stonebuckle",
        summary="Copper Vale Regional Consort of the Underbelly Mercantile, and a Kept of the Hollow Root Covenant. Killed by the party.",
        appearance="dwarf in mining leathers, heavy beard, soot-stained hands",
        tags=["npc", "dwarf", "deceased", "from-wiki", "from-session-log"],
        links=[UNDERBELLY, COVENANT, "character/worrick-thistleby",
               "place/rumbleshot-quarry", "character/melda"],
        data={"aka": ["Shameous", "Seamus"], "covenant_rank": "Kept"},
        body=(
            "Business associate of Worrick Thistleby, and a Kept of the Hollow "
            "Root Covenant. He wanted the Rumbleshot Quarry workers evacuated "
            "for 'safety', which reads very differently once you know his "
            "Covenant affiliation.\n\n"
            "The party killed him and found a secret letter from Melda on the "
            "body."
        ),
    )),
    ("faction", dict(
        slug="six-wolves",
        name="The 6 Wolves",
        summary="A pack of lycanthropes the party met in the foothills after fleeing the Hollow Root.",
        appearance="pack of lycanthropes, moonlit foothills, bristling fur and bared teeth",
        tags=["faction", "from-wiki", "needs-detail"],
        links=["character/twigbeard", "place/the-hollow-root",
               "character/elaric-the-blightwarden"],
        body=(
            "They crossed paths with the party in the foothills soon after the "
            "adventurers used Elaric's portal to flee the Hollow Root. Tension "
            "sparked a short confrontation, but necessity forced a temporary "
            "alliance before they separated again.\n\n"
            "Twigbeard was removed from the pack when the Wolves learned their "
            "supposed seventh lycanthrope was actually a dwarf druid relying on "
            "Wild Shape.\n\n"
            "Current membership is unrecorded."
        ),
    )),
    ("item", dict(
        slug="gnarled-staff-of-the-rooted-one",
        name="Gnarled Staff of the Rooted One",
        summary="Taken from the Rooted One's chamber beneath the Shallow Bog.",
        appearance="tall gnarled staff of dead root-wood, twisted grain, knotted head",
        tags=["magic-item", "from-wiki"],
        links=["character/rooted-one", "place/underground-chamber", "character/wren"],
        body=(
            "One of the artifacts the party pilfered from the Rooted One's "
            "chamber. Likely the tall wooden staff Wren is shown wielding when "
            "she casts Speak With Dead, and possibly the staff the DM asked her "
            "about attuning to via blood."
        ),
    )),
    ("item", dict(
        slug="splinter-of-the-buried-star",
        name="Splinter of the Buried Star",
        summary="A fragment of the Buried Star. In Wren's possession.",
        appearance="jagged splinter of dark crystal, faint inner starlight, cold",
        tags=["magic-item", "plot-critical", "from-wiki"],
        links=["place/buried-star", "character/wren", COVENANT],
        body=(
            "The Buried Star grants the desires of those it favours, through "
            "psychic wish magic. Wren holds a piece of it.\n\n"
            "She also reported a voice in the back of her head when a gemstone "
            "touched a root in the Covenant's chamber, and the session log notes "
            "she has a lot of information about the Covenant that she has not "
            "shared. Those facts sit together uncomfortably."
        ),
    )),
]

UPDATES = [
    ("character", "lucian-lovelyre", dict(
        summary="Aasimar bard of the College of Lore. A prolific musician, assassinated at the Peapod Public House.",
        appearance="handsome aasimar man, tousled dark hair, faintly luminous violet eyes, scarred cheek, warm ochre patterned tunic, lute",
        tags=["player-character", "bard", "aasimar", "deceased", "from-wiki"],
        links=[VALE, "item/bloomfang-rapier", "character/elaric-the-blightwarden", PEAPOD],
        data={"class": "Bard", "subclass": "College of Lore", "race": "Aasimar",
              },
        body=(
            "A prolific musician who often wrote songs about his sexual "
            "conquests and subsequent heartbreak. At the time of his death he "
            "had a residency at the Peapod Public House.\n\n"
            "## Assassination\n\n"
            "Found at the Peapod Pub on the 10th of Tarsakh, the day of his "
            "second resident performance, his throat slit. On his body was a "
            "note:\n\n"
            "> Dearest forgetful adventurers,\n>\n> I'm terribly sorry to hear "
            "about the loss of your friend Lucian. May his melodies echo for "
            "eternity. I wish you nothing but the truth.\n>\n> - E\n\n"
            "It is theorised that Elaric the Blightwarden wrote it. Note the "
            "wording: *forgetful* adventurers, and *I wish you nothing but the "
            "truth*. Both point straight at the amnesia, and wish is the Buried "
            "Star's own mechanism.\n\n"
            "## Discography\n\n"
            "Hundreds of songs over the years. Some towns prefer an uplifting "
            "jig, others a slow and tender tune. Among his most popular:\n\n"
            "- Lucian's Lullaby\n- Midnight in the Forest\n- Tavern Totty\n"
            "- After Last Call\n- My Sweet Songbird\n- Unrequited\n"
            "- Brindlewood Booty"
        ),
    )),
    ("character", "maera-broadkettle", dict(
        name="Maera Broadkettle",
        summary="Owner of the Peapod Public House. Her Misenchanted Lavender Mead wiped the original party's memories.",
        appearance="tavern keeper, sleeves rolled, apron stained lavender, sharp practical manner",
        tags=["npc", "from-wiki"],
        links=[PEAPOD, "item/misenchanted-lavender-mead", "place/enchanters-guild",
               UNDERBELLY, "character/korran-mossborn", "character/lucian-lovelyre"],
        data={"aka": ["Myra"], "occupation": "Owner of the Peapod Public House"},
        body=(
            "Owner of the Peapod Public House and Korran's previous boss. "
            "Tobias's player's session log spells her Myra.\n\n"
            "## Controversy\n\n"
            "Under investigation by the Enchanters' Guild for the Misenchanted "
            "Lavender Mead.\n\n"
            "She had been receiving financial support from the Underbelly "
            "Mercantile in exchange for letting them use her inn as a safehouse "
            "on occasion. That relationship gave her access to exotic alchemical "
            "ingredients, specifically Memory Lattice, which she wanted to use "
            "to conjure wonderful memories during Lucian's first night of "
            "residency.\n\n"
            "Her experiments worked. The finished mead was then altered by the "
            "oak cask, and instead of reinforcing memory it destroyed it.\n\n"
            "So the amnesia was an accident of cooperage, arranged by a woman "
            "trying to do something kind for a bard who was murdered at her pub "
            "a few months later."
        ),
    )),
    ("character", "korran-mossborn", dict(
        summary="Storm Goliath monk of the Bogwatchers' Sanctum. Bartender at the Peapod Public House.",
        tags=["player-character", "monk", "goliath", "from-wiki"],
        links=[VALE, "place/brindlewood", PEAPOD, "faction/bogwatchers-sanctum",
               "place/bogwatchers-sanctum-temple", "character/maera-broadkettle",
               "item/misenchanted-lavender-mead", "character/thog-mossborn"],
        data={"class": "Monk", "race": "Goliath (Storm)", "epithet": "the Still Hand",
              "occupation": "Bartender at the Peapod Public House"},
        body=(
            "Born not among his people's peaks but in the lowland marshes, after "
            "a rockslide swept his tribe away during a seasonal migration. Found "
            "as a child by a wandering hermit of the Bogwatchers' Sanctum and "
            "raised in their hidden temple amid the mists and moss.\n\n"
            "Taught to channel power without aggression and strike only when "
            "harmony was broken. He earned the name the Still Hand for staying "
            "calm when violence loomed.\n\n"
            "Works behind the bar at the Peapod Public House, listening. He "
            "unknowingly served the party Maera's amnesia-inducing Misenchanted "
            "Lavender Mead.\n\n"
            "He drinks little and speaks less, and occasionally disappears for a "
            "few days, returning with bruised knuckles and bog water on his "
            "robes."
        ),
    )),
    ("character", "buster", dict(
        summary="A three-quarter orc, Underbelly Mercantile underling, and a genuinely good guy. Close friend of Tobias.",
        appearance="burly three-quarter orc, green skin, small tusks, worn street clothes, easy grin",
        tags=["npc", "ally", "orc", "from-wiki"],
        links=["character/tavin", UNDERBELLY, "faction/the-belt", PEAPOD,
               "character/tobias-goreguts", "character/darius-vell"],
        data={"race": "3/4-Orc", "affiliation": "Underbelly Mercantile (Underling)",
              "partner": "Tavin"},
        body=(
            "Met the party when he came with Tavin to the Peapod Pub to pick up "
            "the cask of Misenchanted Lavender Mead. He stayed, shared some "
            "drinks, spilled some secrets, and bonded closely with Tobias.\n\n"
            "## Early life\n\n"
            "He has recounted facing racial discrimination from a young age, "
            "when children threw rocks at him and belittled his tusks."
        ),
    )),
    ("character", "tavin", dict(
        summary="A halfling, Underbelly Mercantile underling, and Buster's snooty partner.",
        appearance="halfling in a fine waistcoat, long pipe, sour supercilious expression",
        tags=["npc", "halfling", "from-wiki"],
        links=["character/buster", UNDERBELLY, "character/darius-vell"],
        data={"race": "Halfling", "affiliation": "Underbelly Mercantile (Underling)",
              "partner": "Buster"},
        body=(
            "Just a bad vibe. Smokes his pipe and is rude, and has not made an "
            "attempt to be courteous to Buster. Darius Vell was his uncle."
        ),
    )),
    ("character", "goluub", dict(
        name="Goluub",
        summary="An aboleth who inhabits the Everpool. Known to the Dire Foothills kobolds as Broodmaster.",
        appearance="ancient aboleth, vast eel-like body, three eyes, trailing tentacles, pale slick hide, black underground lake",
        tags=["npc", "antagonist", "creature", "from-wiki"],
        links=["place/everpool", "place/rumbleshot-quarry", "place/dire-foothills",
               "place/the-drowned-amphitheater"],
        data={"creature": "Aboleth", "aka": ["Gollub"], "title": "Broodmaster"},
        body=(
            "The Dire Foothills kobolds call him Broodmaster. He inhabits the "
            "Everpool.\n\n"
            "Kobolds represented him with a doll. Kasbor resisted him and helped "
            "the party. Found at the bottom of an elevator beneath the kobold "
            "warren, in a huge cavern like an amphitheater around an underground "
            "lake."
        ),
    )),
    ("character", "rooted-one", dict(
        summary="An ancient corpse seated on a throne beneath the Shallow Bog, gnarled roots growing outward from his body.",
        appearance="ancient withered corpse on a stone throne, thick gnarled roots growing out of the body and into the walls",
        tags=["npc", "from-wiki"],
        links=["place/underground-chamber", "place/blighted-bog",
               "item/gnarled-staff-of-the-rooted-one"],
        body=(
            "Discovered within the Underground Chamber beneath the Shallow Bog. "
            "His chambers were pilfered by the party, who took his staff along "
            "with other magical artifacts."
        ),
    )),
    ("character", "kept", dict(
        name="The Kept",
        summary="A rank within the Hollow Root Covenant, not an individual. Seamus Stonebuckle held it.",
        appearance="covenant initiate, plain robes, root-mark brand, downcast eyes",
        tags=["faction-rank", "from-wiki"],
        links=[COVENANT, "character/seamus-stonebuckle", "character/sister-lethra",
               "place/buried-star"],
        body=(
            "Earlier seeds treated this as a person because the DM's "
            "relationship graph shows it as a node. The lore drop settles it: "
            "Seamus Stonebuckle is described as a Kept of the Hollow Root "
            "Covenant, so it is a rank or standing within the order.\n\n"
            "Kept as its own page because the graph links it to Sister Lethra "
            "and the Buried Star, so the rank matters structurally."
        ),
    )),
    ("character", "mundus-decepi", dict(
        summary="Rogue. Was mentored by Elaric the Blightwarden inside the Hollow Root Covenant.",
        tags=["player-character", "rogue", "from-wiki", "needs-appearance"],
        links=[VALE, "item/rootbound-dagger", COVENANT,
               "character/elaric-the-blightwarden"],
        data={"class": "Rogue", "mentor": "Elaric the Blightwarden",
              "former_affiliation": "Hollow Root Covenant"},
        body=(
            "A member of the party, formerly of the Hollow Root Covenant, "
            "mentored there by Elaric the Blightwarden.\n\n"
            "This is why he has his own edge to the Covenant on the DM's "
            "relationship graph, separate from the party's. His mentor "
            "assassinated Lucian.\n\n"
            "An Avrae lookup for 'Rogue: Soulknife' appears in the channel, "
            "which given the party's class list is most likely his."
        ),
    )),
    ("faction", "hollow-root-covenant", dict(
        summary="An insular society within the Hollow Root beneath Copper Ridge, worshipping the Buried Star.",
        tags=["faction", "antagonist", "from-wiki"],
        links=["place/the-hollow-root", "place/buried-star", "place/copper-ridge",
               "character/elaric-the-blightwarden", "character/sister-lethra",
               "character/kept", "character/twigbeard", "character/mundus-decepi",
               "character/seamus-stonebuckle"],
        body=(
            "Living in their own insular society within the Hollow Root, nestled "
            "beneath Copper Ridge, this cult-like culture can only be described "
            "as secretive.\n\n"
            "Worshipping the Buried Star, which propels them forward by way of "
            "psychic wish magic, most members attain an otherwise-impossible "
            "lifestyle of peace and scientific progress.\n\n"
            "Read that carefully against what the party has seen. The Covenant "
            "describes itself as peaceful and scientifically advanced. Tobias's player's "
            "session log calls them a vampire cult, and the Bogwatchers oppose "
            "them as the Blight. Elaric mentored Mundus here, then murdered "
            "Lucian. Both accounts can be true at once, which is more "
            "interesting than either being wrong."
        ),
    )),
    ("faction", "underbelly-mercantile", dict(
        summary="Criminal trading concern operating across Copper Vale. Funds Maera's pub, profits from Rumbleshot Quarry.",
        tags=["faction", "antagonist", "from-wiki"],
        links=["character/dak-patterson", "character/darius-vell",
               "character/worrick-thistleby", "character/seamus-stonebuckle",
               "character/buster", "character/tavin", "character/maera-broadkettle",
               "place/rumbleshot-quarry", "place/underbelly-safehouse"],
        body=(
            "## Copper Vale hierarchy\n\n"
            "- **Regional Operator**: Dak Patterson, always accompanied by an "
            "entourage\n"
            "- **Consorts**: Darius Vell, Worrick Thistleby, Seamus Stonebuckle\n"
            "- **Underlings**: Buster, Tavin, and others\n\n"
            "Whatever sits above the regional tier is unrecorded.\n\n"
            "They fund Maera Broadkettle's pub in exchange for using it as an "
            "occasional safehouse, contract Foreman Rumbleshot for ore, and "
            "ultimately profit from the Rumbleshot Quarry. The party are members "
            "of the Belt, a secret policing group keeping tabs on them, and have "
            "killed one consort already."
        ),
    )),
    ("place", "buried-star", dict(
        name="The Buried Star",
        summary="An esoteric artifact worshipped by the Hollow Root Covenant. Functions by Wish magic.",
        appearance="buried radiance under dark earth, cracked ground bleeding pale starlight",
        tags=["artifact", "plot-critical", "from-wiki"],
        links=[COVENANT, "character/kept", "item/splinter-of-the-buried-star",
               "character/wren"],
        data={"map_type": "artifact"},
        body=(
            "Rumoured to function via Wish magic. Those who commune with it are "
            "somehow psychically connected to its intrinsic powers, and those it "
            "favours have their desires made manifest.\n\n"
            "A Splinter of the Buried Star is in Wren's possession.\n\n"
            "Recorded as a place by earlier seeds; it is an artifact. Kept at "
            "this path so existing links hold."
        ),
    )),
    ("place", "everpool", dict(
        summary="The water Goluub inhabits. Named in Lucian's posthumous dream-song alongside the Buried Star.",
        appearance="vast still black underground water, faint pale light far below the surface",
        tags=["site", "from-wiki"],
        links=["character/goluub", "place/buried-star", "place/rumbleshot-quarry"],
        data={"map_type": "site"},
        body=(
            "Goluub the aboleth lives here.\n\n"
            "From the dream on 2026-05-27, in which Lucian appears and sings: "
            "secrets of the buried star revealed, surface of the everpool "
            "concealed. Both halves of that line now point at something real."
        ),
    )),
    ("place", "the-hollow-root", dict(
        summary="The Hollow Root Covenant's home, nestled beneath Copper Ridge. The party fled it through Elaric's portal.",
        appearance="vast hollow root cavity beneath the mountain, dwellings built into pale dead wood, warm lamplight",
        tags=["site", "from-wiki"],
        links=[COVENANT, "place/copper-ridge", "place/underground-chamber",
               "faction/six-wolves", "character/elaric-the-blightwarden"],
        body=(
            "Not a ruin. An insular society lives here, in what the Covenant "
            "presents as peace and scientific progress.\n\n"
            "The party escaped through Elaric's portal and ran into the 6 Wolves "
            "in the foothills shortly afterwards."
        ),
    )),
    ("character", "foreman-rumbleshot", dict(
        name="Surgimir Rumbleshot",
        summary="Foreman of the Rumbleshot Quarry, contracted by the Underbelly Mercantile.",
        tags=["npc", "from-wiki"],
        links=["place/rumbleshot-quarry", UNDERBELLY, "place/dire-foothills",
               "place/copper-ridge"],
        data={"aka": ["Foreman Rumbleshot"]},
        body=(
            "Contracted by the Underbelly Mercantile to supply raw mineral ore "
            "sourced from the Dire Foothills of Copper Ridge."
        ),
    )),
    ("character", "twigbeard", dict(
        summary="A dwarf druid, formerly mistaken for the 6 Wolves' seventh lycanthrope. Plays Twigball.",
        appearance="mossy bearded dwarf druid, twigs and leaves in a long beard, kindly weathered face",
        tags=["npc", "dwarf", "druid", "from-wiki"],
        links=["faction/six-wolves", "item/twigbeards-lucky-beard-twig",
               "lore/twigball", COVENANT],
        body=(
            "A dwarf druid who relies on Wild Shape. The 6 Wolves removed him "
            "from the pack when they worked out their supposed seventh "
            "lycanthrope was nothing of the kind.\n\n"
            "Met on 2025-10-02 walking down the riverside: nice, friendly, "
            "lonely and happy to have company. He runs Twigball, staked in "
            "acorns and pinecones. Tobias went all in and lost everything, then "
            "lost Wren's acorns too.\n\n"
            "The DM's graph places him with the Hollow Root Covenant, which sits "
            "oddly with how harmless he seemed."
        ),
    )),
    ("character", "wren", dict(
        links=[VALE, "item/twigbeards-lucky-beard-twig", "character/timothy-tuttle",
               "place/laurelthel", COVENANT, "item/splinter-of-the-buried-star",
               "item/gnarled-staff-of-the-rooted-one"],
    )),
]


def rewrite_links(library: Library, old_ref: str, new_ref: str) -> int:
    n = 0
    for entity in list(library.all()):
        if old_ref in entity.links:
            entity.links = [new_ref if l == old_ref else l for l in entity.links]
            entity.links = list(dict.fromkeys(entity.links))
            library.save(entity)
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cfg = config_mod.load()
    library = Library(cfg.content_dir)

    # Renames and merges first, so later updates land on the new slugs.
    # A rename moves the page rather than deleting it: the old entity carries
    # its art references and any prose someone has written, and deleting it
    # would silently throw both away.
    for kind, old, new in RENAMES:
        path = library.path_for(kind, old)
        if not path.exists():
            continue
        entity = library.load(kind, old)
        if entity is not None and not library.exists(kind, new):
            entity.slug = new
            library.save(entity)
        path.unlink()
        moved = rewrite_links(library, f"{kind}/{old}", f"{kind}/{new}")
        print(f"renamed {kind}/{old} -> {kind}/{new} ({moved} link(s) rewritten)")

    for (old_kind, old_slug), (new_kind, new_slug) in MERGES:
        path = library.path_for(old_kind, old_slug)
        if path.exists():
            path.unlink()
            moved = rewrite_links(
                library, f"{old_kind}/{old_slug}", f"{new_kind}/{new_slug}"
            )
            print(
                f"merged {old_kind}/{old_slug} -> {new_kind}/{new_slug} "
                f"({moved} link(s) rewritten)"
            )

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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
