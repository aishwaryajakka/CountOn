
"""Encrypt OAuth tokens before they are persisted."""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class TokenEncryptionError(ValueError):
    """Raised when OAuth token encryption or decryption cannot proceed."""


def _get_cipher(key: str | None = None) -> Fernet:
    if key is None:
        configured_key = get_settings().oauth_token_encryption_key
        key = configured_key.get_secret_value() if configured_key else None

    if not key:
        raise TokenEncryptionError(
            "OAUTH_TOKEN_ENCRYPTION_KEY must be configured."
        )

    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError):
        raise TokenEncryptionError(
            "OAUTH_TOKEN_ENCRYPTION_KEY is invalid."
        ) from None


def encrypt_token(token: str, *, key: str | None = None) -> str:
    if not token:
        raise TokenEncryptionError("Token cannot be empty.")

    return _get_cipher(key).encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str, *, key: str | None = None) -> str:
    if not ciphertext:
        raise TokenEncryptionError("Encrypted token cannot be empty.")

    try:
        return _get_cipher(key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError):
        raise TokenEncryptionError(
            "Token decryption failed. Check the encryption key and ciphertext."
        ) from None
