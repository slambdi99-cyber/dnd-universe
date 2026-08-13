"""Build labelled contact sheets from imported Discord attachments.

Scanning a few hundred images one at a time is slow and expensive. This tiles
them into a handful of numbered sheets so the whole archive can be reviewed at
a glance, then the index tells you which file each tile is.

    python tools\\contact_sheet.py --lore ..\\dnd-scribe\\lore\\dnd-campaign
    python tools\\contact_sheet.py --author Korran's player

Writes sheets and index.txt into <lore>/contact_sheets/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

THUMB = 300
COLS = 6
LABEL_H = 22
PAD = 6
PER_SHEET = COLS * 5  # 30 tiles per sheet

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def load_rows(lore: Path, author: str | None):
    msgs = json.loads((lore / "messages.json").read_text(encoding="utf-8"))
    rows = []
    for m in msgs:
        if author and m["author"].lower() != author.lower():
            continue
        for a in m["attachments"]:
            if Path(a["filename"]).suffix.lower() not in IMAGE_EXT:
                continue
            path = lore / "attachments" / a["file"]
            if path.exists():
                rows.append((m, a, path))
    return rows


def build(rows, out_dir: Path, prefix: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sheets = []

    for sheet_no, start in enumerate(range(0, len(rows), PER_SHEET), 1):
        chunk = rows[start : start + PER_SHEET]
        n_rows = (len(chunk) + COLS - 1) // COLS
        w = COLS * (THUMB + PAD) + PAD
        h = n_rows * (THUMB + LABEL_H + PAD) + PAD
        sheet = Image.new("RGB", (w, h), (28, 28, 30))
        draw = ImageDraw.Draw(sheet)

        for i, (m, a, path) in enumerate(chunk):
            col, row = i % COLS, i // COLS
            x = PAD + col * (THUMB + PAD)
            y = PAD + row * (THUMB + LABEL_H + PAD)
            try:
                with Image.open(path) as im:
                    im.seek(0) if getattr(im, "is_animated", False) else None
                    im = im.convert("RGB")
                    im.thumbnail((THUMB, THUMB))
                    sheet.paste(im, (x + (THUMB - im.width) // 2,
                                     y + (THUMB - im.height) // 2))
            except Exception as exc:  # a corrupt file shouldn't kill the sheet
                draw.text((x + 8, y + THUMB // 2), f"unreadable\n{exc}"[:40],
                          fill=(200, 90, 90))

            idx = start + i + 1
            caption = " ".join(m["content"].split())[:34]
            draw.text((x + 2, y + THUMB + 4),
                      f"{idx:>3} {m['author'][:11]} {caption}",
                      fill=(225, 225, 230))

        path = out_dir / f"{prefix}-{sheet_no:02d}.jpg"
        sheet.save(path, quality=88)
        sheets.append(path)
        print(f"  {path.name}  ({len(chunk)} tiles)")

    return sheets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lore", default=r"..\dnd-scribe\lore\dnd-campaign")
    ap.add_argument("--author", help="Only this Discord author")
    args = ap.parse_args()

    lore = Path(args.lore).resolve()
    rows = load_rows(lore, args.author)
    if not rows:
        print("No images matched.")
        return 1

    prefix = f"sheet-{args.author}" if args.author else "sheet"
    out_dir = lore / "contact_sheets"
    print(f"{len(rows)} images -> {out_dir}")
    build(rows, out_dir, prefix)

    lines = []
    for i, (m, a, path) in enumerate(rows, 1):
        caption = " ".join(m["content"].split())[:90]
        lines.append(
            f"{i:>3}  {m['created_at'][:10]}  {m['author']:<16}  "
            f"{a['file']}\n     {caption}"
        )
    (out_dir / f"{prefix}-index.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"  index -> {prefix}-index.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
