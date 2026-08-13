"""MCP server over the Copper Vale universe.

Lets everyone at the table point their own Claude at the world and read or
write it directly, instead of everything routing through one person.

Two ways to run it.

**Locally, over stdio** (each person needs a copy of the content folder):

    python mcp_server.py

**Over the network, for the rest of your table** (one machine hosts, everyone
else connects through a Cloudflare Tunnel):

    python mcp_server.py --http --token YOUR_SHARED_SECRET
    cloudflared tunnel --url http://localhost:8787

Anything exposed to the internet must have `--token` set. The server refuses
to start in HTTP mode without one, because these tools can rewrite your
campaign and an open endpoint is an open invitation.

Pass `--read-only` to serve the world without the write tools, which is the
right setting for a shared link you don't fully control.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Annotated, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from universe import config as config_mod  # noqa: E402
from universe.entities import KINDS, Entity, Library, slugify  # noqa: E402

INSTRUCTIONS = """
This is the shared world of the Copper Vale D&D campaign: places, characters,
factions, items, deities and lore, all cross-linked.

Start with `world_overview` if you don't know the world, or `search_world` for
anything specific. `get_page` returns a full page plus everything that links to
it, which is usually the fastest way to understand how something fits.

When writing, prefer `update_page` over `create_page` for anything that might
already exist; search first. Keep `appearance` visual and concrete since it
feeds the art pipeline, and keep `summary` to one sentence.

