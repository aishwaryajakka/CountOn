from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import ResourceNotFoundError
from app.services import integration_sync_health as health
from app.services.integration_retry import SyncErrorKind, SyncStatus


class FakeDB:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def refresh(self, item):
        pass

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def setup_connection(monkeypatch):
    db = FakeDB()
    user_id = uuid4()
    connection = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        sync_status=SyncStatus.IDLE.value,
        last_attempt_at=None,
        last_synced_at=None,
        last_error_code=None,
        consecutive_failures=0,
        next_retry_at=None,
    )

    def fake_get(session, connection_id, owner_id, *, for_update=False):
        return (
            connection
            if connection_id == connection.id and owner_id == user_id
            else None
        )


    monkeypatch.setattr(health.repository, "get", fake_get)
    return db, connection, user_id


def test_start_attempt_updates_status_and_timestamp(setup_connection):
    db, connection, user_id = setup_connection

    result = health.start_attempt(db, connection.id, user_id)

    assert result.sync_status == SyncStatus.RETRYING.value
    assert result.last_attempt_at is not None
    assert result.next_retry_at is None
    assert db.commits == 1


def test_transient_failure_schedules_retry(setup_connection):
    db, connection, user_id = setup_connection

    result = health.record_failure(
        db, connection.id, user_id, SyncErrorKind.TRANSIENT
    )

    assert result.sync_status == SyncStatus.RETRYING.value
    assert result.consecutive_failures == 1
    assert result.last_error_code == "TRANSIENT_ERROR"
    assert result.next_retry_at is not None
    assert db.commits == 1


def test_authentication_failure_does_not_schedule_retry(setup_connection):
    db, connection, user_id = setup_connection

    result = health.record_failure(
        db, connection.id, user_id, SyncErrorKind.AUTHENTICATION
    )

    assert result.sync_status == SyncStatus.ERROR.value
    assert result.last_error_code == "AUTHENTICATION_ERROR"
    assert result.next_retry_at is None
    assert result.consecutive_failures == 1


def test_success_resets_failure_state(setup_connection):
    db, connection, user_id = setup_connection
    connection.consecutive_failures = 3
    connection.last_error_code = "TRANSIENT_ERROR"
    connection.next_retry_at = datetime.now(timezone.utc)

    result = health.record_success(db, connection.id, user_id)

    assert result.sync_status == SyncStatus.SUCCESS.value
    assert result.last_synced_at is not None
    assert result.consecutive_failures == 0
    assert result.last_error_code is None
    assert result.next_retry_at is None
    assert db.commits == 1


def test_other_users_connection_is_not_accessible(setup_connection):
    db, connection, user_id = setup_connection

    with pytest.raises(ResourceNotFoundError):
        health.record_success(db, connection.id, uuid4())

    assert db.commits == 0

def test_retry_limit_stops_scheduling(setup_connection):
    db, connection, user_id = setup_connection
    connection.consecutive_failures = 5

    result = health.record_failure(
        db,
        connection.id,
        user_id,
        SyncErrorKind.TRANSIENT,
        max_retries=5,
    )

    assert result.consecutive_failures == 6
    assert result.sync_status == SyncStatus.ERROR.value
    assert result.next_retry_at is None
    assert result.last_error_code == "TRANSIENT_ERROR"


def test_permanent_failure_does_not_schedule_retry(setup_connection):
    db, connection, user_id = setup_connection

    result = health.record_failure(
        db,
        connection.id,
        user_id,
        SyncErrorKind.PERMANENT,
    )

    assert result.sync_status == SyncStatus.ERROR.value
    assert result.next_retry_at is None
    assert result.last_error_code == "PERMANENT_ERROR"
