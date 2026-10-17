
"""Safe retry policy for transient integration sync failures."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum


class SyncStatus(StrEnum):
    IDLE = "idle"
    SUCCESS = "success"
    ERROR = "error"
    RETRYING = "retrying"


class SyncErrorKind(StrEnum):
    TRANSIENT = "transient"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    next_retry_at: datetime | None
    error_code: str


def calculate_retry(
    error_kind: SyncErrorKind,
    consecutive_failures: int,
    *,
    now: datetime | None = None,
    max_retries: int = 5,
    base_delay_seconds: int = 30,
    max_delay_seconds: int = 3600,
    retry_after_seconds: int | None = None,
) -> RetryDecision:
    """Calculate a bounded retry time; never retry permanent/auth errors."""
    if consecutive_failures < 1:
        raise ValueError("consecutive_failures must be at least 1")
    if max_retries < 0 or base_delay_seconds < 0 or max_delay_seconds < 0:
        raise ValueError("Retry limits cannot be negative")

    codes = {
        SyncErrorKind.TRANSIENT: "TRANSIENT_ERROR",
        SyncErrorKind.RATE_LIMITED: "RATE_LIMITED",
        SyncErrorKind.AUTHENTICATION: "AUTHENTICATION_ERROR",
        SyncErrorKind.VALIDATION: "VALIDATION_ERROR",
        SyncErrorKind.PERMANENT: "PERMANENT_ERROR",
    }
    code = codes[error_kind]

    retryable = error_kind in {
        SyncErrorKind.TRANSIENT,
        SyncErrorKind.RATE_LIMITED,
    }
    if not retryable or consecutive_failures > max_retries:
        return RetryDecision(False, None, code)

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now must include timezone information")

    exponential_delay = min(
        base_delay_seconds * (2 ** (consecutive_failures - 1)),
        max_delay_seconds,
    )
    if error_kind == SyncErrorKind.RATE_LIMITED and retry_after_seconds is not None:
        delay = min(max(retry_after_seconds, 0), max_delay_seconds)
    else:
        delay = exponential_delay

    return RetryDecision(
        should_retry=True,
        next_retry_at=current_time + timedelta(seconds=delay),
        error_code=code,
    )
