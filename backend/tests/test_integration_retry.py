
from datetime import datetime, timedelta, timezone

import pytest

from app.services.integration_retry import (
    SyncErrorKind,
    calculate_retry,
)


FIXED_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_transient_error_schedules_first_retry():
    result = calculate_retry(
        SyncErrorKind.TRANSIENT, 1, now=FIXED_NOW
    )

    assert result.should_retry is True
    assert result.error_code == "TRANSIENT_ERROR"
    assert result.next_retry_at == FIXED_NOW + timedelta(seconds=30)


def test_exponential_backoff_increases_with_failures():
    first = calculate_retry(
        SyncErrorKind.TRANSIENT, 1, now=FIXED_NOW
    )
    second = calculate_retry(
        SyncErrorKind.TRANSIENT, 2, now=FIXED_NOW
    )
    third = calculate_retry(
        SyncErrorKind.TRANSIENT, 3, now=FIXED_NOW
    )

    assert second.next_retry_at - FIXED_NOW == timedelta(seconds=60)
    assert third.next_retry_at - FIXED_NOW == timedelta(seconds=120)
    assert second.next_retry_at > first.next_retry_at


@pytest.mark.parametrize(
    "error_kind",
    [
        SyncErrorKind.AUTHENTICATION,
        SyncErrorKind.VALIDATION,
        SyncErrorKind.PERMANENT,
    ],
)
def test_non_retryable_errors_are_not_retried(error_kind):
    result = calculate_retry(
        error_kind, 1, now=FIXED_NOW
    )

    assert result.should_retry is False
    assert result.next_retry_at is None


def test_retry_limit_is_enforced():
    result = calculate_retry(
        SyncErrorKind.TRANSIENT,
        6,
        now=FIXED_NOW,
        max_retries=5,
    )

    assert result.should_retry is False
    assert result.next_retry_at is None


def test_backoff_is_capped():
    result = calculate_retry(
        SyncErrorKind.TRANSIENT,
        10,
        now=FIXED_NOW,
        max_retries=10,
        max_delay_seconds=300,
    )

    assert result.should_retry is True
    assert result.next_retry_at == FIXED_NOW + timedelta(seconds=300)


def test_rate_limit_respects_retry_after_with_a_cap():
    result = calculate_retry(
        SyncErrorKind.RATE_LIMITED,
        1,
        now=FIXED_NOW,
        retry_after_seconds=5000,
        max_delay_seconds=3600,
    )

    assert result.should_retry is True
    assert result.error_code == "RATE_LIMITED"
    assert result.next_retry_at == FIXED_NOW + timedelta(seconds=3600)


def test_invalid_failure_count_is_rejected():
    with pytest.raises(ValueError):
        calculate_retry(
            SyncErrorKind.TRANSIENT, 0, now=FIXED_NOW
        )
