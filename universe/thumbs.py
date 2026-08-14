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

from pathlib import Path

# Wide enough to stay sharp on a 2x display at the size each is shown.
SIZES = {
    "card": 400,     # the grids on the front page and the kind indexes
    "page": 1000,    # the hero image at the top of a page
}
QUALITY = 82
FOLDER = ".thumbs"


def path_for(original: Path, size: str) -> Path:
    """Where a thumbnail lives: beside its original, under `.thumbs`."""
    return Path(original).parent / FOLDER / f"{Path(original).stem}-{size}.webp"


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
        from PIL import Image

        with Image.open(original) as img:
            width = SIZES[size]
            if img.width <= width:
                return original
            img = img.convert("RGB")
            img.thumbnail((width, width * 4), Image.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            img.save(target, "WEBP", quality=QUALITY, method=4)
    except Exception:
        # A picture that will not shrink is still a picture. Serving the
        # original is slower than serving a thumbnail and better than serving
        # a broken image.
        return original
    return target


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

# Touched by a collaborator, to prove the update job restarts the server.

# second probe

