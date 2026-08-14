"""MCP server over The Buried Star campaign wiki.

Lets everyone at the table point their own AI assistant at the world and read
or write it directly, instead of everything routing through one person. MCP is
an open protocol, so which assistant is up to them: Claude, ChatGPT, Cursor,
Zed, or anything else that speaks it.

## Secrets

Pages can carry blocks only some people may read:

    :::secret dm, wren
    Wren's aunt is funding the rebellion.
    :::

Every read is filtered by who is asking, which the server works out from the
caller's token. Each person has their own; mint them with
`tools/make_people_tokens.py`. An unrecognised token is refused at the door.

Whole pages can be restricted too, with `visible_to` in their data:

    data:
      visible_to: [dm, wren]

Hidden pages are invisible everywhere: not in listings, not in search, and
links pointing at them are stripped so their existence doesn't leak.

## Running it

Locally, over stdio (the machine holding the files, so full access by default):

    python mcp_server.py
    python mcp_server.py --as wren        # see it as Wren would

Over the network, for the rest of your table:

    python mcp_server.py --http --wiki site --allowed-host <host>

Everyone connects with their own token, minted by `tools/make_people_tokens.py`
and handed out by the connect page. There is no shared token: it was dropped
after one turned up pasted into a Discord channel, and it bought nothing a
personal token does not while telling the server less about who was calling.
`--read-only` serves the world without the write tools.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Annotated, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import Context, MCPServer  # noqa: E402

from universe import config as config_mod  # noqa: E402
from universe import access as access_mod  # noqa: E402
from universe import history as history_mod  # noqa: E402
from universe import inbox as inbox_mod  # noqa: E402
from universe import people as people_mod  # noqa: E402
from universe import schema as schema_mod  # noqa: E402
from universe import uploads as uploads_mod  # noqa: E402
from universe import secrets as secrets_mod  # noqa: E402
from universe.entities import Entity, Library, slugify  # noqa: E402

# An unrecognised token is nobody, exactly like a signed-out web reader and
# exactly like an export. It used to be frozenset({"guest"}), which quietly
# made a page marked visible_to: [guest] readable by strangers over MCP while
# staying hidden on the website. Nobody designed that.
GUEST = access_mod.Viewer.nobody()

INSTRUCTIONS = """
This is the shared world of The Buried Star, a D&D campaign set in the dying
region of Copper Vale: places, characters, factions, items, deities and lore,
all cross-linked.

Start with `world_overview` if you don't know the world, or `search_world` for
anything specific. `get_page` returns a full page plus everything that links to
it, which is usually the fastest way to understand how something fits.

When writing, prefer `update_page` over `create_page` for anything that might
already exist; search first. Keep `appearance` visual and concrete since it
feeds the art pipeline, and keep `summary` to one sentence.

Some pages carry secrets addressed to particular people. You are shown only
what the person holding this connection may see, so if something reads as
incomplete, assume there is more you are not entitled to rather than filling
the gap. Do not speculate about what a hidden section might contain.

To write a secret, pass `secret_audience` to create_page or update_page with
the person keys who may read it. `whoami` says who the server thinks you are.

Sources matter here. Each page records where its content came from, in rough
order of authority: the DM's wiki, the DM's relationship graph, players'
session logs, then Discord chat. If you add something, say where it came from.

