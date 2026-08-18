"""Small copies of big pictures, made once and kept.

The front page shows every settlement, every player character and every faction
as a card, and each card was loading the full-size art: a 1024px PNG, often two
or three megabytes because someone uploaded a scan. Thirty cards meant tens of
megabytes to draw a grid of thumbnails a few hundred pixels wide. On a phone,
away from the house, that is the difference between a wiki people use and one
they stop opening.

So the card grids get thumbnails and the page bodies get a mid-size copy. They
are generated on demand, written next to the original under `.thumbs`, and
never made twice. Deleting the folder is safe: it rebuilds.

WEBP because it is roughly a third the size of an equivalent PNG at this scale
and every browser made since 2020 reads it. The originals are untouched, so
nothing is lost by the choice.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Wide enough to stay sharp on a 2x display at the size each is shown.
SIZES = {
    "card": 400,     # the grids on the front page and the kind indexes
    "page": 1000,    # the hero image at the top of a page
}
# Cards are drawn square: the CSS is `aspect-ratio: 1/1; object-fit: cover` in
# both the front-page grid and the art picker. Cropping here rather than in the
# browser means a tall portrait ships 400x400 instead of 400x1600, and the
# three quarters the browser was going to discard never cross the wire. The
# hero image keeps its shape, because nothing crops it.
SQUARE = {"card"}
QUALITY = 82
FOLDER = ".thumbs"


def _stamp() -> str:
    """A short mark for the settings above.

    A thumbnail is reused whenever it is newer than its original, which is the
    right test for "the picture changed" and no test at all for "the rules
    changed". Change a size, the quality, or whether a size is cropped, and
    every existing thumbnail is wrong while still looking current: nothing
    touched the originals, so nothing rebuilds, and the site quietly serves the
    old shape until somebody deletes the folder by hand.

    Putting the settings in the filename makes that impossible. Different
    settings, different name, so the old file is simply not the one being asked
    for, and `make` clears it away when it writes the replacement.
    """
    recipe = repr((sorted(SIZES.items()), sorted(SQUARE), QUALITY))
    return hashlib.sha256(recipe.encode()).hexdigest()[:8]


def path_for(original: Path, size: str) -> Path:
    """Where a thumbnail lives: beside its original, under `.thumbs`."""
    stem = Path(original).stem
    return Path(original).parent / FOLDER / f"{stem}-{size}-{_stamp()}.webp"


def make(original: Path, size: str = "card") -> Path | None:
    """Return a thumbnail, generating it if this is the first time.

    Returns the original when it cannot be shrunk, so callers never have to
    care: a missing Pillow, a corrupt file, or an image already smaller than
    the target all end with something servable.
    """
    original = Path(original)
    if size not in SIZES or not original.exists():
        return None

    target = path_for(original, size)
    if target.exists() and target.stat().st_mtime >= original.stat().st_mtime:
        return target

    try:
        from PIL import Image, ImageOps

        with Image.open(original) as img:
            width = SIZES[size]
            if img.width <= width:
                return original
            img = img.convert("RGB")
            if size in SQUARE:
                # Never larger than the picture already is on its short side:
                # a wide banner cropped to a square must not be blown up to
                # reach the target, which would cost bytes and gain nothing.
                side = min(width, img.width, img.height)
                # Faces sit above centre far more often than below, so the
                # crop keeps a little more of the top than the bottom.
                img = ImageOps.fit(img, (side, side), Image.LANCZOS,
                                   centering=(0.5, 0.4))
            else:
                img.thumbnail((width, width * 4), Image.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            img.save(target, "WEBP", quality=QUALITY, method=4)
            # Anything for this picture and size under older settings is dead
            # weight now, and nothing will ever ask for it again.
            for stale in target.parent.glob(f"{original.stem}-{size}-*.webp"):
                if stale != target:
                    stale.unlink(missing_ok=True)
    except Exception:
        # A picture that will not shrink is still a picture. Serving the
        # original is slower than serving a thumbnail and better than serving
        # a broken image.
        return original
    return target


SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def originals(root: Path):
    """Every picture under `root` that is not itself a thumbnail."""
    for path in sorted(Path(root).rglob("*")):
        if path.suffix.lower() in SUFFIXES and FOLDER not in path.parts:
            yield path


def warm(root: Path, sizes=None) -> int:
    """Build every thumbnail up front. Returns how many were made.

    On demand is the right default for a picture someone has just uploaded,
    and the wrong one for the first person to open the front page after a
    deploy: they wait for thirty images to be shrunk before any of them
    arrive. Run this after deploying and that visitor pays nothing.

    Cheap to repeat. Anything already current is left alone.
    """
    made = 0
    for path in originals(root):
        for size in (sizes or SIZES):
            target = path_for(path, size)
            before = target.exists()
            if make(path, size) == target and not before:
                made += 1
    return made


def sweep(root: Path) -> int:
    """Delete every generated thumbnail. They rebuild on next request."""
    removed = 0
    for folder in Path(root).rglob(FOLDER):
        for f in folder.glob("*.webp"):
            f.unlink()
            removed += 1
        try:
            folder.rmdir()
        except OSError:
            pass
    return removed
