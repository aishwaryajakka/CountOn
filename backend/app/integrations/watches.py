"""Push is a wake-up hint; authenticated provider pulls remain the fact source."""

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import delete, select

from app.db.models import ProviderSyncState, ProviderWatch
from app.integrations.provider import ProviderError


def renew(db, settings, item, connection, oauth, token, now):
    if not settings.provider_webhook_url:
        return
    provider = (
        "gmail"
        if connection.provider == "google" and connection.connection_type == "email"
        else "google_calendar"
        if connection.provider == "google"
        else "graph"
    )
    if provider == "gmail" and not settings.gmail_pubsub_topic:
        return
    existing = db.scalar(
        select(ProviderWatch).where(
            ProviderWatch.sync_id == item.id,
            ProviderWatch.expires_at > now + timedelta(hours=12),
        )
    )
    if existing:
        return
    registering = db.scalar(
        select(ProviderWatch).where(
            ProviderWatch.sync_id == item.id, ProviderWatch.expires_at > now
        )
    )
    if registering and oauth.decrypt(registering.encrypted_secret, item.id).get(
        "registering"
    ):
        return
    generation = connection.oauth_generation
    secret = secrets.token_urlsafe(32)
    watch = ProviderWatch(
        sync_id=item.id,
        user_id=item.user_id,
        provider=provider,
        external_id=str(uuid4()),
        encrypted_secret=oauth.encrypt(
            {
                "token": secret,
                "account_id": connection.external_account_id,
                "registering": True,
            },
            item.id,
        ),
        expires_at=now + timedelta(minutes=30),
    )
    db.add(watch)
    db.commit()  # Google's initial sync ping may arrive before watch response
    try:
        headers = {"Authorization": "Bearer " + token}
        url = settings.provider_webhook_url.rstrip("/")
        if provider == "gmail":
            response = oauth.http.request(
                "POST",
                "https://gmail.googleapis.com/gmail/v1/users/me/watch",
                headers=headers,
                json={
                    "topicName": settings.gmail_pubsub_topic,
                    "labelIds": ["INBOX"],
                    "labelFilterBehavior": "include",
                },
            )
            expires = datetime.fromtimestamp(
                int(response["expiration"]) / 1000, timezone.utc
            )
        elif provider == "google_calendar":
            response = oauth.http.request(
                "POST",
                "https://www.googleapis.com/calendar/v3/calendars/"
                + quote(item.stream, safe="")
                + "/events/watch",
                headers=headers,
                json={
                    "id": watch.external_id,
                    "type": "web_hook",
                    "address": url + "/google-calendar",
                    "token": secret,
                    "params": {"ttl": "604800"},
                },
            )
            expires = datetime.fromtimestamp(
                int(response["expiration"]) / 1000, timezone.utc
            )
        else:
            resource = (
                "me/mailFolders('inbox')/messages"
                if connection.connection_type == "email"
                else "me/events"
            )
            old = db.scalar(
                select(ProviderWatch).where(
                    ProviderWatch.sync_id == item.id,
                    ProviderWatch.provider == "graph",
                    ProviderWatch.id != watch.id,
                    ProviderWatch.expires_at > now,
                )
            )
            if old:
                secret = oauth.decrypt(old.encrypted_secret, item.id)["token"]
                response = oauth.http.request(
                    "PATCH",
                    "https://graph.microsoft.com/v1.0/subscriptions/" + old.external_id,
                    headers=headers,
                    json={"expirationDateTime": (now + timedelta(days=2)).isoformat()},
                )
                db.delete(old)
                db.flush()
            else:
                response = oauth.http.request(
                    "POST",
                    "https://graph.microsoft.com/v1.0/subscriptions",
                    headers=headers,
                    json={
                        "changeType": "created,updated,deleted",
                        "notificationUrl": url + "/microsoft",
                        "lifecycleNotificationUrl": url + "/microsoft",
                        "resource": resource,
                        "expirationDateTime": (now + timedelta(days=2)).isoformat(),
                        "clientState": secret,
                    },
                )
            watch.external_id = str(response["id"])
            expires = datetime.fromisoformat(
                response["expirationDateTime"].replace("Z", "+00:00")
            )
        # Reconnect/disconnect can revoke this registration while the request is in flight.
        connection = oauth.connection(db, connection.id, item.user_id, lock=True)
        current = db.scalar(
            select(ProviderSyncState)
            .where(ProviderSyncState.id == item.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            current is None
            or connection.status != "connected"
            or connection.oauth_generation != generation
        ):
            db.rollback()
            return
        if (
            expires.tzinfo is None
            or expires <= now
            or expires > now + timedelta(days=8)
        ):
            raise ValueError()
        content = {
            "token": secret,
            "account_id": connection.external_account_id,
            "resource_id": response.get("resourceId"),
        }
        watch.encrypted_secret = oauth.encrypt(content, item.id)
        watch.expires_at = expires
        db.commit()
        db.execute(
            delete(ProviderWatch).where(
                ProviderWatch.sync_id == item.id,
                ProviderWatch.id != watch.id,
                ProviderWatch.expires_at < now,
            )
        )
        db.commit()
    except (ProviderError, KeyError, ValueError, TypeError):
        db.rollback()
        db.execute(delete(ProviderWatch).where(ProviderWatch.id == watch.id))
        db.commit()
        # Periodic delta/history polling continues when push registration fails.
        raise ProviderError("PROVIDER_UNAVAILABLE") from None


def wake(db, item):
    if item.status in ("pending", "running"):
        item.wake_requested_at = item.next_run_at = datetime.now(timezone.utc)
