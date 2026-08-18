"""Rendering for the wiki, shared by the static export and the live server.

One implementation, two callers. `tools/export_site.py` renders with an empty
viewer, which strips every secret, and produces files. `mcp_server.py` renders
per signed-in person, so each reader sees their own version. Keeping both on
the same code means a fix to redaction can't apply to one and miss the other.
"""

from __future__ import annotations

import html
import json
from collections import defaultdict

import markdown as md

from . import access as access_mod
from . import hierarchy as hierarchy_mod
from . import secrets as secrets_mod
from . import thumbs
from . import version as version_mod
from . import tooltips as tooltips_mod
from pathlib import Path

from . import schema as schema_mod
from .entities import Entity, Library

class Renderer:
    """Rendering bound to one schema.

    The schema used to be a module-level global that the server overwrote at
    startup through `site.use(...)`, so what a page rendered with depended on
    assignment order rather than on its arguments. The tell was already in the
    tests: they had to remember to call `use` first, and one that forgot
    silently rendered against whatever schema happened to be on disk.

    The functions below take the schema explicitly. This binds it once, so
    callers do not thread it through every call, and two schemas can exist at
    the same time: exporting one campaign while serving another is now
    expressible, which it was not before.
    """

    def __init__(self, schema: schema_mod.Schema):
        self.schema = schema

    @property
    def name(self) -> str:
        return self.schema.name

    def label(self, kind: str) -> str:
        return self.schema.label(kind)

    def shell(self, *args, **kwargs) -> str:
        return shell(self.schema, *args, **kwargs)

    def body(self, *args, **kwargs) -> str:
        return render_body(self.schema, *args, **kwargs)

    def index(self, *args, **kwargs) -> str:
        return render_index(self.schema, *args, **kwargs)

    def kind_index(self, *args, **kwargs) -> str:
        return render_kind_index(self.schema, *args, **kwargs)

    def search_index(self, *args, **kwargs) -> str:
        return search_index(self.schema, *args, **kwargs)

