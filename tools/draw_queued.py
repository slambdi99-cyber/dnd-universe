"""Draw everything the website asked for while this machine was off.

The wiki lives on a server with no graphics card. When someone presses Art
there, the request is committed to the repo instead of drawn. This is the other
half: run it here, where the card is, and the pictures get made and pushed back.

    python tools\\draw_queued.py            draw everything waiting
    python tools\\draw_queued.py --list     say what is waiting, draw nothing

It pulls first and pushes after, because the queue is shared. A request drawn
twice wastes twenty minutes; a request drawn from a stale copy of the repo can
be one somebody already cancelled.

Nothing is attached to a page. The pictures become candidates, and whoever asked
picks one, same as if they had been generated in front of them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from universe import artqueue, config  # noqa: E402
from universe.assets import AssetStore  # noqa: E402
from universe.entities import Library  # noqa: E402

LOG = ROOT / ".draw-queued.log"


def _log_to_file_when_nobody_is_watching() -> None:
    """Keep a record when this runs with no console attached.

    The scheduled task runs under pythonw, which has no window, so that a
    picture being drawn does not interrupt whoever is using the machine. The
    cost is that everything printed here goes nowhere, and a task that fails
    silently every twenty minutes is the worst kind: the site says a picture is
    queued, forever, and nothing anywhere says why.

    So when stdout is not a terminal, it is also written to a file. Run by
    hand, nothing changes.
    """
    if sys.stdout is not None and sys.stdout.isatty():
        return

    import atexit
    import datetime
    import io

    buffer = io.StringIO()

    class Tee:
        def write(self, text):
            buffer.write(text)
            if sys.__stdout__ is not None:
                try:
                    sys.__stdout__.write(text)
                except (OSError, ValueError):
                    pass
            return len(text)

        def flush(self):
            pass

    sys.stdout = Tee()
    sys.stderr = Tee()

    def dump():
        body = buffer.getvalue().strip()
        if not body:
            return
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        try:
            previous = LOG.read_text(encoding="utf-8") if LOG.exists() else ""
            text = previous + "=== " + stamp + " ===\n" + body + "\n"
            # A breadcrumb trail, not an archive. Keep the tail, so this can
            # never be the thing that fills the disk.
            lines = text.splitlines()
            if len(lines) > 200:
                lines = lines[-200:]
            LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass

    atexit.register(dump)


_log_to_file_when_nobody_is_watching()


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(ROOT), check=False,
                          capture_output=True, text=True, timeout=120)


def main() -> int:
    listing = "--list" in sys.argv

    if not listing:
        # The queue is written by another machine, so what is on disk here is
        # only as fresh as the last pull.
        # Merge, not rebase. An interrupted rebase leaves HEAD detached, and
        # this runs unattended on a schedule where a reboot or a sleep can cut
        # it off. That exact failure left the server committing pages onto a
        # branch that did not exist for days.
        pull = git("pull", "--no-rebase", "--quiet")
        if pull.returncode != 0:
            print("Could not pull. Fix the repo first, then run this again.")
            print(pull.stderr.strip())
            return 1

    cfg = config.load(ROOT)
    waiting = artqueue.pending(ROOT)
    if not waiting:
        print("Nothing waiting.")
        return 0

    print(f"{len(waiting)} request(s) waiting:")
    for item in waiting:
        who = f" (asked by {item.who})" if item.who else ""
        print(f"  {item.page}{who}: {item.prompt}")
    if listing:
        return 0

    library = Library(cfg.content_dir)
    from universe.art import ArtService  # heavy: only imported when drawing

    art = ArtService(cfg, library, AssetStore(cfg.assets_dir))

    drawn = 0
    stale = 0
    failed = 0
    for item in waiting:
        entity = library.load(item.kind, item.slug)
        if entity is None:
            # The page was deleted or renamed after the request was made.
            print(f"  skipped {item.page}: no such page any more")
            artqueue.done(item)
            stale += 1
            continue
        print(f"  drawing {item.page} ...", flush=True)
        try:
            art.generate_custom(entity, item.prompt, count=item.count)
        except Exception as exc:  # out of memory, model missing, bad prompt
            # Leave the request in place. A failure here is usually the card
            # being busy, and the next run should try again rather than
            # silently dropping something somebody asked for.
            print(f"  failed: {exc}")
            failed += 1
            continue
        artqueue.done(item)
        drawn += 1

    if not drawn:
        # Clearing out requests for pages that no longer exist is the queue
        # working, not the queue failing, and this runs on a schedule where a
        # non-zero exit shows up as a red job somebody has to look at.
        print("Nothing to draw." if stale and not failed else "Nothing drawn.")
        if stale and not failed:
            # The requests are gone, so the repo changed even though no picture
            # was made. Push that, or the next run rediscovers them.
            git("add", "--", artqueue.FOLDER)
            git("commit", "-q", "-m",
                f"art: dropped {stale} request(s) for pages that no longer exist",
                "--", artqueue.FOLDER)
            git("push", "--quiet")
        return 1 if failed else 0

    git("add", "--", "assets", artqueue.FOLDER)
    git("commit", "-q", "-m", f"art: drew {drawn} queued request(s)",
        "--", "assets", artqueue.FOLDER)
    push = git("push", "--quiet")
    if push.returncode != 0:
        print("Drawn, but the push failed. Run update.ps1 to sort it out.")
        print(push.stderr.strip())
        return 1

    print(f"Drew {drawn}. They are on the site now, waiting to be picked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
