"""What a viewer is entitled to see.

One module answers the question, because it used to be answered in three
places: the website's renderer, the tooltip index and the MCP server each
carried their own copy of the rule. They agreed by coincidence rather than by
construction, and the failure mode of a disagreement is silent. A page one
surface hides and another serves is a spoiled campaign with no error to notice.

Two rules live here:

  * **Page visibility.** A page may name an audience in `visible_to`. Anyone
    outside it is not told the page exists.
  * **Link stripping.** A page you cannot see must not appear in anyone else's
    Related list either, or its name leaks even though its body does not.

They are the same rule wearing two hats, which is why they moved together.

Secret blocks inside a page stay in `secrets.py`, which was already the deepest
and best-tested module here. This one calls it through `redact()` so that the
all-access viewer is handled in one place rather than two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from . import secrets as secrets_mod
from .entities import Entity


@dataclass(frozen=True)
class Viewer:
    """Who is reading, and what that entitles them to.

    A bare `frozenset[str]` used to be passed around instead. That is how
    "nobody" ended up spelled four different ways across five files, one of
    which quietly meant something else: any set of strings was a valid viewer,
    including an empty one nobody meant to pass. Here you have to say which
    kind of viewer you mean out loud.
    """

    identities: frozenset[str] = frozenset()
    name: str = ""
    # Set only for the process holding the files. Expressed as a flag rather
    # than as a set containing everybody's keys, which is what it used to be:
    # that made full access indistinguishable from a person who happened to be
    # in every audience, and it silently widened whenever someone joined.
    all_access: bool = False

    @classmethod
    def person(cls, person) -> "Viewer":
        return cls(identities=person.identities, name=person.name)

    @classmethod
    def nobody(cls) -> "Viewer":
        """A signed-out reader, an export, or an unrecognised token.

        All three used to be written differently. They are the same thing: no
        claim to any identity, so nothing addressed to anyone is readable.
        """
        return cls(identities=frozenset(), name="")

    @classmethod
    def local(cls, name: str = "local (full access)") -> "Viewer":
        return cls(identities=frozenset(), name=name, all_access=True)

    @classmethod
    def of(cls, identities: Iterable[str], name: str = "") -> "Viewer":
        """Build one from raw identity strings, for tests and seed scripts."""
        return cls(identities=frozenset(str(i).strip().lower() for i in identities),
                   name=name)

    @property
    def is_dm(self) -> bool:
        return self.all_access or "dm" in self.identities

    def __bool__(self) -> bool:
        return bool(self.identities) or self.all_access


def audience_of(entity: Entity) -> frozenset[str] | None:
    """Who a page is restricted to, or None if it is unrestricted.

    Normalising here is the point: the field has been written as a list, as a
    bare string, with stray capitals and with padding, and every reader used to
    handle that itself. An empty list reads as unrestricted, which is
    surprising but is what the wiki has always done, so it stays until someone
    changes it deliberately.
    """
    raw = entity.visible_to
    if not raw:
        return None
    if isinstance(raw, str):
        raw = [raw]
    names = {str(a).strip().lower() for a in raw if str(a).strip()}
    return frozenset(names) or None


def readable(entity: Entity, viewer: Viewer) -> bool:
    if viewer.all_access:
        return True
    audience = audience_of(entity)
    if audience is None:
        return True
    return bool(viewer.identities & audience)


def visible(entities: Iterable[Entity], viewer: Viewer) -> list[Entity]:
    return [e for e in entities if readable(e, viewer)]


def redact(body: str, viewer: Viewer) -> str:
    """Hide the secret blocks this viewer may not read.

    Delegates to `secrets`, but owns the all-access case, so the process
    holding the files does not have to impersonate every person at once to read
    what is already on its own disk.
    """
    if viewer.all_access:
        return body
    return secrets_mod.redact(body, viewer.identities)


def withheld_from(body: str, viewer: Viewer) -> bool:
    """True when the body carries secrets this viewer is not shown."""
    if viewer.all_access:
        return False
    return secrets_mod.hidden_from(body, viewer.identities)


@dataclass
class View:
    """One viewer's version of the world, computed once.

    Holding the readable refs makes link stripping cheap and, more importantly,
    consistent: every surface asks the same object rather than each assembling
    its own `allowed` set and passing it around by hand.
    """

    viewer: Viewer
    entities: list[Entity] = field(default_factory=list)
    refs: frozenset[str] = frozenset()

    def readable(self, entity: Entity) -> bool:
        return entity.ref in self.refs

    def links_of(self, entity: Entity) -> list[str]:
        """The page's links, minus any pointing somewhere this viewer cannot go."""
        return [ref for ref in entity.links if ref in self.refs]

    def backlinks_of(self, entity: Entity, library) -> list[Entity]:
        return [e for e in library.backlinks(entity.ref) if e.ref in self.refs]

    def redact(self, body: str) -> str:
        return redact(body, self.viewer)


def for_viewer(source, viewer: Viewer) -> View:
    """Build a View from a Library or from an already-loaded list of entities."""
    entities = list(source.all()) if hasattr(source, "all") else list(source)
    allowed = visible(entities, viewer)
    return View(viewer=viewer, entities=allowed,
                refs=frozenset(e.ref for e in allowed))
