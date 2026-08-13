"""Export the universe as a static website.

Produces a self-contained `site/` folder: one page per entity, an index, the
art, and a client-side search index. No server-side code, no build step, no
JavaScript framework.

    python tools\\export_site.py

**The static site never contains a secret.** Every secret block is stripped
regardless of audience, and restricted pages are omitted along with any link
pointing at them, because a file cannot know who is reading it.

If you want per-person views, serve the wiki live instead:

    python mcp_server.py --http --wiki-live --allowed-host <host>

Re-run this after changing content; the folder is rewritten each time.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe import site as site_mod
from universe import tooltips as tooltips_mod  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

PUBLIC: frozenset[str] = frozenset()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", help="Output folder (default: <project>/site)")
    args = ap.parse_args()

    cfg = config_mod.load()
    library = Library(cfg.content_dir)
    everything = sorted(library.all(), key=lambda e: (e.kind, e.name))
    entities = site_mod.visible_to(everything, PUBLIC)
    restricted = {e.ref for e in everything} - {e.ref for e in entities}
    if not entities:
        print("No content to export.", file=sys.stderr)
        return 1

    allowed = {e.ref for e in entities}

    site = Path(args.out) if args.out else cfg.root / "site"
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)

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

    index_json = site_mod.search_index(entities, PUBLIC)

    # One shared script so browsers cache it across every page.
    (site / "tooltips.js").write_text(
        f"window.__TIPS__={tooltips_mod.build(entities, PUBLIC, cfg.root, '')};\n"
        + tooltips_mod.TOOLTIP_JS,
        encoding="utf-8",
    )

    by_kind: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        by_kind[entity.kind].append(entity)
        folder = site / entity.kind
        folder.mkdir(exist_ok=True)
        (folder / f"{entity.slug}.html").write_text(
            site_mod.shell(
                entity.name, "../",
                site_mod.render_body(entity, library, images, "../", PUBLIC, allowed),
                index_json, tips=True,
            ),
            encoding="utf-8",
        )

    for kind, items in by_kind.items():
        (site / kind / "index.html").write_text(
            site_mod.shell(
                site_mod.KIND_LABEL.get(kind, kind), "../",
                site_mod.render_kind_index(kind, items, images, "../"), index_json,
            ),
            encoding="utf-8",
        )

    (site / "index.html").write_text(
        site_mod.shell(site_mod.SITE_NAME, "",
                       site_mod.render_index(entities, images, ""), index_json,
                       tips=True),
        encoding="utf-8",
    )

    guide_src = cfg.root / "GUIDE.md"
    if guide_src.exists():
        (site / "guide.html").write_text(
            site_mod.shell("Guide", "",
                           site_mod.render_guide(
                               guide_src.read_text(encoding="utf-8")),
                           index_json),
            encoding="utf-8",
        )

    counts = Counter(e.kind for e in entities)
    size = sum(f.stat().st_size for f in site.rglob("*") if f.is_file()) / 1024 / 1024
    print(f"Exported {len(entities)} pages to {site}  ({size:.0f} MB)")
    for kind, n in sorted(counts.items()):
        print(f"  {n:>3}  {site_mod.KIND_LABEL.get(kind, kind)}")
    print(f"  {len(images):>3}  images")
    if restricted:
        print(f"  {len(restricted):>3}  restricted page(s) excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
