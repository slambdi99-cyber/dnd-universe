"""Export the universe as an Obsidian vault you can actually sit and read.

The content folder is the source of truth, but it isn't browsable: links live
in frontmatter as `place/copper-vale`, and the art isn't referenced from the
markdown at all. This produces a vault where the links are real `[[wikilinks]]`,
the art is embedded, and Obsidian's graph and backlinks work.

    python tools\\export_obsidian.py
    python tools\\export_obsidian.py --out "C:\\path\\to\\vault" --no-images

Then in Obsidian: Open folder as vault, point it at the output.

## One-way, on purpose

This vault is generated. Edits made inside it are overwritten on the next
export, so treat it as a reading copy. Write through `content/`, the CLI, or
the MCP server instead.

It only removes files it created previously, tracked in `.export-manifest.json`,
so anything you add to the vault yourself survives.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from universe import config as config_mod  # noqa: E402
from universe import people as people_mod  # noqa: E402
from universe import secrets as secrets_mod  # noqa: E402
from universe.entities import Entity, Library  # noqa: E402

# Set from --as. Empty means "public only": no secrets for anyone.
VIEWER: frozenset[str] = frozenset()

MANIFEST = ".export-manifest.json"

# Folder per kind. Obsidian resolves [[links]] by name across folders, so this
# is purely for browsing comfort.
FOLDERS = {
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

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str) -> str:
    cleaned = _ILLEGAL.sub("", name).strip().rstrip(".")
    return cleaned or "Untitled"


def build_titles(entities: list[Entity]) -> dict[str, str]:
    """Map each entity ref to a unique vault page title.

    Display names are not unique: Bogwatchers' Sanctum is both a faction (the
    order) and a place (the building). Obsidian resolves [[links]] by filename,
    so duplicates would silently point at whichever it found first. Collisions
    get their kind appended.
    """
    counts = Counter(e.name for e in entities)
    titles: dict[str, str] = {}
    for entity in entities:
        title = entity.name
        if counts[entity.name] > 1:
            title = f"{entity.name} ({entity.kind.capitalize()})"
        titles[entity.ref] = safe_filename(title)
    return titles


def render_page(
    entity: Entity,
    titles: dict[str, str],
    library: Library,
    images: dict[str, str],
) -> str:
    front: dict = {"kind": entity.kind}
    if entity.summary:
        front["summary"] = entity.summary
    if entity.appearance:
        front["appearance"] = entity.appearance
    if entity.tags:
        front["tags"] = entity.tags
    # Alias on the slug so [[copper-vale]] resolves as well as [[Copper Vale]].
    aliases = [entity.slug]
    if titles[entity.ref] != entity.name:
        aliases.append(entity.name)
    front["aliases"] = aliases
    if entity.data:
        front.update({k: v for k, v in entity.data.items() if v not in (None, "")})
    if entity.sources:
        front["sources"] = entity.sources

    parts = [
        "---",
        yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip(),
        "---",
        "",
        f"# {entity.name}",
        "",
    ]

    art = images.get(entity.ref)
    if art:
        parts += [f"![[{art}]]", ""]

    if entity.summary:
        parts += [f"*{entity.summary}*", ""]

    body = secrets_mod.redact(entity.body, VIEWER) if VIEWER \
        else secrets_mod.strip_all(entity.body)
    if body:
        parts += [body, ""]

    # Outgoing links as real wikilinks.
    resolved = [titles[ref] for ref in entity.links if ref in titles]
    if resolved:
        parts += ["## Related", ""]
        parts += [f"- [[{t}]]" for t in sorted(set(resolved))]
        parts.append("")

    # Backlinks are automatic in Obsidian's sidebar, but spelling them out
    # makes the page readable outside Obsidian too.
    back = [titles[e.ref] for e in library.backlinks(entity.ref) if e.ref in titles]
    back = sorted(set(back) - set(resolved))
    if back:
        parts += ["## Mentioned by", ""]
        parts += [f"- [[{t}]]" for t in back]
        parts.append("")

    if entity.appearance:
        parts += ["---", "", f"*Depicted as: {entity.appearance}*", ""]

    return "\n".join(parts)


def render_index(entities: list[Entity], titles: dict[str, str]) -> str:
    by_kind: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        by_kind[entity.kind].append(entity)

    parts = [
        "---",
        "kind: index",
        "---",
        "",
        "# The Buried Star",
        "",
        "*The DM's campaign, set in Copper Vale: a low-lying landscape where "
        "scattered civilization clings to dwindling natural resources.*",
        "",
        f"{len(entities)} pages. Generated from the campaign archive; see "
        "`content/` for the source of truth.",
        "",
    ]

    # Lead with the places people actually care about.
    highlights = [
        e for e in by_kind.get("place", [])
        if e.data.get("map_type") in {"region", "settlement"}
    ]
    if highlights:
        parts += ["## Where", ""]
        parts += [f"- [[{titles[e.ref]}]] — {e.summary}" for e in
                  sorted(highlights, key=lambda e: e.name)]
        parts.append("")

    pcs = [e for e in by_kind.get("character", []) if "player-character" in e.tags]
    if pcs:
        parts += ["## The Party", ""]
        parts += [f"- [[{titles[e.ref]}]] — {e.summary}" for e in
                  sorted(pcs, key=lambda e: e.name)]
        parts.append("")

    former = [e for e in by_kind.get("character", [])
              if "former-party-member" in e.tags or "deceased" in e.tags]
    if former:
        parts += ["## Gone", ""]
        parts += [f"- [[{titles[e.ref]}]] — {e.summary}" for e in
                  sorted(former, key=lambda e: e.name)]
        parts.append("")

    for kind in sorted(by_kind):
        label = FOLDERS.get(kind, kind.capitalize())
        parts += [f"## All {label}", ""]
        parts += [f"- [[{titles[e.ref]}]]" for e in
                  sorted(by_kind[kind], key=lambda e: e.name)]
        parts.append("")

    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="Vault folder (default: <project>/vault)")
    ap.add_argument("--no-images", action="store_true", help="Skip copying art")
    ap.add_argument(
        "--as", dest="as_person", metavar="KEY",
        help="Include the secrets this person may read, e.g. --as dm. "
             "Without it the vault contains no secrets at all.",
    )
    args = ap.parse_args()

    cfg = config_mod.load()
    library = Library(cfg.content_dir)

    global VIEWER
    viewer_name = "public only"
    if args.as_person:
        registry = people_mod.load(cfg.root)
        person = registry.members.get(args.as_person.strip().lower())
        if person is None:
            print(f"No person with key {args.as_person!r} in people.yaml.",
                  file=sys.stderr)
            return 1
        VIEWER = person.identities
        viewer_name = person.name

    everything = sorted(library.all(), key=lambda e: (e.kind, e.name))
    entities = [
        e for e in everything
        if not e.data.get("visible_to")
        or (VIEWER & {str(v).lower() for v in e.data["visible_to"]})
    ]
    hidden = {e.ref for e in everything} - {e.ref for e in entities}
    for entity in entities:
        entity.links = [r for r in entity.links if r not in hidden]

    if not entities:
        print("No content to export.", file=sys.stderr)
        return 1
    print(f"Exporting as: {viewer_name}"
          + (f"  ({len(hidden)} restricted page(s) excluded)" if hidden else ""))

    vault = Path(args.out) if args.out else cfg.root / "vault"
    vault.mkdir(parents=True, exist_ok=True)

    # Only ever delete what a previous export created.
    manifest_path = vault / MANIFEST
    previous = set()
    if manifest_path.exists():
        try:
            previous = set(json.loads(manifest_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass

    titles = build_titles(entities)
    written: set[str] = set()

    # --- art -------------------------------------------------------------
    images: dict[str, str] = {}
    if not args.no_images:
        attachments = vault / "Attachments"
        attachments.mkdir(exist_ok=True)
        store = cfg.assets_dir
        for entity in entities:
            if not entity.art:
                continue
            # Last entry is the most recent render.
            asset_id = entity.art[-1]
            kind, slug, name = asset_id.split("/", 2)
            src = store / kind / slug / f"{name}.png"
            if not src.exists():
                continue
            dest_name = f"{safe_filename(titles[entity.ref])}.png"
            shutil.copy2(src, attachments / dest_name)
            images[entity.ref] = dest_name
            written.add(str(Path("Attachments") / dest_name))

    # --- pages -----------------------------------------------------------
    for entity in entities:
        folder = vault / FOLDERS.get(entity.kind, entity.kind.capitalize())
        folder.mkdir(exist_ok=True)
        rel = Path(folder.name) / f"{titles[entity.ref]}.md"
        (vault / rel).write_text(
            render_page(entity, titles, library, images), encoding="utf-8"
        )
        written.add(str(rel))

    # Deliberately not named after anything in the world. An index called
    # "Copper Vale" would collide with the region's own page, and Obsidian
    # resolves [[links]] by filename, so every [[Copper Vale]] in the vault
    # would become ambiguous.
    index_rel = "Start Here.md"
    (vault / index_rel).write_text(render_index(entities, titles), encoding="utf-8")
    written.add(index_rel)

    # Nothing else may share a page name either, for the same reason.
    stems = Counter(Path(p).stem for p in written if p.endswith(".md"))
    clashes = [name for name, n in stems.items() if n > 1]
    if clashes:
        print(
            f"WARNING: {len(clashes)} duplicate page name(s), so wikilinks to "
            f"them are ambiguous in Obsidian: {', '.join(sorted(clashes))}",
            file=sys.stderr,
        )

    # --- clean up pages from previous exports that no longer exist --------
    removed = 0
    for stale in sorted(previous - written):
        path = vault / stale
        if path.exists():
            path.unlink()
            removed += 1

    manifest_path.write_text(json.dumps(sorted(written), indent=2), encoding="utf-8")

    counts = Counter(e.kind for e in entities)
    print(f"Exported {len(entities)} pages to {vault}")
    for kind, n in sorted(counts.items()):
        print(f"  {n:>3}  {FOLDERS.get(kind, kind)}")
    if images:
        print(f"  {len(images):>3}  images embedded")
    if removed:
        print(f"  {removed:>3}  stale page(s) removed")
    print("\nIn Obsidian: Open folder as vault, and pick that folder.")
    print("Open 'Start Here'. Ctrl+G opens the graph.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
