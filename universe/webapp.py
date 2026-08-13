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

from . import inbox as inbox_mod
from . import people as people_mod
from . import secrets as secrets_mod
from . import site as site_mod
from . import tooltips as tooltips_mod
from .entities import KINDS, Entity, Library, slugify

PUBLIC: frozenset[str] = frozenset()


def _auth_page(title: str, base: str, inner: str) -> HTMLResponse:
    return HTMLResponse(
        site_mod.shell(title, base, inner, "[]", user=None, live=True)
    )


def build(cfg, library: Library, registry: people_mod.People) -> list[Route]:
    """Routes for /wiki. Everything but the guide needs someone signed in.

    Signing in only establishes which secrets to render; it keeps nobody out.
    Anyone with the link can claim any name on the roster, or add themselves.
    """

    # Built on first use, so importing torch and diffusers is deferred until
    # someone actually asks for a picture.
    _art = None

    lore_dir = cfg.raw.get("lore_dir")
    inbox = inbox_mod.Inbox(
        Path(cfg.root),
        (Path(cfg.root) / lore_dir).resolve() if lore_dir else None,
    )

    def nav_extra(user: str | None) -> str:
        """The writing actions, on every page rather than just the front one.

        Adding something was previously a link on the index, which meant
        reading a page about a place and wanting to write down what happened
        there took you back to the front page first. Nobody does that; they
        forget instead.
        """
        if not user:
            return ""
        try:
            waiting = inbox.count(library)
        except OSError:
            waiting = 0
        badge = f'<span class="badge">{waiting}</span>' if waiting else ""
        return (
            '<a class="act" href="/wiki/new">+ New</a>'
            f'<a class="act" href="/wiki/inbox">Inbox{badge}</a>'
        )

    def render(title: str, body: str, index_json: str = "[]", *,
               user: str | None = None, tips: bool = False,
               status: int = 200) -> HTMLResponse:
        return HTMLResponse(
            site_mod.shell(title, "/wiki/", body, index_json, user=user,
                           live=True, tips=tips, extra=nav_extra(user)),
            status_code=status,
        )

    def reload_people() -> None:
        """Pick up anyone added since the server started."""
        fresh = people_mod.load(Path(cfg.root))
        if fresh.members:
            registry.members = fresh.members

    def viewer_for(request) -> tuple[frozenset[str], str | None]:
        key = request.session.get("who")
        if not key:
            return PUBLIC, None
        person = registry.members.get(key)
        if person is None:
            reload_people()
            person = registry.members.get(key)
        if person is None:
            return PUBLIC, None
        return person.identities, person.name

    def entities_for(viewer: frozenset[str]):
        everything = sorted(library.all(), key=lambda e: (e.kind, e.name))
        allowed_list = site_mod.visible_to(everything, viewer)
        return allowed_list, {e.ref for e in allowed_list}

    def images_for(entities) -> dict[str, str]:
        out = {}
        for entity in entities:
            if entity.art:
                kind, slug, name = entity.art[-1].split("/", 2)
                if (cfg.assets_dir / kind / slug / f"{name}.png").exists():
                    out[entity.ref] = f"{kind}-{slug}.png"
        return out

    def require_login(request):
        if not request.session.get("who"):
            return RedirectResponse("/wiki/login", status_code=303)
        return None

    # -- auth ----------------------------------------------------------

    def roster() -> list[people_mod.Person]:
        reload_people()
        return sorted(registry.members.values(),
                      key=lambda p: (not p.is_dm, p.name.lower()))

    async def login(request):
        """Pick who you are. No password.

        This is an honour system by design: nothing stops someone choosing a
        name that isn't theirs, so the secrets feature is a DM screen rather
        than a lock. Fine for a table of friends, and worth remembering before
        putting anything genuinely sensitive behind it.
        """
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
            site_mod.SITE_NAME,
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
            site_mod.KIND_LABEL.get(kind, kind),
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

    # -- art -----------------------------------------------------------

    def art_service():
        """Built on first use so the GPU stack isn't imported at startup."""
        nonlocal _art
        if _art is None:
            from .art import ArtService
            from .assets import AssetStore

            _art = ArtService(cfg, library, AssetStore(cfg.assets_dir))
        return _art

    async def art_panel(request):
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        kind, slug = request.path_params["kind"], request.path_params["slug"]
        _, allowed = entities_for(viewer)
        if f"{kind}/{slug}" not in allowed:
            return HTMLResponse("Not found", status_code=404)
        entity = library.load(kind, slug)

        prompt = ""
        candidates: list[str] = []
        error = ""

        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action", "generate"))

            if action == "pick":
                asset_id = str(form.get("asset", ""))
                # Only accept ids belonging to this page, so a crafted form
                # can't attach someone else's picture.
                if asset_id.startswith(f"{kind}/{slug}/") and \
                        art_service().attach(entity, asset_id):
                    return RedirectResponse(f"/wiki/{kind}/{slug}.html",
                                            status_code=303)
                error = "That image is no longer available."
            else:
                prompt = str(form.get("prompt", "")).strip()
                if not prompt:
                    error = "Describe the picture you want."
                else:
                    try:
                        # Off the event loop: generation takes tens of seconds
                        # and would otherwise freeze the site for everyone.
                        results = await run_in_threadpool(
                            art_service().generate_custom, entity, prompt, count=3
                        )
                        candidates = [r.asset_id for r in results]
                    except Exception as exc:  # GPU out of memory, model missing
                        error = f"Couldn't generate that: {exc}"

        existing = [a for a in entity.art]
        return render(f"Art for {entity.name}",
                      _art_form(entity, existing, candidates, prompt, error),
                      user=user)

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

    async def art_by_id(request):
        """Serve one image by asset id, for the art picker.

        Permission-checked against the page it belongs to, exactly like the
        named art route, or a restricted character's portrait would be
        reachable by guessing an id.
        """
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, _ = viewer_for(request)
        asset_id = request.path_params["asset"]
        if ".." in asset_id or asset_id.count("/") != 2:
            return HTMLResponse("Not found", status_code=404)
        kind, slug, name = asset_id.split("/")
        _, allowed = entities_for(viewer)
        if f"{kind}/{slug}" not in allowed:
            return HTMLResponse("Not found", status_code=404)
        path = Path(cfg.assets_dir) / kind / slug / f"{name}.png"
        if not path.exists():
            return HTMLResponse("Not found", status_code=404)
        return FileResponse(path)

    async def art(request):
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, _ = viewer_for(request)
        name = request.path_params["filename"]
        if "/" in name or "\\" in name or ".." in name:
            return HTMLResponse("Not found", status_code=404)
        _, allowed = entities_for(viewer)
        # Art filenames are "<kind>-<slug>.png"; only serve one whose page this
        # viewer may see, or a restricted page's portrait leaks by direct URL.
        stem = name.rsplit(".", 1)[0]
        kind, _, slug = stem.partition("-")
        if f"{kind}/{slug}" not in allowed:
            return HTMLResponse("Not found", status_code=404)
        entity = library.load(kind, slug)
        if not entity or not entity.art:
            return HTMLResponse("Not found", status_code=404)
        akind, aslug, aname = entity.art[-1].split("/", 2)
        path = Path(cfg.assets_dir) / akind / aslug / f"{aname}.png"
        if not path.exists():
            return HTMLResponse("Not found", status_code=404)
        return FileResponse(path)

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

    # -- the Discord inbox ----------------------------------------------

    async def inbox_page(request):
        """Everything said in Discord that no page accounts for yet.

        A review queue, not an importer. The wiki is what the table decided is
        true; Discord is four years of argument, jokes and half-ideas. Someone
        has to choose between them, and that someone is a person.
        """
        redirect = require_login(request)
        if redirect:
            return redirect
        _, user = viewer_for(request)

        if request.method == "POST":
            form = await request.form()
            action = str(form.get("action", ""))
            if action == "catch_up":
                inbox.catch_up(str(form.get("channel", "")) or None)
            else:
                ids = [i for i in form.getlist("id") if i]
                if ids:
                    inbox.file(ids)
            return RedirectResponse(request.url.path + (
                f"?channel={request.query_params['channel']}"
                if request.query_params.get("channel") else ""
            ), status_code=303)

        channel = request.query_params.get("channel") or None
        if channel and channel not in inbox.channels():
            channel = None
        waiting = inbox.unfiled(library, channel=channel, limit=60)
        total = inbox.count(library)
        return render("Inbox",
                      _inbox_page(waiting, total, inbox.channels(), channel,
                                  inbox.last_sync()),
                      user=user)

    async def inbox_attachment(request):
        """An image posted in Discord, straight from the lore archive.

        Read from `dnd-scribe/lore`, which sits outside this project, so the
        path is resolved and checked rather than trusted.
        """
        redirect = require_login(request)
        if redirect:
            return redirect
        path = inbox.attachment_path(request.path_params["channel"],
                                     request.path_params["filename"])
        if path is None:
            return HTMLResponse("Not found", status_code=404)
        return FileResponse(path)

    # -- editing --------------------------------------------------------

    def form_values(entity: Entity | None, viewer: frozenset[str]) -> dict:
        if entity is None:
            return {"name": "", "summary": "", "appearance": "", "body": "",
                    "tags": "", "links": "", "kind": "place", "source": ""}
        return {
            "name": entity.name,
            "summary": entity.summary,
            "appearance": entity.appearance,
            "body": secrets_mod.redact(entity.body, viewer),
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

        withheld = len(secrets_mod.withheld_blocks(entity.body, viewer))

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
        entity.body = secrets_mod.merge_edit(entity.body, body, viewer)

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
                if supplied and (field != "kind" or supplied in KINDS):
                    values[field] = supplied
            return render("New page",
                          _edit_form(values, registry, withheld=0,
                                     action="/wiki/new", creating=True),
                          user=user)

        form = await request.form()
        name = str(form.get("name", "")).strip()
        kind = str(form.get("kind", "")).strip()
        if not name or kind not in KINDS:
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

    return [
        Route("/wiki/new", new_page, methods=["GET", "POST"]),
        Route("/wiki/{kind}/{slug}/edit", edit, methods=["GET", "POST"]),
        Route("/wiki/login", login, methods=["GET", "POST"]),
        Route("/wiki/people/new", add_person, methods=["GET", "POST"]),
        Route("/wiki/logout", logout),
        Route("/wiki/guide", guide),
        Route("/wiki/connect", connect),
        Route("/wiki/", index),
        Route("/wiki/index.html", index),
        Route("/wiki/tooltips.js", tooltips_js),
        Route("/wiki/inbox", inbox_page, methods=["GET", "POST"]),
        Route("/wiki/inbox/att/{channel}/{filename}", inbox_attachment),
        Route("/wiki/{kind}/{slug}/art", art_panel, methods=["GET", "POST"]),
        Route("/wiki/art/id/{asset:path}.png", art_by_id),
        Route("/wiki/art/{filename}", art),
        Route("/wiki/{kind}/index.html", kind_index),
        Route("/wiki/{kind}/{slug}.html", page),
    ]


def _inbox_page(messages, total: int, channels: list[str],
                channel: str | None, last_sync: str) -> str:
    from urllib.parse import quote

    tabs = "".join(
        f'<a href="/wiki/inbox{"" if c is None else "?channel=" + quote(c)}"'
        f'{" class=\'on\'" if c == channel else ""}>'
        f'{html.escape(c or "Everything")}</a>'
        for c in [None] + channels
    )
    checked = (f"Last checked {html.escape(last_sync[:16].replace('T', ' '))} UTC."
               if last_sync else
               "Discord has not been checked yet. Run sync.ps1 in dnd-scribe.")

    if not messages:
        return f"""
<h1>Inbox</h1>
<p class="summary">Nothing waiting. Everything said in Discord is either
written up or marked as read.</p>
<div class="tabs">{tabs}</div>
<p class="hint">{checked}</p>
"""

    cards = []
    for m in messages:
        shots = "".join(
            f'<img src="/wiki/inbox/att/{quote(m.channel)}/{quote(a["file"])}" '
            f'alt="{html.escape(a.get("filename", ""))}" loading="lazy">'
            for a in m.attachments
            if str(a.get("content_type", "")).startswith("image/") and a.get("file")
        )
        files = ", ".join(
            html.escape(a.get("filename", "")) for a in m.attachments
            if not str(a.get("content_type", "")).startswith("image/")
        )
        # The first line usually names the thing, which is the best guess at a
        # page title anyone is going to get without reading it for them.
        first = (m.text.splitlines() or [""])[0][:80]
        prefill = (f"/wiki/new?name={quote(first)}&body={quote(m.text[:4000])}"
                   f"&source={quote(m.source)}")
        cards.append(f"""
<div class="msg">
  <div class="meta"><strong>{html.escape(m.author)}</strong>
    <span class="chan">#{html.escape(m.channel)}</span>
    <span>{html.escape(m.at[:16].replace("T", " "))}</span></div>
  <div class="text">{html.escape(m.text)}</div>
  {f'<div class="shots">{shots}</div>' if shots else ""}
  {f'<p class="hint">Files: {files}</p>' if files else ""}
  <div class="acts">
    <a href="{prefill}">Write it up</a>
    <form method="post">
      <input type="hidden" name="id" value="{html.escape(m.id)}">
      <button type="submit">Not lore</button>
    </form>
  </div>
</div>""")

    more = ("<p class='hint'>Showing the oldest 60. Deal with these and the "
            "rest appear.</p>" if total > len(messages) else "")

    return f"""
<h1>Inbox</h1>
<p class="summary">{total} message{"s" if total != 1 else ""} from Discord that
no page accounts for yet.</p>
<div class="tabs">{tabs}</div>
<p class="hint">{checked} A message disappears from here when a page cites it,
so writing it up is enough. "Not lore" is for the rest.</p>
{"".join(cards)}
{more}
<form method="post" class="catchup">
  <input type="hidden" name="action" value="catch_up">
  {f'<input type="hidden" name="channel" value="{html.escape(channel)}">' if channel else ""}
  <button type="submit">Mark everything here as read</button>
</form>
"""


# -- forms -------------------------------------------------------------

def _edit_form(v: dict, registry: people_mod.People, withheld: int,
               action: str, creating: bool = False, error: str = "") -> str:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    title = "New page" if creating else f"Editing {v['name']}"

    kinds = "".join(
        f'<option value="{k}"{" selected" if k == v["kind"] else ""}>{k}</option>'
        for k in KINDS
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
        "Please set up an MCP server for me.\n\n"
        f"  Name:      buried-star\n"
        f"  Transport: HTTP (streamable HTTP, not SSE, not stdio)\n"
        f"  URL:       {url}\n"
        f"  Auth:      an Authorization header with the value\n"
        f"             Bearer {token}\n\n"
        "Work out how to add it for whichever Claude client you're running in, "
        "do it if you can, and tell me if there's a step I have to take myself. "
        "Then verify by calling whoami: it should come back with my name."
    )
    cli = (
        f"claude mcp add --transport http buried-star {url} "
        f'--header "Authorization: Bearer {token}"'
    )

    def block(idx: int, text: str) -> str:
        return (
            f'<div class="copyblock"><pre id="b{idx}">{html.escape(text)}</pre>'
            f'<button type="button" onclick="cp(\'b{idx}\',this)">Copy</button></div>'
        )

    return f"""
<h1>Connect Claude</h1>
<p class="summary">Signed in as {html.escape(name)}. Everything below already
has your own details in it.</p>

<p>This lets your Claude read the world and write to it. What you can see is
tied to you, so use your own details and don't pass them around.</p>

<h2>Easiest: paste this into Claude</h2>
{block(1, prompt)}

<h2>Claude Code</h2>
{block(2, cli)}

<h2>Or edit the config file yourself</h2>
{block(3, config)}

<h2>Check it worked</h2>
<p>Ask your Claude: <em>call whoami on buried-star</em>. It should come back
with your name. If it says <em>guest</em>, the header didn't take.</p>

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


def _art_form(entity, existing: list[str], candidates: list[str],
              prompt: str, error: str) -> str:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    current = existing[-1] if existing else None

    def gallery(ids: list[str], heading: str, note: str = "") -> str:
        if not ids:
            return ""
        cards = []
        for asset_id in ids:
            is_current = asset_id == current
            cards.append(
                f'<figure class="{"current" if is_current else ""}">'
                f'<img src="/wiki/art/id/{html.escape(asset_id)}.png" '
                f'alt="" loading="lazy">'
                + (
                    "<button disabled>In use</button>" if is_current else
                    f'<button type="submit" name="asset" '
                    f'value="{html.escape(asset_id)}">Use this one</button>'
                )
                + "</figure>"
            )
        return (f"<h2>{heading}</h2>"
                + (f'<p class="hint">{note}</p>' if note else "")
                + f'<div class="artgrid">{"".join(cards)}</div>')

    picker = ""
    if candidates or existing:
        picker = (
            f'<form method="post" action="/wiki/{entity.kind}/{entity.slug}/art">'
            '<input type="hidden" name="action" value="pick">'
            + gallery(candidates, "Just generated",
                      "Pick one to put it on the page, or write a different "
                      "prompt and try again.")
            + gallery([a for a in existing if a not in candidates],
                      "Already on this page" if not candidates else "Earlier images",
                      "Everything ever drawn for this page. Nothing is thrown away.")
            + "</form>"
        )

    return f"""
<div class="kind">Art<a class="edit" href="/wiki/{entity.kind}/{entity.slug}.html">Back</a></div>
<h1>{html.escape(entity.name)}</h1>
{err}
<form class="auth wide" method="post" action="/wiki/{entity.kind}/{entity.slug}/art">
  <label for="p">Describe the picture
    <span class="hint">Physical and concrete works best: what you'd see,
    not what it means. The house style is added for you.</span></label>
  <textarea id="p" name="prompt" rows="3"
            placeholder="{html.escape(entity.appearance or 'a low timber tavern at dusk, lantern light, wet cobbles')}">{html.escape(prompt)}</textarea>
  <button type="submit">Generate three</button>
</form>
<div class="slow">This runs on the GPU at home and takes roughly a minute for
three pictures. Leave the tab open.</div>
{picker}
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