CSS = """
/* Parchment. The background sits at aged-paper tan rather than near-white,
   panels a shade brighter like a fresh leaf on the pile, ink a warm sepia
   black. Dark mode is the same paper by candlelight, not gray-on-black.
   Muted stays dark enough to clear 4.5:1 on the tan. */
/* Dark, always. The parchment by candlelight is the site's one face; the
   OS light/dark preference is deliberately ignored. `color-scheme: dark`
   tells the browser so its own parts -- scrollbars, form controls, the
   search field's innards -- match. */
:root {
  color-scheme: dark;
  --bg: #1b1712; --panel: #252018; --ink: #e5dcc9; --muted: #a3947a;
  --line: #3c352a;
  --accent: #d2a05f; --accent-soft: #2f2a20;
  /* The Buried Star's teal: the seam gradient, and the focus color, so the
     thing you are about to interact with glows faintly starlike. */
  --star: #3fa9b5;
  --grad: linear-gradient(90deg, #2a8a96, #3aa77f 55%, #7fd0dd);
  /* The lava-lamp layer's whole strength. Tune this one number. */
  --lamp: .08;
  --chrome: #252018;
  /* The top bar sits deepest: darker than the page, so the bands read
     top-down as night sky, chrome, paper. */
  --chrome-deep: #14100a;
}
* { box-sizing: border-box; }
/* The router focuses the arriving page's h1 so assistive tech announces the
   navigation and Tab starts from the top of the new content. tabindex="-1"
   means nothing can reach it by keyboard, so the focus ring marks nothing a
   sighted reader can act on -- it is just a box around the title. */
[tabindex="-1"]:focus { outline: none; }
/* Focus is the star's color everywhere: keyboard rings, and the search field
   while you type in it. */
:focus-visible { outline: 2px solid var(--star); outline-offset: 2px; }
#q:focus { outline: none; border-color: var(--star);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--star) 35%, transparent); }
/* Paper grain: one screenful of SVG fractal noise, tiled over everything by a
   fixed overlay. An overlay rather than a body background so the tooth sits
   on panels and pictures too -- real paper does not stop being paper where
   the ink is. Multiply so it only ever darkens; too faint to see as pattern,
   present enough that the flat tan stops looking like a screen. */
/* The star, sensed more than seen: three teal-green blooms drifting behind
   the parchment on a slow loop. Transform-only animation so it composites on
   the GPU; the blooms are soft-edged gradients rather than blurred layers,
   which costs nothing per frame. Strength lives in --lamp, one number. */
body::before {
  content: ""; position: fixed; inset: -40%; z-index: -1; pointer-events: none;
  background:
    radial-gradient(40% 35% at 25% 30%, #0b6875 0%, transparent 70%),
    radial-gradient(35% 40% at 75% 60%, #2f9d7a 0%, transparent 70%),
    radial-gradient(30% 30% at 55% 20%, #63b7c9 0%, transparent 72%);
  opacity: var(--lamp);
  animation: lamp 90s ease-in-out infinite alternate;
}
@keyframes lamp {
  0%   { transform: rotate(0deg) translate(-4%, -2%) scale(1); }
  50%  { transform: rotate(7deg) translate(3%, 4%) scale(1.18); }
  100% { transform: rotate(-6deg) translate(-2%, 3%) scale(1.06); }
}
@media (prefers-reduced-motion: reduce) {
  body::before { animation: none; }
}
body::after {
  content: ""; position: fixed; inset: 0; z-index: 99;
  pointer-events: none; opacity: .45; mix-blend-mode: soft-light;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.3' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='240' height='240' filter='url(%23n)'/%3E%3C/svg%3E");
}
/* Rough edges for the artwork: a turbulence-displacement filter defined in an
   inline SVG in the shell. Warping the picture's edge makes it sit on the
   paper like something pasted in rather than die-cut. Images and skeleton
   frames only, never blocks with text -- displaced glyphs read as bad
   rendering, not as craft. */
.thumb, img.hero, .filelist .filepic img { filter: url(#roughedge); }
/* Always leave room for the scrollbar. Pages differ in height, so without this
   a short page has no scrollbar and a long one does, the viewport width
   changes by its width on every such navigation, and the whole layout steps
   sideways mid-transition. */
html { scrollbar-gutter: stable; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.65 Georgia, 'Iowan Old Style', 'Palatino Linotype', serif; }
a { color: var(--accent); text-decoration: none; }
/* Links inside prose read as text first: ink with a quiet underline drawn
   as a border, waking to full ink on hover. The gold stays for chrome, link
   lists, and everything outside a paragraph. */
/* !important so tooltip terms inside prose keep the same quiet underline:
   their own border rules load after this sheet and would otherwise win. The
   hover carries it too -- an important base beats a plain hover. */
p a, .within a { color: inherit; text-decoration: none !important;
  border-bottom: 1px solid var(--muted) !important; }
p a:hover, .within a:hover { text-decoration: none !important;
  color: var(--star) !important;
  border-bottom-color: var(--star) !important; }
/* No underline anywhere on hover: the border-bottom treatment below is the
   underline of this site, and the two stacked read as a strikeout gone wrong.
   Instead the star answers: a wide, faint teal glow blooms slowly behind a
   hovered link and lets go quickly when the pointer moves on. The trick is
   two transitions -- the base state's governs the fade-out, the hover
   state's governs the fade-in. */
a { text-shadow: 0 0 1.1em color-mix(in srgb, var(--star) 0%, transparent);
  transition: text-shadow .3s ease; }
a:hover { text-decoration: none !important; color: var(--star);
  text-shadow: 0 0 1.1em color-mix(in srgb, var(--star) 38%, transparent);
  transition: text-shadow 1.6s ease, color .25s ease; }
a.act, .menubtn, .tag {
  box-shadow: 0 0 1em color-mix(in srgb, var(--star) 0%, transparent);
  transition: box-shadow .3s ease; }
a.act:hover, .menubtn:hover, .tag:hover {
  box-shadow: 0 0 1em color-mix(in srgb, var(--star) 25%, transparent);
  transition: box-shadow 1.6s ease; }
/* The star's glint: a thin gradient seam along the very top of the site. */
header.top::before { content: ""; position: absolute; left: 0; right: 0;
  top: 0; height: 2px; background: var(--grad); }
header.top { background: var(--chrome-deep);
  border-bottom: 1px solid var(--line); padding: calc(.45rem + 2px) 1.2rem .45rem;
  display: flex; gap: .3rem 1rem; align-items: center; flex-wrap: wrap; }
header.top .home { white-space: nowrap; }
header.top .home { font-weight: bold; letter-spacing: .02em; }
/* The nav is the one flexible column: it takes the spare width and gives it
   back first, wrapping its own links internally, so the chips and account
   links never get shoved into a stack of their own rows. */
header.top nav { display: flex; gap: .2rem .8rem; flex-wrap: wrap;
  font-size: .85rem; align-items: center; flex: 1 1 auto; min-width: 0; }
.sitenav, header.top .who { flex: none; }
header.top .who { font-size: .75rem; color: var(--muted); }
/* The right-hand cluster: writing actions and the folded-away site pages,
   pushed to the far side so the content links read as their own group. */
.sitenav { margin-left: auto; display: flex; gap: .45rem; align-items: center; }
/* A plain button and a plain panel. This was a <details> first, and the
   user-agent's internal layout for details/summary kept injecting phantom
   height that no CSS of ours could see or remove -- the chip sat 17px below
   its neighbours with a clean DOM. A div obeys ordinary rules. */
.menu { position: relative; display: flex; align-items: center; }
.menubtn { cursor: pointer; font: inherit; font-size: .8rem;
  padding: .12rem .55rem; border: 1px solid var(--line); border-radius: 999px;
  background: var(--panel); color: var(--muted); white-space: nowrap; }
.menubtn[aria-expanded="true"] { border-color: var(--accent);
  color: var(--accent); }
.menupanel[hidden] { display: none; }
.menupanel { position: absolute; right: 0; top: calc(100% + .4rem);
  display: flex; flex-direction: column; min-width: 9rem; z-index: 20;
  background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
  box-shadow: 0 6px 18px rgba(0,0,0,.18); padding: .3rem; }
.menupanel a { padding: .4rem .7rem; border-radius: 4px; font-size: .85rem; }
.menupanel a:hover { background: var(--accent-soft); text-decoration: none; }
/* Writing actions, set apart from the browsing links so "add something" is
   never more than one click away from any page. */
a.act { border: 1px solid var(--line); border-radius: 999px; font-size: .8rem;
  padding: .12rem .55rem; background: var(--panel); white-space: nowrap; }
a.act:hover { background: var(--accent-soft); text-decoration: none; }
a.act .badge { display: inline-block; margin-left: .35rem; padding: 0 .35rem;
  border-radius: 999px; background: var(--accent); color: var(--panel);
  font-size: .75rem; }
/* The search sits in its own band between the nav and the content: part of
   the chrome, not of any page, and the first thing under the header
   everywhere. It scrolls away with the content rather than shadowing it. */
/* The search pins to the top; the nav scrolls away with the page. Mid-read
   the thing you reach for is a search, not the list of kinds. */
.searchbar { background: var(--chrome); position: sticky; top: 0; z-index: 10;
  padding: .4rem 1.2rem .5rem; }
.searchbar { border-bottom: 1px solid var(--line); }
.searchbar .searchwrap { display: flex; gap: .5rem; align-items: center;
  max-width: 44rem; margin: 0 auto; }
.searchbar .qwrap { position: relative; flex: 1; }
/* The writing action lives beside the search, in the star's teal: the two
   things you do from anywhere, side by side. */
.searchbar a.act, h2 a.act { border-color: var(--star); color: var(--star); }
.searchbar a.act:hover, h2 a.act:hover {
  background: color-mix(in srgb, var(--star) 18%, transparent); }
h2 a.act { margin-left: .6rem; font-weight: normal; vertical-align: middle; }
.searchbar #q { display: block; width: 100%; padding: .4rem 2.2rem .4rem .7rem;
  border: 1px solid var(--line); border-radius: 4px; background: var(--bg);
  color: var(--ink); font: inherit; font-size: .9rem; }
/* Our own clear button, shown whenever there is a query. The native one only
   surfaces on hover, which reads as there being no way to clear at all. */
.searchbar #q::-webkit-search-cancel-button { -webkit-appearance: none; }
/* The hotkey's calling card: sits in the empty search field, gone the
   moment the field is focused or holds a query. */
.qkey { position: absolute; left: 9.6rem; top: 50%;
  transform: translateY(-50%); pointer-events: none;
  font-size: .66rem; color: var(--muted); background: var(--panel);
  border: 1px solid var(--line); border-radius: 4px; padding: .06rem .4rem; }
.qwrap:focus-within .qkey, .qwrap.hasq .qkey { display: none; }
#qclear { position: absolute; right: .35rem; top: 50%; transform: translateY(-50%);
  display: none; border: 0; background: none; color: var(--muted);
  font-size: 1.15rem; line-height: 1; padding: .2rem .4rem; cursor: pointer; }
#qclear:hover { color: var(--accent); }
#qclear.show { display: block; }
main { max-width: 46rem; margin: 0 auto; padding: 2rem 1.2rem 5rem; }
/* Entity pages with an aside need room for two columns. Only widened
   when there is genuinely a two-column layout inside, so the guide,
   changelog and index keep the tighter reading measure. */
main:has(.entity.has-side) { max-width: 72rem; }
/* Index pages are card grids, and a grid is the one thing here that gets
   better the more room it has: `auto-fill` just makes more columns. Full
   bleed, with the page padding as the only margin. */
main:has(.grid) { max-width: none; }
h1, h2, h3 { color: var(--accent); }
h1 { font-size: 2.1rem; margin: 0 0 .2rem; line-height: 1.15; }
h2 { font-size: 1.25rem; margin: 2rem 0 .6rem; border-bottom: 1px solid var(--line);
  padding-bottom: .3rem; }
h3 { font-size: 1.05rem; margin: 1.4rem 0 .4rem; }
.kind { color: var(--muted); font-size: .8rem; text-transform: uppercase;
  letter-spacing: .08em; }
.summary { font-style: italic; color: var(--muted); margin: .4rem 0 1.4rem;
  font-size: 1.05rem; }
/* Two-column entity pages on a wide viewport: description on the left, the
   picture with its tags and metadata stacked on the right. On a narrow
   viewport everything stacks in source order -- image, description, metadata
   -- because reading past a wall of tags to reach the description on a phone
   is worse than tags being at the end.

   Gated on `.has-side`: a page with no picture and no metadata flows as one
   column at every width. */
.entity > * + * { margin-top: 1.2rem; }
.entity > .entity-head > *:last-child { margin-bottom: 0; }
.entity-side > *:first-child { margin-top: 0; }
@media (min-width: 64rem) {
  .entity.has-side {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 22rem);
    grid-template-areas: "head head" "main hero" "main side";
    column-gap: 2.5rem;
    align-items: start;
  }
  .entity.has-side > * + * { margin-top: 0; }
  .entity.has-side > .entity-head { grid-area: head; margin-bottom: 1.2rem; }
  .entity.has-side > img.hero     { grid-area: hero; }
  .entity.has-side > .entity-main { grid-area: main; }
  .entity.has-side > .entity-side { grid-area: side; margin-top: 1.2rem; }
  .entity.has-side > .entity-main > :first-child { margin-top: 0; }
  /* The `.meta` margin-top spaces it from a long body in the single-column
     layout. In the aside it and the table's own margin just open a hole
     between the tags and the first row. */
  .entity.has-side > .entity-side .meta { margin-top: 1rem; }
  .entity.has-side > .entity-side .tags { margin-top: 0; }
  .entity.has-side > .entity-side .meta > *:first-child { margin-top: 0; }
  .entity.has-side > .entity-side .meta > *:last-child { margin-bottom: 0; }
}
img.hero { transition: transform .18s ease-out; cursor: zoom-in; }
img.hero { width: 100%; border-radius: 6px; border: 1px solid var(--line);
  display: block; margin: 0 0 1.5rem; }
blockquote { margin: 1rem 0; padding: .5rem 1rem; border-left: 3px solid var(--accent);
  background: var(--accent-soft); }
blockquote p { margin: .3rem 0; }
ul.links { list-style: none; padding: 0; display: flex; flex-wrap: wrap; gap: .5rem; }
ul.links li a { display: inline-block; padding: .25rem .6rem;
  border: 1px solid var(--line); border-radius: 999px; background: var(--panel);
  font-size: .85rem; }
.tags { margin: 1rem 0 0; }
.tag { cursor: pointer; display: inline-block; font-size: .72rem; text-transform: uppercase;
  letter-spacing: .06em; color: var(--muted); border: 1px solid var(--line);
  border-radius: 3px; padding: .1rem .4rem; margin: 0 .3rem .3rem 0; }
.tag:hover { border-color: var(--accent); color: var(--accent); }
.tagpills { margin: .2rem 0 .4rem; display: flex; flex-wrap: wrap; gap: .35rem; }
.pill { font: inherit; font-size: .78rem; cursor: pointer;
  padding: .15rem .6rem; border: 1px solid var(--line); border-radius: 999px;
  background: var(--panel); color: var(--muted); }
.pill.on { border-color: var(--accent); color: var(--accent);
  background: var(--accent-soft); }
.meta { font-size: .8rem; color: var(--muted); margin-top: 2.5rem;
  border-top: 1px solid var(--line); padding-top: .8rem; }
footer.build { max-width: 44rem; margin: 3rem auto 1.5rem; padding: 0 1rem;
  font-size: .72rem; color: var(--muted); text-align: right; }
footer.build code { font-size: inherit; background: none; padding: 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr));
  gap: 1rem; margin: 1rem 0 2rem; }
.card { border: 1px solid var(--line); border-radius: 6px; overflow: hidden;
  background: var(--panel);
  transition: transform .18s ease-out, border-color .3s ease,
              box-shadow .3s ease; }
/* Hovering anywhere on a card lights it and lifts it like a trading card in
   hand; the tilt itself follows the pointer from the script below. Links
   inside keep their own hover treatments on top. */
.card:hover { border-color: var(--star);
  box-shadow: 0 .4em 1.4em color-mix(in srgb, var(--star) 22%, transparent); }
.card:hover .body > a { color: var(--star); }
/* Unless the pointer is on a nested link inside the card -- a tooltip term
   in the summary -- in which case that link alone is teal and the title
   stays gold: two glowing destinations at once would lie about where the
   click goes. */
.card:hover:has(p a:hover) .body > a { color: var(--accent); }
.card { cursor: pointer; }
/* `height: auto` is load-bearing. The markup states width and height so the
   grid can lay out before the pictures arrive, and those attributes land as
   presentational hints; nothing here set `height`, so the hint stood, an
   explicit height beats `aspect-ratio`, and every card rendered 220x400
   instead of square. */
.card img { width: 100%; height: auto; aspect-ratio: 1/1; object-fit: cover;
  display: block; }
.card a.thumb { display: block; }
/* The placeholder thumbnail: kind-agnostic, a big quiet initial on a wash
   of parchment. Goes through the same torn-edge filter as real art, so a
   card without a picture still sits on the page the same way. */
.card a.thumb.noart { display: flex; align-items: center;
  justify-content: center; aspect-ratio: 1 / 1;
  background: linear-gradient(135deg, var(--accent-soft), var(--panel) 75%); }
.card a.thumb.noart svg { width: 42%; height: 42%;
  color: var(--accent); opacity: .45; }
.card.small a.thumb.noart { aspect-ratio: auto; }
.card.small a.thumb.noart svg { width: 1.7rem; height: 1.7rem; }
/* The small variant: thumbnail beside the text, a reference rather than a
   presentation. Same element, same tilt and glow, half the weight. */
.grid.smallgrid { grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: .6rem; }
.card.small { display: flex; align-items: center; }
.card.small a.thumb { flex: 0 0 4.5rem; align-self: stretch; }
.card.small a.thumb img { width: 4.5rem; height: 100%; min-height: 4.5rem;
  aspect-ratio: auto; object-fit: cover; }
.card.small .body { padding: .45rem .65rem; min-width: 0; }
.card.small .body p { display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden; font-size: .75rem; }
.filelist { list-style: none; padding: 0; }
#lightbox { position: fixed; inset: 0; z-index: 200; display: flex;
  align-items: center; justify-content: center; cursor: zoom-out;
  background: rgba(10, 8, 5, .88); }
#lightbox img { max-width: 94vw; max-height: 94vh; border-radius: 4px;
  box-shadow: 0 0 3em rgba(0,0,0,.6); }
.filelist .filepic a { display: block; cursor: zoom-in;
  transition: transform .18s ease-out; }
.filelist .filepic img { display: block; max-width: 100%; border-radius: 6px;
  border: 1px solid var(--line); }
.filelist .filepic .hint { display: block; margin: .3rem 0 1rem; }

/* A card reserves its square before the picture arrives, so the wait is drawn
   as a slow shimmer rather than left as a hole, and the image fades in over it
   instead of snapping into place.

   Everything that hides an image is gated behind `.imgfade`, a class set by one
   line in the head. If that script never runs, the class never appears, every
   picture renders at full opacity, and all that is lost is the animation --
   rather than a page of permanently invisible art, which is what a bare
   `opacity: 0` default would leave behind. */
@keyframes thumb-shimmer {
  from { background-position: 150% 0; }
  to   { background-position: -50% 0; }
}
.thumb {
  background: linear-gradient(90deg,
    var(--accent-soft) 0%, var(--line) 50%, var(--accent-soft) 100%);
  background-size: 200% 100%;
  animation: thumb-shimmer 1.6s linear infinite;
}
/* Stop when the picture is there. Thirty gradients animating forever behind
   opaque images is work the phone does for nobody. */
.thumb.ready { animation: none; background: none; }
/* No per-image fade any more. Fading each image after the page fades in read
   as two loads for one navigation. The whole `#page` fades in as one unit
   instead, once its main picture is ready; the skeleton keeps below-fold
   cards looking intentional while lazy images arrive. */
@media (prefers-reduced-motion: reduce) {
  .thumb { animation: none; }
}

/* The arriving page fades in, so following a link reads as one continuous
   surface rather than a hard cut to a new document.

   Only the arriving page. Cross-document `@view-transition` was here and is
   deliberately gone: it crossfades by animating the outgoing page out, and
   when the browser abandons that partway -- which it does whenever the next
   document is not ready in time -- the old page fades, snaps back, and only
   then gets replaced. Three visible states for one navigation, and no way from
   here to make the abort reliable. A one-directional fade cannot do that,
   because there is no outgoing animation to interrupt.

   `main` rather than `body`: the header is `position: sticky`, and an
   animating ancestor is how sticky quietly stops sticking. */
/* One steady fade for the whole `#page`, gated on a `ready` class the router
   sets after preloading the hero. Cubic-bezier rather than `ease-out` gives a
   softer settle at the end -- the change reads as arrival, not a snap.

   Class-driven rather than a CSS animation because a keyframe fires on every
   element insertion, and the router needs to hold the reveal for a beat while
   the hero decodes. `.imgfade` guards the whole thing: with JS off, no class
   is added, `#page` is visible immediately, and the site works. */
.imgfade #page:not(.ready) > :not(.entity),
.imgfade #page:not(.ready) .entity > * { opacity: 0; }
.imgfade #page > :not(.entity),
.imgfade #page .entity > * {
  /* Two transitions, paired with two delays below: the reveal owns opacity,
     the tilt owns transform. One shorthand here without transform was wiping
     the hero's tilt transition -- it snapped while cards eased, because
     cards sit deeper than the staggered children. */
  transition: opacity 1s cubic-bezier(.4, 0, .2, 1),
              transform .18s ease-out;
}
/* Sections arrive in order, each a tenth behind the one before, so the page
   reads top-to-bottom as it appears. On an entity page the sections are the
   article's regions -- head, picture, body, metadata -- because the article
   wrapper itself is one child of `#page` and staggering that alone would be
   no stagger at all. The `transition-delay` rules must follow the shorthand
   above: a `transition:` shorthand resets delay to zero.

   First child needs no rule (zero delay); past the eighth everything shares
   the tail delay rather than drifting later forever. */
.imgfade #page > :not(.entity):nth-child(2),
.imgfade #page .entity > :nth-child(2) { transition-delay: 0.1s, 0s; }
.imgfade #page > :not(.entity):nth-child(3),
.imgfade #page .entity > :nth-child(3) { transition-delay: 0.2s, 0s; }
.imgfade #page > :not(.entity):nth-child(4),
.imgfade #page .entity > :nth-child(4) { transition-delay: 0.3s, 0s; }
.imgfade #page > :not(.entity):nth-child(5),
.imgfade #page .entity > :nth-child(5) { transition-delay: 0.4s, 0s; }
.imgfade #page > :not(.entity):nth-child(6),
.imgfade #page .entity > :nth-child(6) { transition-delay: 0.5s, 0s; }
.imgfade #page > :not(.entity):nth-child(7),
.imgfade #page .entity > :nth-child(7) { transition-delay: 0.6s, 0s; }
.imgfade #page > :not(.entity):nth-child(8),
.imgfade #page .entity > :nth-child(8) { transition-delay: 0.7s, 0s; }
.imgfade #page > :not(.entity):nth-child(n+9),
.imgfade #page .entity > :nth-child(n+9) { transition-delay: .7s, 0s; }
/* The outgoing page. The router adds `leaving` on click, waits out the short
   fade, and only then swaps. The whole page leaves as one piece -- staggering
   an exit would just delay the reader -- and quick on the way out, slow on
   the way in: leaving should feel like acknowledgement, arriving like a
   settle. */
.imgfade #page.leaving { opacity: 0; transition: opacity .18s ease-in; }
@media (prefers-reduced-motion: reduce) {
  .imgfade #page:not(.ready) > :not(.entity),
  .imgfade #page:not(.ready) .entity > * { opacity: 1; }
  .imgfade #page > :not(.entity),
  .imgfade #page .entity > * { transition: none; }
  .imgfade #page.leaving { opacity: 1; transition: none; }
}
.card .body { padding: .6rem .7rem; }
.card .body > a { font-weight: bold; }
.card .body p { margin: .2rem 0 0; font-size: .8rem; color: var(--muted); }
.card .body p.contains { font-size: .72rem; color: var(--accent);
  font-variant: small-caps; letter-spacing: .04em; }
#results .hit { padding: .5rem .4rem; border-bottom: 1px solid var(--line); }
#results .hit.sel { background: var(--accent-soft); border-radius: 4px; }
#results .hit { position: relative; }
/* Absolutely placed, not floated: a float lands after the row's last block
   and rendered below the highlight instead of inside it. */
#results .hit.sel::after { content: "↵"; position: absolute;
  right: .6rem; top: 50%; transform: translateY(-50%);
  color: var(--muted); font-size: .8rem; }
#results .kbdhints { float: right; font-weight: normal; font-size: .7rem;
  color: var(--muted); }
#results kbd { font-family: inherit; font-size: .66rem;
  border: 1px solid var(--line); border-radius: 4px; padding: .02rem .3rem;
  background: var(--panel); margin: 0 .1rem; }
#results .hit p { margin: .1rem 0 0; font-size: .85rem; color: var(--muted); }
.empty { color: var(--muted); font-style: italic; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .9rem; }
th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid var(--line); }
.secret { border-left: 3px solid var(--accent); background: var(--accent-soft);
  padding: .6rem 1rem; margin: 1rem 0; border-radius: 0 4px 4px 0; }
.secret .who { font-size: .7rem; text-transform: uppercase; letter-spacing: .08em;
  color: var(--accent); display: block; margin-bottom: .3rem; }
form.auth { max-width: 22rem; }
form.auth label { display: block; margin: .9rem 0 .2rem; font-size: .85rem;
  color: var(--muted); }
form.auth input, form.auth select { width: 100%; padding: .5rem .6rem; border: 1px solid var(--line);
  border-radius: 4px; background: var(--panel); color: var(--ink); font: inherit; }
/* The submit is the star's teal; the pills opt out below, because the
   generic form-button gold was swallowing them into a row of shouting
   chips. */
form.auth button { margin-top: 1.2rem; padding: .55rem 1.2rem; border: 0;
  border-radius: 4px; background: var(--star); color: #10262a; font: inherit;
  font-weight: bold; cursor: pointer; }
form.auth button.pill { margin-top: 0; padding: .15rem .6rem;
  font-weight: normal; font-size: .78rem;
  border: 1px solid var(--line); border-radius: 999px;
  background: var(--panel); color: var(--muted); }
form.auth button.pill.on { border-color: var(--accent); color: var(--accent);
  background: var(--accent-soft); }
form.danger { margin-top: 2.5rem; border-top: 1px solid var(--line);
  padding-top: 1rem; }
.dangerbtn { font: inherit; font-size: .85rem; cursor: pointer;
  color: #ffb4ab; background: #3b1512; border: 1px solid #5c221d;
  border-radius: 4px; padding: .35rem .8rem; }
.dangerbtn:hover { border-color: #ffb4ab; }
.error { color: #ffb4ab; background: #3b1512; border: 1px solid #5c221d;
  padding: .6rem .8rem; border-radius: 4px; margin: 1rem 0; font-size: .9rem; }
.hint { color: var(--muted); font-size: .85rem; }
.guide h1 { margin-top: 0; }
.guide h2 { margin-top: 2.4rem; }
.guide pre { background: var(--panel); border: 1px solid var(--line);
  border-radius: 4px; padding: .8rem 1rem; overflow-x: auto; font-size: .8rem;
  line-height: 1.5; font-family: ui-monospace, Consolas, monospace;
  white-space: pre-wrap; word-break: break-word; }
.guide code { background: var(--accent-soft); padding: .1rem .3rem;
  border-radius: 3px; font-size: .85em;
  font-family: ui-monospace, Consolas, monospace; }
.guide pre code { background: none; padding: 0; font-size: inherit; }
.guide hr { border: 0; border-top: 1px solid var(--line); margin: 2.5rem 0; }
.guide blockquote { font-style: italic; }
.guide table { font-size: .85rem; }
.guide li { margin: .3rem 0; }
a.edit { float: right; font-size: .8rem; text-transform: none;
  letter-spacing: 0; border: 1px solid var(--line); border-radius: 4px;
  padding: .1rem .5rem; background: var(--panel); }
form.auth.wide { max-width: 46rem; }
form.auth textarea { width: 100%; padding: .5rem .6rem; border: 1px solid var(--line);
  border-radius: 4px; background: var(--panel); color: var(--ink);
  font: inherit; font-size: .9rem; line-height: 1.5; resize: vertical;
  font-family: ui-monospace, Consolas, monospace; }
form.auth label .hint { display: block; font-weight: normal; margin-top: .1rem; }
fieldset.secretbox { margin: 1.6rem 0 0; border: 1px solid var(--line);
  border-radius: 4px; padding: .6rem 1rem 1rem; }
fieldset.secretbox legend { font-size: .85rem; color: var(--accent);
  padding: 0 .4rem; }
.cbs { display: flex; flex-wrap: wrap; gap: .8rem; margin-top: .6rem; }
label.cb { display: inline-flex; align-items: center; gap: .3rem; margin: 0;
  font-size: .85rem; color: var(--ink); }
label.cb input { width: auto; }
.notice { border-left: 3px solid var(--accent); background: var(--accent-soft);
  padding: .6rem 1rem; margin: 1rem 0; font-size: .9rem; border-radius: 0 4px 4px 0; }
.newpage { float: right; font-size: .85rem; }
.whogrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: .7rem; margin: 1.4rem 0; }
button.who.on { border-color: var(--accent); background: var(--accent-soft); }
button.who { display: flex; flex-direction: column; gap: .15rem; text-align: left;
  padding: .8rem 1rem; border: 1px solid var(--line); border-radius: 6px;
  background: var(--panel); color: var(--ink); font: inherit; cursor: pointer; }
button.who:hover { border-color: var(--accent); }
button.who .n { font-weight: bold; }
button.who .c { font-size: .8rem; color: var(--muted); }
details.newperson { margin-top: 2rem; border-top: 1px solid var(--line);
  padding-top: 1rem; }
details.newperson summary { cursor: pointer; color: var(--accent);
  font-size: .9rem; }
.artgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
  gap: .8rem; margin: 1rem 0; }
.artgrid figure { margin: 0; border: 1px solid var(--line); border-radius: 6px;
  overflow: hidden; background: var(--panel); }
.artgrid .thumb { display: block; }
.artgrid img { width: 100%; display: block; aspect-ratio: 1/1; object-fit: cover; }
.artgrid button { width: 100%; border: 0; border-top: 1px solid var(--line);
  padding: .45rem; background: var(--panel); color: var(--accent); font: inherit;
  font-size: .85rem; cursor: pointer; }
.artgrid button:hover { background: var(--accent-soft); }
.artgrid figure.current { border-color: var(--accent); }
.artgrid figure.current button { color: var(--muted); cursor: default; }
.slow { border-left: 3px solid var(--accent); background: var(--accent-soft);
  padding: .6rem 1rem; margin: 1rem 0; font-size: .9rem; border-radius: 0 4px 4px 0; }
/* Uploaded files */
ul.filelist { list-style: none; padding: 0; }
ul.filelist li { padding: .35rem 0; border-bottom: 1px solid var(--line); }
.filerow { display: flex; gap: .8rem; align-items: center; padding: .6rem .8rem;
  border: 1px solid var(--line); border-radius: 6px; background: var(--panel);
  margin: .5rem 0; }
.filerow img { width: 3.5rem; height: 3.5rem; object-fit: cover; border-radius: 4px; }
.filerow .what { flex: 1; display: flex; flex-direction: column; }
input[type=file] { font: inherit; font-size: .9rem; padding: .4rem 0; }
/* Structure editor */
.kindrow { display: flex; gap: .6rem; flex-wrap: wrap; align-items: center;
  padding: .5rem .7rem; border: 1px solid var(--line); border-radius: 6px;
  background: var(--panel); margin: .4rem 0; }
.kindrow code { background: var(--accent-soft); padding: .1rem .4rem;
  border-radius: 3px; font-size: .85rem; }
form.inline { display: inline-flex; gap: .4rem; align-items: center; margin: 0; }
form.inline input, form.inline select { padding: .25rem .4rem; font: inherit;
  font-size: .85rem; border: 1px solid var(--line); border-radius: 4px;
  background: var(--bg); color: var(--ink); width: auto; }
form.inline button { border: 1px solid var(--line); border-radius: 4px;
  padding: .25rem .7rem; background: var(--bg); color: var(--ink); font: inherit;
  font-size: .85rem; cursor: pointer; }
form.inline button:hover { background: var(--accent-soft); }
/* Discord inbox */
.tabs { display: flex; gap: .8rem; flex-wrap: wrap; font-size: .85rem;
  border-bottom: 1px solid var(--line); padding-bottom: .5rem; margin: 1rem 0; }
.tabs a.on { color: var(--ink); font-weight: bold; }
form.catchup { margin: 2rem 0 0; }
form.catchup button { border: 1px solid var(--line); border-radius: 4px;
  padding: .4rem .9rem; background: var(--panel); color: var(--muted);
  font: inherit; font-size: .85rem; cursor: pointer; }
form.catchup button:hover { color: var(--ink); background: var(--accent-soft); }
.msg { border: 1px solid var(--line); border-radius: 6px; background: var(--panel);
  padding: .8rem 1rem; margin: .8rem 0; }
.msg .meta { font-size: .8rem; color: var(--muted); display: flex; gap: .5rem;
  flex-wrap: wrap; align-items: baseline; }
.msg .meta .chan { color: var(--accent); }
.msg .text { margin: .5rem 0 0; white-space: pre-wrap; }
.msg .shots { display: flex; gap: .5rem; flex-wrap: wrap; margin-top: .6rem; }
.msg .shots img { max-height: 11rem; border-radius: 4px; border: 1px solid var(--line); }
.msg .acts { margin-top: .7rem; display: flex; gap: .8rem; align-items: center;
  font-size: .85rem; }
.msg form { display: inline; }
.msg button { border: 1px solid var(--line); border-radius: 4px; padding: .25rem .7rem;
  background: var(--bg); color: var(--ink); font: inherit; font-size: .85rem;
  cursor: pointer; }
.msg button:hover { background: var(--accent-soft); }
.sheet { border: 1px solid var(--line); border-radius: 6px; padding: .9rem 1.1rem;
  margin: 2rem 0 0; background: var(--panel); }
.sheet .statline { font-size: .85rem; color: var(--muted); text-transform: uppercase;
  letter-spacing: .06em; margin-bottom: .5rem; }
/* The sheet link is a d20 now, not a sentence: the hint below already
   explains where the numbers live, and the die says "roll here". Brand red,
   the one non-palette color on the site, because recognition is the point. */
a.sheetlink { display: inline-flex; padding: .35rem; border-radius: 6px;
  color: #e40712; border: 1px solid var(--line); background: var(--panel); }
a.sheetlink svg { width: 1.9rem; height: 1.9rem; }
a.sheetlink:hover { text-decoration: none; border-color: #e40712; }
.sheet .hint { margin: .6rem 0 0; }
.copyblock { position: relative; margin: 1rem 0; }
.copyblock pre { background: var(--panel); border: 1px solid var(--line);
  border-radius: 4px; padding: .8rem 1rem; overflow-x: auto; font-size: .8rem;
  line-height: 1.5; white-space: pre-wrap; word-break: break-word;
  font-family: ui-monospace, Consolas, monospace; }
.copyblock button { position: absolute; top: .5rem; right: .5rem;
  padding: .25rem .6rem; font-size: .75rem; border: 1px solid var(--line);
  border-radius: 4px; background: var(--bg); color: var(--ink); cursor: pointer; }

/* The connect page is one block to copy, with the per-client recipes folded
   underneath. The fold has to look pressable: a summary that reads as a
   heading gets treated as one, and nobody finds what is under it. */
details { margin: 2rem 0 1rem; border-top: 1px solid var(--line);
  padding-top: 1rem; }
details > summary { cursor: pointer; font-size: .9rem; color: var(--muted);
  list-style: none; user-select: none; }
details > summary::-webkit-details-marker { display: none; }
details > summary::before { content: "\\25B8 "; display: inline-block;
  width: 1em; transition: transform .15s; }
details[open] > summary::before { transform: rotate(90deg); }
details > summary:hover { color: var(--ink); }
details h2 { font-size: 1rem; margin-top: 1.6rem; }

/* Where you are: Copper Vale > Valeshire > the tavern. Above the title and
   quieter than it, because it is orientation rather than the subject.
   No real page names in here: this stylesheet is embedded in every response
   including the sign-in page, and one of the pub names is also the passphrase. */
.trail { font-size: .85rem; color: var(--muted); margin: 0 0 .3rem; }
.trail a { color: var(--muted); text-decoration: none; }
.trail a:hover { color: var(--accent); text-decoration: underline; }
.kind a.kindlink { color: inherit; text-decoration: none; }
.kind a.kindlink:hover { color: var(--accent); text-decoration: underline; }

/* What a place contains. Summaries inline, because a list of fifteen shop
   names tells you much less than a list of fifteen shops. */
ul.within { list-style: none; padding: 0; margin: .4rem 0 0; }
ul.within li { padding: .35rem 0; border-bottom: 1px solid var(--line); }
ul.within li:last-child { border-bottom: none; }
ul.within .hint { display: block; margin-top: .1rem; }

/* The review page: the whole world as a shape, with the guesses marked. */
ul.shape { list-style: none; padding: 0; margin: 1rem 0; }
ul.shape li { padding: .2rem 0; font-size: .9rem; }
ul.shape .fix { margin-left: .6rem; font-size: .75rem; color: var(--muted);
  text-decoration: none; opacity: 0; }
ul.shape li:hover .fix { opacity: 1; }
ul.shape .fix:hover { color: var(--accent); text-decoration: underline; }
ul.shape .guess { margin-left: .6rem; font-size: .7rem; color: var(--muted);
  border: 1px solid var(--line); border-radius: 3px; padding: 0 .3rem; }
"""

