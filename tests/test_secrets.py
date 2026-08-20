"""Tests for secret sections.

This is the one part of the project where a bug means a spoiled campaign
rather than an annoying error, so it gets tested harder than the rest: the
parser, the redaction, the fail-closed behaviour, and then the actual exports,
asserting no secret text reaches a file.

    python tests\\test_secrets.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import secrets as s  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402
from universe.people import People, Person  # noqa: E402

FAIL: list[str] = []
CANARY = "ZZCANARYZZ"


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


print("\n== parsing ==")
body = """Public opening.

:::secret dm, wren
Hidden middle.
:::

Public close."""
segs = s.parse(body)
check("splits into three segments", len(segs) == 3, str(len(segs)))
check("first is public", not segs[0].is_secret)
check("second is secret", segs[1].is_secret)
check("audience parsed", segs[1].audience == frozenset({"dm", "wren"}),
      str(segs[1].audience))
check("third is public", not segs[2].is_secret)
check("has_secrets true", s.has_secrets(body))
check("audiences collected", s.audiences(body) == {"dm", "wren"})

print("\n== redaction ==")
check("named person sees it", "Hidden middle" in s.redact(body, {"wren"}))
check("other player does not", "Hidden middle" not in s.redact(body, {"tobias"}))
check("public text always survives", "Public opening" in s.redact(body, {"tobias"}))
check("closing text survives too", "Public close" in s.redact(body, {"tobias"}))
check("no viewer sees nothing secret", "Hidden middle" not in s.redact(body, set()))
check("strip_all removes it", "Hidden middle" not in s.strip_all(body))
check("strip_all keeps public", "Public close" in s.strip_all(body))

print("\n== dm alias ==")
dm_body = f":::secret dm\n{CANARY}\n:::"
check("dm role sees dm secrets", CANARY in s.redact(dm_body, {"dm", "dm"}))
check("player does not", CANARY not in s.redact(dm_body, {"wren", "player"}))
check("a person literally keyed 'dm' also matches", CANARY in s.redact(dm_body, {"dm"}))

print("\n== fail closed ==")
unterminated = f"Public.\n\n:::secret dm\n{CANARY}\nmore text"
check("unterminated block stays hidden",
      CANARY not in s.redact(unterminated, {"wren"}))
check("unterminated block visible to its audience",
      CANARY in s.redact(unterminated, {"dm"}))
check("unterminated: public part survives",
      "Public." in s.redact(unterminated, {"wren"}))

empty_aud = f":::secret\n{CANARY}\n:::"
check("empty audience hidden from players",
      CANARY not in s.redact(empty_aud, {"wren", "player"}))
check("empty audience defaults to dm", CANARY in s.redact(empty_aud, {"dm"}))

nested = f":::secret dm\nouter\n:::secret wren\n{CANARY}\n:::"
check("re-opening inside a block does not widen the audience",
      CANARY not in s.redact(nested, {"wren"}), s.redact(nested, {"wren"}))
check("original audience still reads it", CANARY in s.redact(nested, {"dm"}))

print("\n== case and spacing ==")
check("audience is case-insensitive",
      CANARY in s.redact(f":::secret DM\n{CANARY}\n:::", {"dm"}))
check("viewer keys are case-insensitive",
      CANARY in s.redact(f":::secret dm\n{CANARY}\n:::", {"DM"}))
check("semicolons accepted as separators",
      CANARY in s.redact(f":::secret dm; wren\n{CANARY}\n:::", {"wren"}))
# A marker must own its line. Mid-line text that looks like one must not open
# a block, or ordinary prose could silently hide everything after it.
inline = f"Talk of a :::secret dm plan.\n\n{CANARY} stays public."
check("mid-line marker does not open a block", CANARY in s.strip_all(inline),
      s.strip_all(inline)[:60])
check("mid-line marker leaves the line intact",
      ":::secret dm plan" in s.strip_all(inline))
indented = f"  :::secret dm\n{CANARY}\n  :::"
check("an indented marker is not a marker either",
      CANARY in s.strip_all(indented))

print("\n== wrap round-trips ==")
wrapped = s.wrap(CANARY, ["Wren", "dm"])
check("wrap hides from others", CANARY not in s.strip_all(wrapped))
check("wrap shows to audience", CANARY in s.redact(wrapped, {"wren"}))

print("\n== visited blocks ==")
gated = f"Public shopfront.\n\n:::visited\n{CANARY}\n:::"
check("player cannot read before the visit",
      CANARY not in s.redact(gated, {"wren", "player"}))
check("the DM can", CANARY in s.redact(gated, {"dm"}))
check("the visited key opens it",
      CANARY in s.redact(gated, {"wren", "player", "visited"}))
check("public text around it survives",
      "Public shopfront." in s.redact(gated, {"wren"}))
extra = f":::visited wren\n{CANARY}\n:::"
check("extra keys on the line still work", CANARY in s.redact(extra, {"wren"}))
check("but other players still wait", CANARY not in s.redact(extra, {"tobias"}))
check("wrap keeps the visited spelling",
      s.wrap(CANARY, {"dm", "visited"}).startswith(":::visited"))
check("wrapped visited round-trips",
      CANARY in s.redact(s.wrap(CANARY, {"dm", "visited"}), {"visited"}))

print("\n== the edit form must not flatten readable secrets ==")
page = f"Public opening.\n\n:::secret dm\n{CANARY}\n:::\n\nPublic close."
form = s.visible_body(page, {"dm"})
check("readable block keeps its fence", ":::secret dm" in form)
saved = s.merge_edit(page, form, {"dm"})
check("a no-op edit keeps the secret", s.has_secrets(saved))
check("and its audience", CANARY not in s.redact(saved, {"wren"}))
check("withheld blocks still drop from the form",
      CANARY not in s.visible_body(page, {"wren"}))
form_v = s.visible_body(gated, {"dm"})
check("visited fence survives the form too", ":::visited" in form_v)

print("\n== people registry ==")
reg = People(
    members={
        "dm": Person(key="dm", name="The DM", role="dm"),
        "wren": Person(key="wren", name="Wren", role="player"),
    },
    tokens={"tok-dm": "dm", "tok-wren": "wren"},
)
check("resolves a token", reg.resolve("tok-wren").name == "Wren")
check("rejects an unknown token", reg.resolve("nope") is None)
check("dm identities include role", reg.members["dm"].identities == frozenset({"dm", "dm"}))
check("player identities include role",
      reg.members["wren"].identities == frozenset({"wren", "player"}))

print("\n== exports must never leak ==")
sandbox = Path(tempfile.mkdtemp(prefix="secrets-test-"))
lib = Library(sandbox / "content")
lib.save(Entity(
    kind="place", slug="test-town", name="Test Town",
    summary="A town.", appearance="a town",
    body=f"Everyone knows this.\n\n:::secret dm\n{CANARY}\n:::",
))
lib.save(Entity(
    kind="character", slug="test-hidden", name="Test Hidden",
    summary="Should not appear publicly.", appearance="a figure",
    body=f"{CANARY} whole page.",
    data={"visible_to": ["dm"]},
))
lib.save(Entity(
    kind="character", slug="test-linker", name="Test Linker",
    summary="Links to the hidden page.", appearance="someone",
    links=["character/test-hidden"],
))

import shutil  # noqa: E402

shutil.copy(ROOT / "config.yaml", sandbox / "config.yaml")
shutil.copytree(ROOT / "universe", sandbox / "universe")
(sandbox / "tools").mkdir()
for tool in ("export_site.py", "export_obsidian.py"):
    shutil.copy(ROOT / "tools" / tool, sandbox / "tools" / tool)
shutil.copy(ROOT / "people.yaml", sandbox / "people.yaml")

for tool, out in (("export_site.py", "site"), ("export_obsidian.py", "vault")):
    proc = subprocess.run(
        [sys.executable, str(sandbox / "tools" / tool), "--no-images"]
        if tool == "export_obsidian.py"
        else [sys.executable, str(sandbox / "tools" / tool)],
        cwd=str(sandbox), capture_output=True, text=True, timeout=300,
    )
    ok = proc.returncode == 0
    check(f"{tool} runs", ok, proc.stderr.strip()[:120])
    if not ok:
        continue
    target = sandbox / out
    hits = [
        p.name for p in target.rglob("*")
        if p.is_file() and p.suffix in {".html", ".md", ".json", ".txt"}
        and CANARY in p.read_text(encoding="utf-8", errors="ignore")
    ]
    check(f"{out}: no secret text anywhere", not hits, str(hits[:3]))
    leaked_page = list(target.rglob("*Hidden*"))
    check(f"{out}: restricted page not exported", not leaked_page,
          str([p.name for p in leaked_page]))
    linker = list(target.rglob("*Linker*")) + list(target.rglob("test-linker*"))
    if linker:
        text = linker[0].read_text(encoding="utf-8", errors="ignore")
        check(f"{out}: link to the hidden page stripped",
              "test-hidden" not in text and "Test Hidden" not in text)

print("\n== obsidian --as dm does include his secrets ==")
proc = subprocess.run(
    [sys.executable, str(sandbox / "tools" / "export_obsidian.py"),
     "--no-images", "--as", "dm", "--out", str(sandbox / "vault-dm")],
    cwd=str(sandbox), capture_output=True, text=True, timeout=300,
)
check("runs", proc.returncode == 0, proc.stderr.strip()[:120])
if proc.returncode == 0:
    found = any(
        CANARY in p.read_text(encoding="utf-8", errors="ignore")
        for p in (sandbox / "vault-dm").rglob("*.md")
    )
    check("The DM's vault contains his secret", found)

shutil.rmtree(sandbox, ignore_errors=True)

print("\n== secret table columns ==")
TABLE = """Grum casts bells.

