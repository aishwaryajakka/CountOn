"""Repository operations for the notification delivery queue."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Notification, NotificationDelivery


BASE_RETRY_SECONDS = 60
MAX_RETRY_SECONDS = 6 * 60 * 60


def enqueue_delivery(
    db: Session,
    notification: Notification,
    channel: str,
    max_attempts: int = 5,
) -> NotificationDelivery:
    """Create one delivery job per notification and channel."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    statement = (
        insert(NotificationDelivery)
        .values(
            notification_id=notification.id,
            channel=channel,
            status="pending",
            attempt_count=0,
            max_attempts=max_attempts,
        )
        .on_conflict_do_nothing(
            constraint="uq_notification_delivery_channel"
        )
        .returning(NotificationDelivery.id)
    )

    delivery_id = db.scalar(statement)

    if delivery_id is not None:
        delivery = db.get(NotificationDelivery, delivery_id)
        if delivery is None:
            raise RuntimeError("DELIVERY_ENQUEUE_CONFLICT")
        return delivery

    # An existing job means this notification/channel was already enqueued.
    existing = db.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.notification_id == notification.id,
            NotificationDelivery.channel == channel,
        )
    )

    if existing is None:
        raise RuntimeError("DELIVERY_ENQUEUE_CONFLICT")

    return existing


def claim_due_deliveries(
    db: Session,
    batch_size: int = 50,
) -> list[NotificationDelivery]:
    """Claim due jobs while avoiding rows locked by other workers."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    now = datetime.now(timezone.utc)

    deliveries = list(
        db.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.status == "pending",
                NotificationDelivery.next_attempt_at <= now,
                NotificationDelivery.attempt_count
                < NotificationDelivery.max_attempts,
            )
            .order_by(
                NotificationDelivery.next_attempt_at,
                NotificationDelivery.id,
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    )

    for delivery in deliveries:
        delivery.status = "processing"
        delivery.last_attempt_at = now
        delivery.processing_started_at = now
        delivery.attempt_count += 1

    db.flush()
    return deliveries


def get_delivery(
    db: Session,
    delivery_id: UUID,
) -> NotificationDelivery | None:
    """Retrieve a delivery by its ID."""
    return db.get(NotificationDelivery, delivery_id)


def recover_stale_deliveries(
    db: Session,
    stale_after_seconds: int = 600,
    batch_size: int = 50,
) -> dict[str, int]:
    """Recover deliveries left processing after a worker crash."""
    if stale_after_seconds < 1:
        raise ValueError("stale_after_seconds must be at least 1")

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=stale_after_seconds)

    deliveries = list(
        db.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.status == "processing",
                NotificationDelivery.processing_started_at.is_not(None),
                NotificationDelivery.processing_started_at <= cutoff,
            )
            .order_by(
                NotificationDelivery.processing_started_at,
                NotificationDelivery.id,
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    )

    recovered = 0
    failed = 0

    for delivery in deliveries:
        delivery.last_error = "DELIVERY_WORKER_TIMEOUT"
        delivery.processing_started_at = None

        if delivery.attempt_count >= delivery.max_attempts:
            delivery.status = "failed"
            failed += 1
            continue

        delivery.status = "pending"

        retry_delay = min(
            BASE_RETRY_SECONDS
            * (2 ** max(0, delivery.attempt_count - 1)),
            MAX_RETRY_SECONDS,
        )

        delivery.next_attempt_at = now + timedelta(
            seconds=retry_delay
        )
        recovered += 1

    db.flush()

    return {
        "recovered": recovered,
        "failed": failed,
    }
