"""Link each character page to their D&D Beyond sheet.

The sheet stays the source of truth for anything mechanical: hit points,
spells, inventory, gold. Those change every session and would be stale in this
wiki within a week, so they aren't copied. The wiki holds who someone is; the
sheet holds what they can do.

Character IDs read from the campaign page at
https://www.dndbeyond.com/campaigns/6916676 on 2026-08-13.

    python tools\\seed_sheet_links.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe.entities import Library  # noqa: E402

CAMPAIGN = "https://www.dndbeyond.com/campaigns/6916676"

SHEETS = {
    "aelan-viremont": "169093190",
    "korran-mossborn": "153830761",
    "timothy-tuttle": "151162336",
    "tobias-goreguts": "151161161",
    "wren": "150673315",
}


def main() -> int:
    cfg = config_mod.load()
    library = Library(cfg.content_dir)
    updated = missing = 0

    for slug, sheet_id in SHEETS.items():
        entity = library.load("character", slug)
        if entity is None:
            print(f"  skip: character/{slug} not found", file=sys.stderr)
            missing += 1
            continue
        entity.data["dndbeyond_sheet"] = f"https://www.dndbeyond.com/characters/{sheet_id}"
        entity.data["dndbeyond_campaign"] = CAMPAIGN
        library.save(entity)
        updated += 1
        print(f"  {entity.name:<20} -> {entity.data['dndbeyond_sheet']}")

    print(f"\n{updated} linked" + (f", {missing} missing" if missing else ""))
    print("\nLucian and Mundus are deactivated on D&D Beyond and have no live "
          "sheet link, so they're deliberately left without one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
