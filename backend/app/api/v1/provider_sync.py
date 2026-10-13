"""Authenticated provider management and verified, bounded push wake-ups."""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import CurrentUser, get_db
from app.api.v1.provider_oauth import AuthorizationURL, OAuthCompletion
from app.core.config import get_settings
from app.db.models import ExpectationSourceBinding, ProviderSyncState, ProviderWatch
from app.db.models.integration import IntegrationConnection, ProviderOAuthState
from app.integrations.accounts import account_oauth
from app.integrations.adapters import AccountAdapter
from app.integrations.provider import ProviderError
from app.integrations.watches import wake
from app.schemas.provider_sync import (
    BindingCreate,
    BindingResponse,
    DisconnectRequest,
    SyncResponse,
    SyncSelection,
)
from app.schemas.source_plan import (
    AppliedMonitoringPlan,
    ConfirmMonitoringPlan,
    MonitoringPlan,
    SourcePlanRequest,
)
from app.services import integration_service, source_planning_service
from app.services import provider_sync_service as service
from app.services.expectation_service import get_expectation


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["provider-sync"], dependencies=[Depends(no_store)])
Database = Annotated[Session, Depends(get_db)]


@router.get("/integrations/providers")
def capabilities(user: CurrentUser):
    settings = get_settings()
    return {
        "google": settings.google_integrations_enabled,
        "microsoft": settings.microsoft_graph_enabled,
        "automatic_sync": settings.provider_sync_enabled,
        "push": bool(settings.provider_webhook_url),
    }


@router.post(
    "/integrations/{connection_id}/oauth/authorize", response_model=AuthorizationURL
)
def authorize(connection_id: UUID, db: Database, user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    connection = integration_service.get(db, connection_id, user.id)
    return {
        "authorization_url": account_oauth(get_settings(), connection).begin(
            db, connection_id, user.id
        )
    }


def exchange(db, state, code, provider):
    pending = db.scalar(
        select(ProviderOAuthState).where(
            ProviderOAuthState.state_digest
            == hashlib.sha256(state.encode()).hexdigest(),
            ProviderOAuthState.expires_at > datetime.now(timezone.utc),
        )
    )
    if pending is None:
        raise ProviderError("OAUTH_STATE_INVALID", retryable=False)
    connection = integration_service.get(db, pending.connection_id, pending.user_id)
    if connection.provider != provider:
        raise ProviderError("OAUTH_STATE_INVALID", retryable=False)
    return account_oauth(get_settings(), connection).complete(
        db, connection.id, pending.user_id, state, code
    )


@router.get("/integrations/oauth/google/callback", response_class=HTMLResponse)
def google_callback(request: Request, db: Database):
    if len(str(request.url)) > 12000 or any(
        len(request.query_params.getlist(k)) != 1 for k in ("state", "code")
    ):
        raise ProviderError("OAUTH_STATE_INVALID", retryable=False)
    try:
        data = OAuthCompletion.model_validate(
            {
                "state": request.query_params["state"],
                "code": request.query_params["code"],
            }
        )
    except (KeyError, ValueError):
        raise ProviderError("OAUTH_STATE_INVALID", retryable=False) from None
    exchange(db, data.state.get_secret_value(), data.code.get_secret_value(), "google")
    return HTMLResponse(
        "<!doctype html><html><title>CountOn</title><p>Account connected. Return to CountOn and select a source to synchronize.</p></html>",
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        },
    )


@router.get("/integrations/{connection_id}/calendars")
def calendars(connection_id: UUID, db: Database, user: CurrentUser):
    connection = integration_service.get(db, connection_id, user.id)
    if connection.connection_type != "calendar":
        raise ProviderError("PERMISSION_DENIED", retryable=False)
    oauth = account_oauth(get_settings(), connection)
    token = oauth.access_token(db, connection.id, user.id, datetime.now(timezone.utc))
    return AccountAdapter(connection.provider, "calendar", oauth.http).calendars(token)


@router.post("/integrations/{connection_id}/sync", response_model=SyncResponse)
def enroll(
    connection_id: UUID, payload: SyncSelection, db: Database, user: CurrentUser
):
    return service.enroll(db, get_settings(), connection_id, user.id, payload)


