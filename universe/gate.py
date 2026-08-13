"""One shared passphrase in front of the wiki.

The site has no accounts on purpose: you click your name and the world renders
for you. That was fine while the address was known to six people. Now the
project is public and a `.ts.net` hostname is guessable, so there needs to be
something between a stranger and four years of work.

This is that something, and it is deliberately the weakest thing that works:
one passphrase, shared, typed once a month. It answers "is this someone from
our table" and nothing else. Who you are is still the name you pick, still on
the honour system, still not a security boundary.

The passphrase is stored as a scrypt hash in `.wiki-passphrase` (gitignored).
Plaintext would mean the DM's screen and the group chat both hold a readable
copy, and the file gets backed up to places nobody thinks about.

The MCP endpoint is untouched: it already authenticates with per-person bearer
tokens, which are stronger than this and identify the caller.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path

FILE = ".wiki-passphrase"

# scrypt is memory-hard, which is the point: a GPU cannot parallelise it the
# way it can SHA-256. n=2**14 with 64MB of headroom takes about 60ms here.
# OpenSSL's default maxmem is 32MiB and n=2**15 needs exactly that, so it fails
# with "memory limit exceeded" unless maxmem is passed. Set it explicitly.
N, R, P = 2 ** 14, 8, 1
MAXMEM = 64 * 1024 * 1024
KEYLEN = 32


def _derive(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        passphrase.encode("utf-8"), salt=salt,
        n=N, r=R, p=P, maxmem=MAXMEM, dklen=KEYLEN,
    )


def set_passphrase(root: Path, passphrase: str) -> tuple[bool, str]:
    """Store a new passphrase. Returns (ok, message)."""
    passphrase = passphrase.strip()
    if len(passphrase) < 6:
        return False, "Use at least six characters."

    salt = secrets.token_bytes(16)
    (Path(root) / FILE).write_text(
        json.dumps({
            "algorithm": "scrypt",
            "n": N, "r": R, "p": P,
            "salt": salt.hex(),
            "hash": _derive(passphrase, salt).hex(),
        }, indent=2),
        encoding="utf-8",
    )
    return True, "Passphrase set. Everyone will be asked for it once, then not again for a month."


def is_enabled(root: Path) -> bool:
    """No file means no gate, so the wiki keeps working if nobody sets one."""
    return (Path(root) / FILE).exists()


def check(root: Path, attempt: str) -> bool:
    """Verify an attempt, in constant time, failing closed on a broken file."""
    path = Path(root) / FILE
    if not path.exists():
        return True
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
        salt = bytes.fromhex(stored["salt"])
        expected = bytes.fromhex(stored["hash"])
        derived = hashlib.scrypt(
            (attempt or "").encode("utf-8"), salt=salt,
            n=int(stored.get("n", N)), r=int(stored.get("r", R)),
            p=int(stored.get("p", P)), maxmem=MAXMEM, dklen=len(expected),
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        # A corrupt file locks everyone out rather than letting everyone in.
        return False
    return hmac.compare_digest(derived, expected)


def clear(root: Path) -> bool:
    path = Path(root) / FILE
    if path.exists():
        path.unlink()
        return True
    return False
