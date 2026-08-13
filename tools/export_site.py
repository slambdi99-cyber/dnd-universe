"""Export the universe as a static website.

Produces a self-contained `site/` folder: one page per entity, an index, the
art, and a client-side search index. No server-side code, no build step, no
JavaScript framework. `mcp_server.py --wiki site` serves it, so the whole table
reads the world from a link instead of installing Obsidian.

    python tools\\export_site.py

Re-run after changing content. The folder is rewritten each time.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import markdown as md  # noqa: E402

from universe import config as config_mod  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

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
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.65 Georgia, 'Iowan Old Style', 'Palatino Linotype', serif;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
header.top {
  position: sticky; top: 0; z-index: 10; background: var(--panel);
  border-bottom: 1px solid var(--line); padding: .7rem 1.2rem;
  display: flex; gap: 1rem; align-items: center; flex-wrap: wrap;
}
header.top .home { font-weight: bold; letter-spacing: .02em; }
header.top nav { display: flex; gap: .8rem; flex-wrap: wrap; font-size: .85rem; }
#q {
  margin-left: auto; padding: .4rem .7rem; min-width: 14rem; flex: 1 1 12rem;
  border: 1px solid var(--line); border-radius: 4px;
  background: var(--bg); color: var(--ink); font: inherit; font-size: .9rem;
}
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
blockquote {
  margin: 1rem 0; padding: .5rem 1rem; border-left: 3px solid var(--accent);
  background: var(--accent-soft); color: var(--ink);
}
blockquote p { margin: .3rem 0; }
ul.links { list-style: none; padding: 0; display: flex; flex-wrap: wrap; gap: .5rem; }
ul.links li a {
  display: inline-block; padding: .25rem .6rem; border: 1px solid var(--line);
  border-radius: 999px; background: var(--panel); font-size: .85rem;
}
.tags { margin: 1rem 0 0; }
.tag {
  display: inline-block; font-size: .72rem; text-transform: uppercase;
  letter-spacing: .06em; color: var(--muted); border: 1px solid var(--line);
  border-radius: 3px; padding: .1rem .4rem; margin: 0 .3rem .3rem 0;
}
.meta { font-size: .8rem; color: var(--muted); margin-top: 2.5rem;
        border-top: 1px solid var(--line); padding-top: .8rem; }
.meta code { font-size: .75rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr));
        gap: 1rem; margin: 1rem 0 2rem; }
.card {
  border: 1px solid var(--line); border-radius: 6px; overflow: hidden;
  background: var(--panel);
}
.card img { width: 100%; aspect-ratio: 1/1; object-fit: cover; display: block; }
.card .body { padding: .6rem .7rem; }
.card .body a { font-weight: bold; }
.card .body p { margin: .2rem 0 0; font-size: .8rem; color: var(--muted); }
#results { margin: 1rem 0; }
#results .hit { padding: .5rem 0; border-bottom: 1px solid var(--line); }
#results .hit p { margin: .1rem 0 0; font-size: .85rem; color: var(--muted); }
.empty { color: var(--muted); font-style: italic; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .9rem; }
th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid var(--line); }
"""

SEARCH_JS = """
const idx = window.__INDEX__ || [];
const q = document.getElementById('q');
const results = document.getElementById('results');
const page = document.getElementById('page');
function render(term) {
  const t = term.trim().toLowerCase();
  if (!t) { results.innerHTML = ''; results.hidden = true;
            if (page) page.hidden = false; return; }
  const hits = idx.filter(e => e.h.includes(t)).slice(0, 40);
  results.hidden = false;
  if (page) page.hidden = true;
  results.innerHTML = hits.length
    ? '<h2>' + hits.length + ' result' + (hits.length===1?'':'s') + '</h2>' +
      hits.map(e => '<div class="hit"><a href="' + BASE + e.u + '">' + e.n +
        '</a> <span class="kind">' + e.k + '</span><p>' + e.s + '</p></div>').join('')
    : '<p class="empty">Nothing matches that.</p>';
}
q.addEventListener('input', () => render(q.value));
q.addEventListener('keydown', e => { if (e.key === 'Escape') { q.value=''; render(''); } });
"""


