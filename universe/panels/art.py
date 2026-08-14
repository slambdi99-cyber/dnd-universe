"""The picture at the top of a page: generated, or uploaded.

Both land in the same gallery on purpose. A portrait someone drew or
commissioned should be able to beat SDXL's attempt, and it can only do that if
they sit side by side and one click apart.

Nothing is attached until a person picks it, so a prompt that comes out badly
costs GPU time and nothing else.
"""

from __future__ import annotations

from functools import partial

import html
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import thumbs as thumbs_mod
from ..assetref import ArtName, AssetRef
from .. import uploads as uploads_mod

async def art_panel(request, wiki):
    redirect = wiki.require_login(request)
    if redirect:
        return redirect
    viewer, user = wiki.viewer_for(request)
    kind, slug = request.path_params["kind"], request.path_params["slug"]
    _, allowed = wiki.entities_for(viewer)
    if f"{kind}/{slug}" not in allowed:
        return HTMLResponse("Not found", status_code=404)
    entity = wiki.library.load(kind, slug)

    prompt = ""
    candidates: list[str] = []
    error = ""
    message = ""

    if request.method == "POST":
        form = await request.form()
        action = str(form.get("action", "generate"))

        if action == "upload":
            # A picture someone drew, commissioned, or found beats anything
            # the GPU produces, so uploads join the same gallery rather
            # than living in a second-class section of their own.
            sent = form.get("file")
            data = await sent.read() if hasattr(sent, "read") else b""
            upload, note = uploads_mod.save(
                Path(wiki.cfg.assets_dir), kind, slug, data,
                getattr(sent, "filename", "") or "")
            if upload is None:
                error = note
            elif not upload.is_image:
                error = ("That isn't an image the browser can show. Add it "
                         "as an attachment on the page instead.")
            else:
                wiki.art().attach(entity, upload.asset_id)
                return RedirectResponse(f"/wiki/{kind}/{slug}.html",
                                        status_code=303)
        elif action == "pick":
            asset_id = str(form.get("asset", ""))
            # Only accept ids belonging to this page, so a crafted form
            # can't attach someone else's picture.
            if asset_id.startswith(f"{kind}/{slug}/") and \
                    wiki.art().attach(entity, asset_id):
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
                        wiki.art().generate_custom, entity, prompt, count=3
                    )
                    candidates = [r.asset_id for r in results]
                except Exception as exc:  # GPU out of memory, model missing
                    error = f"Couldn't generate that: {exc}"

    entity = wiki.library.load(kind, slug) or entity
    existing = [a for a in entity.art]
    return wiki.render(f"Art for {entity.name}",
                  _art_form(entity, existing, candidates, prompt, error,
                            message),
                  user=user)


async def art_by_id(request, wiki):
    """Serve one image by asset id, for the art picker.

    Permission-checked against the page it belongs to, exactly like the
    named art route, or a restricted character's portrait would be
    reachable by guessing an id.
    """
    redirect = wiki.require_login(request)
    if redirect:
        return redirect
    viewer, _ = wiki.viewer_for(request)
    ref = AssetRef.parse(request.path_params["asset"])
    if ref is None:
        return wiki.not_found()
    _, allowed = wiki.entities_for(viewer)
    if ref.page not in allowed:
        return wiki.not_found()
    path = ref.path_under(wiki.cfg.assets_dir)
    if path is None:
        return wiki.not_found()
    size = request.query_params.get("size", "")
    if size in thumbs_mod.SIZES:
        path = thumbs_mod.make(path, size) or path
    # An asset id is a content hash, so these bytes are immutable.
    return FileResponse(path, headers={"Cache-Control": "private, max-age=604800"})


async def art(request, wiki):
    redirect = wiki.require_login(request)
    if redirect:
        return redirect
    viewer, _ = wiki.viewer_for(request)
    # "<kind>-<slug>.png". Only served if this viewer may see the page it
    # belongs to, or a restricted character's portrait leaks by direct URL.
    named = ArtName.parse(request.path_params["filename"])
    if named is None:
        return wiki.not_found()
    _, allowed = wiki.entities_for(viewer)
    if named.page not in allowed:
        return wiki.not_found()
    entity = wiki.library.load(named.kind, named.slug)
    if not entity or not entity.art:
        return wiki.not_found()
    current = AssetRef.parse(entity.art[-1])
    path = current.path_under(wiki.cfg.assets_dir) if current else None
    if path is None:
        return wiki.not_found()

    # ?size=card for the grids, ?size=page for a hero. A card was pulling the
    # full-size original, so a front page of thirty of them was tens of
    # megabytes to draw thumbnails a few hundred pixels wide.
    size = request.query_params.get("size", "")
    if size in thumbs_mod.SIZES:
        path = thumbs_mod.make(path, size) or path

    # Art is content-addressed: a given URL's bytes never change, because
    # picking a different picture changes the entity's current asset id and
    # therefore what this route resolves to. A week is conservative.
    return FileResponse(path, headers={
        "Cache-Control": "private, max-age=604800",
    })


def _art_form(entity, existing: list[str], candidates: list[str],
              prompt: str, error: str, message: str = "") -> str:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    note = f'<div class="notice">{html.escape(message)}</div>' if message else ""
    current = existing[-1] if existing else None

    def gallery(ids: list[str], heading: str, note: str = "") -> str:
        if not ids:
            return ""
        cards = []
        for asset_id in ids:
            is_current = asset_id == current
            cards.append(
                f'<figure class="{"current" if is_current else ""}">'
                f'<img src="/wiki/art/id/{html.escape(asset_id)}.png?size=card" '
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
{err}{note}
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

<h2>Or upload one</h2>
<p class="hint">A picture you drew, commissioned or found. It goes straight on
the page and joins the gallery below. PNG, JPEG, GIF or WEBP, up to 25MB.</p>
<form class="auth wide" method="post" enctype="multipart/form-data"
      action="/wiki/{entity.kind}/{entity.slug}/art">
  <input type="hidden" name="action" value="upload">
  <input type="file" name="file" accept="image/png,image/jpeg,image/gif,image/webp" required>
  <button type="submit">Upload</button>
</form>
{picker}
"""


def routes(wiki) -> list[Route]:
    return [
        Route("/wiki/{kind}/{slug}/art", partial(art_panel, wiki=wiki),
              methods=["GET", "POST"]),
        Route("/wiki/art/id/{asset:path}.png", partial(art_by_id, wiki=wiki)),
        Route("/wiki/art/{filename}", partial(art, wiki=wiki)),
    ]
