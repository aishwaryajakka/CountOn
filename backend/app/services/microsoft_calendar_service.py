
"""Fetch calendar events through Microsoft Graph."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.models.calendar_event import CalendarEvent
from app.db.models.integration import IntegrationConnection
from app.services.microsoft_token_service import (
    MicrosoftOAuthError,
    get_valid_microsoft_access_token,
)

GRAPH_EVENTS_URL = "https://graph.microsoft.com/v1.0/me/events"


class MicrosoftCalendarError(Exception):
    """Raised when Microsoft Calendar retrieval fails."""

def _parse_event_datetime(value: Any) -> datetime | None:
    """Parse a Microsoft Graph event datetime into a timezone-aware datetime."""
    if not isinstance(value, dict):
        return None

    raw_value = value.get("dateTime")
    if not isinstance(raw_value, str):
        return None

    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None

    # Microsoft Graph can return a datetime without an explicit UTC offset.
    event_timezone = value.get("timeZone")
    if parsed.tzinfo is None and event_timezone == "UTC":
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed

def list_microsoft_calendar_events(
    db: Session,
    *,
    connection_id: UUID,
    user_id: UUID,
    top: int = 10,
) -> dict[str, Any]:
    """Fetch recent and upcoming events from an owned calendar connection."""

    if not 1 <= top <= 100:
        raise ValueError("top must be between 1 and 100")

    try:
        access_token = get_valid_microsoft_access_token(
            db,
            connection_id=connection_id,
            user_id=user_id,
            connection_type="calendar",
        )

        # Persist refreshed credentials before making the Graph request.
        db.commit()

        now = datetime.now(timezone.utc).isoformat()
        response = httpx.get(
            GRAPH_EVENTS_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "$top": top,
                "$orderby": "start/dateTime",
                "$filter": f"end/dateTime ge '{now}'",
                "$select": (
                    "id,subject,bodyPreview,start,end,location,"
                    "organizer,isCancelled,webLink"
                ),
            },
            timeout=15.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()

    except MicrosoftOAuthError:
        db.rollback()
        raise
    except httpx.HTTPStatusError as exc:
        db.rollback()

        if exc.response.status_code == 401:
            raise MicrosoftCalendarError(
                "Microsoft rejected the token; reconnect Calendar."
            ) from None

        if exc.response.status_code == 403:
            raise MicrosoftCalendarError(
                "Microsoft denied calendar access; check Calendars.Read."
            ) from None

        raise MicrosoftCalendarError(
            "Microsoft Graph could not return calendar events."
        ) from None
    except (httpx.HTTPError, ValueError):
        db.rollback()
        raise MicrosoftCalendarError(
            "Could not retrieve Microsoft Calendar events."
        ) from None


    if not isinstance(payload, dict) or not isinstance(
        payload.get("value"), list
    ):
        raise MicrosoftCalendarError(
            "Microsoft Graph returned an invalid calendar response."
        )

    try:
        connection = db.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.id == connection_id,
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.connection_type == "calendar",
            )
        )

        if connection is None:
            raise MicrosoftCalendarError(
                "Microsoft Calendar connection was not found."
            )

        synced_at = datetime.now(timezone.utc)

        for event in payload["value"]:
            if not isinstance(event, dict):
                continue

            external_id = event.get("id")
            if not isinstance(external_id, str) or not external_id:
                continue

            saved_event = db.scalar(
                select(CalendarEvent).where(
                    CalendarEvent.connection_id == connection_id,
                    CalendarEvent.external_event_id == external_id,
                )
            )

            if saved_event is None:
                saved_event = CalendarEvent(
                    connection_id=connection_id,
                    external_event_id=external_id,
                )
                db.add(saved_event)

            saved_event.subject = event.get("subject")
            saved_event.start_at = _parse_event_datetime(event.get("start"))
            saved_event.end_at = _parse_event_datetime(event.get("end"))
            saved_event.is_cancelled = bool(event.get("isCancelled", False))
            saved_event.event_data = event
            saved_event.last_synced_at = synced_at

        connection.last_synced_at = synced_at
        connection.sync_status = "idle"

        db.commit()

    except MicrosoftCalendarError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise MicrosoftCalendarError(
            "Could not save Microsoft Calendar events."
        ) from None

    return payload