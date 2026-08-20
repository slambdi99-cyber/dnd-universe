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
check("changelog redirects", c.get("/wiki/changelog").status_code == 303)

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
change_page = wren.get("/wiki/changelog")
check("changelog renders", change_page.status_code == 200, str(change_page.status_code))
check("changelog is in the nav", "/wiki/changelog" in page.text)

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
check("records explicit active art",
      after.data.get("active_art") == "character/wren/custom1-abc123",
      str(after.data))
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

from universe import site as site_mod  # noqa: E402

print("\n== search survives the deferred index ==")
# The index is served separately by /wiki/search.js, which is deferred, while
# SEARCH_JS is inline and runs first. It must therefore read window.__INDEX__
# per query; a copy taken at load time is always empty, and every search on the
# live site answers "Nothing matches that."
js = site_mod.SEARCH_JS
check("index is not captured at load", "const idx = window.__INDEX__" not in js)
check("index is read per query", "idx()" in js)
page_html = wren.get("/wiki/character/wren.html").text
check("live page defers the index", 'src="/wiki/search.js" defer' in page_html)
check("live page does not inline the index", "window.__INDEX__=[{" not in page_html)
check("the index endpoint serves the pages",
      "Wren" in wren.get("/wiki/search.js").text)
check("results are ranked, not index order", "sort(" in js and "rank(" in js)

print("\n== card thumbnails open the page ==")
card = site_mod._cards(
    [Entity(kind="place", slug="brindlewood", name="Brindlewood", summary="A township.")],
    {"place/brindlewood": "place-brindlewood.png"}, "/wiki/")
check("the thumbnail is a link", '<a class="thumb" href="/wiki/place/brindlewood.html"'
      in card, card[:120])
check("it goes where the title goes", card.count('href="/wiki/place/brindlewood.html"') == 2)
check("it is skipped by tab", 'tabindex="-1"' in card)
check("and not announced twice", 'aria-hidden="true"' in card)
nopic = site_mod._cards(
    [Entity(kind="place", slug="brindlewood", name="Brindlewood", summary="A township.")],
    {}, "/wiki/")
check("a card with no art shows its kind's icon",
      'thumb noart' in nopic and "<svg" in nopic,
      "same shape as its neighbours instead of collapsing to a caption")

# The real `images_for` always puts a `?v=` on the name so the week-long cache
# lets go when somebody picks a different picture. The fixture above leaves it
# out, and that is exactly how `?v=...?size=card` shipped: a second `?` is not
# a separator, so `size` stopped being a parameter, the route fell through to
# the full-size original, and thirty of those went out to draw thirty
# thumbnails. So ask the question the way the site asks it.
import re  # noqa: E402
from urllib.parse import parse_qs, urlparse  # noqa: E402

versioned = site_mod._cards(
    [Entity(kind="place", slug="brindlewood", name="Brindlewood", summary="A township.")],
    {"place/brindlewood": "place-brindlewood.png?v=upload-966b3654dd432f5a"}, "/wiki/")
src = re.search(r'<img src="([^"]+)"', versioned).group(1)
query = parse_qs(urlparse(src).query)
check("a versioned card still asks for a thumbnail",
      query.get("size") == ["card"], src)
check("and the version survives alongside it",
      query.get("v") == ["upload-966b3654dd432f5a"], src)
check("the card states its size, so the grid lays out once",
      f'width="{site_mod.THUMB_PX}"' in versioned)

hero = site_mod.render_body(
    site_mod.schema_mod.load(sandbox),
    lib.load("place", "brindlewood"), lib,
    {"place/brindlewood": "place-brindlewood.png?v=upload-966b3654dd432f5a"},
    "/wiki/", site_mod.access_mod.Viewer.nobody(), set())
hero_src = re.search(r'<img class="hero" src="([^"]+)"', hero)
check("the hero asks for its own size too",
      hero_src is not None
      and parse_qs(urlparse(hero_src.group(1)).query).get("size") == ["page"],
      hero_src.group(1) if hero_src else "no hero img")

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

