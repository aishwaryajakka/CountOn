"""Unit tests for notification delivery retry behavior."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.services.notification_delivery_service import (
    BASE_RETRY_SECONDS,
    MAX_RETRY_SECONDS,
    _record_failure,
    _retry_delay,
    run_delivery_cycle,
)


@pytest.mark.parametrize(
    ("attempt_count", "expected_seconds"),
    [
        (0, 60),
        (1, 60),
        (2, 120),
        (3, 240),
        (4, 480),
        (5, 960),
        (10, 21600),
    ],
)
def test_retry_delay_uses_exponential_backoff(
    attempt_count, expected_seconds
):
    assert _retry_delay(attempt_count) == expected_seconds


def test_retry_delay_never_exceeds_six_hours():
    assert _retry_delay(100) == MAX_RETRY_SECONDS
    assert MAX_RETRY_SECONDS == 6 * 60 * 60


def test_record_failure_schedules_retry():
    now = datetime.now(timezone.utc)

    delivery = SimpleNamespace(
        attempt_count=2,
        max_attempts=5,
        status="processing",
        last_error=None,
        next_attempt_at=now,
        processing_started_at=now,
    )

    _record_failure(delivery, now, "DELIVERY_PROVIDER_ERROR")

    assert delivery.status == "pending"
    assert delivery.last_error == "DELIVERY_PROVIDER_ERROR"
    assert delivery.next_attempt_at == now + timedelta(seconds=120)
    assert delivery.processing_started_at is None


def test_record_failure_marks_delivery_failed_at_max_attempts():
    now = datetime.now(timezone.utc)

    delivery = SimpleNamespace(
        attempt_count=5,
        max_attempts=5,
        status="processing",
        last_error=None,
        next_attempt_at=now,
        processing_started_at=now,
    )

    _record_failure(delivery, now, "DELIVERY_PROVIDER_ERROR")

    assert delivery.status == "failed"
    assert delivery.last_error == "DELIVERY_PROVIDER_ERROR"
    assert delivery.next_attempt_at == now
    assert delivery.processing_started_at is None


def test_record_failure_uses_one_minute_delay_for_first_attempt():
    now = datetime.now(timezone.utc)

    delivery = SimpleNamespace(
        attempt_count=1,
        max_attempts=5,
        status="processing",
        last_error=None,
        next_attempt_at=now,
        processing_started_at=now,
    )

    _record_failure(delivery, now, "DELIVERY_NOT_CONFIRMED")

    assert delivery.status == "pending"
    assert delivery.next_attempt_at == now + timedelta(
        seconds=BASE_RETRY_SECONDS
    )
    assert delivery.processing_started_at is None


def test_delivery_cycle_returns_zero_counts_when_queue_is_empty():
    with (
        patch(
            "app.services.notification_delivery_service.SessionLocal"
        ) as session_local,
        patch(
            "app.services.notification_delivery_service.recover_stale_deliveries",
            return_value={"recovered": 0, "failed": 0},
        ),
        patch(
            "app.services.notification_delivery_service.claim_due_deliveries",
            return_value=[],
        ),
    ):
        session = MagicMock()
        session_local.return_value.__enter__.return_value = session

        result = run_delivery_cycle(adapters={})

    assert result == {
        "processed": 0,
        "delivered": 0,
        "retried": 0,
        "failed": 0,
    }
    session.commit.assert_called_once()


def test_delivery_cycle_marks_successful_delivery():
    delivery_id = uuid4()
    notification_id = uuid4()

    delivery = SimpleNamespace(
        id=delivery_id,
        notification_id=notification_id,
        channel="email",
        status="processing",
        attempt_count=1,
        max_attempts=5,
        processing_started_at=datetime.now(timezone.utc),
        delivered_at=None,
        last_error=None,
    )
    notification = SimpleNamespace(id=notification_id)

    adapter = MagicMock()
    adapter.deliver.return_value = True

    # Configure the three database sessions used by the service.
    claim_session = MagicMock()
    prepare_session = MagicMock()
    result_session = MagicMock()

    prepare_session.scalar.return_value = delivery
    prepare_session.get.return_value = notification
    result_session.scalar.return_value = delivery

    sessions = [claim_session, prepare_session, result_session]

    for session in sessions:
        session.__enter__.return_value = session

    with (
        patch(
            "app.services.notification_delivery_service.SessionLocal",
            side_effect=sessions,
        ),
        patch(
            "app.services.notification_delivery_service.recover_stale_deliveries",
            return_value={"recovered": 0, "failed": 0},
        ),
        patch(
            "app.services.notification_delivery_service.claim_due_deliveries",
            return_value=[delivery],
        ),
    ):
        result = run_delivery_cycle(adapters={"email": adapter})

    assert result == {
        "processed": 1,
        "delivered": 1,
        "retried": 0,
        "failed": 0,
    }
    adapter.deliver.assert_called_once_with(notification)
    assert delivery.status == "delivered"
    assert delivery.delivered_at is not None
    assert delivery.last_error is None
    assert delivery.processing_started_at is None


