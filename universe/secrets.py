"""Secret sections inside otherwise-shared pages.

A page can be readable by the whole table while carrying a block only some
people are meant to see:

    Wren is from Lorithal and has been secretive about it.

    :::secret dm, wren
    Her aunt is the one funding the rebellion. Wren has known since Worrick's
    party and has not told anyone.
    :::

    The party is aware she recognised someone there.

The audience is a comma-separated list of person keys from `people.yaml`, plus
the special key `dm`, which matches anyone whose role is dm. Everything outside
a block is public.

## Fail closed

Every ambiguity resolves toward hiding. An unterminated block hides the rest of
the page. An unreadable audience hides the block. A block with an empty
audience is visible to nobody but the DM. This is deliberate: the cost of
wrongly hiding something is a confused question in Discord, and the cost of
wrongly showing it is a spoiled campaign.

`strip_all` is the function the public website uses. It removes every block
regardless of audience, so a secret cannot reach a static file at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

OPEN = re.compile(r"^:::(?P<tag>secret|visited)\b[ \t]*(?P<audience>.*?)[ \t]*$",
                  re.IGNORECASE)
CLOSE = re.compile(r"^:::[ \t]*$")

# Anyone whose role is dm matches this in an audience list.
DM_KEY = "dm"

# Not a person. A page marked visited grants this identity to every reader,
# so a `:::visited` block stays DM-only until the DM checks the place off,
# then opens to the whole table without anyone editing the body.
VISITED_KEY = "visited"


@dataclass
class Segment:
    text: str
    # None means public. A set means only these identities may read it.
    audience: frozenset[str] | None

    @property
    def is_secret(self) -> bool:
        return self.audience is not None


def _parse_audience(raw: str) -> frozenset[str]:
    keys = {k.strip().lower() for k in raw.replace(";", ",").split(",")}
    keys.discard("")
    # An empty or unparseable audience is not "everyone", it's "the DM only".
    return frozenset(keys) if keys else frozenset({DM_KEY})


def parse(body: str) -> list[Segment]:
    """Split a body into public and secret segments, in order."""
    segments: list[Segment] = []
    buffer: list[str] = []
    audience: frozenset[str] | None = None

    def flush() -> None:
        if buffer:
            text = "\n".join(buffer).strip("\n")
            if text.strip():
                segments.append(Segment(text=text, audience=audience))
            buffer.clear()

    for line in body.splitlines():
        opening = OPEN.match(line)
        if opening:
            # A nested or repeated open inside a block is malformed. Keep the
            # existing audience rather than widening it.
            if audience is None:
                flush()
                audience = _parse_audience(opening.group("audience"))
                # `:::visited` is sugar: readable by the DM now and by
                # everyone once the page is marked visited. Any extra keys
                # listed on the line keep working alongside.
                if opening.group("tag").lower() == VISITED_KEY:
                    audience |= {DM_KEY, VISITED_KEY}
            continue
        if CLOSE.match(line) and audience is not None:
            flush()
            audience = None
            continue
        buffer.append(line)

    # Unterminated block: everything after the opener stays secret.
    flush()
    return segments


# -- secret columns ----------------------------------------------------------
#
# A table can carry one shared body with a column only some readers see:
#
#     | Item | Price | Notes ::dm |
#     | --- | ---: | --- |
#     | Ear trumpet | 12g | He finds these very funny |
#
# `::` plus an audience list on a header cell marks the whole column. Readers
# outside the audience receive the same table without that column; readers
# inside it see the header as "Notes · dm", so a secret column never looks
# like an ordinary one. The same fail-closed rules as blocks apply: an
# unparseable audience is the DM's alone.
#
# For editing, a table holding a column the editor may not read is withheld
# whole, exactly like a block they may not read, and folded back on save.
# Splicing their edited rows back around hidden cells would need to match
# rows across renames and reorders, and a wrong match publishes or destroys
# a secret; withholding the table costs an edit request in Discord instead.
#
# Escaped pipes are not understood. A table exotic enough to need `\|`
# should carry its secrets as a block.

_COL = re.compile(
    r"^(?P<name>.*?)[ \t]*::[ \t]*"
    r"(?P<aud>[A-Za-z][\w-]*(?:[ \t]*,[ \t]*[A-Za-z][\w-]*)*)[ \t]*$"
)
_SEP = re.compile(r"^\|(?=.*-)[ \t:\-|]+$")

# Sentinel for "every column, chips on": the all-access process reads the
# files it already owns, but still wants secret columns visibly marked.
ALL = object()


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _tables(lines: list[str]):
    """Yield (start, end) line ranges of markdown tables: a header row
    starting with |, a separator row, then every following | row."""
    i = 0
    while i < len(lines):
        if (lines[i].lstrip().startswith("|") and i + 1 < len(lines)
                and _SEP.match(lines[i + 1].strip())):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            yield i, j
            i = j
        else:
            i += 1


def _column_audiences(header: list[str]) -> dict[int, frozenset[str]]:
    out: dict[int, frozenset[str]] = {}
    for i, cell in enumerate(header):
        m = _COL.match(cell)
        if m:
            out[i] = _parse_audience(m.group("aud"))
    return out


def redact_columns(text: str, viewer) -> str:
    """Rewrite the tables in `text` for one reader.

    `viewer` is a set of identities (keep the columns they may read, drop
    the rest), None (drop every secret column: the public/export view), or
    the module's ALL sentinel (keep everything: the all-access reader).
    A kept secret column's header is rewritten to name its audience, so it
    can never pass for a public one.
    """
    lines = text.splitlines()
    changed = False
    for start, end in _tables(lines):
        header = _cells(lines[start])
        marked = _column_audiences(header)
        if not marked:
            continue
        drop = {
            i for i, aud in marked.items()
            if viewer is not ALL and (viewer is None or not (viewer & aud))
        }
        for li in range(start, end):
            cells = _cells(lines[li])
            if li == start:
                for ci, aud in marked.items():
                    if ci not in drop and ci < len(cells):
                        name = _COL.match(cells[ci]).group("name").strip()
                        cells[ci] = f"{name} &middot; {', '.join(sorted(aud))}"
            lines[li] = _row([c for ci, c in enumerate(cells) if ci not in drop])
        changed = True
    return "\n".join(lines) if changed else text


def _column_withheld(text: str, viewer: set[str] | frozenset[str]) -> bool:
    """Whether any table column in `text` is hidden from this viewer."""
    lines = text.splitlines()
    for start, _ in _tables(lines):
        for aud in _column_audiences(_cells(lines[start])).values():
            if not (viewer & aud):
                return True
    return False


def _excise_hidden_tables(
    text: str, viewer: set[str] | frozenset[str]
) -> tuple[str, list[str]]:
    """Split `text` into (editable remainder, tables withheld whole).

    A table is withheld when it carries a column this viewer may not read;
    see the note above on why the table travels whole rather than by cell.
    """
    lines = text.splitlines()
    cut: list[tuple[int, int]] = []
    tables: list[str] = []
    for start, end in _tables(lines):
        marked = _column_audiences(_cells(lines[start]))
        if any(not (viewer & aud) for aud in marked.values()):
            tables.append("\n".join(lines[start:end]))
            cut.append((start, end))
    if not cut:
        return text, []
    keep: list[str] = []
    removed = set()
    for start, end in cut:
        removed.update(range(start, end))
    for i, line in enumerate(lines):
        if i not in removed:
            keep.append(line)
    return "\n".join(keep).strip("\n"), tables


def redact(body: str, identities: set[str] | frozenset[str]) -> str:
    """Return the body as this viewer may see it.

    `identities` is everything the viewer counts as: their own key, plus their
    role, so `:::secret dm` matches any DM without naming them.
    """
    viewer = {i.lower() for i in identities}
    kept = [
        redact_columns(s.text, viewer)
        for s in parse(body)
        if s.audience is None or (viewer & s.audience)
    ]
    return "\n\n".join(kept).strip()


def strip_all(body: str) -> str:
    """Return only the public parts. Used for anything leaving the system."""
    return "\n\n".join(
        redact_columns(s.text, None) for s in parse(body) if not s.is_secret
    ).strip()


def has_secrets(body: str) -> bool:
    if any(s.is_secret for s in parse(body)):
        return True
    lines = body.splitlines()
    return any(
        _column_audiences(_cells(lines[start]))
        for start, _ in _tables(lines)
    )


def hidden_from(body: str, identities: set[str] | frozenset[str]) -> bool:
    """Whether any block in this body is withheld from this viewer.

    Asked directly rather than inferred by comparing the redacted text to the
    original: redaction re-joins paragraphs, so the strings differ even when
    nothing was removed.
    """
    viewer = {i.lower() for i in identities}
    if any(
        s.audience is not None and not (viewer & s.audience) for s in parse(body)
    ):
        return True
    return _column_withheld(body, viewer)


def audiences(body: str) -> set[str]:
    """Every identity named by any secret block or column in this body."""
    out: set[str] = set()
    for segment in parse(body):
        if segment.audience:
            out |= set(segment.audience)
    lines = body.splitlines()
    for start, _ in _tables(lines):
        for aud in _column_audiences(_cells(lines[start])).values():
            out |= set(aud)
    return out


def withheld_blocks(body: str, identities: set[str] | frozenset[str]) -> list[str]:
    """The secret blocks this viewer cannot read, as raw fenced text.

    Needed for editing. Someone editing a page only ever sees their own
    version, so saving it verbatim would delete everyone else's secrets. These
    blocks get carried across untouched.
    """
    viewer = {i.lower() for i in identities}
    out = []
    for segment in parse(body):
        if segment.audience is not None and not (viewer & segment.audience):
            out.append(wrap(segment.text, segment.audience))
    return out


def merge_edit(
    original: str, edited: str, identities: set[str] | frozenset[str]
) -> str:
    """Fold an edited visible body back into the full one.

    Blocks the editor could not see are appended, unchanged. They may move to
    the end of the page, which is a small cost against the alternative of
    quietly destroying them.
    """
    kept = withheld_blocks(original, identities)
    kept += withheld_column_tables(original, identities)
    parts = [edited.strip()] + kept
    return "\n\n".join(p for p in parts if p.strip()).strip()


def withheld_column_tables(
    body: str, identities: set[str] | frozenset[str]
) -> list[str]:
    """Tables withheld from this editor because of a column they may not read.

    Each comes back wearing its segment's fence where it had one, so a table
    carried out of a `:::visited` block folds back in as visited material
    rather than surfacing as public prose.
    """
    viewer = {i.lower() for i in identities}
    out: list[str] = []
    for segment in parse(body):
        if segment.audience is not None and not (viewer & segment.audience):
            continue  # the whole block is already carried by withheld_blocks
        _, tables = _excise_hidden_tables(segment.text, viewer)
        for table in tables:
            out.append(wrap(table, segment.audience) if segment.audience
                       else table)
    return out


def wrap(text: str, audience: list[str] | set[str]) -> str:
    """Build a secret block, for tools that write one.

    An audience carrying the visited key round-trips as `:::visited`, the
    form a person would have typed, rather than as the expanded audience
    list the parser gives it.
    """
    keys = {str(a).strip().lower() for a in audience if str(a).strip()}
    if VISITED_KEY in keys:
        rest = ", ".join(sorted(keys - {VISITED_KEY, DM_KEY}))
        header = f":::{VISITED_KEY}" + (f" {rest}" if rest else "")
    else:
        header = f":::secret {', '.join(sorted(keys)) or DM_KEY}"
    return f"{header}\n{text.strip()}\n:::"


def visible_body(body: str, identities: set[str] | frozenset[str]) -> str:
    """The body as this viewer may *edit* it.

    Withheld blocks are removed, exactly as `redact` does -- but blocks the
    viewer may read keep their fences. `redact` strips them for display, and
    an edit form built from that flattens every readable secret into public
    prose on the next save. The fences are part of the text the editor is
    trusted with; hiding them was how secrets leaked.
    """
    viewer = {i.lower() for i in identities}
    parts = []
    for segment in parse(body):
        if segment.audience is not None and not (viewer & segment.audience):
            continue
        # A table with a column this editor may not read leaves the form
        # whole; merge_edit folds it back on save. Editing around hidden
        # cells is how they get destroyed.
        text, _ = _excise_hidden_tables(segment.text, viewer)
        if not text.strip():
            continue
        parts.append(wrap(text, segment.audience) if segment.audience
                     else text)
    return "\n\n".join(parts).strip()
