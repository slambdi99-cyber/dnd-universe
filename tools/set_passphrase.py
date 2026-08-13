"""Set the shared passphrase that guards the wiki.

    python tools\\set_passphrase.py            # prompts, twice, without echoing
    python tools\\set_passphrase.py --suggest  # invent a memorable one first
    python tools\\set_passphrase.py --remove   # take the gate off again

It prompts rather than taking an argument, so the passphrase never lands in
your shell history, in scrollback, or in a screen share. What gets written to
`.wiki-passphrase` is a scrypt hash, not the passphrase, so the file is useless
to anyone who finds it and there is no readable copy on the machine.

Everyone types it once and stays in for about a month. It answers "is this
someone from our table" and nothing else: who you are is still the name you
pick on the way in.

The MCP server is not affected. That already authenticates with per-person
bearer tokens, which are stronger than this and say who is calling.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import config as config_mod  # noqa: E402
from universe import gate as gate_mod  # noqa: E402

# Short, unambiguous, easy to spell down a Discord call. 256 words, so five
# picks is 40 bits: far beyond anything worth brute-forcing against scrypt.
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suggest", action="store_true",
                    help="Print a few memorable passphrases and exit")
    ap.add_argument("--remove", action="store_true",
                    help="Remove the gate; the wiki goes back to open")
    args = ap.parse_args()

    cfg = config_mod.load()

    if args.suggest:
        print("\nPick one, then run this again without --suggest:\n")
        for _ in range(5):
            print("   " + "-".join(secrets.choice(WORDS) for _ in range(4)))
        print()
        return 0

    if args.remove:
        if gate_mod.clear(cfg.root):
            print("Gate removed. Anyone with the link can walk in again.")
        else:
            print("There was no passphrase set.")
        return 0

    if gate_mod.is_enabled(cfg.root):
        print("A passphrase is already set. Entering a new one replaces it,")
        print("and everyone signed in now will be asked again.\n")

    try:
        first = getpass.getpass("Passphrase (typing is hidden): ")
        second = getpass.getpass("Again, to be sure: ")
    except (EOFError, KeyboardInterrupt):
        print("\nNothing changed.")
        return 1

    if first != second:
        print("Those don't match. Nothing changed.", file=sys.stderr)
        return 1

    ok, message = gate_mod.set_passphrase(cfg.root, first)
    if not ok:
        print(message, file=sys.stderr)
        return 1

    print(f"\n{message}")
    print("\nRestart the wiki for it to take effect:")
    print("  powershell -ExecutionPolicy Bypass -File .\\start.ps1")
    print("\nThen put it in the group chat. It is not stored anywhere readable,")
    print("so if everyone forgets it, run this again to set a new one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
