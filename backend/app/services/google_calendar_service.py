
"""Fetch Google Calendar events using stored OAuth credentials."""

from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.services.google_oauth_service import GoogleOAuthError
from app.services.google_calendar_token_service import (
    get_valid_google_access_token,
)


GOOGLE_CALENDAR_EVENTS_URL = (
    "https://www.googleapis.com/calendar/v3/calendars/primary/events"
)


def list_google_calendar_events(
    db: Session,
    *,
    connection_id: UUID,
    user_id: UUID,
    max_results: int = 10,
) -> dict:
    """Fetch events for the authenticated user's connected Google Calendar."""
    access_token = get_valid_google_access_token(
        db,
        connection_id=connection_id,
        user_id=user_id,
    )

    # Persist refreshed credentials before making the Calendar request.
    db.commit()

    try:
        response = httpx.get(
            GOOGLE_CALENDAR_EVENTS_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
                "timeMin": "2000-01-01T00:00:00Z",
            },
            timeout=10.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise GoogleOAuthError(
                "Google rejected the access token; reconnect the account."
            ) from None
        raise GoogleOAuthError(
            "Google Calendar could not return events."
        ) from None
    except (httpx.HTTPError, ValueError):
        raise GoogleOAuthError(
            "Google Calendar could not return events."
        ) from None

    if not isinstance(payload, dict):
        raise GoogleOAuthError("Google Calendar returned an invalid response.")

    return payload
