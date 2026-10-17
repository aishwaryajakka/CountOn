
import pytest
from unittest.mock import patch

from app.api.dependencies import get_current_user
from app.main import app


pytestmark = pytest.mark.integration


def test_calendar_events_success(client, db, users):
    connection_response = client.post(
        "/api/v1/integrations",
        json={
            "provider": "google",
            "connection_type": "calendar",
            "status": "connected",
            "display_name": "Test Calendar",
        },
    )
    assert connection_response.status_code == 201
    connection_id = connection_response.json()["id"]

    expected = {
        "items": [
            {"id": "event-1", "summary": "Test event"}
        ]
    }

    with patch(
        "app.api.v1.calendar.list_google_calendar_events",
        return_value=expected,
    ) as mock_list:
        response = client.get(
            f"/api/v1/calendar/connections/{connection_id}/events"
        )

    assert response.status_code == 200
    assert response.json() == expected
    mock_list.assert_called_once()


def test_calendar_events_google_error_is_sanitized(client):
    from app.services.google_oauth_service import GoogleOAuthError

    connection_response = client.post(
        "/api/v1/integrations",
        json={
            "provider": "google",
            "connection_type": "calendar",
            "status": "connected",
        },
    )
    connection_id = connection_response.json()["id"]

    with patch(
        "app.api.v1.calendar.list_google_calendar_events",
        side_effect=GoogleOAuthError("sensitive provider details"),
    ):
        response = client.get(
            f"/api/v1/calendar/connections/{connection_id}/events"
        )

    assert response.status_code == 502
    assert "sensitive provider details" not in response.text


def test_calendar_events_reject_invalid_connection_id(client):
    response = client.get(
        "/api/v1/calendar/connections/not-a-uuid/events"
    )

    assert response.status_code == 422


def test_calendar_events_requires_authentication(client, monkeypatch):
    from app.api.dependencies import get_current_user

    app.dependency_overrides.pop(get_current_user, None)

    response = client.get(
        "/api/v1/calendar/connections/"
        "10000000-0000-4000-8000-000000000001/events"
    )

    assert response.status_code == 401
