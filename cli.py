"""Command line for the universe toolchain.

    python cli.py import-map world.json [--dry-run]
    python cli.py new place "The Drowned Lantern" --appearance "..."
    python cli.py art the-drowned-lantern [--variant interior] [--all] [--dry-run]
    python cli.py ls [place] [--tag settlement]
    python cli.py show the-drowned-lantern
    python cli.py check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from universe import config as config_mod
from universe.assets import AssetStore
from universe.entities import Entity, Library, slugify
from universe.worldmap import azgaar


def _library(cfg) -> Library:
    return Library(cfg.content_dir)


def _find(library: Library, slug: str) -> Entity | None:
    for entity in library.all():
        if entity.slug == slug:
            return entity
    return None


def cmd_import_map(args, cfg) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"No such file: {path}", file=sys.stderr)
        return 1

    report = azgaar.import_map(path, _library(cfg), dry_run=args.dry_run)
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if args.dry_run:
        print(f"Dry run. Would import {report.created} entities.")
        for kind, count in sorted(report.by_kind.items()):
            print(f"  {count:>5}  {kind}")
        print("\nNothing was written. Drop --dry-run to import.")
    else:
        print(report.summary())
        print(f"\nWritten to {cfg.content_dir}")
    return 0


def cmd_new(args, cfg) -> int:
    library = _library(cfg)
    slug = args.slug or slugify(args.name)
    if library.exists(args.kind, slug):
        print(f"{args.kind}/{slug} already exists.", file=sys.stderr)
        return 1

    entity = Entity(
        kind=args.kind,
        slug=slug,
        name=args.name,
        summary=args.summary or "",
        appearance=args.appearance or "",
        tags=args.tag or [],
        links=args.link or [],
    )
    path = library.save(entity)
    print(f"Created {path}")
    return 0


def cmd_art(args, cfg) -> int:
    from universe.art import ArtService

    library = _library(cfg)
    store = AssetStore(cfg.assets_dir)
    service = ArtService(cfg, library, store, house_style=args.style)

    if args.all:
        targets = list(library.all(args.kind))
    else:
        entity = _find(library, args.slug)
        if entity is None:
            print(f"No entity with slug '{args.slug}'.", file=sys.stderr)
            return 1
        targets = [entity]

    if not targets:
        print("Nothing to draw.")
        return 0

    missing_appearance = [e.name for e in targets if not e.appearance.strip()]
    if missing_appearance:
        preview = ", ".join(missing_appearance[:5])
        more = f" and {len(missing_appearance) - 5} more" if len(missing_appearance) > 5 else ""
        print(
            f"note: no appearance written for {preview}{more}.\n"
            f"      They'll be drawn from name and summary, which is much "
            f"vaguer. Add an `appearance:` line for better results.\n",
            file=sys.stderr,
        )

    for entity in targets:
        result = service.generate(
            entity, args.variant, force=args.force, dry_run=args.dry_run
        )
        if args.dry_run:
            print(f"{entity.name}\n  {result.spec.prompt}\n  seed {result.spec.seed}\n")
        elif result.generated:
            print(f"drew   {entity.name} -> {result.path}")
        else:
            print(f"cached {entity.name} -> {result.path}")

    if args.dry_run:
        print(f"{len(targets)} prompt(s). Nothing generated.")
    return 0


def cmd_ls(args, cfg) -> int:
    library = _library(cfg)
    rows = []
    for entity in library.all(args.kind):
        if args.tag and args.tag not in entity.tags:
            continue
        rows.append(entity)

    if not rows:
        print("Nothing found.")
        return 0

    width = max(len(e.name) for e in rows)
    for entity in rows:
        art = f"  [{len(entity.art)} art]" if entity.art else ""
        print(f"{entity.name:<{width}}  {entity.kind:<10} {entity.slug}{art}")
    print(f"\n{len(rows)} entities")
    return 0


def cmd_show(args, cfg) -> int:
    library = _library(cfg)
    entity = _find(library, args.slug)
    if entity is None:
        print(f"No entity with slug '{args.slug}'.", file=sys.stderr)
        return 1

    print(entity.render())
    back = library.backlinks(entity.ref)
    if back:
        print(f"Linked from: {', '.join(e.name for e in back)}")
    return 0


def cmd_check(args, cfg) -> int:
    """Look for the things that quietly rot in a shared wiki."""
    library = _library(cfg)
    entities = list(library.all())
    refs = {e.ref for e in entities}

    broken: list[tuple[str, str]] = []
    orphans: list[str] = []
    no_art: list[str] = []

    for entity in entities:
        for link in entity.links:
            if link not in refs:
                broken.append((entity.ref, link))
        if not entity.links and not library.backlinks(entity.ref):
            orphans.append(entity.name)
        if not entity.art:
            no_art.append(entity.name)

    print(f"{len(entities)} entities")
    if broken:
        print(f"\n{len(broken)} broken link(s):")
        for source, target in broken[:20]:
            print(f"  {source} -> {target}")
    if orphans:
        print(f"\n{len(orphans)} unlinked entities (nothing points at them):")
        print("  " + ", ".join(orphans[:20]))
    if no_art:
        print(f"\n{len(no_art)} without art")
    if not broken and not orphans:
        print("No broken links, nothing orphaned.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cli.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import-map", help="Import an Azgaar JSON export")
    p.add_argument("path")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_import_map)

    p = sub.add_parser("new", help="Create an entity")
    p.add_argument("kind")
    p.add_argument("name")
    p.add_argument("--slug")
    p.add_argument("--summary")
    p.add_argument("--appearance")
    p.add_argument("--tag", action="append")
    p.add_argument("--link", action="append")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("art", help="Generate art for entities")
    p.add_argument("slug", nargs="?")
    p.add_argument("--all", action="store_true", help="Every entity")
    p.add_argument("--kind", help="Limit --all to one kind")
    p.add_argument("--variant", default="default")
    p.add_argument(
        "--style",
        help="Override house_style for this run, for A/B testing a look. "
        "Seeds are unchanged, so composition stays fixed and only the "
        "rendering differs.",
    )
    p.add_argument("--force", action="store_true", help="Regenerate even if cached")
    p.add_argument("--dry-run", action="store_true", help="Print prompts only")
    p.set_defaults(func=cmd_art)

    p = sub.add_parser("ls", help="List entities")
    p.add_argument("kind", nargs="?")
    p.add_argument("--tag")
    p.set_defaults(func=cmd_ls)

    p = sub.add_parser("show", help="Print one entity")
    p.add_argument("slug")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("check", help="Find broken links and orphans")
    p.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv[1:])
    if args.command == "art" and not args.all and not args.slug:
        print("Give a slug, or --all.", file=sys.stderr)
        return 1
    cfg = config_mod.load()
    return args.func(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
