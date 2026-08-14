"""Rendering for the wiki, shared by the static export and the live server.

One implementation, two callers. `tools/export_site.py` renders with an empty
viewer, which strips every secret, and produces files. `mcp_server.py` renders
per signed-in person, so each reader sees their own version. Keeping both on
the same code means a fix to redaction can't apply to one and miss the other.
"""

from __future__ import annotations

import html
import json
from collections import defaultdict

import markdown as md

from . import access as access_mod
from . import secrets as secrets_mod
from . import tooltips as tooltips_mod
from pathlib import Path

from . import schema as schema_mod
from .entities import Entity, Library

class Renderer:
    """Rendering bound to one schema.

    The schema used to be a module-level global that the server overwrote at
    startup through `site.use(...)`, so what a page rendered with depended on
    assignment order rather than on its arguments. The tell was already in the
    tests: they had to remember to call `use` first, and one that forgot
    silently rendered against whatever schema happened to be on disk.

    The functions below take the schema explicitly. This binds it once, so
    callers do not thread it through every call, and two schemas can exist at
    the same time: exporting one campaign while serving another is now
    expressible, which it was not before.
    """

    def __init__(self, schema: schema_mod.Schema):
        self.schema = schema

    @property
    def name(self) -> str:
        return self.schema.name

    def label(self, kind: str) -> str:
        return self.schema.label(kind)

    def shell(self, *args, **kwargs) -> str:
        return shell(self.schema, *args, **kwargs)

    def body(self, *args, **kwargs) -> str:
        return render_body(self.schema, *args, **kwargs)

    def index(self, *args, **kwargs) -> str:
        return render_index(self.schema, *args, **kwargs)

    def kind_index(self, *args, **kwargs) -> str:
        return render_kind_index(self.schema, *args, **kwargs)

    def search_index(self, *args, **kwargs) -> str:
        return search_index(self.schema, *args, **kwargs)

