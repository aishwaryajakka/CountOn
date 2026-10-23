"""Main-compatible calendar reads from canonical owned, authorized projections."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.core.config import get_settings
from app.db.models import ProviderSyncState
from app.integrations.provider import ProviderError
from app.services import integration_service, provider_sync_service

router = APIRouter(prefix="/calendar", tags=["calendar"])
Database = Annotated[Session, Depends(get_db)]


def selected_stream(db, user_id, *, connection_id=None, provider=None, kind="calendar"):
    if connection_id:
        connection = integration_service.get(db, connection_id, user_id)
        if (
            connection.connection_type != kind
            or provider
            and connection.provider != provider
        ):
            raise HTTPException(
                409, "Select an authorized account of the requested type"
            )
    query = select(ProviderSyncState).where(ProviderSyncState.user_id == user_id)
    if connection_id:
        query = query.where(ProviderSyncState.connection_id == connection_id)
    states = list(db.scalars(query.order_by(ProviderSyncState.id).limit(21)))
    if len(states) > 20:
        raise HTTPException(409, "Narrow the selected source in Connected Accounts")
    matches = []
    for state in states:
        if connection_id and state.connection_id != connection_id:
            continue
        connection = integration_service.get(db, state.connection_id, user_id)
        if connection.connection_type == kind and (
            not provider or connection.provider == provider
        ):
            matches.append(state)
    if len(matches) != 1:
        raise HTTPException(
            409,
            "Select exactly one authorized synchronized source in Connected Accounts",
        )
    return matches[0]


def projected_items(db, user_id, state, limit):
    events = provider_sync_service.events(db, get_settings(), state.id, user_id)
    return [
        {
            "id": row["id"],
            "summary": row["facts"].get("title"),
            "start": row["facts"].get("start"),
            "end": row["facts"].get("end"),
            "status": row["facts"].get("status"),
            "facts": row["facts"],
        }
        for row in events[:limit]
    ]


@router.get("/connections/{connection_id}/events")
def list_events(
    connection_id: UUID,
    db: Database,
    user: CurrentUser,
    max_results: Annotated[int, Query(ge=1, le=100)] = 10,
):
    state = selected_stream(db, user.id, connection_id=connection_id)
    try:
        return {"items": projected_items(db, user.id, state, max_results)}
    except ProviderError:
        raise HTTPException(502, "Calendar projection is unavailable") from None
