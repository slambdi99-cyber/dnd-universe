"""Everything said in Discord that no page accounts for yet.

A review queue, never an importer. The wiki is what the table decided is true;
Discord is four years of argument, jokes and half-ideas. Only a person can tell
those apart, so nothing here writes to the wiki on its own.
"""

from __future__ import annotations

from functools import partial

import html
from pathlib import Path

from starlette.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.routing import Route

async def inbox_page(request, wiki):
    """Everything said in Discord that no page accounts for yet.

    A review queue, not an importer. The wiki is what the table decided is
    true; Discord is four years of argument, jokes and half-ideas. Someone
    has to choose between them, and that someone is a person.
    """
    redirect = wiki.require_login(request)
    if redirect:
        return redirect
    _, user = wiki.viewer_for(request)

    if request.method == "POST":
        form = await request.form()
        action = str(form.get("action", ""))
        if action == "catch_up":
            wiki.inbox.catch_up(str(form.get("channel", "")) or None)
        else:
            ids = [i for i in form.getlist("id") if i]
            if ids:
                wiki.inbox.file(ids)
        return RedirectResponse(request.url.path + (
            f"?channel={request.query_params['channel']}"
            if request.query_params.get("channel") else ""
        ), status_code=303)

    channel = request.query_params.get("channel") or None
    if channel and channel not in wiki.inbox.channels():
        channel = None
    waiting = wiki.inbox.unfiled(wiki.library, channel=channel, limit=60)
    total = wiki.inbox.count(wiki.library)
    return wiki.render("Inbox",
                  _inbox_page(waiting, total, wiki.inbox.channels(), channel,
                              wiki.inbox.last_sync()),
                  user=user)


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


def routes(wiki) -> list[Route]:
    return [
        Route("/wiki/inbox", partial(inbox_page, wiki=wiki),
              methods=["GET", "POST"]),
        Route("/wiki/inbox/att/{channel}/{filename}",
              partial(inbox_attachment, wiki=wiki)),
    ]
