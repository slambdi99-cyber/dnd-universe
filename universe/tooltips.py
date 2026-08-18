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

That rule covers page names too, and used to not. It was applied only to a
hand-kept list of SRD spell words, so a page could be called "The" or "Kept"
and match lowercase, linking every occurrence in every body on the site. A
page name is exactly as likely to be an ordinary word as a spell is.

Where terms overlap, the longest wins: in "the Hollow Root Covenant", the
faction matches before `The Hollow Root` can claim the first three words and
strand "Covenant".

Wiki entries respect visibility: a page you can't see never appears in your
index, or the tooltip would leak its existence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote_plus

from . import secrets as secrets_mod
from . import access as access_mod
from .entities import Entity


def load_srd(root: Path) -> list[dict]:
    path = root / "data" / "srd.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except json.JSONDecodeError:
        return []


def _readable(entity: Entity, viewer) -> bool:
    """Kept as a name, delegating to the one implementation of the rule."""
    return access_mod.readable(entity, viewer)


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
            body = access_mod.redact(entity.body, viewer)
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

    # First names for characters: "Elaric" finds Elaric the Blightwarden if
    # and only if exactly one character starts with Elaric. People talk in
    # first names; an ambiguous one simply is not offered. Characters only,
    # deliberately: places and lore lead with ordinary words -- Her Verdancy,
    # House of the Bricklayers, East Gate -- and a caps-only single word
    # still matches at the start of every sentence. Titles are not names,
    # so Sister Lethra does not turn every sentence-initial "Sister" into
    # her.
    STOP = {"the", "a", "an", "of", "and",
            "sister", "brother", "mother", "father", "lady", "lord",
            "king", "queen", "old", "saint"}
    candidates: dict[str, list[dict]] = {}
    for entry in seen.values():
        words = entry["term"].split()
        if len(words) < 2 or entry["kind"] != "wiki":
            continue
        if entry.get("meta") != "Character":
            continue
        lead = words[0]
        if lead.lower() in STOP or len(lead) < 3:
            continue
        candidates.setdefault(lead.lower(), []).append(entry)
    aliases = {}
    for lead, owners in candidates.items():
        if len(owners) == 1 and lead not in seen:
            aliases[lead] = owners[0]

    payload = []
    for lead, entry in aliases.items():
        payload.append({
            "t": entry["term"].split()[0],
            "n": entry["term"],
            "k": entry["kind"],
            "m": entry.get("meta", ""),
            "d": entry.get("text", ""),
            "u": entry.get("url", ""),
            "c": 1,
        })
    for entry in seen.values():
        term = entry["term"]
        url = entry.get("url", "")
        if not url and entry["kind"] != "wiki":
            # Straight to D&D Beyond for the full entry. The tooltip carries a
            # trimmed SRD summary; anything beyond that belongs on the site
            # where the table's books actually live, and where The DM's content
            # sharing already gives everyone access.
            url = "https://www.dndbeyond.com/search?q=" + quote_plus(term)
        payload.append({
            "t": term,
            "k": entry["kind"],
            "m": entry.get("meta", ""),
            "d": entry.get("text", ""),
            "u": url,
            # 1 = needs a capital letter to match. Every single-word term,
            # not only the SRD ones in AMBIGUOUS: a page name is as likely to
            # be an ordinary word as a spell is. A page called "The" or "Kept"
            # was matching case-insensitively and linking every occurrence in
            # every body. Multi-word terms stay loose, because "eldritch
            # blast" cannot turn up by accident.
            "c": 1 if " " not in term else 0,
        })
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


TOOLTIP_CSS = """
.tt { border-bottom: 1px dotted var(--muted); cursor: pointer; }
.tt:hover { border-bottom-color: var(--star); }
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
    // One link per term per page. A name that appears nine times wrapped
    // nine times reads as decoration, not navigation; the first mention
    // carries the link and the rest stay prose, the way wikis have always
    // done it.
    const seen = new Set();
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
      // A card naming its own subject must not link to itself either: the
      // whole card already goes there. Its title link says where "here" is.
      const card = node.parentElement && node.parentElement.closest('.card');
      const ownHref = card
        ? (card.querySelector('.body > a') || {getAttribute: () => ''})
            .getAttribute('href')
        : '';
      const html = node.nodeValue.replace(re, (match) => {
        const e = byKey.get(match.toLowerCase());
        if (!e) return match;
        // A page's own name in its own prose is not a link anywhere: leave
        // it as text rather than offering a click that goes nowhere.
        if (e.u && e.u === location.pathname) return match;
        if (e.u && ownHref && e.u === ownHref) return match;
        const seenKey = e.t.toLowerCase();
        if (seen.has(seenKey)) return match;
        // Ambiguous single words only count when capitalised.
        if (e.c && match[0] !== match[0].toUpperCase()) return match;
        const cls = e.k === 'wiki' ? 'tt tt-wiki' : 'tt';
        const key = e.t.toLowerCase().replace(/"/g, '&quot;');
        seen.add(seenKey);
        if (e.u) {
          const target = e.k === 'wiki' ? '' : ' target="_blank" rel="noopener"';
          return '<a class="' + cls + '" data-t="' + key + '" href="' +
                 e.u.replace(/"/g, '&quot;') + '"' + target + '>' + match + '</a>';
        }
        return '<span class="' + cls + '" data-t="' + key + '">' + match + '</span>';
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
      '<h4>' + (e.n || e.t) + '</h4>' +
      (e.m ? '<div class="m">' + e.m + '</div>' : '') +
      '<p>' + (e.d || 'No description.') + '</p>' +
      (e.u && e.k !== 'wiki'
        ? '<a href="' + e.u + '" target="_blank" rel="noopener">' +
          'Full entry on D&amp;D Beyond</a>'
        : '');
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
  /* The router hides tooltips before a swap (a hover the reader is
     leaving must not linger over the next page) and re-walks the
     incoming content (a swapped-in `#page` has no `.tt` spans yet). */
  window.__tipsHide = hide;
  window.__tipsWalk = walk;

  document.addEventListener('mouseover', e => {
    const el = e.target.closest('.tt');
    if (el) show(el);
  });
  document.addEventListener('mouseout', e => {
    if (e.target.closest('.tt')) hide();
  });
  // Links navigate normally; non-link tooltip spans still open on tap.
  document.addEventListener('click', e => {
    const el = e.target.closest('.tt');
    if (el && el.tagName !== 'A') { e.preventDefault(); show(el); }
    else if (!e.target.closest('.tt') && !e.target.closest('#tip')) hide();
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
  window.addEventListener('scroll', hide, { passive: true });

  const page = document.getElementById('page');
  if (page) walk(page);
})();
"""
