"""Generate a wiki password your table can actually type.

Writes a five-word passphrase to `.wiki-password` (gitignored). Words rather
than random characters because five friends have to type this on phones, and a
passphrase they'll actually use beats a stronger one they paste into a group
chat and then lose.

    python tools\\make_wiki_password.py          # generate, or show the existing one
    python tools\\make_wiki_password.py --force  # replace it

The file is printed only when you ask for it, so it doesn't end up in logs or
scrollback by accident.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402

# 256 short, unambiguous, easy-to-spell words. Five picks gives 40 bits, which
# is far beyond anything worth brute-forcing over a tunnel nobody has guessed.
WORDS = """
amber anchor anvil apple arbor arrow ashen aspen badge banjo barley basin beacon
beetle bellow birch bishop bison blade bloom bluff bolt bonfire border bramble
brass bridge bronze brook burrow candle canvas canyon cedar chalk chapel cider
cinder clover cobalt copper coral cotton cove crane crater creek crest crow
crown crystal cypress dagger dapple dawn delta ditch dovetail dragon drift
dusty ember falcon fable fathom fennel fern ferry fiddle finch flagon flint
forge fossil fountain fox frost gale garnet gate ginger glade glass gorge
granite grove gully hammer harbor harvest hawk hazel hearth heather hedge
hemlock heron hickory hollow honey hornet ink iris ivory jade jasper juniper
kettle kiln lantern larch lark laurel ledge lichen lily linen lodge loom lupine
lyre maple marble marsh meadow mica mint mire mist moss moth nettle nickel
oaken ochre onyx opal orchard osprey otter owl paddle parchment peak pearl
pebble pewter pigeon pillar pine plover plum pond poplar prairie quarry quartz
quill rafter ragged rapids raven reed relic ridge rill rook rosin rowan rudder
rushes rust saddle sage sandbar sapling satchel scarlet sedge shale shell
shepherd shore sienna signal silo silver sled slate sloop smoke sorrel spark
sparrow spindle spire spruce spur stable starling steeple stirrup stonework
stork stream sumac summit swallow sycamore tallow tamarack tangle teal tender
thicket thimble thistle thorn thrush timber tinder toll torrent tower trail
trellis trout trowel tundra turret umber valley vane velvet verdant vessel vine
violet walnut warden warren watch weaver whistle willow window winter wolf
woodland wren yarrow yeoman yonder
""".split()


def generate(words: int = 5) -> str:
    return "-".join(secrets.choice(WORDS) for _ in range(words))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="Replace an existing password")
    ap.add_argument("--show", action="store_true", help="Print it to the terminal")
    ap.add_argument("--words", type=int, default=5)
    args = ap.parse_args()

    cfg = config_mod.load()
    path = cfg.root / ".wiki-password"

    if path.exists() and not args.force:
        print(f"A password already exists at {path}")
        if args.show:
            print(f"\n  {path.read_text(encoding='utf-8').strip()}\n")
        else:
            print("Open that file to read it, or pass --show. Use --force to replace.")
        return 0

    password = generate(args.words)
    path.write_text(password, encoding="utf-8")
    entropy = args.words * 8  # 256 words = 8 bits each
    print(f"Wrote a {args.words}-word password to {path}  (~{entropy} bits)")
    if args.show:
        print(f"\n  {password}\n")
    else:
        print("Open that file to read it, or re-run with --show.")

    print(
        "\nServe the wiki with it:\n"
        '  $env:UNIVERSE_WIKI_PASSWORD = (Get-Content .wiki-password -Raw).Trim()\n'
        "  .\\.venv\\Scripts\\python.exe mcp_server.py --http --wiki site "
        "--allowed-host <your-host>"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