CSS = """
:root {
  --bg: #faf7f2; --panel: #fffdfa; --ink: #24211d; --muted: #6b6459;
  --line: #e3ddd2; --accent: #8a5a2b; --accent-soft: #f0e6d8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #17150f; --panel: #201d16; --ink: #ece7dd; --muted: #9c9384;
    --line: #322d23; --accent: #d9a05b; --accent-soft: #2b2418;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.65 Georgia, 'Iowan Old Style', 'Palatino Linotype', serif; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
header.top { position: sticky; top: 0; z-index: 10; background: var(--panel);
  border-bottom: 1px solid var(--line); padding: .7rem 1.2rem;
  display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
header.top .home { font-weight: bold; letter-spacing: .02em; }
header.top nav { display: flex; gap: .8rem; flex-wrap: wrap; font-size: .85rem;
  align-items: center; }
header.top .who { font-size: .8rem; color: var(--muted); }
/* Writing actions, set apart from the browsing links so "add something" is
   never more than one click away from any page. */
nav a.act { border: 1px solid var(--line); border-radius: 999px;
  padding: .1rem .6rem; background: var(--panel); }
nav a.act:hover { background: var(--accent-soft); text-decoration: none; }
nav a.act .badge { display: inline-block; margin-left: .35rem; padding: 0 .35rem;
  border-radius: 999px; background: var(--accent); color: var(--panel);
  font-size: .75rem; }
#q { margin-left: auto; padding: .4rem .7rem; min-width: 12rem; flex: 1 1 10rem;
  border: 1px solid var(--line); border-radius: 4px; background: var(--bg);
  color: var(--ink); font: inherit; font-size: .9rem; }
main { max-width: 46rem; margin: 0 auto; padding: 2rem 1.2rem 5rem; }
h1 { font-size: 2.1rem; margin: 0 0 .2rem; line-height: 1.15; }
h2 { font-size: 1.25rem; margin: 2rem 0 .6rem; border-bottom: 1px solid var(--line);
  padding-bottom: .3rem; }
h3 { font-size: 1.05rem; margin: 1.4rem 0 .4rem; }
.kind { color: var(--muted); font-size: .8rem; text-transform: uppercase;
  letter-spacing: .08em; }
.summary { font-style: italic; color: var(--muted); margin: .4rem 0 1.4rem;
  font-size: 1.05rem; }
img.hero { width: 100%; border-radius: 6px; border: 1px solid var(--line);
  display: block; margin: 0 0 1.5rem; }
blockquote { margin: 1rem 0; padding: .5rem 1rem; border-left: 3px solid var(--accent);
  background: var(--accent-soft); }
blockquote p { margin: .3rem 0; }
ul.links { list-style: none; padding: 0; display: flex; flex-wrap: wrap; gap: .5rem; }
ul.links li a { display: inline-block; padding: .25rem .6rem;
  border: 1px solid var(--line); border-radius: 999px; background: var(--panel);
  font-size: .85rem; }
.tags { margin: 1rem 0 0; }
.tag { display: inline-block; font-size: .72rem; text-transform: uppercase;
  letter-spacing: .06em; color: var(--muted); border: 1px solid var(--line);
  border-radius: 3px; padding: .1rem .4rem; margin: 0 .3rem .3rem 0; }
.meta { font-size: .8rem; color: var(--muted); margin-top: 2.5rem;
  border-top: 1px solid var(--line); padding-top: .8rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr));
  gap: 1rem; margin: 1rem 0 2rem; }
.card { border: 1px solid var(--line); border-radius: 6px; overflow: hidden;
  background: var(--panel); }
.card img { width: 100%; aspect-ratio: 1/1; object-fit: cover; display: block; }
.card .body { padding: .6rem .7rem; }
.card .body a { font-weight: bold; }
.card .body p { margin: .2rem 0 0; font-size: .8rem; color: var(--muted); }
#results .hit { padding: .5rem 0; border-bottom: 1px solid var(--line); }
#results .hit p { margin: .1rem 0 0; font-size: .85rem; color: var(--muted); }
.empty { color: var(--muted); font-style: italic; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .9rem; }
th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid var(--line); }
.secret { border-left: 3px solid var(--accent); background: var(--accent-soft);
  padding: .6rem 1rem; margin: 1rem 0; border-radius: 0 4px 4px 0; }
.secret .who { font-size: .7rem; text-transform: uppercase; letter-spacing: .08em;
  color: var(--accent); display: block; margin-bottom: .3rem; }
form.auth { max-width: 22rem; }
form.auth label { display: block; margin: .9rem 0 .2rem; font-size: .85rem;
  color: var(--muted); }
form.auth input, form.auth select { width: 100%; padding: .5rem .6rem; border: 1px solid var(--line);
  border-radius: 4px; background: var(--panel); color: var(--ink); font: inherit; }
form.auth button { margin-top: 1.2rem; padding: .55rem 1.2rem; border: 0;
  border-radius: 4px; background: var(--accent); color: #fff; font: inherit;
  cursor: pointer; }
.error { color: #b3261e; background: #fdecea; border: 1px solid #f5c6c2;
  padding: .6rem .8rem; border-radius: 4px; margin: 1rem 0; font-size: .9rem; }
@media (prefers-color-scheme: dark) {
  .error { color: #ffb4ab; background: #3b1512; border-color: #5c221d; }
}
.hint { color: var(--muted); font-size: .85rem; }
.guide h1 { margin-top: 0; }
.guide h2 { margin-top: 2.4rem; }
.guide pre { background: var(--panel); border: 1px solid var(--line);
  border-radius: 4px; padding: .8rem 1rem; overflow-x: auto; font-size: .8rem;
  line-height: 1.5; font-family: ui-monospace, Consolas, monospace;
  white-space: pre-wrap; word-break: break-word; }
.guide code { background: var(--accent-soft); padding: .1rem .3rem;
  border-radius: 3px; font-size: .85em;
  font-family: ui-monospace, Consolas, monospace; }
.guide pre code { background: none; padding: 0; font-size: inherit; }
.guide hr { border: 0; border-top: 1px solid var(--line); margin: 2.5rem 0; }
.guide blockquote { font-style: italic; }
.guide table { font-size: .85rem; }
.guide li { margin: .3rem 0; }
a.edit { float: right; font-size: .8rem; text-transform: none;
  letter-spacing: 0; border: 1px solid var(--line); border-radius: 4px;
  padding: .1rem .5rem; background: var(--panel); }
form.auth.wide { max-width: 46rem; }
form.auth textarea { width: 100%; padding: .5rem .6rem; border: 1px solid var(--line);
  border-radius: 4px; background: var(--panel); color: var(--ink);
  font: inherit; font-size: .9rem; line-height: 1.5; resize: vertical;
  font-family: ui-monospace, Consolas, monospace; }
form.auth label .hint { display: block; font-weight: normal; margin-top: .1rem; }
fieldset.secretbox { margin: 1.6rem 0 0; border: 1px solid var(--line);
  border-radius: 4px; padding: .6rem 1rem 1rem; }
fieldset.secretbox legend { font-size: .85rem; color: var(--accent);
  padding: 0 .4rem; }
.cbs { display: flex; flex-wrap: wrap; gap: .8rem; margin-top: .6rem; }
label.cb { display: inline-flex; align-items: center; gap: .3rem; margin: 0;
  font-size: .85rem; color: var(--ink); }
label.cb input { width: auto; }
.notice { border-left: 3px solid var(--accent); background: var(--accent-soft);
  padding: .6rem 1rem; margin: 1rem 0; font-size: .9rem; border-radius: 0 4px 4px 0; }
.newpage { float: right; font-size: .85rem; }
.whogrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: .7rem; margin: 1.4rem 0; }
button.who.on { border-color: var(--accent); background: var(--accent-soft); }
button.who { display: flex; flex-direction: column; gap: .15rem; text-align: left;
  padding: .8rem 1rem; border: 1px solid var(--line); border-radius: 6px;
  background: var(--panel); color: var(--ink); font: inherit; cursor: pointer; }
button.who:hover { border-color: var(--accent); }
button.who .n { font-weight: bold; }
button.who .c { font-size: .8rem; color: var(--muted); }
details.newperson { margin-top: 2rem; border-top: 1px solid var(--line);
  padding-top: 1rem; }
details.newperson summary { cursor: pointer; color: var(--accent);
  font-size: .9rem; }
.artgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
  gap: .8rem; margin: 1rem 0; }
.artgrid figure { margin: 0; border: 1px solid var(--line); border-radius: 6px;
  overflow: hidden; background: var(--panel); }
.artgrid img { width: 100%; display: block; aspect-ratio: 1/1; object-fit: cover; }
.artgrid button { width: 100%; border: 0; border-top: 1px solid var(--line);
  padding: .45rem; background: var(--panel); color: var(--accent); font: inherit;
  font-size: .85rem; cursor: pointer; }
.artgrid button:hover { background: var(--accent-soft); }
.artgrid figure.current { border-color: var(--accent); }
.artgrid figure.current button { color: var(--muted); cursor: default; }
.slow { border-left: 3px solid var(--accent); background: var(--accent-soft);
  padding: .6rem 1rem; margin: 1rem 0; font-size: .9rem; border-radius: 0 4px 4px 0; }
/* Uploaded files */
ul.filelist { list-style: none; padding: 0; }
ul.filelist li { padding: .35rem 0; border-bottom: 1px solid var(--line); }
.filerow { display: flex; gap: .8rem; align-items: center; padding: .6rem .8rem;
  border: 1px solid var(--line); border-radius: 6px; background: var(--panel);
  margin: .5rem 0; }
.filerow img { width: 3.5rem; height: 3.5rem; object-fit: cover; border-radius: 4px; }
.filerow .what { flex: 1; display: flex; flex-direction: column; }
input[type=file] { font: inherit; font-size: .9rem; padding: .4rem 0; }
/* Structure editor */
.kindrow { display: flex; gap: .6rem; flex-wrap: wrap; align-items: center;
  padding: .5rem .7rem; border: 1px solid var(--line); border-radius: 6px;
  background: var(--panel); margin: .4rem 0; }
.kindrow code { background: var(--accent-soft); padding: .1rem .4rem;
  border-radius: 3px; font-size: .85rem; }
form.inline { display: inline-flex; gap: .4rem; align-items: center; margin: 0; }
form.inline input, form.inline select { padding: .25rem .4rem; font: inherit;
  font-size: .85rem; border: 1px solid var(--line); border-radius: 4px;
  background: var(--bg); color: var(--ink); width: auto; }
form.inline button { border: 1px solid var(--line); border-radius: 4px;
  padding: .25rem .7rem; background: var(--bg); color: var(--ink); font: inherit;
  font-size: .85rem; cursor: pointer; }
form.inline button:hover { background: var(--accent-soft); }
/* Discord inbox */
.tabs { display: flex; gap: .8rem; flex-wrap: wrap; font-size: .85rem;
  border-bottom: 1px solid var(--line); padding-bottom: .5rem; margin: 1rem 0; }
.tabs a.on { color: var(--ink); font-weight: bold; }
form.catchup { margin: 2rem 0 0; }
form.catchup button { border: 1px solid var(--line); border-radius: 4px;
  padding: .4rem .9rem; background: var(--panel); color: var(--muted);
  font: inherit; font-size: .85rem; cursor: pointer; }
form.catchup button:hover { color: var(--ink); background: var(--accent-soft); }
.msg { border: 1px solid var(--line); border-radius: 6px; background: var(--panel);
  padding: .8rem 1rem; margin: .8rem 0; }
.msg .meta { font-size: .8rem; color: var(--muted); display: flex; gap: .5rem;
  flex-wrap: wrap; align-items: baseline; }
.msg .meta .chan { color: var(--accent); }
.msg .text { margin: .5rem 0 0; white-space: pre-wrap; }
.msg .shots { display: flex; gap: .5rem; flex-wrap: wrap; margin-top: .6rem; }
.msg .shots img { max-height: 11rem; border-radius: 4px; border: 1px solid var(--line); }
.msg .acts { margin-top: .7rem; display: flex; gap: .8rem; align-items: center;
  font-size: .85rem; }
.msg form { display: inline; }
.msg button { border: 1px solid var(--line); border-radius: 4px; padding: .25rem .7rem;
  background: var(--bg); color: var(--ink); font: inherit; font-size: .85rem;
  cursor: pointer; }
.msg button:hover { background: var(--accent-soft); }
.sheet { border: 1px solid var(--line); border-radius: 6px; padding: .9rem 1.1rem;
  margin: 2rem 0 0; background: var(--panel); }
.sheet .statline { font-size: .85rem; color: var(--muted); text-transform: uppercase;
  letter-spacing: .06em; margin-bottom: .5rem; }
a.sheetlink { display: inline-block; padding: .45rem .9rem; border-radius: 4px;
  background: var(--accent); color: #fff; font-size: .9rem; }
a.sheetlink:hover { text-decoration: none; opacity: .9; }
.sheet .hint { margin: .6rem 0 0; }
.copyblock { position: relative; margin: 1rem 0; }
.copyblock pre { background: var(--panel); border: 1px solid var(--line);
  border-radius: 4px; padding: .8rem 1rem; overflow-x: auto; font-size: .8rem;
  line-height: 1.5; white-space: pre-wrap; word-break: break-word;
  font-family: ui-monospace, Consolas, monospace; }
.copyblock button { position: absolute; top: .5rem; right: .5rem;
  padding: .25rem .6rem; font-size: .75rem; border: 1px solid var(--line);
  border-radius: 4px; background: var(--bg); color: var(--ink); cursor: pointer; }
"""

