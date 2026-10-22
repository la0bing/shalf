"""Password hashing with scrypt (stdlib, memory-hard)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    encoded = [base64.b64encode(part).decode() for part in (salt, digest)]
    return "$".join(["scrypt", str(_N), str(_R), str(_P), *encoded])


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        hashlib.scrypt(
            b"timing", salt=b"0" * 16, n=_N, r=_R, p=_P, dklen=32
        )  # same cost either way
        return False
    try:
        _, n, r, p, salt, digest = encoded.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