`whats_new` returns messages posted in the campaign's Discord channels that no
page accounts for yet. Read them, and where one contains something worth
keeping, write it up with create_page or update_page and pass the message's
`source` value through. That both credits it and clears it from the queue.
Judge what belongs: most chat is banter, and a wiki full of confidently
recorded jokes is worse than a thin one. `mark_filed` dismisses the rest.
"""


def build_server(
    cfg,
    library: Library,
    registry: people_mod.People,
    read_only: bool,
    default_identity: access_mod.Viewer,
    default_name: str,
    schema: schema_mod.Schema | None = None,
) -> MCPServer:
    schema = schema or schema_mod.load(Path(cfg.root))

    server = MCPServer(
        name="buried-star",
        title="The Buried Star",
        instructions=INSTRUCTIONS.strip(),
        version="2.0.0",
    )

    # -- identity ------------------------------------------------------

    def viewer(ctx: Context | None) -> tuple[access_mod.Viewer, str]:
        """Work out who is asking, from the token they presented.

        Headers are client-supplied, so nothing here trusts a claimed name. The
        only thing consulted is the bearer token, which the server minted, and
        an unrecognised one is a guest rather than an error.

        On stdio there are no headers at all; that caller already has the files
        on disk, so it gets `default_identity`.
        """
        headers = getattr(ctx, "headers", None) if ctx is not None else None
        if not headers:
            return default_identity, default_name

        raw = headers.get("authorization") or headers.get("Authorization") or ""
        scheme, _, token = raw.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return GUEST, "guest"

        person = registry.resolve(token.strip())
        if person is None:
            return GUEST, "guest"
        return access_mod.Viewer.person(person), person.name

    def can_see(entity: Entity, viewer) -> bool:
        return access_mod.readable(entity, viewer)

    def visible(viewer, kind: str | None = None) -> list[Entity]:
        return access_mod.visible(library.all(kind), viewer)

    def find(ref: str, ids: access_mod.Viewer) -> Entity | None:
        ref = ref.strip()
        candidates = visible(ids)
        if "/" in ref:
            kind, slug = ref.split("/", 1)
            for entity in candidates:
                if entity.kind == kind and entity.slug == slug:
                    return entity
        lowered = ref.lower()
        for entity in candidates:
            if entity.slug == lowered or entity.name.lower() == lowered:
                return entity
        partial = [e for e in candidates if lowered in e.name.lower()]
        return partial[0] if len(partial) == 1 else None

    def render(entity: Entity, ids: access_mod.Viewer, *, full: bool = True) -> dict:
        out: dict[str, Any] = {
            "ref": entity.ref,
            "name": entity.name,
            "kind": entity.kind,
            "summary": entity.summary,
        }
        if not full:
            return out

        body = access_mod.redact(entity.body, ids)
        allowed = {e.ref for e in visible(ids)}
        out.update(
            {
                "appearance": entity.appearance,
                "tags": entity.tags,
                # Links to pages this viewer can't see are removed, so a hidden
                # page's existence doesn't leak through someone else's page.
                "links": [r for r in entity.links if r in allowed],
                "sources": entity.sources,
                "data": dict(entity.data),
                "body": body,
                "art_count": len(entity.art),
                "linked_from": [
                    e.ref for e in library.backlinks(entity.ref) if e.ref in allowed
                ],
            }
        )
        if access_mod.withheld_from(entity.body, ids):
            out["note"] = (
                "This page contains secret sections you are not shown. "
                "Do not speculate about their contents."
            )
        return out

    def haystack(entity: Entity, ids: access_mod.Viewer) -> str:
        """Searchable text, secrets excluded unless this viewer may read them.

        Search must never match on hidden text: a page surfacing for a word
        only present in a secret would reveal the secret's contents.
        """
        return " ".join(
            [entity.name, entity.summary, access_mod.redact(entity.body, ids),
             " ".join(entity.tags)]
        ).lower()

    # -- read tools ----------------------------------------------------

    @server.tool(description="Who the server thinks you are, and what you can see.")
    def whoami(ctx: Context) -> dict:
        ids, name = viewer(ctx)
        entities = list(library.all())
        allowed = [e for e in entities if can_see(e, ids)]
        return {
            "you": name,
            "identities": sorted(ids.identities),
            # True only for the process holding the files, never for a token.
            "full_access": ids.all_access,
            "pages_visible": len(allowed),
            "pages_hidden": len(entities) - len(allowed),
            "can_write": not read_only,
        }

    @server.tool(
        description="Search the world by keyword across names, summaries, "
        "bodies and tags. Use this before creating anything."
    )
    def search_world(
        ctx: Context,
        query: Annotated[str, "Words to look for, e.g. 'vampire' or 'Brindlewood'"],
        kind: Annotated[str | None, "Limit to one kind. See get_structure."] = None,
        limit: Annotated[int, "Maximum results"] = 10,
    ) -> dict:
        ids, _ = viewer(ctx)
        q = query.lower().strip()
        if not q:
            return {"query": query, "total": 0, "results": []}
        hits = [
            e for e in visible(ids, kind)
            if q in haystack(e, ids)
        ]
        return {
            "query": query,
            "total": len(hits),
            "results": [render(e, ids, full=False) for e in hits[:limit]],
        }

    @server.tool(
        description="Get one page in full, including everything that links to "
        "it. Accepts a name ('Korran Mossborn'), a slug, or 'kind/slug'."
    )
    def get_page(ctx: Context, ref: Annotated[str, "Name, slug, or kind/slug"]) -> dict:
        ids, _ = viewer(ctx)
        entity = find(ref, ids)
        if entity is None:
            return {"error": f"Nothing found for {ref!r}. Try search_world first."}
        return render(entity, ids)

    @server.tool(description="List pages, optionally filtered by kind and tag.")
    def list_pages(
        ctx: Context,
        kind: Annotated[str | None, "One kind. See get_structure."] = None,
        tag: Annotated[str | None, "Only pages carrying this tag"] = None,
        limit: Annotated[int, "Maximum results"] = 100,
    ) -> dict:
        ids, _ = viewer(ctx)
        rows = [e for e in visible(ids, kind) if not tag or tag in e.tags]
        return {"total": len(rows),
                "results": [render(e, ids, full=False) for e in rows[:limit]]}

    @server.tool(
        description="A high-level picture of the world: how many pages of each "
        "kind, the major factions and places, and what is unfinished."
    )
    def world_overview(ctx: Context) -> dict:
        ids, _ = viewer(ctx)
        entities = visible(ids)
        by_kind: dict[str, int] = {}
        for entity in entities:
            by_kind[entity.kind] = by_kind.get(entity.kind, 0) + 1

        def named(kind: str, tag: str | None = None) -> list[str]:
            return [e.name for e in entities
                    if e.kind == kind and (tag is None or tag in e.tags)]

        return {
            "counts": by_kind,
            "total": len(entities),
            "player_characters": named("character", "player-character"),
            "factions": named("faction"),
            "regions_and_settlements": [
                e.name for e in entities
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
    def open_questions(ctx: Context) -> dict:
        ids, _ = viewer(ctx)
        entities = visible(ids)
        return {
            "needs_detail": [
                {"ref": e.ref, "name": e.name, "summary": e.summary}
                for e in entities if "needs-detail" in e.tags
            ],
            "needs_appearance": [
                {"ref": e.ref, "name": e.name}
                for e in entities if "needs-appearance" in e.tags
            ],
            "no_backlinks": [
                e.name for e in entities
                if not library.backlinks(e.ref) and not e.links
            ],
        }

    if read_only:
        return server

    # -- structure -----------------------------------------------------
    #
    # Everyone connected can reshape the world, not just the DM. That was a
    # deliberate call by the person who runs this: the table shares the
    # campaign, so it shares the shape of it. The safety net is git rather than
    # permissions, so every structural change snapshots first and anything
    # regrettable is one `git revert` away.

    def snapshot(what: str, who: str) -> bool:
        """Commit before reshaping anything, so it can be undone.

        Same net as the website's, and the same implementation: two copies of
        an undo button drift, and the one that drifts is the one nobody
        noticed was wrong.
        """
        return history_mod.snapshot(Path(cfg.root), what, who)

    @server.tool(
        description="The shape of the world: what kinds of page exist, how the "
        "front page is laid out, and what the site is called. Read this before "
        "changing any of it."
    )
    def get_structure(ctx: Context) -> dict:
        schema.reload_if_changed()
        counts = {k: sum(1 for _ in library.all(k)) for k in schema.keys}
        stray = sorted(
            d.name for d in Path(library.root).iterdir()
            if d.is_dir() and not schema.has(d.name)
        ) if Path(library.root).exists() else []
        return {
            "site": {"name": schema.name, "tagline": schema.tagline},
            "kinds": [{**k.as_dict(), "pages": counts.get(k.key, 0)}
                      for k in schema.kinds],
            "index_tags": [t.as_dict() for t in schema.index_tags],
            "home_sections": [s.as_dict() for s in schema.home],
            "folders_with_no_kind": stray,
            "note": "Anyone connected can change all of this. Changes are "
                    "committed to git first, so they can be undone.",
        }

    @server.tool(
        description="Add a kind of page, e.g. 'ship' or 'quest'. Use this when "
        "the campaign has a category of thing the wiki has no home for."
    )
    def add_kind(
        ctx: Context,
        key: Annotated[str, "Lowercase, singular, e.g. 'ship'"],
        label: Annotated[str, "Plural, as shown in the nav, e.g. 'Ships'"] = "",
        in_nav: Annotated[bool, "Show it in the top nav bar"] = True,
    ) -> dict:
        if read_only:
            return {"error": "This connection is read-only."}
        _, who = viewer(ctx)
        schema.reload_if_changed()
        ok, message = schema_mod.add_kind(schema, key, label, nav=in_nav)
        return {"ok": ok, "message": message, "kinds": list(schema.keys)} if ok \
            else {"error": message}

    @server.tool(
        description="Rename a kind, or change its label, nav visibility or "
        "position. Renaming moves every page and repoints every link."
    )
    def change_kind(
        ctx: Context,
        key: Annotated[str, "The kind to change"],
        rename_to: Annotated[str, "New key. Moves all its pages."] = "",
        label: Annotated[str, "New label for the nav"] = "",
        in_nav: Annotated[bool | None, "Show or hide it in the nav"] = None,
        position: Annotated[int | None, "0-based position in the nav"] = None,
    ) -> dict:
        if read_only:
            return {"error": "This connection is read-only."}
        _, who = viewer(ctx)
        schema.reload_if_changed()

        if rename_to.strip():
            snapshot(f"rename kind {key} to {rename_to}", who)
            ok, message = schema_mod.rename_kind(schema, key, rename_to,
                                                 library, label=label)
            if not ok:
                return {"error": message}
            if in_nav is not None or position is not None:
                schema_mod.update_kind(schema, rename_to, nav=in_nav,
                                       position=position)
            return {"ok": True, "message": message, "kinds": list(schema.keys)}

        ok, message = schema_mod.update_kind(
            schema, key, label=label or None, nav=in_nav, position=position)
        return {"ok": ok, "message": message} if ok else {"error": message}

    @server.tool(
        description="Remove a kind. Its pages have to go somewhere, so pass "
        "move_pages_to unless it's empty."
    )
    def remove_kind(
        ctx: Context,
        key: Annotated[str, "The kind to remove"],
        move_pages_to: Annotated[str, "Kind to move its pages into"] = "",
    ) -> dict:
        if read_only:
            return {"error": "This connection is read-only."}
        _, who = viewer(ctx)
        schema.reload_if_changed()
        snapshot(f"remove kind {key}", who)
        ok, message = schema_mod.remove_kind(schema, key, library, move_pages_to)
        return {"ok": ok, "message": message, "kinds": list(schema.keys)} if ok \
            else {"error": message}

    @server.tool(
        description="Move one page to a different kind, keeping its links."
    )
    def move_page(
        ctx: Context,
        ref: Annotated[str, "The page, as kind/slug"],
        to_kind: Annotated[str, "The kind to move it to"],
    ) -> dict:
        if read_only:
            return {"error": "This connection is read-only."}
        ids, _ = viewer(ctx)
        schema.reload_if_changed()
        entity = find(ref, ids)
        if entity is None:
            return {"error": f"Nothing found for {ref!r}."}
        ok, message = schema_mod.move_page(library, entity.ref, to_kind, schema)
        return {"ok": ok, "message": message} if ok else {"error": message}

    @server.tool(
        description="Rename the site, or change the line under the title on "
        "the front page."
    )
    def set_site(
        ctx: Context,
        name: Annotated[str, "What the wiki is called"] = "",
        tagline: Annotated[str, "One line under the title"] = "",
    ) -> dict:
        if read_only:
            return {"error": "This connection is read-only."}
        schema.reload_if_changed()
        ok, message = schema_mod.set_site(schema, name, tagline)
        return {"ok": ok, "message": message} if ok else {"error": message}

    @server.tool(
        description="Rebuild the front page. Each section is a heading over a "
        "filtered set of pages: {title, kind, tag?, any_tag?, data?}. Call "
        "get_structure first and send back a modified list; this replaces all "
        "of them."
    )
    def set_home_sections(
        ctx: Context,
        sections: Annotated[
            list[dict],
            "In display order, e.g. [{'title':'The Party','kind':'character',"
            "'tag':'player-character'}]",
        ],
    ) -> dict:
        if read_only:
            return {"error": "This connection is read-only."}
        _, who = viewer(ctx)
        schema.reload_if_changed()
        snapshot("rebuild the front page", who)
        ok, message = schema_mod.set_home(schema, sections)
        return {"ok": ok, "message": message,
                "home_sections": [s.as_dict() for s in schema.home]} if ok \
            else {"error": message}

    @server.tool(
        description="Rebuild the tag groups used to split kind index pages. "
        "Each group is {title, kind, tag}. Pages without a configured tag stay "
        "visible in an automatic Other section. Call get_structure first and "
        "send back a modified index_tags list; this replaces all of them."
    )
    def set_index_tags(
        ctx: Context,
        groups: Annotated[
            list[dict],
            "In display order, e.g. [{'title':'Player Characters',"
            "'kind':'character','tag':'player-character'}]",
        ],
    ) -> dict:
        if read_only:
            return {"error": "This connection is read-only."}
        _, who = viewer(ctx)
        schema.reload_if_changed()
        snapshot("rebuild index page tag groups", who)
        ok, message = schema_mod.set_index_tags(schema, groups)
        return {"ok": ok, "message": message,
                "index_tags": [t.as_dict() for t in schema.index_tags]} if ok \
            else {"error": message}

    # -- files ---------------------------------------------------------

    @server.tool(
        description="List the files attached to a page: maps, handouts, PDFs, "
        "recordings. Returns download URLs."
    )
    def list_files(
        ctx: Context,
        ref: Annotated[str, "Name, slug, or kind/slug"],
    ) -> dict:
        ids, _ = viewer(ctx)
        entity = find(ref, ids)
        if entity is None:
            return {"error": f"Nothing found for {ref!r}."}
        files = uploads_mod.attachments_of(entity)
        return {
            "page": entity.ref,
            "files": [
                {**f, "url": f"/wiki/file/{f['id']}"} for f in files
            ],
            "note": "Uploading is done on the website: open the page and click "
                    "Files. Assistants can read and remove them from here.",
        }

    @server.tool(
        description="Take a file off a page. The file itself is kept, in case "
        "another page uses it."
    )
    def remove_file(
        ctx: Context,
        ref: Annotated[str, "Name, slug, or kind/slug"],
        file_id: Annotated[str, "The file's id, from list_files"],
    ) -> dict:
        if read_only:
            return {"error": "This connection is read-only."}
        ids, _ = viewer(ctx)
        entity = find(ref, ids)
        if entity is None:
            return {"error": f"Nothing found for {ref!r}."}
        if not uploads_mod.detach_file(entity, file_id.strip()):
            return {"error": f"{file_id} isn't attached to {entity.ref}."}
        library.save(entity)
        return {"ok": True, "message": f"Removed from {entity.ref}."}

    # -- the Discord inbox ---------------------------------------------

    lore_dir = cfg.raw.get("lore_dir")
    inbox = inbox_mod.Inbox(
        Path(cfg.root),
        (Path(cfg.root) / lore_dir).resolve() if lore_dir else None,
    )

    @server.tool(
        description="Messages posted in the campaign's Discord channels that "
        "no page accounts for yet. Read them, write up what matters, and pass "
        "each message's `source` through to create_page or update_page."
    )
    def whats_new(
        ctx: Context,
        channel: Annotated[str, "Limit to one channel, e.g. 'lore-drop'"] = "",
        limit: Annotated[int, "How many messages, oldest first"] = 25,
    ) -> dict:
        try:
            waiting = inbox.unfiled(
                library, channel=channel.strip() or None,
                limit=max(1, min(limit, 100)),
            )
            total = inbox.count(library)
        except OSError as exc:
            return {"error": f"Can't read the lore archive: {exc}"}

        return {
            "waiting": total,
            "showing": len(waiting),
            "channels": inbox.channels(),
            "last_sync": inbox.last_sync(),
            "messages": [m.as_dict() for m in waiting],
            "note": "Most of this is chat. Only write up what the table would "
                    "call canon, and say so if you're unsure rather than "
                    "inventing detail to fill a page.",
        }

    @server.tool(
        description="Dismiss Discord messages that aren't worth a page. Use "
        "this for banter; anything you write up is cleared automatically by "
        "citing its source."
    )
    def mark_filed(
        ctx: Context,
        message_ids: Annotated[list[str], "IDs from whats_new"],
    ) -> dict:
        if read_only:
            return {"error": "This connection is read-only."}
        filed = inbox.file(message_ids or [])
        return {"filed": filed, "still_waiting": inbox.count(library)}

    # -- write tools ---------------------------------------------------

    def secret_block(text: str, audience: list[str] | None) -> str:
        return secrets_mod.wrap(text, audience) if audience else text

    @server.tool(
        description="Create a new page. Search first: prefer update_page if "
        "anything similar already exists."
    )
    def create_page(
        ctx: Context,
        kind: Annotated[str, "A kind from get_structure, e.g. 'place'"],
        name: Annotated[str, "Display name, e.g. 'Sister Lethra'"],
        summary: Annotated[str, "One sentence on what this is"] = "",
        appearance: Annotated[
            str, "What it looks like, visual and concrete. Feeds the art pipeline."
        ] = "",
        body: Annotated[str, "Longer prose. Markdown is fine."] = "",
        tags: Annotated[list[str] | None, "Tags, e.g. ['npc', 'ally']"] = None,
        links: Annotated[list[str] | None, "Related pages as 'kind/slug'"] = None,
        source: Annotated[str, "Where this came from, e.g. 'session 2026-08-12'"] = "",
        secret_audience: Annotated[
            list[str] | None,
            "Person keys who may read the body, e.g. ['dm','wren']. Omit for "
            "a page everyone can read.",
        ] = None,
        visible_to: Annotated[
            list[str] | None,
            "Hide the whole page from everyone except these person keys.",
        ] = None,
    ) -> dict:
        ids, who = viewer(ctx)
        schema.reload_if_changed()
        if not schema.has(kind):
            return {"error": f"kind must be one of: {', '.join(schema.keys)}. "
                             f"Add one with add_kind if the world needs it."}
        slug = slugify(name)
        if library.exists(kind, slug):
            return {"error": f"{kind}/{slug} already exists. Use update_page instead."}

        entity = Entity(
            kind=kind, slug=slug, name=name, summary=summary, appearance=appearance,
            body=secret_block(body, secret_audience),
            tags=list(tags or []), links=list(links or []),
            sources=[source] if source else [],
            visible_to=[v.lower() for v in visible_to] if visible_to else [],
        )
        entity.sources.append(f"written by {who}")
        library.save(entity)
        return {"created": entity.ref, "page": render(entity, ids)}

    @server.tool(
        description="Update a page. Text fields replace, list fields append. "
        "Body can be appended to rather than overwritten, which is usually what "
        "you want when adding what happened in a session."
    )
    def update_page(
        ctx: Context,
        ref: Annotated[str, "Name, slug, or kind/slug"],
        summary: Annotated[str | None, "Replaces the existing summary"] = None,
        appearance: Annotated[str | None, "Replaces the existing appearance"] = None,
        append_body: Annotated[str | None, "Appended to the end of the body"] = None,
        add_tags: Annotated[list[str] | None, "Tags to add"] = None,
        add_links: Annotated[list[str] | None, "Links to add, as 'kind/slug'"] = None,
        source: Annotated[str, "Where this update came from"] = "",
        secret_audience: Annotated[
            list[str] | None,
            "If set, the appended text becomes a secret only these people can read.",
        ] = None,
    ) -> dict:
        ids, who = viewer(ctx)
        entity = find(ref, ids)
        if entity is None:
            return {"error": f"Nothing found for {ref!r}."}

        if summary is not None:
            entity.summary = summary
        if appearance is not None:
            entity.appearance = appearance
        if append_body:
            addition = secret_block(append_body.strip(), secret_audience)
            entity.body = (entity.body.rstrip() + "\n\n" + addition).strip()
        if add_tags:
            entity.tags = list(dict.fromkeys(entity.tags + list(add_tags)))
        if add_links:
            entity.links = list(dict.fromkeys(entity.links + list(add_links)))
        for note in ([source] if source else []) + [f"updated by {who}"]:
            if note not in entity.sources:
                entity.sources.append(note)

        library.save(entity)
        return {"updated": entity.ref, "page": render(entity, ids)}

    @server.tool(
        description="Link two pages to each other. Cross-links are what make "
        "the wiki useful, so link generously."
    )
    def link_pages(
        ctx: Context,
        a: Annotated[str, "First page: name, slug, or kind/slug"],
        b: Annotated[str, "Second page"],
        one_way: Annotated[bool, "Only link a to b, not back"] = False,
    ) -> dict:
        ids, _ = viewer(ctx)
        first, second = find(a, ids), find(b, ids)
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
    """Check an HTTP Basic header against the wiki password."""
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
    allowed_hosts: list[str],
    registry: people_mod.People,
    wiki_dir: Path | None = None,
    wiki_password: str = "",
    live_routes: list | None = None,
    session_secret: str = "",
):
    """Wrap the MCP app with auth.

    Only a person's own token opens this door. There used to be a shared guest
    token as well, which let an unrecognised caller in as nobody: no secrets,
    but the write tools were still reachable, so a stranger holding it could
    edit the campaign.

    It was dropped after a copy turned up pasted into a Discord channel. That
    is what a shared secret does eventually, and there was nothing left for it
    to buy, because everyone has a personal token that also says who they are,
    which this one never could.
    """
    from mcp.server.mcpserver.server import TransportSecuritySettings
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Mount

    def accepted(header: str) -> bool:
        scheme, _, supplied = header.partition(" ")
        if scheme.lower() != "bearer" or not supplied:
            return False
        # `resolve` compares against every known token in constant time, so a
        # near-miss does not take measurably longer than a wild guess.
        return registry.resolve(supplied.strip()) is not None

    class Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            # The live wiki does its own sign-in, so it isn't gated here.
            if live_routes and request.url.path.startswith("/wiki"):
                return await call_next(request)

            if wiki_dir is not None and request.url.path.startswith("/wiki"):
                if not wiki_password or _basic_ok(
                    request.headers.get("authorization", ""), wiki_password
                ):
                    return await call_next(request)
                return Response(
                    "The Buried Star is private.", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="The Buried Star"'},
                )

            if not accepted(request.headers.get("authorization", "")):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    security = TransportSecuritySettings(
        allowed_hosts=allowed_hosts, allowed_origins=["*"]
    )
    inner = server.streamable_http_app(transport_security=security)
    routes = list(inner.routes)
    middleware = [Middleware(Auth)]

    if live_routes:
        from starlette.middleware.sessions import SessionMiddleware

        # Routes first so they win over any static mount.
        routes = list(live_routes) + routes
        middleware.append(
            Middleware(
                SessionMiddleware,
                secret_key=session_secret,
                session_cookie="buried_star",
                max_age=60 * 60 * 24 * 30,
                same_site="lax",
                https_only=True,
            )
        )
    elif wiki_dir is not None:
        from starlette.staticfiles import StaticFiles

        routes.append(
            Mount("/wiki", app=StaticFiles(directory=str(wiki_dir), html=True),
                  name="wiki")
        )

    return Starlette(
        routes=routes,
        middleware=middleware,
        lifespan=inner.router.lifespan_context,
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--http", action="store_true", help="Serve over HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--read-only", action="store_true",
                    help="Serve without the create/update/link tools")
    ap.add_argument("--as", dest="as_person", metavar="KEY",
                    help="On stdio, view the world as this person. Default: full access.")
    ap.add_argument("--wiki", help="Serve a static site folder at /wiki")
    ap.add_argument(
        "--wiki-live", action="store_true",
        help="Serve the wiki live at /wiki, so each person picks their name and "
             "sees their own secrets. Replaces --wiki.",
    )
    ap.add_argument("--wiki-password",
                    default=os.environ.get("UNIVERSE_WIKI_PASSWORD", ""),
                    help="Password for /wiki via HTTP Basic. Omit to leave it open.")
    ap.add_argument("--allowed-host", action="append", default=[],
                    help="Public hostname clients connect through. Required behind "
                         "a tunnel; the transport rejects unknown Host headers.")
    args = ap.parse_args(argv[1:])

    cfg = config_mod.load()
    library = Library(cfg.content_dir)
    if not cfg.content_dir.exists():
        print(f"No content at {cfg.content_dir}. Run the seed scripts first.",
              file=sys.stderr)
        return 1

    registry = people_mod.load(cfg.root)

    # stdio callers already hold the files, so they get everything unless they
    # ask to be someone specific.
    # Full access is a flag, not a set containing everyone's key. The old
    # spelling was indistinguishable from a person who happened to be in every
    # audience, and it silently widened whenever someone joined the table.
    default_identity = access_mod.Viewer.local()
    default_name = "local (full access)"
    if args.as_person:
        person = registry.members.get(args.as_person.strip().lower())
        if person is None:
            print(f"No person with key {args.as_person!r} in people.yaml.",
                  file=sys.stderr)
            return 1
        default_identity = access_mod.Viewer.person(person)
        default_name = person.name

    # One schema object shared by the tools and the wiki, so a kind added
    # through Claude appears in the site's nav without a restart.
    schema = schema_mod.load(cfg.root)
    server = build_server(cfg, library, registry, args.read_only,
                          default_identity, default_name, schema=schema)
    count = sum(1 for _ in library.all())
    mode = "read-only" if args.read_only else "read/write"
    secret_pages = sum(
        1 for e in library.all()
        if secrets_mod.has_secrets(e.body) or e.visible_to
    )

    if not args.http:
        print(f"[mcp] buried-star, {count} pages ({secret_pages} with secrets), "
              f"{mode}, stdio as {default_name}", file=sys.stderr)
        server.run(transport="stdio")
        return 0

    if not registry.tokens:
        print(
            "Refusing to serve over HTTP with no personal tokens.\n\n"
            "Nobody could connect, and an endpoint that accepts nothing is\n"
            "just a slower way of being offline. Mint them with:\n"
            "  python tools\\make_people_tokens.py",
            file=sys.stderr,
        )
        return 2

    try:
        import uvicorn
    except ImportError:
        print("HTTP mode needs uvicorn:  pip install uvicorn", file=sys.stderr)
        return 1

    live_routes = None
    session_secret = ""
    if args.wiki_live:
        from universe import webapp

        # A stable secret, so sign-ins survive a restart. Generated once.
        secret_path = cfg.root / ".session-secret"
        if not secret_path.exists():
            import secrets as pysecrets

            secret_path.write_text(pysecrets.token_urlsafe(32), encoding="utf-8")
        session_secret = secret_path.read_text(encoding="utf-8").strip()
        live_routes = webapp.build(cfg, library, registry, schema=schema)
        from universe import gate as gate_mod

        guarded = ("passphrase required" if gate_mod.is_enabled(cfg.root)
                   else "OPEN, no passphrase")
        print(
            f"[mcp] wiki: live, {len(registry.members)} name(s) to pick from, "
            f"{guarded}",
            file=sys.stderr,
        )

    wiki_dir = None
    if args.wiki and not args.wiki_live:
        wiki_dir = Path(args.wiki)
        if not wiki_dir.is_absolute():
            wiki_dir = cfg.root / wiki_dir
        if not (wiki_dir / "index.html").exists():
            print(f"No site at {wiki_dir}. Build it: python tools/export_site.py",
                  file=sys.stderr)
            return 1

    hosts = [f"{args.host}:{args.port}", f"localhost:{args.port}",
             f"127.0.0.1:{args.port}", *args.allowed_host]
    print(
        f"[mcp] buried-star, {count} pages ({secret_pages} with secrets), {mode}\n"
        f"[mcp] {len(registry.members)} people, {len(registry.tokens)} personal token(s)\n"
        f"[mcp] http://{args.host}:{args.port}/mcp (bearer token required)\n"
        + (
            f"[mcp] http://{args.host}:{args.port}/wiki "
            f"(sign-in required, per-person secrets)\n" if live_routes
            else "[mcp] http://{}:{}/wiki ({})\n".format(
                args.host, args.port,
                "password protected" if args.wiki_password
                else "OPEN - anyone with the link can read the public pages",
            ) if wiki_dir else ""
        )
        + f"[mcp] accepting Host: {', '.join(dict.fromkeys(hosts))}",
        file=sys.stderr,
    )
    uvicorn.run(
        http_app(server, list(dict.fromkeys(hosts)), registry,
                 wiki_dir, args.wiki_password, live_routes, session_secret),
        host=args.host, port=args.port, log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
