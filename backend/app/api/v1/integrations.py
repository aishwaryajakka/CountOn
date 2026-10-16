
"""Authenticated connected accounts and provider event ingestion."""

from typing import Annotated
from uuid import UUID

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


@router.post("/{expectation_id}/events/ring", status_code=201)
def ingest_ring_event(
    expectation_id: UUID,
    db: Database,
    user: CurrentUser,
    event: dict = Body(...),
):
    try:
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
