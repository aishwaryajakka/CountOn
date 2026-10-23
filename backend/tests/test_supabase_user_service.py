
"""Tests for Supabase Auth user email lookup."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.services.supabase_user_service import get_user_email


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def settings():
    secret = MagicMock()
    secret.get_secret_value.return_value = "test-secret"

    return SimpleNamespace(
        supabase_url="https://example.supabase.co",
        supabase_secret_key=secret,
    )


def test_get_user_email_returns_verified_email(user_id, settings):
    response = MagicMock()
    response.json.return_value = {
        "email": "user@example.com",
        "email_confirmed_at": "2026-01-01T00:00:00Z",
    }
    response.raise_for_status.return_value = None

    with (
        patch(
            "app.services.supabase_user_service.get_settings",
            return_value=settings,
        ),
        patch(
            "app.services.supabase_user_service.httpx.get",
            return_value=response,
        ) as mock_get,
    ):
        email = get_user_email(user_id)

    assert email == "user@example.com"
    mock_get.assert_called_once()
    assert str(user_id) in mock_get.call_args.args[0]


def test_get_user_email_rejects_unverified_email(user_id, settings):
    response = MagicMock()
    response.json.return_value = {
        "email": "user@example.com",
        "email_confirmed_at": None,
    }
    response.raise_for_status.return_value = None

    with (
        patch(
            "app.services.supabase_user_service.get_settings",
            return_value=settings,
        ),
        patch(
            "app.services.supabase_user_service.httpx.get",
            return_value=response,
        ),pytest.raises(
        RuntimeError, match="SUPABASE_USER_EMAIL_UNVERIFIED"
    )
    ):
        get_user_email(user_id)


def test_get_user_email_handles_api_failure(user_id, settings):
    with (
        patch(
            "app.services.supabase_user_service.get_settings",
            return_value=settings,
        ),
        patch(
            "app.services.supabase_user_service.httpx.get",
            side_effect=httpx.ConnectError("test error"),
        ),pytest.raises(
        RuntimeError, match="SUPABASE_USER_LOOKUP_FAILED"
    )
    ):
        get_user_email(user_id)
