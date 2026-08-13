"""Delete generated art that no entity points at any more.

Renaming an entity or rewriting its appearance changes the prompt hash, so the
old image stays on disk unreferenced. Harmless but it accumulates, and after a
big correction pass it's most of the folder.

    python tools\\prune_assets.py --dry-run
    python tools\\prune_assets.py

Only touches files under assets/. Content is never modified.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe.entities import Library  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = config_mod.load()
    library = Library(cfg.content_dir)
    assets = Path(cfg.assets_dir)
    if not assets.exists():
        print("No assets folder.")
        return 0

    keep = {a for e in library.all() for a in e.art}
    removed = freed = 0

    for png in sorted(assets.rglob("*.png")):
        # assets/<kind>/<slug>/<variant>-<hash>.png -> "<kind>/<slug>/<name>"
        asset_id = f"{png.parent.parent.name}/{png.parent.name}/{png.stem}"
        if asset_id in keep:
            continue
        freed += png.stat().st_size
        print(f"{'would remove' if args.dry_run else 'removed'}  {asset_id}")
        if not args.dry_run:
            png.unlink()
            png.with_suffix(".json").unlink(missing_ok=True)
        removed += 1

    # Clear out folders left empty by renames.
    if not args.dry_run:
        for folder in sorted(assets.rglob("*"), reverse=True):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()

    kept = list(assets.rglob("*.png"))
    print(
        f"\n{removed} pruned ({freed / 1024 / 1024:.1f} MB), "
        f"{len(kept)} kept ({sum(f.stat().st_size for f in kept) / 1024 / 1024:.1f} MB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
