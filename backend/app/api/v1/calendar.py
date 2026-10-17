
"""Authenticated Google Calendar endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.services.google_oauth_service import GoogleOAuthError
from app.services.google_calendar_service import list_google_calendar_events


router = APIRouter(prefix="/calendar", tags=["Google Calendar"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/connections/{connection_id}/events")
def list_events(
    connection_id: UUID,
    db: Database,
    user: CurrentUser,
    max_results: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict:
    """List events from the user's connected Google Calendar."""
    try:
        return list_google_calendar_events(
            db,
            connection_id=connection_id,
            user_id=user.id,
            max_results=max_results,
        )
    except GoogleOAuthError as exc:
        db.rollback()
        message = str(exc)

        if "not found" in message.lower():
            raise HTTPException(
                status_code=404,
                detail="Connected Google Calendar was not found.",
            ) from None

        raise HTTPException(
            status_code=502,
            detail="Google Calendar request failed.",
        ) from None
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not load Google Calendar events.",
        ) from None
