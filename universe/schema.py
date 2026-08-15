"""The shape of the world: what kinds of thing exist, and how the site is laid out.

This used to be three hardcoded lists in three modules. It's config now, because
the people using this wiki are the people who should get to decide that a
campaign needs Ships, or Quests, or that "Deities" should be called "Gods", and
none of them are going to edit Python to do it.

Everything here is editable by anyone connected, through the `structure` tools
on the MCP server or the Structure page on the site. There is no DM tier: the
table shares the world, so it shares the shape of it.

What is deliberately NOT here: anything that runs code. Structure is data, and
data is recoverable from git. A tool that could edit the templates or the server
would hand a shell to anyone who ever leaked a token.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import hierarchy as hierarchy_mod

import yaml

KEY = re.compile(r"^[a-z][a-z0-9-]{1,23}$")

FILE = "structure.yaml"

HEADER = """# The shape of this wiki: what kinds of thing exist, how the front page is
# arranged, and what the site is called.
#
# Rewritten by software whenever someone changes the structure through Claude
# or the Structure page, so don't put comments below this line: they won't
# survive. Hand-edit it freely otherwise; the site picks changes up without a
# restart.
"""

# What a campaign is made of, until someone decides otherwise. Only used to
# write the first `kinds:` block; after that structure.yaml is the truth.
DEFAULT_KINDS: tuple[tuple[str, str], ...] = (
    ("place", "Places"),
    ("character", "Characters"),
    ("faction", "Factions"),
    ("item", "Items"),
    ("deity", "Deities"),
    ("creature", "Creatures"),
    ("event", "Events"),
    ("session", "Sessions"),
    ("lore", "Lore"),
)

DEFAULT_HOME: tuple[dict, ...] = (
    {"title": "Where", "kind": "place",
     "data": {"map_type": ["region", "settlement"]}},
    {"title": "The Party", "kind": "character", "tag": "player-character"},
    {"title": "Gone", "kind": "character",
     "any_tag": ["former-party-member", "deceased"]},
    {"title": "Factions", "kind": "faction"},
)


@dataclass
class IndexTag:
    """One tag-backed group on a kind's index page."""

    title: str
    kind: str
    tag: str

    def as_dict(self) -> dict:
        return {"title": self.title, "kind": self.kind, "tag": self.tag}


@dataclass
class Kind:
    key: str
    label: str
    nav: bool = True

    def as_dict(self) -> dict:
        out = {"key": self.key, "label": self.label}
        if not self.nav:
            out["nav"] = False
        return out


@dataclass
class Section:
    """One block of cards on the front page."""

    title: str
    kind: str
    tag: str = ""
    any_tag: list[str] = field(default_factory=list)
    data: dict[str, list[str]] = field(default_factory=dict)

    def matches(self, entity) -> bool:
        if entity.kind != self.kind:
            return False
        if self.tag and self.tag not in entity.tags:
            return False
        if self.any_tag and not (set(self.any_tag) & set(entity.tags)):
            return False
        for key, allowed in self.data.items():
            if str(entity.data.get(key, "")) not in allowed:
                return False
        return True

    def as_dict(self) -> dict:
        out: dict[str, Any] = {"title": self.title, "kind": self.kind}
        if self.tag:
            out["tag"] = self.tag
        if self.any_tag:
            out["any_tag"] = list(self.any_tag)
        if self.data:
            out["data"] = {k: list(v) for k, v in self.data.items()}
        return out


