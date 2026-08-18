"""Build every thumbnail now, so nobody waits for one later.

Thumbnails are made on demand and kept, which is right for a picture someone
has just uploaded and wrong for the first person to open the site after a
deploy: they wait while thirty images are shrunk, one after another, before
any of them arrive. Running this as the last step of a deploy moves that work
off the visitor and onto the deploy.

    python tools/warm_thumbs.py
    python tools/warm_thumbs.py --rebuild    # after changing sizes or quality

Safe to run repeatedly and safe to interrupt: anything already current is
skipped, and anything missing is simply made on the next request.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe import thumbs  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rebuild", action="store_true",
                    help="Delete the existing thumbnails first")
    args = ap.parse_args()

    cfg = config_mod.load()
    roots = [Path(cfg.assets_dir), Path(cfg.files_dir)]

    if args.rebuild:
        gone = sum(thumbs.sweep(r) for r in roots if r.exists())
        print(f"Removed {gone} existing thumbnail(s).")

    started = time.perf_counter()
    made = 0
    for root in roots:
        if not root.exists():
            continue
        found = len(list(thumbs.originals(root)))
        if not found:
            continue
        built = thumbs.warm(root)
        made += built
        print(f"{root}: {found} image(s), {built} thumbnail(s) built")

    elapsed = time.perf_counter() - started
    print(f"\nBuilt {made} thumbnail(s) in {elapsed:.1f}s."
          if made else "\nEverything was already built.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
