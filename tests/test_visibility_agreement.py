"""Pin the three implementations of page visibility against each other.

"May this person see this page" used to be written out four times: in the
website's renderer, the tooltip index, the MCP server and the Obsidian
exporter. They agreed by coincidence rather than by construction, and a
disagreement fails silently, which is the worst way for this particular rule to
fail.

This file was written before that refactor to pin what the four did, and it is
kept afterwards to prove `universe/access.py` still does exactly that. The
expectations below were recorded from the old implementations and have not been
edited since, including the surprising one: an empty `visible_to` list means
everyone, not nobody.

The MCP arm stays because it exercises the rule through a real server rather
than through a direct call, so a future refactor that rewires the tools without
touching `access` still gets caught.

    python tests\\test_visibility_agreement.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import access as access_mod  # noqa: E402
from universe import tooltips as tooltips_mod  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


# -- the matrix --------------------------------------------------------
#
# Every shape `visible_to` has ever been written in, plus the shapes a person
# could plausibly type into the frontmatter by hand.

PAGES: dict[str, object] = {
    "public": None,                       # no visible_to at all
    "list-one": ["dm"],
    "list-two": ["dm", "wren"],
    "bare-string": "dm",                  # a hand-written scalar, not a list
    "mixed-case": ["DM"],
    "padded": ["  dm  "],
    "empty-list": [],                     # falsy: does this mean nobody, or everyone?
    "unknown-key": ["gandalf"],           # audience that matches no one
}

VIEWERS: dict[str, "access_mod.Viewer"] = {
    "nobody": access_mod.Viewer.nobody(),
    "dm": access_mod.Viewer.of({"dm"}),
    "wren": access_mod.Viewer.of({"wren", "player"}),
    "tobias": access_mod.Viewer.of({"tobias", "player"}),
    # An unrecognised MCP token. It used to carry a literal "guest" identity,
    # which made visible_to: [guest] readable by strangers over MCP alone.
    "guest": access_mod.Viewer.nobody(),
    "local": access_mod.Viewer.local(),
}


def build_library(root: Path) -> Library:
    lib = Library(root / "content")
    for slug, audience in PAGES.items():
        data = {} if audience is None else {"visible_to": audience}
        lib.save(Entity(kind="lore", slug=slug, name=slug.replace("-", " ").title(),
                        summary="A page.", body="Body text.", data=data))
    return lib


# -- the three implementations, each driven the way its callers drive it ----

def via_access(lib: Library, viewer) -> set[str]:
    return {e.slug for e in access_mod.visible(lib.all(), viewer)}


def via_tooltips(lib: Library, viewer) -> set[str]:
    """The hover index, which now delegates but is checked anyway."""
    return {e.slug for e in lib.all() if tooltips_mod._readable(e, viewer)}


async def via_mcp(sandbox: Path, as_person: str | None) -> set[str]:
    """Drive the real MCP tool rather than a copy of its logic.

    `can_see` is a closure inside build_server and the tools need a live
    request context, so the honest way to characterise it is to run the server
    the way a caller does and ask a tool that filters by it. Identity is fixed
    at startup by `--as`, hence one server per viewer.
    """
    import os

    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    args = [str(sandbox / "mcp_server.py")]
    if as_person:
        args += ["--as", as_person]
    params = StdioServerParameters(
        command=sys.executable, args=args, cwd=str(sandbox), env={**os.environ},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("list_pages", {"kind": "lore"})

    payload = getattr(result, "structured_content", None) or getattr(
        result, "structuredContent", None)
    if not payload:
        for block in getattr(result, "content", []):
            text = getattr(block, "text", None)
            if text:
                payload = json.loads(text)
                break
    if isinstance(payload, dict):
        payload = payload.get("result", payload)
    rows = payload["results"] if isinstance(payload, dict) else payload
    return {row["ref"].split("/", 1)[1] for row in rows}


# -- run ---------------------------------------------------------------

sandbox = Path(tempfile.mkdtemp(prefix="visibility-"))
shutil.copytree(ROOT / "universe", sandbox / "universe")
shutil.copy(ROOT / "config.yaml", sandbox / "config.yaml")
shutil.copy(ROOT / "people.yaml", sandbox / "people.yaml")
shutil.copy(ROOT / "mcp_server.py", sandbox / "mcp_server.py")
library = build_library(sandbox)

# Which viewers MCP can actually be asked about. Identity comes from `--as`,
# which takes a person key, so the two synthetic viewers have no stdio
# equivalent: "nobody" and "guest" only arise from an unrecognised bearer token
# over HTTP. Those paths are covered by test_mcp_secrets and test_webapp; here
# they are compared between the two importable implementations only.
AS_PERSON = {"dm": "dm", "wren": "wren", "tobias": "tobias", "local": None}

print("\n== the three agree, viewer by viewer ==")
observed: dict[str, set[str]] = {}
for label, viewer in VIEWERS.items():
    a = via_access(library, viewer)
    b = via_tooltips(library, viewer)
    observed[label] = a
    check(f"{label}: access and tooltips agree", a == b,
          f"access={sorted(a)} tooltips={sorted(b)}")
    if label in AS_PERSON:
        c = asyncio.run(via_mcp(sandbox, AS_PERSON[label]))
        check(f"{label}: access and MCP agree", a == c,
              f"access={sorted(a)} mcp={sorted(c)}")
    else:
        print(f"    ..    {label}: no stdio equivalent, HTTP-only viewer")

print("\n== and this is what they currently do ==")
# Recorded from the old implementations and not edited since. Anything
# surprising here is a bug to fix deliberately, not to fix by accident.
EXPECTED = {
    "nobody":  {"public", "empty-list"},
    "dm":      {"public", "empty-list", "list-one", "list-two", "bare-string",
                "mixed-case", "padded"},
    "wren":    {"public", "empty-list", "list-two"},
    "tobias":  {"public", "empty-list"},
    "guest":   {"public", "empty-list"},
    # The one deliberate difference from the old behaviour, and the reason it
    # is spelled out rather than quietly absorbed. "local" used to be the union
    # of everybody's keys, so a page addressed to a name matching nobody, a
    # typo or someone who has left, was invisible to every viewer including the
    # machine holding the files. Full access is now a flag, so that machine can
    # read what is on its own disk.
    "local":   {"public", "empty-list", "list-one", "list-two", "bare-string",
                "mixed-case", "padded", "unknown-key"},
}
for label, expected in EXPECTED.items():
    check(f"{label} sees exactly {sorted(expected)}", observed[label] == expected,
          f"got {sorted(observed[label])}")

print("\n== the awkward shapes, spelled out ==")
check("a bare string audience behaves like a one-item list",
      "bare-string" in observed["dm"] and "bare-string" not in observed["wren"])
check("audience matching ignores case",
      "mixed-case" in observed["dm"])
check("audience matching ignores surrounding whitespace",
      "padded" in observed["dm"])
check("an empty list means everyone, not no one",
      "empty-list" in observed["nobody"],
      "falsy audience is treated as unrestricted; surprising, and preserved "
      "by the refactor rather than quietly changed")
check("an audience naming nobody real hides the page from every person",
      all("unknown-key" not in observed[who]
          for who in ("nobody", "dm", "wren", "tobias", "guest")),
      "a typo in an audience should not publish the page")
check("but the machine holding the files can still read it",
      "unknown-key" in observed["local"],
      "otherwise a typo makes a page nobody at all can recover")
check("a page with no visible_to is readable by a viewer with no identity",
      "public" in observed["nobody"])

shutil.rmtree(sandbox, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