SEARCH_JS = """
const idx = window.__INDEX__ || [];
const q = document.getElementById('q');
const results = document.getElementById('results');
const page = document.getElementById('page');
if (q) {
  const render = term => {
    const t = term.trim().toLowerCase();
    if (!t) { results.innerHTML=''; results.hidden=true;
              if (page) page.hidden=false; return; }
    const hits = idx.filter(e => e.h.includes(t)).slice(0, 40);
    results.hidden = false;
    if (page) page.hidden = true;
    results.innerHTML = hits.length
      ? '<h2>' + hits.length + ' result' + (hits.length===1?'':'s') + '</h2>' +
        hits.map(e => '<div class="hit"><a href="' + BASE + e.u + '">' + e.n +
          '</a> <span class="kind">' + e.k + '</span><p>' + e.s + '</p></div>').join('')
      : '<p class="empty">Nothing matches that.</p>';
  };
  q.addEventListener('input', () => render(q.value));
  q.addEventListener('keydown', e => { if (e.key==='Escape') { q.value=''; render(''); } });
}
"""


def page_url(ref: str) -> str:
    kind, slug = ref.split("/", 1)
    return f"{kind}/{slug}.html"


def shell(schema, title: str, base: str, body: str, index_json: str,
          user: str | None = None, live: bool = False,
          tips: bool = False, extra: str = "") -> str:
    """Wrap rendered body text in the site chrome.

    `extra` goes in the nav and is only ever passed by the live server: the
    static export has nothing to link to for writing, and a New button that
    404s is worse than no button.
    """
    # The live server routes /wiki/guide; a static export has to be a real file
    # with an .html extension, or the browser downloads it instead of showing it.
    guide_href = f"{base}guide" if live else f"{base}guide.html"
    schema.reload_if_changed()
    nav = "".join(
        f'<a href="{base}{k.key}/index.html">{html.escape(k.label)}</a>'
        for k in schema.nav
    ) + f'<a href="{guide_href}">Guide</a>'
    # ASCII separators on purpose: these strings get rewritten by tooling now
    # and then, and a stray encoding round-trip turns punctuation into mojibake.
    full = title if title == schema.name else f"{title} - {schema.name}"
    if live:
        account = (
            f'<span class="who">{html.escape(user)} &middot; '
            f'<a href="{base}login">not you?</a> &middot; '
            f'<a href="{base}connect">connect an assistant</a> &middot; '
            f'<a href="{base}logout">sign out</a></span>'
            if user else f'<span class="who"><a href="{base}login">sign in</a></span>'
        )
    else:
        account = ""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full)}</title>