SEARCH_JS = """
// Read the index per query, never once at load. This script is inline, so it
// runs while the page is still parsing; on the live server the index arrives
// separately from search.js, which is deferred and has not run yet. Capturing
// it here left every search reading an empty list and saying nothing matched.
const idx = () => window.__INDEX__ || [];
// Rank by where the term hit: an exact name beats a passing mention in a body.
// Without this the order is whatever the index is in, which is alphabetical by
// ref, so `archive/` pages sort above the page you actually searched for.
const rank = (e, t) => {
  const n = (e.n || '').toLowerCase();
  if (n === t) return 0;
  if (n.startsWith(t)) return 1;
  if (n.includes(t)) return 2;
  return (e.s || '').toLowerCase().includes(t) ? 3 : 4;
};
const q = document.getElementById('q');
const results = document.getElementById('results');
if (q) {
  // Keyboard selection: arrows walk the hits, Enter opens the one selected
  // (or the first, which makes search-type-enter the fast path to a page).
  let sel = -1;
  const hitLinks = () => [...results.querySelectorAll('.hit a')];
  const paint = () => {
    results.querySelectorAll('.hit').forEach((h, i) =>
      h.classList.toggle('sel', i === sel));
    const on = results.querySelectorAll('.hit')[sel];
    if (on) on.scrollIntoView({ block: 'nearest' });
  };
  const render = term => {
    sel = -1;
    // Read `#page` fresh, not once at load: the router replaces it, and a
    // captured reference points at a detached node after the first swap.
    const page = document.getElementById('page');
    const t = term.trim().toLowerCase();
    if (!t) { results.innerHTML=''; results.hidden=true;
              if (page) page.hidden=false; return; }
    const hits = idx().filter(e => e.h.includes(t))
      .map(e => [rank(e, t), e])
      .sort((a, b) => a[0] - b[0] || a[1].n.length - b[1].n.length)
      .map(pair => pair[1]).slice(0, 40);
    results.hidden = false;
    if (page) page.hidden = true;
    results.innerHTML = hits.length
      ? '<h2>' + hits.length + ' result' + (hits.length===1?'':'s') +
        '<span class="kbdhints"><kbd>&#8595;</kbd><kbd>&#8593;</kbd> move' +
        ' &middot; <kbd>&#8629;</kbd> open</span></h2>' +
        hits.map(e => '<div class="hit"><a href="' + BASE + e.u + '">' + e.n +
          '</a> <span class="kind">' + e.k + '</span><p>' + e.s + '</p></div>').join('')
      : '<p class="empty">Nothing matches that.</p>';
    if (hits.length) { sel = 0; paint(); }
  };
  const qclear = document.getElementById('qclear');
  const syncClear = () => {
    if (qclear) qclear.classList.toggle('show', !!q.value);
    const wrap = q.closest('.qwrap');
    if (wrap) wrap.classList.toggle('hasq', !!q.value);
  };
  // Enter with nothing focused jumps to the search: the keyboard's way of
  // reaching for the bar at the top. Anything interactive keeps its Enter
  // -- a focused link still navigates, a button still fires.
  document.addEventListener('keydown', e => {
    if (e.key !== 'Enter' || e.metaKey || e.ctrlKey || e.altKey) return;
    const el = document.activeElement;
    if (el && el !== document.body &&
        (el.isContentEditable ||
         /^(A|BUTTON|INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
    e.preventDefault();
    q.focus();
    q.select();
  });
  q.addEventListener('input', () => { render(q.value); syncClear(); });
  q.addEventListener('keydown', e => {
    if (e.key==='Escape') { q.value=''; render(''); syncClear(); return; }
    if (results.hidden) return;
    const n = hitLinks().length;
    if (e.key === 'ArrowDown' && n) {
      sel = Math.min(sel + 1, n - 1); paint(); e.preventDefault();
    } else if (e.key === 'ArrowUp' && n) {
      sel = Math.max(sel - 1, -1); paint(); e.preventDefault();
    } else if (e.key === 'Enter' && n) {
      hitLinks()[Math.max(sel, 0)].click(); e.preventDefault();
    }
  });
  if (qclear) qclear.addEventListener('click', () => {
    q.value=''; render(''); syncClear(); q.focus(); });
  // A tag is a search the page already wrote: clicking one runs it. The
  // index includes tags in its haystack, so the term finds every page
  // carrying the tag. Delegated, so tags on router-swapped pages count.
  document.addEventListener('click', e => {
    const t = e.target.closest('.tag');
    if (!t) return;
    q.value = t.textContent.trim();
    render(q.value); syncClear();
    window.scrollTo(0, 0);
  });
}
"""


