"""Shrink the art store, treating regenerable and irreplaceable differently.

    python tools\\compress_art.py              # show what it would do
    python tools\\compress_art.py --apply      # do it
    python tools\\compress_art.py --apply --all-lossless

192MB of PNGs, most of them SDXL output at 1024px and a few of them multi-
megabyte scans somebody uploaded. Measured on this store:

    PNG re-compression   98% of original   not worth the run
    WEBP lossless        69%               nothing lost
    WEBP quality 90      15%               no visible difference
    WEBP quality 82      10%               starts to show

The 6x saving is lossy, and lossy is a different decision depending on where
the picture came from:

  * **Generated art** can be made again. Its sidecar records the prompt, the
    seed, the model, the size and the steps, so the worst case of compressing
    it too hard is an afternoon of GPU time. It gets quality 90.

  * **Uploads** cannot. The city map Sam drew, the party portrait, a scan of
    someone's character sheet: there is one copy and this is it. They get
    lossless WEBP, which still saves about a third and throws nothing away.

`--all-lossless` applies the careful treatment to everything, for anyone who
would rather have the disk space than the certainty.

Asset ids carry no extension, so nothing in `content/` refers to the format
and no page needs rewriting. The originals are deleted only after the
replacement is written and verified as readable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402

# An uploaded file is named `upload-<hash>`; everything else came from the
# generator. That naming is set in universe/uploads.py.
UPLOAD_PREFIX = "upload-"
LOSSY_QUALITY = 90


def convert(path: Path, lossless: bool, quality: int) -> tuple[int, int] | None:
    """Write a WEBP beside a PNG and remove the PNG. Returns (before, after)."""
    from PIL import Image

    target = path.with_suffix(".webp")
    before = path.stat().st_size
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            if lossless:
                img.save(target, "WEBP", lossless=True, method=4)
            else:
                img.save(target, "WEBP", quality=quality, method=4)
        # Read it back before deleting anything. A truncated write that nobody
        # checked would take the only copy of a scanned map with it.
        with Image.open(target) as check:
            check.verify()
    except Exception as exc:
        print(f"  skipped {path.name}: {exc}")
        if target.exists():
            target.unlink()
        return None

    after = target.stat().st_size
    if after >= before:
        # Rare, but it happens on small flat images. Keep whichever is smaller.
        target.unlink()
        return None
    path.unlink()
    return before, after


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="Actually convert. Without this it only reports.")
    ap.add_argument("--all-lossless", action="store_true",
                    help="Lossless for generated art too, not just uploads")
    ap.add_argument("--quality", type=int, default=LOSSY_QUALITY,
                    help=f"Quality for generated art (default {LOSSY_QUALITY})")
    args = ap.parse_args()

    cfg = config_mod.load()
    roots = [("art", cfg.assets_dir), ("files", cfg.files_dir)]

    totals = {"before": 0, "after": 0, "done": 0, "skipped": 0}
    for label, root in roots:
        if not Path(root).exists():
            continue
        images = [p for p in Path(root).rglob("*.png") if ".thumbs" not in p.parts]
        images += [p for p in Path(root).rglob("*.jpg") if ".thumbs" not in p.parts]
        if not images:
            continue

        print(f"\n{label}: {len(images)} image(s) in {root}")
        for path in sorted(images):
            # An upload is irreplaceable; generated art is not.
            uploaded = path.name.startswith(UPLOAD_PREFIX) or label == "files"
            lossless = uploaded or args.all_lossless
            size = path.stat().st_size

            if not args.apply:
                how = "lossless" if lossless else f"q{args.quality}"
                print(f"  would convert {path.name[:44]:44} {size/1024:7.0f}K  {how}")
                totals["before"] += size
                continue

            result = convert(path, lossless, args.quality)
            if result is None:
                totals["skipped"] += 1
                continue
            before, after = result
            totals["before"] += before
            totals["after"] += after
            totals["done"] += 1

    print()
    if not args.apply:
        print(f"Would convert {totals['before'] / 1024 / 1024:.0f} MB of images.")
        print("Uploads go lossless, generated art goes to quality "
              f"{args.quality}. Re-run with --apply.")
        return 0

    saved = totals["before"] - totals["after"]
    print(f"Converted {totals['done']} image(s), skipped {totals['skipped']}.")
    if totals["before"]:
        print(f"{totals['before'] / 1024 / 1024:.0f} MB is now "
              f"{totals['after'] / 1024 / 1024:.0f} MB, "
              f"saving {saved / 1024 / 1024:.0f} MB "
              f"({100 * saved / totals['before']:.0f}%).")
    print("\nAsset ids do not carry a format, so no page needed changing.")
    print("Thumbnails rebuild themselves; delete assets/**/.thumbs to force it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
