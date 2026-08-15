"""End-to-end test of the MCP server.

Launches `mcp_server.py` as a real subprocess over stdio and drives it with a
real MCP client, so this exercises the actual protocol rather than calling the
Python functions directly.

Writes go to a throwaway copy of the content folder, never your campaign.

    python tests\\test_mcp.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

from universe import access as access_mod  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


def payload(result) -> dict:
    """Pull the JSON body out of a tool result."""
    sc = getattr(result, "structured_content", None) or getattr(
        result, "structuredContent", None
    )
    if sc:
        # Non-dict returns get wrapped under "result" by the SDK.
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
    return {}


def make_sandbox() -> Path:
    """A disposable copy of the project so writes never touch real content."""
    sandbox = Path(tempfile.mkdtemp(prefix="universe-mcp-"))
    shutil.copytree(ROOT / "universe", sandbox / "universe")
    shutil.copy(ROOT / "mcp_server.py", sandbox / "mcp_server.py")
    shutil.copy(ROOT / "config.yaml", sandbox / "config.yaml")
    if (ROOT / "content").exists():
        shutil.copytree(ROOT / "content", sandbox / "content")
    return sandbox


async def run() -> None:
    sandbox = make_sandbox()
    print(f"sandbox: {sandbox}\n")

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(sandbox / "mcp_server.py")],
        cwd=str(sandbox),
        env={**os.environ},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print("== handshake ==")
            info = getattr(init, "server_info", None) or init.serverInfo
            check("server initializes", info.name == "buried-star", info.name)
            check("instructions provided", bool(init.instructions))

            tools = {t.name: t for t in (await session.list_tools()).tools}
            print(f"\n== tools ({len(tools)}) ==")
            for expected in ("search_world", "get_page", "list_pages",
                             "world_overview", "open_questions",
                             "create_page", "update_page", "link_pages"):
                check(f"exposes {expected}", expected in tools)
            check("every tool documented",
                  all(t.description for t in tools.values()))

            print("\n== world_overview ==")
            data = payload(await session.call_tool("world_overview", {}))
            check("reports a total", data.get("total", 0) > 50, str(data.get("total")))
            check("counts places", data.get("counts", {}).get("place", 0) > 20,
                  str(data.get("counts")))
            pcs = data.get("player_characters", [])
            check("lists player characters", len(pcs) >= 5, str(len(pcs)))
            check("Tobias among them", any("Tobias" in p for p in pcs), str(pcs[:3]))

            print("\n== search_world ==")
            data = payload(await session.call_tool(
                "search_world", {"query": "vampire"}))
            check("finds the covenant by theme", data.get("total", 0) >= 1,
                  str(data.get("total")))
            data = payload(await session.call_tool(
                "search_world", {"query": "bog", "kind": "place", "limit": 5}))
            check("kind filter works",
                  all(r["kind"] == "place" for r in data.get("results", [])))
            check("respects limit", len(data.get("results", [])) <= 5)
            data = payload(await session.call_tool(
                "search_world", {"query": "zzzznotathing"}))
            check("empty search is not an error", data.get("total") == 0)

            print("\n== get_page ==")
            data = payload(await session.call_tool(
                "get_page", {"ref": "Korran Mossborn"}))
            check("resolves by display name", data.get("name") == "Korran Mossborn",
                  str(data.get("name") or data.get("error")))
            check("returns the body", "Bogwatchers" in data.get("body", ""))
            check("returns backlinks", len(data.get("linked_from", [])) > 0,
                  str(len(data.get("linked_from", []))))
            check("returns appearance", bool(data.get("appearance")))

            data = payload(await session.call_tool("get_page", {"ref": "korran"}))
            check("resolves by partial name", data.get("name") == "Korran Mossborn",
                  str(data.get("name") or data.get("error")))
            data = payload(await session.call_tool(
                "get_page", {"ref": "place/brindlewood"}))
            check("resolves by kind/slug", data.get("name") == "Brindlewood")
            data = payload(await session.call_tool("get_page", {"ref": "nope"}))
            check("missing page returns a helpful error", "error" in data,
                  str(data)[:60])

            print("\n== create_page ==")
            data = payload(await session.call_tool("create_page", {
                "kind": "character",
                "name": "Test Innkeeper",
                "summary": "A test NPC.",
                "appearance": "stout innkeeper, flour-dusted apron",
                "tags": ["npc", "test"],
                "links": ["place/brindlewood"],
                "source": "test suite",
            }))
            check("creates a page", data.get("created") == "character/test-innkeeper",
                  str(data.get("created") or data.get("error")))
            check("file written to disk",
                  (sandbox / "content" / "character" / "test-innkeeper.md").exists())

            dupe = payload(await session.call_tool("create_page", {
                "kind": "character", "name": "Test Innkeeper"}))
            check("refuses duplicates", "error" in dupe, str(dupe)[:70])
            bad = payload(await session.call_tool("create_page", {
                "kind": "spaceship", "name": "Nope"}))
            check("rejects an unknown kind", "error" in bad, str(bad)[:60])

            print("\n== update_page ==")
            data = payload(await session.call_tool("update_page", {
                "ref": "Test Innkeeper",
                "append_body": "She remembers every face.",
                "add_tags": ["ally"],
                "add_links": ["place/valeshire"],
                "source": "session 2026-08-13",
            }))
            page = data.get("page", {})
            check("appends to body", "remembers every face" in page.get("body", ""))
            check("adds tags without dropping old ones",
                  {"npc", "test", "ally"} <= set(page.get("tags", [])),
                  str(page.get("tags")))
            check("adds links", "place/valeshire" in page.get("links", []))
            check("records the source", "session 2026-08-13" in page.get("sources", []))

            again = payload(await session.call_tool("update_page", {
                "ref": "Test Innkeeper", "add_tags": ["ally"]}))
            check("tag add is idempotent",
                  again["page"]["tags"].count("ally") == 1)

            print("\n== link_pages ==")
            data = payload(await session.call_tool("link_pages", {
                "a": "Test Innkeeper", "b": "Peapod Public House"}))
            check("links both ways", "linked" in data, str(data)[:70])
            back = payload(await session.call_tool(
                "get_page", {"ref": "Peapod Public House"}))
            check("reverse link is real",
                  "character/test-innkeeper" in back.get("links", []),
                  str(back.get("links"))[:80])
            self_link = payload(await session.call_tool("link_pages", {
                "a": "Test Innkeeper", "b": "Test Innkeeper"}))
            check("refuses self-links", "error" in self_link)

            print("\n== the real campaign was untouched ==")
            check("no test page in the real content folder",
                  not (ROOT / "content" / "character" / "test-innkeeper.md").exists())

    # -- read-only mode is a separate server process ----------------------
    print("\n== read-only mode ==")
    ro = StdioServerParameters(
        command=sys.executable,
        args=[str(sandbox / "mcp_server.py"), "--read-only"],
        cwd=str(sandbox),
        env={**os.environ},
    )
    async with stdio_client(ro) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {t.name for t in (await session.list_tools()).tools}
            check("read tools still present", "search_world" in names)
            check("create_page withheld", "create_page" not in names)
            check("update_page withheld", "update_page" not in names)
            check("link_pages withheld", "link_pages" not in names)

    shutil.rmtree(sandbox, ignore_errors=True)


def check_http_refuses_without_token() -> None:
    """HTTP mode must not start with nobody able to authenticate.

    There is no shared token any more, so the thing that would make the
    endpoint useless is having no personal tokens at all. Run it somewhere
    with no .people-tokens.json and it should say so rather than listen.

    Runs in a throwaway copy, and on a port nothing else uses: pointing it at
    the project would have it read the real content and fight the live server
    for 8787.
    """
    import subprocess

    print("\n== HTTP mode refuses to run with no personal tokens ==")
    bare = Path(tempfile.mkdtemp(prefix="mcp-notokens-"))
    shutil.copytree(ROOT / "universe", bare / "universe")
    shutil.copy(ROOT / "mcp_server.py", bare / "mcp_server.py")
    shutil.copy(ROOT / "config.yaml", bare / "config.yaml")
    shutil.copy(ROOT / "people.yaml", bare / "people.yaml")
    (bare / "content" / "lore").mkdir(parents=True)
    (bare / "content" / "lore" / "x.md").write_text(
        "---\nname: X\nkind: lore\n---\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(bare / "mcp_server.py"), "--http", "--port", "8799"],
        capture_output=True, text=True, cwd=str(bare), timeout=60,
    )
    check("exits non-zero", proc.returncode == 2, f"rc={proc.returncode}")
    check("explains why", "no personal tokens" in proc.stderr,
          proc.stderr.strip()[:70])
    check("says how to fix it", "make_people_tokens" in proc.stderr)
    shutil.rmtree(bare, ignore_errors=True)


def check_http_auth() -> None:
    """A live HTTP server must reject every request without the right token.

    This is the security boundary for anything served through a public tunnel,
    so it gets a real server, real sockets, and real status codes.
    """
    import subprocess
    import time
    import urllib.error
    import urllib.request

    print("\n== HTTP bearer auth ==")
    # A real person's token, because that is now the only kind there is.
    from universe import people as people_mod

    token = people_mod.ensure_token(ROOT, "wren")
    port = 8791
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "mcp_server.py"), "--http",
         "--port", str(port), "--host", "127.0.0.1"],
        cwd=str(ROOT), env={**os.environ},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/mcp"
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "1"}},
    }).encode()

    def post(auth: str | None) -> int:
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        if auth is not None:
            req.add_header("Authorization", auth)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            return exc.code

    try:
        # Wait for the port to come up rather than guessing at a sleep.
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                post(f"Bearer {token}")
                break
            except Exception:
                time.sleep(0.5)
        else:
            check("server came up", False, "timed out")
            return

        check("no auth header is rejected", post(None) == 401, str(post(None)))
        check("wrong token is rejected", post("Bearer nope") == 401)
        check("malformed header is rejected", post(token) == 401)
        check("a person's own token is accepted", post(f"Bearer {token}") == 200)
        # The one this change exists for: the shared token is gone, so a
        # caller who is nobody in particular gets nothing at all.
        check("an unrecognised token is nobody, not a guest",
              post("Bearer dcQv5FUs7SHLxRC3C9gDbnTo") == 401,
              "the value that turned up in a Discord channel")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def check_instructions_match_the_tools() -> None:
    """Every tool the instructions name must actually exist.

    The instructions are the first thing an assistant reads and the last thing
    anyone remembers to update. A tool named there that has since been renamed
    sends every connected assistant to call something that is not there, and
    nothing else in this project would notice: the server starts fine, the
    tools work fine, and only the advice is wrong.
    """
    import re

    import mcp_server

    named = set(re.findall(r"`([a-z_]{4,})`", mcp_server.INSTRUCTIONS))
    # Backticks also wrap field names, which are not tools.
    fields = {"appearance", "summary", "secret_audience", "source", "within",
              "inside_of", "contains"}
    named -= fields

    print("\n== the instructions describe tools that exist ==")
    real = {n for n, _ in _tool_names()}
    missing = sorted(named - real)
    check("no tool is named that does not exist", not missing, str(missing))
    check("and the instructions name a useful number of them",
          len(named & real) >= 8, f"{len(named & real)} of {len(real)}")

    # The hierarchy is invisible unless an assistant is told to set it: a new
    # shop with no `within` lands at the top level beside the continents, which
    # is wrong in a way that reads as a decision rather than an omission.
    check("the hierarchy is explained", "within" in mcp_server.INSTRUCTIONS,
          "a place written without it lands beside the continents")


def _tool_names() -> list[tuple[str, str]]:
    """(name, description) for every tool the server actually registers."""
    import mcp_server
    from universe import config as config_mod
    from universe import people as people_mod
    from universe.entities import Library

    cfg = config_mod.load(ROOT)
    server = mcp_server.build_server(
        cfg, Library(cfg.content_dir), people_mod.load(ROOT), False,
        access_mod.Viewer.local(), "test",
    )
    tools = asyncio.run(server.list_tools())
    return [(t.name, t.description or "") for t in tools]


if __name__ == "__main__":
    asyncio.run(run())
    check_http_refuses_without_token()
    check_http_auth()
    check_instructions_match_the_tools()
    print()
    if FAIL:
        print(f"{len(FAIL)} FAILURE(S): {FAIL}")
        sys.exit(1)
    print("all checks passed")
