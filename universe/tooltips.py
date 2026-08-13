"""Hover tooltips for game terms and wiki cross-references.

Two sources feed one index:

  * **The SRD**, fetched once by `tools/fetch_srd.py`: spells, conditions and
    magic items, under CC BY 4.0.
  * **The wiki itself**: every place, character, faction and item, so hovering
    "Brindlewood" in a session write-up shows what Brindlewood is without
    leaving the page.

## Matching, and why it is fussy

Naive substring matching produces nonsense. Several SRD spells are ordinary
English words: Light, Shield, Command, Bane, Heal, Fly, Sleep, Web, Blur, Aid.
Marking up every "the light of the moon" would be worse than no tooltips at
all.

So single-word terms only match when capitalised in the text, which is how
people actually write them ("cast Fireball", "hit with Bane"). Multi-word
terms match case-insensitively, because "eldritch blast" is unambiguous.

Wiki entries respect visibility: a page you can't see never appears in your
index, or the tooltip would leak its existence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import secrets as secrets_mod
from .entities import Entity

# Single words common enough in prose that matching them unconditionally would
# be worse than useless. These need a capital letter to count.
AMBIGUOUS = {
    "aid", "alarm", "bane", "barkskin", "bless", "blur", "branding", "clone",
    "cloudkill", "command", "compulsion", "confusion", "counterspell",
    "darkness", "daylight", "disintegrate", "dream", "druidcraft", "earthquake",
    "enlarge", "entangle", "eyebite", "fabricate", "fear", "feather", "fly",
    "forbiddance", "foresight", "freedom", "friends", "geas", "glibness",
    "goodberry", "grease", "guidance", "haste", "heal", "heat", "hex", "guards",
    "identify", "imprisonment", "invisibility", "jump", "knock", "levitate",
    "light", "longstrider", "mending", "message", "mislead", "misty", "move",
    "nondetection", "passwall", "prayer", "prestidigitation", "reincarnate",
    "resistance", "resurrection", "revivify", "sanctuary", "seeming", "shatter",
    "shield", "shillelagh", "silence", "sleep", "slow", "spare", "stoneskin",
    "suggestion", "sunbeam", "sunburst", "telekinesis", "teleport", "thaumaturgy",
    "thunderwave", "tongues", "transport", "trap", "true", "web", "wish",
    "blade", "blight", "chill", "control", "creation", "dominate", "feign",
    "gaseous", "gate", "glyph", "guardian", "harm", "hold", "hunter", "maze",
    "mirror", "planar", "plane", "poison", "power", "produce", "protection",
    "purify", "raise", "ray", "regenerate", "remove", "rope", "scrying", "seek",
    "sending", "sequester", "shape", "simulacrum", "speak", "spike", "storm",
    "symbol", "time", "tiny", "vampiric", "wall", "warding", "water", "wind",
    "word", "zone",
}


def load_srd(root: Path) -> list[dict]:
    path = root / "data" / "srd.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except json.JSONDecodeError:
        return []


def _readable(entity: Entity, viewer: frozenset[str]) -> bool:
    allowed = entity.data.get("visible_to")
    if not allowed:
        return True
    if isinstance(allowed, str):
        allowed = [allowed]
    return bool(viewer & {str(a).strip().lower() for a in allowed})


def wiki_entries(entities: list[Entity], viewer: frozenset[str],
                 base: str) -> list[dict]:
    out = []
    # Filtered here as well as by the caller. Every route already passes a
    # visible set, but a tooltip index that leaks a hidden page's name and
    # summary would undo the page-level hiding entirely, so this does not
    # depend on the caller getting it right.
    for entity in (e for e in entities if _readable(e, viewer)):
        summary = entity.summary.strip()
        if not summary:
            body = secrets_mod.redact(entity.body, viewer)
            summary = body.split("\n\n")[0][:200] if body else ""
        out.append({
            "term": entity.name,
            "kind": "wiki",
            "meta": entity.kind.capitalize(),
            "text": summary,
            "url": f"{base}{entity.kind}/{entity.slug}.html",
        })
    return out


def build(entities: list[Entity], viewer: frozenset[str], root: Path,
          base: str) -> str:
    """The tooltip index, as JSON for the browser."""
    entries = wiki_entries(entities, viewer, base) + load_srd(root)

    # Wiki entries win over SRD ones on a name clash: your Bloodroot Greatsword
    # matters more here than a generic entry of the same name.
    seen: dict[str, dict] = {}
    for entry in entries:
        key = entry["term"].lower()
        if key not in seen:
            seen[key] = entry

    payload = []
    for entry in seen.values():
        term = entry["term"]
        payload.append({
            "t": term,
            "k": entry["kind"],
            "m": entry.get("meta", ""),
            "d": entry.get("text", ""),
            "u": entry.get("url", ""),
            # 1 = needs a capital letter to match.
            "c": 1 if (" " not in term and term.lower() in AMBIGUOUS) else 0,
        })
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


TOOLTIP_CSS = """
.tt { border-bottom: 1px dotted var(--accent); cursor: help; }
.tt-wiki { border-bottom-style: solid; }
#tip {
  position: absolute; z-index: 50; max-width: 22rem; padding: .7rem .9rem;
  background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
  box-shadow: 0 6px 24px rgba(0,0,0,.25); font-size: .85rem; line-height: 1.5;
  display: none;
}
#tip h4 { margin: 0 0 .1rem; font-size: .95rem; }
#tip .m { color: var(--accent); font-size: .72rem; text-transform: uppercase;
  letter-spacing: .06em; margin-bottom: .4rem; }
