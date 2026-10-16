
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import google_calendar_token_service as service
from app.services.google_oauth_service import GoogleOAuthError


@pytest.fixture
def setup_service(monkeypatch):
    connection_id = uuid4()
    user_id = uuid4()
    db = SimpleNamespace(flush=lambda: None)
    connection = SimpleNamespace(
        id=connection_id,
        user_id=user_id,
        provider="google",
        connection_type="calendar",
        status="connected",
        scopes=["openid", "email", "https://www.googleapis.com/auth/calendar.events.readonly"],
    )
    monkeypatch.setattr(
        service.integration_repository,
        "get",
        lambda db, cid, uid: connection
        if cid == connection_id and uid == user_id
        else None,
    )
    return db, connection_id, user_id, connection


def test_valid_token_is_reused(monkeypatch, setup_service):
    db, connection_id, user_id, _ = setup_service
    monkeypatch.setattr(
        service,
        "get_credentials",
        lambda db, cid: {
            "access_token": "valid-access",
            "refresh_token": "refresh",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        },
    )

    def unexpected_refresh(token):
        pytest.fail("Refresh should not run for a valid token")

    monkeypatch.setattr(service, "refresh_google_access_token", unexpected_refresh)

    result = service.get_valid_google_access_token(
        db, connection_id=connection_id, user_id=user_id
    )
    assert result == "valid-access"


def test_expired_token_is_refreshed_and_saved(monkeypatch, setup_service):
    db, connection_id, user_id, connection = setup_service
    monkeypatch.setattr(
        service,
        "get_credentials",
        lambda db, cid: {
            "access_token": "old-access",
            "refresh_token": "saved-refresh",
            "expires_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        },
    )
    monkeypatch.setattr(
        service,
        "refresh_google_access_token",
        lambda token: {
            "access_token": "new-access",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "token_type": "Bearer",
        },
    )

    saved = {}

    def fake_save(db, **kwargs):
        saved.update(kwargs)

    monkeypatch.setattr(service, "save_credentials", fake_save)

    result = service.get_valid_google_access_token(
        db, connection_id=connection_id, user_id=user_id
    )

    assert result == "new-access"
    assert saved["refresh_token"] is None
    assert saved["scopes"] == " ".join(connection.scopes)
    assert saved["access_token"] == "new-access"


def test_other_user_cannot_access_connection(monkeypatch, setup_service):
    db, connection_id, _, _ = setup_service

    with pytest.raises(GoogleOAuthError):
        service.get_valid_google_access_token(
            db, connection_id=connection_id, user_id=uuid4()
        )


def test_missing_refresh_token_fails(monkeypatch, setup_service):
    db, connection_id, user_id, _ = setup_service
    monkeypatch.setattr(
        service,
        "get_credentials",
        lambda db, cid: {
            "access_token": "old-access",
            "refresh_token": None,
            "expires_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        },
    )

    with pytest.raises(GoogleOAuthError, match="refresh token is unavailable"):
        service.get_valid_google_access_token(
            db, connection_id=connection_id, user_id=user_id
        )
