"""Files people upload: pictures for a page, and attachments on it.

Two things land here. An image uploaded through the art panel joins the same
gallery as the generated ones, so a portrait someone drew or commissioned sits
beside SDXL's attempts and can be chosen over them. Anything else (a map, a
handout, a PDF of a homebrew subclass, a voice memo) becomes an attachment
listed on the page.

Uploads are the classic way to turn a wiki into someone else's web server, so
the rules here are narrow on purpose:

  * The type is decided by the file's own leading bytes, not its name and not
    the browser's claim. A .png that starts with `<?php` or `<svg` is refused.
  * SVG is not an image as far as this is concerned. It's a document that can
    carry script, and it would run on the wiki's own origin.
  * Stored names are content hashes. Nothing a person typed reaches the
    filesystem, so `../` and friends have nowhere to go.
  * Anything that isn't a plain image is served as a download, never rendered
    in the page.

Everyone signed in can upload, same as everything else here.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .assetref import AssetRef
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024

# (extension, media type, leading bytes). Order matters only for readability.
IMAGE_SIGNATURES: tuple[tuple[str, str, bytes], ...] = (
    ("png", "image/png", b"\x89PNG\r\n\x1a\n"),
    ("jpg", "image/jpeg", b"\xff\xd8\xff"),
    ("gif", "image/gif", b"GIF87a"),
    ("gif", "image/gif", b"GIF89a"),
)

# Everything else worth keeping on a campaign page. Same rule: the bytes decide.
FILE_SIGNATURES: tuple[tuple[str, str, bytes], ...] = (
    ("pdf", "application/pdf", b"%PDF-"),
    ("zip", "application/zip", b"PK\x03\x04"),
    ("mp3", "audio/mpeg", b"ID3"),
    ("ogg", "audio/ogg", b"OggS"),
)

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class Upload:
    asset_id: str      # "<kind>/<slug>/<name>" without the extension
    filename: str      # what to call it on the way back out
    media_type: str
    extension: str
    is_image: bool
    size: int


def sniff(data: bytes) -> tuple[str, str, bool] | None:
    """Work out what this actually is. Returns (extension, media type, is_image).

    WEBP and MP4 need a second look because their magic is a container header
    with the real format four bytes in.
    """
    for ext, media, magic in IMAGE_SIGNATURES:
        if data.startswith(magic):
            return ext, media, True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp", True
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"mp42", b"isom", b"iso2", b"avc1", b"mp41"):
            return "mp4", "video/mp4", False
        if brand in (b"heic", b"heix", b"mif1"):
            # A real image, but browsers outside Safari won't show it, so it's
            # handled as a download rather than offered as a page picture.
            return "heic", "image/heic", False
    for ext, media, magic in FILE_SIGNATURES:
        if data.startswith(magic):
            return ext, media, False
    return None


def clean_name(name: str, extension: str) -> str:
    """A display name safe to put in a header and a link."""
    stem = SAFE_NAME.sub("-", Path(name or "").stem).strip("-.")[:60]
    return f"{stem or 'file'}.{extension}"


def save(root: Path, kind: str, slug: str, data: bytes,
         original_name: str = "") -> tuple[Upload | None, str]:
    """Store an upload. Returns (upload, message); upload is None on refusal."""
    if not data:
        return None, "That file was empty."
    if len(data) > MAX_BYTES:
        return None, (f"That's {len(data) / 1024 / 1024:.0f}MB and the limit is "
                      f"{MAX_BYTES // 1024 // 1024}MB. Link to it instead.")

    sniffed = sniff(data)
    if sniffed is None:
        return None, ("That file type isn't accepted. Images (PNG, JPEG, GIF, "
                      "WEBP), PDFs, zips, MP3, OGG and MP4 are. SVG isn't: it "
                      "can carry scripts, and it would run as part of the site.")

    extension, media_type, is_image = sniffed
    digest = hashlib.sha256(data).hexdigest()[:16]
    name = f"upload-{digest}"

    folder = Path(root) / kind / slug
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.{extension}"
    if not path.exists():
        path.write_bytes(data)

    return Upload(
        asset_id=f"{kind}/{slug}/{name}",
        filename=clean_name(original_name, extension),
        media_type=media_type,
        extension=extension,
        is_image=is_image,
        size=len(data),
    ), "Uploaded."


KNOWN_EXTENSIONS = ({e for e, _, _ in IMAGE_SIGNATURES}
                    | {e for e, _, _ in FILE_SIGNATURES}
                    | {"webp", "mp4", "heic"})


def locate(root: Path, asset_id) -> Path | None:
    """Find a stored upload, whatever extension it was saved with.

    Takes an `AssetRef` or the string form of one. Parsing is what makes this
    safe, so a string that will not parse simply has no file: there is no path
    to build from it.
    """
    ref = asset_id if isinstance(asset_id, AssetRef) else AssetRef.parse(asset_id)
    if ref is None:
        return None
    return ref.find_under(root, KNOWN_EXTENSIONS)


def media_type_for(path: Path) -> str:
    ext = path.suffix.lstrip(".").lower()
    for e, media, _ in IMAGE_SIGNATURES + FILE_SIGNATURES:
        if e == ext:
            return media
    return {"webp": "image/webp", "mp4": "video/mp4",
            "heic": "image/heic"}.get(ext, "application/octet-stream")


def attachments_of(entity) -> list[dict]:
    """The files recorded on a page, as stored in its frontmatter."""
    found = entity.data.get("files") or []
    return [f for f in found if isinstance(f, dict) and f.get("id")]


def attach_file(entity, upload: Upload, who: str = "") -> None:
    files = attachments_of(entity)
    if any(f["id"] == upload.asset_id for f in files):
        return
    files.append({
        "id": upload.asset_id,
        "name": upload.filename,
        "type": upload.media_type,
        "size": upload.size,
        **({"by": who} if who else {}),
    })
    entity.data["files"] = files


def detach_file(entity, asset_id: str) -> bool:
    """Forget a file. The bytes stay on disk: another page may cite the same
    hash, and a wiki that deletes on unlink loses a shared map to one tidy-up."""
    files = attachments_of(entity)
    remaining = [f for f in files if f["id"] != asset_id]
    if len(remaining) == len(files):
        return False
    entity.data["files"] = remaining
    if not remaining:
        entity.data.pop("files", None)
    return True
