"""Asking for a picture when the machine that draws them is elsewhere.

The wiki is moving to a free host with no GPU. Everything people do daily works
there, except drawing, which needs a 12GB card sitting in Spencer's office. So
a request travels the same way everything else does: as a file in the repo.

    someone presses Art  ->  a request is committed
    the machine at home  ->  drains the queue, commits the pictures
    the site             ->  pulls, and the candidates are waiting

Nothing here generates anything. This is the postbox, not the artist.

The button says "queued, waiting for the machine at home" rather than failing,
because a request that will be honoured in an hour is a different thing from an
error, and telling someone their click did nothing when it did is the worse
lie.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FOLDER = "art-queue"
_SAFE = re.compile(r"[^a-z0-9-]+")


@dataclass
class Request:
    kind: str
    slug: str
    prompt: str
    count: int = 3
    who: str = ""
    at: str = ""
    path: Path | None = field(default=None, compare=False)

    @property
    def page(self) -> str:
        return f"{self.kind}/{self.slug}"

    def as_dict(self) -> dict:
        return {"kind": self.kind, "slug": self.slug, "prompt": self.prompt,
                "count": self.count, "who": self.who, "at": self.at}


def _name(kind: str, slug: str, prompt: str) -> str:
    """One file per page and prompt, so pressing the button twice is idempotent.

    Someone refreshing an impatient tab should not queue the same picture five
    times and burn twenty minutes of GPU on it.
    """
    import zlib

    stamp = f"{zlib.crc32(prompt.encode('utf-8')) & 0xFFFFFF:06x}"
    return f"{_SAFE.sub('-', kind)}-{_SAFE.sub('-', slug)}-{stamp}.json"


def request(root: Path, kind: str, slug: str, prompt: str,
            who: str = "", count: int = 3) -> Request | None:
    """Queue a picture. Returns the request, or None if the prompt is empty."""
    prompt = " ".join((prompt or "").split())[:600]
    if not prompt:
        return None

    folder = Path(root) / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    item = Request(
        kind=kind, slug=slug, prompt=prompt, count=max(1, min(count, 4)),
        who=who, at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    path = folder / _name(kind, slug, prompt)
    path.write_text(json.dumps(item.as_dict(), indent=2), encoding="utf-8")
    item.path = path
    return item


def pending(root: Path, kind: str = "", slug: str = "") -> list[Request]:
    """Everything waiting, oldest first, optionally for one page."""
    folder = Path(root) / FOLDER
    if not folder.exists():
        return []
    out: list[Request] = []
    for path in sorted(folder.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A half-written request is not worth crashing a page render over.
            continue
        item = Request(
            kind=str(raw.get("kind", "")), slug=str(raw.get("slug", "")),
            prompt=str(raw.get("prompt", "")), count=int(raw.get("count", 3)),
            who=str(raw.get("who", "")), at=str(raw.get("at", "")), path=path,
        )
        if kind and item.kind != kind:
            continue
        if slug and item.slug != slug:
            continue
        out.append(item)
    return sorted(out, key=lambda r: r.at)


def done(item: Request) -> bool:
    """Forget a request once its pictures exist."""
    if item.path and item.path.exists():
        item.path.unlink()
        return True
    return False


def waiting_for(root: Path, kind: str, slug: str) -> str:
    """What to tell someone looking at a page with a request outstanding."""
    items = pending(root, kind, slug)
    if not items:
        return ""
    if len(items) == 1:
        return "One picture is queued, waiting for the machine at home."
    return f"{len(items)} pictures are queued, waiting for the machine at home."