@dataclass
class Schema:
    root: Path
    name: str = "The Buried Star"
    tagline: str = ""
    kinds: list[Kind] = field(default_factory=list)
    home: list[Section] = field(default_factory=list)
    index_tags: list[IndexTag] = field(default_factory=list)
    _stamp: float = 0.0

    # -- lookups -------------------------------------------------------

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(k.key for k in self.kinds)

    def label(self, key: str) -> str:
        for kind in self.kinds:
            if kind.key == key:
                return kind.label
        # A folder exists that no kind describes: show it rather than hide it.
        # Losing sight of forty pages because someone deleted a kind is worse
        # than an ugly heading.
        return key.replace("-", " ").title()

    def has(self, key: str) -> bool:
        return key in self.keys

    @property
    def nav(self) -> list[Kind]:
        return [k for k in self.kinds if k.nav]

    def as_dict(self) -> dict:
        return {
            "site": {"name": self.name, "tagline": self.tagline},
            "kinds": [k.as_dict() for k in self.kinds],
            "index_tags": [t.as_dict() for t in self.index_tags],
            "home": [s.as_dict() for s in self.home],
        }

    # -- persistence ---------------------------------------------------

    def reload_if_changed(self) -> None:
        """Pick up edits made by another process, or by hand.

        The site and the MCP server are one process today, but a seed script or
        a person with a text editor is not, and a wiki that needs restarting to
        notice a change is a wiki whose structure nobody edits.
        """
        try:
            stamp = (self.root / FILE).stat().st_mtime
        except OSError:
            return
        if stamp != self._stamp:
            fresh = load(self.root)
            self.name, self.tagline = fresh.name, fresh.tagline
            self.kinds = fresh.kinds
            self.index_tags = fresh.index_tags
            self.home = fresh.home
            self._stamp = stamp

    def save(self) -> None:
        """Write the structure to structure.yaml.

        Its own file rather than a section of config.yaml, because this one is
        rewritten by software every time someone adds a kind, and a YAML
        round-trip discards comments. config.yaml is hand-edited and its
        comments are the only documentation of what half those settings do.
        """
        path = self.root / FILE
        path.write_text(HEADER + yaml.safe_dump(
            self.as_dict(), sort_keys=False, allow_unicode=True), encoding="utf-8")
        self._stamp = path.stat().st_mtime


def load(root: Path) -> Schema:
    """Read structure.yaml, falling back to config.yaml, then to the defaults."""
    path = Path(root) / FILE
    raw: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        # Structure lived in config.yaml briefly. Read it from there if it's
        # still the only copy, so an existing setup isn't reset to defaults.
        legacy = Path(root) / "config.yaml"
        if legacy.exists():
            found = yaml.safe_load(legacy.read_text(encoding="utf-8")) or {}
            raw = {k: found[k] for k in ("site", "kinds", "home") if k in found}

    site = raw.get("site") or {}
    kinds: list[Kind] = []
    for entry in raw.get("kinds") or []:
        if isinstance(entry, str):
            kinds.append(Kind(key=entry, label=entry.capitalize() + "s"))
        elif isinstance(entry, dict) and entry.get("key"):
            key = str(entry["key"]).strip().lower()
            if KEY.match(key):
                kinds.append(Kind(
                    key=key,
                    label=str(entry.get("label") or key.capitalize()),
                    nav=bool(entry.get("nav", True)),
                ))
    if not kinds:
        kinds = [Kind(key=k, label=label) for k, label in DEFAULT_KINDS]

    home: list[Section] = []
    for entry in raw.get("home") or DEFAULT_HOME:
        if not isinstance(entry, dict) or not entry.get("kind"):
            continue
        home.append(Section(
            title=str(entry.get("title") or ""),
            kind=str(entry["kind"]).strip().lower(),
            tag=str(entry.get("tag") or ""),
            any_tag=[str(t) for t in (entry.get("any_tag") or [])],
            data={str(k): [str(x) for x in (v if isinstance(v, list) else [v])]
                  for k, v in (entry.get("data") or {}).items()},
        ))

    index_tags: list[IndexTag] = []
    for entry in raw.get("index_tags") or []:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind", "")).strip().lower()
        tag = str(entry.get("tag", "")).strip()
        title = str(entry.get("title", "")).strip()
        if kind and tag and title:
            index_tags.append(IndexTag(title=title, kind=kind, tag=tag))

    schema = Schema(
        root=Path(root),
        name=str(site.get("name") or "The Buried Star"),
        tagline=str(site.get("tagline") or
                    "The DM's campaign, set in Copper Vale: a low-lying landscape "
                    "where scattered civilization clings to dwindling natural "
                    "resources."),
        kinds=kinds,
        home=home,
        index_tags=index_tags,
    )
    try:
        schema._stamp = path.stat().st_mtime
    except OSError:
        pass
    return schema


# -- editing -----------------------------------------------------------
#
# Every mutation returns (ok, message). The message is written for whoever
# asked, human or model, and says what actually happened rather than "done".


def add_kind(schema: Schema, key: str, label: str = "", *,
             nav: bool = True) -> tuple[bool, str]:
    key = (key or "").strip().lower().replace(" ", "-")
    if not KEY.match(key):
        return False, ("A kind's key is lowercase letters, numbers and hyphens, "
                       "2 to 24 characters, e.g. 'ship' or 'plot-thread'.")
    if schema.has(key):
        return False, f"{key} already exists."
    schema.kinds.append(Kind(key=key, label=label.strip() or key.capitalize() + "s",
                             nav=nav))
    schema.save()
    return True, f"Added {key}, shown as {schema.label(key)}."


