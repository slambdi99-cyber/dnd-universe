"""Seed character sheet facts from the D&D Beyond campaign page.

Source: https://www.dndbeyond.com/campaigns/6916676 ("The Buried Star"),
read 2026-08-12. This is the mechanical record: race, class, subclass and
level, straight from the sheets, so it outranks anything inferred from art or
session notes on those specific fields.

It does not describe what anyone looks like. Appearances stay as they are,
transcribed from the art each player posted.

    python tools\\seed_dndbeyond.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe.entities import Library  # noqa: E402

SRC = "dndbeyond:campaign/6916676"

# slug -> fields to merge into `data`, plus tag changes
SHEETS = {
    "aelan-viremont": dict(
        data={"race": "Human", "class": "Wizard", "subclass": "Illusionist",
              "level": 4, "player": "Aelan Viremont", "dndbeyond_player": "Aelan Viremont",
              "discord_id": "REDACTED", "status": "active"},
        summary="Human illusionist wizard. Joined the party on the road to Laurelthel in August 2026.",
        appearance="human wizard, travelling robes over practical clothes, hooded cloak, "
                   "spellbook at the hip, faint shimmer of illusion at the fingertips",
        drop_tags=["needs-appearance"],
        add_tags=["wizard", "human"],
    ),
    "korran-mossborn": dict(
        data={"race": "Goliath", "class": "Monk",
              "subclass": "Warrior of the Elements", "level": 4,
              "dndbeyond_player": "Korrans-player", "status": "active"},
    ),
    "timothy-tuttle": dict(
        data={"race": "Tortle", "class": "Druid",
              "subclass": "Circle of the Shepherd (2024)", "level": 4,
              "dndbeyond_player": "TimTuttle", "status": "active"},
    ),
    "tobias-goreguts": dict(
        data={"race": "Half-Orc", "class": "Barbarian",
              "subclass": "Path of the Ancestral Guardian (XGtE)", "level": 4,
              "dndbeyond_player": "Maximpod", "status": "active"},
        summary="Half-orc barbarian of the Path of the Ancestral Guardian, and a "
                "former mercenary of the 11th Battalion.",
    ),
    "wren": dict(
        data={"race": "Elf", "class": "Fighter", "subclass": "Battle Master",
              "level": 4, "dndbeyond_player": "Nrwshoe",
              "discord_id": "REDACTED", "status": "active"},
        summary="Elf fighter of the Battle Master archetype, from Laurelthel. "
                "Carries a splinter of the Buried Star.",
        add_tags=["fighter"],
        note=(
            "\n\n## A discrepancy worth resolving\n\n"
            "Her sheet says Fighter (Battle Master), which has no spellcasting. "
            "But the DM posted art captioned 'Wren casting Speak With Dead', and "
            "the session log has her hearing a voice when a gemstone touched a "
            "root in the Covenant's chamber.\n\n"
            "The most likely explanation is an item rather than a class feature: "
            "she holds the Gnarled Staff of the Rooted One and a Splinter of the "
            "Buried Star, either of which could carry the spell. Worth asking "
            "her player rather than assuming the sheet or the fiction is wrong."
        ),
    ),
    "lucian-lovelyre": dict(
        data={"race": "Aasimar", "class": "Bard", "subclass": "College of Lore",
              "level": 3, "dndbeyond_player": "Lucians-player",
              "discord_id": "766420870016663572", "status": "deactivated"},
    ),
    "mundus-decepi": dict(
        data={"race": "Halfling", "class": "Rogue", "level": 3,
              "dndbeyond_player": "MundusDecepi",
              "discord_id": "REDACTED", "status": "deactivated"},
        summary="Halfling rogue, mentored by Elaric the Blightwarden inside the "
                "Hollow Root Covenant. Currently deactivated on D&D Beyond.",
        appearance="halfling in dark leathers, hood up, twin daggers, "
                   "light crossbow across the back, wary eyes",
        drop_tags=["needs-appearance"],
        add_tags=["halfling"],
        note=(
            "\n\n## Status\n\n"
            "His sheet sits under Deactivated Characters on D&D Beyond, "
            "alongside Lucian's, and stopped at level 3 while the rest of the "
            "party reached 4. That usually means the character is out of play.\n\n"
            "Not removed from the active party list without confirmation: "
            "deactivating a sheet and a player leaving are different things."
        ),
    ),
}


def main() -> int:
    cfg = config_mod.load()
    library = Library(cfg.content_dir)
    patched = missing = 0

    for slug, spec in SHEETS.items():
        entity = library.load("character", slug)
        if entity is None:
            print(f"  skip: character/{slug} not found", file=sys.stderr)
            missing += 1
            continue

        entity.data.update(spec.get("data", {}))
        if spec.get("summary"):
            entity.summary = spec["summary"]
        if spec.get("appearance"):
            entity.appearance = spec["appearance"]
        for tag in spec.get("drop_tags", []):
            if tag in entity.tags:
                entity.tags.remove(tag)
        for tag in spec.get("add_tags", []):
            if tag not in entity.tags:
                entity.tags.append(tag)
        note = spec.get("note")
        if note and note.strip() not in entity.body:
            entity.body = (entity.body.rstrip() + note).strip()
        if SRC not in entity.sources:
            entity.sources.append(SRC)

        library.save(entity)
        patched += 1
        d = entity.data
        print(f"  {entity.name}: {d.get('race')} {d.get('class')}"
              f"{' / ' + d['subclass'] if d.get('subclass') else ''}"
              f" (lvl {d.get('level')}, {d.get('status')})")

    print(f"\n{patched} corrected" + (f", {missing} missing" if missing else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
