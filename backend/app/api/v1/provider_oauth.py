"""Backend-only consent/code exchange with the existing authenticated principal."""

from datetime import datetime, timezone
from hashlib import sha256
from typing import Annotated
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import CurrentUser, get_db
from app.core.config import get_settings
from app.db.models.integration import ProviderOAuthState
from app.integrations.microsoft import MicrosoftOAuth
from app.integrations.provider import ProviderError
from app.schemas.integration import IntegrationResponse

router = APIRouter(prefix="/integrations", tags=["provider-oauth"])
Database = Annotated[Session, Depends(get_db)]


class OAuthCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    state: SecretStr = Field(min_length=32, max_length=128)
    code: SecretStr = Field(min_length=1, max_length=8192)


class AuthorizationURL(BaseModel):
    authorization_url: str


@router.post("/oauth/microsoft/callback", response_class=HTMLResponse)
async def callback(request: Request, db: Database):
    # form_post avoids authorization codes in URL/access logs. The initial JWT
    # owner is resolved from durable one-time state, never from callback input.
    if (
        request.headers.get("Content-Type", "").split(";")[0]
        != "application/x-www-form-urlencoded"
    ):
        raise ProviderError("OAUTH_STATE_INVALID", retryable=False)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 12000:
            raise ProviderError("OAUTH_STATE_INVALID", retryable=False)
    try:
        form = parse_qs(body.decode(), strict_parsing=True, max_num_fields=8)
        if any(len(value) != 1 for value in form.values()):
            raise ValueError()
        parsed = OAuthCompletion.model_validate(
            {"state": form["state"][0], "code": form["code"][0]}
        )
    except (ValueError, KeyError):
        raise ProviderError("OAUTH_STATE_INVALID", retryable=False) from None
    state = parsed.state.get_secret_value()

    def exchange():
        pending = db.scalar(
            select(ProviderOAuthState).where(
                ProviderOAuthState.state_digest == sha256(state.encode()).hexdigest(),
                ProviderOAuthState.expires_at > datetime.now(timezone.utc),
            )
        )
        if pending is None:
            raise ProviderError("OAUTH_STATE_INVALID", retryable=False)
        MicrosoftOAuth(get_settings()).complete(
            db,
            pending.connection_id,
            pending.user_id,
            state,
            parsed.code.get_secret_value(),
        )

    await run_in_threadpool(exchange)
    return HTMLResponse(
        "<!doctype html><html><title>CountOn</title><p>Outlook connected. Return to CountOn.</p></html>",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.post(
    "/{connection_id}/oauth/microsoft/authorize", response_model=AuthorizationURL
)
def authorize(connection_id: UUID, db: Database, user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {
        "authorization_url": MicrosoftOAuth(get_settings()).begin(
            db, connection_id, user.id
        )
    }


@router.post(
    "/{connection_id}/oauth/microsoft/complete", response_model=IntegrationResponse
)
def complete(
    connection_id: UUID, payload: OAuthCompletion, db: Database, user: CurrentUser
):
    return MicrosoftOAuth(get_settings()).complete(
        db,
        connection_id,
        user.id,
        payload.state.get_secret_value(),
        payload.code.get_secret_value(),
    )


@router.post("/{connection_id}/oauth/microsoft/disconnect", status_code=204)
def disconnect(connection_id: UUID, db: Database, user: CurrentUser):
    MicrosoftOAuth(get_settings()).disconnect(db, connection_id, user.id)
    return Response(status_code=204)
