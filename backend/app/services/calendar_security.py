"""Encryption helpers for Google Calendar credentials."""

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

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


def google_account_fingerprint(account_id: str) -> str:
    """Return a stable, non-reversible fingerprint for a verified Google ID."""
    if not account_id:
        raise ValueError("Google account identity is unavailable")

    _fernet()
    key = get_settings().calendar_token_encryption_key
    assert key is not None
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"coursecorrect-calendar-identity-v1",
        info=b"google-account-fingerprint",
    ).derive(base64.urlsafe_b64decode(key.encode()))
    return hmac.new(
        derived_key, account_id.encode(), hashlib.sha256
    ).hexdigest()
