"""Owned account synchronization controls and explicit expectation/source linkage."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.exceptions import (
    ExpectationNotFoundError,
    InvalidExpectationError,
    ResourceNotFoundError,
)
from app.db.models import (
    Evidence,
    Expectation,
    ExpectationSourceBinding,
    MonitoringJob,
    ProviderSourceEvent,
    ProviderSyncState,
    ProviderWatch,
)
from app.db.models.integration import IntegrationCredential, ProviderOAuthState
from app.integrations.accounts import account_oauth
from app.integrations.adapters import AccountAdapter
from app.integrations.provider import ProviderError
from app.repositories import audit
from app.services import integration_service
from app.services.expectation_service import get_expectation


def sync(db, id, user_id, *, lock=False):
    query = select(ProviderSyncState).where(
        ProviderSyncState.id == id, ProviderSyncState.user_id == user_id
    )
    item = db.scalar(
        (query.with_for_update() if lock else query).execution_options(
            populate_existing=True
        )
    )
    if item is None:
        raise ResourceNotFoundError("SYNC_NOT_FOUND", "Source not found")
    return item


def enroll(db, settings, connection_id, user_id, selection):
    connection = integration_service.get(db, connection_id, user_id)
    oauth = account_oauth(settings, connection)
    token = oauth.access_token(db, connection.id, user_id, datetime.now(timezone.utc))
    if connection.connection_type == "calendar":
        if selection.calendar_id not in {
            c["id"]
            for c in AccountAdapter(
                connection.provider, "calendar", oauth.http
            ).calendars(token)
        }:
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        stream = selection.calendar_id
    else:
        if selection.calendar_id:
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        stream = "inbox"
    connection = oauth.connection(db, connection.id, user_id, lock=True)
    if (
        connection.status != "connected"
        or db.get(IntegrationCredential, connection.id) is None
    ):
        raise ProviderError("AUTH_REQUIRED", retryable=False)
    item = db.scalar(
        select(ProviderSyncState).where(
            ProviderSyncState.connection_id == connection_id,
            ProviderSyncState.stream == stream,
        )
    )
    if item is None:
        item = ProviderSyncState(
            connection_id=connection_id, user_id=user_id, stream=stream
        )
        db.add(item)
    elif item.status != "running":
        item.status, item.attempt_count, item.last_error = "pending", 0, None
    item.next_run_at = datetime.now(timezone.utc)
    audit.record(db, user_id, "integration", connection_id, "provider.sync_requested")
    db.commit()
    db.refresh(item)
    return item


def queue(db, id, user_id):
    item = sync(db, id, user_id, lock=True)
    if item.status != "running":
        item.status, item.attempt_count, item.last_error = "pending", 0, None
    item.next_run_at = datetime.now(timezone.utc)
    db.commit()
    return item


def bind(db, expectation_id, user_id, payload, *, commit=True):
    expectation = get_expectation(db, expectation_id, user_id)
    item = sync(db, payload.sync_id, user_id)
    connection = integration_service.get(db, item.connection_id, user_id)
    db.refresh(connection, with_for_update=True)
    item = sync(db, item.id, user_id, lock=True)
    expectation = db.scalar(
        select(Expectation)
        .where(
            Expectation.id == expectation_id,
            Expectation.user_id == user_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if expectation is None:
        raise ExpectationNotFoundError(expectation_id)
    if expectation.status.value in ("cancelled", "resolved"):
        raise InvalidExpectationError("Terminal expectations cannot be monitored")
    if (
        connection.status != "connected"
        or not connection.oauth_generation
        or db.get(IntegrationCredential, connection.id) is None
    ):
        raise ProviderError("AUTH_REQUIRED", retryable=False)
    rule = payload.rule
    if (connection.connection_type == "calendar") != (rule.kind == "calendar"):
        raise ProviderError("PERMISSION_DENIED", retryable=False)
    source = source_name(connection)
    # Source opt-in is an explicit part of this binding action, not model inference.
    expectation.evidence_sources = list(
        dict.fromkeys([*expectation.evidence_sources, source])
    )
    binding = db.scalar(
        select(ExpectationSourceBinding).where(
            ExpectationSourceBinding.expectation_id == expectation_id,
            ExpectationSourceBinding.sync_id == item.id,
        )
    )
    if binding is None:
        binding = ExpectationSourceBinding(
            expectation_id=expectation_id,
            sync_id=item.id,
            user_id=user_id,
            rule=rule.model_dump(mode="json"),
        )
        db.add(binding)
    else:
        binding.rule = rule.model_dump(mode="json")
    # Invalidate a worker page so it cannot publish with an obsolete source rule.
    item.lease_token, item.lease_expires_at = None, None
    item.status, item.next_run_at, item.round_id = (
        "pending",
        datetime.now(timezone.utc),
        uuid4(),
    )
    audit.record(db, user_id, "expectation", expectation_id, "provider.source_bound")
    db.flush()
    # A full account binding replaces the legacy per-job Mail.ReadBasic fetch.
    for job in db.scalars(
        select(MonitoringJob).where(
            MonitoringJob.expectation_id == expectation_id,
            MonitoringJob.user_id == user_id,
        )
    ):
        job.connection_id, job.provider_config = None, {}
    from app.monitoring.sources import wake

    wake(db, expectation, datetime.now(timezone.utc))
    if commit:
        db.commit()
        db.refresh(binding)
    else:
        db.flush()
    return binding


def source_name(connection):
    return (
        ("gmail_email" if connection.provider == "google" else "outlook_email")
        if connection.connection_type == "email"
        else f"{connection.provider}_calendar"
    )


def disconnect(db, settings, connection_id, user_id, payload):
    connection = integration_service.get(db, connection_id, user_id)
    oauth = account_oauth(settings, connection)
    credential = db.get(IntegrationCredential, connection.id)
    tokens, registrations = {}, []
    try:
        tokens = (
            oauth.decrypt(credential.encrypted_tokens, connection.id)
            if credential
            else {}
        )
        watches = list(
            db.scalars(
                select(ProviderWatch)
                .join(ProviderSyncState, ProviderSyncState.id == ProviderWatch.sync_id)
                .where(
                    ProviderSyncState.connection_id == connection.id,
                    ProviderWatch.user_id == user_id,
                )
            )
        )
        registrations = [
            (
                watch.provider,
                watch.external_id,
                oauth.decrypt(watch.encrypted_secret, watch.sync_id),
            )
            for watch in watches
        ]
    except ProviderError:
        pass  # local disconnection remains available even after configuration/key removal
    # Fence reads first. Revocation is outside the transaction and can't undo local removal.
    connection = oauth.connection(db, connection.id, user_id, lock=True)
    connection.status, connection.scopes, connection.oauth_generation = (
        "disconnected",
        [],
        None,
    )
    for model in (ProviderOAuthState, IntegrationCredential, ProviderSyncState):
        db.execute(delete(model).where(model.connection_id == connection.id))
    if payload.erase_evidence:
        db.execute(
            delete(Evidence).where(
                Evidence.raw_data["connection_id"].astext == str(connection.id),
                Evidence.expectation_id.in_(
                    select(Expectation.id).where(Expectation.user_id == user_id)
                ),
            )
        )
    audit.record(db, user_id, "integration", connection.id, "provider.disconnected")
    db.commit()
    for provider, external_id, secret in registrations:
        try:
            headers = {"Authorization": "Bearer " + str(tokens.get("access_token", ""))}
            if provider == "gmail":
                oauth.http.request(
                    "POST",
                    "https://gmail.googleapis.com/gmail/v1/users/me/stop",
                    headers=headers,
                )
            elif provider == "google_calendar" and secret.get("resource_id"):
                oauth.http.request(
                    "POST",
                    "https://www.googleapis.com/calendar/v3/channels/stop",
                    headers=headers,
                    json={"id": external_id, "resourceId": secret["resource_id"]},
                )
            elif provider == "graph":
                oauth.http.request(
                    "DELETE",
                    "https://graph.microsoft.com/v1.0/subscriptions/" + external_id,
                    headers=headers,
                )
        except ProviderError:
            pass  # stale provider registration expires and has no retained local authority
    revoked = False
    if (
        payload.revoke
        and connection.provider == "google"
        and tokens.get("refresh_token")
    ):
        try:
            oauth.http.request(
                "POST",
                "https://oauth2.googleapis.com/revoke",
                data={"token": tokens["refresh_token"]},
            )
            revoked = True
        except ProviderError:
            pass  # local purge succeeds even if remote revocation is unavailable
    return {
        "disconnected": True,
        "provider_revoked": revoked,
        "revocation_action": None
        if revoked
        else "Remove CountOn's grant in your provider account permissions if needed.",
    }


def events(db, settings, id, user_id):
    item = sync(db, id, user_id)
    connection = integration_service.get(db, item.connection_id, user_id)
    crypto = account_oauth(settings, connection)
    rows = db.scalars(
        select(ProviderSourceEvent)
        .where(
            ProviderSourceEvent.sync_id == id, ProviderSourceEvent.user_id == user_id
        )
        .order_by(ProviderSourceEvent.observed_at.desc())
        .limit(100)
    )
    return [
        {
            "id": row.external_id,
            "facts": crypto.decrypt(row.encrypted_facts, item.id),
            "observed_at": row.observed_at,
        }
        for row in rows
    ]