# Marks each picture once it has actually decoded, and stops the shimmer behind
# it. Runs after the images are in the DOM; anything still loading keeps its
# skeleton until its own `load` fires, which for a lazy image is when it is
# scrolled near.
NAV_JS = """
/* Client-side navigation: intercept clicks on same-origin `/wiki/` links,
   fetch the next page, swap the content region.

   Progressive enhancement, not an app rewrite. Every page still renders on the
   server, still works with JS off, still bookmarks and view-sources correctly.
   The router is a shim on top that keeps the document alive across clicks, so
   the header does not have to be torn down and reborn between pages -- which
   is what made a navigation read as a flash regardless of what CSS animation
   we asked for.

   Only `#page` moves. The header, footer, and the tooltip/search listeners on
   `document` all stay put. Redirects fall through to a real navigation, so
   sign-out, session expiry and the gate never leave the browser looking at a
   header from the wrong session. */
(function(){
if(!window.history||!window.history.pushState||!window.DOMParser)return;

var savedScroll={};

function localWikiUrl(a,e){
  if(e.defaultPrevented||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return null;
  if(e.button!==0)return null;
  if(a.target||a.hasAttribute('download')||a.hasAttribute('data-full-nav'))return null;
  var u; try{u=new URL(a.href,location.origin);}catch(x){return null;}
  if(u.origin!==location.origin)return null;
  if(u.pathname.indexOf('/wiki/')!==0)return null;
  /* Downloads and raw images are not pages: fetching a 2MB attachment,
     failing to find #page in it, and stopping is a click that does nothing.
     The browser handles these natively. */
  if(u.pathname.indexOf('/wiki/file/')===0)return null;
  if(u.pathname.indexOf('/wiki/art/')===0)return null;
  /* Same-page hash link: let the browser scroll. Nothing to fetch. */
  if(u.pathname===location.pathname&&u.search===location.search&&u.hash)return null;
  return u;
}

document.addEventListener('click',function(e){
  /* The site menu: the button toggles it; any other click closes it --
     including its own links, which the router handles without a page load,
     so nothing else would ever shut it. */
  var mb=e.target.closest?e.target.closest('.menubtn'):null;
  document.querySelectorAll('.menu .menupanel:not([hidden])').forEach(function(pn){
    if(!mb||!pn.parentElement.contains(mb)){
      pn.hidden=true;
      pn.parentElement.querySelector('.menubtn').setAttribute('aria-expanded','false');
    }
  });
  if(mb){
    var pn=mb.parentElement.querySelector('.menupanel');
    pn.hidden=!pn.hidden;
    mb.setAttribute('aria-expanded', pn.hidden?'false':'true');
    return;
  }
  var a=e.target.closest?e.target.closest('a'):null;
  if(!a||!a.getAttribute('href'))return;
  var u=localWikiUrl(a,e); if(!u)return;
  e.preventDefault();
  savedScroll[location.href]=window.scrollY;
  go(u.href,true);
});

window.addEventListener('popstate',function(){ go(location.href,false); });

/* Forms marked dangerous ask before they act. */
document.addEventListener('submit',function(e){
  var f=e.target;
  if(f.classList&&f.classList.contains('danger')&&
     !window.confirm(f.getAttribute('data-confirm')||'Are you sure?'))
    e.preventDefault();
});

/* Warm the browser cache for the pictures that will be on screen when the
   next page arrives, so the swap-in reads as one arrival rather than "page,
   then image". The hero is always above the fold if it exists; eager card
   images (not `loading="lazy"`) tend to be above the fold too. Everything
   else stays lazy and shows its skeleton on the way in, which is what
   skeletons are for.

   Racing against a timer, because one slow or broken picture must not hold
   the whole navigation up: about a second is short enough to feel like an
   attentive click and long enough for a cold WEBP over a home line. */
function preloadAbove(incoming){
  var urls=[];
  var hero=incoming.querySelector('img.hero');
  if(hero&&hero.getAttribute('src')) urls.push(hero.getAttribute('src'));
  var eager=incoming.querySelectorAll('img:not([loading="lazy"])');
  for(var j=0;j<eager.length&&urls.length<8;j++){
    var src=eager[j].getAttribute('src');
    if(src&&urls.indexOf(src)<0) urls.push(src);
  }
  if(!urls.length) return Promise.resolve();
  var jobs=urls.map(function(u){return new Promise(function(res){
    var i=new Image(); i.onload=res; i.onerror=res; i.src=u;
  });});
  return Promise.race([
    Promise.all(jobs),
    new Promise(function(res){ setTimeout(res,900); })
  ]);
}

function go(url,push){
  /* Hovered tooltips do not survive their anchor being removed. Hide any
     visible tip before the swap so it does not linger over the next page. */
  if(window.__tipsHide) window.__tipsHide();
  /* Fade the old page out while the fetch runs, and never swap before the
     fade has had its moment. The timer rather than `transitionend`, which
     does not fire for a tab in the background and would wedge the click. */
  var leaving=document.getElementById('page');
  if(leaving) leaving.classList.add('leaving');
  var fadedOut=new Promise(function(res){ setTimeout(res,200); });
  fetch(url,{credentials:'same-origin',headers:{'Accept':'text/html'}})
    .then(function(r){
      /* A redirect means the session changed or the gate is up. Full-nav to
         the destination rather than swapping content under a stale header. */
      if(r.redirected){ location.href=r.url; return null; }
      if(!r.ok) throw new Error('status '+r.status);
      return r.text();
    })
    .then(function(html){
      if(html===null) return null;
      var doc=new DOMParser().parseFromString(html,'text/html');
      var incoming=doc.getElementById('page');
      /* Anything without a #page is not swappable -- a download, an export,
         a future route this script has not heard of. Full navigation, never
         a silent nothing. */
      if(!incoming){ location.href=url; return null; }
      /* Preload BEFORE swapping. The old page stays put on screen while the
         browser warms its cache; the swap then reads as arrival, not blank. */
      return preloadAbove(incoming).then(function(){ return {doc:doc,incoming:incoming}; });
    })
    .then(function(payload){
      if(!payload) return null;
      return fadedOut.then(function(){ return payload; });
    })
    .then(function(payload){
      if(!payload) return;
      var current=document.getElementById('page');
      if(!current){ location.href=url; return; }
      if(payload.doc.title) document.title=payload.doc.title;
      /* Arriving anywhere dismisses the search: the query is cleared, the
         results list is emptied and hidden. Without this, navigating from a
         result kept the results on screen and the arriving page hidden --
         the search UI owns `#page.hidden`, and the incoming element must
         not inherit a hidden world. */
      var q=document.getElementById('q');
      if(q) q.value='';
      var qc=document.getElementById('qclear');
      if(qc) qc.classList.remove('show');
      var qw=q&&q.closest?q.closest('.qwrap'):null;
      if(qw) qw.classList.remove('hasq');
      var res=document.getElementById('results');
      if(res){ res.hidden=true; res.innerHTML=''; }
      payload.incoming.hidden=false;
      current.replaceWith(payload.incoming);
      if(push) history.pushState({url:url},'',url);
      var y=savedScroll[url]; window.scrollTo(0,typeof y==='number'?y:0);
      if(window.__imgFadeInit) window.__imgFadeInit(payload.incoming);
      /* The tooltip walker runs once on load, scoped to the initial `#page`.
         Swapped-in content needs the same treatment or nothing lights up. */
      if(window.__tipsWalk) window.__tipsWalk(payload.incoming);
      /* Two frames of settle before revealing: one for insert, one for the
         browser to acknowledge the images are decoded. Without this, the
         transition sometimes starts from `.ready` and never plays. */
      requestAnimationFrame(function(){
        requestAnimationFrame(function(){ payload.incoming.classList.add('ready'); });
      });
      /* Move focus for a11y and to reset tab order onto the new page. */
      var h1=payload.incoming.querySelector('h1');
      if(h1){ h1.tabIndex=-1; h1.focus({preventScroll:true}); }
    })
    .catch(function(){ location.href=url; });
}
})();
"""


