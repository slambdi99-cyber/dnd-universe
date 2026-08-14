"""The live wiki: sign-in, per-person rendering, editing and art.

Unlike the static export, this knows who is reading. Each page is rendered for
whoever is signed in: their secrets appear, other people's don't, and pages
restricted away from them don't exist as far as they can tell.

Signing in is picking your name off a list. There is no password, which is a
deliberate choice for a table of friends: it means the secrets feature is a DM
screen, not a lock. Worth remembering before putting anything genuinely
sensitive behind it.
"""

from __future__ import annotations

import html
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.responses import (FileResponse, HTMLResponse,
                                 RedirectResponse, Response)
from starlette.routing import Route

from . import access as access_mod
from . import gate as gate_mod
from . import inbox as inbox_mod
from . import schema as schema_mod
from . import uploads as uploads_mod
from . import people as people_mod
from . import secrets as secrets_mod
from . import site as site_mod
from . import wiki as wiki_mod
from . import panels
from . import tooltips as tooltips_mod
from .entities import Entity, Library, slugify


def _auth_page(title: str, base: str, inner: str) -> HTMLResponse:
    return HTMLResponse(
        site_mod.shell(title, base, inner, "[]", user=None, live=True)
    )


def build(cfg, library: Library, registry: people_mod.People,
          schema: schema_mod.Schema | None = None) -> list[Route]:
    """Routes for /wiki. Everything but the guide needs someone signed in.

    Signing in only establishes which secrets to render; it keeps nobody out.
    Anyone with the link can claim any name on the roster, or add themselves.
    """

    schema = schema or schema_mod.load(Path(cfg.root))
    site_mod.use(schema)

    lore_dir = cfg.raw.get("lore_dir")
    wiki = wiki_mod.Wiki(
        cfg=cfg, library=library, registry=registry, schema=schema,
        inbox=inbox_mod.Inbox(
            Path(cfg.root),
            (Path(cfg.root) / lore_dir).resolve() if lore_dir else None,
        ),
    )

    # Short names for what this module still does itself. Everything else about
    # a request now belongs to `wiki`, and the features to `panels`.
    render = wiki.render
    require_login = wiki.require_login
    viewer_for = wiki.viewer_for
    entities_for = wiki.entities_for
    images_for = wiki.images_for
    reload_people = wiki.reload_people
    roster = wiki.roster

    # -- auth ----------------------------------------------------------

    async def enter(request):
        """The shared passphrase, in front of everything but the guide.

        Rate-limited only by scrypt, which takes ~60ms per attempt. That is
        slow enough to make guessing a five-word passphrase pointless and fast
        enough that nobody notices typing theirs.
        """
        if not gate_mod.is_enabled(Path(cfg.root)):
            return RedirectResponse("/wiki/login", status_code=303)

        if request.method == "GET":
            if request.session.get("gate"):
                return RedirectResponse("/wiki/login", status_code=303)
            return _auth_page("The Buried Star", "/wiki/", _gate_form())

        form = await request.form()
        attempt = str(form.get("passphrase", ""))
        ok = await run_in_threadpool(gate_mod.check, Path(cfg.root), attempt)
        if not ok:
            return _auth_page(
                "The Buried Star", "/wiki/",
                _gate_form(error="That isn't it. Ask in the group chat."),
            )
        request.session["gate"] = True
        return RedirectResponse("/wiki/login", status_code=303)

    async def login(request):
        """Pick who you are. No password.

        This is an honour system by design: nothing stops someone choosing a
        name that isn't theirs, so the secrets feature is a DM screen rather
        than a lock. Fine for a table of friends, and worth remembering before
        putting anything genuinely sensitive behind it.
        """
        if gate_mod.is_enabled(Path(cfg.root)) and not request.session.get("gate"):
            return RedirectResponse("/wiki/enter", status_code=303)

        if request.method == "GET":
            if request.session.get("who"):
                return RedirectResponse("/wiki/", status_code=303)
            return _auth_page("Who are you?", "/wiki/", _signin_form(roster()))

        form = await request.form()
        key = str(form.get("who", "")).strip().lower()
        reload_people()
        if key not in registry.members:
            return _auth_page(
                "Who are you?", "/wiki/",
                _signin_form(roster(), error="Pick a name from the list."),
            )
        request.session["who"] = key
        return RedirectResponse("/wiki/", status_code=303)

    async def add_person(request):
        if gate_mod.is_enabled(Path(cfg.root)) and not request.session.get("gate"):
            return RedirectResponse("/wiki/enter", status_code=303)
        if request.method == "GET":
            return RedirectResponse("/wiki/login", status_code=303)

        form = await request.form()
        name = str(form.get("name", "")).strip()
        character = str(form.get("character", "")).strip()
        person = people_mod.add_person(Path(cfg.root), name, character)
        if person is None:
            return _auth_page(
                "Who are you?", "/wiki/",
                _signin_form(
                    roster(),
                    error="Give a name that isn't already on the list."
                    if name else "Enter a name.",
                ),
            )
        reload_people()
        request.session["who"] = person.key
        return RedirectResponse("/wiki/", status_code=303)

    async def logout(request):
        request.session.clear()
        return RedirectResponse("/wiki/login", status_code=303)

    async def guide(request):
        """The player guide. Readable without an account on purpose.

        It's the page that explains how to get an account in the first place,
        so putting it behind the login would be a locked door with the key
        inside. It contains no campaign content.
        """
        _, user = viewer_for(request)
        source = Path(cfg.root) / "GUIDE.md"
        if not source.exists():
            return render("Guide",
                          "<h1>Guide</h1><p class='hint'>GUIDE.md is missing "
                          "from the project folder.</p>",
                          user=user, status=404)
        return render("Guide",
                      site_mod.render_guide(source.read_text(encoding="utf-8")),
                      user=user)

    # -- pages ---------------------------------------------------------

    async def index(request):
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        entities, _ = entities_for(viewer)
        images = images_for(entities)
        return render(
            schema.name,
            site_mod.render_index(entities, images, "/wiki/", editable=True),
            site_mod.search_index(entities, viewer), user=user, tips=True,
        )

    async def kind_index(request):
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        kind = request.path_params["kind"]
        entities, _ = entities_for(viewer)
        items = [e for e in entities if e.kind == kind]
        if not items:
            return HTMLResponse("Not found", status_code=404)
        images = images_for(entities)
        return render(
            schema.label(kind),
            site_mod.render_kind_index(kind, items, images, "/wiki/"),
            site_mod.search_index(entities, viewer), user=user, tips=True,
        )

    async def page(request):
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        kind, slug = request.path_params["kind"], request.path_params["slug"]
        entities, allowed = entities_for(viewer)
        if f"{kind}/{slug}" not in allowed:
            # Deliberately the same response as a page that doesn't exist, so
            # a 403 can't be used to enumerate hidden pages.
            return render("Not found",
                          "<h1>Not found</h1><p class='hint'>No such page.</p>",
                          user=user, status=404)
        entity = library.load(kind, slug)
        images = images_for(entities)
        return render(
            entity.name,
            site_mod.render_body(entity, library, images, "/wiki/", viewer, allowed,
                                 editable=True),
            site_mod.search_index(entities, viewer), user=user, tips=True,
        )

    async def tooltips_js(request):
        """The tooltip index, as a script so browsers cache it across pages.

        Built per viewer: a page you can't see must not appear here either, or
        hovering a name would reveal something the page itself hides.
        """
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, _ = viewer_for(request)
        entities, _ = entities_for(viewer)
        index = tooltips_mod.build(entities, viewer, Path(cfg.root), "/wiki/")
        return Response(
            f"window.__TIPS__={index};\n{tooltips_mod.TOOLTIP_JS}",
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    async def connect(request):
        """Everything someone needs to point their own Claude at the world.

        Self-service on purpose: they signed in already, so the server knows
        who they are and can mint their token itself. Nobody has to ask the DM
        for a credential, which was the last manual step in onboarding.
        """
        redirect = require_login(request)
        if redirect:
            return redirect
        key = request.session.get("who")
        person = registry.members.get(key) if key else None
        if person is None:
            return render("Connect",
                          "<h1>Connect</h1><p class='hint'>Your account isn't "
                          "linked to anyone. Ask your DM.</p>",
                          user=None, status=404)

        token = people_mod.ensure_token(Path(cfg.root), person.key)
        base = str(request.base_url).rstrip("/")
        return render("Connect Claude",
                      _connect_page(person.name, f"{base}/mcp", token),
                      user=person.name)

    # -- editing --------------------------------------------------------

    def form_values(entity: Entity | None, viewer: access_mod.Viewer) -> dict:
        if entity is None:
            return {"name": "", "summary": "", "appearance": "", "body": "",
                    "tags": "", "links": "", "kind": "place", "source": ""}
        return {
            "name": entity.name,
            "summary": entity.summary,
            "appearance": entity.appearance,
            "body": access_mod.redact(entity.body, viewer),
            "tags": ", ".join(entity.tags),
            "links": ", ".join(entity.links),
            "kind": entity.kind,
        }

    async def edit(request):
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        kind, slug = request.path_params["kind"], request.path_params["slug"]
        _, allowed = entities_for(viewer)
        if f"{kind}/{slug}" not in allowed:
            return HTMLResponse("Not found", status_code=404)
        entity = library.load(kind, slug)

        withheld = len(secrets_mod.withheld_blocks(entity.body, viewer.identities))

        if request.method == "GET":
            return render(
                f"Editing {entity.name}",
                _edit_form(form_values(entity, viewer), registry, withheld=withheld,
                           action=f"/wiki/{kind}/{slug}/edit"),
                user=user,
            )

        form = await request.form()
        entity.name = str(form.get("name", entity.name)).strip() or entity.name
        entity.summary = str(form.get("summary", "")).strip()
        entity.appearance = str(form.get("appearance", "")).strip()
        entity.tags = [t.strip() for t in str(form.get("tags", "")).split(",") if t.strip()]
        entity.links = [
            l.strip() for l in str(form.get("links", "")).split(",")
            if l.strip() and "/" in l
        ]

        body = str(form.get("body", ""))
        secret_text = str(form.get("secret_text", "")).strip()
        audience = [a for a in form.getlist("audience") if a]
        if secret_text and audience:
            body = body.rstrip() + "\n\n" + secrets_mod.wrap(secret_text, audience)
        # Anything this editor could not see is carried across untouched.
        entity.body = secrets_mod.merge_edit(entity.body, body, viewer.identities)

        note = f"edited by {user} on the wiki"
        if note not in entity.sources:
            entity.sources.append(note)
        library.save(entity)
        return RedirectResponse(f"/wiki/{kind}/{slug}.html", status_code=303)

    async def new_page(request):
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)

        if request.method == "GET":
            # Prefilled from the query string, which is how the inbox hands a
            # Discord message straight into the form: the text is already
            # there and you write over it rather than retyping it.
            values = form_values(None, viewer)
            for field in ("name", "summary", "body", "kind", "source"):
                supplied = request.query_params.get(field, "").strip()
                if supplied and (field != "kind" or schema.has(supplied)):
                    values[field] = supplied
            return render("New page",
                          _edit_form(values, registry, withheld=0,
                                     action="/wiki/new", creating=True),
                          user=user)

        form = await request.form()
        name = str(form.get("name", "")).strip()
        kind = str(form.get("kind", "")).strip()
        if not name or not schema.has(kind):
            return render(
                "New page",
                _edit_form({**form_values(None, viewer), "name": name,
                            "kind": kind, "body": str(form.get("body", "")),
                            "summary": str(form.get("summary", "")),
                            "source": str(form.get("source", ""))},
                           registry, withheld=0, action="/wiki/new",
                           creating=True,
                           error="Give it a name and pick a type."),
                user=user,
            )

        slug = slugify(name)
        if library.exists(kind, slug):
            return RedirectResponse(f"/wiki/{kind}/{slug}.html", status_code=303)

        body = str(form.get("body", ""))
        secret_text = str(form.get("secret_text", "")).strip()
        audience = [a for a in form.getlist("audience") if a]
        if secret_text and audience:
            body = body.rstrip() + "\n\n" + secrets_mod.wrap(secret_text, audience)

        source = str(form.get("source", "")).strip()
        entity = Entity(
            kind=kind, slug=slug, name=name,
            summary=str(form.get("summary", "")).strip(),
            appearance=str(form.get("appearance", "")).strip(),
            body=body.strip(),
            tags=[t.strip() for t in str(form.get("tags", "")).split(",") if t.strip()],
            links=[l.strip() for l in str(form.get("links", "")).split(",")
                   if l.strip() and "/" in l],
            sources=([source] if source else []) + [f"created by {user} on the wiki"],
        )
        library.save(entity)
        # A page citing a Discord message is the message being dealt with, so
        # the inbox drops it without anyone pressing a second button.
        return RedirectResponse(f"/wiki/{kind}/{slug}.html", status_code=303)

    return panels.routes(wiki) + [
        Route("/wiki/new", new_page, methods=["GET", "POST"]),
        Route("/wiki/{kind}/{slug}/edit", edit, methods=["GET", "POST"]),
        Route("/wiki/enter", enter, methods=["GET", "POST"]),
        Route("/wiki/login", login, methods=["GET", "POST"]),
        Route("/wiki/people/new", add_person, methods=["GET", "POST"]),
        Route("/wiki/logout", logout),
        Route("/wiki/guide", guide),
        Route("/wiki/connect", connect),
        Route("/wiki/", index),
        Route("/wiki/index.html", index),
        Route("/wiki/tooltips.js", tooltips_js),
        Route("/wiki/{kind}/index.html", kind_index),
        Route("/wiki/{kind}/{slug}.html", page),
    ]


