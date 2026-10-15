
"""Encryption helpers for external OAuth tokens."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    key = settings.oauth_token_encryption_key

    if key is None:
        raise RuntimeError(
            "OAUTH_TOKEN_ENCRYPTION_KEY is not configured."
        )

    try:
        return Fernet(key.get_secret_value().encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "OAUTH_TOKEN_ENCRYPTION_KEY is invalid. "
            "It must be a valid Fernet key."
        ) from exc


def encrypt_token(token: str) -> str:
    """Encrypt a token before database storage."""
    if not token:
        raise ValueError("Token cannot be empty.")

    return _get_fernet().encrypt(
        token.encode("utf-8")
    ).decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a token when needed for provider API calls."""
    try:
        return _get_fernet().decrypt(
            encrypted_token.encode("utf-8")
        ).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            "Token decryption failed. Check the encryption key."
        ) from exc
