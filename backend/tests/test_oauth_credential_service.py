

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import oauth_credential_service as service
from app.services.oauth_token_encryption import TokenEncryptionError


@pytest.fixture
def fake_db():
    return object()


def test_save_credentials_encrypts_tokens(monkeypatch, fake_db):
    connection_id = uuid4()
    captured = {}

    monkeypatch.setattr(service, "encrypt_token", lambda token: f"encrypted:{token}")

    def fake_save(db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(service.repository, "save", fake_save)

    service.save_credentials(
        fake_db,
        connection_id=connection_id,
        access_token="access-secret",
        refresh_token="refresh-secret",
    )

    assert captured["connection_id"] == connection_id
    assert captured["encrypted_access_token"] == "encrypted:access-secret"
    assert captured["encrypted_refresh_token"] == "encrypted:refresh-secret"


def test_save_credentials_without_refresh_token(monkeypatch, fake_db):
    captured = {}

    monkeypatch.setattr(service, "encrypt_token", lambda token: f"encrypted:{token}")

    def fake_save(db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(service.repository, "save", fake_save)

    service.save_credentials(
        fake_db,
        connection_id=uuid4(),
        access_token="access-secret",
    )

    assert captured["encrypted_refresh_token"] is None


def test_get_credentials_decrypts_tokens(monkeypatch, fake_db):
    connection_id = uuid4()
    expires_at = datetime.now(timezone.utc)

    monkeypatch.setattr(
        service.repository,
        "get_by_connection_id",
        lambda db, cid: SimpleNamespace(
            encrypted_access_token="encrypted-access",
            encrypted_refresh_token="encrypted-refresh",
            expires_at=expires_at,
        ),
    )
    monkeypatch.setattr(
        service,
        "decrypt_token",
        lambda token: token.removeprefix("encrypted-"),
    )

    result = service.get_credentials(fake_db, connection_id)

    assert result == {
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_at": expires_at,
    }


def test_get_credentials_returns_none_when_missing(monkeypatch, fake_db):
    monkeypatch.setattr(
        service.repository,
        "get_by_connection_id",
        lambda db, cid: None,
    )

    assert service.get_credentials(fake_db, uuid4()) is None


def test_delete_credentials_delegates_to_repository(monkeypatch, fake_db):
    connection_id = uuid4()
    deleted = []

    monkeypatch.setattr(
        service.repository,
        "delete",
        lambda db, cid: deleted.append((db, cid)),
    )

    service.delete_credentials(fake_db, connection_id)

    assert deleted == [(fake_db, connection_id)]


def test_save_fails_closed_when_encryption_fails(monkeypatch, fake_db):
    def fail_encryption(token):
        raise TokenEncryptionError("Encryption key missing")

    monkeypatch.setattr(service, "encrypt_token", fail_encryption)

    with pytest.raises(TokenEncryptionError):
        service.save_credentials(
            fake_db,
            connection_id=uuid4(),
            access_token="access-secret",
        )
