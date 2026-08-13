"""Mint invite codes so your table can create their own wiki accounts.

Registration is open but gated: a code is bound to one person in people.yaml,
and using it makes the new account that person. This is what stops anyone who
finds the URL from registering as the DM.

    python tools\\make_invites.py           # one code per person without an account
    python tools\\make_invites.py --show    # print them, to hand out
    python tools\\make_invites.py --for wren

Codes are single use. Hand each one to the right person: whoever redeems Wren's
code can read Wren's secrets.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from universe import accounts as accounts_mod  # noqa: E402
from universe import config as config_mod  # noqa: E402
from universe import people as people_mod  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show", action="store_true", help="Print the codes")
    ap.add_argument("--for", dest="only", metavar="KEY",
                    help="Mint a code for just this person")
    args = ap.parse_args()

    cfg = config_mod.load()
    registry = people_mod.load(cfg.root)
    if not registry.members:
        print("No people in people.yaml.", file=sys.stderr)
        return 1

    accounts = accounts_mod.load(cfg.root)
    registered = {accounts.key_for(u) for u in accounts.emails}
    outstanding = set(accounts.open_invites().values())

    if args.only:
        wanted = [args.only.strip().lower()]
        if wanted[0] not in registry.members:
            print(f"No person with key {args.only!r}.", file=sys.stderr)
            return 1
    else:
        # Don't mint for people who already have an account or a live code.
        wanted = [
            k for k in registry.members
            if k not in registered and k not in outstanding
        ]

    minted = {key: accounts.mint_invite(key) for key in wanted}
    if minted:
        accounts.save()

    print(f"{len(accounts.emails)} account(s), "
          f"{len(accounts.open_invites())} unused invite(s)")
    if minted:
        print(f"  minted for: {', '.join(sorted(minted))}")
    else:
        print("  nothing to mint: everyone has an account or an open invite.")

    if args.show:
        codes = accounts.open_invites()
        if not codes:
            print("\nNo unused codes.")
            return 0
        print("\nHand each code to the right person. Whoever uses it becomes "
              "that person.\n")
        for code, key in sorted(codes.items(), key=lambda kv: kv[1]):
            person = registry.members.get(key)
            label = person.name if person else key
            role = "DM" if person and person.is_dm else (
                person.character if person and person.character else "player")
            print(f"  {label} ({role})")
            print(f"      {code}\n")
    elif minted:
        print("\nRe-run with --show to print them.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

