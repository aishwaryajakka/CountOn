"""Compatibility URL adapters to the ONE canonical delegated OAuth authority.

No independent credentials, cookie session, PKCE/state format, or token store.
Provider redirect URIs must still be explicitly configured and registered.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.api.v1 import provider_oauth, provider_sync
from app.core.config import get_settings
from app.integrations.accounts import account_oauth
from app.schemas.integration import IntegrationCreate
from app.services import integration_service

router = APIRouter(prefix="/oauth", tags=["oauth-compatibility"])
Database = Annotated[Session, Depends(get_db)]


def start(db, user_id, provider, kind, connection_id=None):
    if connection_id:
        connection = integration_service.get(db, connection_id, user_id)
        if connection.provider != provider or connection.connection_type != kind:
            raise HTTPException(
                409, "Select the requested provider and connection type"
            )
    else:
        connections = integration_service.list_connections(
            db, user_id, provider=provider, connection_type=kind, limit=2
        )
        if len(connections) > 1:
            raise HTTPException(409, "Choose an account using connection_id")
        connection = (
            connections[0]
            if connections
            else integration_service.create(
                db, IntegrationCreate(provider=provider, connection_type=kind), user_id
            )
        )
    return {
        "authorization_url": account_oauth(get_settings(), connection).begin(
            db, connection.id, user_id
        )
    }


@router.get("/google/start")
@router.get("/google/login")
def google(
    response: Response,
    db: Database,
    user: CurrentUser,
    connection_id: UUID | None = None,
):
    response.headers["Cache-Control"] = "no-store"
    return start(db, user.id, "google", "calendar", connection_id)


@router.get("/google/gmail/start")
def gmail(
    response: Response,
    db: Database,
    user: CurrentUser,
    connection_id: UUID | None = None,
):
    response.headers["Cache-Control"] = "no-store"
    return start(db, user.id, "google", "email", connection_id)


@router.get("/microsoft/outlook/start")
def outlook(
    response: Response,
    db: Database,
    user: CurrentUser,
    connection_id: UUID | None = None,
):
    response.headers["Cache-Control"] = "no-store"
    return start(db, user.id, "microsoft", "email", connection_id)


@router.get("/microsoft/calendar/start")
def microsoft_calendar(
    response: Response,
    db: Database,
    user: CurrentUser,
    connection_id: UUID | None = None,
):
    response.headers["Cache-Control"] = "no-store"
    return start(db, user.id, "microsoft", "calendar", connection_id)


@router.get("/google/callback")
@router.get("/google/gmail/callback")
def google_callback(request: Request, db: Database):
    return provider_sync.google_callback(request, db)


@router.post("/microsoft/outlook/callback")
@router.post("/microsoft/calendar/callback")
async def microsoft_callback(request: Request, db: Database):
    # Preserve the canonical form_post contract; do not expose codes in GET URLs.
    return await provider_oauth.callback(request, db)
