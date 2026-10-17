"""Track connector sync attempts, safe errors, retries, and recovery."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.repositories import integration as repository
from app.services.integration_retry import (
    SyncErrorKind,
    SyncStatus,
    calculate_retry,
)


def _get_connection(
    db: Session,
    connection_id: UUID,
    user_id: UUID,
    *,
    for_update: bool = False,
):
    item = repository.get(
        db,
        connection_id,
        user_id,
        for_update=for_update,
    )
    if item is None:
        raise ResourceNotFoundError(
            "INTEGRATION_NOT_FOUND", "Integration not found"
        )
    return item


def start_attempt(db: Session, connection_id: UUID, user_id: UUID):
    """Record the start of an explicitly triggered sync attempt."""
    item = _get_connection(db, connection_id, user_id)
    try:
        item.sync_status = SyncStatus.RETRYING.value
        item.last_attempt_at = datetime.now(timezone.utc)
        item.next_retry_at = None
        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise


def record_failure(
    db: Session,
    connection_id: UUID,
    user_id: UUID,
    error_kind: SyncErrorKind,
    *,
    retry_after_seconds: int | None = None,
    max_retries: int = 5,
):
    """Persist a classified error without storing raw exception details."""
    item = _get_connection(db, connection_id, user_id)
    try:
        failures = item.consecutive_failures + 1
        decision = calculate_retry(
            error_kind,
            failures,
            now=datetime.now(timezone.utc),
            max_retries=max_retries,
            retry_after_seconds=retry_after_seconds,
        )

        item.last_attempt_at = datetime.now(timezone.utc)
        item.consecutive_failures = failures
        item.last_error_code = decision.error_code
        item.next_retry_at = decision.next_retry_at
        item.sync_status = (
            SyncStatus.RETRYING.value
            if decision.should_retry
            else SyncStatus.ERROR.value
        )

        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise


def record_success(
    db: Session,
    connection_id: UUID,
    user_id: UUID,
):
    """Clear failure state after a confirmed successful sync."""
    item = _get_connection(
        db, connection_id, user_id, for_update=True
    )
    try:
        now = datetime.now(timezone.utc)
        item.sync_status = SyncStatus.SUCCESS.value
        item.last_attempt_at = now
        item.last_synced_at = now
        item.last_error_code = None
        item.consecutive_failures = 0
        item.next_retry_at = None

        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise
