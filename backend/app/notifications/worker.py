"""Fenced opt-in email outbox. Run python -m app.notifications.worker [--once]."""

import argparse
import logging
import signal
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import or_, select

from app.core.config import get_settings
from app.core.observability import record
from app.db.models import (
    Expectation,
    Notification,
    NotificationDelivery,
    NotificationPreference,
)
from app.notifications.delivery import EmailChannel, decrypt, encrypt, ready_at
from app.services.notification_service import enabled

logger = logging.getLogger(__name__)


class DeliveryWorker:
    def __init__(self, sessions, settings, *, channel=None, now=None):
        self.sessions, self.settings = sessions, settings
        self.channel = channel or EmailChannel(settings)
        self.now = now or (lambda: datetime.now(timezone.utc))

    def claim(self):
        now = self.now()
        with self.sessions() as db:
            item = db.scalar(
                select(NotificationDelivery)
                .where(
                    or_(
                        NotificationDelivery.status == "pending",
                        (NotificationDelivery.status == "running")
                        & (NotificationDelivery.lease_expires_at <= now),
                    ),
                    NotificationDelivery.next_run_at <= now,
                )
                .order_by(NotificationDelivery.next_run_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if item is None:
                return None
            # Resend retains idempotency keys for 24 hours. Stop before that
            # window expires: ambiguous delivery is inspected, never blindly resent.
            if item.first_attempt_at and (now - item.first_attempt_at) >= timedelta(
                hours=23
            ):
                item.status, item.last_error = "failed", "DELIVERY_WINDOW_EXPIRED"
                item.lease_token = item.lease_expires_at = None
                db.commit()
                return ()
            if item.attempt_count >= 8:
                item.status, item.last_error = "failed", "ATTEMPTS_EXHAUSTED"
                db.commit()
                return ()
            pref = db.get(NotificationPreference, item.user_id)
            notification = db.get(Notification, item.notification_id)
            expectation = db.get(Expectation, notification.expectation_id)
            if (
                not pref
                or not pref.email_enabled
                or not pref.encrypted_recipient
                or not enabled(db, item.user_id, notification.type)
                or notification.status in ("read", "dismissed")
                or expectation.status.value in ("cancelled", "resolved")
            ):
                item.status = "cancelled"
                db.commit()
                return ()
            due = ready_at(pref, now)
            if due > now:
                item.status, item.next_run_at = "pending", due
                db.commit()
                return ()
            try:
                recipient = decrypt(
                    self.settings, pref.encrypted_recipient, item.user_id
                )["email"]
                if not item.encrypted_payload:
                    # Do not email private claim text, raw evidence, model output or tokens.
                    payload = {
                        "from": self.settings.notification_email_from,
                        "to": [recipient],
                        "subject": "CountOn: something needs your attention",
                        "text": notification.message
                        + "\n\n"
                        + self.settings.frontend_public_url.rstrip("/")
                        + "/expectations/"
                        + str(expectation.id),
                    }
                    item.encrypted_payload = encrypt(self.settings, payload, item.id)
                payload = decrypt(self.settings, item.encrypted_payload, item.id)
            except Exception:  # noqa: BLE001 -- rotated/corrupt ciphertext is a safe dead letter
                item.status, item.last_error = "failed", "CREDENTIAL_UNAVAILABLE"
                item.lease_token = item.lease_expires_at = None
                db.commit()
                return ()
            if payload.get("to") != [recipient]:
                item.status, item.last_error = "cancelled", "RECIPIENT_CHANGED"
                db.commit()
                return ()
            item.status, item.lease_token = "running", uuid4()
            item.lease_expires_at = now + timedelta(seconds=60)
            item.first_attempt_at = item.first_attempt_at or now
            item.attempt_count += 1
            claim = (
                item.id,
                item.lease_token,
                payload,
            )
            db.commit()
            return claim

    def once(self):
        if not self.settings.notification_email_enabled:
            return False
        claim = self.claim()
        if claim is None:
            return False
        if not claim:
            return True
        id, token, payload = claim
        error = None
        try:
            self.channel.send(payload, id)
        except Exception as failure:  # noqa: BLE001 -- never log payload or private transport errors
            from app.integrations.provider import ProviderError

            error = (
                failure
                if isinstance(failure, ProviderError)
                else ProviderError("PROVIDER_UNAVAILABLE")
            )
        with self.sessions() as db:
            item = db.scalar(
                select(NotificationDelivery)
                .where(NotificationDelivery.id == id)
                .with_for_update()
            )
            if (
                not item
                or item.status != "running"
                or item.lease_token != token
                or item.lease_expires_at <= self.now()
            ):
                return True
            if error:
                item.last_error = error.code
                item.status = (
                    "pending"
                    if error.retryable and item.attempt_count < 8
                    else "failed"
                )
                item.next_run_at = self.now() + timedelta(
                    seconds=max(
                        error.retry_after, min(3600, 30 * 2**item.attempt_count)
                    )
                )
            else:
                item.status, item.sent_at, item.last_error = "sent", self.now(), None
            item.lease_token = item.lease_expires_at = None
            db.commit()
        logger.info(
            "Notification delivery attempt",
            extra={"result_status": "failed" if error else "sent"},
        )
        record("notification_delivery_results", "failed" if error else "sent")
        return True


def main():
    from app.core.logging import configure_logging
    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging()
    if not settings.notification_email_enabled:
        raise SystemExit(
            "Email delivery is disabled; the in-app inbox remains available."
        )
    worker = DeliveryWorker(SessionLocal, settings)
    stop = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stop.set())
    while not stop.is_set():
        try:
            processed = worker.once()
        except Exception:  # noqa: BLE001 -- leases survive outages, database diagnostics stay private
            logger.error("Notification delivery unavailable")
            if args.once:
                raise SystemExit(1) from None
            processed = False
        if args.once:
            return
        if not processed:
            stop.wait(2)


if __name__ == "__main__":
    main()
