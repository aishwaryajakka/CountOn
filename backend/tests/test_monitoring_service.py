
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy import select

from app.db.models import (
    ComparisonType,
    Expectation,
    ExpectationStatus,
    ExpectationType,
    MonitoringJob,
    Notification,
)
from app.repositories.operations import ensure_job
from app.services import monitoring_service


def make_expectation(
    *,
    deadline=None,
    metric="total_cost",
    status=ExpectationStatus.monitoring,
):
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status=status,
        deadline=deadline,
        metric=metric,
        compiler_metadata={},
    )


def make_job(expectation):
    return SimpleNamespace(
        id=uuid4(),
        expectation_id=expectation.id,
        user_id=expectation.user_id,
        status="pending",
        last_error=None,
        last_run_at=None,
        next_run_at=None,
        attempt_count=0,
    )


def test_missing_evidence_creates_notification(monkeypatch):
    expectation = make_expectation()
    job = make_job(expectation)
    db = Mock()

    # First scalar call loads the expectation; second checks evidence.
    db.scalar.side_effect = [expectation, None]

    create_notification = Mock(return_value=(object(), True))
    monkeypatch.setattr(
        monitoring_service,
        "create_monitoring_notification",
        create_notification,
    )

    monitoring_service.process_monitoring_job(db, job)

    create_notification.assert_called_once_with(
        db=db,
        expectation=expectation,
        notification_type="missing_evidence",
        message="An expectation is missing relevant evidence.",
    )
    assert job.status == "pending"
    assert job.attempt_count == 1
    assert job.last_error is None
    assert job.next_run_at > job.last_run_at


def test_overdue_expectation_creates_notification(monkeypatch):
    expectation = make_expectation(
        deadline=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    job = make_job(expectation)
    db = Mock()
    db.scalar.side_effect = [expectation, object()]

    create_notification = Mock(return_value=(object(), True))
    monkeypatch.setattr(
        monitoring_service,
        "create_monitoring_notification",
        create_notification,
    )

    monitoring_service.process_monitoring_job(db, job)

    create_notification.assert_called_once_with(
        db=db,
        expectation=expectation,
        notification_type="expectation_overdue",
        message="An expectation has passed its deadline.",
    )
    assert job.status == "pending"
    assert job.attempt_count == 1


def test_overdue_and_missing_evidence_create_both_notifications(
    monkeypatch,
):
    expectation = make_expectation(
        deadline=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    job = make_job(expectation)
    db = Mock()
    db.scalar.side_effect = [expectation, None]

    create_notification = Mock(return_value=(object(), True))
    monkeypatch.setattr(
        monitoring_service,
        "create_monitoring_notification",
        create_notification,
    )

    monitoring_service.process_monitoring_job(db, job)

    types = [
        call.kwargs["notification_type"]
        for call in create_notification.call_args_list
    ]
    assert types == ["expectation_overdue", "missing_evidence"]
    assert job.status == "pending"
    assert job.attempt_count == 1


def test_terminal_expectation_completes_job(monkeypatch):
    expectation = make_expectation(status=ExpectationStatus.fulfilled)
    job = make_job(expectation)
    db = Mock()
    db.scalar.return_value = expectation

    create_notification = Mock()
    monkeypatch.setattr(
        monitoring_service,
        "create_monitoring_notification",
        create_notification,
    )

    monitoring_service.process_monitoring_job(db, job)

    assert job.status == "completed"
    assert job.last_error is None
    assert job.last_run_at is not None
    create_notification.assert_not_called()


def test_monitoring_job_is_rescheduled_for_next_check(monkeypatch):
    expectation = make_expectation()
    job = make_job(expectation)
    db = Mock()
    db.scalar.side_effect = [expectation, object()]

    monkeypatch.setattr(
        monitoring_service,
        "create_monitoring_notification",
        Mock(),
    )

    before = datetime.now(timezone.utc)

    monitoring_service.process_monitoring_job(db, job)

    after = datetime.now(timezone.utc)

    assert job.status == "pending"
    assert job.attempt_count == 1
    assert job.last_error is None
    assert job.last_run_at is not None
    assert before <= job.last_run_at <= after

    expected_delay = timedelta(
        minutes=monitoring_service.CHECK_INTERVAL_MINUTES
    )
    assert job.next_run_at == (
        job.last_run_at + expected_delay
    )



def test_existing_monitoring_notification_is_not_created_again(
    monkeypatch,
):
    from app.repositories import notification as notification_repository

    expectation = make_expectation()
    db = Mock()

    # Simulate PostgreSQL preventing a duplicate insert.
    db.scalar.return_value = None

    result = notification_repository.create_monitoring_notification(
        db=db,
        expectation=expectation,
        notification_type="missing_evidence",
        message="An expectation is missing relevant evidence.",
    )

    assert result == (None, False)
    db.add.assert_not_called()
    db.flush.assert_not_called()

def test_monitoring_job_creates_real_notifications_and_reschedules(db, users):
    user = users[0]

    expectation = Expectation(
        user_id=user.id,
        claim="Test expectation for monitoring",
        type=ExpectationType.numeric_comparison,
        metric="total_cost",
        comparison=ComparisonType.less_than,
        deadline=datetime.now(timezone.utc) - timedelta(hours=1),
        evidence_sources=[],
        status=ExpectationStatus.monitoring,
    )
    db.add(expectation)
    db.flush()

    ensure_job(db, expectation)
    db.flush()

    job = db.scalar(
        select(MonitoringJob).where(
            MonitoringJob.expectation_id == expectation.id
        )
    )
    assert job is not None

    monitoring_service.process_monitoring_job(db, job)
    db.flush()

    notification_types = set(
        db.scalars(
            select(Notification.type).where(
                Notification.expectation_id == expectation.id,
                Notification.user_id == user.id,
            )
        )
    )

    assert notification_types == {
        "expectation_overdue",
        "missing_evidence",
    }
    assert job.status == "pending"
    assert job.attempt_count == 1
    assert job.last_error is None
    assert job.next_run_at > job.last_run_at
