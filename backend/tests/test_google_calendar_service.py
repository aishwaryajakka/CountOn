
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
import pytest

from app.services.google_oauth_service import GoogleOAuthError
from app.services.google_calendar_service import (
    GOOGLE_CALENDAR_EVENTS_URL,
    list_google_calendar_events,
)


def test_list_events_success():
    connection_id = uuid4()
    user_id = uuid4()
    db = Mock()

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "items": [{"id": "event-1", "summary": "Test event"}]
    }

    with (
        patch(
            "app.services.google_calendar_service.get_valid_google_access_token",
            return_value="fake-access-token",
        ) as get_token,
        patch(
            "app.services.google_calendar_service.httpx.get",
            return_value=response,
        ) as http_get,
    ):
        result = list_google_calendar_events(
            db,
            connection_id=connection_id,
            user_id=user_id,
            max_results=5,
        )

    assert result["items"][0]["summary"] == "Test event"
    get_token.assert_called_once_with(
        db,
        connection_id=connection_id,
        user_id=user_id,
    )
    db.commit.assert_called_once()

    args, kwargs = http_get.call_args
    assert args[0] == GOOGLE_CALENDAR_EVENTS_URL
    assert kwargs["headers"]["Authorization"] == "Bearer fake-access-token"
    assert kwargs["params"]["maxResults"] == 5


def test_calendar_http_error_is_sanitized():
    db = Mock()

    response = Mock()
    response.status_code = 500
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "provider error",
        request=Mock(),
        response=response,
    )

    with (
        patch(
            "app.services.google_calendar_service.get_valid_google_access_token",
            return_value="fake-access-token",
        ),
        patch(
            "app.services.google_calendar_service.httpx.get",
            return_value=response,
        ),
    ):
        with pytest.raises(
            GoogleOAuthError,
            match="Google Calendar could not return events",
        ):
            list_google_calendar_events(
                db,
                connection_id=uuid4(),
                user_id=uuid4(),
            )


def test_network_error_is_sanitized():
    with (
        patch(
            "app.services.google_calendar_service.get_valid_google_access_token",
            return_value="fake-access-token",
        ),
        patch(
            "app.services.google_calendar_service.httpx.get",
            side_effect=httpx.ConnectError("connection failed"),
        ),
    ):
        with pytest.raises(
            GoogleOAuthError,
            match="Google Calendar could not return events",
        ):
            list_google_calendar_events(
                Mock(),
                connection_id=uuid4(),
                user_id=uuid4(),
            )


def test_invalid_json_shape_is_rejected():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = ["not", "an", "object"]

    with (
        patch(
            "app.services.google_calendar_service.get_valid_google_access_token",
            return_value="fake-access-token",
        ),
        patch(
            "app.services.google_calendar_service.httpx.get",
            return_value=response,
        ),
    ):
        with pytest.raises(
            GoogleOAuthError,
            match="Google Calendar returned an invalid response",
        ):
            list_google_calendar_events(
                Mock(),
                connection_id=uuid4(),
                user_id=uuid4(),
            )
