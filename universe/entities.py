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

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml

try:  # libyaml, when the host has it
    # Frontmatter parsing is the single hottest thing the site does: every
    # request that asks "what may this viewer see" parses every page, and the
    # pure-Python YAML loader is ~40x slower than the C one at that. Where
    # libyaml is missing the pure-Python loader still works, only slower.
    _Loader = yaml.CSafeLoader
except AttributeError:  # pragma: no cover - depends on the host's PyYAML build
    _Loader = yaml.SafeLoader

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


def _audience(meta: dict) -> list[str]:
    """Read `visible_to` from either place, tolerating a bare string.

    It lived under `data` first and is a top-level field now. Both spellings
    are accepted so no existing page needs editing; a page moves to the new
    shape the next time anything saves it.
    """
    raw = meta.get("visible_to")
    if raw is None:
        raw = (meta.get("data") or {}).get("visible_to")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    return [str(a) for a in raw]


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
    # Who may see this page at all. Empty means everyone. A first-class field
    # rather than a key in `data`, because it is the one entry that changes who
    # the page renders for: leaving it in the freeform dict meant every reader
    # had to normalise it itself and every writer had to remember to strip it
    # back out of rendered output.
    visible_to: list[str] = field(default_factory=list)
    # The place this one sits inside, as "place/slug". Empty means top level.
    #
    # Recorded on the child rather than as a list on the parent, so there is one
    # fact in one file: a district cannot be inside two cities, and moving it is
    # a one-line edit that cannot leave the old parent still claiming it. What a
    # place contains is worked out by looking, in `hierarchy.py`.
    within: str = ""
    # Kind-specific structured fields (population, alignment, coordinates...).
    data: dict[str, Any] = field(default_factory=dict)
    # Freeform prose. Everything below the frontmatter.
    body: str = ""

    def __post_init__(self) -> None:
        """Lift `visible_to` out of `data`, however this entity was built.

        Doing it only in `parse` was not enough: a seed script or a test that
        constructs an Entity directly with data={"visible_to": [...]} would
        silently produce a public page, because the restriction sat somewhere
        nothing reads any more. Silent is the whole problem with this rule, so
        normalisation happens on every Entity, not just parsed ones.
        """
        stray = self.data.pop("visible_to", None) if self.data else None
        if stray and not self.visible_to:
            self.visible_to = [stray] if isinstance(stray, str) else list(stray)

        # Same treatment for `within`, and for the same reason: an Entity built
        # by hand with data={"within": ...} would otherwise sit at the top level
        # while looking, in the file, exactly like one that does not.
        stray = self.data.pop("within", None) if self.data else None
        if stray and not self.within:
            self.within = str(stray)
        # A bare slug is what a person types. Only places nest, so the kind is
        # never ambiguous and demanding the prefix would just be a trap.
        if self.within and "/" not in self.within:
            self.within = f"place/{self.within}"

    @property
    def ref(self) -> str:
        return f"{self.kind}/{self.slug}"

    def copy(self) -> "Entity":
        """An independent Entity with the same contents.

        The library hands out cached parses, and an Entity is mutable: `upsert`
        edits one in place, panels append to `art`. Without a copy at the door,
        one request's edit would show up in the next request's read of a file
        that never changed on disk.
        """
        return Entity(
            kind=self.kind, slug=self.slug, name=self.name,
            summary=self.summary, tags=list(self.tags), links=list(self.links),
            sources=list(self.sources), art=list(self.art),
            appearance=self.appearance, visible_to=list(self.visible_to),
            within=self.within, data=copy.deepcopy(self.data), body=self.body,
        )

    def to_frontmatter(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "kind": self.kind}
        for key in ("summary", "appearance", "within"):
            value = getattr(self, key)
            if value:
                out[key] = value
        for key in ("tags", "links", "sources", "art", "visible_to"):
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

        meta = yaml.load(match.group(1), Loader=_Loader) or {}
        body = match.group(2).strip()
        return cls(
            kind=meta.get("kind", kind),
            slug=slug,
            name=meta.get("name", slug),
            summary=meta.get("summary", "") or "",
            appearance=meta.get("appearance", "") or "",
            within=str(meta.get("within") or ""),
            tags=list(meta.get("tags") or []),
            links=list(meta.get("links") or []),
            sources=list(meta.get("sources") or []),
            art=list(meta.get("art") or []),
            visible_to=_audience(meta),
            # `visible_to` is lifted out of `data` on the way in, so a page
            # written before it was a field parses the same as one written
            # after, and nothing downstream has to special-case it back out.
            data={k: v for k, v in (meta.get("data") or {}).items()
                  if k not in ("visible_to", "within")},
            body=body,
        )


class Library:
    """Reads and writes entities under a content root.

    Parsed pages are cached in memory, keyed on each file's mtime and size, so
    a file is only parsed again once it actually changes on disk. This is not a
    micro-optimisation: `entities_for` parses the whole library to work out
    what a viewer may see, and it runs on every request including each of the
    thirty thumbnails on the front page. With 120 pages that was 105ms of YAML
    per image, serialised on the event loop, which cost far more than sending
    the picture did.

    Keying on (mtime_ns, size) means an edit from anywhere invalidates the
    entry: the MCP server, a git pull, or a hand edit in an editor all change
    one or both. Nothing has to remember to tell the cache.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self._parsed: dict[Path, tuple[tuple[int, int], Entity]] = {}

    def _read(self, path: Path, kind: str, slug: str) -> Entity:
        """Parse a page, or hand back the last parse if it has not changed."""
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            stamp = None
        if stamp is not None:
            cached = self._parsed.get(path)
            if cached is not None and cached[0] == stamp:
                return cached[1].copy()
        entity = Entity.parse(path.read_text(encoding="utf-8"), kind=kind, slug=slug)
        if stamp is not None:
            self._parsed[path] = (stamp, entity)
        return entity.copy()

    def path_for(self, kind: str, slug: str) -> Path:
        return self.root / kind / f"{slug}.md"

    def exists(self, kind: str, slug: str) -> bool:
        return self.path_for(kind, slug).exists()

    def load(self, kind: str, slug: str) -> Entity | None:
        path = self.path_for(kind, slug)
        if not path.exists():
            return None
        return self._read(path, kind, slug)

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

        for scalar in ("summary", "appearance", "within"):
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
                yield self._read(path, k, path.stem)

    def search(self, query: str) -> list[Entity]:
        """Matching entities, best match first.

        Ranked because callers truncate. `all()` yields alphabetically by kind
        then slug, so unranked results put `archive/` first and buried the page
        you searched for below anything that merely mentioned it: searching
        `Gulthias` returned the archived misspelling before `Gulthias Tree`.
        """
        q = query.lower().strip()
        if not q:
            return []
        hits = []
        for entity in self.all():
            haystack = " ".join(
                [entity.name, entity.summary, entity.body, " ".join(entity.tags)]
            ).lower()
            if q in haystack:
                hits.append((self._rank(entity, q), len(entity.name), entity))
        hits.sort(key=lambda hit: (hit[0], hit[1]))
        return [entity for _, _, entity in hits]

    @staticmethod
    def _rank(entity: Entity, q: str) -> int:
        """Where the term hit, lowest first. An exact name beats a body mention."""
        name = entity.name.lower()
        if name == q:
            return 0
        if name.startswith(q):
            return 1
        if q in name:
            return 2
        if q in " ".join(entity.tags).lower():
            return 3
        return 4 if q in entity.summary.lower() else 5

    def backlinks(self, ref: str) -> list[Entity]:
        return [e for e in self.all() if ref in e.links]
