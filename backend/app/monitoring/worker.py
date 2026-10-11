"""Durable PostgreSQL leases; provider I/O outside the atomic evaluation transaction."""

import argparse
import logging
import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import observability
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.models import Expectation, ExpectationStatus, MonitoringJob
from app.db.models.integration import IntegrationConnection, IntegrationCredential
from app.db.session import SessionLocal
from app.integrations.provider import EvidenceProvider, ProviderError
from app.schemas.evidence import EvidenceCreate
from app.services import evaluation_service, evidence_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    expectation_id: UUID
    user_id: UUID
    token: UUID
    run_key: UUID


def timestamp(db: Session, now: datetime | None = None) -> datetime:
    value = now if now is not None else db.scalar(select(func.clock_timestamp()))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RuntimeError("Monitoring requires an aware database clock")
    return value


def claim_due(
    db: Session, lease_seconds: int, *, now: datetime | None = None
) -> Claim | None:
    current = timestamp(db, now)
    while True:
        job = db.scalar(
            select(MonitoringJob)
            .where(
                or_(
                    (MonitoringJob.status == "pending")
                    & (MonitoringJob.next_run_at <= current),
                    (MonitoringJob.status == "running")
                    & or_(
                        MonitoringJob.lease_expires_at <= current,
                        MonitoringJob.lease_expires_at.is_(None),
                    ),
                )
            )
            .order_by(MonitoringJob.next_run_at, MonitoringJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            db.rollback()
            return None
        if job.attempt_count >= job.max_attempts:
            job.status = "failed"
            job.last_error = "ATTEMPTS_EXHAUSTED"
            job.lease_token = job.lease_expires_at = None
            db.commit()
            continue
        job.attempt_count += 1
        job.status = "running"
        job.lease_token = uuid4()
        job.lease_expires_at = current + timedelta(seconds=lease_seconds)
        claim = Claim(
            job.id, job.expectation_id, job.user_id, job.lease_token, job.run_key
        )
        db.commit()
        return claim


def live_claim(job: MonitoringJob | None, claim: Claim, now: datetime) -> bool:
    return bool(
        job
        and job.status == "running"
        and job.lease_token == claim.token
        and job.run_key == claim.run_key
        and job.lease_expires_at
        and job.lease_expires_at > now
    )


class Worker:
    def __init__(
        self,
        settings: Settings,
        session_factory: Callable[[], Session] = SessionLocal,
        provider: EvidenceProvider | None = None,
    ):
        self.settings = settings
        self.sessions = session_factory
        self.provider = provider

    def finish(
        self,
        claim: Claim,
        evidence: list[EvidenceCreate],
        *,
        now: datetime | None = None,
    ) -> bool:
        with self.sessions() as db:
            # Same lock order as schedule/lifecycle writes. Claim acquisition never
            # waits on an expectation, and provider I/O never holds these locks.
            expectation = db.scalar(
                select(Expectation)
                .where(
                    Expectation.id == claim.expectation_id,
                    Expectation.user_id == claim.user_id,
                )
                .with_for_update()
            )
            job = db.scalar(
                select(MonitoringJob)
                .where(
                    MonitoringJob.id == claim.job_id,
                    MonitoringJob.user_id == claim.user_id,
                )
                .with_for_update()
            )
            current = timestamp(db, now)
            if not live_claim(job, claim, current):
                return False
            assert job is not None
            if expectation is None or expectation.status in (
                ExpectationStatus.cancelled,
                ExpectationStatus.resolved,
            ):
                job.status = "cancelled"
            elif (
                not job.recurring and expectation.status == ExpectationStatus.fulfilled
            ):
                job.status = "completed"
            else:
                provider_identity = None
                if job.connection_id:
                    connection = db.scalar(
                        select(IntegrationConnection)
                        .where(
                            IntegrationConnection.id == job.connection_id,
                            IntegrationConnection.user_id == claim.user_id,
                        )
                        .with_for_update()
                    )
                    if (
                        connection is None
                        or connection.status != "connected"
                        or connection.provider != "microsoft"
                        or connection.connection_type != "email"
                        or "Mail.ReadBasic" not in connection.scopes
                        or not connection.external_account_id
                        or db.get(IntegrationCredential, job.connection_id) is None
                    ):
                        raise ProviderError("AUTH_REQUIRED", retryable=False)
                    provider_identity = {
                        "provider": "microsoft_graph",
                        "connection_id": str(connection.id),
                        "account_id": connection.external_account_id,
                    }
                    if any(
                        payload.source != "outlook_email"
                        or any(
                            payload.raw_data.get(k) != v
                            for k, v in provider_identity.items()
                        )
                        for payload in evidence
                    ):
                        raise ProviderError("PERMISSION_DENIED", retryable=False)
                    connection.last_synced_at = current
                for payload in evidence:
                    evidence_service.add_evidence(
                        db,
                        expectation.id,
                        payload,
                        claim.user_id,
                        idempotency_key=payload.external_event_id,
                        commit=False,
                    )
                result = evaluation_service.evaluate_expectation(
                    db,
                    expectation.id,
                    claim.user_id,
                    idempotency_key=f"monitor:{job.id}:{claim.run_key}",
                    commit=False,
                    monitoring_at=current,
                    max_evidence_age_seconds=job.max_evidence_age_seconds,
                    window_start=job.window_start_at,
                    provider_identity=provider_identity,
                )
                job.last_run_at = current
                if result.result.value == "UNKNOWN":
                    expectation.status = ExpectationStatus.monitoring
                if not job.recurring and result.result.value == "MATCH":
                    job.status = "completed"
                else:
                    # Skip missed polling intervals; do not produce catch-up storms.
                    period = timedelta(seconds=job.interval_seconds)
                    elapsed = max(
                        1,
                        int((current - job.scheduled_at).total_seconds())
                        // job.interval_seconds
                        + 1,
                    )
                    if job.recurring:
                        job.window_start_at = job.scheduled_at + period * (elapsed - 1)
                    job.scheduled_at += period * elapsed
                    job.next_run_at = job.scheduled_at
                    job.run_key = uuid4()
                    job.status = "pending"
                job.attempt_count = 0
                job.last_error = None
            job.lease_token = job.lease_expires_at = None
            db.commit()
        logger.info(
            "Monitoring run persisted",
            extra={
                "expectation_id": str(claim.expectation_id),
                "result_status": "success",
            },
        )
        return True

    def fail(
        self, claim: Claim, error: ProviderError, *, now: datetime | None = None
    ) -> None:
        with self.sessions() as db:
            job = db.scalar(
                select(MonitoringJob)
                .where(MonitoringJob.id == claim.job_id)
                .with_for_update()
            )
            current = timestamp(db, now)
            if not live_claim(job, claim, current):
                return
            assert job is not None
            job.last_error = error.code
            if not error.retryable or job.attempt_count >= job.max_attempts:
                job.status = "failed"  # durable dead-letter row; explicit requeue only
            else:
                job.status = "pending"
                delay = min(
                    86400,
                    self.settings.monitoring_backoff_seconds
                    * 2 ** (job.attempt_count - 1),
                )
                job.next_run_at = current + timedelta(
                    seconds=max(delay, error.retry_after)
                )
            job.lease_token = job.lease_expires_at = None
            db.commit()
        logger.warning(
            "Monitoring run deferred",
            extra={
                "expectation_id": str(claim.expectation_id),
                "result_status": "failed",
            },
        )

    def run_once(self, *, now: datetime | None = None) -> bool:
        with self.sessions() as db:
            claim = claim_due(db, self.settings.monitoring_lease_seconds, now=now)
        if claim is None:
            return False
        correlation = observability.request_id.set(str(claim.run_key))
        started = perf_counter()
        try:
            payloads = []
            with self.sessions() as db:
                job = db.get(MonitoringJob, claim.job_id)
                expectation = db.scalar(
                    select(Expectation).where(
                        Expectation.id == claim.expectation_id,
                        Expectation.user_id == claim.user_id,
                    )
                )
                current = timestamp(db, now)
                if not live_claim(job, claim, current):
                    return True
                assert job is not None
                if (
                    expectation is not None
                    and expectation.status
                    not in (ExpectationStatus.cancelled, ExpectationStatus.resolved)
                    and (
                        job.recurring
                        or expectation.status != ExpectationStatus.fulfilled
                    )
                    and job.connection_id
                ):
                    provider = self.provider
                    if provider is None:
                        from app.integrations.microsoft import OutlookProvider

                        provider = OutlookProvider(self.settings)
                    payloads = provider.fetch(db, job, expectation, current)
            self.finish(claim, payloads, now=now)
        except ProviderError as error:
            self.fail(claim, error, now=now)
        except Exception:  # noqa: BLE001 -- never log provider bodies, tokens, SQL or exception text
            self.fail(claim, ProviderError("WORKER_ERROR"), now=now)
        finally:
            observability.record("monitoring_attempts", "worker")
            observability.record(
                "monitoring_latency_seconds", "worker", perf_counter() - started
            )
            observability.request_id.reset(correlation)
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Attempt one due job then exit"
    )
    args = parser.parse_args()
    settings = get_settings()
    configure_logging()
    if not settings.monitoring_enabled:
        print("Monitoring disabled; set MONITORING_ENABLED=true on the trusted backend")
        return 1
    worker = Worker(settings)
    stopped = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stopped.set())
    while not stopped.is_set():
        try:
            processed = worker.run_once()
        except Exception:  # noqa: BLE001 -- database outage leaves leases reclaimable
            logger.error("Monitoring database unavailable")
            if args.once:
                return 1
            processed = False
        if args.once:
            return 0
        if not processed:
            stopped.wait(settings.monitoring_poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