@router.get("/integrations/{connection_id}/sync", response_model=list[SyncResponse])
def states(connection_id: UUID, db: Database, user: CurrentUser):
    integration_service.get(db, connection_id, user.id)
    return list(
        db.scalars(
            select(ProviderSyncState).where(
                ProviderSyncState.connection_id == connection_id,
                ProviderSyncState.user_id == user.id,
            )
        )
    )


@router.post("/integrations/{connection_id}/disconnect")
def disconnect(
    connection_id: UUID, payload: DisconnectRequest, db: Database, user: CurrentUser
):
    return service.disconnect(db, get_settings(), connection_id, user.id, payload)


@router.post("/provider-sync/{id}/run", response_model=SyncResponse)
def run(id: UUID, db: Database, user: CurrentUser):
    return service.queue(db, id, user.id)


@router.get("/provider-sync/{id}/events")
def events(id: UUID, db: Database, user: CurrentUser):
    return service.events(db, get_settings(), id, user.id)


@router.post(
    "/expectations/{expectation_id}/monitoring-plan/preview",
    response_model=MonitoringPlan,
)
def preview_plan(
    expectation_id: UUID, payload: SourcePlanRequest, db: Database, user: CurrentUser
):
    return source_planning_service.preview(
        db, get_settings(), expectation_id, user.id, payload
    )


@router.post(
    "/expectations/{expectation_id}/monitoring-plan/confirm",
    response_model=AppliedMonitoringPlan,
)
def confirm_plan(
    expectation_id: UUID,
    payload: ConfirmMonitoringPlan,
    db: Database,
    user: CurrentUser,
):
    return source_planning_service.apply(
        db, get_settings(), expectation_id, user.id, payload
    )


@router.post("/expectations/{expectation_id}/sources", response_model=BindingResponse)
def bind(expectation_id: UUID, payload: BindingCreate, db: Database, user: CurrentUser):
    return service.bind(db, expectation_id, user.id, payload)


@router.get(
    "/expectations/{expectation_id}/sources", response_model=list[BindingResponse]
)
def bindings(expectation_id: UUID, db: Database, user: CurrentUser):
    get_expectation(db, expectation_id, user.id)
    return list(
        db.scalars(
            select(ExpectationSourceBinding).where(
                ExpectationSourceBinding.expectation_id == expectation_id,
                ExpectationSourceBinding.user_id == user.id,
            )
        )
    )


@router.delete("/expectations/{expectation_id}/sources/{binding_id}", status_code=204)
def unbind(expectation_id: UUID, binding_id: UUID, db: Database, user: CurrentUser):
    expectation = get_expectation(db, expectation_id, user.id)
    binding = db.scalar(
        select(ExpectationSourceBinding).where(
            ExpectationSourceBinding.id == binding_id,
            ExpectationSourceBinding.expectation_id == expectation_id,
            ExpectationSourceBinding.user_id == user.id,
        )
    )
    if binding:
        item = service.sync(db, binding.sync_id, user.id, lock=True)
        item.lease_token, item.lease_expires_at, item.status = None, None, "pending"
        db.delete(binding)
        db.flush()
        from app.monitoring.sources import wake as wake_monitoring

        wake_monitoring(db, expectation, datetime.now(timezone.utc))
        db.commit()
    return Response(status_code=204)


async def bounded_body(request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise TypeError()
        return data
    except (ValueError, TypeError):
        raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False) from None


def verified_pubsub(token, settings):
    if not settings.gmail_pubsub_audience or not settings.gmail_pubsub_service_account:
        raise ProviderError("PERMISSION_DENIED", retryable=False)
    try:
        header = jwt.get_unverified_header(token)
        if (
            header.get("alg") != "RS256"
            or not isinstance(header.get("kid"), str)
            or len(header["kid"]) > 128
        ):
            raise ValueError()
        with (
            httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client,
            client.stream(
                "GET", "https://www.googleapis.com/oauth2/v3/certs"
            ) as response,
        ):
            response.raise_for_status()
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise ValueError()
            keys = json.loads(raw)["keys"]
        key = next(k for k in keys if k["kid"] == header["kid"])
        claims = jwt.decode(
            token,
            jwt.PyJWK.from_dict(key).key,
            algorithms=["RS256"],
            audience=settings.gmail_pubsub_audience,
            options={
                "require": ["exp", "iat", "iss", "aud", "email", "email_verified"]
            },
        )
        if (
            claims["iss"] not in ("https://accounts.google.com", "accounts.google.com")
            or claims["email"] != settings.gmail_pubsub_service_account
            or claims["email_verified"] is not True
        ):
            raise ValueError()
        return claims
    except (
        jwt.PyJWTError,
        httpx.HTTPError,
        ValueError,
        KeyError,
        StopIteration,
        TypeError,
    ):
        raise ProviderError("PERMISSION_DENIED", retryable=False) from None