# -- forms -------------------------------------------------------------

def _edit_form(v: dict, registry: people_mod.People, withheld: int,
               action: str, creating: bool = False, error: str = "") -> str:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    title = "New page" if creating else f"Editing {v['name']}"

    kinds = "".join(
        f'<option value="{html.escape(k.key)}"'
        f'{" selected" if k.key == v["kind"] else ""}>'
        f'{html.escape(k.label)}</option>'
        for k in site_mod.SCHEMA.kinds
    )
    kind_field = (
        f'  <label for="k">Type</label>\n  <select id="k" name="kind">{kinds}</select>'
        if creating else ""
    )
    # Carried through the form rather than the URL, so a page made from a
    # Discord message credits the message even after a validation round-trip.
    source_field = (
        f'<input type="hidden" name="source" value="{html.escape(v.get("source", ""))}">'
        if creating and v.get("source") else ""
    )
    from_note = (
        f'<div class="notice">Written up from a message in Discord. The page '
        f'will credit it, and the inbox will stop showing it.</div>'
        if creating and v.get("source", "").startswith("discord:") else ""
    )

    warning = ""
    if withheld:
        warning = (
            f'<div class="notice">This page has {withheld} secret section'
            f'{"s" if withheld != 1 else ""} you cannot read. '
            f"They are kept exactly as they are, and will sit at the end of the "
            f"page after you save.</div>"
        )

    boxes = "".join(
        f'<label class="cb"><input type="checkbox" name="audience" '
        f'value="{html.escape(p.key)}"> {html.escape(p.name)}'
        f'{" (DM)" if p.is_dm else ""}</label>'
        for p in registry.members.values()
    )

    return f"""
<h1>{html.escape(title)}</h1>
{err}
{warning}
{from_note}
<form class="auth wide" method="post" action="{action}">
{source_field}
{kind_field}
  <label for="n">Name</label>
  <input id="n" name="name" value="{html.escape(v['name'])}" required>

  <label for="s">Summary <span class="hint">one sentence on what it is</span></label>
  <input id="s" name="summary" value="{html.escape(v['summary'])}">

  <label for="a">Appearance <span class="hint">what it looks like, concrete
    and visual. This is what the art generator draws, so write physique and
    colour, not "a tortle".</span></label>
  <input id="a" name="appearance" value="{html.escape(v['appearance'])}">

  <label for="b">Body <span class="hint">markdown is fine</span></label>
  <textarea id="b" name="body" rows="16">{html.escape(v['body'])}</textarea>

  <label for="t">Tags <span class="hint">comma separated</span></label>
  <input id="t" name="tags" value="{html.escape(v['tags'])}">

  <label for="l">Links <span class="hint">comma separated, as
    place/brindlewood</span></label>
  <input id="l" name="links" value="{html.escape(v['links'])}">

  <fieldset class="secretbox">
    <legend>Add a secret</legend>
    <p class="hint">Only the people you tick will ever see this, on the site or
    through their own Claude. Leave it empty for nothing.</p>
    <textarea name="secret_text" rows="4"
              placeholder="Something only some of us know..."></textarea>
    <div class="cbs">{boxes}</div>
  </fieldset>

  <button type="submit">{"Create" if creating else "Save"}</button>
</form>
"""