def slug_to_url(ref: str) -> str:
    kind, slug = ref.split("/", 1)
    return f"{kind}/{slug}.html"


def shell(title: str, base: str, body: str, index_json: str) -> str:
    nav = "".join(
        f'<a href="{base}{kind}/index.html">{label}</a>'
        for kind, label in KIND_LABEL.items()
    )
    # The index is already called Copper Vale; don't suffix it with itself.
    full_title = title if title == "Copper Vale" else f"{title} — Copper Vale"
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<style>{CSS}</style>
</head><body>
<header class="top">
  <a class="home" href="{base}index.html">Copper Vale</a>
  <nav>{nav}</nav>
  <input id="q" type="search" placeholder="Search the world..." autocomplete="off">
</header>
<main>
  <div id="results" hidden></div>
  <div id="page">{body}</div>
</main>
<script>const BASE={json.dumps(base)};window.__INDEX__={index_json};{SEARCH_JS}</script>
</body></html>
"""


def render_body(entity: Entity, library: Library, images: dict[str, str],
                base: str) -> str:
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
    if entity.body.strip():
        parts.append(md.markdown(entity.body, extensions=["tables", "nl2br"]))

    def link_list(refs, heading):
        items = []
        for ref in sorted(set(refs)):
            target = library.load(*ref.split("/", 1))
            if target:
                items.append(
                    f'<li><a href="{base}{slug_to_url(ref)}">'
                    f"{html.escape(target.name)}</a></li>"
                )
        if items:
            parts.append(f"<h2>{heading}</h2>")
            parts.append(f'<ul class="links">{"".join(items)}</ul>')

    link_list(entity.links, "Related")
    back = [e.ref for e in library.backlinks(entity.ref) if e.ref not in entity.links]
    link_list(back, "Mentioned by")

    if entity.tags:
        parts.append(
            '<div class="tags">'
            + "".join(f'<span class="tag">{html.escape(t)}</span>' for t in entity.tags)
            + "</div>"
        )

    meta = []
    if entity.data:
        rows = "".join(
            f"<tr><th>{html.escape(str(k).replace('_',' '))}</th>"
            f"<td>{html.escape(str(v))}</td></tr>"
            for k, v in entity.data.items() if v not in (None, "", [], {})
        )
        if rows:
            meta.append(f"<table>{rows}</table>")
    if entity.sources:
        srcs = ", ".join(f"<code>{html.escape(s)}</code>" for s in entity.sources)
        meta.append(f"<p>Sources: {srcs}</p>")
    if meta:
        parts.append(f'<div class="meta">{"".join(meta)}</div>')

    return "\n".join(parts)


def render_index(entities: list[Entity], images: dict[str, str], base: str) -> str:
    by_kind: dict[str, list[Entity]] = defaultdict(list)
    for e in entities:
        by_kind[e.kind].append(e)

    def cards(items):
        out = []
        for e in sorted(items, key=lambda e: e.name):
            img = (
                f'<img src="{base}art/{images[e.ref]}" alt="" loading="lazy">'
                if e.ref in images else ""
            )
            out.append(
                f'<div class="card">{img}<div class="body">'
                f'<a href="{base}{slug_to_url(e.ref)}">{html.escape(e.name)}</a>'
                f"<p>{html.escape(e.summary[:90])}</p></div></div>"
            )
        return f'<div class="grid">{"".join(out)}</div>'

    parts = [
        "<h1>Copper Vale</h1>",
        '<p class="summary">A low-lying landscape where scattered civilization '
        "clings to dwindling natural resources.</p>",
    ]

    places = [e for e in by_kind.get("place", [])
              if e.data.get("map_type") in {"region", "settlement"}]
    if places:
        parts += ["<h2>Where</h2>", cards(places)]

    pcs = [e for e in by_kind.get("character", []) if "player-character" in e.tags]
    if pcs:
        parts += ["<h2>The Party</h2>", cards(pcs)]

    gone = [e for e in by_kind.get("character", [])
            if "former-party-member" in e.tags or "deceased" in e.tags]
    if gone:
        parts += ["<h2>Gone</h2>", cards(gone)]

    if by_kind.get("faction"):
        parts += ["<h2>Factions</h2>", cards(by_kind["faction"])]

    parts.append(
        f'<p class="meta">{len(entities)} pages. '
        f"Generated from the campaign archive.</p>"
    )
    return "\n".join(parts)


def render_kind_index(kind: str, items: list[Entity], images: dict[str, str],
                      base: str) -> str:
    label = KIND_LABEL.get(kind, kind.capitalize())
    out = []
    for e in sorted(items, key=lambda e: e.name):
        img = (f'<img src="{base}art/{images[e.ref]}" alt="" loading="lazy">'
               if e.ref in images else "")
        out.append(
            f'<div class="card">{img}<div class="body">'
            f'<a href="{base}{slug_to_url(e.ref)}">{html.escape(e.name)}</a>'
            f"<p>{html.escape(e.summary[:90])}</p></div></div>"
        )
    return (f"<h1>{label}</h1><p class=\"summary\">{len(items)} pages.</p>"
            f'<div class="grid">{"".join(out)}</div>')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", help="Output folder (default: <project>/site)")
    args = ap.parse_args()

    cfg = config_mod.load()
    library = Library(cfg.content_dir)
    entities = sorted(library.all(), key=lambda e: (e.kind, e.name))
    if not entities:
        print("No content to export.", file=sys.stderr)
        return 1

    site = Path(args.out) if args.out else cfg.root / "site"
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)

    # --- art -------------------------------------------------------------
    art_dir = site / "art"
    art_dir.mkdir()
    images: dict[str, str] = {}
    for entity in entities:
        if not entity.art:
            continue
        kind, slug, name = entity.art[-1].split("/", 2)
        src = cfg.assets_dir / kind / slug / f"{name}.png"
        if src.exists():
            dest = f"{kind}-{slug}.png"
            shutil.copy2(src, art_dir / dest)
            images[entity.ref] = dest

    # --- search index ----------------------------------------------------
    index = [
        {
            "n": e.name,
            "k": KIND_LABEL.get(e.kind, e.kind).rstrip("s"),
            "s": e.summary[:120],
            "u": slug_to_url(e.ref),
            # One lowercase haystack; the client does a simple substring match,
            # which is plenty for 84 pages and needs no dependencies.
            "h": " ".join(
                [e.name, e.summary, e.body, " ".join(e.tags)]
            ).lower(),
        }
        for e in entities
    ]
    index_json = json.dumps(index, ensure_ascii=False)

    # --- pages -----------------------------------------------------------
    by_kind: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        by_kind[entity.kind].append(entity)
        folder = site / entity.kind
        folder.mkdir(exist_ok=True)
        (folder / f"{entity.slug}.html").write_text(
            shell(entity.name, "../",
                  render_body(entity, library, images, "../"), index_json),
            encoding="utf-8",
        )

    for kind, items in by_kind.items():
        (site / kind / "index.html").write_text(
            shell(KIND_LABEL.get(kind, kind), "../",
                  render_kind_index(kind, items, images, "../"), index_json),
            encoding="utf-8",
        )

    (site / "index.html").write_text(
        shell("Copper Vale", "", render_index(entities, images, ""), index_json),
        encoding="utf-8",
    )

    counts = Counter(e.kind for e in entities)
    size = sum(f.stat().st_size for f in site.rglob("*") if f.is_file()) / 1024 / 1024
    print(f"Exported {len(entities)} pages to {site}  ({size:.0f} MB)")
    for kind, n in sorted(counts.items()):
        print(f"  {n:>3}  {KIND_LABEL.get(kind, kind)}")
    print(f"  {len(images):>3}  images")
    print("\nServe it with:")
    print("  python mcp_server.py --http --wiki site --allowed-host <your-host>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
