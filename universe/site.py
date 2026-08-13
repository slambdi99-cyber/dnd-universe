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

from . import secrets as secrets_mod
from .entities import Entity, Library

KIND_LABEL = {
    "place": "Places",
    "character": "Characters",
    "faction": "Factions",
    "item": "Items",
    "deity": "Deities",
    "creature": "Creatures",
    "event": "Events",
    "session": "Sessions",
    "lore": "Lore",
}

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
header.top nav { display: flex; gap: .8rem; flex-wrap: wrap; font-size: .85rem; }
header.top .who { font-size: .8rem; color: var(--muted); }
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
form.auth input { width: 100%; padding: .5rem .6rem; border: 1px solid var(--line);
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


def shell(title: str, base: str, body: str, index_json: str,
          user: str | None = None, live: bool = False) -> str:
    nav = "".join(
        f'<a href="{base}{kind}/index.html">{label}</a>'
        for kind, label in KIND_LABEL.items()
    )
    full = title if title == "Copper Vale" else f"{title} — Copper Vale"
    if live:
        account = (
            f'<span class="who">{html.escape(user)} · '
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
<style>{CSS}</style>
</head><body>
<header class="top">
  <a class="home" href="{base}index.html">Copper Vale</a>
  <nav>{nav}</nav>
  {account}
  <input id="q" type="search" placeholder="Search the world..." autocomplete="off">
</header>
<main>
  <div id="results" hidden></div>
  <div id="page">{body}</div>
</main>
<script>const BASE={json.dumps(base)};window.__INDEX__={index_json};{SEARCH_JS}</script>
</body></html>
"""


def _markdown(text: str) -> str:
    return md.markdown(text, extensions=["tables", "nl2br"])


def render_body(entity: Entity, library: Library, images: dict[str, str],
                base: str, viewer: frozenset[str], allowed: set[str]) -> str:
    parts = [
        f'<div class="kind">{html.escape(KIND_LABEL.get(entity.kind, entity.kind))}</div>',
        f"<h1>{html.escape(entity.name)}</h1>",
    ]
    if entity.summary:
        parts.append(f'<p class="summary">{html.escape(entity.summary)}</p>')
    if entity.ref in images:
        parts.append(
            f'<img class="hero" src="{base}art/{images[entity.ref]}" '
            f'alt="{html.escape(entity.name)}" loading="lazy">'
        )

    # Secret blocks this viewer may read are shown, marked, so nobody repeats
    # them at the table by accident.
    for segment in secrets_mod.parse(entity.body):
        if segment.audience is None:
            parts.append(_markdown(segment.text))
        elif viewer & segment.audience:
            who = ", ".join(sorted(segment.audience))
            parts.append(
                f'<div class="secret"><span class="who">secret · {html.escape(who)}'
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

    link_list(entity.links, "Related")
    link_list(
        [e.ref for e in library.backlinks(entity.ref) if e.ref not in entity.links],
        "Mentioned by",
    )

    if entity.tags:
        parts.append(
            '<div class="tags">'
            + "".join(f'<span class="tag">{html.escape(t)}</span>' for t in entity.tags)
            + "</div>"
        )

    meta = []
    data = {k: v for k, v in entity.data.items()
            if k != "visible_to" and v not in (None, "", [], {})}
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
        img = (f'<img src="{base}art/{images[e.ref]}" alt="" loading="lazy">'
               if e.ref in images else "")
        out.append(
            f'<div class="card">{img}<div class="body">'
            f'<a href="{base}{page_url(e.ref)}">{html.escape(e.name)}</a>'
            f"<p>{html.escape(e.summary[:90])}</p></div></div>"
        )
    return f'<div class="grid">{"".join(out)}</div>'


def render_index(entities: list[Entity], images: dict[str, str], base: str) -> str:
    by_kind: dict[str, list[Entity]] = defaultdict(list)
    for e in entities:
        by_kind[e.kind].append(e)

    parts = [
        "<h1>Copper Vale</h1>",
        '<p class="summary">A low-lying landscape where scattered civilization '
        "clings to dwindling natural resources.</p>",
    ]
    places = [e for e in by_kind.get("place", [])
              if e.data.get("map_type") in {"region", "settlement"}]
    if places:
        parts += ["<h2>Where</h2>", _cards(places, images, base)]
    pcs = [e for e in by_kind.get("character", []) if "player-character" in e.tags]
    if pcs:
        parts += ["<h2>The Party</h2>", _cards(pcs, images, base)]
    gone = [e for e in by_kind.get("character", [])
            if "former-party-member" in e.tags or "deceased" in e.tags]
    if gone:
        parts += ["<h2>Gone</h2>", _cards(gone, images, base)]
    if by_kind.get("faction"):
        parts += ["<h2>Factions</h2>", _cards(by_kind["faction"], images, base)]
    parts.append(f'<p class="meta">{len(entities)} pages.</p>')
    return "\n".join(parts)


def render_kind_index(kind: str, items: list[Entity], images: dict[str, str],
                      base: str) -> str:
    label = KIND_LABEL.get(kind, kind.capitalize())
    return (f"<h1>{label}</h1><p class=\"summary\">{len(items)} pages.</p>"
            + _cards(items, images, base))


def search_index(entities: list[Entity], viewer: frozenset[str]) -> str:
    """Client-side index containing only text this viewer may read."""
    return json.dumps(
        [
            {
                "n": e.name,
                "k": KIND_LABEL.get(e.kind, e.kind).rstrip("s"),
                "s": e.summary[:120],
                "u": page_url(e.ref),
                "h": " ".join(
                    [e.name, e.summary, secrets_mod.redact(e.body, viewer),
                     " ".join(e.tags)]
                ).lower(),
            }
            for e in entities
        ],
        ensure_ascii=False,
    )


def visible_to(entities: list[Entity], viewer: frozenset[str]) -> list[Entity]:
    out = []
    for entity in entities:
        allowed = entity.data.get("visible_to")
        if not allowed:
            out.append(entity)
            continue
        if isinstance(allowed, str):
            allowed = [allowed]
        if viewer & {str(a).strip().lower() for a in allowed}:
            out.append(entity)
    return out