<style>{CSS}{tooltips_mod.TOOLTIP_CSS if tips else ""}</style>
</head><body>
<header class="top">
  <a class="home" href="{base}index.html">{html.escape(schema.name)}</a>
  <nav>{nav}{extra}</nav>
  {account}
  <input id="q" type="search" placeholder="Search the world..." autocomplete="off">
</header>
<main>
  <div id="results" hidden></div>
  <div id="page">{body}</div>
</main>
<script>const BASE={json.dumps(base)};{"window.__INDEX__=" + index_json + ";" if index_json != "[]" else ""}{SEARCH_JS}</script>
{f'<script src="{base}search.js" defer></script>' if live else ""}
{f'<script src="{base}tooltips.js"></script>' if tips else ""}
</body></html>
"""


def _markdown(text: str) -> str:
    return md.markdown(text, extensions=["tables", "nl2br"])


def render_guide(source: str) -> str:
    """The player guide, rendered from GUIDE.md.

    No nl2br here: the guide is prose with fenced code blocks that people copy,
    and forcing a line break at every newline would mangle them.
    """
    return (
        '<div class="guide">'
        + md.markdown(source, extensions=["tables", "fenced_code", "toc"])
        + "</div>"
    )


def render_body(schema, entity: Entity, library: Library, images: dict[str, str],
                base: str, viewer, allowed: set[str],
                editable: bool = False) -> str:
    edit_link = (
        f'<a class="edit" href="{base}{entity.kind}/{entity.slug}/edit">Edit</a>'
        f'<a class="edit" href="{base}{entity.kind}/{entity.slug}/art">Art</a>'
        f'<a class="edit" href="{base}{entity.kind}/{entity.slug}/files">Files</a>'
        if editable else ""
    )
    parts = [
        f'<div class="kind">{html.escape(schema.label(entity.kind))}'
        f"{edit_link}</div>",
        f"<h1>{html.escape(entity.name)}</h1>",
    ]
    if entity.summary:
        parts.append(f'<p class="summary">{html.escape(entity.summary)}</p>')
    if entity.ref in images:
        parts.append(
            f'<img class="hero" src="{base}art/{images[entity.ref]}?size=page" '
            f'alt="{html.escape(entity.name)}" loading="lazy">'
        )

    # Secret blocks this viewer may read are shown, marked, so nobody repeats
    # them at the table by accident.
    for segment in secrets_mod.parse(entity.body):
        if segment.audience is None:
            parts.append(_markdown(segment.text))
        elif viewer.all_access or (viewer.identities & segment.audience):
            who = ", ".join(sorted(segment.audience))
            parts.append(
                f'<div class="secret"><span class="who">secret &middot; {html.escape(who)}'
                f"</span>{_markdown(segment.text)}</div>"
            )

    def link_list(refs, heading):
        items = []
        for ref in sorted(set(refs)):
            if ref not in allowed:
                continue
            target = library.load(*ref.split("/", 1))
            if target:
                items.append(
                    f'<li><a href="{base}{page_url(ref)}">'
                    f"{html.escape(target.name)}</a></li>"
                )
        if items:
            parts.append(f"<h2>{heading}</h2>")
            parts.append(f'<ul class="links">{"".join(items)}</ul>')

    # Attachments, before the cross-links: a handout or a battle map is part of
    # the page, where Related is navigation away from it. Only shown live; the
    # static export has no route that can check who may download them.
    files = [f for f in (entity.data.get("files") or [])
             if isinstance(f, dict) and f.get("id")]
    if files and editable:
        rows = []
        for f in files:
            size = int(f.get("size", 0) or 0)
            readable = (f"{size / 1024 / 1024:.1f}MB" if size > 1024 * 1024
                        else f"{max(1, size // 1024)}KB")
            rows.append(
                f'<li><a href="{base}file/{html.escape(str(f["id"]))}">'
                f'{html.escape(str(f.get("name", "file")))}</a> '
                f'<span class="hint">{readable}</span></li>'
            )
        parts.append("<h2>Files</h2>")
        parts.append(f'<ul class="filelist">{"".join(rows)}</ul>')

    link_list(entity.links, "Related")
    link_list(
        [e.ref for e in library.backlinks(entity.ref) if e.ref not in entity.links],
        "Mentioned by",
    )

    sheet = entity.data.get("dndbeyond_sheet")
    if sheet:
        bits = " &middot; ".join(
            filter(None, [
                html.escape(str(entity.data.get("race", ""))),
                html.escape(str(entity.data.get("class", ""))),
                html.escape(str(entity.data.get("subclass", ""))),
                f"level {entity.data['level']}" if entity.data.get("level") else "",
            ])
        )
        parts.append(
            '<div class="sheet">'
            f'<div class="statline">{bits}</div>'
            f'<a class="sheetlink" href="{html.escape(sheet)}" target="_blank" '
            f'rel="noopener">Open character sheet on D&amp;D Beyond</a>'
            '<p class="hint">Hit points, spells and inventory live on the sheet, '
            'not here. It needs a D&amp;D Beyond account with access to the '
            'campaign.</p></div>'
        )

    if entity.tags:
        parts.append(
            '<div class="tags">'
            + "".join(f'<span class="tag">{html.escape(t)}</span>' for t in entity.tags)
            + "</div>"
        )

    meta = []
    # Fields already shown as the sheet button don't need a second airing in
    # the raw metadata table.
    shown_above = {"visible_to", "dndbeyond_sheet", "dndbeyond_campaign"}
    data = {k: v for k, v in entity.data.items()
            if k not in shown_above and v not in (None, "", [], {})}
    if data:
        rows = "".join(
            f"<tr><th>{html.escape(str(k).replace('_',' '))}</th>"
            f"<td>{html.escape(str(v))}</td></tr>" for k, v in data.items()
        )
        meta.append(f"<table>{rows}</table>")
    if entity.sources:
        meta.append("<p>Sources: " + ", ".join(
            f"<code>{html.escape(s)}</code>" for s in entity.sources) + "</p>")
    if meta:
        parts.append(f'<div class="meta">{"".join(meta)}</div>')

    return "\n".join(parts)


def _cards(items: list[Entity], images: dict[str, str], base: str) -> str:
    out = []
    for e in sorted(items, key=lambda e: e.name):
        img = (f'<img src="{base}art/{images[e.ref]}?size=card" alt="" loading="lazy">'
               if e.ref in images else "")
        out.append(
            f'<div class="card">{img}<div class="body">'
            f'<a href="{base}{page_url(e.ref)}">{html.escape(e.name)}</a>'
            f"<p>{html.escape(e.summary[:90])}</p></div></div>"
        )
    return f'<div class="grid">{"".join(out)}</div>'


def render_index(schema, entities: list[Entity], images: dict[str, str],
                 base: str, editable: bool = False) -> str:
    """The front page, assembled from the sections in config.yaml.

    Each section is a heading and a filter. An empty one is skipped rather than
    rendered as a bare heading, so a section for a kind nobody has written yet
    costs nothing to leave configured.
    """
    schema.reload_if_changed()
    parts = [
        f'<a class="newpage" href="{base}new">+ New page</a>' if editable else "",
        f"<h1>{html.escape(schema.name)}</h1>",
        f'<p class="summary">{html.escape(schema.tagline)}</p>'
        if schema.tagline else "",
    ]
    for section in schema.home:
        matched = [e for e in entities if section.matches(e)]
        if not matched:
            continue
        if section.title:
            parts.append(f"<h2>{html.escape(section.title)}</h2>")
        parts.append(_cards(matched, images, base))

    parts.append(f'<p class="meta">{len(entities)} pages.</p>')
    return "\n".join(parts)


def render_kind_index(schema, kind: str, items: list[Entity],
                      images: dict[str, str], base: str) -> str:
    label = schema.label(kind)
    return (f"<h1>{label}</h1><p class=\"summary\">{len(items)} pages.</p>"
            + _cards(items, images, base))


def search_index(schema, entities: list[Entity], viewer) -> str:
    """Client-side index containing only text this viewer may read."""
    return json.dumps(
        [
            {
                "n": e.name,
                "k": schema.label(e.kind).rstrip("s"),
                "s": e.summary[:120],
                "u": page_url(e.ref),
                "h": " ".join(
                    [e.name, e.summary, access_mod.redact(e.body, viewer),
                     " ".join(e.tags)]
                ).lower(),
            }
            for e in entities
        ],
        ensure_ascii=False,
    )


