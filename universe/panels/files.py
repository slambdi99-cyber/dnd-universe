"""Files that belong to a page: maps, handouts, PDFs, recordings.

Separate from art because they are different jobs. Art is the one picture at
the top of the page; this is everything else the table wants kept with it.

Everything here is served as a download and never inline. A file that renders
in the page is a file that can run scripts on the wiki's own origin.
"""

from __future__ import annotations

from functools import partial

import html
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, HTMLResponse
from starlette.routing import Route

from ..assetref import AssetRef
from .. import thumbs as thumbs_mod
from .. import uploads as uploads_mod

async def files_panel(request, wiki):
    """Files that belong to a page: maps, handouts, PDFs, recordings.

    Separate from art because they're different jobs. Art is the one
    picture at the top of the page; this is everything else the table
    wants to keep with it.
    """
    redirect = wiki.require_login(request)
    if redirect:
        return redirect
    viewer, user = wiki.viewer_for(request)
    kind, slug = request.path_params["kind"], request.path_params["slug"]
    _, allowed = wiki.entities_for(viewer)
    if f"{kind}/{slug}" not in allowed:
        return HTMLResponse("Not found", status_code=404)
    entity = wiki.library.load(kind, slug)
    error = message = ""

    if request.method == "POST":
        form = await request.form()
        if str(form.get("action", "")) == "remove":
            if uploads_mod.detach_file(entity, str(form.get("file", ""))):
                wiki.library.save(entity)
                message = "Removed from this page."
            else:
                error = "That file isn't on this page."
        else:
            sent = form.get("file")
            data = await sent.read() if hasattr(sent, "read") else b""
            upload, note = uploads_mod.save(
                Path(wiki.cfg.files_dir), kind, slug, data,
                getattr(sent, "filename", "") or "")
            if upload is None:
                error = note
            else:
                uploads_mod.attach_file(entity, upload, user or "")
                wiki.library.save(entity)
                message = f"Added {upload.filename}."

    return wiki.render(f"Files on {entity.name}",
                  _files_form(entity, uploads_mod.attachments_of(entity),
                              message, error),
                  user=user)


async def file_download(request, wiki):
    """Serve an attachment, permission-checked against its page.

    Always as a download, never inline. A file that renders in the page is
    a file that can run scripts on the wiki's own origin, and the point of
    this route is to hand people back what they put in, not to host it.
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

    path = uploads_mod.locate(Path(wiki.cfg.files_dir), ref)
    if path is None:
        return wiki.not_found()

    entity = wiki.library.load(ref.kind, ref.slug)
    name = next((f.get("name") for f in uploads_mod.attachments_of(entity)
                 if f.get("id") == str(ref)), path.name) if entity else path.name

    # ?size=card / ?size=page for the inline previews, exactly like the art
    # route. Only when the shrink actually produced a thumbnail: `make` hands
    # back the original for anything it cannot read, and serving a PDF or a
    # zip inline because someone typed ?size= would reopen the hole the
    # attachment disposition exists to close. A generated WEBP cannot carry
    # scripts, so it alone may render in the page.
    size = request.query_params.get("size", "")
    if size in thumbs_mod.SIZES:
        shrunk = await run_in_threadpool(thumbs_mod.make, path, size)
        if shrunk is not None and shrunk != path:
            return FileResponse(shrunk, headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, max-age=604800",
            })

    return FileResponse(
        path,
        media_type=uploads_mod.media_type_for(path),
        filename=name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _files_form(entity, files: list[dict], message: str, error: str) -> str:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    note = f'<div class="notice">{html.escape(message)}</div>' if message else ""

    rows = []
    for f in files:
        size = f.get("size", 0)
        readable = (f"{size / 1024 / 1024:.1f}MB" if size > 1024 * 1024
                    else f"{max(1, size // 1024)}KB")
        by = f" &middot; added by {html.escape(str(f['by']))}" if f.get("by") else ""
        preview = (f'<img src="/wiki/file/{html.escape(f["id"])}" alt="" loading="lazy">'
                   if str(f.get("type", "")).startswith("image/") else "")
        rows.append(f"""
<div class="filerow">
  {preview}
  <div class="what">
    <a href="/wiki/file/{html.escape(f["id"])}">{html.escape(f.get("name", "file"))}</a>
    <span class="hint">{html.escape(str(f.get("type", "")))} &middot; {readable}{by}</span>
  </div>
  <form method="post" class="inline">
    <input type="hidden" name="action" value="remove">
    <input type="hidden" name="file" value="{html.escape(f["id"])}">
    <button type="submit">Remove</button>
  </form>
</div>""")

    listing = ("".join(rows) if rows else
               '<p class="hint">Nothing attached yet.</p>')

    return f"""
<div class="kind">Files<a class="edit" href="/wiki/{entity.kind}/{entity.slug}.html">Back</a></div>
<h1>{html.escape(entity.name)}</h1>
{err}{note}
<p class="summary">Maps, handouts, PDFs, recordings: anything the table wants
kept with this page.</p>
{listing}

<h2>Add a file</h2>
<form class="auth wide" method="post" enctype="multipart/form-data">
  <input type="file" name="file" required>
  <button type="submit">Upload</button>
</form>
<p class="hint">Images, PDF, ZIP, MP3, OGG and MP4, up to 25MB. Not SVG: it can
carry scripts, and it would run as part of this site. Removing a file takes it
off the page but doesn't delete it, in case another page uses the same one.</p>
"""


def routes(wiki) -> list[Route]:
    return [
        Route("/wiki/{kind}/{slug}/files", partial(files_panel, wiki=wiki),
              methods=["GET", "POST"]),
        Route("/wiki/file/{asset:path}", partial(file_download, wiki=wiki)),
    ]
