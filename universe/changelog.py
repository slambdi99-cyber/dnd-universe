"""A generated changelog from git history.

The old changelog was a wiki page, which meant the audit trail had to be
manually updated by the same tools it was supposed to describe. Git already
knows who changed which files and when, so this page is generated instead.
"""

from __future__ import annotations

import html
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .entities import Library

TIMEOUT = 10
COMMIT_MARKER = "CHANGELOG_COMMIT"


@dataclass
class Change:
    commit: str
    when: str
    author: str
    subject: str
    status: str
    ref: str
    name: str


@dataclass
class Changelog:
    changes: list[Change] = field(default_factory=list)
    error: str = ""


def _git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def load(root: Path, library: Library, *, limit: int = 120) -> Changelog:
    """Return recent content-page changes from git.

    Only files under `content/` are treated as page changes. Deleted pages still
    appear by their last path; current pages are labelled from their frontmatter
    when possible.
    """
    root = Path(root)
    result = _git(
        root,
        "log",
        f"--max-count={limit}",
        "--date=iso-strict",
        "--name-status",
        f"--pretty=format:{COMMIT_MARKER}%x1f%H%x1f%aI%x1f%an%x1f%ae%x1f%s",
        "--",
        "content",
    )
    if result is None:
        return Changelog(error="Git history is not available.")
    if result.returncode != 0:
        msg = result.stderr.strip() or "Git history could not be read."
        return Changelog(error=msg)

    changes: list[Change] = []
    current: tuple[str, str, str, str, str] | None = None
    for raw in result.stdout.splitlines():
        if not raw:
            continue
        if raw.startswith(COMMIT_MARKER):
            fields = raw.split("\x1f", 5)
            if len(fields) == 6:
                current = tuple(fields[1:])  # type: ignore[assignment]
            continue
        if current is None:
            continue

        parts = raw.split("\t")
        status = parts[0]
        path = parts[-1] if len(parts) > 1 else ""
        ref = _ref_from_path(path)
        if not ref:
            continue
        commit, when, author, email, subject = current
        changes.append(Change(
            commit=commit[:7],
            when=when[:10],
            author=f"{author} <{email}>",
            subject=subject,
            status=status[:1],
            ref=ref,
            name=_name_for_ref(library, ref),
        ))

    return Changelog(changes=changes)


def render(log: Changelog, base: str) -> str:
    if log.error:
        return (
            "<h1>Changelog</h1>"
            f'<p class="summary">{html.escape(log.error)}</p>'
        )

    recent = log.changes[:30]
    parts = [
        "<h1>Changelog</h1>",
        '<p class="summary">Generated from git history. It tracks changes to '
        "wiki content pages by page and by author.</p>",
        "<h2>Recent Changes</h2>",
        _rows(recent, base),
        "<h2>By Page</h2>",
        _grouped(log.changes, key=lambda c: c.ref, title=lambda c: _page_link(c, base)),
        "<h2>By User</h2>",
        _grouped(log.changes, key=lambda c: c.author, title=lambda c: html.escape(c.author)),
    ]
    return "\n".join(parts)


def restrict(log: Changelog, refs: set[str] | frozenset[str]) -> Changelog:
    return Changelog(
        changes=[change for change in log.changes if change.ref in refs],
        error=log.error,
    )


def _ref_from_path(path: str) -> str:
    if not path.startswith("content/") or not path.endswith(".md"):
        return ""
    bits = Path(path).parts
    if len(bits) != 3:
        return ""
    return f"{bits[1]}/{bits[2][:-3]}"


def _name_for_ref(library: Library, ref: str) -> str:
    entity = library.load(*ref.split("/", 1))
    return entity.name if entity else ref


def _page_link(change: Change, base: str) -> str:
    href = f"{base}{html.escape(change.ref)}.html"
    return f'<a href="{href}">{html.escape(change.name)}</a>'


def _rows(changes: list[Change], base: str) -> str:
    if not changes:
        return '<p class="empty">No page changes found.</p>'
    rows = []
    for change in changes:
        rows.append(
            "<tr>"
            f"<td>{html.escape(change.when)}</td>"
            f"<td>{html.escape(change.status)}</td>"
            f"<td>{_page_link(change, base)}</td>"
            f"<td>{html.escape(change.author)}</td>"
            f"<td>{html.escape(change.subject)}</td>"
            f"<td><code>{html.escape(change.commit)}</code></td>"
            "</tr>"
        )
    return (
        "<table><tr><th>When</th><th></th><th>Page</th><th>User</th>"
        f"<th>Change</th><th>Commit</th></tr>{''.join(rows)}</table>"
    )


def _grouped(changes: list[Change], *, key, title) -> str:
    groups: dict[str, list[Change]] = {}
    first: dict[str, Change] = {}
    for change in changes:
        k = key(change)
        groups.setdefault(k, []).append(change)
        first.setdefault(k, change)
    if not groups:
        return '<p class="empty">No page changes found.</p>'

    out = []
    ordered = sorted(groups, key=lambda k: (-len(groups[k]), k.lower()))
    for k in ordered:
        rows = "".join(
            "<li>"
            f"{html.escape(change.when)} - {html.escape(change.subject)} "
            f"<span class=\"hint\">{html.escape(change.commit)}</span>"
            "</li>"
            for change in groups[k][:8]
        )
        more = len(groups[k]) - 8
        if more > 0:
            rows += f'<li class="hint">{more} more change{"s" if more != 1 else ""}</li>'
        out.append(
            f"<h3>{title(first[k])}</h3>"
            f'<ul class="links">{rows}</ul>'
        )
    return "".join(out)
