"""Owner-authenticated scheduling on the existing job table; invalidate stale leases."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidExpectationError, ResourceNotFoundError
from app.db.models import Expectation, ExpectationStatus, MonitoringJob
from app.db.models.integration import IntegrationConnection, IntegrationCredential
from app.repositories import operations
from app.schemas.monitoring import MonitoringSchedule
from app.services.expectation_service import get_expectation


def get(db: Session, expectation_id: UUID, user_id: UUID) -> MonitoringJob:
    get_expectation(db, expectation_id, user_id)
    job = db.scalar(
        select(MonitoringJob)
        .where(
            MonitoringJob.expectation_id == expectation_id,
            MonitoringJob.user_id == user_id,
        )
        .order_by(
            MonitoringJob.status.in_(["pending", "running", "paused"]).desc(),
            MonitoringJob.created_at.desc(),
            MonitoringJob.id.desc(),
        )
        .limit(1)
    )
    if job is None:
        raise ResourceNotFoundError(
            "MONITORING_NOT_FOUND", "Monitoring schedule not found"
        )
    return job


def configure(
    db: Session, expectation_id: UUID, user_id: UUID, schedule: MonitoringSchedule
) -> MonitoringJob:
    get_expectation(db, expectation_id, user_id)
    expectation = db.scalar(
        select(Expectation)
        .where(Expectation.id == expectation_id, Expectation.user_id == user_id)
        .with_for_update()
    )
    if expectation is None or expectation.status in (
        ExpectationStatus.cancelled,
        ExpectationStatus.resolved,
    ):
        raise InvalidExpectationError("Terminal expectations cannot be monitored")
    if schedule.recurring and expectation.type.value in ("temporal", "event"):
        raise InvalidExpectationError(
            "Recurring temporal deadlines require explicit per-period criteria; use a single deadline"
        )
    if schedule.connection_id:
        connection = db.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.id == schedule.connection_id,
                IntegrationConnection.user_id == user_id,
            )
        )
        if connection is None:
            raise ResourceNotFoundError(
                "INTEGRATION_NOT_FOUND", "Integration not found"
            )
        if (
            connection.provider != "microsoft"
            or connection.connection_type != "email"
            or connection.status != "connected"
            or "Mail.ReadBasic" not in connection.scopes
            or db.get(IntegrationCredential, connection.id) is None
            or expectation.type.value != "numeric_comparison"
            or not expectation.metric
            or "outlook_email" not in expectation.evidence_sources
        ):
            raise InvalidExpectationError(
                "Outlook monitoring requires a connected email account and an explicit numeric outlook_email source"
            )
    # Reuse the active row, or the latest completed/dead-letter row. No duplicate job.
    job = db.scalar(
        select(MonitoringJob)
        .where(
            MonitoringJob.expectation_id == expectation_id,
            MonitoringJob.user_id == user_id,
        )
        .order_by(
            MonitoringJob.status.in_(["pending", "running", "paused"]).desc(),
            MonitoringJob.created_at.desc(),
            MonitoringJob.id.desc(),
        )
        .with_for_update()
        .limit(1)
    )
    if job is None:
        job = MonitoringJob(expectation_id=expectation_id, user_id=user_id)
        db.add(job)
    for field in (
        "next_run_at",
        "interval_seconds",
        "recurring",
        "window_start_at",
        "max_evidence_age_seconds",
        "max_attempts",
        "status",
        "connection_id",
    ):
        setattr(job, field, getattr(schedule, field))
    job.scheduled_at = schedule.next_run_at
    job.provider_config = (
        schedule.outlook_rule.model_dump() if schedule.outlook_rule else {}
    )
    job.run_key = uuid4()
    job.lease_token = job.lease_expires_at = job.last_error = None
    job.attempt_count = 0
    operations.audit(db, expectation, "monitoring.configured")
    db.commit()
    db.refresh(job)
    return job
