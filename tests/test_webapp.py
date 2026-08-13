"""Tests for the live wiki: sign-in, per-person views, editing and art.

Sign-in is a name picker with no password, on purpose. So the assertions here
are not about keeping people out; they're about the wiki showing each person
the right thing once they've said who they are, and about editing never
destroying what the editor can't see.

    python tests\\test_webapp.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAIL: list[str] = []
DM_ONLY = "DMONLYCANARY"
NICK_ONLY = "NICKONLYCANARY"
SHARED = "Everyone can read this."


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


sandbox = Path(tempfile.mkdtemp(prefix="webapp-test-"))
shutil.copytree(ROOT / "universe", sandbox / "universe")
for f in ("config.yaml", "people.yaml", "GUIDE.md"):
    shutil.copy(ROOT / f, sandbox / f)
sys.path.insert(0, str(sandbox))

from starlette.applications import Starlette  # noqa: E402
from starlette.middleware import Middleware  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from universe import config as config_mod  # noqa: E402
from universe import people as people_mod  # noqa: E402
from universe import webapp  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

cfg = config_mod.load(sandbox)
# Point the Discord inbox at a sandbox archive. Left alone it resolves to
# ../dnd-scribe/lore, and a test that reads the real campaign archive is a test
# whose results depend on what someone said in Discord this morning.
cfg.raw["lore_dir"] = "lore"
lib = Library(cfg.content_dir)
lib.save(Entity(
    kind="character", slug="wren", name="Wren", summary="An elf fighter.",
    appearance="an elf",
    body=(f"{SHARED}\n\n:::secret dm, wren\n{NICK_ONLY}\n:::\n\n"
          f":::secret dm\n{DM_ONLY}\n:::"),
))
lib.save(Entity(
    kind="lore", slug="dm-notes", name="DM Notes", summary="Behind the screen.",
    appearance="notes", body="Plot twists.", data={"visible_to": ["dm"]},
))
lib.save(Entity(
    kind="place", slug="brindlewood", name="Brindlewood", summary="A township.",
    appearance="a township", links=["lore/dm-notes"],
))

registry = people_mod.load(sandbox)
app = Starlette(
    routes=webapp.build(cfg, lib, registry),
    middleware=[Middleware(SessionMiddleware, secret_key="test-secret",
                           session_cookie="cv")],
)


def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def signed_in_as(key: str) -> TestClient:
    c = client()
    c.post("/wiki/login", data={"who": key})
    return c


print("\n== signed out ==")
c = client()
check("index redirects to sign in", c.get("/wiki/").status_code == 303)
check("redirect target is login", c.get("/wiki/").headers.get("location") == "/wiki/login")
check("a page redirects", c.get("/wiki/character/wren.html").status_code == 303)
check("art redirects", c.get("/wiki/art/character-wren.png").status_code == 303)
check("editing redirects", c.get("/wiki/character/wren/edit").status_code == 303)
check("the art panel redirects", c.get("/wiki/character/wren/art").status_code == 303)

print("\n== the sign-in picker ==")
form = c.get("/wiki/login")
check("renders", form.status_code == 200)
check("offers every name", all(n in form.text for n in
      ("The DM", "Tobias Goreguts", "Timothy Tuttle", "Korran Mossborn", "Wren", "Aelan Viremont")))
check("shows characters alongside", "Wren" in form.text and "Tobias Goreguts" in form.text)
check("no password field", 'type="password"' not in form.text)
check("no email field", 'type="email"' not in form.text)
check("offers adding someone new", "Someone new" in form.text)
check("links to the guide", "/wiki/guide" in form.text)

check("an unknown name is refused",
      "Pick a name" in client().post("/wiki/login", data={"who": "gandalf"}).text)
check("a blank choice is refused",
      "Pick a name" in client().post("/wiki/login", data={"who": ""}).text)

print("\n== signing in ==")
wren = signed_in_as("wren")
check("lands on the wiki", wren.get("/wiki/").status_code == 200)
page = wren.get("/wiki/character/wren.html")
check("public text shown", SHARED in page.text)
check("his own secret shown", NICK_ONLY in page.text)
check("secret is marked", 'class="secret"' in page.text)
check("dm-only secret hidden", DM_ONLY not in page.text)
check("header shows his name", "Wren" in page.text)

print("\n== what each person sees ==")
dm = signed_in_as("dm")
tobias = signed_in_as("tobias")
sam_page = dm.get("/wiki/character/wren.html")
check("dm sees the dm secret", DM_ONLY in sam_page.text)
check("dm sees wren's too", NICK_ONLY in sam_page.text)
check("tobias sees neither",
      DM_ONLY not in tobias.get("/wiki/character/wren.html").text
      and NICK_ONLY not in tobias.get("/wiki/character/wren.html").text)
check("dm opens the restricted page",
      dm.get("/wiki/lore/dm-notes.html").status_code == 200)
check("wren gets 404, not 403",
      wren.get("/wiki/lore/dm-notes.html").status_code == 404)
check("link to it stripped for wren",
      "dm-notes" not in wren.get("/wiki/place/brindlewood.html").text)
check("its art is 404 for wren",
      wren.get("/wiki/art/lore-dm-notes.png").status_code == 404)

print("\n== adding someone new ==")
fresh = client()
r = fresh.post("/wiki/people/new", data={"name": "Dave", "character": "Grimble"})
check("redirects in", r.status_code == 303, str(r.status_code))
check("written to people.yaml", "Dave" in (sandbox / "people.yaml").read_text(encoding="utf-8"))
check("signed in as them", fresh.get("/wiki/").status_code == 200)
check("appears in the picker next time", "Dave" in client().get("/wiki/login").text)
check("a duplicate name is refused",
      "already on the list" in client().post(
          "/wiki/people/new", data={"name": "Dave"}).text)
check("a blank name is refused",
      "Enter a name" in client().post("/wiki/people/new", data={"name": "  "}).text)
check("people.yaml comments survived",
      "# Who can read what." in (sandbox / "people.yaml").read_text(encoding="utf-8"))

print("\n== editing ==")
form = wren.get("/wiki/character/wren/edit")
check("form renders", form.status_code == 200)
check("body is his redacted view", NICK_ONLY in form.text and DM_ONLY not in form.text)
check("warns what is withheld", "cannot read" in form.text)

wren.post("/wiki/character/wren/edit", data={
    "name": "Wren", "summary": "Elf fighter, edited.", "appearance": "an elf",
    "body": f"{SHARED}\n\nRewritten by Wren.", "tags": "", "links": "",
})
raw = (sandbox / "content" / "character" / "wren.md").read_text(encoding="utf-8")
check("the DM's secret survived", DM_ONLY in raw, "this is the whole point")
check("his edit landed", "Rewritten by Wren." in raw)
check("attributed", "edited by Wren" in raw)

wren.post("/wiki/character/wren/edit", data={
    "name": "Wren", "summary": "Elf fighter, edited.", "appearance": "an elf",
    "body": f"{SHARED}\n\nRewritten by Wren.", "tags": "", "links": "",
    "secret_text": "NICKSNEWSECRET", "audience": ["wren", "dm"],
})
check("wren sees his new secret",
      "NICKSNEWSECRET" in wren.get("/wiki/character/wren.html").text)
check("tobias does not",
      "NICKSNEWSECRET" not in tobias.get("/wiki/character/wren.html").text)

print("\n== creating ==")
r = wren.post("/wiki/new", data={
    "kind": "place", "name": "Test Tavern", "summary": "A tavern.",
    "appearance": "a low timber tavern", "body": "Somewhere to drink.",
    "tags": "site", "links": "place/brindlewood",
})
check("redirects to the page", r.status_code == 303)
made = sandbox / "content" / "place" / "test-tavern.md"
check("file written", made.exists())
if made.exists():
    check("attributed", "created by Wren" in made.read_text(encoding="utf-8"))
check("unknown kind refused",
      "pick a type" in wren.post("/wiki/new",
                                 data={"kind": "spaceship", "name": "X"}).text.lower())

print("\n== the art panel ==")
panel = wren.get("/wiki/character/wren/art")
check("renders", panel.status_code == 200, str(panel.status_code))
check("has a prompt field", 'name="prompt"' in panel.text)
check("warns it is slow", "takes roughly a minute" in panel.text)
check("empty prompt refused",
      "Describe the picture" in wren.post(
          "/wiki/character/wren/art", data={"prompt": "  "}).text)

# Attaching is tested without the GPU by planting a file where one would land.
asset_dir = Path(cfg.assets_dir) / "character" / "wren"
asset_dir.mkdir(parents=True, exist_ok=True)
(asset_dir / "custom1-abc123.png").write_bytes(b"\x89PNG\r\n\x1a\n")
r = wren.post("/wiki/character/wren/art",
              data={"action": "pick", "asset": "character/wren/custom1-abc123"})
check("picking attaches it", r.status_code == 303, str(r.status_code))
after = lib.load("character", "wren")
check("recorded as current", after.art[-1] == "character/wren/custom1-abc123",
      str(after.art))
r = wren.post("/wiki/character/wren/art",
              data={"action": "pick", "asset": "lore/dm-notes/default-x"})
check("cannot attach another page's image", "no longer available" in r.text)
check("cannot attach a nonexistent id",
      "no longer available" in wren.post(
          "/wiki/character/wren/art",
          data={"action": "pick", "asset": "character/wren/nope"}).text)

print("\n== art by id is permission checked ==")
check("wren cannot fetch a restricted page's image by id",
      wren.get("/wiki/art/id/lore/dm-notes/default-x.png").status_code == 404)
check("traversal refused",
      wren.get("/wiki/art/id/../../secret.png").status_code in (404, 400))

print("\n== the inbox ==")
import json  # noqa: E402

lore = sandbox / "lore"
(lore / "lore-drop").mkdir(parents=True, exist_ok=True)
BASE = 1400000000000000000


def discord_msg(n: int, text: str) -> dict:
    return {"id": str(BASE + n), "author": "The DM", "author_id": "1",
            "is_bot": False, "created_at": "2026-08-12T19:30:00+00:00",
            "content": text, "attachments": [], "embeds": [],
            "reply_to": None, "reactions": []}


def write_lore(messages: list[dict]) -> None:
    (lore / "lore-drop" / "messages.json").write_text(
        json.dumps(messages), encoding="utf-8")


# Written before anyone looks, so the first read sets the watermark here and
# the backlog behaviour is exercised rather than assumed.
write_lore([discord_msg(1, "The old bridge at Cutter Creek washed out in spring.")])
ic = signed_in_as("wren")
ic.get("/wiki/inbox")
write_lore([
    discord_msg(1, "The old bridge at Cutter Creek washed out in spring."),
    discord_msg(2, "Sister Lethra keeps the records in a locked cabinet."),
])
inbox_page = ic.get("/wiki/inbox")
check("renders", inbox_page.status_code == 200, str(inbox_page.status_code))
check("shows the new message", "Sister Lethra" in inbox_page.text)
check("history is not a backlog", "Cutter Creek" not in inbox_page.text)
check("offers to write it up", "/wiki/new?name=" in inbox_page.text)
check("offers to dismiss it", "Not lore" in inbox_page.text)
check("nav carries a badge", 'class="badge"' in inbox_page.text)
check("nav offers New everywhere",
      '/wiki/new">+ New' in ic.get("/wiki/character/wren.html").text)
check("signed out sees no inbox link",
      "/wiki/inbox" not in client().get("/wiki/login").text)
check("signed out cannot open it",
      client().get("/wiki/inbox").status_code == 303)

prefill = ic.get(f"/wiki/new?name=Sister+Lethra&source=discord:lore-drop:{BASE + 2}"
                 "&body=Keeps+the+records.")
check("prefilled form", "Sister Lethra" in prefill.text and "Keeps the records." in prefill.text)
check("says where it came from", "Written up from a message" in prefill.text)
ic.post("/wiki/new", data={
    "kind": "character", "name": "Sister Lethra", "summary": "A record keeper.",
    "appearance": "a stooped woman in bog-green robes", "body": "Keeps the records.",
    "tags": "", "links": "", "source": f"discord:lore-drop:{BASE + 2}",
})
made = sandbox / "content" / "character" / "sister-lethra.md"
check("page written", made.exists())
if made.exists():
    check("credits the message",
          f"discord:lore-drop:{BASE + 2}" in made.read_text(encoding="utf-8"))
check("and it leaves the inbox", "Sister Lethra" not in ic.get("/wiki/inbox").text,
      "citing the source is enough; no second button")

write_lore([
    discord_msg(1, "The old bridge at Cutter Creek washed out in spring."),
    discord_msg(2, "Sister Lethra keeps the records in a locked cabinet."),
    discord_msg(3, "Does anyone remember where we left the cart?"),
])
check("next one waiting", "left the cart" in ic.get("/wiki/inbox").text)
ic.post("/wiki/inbox", data={"id": str(BASE + 3)})
check("dismissing works", "left the cart" not in ic.get("/wiki/inbox").text)
check("empty inbox says so", "Nothing waiting" in ic.get("/wiki/inbox").text)

(lore / "lore-drop" / "attachments").mkdir(parents=True, exist_ok=True)
(lore / "lore-drop" / "attachments" / "9-map.png").write_bytes(b"\x89PNG\r\n\x1a\n")
check("serves an attachment",
      ic.get("/wiki/inbox/att/lore-drop/9-map.png").status_code == 200)
check("refuses traversal",
      ic.get("/wiki/inbox/att/lore-drop/..%2F..%2Fpeople.yaml").status_code in (404, 400))
check("attachments need a login",
      client().get("/wiki/inbox/att/lore-drop/9-map.png").status_code == 303)

print("\n== the guide ==")
g = client().get("/wiki/guide")
check("readable signed out", g.status_code == 200)
check("carries no secret", DM_ONLY not in g.text and NICK_ONLY not in g.text)

print("\n== connect ==")
conn = wren.get("/wiki/connect")
check("renders", conn.status_code == 200)
check("shows his name", "Wren" in conn.text)
check("offers a token", "Bearer" in conn.text)

print("\n== sign out ==")
check("logout redirects", wren.get("/wiki/logout").status_code == 303)
check("session cleared", wren.get("/wiki/").status_code == 303)

shutil.rmtree(sandbox, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
