"""Cryptographic utilities, password hashing, and JWT handling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from typing import Any

import bcrypt
import jwt

ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 60
MINIMUM_SECRET_KEY_LENGTH = 32


def get_jwt_secret_key() -> str:
    """Retrieve signing key from environment or fail safely.

    Refuses startup/token signing if secret is absent or insecurely short (< 32 chars).
    """
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not secret or len(secret) < MINIMUM_SECRET_KEY_LENGTH:
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable is not configured or shorter than 32 characters. "
            "A secure signing secret is required for authentication."
        )
    return secret


def get_password_hash(password: str) -> str:
    """Hash password using direct bcrypt with salt."""
    if not password:
        raise ValueError("Password must not be empty.")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create signed JWT access token with validated algorithm and claims."""
    now = datetime.now(timezone.utc)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        to_encode.update(extra_claims)

    secret_key = get_jwt_secret_key()
    return jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token against algorithm allowlist.

    Raises jwt.PyJWTError subclasses upon invalid or expired tokens.
    """
    secret_key = get_jwt_secret_key()
    return jwt.decode(
        token,
        secret_key,
        algorithms=[ALGORITHM],
        options={"require": ["sub", "exp", "iat"]},
    )