def _connect_page(name: str, url: str, token: str) -> str:
    """Connection details for any MCP client, not one vendor's.

    MCP is an open protocol with a lot of implementations, and the table
    shouldn't all have to run the same assistant to use the wiki. So the page
    leads with the three facts every client needs (endpoint, transport, header)
    and treats the per-client recipes as convenience rather than the way in.
    """
    facts = (
        f"Name:      buried-star\n"
        f"Transport: HTTP (streamable HTTP, not SSE, not stdio)\n"
        f"URL:       {url}\n"
        f"Header:    Authorization: Bearer {token}"
    )
    config = (
        '{\n'
        '  "mcpServers": {\n'
        '    "buried-star": {\n'
        '      "type": "http",\n'
        f'      "url": "{url}",\n'
        '      "headers": {\n'
        f'        "Authorization": "Bearer {token}"\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '}'
    )
    prompt = (
        "Please connect me to an MCP server.\n\n"
        f"  Name:      buried-star\n"
        f"  Transport: HTTP (streamable HTTP, not SSE, not stdio)\n"
        f"  URL:       {url}\n"
        f"  Auth:      an Authorization header with the value\n"
        f"             Bearer {token}\n\n"
        "Work out how MCP servers are added in whichever client you're running "
        "in, do it if you can, and tell me if there's a step I have to take "
        "myself. Then verify by calling whoami: it should come back with my name."
    )
    cli = (
        f"claude mcp add --transport http buried-star {url} "
        f'--header "Authorization: Bearer {token}"'
    )
    curl = (
        f"curl -s {url} \\\n"
        f'  -H "Authorization: Bearer {token}" \\\n'
        f'  -H "Content-Type: application/json" \\\n'
        f'  -H "Accept: application/json, text/event-stream" \\\n'
        f"  -d '{{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}}'"
    )

    def block(idx: int, text: str) -> str:
        return (
            f'<div class="copyblock"><pre id="b{idx}">{html.escape(text)}</pre>'
            f'<button type="button" onclick="cp(\'b{idx}\',this)">Copy</button></div>'
        )

    return f"""
<h1>Connect an assistant</h1>
<p class="summary">Signed in as {html.escape(name)}. Everything below already
has your own details in it.</p>

<p>This wiki speaks <a href="https://modelcontextprotocol.io">MCP</a>, which is
an open protocol rather than one company's feature. Anything that speaks it can
read this world and write to it: Claude, ChatGPT, Cursor, VS Code, Zed, Goose,
Cline, or something you wrote yourself. What you can see is tied to you, so use
your own details and don't pass them around.</p>

<h2>The details, for any client</h2>
{block(0, facts)}
<p class="hint">Most clients ask for exactly these three things somewhere in
their settings, under MCP, Connectors, or Tools.</p>

<h2>Easiest: paste this into whatever you use</h2>
<p class="hint">Assistants are generally good at configuring themselves.</p>
{block(1, prompt)}

<h2>Claude Code, and other CLIs that copied its syntax</h2>
{block(2, cli)}

<h2>A config file</h2>
<p class="hint">Claude Desktop, Cursor, Windsurf, Cline, Zed and most others use
this shape, in their own settings file. Some spell the top-level key
<code>servers</code> or <code>mcp.servers</code>; the inside is the same.</p>
{block(3, config)}

<h2>Check it worked</h2>
<p>Ask your assistant: <em>call whoami on buried-star</em>. It should come back
with your name. If it says <em>guest</em>, the header didn't take.</p>

<p class="hint">Or without an assistant at all, to prove the endpoint is up:</p>
{block(4, curl)}

<p class="hint">Treat this like a password: it can write to the campaign, and
it decides whose secrets you're shown. If it leaks, tell your DM and it can be
replaced.</p>

<script>
function cp(id, btn) {{
  navigator.clipboard.writeText(document.getElementById(id).innerText).then(
    () => {{ const t = btn.textContent; btn.textContent = 'Copied';
             setTimeout(() => btn.textContent = t, 1500); }},
    () => {{ btn.textContent = 'Press Ctrl+C'; }}
  );
}}
</script>
"""


