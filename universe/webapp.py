"""The live wiki: accounts, sign-in, and per-person rendering.

Unlike the static export, this knows who is reading. Each person signs in with
their own username and password, and every page is rendered for their identity:
their secrets appear, other people's don't, and pages restricted away from them
don't exist as far as they can tell.

Registration is open but gated by a one-time invite code bound to a person in
`people.yaml`. Without that gate anyone who found the URL could register as the
DM. Nothing the registrant types decides who they are; the code does.
"""

from __future__ import annotations

import html
from pathlib import Path

from starlette.responses import (FileResponse, HTMLResponse,
                                 RedirectResponse, Response)
from starlette.routing import Route

from . import accounts as accounts_mod
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


def build(cfg, library: Library, registry: people_mod.People,
          accounts: accounts_mod.Accounts,
          require_invite: bool = False) -> list[Route]:
    """Routes for /wiki. Everything requires a signed-in account.

    With `require_invite`, registration needs a one-time code that decides who
    the new account is. Without it, registration is open and people pick
    themselves from the roster, which trusts anyone holding the link to be
    honest about which of your friends they are.
    """

    def viewer_for(request) -> tuple[frozenset[str], str | None]:
        email = request.session.get("user")
        if not email:
            return PUBLIC, None
        key = accounts.key_for(email)
        person = registry.members.get(key) if key else None
        if person is None:
            # Account references a person who has since been removed.
            return PUBLIC, email
        # Show the person's name in the header rather than their address.
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
        if not request.session.get("user"):
            return RedirectResponse("/wiki/login", status_code=303)
        return None

    # -- auth ----------------------------------------------------------

    async def login(request):
        if request.method == "GET":
            if request.session.get("user"):
                return RedirectResponse("/wiki/", status_code=303)
            return _auth_page("Sign in", "/wiki/", _login_form())

        form = await request.form()
        account = accounts.authenticate(
            str(form.get("email", "")), str(form.get("password", ""))
        )
        if account is None:
            # One message for both causes, so this can't be used to find out
            # which addresses have accounts.
            return _auth_page(
                "Sign in", "/wiki/",
                _login_form(error="That email and password don't match.",
                            email=str(form.get("email", ""))),
            )
        request.session["user"] = account.email
        return RedirectResponse("/wiki/", status_code=303)

    def roster() -> list[tuple[str, str]]:
        """People still available to claim, for the picker."""
        taken = accounts.claimed_keys
        return [
            (p.key, f"{p.name}" + (f" ({p.character})" if p.character
                                   else " (DM)" if p.is_dm else ""))
            for p in registry.members.values()
            if p.key not in taken
        ]

    async def register(request):
        if request.method == "GET":
            return _auth_page(
                "Create an account", "/wiki/",
                _register_form(require_invite=require_invite, roster=roster()),
            )

        form = await request.form()
        account, error = accounts.register(
            str(form.get("email", "")),
            str(form.get("password", "")),
            code=str(form.get("code", "")) if require_invite else "",
            key=str(form.get("who", "")),
            known_keys=set(registry.members),
        )
        if account is None:
            return _auth_page(
                "Create an account", "/wiki/",
                _register_form(
                    error=error,
                    email=str(form.get("email", "")),
                    code=str(form.get("code", "")),
                    who=str(form.get("who", "")),
                    require_invite=require_invite,
                    roster=roster(),
                ),
            )
        request.session["user"] = account.email
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
            return HTMLResponse(
                site_mod.shell("Guide", "/wiki/",
                               "<h1>Guide</h1><p class='hint'>GUIDE.md is "
                               "missing from the project folder.</p>",
                               "[]", user=user, live=True),
                status_code=404,
            )
        return HTMLResponse(site_mod.shell(
            "Guide", "/wiki/",
            site_mod.render_guide(source.read_text(encoding="utf-8")),
            "[]", user=user, live=True,
        ))

    # -- pages ---------------------------------------------------------

    async def index(request):
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        entities, _ = entities_for(viewer)
        images = images_for(entities)
        return HTMLResponse(site_mod.shell(
            "Copper Vale", "/wiki/",
            site_mod.render_index(entities, images, "/wiki/", editable=True),
            site_mod.search_index(entities, viewer), user=user, live=True,
            tips=True,
        ))

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
        return HTMLResponse(site_mod.shell(
            site_mod.KIND_LABEL.get(kind, kind), "/wiki/",
            site_mod.render_kind_index(kind, items, images, "/wiki/"),
            site_mod.search_index(entities, viewer), user=user, live=True,
            tips=True,
        ))

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
            return HTMLResponse(
                site_mod.shell("Not found", "/wiki/",
                               "<h1>Not found</h1><p class='hint'>No such page.</p>",
                               "[]", user=user, live=True),
                status_code=404,
            )
        entity = library.load(kind, slug)
        images = images_for(entities)
        return HTMLResponse(site_mod.shell(
            entity.name, "/wiki/",
            site_mod.render_body(entity, library, images, "/wiki/", viewer, allowed,
                                 editable=True),
            site_mod.search_index(entities, viewer), user=user, live=True,
            tips=True,
        ))

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
        email = request.session.get("user")
        key = accounts.key_for(email)
        person = registry.members.get(key) if key else None
        if person is None:
            return HTMLResponse(
                site_mod.shell("Connect", "/wiki/",
                               "<h1>Connect</h1><p class='hint'>Your account "
                               "isn't linked to anyone. Ask your DM.</p>",
                               "[]", user=email, live=True),
                status_code=404,
            )

        token = people_mod.ensure_token(Path(cfg.root), person.key)
        base = str(request.base_url).rstrip("/")
        return HTMLResponse(site_mod.shell(
            "Connect Claude", "/wiki/",
            _connect_page(person.name, f"{base}/mcp", token),
            "[]", user=person.name, live=True,
        ))

    # -- editing --------------------------------------------------------

    def form_values(entity: Entity | None, viewer: frozenset[str]) -> dict:
        if entity is None:
            return {"name": "", "summary": "", "appearance": "", "body": "",
                    "tags": "", "links": "", "kind": "place"}
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
            return HTMLResponse(site_mod.shell(
                f"Editing {entity.name}", "/wiki/",
                _edit_form(form_values(entity, viewer), registry, withheld=withheld,
                           action=f"/wiki/{kind}/{slug}/edit"),
                "[]", user=user, live=True,
            ))

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
            return HTMLResponse(site_mod.shell(
                "New page", "/wiki/",
                _edit_form(form_values(None, viewer), registry, withheld=0,
                           action="/wiki/new", creating=True),
                "[]", user=user, live=True,
            ))

        form = await request.form()
        name = str(form.get("name", "")).strip()
        kind = str(form.get("kind", "")).strip()
        if not name or kind not in KINDS:
            return HTMLResponse(site_mod.shell(
                "New page", "/wiki/",
                _edit_form({**form_values(None, viewer),
                            "name": name, "kind": kind},
                           registry, withheld=0, action="/wiki/new",
                           creating=True,
                           error="Give it a name and pick a type."),
                "[]", user=user, live=True,
            ))

        slug = slugify(name)
        if library.exists(kind, slug):
            return RedirectResponse(f"/wiki/{kind}/{slug}.html", status_code=303)

        body = str(form.get("body", ""))
        secret_text = str(form.get("secret_text", "")).strip()
        audience = [a for a in form.getlist("audience") if a]
        if secret_text and audience:
            body = body.rstrip() + "\n\n" + secrets_mod.wrap(secret_text, audience)

        entity = Entity(
            kind=kind, slug=slug, name=name,
            summary=str(form.get("summary", "")).strip(),
            appearance=str(form.get("appearance", "")).strip(),
            body=body.strip(),
            tags=[t.strip() for t in str(form.get("tags", "")).split(",") if t.strip()],
            links=[l.strip() for l in str(form.get("links", "")).split(",")
                   if l.strip() and "/" in l],
            sources=[f"created by {user} on the wiki"],
        )
        library.save(entity)
        return RedirectResponse(f"/wiki/{kind}/{slug}.html", status_code=303)

    return [
        Route("/wiki/new", new_page, methods=["GET", "POST"]),
        Route("/wiki/{kind}/{slug}/edit", edit, methods=["GET", "POST"]),
        Route("/wiki/login", login, methods=["GET", "POST"]),
        Route("/wiki/register", register, methods=["GET", "POST"]),
        Route("/wiki/logout", logout),
        Route("/wiki/guide", guide),
        Route("/wiki/connect", connect),
        Route("/wiki/", index),
        Route("/wiki/index.html", index),
        Route("/wiki/tooltips.js", tooltips_js),
        Route("/wiki/art/{filename}", art),
        Route("/wiki/{kind}/index.html", kind_index),
        Route("/wiki/{kind}/{slug}.html", page),
    ]


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
<form class="auth wide" method="post" action="{action}">
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
        '    "copper-vale": {\n'
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
        f"  Name:      copper-vale\n"
        f"  Transport: HTTP (streamable HTTP, not SSE, not stdio)\n"
        f"  URL:       {url}\n"
        f"  Auth:      an Authorization header with the value\n"
        f"             Bearer {token}\n\n"
        "Work out how to add it for whichever Claude client you're running in, "
        "do it if you can, and tell me if there's a step I have to take myself. "
        "Then verify by calling whoami: it should come back with my name."
    )
    cli = (
        f"claude mcp add --transport http copper-vale {url} "
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
<p>Ask your Claude: <em>call whoami on copper-vale</em>. It should come back
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


def _login_form(error: str = "", email: str = "") -> str:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    return f"""
<h1>Sign in</h1>
<p class="summary">Copper Vale is private to the table.</p>
{err}
<form class="auth" method="post" action="/wiki/login">
  <label for="e">Email</label>
  <input id="e" name="email" type="email" value="{html.escape(email)}"
         autocomplete="email" autofocus required>
  <label for="p">Password</label>
  <input id="p" name="password" type="password" autocomplete="current-password" required>
  <button type="submit">Sign in</button>
</form>
<p class="hint">No account yet? <a href="/wiki/register">Create one</a>.
First time here? Read the <a href="/wiki/guide">guide</a>.</p>
"""


def _register_form(error: str = "", email: str = "", code: str = "",
                   who: str = "", require_invite: bool = False,
                   roster: list[tuple[str, str]] | None = None) -> str:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    roster = roster or []

    if require_invite:
        intro = ("You'll need the invite code your DM gave you. It decides "
                 "whose secrets you can read, so use your own.")
        identity = (
            '  <label for="c">Invite code</label>\n'
            f'  <input id="c" name="code" value="{html.escape(code)}" autofocus required>'
        )
    elif not roster:
        return f"""
<h1>Create an account</h1>
{err}
<p class="summary">Everyone on the roster already has an account.</p>
<p class="hint"><a href="/wiki/login">Sign in</a>, or ask your DM if you think
this is wrong.</p>
"""
    else:
        intro = ("Pick your name so the wiki knows whose secrets to show you. "
                 "Choose your own; the world looks different for everyone.")
        options = "".join(
            f'<option value="{html.escape(key)}"'
            f'{" selected" if key == who else ""}>{html.escape(label)}</option>'
            for key, label in roster
        )
        identity = (
            '  <label for="w">Who are you?</label>\n'
            f'  <select id="w" name="who" autofocus required>\n'
            f'    <option value="">Choose your name...</option>\n{options}\n  </select>'
        )

    return f"""
<h1>Create an account</h1>
<p class="summary">{intro}</p>
{err}
<form class="auth" method="post" action="/wiki/register">
{identity}
  <label for="e">Email</label>
  <input id="e" name="email" type="email" value="{html.escape(email)}"
         autocomplete="email" required>
  <label for="p">Password</label>
  <input id="p" name="password" type="password" autocomplete="new-password"
         minlength="8" required>
  <button type="submit">Create account</button>
</form>
<p class="hint">At least 8 characters. Your email is just your sign-in name;
nothing is sent to it. Already registered? <a href="/wiki/login">Sign in</a>.
Not sure what any of this is? Read the <a href="/wiki/guide">guide</a>.</p>
"""
