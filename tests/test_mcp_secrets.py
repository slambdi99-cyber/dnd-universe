"""End-to-end test that the MCP server shows each person only their own view.

Runs a real server over stdio for several identities and asserts the same page
comes back differently for each. Uses a throwaway copy of the project, never
the live campaign.

    python tests\\test_mcp_secrets.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

FAIL: list[str] = []
DM_ONLY = "DMONLYCANARY"
NICK_ONLY = "NICKONLYCANARY"
SHARED = "Everyone can read this."


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


def payload(result) -> dict:
    sc = getattr(result, "structured_content", None) or getattr(
        result, "structuredContent", None
    )
    if sc:
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
    return {}


def build_sandbox() -> Path:
    sandbox = Path(tempfile.mkdtemp(prefix="mcp-secrets-"))
    shutil.copytree(ROOT / "universe", sandbox / "universe")
    shutil.copy(ROOT / "mcp_server.py", sandbox / "mcp_server.py")
    shutil.copy(ROOT / "config.yaml", sandbox / "config.yaml")
    shutil.copy(ROOT / "people.yaml", sandbox / "people.yaml")

    sys.path.insert(0, str(sandbox))
    from universe.entities import Entity, Library

    lib = Library(sandbox / "content")
    lib.save(Entity(
        kind="character", slug="wren", name="Wren",
        summary="Elf fighter from Laurelthel.", appearance="an elf",
        body=(
            f"{SHARED}\n\n"
            f":::secret dm, wren\n{NICK_ONLY}\n:::\n\n"
            f":::secret dm\n{DM_ONLY}\n:::"
        ),
    ))
    lib.save(Entity(
        kind="lore", slug="dm-notes", name="DM Notes",
        summary="Behind the screen.", appearance="notes",
        body="Plot twists.", data={"visible_to": ["dm"]},
    ))
    lib.save(Entity(
        kind="place", slug="brindlewood", name="Brindlewood",
        summary="A township.", appearance="a township",
        links=["lore/dm-notes"],
    ))
    return sandbox


async def as_person(sandbox: Path, key: str | None) -> dict:
    """Ask the server, as this person, for everything we want to compare."""
    args = [str(sandbox / "mcp_server.py")]
    if key:
        args += ["--as", key]
    params = StdioServerParameters(
        command=sys.executable, args=args, cwd=str(sandbox), env={**os.environ}
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return {
                "who": payload(await session.call_tool("whoami", {})),
                "wren": payload(await session.call_tool("get_page", {"ref": "Wren"})),
                "notes": payload(
                    await session.call_tool("get_page", {"ref": "DM Notes"})
                ),
                "brindlewood": payload(
                    await session.call_tool("get_page", {"ref": "Brindlewood"})
                ),
                "overview": payload(await session.call_tool("world_overview", {})),
                "search_nick": payload(
                    await session.call_tool("search_world", {"query": NICK_ONLY})
                ),
                "search_dm": payload(
                    await session.call_tool("search_world", {"query": DM_ONLY})
                ),
            }


async def run() -> None:
    sandbox = build_sandbox()
    print(f"sandbox: {sandbox}\n")

    dm = await as_person(sandbox, "dm")
    wren = await as_person(sandbox, "wren")
    tobias = await as_person(sandbox, "tobias")

    print("== identity ==")
    check("dm is the dm", "dm" in dm["who"]["identities"], str(dm["who"]))
    check("wren is a player", "player" in wren["who"]["identities"])
    check("dm sees more pages than tobias",
          dm["who"]["pages_visible"] > tobias["who"]["pages_visible"],
          f"{dm['who']['pages_visible']} vs {tobias['who']['pages_visible']}")

    print("\n== the same page, three ways ==")
    check("everyone gets the public part", all(
        SHARED in p["wren"]["body"] for p in (dm, wren, tobias)))
    check("wren reads his own secret", NICK_ONLY in wren["wren"]["body"])
    check("dm reads wren's secret too", NICK_ONLY in dm["wren"]["body"])
    check("tobias does not", NICK_ONLY not in tobias["wren"]["body"],
          tobias["wren"]["body"][:80])
    check("dm reads the dm-only secret", DM_ONLY in dm["wren"]["body"])
    check("wren does not read dm-only", DM_ONLY not in wren["wren"]["body"])
    check("tobias does not read dm-only", DM_ONLY not in tobias["wren"]["body"])
    check("tobias is told something is hidden", "note" in tobias["wren"],
          str(tobias["wren"].get("note", ""))[:50])
    check("dm is not told anything is hidden", "note" not in dm["wren"])

    print("\n== whole-page restriction ==")
    check("dm can open DM Notes", dm["notes"].get("name") == "DM Notes")
    check("wren cannot", "error" in wren["notes"], str(wren["notes"])[:60])
    check("tobias cannot", "error" in tobias["notes"])
    check("restricted page absent from tobias' overview",
          "DM Notes" not in json.dumps(tobias["overview"]))

    print("\n== links do not leak the page's existence ==")
    check("dm sees the link", "lore/dm-notes" in dm["brindlewood"]["links"])
    check("wren does not", "lore/dm-notes" not in wren["brindlewood"]["links"],
          str(wren["brindlewood"]["links"]))
    check("tobias does not", "lore/dm-notes" not in tobias["brindlewood"]["links"])

    print("\n== search cannot be used to fish for secrets ==")
    check("wren finds his own secret by searching it",
          wren["search_nick"]["total"] >= 1)
    check("tobias searching wren's secret finds nothing",
          tobias["search_nick"]["total"] == 0, str(tobias["search_nick"]["total"]))
    check("wren searching the dm secret finds nothing",
          wren["search_dm"]["total"] == 0)
    check("dm searching the dm secret finds it", dm["search_dm"]["total"] >= 1)

    print("\n== default stdio identity is full access ==")
    local = await as_person(sandbox, None)
    check("local sees everything", DM_ONLY in local["wren"]["body"]
          and NICK_ONLY in local["wren"]["body"])
    check("local can open restricted pages", local["notes"].get("name") == "DM Notes")

    shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run())
    print()
    if FAIL:
        print(f"{len(FAIL)} FAILURE(S): {FAIL}")
        sys.exit(1)
    print("all checks passed")
