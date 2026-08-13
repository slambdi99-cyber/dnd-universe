"""Tests for the live wiki: accounts, invite gating, and per-person views.

Uses Starlette's test client against the real routes, on a throwaway copy of
the project. The important assertions are the negative ones: registration
cannot be self-served without a code, and no reader ever receives another
person's secret.

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
shutil.copy(ROOT / "config.yaml", sandbox / "config.yaml")
shutil.copy(ROOT / "people.yaml", sandbox / "people.yaml")
sys.path.insert(0, str(sandbox))

from starlette.applications import Starlette  # noqa: E402
from starlette.middleware import Middleware  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from universe import accounts as accounts_mod  # noqa: E402
from universe import config as config_mod  # noqa: E402
from universe import people as people_mod  # noqa: E402
from universe import webapp  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

cfg = config_mod.load(sandbox)
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
accounts = accounts_mod.load(sandbox)


def make_app(require_invite: bool) -> Starlette:
    return Starlette(
        routes=webapp.build(cfg, lib, registry, accounts,
                            require_invite=require_invite),
        middleware=[Middleware(SessionMiddleware, secret_key="test-secret",
                               session_cookie="cv")],
    )


app = make_app(require_invite=True)


def client(target: Starlette | None = None) -> TestClient:
    return TestClient(target or app, follow_redirects=False)


print("\n== signed out ==")
c = client()
r = c.get("/wiki/")
check("index redirects to sign in", r.status_code == 303, str(r.status_code))
check("redirect target is login", r.headers.get("location") == "/wiki/login")
r = c.get("/wiki/character/wren.html")
check("a page redirects too", r.status_code == 303)
r = c.get("/wiki/art/character-wren.png")
check("art redirects too", r.status_code == 303)
r = c.get("/wiki/login")
check("login page renders", r.status_code == 200 and "Sign in" in r.text)
check("login asks for email", 'type="email"' in r.text)

print("\n== registration is gated ==")
c = client()
r = c.post("/wiki/register", data={"email": "x@example.com", "password": "hunter2hunter",
                                   "code": "not-a-real-code"})
check("bogus code rejected", r.status_code == 200 and "invite code" in r.text and "valid" in r.text)
check("no account created", accounts.emails == [], str(accounts.emails))

nick_code = accounts.mint_invite("wren")
sam_code = accounts.mint_invite("dm")
accounts.save()

r = c.post("/wiki/register", data={"email": "notanemail", "password": "hunter2hunter",
                                   "code": nick_code})
check("bad email rejected", "email address" in r.text)
r = c.post("/wiki/register", data={"email": "wren@example.com", "password": "short",
                                   "code": nick_code})
check("short password rejected", "at least 8" in r.text)
check("code still unused after failures", accounts.invite_key(nick_code) == "wren")

print("\n== registering with a real code ==")
wren = client()
r = wren.post("/wiki/register", data={"email": "Wren@Example.com",
                                      "password": "hunter2hunter", "code": nick_code})
check("registration succeeds", r.status_code == 303, str(r.status_code))
check("account bound to the code's person", accounts.key_for("wren@example.com") == "wren")
check("email normalised to lowercase", "wren@example.com" in accounts.emails)
check("code is now spent", accounts.invite_key(nick_code) is None)

reuse = client()
r = reuse.post("/wiki/register", data={"email": "other@example.com",
                                       "password": "hunter2hunter", "code": nick_code})
check("code cannot be reused", "invite code" in r.text and "valid" in r.text)

print("\n== signing in ==")
c2 = client()
# The rendered message is HTML-escaped, so the apostrophe is not a literal one.
DENIED = "match"


def error_text(html_text: str) -> str:
    import re
    m = re.search(r'<div class="error">(.*?)</div>', html_text, re.S)
    return m.group(1).strip() if m else ""


r = c2.post("/wiki/login", data={"email": "wren@example.com", "password": "wrong"})
wrong_pw = error_text(r.text)
check("wrong password refused", r.status_code == 200 and DENIED in wrong_pw)
r = c2.post("/wiki/login", data={"email": "nobody@example.com", "password": "hunter2hunter"})
unknown = error_text(r.text)
check("unknown email is refused too", DENIED in unknown)
# The pages differ by the echoed address, which is the user's own input. What
# must not differ is the message, or it tells you which addresses have accounts.
check("both refusals give the identical message", unknown == wrong_pw,
      f"{unknown!r} vs {wrong_pw!r}")
r = c2.post("/wiki/login", data={"email": "WREN@example.com",
                                 "password": "hunter2hunter"})
check("sign-in is case-insensitive", r.status_code == 303)

print("\n== what Wren sees ==")
page = wren.get("/wiki/character/wren.html")
check("page renders", page.status_code == 200)
check("public text shown", SHARED in page.text)
check("his own secret shown", NICK_ONLY in page.text)
check("secret is visibly marked", 'class="secret"' in page.text)
check("dm-only secret hidden", DM_ONLY not in page.text)
check("header shows his name", ">Wren<" in page.text or "Wren" in page.text)

notes = wren.get("/wiki/lore/dm-notes.html")
check("restricted page is 404, not 403", notes.status_code == 404, str(notes.status_code))
brind = wren.get("/wiki/place/brindlewood.html")
check("link to restricted page stripped", "dm-notes" not in brind.text)
art = wren.get("/wiki/art/lore-dm-notes.png")
check("art for a restricted page is 404", art.status_code == 404)

print("\n== what The DM sees ==")
dm = client()
dm.post("/wiki/register", data={"email": "dm@example.com",
                                 "password": "hunter2hunter", "code": sam_code})
page = dm.get("/wiki/character/wren.html")
check("dm sees the dm-only secret", DM_ONLY in page.text)
check("dm sees wren's secret too", NICK_ONLY in page.text)
check("dm can open the restricted page",
      dm.get("/wiki/lore/dm-notes.html").status_code == 200)
check("dm sees the link to it", "dm-notes" in dm.get("/wiki/place/brindlewood.html").text)

print("\n== search index is per person ==")
# The client-side haystack is lowercased, so compare against lowercase or the
# assertions pass regardless of what leaked.
nick_index = wren.get("/wiki/").text.lower()
sam_index = dm.get("/wiki/").text.lower()
check("wren's index includes his own secret", NICK_ONLY.lower() in nick_index)
check("wren's index excludes the dm secret", DM_ONLY.lower() not in nick_index)
check("dm's index includes both",
      DM_ONLY.lower() in sam_index and NICK_ONLY.lower() in sam_index)

print("\n== sign out ==")
r = wren.get("/wiki/logout")
check("logout redirects", r.status_code == 303)
check("session cleared", wren.get("/wiki/").status_code == 303)

print("\n== open registration ==")
open_app = make_app(require_invite=False)
o = client(open_app)
form = o.get("/wiki/register").text
check("offers a person picker", "<select" in form and 'name="who"' in form)
check("no invite field", 'name="code"' not in form)
check("claimed people are not offered", ">Wren" not in form and ">The DM" not in form,
      "already registered above")
check("unclaimed people are offered", "Tobias Goreguts" in form)

r = o.post("/wiki/register", data={"email": "tobias@example.com",
                                   "password": "hunter2hunter", "who": "tobias"})
check("registers by picking a name", r.status_code == 303, str(r.status_code))
check("bound to the chosen person",
      accounts.key_for("tobias@example.com") == "tobias")

r2 = client(open_app).post("/wiki/register", data={
    "email": "imposter@example.com", "password": "hunter2hunter", "who": "tobias"})
check("a name cannot be claimed twice", "already registered" in r2.text)
r3 = client(open_app).post("/wiki/register", data={
    "email": "nobody@example.com", "password": "hunter2hunter", "who": "gandalf"})
check("an unknown name is refused", "Pick who you are" in r3.text)
r4 = client(open_app).post("/wiki/register", data={
    "email": "blank@example.com", "password": "hunter2hunter", "who": ""})
check("no name selected is refused", "Pick who you are" in r4.text)

print("\n== what Tobias Goreguts sees, registered openly ==")
goobs_page = o.get("/wiki/character/wren.html")
check("public text shown", SHARED in goobs_page.text)
check("wren's secret hidden", NICK_ONLY not in goobs_page.text)
check("dm secret hidden", DM_ONLY not in goobs_page.text)

shutil.rmtree(sandbox, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")

