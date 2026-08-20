"""Everything said in Discord that no page accounts for yet.

A review queue, never an importer. The wiki is what the table decided is true;
Discord is four years of argument, jokes and half-ideas. Only a person can tell
those apart, so nothing here writes to the wiki on its own.
"""

from __future__ import annotations

from functools import partial

import html
from pathlib import Path

from urllib.parse import quote

from starlette.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import uploads as uploads_mod

async def inbox_page(request, wiki):
    """Everything said in Discord that no page accounts for yet.

    A review queue, not an importer. The wiki is what the table decided is
    true; Discord is four years of argument, jokes and half-ideas. Someone
    has to choose between them, and that someone is a person.
    """
    redirect = wiki.require_login(request)
    if redirect:
        return redirect
    viewer, user = wiki.viewer_for(request)

    keep = (f"?channel={request.query_params['channel']}"
            if request.query_params.get("channel") else "")

    if request.method == "POST":
        form = await request.form()
        action = str(form.get("action", ""))
        if action == "catch_up":
            wiki.inbox.catch_up(str(form.get("channel", "")) or None)
        elif action == "attach":
            note, error = _attach(wiki, viewer, user, form)
            extra = f"note={quote(note)}" if note else f"error={quote(error)}"
            return RedirectResponse(
                request.url.path + keep + ("&" if keep else "?") + extra,
                status_code=303)
        else:
            ids = [i for i in form.getlist("id") if i]
            if ids:
                wiki.inbox.file(ids)
        return RedirectResponse(request.url.path + keep, status_code=303)

    channel = request.query_params.get("channel") or None
    if channel and channel not in wiki.inbox.channels():
        channel = None
    waiting = wiki.inbox.unfiled(wiki.library, channel=channel, limit=60)
    total = wiki.inbox.count(wiki.library)
    entities, _ = wiki.entities_for(viewer)
    return wiki.render("Inbox",
                  _inbox_page(waiting, total, wiki.inbox.channels(), channel,
                              wiki.inbox.last_sync(),
                              _page_options(entities, wiki.schema),
                              note=request.query_params.get("note", "")[:300],
                              error=request.query_params.get("error", "")[:300]),
                  user=user)


def _attach(wiki, viewer, who, form) -> tuple[str, str]:
    """Copy a message's Discord attachments onto a page as ordinary files.

    Returns (note, error), one of which is empty. The bytes go through the
    same pipeline as the Files panel, so the type sniffing and the size limit
    hold here too. The page then cites the message as a source, which is what
    clears it from the inbox: writing nothing extra down is the point.
    """
    mid = str(form.get("id", "")).strip()
    ref = str(form.get("page", "")).strip()
    message = next((m for m in wiki.inbox.unfiled(wiki.library, limit=0)
                    if m.id == mid), None)
    if message is None:
        return "", "That message is no longer in the inbox."
    _, allowed = wiki.entities_for(viewer)
    if ref not in allowed:
        return "", "Pick a page from the list."
    entity = wiki.library.load(*ref.split("/", 1))
    if entity is None:
        return "", "That page has gone."

    attached: list[str] = []
    refused: list[str] = []
    for a in message.attachments:
        shown = a.get("filename") or a.get("file") or "file"
        stored = a.get("file")
        # `file` is the name dnd-scribe saved the download under; a message
        # can list an attachment it never managed to fetch.
        if not stored:
            refused.append(f"{shown} was never downloaded")
            continue
        path = wiki.inbox.attachment_path(message.channel, stored)
        if path is None or not path.exists():
            refused.append(f"{shown} is missing from the archive")
            continue
        upload, why = uploads_mod.save(
            Path(wiki.cfg.files_dir), entity.kind, entity.slug,
            path.read_bytes(), shown)
        if upload is None:
            refused.append(f"{shown}: {why}")
        else:
            uploads_mod.attach_file(entity, upload, who or "")
            attached.append(upload.filename)

    if not attached:
        return "", "; ".join(refused) or "That message has no attachments."

    if message.source not in entity.sources:
        entity.sources.append(message.source)
    wiki.library.save(entity)
    wiki.record(f"{entity.ref}: file attached from the inbox", who or "")
    note = f"Attached {', '.join(attached)} to {entity.name}."
    if refused:
        note += " Skipped: " + "; ".join(refused) + "."
    return note, ""