Sources matter here. Each page records where its content came from, in rough
order of authority: the DM's wiki, the DM's relationship graph, players'
session logs, then Discord chat. If you add something, say where it came from.
"""


def build_server(library: Library, read_only: bool) -> MCPServer:
    server = MCPServer(
        name="copper-vale",
        title="Copper Vale Universe",
        instructions=INSTRUCTIONS.strip(),
        version="1.0.0",
    )

    # -- helpers -------------------------------------------------------

    def find(ref: str) -> Entity | None:
        """Resolve 'kind/slug', a bare slug, or a display name."""
        ref = ref.strip()
        if "/" in ref:
            kind, slug = ref.split("/", 1)
            found = library.load(kind, slug)
            if found:
                return found
        lowered = ref.lower()
        candidates = list(library.all())
        for entity in candidates:
            if entity.slug == lowered or entity.name.lower() == lowered:
                return entity
        # Last resort: unique prefix match, so "korran" finds Korran Mossborn.
        partial = [e for e in candidates if lowered in e.name.lower()]
        return partial[0] if len(partial) == 1 else None

    def render(entity: Entity, *, full: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ref": entity.ref,
            "name": entity.name,
            "kind": entity.kind,
            "summary": entity.summary,
        }
        if not full:
            return out
        out.update(
            {
                "appearance": entity.appearance,
                "tags": entity.tags,
                "links": entity.links,
                "sources": entity.sources,
                "data": entity.data,
                "body": entity.body,
                "art_count": len(entity.art),
                "linked_from": [e.ref for e in library.backlinks(entity.ref)],
            }
        )
        return out

    # -- read tools ----------------------------------------------------

    @server.tool(
        description="Search the world by keyword across names, summaries, "
        "bodies and tags. Use this before creating anything."
    )
    def search_world(
        query: Annotated[str, "Words to look for, e.g. 'vampire' or 'Brindlewood'"],
        kind: Annotated[str | None, f"Limit to one of: {', '.join(KINDS)}"] = None,
        limit: Annotated[int, "Maximum results"] = 10,
    ) -> dict[str, Any]:
        hits = library.search(query)
        if kind:
            hits = [e for e in hits if e.kind == kind]
        return {
            "query": query,
            "total": len(hits),
            "results": [render(e, full=False) for e in hits[:limit]],
        }

    @server.tool(
        description="Get one page in full, including everything that links to "
        "it. Accepts a name ('Korran Mossborn'), a slug, or 'kind/slug'."
    )
    def get_page(
        ref: Annotated[str, "Name, slug, or kind/slug"],
    ) -> dict[str, Any]:
        entity = find(ref)
        if entity is None:
            return {"error": f"Nothing found for {ref!r}. Try search_world first."}
        return render(entity)

    @server.tool(description="List pages, optionally filtered by kind and tag.")
    def list_pages(
        kind: Annotated[str | None, f"One of: {', '.join(KINDS)}"] = None,
        tag: Annotated[str | None, "Only pages carrying this tag"] = None,
        limit: Annotated[int, "Maximum results"] = 100,
    ) -> dict[str, Any]:
        rows = [e for e in library.all(kind) if not tag or tag in e.tags]
        return {
            "total": len(rows),
            "results": [render(e, full=False) for e in rows[:limit]],
        }

    @server.tool(
        description="A high-level picture of the world: how many pages of each "
        "kind, the major factions and places, and what is unfinished."
    )
    def world_overview() -> dict[str, Any]:
        entities = list(library.all())
        by_kind: dict[str, int] = {}
        for entity in entities:
            by_kind[entity.kind] = by_kind.get(entity.kind, 0) + 1

        def named(kind: str, tag: str | None = None) -> list[str]:
            return [
                e.name
                for e in entities
                if e.kind == kind and (tag is None or tag in e.tags)
            ]

        return {
            "counts": by_kind,
            "total": len(entities),
            "player_characters": named("character", "player-character"),
            "factions": named("faction"),
            "regions_and_settlements": [
                e.name
                for e in entities
                if e.kind == "place"
                and e.data.get("map_type") in {"region", "settlement"}
            ],
            "needs_detail": [e.name for e in entities if "needs-detail" in e.tags],
            "needs_appearance": [
                e.name for e in entities if "needs-appearance" in e.tags
            ],
        }

    @server.tool(
        description="Pages that are deliberately incomplete: a name exists but "
        "the detail or the visual description does not. Good place to start "
        "contributing."
    )
    def open_questions() -> dict[str, Any]:
        entities = list(library.all())
        return {
            "needs_detail": [
                {"ref": e.ref, "name": e.name, "summary": e.summary}
                for e in entities
                if "needs-detail" in e.tags
            ],
            "needs_appearance": [
                {"ref": e.ref, "name": e.name}
                for e in entities
                if "needs-appearance" in e.tags
            ],
            "no_backlinks": [
                e.name
                for e in entities
                if not library.backlinks(e.ref) and not e.links
            ],
        }

    if read_only:
        return server

    # -- write tools ---------------------------------------------------

    @server.tool(
        description="Create a new page. Search first: prefer update_page if "
        "anything similar already exists."
    )
    def create_page(
        kind: Annotated[str, f"One of: {', '.join(KINDS)}"],
        name: Annotated[str, "Display name, e.g. 'Sister Lethra'"],
        summary: Annotated[str, "One sentence on what this is"] = "",
        appearance: Annotated[
            str, "What it looks like, visual and concrete. Feeds the art pipeline."
        ] = "",
        body: Annotated[str, "Longer prose. Markdown is fine."] = "",
        tags: Annotated[list[str] | None, "Tags, e.g. ['npc', 'ally']"] = None,
        links: Annotated[
            list[str] | None, "Related pages as 'kind/slug', e.g. ['place/brindlewood']"
        ] = None,
        source: Annotated[str, "Where this came from, e.g. 'session 2026-08-12'"] = "",
    ) -> dict[str, Any]:
        if kind not in KINDS:
            return {"error": f"kind must be one of: {', '.join(KINDS)}"}
        slug = slugify(name)
        if library.exists(kind, slug):
            return {
                "error": f"{kind}/{slug} already exists. Use update_page instead.",
                "existing": render(library.load(kind, slug), full=False),
            }
        entity = Entity(
            kind=kind,
            slug=slug,
            name=name,
            summary=summary,
            appearance=appearance,
            body=body,
            tags=list(tags or []),
            links=list(links or []),
            sources=[source] if source else [],
        )
        library.save(entity)
        return {"created": entity.ref, "page": render(entity)}

    @server.tool(
        description="Update a page. Text fields replace, list fields append. "
        "Body can be appended to rather than overwritten, which is usually what "
        "you want when adding what happened in a session."
    )
    def update_page(
        ref: Annotated[str, "Name, slug, or kind/slug"],
        summary: Annotated[str | None, "Replaces the existing summary"] = None,
        appearance: Annotated[str | None, "Replaces the existing appearance"] = None,
        append_body: Annotated[str | None, "Appended to the end of the body"] = None,
        replace_body: Annotated[str | None, "Replaces the whole body"] = None,
        add_tags: Annotated[list[str] | None, "Tags to add"] = None,
        add_links: Annotated[list[str] | None, "Links to add, as 'kind/slug'"] = None,
        source: Annotated[str, "Where this update came from"] = "",
    ) -> dict[str, Any]:
        entity = find(ref)
        if entity is None:
            return {"error": f"Nothing found for {ref!r}."}

        if summary is not None:
            entity.summary = summary
        if appearance is not None:
            entity.appearance = appearance
        if replace_body is not None:
            entity.body = replace_body
        if append_body:
            entity.body = (entity.body.rstrip() + "\n\n" + append_body.strip()).strip()
        if add_tags:
            entity.tags = list(dict.fromkeys(entity.tags + list(add_tags)))
        if add_links:
            entity.links = list(dict.fromkeys(entity.links + list(add_links)))
        if source and source not in entity.sources:
            entity.sources.append(source)

        library.save(entity)
        return {"updated": entity.ref, "page": render(entity)}

    @server.tool(
        description="Link two pages to each other. Cross-links are what make "
        "the wiki useful, so link generously."
    )
    def link_pages(
        a: Annotated[str, "First page: name, slug, or kind/slug"],
        b: Annotated[str, "Second page"],
        one_way: Annotated[bool, "Only link a to b, not back"] = False,
    ) -> dict[str, Any]:
        first, second = find(a), find(b)
        if first is None:
            return {"error": f"Nothing found for {a!r}."}
        if second is None:
            return {"error": f"Nothing found for {b!r}."}
        if first.ref == second.ref:
            return {"error": "A page cannot link to itself."}

        if second.ref not in first.links:
            first.links.append(second.ref)
            library.save(first)
        if not one_way and first.ref not in second.links:
            second.links.append(first.ref)
            library.save(second)
        return {"linked": [first.ref, second.ref], "one_way": one_way}

    return server


def _basic_ok(header: str, password: str) -> bool:
    """Check an HTTP Basic header against the wiki password.

    The username is ignored: there is one shared secret, and asking five
    friends to remember a username as well helps nobody. Comparison is
    constant-time.
    """
    import base64
    import binascii
    import hmac

    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return False
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    _, _, supplied = decoded.partition(":")
    return hmac.compare_digest(supplied, password)


def http_app(
    server: MCPServer,
    token: str,
    allowed_hosts: list[str],
    wiki_dir: Path | None = None,
    wiki_password: str = "",
):
    """Wrap the MCP app with bearer-token auth for anything exposed publicly.

    `allowed_hosts` feeds the transport's DNS-rebinding protection, which
    rejects any request whose Host header it doesn't recognise. Behind a tunnel
    the Host is the public hostname, not localhost, so it has to be listed or
    every authenticated request comes back 421 Misdirected Request.
    """
    from mcp.server.mcpserver.server import TransportSecuritySettings
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Mount

    class BearerAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            # The wiki is a read-only rendering opened from a shared link, so it
            # uses HTTP Basic rather than the bearer token: browsers prompt for
            # it, remember it, and it works on a phone. The MCP tools, which can
            # rewrite the campaign, always require the token.
            if wiki_dir is not None and request.url.path.startswith("/wiki"):
                if not wiki_password:
                    return await call_next(request)
                if _basic_ok(request.headers.get("authorization", ""), wiki_password):
                    return await call_next(request)
                return Response(
                    "Copper Vale is private.",
                    status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="Copper Vale"'},
                )

            supplied = request.headers.get("authorization", "")
            expected = f"Bearer {token}"
            # Compare in constant time; these are shared secrets over the wire.
            import hmac

            if not hmac.compare_digest(supplied, expected):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    security = TransportSecuritySettings(
        allowed_hosts=allowed_hosts,
        allowed_origins=["*"],
    )
    inner = server.streamable_http_app(transport_security=security)
    routes = list(inner.routes)
    if wiki_dir is not None:
        from starlette.staticfiles import StaticFiles

        routes.append(
            Mount("/wiki", app=StaticFiles(directory=str(wiki_dir), html=True),
                  name="wiki")
        )
    return Starlette(
        routes=routes,
        middleware=[Middleware(BearerAuth)],
        lifespan=inner.router.lifespan_context,
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--http", action="store_true", help="Serve over HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument(
        "--token",
        default=os.environ.get("UNIVERSE_MCP_TOKEN", ""),
        help="Shared secret for HTTP mode. Required. Or set UNIVERSE_MCP_TOKEN.",
    )
    ap.add_argument(
        "--read-only",
        action="store_true",
        help="Serve without the create/update/link tools",
    )
    ap.add_argument(
        "--wiki",
        help="Serve a static site folder at /wiki, readable without a token. "
        "Build it with tools/export_site.py.",
    )
    ap.add_argument(
        "--wiki-password",
        default=os.environ.get("UNIVERSE_WIKI_PASSWORD", ""),
        help="Password for /wiki via HTTP Basic. Or set UNIVERSE_WIKI_PASSWORD. "
        "Omit to leave the wiki open to anyone with the link.",
    )
    ap.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        help="Public hostname clients will connect through, e.g. a "
        "trycloudflare.com subdomain. Repeatable. Required behind a tunnel: "
        "the transport rejects unrecognised Host headers with 421.",
    )
    args = ap.parse_args(argv[1:])

    cfg = config_mod.load()
    library = Library(cfg.content_dir)
    if not cfg.content_dir.exists():
        print(f"No content at {cfg.content_dir}. Run the seed scripts first.",
              file=sys.stderr)
        return 1

    server = build_server(library, read_only=args.read_only)
    count = sum(1 for _ in library.all())
    mode = "read-only" if args.read_only else "read/write"

    if not args.http:
        print(f"[mcp] copper-vale, {count} pages, {mode}, stdio", file=sys.stderr)
        server.run(transport="stdio")
        return 0

    if not args.token:
        print(
            "Refusing to serve over HTTP without --token.\n\n"
            "These tools can rewrite the campaign, and an unauthenticated\n"
            "endpoint behind a public tunnel is an open invitation. Pick a long\n"
            "random string, pass it with --token or UNIVERSE_MCP_TOKEN, and give\n"
            "it to your players.",
            file=sys.stderr,
        )
        return 2

    try:
        import uvicorn
    except ImportError:
        print("HTTP mode needs uvicorn:  pip install uvicorn", file=sys.stderr)
        return 1

    hosts = [
        f"{args.host}:{args.port}",
        f"localhost:{args.port}",
        f"127.0.0.1:{args.port}",
        *args.allowed_host,
    ]
    wiki_dir = None
    if args.wiki:
        wiki_dir = Path(args.wiki)
        if not wiki_dir.is_absolute():
            wiki_dir = cfg.root / wiki_dir
        if not (wiki_dir / "index.html").exists():
            print(
                f"No site at {wiki_dir}. Build it first:\n"
                f"  python tools/export_site.py",
                file=sys.stderr,
            )
            return 1

    print(
        f"[mcp] copper-vale, {count} pages, {mode}\n"
        f"[mcp] http://{args.host}:{args.port}/mcp (bearer token required)\n"
        + (
            "[mcp] http://{}:{}/wiki ({})\n".format(
                args.host, args.port,
                "password protected" if args.wiki_password
                else "OPEN - anyone with the link can read the campaign",
            )
            if wiki_dir else ""
        )
        + f"[mcp] accepting Host: {', '.join(dict.fromkeys(hosts))}",
        file=sys.stderr,
    )
    uvicorn.run(
        http_app(server, args.token, list(dict.fromkeys(hosts)), wiki_dir,
                 args.wiki_password),
        host=args.host,
        port=args.port,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
