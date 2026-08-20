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

import hashlib
import html
import json
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.responses import (FileResponse, HTMLResponse,
                                 RedirectResponse, Response)
from starlette.routing import Route

from . import access as access_mod
from . import changelog as changelog_mod
from . import encounter as encounter_mod
from . import gate as gate_mod
from . import hierarchy as hierarchy_mod
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


def _auth_page(wiki, title: str, base: str, inner: str) -> HTMLResponse:
    return HTMLResponse(
        wiki.pages.shell(title, base, inner, "[]", user=None, live=True)
    )


def build(cfg, library: Library, registry: people_mod.People,
          schema: schema_mod.Schema | None = None) -> list[Route]:
    """Routes for /wiki. Everything but the guide needs someone signed in.

    Signing in only establishes which secrets to render; it keeps nobody out.
    Anyone with the link can claim any name on the roster, or add themselves.
    """

    schema = schema or schema_mod.load(Path(cfg.root))

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
            return _auth_page(wiki, "The Buried Star", "/wiki/", _gate_form())

        form = await request.form()
        attempt = str(form.get("passphrase", ""))
        ok = await run_in_threadpool(gate_mod.check, Path(cfg.root), attempt)
        if not ok:
            return _auth_page(
                wiki,                 "The Buried Star", "/wiki/",
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
            # Shown even when already signed in. Bouncing straight to the front
            # page made this look broken: you would clear the passphrase, land
            # on the homepage as whoever you were last time, and never see the
            # picker. Switching person is also the only way to check what
            # someone else can see, which is the point of the whole feature.
            return _auth_page(
                wiki,                 "Who are you?", "/wiki/",
                _signin_form(roster(), current=request.session.get("who")))

        form = await request.form()
        key = str(form.get("who", "")).strip().lower()
        reload_people()
        if key not in registry.members:
            return _auth_page(
                wiki,                 "Who are you?", "/wiki/",
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
                wiki,                 "Who are you?", "/wiki/",
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
            wiki.pages.index(entities, images, "/wiki/", editable=True),
            user=user, tips=True,
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
            wiki.pages.kind_index(kind, items, images, "/wiki/"),
            user=user, tips=True,
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
            wiki.pages.body(entity, library, images, "/wiki/", viewer, allowed,
                            editable=True),
            user=user, tips=True,
        )

    def cached_script(request, body: str) -> Response:
        """Serve a per-viewer script that the browser may keep, with an ETag.

        These are big: the tooltip index is 400KB and the search index 60KB.
        They were marked `no-store`, so every page load fetched both again,
        which on a phone is most of the wait. They are still built per viewer,
        because a page you cannot see must not appear in either, so the cache
        is `private` and the ETag is a hash of what this viewer actually gets.
        A permission change alters the hash and the browser is told to refetch.
        """
        tag = '"' + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16] + '"'
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers={
                "ETag": tag, "Cache-Control": "private, max-age=300"})
        return Response(
            body,
            media_type="application/javascript",
            headers={"ETag": tag, "Cache-Control": "private, max-age=300"},
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
        return cached_script(
            request, f"window.__TIPS__={index};\n{tooltips_mod.TOOLTIP_JS}")

    async def search_js(request):
        """The search index, out of the page and into something cacheable.

        It was inlined into every page: 60KB of the same JSON on all 112 of
        them, re-sent on every navigation. The page is a quarter of its old
        size without it.
        """
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, _ = viewer_for(request)
        entities, _ = entities_for(viewer)
        return cached_script(
            request, f"window.__INDEX__={wiki.pages.search_index(entities, viewer)};")

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

    async def changelog(request):
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        _, allowed = entities_for(viewer)
        log = changelog_mod.restrict(
            changelog_mod.load(Path(cfg.root), library), allowed)
        return render("Changelog", changelog_mod.render(log, "/wiki/"), user=user)

    async def places(request):
        """The whole world as a shape, for checking it is right.

        The Places index stays a flat list, which is the right thing when you
        know what you are looking for. This is the other question: is Harvest
        Abbey really in The Broadheights, and what did nothing say anything
        about?

        Most of these parents were worked out from tags and links rather than
        stated by a person, so the ones that were guessed say so, and fixing
        one is editing that place.
        """
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        _, allowed = entities_for(viewer)
        everything = [p for p in library.all(hierarchy_mod.KIND)
                      if p.ref in allowed]

        rows = []
        for depth, place in hierarchy_mod.tree(everything):
            guess = str(place.data.get("within_inferred") or "")
            note = ""
            if guess:
                how = {"tag": "from a tag", "name": "from its name",
                       "link": "from a link"}.get(guess, guess)
                note = f'<span class="guess">guessed {html.escape(how)}</span>'
            rows.append(
                f'<li style="margin-left:{depth * 1.4:.1f}rem">'
                f'<a href="/wiki/{place.kind}/{place.slug}.html">'
                f"{html.escape(place.name)}</a>"
                f'<a class="fix" href="/wiki/{place.kind}/{place.slug}/edit">'
                f"move</a>{note}</li>"
            )

        loose = [p for p in everything if not p.within]
        guessed = sum(1 for p in everything if p.data.get("within_inferred"))
        body = f"""
<div class="kind">Places</div>
<h1>Where everything is</h1>
<p class="summary">{len(everything)} places. {guessed} of these parents were
worked out from the tags and links that were already there, rather than said
by a person, so check the ones marked as guesses.</p>
<p class="hint">{len(loose)} sit at the top level, which is either right or
means nobody has said where they are yet. Either way, "move" is how you
change one.</p>
<ul class="shape">{"".join(rows)}</ul>
"""
        return render("Where everything is", body, user=user)

    # -- editing --------------------------------------------------------

    def form_values(entity: Entity | None, viewer: access_mod.Viewer) -> dict:
        if entity is None:
            return {"name": "", "summary": "", "appearance": "", "body": "",
                    "tags": "", "links": "", "kind": "place", "source": "",
                    "within": "", "revealed_by": ""}
        return {
            "name": entity.name,
            "summary": entity.summary,
            "appearance": entity.appearance,
            "body": access_mod.editable_body(entity, viewer),
            "tags": ", ".join(entity.tags),
            "links": ", ".join(entity.links),
            "kind": entity.kind,
            "within": entity.within,
            # Canonical form rather than what the file happens to say, so a
            # bare slug someone hand-wrote reads back as place/slug.
            "revealed_by": ", ".join(sorted(encounter_mod.sources_of(entity))),
        }

    def apply_gate(entity: Entity, raw: str) -> bool:
        """Set a page's reveal gate from the form field. Returns True on change.

        An emptied field drops the derived `revealed` flag with the gate, so
        an ungated page carries no leftover bookkeeping.
        """
        before = entity.data.get("revealed_by")
        cleaned = [r.strip().lower() for r in raw.split(",") if r.strip()]
        if cleaned:
            entity.data["revealed_by"] = cleaned
        else:
            entity.data.pop("revealed_by", None)
            entity.data.pop("revealed", None)
        return entity.data.get("revealed_by") != before

    def tag_suggestions() -> dict[str, list[str]]:
        """The tags each kind actually uses, most common first.

        Mined from the pages rather than configured, so the pills on the new
        page form always speak the wiki's current vocabulary. Provenance and
        hygiene tags (from-*, needs-*) are machinery, not description, and
        offering them as pills would teach people to click them.
        """
        from collections import Counter
        per: dict[str, Counter] = {}
        for e in library.all():
            c = per.setdefault(e.kind, Counter())
            for t in e.tags:
                if not t.startswith(("from-", "needs-")):
                    c[t] += 1
        return {k: [t for t, _ in c.most_common(10)] for k, c in per.items()}

    def place_options(current: str, exclude: str = "") -> str:
        """A dropdown of places to sit inside, indented to show the shape.

        Anything inside `exclude` is left out, along with `exclude` itself, so
        the form cannot offer a choice that would make a loop. Refusing after
        the fact would be a worse way to learn the same thing.
        """
        places = list(library.all(hierarchy_mod.KIND))
        by_ref = hierarchy_mod.index(places)
        out = ['<option value="">Nowhere, it is a top level place</option>']
        for depth, place in hierarchy_mod.tree(places):
            if exclude and (place.ref == exclude
                            or hierarchy_mod.would_cycle(exclude, place.ref, by_ref)):
                continue
            sel = " selected" if place.ref == current else ""
            pad = "&nbsp;" * (depth * 4)
            out.append(f'<option value="{html.escape(place.ref)}"{sel}>'
                       f"{pad}{html.escape(place.name)}</option>")
        return "".join(out)

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

        # The page's own unlocks count here too: an editor on a visited place
        # sees its upon-visiting sections in the textarea like any other
        # public prose, instead of having them "preserved" behind their back.
        editing_ids = access_mod.page_viewer(entity, viewer).identities
        withheld = len(secrets_mod.withheld_blocks(entity.body, editing_ids))

        if request.method == "GET":
            return render(
                f"Editing {entity.name}",
                _edit_form(form_values(entity, viewer), registry, schema.kinds,
                           withheld=withheld,
                           action=f"/wiki/{kind}/{slug}/edit",
                           within_options=(
                               place_options(entity.within, exclude=entity.ref)
                               if kind == hierarchy_mod.KIND else ""),
                           dm=viewer.is_dm),
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
        if entity.kind == hierarchy_mod.KIND and "within" in form:
            chosen = str(form.get("within", "")).strip()
            places = list(library.all(hierarchy_mod.KIND))
            # The dropdown already leaves out anything that would loop. This is
            # for a hand-made POST, which is cheap to defend against and
            # otherwise writes a file nothing can render.
            if not chosen or not hierarchy_mod.would_cycle(
                    entity.ref, chosen, hierarchy_mod.index(places)):
                entity.within = chosen
                entity.data.pop("within_inferred", None)

        body = str(form.get("body", ""))
        secret_text = str(form.get("secret_text", "")).strip()
        audience = [a for a in form.getlist("audience") if a]
        if secret_text and audience:
            body = body.rstrip() + "\n\n" + secrets_mod.wrap(secret_text, audience)
        # Anything this editor could not see is carried across untouched.
        entity.body = secrets_mod.merge_edit(entity.body, body, editing_ids)

        # The reveal gate, from the DM's copy of the form only. A player's
        # form never carries the field, and a hand-made POST that does is
        # ignored rather than honoured.
        gate_changed = False
        if viewer.is_dm and "revealed_by" in form:
            gate_changed = apply_gate(entity, str(form.get("revealed_by", "")))

        note = f"edited by {user} on the wiki"
        if note not in entity.sources:
            entity.sources.append(note)
        library.save(entity)
        if gate_changed:
            # The gate may be born open: its source could have been
            # encountered before the gate existed.
            access_mod.recompute_reveals(library)
        # `sources` says a person touched this page at some point; it is
        # deduped, so a second edit adds nothing. The commit is what carries
        # when, and how often, and is what the changelog counts.
        wiki.record(f"{entity.kind}/{entity.slug}: edited on the wiki", user)
        return RedirectResponse(f"/wiki/{kind}/{slug}.html", status_code=303)

    async def delete_page(request):
        """Delete a page outright. Git history is the undo button.

        POST only, and the form that posts here confirms first. The page's
        art and files stay on disk: they are tracked, harmless orphaned, and
        deleting them here would leave the server's working tree carrying
        removals that repo-sync does not stage. Inbound links are stripped
        -- a click on a ghost helps nobody -- and anything nested inside a
        deleted place floats to the top level rather than hanging from
        nothing.
        """
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        kind, slug = request.path_params["kind"], request.path_params["slug"]
        ref = f"{kind}/{slug}"
        _, allowed = entities_for(viewer)
        if ref not in allowed:
            return HTMLResponse("Not found", status_code=404)

        path = library.path_for(kind, slug)
        if path.exists():
            path.unlink()
        for other in list(library.all()):
            touched = False
            if ref in other.links:
                other.links = [l for l in other.links if l != ref]
                touched = True
            if other.within == ref:
                other.within = ""
                touched = True
            if touched:
                library.save(other)
        wiki.record(f"{ref}: deleted on the wiki", user or "someone")
        return RedirectResponse(f"/wiki/{kind}/index.html", status_code=303)

    async def toggle_visited(request):
        """Move a page's encounter flag: visited, met, known, seen.

        DM only, any kind. The route keeps its old name because the concept
        grew out of the places-only visited checkbox and old links still
        point here. The form's `set` field says where the flag goes --
        "true" (encountered), "false" (hidden from everyone but the DM),
        "clear" (untracked, public) -- and a bare POST keeps the original
        toggle so nothing scripted against it breaks.
        """
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        kind, slug = request.path_params["kind"], request.path_params["slug"]
        ref = f"{kind}/{slug}"
        _, allowed = entities_for(viewer)
        # Non-DMs get the same 404 as a missing page, like every other
        # route: a 403 would confirm there is something here to press.
        if ref not in allowed or not viewer.is_dm:
            return HTMLResponse("Not found", status_code=404)
        entity = library.load(kind, slug)
        verb = encounter_mod.flag_key(entity.kind)
        form = await request.form()
        choice = str(form.get("set", ""))
        if choice == "true":
            encounter_mod.mark(entity, True)
            note = f"marked {verb}"
        elif choice == "false":
            encounter_mod.mark(entity, False)
            note = f"hidden until {verb}"
        elif choice == "clear":
            encounter_mod.mark(entity, None)
            note = f"unmarked {verb}"
        else:
            # The original button: flips between encountered and untracked.
            value = None if encounter_mod.flag_of(entity) else True
            encounter_mod.mark(entity, value)
            note = f"marked {verb}" if value else f"unmarked {verb}"
        library.save(entity)
        # An encounter can reveal other pages outright -- walk into the shop
        # and you have met the shopkeeper -- so the cascade map is settled
        # in the same breath as the flag.
        revealed = access_mod.recompute_reveals(library)
        if revealed:
            note += ", changing " + ", ".join(sorted(revealed))
        wiki.record(f"{ref}: {note} on the wiki", user or "someone")
        # The reveal web posts the same toggles; send its presses back to
        # the board instead of scattering the DM onto individual pages.
        if str(form.get("back", "")) == "reveals":
            return RedirectResponse("/wiki/reveals", status_code=303)
        return RedirectResponse(f"/wiki/{kind}/{slug}.html", status_code=303)

    async def reveal_web(request):
        """The reveal graph, drawn. DM only: the web IS the trick showing."""
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        if not viewer.is_dm:
            return HTMLResponse("Not found", status_code=404)
        return render("Reveal web",
                      site_mod.render_reveal_web(schema, library, "/wiki/"),
                      user=user)

    async def wire_reveal(request):
        """Connect two pages in the reveal graph. DM only.

        `direction` says which end of the wire this page holds: "revealed_by"
        adds `target` to this page's own gate, "reveals" adds this page to
        the target's. Either way the stored fact is one `revealed_by` list
        on the gated page -- the wire has no second record to drift.
        """
        redirect = require_login(request)
        if redirect:
            return redirect
        viewer, user = viewer_for(request)
        kind, slug = request.path_params["kind"], request.path_params["slug"]
        ref = f"{kind}/{slug}"
        _, allowed = entities_for(viewer)
        # Same 404 as a missing page for non-DMs, like every other route:
        # a 403 would confirm there is something here to press.
        if ref not in allowed or not viewer.is_dm:
            return HTMLResponse("Not found", status_code=404)
        entity = library.load(kind, slug)
        form = await request.form()
        direction = str(form.get("direction", ""))
        raw = str(form.get("target", "")).strip()
        target = library.load(*raw.split("/", 1)) if "/" in raw else None
        if target is None and raw:
            # A typed name rather than a picked ref. Exact match only:
            # guessing at "Bogwatchers" between the temple and the faction
            # would wire a gate nobody asked for.
            matches = [e for e in library.all()
                       if e.name.strip().lower() == raw.lower()]
            if len(matches) == 1:
                target = matches[0]
        if target is None or direction not in ("revealed_by", "reveals"):
            return HTMLResponse("No such page.", status_code=400)
        gated = entity if direction == "revealed_by" else target
        source = target if direction == "revealed_by" else entity
        if gated.ref == source.ref:
            return HTMLResponse("A page cannot reveal itself.",
                                status_code=400)
        if source.ref not in encounter_mod.sources_of(gated):
            gates = gated.data.get("revealed_by") or []
            if isinstance(gates, str):
                gates = [gates]
            gated.data["revealed_by"] = list(gates) + [source.ref]
            library.save(gated)
            # The new wire may already be live: a gate wired to a place the
            # party has stood in reveals its page in the same breath.
            revealed = access_mod.recompute_reveals(library)
            note = f"revealed by {source.ref}"
            if revealed:
                note += ", changing " + ", ".join(sorted(revealed))
            wiki.record(f"{gated.ref}: {note} on the wiki", user or "someone")
        return RedirectResponse(f"/wiki/{kind}/{slug}.html", status_code=303)

    async def impersonate(request):
        """Put on, or take off, a player's eyes. DM only.

        Sets nothing but a session key: `viewer_for` does the actual seeing,
        and `require_login` keeps the mask read-only. Posting without a
        valid player clears the mask, which is what the "back to yourself"
        button sends.
        """
        redirect = require_login(request)
        if redirect:
            return redirect
        person = registry.members.get(request.session.get("who", ""))
        if person is None or not person.is_dm:
            # Same 404 a player gets on any DM-only door.
            return HTMLResponse("Not found", status_code=404)
        form = await request.form()
        target = str(form.get("who", "")).strip().lower()
        other = registry.members.get(target)
        if other is not None and not other.is_dm:
            request.session["as"] = target
        else:
            request.session.pop("as", None)
        return RedirectResponse("/wiki/", status_code=303)

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
            for field in ("name", "summary", "body", "kind", "source",
                          "within", "links"):
                supplied = request.query_params.get(field, "").strip()
                if supplied and (field != "kind" or schema.has(supplied)):
                    values[field] = supplied
            # The Inside picker, from birth: half of new places are written
            # the moment somebody walks into somewhere, and giving the page
            # its parent now beats a second trip through the edit form. The
            # field only means anything when the type picked is Place; the
            # POST below ignores it for everything else.
            return render("New page",
                          _edit_form(values, registry, schema.kinds, withheld=0,
                                     action="/wiki/new", creating=True,
                                     within_options=place_options(
                                         values.get("within", "")),
                                     tag_pills=tag_suggestions(),
                                     dm=viewer.is_dm),
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
                            "source": str(form.get("source", "")),
                            "revealed_by": str(form.get("revealed_by", ""))},
                           registry, schema.kinds, withheld=0,
                           action="/wiki/new", creating=True,
                           error="Give it a name and pick a type.",
                           within_options=place_options(""),
                           tag_pills=tag_suggestions(),
                           dm=viewer.is_dm),
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
        # Only places nest; a chosen parent on any other kind is dropped, and
        # a fresh page has no children, so no choice of parent can loop.
        within = str(form.get("within", "")).strip()
        if kind != hierarchy_mod.KIND:
            within = ""
        elif within:
            if "/" not in within:
                within = f"{hierarchy_mod.KIND}/{within}"
            # A hand-made POST can name a parent that is not there; a page
            # inside a ghost renders as inside nothing but keeps the lie.
            if not library.exists(*within.split("/", 1)):
                within = ""
        entity = Entity(
            kind=kind, slug=slug, name=name, within=within,
            summary=str(form.get("summary", "")).strip(),
            appearance=str(form.get("appearance", "")).strip(),
            body=body.strip(),
            tags=[t.strip() for t in str(form.get("tags", "")).split(",") if t.strip()],
            links=[l.strip() for l in str(form.get("links", "")).split(",")
                   if l.strip() and "/" in l],
            sources=([source] if source else []) + [f"created by {user} on the wiki"],
        )
        gate_changed = False
        if viewer.is_dm and "revealed_by" in form:
            gate_changed = apply_gate(entity, str(form.get("revealed_by", "")))
        library.save(entity)
        if gate_changed:
            access_mod.recompute_reveals(library)
        wiki.record(f"{kind}/{slug}: created on the wiki", user)
        # A page citing a Discord message is the message being dealt with, so
        # the inbox drops it without anyone pressing a second button.
        return RedirectResponse(f"/wiki/{kind}/{slug}.html", status_code=303)

    return panels.routes(wiki) + [
        Route("/wiki/new", new_page, methods=["GET", "POST"]),
        Route("/wiki/{kind}/{slug}/edit", edit, methods=["GET", "POST"]),
        Route("/wiki/{kind}/{slug}/delete", delete_page, methods=["POST"]),
        Route("/wiki/{kind}/{slug}/visited", toggle_visited, methods=["POST"]),
        Route("/wiki/{kind}/{slug}/wire", wire_reveal, methods=["POST"]),
        Route("/wiki/reveals", reveal_web),
        Route("/wiki/impersonate", impersonate, methods=["POST"]),
        Route("/wiki/enter", enter, methods=["GET", "POST"]),
        Route("/wiki/login", login, methods=["GET", "POST"]),
        Route("/wiki/people/new", add_person, methods=["GET", "POST"]),
        Route("/wiki/logout", logout),
        Route("/wiki/guide", guide),
        Route("/wiki/connect", connect),
        Route("/wiki/changelog", changelog),
        Route("/wiki/places", places),
        Route("/wiki/", index),
        Route("/wiki/index.html", index),
        Route("/wiki/tooltips.js", tooltips_js),
        Route("/wiki/search.js", search_js),
        Route("/wiki/{kind}/index.html", kind_index),
        Route("/wiki/{kind}/{slug}.html", page),
    ]


# -- forms -------------------------------------------------------------

def _edit_form(v: dict, registry: people_mod.People, kinds, withheld: int,
               action: str, creating: bool = False, error: str = "",
               within_options: str = "",
               tag_pills: dict[str, list[str]] | None = None,
               dm: bool = False) -> str:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    title = "New page" if creating else f"Editing {v['name']}"

    # Delete, behind a confirm (wired in the shell script): a separate form,
    # because a button inside the edit form would submit the edit.
    delete_form = "" if creating else f"""
<form class="danger" method="post" action="{action[:-len('/edit')]}/delete"
      data-confirm="Delete {html.escape(v['name'])}? Git history keeps a copy,
but the page comes off the site now.">
  <button type="submit" class="dangerbtn">Delete this page</button>
</form>
"""

    kinds = "".join(
        f'<option value="{html.escape(k.key)}"'
        f'{" selected" if k.key == v["kind"] else ""}>'
        f'{html.escape(k.label)}</option>'
        for k in kinds
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

    # Only places nest, and only on a form that was given the options. Anything
    # that would make a loop is already missing from the list. On the new-page
    # form the row is present for every type but shown only while Place is
    # picked -- the script below drives it off the type selector.
    within_field = (
        '  <div id="withinrow">'
        '<label for="w">Inside <span class="hint">the larger place this one '
        'sits in. A shop goes inside its city, a district inside its '
        'realm.</span></label>\n'
        f'  <select id="w" name="within">{within_options}</select></div>\n'
        if within_options else ""
    )

    # A new page asks for what only a person can supply -- name, summary,
    # tags, where it sits. Appearance and body are writing work, better done
    # on the page itself once it exists, and a six-field birth form gets
    # abandoned halfway. One exception: the inbox hands a Discord message's
    # text in as the body, and that text needs somewhere to sit -- dropping
    # the field would drop the message.
    appearance_field = "" if creating else f"""
  <label for="a">Appearance <span class="hint">what it looks like, concrete
    and visual. This is what the art generator draws, so write physique and
    colour, not "a tortle".</span></label>
  <input id="a" name="appearance" value="{html.escape(v['appearance'])}">
"""
    body_field = "" if creating and not v["body"].strip() else f"""
  <label for="b">Body <span class="hint">markdown is fine, tables included
    &mdash; the <a href="/wiki/guide">guide</a> shows the shape</span></label>
  <textarea id="b" name="body" rows="16">{html.escape(v['body'])}</textarea>
"""

    # The wiki's own vocabulary as toggles, per type. Clicking writes into
    # the same text input, so hand-typed tags and pills coexist.
    pills_html = ""
    pills_script = ""
    if creating and tag_pills:
        pills_html = '<div id="tagpills" class="tagpills"></div>'
        pills_script = f"""
<script>
(function() {{
  var SUG = {json.dumps(tag_pills)};
  var k = document.getElementById('k');
  var t = document.getElementById('t');
  var row = document.getElementById('withinrow');
  var pills = document.getElementById('tagpills');
  if (!k || !t || !pills) return;
  function cur() {{
    return t.value.split(',').map(function(x) {{ return x.trim(); }})
      .filter(Boolean);
  }}
  function draw() {{
    if (row) row.style.display = k.value === 'place' ? '' : 'none';
    pills.innerHTML = '';
    var have = cur();
    (SUG[k.value] || []).forEach(function(tag) {{
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'pill' + (have.indexOf(tag) >= 0 ? ' on' : '');
      b.textContent = tag;
      b.addEventListener('click', function() {{
        var list = cur(), i = list.indexOf(tag);
        if (i >= 0) list.splice(i, 1); else list.push(tag);
        t.value = list.join(', ');
        b.classList.toggle('on', i < 0);
      }});
      pills.appendChild(b);
    }});
  }}
  k.addEventListener('change', draw);
  t.addEventListener('input', function() {{
    var have = cur();
    pills.querySelectorAll('.pill').forEach(function(b) {{
      b.classList.toggle('on', have.indexOf(b.textContent) >= 0);
    }});
  }});
  draw();
}})();
</script>
"""

    boxes = "".join(
        f'<label class="cb"><input type="checkbox" name="audience" '
        f'value="{html.escape(p.key)}"> {html.escape(p.name)}'
        f'{" (DM)" if p.is_dm else ""}</label>'
        for p in registry.members.values()
    )

    # The reveal gate, only on the DM's copy of the form. Rendering it for a
    # player would name the trick even with the value blank.
    gate_field = "" if not dm else f"""
  <fieldset class="secretbox">
    <legend>Reveal gate</legend>
    <p class="hint">Hidden until the party encounters one of these pages --
    visiting the shop counts as meeting whoever it reveals. Comma separated,
    as place/the-kindled-wick; a bare name is taken as a place. Leave empty
    for no gate; the Hide/Mark buttons on the page cover one-off hiding.</p>
    <input name="revealed_by" value="{html.escape(v.get('revealed_by', ''))}">
  </fieldset>
"""

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

{appearance_field}{body_field}{within_field}
  <label for="t">Tags <span class="hint">comma separated, or click</span></label>
  {pills_html}
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
{gate_field}
  <button type="submit">{"Create" if creating else "Save"}</button>
</form>
{delete_form}
{pills_script}
"""


def _connect_page(name: str, url: str, token: str) -> str:
    """One thing to copy, and everything else folded away behind it.

    This page used to open with five blocks: the raw facts, a prompt, a CLI
    line, a config file and a curl check. All correct, and all asking the
    reader to first work out which of the five was theirs. Most of the table
    does not know what transport their assistant uses and should not have to.

    So there is one block now. Assistants are good at configuring themselves
    given the details, and the details are in it. The per-client recipes are
    still here for anything that cannot, but they are folded away, because a
    page that opens with a decision is a page people close.
    """
    prompt = (
        "Connect me to my D&D campaign wiki. It's an MCP server.\n"
        "\n"
        f"  Name:       buried-star\n"
        f"  Transport:  streamable HTTP (not SSE, not stdio)\n"
        f"  URL:        {url}\n"
        f"  Header:     Authorization: Bearer {token}\n"
        "\n"
        "Add it however this client does that. If you can't do it yourself, "
        "tell me exactly which buttons to press.\n"
        "\n"
        "Then check it worked by calling the whoami tool. It should come back "
        f"with my name, {name}. If it says guest, the header didn't go through."
    )
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
<p class="summary">Copy this and paste it to Claude, ChatGPT, or whatever you
use. It already has your own details in it.</p>

{block(1, prompt)}

<p class="hint">That's the whole thing. Assistants know how to add an MCP server
to themselves, and this tells them everything they need. If yours can't, it will
tell you which buttons to press.</p>

<p class="hint"><strong>Treat it like a password.</strong> It can write to the
campaign, and it decides whose secrets you get shown, so it is yours and not the
table's. If it leaks, tell your DM and it can be replaced.</p>

<details>
<summary>If your client wants it spelled out</summary>

<p>This wiki speaks <a href="https://modelcontextprotocol.io">MCP</a>, an open
protocol rather than one company's feature, so anything that speaks it can read
this world and write to it.</p>

<h2>The details, for any client</h2>
{block(0, facts)}
<p class="hint">Most clients ask for exactly these somewhere in their settings,
under MCP, Connectors, or Tools.</p>

<h2>Claude Code, and other CLIs that copied its syntax</h2>
{block(2, cli)}

<h2>A config file</h2>
<p class="hint">Claude Desktop, Cursor, Windsurf, Cline, Zed and most others use
this shape, in their own settings file. Some spell the top-level key
<code>servers</code> or <code>mcp.servers</code>; the inside is the same.</p>
{block(3, config)}

<h2>Proving the endpoint is up, without an assistant at all</h2>
{block(4, curl)}

</details>

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


def _signin_form(roster: list, error: str = "", current: str | None = None) -> str:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""

    buttons = "".join(
        f'<button class="who{" on" if p.key == current else ""}" type="submit" '
        f'name="who" value="{html.escape(p.key)}">'
        f'<span class="n">{html.escape(p.name)}</span>'
        f'<span class="c">{html.escape(p.character) if p.character else ("Dungeon Master" if p.is_dm else "Player")}</span>'
        f"</button>"
        for p in roster
    )
    if current:
        err = err + ('<div class="notice">You are signed in already. Pick a '
                     'different name to see the world as they do.</div>')

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