def _page_options(entities, schema) -> str:
    """The attach dropdown: every page this viewer can see, grouped by kind."""
    by_kind: dict[str, list] = {}
    for e in entities:
        by_kind.setdefault(e.kind, []).append(e)
    known = [k.key for k in schema.kinds]
    out = ['<option value="">Attach the file to&hellip;</option>']
    for kind in known + sorted(set(by_kind) - set(known)):
        group = sorted(by_kind.get(kind, []), key=lambda e: e.name.lower())
        if not group:
            continue
        out.append(f'<optgroup label="{html.escape(schema.label(kind))}">')
        out.extend(
            f'<option value="{html.escape(e.ref)}">{html.escape(e.name)}</option>'
            for e in group)
        out.append("</optgroup>")
    return "".join(out)


async def inbox_attachment(request, wiki):
    """An image posted in Discord, straight from the lore archive.

    Read from `dnd-scribe/lore`, which sits outside this project, so the
    path is resolved and checked rather than trusted.
    """
    redirect = wiki.require_login(request)
    if redirect:
        return redirect
    path = wiki.inbox.attachment_path(request.path_params["channel"],
                                 request.path_params["filename"])
    if path is None:
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(path)


def _inbox_page(messages, total: int, channels: list[str],
                channel: str | None, last_sync: str,
                page_options: str = "", note: str = "",
                error: str = "") -> str:
    def tab(c: str | None) -> str:
        href = "/wiki/inbox" if c is None else f"/wiki/inbox?channel={quote(c)}"
        cls = " class='on'" if c == channel else ""
        return f'<a href="{href}"{cls}>{html.escape(c or "Everything")}</a>'

    tabs = "".join(tab(c) for c in [None] + channels)
    checked = (f"Last checked {html.escape(last_sync[:16].replace('T', ' '))} UTC."
               if last_sync else
               "Discord has not been checked yet. Run sync.ps1 in dnd-scribe.")
    banner = ((f'<div class="notice">{html.escape(note)}</div>' if note else "")
              + (f'<div class="error">{html.escape(error)}</div>' if error else ""))

    if not messages:
        return f"""
<h1>Inbox</h1>
{banner}
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
        # Only offered when something was actually downloaded: an attachment
        # dnd-scribe never fetched has no bytes to copy anywhere.
        attach = ""
        if page_options and any(a.get("file") for a in m.attachments):
            attach = f"""
    <form method="post" class="inline">
      <input type="hidden" name="action" value="attach">
      <input type="hidden" name="id" value="{html.escape(m.id)}">
      <select name="page" required>{page_options}</select>
      <button type="submit">Attach</button>
    </form>"""
        cards.append(f"""
<div class="msg">
  <div class="meta"><strong>{html.escape(m.author)}</strong>
    <span class="chan">#{html.escape(m.channel)}</span>
    <span>{html.escape(m.at[:16].replace("T", " "))}</span></div>
  <div class="text">{html.escape(m.text)}</div>
  {f'<div class="shots">{shots}</div>' if shots else ""}
  {f'<p class="hint">Files: {files}</p>' if files else ""}
  <div class="acts">
    <a href="{prefill}">Write it up</a>{attach}
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
{banner}
<p class="summary">{total} message{"s" if total != 1 else ""} from Discord that
no page accounts for yet.</p>
<div class="tabs">{tabs}</div>
<p class="hint">{checked} A message disappears from here when a page cites it,
so writing it up is enough. "Attach" copies a message's file onto the page you
pick. "Not lore" is for the rest.</p>
{"".join(cards)}
{more}
<form method="post" class="catchup">
  <input type="hidden" name="action" value="catch_up">
  {f'<input type="hidden" name="channel" value="{html.escape(channel)}">' if channel else ""}
  <button type="submit">Mark everything here as read</button>
</form>
"""


def routes(wiki) -> list[Route]:
    return [
        Route("/wiki/inbox", partial(inbox_page, wiki=wiki),
              methods=["GET", "POST"]),
        Route("/wiki/inbox/att/{channel}/{filename}",
              partial(inbox_attachment, wiki=wiki)),
    ]
