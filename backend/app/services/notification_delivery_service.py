"""Reliable notification delivery processing with retries."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Notification, NotificationDelivery
from app.db.session import SessionLocal
from app.repositories.notification_delivery import (
    claim_due_deliveries,
    enqueue_delivery,
    recover_stale_deliveries,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
BASE_RETRY_SECONDS = 60
MAX_RETRY_SECONDS = 6 * 60 * 60


class DeliveryAdapter(Protocol):
    """Adapter for a configured external delivery provider."""

    def deliver(self, notification: Notification) -> bool:
        """Return True only when the provider confirms delivery."""


def enqueue_notification_delivery(
    db: Session,
    notification_id: UUID,
    channel: str,
    max_attempts: int = 5,
) -> NotificationDelivery:
    """Enqueue delivery for an existing notification."""
    notification = db.scalar(
        select(Notification).where(Notification.id == notification_id)
    )

    if notification is None:
        raise ValueError("NOTIFICATION_NOT_FOUND")

    if channel == "in_app":
        raise ValueError("IN_APP_DELIVERY_NOT_REQUIRED")

    return enqueue_delivery(
        db=db,
        notification=notification,
        channel=channel,
        max_attempts=max_attempts,
    )


def _retry_delay(attempt_count: int) -> int:
    """Exponential backoff, capped at six hours."""
    return min(
        BASE_RETRY_SECONDS * (2 ** max(0, attempt_count - 1)),
        MAX_RETRY_SECONDS,
    )


def _record_failure(
    delivery: NotificationDelivery,
    now: datetime,
    error_code: str,
) -> None:
    """Schedule a retry or mark the delivery permanently failed."""
    delivery.last_error = error_code
    delivery.processing_started_at = None

    if delivery.attempt_count >= delivery.max_attempts:
        delivery.status = "failed"
        return

    delivery.status = "pending"
    delivery.next_attempt_at = now + timedelta(
        seconds=_retry_delay(delivery.attempt_count)
    )


def run_delivery_cycle(
    adapters: dict[str, DeliveryAdapter],
    batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    """Claim and process a batch of queued external deliveries."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    processed = 0
    delivered = 0
    retried = 0
    failed = 0

    # Recover stale jobs and claim due jobs in a short transaction.
    with SessionLocal() as db:
        try:
            recovery = recover_stale_deliveries(db)

            if recovery["recovered"] or recovery["failed"]:
                logger.warning(
                    "Recovered stale notification deliveries: %s",
                    recovery,
                )

            jobs = claim_due_deliveries(db, batch_size=batch_size)
            claimed = [(job.id, job.channel) for job in jobs]

            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not claim notification deliveries")
            raise

    for delivery_id, channel in claimed:
        adapter = adapters.get(channel)

        # Load the delivery and notification without holding a database
        # lock during the external provider call.
        with SessionLocal() as db:
            try:
                delivery = db.scalar(
                    select(NotificationDelivery)
                    .where(NotificationDelivery.id == delivery_id)
                    .with_for_update()
                )

                if delivery is None or delivery.status != "processing":
                    db.rollback()
                    continue

                notification = db.get(
                    Notification, delivery.notification_id
                )

                if notification is None:
                    delivery.status = "failed"
                    delivery.last_error = "NOTIFICATION_NOT_FOUND"
                    delivery.processing_started_at = None
                    db.commit()

                    failed += 1
                    processed += 1
                    continue

                if adapter is None:
                    _record_failure(
                        delivery,
                        datetime.now(timezone.utc),
                        "DELIVERY_ADAPTER_UNAVAILABLE",
                    )
                    is_failed = delivery.status == "failed"
                    db.commit()

                    if is_failed:
                        failed += 1
                    else:
                        retried += 1

                    processed += 1
                    continue

                db.commit()

            except Exception:
                db.rollback()
                logger.exception(
                    "Could not prepare notification delivery id=%s",
                    delivery_id,
                )
                continue

        # The provider call happens outside the database transaction.
        try:
            success = adapter.deliver(notification)
        except Exception:
            # Avoid storing raw exception messages that might contain secrets.
            success = False
            error_code = "DELIVERY_PROVIDER_ERROR"
            logger.exception(
                "Notification provider raised an exception for delivery id=%s",
                delivery_id,
            )
        else:
            error_code = "DELIVERY_NOT_CONFIRMED"

        # Persist the confirmed result or schedule a retry.
        with SessionLocal() as db:
            try:
                delivery = db.scalar(
                    select(NotificationDelivery)
                    .where(NotificationDelivery.id == delivery_id)
                    .with_for_update()
                )

                if delivery is None or delivery.status != "processing":
                    db.rollback()
                    continue

                now = datetime.now(timezone.utc)

                if success is True:
                    delivery.status = "delivered"
                    delivery.delivered_at = now
                    delivery.last_error = None
                    delivery.processing_started_at = None
                    delivered += 1
                else:
                    _record_failure(delivery, now, error_code)

                    if delivery.status == "failed":
                        failed += 1
                    else:
                        retried += 1

                db.commit()
                processed += 1

            except Exception:
                db.rollback()
                logger.exception(
                    "Could not save delivery result id=%s",
                    delivery_id,
                )
                raise

    return {
        "processed": processed,
        "delivered": delivered,
        "retried": retried,
        "failed": failed,
    }
