import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_ph = PasswordHasher()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_secret(secret: str) -> str:
    return _ph.hash(secret)


def verify_secret(hashed: str | None, secret: str) -> bool:
    if not hashed:
        return False
    try:
        return _ph.verify(hashed, secret)
    except (VerificationError, InvalidHashError):
        return False