TUNER_JS = """
/* The paper tuner: sliders over the grain and rough-edge parameters, live.
   A tuning aid, not a feature -- the panel only appears with `?tune` in the
   URL, but saved values apply on every page load so the whole site can be
   judged while tuned. `Copy` puts the numbers on the clipboard to be baked
   into the stylesheet, `Reset` returns to what ships. Live server only. */
(function(){
var KEY='paper-tuner';
var saved={}; try{saved=JSON.parse(localStorage.getItem(KEY))||{};}catch(e){}
var DEF={go:0.45, gf:0.3, es:4, ef:0.045};
var v={}; for(var k in DEF) v[k]=(typeof saved[k]==='number')?saved[k]:DEF[k];
var st=document.createElement('style'); document.head.appendChild(st);
function noise(f){
  return 'url("data:image/svg+xml,'+encodeURIComponent(
    "<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>"+
    "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='"+f+
    "' numOctaves='2' stitchTiles='stitch'/></filter>"+
    "<rect width='240' height='240' filter='url(#n)'/></svg>")+'")';
}
function apply(){
  st.textContent='body::after{opacity:'+v.go+' !important;'+
                 'background-image:'+noise(v.gf)+' !important}';
  var d=document.querySelector('#roughedge feDisplacementMap');
  if(d) d.setAttribute('scale',v.es);
  var t=document.querySelector('#roughedge feTurbulence');
  if(t) t.setAttribute('baseFrequency',v.ef.toFixed(3)+' '+(v.ef*1.5).toFixed(3));
  localStorage.setItem(KEY,JSON.stringify(v));
}
apply();
if(!/[?&#]tune/.test(location.search+location.hash)) return;

var css=document.createElement('style');
css.textContent='#tuner{position:fixed;right:1rem;bottom:1rem;z-index:1000;'+
'background:var(--panel);border:1px solid var(--line);border-radius:8px;'+
'padding:.8rem 1rem 1rem;font-size:.78rem;width:16rem;'+
'box-shadow:0 6px 18px rgba(0,0,0,.25)}'+
'#tuner h3{margin:0 0 .2rem;font-size:.85rem}'+
'#tuner label{display:block;margin:.5rem 0 .1rem;color:var(--muted)}'+
'#tuner .val{float:right;color:var(--ink);font-variant-numeric:tabular-nums}'+
'#tuner input[type=range]{width:100%;margin:0}'+
'#tuner button{margin:.7rem .5rem 0 0;font:inherit;padding:.2rem .6rem;'+
'border:1px solid var(--line);border-radius:4px;background:var(--accent-soft);'+
'color:var(--ink);cursor:pointer}';
document.head.appendChild(css);

var P=document.createElement('div'); P.id='tuner';
P.innerHTML='<h3>Paper</h3>';
function row(label,key,min,max,step){
  var l=document.createElement('label');
  l.textContent=label;
  var out=document.createElement('span'); out.className='val';
  out.textContent=v[key]; l.appendChild(out);
  var r=document.createElement('input');
  r.type='range'; r.min=min; r.max=max; r.step=step; r.value=v[key];
  r.addEventListener('input',function(){
    v[key]=parseFloat(r.value); out.textContent=r.value; apply();
  });
  P.appendChild(l); P.appendChild(r);
  return function(){ r.value=v[key]; out.textContent=v[key]; };
}
var syncs=[
  row('grain strength','go',0,0.5,0.01),
  row('grain fineness','gf',0.15,1.4,0.05),
  row('edge roughness','es',0,14,1),
  row('edge wobble','ef',0.005,0.09,0.005),
];
var copy=document.createElement('button'); copy.textContent='Copy values';
copy.addEventListener('click',function(){
  var txt='grain opacity '+v.go+', grain baseFrequency '+v.gf+
          ', edge scale '+v.es+', edge baseFrequency '+v.ef.toFixed(3)+
          ' '+(v.ef*1.5).toFixed(3);
  (navigator.clipboard&&navigator.clipboard.writeText)?
    navigator.clipboard.writeText(txt).then(function(){copy.textContent='Copied';}):
    (copy.textContent=txt);
});
var reset=document.createElement('button'); reset.textContent='Reset';
reset.addEventListener('click',function(){
  localStorage.removeItem(KEY);
  for(var k in DEF) v[k]=DEF[k];
  apply(); syncs.forEach(function(f){f();}); copy.textContent='Copy values';
});
P.appendChild(copy); P.appendChild(reset);
document.body.appendChild(P);
})();
"""


