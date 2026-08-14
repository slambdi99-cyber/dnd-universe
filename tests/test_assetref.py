"""Tests for turning caller-supplied strings into paths.

Four routes used to do this themselves with four slightly different checks.
Now there is one type, so the nasty inputs can be enumerated properly in one
place instead of being partially covered in four.

The rule being tested is that parsing is the gate: an unparsed string cannot
become a path, because nothing downstream accepts a string.

    python tests\\test_assetref.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe.assetref import ArtName, AssetRef, confine, safe_filename  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


print("\n== what parses ==")
ok = AssetRef.parse("character/wren/default-9f4b037a")
check("a normal ref", ok is not None and ok.kind == "character")
check("keeps its parts", (ok.slug, ok.name) == ("wren", "default-9f4b037a"))
check("round-trips", str(ok) == "character/wren/default-9f4b037a")
check("knows its page", ok.page == "character/wren")
check("underscores allowed", AssetRef.parse("a/b/c_d") is not None)
check("digits allowed", AssetRef.parse("a1/b2/c3") is not None)

print("\n== what does not ==")
REFUSED = [
    ("empty", ""),
    ("none", None),
    ("not a string", 12345),
    ("one segment", "wren"),
    ("two segments", "character/wren"),
    ("four segments", "character/wren/a/b"),
    ("dot dot", "character/../secret"),
    ("dot dot alone", "../../etc/passwd"),
    ("trailing slash", "character/wren/"),
    ("leading slash", "/character/wren/name"),
    ("double slash", "character//name"),
    ("backslash", "character\\wren\\name"),
    ("windows absolute", "C:/Windows/System32"),
    ("null byte", "character/wren/na\x00me"),
    ("newline", "character/wren/na\nme"),
    ("space", "character/wren/na me"),
    ("dot in a segment", "character/wren/name.png"),
    ("url encoded traversal", "character/wren/..%2f..%2fpasswd"),
    ("leading dot", "character/wren/.hidden"),
    ("tilde", "character/wren/~root"),
    ("colon", "character/wren/alt:stream"),
    ("very long segment", "a/b/" + "x" * 200),
]
for label, value in REFUSED:
    check(f"refuses {label}", AssetRef.parse(value) is None, repr(value)[:40])

print("\n== the flat art filename ==")
art = ArtName.parse("character-wren.png")
check("parses", art is not None and art.page == "character/wren")
check("splits on the first hyphen only",
      ArtName.parse("place-copper-vale.png").page == "place/copper-vale",
      "slugs contain hyphens; kinds do not")
for label, value in [
    ("no extension", "character-wren"),
    ("wrong extension", "character-wren.jpg"),
    ("no hyphen", "character.png"),
    ("traversal", "../../secret.png"),
    ("a slash", "character/wren.png"),
    ("empty", ""),
    ("just the extension", ".png"),
]:
    check(f"refuses {label}", ArtName.parse(value) is None, repr(value)[:32])

print("\n== loose filenames, which we do not control ==")
for label, value, expected in [
    ("an ordinary discord name", "1234-image.png", True),
    ("spaces and brackets", "Screenshot (3).png", True),
    ("unicode", "kort\u00e6.png", True),
    ("traversal", "../secret", False),
    ("windows traversal", "..\\secret", False),
    ("embedded traversal", "a/../../b", False),
    ("a slash", "sub/dir.png", False),
    ("null byte", "a\x00.png", False),
    ("hidden file", ".env", False),
    ("empty", "", False),
    ("absurdly long", "x" * 300, False),
]:
    check(f"{label}: {'allowed' if expected else 'refused'}",
          safe_filename(value) is expected, repr(value)[:34])

print("\n== confinement is the check that survives a symlink ==")
sandbox = Path(tempfile.mkdtemp(prefix="assetref-"))
(sandbox / "store" / "character" / "wren").mkdir(parents=True)
real = sandbox / "store" / "character" / "wren" / "art.png"
real.write_bytes(b"\x89PNG")
(sandbox / "outside.txt").write_text("not yours", encoding="utf-8")

store = sandbox / "store"
check("finds a real file", AssetRef.parse("character/wren/art").path_under(store) == real.resolve())
check("missing file is None",
      AssetRef.parse("character/wren/nope").path_under(store) is None)
check("wrong extension is None",
      AssetRef.parse("character/wren/art").path_under(store, ".jpg") is None)
check("find_under tries each extension",
      AssetRef.parse("character/wren/art").find_under(store, {"jpg", "png"}) == real.resolve())
check("confine rejects a path outside the root",
      confine(store, sandbox / "outside.txt") is None)
check("confine accepts one inside", confine(store, real) == real.resolve())

# A symlink is the case no string check can catch, which is why path_under
# resolves before comparing. Skipped where the OS will not create one.
link = store / "character" / "wren" / "escape.png"
try:
    link.symlink_to(sandbox / "outside.txt")
    made = True
except (OSError, NotImplementedError):
    made = False
if made:
    check("a symlink pointing out of the store is refused",
          AssetRef.parse("character/wren/escape").path_under(store) is None,
          "string validation cannot see this; resolving can")
else:
    print("    ..    symlink test skipped: no permission to create one")

shutil.rmtree(sandbox, ignore_errors=True)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("all checks passed")