def update_kind(schema: Schema, key: str, *, label: str | None = None,
                nav: bool | None = None,
                position: int | None = None) -> tuple[bool, str]:
    key = (key or "").strip().lower()
    kind = next((k for k in schema.kinds if k.key == key), None)
    if kind is None:
        return False, f"No kind called {key!r}."
    changed = []
    if label is not None and label.strip() and label.strip() != kind.label:
        kind.label = label.strip()
        changed.append(f"labelled {kind.label}")
    if nav is not None and nav != kind.nav:
        kind.nav = nav
        changed.append("shown in the nav" if nav else "hidden from the nav")
    if position is not None:
        schema.kinds.remove(kind)
        schema.kinds.insert(max(0, min(position, len(schema.kinds))), kind)
        changed.append(f"moved to position {position + 1}")
    if not changed:
        return False, "Nothing to change."
    schema.save()
    return True, f"{key}: {', and '.join(changed)}."


def rename_kind(schema: Schema, key: str, new_key: str, library,
                *, label: str = "") -> tuple[bool, str]:
    """Rename a kind and move every page and link with it.

    The migration is the whole job. A rename that leaves forty pages in the old
    folder and every cross-link pointing at a ref that no longer resolves is
    worse than refusing.
    """
    key = (key or "").strip().lower()
    new_key = (new_key or "").strip().lower().replace(" ", "-")
    if not schema.has(key):
        return False, f"No kind called {key!r}."
    if not KEY.match(new_key):
        return False, "The new key must be lowercase letters, numbers and hyphens."
    if schema.has(new_key):
        return False, f"{new_key} already exists. Move the pages instead."

    moved = _move_pages(library, key, new_key)
    relinked = _rewrite_links(library, {f"{key}/": f"{new_key}/"})

    for kind in schema.kinds:
        if kind.key == key:
            kind.key = new_key
            if label.strip():
                kind.label = label.strip()
    for section in schema.home:
        if section.kind == key:
            section.kind = new_key
    for tag in schema.index_tags:
        if tag.kind == key:
            tag.kind = new_key
    schema.save()
    return True, (f"Renamed {key} to {new_key}: {moved} page(s) moved, "
                  f"{relinked} link(s) updated.")


def remove_kind(schema: Schema, key: str, library,
                move_pages_to: str = "") -> tuple[bool, str]:
    key = (key or "").strip().lower()
    if not schema.has(key):
        return False, f"No kind called {key!r}."
    if len(schema.kinds) <= 1:
        return False, "That's the last kind. The wiki needs somewhere to put things."

    count = sum(1 for _ in library.all(key))
    if count and not move_pages_to:
        return False, (f"{key} still has {count} page(s). Pass move_pages_to to "
                       f"send them somewhere, or they'd be stranded in a folder "
                       f"nothing lists.")
    if move_pages_to:
        target = move_pages_to.strip().lower()
        if not schema.has(target):
            return False, f"No kind called {target!r} to move them to."
        _move_pages(library, key, target)
        _rewrite_links(library, {f"{key}/": f"{target}/"})

    schema.kinds = [k for k in schema.kinds if k.key != key]
    schema.home = [s for s in schema.home if s.kind != key]
    schema.index_tags = [t for t in schema.index_tags if t.kind != key]
    schema.save()
    where = f", {count} page(s) moved to {move_pages_to}" if move_pages_to else ""
    return True, f"Removed {key}{where}."


def move_page(library, ref: str, to_kind: str, schema: Schema) -> tuple[bool, str]:
    """Move one page to another kind, keeping its links intact."""
    if "/" not in ref:
        return False, "Give the page as kind/slug."
    kind, slug = ref.split("/", 1)
    to_kind = to_kind.strip().lower()
    if not schema.has(to_kind):
        return False, f"No kind called {to_kind!r}."
    entity = library.load(kind, slug)
    if entity is None:
        return False, f"No page at {ref}."
    if library.exists(to_kind, slug):
        return False, f"{to_kind}/{slug} already exists."

    # Only places nest, so moving one to another kind would leave whatever is
    # inside it pointing at something that is no longer a place. Refuse, and
    # say what is in the way, rather than silently flattening a city's worth of
    # shops to the top level.
    if kind != to_kind:
        inside = hierarchy_mod.children(entity.ref, library.all(kind))
        if inside:
            names = ", ".join(p.name for p in inside[:5])
            more = f" and {len(inside) - 5} more" if len(inside) > 5 else ""
            return False, (
                f"{entity.name} has {len(inside)} place(s) inside it: {names}"
                f"{more}. Move them out first, or they would be left pointing "
                f"at something that is no longer a place."
            )

    entity.kind = to_kind
    library.save(entity)
    library.path_for(kind, slug).unlink()
    relinked = _rewrite_links(library, {f"{kind}/{slug}": f"{to_kind}/{slug}"})
    return True, f"Moved {ref} to {to_kind}/{slug}, {relinked} link(s) updated."