TILT_JS = """
/* The trading-card tilt: each card -- and each standalone picture, the
   hero on a page and the attachments in Files -- leans toward the pointer,
   a few degrees
   of perspective rotation that tracks as the mouse moves and eases back on
   the way out. Delegated from the document so cards swapped in by the
   router tilt without rebinding, throttled to one transform per frame.
   Touch screens and reduced-motion readers never see it. */
(function(){
if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
if(matchMedia('(hover: none)').matches)return;
var SEL='.card, img.hero, .filelist .filepic a';
var card=null,ev=null,raf=0;
function apply(){
  raf=0;
  if(!card||!ev)return;
  var b=card.getBoundingClientRect();
  var px=(ev.clientX-b.left)/b.width-.5;
  var py=(ev.clientY-b.top)/b.height-.5;
  card.style.transform='perspective(40rem) rotateX('+(-py*5).toFixed(2)+
    'deg) rotateY('+(px*5).toFixed(2)+'deg) translateY(-2px)';
}
document.addEventListener('pointermove',function(e){
  var c=e.target.closest?e.target.closest(SEL):null;
  if(c!==card){ if(card)card.style.transform=''; card=c; }
  if(!c)return;
  ev=e;
  if(!raf)raf=requestAnimationFrame(apply);
},{passive:true});
document.addEventListener('pointerout',function(e){
  if(card&&!e.relatedTarget){ card.style.transform=''; card=null; }
},{passive:true});
})();

/* The whole card is the link, not just its title: a card with no art is
   otherwise mostly dead surface, and the tilt and glow already promise the
   click. Nested links -- tooltip terms in the summary -- keep their own
   destinations; only a click on the card's inert parts follows the title. */
(function(){
document.addEventListener('click',function(e){
  if(e.defaultPrevented||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;
  if(e.button!==0)return;
  if(e.target.closest&&e.target.closest('a,button'))return;
  var card=e.target.closest?e.target.closest('.card'):null;
  if(!card)return;
  var title=card.querySelector('.body > a');
  if(title)title.click();
});
})();

/* Image attachments open full screen instead of downloading: the click is
   a look, and the download still exists for anyone without scripts or via
   the browser's save-image. Non-image files keep their download click.
   The big view fetches the ORIGINAL, not the thumbnail -- a battle map
   opened fullscreen is opened to be read. Escape or any click closes. */
(function(){
function close(){
  var b=document.getElementById('lightbox');
  if(b)b.remove();
}
function open(src,alt){
  close();
  var box=document.createElement('div');
  box.id='lightbox';
  var img=document.createElement('img');
  img.src=src; img.alt=alt||'';
  box.appendChild(img);
  document.body.appendChild(box);
}
document.addEventListener('click',function(e){
  var a=e.target.closest?e.target.closest('a.lightboxable'):null;
  if(a){ e.preventDefault(); open(a.getAttribute('href'),
    (a.querySelector('img')||{}).alt||''); return; }
  /* The hero too: clicking the page's picture asks to see it properly.
     The size param comes off so the original arrives, not the 1000px copy. */
  var h=e.target.closest?e.target.closest('img.hero'):null;
  if(h){ open(h.src.replace(/([?&])size=[^&]*&?/,'$1').replace(/[?&]$/,''),
              h.alt); return; }
  if(e.target.closest&&e.target.closest('#lightbox'))close();
});
document.addEventListener('keydown',function(e){
  if(e.key==='Escape')close();
});
})();
"""


IMG_FADE_JS = """
/* Stop each card's skeleton shimmer once its picture is actually there.
   No per-image opacity fade -- that role now belongs to the `#page` reveal --
   only the frame's `ready` class, which turns the gradient off. */
window.__imgFadeInit=function(root){
var imgs=(root||document).querySelectorAll('.card img,.artgrid img,img.hero');
for(var i=0;i<imgs.length;i++){(function(img){
if(img.__fadeBound)return; img.__fadeBound=true;
var frame=img.closest('.thumb'); if(!frame)return;
var done=function(){ frame.classList.add('ready'); };
if(img.complete&&img.naturalWidth>0){done();return;}
img.addEventListener('load',done);
/* A picture that will not load must not leave a skeleton shimmering at the
   reader forever. Give up and let the broken image state through. */
img.addEventListener('error',done);
})(imgs[i]);}
};
window.__imgFadeInit();

/* Initial-load reveal. On the very first paint the router has not run yet,
   so the same held-then-fade behavior has to be applied to the `#page` that
   already exists. Wait for its above-fold pictures, then add `.ready`.
   A safety timer guards against a hung image. */
(function(){
var page=document.getElementById('page'); if(!page) return;
var above=[]; var hero=page.querySelector('img.hero');
if(hero) above.push(hero);
var eager=page.querySelectorAll('img:not([loading="lazy"])');
for(var i=0;i<eager.length&&above.length<8;i++){
if(above.indexOf(eager[i])<0) above.push(eager[i]); }
var pending=above.length; var reveal=function(){ page.classList.add('ready'); };
if(!pending){ reveal(); return; }
var one=function(){ if(--pending<=0) reveal(); };
above.forEach(function(img){
if(img.complete&&img.naturalWidth>0){ one(); return; }
img.addEventListener('load',one); img.addEventListener('error',one);
});
setTimeout(reveal,900);
})();
"""


def page_url(ref: str) -> str:
    kind, slug = ref.split("/", 1)
    return f"{kind}/{slug}.html"


def shell(schema, title: str, base: str, body: str, index_json: str,
          user: str | None = None, live: bool = False,
          tips: bool = False, extra: str = "", actions: str = "") -> str:
    """Wrap rendered body text in the site chrome.

    `actions` (the + New button) and `extra` (the server-only site links that
    join the dropdown) are only ever passed by the live server: the static
    export has nothing to link to for writing, and a New button that 404s is
    worse than no button.
    """
    # The live server routes /wiki/guide; a static export has to be a real file
    # with an .html extension, or the browser downloads it instead of showing it.
    guide_href = f"{base}guide" if live else f"{base}guide.html"
    schema.reload_if_changed()
    # Content on the left, site machinery folded away. The kinds are what a
    # reader navigates by; Inbox, Structure, Guide and Changelog are about
    # the wiki rather than the world, and sat in the same row they made the
    # nav read as nine equal destinations when it is really five and change.
    changelog = f'<a href="{base}changelog">Changelog</a>' if live else ""
    guide_link = "" if live else f'<a href="{guide_href}">Guide</a>'
    site_links = f'{extra}{changelog}{guide_link}'
    dropdown = (f'<div class="menu"><button type="button" class="menubtn" '
                f'aria-haspopup="true" aria-expanded="false">Site &#9662;</button>'
                f'<div class="menupanel" hidden>{site_links}</div></div>'
                if site_links else "")
    nav = "".join(
        f'<a href="{base}{k.key}/index.html">{html.escape(k.label)}</a>'
        for k in schema.nav
    )
    # ASCII separators on purpose: these strings get rewritten by tooling now
    # and then, and a stray encoding round-trip turns punctuation into mojibake.
    full = title if title == schema.name else f"{title} - {schema.name}"
    if live:
        account = (
            f'<span class="who">{html.escape(user)} &middot; '
            f'<a href="{base}login">not you?</a> &middot; '
            f'<a href="{guide_href}">guide</a> &middot; '
            f'<a href="{base}connect">connect an assistant</a> &middot; '
            f'<a href="{base}logout">sign out</a></span>'
            if user else f'<span class="who"><a href="{base}login">sign in</a></span>'
        )
    else:
        account = ""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full)}</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns%3D'http://www.w3.org/2000/svg' viewBox%3D'0 0 64 64'%3E%3Crect width%3D'64' height%3D'64' rx%3D'12' fill%3D'#1b1712'/%3E%3Cpath d%3D'M32 8 L37.5 26.5 L56 32 L37.5 37.5 L32 56 L26.5 37.5 L8 32 L26.5 26.5 Z' fill%3D'#3fa9b5'/%3E%3Ccircle cx%3D'32' cy%3D'32' r%3D'3.4' fill%3D'#e5dcc9'/%3E%3C/svg%3E">
<style>{CSS}{tooltips_mod.TOOLTIP_CSS if tips else ""}</style>
<script>document.documentElement.classList.add("imgfade")</script>
</head><body>
<svg width="0" height="0" aria-hidden="true" style="position:absolute">
  <filter id="roughedge">
    <feTurbulence type="fractalNoise" baseFrequency=".045 .068" numOctaves="3"
                  seed="7" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="4"/>
  </filter>
</svg>
<header class="top">
  <a class="home" href="{base}index.html">{html.escape(schema.name)}</a>
  <nav>{nav}</nav>
  <div class="sitenav">{dropdown}</div>
  {account}
