"""Main calendar URLs retain ownership and bounded canonical projection reads."""

from unittest.mock import patch
from uuid import UUID

import pytest

from app.api.dependencies import get_current_user
from app.db.models import ProviderSyncState
from app.integrations.provider import ProviderError
from app.main import app

pytestmark = pytest.mark.integration


def calendar(client, db, users):
    connection = client.post(
        "/api/v1/integrations",
        json={
            "provider": "google",
            "connection_type": "calendar",
            "display_name": "Test calendar",
        },
    ).json()
    db.add(
        ProviderSyncState(
            connection_id=UUID(connection["id"]),
            user_id=users[0].id,
            stream="selected-calendar",
        )
    )
    db.commit()
    return connection["id"]


def test_calendar_events_success(client, db, users):
    identity = calendar(client, db, users)
    facts = [
        {
            "id": "event-1",
            "facts": {"title": "Test event", "start": "2026-10-23T12:00:00Z"},
        }
    ]
    with patch("app.api.v1.calendar.provider_sync_service.events", return_value=facts):
        response = client.get(f"/api/v1/calendar/connections/{identity}/events")
    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "event-1"
    assert response.json()["items"][0]["summary"] == "Test event"


def test_calendar_events_google_error_is_sanitized(client, db, users):
    identity = calendar(client, db, users)
    with patch(
        "app.api.v1.calendar.provider_sync_service.events",
        side_effect=ProviderError("PROVIDER_UNAVAILABLE"),
    ):
        response = client.get(f"/api/v1/calendar/connections/{identity}/events")
    assert response.status_code == 502
    assert response.json()["error"]["message"] == "Http error"


def test_calendar_events_reject_invalid_connection_id(client):
    assert (
        client.get("/api/v1/calendar/connections/not-a-uuid/events").status_code == 422
    )


def test_calendar_events_requires_authentication(client):
    app.dependency_overrides.pop(get_current_user, None)
    assert (
        client.get(
            "/api/v1/calendar/connections/10000000-0000-4000-8000-000000000001/events"
        ).status_code
        == 401
    )


def test_calendar_events_cannot_read_another_user(client, db, users):
    identity = calendar(client, db, users)
    app.dependency_overrides[get_current_user] = lambda: users[1]
    assert (
        client.get(f"/api/v1/calendar/connections/{identity}/events").status_code == 404
    )
