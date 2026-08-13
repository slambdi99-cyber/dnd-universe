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
    """HTTP mode must not start unauthenticated."""
    import subprocess

    print("\n== HTTP mode refuses to run without a token ==")
    env = {**os.environ}
    env.pop("UNIVERSE_MCP_TOKEN", None)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "mcp_server.py"), "--http"],
        capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=60,
    )
    check("exits non-zero", proc.returncode == 2, f"rc={proc.returncode}")
    check("explains why", "Refusing to serve over HTTP" in proc.stderr,
          proc.stderr.strip()[:70])


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
    token = "test-secret-do-not-use"
    port = 8791
    env = {**os.environ, "UNIVERSE_MCP_TOKEN": token}
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "mcp_server.py"), "--http",
         "--port", str(port), "--host", "127.0.0.1"],
        cwd=str(ROOT), env=env,
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
        check("correct token is accepted", post(f"Bearer {token}") == 200)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(run())
    check_http_refuses_without_token()
    check_http_auth()
    print()
    if FAIL:
        print(f"{len(FAIL)} FAILURE(S): {FAIL}")
        sys.exit(1)
    print("all checks passed")
