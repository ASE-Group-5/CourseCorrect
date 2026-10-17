"""Encryption helpers for Google Calendar credentials."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().calendar_token_encryption_key
    if not key:
        raise RuntimeError("Calendar token encryption is not configured")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Calendar token encryption key is invalid") from exc


def encrypt_refresh_token(refresh_token: str) -> str:
    """Encrypt a Google refresh token for database storage."""
    return _fernet().encrypt(refresh_token.encode()).decode()


def decrypt_refresh_token(encrypted_token: str) -> str:
    """Decrypt a stored refresh token, rejecting tampered ciphertext."""
    try:
        return _fernet().decrypt(encrypted_token.encode()).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ValueError("Stored calendar credentials are unusable") from exc
