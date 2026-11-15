"""Password hashing and login tokens (stories 1-2)."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the password."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if the password matches the bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # Malformed hash or a password over 72 bytes.
        return False


TOKEN_USER_FIELDS = ("username", "email", "full_name", "role")


def create_access_token(user: dict) -> str:
    """Return a signed token carrying the user until it expires."""
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    claims = {field: user[field] for field in TOKEN_USER_FIELDS}
    return jwt.encode(
        {"sub": str(user["id"]), **claims, "exp": expires},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict | None:
    """Return the user in a valid, unexpired token, or None otherwise."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", *TOKEN_USER_FIELDS]},
        )
        return {
            "id": int(payload["sub"]),
            **{field: payload[field] for field in TOKEN_USER_FIELDS},
        }
    except (jwt.InvalidTokenError, ValueError):
        return None