</header>
<div class="searchbar"><div class="searchwrap">
  <span class="qwrap">
    <input id="q" type="search" placeholder="Search the world..." autocomplete="off">
    <kbd class="qkey" aria-hidden="true">&#8629; enter</kbd>
    <button id="qclear" type="button" aria-label="Clear search">&#215;</button>
  </span>
  {actions}
</div></div>
<main>
  <div id="results" hidden></div>
  <div id="page">{body}</div>
</main>
<footer class="build">{html.escape(schema.name)} &middot; <code>{html.escape(version_mod.describe())}</code></footer>
<script>const BASE={json.dumps(base)};{"window.__INDEX__=" + index_json + ";" if index_json != "[]" else ""}{SEARCH_JS}{IMG_FADE_JS}{NAV_JS}{TILT_JS}{TUNER_JS if live else ""}</script>
{f'<script src="{base}search.js" defer></script>' if live else ""}
{f'<script src="{base}tooltips.js"></script>' if tips else ""}
</body></html>
"""


def _markdown(text: str) -> str:
    return md.markdown(text, extensions=["tables", "nl2br"])


def render_guide(source: str) -> str:
    """The player guide, rendered from GUIDE.md.

    No nl2br here: the guide is prose with fenced code blocks that people copy,
    and forcing a line break at every newline would mangle them.
    """
    return (
        '<div class="guide">'
        + md.markdown(source, extensions=["tables", "fenced_code", "toc"])
        + "</div>"
    )


def render_body(schema, entity: Entity, library: Library, images: dict[str, str],
                base: str, viewer, allowed: set[str],
                editable: bool = False) -> str:
    # Three regions on a wide viewport: the page identity spans the top, the
    # picture and the metadata sit on the left, the description and its
    # sub-sections sit on the right. The regions are separate elements rather
    # than one flat list, so the source order stays mobile-friendly (image,
    # description, then metadata) and CSS grid does the reflow at wide widths.
    head_parts: list[str] = []
    main_parts: list[str] = []
    side_parts: list[str] = []

    edit_link = (
        f'<a class="edit" href="{base}{entity.kind}/{entity.slug}/edit">Edit</a>'
        f'<a class="edit" href="{base}{entity.kind}/{entity.slug}/art">Art</a>'
        f'<a class="edit" href="{base}{entity.kind}/{entity.slug}/files">Files</a>'
        if editable else ""
    )
    head_parts.append(
        f'<div class="kind"><a class="kindlink" '
        f'href="{base}{entity.kind}/index.html">'
        f'{html.escape(schema.label(entity.kind))}</a>'
        f"{edit_link}</div>"
    )

    # Where you are, for someone who arrived from a search or a link and has
    # no idea whether this pub is in Valeshire or three hundred miles away.
    #
    # The trail is cut at the first ancestor this viewer may not read, and
    # shows nothing above it. Half a trail would announce that something is
    # hidden in between, and a place name is usually the whole spoiler.
    # Scanned by the page's own kind rather than a hardcoded "place", so that
    # renaming the kind does not quietly stop the hierarchy working.
    siblings = list(library.all(entity.kind))
    trail = hierarchy_mod.trail_for(entity, hierarchy_mod.index(siblings), viewer)
    if trail:
        crumbs = " &rsaquo; ".join(
            f'<a href="{base}{page_url(p.ref)}">{html.escape(p.name)}</a>'
            for p in trail
        )
        head_parts.append(f'<nav class="trail">{crumbs}</nav>')

    head_parts.append(f"<h1>{html.escape(entity.name)}</h1>")
    if entity.summary:
        head_parts.append(f'<p class="summary">{html.escape(entity.summary)}</p>')

    hero_html = ""
    if entity.ref in images:
        hero_html = (
            f'<img class="hero" src="{art_url(base, images[entity.ref], "page")}" '
            f'alt="{html.escape(entity.name)}" loading="lazy">'
        )

    # Secret blocks this viewer may read are shown, marked, so nobody repeats
    # them at the table by accident.
    for segment in secrets_mod.parse(entity.body):
        if segment.audience is None:
            main_parts.append(_markdown(segment.text))
        elif viewer.all_access or (viewer.identities & segment.audience):
            who = ", ".join(sorted(segment.audience))
            main_parts.append(
                f'<div class="secret"><span class="who">secret &middot; {html.escape(who)}'
                f"</span>{_markdown(segment.text)}</div>"
            )

    def link_list(refs, heading, addable=False):
        # Cards, not pills: a related page with a face is recognised faster
        # than its name, and the grid is the same one the indexes use, so
        # the whole site turns pages over the same way.
        targets = []
        for ref in sorted(set(refs)):
            if ref not in allowed:
                continue
            target = library.load(*ref.split("/", 1))
            if target:
                targets.append(target)
        # "+ Add related" births a page that already links back here: the
        # new-page form arrives with this page in its links field. Shown
        # even over an empty section, because the first related page is
        # exactly when the button earns its keep.
        button = (f' <a class="act" href="{base}new?links={entity.ref}">'
                  f'+ Add related</a>' if addable and editable else "")
        if targets or button:
            main_parts.append(f"<h2>{heading}{button}</h2>")
            if targets:
                main_parts.append(_cards(targets, images, base, small=True))

    # Attachments, before the cross-links: a handout or a battle map is part of
    # the page, where Related is navigation away from it. Only shown live; the
    # static export has no route that can check who may download them.
    files = [f for f in (entity.data.get("files") or [])
             if isinstance(f, dict) and f.get("id")]
    if files and editable:
        rows = []
        for f in files:
            size = int(f.get("size", 0) or 0)
            readable = (f"{size / 1024 / 1024:.1f}MB" if size > 1024 * 1024
                        else f"{max(1, size // 1024)}KB")
            fid = html.escape(str(f["id"]))
            fname = html.escape(str(f.get("name", "file")))
            # An image attachment shows itself; clicking it still downloads
            # the original. Anything else stays a plain link -- the download
            # route only serves inline what the thumbnailer itself produced.
            if str(f.get("type", "")).startswith("image/"):
                rows.append(
                    f'<li class="filepic"><a href="{base}file/{fid}" '
                    f'class="lightboxable">'
                    f'<img src="{base}file/{fid}?size=page" alt="{fname}" '
                    f'loading="lazy"></a>'
                    f'<span class="hint">{fname} &middot; {readable}</span></li>'
                )
            else:
                rows.append(
                    f'<li><a href="{base}file/{fid}">{fname}</a> '
                    f'<span class="hint">{readable}</span></li>'
                )
        main_parts.append("<h2>Files</h2>")
        main_parts.append(f'<ul class="filelist">{"".join(rows)}</ul>')

    # What is inside this place, before Related, because a city's own districts
    # are the page rather than navigation away from it. Direct children only:
    # the districts list their own buildings, and a region showing every shop
    # in every town is not an index of anything.
    contained = [child for child in hierarchy_mod.children(entity.ref, siblings)
                 if child.ref in allowed]
    if contained:
        # Full-size cards, unlike Related's small ones: what a place holds
        # is this page's own content, not a reference away from it.
        main_parts.append(f"<h2>Inside {html.escape(entity.name)}</h2>")
        main_parts.append(_cards(contained, images, base))

    link_list(entity.links, "Related", addable=True)
    link_list(
        [e.ref for e in library.backlinks(entity.ref) if e.ref not in entity.links],
        "Mentioned by",
    )

    sheet = entity.data.get("dndbeyond_sheet")
    if sheet:
        bits = " &middot; ".join(
            filter(None, [
                html.escape(str(entity.data.get("race", ""))),
                html.escape(str(entity.data.get("class", ""))),
                html.escape(str(entity.data.get("subclass", ""))),
                f"level {entity.data['level']}" if entity.data.get("level") else "",
            ])
        )
        main_parts.append(
            '<div class="sheet">'
            f'<div class="statline">{bits}</div>'
            f'<a class="sheetlink" href="{html.escape(sheet)}" target="_blank" '
            f'rel="noopener" title="Open character sheet on D&amp;D Beyond" '
            f'aria-label="Open character sheet on D&amp;D Beyond">'
            f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.4" stroke-linejoin="round" aria-hidden="true">'
            f'<path d="M12 2 L21 7 V17 L12 22 L3 17 V7 Z"/>'
            f'<path d="M12 7.2 L16.5 15 H7.5 Z"/>'
            f'<path d="M12 2 V7.2 M21 7 L16.5 15 M3 7 L7.5 15 '
            f'M12 22 L16.5 15 M12 22 L7.5 15 M21 17 L16.5 15 M3 17 L7.5 15"/>'
            f'</svg></a>'
            '<p class="hint">Hit points, spells and inventory live on the sheet, '
            'not here. It needs a D&amp;D Beyond account with access to the '
            'campaign.</p></div>'
        )

    if entity.tags:
        side_parts.append(
            '<div class="tags">'
            + "".join(f'<span class="tag">{html.escape(t)}</span>' for t in entity.tags)
            + "</div>"
        )

    meta = []
    # Fields already shown as the sheet button don't need a second airing in
    # the raw metadata table.
    shown_above = {"visible_to", "dndbeyond_sheet", "dndbeyond_campaign"}
    data = {k: v for k, v in entity.data.items()
            if k not in shown_above and v not in (None, "", [], {})}
    if data:
        rows = "".join(
            f"<tr><th>{html.escape(str(k).replace('_',' '))}</th>"
            f"<td>{html.escape(str(v))}</td></tr>" for k, v in data.items()
        )
        meta.append(f"<table>{rows}</table>")
    if entity.sources:
        meta.append("<p>Sources: " + ", ".join(
            f"<code>{html.escape(s)}</code>" for s in entity.sources) + "</p>")
    if meta:
        side_parts.append(f'<div class="meta">{"".join(meta)}</div>')

    pieces: list[str] = []
    pieces.append(f'<header class="entity-head">{"".join(head_parts)}</header>')
    if hero_html:
        pieces.append(hero_html)
    if main_parts:
        pieces.append(f'<div class="entity-main">{"".join(main_parts)}</div>')
    if side_parts:
        pieces.append(f'<aside class="entity-side">{"".join(side_parts)}</aside>')

    # Only take on the two-column shape when there is genuinely something to
    # put on the left. A page with no picture, no tags and no raw metadata is
    # just prose and would render as a narrow column next to a permanently
    # empty aside.
    has_side = bool(hero_html or side_parts)
    klass = "entity has-side" if has_side else "entity"
    return f'<article class="{klass}">{"".join(pieces)}</article>'



# What a card thumbnail actually is, so the markup can say so. Square because
# `thumbs.SQUARE` crops it that way and the CSS below shows it that way.
THUMB_PX = thumbs.SIZES["card"]

# Placeholder icons for pages without art, one per kind, plain line drawings
# in the accent color. Inline SVG so the export stays self-contained; a kind
# these have not heard of gets the framed-picture fallback.
_ICON_ATTRS = ('viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"')
_KIND_ICONS = {
    "place": ('<path d="M3 18 L9 8 L13 13.5 L16 9.5 L21 18 Z"/>'
              '<circle cx="18.2" cy="5.8" r="1.4"/>'),
    "character": ('<circle cx="12" cy="8" r="3.4"/>'
                  '<path d="M5.2 19.2 c0-4 3-6.2 6.8-6.2 s6.8 2.2 6.8 6.2"/>'),
    "faction": '<path d="M6.5 4.5 h11 v14.5 l-5.5-3.8 -5.5 3.8 Z"/>',
    "item": ('<path d="M12 3.2 V13"/><path d="M8.6 13 H15.4"/>'
             '<path d="M12 13 V17"/><circle cx="12" cy="18.6" r="1.2"/>'),
    "creature": ('<circle cx="8.3" cy="9" r="1.35"/>'
                 '<circle cx="12" cy="7.4" r="1.35"/>'
                 '<circle cx="15.7" cy="9" r="1.35"/>'
                 '<path d="M12 11.2 c2.6 0 4.2 1.8 4.2 3.6 0 1.9-1.9 3-4.2 3'
                 ' s-4.2-1.1-4.2-3 c0-1.8 1.6-3.6 4.2-3.6 Z"/>'),
    "deity": ('<circle cx="12" cy="12" r="3"/>'
              '<path d="M12 4.5 V6.8 M12 17.2 V19.5 M4.5 12 H6.8 M17.2 12 '
              'H19.5 M6.7 6.7 L8.3 8.3 M15.7 15.7 L17.3 17.3 M17.3 6.7 '
              'L15.7 8.3 M8.3 15.7 L6.7 17.3"/>'),
    "lore": ('<path d="M4 6.2 c3-1.5 5-1.5 8 0 c3-1.5 5-1.5 8 0 V18.8 '
             'c-3-1.5-5-1.5-8 0 c-3 1.5-5 1.5-8 0 Z"/>'
             '<path d="M12 6.2 V18.8"/>'),
}
_ICON_FALLBACK = ('<rect x="4" y="5" width="16" height="14" rx="2"/>'
                  '<circle cx="9" cy="10" r="1.5"/>'
                  '<path d="M4 16.5 l4.5-4.5 4 4 2.5-2.5 5 5"/>')


def _kind_icon(kind: str) -> str:
    return (f'<svg {_ICON_ATTRS} aria-hidden="true">'
            f'{_KIND_ICONS.get(kind, _ICON_FALLBACK)}</svg>')


def art_url(base: str, name: str, size: str) -> str:
    """The URL for one entity's picture at one size.

    `images_for` already puts a `?v=` on the name so the week-long cache lets
    go when somebody picks a different picture. Appending `?size=` to that
    produced `...png?v=upload-966b?size=card`, and a second `?` is not a
    separator: the whole of `upload-966b?size=card` became the value of `v`,
    `size` was never a parameter at all, and the route fell through to the
    original every time. Thirty full-size pictures, on a page asking for
    thirty thumbnails, with nothing anywhere reporting an error.

    So the joining happens here, once, rather than at each call site.
    """
    return f"{base}art/{name}{'&' if '?' in name else '?'}size={size}"


def _completeness(e: Entity) -> float:
    """How finished a page is, for ordering an index.

    Art carries the most weight because a card without a picture reads as a
    stub whatever the prose says; then prose, capped so one enormous page
    does not pin itself to the front forever. The `needs-*` tags subtract:
    they are the wiki's own admission that something is missing.
    """
    score = 0.0
    if e.art:
        score += 2
    if e.summary:
        score += 1
    if e.appearance:
        score += 1
    score += min(len(e.body) / 400.0, 3.0)
    score -= sum(1 for t in e.tags if t.startswith("needs-"))
    return score


def _cards(items: list[Entity], images: dict[str, str], base: str,
           notes: dict[str, str] | None = None,
           by_completeness: bool = False, small: bool = False) -> str:
    # `small` is the sidebar-weight variant: thumbnail beside the text at a
    # fraction of the size, for sections that reference pages rather than
    # present them -- Related on an entity page should not shout as loudly
    # as the index.
    key = (lambda e: (-_completeness(e), e.name)) if by_completeness \
        else (lambda e: e.name)
    out = []
    for e in sorted(items, key=key):
        href = f"{base}{page_url(e.ref)}"
        note = (notes or {}).get(e.ref, "")
        note_html = f'<p class="contains">{html.escape(note)}</p>' if note else ""
        # The picture is the obvious thing to click on a card, so it opens the
        # page too. It is hidden from assistive tech and skipped by tab: it goes
        # exactly where the title link below it goes, and announcing every card
        # twice is worse than not linking the image at all.
        # Width and height are stated, not inferred: the browser then knows a
        # card's shape before the picture arrives and lays the grid out once,
        # rather than reflowing every card as each image lands. Decoding is
        # async so a slow one cannot hold up the paint of the rest.
        if e.ref in images:
            img = (f'<a class="thumb" href="{href}" tabindex="-1" aria-hidden="true">'
                   f'<img src="{art_url(base, images[e.ref], "card")}" alt=""'
                   f' width="{THUMB_PX}" height="{THUMB_PX}"'
                   ' loading="lazy" decoding="async">'
                   "</a>")
        else:
            # No art yet: the kind's icon on parchment holds the space, so
            # a card without a picture keeps the same shape as its
            # neighbours instead of collapsing to a caption -- and says at
            # a glance what sort of thing it is.
            img = (f'<a class="thumb noart" href="{href}" tabindex="-1" '
                   f'aria-hidden="true">{_kind_icon(e.kind)}</a>')
        card_cls = "card small" if small else "card"
        out.append(
            f'<div class="{card_cls}">{img}<div class="body">'
            f'<a href="{href}">{html.escape(e.name)}</a>'
            f"<p>{html.escape(e.summary[:90])}</p>{note_html}</div></div>"
        )
    grid_cls = "grid smallgrid" if small else "grid"
    return f'<div class="{grid_cls}">{"".join(out)}</div>'


def render_index(schema, entities: list[Entity], images: dict[str, str],
                 base: str, editable: bool = False) -> str:
    """The front page, assembled from the sections in config.yaml.

    Each section is a heading and a filter. An empty one is skipped rather than
    rendered as a bare heading, so a section for a kind nobody has written yet
    costs nothing to leave configured.
    """
    schema.reload_if_changed()
    parts = [
        f'<a class="newpage" href="{base}new">+ New page</a>' if editable else "",
        f"<h1>{html.escape(schema.name)}</h1>",
        f'<p class="summary">{html.escape(schema.tagline)}</p>'
        if schema.tagline else "",
    ]
    for section in schema.home:
        matched = [e for e in entities if section.matches(e)]
        if not matched:
            continue
        if section.title:
            parts.append(f"<h2>{html.escape(section.title)}</h2>")
        parts.append(_cards(matched, images, base))

    parts.append(f'<p class="meta">{len(entities)} pages.</p>')
    return "\n".join(parts)


# The census vocabulary for a card's "what is inside" line, in display order.
# A child counts under its first matching entry; anything unmatched is just a
# place. Same vocabulary as the index groups in structure.yaml on purpose --
# two names for the same category would drift.
_CENSUS = [
    ("region", {"region", "realm"}),
    ("settlement", {"settlement", "town", "city"}),
    ("district", {"district"}),
    ("landmark", {"landmark"}),
    ("site", {"site"}),
    ("wild", {"wilderness", "mountains", "river", "water"}),
]


def _census_line(top: Entity, children: dict[str, list[Entity]]) -> str:
    """"5 landmarks, 3 districts" for everything inside one place.

    Counts every descendant, not just direct children: the point of the line
    is "how much world is in here", and a city whose landmarks all hang off
    its districts would otherwise claim to contain almost nothing. Counting
    walks only entities this viewer already received, so a hidden page is
    absent from the census exactly as it is absent from everywhere else.
    """
    tally: dict[str, int] = {}
    queue = list(children.get(top.ref, []))
    while queue:
        e = queue.pop()
        queue.extend(children.get(e.ref, []))
        for name, tags in _CENSUS:
            if tags & set(e.tags):
                tally[name] = tally.get(name, 0) + 1
                break
        else:
            tally["place"] = tally.get("place", 0) + 1
    ordered = sorted(tally.items(), key=lambda kv: -kv[1])
    if not ordered:
        return ""
    # Prefixed, because "17 sites, 5 landmarks" floating under a summary
    # reads as trivia until the line says what it counts.
    return "inside: " + ", ".join(
        f"{n} {name}{'s' if n != 1 else ''}" for name, n in ordered)


def render_kind_index(schema, kind: str, items: list[Entity],
                      images: dict[str, str], base: str) -> str:
    label = schema.label(kind)

    # A kind that nests shows only its top-level pages: the primaries. What
    # is inside a place belongs to that place's page, and a flat index of
    # sixty nested rooms and alleys buries the eleven places anyone actually
    # navigates by. Each card carries a census of what it holds instead.
    nested = [e for e in items if e.within]
    children: dict[str, list[Entity]] = {}
    for e in nested:
        children.setdefault(e.within, []).append(e)
    top = [e for e in items if not e.within]
    notes = {e.ref: _census_line(e, children) for e in items} if nested else {}
    summary = (f"{len(items)} {label.lower()} &mdash; {len(top)} top level, "
               f"{len(nested)} nested."
               if nested else f"{len(items)} pages.")

    parts = [f"<h1>{label}</h1><p class=\"summary\">{summary}</p>"]
    groups = [g for g in schema.index_tags if g.kind == kind]
    if groups:
        # Groups match over every page, nested or not: tagging a sub-location
        # `region` is a deliberate promotion into the index (Dire Foothills
        # sits inside Copper Vale and still deserves the Regions shelf). The
        # Other section stays primaries-only, so an untagged room or alley
        # never floats up on its own.
        grouped: set[str] = set()
        for spec in groups:
            group = [e for e in items if spec.matches(e)]
            grouped.update(e.ref for e in group)
            if group:
                parts.append(f"<h2>{html.escape(spec.title)}</h2>")
                parts.append(_cards(group, images, base, notes,
                                    by_completeness=True))
        other = [e for e in top if e.ref not in grouped]
        if other:
            parts.append(f"<h2>Other {html.escape(label)}</h2>")
            parts.append(_cards(other, images, base, notes,
                                by_completeness=True))
        return "".join(parts)

    parts.append(_cards(top if nested else items, images, base, notes,
                        by_completeness=True))
    return "".join(parts)


def search_index(schema, entities: list[Entity], viewer) -> str:
    """Client-side index containing only text this viewer may read."""
    return json.dumps(
        [
            {
                "n": e.name,
                "k": schema.label(e.kind).rstrip("s"),
                "s": e.summary[:120],
                "u": page_url(e.ref),
                "h": " ".join(
                    [e.name, e.summary, access_mod.redact(e.body, viewer),
                     " ".join(e.tags)]
                ).lower(),
            }
            for e in entities
        ],
        ensure_ascii=False,
    )
