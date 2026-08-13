"""Download SRD spells, conditions and magic items for hover tooltips.

Source: dnd5eapi.co, serving the D&D 5.1 System Reference Document, which is
published under Creative Commons Attribution 4.0. That is why this fetches the
SRD rather than scraping a rulebook: the SRD may be redistributed with credit,
and the Player's Handbook may not.

Writes `data/srd.json` once. The wiki then works offline and doesn't depend on
anyone else's uptime during a session.

    python tools\\fetch_srd.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402

API = "https://www.dnd5eapi.co/api/2014"
UA = {"User-Agent": "copper-vale-wiki"}

# Tooltips are a glance, not a rules lookup. Long entries are trimmed and the
# reader can open the real source if they need the rest.
MAX_CHARS = 600


def fetch(path: str) -> dict:
    req = urllib.request.Request(f"{API}{path}", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def trim(parts: list[str]) -> str:
    text = " ".join(p.strip() for p in parts if p.strip())
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS]
    stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[: stop + 1] if stop > MAX_CHARS * 0.6 else cut.rstrip()) + " ..."


def collect(kind: str, endpoint: str, meta_of) -> list[dict]:
    listing = fetch(endpoint)
    out = []
    total = listing.get("count", 0)
    for i, ref in enumerate(listing["results"], 1):
        try:
            item = fetch(f"/{endpoint.strip('/')}/{ref['index']}")
        except urllib.error.HTTPError:
            continue
        out.append({
            "term": item["name"],
            "kind": kind,
            "meta": meta_of(item),
            "text": trim(item.get("desc") or []),
        })
        if i % 50 == 0 or i == total:
            print(f"  {kind}: {i}/{total}", flush=True)
    return out


def spell_meta(s: dict) -> str:
    level = s.get("level", 0)
    school = (s.get("school") or {}).get("name", "")
    tier = "Cantrip" if level == 0 else f"Level {level}"
    bits = [f"{tier} {school}".strip(), s.get("casting_time", ""), s.get("range", "")]
    if s.get("concentration"):
        bits.append("Concentration")
    if s.get("ritual"):
        bits.append("Ritual")
    return " · ".join(b for b in bits if b)


def main() -> int:
    cfg = config_mod.load()
    out_dir = cfg.root / "data"
    out_dir.mkdir(exist_ok=True)

    print("Fetching SRD content (a few thousand small requests, be patient)...")
    entries: list[dict] = []
    entries += collect("spell", "/spells", spell_meta)
    entries += collect("condition", "/conditions", lambda c: "Condition")
    entries += collect(
        "item", "/magic-items",
        lambda m: (m.get("rarity") or {}).get("name", "Magic item"),
    )

    payload = {
        "source": "SRD 5.1 via dnd5eapi.co",
        "licence": "CC BY 4.0",
        "entries": sorted(entries, key=lambda e: e["term"].lower()),
    }
    path = out_dir / "srd.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    size = path.stat().st_size / 1024
    print(f"\nWrote {len(entries)} entries to {path}  ({size:.0f} KB)")
    for kind in ("spell", "condition", "item"):
        print(f"  {sum(1 for e in entries if e['kind'] == kind):>4}  {kind}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
