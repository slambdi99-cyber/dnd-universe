"""Import an Azgaar Fantasy Map Generator export into universe entities.

Azgaar's generator (https://azgaar.github.io/Fantasy-Map-Generator/) does the
part that isn't worth building: coastlines, rivers, biomes, political borders,
and a few thousand plausible place names. This turns its export into your own
entities, so the world becomes queryable, linkable, and drawable rather than a
picture you squint at.

Use **Export > Save as JSON** (not the .map file, which is a custom delimited
format). Then:

    python cli.py import-map path\\to\\world.json

What comes across:

    states     -> place (realm)      linked to their capital
    provinces  -> place (province)   linked to their realm
    burgs      -> place (settlement) linked to realm and province
    cultures   -> faction
    religions  -> faction
    markers    -> lore, when the map has legend text for them

Legend text from the map's Notes becomes the entity body, so anything you've
already written in the generator carries over.

A caution worth reading: FMG's JSON shape shifts between versions, and this
parser is deliberately tolerant rather than strict. It skips what it doesn't
recognise instead of failing. Run it with --dry-run first and check the counts
look like your map.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..entities import Entity, slugify


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def note(self, kind: str) -> None:
        self.by_kind[kind] = self.by_kind.get(kind, 0) + 1

    def summary(self) -> str:
        parts = [f"{n} {k}" for k, n in sorted(self.by_kind.items())]
        return (
            f"{self.created} created, {self.updated} updated, "
            f"{self.skipped} skipped ({', '.join(parts) or 'nothing'})"
        )


def _section(data: dict, name: str) -> list[dict]:
    """Pull a collection, tolerating the pack/top-level split across versions.

    FMG arrays are 1-indexed with a placeholder at position 0, and deleted
    entries are left in place marked `removed`. Both are filtered here so
    callers never have to think about it.
    """
    raw = None
    if isinstance(data.get("pack"), dict) and name in data["pack"]:
        raw = data["pack"][name]
    elif name in data:
        raw = data[name]
    if not isinstance(raw, list):
        return []

    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get("removed"):
            continue
        if not item.get("name") and name != "markers":
            continue
        out.append(item)
    return out


def _notes_index(data: dict) -> dict[str, str]:
    """FMG stores legend text in `notes`, keyed like 'burg12' or 'state3'."""
    notes = data.get("notes")
    if not isinstance(notes, list):
        return {}
    index = {}
    for note in notes:
        if isinstance(note, dict) and note.get("id"):
            legend = (note.get("legend") or "").strip()
            if legend:
                index[str(note["id"])] = legend
    return index


def _biome_names(data: dict) -> list[str]:
    biomes = data.get("biomesData")
    if isinstance(biomes, dict) and isinstance(biomes.get("name"), list):
        return [str(n) for n in biomes["name"]]
    return []


def _cell_biomes(data: dict) -> dict[int, int]:
    """cell index -> biome index, if the export included cells.

    Cells are the biggest part of the file and some exports omit them. Missing
    cells cost you biome flavour in the generated descriptions, nothing more.
    """
    pack = data.get("pack")
    cells = pack.get("cells") if isinstance(pack, dict) else None
    if cells is None:
        return {}

    # Newer exports use a dict of parallel arrays; older ones a list of dicts.
    if isinstance(cells, dict) and isinstance(cells.get("biome"), list):
        return {i: b for i, b in enumerate(cells["biome"]) if isinstance(b, int)}
    if isinstance(cells, list):
        out = {}
        for cell in cells:
            if isinstance(cell, dict) and "i" in cell and "biome" in cell:
                out[int(cell["i"])] = int(cell["biome"])
        return out
    return {}


def describe_burg(burg: dict, biome: str | None) -> str:
    """A short visual description, built from what the map already knows.

    This is what the art pipeline draws, so it's deliberately concrete: size,
    defences, water, landscape. No adjectives the map can't justify.
    """
    pop = float(burg.get("population") or 0)
    # FMG population is in thousands.
    people = pop * 1000

    if people >= 20000:
        size = "large walled city"
    elif people >= 5000:
        size = "busy town"
    elif people >= 1000:
        size = "small town"
    else:
        size = "village"

    bits = [size]
    if burg.get("capital"):
        bits.append("capital, grand architecture")
    if burg.get("port"):
        bits.append("harbor with moored ships")
    if burg.get("citadel"):
        bits.append("stone citadel on high ground")
    if burg.get("walls") and people < 20000:
        bits.append("defensive walls")
    if burg.get("temple"):
        bits.append("temple spire")
    if burg.get("plaza"):
        bits.append("open market square")
    if burg.get("shanty"):
        bits.append("shanties outside the walls")
    if biome:
        bits.append(f"{biome.lower()} landscape")

    return ", ".join(bits)


def _entity_for_state(
    state: dict, notes: dict[str, str], burg_slugs: dict[int, str]
) -> Entity | None:
    name = str(state.get("fullName") or state.get("name") or "").strip()
    if not name or str(state.get("name")).lower() == "neutrals":
        return None

    slug = slugify(name)
    links = []
    capital_id = state.get("capital")
    if capital_id and capital_id in burg_slugs:
        links.append(f"place/{burg_slugs[capital_id]}")

    form = state.get("formName") or "Realm"
    return Entity(
        kind="place",
        slug=slug,
        name=name,
        summary=f"{form} on the world map.",
        appearance=(
            f"sweeping territory of a {form.lower()}, rolling landscape, "
            f"distant walled settlements, banners on the wind"
        ),
        tags=["realm", "from-map"],
        links=links,
        sources=[f"azgaar:state:{state.get('i')}"],
        body=notes.get(f"state{state.get('i')}", ""),
        data={
            "map_type": "realm",
            "form": state.get("formName"),
            "area": state.get("area"),
            "urban_population": state.get("urban"),
            "rural_population": state.get("rural"),
            "color": state.get("color"),
            "azgaar_id": state.get("i"),
        },
    )


def _entity_for_burg(
    burg: dict,
    notes: dict[str, str],
    state_slugs: dict[int, str],
    province_slugs: dict[int, str],
    biome_of: dict[int, int],
    biome_names: list[str],
) -> Entity | None:
    name = str(burg.get("name") or "").strip()
    if not name:
        return None

    biome = None
    cell = burg.get("cell")
    if isinstance(cell, int) and cell in biome_of:
        idx = biome_of[cell]
        if 0 <= idx < len(biome_names):
            biome = biome_names[idx]

    links = []
    if burg.get("state") in state_slugs:
        links.append(f"place/{state_slugs[burg['state']]}")
    if burg.get("province") in province_slugs:
        links.append(f"place/{province_slugs[burg['province']]}")

    population = round(float(burg.get("population") or 0) * 1000)

    return Entity(
        kind="place",
        slug=slugify(name),
        name=name,
        summary=f"Settlement of roughly {population:,} people."
        if population
        else "Settlement on the world map.",
        appearance=describe_burg(burg, biome),
        tags=["settlement", "from-map"]
        + (["capital"] if burg.get("capital") else [])
        + (["port"] if burg.get("port") else []),
        links=links,
        sources=[f"azgaar:burg:{burg.get('i')}"],
        body=notes.get(f"burg{burg.get('i')}", ""),
        data={
            "map_type": "settlement",
            "population": population,
            "biome": biome,
            "x": burg.get("x"),
            "y": burg.get("y"),
            "port": bool(burg.get("port")),
            "capital": bool(burg.get("capital")),
            "azgaar_id": burg.get("i"),
        },
    )


def parse(path: Path) -> tuple[list[Entity], ImportReport]:
    report = ImportReport()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} isn't valid JSON. Use Export > Save as JSON in the map "
            f"generator, not the .map file. ({exc})"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(f"{path} doesn't look like an Azgaar export.")

    notes = _notes_index(data)
    biome_names = _biome_names(data)
    biome_of = _cell_biomes(data)

    states = _section(data, "states")
    provinces = _section(data, "provinces")
    burgs = _section(data, "burgs")
    cultures = _section(data, "cultures")
    religions = _section(data, "religions")

    if not any([states, burgs, provinces]):
        report.warnings.append(
            "No states, provinces or burgs found. Either the map is empty or "
            "this export has a shape the parser doesn't recognise."
        )

    # Slug maps first, so cross-links can be resolved in one pass.
    burg_slugs = {
        b["i"]: slugify(str(b["name"]))
        for b in burgs
        if b.get("i") is not None and b.get("name")
    }
    state_slugs = {
        s["i"]: slugify(str(s.get("fullName") or s.get("name")))
        for s in states
        if s.get("i") is not None and s.get("name")
    }
    province_slugs = {
        p["i"]: slugify(str(p.get("fullName") or p.get("name")))
        for p in provinces
        if p.get("i") is not None and p.get("name")
    }

    entities: list[Entity] = []

    for state in states:
        entity = _entity_for_state(state, notes, burg_slugs)
        if entity:
            entities.append(entity)
            report.note("realm")
        else:
            report.skipped += 1

    for province in provinces:
        name = str(province.get("fullName") or province.get("name") or "").strip()
        if not name:
            report.skipped += 1
            continue
        links = []
        if province.get("state") in state_slugs:
            links.append(f"place/{state_slugs[province['state']]}")
        entities.append(
            Entity(
                kind="place",
                slug=slugify(name),
                name=name,
                summary="Province on the world map.",
                appearance=(
                    "rolling countryside, scattered farmsteads, "
                    "old waymarkers along a dirt road"
                ),
                tags=["province", "from-map"],
                links=links,
                sources=[f"azgaar:province:{province.get('i')}"],
                body=notes.get(f"province{province.get('i')}", ""),
                data={"map_type": "province", "azgaar_id": province.get("i")},
            )
        )
        report.note("province")

    for burg in burgs:
        entity = _entity_for_burg(
            burg, notes, state_slugs, province_slugs, biome_of, biome_names
        )
        if entity:
            entities.append(entity)
            report.note("settlement")
        else:
            report.skipped += 1

    for group, tag in ((cultures, "culture"), (religions, "religion")):
        for item in group:
            name = str(item.get("name") or "").strip()
            if not name or name.lower() in {"wildlands", "no religion"}:
                report.skipped += 1
                continue
            entities.append(
                Entity(
                    kind="faction",
                    slug=slugify(name),
                    name=name,
                    summary=f"{tag.capitalize()} recorded on the world map.",
                    # Factions render as heraldry, so the useful visual detail
                    # is the motif, not a description of the people.
                    appearance=(
                        f"{(item.get('type') or tag).lower()} motifs, "
                        f"bold simple sigil, two-color heraldry"
                    ),
                    tags=[tag, "from-map"],
                    sources=[f"azgaar:{tag}:{item.get('i')}"],
                    body=notes.get(f"{tag}{item.get('i')}", ""),
                    data={
                        "map_type": tag,
                        "type": item.get("type"),
                        "azgaar_id": item.get("i"),
                    },
                )
            )
            report.note(tag)

    return entities, report


def import_map(path: Path, library, *, dry_run: bool = False) -> ImportReport:
    entities, report = parse(path)
    if dry_run:
        report.created = len(entities)
        return report

    for entity in entities:
        _, created = library.upsert(entity)
        if created:
            report.created += 1
        else:
            report.updated += 1
    return report
