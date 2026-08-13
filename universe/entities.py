"""The core data model for the universe.

Entities are markdown files with YAML frontmatter, living under
`content/<kind>/<slug>.md`. That's a deliberate choice and worth understanding
before building on it:

  * Several people edit this world at once. Markdown in git merges; a database
    needs a migration and a merge strategy for every schema change.
  * Claude can read and write these files directly, which is the whole point of
    the MCP server. Handing a language model a file is much less fragile than
    handing it a write API.
  * The web app doesn't lose anything. It indexes these files into SQLite or
    Postgres on load and queries the index. Files stay the source of truth, the
    database is a cache you can delete and rebuild.

If you'd rather the database be authoritative, say so before the web app gets
built; it's a cheap change now and an expensive one later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml

# The kinds of thing a campaign world is made of. Add to this freely; nothing
# is hardcoded to the list except the folder each kind lives in.
KINDS = (
    "place",
    "character",
    "faction",
    "item",
    "event",
    "session",
    "creature",
    "deity",
    "lore",
)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def slugify(name: str) -> str:
    slug = _SLUG_STRIP.sub("-", name.lower()).strip("-")
    return slug or "unnamed"


@dataclass
class Entity:
    kind: str
    slug: str
    name: str
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    # Slugs of related entities, as "kind/slug". Cross-links are the whole
    # value of a campaign wiki, so they're first-class rather than parsed out
    # of the prose.
    links: list[str] = field(default_factory=list)
    # Where this came from: a Discord message ID, a session segment, a map
    # import. Lets you trace any claim back to the table.
    sources: list[str] = field(default_factory=list)
    # Asset IDs from the art store.
    art: list[str] = field(default_factory=list)
    # Short, concrete, visual. Feeds the image prompts. Kept separate from
    # `summary` because what a thing looks like and what it means are
    # different questions.
    appearance: str = ""
    # Kind-specific structured fields (population, alignment, coordinates...).
    data: dict[str, Any] = field(default_factory=dict)
    # Freeform prose. Everything below the frontmatter.
    body: str = ""

    @property
    def ref(self) -> str:
        return f"{self.kind}/{self.slug}"

    def to_frontmatter(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "kind": self.kind}
        for key in ("summary", "appearance"):
            value = getattr(self, key)
            if value:
                out[key] = value
        for key in ("tags", "links", "sources", "art"):
            value = getattr(self, key)
            if value:
                out[key] = value
        if self.data:
            out["data"] = self.data
        return out

    def render(self) -> str:
        fm = yaml.safe_dump(
            self.to_frontmatter(), sort_keys=False, allow_unicode=True
        ).strip()
        body = self.body.strip()
        return f"---\n{fm}\n---\n\n{body}\n" if body else f"---\n{fm}\n---\n"

    @classmethod
    def parse(cls, text: str, *, kind: str, slug: str) -> "Entity":
        match = _FRONTMATTER.match(text)
        if not match:
            # A file with no frontmatter is still content, not an error. Treat
            # the first heading as the name so hand-written notes drop in.
            first = next(
                (ln.lstrip("# ").strip() for ln in text.splitlines() if ln.strip()),
                slug,
            )
            return cls(kind=kind, slug=slug, name=first, body=text.strip())

        meta = yaml.safe_load(match.group(1)) or {}
        body = match.group(2).strip()
        return cls(
            kind=meta.get("kind", kind),
            slug=slug,
            name=meta.get("name", slug),
            summary=meta.get("summary", "") or "",
            appearance=meta.get("appearance", "") or "",
            tags=list(meta.get("tags") or []),
            links=list(meta.get("links") or []),
            sources=list(meta.get("sources") or []),
            art=list(meta.get("art") or []),
            data=dict(meta.get("data") or {}),
            body=body,
        )


class Library:
    """Reads and writes entities under a content root."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def path_for(self, kind: str, slug: str) -> Path:
        return self.root / kind / f"{slug}.md"

    def exists(self, kind: str, slug: str) -> bool:
        return self.path_for(kind, slug).exists()

    def load(self, kind: str, slug: str) -> Entity | None:
        path = self.path_for(kind, slug)
        if not path.exists():
            return None
        return Entity.parse(path.read_text(encoding="utf-8"), kind=kind, slug=slug)

    def save(self, entity: Entity) -> Path:
        path = self.path_for(entity.kind, entity.slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entity.render(), encoding="utf-8")
        return path

    def replace(self, entity: Entity) -> tuple[Entity, bool]:
        """Overwrite an entity, but keep machine-managed fields.

        `art` is written by the art pipeline, never by a human or a seed script,
        so a seed that overwrites a page has no opinion about it and must not
        erase it. Without this, re-running a corrected seed with --force throws
        away every generated image reference and the next run redraws the lot.
        """
        existing = self.load(entity.kind, entity.slug)
        is_new = existing is None
        if existing is not None and not entity.art:
            entity.art = list(existing.art)
        self.save(entity)
        return entity, is_new

    def upsert(self, entity: Entity) -> tuple[Entity, bool]:
        """Merge into an existing entity rather than clobbering it.

        Anything a human wrote wins. Imports and generators fill gaps and add
        to lists, they never overwrite prose someone typed. Getting this wrong
        means a re-import silently eats a night of worldbuilding.
        """
        existing = self.load(entity.kind, entity.slug)
        if existing is None:
            self.save(entity)
            return entity, True

        for scalar in ("summary", "appearance"):
            if not getattr(existing, scalar) and getattr(entity, scalar):
                setattr(existing, scalar, getattr(entity, scalar))
        if not existing.body.strip() and entity.body.strip():
            existing.body = entity.body

        for listy in ("tags", "links", "sources", "art"):
            merged = list(dict.fromkeys(getattr(existing, listy) + getattr(entity, listy)))
            setattr(existing, listy, merged)

        for key, value in entity.data.items():
            existing.data.setdefault(key, value)

        self.save(existing)
        return existing, False

    def all(self, kind: str | None = None) -> Iterator[Entity]:
        kinds = [kind] if kind else sorted(
            d.name for d in self.root.iterdir() if d.is_dir()
        ) if self.root.exists() else []
        for k in kinds:
            folder = self.root / k
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.md")):
                yield Entity.parse(
                    path.read_text(encoding="utf-8"), kind=k, slug=path.stem
                )

    def search(self, query: str) -> list[Entity]:
        q = query.lower().strip()
        if not q:
            return []
        hits = []
        for entity in self.all():
            haystack = " ".join(
                [entity.name, entity.summary, entity.body, " ".join(entity.tags)]
            ).lower()
            if q in haystack:
                hits.append(entity)
        return hits

    def backlinks(self, ref: str) -> list[Entity]:
        return [e for e in self.all() if ref in e.links]