#tip p { margin: 0; }
#tip a { font-size: .8rem; display: inline-block; margin-top: .5rem; }
"""

TOOLTIP_JS = r"""
(function () {
  const idx = window.__TIPS__ || [];
  if (!idx.length) return;
  const byKey = new Map();
  idx.forEach(e => byKey.set(e.t.toLowerCase(), e));

  // Longest first, so "Eldritch Blast" wins over "Blast".
  const terms = idx.map(e => e.t).sort((a, b) => b.length - a.length);
  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp('\\b(' + terms.map(esc).join('|') + ')\\b', 'gi');

  // Never rewrite inside these: links already do something, and code and
  // headings should stay literal.
  const SKIP = new Set(['A', 'CODE', 'PRE', 'SCRIPT', 'STYLE', 'TEXTAREA',
                        'INPUT', 'SELECT', 'H1', 'H2', 'H3', 'BUTTON']);

  function walk(root) {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        if (!n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        for (let p = n.parentElement; p && p !== root; p = p.parentElement) {
          if (SKIP.has(p.tagName) || p.classList.contains('tt'))
            return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    const jobs = [];
    let n;
    while ((n = w.nextNode())) if (re.test(n.nodeValue)) { re.lastIndex = 0; jobs.push(n); }
    jobs.forEach(node => {
      const html = node.nodeValue.replace(re, (match) => {
        const e = byKey.get(match.toLowerCase());
        if (!e) return match;
        // Ambiguous single words only count when capitalised.
        if (e.c && match[0] !== match[0].toUpperCase()) return match;
        const cls = e.k === 'wiki' ? 'tt tt-wiki' : 'tt';
        return '<span class="' + cls + '" data-t="' +
               e.t.toLowerCase().replace(/"/g, '&quot;') + '">' + match + '</span>';
      });
      if (html !== node.nodeValue) {
        const span = document.createElement('span');
        span.innerHTML = html;
        node.parentNode.replaceChild(span, node);
      }
    });
  }

  const tip = document.createElement('div');
  tip.id = 'tip';
  document.body.appendChild(tip);

  function show(el) {
    const e = byKey.get(el.dataset.t);
    if (!e) return;
    tip.innerHTML =
      '<h4>' + e.t + '</h4>' +
      (e.m ? '<div class="m">' + e.m + '</div>' : '') +
      '<p>' + (e.d || 'No description.') + '</p>' +
      (e.u ? '<a href="' + e.u + '">Open page</a>' : '');
    tip.style.display = 'block';
    const r = el.getBoundingClientRect();
    const t = tip.getBoundingClientRect();
    let left = r.left + window.scrollX;
    left = Math.min(left, window.scrollX + document.documentElement.clientWidth - t.width - 12);
    let top = r.bottom + window.scrollY + 6;
    if (r.bottom + t.height + 12 > window.innerHeight) top = r.top + window.scrollY - t.height - 6;
    tip.style.left = Math.max(8, left) + 'px';
    tip.style.top = top + 'px';
  }
  function hide() { tip.style.display = 'none'; }

  document.addEventListener('mouseover', e => {
    const el = e.target.closest('.tt');
    if (el) show(el);
  });
  document.addEventListener('mouseout', e => {
    if (e.target.closest('.tt')) hide();
  });
  // Tap to open on touch, tap elsewhere to dismiss.
  document.addEventListener('click', e => {
    const el = e.target.closest('.tt');
    if (el) { e.preventDefault(); show(el); } else if (!e.target.closest('#tip')) hide();
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
  window.addEventListener('scroll', hide, { passive: true });

  const page = document.getElementById('page');
  if (page) walk(page);
})();
"""
