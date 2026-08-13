"""What's arrived in Discord that isn't in the wiki yet.

`dnd-scribe` pulls channels into `lore/<channel>/messages.json` on a schedule.
This decides which of those messages still need a human decision, and remembers
the ones that have had one.

A message stops being new when any of these is true:

  * someone filed it (the button on /wiki/inbox, or the `mark_filed` tool)
  * a page cites it, i.e. some entity has `discord:<channel>:<id>` in `sources`
  * it predates the watermark, set the first time the inbox ever runs

That last one matters. Four years of history was already folded into the wiki
by the seed scripts, so an inbox that started from message one would open with
eight hundred unread items and never be looked at again. First run treats
everything already on disk as handled and starts watching from there.

Nothing in here summarises or writes. It hands you the raw messages and lets a
person decide what's canon, because a summariser wired straight into the wiki
would fill the campaign with confident fiction nobody said at the table.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

STATE_FILE = ".inbox.json"
DEFAULT_LORE = Path("..") / "dnd-scribe" / "lore"

# Matches the source strings written by create_page/update_page, e.g.
# "discord:lore-drop:1464466677759479818". The 15-digit floor keeps it from
# matching a date-shaped source like "discord:lore-drop:2026-08-13".
CITED = re.compile(r"discord:[^\s:]+:(\d{15,})")

# Discord posts a lot of noise. None of this is worth a person's attention.
SKIP_PREFIXES = ("!", "/", "http://tenor.com", "https://tenor.com")


@dataclass
class Message:
    channel: str
    id: str
    author: str
    at: str
    text: str
    attachments: list[dict] = field(default_factory=list)
    reply_to: str | None = None

    @property
    def source(self) -> str:
        """What to pass as `source` when this turns into a page."""
        return f"discord:{self.channel}:{self.id}"

    @property
    def date(self) -> str:
        return self.at[:10]

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "channel": self.channel,
            "author": self.author,
            "at": self.at,
            "text": self.text,
            "attachments": [a.get("filename", "") for a in self.attachments],
            "source": self.source,
        }


def _worth_reading(record: dict) -> bool:
    if record.get("is_bot"):
        return False
    text = (record.get("content") or "").strip()
    if record.get("attachments") or record.get("embeds"):
        return True
    if not text:
        return False
    if text.startswith(SKIP_PREFIXES):
        return False
    # Single words and reactions ("lol", "nice", "^") are chat, not lore.
    return len(text) > 12 and len(text.split()) > 2


class Inbox:
    def __init__(self, root: Path, lore_dir: Path | None = None):
        self.root = Path(root)
        self.lore = Path(lore_dir) if lore_dir else (self.root / DEFAULT_LORE)
        self._cache: dict[str, tuple[float, list[dict]]] = {}

    # -- channels and messages -----------------------------------------

    def channels(self) -> list[str]:
        if not self.lore.exists():
            return []
        return sorted(
            p.name for p in self.lore.iterdir()
            if p.is_dir() and (p / "messages.json").exists()
        )

    def _records(self, channel: str) -> list[dict]:
        """Every message in a channel, cached against the file's mtime.

        The campaign channel is half a megabyte of JSON and the inbox is
        consulted on every page load to draw the badge, so re-parsing it each
        time is the difference between a wiki that feels instant and one that
        doesn't.
        """
        path = self.lore / channel / "messages.json"
        if not path.exists():
            return []
        stamp = path.stat().st_mtime
        cached = self._cache.get(channel)
        if cached and cached[0] == stamp:
            return cached[1]
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # A sync interrupted mid-write leaves truncated JSON. Better to
            # show nothing for that channel this minute than to crash the wiki.
            return []
        if not isinstance(records, list):
            return []
        self._cache[channel] = (stamp, records)
        return records

    # -- state ---------------------------------------------------------

    def _load(self) -> dict:
        path = self.root / STATE_FILE
        state: dict = {}
        if path.exists():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = {}
        if not isinstance(state, dict):
            state = {}
        state.setdefault(
            "initialised",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        state.setdefault("note", (
            "Messages at or below each watermark are treated as already in the "
            "wiki. Set a channel's watermark to \"0\" to review it from the "
            "start; delete the entry and it re-adopts the newest message."
        ))
        state.setdefault("watermark", {})
        state.setdefault("filed", [])
        return self._adopt_new_channels(state)

    def _adopt_new_channels(self, state: dict) -> dict:
        """A channel seen for the first time starts from its newest message.

        Adopting per channel rather than once, globally, because the two happen
        in either order: the wiki runs before anything is imported, and a fourth
        channel gets imported months later. Either way the point stands, which
        is that an import is a backlog, not news. Reviewing one from the start
        is a deliberate act: set its watermark to 0.
        """
        changed = False
        for channel in self.channels():
            if channel in state["watermark"]:
                continue
            ids = [int(r["id"]) for r in self._records(channel)
                   if str(r.get("id", "")).isdigit()]
            state["watermark"][channel] = str(max(ids)) if ids else "0"
            changed = True
        if changed:
            self._save(state)
        return state

    def _save(self, state: dict) -> None:
        (self.root / STATE_FILE).write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    # -- the actual question -------------------------------------------

    def cited(self, library) -> set[str]:
        """Message IDs some page already credits as a source."""
        found: set[str] = set()
        for entity in library.all():
            for source in entity.sources:
                found.update(CITED.findall(str(source)))
        return found

    def unfiled(self, library, *, channel: str | None = None,
                limit: int = 50) -> list[Message]:
        state = self._load()
        handled = set(state.get("filed", [])) | self.cited(library)
        watermark = state.get("watermark", {})

        out: list[Message] = []
        for name in self.channels():
            if channel and name != channel:
                continue
            floor = int(watermark.get(name, 0) or 0)
            for record in self._records(name):
                mid = str(record.get("id", ""))
                if not mid.isdigit() or int(mid) <= floor or mid in handled:
                    continue
                if not _worth_reading(record):
                    continue
                out.append(Message(
                    channel=name,
                    id=mid,
                    author=record.get("author", "unknown"),
                    at=record.get("created_at", ""),
                    text=(record.get("content") or "").strip(),
                    attachments=record.get("attachments") or [],
                    reply_to=record.get("reply_to"),
                ))

        out.sort(key=lambda m: int(m.id))
        return out[:limit] if limit else out

    def count(self, library) -> int:
        return len(self.unfiled(library, limit=0))

    def file(self, ids: Iterable[str]) -> int:
        """Mark messages handled. Returns how many were newly filed."""
        state = self._load()
        filed = set(state.get("filed", []))
        before = len(filed)
        filed.update(str(i).strip() for i in ids if str(i).strip().isdigit())
        state["filed"] = sorted(filed)
        self._save(state)
        return len(filed) - before

    def catch_up(self, channel: str | None = None) -> int:
        """Mark everything currently unread as read, without filing it.

        Moves the watermark rather than listing thousands of IDs, so the state
        file stays small however long this runs.
        """
        state = self._load()
        moved = 0
        for name in self.channels():
            if channel and name != channel:
                continue
            ids = [int(r["id"]) for r in self._records(name) if str(r.get("id", "")).isdigit()]
            if not ids:
                continue
            newest = str(max(ids))
            if state["watermark"].get(name) != newest:
                state["watermark"][name] = newest
                moved += 1
        self._save(state)
        return moved

    def attachment_path(self, channel: str, filename: str) -> Path | None:
        """Locate a downloaded attachment, refusing anything outside lore/."""
        if not channel or "/" in filename or "\\" in filename or ".." in filename:
            return None
        if channel not in self.channels():
            return None
        path = (self.lore / channel / "attachments" / filename).resolve()
        try:
            path.relative_to(self.lore.resolve())
        except ValueError:
            return None
        return path if path.exists() else None

    def last_sync(self) -> str:
        """When dnd-scribe last checked Discord, if it has ever said."""
        path = self.lore.parent / ".sync-state.json"
        if not path.exists():
            return ""
        try:
            return str(json.loads(path.read_text(encoding="utf-8")).get("last_run", ""))
        except json.JSONDecodeError:
            return ""
