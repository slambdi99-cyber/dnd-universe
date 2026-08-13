"""Tests for the Discord inbox: what counts as new, and what stops being new.

The interesting cases are all about *not* nagging people. An inbox that shows
the same message forever, or that opens with four years of backlog, is an inbox
nobody opens twice.

    python tests\\test_inbox.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe.entities import Entity, Library  # noqa: E402
from universe.inbox import Inbox  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


sandbox = Path(tempfile.mkdtemp(prefix="inbox-test-"))
lore = sandbox / "lore"
lib = Library(sandbox / "content")

# Snowflakes are ordered, and the code relies on that, so the fixtures use
# realistic increasing IDs rather than 1, 2, 3.
BASE = 1400000000000000000


def msg(n: int, text: str, **kw) -> dict:
    return {
        "id": str(BASE + n),
        "author": kw.get("author", "The DM"),
        "author_id": "REDACTED",
        "is_bot": kw.get("is_bot", False),
        "created_at": f"2026-08-{10 + n % 20:02d}T19:30:00+00:00",
        "content": text,
        "attachments": kw.get("attachments", []),
        "embeds": [],
        "reply_to": None,
        "reactions": [],
    }


def write(channel: str, messages: list[dict]) -> None:
    d = lore / channel
    d.mkdir(parents=True, exist_ok=True)
    (d / "messages.json").write_text(json.dumps(messages), encoding="utf-8")


write("lore-drop", [
    msg(1, "The Everpool is fed by a spring nobody has found the source of."),
    msg(2, "lol"),
])
write("dnd-campaign", [
    msg(3, "Session tonight at 7?"),
])

print("\n== first run ==")
inbox = Inbox(sandbox, lore)
check("finds the channels", inbox.channels() == ["dnd-campaign", "lore-drop"],
      str(inbox.channels()))
check("history is not a backlog", inbox.count(lib) == 0,
      "everything already imported is treated as handled")
state = json.loads((sandbox / ".inbox.json").read_text(encoding="utf-8"))
check("watermark recorded per channel",
      set(state["watermark"]) == {"lore-drop", "dnd-campaign"}, str(state["watermark"]))
check("says so in the file", "already in the wiki" in state["note"])

print("\n== a channel imported later ==")
write("session-notes", [msg(11, "Wrote up everything from the last three months.")])
later = Inbox(sandbox, lore)
check("its history is a backlog too, not news", later.count(lib) == 0,
      "the wiki often runs before a channel is ever imported")
check("watermark adopted for it",
      json.loads((sandbox / ".inbox.json").read_text(encoding="utf-8"))
      ["watermark"].get("session-notes") == str(BASE + 11))
shutil.rmtree(lore / "session-notes")

print("\n== something new arrives ==")
write("lore-drop", [
    msg(1, "The Everpool is fed by a spring nobody has found the source of."),
    msg(2, "lol"),
    msg(4, "Sister Lethra keeps the Bogwatchers' records in a locked cabinet."),
    msg(5, "nice"),
    msg(6, "", is_bot=False),
    msg(7, "Rolled a nat 20 finally", is_bot=True),
])
inbox = Inbox(sandbox, lore)
waiting = inbox.unfiled(lib)
check("only the real one shows", len(waiting) == 1, f"{[w.text[:20] for w in waiting]}")
check("it's the right one", waiting and "Sister Lethra" in waiting[0].text)
check("short chat filtered", all("nice" != w.text for w in waiting))
check("empty message filtered", all(w.text for w in waiting))
check("bot filtered", all(w.author != "The DM" or "nat 20" not in w.text for w in waiting))
check("source is citable", waiting[0].source == f"discord:lore-drop:{BASE + 4}",
      waiting[0].source)

print("\n== writing it up clears it ==")
lib.save(Entity(
    kind="character", slug="sister-lethra", name="Sister Lethra",
    summary="Keeper of the Bogwatchers' records.",
    sources=[f"discord:lore-drop:{BASE + 4}", "created by Wren on the wiki"],
))
check("cited message drops out", inbox.count(lib) == 0,
      "a page citing it is the message being dealt with")
check("cited() sees it", str(BASE + 4) in inbox.cited(lib))

print("\n== a date-shaped source is not a message id ==")
lib.save(Entity(kind="lore", slug="old", name="Old",
                sources=["discord:lore-drop:2026-08-13"]))
check("not mistaken for an id", not any(
    c == "2026-08-13" for c in inbox.cited(lib)))

print("\n== filing by hand ==")
write("lore-drop", [
    msg(1, "The Everpool is fed by a spring nobody has found the source of."),
    msg(4, "Sister Lethra keeps the Bogwatchers' records in a locked cabinet."),
    msg(8, "Does anyone remember where we left the cart last session?"),
])
inbox = Inbox(sandbox, lore)
check("the question is waiting", inbox.count(lib) == 1, str(inbox.count(lib)))
check("filing reports one", inbox.file([str(BASE + 8)]) == 1)
check("and it's gone", inbox.count(lib) == 0)
check("filing twice is a no-op", inbox.file([str(BASE + 8)]) == 0)
check("junk ids ignored", inbox.file(["nope", ""]) == 0)

print("\n== catch up ==")
write("dnd-campaign", [
    msg(3, "Session tonight at 7?"),
    msg(9, "Reminder that we are skipping next week for the holiday."),
    msg(10, "Also I finally levelled Korran to 5, sheet is updated."),
])
inbox = Inbox(sandbox, lore)
check("two waiting", inbox.count(lib) == 2, str(inbox.count(lib)))
check("one channel filter works",
      len(inbox.unfiled(lib, channel="lore-drop")) == 0)
inbox.catch_up("dnd-campaign")
check("catch up clears them", inbox.count(lib) == 0)
check("state file stayed small",
      len(json.loads((sandbox / ".inbox.json").read_text(encoding="utf-8"))["filed"]) == 1,
      "catch_up moves the watermark rather than listing IDs")

print("\n== attachments ==")
(lore / "lore-drop" / "attachments").mkdir(parents=True, exist_ok=True)
(lore / "lore-drop" / "attachments" / "123-map.png").write_bytes(b"\x89PNG")
(sandbox / "secret.txt").write_text("nope", encoding="utf-8")
check("finds a real one",
      inbox.attachment_path("lore-drop", "123-map.png") is not None)
check("refuses traversal",
      inbox.attachment_path("lore-drop", "../../secret.txt") is None)
check("refuses a backslash",
      inbox.attachment_path("lore-drop", "..\\secret.txt") is None)
check("refuses an unknown channel",
      inbox.attachment_path("made-up", "123-map.png") is None)
check("refuses a missing file",
      inbox.attachment_path("lore-drop", "nothing.png") is None)

print("\n== broken input ==")
(lore / "lore-drop" / "messages.json").write_text("{ truncated", encoding="utf-8")
inbox = Inbox(sandbox, lore)
check("half-written json doesn't crash the wiki", inbox.count(lib) == 0)

missing = Inbox(sandbox, sandbox / "nowhere")
check("a missing lore folder is empty, not an error", missing.channels() == [])

shutil.rmtree(sandbox, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
