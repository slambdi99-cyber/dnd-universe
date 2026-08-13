"""Tests for uploaded files.

Uploads are how a wiki becomes someone else's web server, so most of these are
about refusal: what the bytes actually are, where they land on disk, and what
the server agrees to hand back.

    python tests\\test_uploads.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import uploads  # noqa: E402
from universe.entities import Entity  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


sandbox = Path(tempfile.mkdtemp(prefix="uploads-test-"))

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32
PDF = b"%PDF-1.7\n" + b"\x00" * 64
MP3 = b"ID3\x03\x00" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b"<!doctype html><script>alert(1)</script>"
PHP = b"<?php system($_GET['c']); ?>"

print("\n== what it is, by its bytes ==")
for label, data, ext, image in [
    ("PNG", PNG, "png", True), ("JPEG", JPEG, "jpg", True),
    ("GIF", GIF, "gif", True), ("WEBP", WEBP, "webp", True),
    ("PDF", PDF, "pdf", False), ("MP3", MP3, "mp3", False),
    ("MP4", MP4, "mp4", False),
]:
    got = uploads.sniff(data)
    check(f"{label} recognised", got is not None and got[0] == ext, str(got))
    check(f"{label} image flag", got is not None and got[2] is image)

print("\n== what it refuses ==")
check("SVG is refused", uploads.sniff(SVG) is None,
      "it is a document that can carry script, on our own origin")
check("HTML is refused", uploads.sniff(HTML) is None)
check("PHP is refused", uploads.sniff(PHP) is None)
check("empty is refused", uploads.sniff(b"") is None)
check("a PNG name doesn't make it a PNG",
      uploads.save(sandbox, "place", "x", SVG, "innocent.png")[0] is None,
      "the extension is never consulted")

ok, msg = uploads.save(sandbox, "place", "x", b"", "empty.png")
check("empty file rejected with a reason", ok is None and "empty" in msg.lower(), msg)
big = PNG + b"\x00" * (uploads.MAX_BYTES + 1)
ok, msg = uploads.save(sandbox, "place", "x", big, "huge.png")
check("oversized rejected", ok is None and "limit" in msg, msg)

print("\n== storing ==")
up, msg = uploads.save(sandbox, "place", "brindlewood", PNG, "The Map!!.png")
check("saved", up is not None, msg)
check("stored under kind/slug",
      (sandbox / "place" / "brindlewood").exists())
check("filename is a content hash, not theirs",
      up.asset_id.startswith("place/brindlewood/upload-")
      and "Map" not in up.asset_id, up.asset_id)
check("display name kept, cleaned",
      up.filename == "The-Map.png", up.filename)
check("size recorded", up.size == len(PNG))

again, _ = uploads.save(sandbox, "place", "brindlewood", PNG, "copy.png")
check("same bytes reuse the same id", again.asset_id == up.asset_id,
      "content-addressed, so a re-upload costs nothing")
files = list((sandbox / "place" / "brindlewood").glob("*"))
check("and only one file on disk", len(files) == 1, str(len(files)))

evil = uploads.save(sandbox, "place", "brindlewood", PNG, "../../../etc/passwd")
check("a traversal filename can't escape",
      evil[0].filename == "passwd.png", evil[0].filename)

print("\n== finding it again ==")
check("locate finds it", uploads.locate(sandbox, up.asset_id) is not None)
check("wrong id gives nothing", uploads.locate(sandbox, "place/x/nope") is None)
check("traversal refused", uploads.locate(sandbox, "../../secret") is None)
check("a bare name refused", uploads.locate(sandbox, "upload-abc") is None)
check("media type from the file",
      uploads.media_type_for(uploads.locate(sandbox, up.asset_id)) == "image/png")

print("\n== attaching to a page ==")
entity = Entity(kind="place", slug="brindlewood", name="Brindlewood")
pdf, _ = uploads.save(sandbox, "place", "brindlewood", PDF, "handout.pdf")
uploads.attach_file(entity, up, who="Wren")
uploads.attach_file(entity, pdf, who="The DM")
check("both listed", len(uploads.attachments_of(entity)) == 2)
check("attribution kept",
      uploads.attachments_of(entity)[0].get("by") == "Wren")
uploads.attach_file(entity, up, who="Wren")
check("attaching twice does nothing", len(uploads.attachments_of(entity)) == 2)

check("detach reports", uploads.detach_file(entity, up.asset_id))
check("one left", len(uploads.attachments_of(entity)) == 1)
check("detaching what isn't there is False",
      not uploads.detach_file(entity, "place/brindlewood/upload-nope"))
check("the bytes stay on disk", uploads.locate(sandbox, up.asset_id) is not None,
      "another page may cite the same hash")
uploads.detach_file(entity, pdf.asset_id)
check("the key is dropped when empty", "files" not in entity.data,
      "an empty list would render as an empty Files heading")

print("\n== it survives a save and reload ==")
uploads.attach_file(entity, pdf, who="The DM")
parsed = Entity.parse(entity.render(), kind="place", slug="brindlewood")
check("frontmatter round-trips",
      uploads.attachments_of(parsed)[0]["id"] == pdf.asset_id)
check("and keeps the name", uploads.attachments_of(parsed)[0]["name"] == "handout.pdf")

shutil.rmtree(sandbox, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
