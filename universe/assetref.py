"""Turning a caller-supplied string into a path, once, safely.

Four routes used to hand user input to the filesystem, and each defended itself
with its own hand-rolled check. They were not the same check: two rejected
backslashes and two did not, two resolved the final path and confined it to its
root while two trusted the string test alone. All four were probably fine, and
"probably fine" is the problem. Every new file-serving route restarted the
argument, and a reviewer had to re-derive whether that one was safe.

So parsing is the gate. An unparsed string cannot become a path, because
nothing here takes one: you get an `AssetRef` or you get nothing, and only an
`AssetRef` can produce a path. The check cannot be forgotten because there is
no other way through.

Three shapes exist in this project, and all three live here so that the next
route picks one rather than inventing a fourth:

    AssetRef   kind/slug/name    a picture or an attachment on a page
    ArtName    kind-slug.png     the named art route's flat filename
    a loose filename             Discord attachments, named by strangers
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Deliberately strict. These are machine-made identifiers: a kind is a schema
# key, a slug comes from `slugify`, and a name is either a content hash or a
# variant label. Nothing here should ever contain a separator, a dot, a space
# or a control character, so anything that does is a probe rather than a typo.
SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

# An asset id carries no extension, which turns out to be load-bearing:
# compressing the store from PNG to WEBP changes every file on disk and not a
# single reference in content/. Resolution tries the formats in the order they
# are most likely to exist.
IMAGE_SUFFIXES = ("webp", "png", "jpg", "jpeg", "gif")


def confine(root: Path, candidate: Path) -> Path | None:
    """The resolved path, if it really lives under `root`, else nothing.

    The last line of defence, and the only one that survives a symlink. String
    checks describe what a name looks like; this asks the filesystem where the
    name actually leads.
    """
    base = Path(root).resolve()
    try:
        resolved = Path(candidate).resolve()
        resolved.relative_to(base)
    except (ValueError, OSError):
        return None
    return resolved if resolved.exists() else None


@dataclass(frozen=True)
class AssetRef:
    """A reference to one stored file, as `kind/slug/name`."""

    kind: str
    slug: str
    name: str

    def __str__(self) -> str:
        return f"{self.kind}/{self.slug}/{self.name}"

    @property
    def page(self) -> str:
        """The entity ref this file belongs to, for the permission check."""
        return f"{self.kind}/{self.slug}"

    @classmethod
    def parse(cls, text) -> "AssetRef | None":
        """Read a ref, or return None. Never raises, never guesses."""
        if not text or not isinstance(text, str):
            return None
        parts = text.split("/")
        if len(parts) != 3 or not all(SEGMENT.match(p) for p in parts):
            return None
        return cls(kind=parts[0], slug=parts[1], name=parts[2])

    def path_under(self, root: Path, suffix: str = ".png") -> Path | None:
        """The file this ref names, if it is really inside `root`.

        Resolved and confined even though the segments are already validated.
        The regex is the fence; this is the check that the fence held, and it
        also catches a symlink pointing out of the store, which no amount of
        string validation can.
        """
        return confine(
            root, Path(root) / self.kind / self.slug / f"{self.name}{suffix}")

    def image_under(self, root: Path) -> Path | None:
        """The stored image for this ref, whatever format it is in."""
        return self.find_under(root, IMAGE_SUFFIXES)

    def find_under(self, root: Path, suffixes) -> Path | None:
        """The same, for a store where the extension is not known up front."""
        for suffix in suffixes:
            found = self.path_under(root, "." + str(suffix).lstrip("."))
            if found is not None:
                return found
        return None


@dataclass(frozen=True)
class ArtName:
    """The flat `kind-slug.png` filename the named art route serves.

    A separate shape because it is genuinely one: the URL carries no slashes,
    and a slug may contain hyphens, so the split is on the first hyphen only.
    """

    kind: str
    slug: str

    @property
    def page(self) -> str:
        return f"{self.kind}/{self.slug}"

    @classmethod
    def parse(cls, filename) -> "ArtName | None":
        if not filename or not isinstance(filename, str):
            return None
        if not filename.endswith(".png"):
            return None
        stem = filename[: -len(".png")]
        kind, sep, slug = stem.partition("-")
        if not sep or not SEGMENT.match(kind) or not SEGMENT.match(slug):
            return None
        return cls(kind=kind, slug=slug)


# -- the loose case ----------------------------------------------------
#
# Not every filename here was made here. Discord attachments arrive named by
# whoever uploaded them, so they carry extensions, spaces and punctuation and
# cannot be held to SEGMENT. What is left is refusing the characters that let a
# name climb out of its folder, and then confining the result anyway.

SEPARATORS = ("/", "\\", "\x00")


def safe_filename(name) -> bool:
    """True if this is a plain filename rather than a path fragment."""
    if not name or not isinstance(name, str) or len(name) > 200:
        return False
    if any(sep in name for sep in SEPARATORS):
        return False
    # `..` anywhere, not only as a whole segment, so a decoded `..%2f` and a
    # name like `..\..\thing` are both refused. A leading dot is refused too:
    # nothing legitimate here is a hidden file.
    return ".." not in name and not name.startswith(".")