def set_site(schema: Schema, name: str = "", tagline: str = "") -> tuple[bool, str]:
    changed = []
    if name.strip() and name.strip() != schema.name:
        schema.name = name.strip()[:60]
        changed.append(f"named {schema.name}")
    if tagline.strip() and tagline.strip() != schema.tagline:
        schema.tagline = tagline.strip()[:300]
        changed.append("re-worded the tagline")
    if not changed:
        return False, "Nothing to change."
    schema.save()
    return True, "The site is " + ", and ".join(changed) + "."


def set_home(schema: Schema, sections: list[dict]) -> tuple[bool, str]:
    parsed: list[Section] = []
    for entry in sections or []:
        if not isinstance(entry, dict):
            return False, "Each section is an object with a title and a kind."
        kind = str(entry.get("kind", "")).strip().lower()
        if not schema.has(kind):
            return False, (f"No kind called {kind!r}. Existing kinds: "
                           f"{', '.join(schema.keys)}.")
        parsed.append(Section(
            title=str(entry.get("title") or "").strip(),
            kind=kind,
            tag=str(entry.get("tag") or "").strip(),
            any_tag=[str(t).strip() for t in (entry.get("any_tag") or [])],
            data={str(k): [str(x) for x in (v if isinstance(v, list) else [v])]
                  for k, v in (entry.get("data") or {}).items()},
        ))
    schema.home = parsed
    schema.save()
    return True, f"Front page rebuilt with {len(parsed)} section(s)."


def set_index_tags(schema: Schema, groups: list[dict]) -> tuple[bool, str]:
    parsed: list[IndexTag] = []
    for entry in groups or []:
        if not isinstance(entry, dict):
            return False, "Each index tag group is an object with title, kind and tag."
        kind = str(entry.get("kind", "")).strip().lower()
        if not schema.has(kind):
            return False, (f"No kind called {kind!r}. Existing kinds: "
                           f"{', '.join(schema.keys)}.")
        title = str(entry.get("title", "")).strip()
        tag = str(entry.get("tag", "")).strip()
        if not title or not tag:
            return False, "Each index tag group needs a title and a tag."
        parsed.append(IndexTag(title=title, kind=kind, tag=tag))
    schema.index_tags = parsed
    schema.save()
    return True, f"Index pages rebuilt with {len(parsed)} tag group(s)."


# -- migration helpers -------------------------------------------------

def _move_pages(library, old_kind: str, new_kind: str) -> int:
    moved = 0
    for entity in list(library.all(old_kind)):
        source = library.path_for(old_kind, entity.slug)
        entity.kind = new_kind
        library.save(entity)
        if source.exists():
            source.unlink()
        moved += 1
    folder = library.root / old_kind
    if folder.exists() and not any(folder.iterdir()):
        folder.rmdir()
    return moved


def _swap(ref: str, swaps: dict[str, str]) -> tuple[str, bool]:
    for old, new in swaps.items():
        if ref == old.rstrip("/"):
            return new, True
        if ref.startswith(old):
            return new + ref[len(old):], True
    return ref, False


def _rewrite_links(library, swaps: dict[str, str]) -> int:
    """Repoint every cross-link after a move. Returns references changed.

    `within` is repointed too. Renaming the `place` kind moves every page and
    used to leave each child still saying `within: place/valeshire`, pointing
    at a folder that no longer existed, which silently flattened the entire
    hierarchy into a list of top-level places.
    """
    changed = 0
    for entity in list(library.all()):
        touched = False
        new_links = []
        for link in entity.links:
            link, hit = _swap(link, swaps)
            touched = touched or hit
            changed += 1 if hit else 0
            new_links.append(link)

        if entity.within:
            parent, hit = _swap(entity.within, swaps)
            if hit:
                entity.within = parent
                touched = True
                changed += 1

        if touched:
            entity.links = new_links
            library.save(entity)
    return changed
