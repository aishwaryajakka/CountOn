from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1 import oauth


@pytest.fixture
def callback_setup(monkeypatch):
    user_id = uuid4()
    state = "valid-test-state"
    db = SimpleNamespace(
        rollback=lambda: None,
        commit=lambda: None,
        flush=lambda: None,
        add=lambda obj: None,
        scalar=lambda statement: None,
    )

    def fake_consume_oauth_state(db, value, provider="google"):
        if value == state and provider == "google_gmail":
            return user_id
        return None


    monkeypatch.setattr(
        oauth,
        "consume_oauth_state",
        fake_consume_oauth_state,
    )
    monkeypatch.setattr(
        oauth,
        "get_settings",
        lambda: SimpleNamespace(
            google_gmail_redirect_uri=(
                "https://example.test/api/v1/oauth/google/gmail/callback"
            )
        ),
    )

    return db, user_id, state


def make_request(state, cookie_state, code="test-code"):
    query = {"state": state, "code": code}
    return SimpleNamespace(
        query_params=query,
        cookies={oauth.GMAIL_STATE_COOKIE: cookie_state},
    )


def test_gmail_callback_rejects_mismatched_state(callback_setup):
    db, _, state = callback_setup
    request = make_request(state, "different-state")

    response = oauth.google_gmail_oauth_callback(request, db)

    assert response.status_code == 400
    assert "state validation failed" in response.body.decode()


def test_gmail_callback_rejects_unknown_state(
    monkeypatch, callback_setup
):
    db, _, state = callback_setup
    request = make_request(state, state)

    monkeypatch.setattr(
        oauth,
        "consume_oauth_state",
        lambda db, value, provider="google": None,
    )

    response = oauth.google_gmail_oauth_callback(request, db)

    assert response.status_code == 400
    assert "invalid, expired, or already used" in response.body.decode()


def test_gmail_callback_rejects_missing_cookie(callback_setup):
    db, _, state = callback_setup
    request = make_request(state, None)
    request.cookies = {}

    response = oauth.google_gmail_oauth_callback(request, db)

    assert response.status_code == 400
    assert "state validation failed" in response.body.decode()


def test_gmail_callback_rejects_missing_code(callback_setup):
    db, _, state = callback_setup
    request = make_request(state, state, code="")

    response = oauth.google_gmail_oauth_callback(request, db)

    assert response.status_code == 400
    assert "authorization was not completed" in response.body.decode()


def test_gmail_callback_rejects_missing_readonly_scope(
    monkeypatch, callback_setup
):
    db, _, state = callback_setup
    request = make_request(state, state)

    monkeypatch.setattr(
        oauth,
        "exchange_gmail_authorization_code",
        lambda code: {
            "access_token": "test-access",
            "expires_at": datetime.now(timezone.utc),
            "scope": "openid email",
        },
    )

    response = oauth.google_gmail_oauth_callback(request, db)

    assert response.status_code == 502
    assert "Could not complete Gmail connection" in response.body.decode()


def test_gmail_callback_rejects_invalid_identity(
    monkeypatch, callback_setup
):
    db, _, state = callback_setup
    request = make_request(state, state)

    monkeypatch.setattr(
        oauth,
        "exchange_gmail_authorization_code",
        lambda code: {
            "access_token": "test-access",
            "expires_at": datetime.now(timezone.utc),
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
        },
    )
    monkeypatch.setattr(
        oauth,
        "fetch_google_userinfo",
        lambda token: {"email": "test@example.com"},
    )

    response = oauth.google_gmail_oauth_callback(request, db)

    assert response.status_code == 502
    assert "Could not complete Gmail connection" in response.body.decode()

def test_gmail_callback_saves_connection_and_credentials(
    monkeypatch, callback_setup
):
    db, user_id, state = callback_setup
    request = make_request(state, state)
    required_scope = "https://www.googleapis.com/auth/gmail.readonly"

    saved = {}
    connection = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        provider="google",
        connection_type="email",
        external_account_id="google-user-123",
        display_name=None,
        status=None,
        scopes=[],
        connection_metadata={},
    )

    db.scalar = lambda statement: None
    db.add = lambda obj: saved.update(connection=obj)
    db.flush = lambda: None

    committed = []
    db.commit = lambda: committed.append(True)

    tokens = {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "expires_at": datetime.now(timezone.utc),
        "scope": (
            "openid email "
            "https://www.googleapis.com/auth/gmail.readonly"
        ),
        "token_type": "Bearer",
    }

    monkeypatch.setattr(
        oauth,
        "exchange_gmail_authorization_code",
        lambda code: tokens,
    )
    monkeypatch.setattr(
        oauth,
        "fetch_google_userinfo",
        lambda token: {
            "sub": "google-user-123",
            "email": "test@example.com",
        },
    )

    # Simulate the database-generated connection ID after flush.
    def fake_flush():
        saved["connection"].id = connection.id

    db.flush = fake_flush

    credentials = {}
    monkeypatch.setattr(
        oauth,
        "save_credentials",
        lambda db, **kwargs: credentials.update(kwargs),
    )

    response = oauth.google_gmail_oauth_callback(request, db)

    assert response.status_code == 200
    assert "Gmail connected successfully" in response.body.decode()

    created = saved["connection"]
    assert created.user_id == user_id
    assert created.provider == "google"
    assert created.connection_type == "email"
    assert created.external_account_id == "google-user-123"
    assert created.display_name == "test@example.com"
    assert created.status == "connected"
    assert required_scope in created.scopes
    assert created.connection_metadata == {"email": "test@example.com"}

    assert credentials["connection_id"] == connection.id
    assert credentials["access_token"] == "test-access-token"
    assert credentials["refresh_token"] == "test-refresh-token"
    assert credentials["provider"] == "google"
    assert committed