def _gate_form(error: str = "") -> str:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    return f"""
<h1>The Buried Star</h1>
<p class="summary">Our campaign wiki. There's one passphrase for the whole
table; it's in the group chat.</p>
{err}
<form class="auth" method="post" action="/wiki/enter">
  <label for="pp">Passphrase</label>
  <input id="pp" name="passphrase" type="password" autocomplete="current-password"
         autofocus required>
  <button type="submit">Come in</button>
</form>
<p class="hint">You'll be asked once, then not again for about a month. New
here? Read the <a href="/wiki/guide">guide</a>.</p>
"""


def _signin_form(roster: list, error: str = "") -> str:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""

    buttons = "".join(
        f'<button class="who" type="submit" name="who" '
        f'value="{html.escape(p.key)}">'
        f'<span class="n">{html.escape(p.name)}</span>'
        f'<span class="c">{html.escape(p.character) if p.character else ("Dungeon Master" if p.is_dm else "Player")}</span>'
        f"</button>"
        for p in roster
    )

    return f"""
<h1>Who are you?</h1>
<p class="summary">Pick your name. The world looks different depending on who
is reading it.</p>
{err}
<form method="post" action="/wiki/login">
  <div class="whogrid">{buttons}</div>
</form>

<details class="newperson">
  <summary>Someone new?</summary>
  <form class="auth" method="post" action="/wiki/people/new">
    <label for="nn">Your name</label>
    <input id="nn" name="name" maxlength="60" required>
    <label for="nc">Character <span class="hint">optional, if you have
      one</span></label>
    <input id="nc" name="character" maxlength="60">
    <button type="submit">Add me</button>
  </form>
</details>

<p class="hint">First time here? Read the <a href="/wiki/guide">guide</a>.</p>
"""
