"""Preserve main's authenticated manual-event URLs without provider impersonation."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.api.v1.calendar import projected_items, selected_stream
from app.core.exceptions import InvalidExpectationError
from app.schemas.evidence import EvidenceResponse
from app.services import integration_event_service as service
from app.services import provider_sync_service

router = APIRouter(prefix="/integrations", tags=["manual-events"])
Database = Annotated[Session, Depends(get_db)]


def ingest(kind, db, expectation_id, user_id, event):
    try:
        return getattr(service, f"ingest_{kind}_event")(
            db, expectation_id, user_id, event
        )
    except ValueError:
        raise InvalidExpectationError(
            "Check the manual event identifier, timestamp and fact fields"
        ) from None


@router.post(
    "/{expectation_id}/events/ring", response_model=EvidenceResponse, status_code=201
)
def ring(
    expectation_id: UUID,
    db: Database,
    user: CurrentUser,
    event: Annotated[dict, Body()],
):
    return ingest("ring", db, expectation_id, user.id, event)


@router.post(
    "/{expectation_id}/events/bee", response_model=EvidenceResponse, status_code=201
)
def bee(
    expectation_id: UUID,
    db: Database,
    user: CurrentUser,
    event: Annotated[dict, Body()],
):
    return ingest("bee", db, expectation_id, user.id, event)


@router.post(
    "/{expectation_id}/events/email", response_model=EvidenceResponse, status_code=201
)
def email(
    expectation_id: UUID,
    db: Database,
    user: CurrentUser,
    event: Annotated[dict, Body()],
):
    return ingest("email", db, expectation_id, user.id, event)


# Main's service-specific sync/read URLs reuse the canonical selected stream.


@router.post("/{connection_id}/outlook/sync")
def outlook_sync(
    connection_id: UUID,
    db: Database,
    user: CurrentUser,
    top: Annotated[int, Query(ge=1, le=100)] = 25,
):
    state = selected_stream(
        db, user.id, connection_id=connection_id, provider="microsoft", kind="email"
    )
    provider_sync_service.queue(db, state.id, user.id)
    return {
        "queued": True,
        "sync_id": state.id,
        "messages_processed": 0,
        "evidence_created": 0,
    }


@router.post("/{connection_id}/microsoft-calendar/sync")
def microsoft_calendar_sync(
    connection_id: UUID,
    db: Database,
    user: CurrentUser,
    top: Annotated[int, Query(ge=1, le=100)] = 10,
):
    state = selected_stream(
        db, user.id, connection_id=connection_id, provider="microsoft"
    )
    provider_sync_service.queue(db, state.id, user.id)
    return {
        "queued": True,
        "sync_id": state.id,
        "items": projected_items(db, user.id, state, top),
    }


@router.get("/google/gmail/messages")
def gmail_messages(
    db: Database,
    user: CurrentUser,
    max_results: Annotated[int, Query(ge=1, le=100)] = 10,
):
    state = selected_stream(db, user.id, provider="google", kind="email")
    return {"messages": projected_items(db, user.id, state, max_results)}
