"""Wiki accounts: email, password, and who you are in the world.

Your friends make their own logins, but registration is gated by a one-time
invite code. That gate is the whole point: without it, anyone who found the URL
could register claiming to be the DM and read every secret in the campaign. A
code is bound to one person key from `people.yaml`, so registering with Wren's
code makes you Wren, and nothing the registrant types decides that.

The email address is an identifier and nothing more. Nothing is sent to it and
it is never verified, because there's no mail server here and the invite code
is what actually establishes who someone is. Say so if anyone asks why they got
no confirmation message.

Stored in `.accounts.json` (gitignored):

    {
      "users":   {"wren@example.com": {"key": "wren", "salt": "...", "hash": "..."}},
      "invites": {"CODE": {"key": "wren", "used_by": null}}
    }

Passwords are hashed with scrypt and a per-user salt. The plaintext is never
written anywhere.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

ACCOUNTS_FILE = ".accounts.json"

# scrypt parameters. n=2**15 costs ~50ms per attempt here, which is invisible
# to a person signing in and expensive for anyone guessing.
#
# maxmem must be set explicitly: these parameters need 128 * n * r = 32MiB, and
# OpenSSL's default ceiling is exactly 32MiB, so the call fails with "memory
# limit exceeded" without headroom.
_N, _R, _P, _DKLEN = 2**15, 8, 1, 32
_MAXMEM = 96 * 1024 * 1024

# Deliberately permissive. Real addresses are stranger than most patterns
# allow, and this is an identifier rather than a delivery route, so the only
# job here is to reject obvious typos.
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


@dataclass
class Account:
    email: str
    key: str  # which person in people.yaml this is


def normalise(email: str) -> str:
    """Addresses are case-insensitive in practice; store one canonical form."""
    return email.strip().lower()


class Accounts:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict = {"users": {}, "invites": {}}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                self._data["users"] = loaded.get("users", {})
                self._data["invites"] = loaded.get("invites", {})
            except json.JSONDecodeError:
                pass

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    # -- passwords -----------------------------------------------------

    @staticmethod
    def _hash(password: str, salt: bytes) -> str:
        return hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P,
            dklen=_DKLEN, maxmem=_MAXMEM,
        ).hex()

    # -- invites -------------------------------------------------------

    def mint_invite(self, key: str) -> str:
        code = secrets.token_urlsafe(9)
        self._data["invites"][code] = {"key": key.lower(), "used_by": None}
        return code

    def open_invites(self) -> dict[str, str]:
        return {
            code: info["key"]
            for code, info in self._data["invites"].items()
            if not info.get("used_by")
        }

    def invite_key(self, code: str) -> str | None:
        """The person key an unused code grants, compared in constant time."""
        found = None
        for candidate, info in self._data["invites"].items():
            if hmac.compare_digest(code, candidate) and not info.get("used_by"):
                found = info["key"]
        return found

    # -- registration and sign-in --------------------------------------

    def register(
        self, email: str, password: str, code: str
    ) -> tuple[Account | None, str]:
        email = normalise(email)
        if not EMAIL.match(email):
            return None, "That doesn't look like an email address."
        if len(password) < MIN_PASSWORD:
            return None, f"Password must be at least {MIN_PASSWORD} characters."
        if email in self._data["users"]:
            return None, "There's already an account with that email. Sign in instead."

        key = self.invite_key(code.strip())
        if key is None:
            return None, "That invite code isn't valid, or has already been used."

        salt = secrets.token_bytes(16)
        self._data["users"][email] = {
            "key": key,
            "salt": salt.hex(),
            "hash": self._hash(password, salt),
        }
        self._data["invites"][code.strip()]["used_by"] = email
        self.save()
        return Account(email=email, key=key), ""

    def authenticate(self, email: str, password: str) -> Account | None:
        record = self._data["users"].get(normalise(email))
        if record is None:
            # Hash anyway, so an unknown address takes as long as a wrong
            # password and can't be identified by timing.
            self._hash(password, b"\x00" * 16)
            return None
        salt = bytes.fromhex(record["salt"])
        if not hmac.compare_digest(self._hash(password, salt), record["hash"]):
            return None
        return Account(email=normalise(email), key=record["key"])

    def set_password(self, email: str, password: str) -> bool:
        record = self._data["users"].get(normalise(email))
        if record is None:
            return False
        salt = secrets.token_bytes(16)
        record["salt"] = salt.hex()
        record["hash"] = self._hash(password, salt)
        self.save()
        return True

    @property
    def emails(self) -> list[str]:
        return sorted(self._data["users"])

    def key_for(self, email: str) -> str | None:
        record = self._data["users"].get(normalise(email))
        return record["key"] if record else None


def load(root: Path) -> Accounts:
    return Accounts(root / ACCOUNTS_FILE)
