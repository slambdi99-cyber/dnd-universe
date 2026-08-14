"""The per-request machinery every part of the website shares.

`webapp.py` grew into the whole application: nine features and their HTML in
one 1,360-line module, and the file every change had to touch. The features
have moved out into `panels/`, and this is what they all needed from it.

The obvious split, routes in one module and HTML in another, was rejected on
purpose. It produces two shallow modules that have to be read together, because
every change touches both. Cutting by feature instead means a panel's route,
its form and its rendering sit in one file, and the whole story of "what happens
when someone uploads a battle map" is readable in one screen.

So this holds the things that are genuinely common: who is asking, what they may
see, how a page is wrapped in the site's chrome, and how a structural change is
made undoable. Panels take one of these and add a feature.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.responses import HTMLResponse, RedirectResponse

from . import access as access_mod
from . import gate as gate_mod
from . import inbox as inbox_mod
from . import people as people_mod
from . import schema as schema_mod
from . import site as site_mod
from .entities import Entity, Library


@dataclass
class Wiki:
    """One live wiki, and everything a request needs to be answered."""

    cfg: Any
    library: Library
    registry: people_mod.People
    schema: schema_mod.Schema
    inbox: inbox_mod.Inbox
    _art: Any = None
    _renderer: Any = None

    @property
    def pages(self) -> site_mod.Renderer:
        """Rendering bound to this wiki's schema."""
        if self._renderer is None:
            self._renderer = site_mod.Renderer(self.schema)
        return self._renderer

    # -- people --------------------------------------------------------

    def reload_people(self) -> None:
        """Pick up anyone added since the server started."""
        fresh = people_mod.load(Path(self.cfg.root))
        if fresh.members:
            self.registry.members = fresh.members

    def roster(self) -> list[people_mod.Person]:
        self.reload_people()
        return sorted(self.registry.members.values(),
                      key=lambda p: (not p.is_dm, p.name.lower()))

    # -- who is asking -------------------------------------------------

    def viewer_for(self, request) -> tuple[access_mod.Viewer, str | None]:
        key = request.session.get("who")
        if not key:
            return access_mod.Viewer.nobody(), None
        person = self.registry.members.get(key)
        if person is None:
            self.reload_people()
            person = self.registry.members.get(key)
        if person is None:
            return access_mod.Viewer.nobody(), None
        return access_mod.Viewer.person(person), person.name

    def require_login(self, request):
        """Two doors, in order: the shared passphrase, then who you are.

        The passphrase answers "is this someone from our table". The name
        answers "which secrets do I render". Only the first is a boundary.
        """
        if gate_mod.is_enabled(Path(self.cfg.root)) and not request.session.get("gate"):
            return RedirectResponse("/wiki/enter", status_code=303)
        if not request.session.get("who"):
            return RedirectResponse("/wiki/login", status_code=303)
        return None

    def open_page(self, request):
        """Resolve `kind/slug` from the path for a viewer who may read it.

        Returns (entity, viewer, user) or (None, viewer, user). Every panel
        that acts on one page starts this way, and a page the viewer may not
        see is indistinguishable from one that does not exist.
        """
        viewer, user = self.viewer_for(request)
        kind, slug = request.path_params["kind"], request.path_params["slug"]
        _, allowed = self.entities_for(viewer)
        if f"{kind}/{slug}" not in allowed:
            return None, viewer, user
        return self.library.load(kind, slug), viewer, user

    # -- what they may see ---------------------------------------------

    def entities_for(self, viewer: access_mod.Viewer):
        """One viewer's world, computed once per request."""
        everything = sorted(self.library.all(), key=lambda e: (e.kind, e.name))
        view = access_mod.for_viewer(everything, viewer)
        return view.entities, view.refs

    def images_for(self, entities) -> dict[str, str]:
        out = {}
        for entity in entities:
            if entity.art:
                kind, slug, name = entity.art[-1].split("/", 2)
                if (self.cfg.assets_dir / kind / slug / f"{name}.png").exists():
                    out[entity.ref] = f"{kind}-{slug}.png"
        return out

    # -- rendering -----------------------------------------------------

    def nav_extra(self, user: str | None) -> str:
        """The writing actions, on every page rather than just the front one.

        Adding something was previously a link on the index, which meant
        reading a page about a place and wanting to write down what happened
        there took you back to the front page first. Nobody does that; they
        forget instead.
        """
        if not user:
            return ""
        try:
            waiting = self.inbox.count(self.library)
        except OSError:
            waiting = 0
        badge = f'<span class="badge">{waiting}</span>' if waiting else ""
        return (
            '<a class="act" href="/wiki/new">+ New</a>'
            f'<a class="act" href="/wiki/inbox">Inbox{badge}</a>'
            '<a class="act" href="/wiki/structure">Structure</a>'
        )

    def render(self, title: str, body: str, index_json: str = "[]", *,
               user: str | None = None, tips: bool = False,
               status: int = 200) -> HTMLResponse:
        return HTMLResponse(
            self.pages.shell(title, "/wiki/", body, index_json, user=user,
                             live=True, tips=tips, extra=self.nav_extra(user)),
            status_code=status,
        )

    def not_found(self) -> HTMLResponse:
        return HTMLResponse("Not found", status_code=404)

    # -- art -----------------------------------------------------------

    def art(self):
        """Built on first use so the GPU stack isn't imported at startup."""
        if self._art is None:
            from .art import ArtService
            from .assets import AssetStore

            self._art = ArtService(self.cfg, self.library,
                                   AssetStore(self.cfg.assets_dir))
        return self._art

    # -- undo ----------------------------------------------------------

    def snapshot(self, what: str, who: str) -> None:
        """Commit before reshaping anything, so it can be undone.

        A rename touches every file in content/, and without a commit first
        there is no before to go back to.
        """
        import subprocess

        try:
            subprocess.run(["git", "add", "-A"], cwd=self.cfg.root, check=False,
                           capture_output=True, timeout=30)
            subprocess.run(
                ["git", "commit", "-q", "-m", f"before: {what} ({who})"],
                cwd=self.cfg.root, check=False, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            # No git, or no repo. The change still goes ahead: the person asked
            # for it, and refusing to work without version control would be a
            # strange place to draw a line.
            pass
