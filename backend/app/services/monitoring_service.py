
"""Background monitoring for CountOn expectations."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Expectation,
    ExpectationStatus,
    Evidence,
    MonitoringJob,
)
from app.db.session import SessionLocal
from app.repositories.notification import create_monitoring_notification

logger = logging.getLogger(__name__)

CHECK_INTERVAL_MINUTES = 60
BATCH_SIZE = 50


def process_monitoring_job(db: Session, job: MonitoringJob) -> None:
    """Process one monitoring job within the caller's transaction."""
    now = datetime.now(timezone.utc)

    expectation = db.scalar(
        select(Expectation).where(
            Expectation.id == job.expectation_id,
            Expectation.user_id == job.user_id,
        )
    )

    # Cancel jobs whose expectation no longer exists.
    if expectation is None:
        job.status = "cancelled"
        job.last_error = None
        job.last_run_at = now
        return

    # Stop monitoring terminal expectations.
    if expectation.status in (
        ExpectationStatus.resolved,
        ExpectationStatus.cancelled,
        ExpectationStatus.fulfilled,
        ExpectationStatus.contradicted,
    ):
        job.status = "completed"
        job.last_error = None
        job.last_run_at = now
        return

    # Check whether relevant evidence exists.
    evidence_statement = select(Evidence.id).where(
        Evidence.expectation_id == expectation.id
    )

    if expectation.metric is not None:
        evidence_statement = evidence_statement.where(
            Evidence.metric == expectation.metric
        )

    has_evidence = (
        db.scalar(evidence_statement.limit(1)) is not None
    )

    # Notify when the expectation's deadline has passed.
    if expectation.deadline is not None and expectation.deadline <= now:
        logger.info(
            "Monitoring found overdue expectation id=%s",
            expectation.id,
        )

        create_monitoring_notification(
            db=db,
            expectation=expectation,
            notification_type="expectation_overdue",
            message="An expectation has passed its deadline.",
        )

    # Check independently so both alerts can be created when applicable.
    if not has_evidence:
        logger.info(
            "Monitoring found missing evidence expectation id=%s",
            expectation.id,
        )

        create_monitoring_notification(
            db=db,
            expectation=expectation,
            notification_type="missing_evidence",
            message="An expectation is missing relevant evidence.",
        )

    # Schedule the next recurring check.
    job.last_run_at = now
    job.attempt_count += 1
    job.last_error = None
    job.next_run_at = now + timedelta(
        minutes=CHECK_INTERVAL_MINUTES
    )
    job.status = "pending"


def run_monitoring_cycle() -> dict[str, int]:
    """Process a bounded batch of due monitoring jobs."""
    now = datetime.now(timezone.utc)
    processed = 0
    failed = 0

    with SessionLocal() as db:
        try:
            jobs = list(
                db.scalars(
                    select(MonitoringJob)
                    .where(
                        MonitoringJob.status == "pending",
                        MonitoringJob.next_run_at <= now,
                    )
                    .order_by(
                        MonitoringJob.next_run_at,
                        MonitoringJob.id,
                    )
                    .limit(BATCH_SIZE)
                    .with_for_update(skip_locked=True)
                )
            )

            for job in jobs:
                try:
                    # A savepoint helps isolate an individual job failure.
                    with db.begin_nested():
                        process_monitoring_job(db, job)

                    processed += 1

                except Exception:
                    logger.exception(
                        "Monitoring job failed id=%s",
                        job.id,
                    )

                    # Keep the failed job eligible for a later retry.
                    job.last_error = "MONITORING_JOB_FAILED"
                    job.last_run_at = now
                    job.attempt_count += 1
                    job.next_run_at = now + timedelta(
                        minutes=CHECK_INTERVAL_MINUTES
                    )
                    job.status = "pending"
                    failed += 1

            db.commit()

        except Exception:
            db.rollback()
            logger.exception("Monitoring cycle failed")
            raise

    return {
        "processed": processed,
        "failed": failed,
    }