| Item | Price | Notes ::dm |
| --- | ---: | --- |
| Handbell | 5g | |
| Ear trumpet | 12g | He finds these very funny |
"""

player = s.redact(TABLE, {"wren"})
check("player keeps the table", "Handbell" in player)
check("player loses the column", "very funny" not in player)
check("player never sees the header", "Notes" not in player)
check("public prose survives", "Grum casts bells." in player)
dm = s.redact(TABLE, {"dm"})
check("dm keeps the column", "very funny" in dm)
check("dm's header names the audience", "Notes &middot; dm" in dm)
check("the marker itself never renders", "::dm" not in dm)
check("strip_all drops the column", "very funny" not in s.strip_all(TABLE))
check("a column counts as a secret", s.has_secrets(TABLE))
check("hidden_from sees the column", s.hidden_from(TABLE, {"wren"}))
check("but not for the dm", not s.hidden_from(TABLE, {"dm"}))
check("audiences includes the column's", "dm" in s.audiences(TABLE))

form = s.visible_body(TABLE, {"wren"})
check("the table leaves the player's edit form", "Handbell" not in form,
      "editing around hidden cells is how they get destroyed")
check("the prose stays editable", "Grum casts bells." in form)
merged = s.merge_edit(TABLE, form + "\n\nWren added a line.", {"wren"})
check("saving folds the table back", "very funny" in merged)
check("with the marker intact", "Notes ::dm" in merged)
check("and keeps the player's edit", "Wren added a line." in merged)
check("dm edit form keeps the table verbatim",
      "Notes ::dm" in s.visible_body(TABLE, {"dm"}))

VISITED_TABLE = (":::visited\n| Item | Notes ::dm |\n| --- | --- |\n"
                 "| Fork | Planar |\n:::")
opened = s.redact(VISITED_TABLE, {"wren", "visited"})
check("a visited table opens without its dm column",
      "Fork" in opened and "Planar" not in opened)
carried = s.merge_edit(VISITED_TABLE, s.visible_body(
    VISITED_TABLE, {"wren", "visited"}), {"wren", "visited"})
check("a carried table keeps its visited fence",
      ":::visited" in carried and "Planar" in carried,
      "a table falling out of its fence would surface as public prose")

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
