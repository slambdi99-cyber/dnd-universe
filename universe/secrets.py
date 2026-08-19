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


def redact(body: str, identities: set[str] | frozenset[str]) -> str:
    """Return the body as this viewer may see it.

    `identities` is everything the viewer counts as: their own key, plus their
    role, so `:::secret dm` matches any DM without naming them.
    """
    viewer = {i.lower() for i in identities}
    kept = [
        s.text
        for s in parse(body)
        if s.audience is None or (viewer & s.audience)
    ]
    return "\n\n".join(kept).strip()


def strip_all(body: str) -> str:
    """Return only the public parts. Used for anything leaving the system."""
    return "\n\n".join(s.text for s in parse(body) if not s.is_secret).strip()


def has_secrets(body: str) -> bool:
    return any(s.is_secret for s in parse(body))


def hidden_from(body: str, identities: set[str] | frozenset[str]) -> bool:
    """Whether any block in this body is withheld from this viewer.

    Asked directly rather than inferred by comparing the redacted text to the
    original: redaction re-joins paragraphs, so the strings differ even when
    nothing was removed.
    """
    viewer = {i.lower() for i in identities}
    return any(
        s.audience is not None and not (viewer & s.audience) for s in parse(body)
    )


def audiences(body: str) -> set[str]:
    """Every identity named by any secret block in this body."""
    out: set[str] = set()
    for segment in parse(body):
        if segment.audience:
            out |= set(segment.audience)
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
    parts = [edited.strip()] + kept
    return "\n\n".join(p for p in parts if p.strip()).strip()


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
        if segment.audience is None:
            parts.append(segment.text)
        elif viewer & segment.audience:
            parts.append(wrap(segment.text, segment.audience))
    return "\n\n".join(parts).strip()
