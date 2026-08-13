"""Turning an entity into an image prompt.

A campaign world only looks like one world if the art is consistent, so every
prompt is assembled the same way:

    <house style> , <shot template for this kind and variant> , <appearance> ,
    <context from linked entities> , <quality tail>

The house style comes from config.yaml and is the single lever that restyles
the entire universe. The shot templates decide framing. `appearance` is the
entity's own visual description and is the only part that should be unique.

SDXL's text encoder truncates at 77 tokens, so this is a budget, not a
paragraph. Parts are emitted in priority order and the tail is cut first.
"""

from __future__ import annotations

from dataclasses import dataclass

from .entities import Entity

# kind -> variant -> framing. "default" is used when no variant is asked for.
SHOTS: dict[str, dict[str, str]] = {
    "character": {
        "default": "character portrait, head and shoulders, facing viewer, neutral background",
        "portrait": "character portrait, head and shoulders, facing viewer, neutral background",
        "full": "full body character illustration, standing, simple background",
        "action": "dynamic action pose, mid-motion, dramatic angle",
    },
    "place": {
        "default": "wide establishing shot, no people, atmospheric",
        "wide": "wide establishing shot, no people, atmospheric",
        "interior": "interior view, warm practical lighting, lived-in detail",
        "aerial": "high aerial view looking down, sweeping landscape",
        "map": "hand-drawn parchment map vignette, ink and wash, cartographic",
    },
    "creature": {
        "default": "full body creature illustration, menacing, neutral background",
        "portrait": "creature head study, close up, detailed",
    },
    "item": {
        "default": "single object study, centered, dark neutral background, museum lighting",
    },
    "faction": {
        "default": "heraldic emblem, symmetrical, banner and sigil, flat graphic",
    },
    "event": {
        "default": "dramatic scene illustration, multiple figures, cinematic composition",
    },
    "deity": {
        "default": "divine holy symbol, iconographic, centered, radiant, stained-glass feel",
        "avatar": "towering divine figure, awe-inspiring, glowing, low angle",
    },
}

DEFAULT_SHOT = "illustration, centered composition"
QUALITY_TAIL = "highly detailed, sharp focus"


@dataclass
class Prompt:
    text: str
    negative: str
    seed: int

    def as_dict(self) -> dict:
        return {"prompt": self.text, "negative": self.negative, "seed": self.seed}


def stable_seed(*parts: str) -> int:
    """Deterministic seed from the entity identity.

    The same character regenerates with the same seed every time, so their face
    stays roughly consistent across runs. Change the variant and you get a new
    but still repeatable seed.
    """
    import zlib

    return zlib.crc32("::".join(parts).encode("utf-8")) & 0x7FFFFFFF


def shot_for(kind: str, variant: str) -> str:
    return SHOTS.get(kind, {}).get(variant) or SHOTS.get(kind, {}).get(
        "default", DEFAULT_SHOT
    )


# Place types that contain other places. A region shouldn't borrow the look of
# the cities inside it: it's the landscape they sit in.
CONTAINER_TYPES = {"region", "range", "wilderness", "river", "landmark", "realm"}


def clauses(text: str) -> list[str]:
    return [c.strip() for c in text.split(",") if c.strip()]


def trim_to_words(text: str, max_words: int) -> str:
    """Cut to a word budget on a comma boundary.

    Cutting mid-phrase leaves fragments like "timber buildings and", which the
    image model reads as a broken instruction. Better to drop a whole clause.
    """
    parts = clauses(text)
    kept: list[str] = []
    used = 0
    for part in parts:
        n = len(part.split())
        if used + n > max_words:
            if kept:
                break
            # The very first clause alone busts the budget. A hard cut is the
            # only option left, and the budget is a real token limit, not a
            # preference, so it wins.
            return " ".join(part.split()[:max_words])
        kept.append(part)
        used += n
    return ", ".join(kept)


def context_clause(entity: Entity, library=None, budget: int = 8) -> str:
    """A little setting borrowed from the place this thing sits in.

    A tavern in a river city should look like it sits in a river city. Applies
    only to settlements and sites: a region has nothing to inherit from, and a
    character portrait asking for a neutral background doesn't want landscape
    glued to it.
    """
    if library is None or not entity.links or entity.kind != "place":
        return ""
    if entity.data.get("map_type") in CONTAINER_TYPES:
        return ""

    for ref in entity.links:
        if not ref.startswith("place/"):
            continue
        linked = library.load("place", ref.split("/", 1)[1])
        if not linked or not linked.appearance:
            continue
        # Only inherit downward, from something that contains this.
        if linked.data.get("map_type") not in CONTAINER_TYPES:
            continue
        return trim_to_words(linked.appearance, budget)
    return ""


def build(
    entity: Entity,
    *,
    house_style: str,
    negative: str,
    variant: str = "default",
    max_words: int = 60,
    library=None,
) -> Prompt:
    parts: list[str] = []
    if house_style.strip():
        parts.append(house_style.strip())

    parts.append(shot_for(entity.kind, variant))

    # The subject itself. Deliberately never falls back to `summary`: a summary
    # says what a thing means, not what it looks like, and "Settlement of
    # roughly 24,000 people" in an image prompt is pure noise. Better to draw
    # from the bare name and let the CLI warn that an appearance is missing.
    parts.append(entity.appearance.strip() or entity.name)

    context = context_clause(entity, library)
    if context:
        parts.append(context)

    parts.append(QUALITY_TAIL)

    text = trim_to_words(", ".join(p for p in parts if p), max_words)

    return Prompt(
        text=text,
        negative=negative,
        seed=stable_seed(entity.kind, entity.slug, variant),
    )
