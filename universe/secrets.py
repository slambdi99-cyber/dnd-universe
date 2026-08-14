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

OPEN = re.compile(r"^:::secret\b[ \t]*(?P<audience>.*?)[ \t]*$", re.IGNORECASE)
CLOSE = re.compile(r"^:::[ \t]*$")

# Anyone whose role is dm matches this in an audience list.
DM_KEY = "dm"


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
    """Build a secret block, for tools that write one."""
    keys = ", ".join(sorted({str(a).strip().lower() for a in audience if str(a).strip()}))
    return f":::secret {keys or DM_KEY}\n{text.strip()}\n:::"