print("\n== attaching a file from the inbox ==")
# A map posted in Discord should land on a page without a download-reupload
# round trip through someone's phone.
att_dir = lore / "lore-drop" / "attachments"
att_dir.mkdir(parents=True, exist_ok=True)
(att_dir / "map.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"not really a map")
write_lore([
    discord_msg(1, "The old bridge at Cutter Creek washed out in spring."),
    discord_msg(2, "Sister Lethra keeps the records in a locked cabinet."),
    discord_msg(3, "Does anyone remember where we left the cart?"),
    {**discord_msg(4, "tactical grid from tonight"),
     "attachments": [{"filename": "map.png", "file": "map.png",
                      "content_type": "image/png"}]},
])
inbox_page = ic.get("/wiki/inbox")
check("a message with a file offers an attach target",
      "Attach the file to" in inbox_page.text)
check("the dropdown hides what the viewer can't see",
      "DM Notes" not in inbox_page.text)
refused = ic.post("/wiki/inbox", data={"action": "attach",
                                       "id": str(BASE + 4),
                                       "page": "lore/dm-notes"})
check("a hidden page is not a valid target",
      "error=" in refused.headers.get("location", ""),
      "the dropdown never offered it; a hand-made POST must not work either")
attached = ic.post("/wiki/inbox", data={"action": "attach",
                                        "id": str(BASE + 4),
                                        "page": "place/brindlewood"})
check("attaching redirects with a note", attached.status_code == 303
      and "note=" in attached.headers.get("location", ""))
bw = lib.load("place", "brindlewood")
bw_files = bw.data.get("files") or []
check("the file is on the page",
      any(f.get("name") == "map.png" for f in bw_files))
check("the page cites the message",
      f"discord:lore-drop:{BASE + 4}" in bw.sources)
check("so the message leaves the inbox",
      "tactical grid" not in ic.get("/wiki/inbox").text)
check("and the file downloads from the page",
      bool(bw_files)
      and ic.get(f"/wiki/file/{bw_files[0]['id']}").status_code == 200)

(lore / "lore-drop" / "attachments").mkdir(parents=True, exist_ok=True)
(lore / "lore-drop" / "attachments" / "9-map.png").write_bytes(b"\x89PNG\r\n\x1a\n")
check("serves an attachment",
      ic.get("/wiki/inbox/att/lore-drop/9-map.png").status_code == 200)
check("refuses traversal",
      ic.get("/wiki/inbox/att/lore-drop/..%2F..%2Fpeople.yaml").status_code in (404, 400))
check("attachments need a login",
      client().get("/wiki/inbox/att/lore-drop/9-map.png").status_code == 303)

print("\n== uploading a picture ==")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
r = wren.post("/wiki/character/wren/art",
              data={"action": "upload"},
              files={"file": ("mine.png", PNG, "image/png")})
check("uploaded art lands on the page", r.status_code == 303, str(r.status_code))
after = lib.load("character", "wren")
check("recorded as current", after.art[-1].startswith("character/wren/upload-"),
      str(after.art[-1]))
check("and it serves",
      wren.get(f"/wiki/art/id/{after.art[-1]}.png").status_code == 200)
uploaded_page = wren.get("/wiki/character/wren.html").text
check("page image URL changes with selected art",
      f"/wiki/art/character-wren.png?v={after.art[-1].split('/')[-1]}" in uploaded_page)
panel = wren.get("/wiki/character/wren/art").text
check("current art can be marked inactive", "Mark inactive" in panel)
r = wren.post("/wiki/character/wren/art",
              data={"action": "remove", "asset": after.art[-1]})
check("marking inactive redirects to art panel", r.status_code == 303,
      str(r.status_code))
after_inactive = lib.load("character", "wren")
check("inactive art stays in the gallery list", after.art[-1] in after_inactive.art,
      str(after_inactive.art))
check("inactive art is no longer active",
      after_inactive.data.get("active_art") == "",
      str(after_inactive.data))
check("inactive art drops off the page",
      "/wiki/art/character-wren.png" not in wren.get("/wiki/character/wren.html").text)
check("inactive art can be picked again",
      "Use this one" in wren.get("/wiki/character/wren/art").text)
bad = wren.post("/wiki/character/wren/art", data={"action": "upload"},
                files={"file": ("evil.png", SVG, "image/svg+xml")})
# Apostrophes come back HTML-escaped, so match on text that has none.
check("an SVG named .png is refused",
      "accepted" in bad.text and "SVG" in bad.text,
      "the bytes decide, not the name")

print("\n== files on a page ==")
panel = wren.get("/wiki/character/wren/files")
check("panel renders", panel.status_code == 200)
check("says nothing is attached yet", "Nothing attached yet" in panel.text)
r = wren.post("/wiki/character/wren/files",
              files={"file": ("map.pdf", b"%PDF-1.7\n" + b"\x00" * 40,
                              "application/pdf")})
check("upload accepted", "Added map.pdf" in r.text)
check("listed on the page",
      "map.pdf" in wren.get("/wiki/character/wren.html").text)
entity = lib.load("character", "wren")
file_id = entity.data["files"][0]["id"]
got = wren.get(f"/wiki/file/{file_id}")
check("downloads", got.status_code == 200)
check("as an attachment, never inline",
      "attachment" in got.headers.get("content-disposition", ""),
      got.headers.get("content-disposition", ""))
check("with the right type", got.headers["content-type"].startswith("application/pdf"))
check("and nosniff", got.headers.get("x-content-type-options") == "nosniff")
check("a viewer who can't see the page can't have the file",
      tobias.get(f"/wiki/file/{file_id}").status_code in (200, 404),
      "wren is public, so this is only a smoke test")
check("signed out cannot download",
      client().get(f"/wiki/file/{file_id}").status_code == 303)
check("traversal refused",
      wren.get("/wiki/file/../../people.yaml").status_code in (404, 400, 303))

# The real permission check: a file on a page only The DM can see.
sam_entity = lib.load("lore", "dm-notes")
sam_entity.data["files"] = [{"id": "lore/dm-notes/upload-deadbeef",
                             "name": "plot.pdf", "type": "application/pdf",
                             "size": 10}]
lib.save(sam_entity)
check("wren cannot fetch a restricted page's file",
      wren.get("/wiki/file/lore/dm-notes/upload-deadbeef").status_code == 404)

r = wren.post("/wiki/character/wren/files",
              data={"action": "remove", "file": file_id})
check("removing works", "Removed from this page" in r.text)
check("gone from the page",
      "map.pdf" not in wren.get("/wiki/character/wren.html").text)

print("\n== structure ==")
s = wren.get("/wiki/structure")
check("renders", s.status_code == 200)
check("lists the kinds", "character" in s.text and "Places" in s.text)
check("in the nav", "/wiki/structure" in wren.get("/wiki/").text)
check("signed out cannot open it",
      client().get("/wiki/structure").status_code == 303)
r = wren.post("/wiki/structure", data={"action": "add_kind", "key": "ship",
                                       "label": "Ships", "in_nav": "on"})
check("a player can add a kind", "Added ship" in r.text,
      "no DM tier: anyone connected can reshape the world")
check("it appears in the nav", ">Ships<" in wren.get("/wiki/").text)
check("and in the new-page form", ">Ships<" in wren.get("/wiki/new").text)
r = wren.post("/wiki/structure", data={"action": "add_kind", "key": "ship"})
check("duplicates refused", "already exists" in r.text)
r = wren.post("/wiki/structure", data={"action": "remove_kind", "key": "ship"})
check("and removed again", "Removed ship" in r.text)
r = wren.post("/wiki/structure", data={"action": "set_site",
                                       "name": "Test Title", "tagline": "A line."})
check("the site can be renamed", "Test Title" in r.text)
check("the header changes", "Test Title" in wren.get("/wiki/").text)
wren.post("/wiki/structure", data={"action": "set_site", "name": "The Buried Star"})
r = wren.post("/wiki/structure", data={"action": "set_home",
                                       "home": "not: valid: yaml: at: all"})
check("bad YAML is reported, not raised",
      "valid YAML" in r.text or "parse" in r.text,
      "a broken paste must not 500 the page")

print("\n== switching person ==")
# The bug this covers: /wiki/login used to redirect to the front page whenever
# someone was already signed in, so clearing the passphrase dropped you on the
# homepage as whoever you were last time and the picker was unreachable.
already = signed_in_as("wren")
switch = already.get("/wiki/login")
check("the picker is reachable while signed in", switch.status_code == 200,
      str(switch.status_code))
check("it says so rather than looking broken", "signed in already" in switch.text)
check("the current person is marked", 'class="who on"' in switch.text)
check("every other name is still offered", "Tobias Goreguts" in switch.text)
already.post("/wiki/login", data={"who": "tobias"})
check("switching actually switches",
      "Tobias Goreguts" in already.get("/wiki/").text)
check("and the old identity is gone",
      NICK_ONLY not in already.get("/wiki/character/wren.html").text,
      "otherwise you would keep the previous person's secrets")
check("the header offers the switch", "not you?" in already.get("/wiki/").text)

print("\n== the shared passphrase ==")
from universe import gate as gate_mod  # noqa: E402

gate_mod.set_passphrase(sandbox, "peapod-dungeon-test")
stranger = client()
check("the front page now asks for it",
      stranger.get("/wiki/").headers.get("location") == "/wiki/enter")
check("so does the name picker",
      stranger.get("/wiki/login").headers.get("location") == "/wiki/enter",
      "otherwise the picker is the front door")
check("so does adding yourself",
      stranger.post("/wiki/people/new", data={"name": "Mallory"}
                    ).headers.get("location") == "/wiki/enter")
check("and a page",
      stranger.get("/wiki/character/wren.html").headers.get("location") == "/wiki/enter")
check("and its art",
      stranger.get("/wiki/art/character-wren.png").headers.get("location") == "/wiki/enter")
check("and the structure editor",
      stranger.get("/wiki/structure").headers.get("location") == "/wiki/enter")

form = stranger.get("/wiki/enter")
check("the gate renders", form.status_code == 200)
check("as a password field", 'type="password"' in form.text)
check("it does not name the passphrase", "peapod" not in form.text.lower())
check("the guide is still reachable", "/wiki/guide" in form.text,
      "the page explaining how to get in cannot be behind the door")

bad = stranger.post("/wiki/enter", data={"passphrase": "wrong"})
check("a wrong passphrase is refused", "isn't it" in bad.text or "n&#x27;t it" in bad.text)
check("and does not let you in",
      stranger.get("/wiki/").headers.get("location") == "/wiki/enter")
check("empty is refused",
      stranger.post("/wiki/enter", data={"passphrase": ""}).status_code == 200)

good = stranger.post("/wiki/enter", data={"passphrase": "peapod-dungeon-test"})
check("the right one gets in", good.status_code == 303, str(good.status_code))
check("and lands on the picker", good.headers.get("location") == "/wiki/login")
check("which now renders", stranger.get("/wiki/login").status_code == 200)
stranger.post("/wiki/login", data={"who": "wren"})
check("and then the wiki works normally",
      stranger.get("/wiki/").status_code == 200)

# Signing out should not hand the next person a free pass on a shared machine.
stranger.get("/wiki/logout")
check("signing out drops the passphrase too",
      stranger.get("/wiki/").headers.get("location") == "/wiki/enter",
      "a shared laptop should not stay unlocked")

# Sessions that predate the gate are NOT grandfathered. The reason to add a
# passphrase is that the site was reachable by anyone for a while, so the one
# person it must challenge is whoever was already inside.
check("a session from before the gate is challenged too",
      wren.get("/wiki/").headers.get("location") == "/wiki/enter",
      "otherwise a stranger who wandered in keeps a month of access")

gate_mod.clear(sandbox)
check("removing it opens the door again",
      client().get("/wiki/").headers.get("location") == "/wiki/login")

print("\n== the guide ==")
g = client().get("/wiki/guide")
check("readable signed out", g.status_code == 200)
check("carries no secret", DM_ONLY not in g.text and NICK_ONLY not in g.text)

print("\n== connect ==")
conn = wren.get("/wiki/connect")
check("renders", conn.status_code == 200)
check("shows his name", "Wren" in conn.text)
check("offers a token", "Bearer" in conn.text)

print("\n== places inside places ==")
lib.save(Entity(kind="place", slug="copper-vale", name="Copper Vale",
                summary="A low-lying region.", appearance="a region"))
lib.save(Entity(kind="place", slug="valeshire", name="Valeshire",
                summary="A city on the river.", appearance="a city",
                within="place/copper-vale"))
lib.save(Entity(kind="place", slug="the-tavern", name="The Tavern",
                summary="Where everyone drinks.", appearance="a tavern",
                within="place/valeshire"))
# A hidden region with a visible room in it. The room stays readable; the
# trail above it must not appear, because a place name is usually the spoiler.
lib.save(Entity(kind="place", slug="hidden-vault", name="The Hidden Vault",
                summary="Secret.", appearance="a vault",
                within="place/copper-vale", data={"visible_to": ["dm"]}))
lib.save(Entity(kind="place", slug="the-antechamber", name="The Antechamber",
                summary="A room off the vault.", appearance="a room",
                within="place/hidden-vault"))

page = wren.get("/wiki/place/the-tavern.html")
check("a nested place renders", page.status_code == 200)
check("with a trail showing where it is", 'class="trail"' in page.text)
check("naming the region", "Copper Vale" in page.text)
check("and the city", "Valeshire" in page.text)

parent = wren.get("/wiki/place/valeshire.html")
check("a parent lists what is inside it", "Inside Valeshire" in parent.text)
check("naming the child", "The Tavern" in parent.text)
check("with its summary, so a list of names is a list of places",
      "Where everyone drinks" in parent.text)

region = wren.get("/wiki/place/copper-vale.html")
check("a region lists its city", "Valeshire" in region.text)
check("but not its grandchildren",
      "The Tavern" not in region.text.split("Inside Copper Vale")[-1][:400],
      "the city lists its own pubs; a region repeating them indexes nothing")

print("\n== a trail stops at a secret ==")
# The rule that fails silently, checked through the actual site rather than
# the module, because this is the path that renders for a player.
room = wren.get("/wiki/place/the-antechamber.html")
check("the room itself is readable", room.status_code == 200)
check("no trail at all for a player", 'class="trail"' not in room.text,
      "showing Copper Vale alone would say something is hidden in between")
check("and the hidden name is nowhere on it", "Hidden Vault" not in room.text)

dm_room = dm.get("/wiki/place/the-antechamber.html")
check("the DM sees the whole trail", 'class="trail"' in dm_room.text)
check("including the secret one", "Hidden Vault" in dm_room.text)
check("a hidden parent does not hide the room from anyone",
      wren.get("/wiki/place/the-antechamber.html").status_code == 200)

print("\n== moving a place ==")
form = wren.get("/wiki/place/the-tavern/edit")
check("the edit form offers somewhere to put it", 'name="within"' in form.text)
check("with its current parent selected",
      'value="place/valeshire" selected' in form.text)
check("it is not offered as its own parent",
      'value="place/the-tavern"' not in form.text)
# The vault holds the antechamber, so offering the antechamber as the vault's
# own parent would let the form build a loop it then has to refuse.
vault_form = dm.get("/wiki/place/hidden-vault/edit")
check("nor is anything already inside it",
      'value="place/the-antechamber"' not in vault_form.text,
      "the form must not offer a choice it would then reject")
check("but an unrelated place still is",
      'value="place/valeshire"' in vault_form.text)

moved = wren.post("/wiki/place/the-tavern/edit",
                  data={"name": "The Tavern", "summary": "Where everyone drinks.",
                        "appearance": "a tavern", "body": "", "tags": "",
                        "links": "", "within": "place/copper-vale"})
check("saving a move redirects", moved.status_code == 303)
check("and it moved", lib.load("place", "the-tavern").within == "place/copper-vale")

# A hand-made POST, bypassing the dropdown that already excludes loops.
wren.post("/wiki/place/copper-vale/edit",
          data={"name": "Copper Vale", "summary": "A low-lying region.",
                "appearance": "a region", "body": "", "tags": "", "links": "",
                "within": "place/the-tavern"})
check("a loop is refused even when posted directly",
      lib.load("place", "copper-vale").within != "place/the-tavern",
      "a region inside a pub inside that region renders forever")

print("\n== the review page ==")
shape = wren.get("/wiki/places")
check("renders", shape.status_code == 200)
check("lists every place a viewer may see", "Valeshire" in shape.text)
check("and not the ones they may not", "Hidden Vault" not in shape.text)
check("the DM sees the hidden one", "Hidden Vault" in dm.get("/wiki/places").text)

print("\n== indexes keep hidden pages off the screen ==")
# Indexes are what gets projected at the table, so a hidden page stays off
# them for everyone -- the DM included. The review page above is the DM's
# tool for finding them; the index is the table's.
kind_index = dm.get("/wiki/place/index.html")
check("the kind index still lists visible places", "Valeshire" in kind_index.text)
check("but not the hidden one, even for the DM",
      "Hidden Vault" not in kind_index.text,
      "search and the review page still reach it; the index gets projected")
home = dm.get("/wiki/")
check("nor does the front page", "Hidden Vault" not in home.text)
# Search suggestions surface under a typed letter on the same projected
# screen, so the search index follows the index rule, not the page rule.
search = dm.get("/wiki/search.js")
check("search index skips the hidden page, even for the DM",
      "Hidden Vault" not in search.text,
      "a hidden name in the suggestions is the spoiler itself")
check("but still carries visible ones", "Valeshire" in search.text)

print("\n== hiding pages at will: met, known, seen ==")
lib.save(Entity(kind="character", slug="stranger", name="The Stranger",
                summary="Nobody knows them yet.", appearance="a hood",
                body="Public prose.\n\n:::visited\nUPONMEETING\n:::"))
check("a fresh page is public",
      wren.get("/wiki/character/stranger.html").status_code == 200)
check("its upon-meeting prose is fenced",
      "UPONMEETING" not in wren.get("/wiki/character/stranger.html").text)
dm.post("/wiki/character/stranger/visited", data={"set": "false"})
check("the DM hides them at will",
      wren.get("/wiki/character/stranger.html").status_code == 404)
check("the file says met: false",
      lib.load("character", "stranger").data.get("met") is False)
dm_view = dm.get("/wiki/character/stranger.html")
check("the DM still reads the page", dm_view.status_code == 200)
check("with the kind's verb on the chip", "hidden until marked met" in dm_view.text,
      "no revealed_by sources: the only key is the DM's own button, say so")
check("a player cannot press the button",
      wren.post("/wiki/character/stranger/visited",
                data={"set": "true"}).status_code == 404)
dm.post("/wiki/character/stranger/visited", data={"set": "true"})
met = wren.get("/wiki/character/stranger.html")
check("marking met reveals them", met.status_code == 200)
check("and opens the upon-meeting prose", "UPONMEETING" in met.text)

print("\n== encounters cascade ==")
# Visit the shop and you have met the shopkeeper: the gate is the cascade.
lib.save(Entity(kind="place", slug="wick-shop", name="The Wick Shop",
                summary="Candles and charms.", appearance="a shop"))
lib.save(Entity(kind="character", slug="shopkeep", name="The Shopkeep",
                summary="Keeps the wick shop.", appearance="an apron",
                body="Runs the counter.\n\n:::visited\nMETBYVISIT\n:::",
                data={"revealed_by": ["place/wick-shop"]}))
check("gated on an unvisited shop, so hidden",
      wren.get("/wiki/character/shopkeep.html").status_code == 404)
wiring = dm.get("/wiki/character/shopkeep.html")
check("the DM reads the gate as a section of the page",
      "Revealed by <span" in wiring.text and "The Wick Shop" in wiring.text)
check("and the chip names the key inline",
      "hidden until met &middot; via" in wiring.text,
      "a chip that just says 'hidden until met' points at nothing")
shop_page = dm.get("/wiki/place/wick-shop.html")
check("and the same wire from the other end",
      "Reveals <span" in shop_page.text and "The Shopkeep" in shop_page.text)
check("with the encounter state on the card",
      "not yet encountered" in shop_page.text)
check("players never see the wiring",
      "Reveals <span" not in wren.get("/wiki/place/wick-shop.html").text)
dm.post("/wiki/place/wick-shop/visited")  # the original toggle, no set field
keeper = wren.get("/wiki/character/shopkeep.html")
check("visiting the shop reveals the shopkeep", keeper.status_code == 200)
check("and counts as meeting them: the upon-meeting prose is open",
      "METBYVISIT" in keeper.text)
dm.post("/wiki/place/wick-shop/visited")  # toggle back off
check("un-visiting takes them away again",
      wren.get("/wiki/character/shopkeep.html").status_code == 404,
      "the cascade wrote only the derived flag, so it retracts cleanly")

print("\n== wiring reveals from the page ==")
check("the sections carry an add form",
      'action="/wiki/place/wick-shop/wire"' in dm.get("/wiki/place/wick-shop.html").text)
check("with the whole library as its picker",
      'datalist id="allpages"' in dm.get("/wiki/place/wick-shop.html").text)
lib.save(Entity(kind="character", slug="regular", name="The Regular",
                summary="Always at the counter.", appearance="a mug"))
r = dm.post("/wiki/place/wick-shop/wire",
            data={"direction": "reveals", "target": "character/regular"})
check("wiring 'reveals' redirects home", r.status_code == 303)
check("and writes the gate on the target",
      "place/wick-shop" in (lib.load("character", "regular").data.get("revealed_by") or []))
r = dm.post("/wiki/character/regular/wire",
            data={"direction": "revealed_by", "target": "The Shopkeep"})
check("an exact name resolves like a ref", r.status_code == 303, str(r.status_code))
check("and lands on this page's own gate",
      "character/shopkeep" in lib.load("character", "regular").data["revealed_by"])
check("wiring twice records once",
      dm.post("/wiki/place/wick-shop/wire",
              data={"direction": "reveals", "target": "character/regular"}).status_code == 303
      and (lib.load("character", "regular").data["revealed_by"]).count("place/wick-shop") == 1)
check("a page cannot reveal itself",
      dm.post("/wiki/character/regular/wire",
              data={"direction": "revealed_by", "target": "character/regular"}).status_code == 400)
check("an unknown target is refused",
      dm.post("/wiki/character/regular/wire",
              data={"direction": "revealed_by", "target": "nowhere"}).status_code == 400)
check("players cannot wire",
      wren.post("/wiki/place/wick-shop/wire",
                data={"direction": "reveals", "target": "character/regular"}).status_code == 404)
check("nor do they see the forms",
      'wire"' not in wren.get("/wiki/place/wick-shop.html").text)
# Wiring to a page the party already stands in reveals in the same breath.
dm.post("/wiki/place/wick-shop/visited", data={"set": "true"})
check("a wire to visited ground is live at once",
      wren.get("/wiki/character/regular.html").status_code == 200)
dm.post("/wiki/place/wick-shop/visited", data={"set": "clear"})

print("\n== the reveal web ==")
board = dm.get("/wiki/reveals")
check("the DM gets the board", board.status_code == 200)
check("wired pages are on it",
      "The Shopkeep" in board.text and "The Wick Shop" in board.text)
check("cards carry their wires for the script",
      'data-srcs="place/wick-shop"' in board.text)
check("and their toggles", 'name="back" value="reveals"' in board.text)
check("players get a 404, not a hint",
      wren.get("/wiki/reveals").status_code == 404)
check("the menu offers it to the DM",
      "/wiki/reveals" in dm.get("/wiki/").text)
check("but not to players", "/wiki/reveals" not in wren.get("/wiki/").text)
r = dm.post("/wiki/place/wick-shop/visited",
            data={"set": "true", "back": "reveals"})
check("a board toggle returns to the board",
      r.status_code == 303 and r.headers["location"] == "/wiki/reveals")
check("and the flag moved", lib.load("place", "wick-shop").data.get("visited") is True)
dm.post("/wiki/place/wick-shop/visited", data={"set": "clear", "back": "reveals"})

print("\n== the DM borrows a player's eyes ==")
mask = signed_in_as("dm")
check("the site menu offers View as", "View as" in mask.get("/wiki/").text)
check("players are not offered it", "View as" not in wren.get("/wiki/").text)
mask.post("/wiki/impersonate", data={"who": "wren"})
front = mask.get("/wiki/")
check("the header says whose eyes", "seeing as Wren" in front.text)
check("a concealed page is gone for the mask too",
      mask.get("/wiki/character/shopkeep.html").status_code == 404)
check("so is a dm-only page",
      mask.get("/wiki/lore/dm-notes.html").status_code == 404)
blocked = mask.post("/wiki/character/stranger/edit", data={
    "name": "The Stranger", "summary": "VANDALIZED", "appearance": "x",
    "body": "", "tags": "", "links": ""})
check("writes are refused while masked",
      blocked.headers.get("location") == "/wiki/"
      and lib.load("character", "stranger").summary != "VANDALIZED",
      "an edit through the mask would land in the player's name")
check("players cannot impersonate",
      wren.post("/wiki/impersonate", data={"who": "dm"}).status_code == 404)
mask.post("/wiki/impersonate", data={})  # the back-to-yourself button
check("the mask comes off", "seeing as" not in mask.get("/wiki/").text)
check("and the DM's eyes are back",
      mask.get("/wiki/lore/dm-notes.html").status_code == 200)

print("\n== the DM wires gates from the edit form ==")
lib.save(Entity(kind="item", slug="ledger-book", name="Ledger Book",
                summary="A ledger.", appearance="a ledger"))
ledger_form = {"name": "Ledger Book", "summary": "A ledger.",
               "appearance": "a ledger", "body": "", "tags": "", "links": ""}
check("the DM's form offers the gate",
      'name="revealed_by"' in dm.get("/wiki/item/ledger-book/edit").text)
check("a player's form does not",
      'name="revealed_by"' not in wren.get("/wiki/item/ledger-book/edit").text)
dm.post("/wiki/item/ledger-book/edit",
        data={**ledger_form, "revealed_by": "place/wick-shop"})
check("saving a gate hides the item",
      wren.get("/wiki/item/ledger-book.html").status_code == 404)
check("and the form reads it back",
      "place/wick-shop" in dm.get("/wiki/item/ledger-book/edit").text)
dm.post("/wiki/place/wick-shop/visited")
check("the gate obeys the source's flag",
      wren.get("/wiki/item/ledger-book.html").status_code == 200)
dm.post("/wiki/item/ledger-book/edit",
        data={**ledger_form, "revealed_by": "place/wick-shop"})
check("a gate re-saved against a visited source stays open",
      wren.get("/wiki/item/ledger-book.html").status_code == 200,
      "the edit handler recomputes, so the gate is born open")
dm.post("/wiki/place/wick-shop/visited")  # unvisit
check("and closes when the source unvisits",
      wren.get("/wiki/item/ledger-book.html").status_code == 404)
wren.post("/wiki/character/stranger/edit",
          data={"name": "The Stranger", "summary": "Nobody knows them yet.",
                "appearance": "a hood", "body": "Public prose.", "tags": "",
                "links": "", "revealed_by": "place/wick-shop"})
check("a player smuggling the field changes nothing",
      not lib.load("character", "stranger").data.get("revealed_by"))
dm.post("/wiki/item/ledger-book/edit", data={**ledger_form, "revealed_by": ""})
check("clearing the field opens the gate",
      wren.get("/wiki/item/ledger-book.html").status_code == 200)
check("and drops the bookkeeping with it",
      "revealed" not in (lib.load("item", "ledger-book").data or {}))

print("\n== asking for art where there is no graphics card ==")
# The site now runs on a free server with no GPU. Pressing Art there has to do
# something other than fail, or the feature silently disappears for everyone
# and only the DM, sitting at the machine that draws, ever notices.
from universe import artqueue  # noqa: E402

no_gpu = sandbox / ".no-gpu"
no_gpu.write_text("no card here", encoding="utf-8")
check("the marker file is what decides", cfg.draws_here is False)
art_before = list((lib.load("character", "wren") or Entity("", "", "")).art)
asked = wren.post("/wiki/character/wren/art",
                  data={"prompt": "an elf in a salt-stained coat"})
check("the page answers rather than erroring", asked.status_code == 200)
check("it says the request is queued", "Queued" in asked.text)
check("and does not claim it failed", "Couldn't generate" not in asked.text)
queued = artqueue.pending(sandbox, "character", "wren")
check("the request is on disk for the other machine", len(queued) == 1,
      str(queued))
check("it carries the prompt",
      bool(queued) and queued[0].prompt == "an elf in a salt-stained coat")
check("and who asked", bool(queued) and queued[0].who == "Wren")

# The important half: nothing was drawn, and nothing was attached. A queued
# request must not look like a finished picture. Wren already has an uploaded
# portrait from further up this file, so the claim is that asking added
# nothing, not that the page is bare.
check("the page's art is unchanged",
      list((lib.load("character", "wren") or Entity("", "", "")).art) == art_before,
      "a request that is still in a queue must not appear as a picture")

again = wren.get("/wiki/character/wren/art")
check("the wait is visible on the page", "Waiting for the machine at home" in again.text)
check("the button asks rather than promises", "Ask for three" in again.text)

no_gpu.unlink()
check("removing the marker restores drawing", cfg.draws_here is True)
back = wren.get("/wiki/character/wren/art")
check("at home the button generates", "Generate three" in back.text)

print("\n== sign out ==")
check("logout redirects", wren.get("/wiki/logout").status_code == 303)
check("session cleared", wren.get("/wiki/").status_code == 303)

shutil.rmtree(sandbox, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
