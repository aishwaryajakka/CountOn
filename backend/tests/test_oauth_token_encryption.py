
import pytest
from cryptography.fernet import Fernet

from app.services.oauth_token_encryption import (
    TokenEncryptionError,
    decrypt_token,
    encrypt_token,
)


@pytest.fixture
def key():
    return Fernet.generate_key().decode("ascii")


def test_token_round_trip(key):
    token = "sample-access-token"
    encrypted = encrypt_token(token, key=key)

    assert encrypted != token
    assert decrypt_token(encrypted, key=key) == token


def test_wrong_key_cannot_decrypt(key):
    encrypted = encrypt_token("sample-token", key=key)
    other_key = Fernet.generate_key().decode("ascii")

    with pytest.raises(TokenEncryptionError):
        decrypt_token(encrypted, key=other_key)


def test_tampered_ciphertext_is_rejected(key):
    encrypted = encrypt_token("sample-token", key=key)
    replacement = "A" if encrypted[-1] != "A" else "B"

    with pytest.raises(TokenEncryptionError):
        decrypt_token(encrypted[:-1] + replacement, key=key)


def test_missing_key_fails_closed(monkeypatch):
    from app.core import config
    from app.services import oauth_token_encryption as encryption

    class FakeSettings:
        oauth_token_encryption_key = None

    monkeypatch.setattr(config, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(encryption, "get_settings", lambda: FakeSettings())

    with pytest.raises(TokenEncryptionError, match="must be configured"):
        encrypt_token("sample-token")


def test_empty_token_is_rejected(key):
    with pytest.raises(TokenEncryptionError):
        encrypt_token("", key=key)