@router.post("/integrations/webhooks/gmail", status_code=204)
async def gmail_push(request: Request, db: Database):
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or len(authorization) > 12000:
        raise ProviderError("PERMISSION_DENIED", retryable=False)
    settings = get_settings()
    await run_in_threadpool(verified_pubsub, authorization[7:], settings)
    data = await bounded_body(request)
    try:
        message = json.loads(base64.b64decode(data["message"]["data"], validate=True))
        account = message["emailAddress"]
        if not isinstance(account, str) or len(account) > 255:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False) from None
    items = db.scalars(
        select(ProviderSyncState)
        .join(
            IntegrationConnection,
            IntegrationConnection.id == ProviderSyncState.connection_id,
        )
        .where(
            IntegrationConnection.provider == "google",
            IntegrationConnection.connection_type == "email",
            IntegrationConnection.status == "connected",
            IntegrationConnection.external_account_id == account,
        )
    )
    for item in items:
        wake(db, item)
    db.commit()
    return Response(status_code=204)


@router.post("/integrations/webhooks/google-calendar", status_code=204)
def calendar_push(request: Request, db: Database):
    watch = db.scalar(
        select(ProviderWatch).where(
            ProviderWatch.provider == "google_calendar",
            ProviderWatch.external_id == request.headers.get("x-goog-channel-id", ""),
            ProviderWatch.expires_at > datetime.now(timezone.utc),
        )
    )
    if watch is None:
        raise ProviderError("PERMISSION_DENIED", retryable=False)
    item = service.sync(db, watch.sync_id, watch.user_id)
    connection = integration_service.get(db, item.connection_id, item.user_id)
    secret = account_oauth(get_settings(), connection).decrypt(
        watch.encrypted_secret, item.id
    )
    token = request.headers.get("x-goog-channel-token", "")
    if (
        len(token) > 256
        or not hmac.compare_digest(token, secret["token"])
        or secret.get("resource_id")
        and request.headers.get("x-goog-resource-id") != secret["resource_id"]
    ):
        raise ProviderError("PERMISSION_DENIED", retryable=False)
    wake(db, item)
    db.commit()
    return Response(status_code=204)


@router.post("/integrations/webhooks/microsoft")
async def graph_push(request: Request, db: Database):
    validation = request.query_params.get("validationToken")
    if validation is not None:
        if (
            len(validation) > 1024
            or len(request.query_params.getlist("validationToken")) != 1
            or any(ord(c) < 32 for c in validation)
        ):
            raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
        return PlainTextResponse(validation, headers={"Cache-Control": "no-store"})
    data = await bounded_body(request)
    values = data.get("value")
    if not isinstance(values, list) or len(values) > 100:
        raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
    for notification in values:
        if not isinstance(notification, dict):
            raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
        watch = db.scalar(
            select(ProviderWatch).where(
                ProviderWatch.provider == "graph",
                ProviderWatch.external_id
                == str(notification.get("subscriptionId", "")),
                ProviderWatch.expires_at > datetime.now(timezone.utc),
            )
        )
        supplied = notification.get("clientState")
        if watch is None or not isinstance(supplied, str) or len(supplied) > 256:
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        item = service.sync(db, watch.sync_id, watch.user_id)
        connection = integration_service.get(db, item.connection_id, item.user_id)
        secret = account_oauth(get_settings(), connection).decrypt(
            watch.encrypted_secret, item.id
        )
        if not hmac.compare_digest(supplied, secret["token"]):
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        # Never follow resource URLs or take facts from a webhook body.
        wake(db, item)
        if notification.get("lifecycleEvent") in (
            "subscriptionRemoved",
            "reauthorizationRequired",
        ):
            watch.expires_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=202)
