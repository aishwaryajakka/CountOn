from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace

import httpx
import pytest

from app.services import google_oauth_service as service
from app.services.google_oauth_service import GoogleOAuthError


@pytest.fixture
def gmail_settings(monkeypatch):
    settings = SimpleNamespace(
        google_client_id="test-client-id",
        google_client_secret=SimpleNamespace(
            get_secret_value=lambda: "test-client-secret"
        ),
        google_gmail_redirect_uri="https://example.test/oauth/google/gmail/callback",
    )
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    return settings


def test_build_gmail_authorization_url(gmail_settings):
    url = service.build_gmail_authorization_url("test-state")

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert params["client_id"] == ["test-client-id"]
    assert params["redirect_uri"] == [
        "https://example.test/oauth/google/gmail/callback"
    ]
    assert params["state"] == ["test-state"]
    assert params["response_type"] == ["code"]
    assert "https://www.googleapis.com/auth/gmail.readonly" in (
        params["scope"][0].split()
    )


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("google_client_id", None),
        ("google_gmail_redirect_uri", None),
    ],
)
def test_build_gmail_authorization_url_requires_configuration(
    monkeypatch, gmail_settings, setting, value
):
    setattr(gmail_settings, setting, value)

    with pytest.raises(GoogleOAuthError):
        service.build_gmail_authorization_url("test-state")


def test_build_gmail_authorization_url_requires_state(gmail_settings):
    with pytest.raises(GoogleOAuthError, match="state"):
        service.build_gmail_authorization_url("")


def test_exchange_gmail_authorization_code_success(
    monkeypatch, gmail_settings
):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.readonly",
                "token_type": "Bearer",
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(service.httpx, "post", fake_post)

    before = datetime.now(timezone.utc)
    result = service.exchange_gmail_authorization_code("test-code")
    after = datetime.now(timezone.utc)

    assert captured["url"] == service.GOOGLE_TOKEN_URL
    assert captured["data"]["code"] == "test-code"
    assert captured["data"]["client_id"] == "test-client-id"
    assert captured["data"]["client_secret"] == "test-client-secret"
    assert captured["data"]["redirect_uri"] == (
        gmail_settings.google_gmail_redirect_uri
    )
    assert result["access_token"] == "test-access-token"
    assert result["refresh_token"] == "test-refresh-token"
    assert result["scope"] == (
        "https://www.googleapis.com/auth/gmail.readonly"
    )
    assert before < result["expires_at"] <= after.replace(
        microsecond=after.microsecond
    ) + __import__("datetime").timedelta(seconds=3601)


def test_exchange_gmail_authorization_code_requires_code(
    gmail_settings,
):
    with pytest.raises(GoogleOAuthError, match="code"):
        service.exchange_gmail_authorization_code("")


def test_exchange_gmail_authorization_code_rejects_invalid_token(
    monkeypatch, gmail_settings
):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "token-without-expiry"}

    monkeypatch.setattr(
        service.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(),
    )

    with pytest.raises(GoogleOAuthError, match="invalid token response"):
        service.exchange_gmail_authorization_code("test-code")


def test_exchange_gmail_authorization_code_handles_http_error(
    monkeypatch, gmail_settings
):
    def fake_post(*args, **kwargs):
        request = httpx.Request("POST", service.GOOGLE_TOKEN_URL)
        response = httpx.Response(400, request=request)
        raise httpx.HTTPStatusError(
            "Bad request",
            request=request,
            response=response,
        )

    monkeypatch.setattr(service.httpx, "post", fake_post)

    with pytest.raises(GoogleOAuthError, match="token exchange failed"):
        service.exchange_gmail_authorization_code("test-code")
