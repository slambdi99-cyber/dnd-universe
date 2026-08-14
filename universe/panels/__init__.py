"""One module per feature of the website.

Each panel owns its routes, its forms and its rendering, and exposes a single
`routes(wiki)`. That is the whole interface: one line over a few hundred lines
of behaviour, so "change the art panel" is a file rather than a line range
inside a file that also contains the inbox.
"""

from __future__ import annotations

from . import art, files, inbox, structure


def routes(wiki) -> list:
    """Every panel's routes, in one list for the app to mount."""
    return [
        *structure.routes(wiki),
        *inbox.routes(wiki),
        *art.routes(wiki),
        *files.routes(wiki),
    ]
