
"""Authenticated connected accounts and provider event ingestion."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response, Body, HTTPException
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.db.models.integration import (
    ConnectionStatus,
    ConnectionType,
    Provider,
)
from app.schemas.integration import (
    IntegrationCreate,
    IntegrationResponse,
    IntegrationUpdate,
)
from app.services import integration_event_service
from app.services import integration_service as service
from app.schemas.evidence import EvidenceResponse
from app.services import integration_event_service
from app.services import outlook_sync_service
from app.services.microsoft_outlook_service import MicrosoftOutlookError
from app.services.microsoft_token_service import MicrosoftOAuthError
from app.services.microsoft_calendar_service import (
    list_microsoft_calendar_events,
    MicrosoftCalendarError,
)
from app.services.gmail_service import fetch_gmail_messages

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])
Database = Annotated[Session, Depends(get_db)]


@router.post("", response_model=IntegrationResponse, status_code=201)
def create(
    payload: IntegrationCreate,
    db: Database,
    user: CurrentUser,
):
    return service.create(db, payload, user.id)


@router.get("", response_model=list[IntegrationResponse])
def list_connections(
    db: Database,
    user: CurrentUser,
    provider: Provider | None = None,
    connection_type: ConnectionType | None = None,
    status: ConnectionStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list_connections(
        db,
        user.id,
        provider=provider,
        connection_type=connection_type,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/{id}", response_model=IntegrationResponse)
def get(
    id: UUID,
    db: Database,
    user: CurrentUser,
):
    return service.get(db, id, user.id)


@router.patch("/{id}", response_model=IntegrationResponse)
def update(
    id: UUID,
    payload: IntegrationUpdate,
    db: Database,
    user: CurrentUser,
):
    return service.update(db, id, payload, user.id)


@router.delete("/{id}", status_code=204)
def delete(
    id: UUID,
    db: Database,
    user: CurrentUser,
):
    service.delete(db, id, user.id)
    return Response(status_code=204)

@router.post(
    "/{expectation_id}/events/bee",
    response_model=EvidenceResponse,
    status_code=201,
    summary="Ingest a simulated Bee event",
)
def ingest_bee_event(

@router.post("/{expectation_id}/events/ring", status_code=201)
def ingest_ring_event(
    expectation_id: UUID,
    db: Database,
    user: CurrentUser,
    event: dict = Body(...),
):
    try:
        return integration_event_service.ingest_bee_event(
        return integration_event_service.ingest_ring_event(
            db=db,
            expectation_id=expectation_id,
            user_id=user.id,
            event=event,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

@router.post("/{connection_id}/outlook/sync")
def sync_outlook(
    connection_id: UUID,
    db: Database,
    user: CurrentUser,
    top: Annotated[int, Query(ge=1, le=100)] = 25,
):
    try:
        return outlook_sync_service.sync_outlook_emails(
            db=db,
            connection_id=connection_id,
            user_id=user.id,
            top=top,
        )
    except (MicrosoftOAuthError, MicrosoftOutlookError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{connection_id}/microsoft-calendar/sync")
def sync_microsoft_calendar(
    connection_id: UUID,
    db: Database,
    user: CurrentUser,
    top: Annotated[int, Query(ge=1, le=100)] = 10,
):
    """Fetch upcoming events from a connected Microsoft Calendar."""
    try:
        return list_microsoft_calendar_events(
            db=db,
            connection_id=connection_id,
            user_id=user.id,
            top=top,
        )
    except MicrosoftOAuthError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MicrosoftCalendarError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not load Microsoft Calendar events.",
        ) from None

@router.post("/{expectation_id}/events/bee", status_code=201)
def ingest_bee_event(
    expectation_id: UUID,
    db: Database,
    user: CurrentUser,
    event: dict = Body(...),
):
    try:
        return integration_event_service.ingest_bee_event(
            db=db,
            expectation_id=expectation_id,
            user_id=user.id,
            event=event,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.post("/{expectation_id}/events/email", status_code=201)
def ingest_email_event(
    expectation_id: UUID,
    db: Database,
    user: CurrentUser,
    event: dict = Body(...),
):
    try:
        return integration_event_service.ingest_email_event(
            db=db,
            expectation_id=expectation_id,
            user_id=user.id,
            event=event,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.get("/google/gmail/messages")
def get_gmail_messages(
    db: Database,
    user: CurrentUser,
    max_results: Annotated[int, Query(ge=1, le=100)] = 10,
):
    try:
        return fetch_gmail_messages(
            db=db,
            user_id=user.id,
            max_results=max_results,
        )
    except Exception as exc:
        logger.error(
            "Gmail endpoint failed: %s: %s",
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise
