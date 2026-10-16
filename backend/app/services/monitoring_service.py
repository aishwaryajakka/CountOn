"""
Continuous Monitoring & Automated External Account Event Trigger Service.
Orchestrates automatic data fetching, event triggers, evidence ingestion,
continuous evaluation, and proactive mismatch notification with Bedrock 'Why?' explanations.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Expectation, ExpectationStatus, ExpectationType
from app.db.models.operations import Notification
from app.schemas.evidence import EvidenceCreate
from app.repositories import evidence as evidence_repository
from app.services import evaluation_service, investigator_service, expectation_service
from app.ai.gmail_intelligence import (
    GmailContextPayload,
    extract_from_gmail_context,
    convert_gmail_to_evidence,
)
from app.ai.outlook_intelligence import (
    OutlookContextPayload,
    extract_from_outlook_context,
    convert_outlook_to_evidence,
)
from app.ai.amazon_intelligence import (
    AmazonDeliveryPayload,
    AmazonOrderContext,
    extract_from_amazon_context,
    convert_amazon_to_evidence,
)
from app.schemas.expectation import ExpectationCreate
from app.ai.models.expectation import InvestigationResult

logger = logging.getLogger(__name__)


class MonitoringEventResult:
    """Result of processing an external account event trigger."""
    def __init__(
        self,
        expectation_id: UUID,
        provider: str,
        event_type: str,
        evaluation_result: str,
        mismatch_detected: bool,
        evidence_created: int,
        summary: str,
        investigation: Optional[InvestigationResult] = None,
        notification_id: Optional[UUID] = None,
    ):
        self.expectation_id = expectation_id
        self.provider = provider
        self.event_type = event_type
        self.evaluation_result = evaluation_result
        self.mismatch_detected = mismatch_detected
        self.evidence_created = evidence_created
        self.summary = summary
        self.investigation = investigation
        self.notification_id = notification_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "expectation_id": str(self.expectation_id),
            "provider": self.provider,
            "event_type": self.event_type,
            "evaluation_result": self.evaluation_result,
            "mismatch_detected": self.mismatch_detected,
            "evidence_created": self.evidence_created,
            "summary": self.summary,
            "investigation": self.investigation.model_dump() if self.investigation else None,
            "notification_id": str(self.notification_id) if self.notification_id else None,
        }


def _find_or_create_expectation_for_event(
    db: Session,
    user_id: UUID,
    provider: str,
    extracted_exp: Any,
) -> Expectation:
    """
    Finds an existing active expectation matching the provider/metric or auto-creates one.
    """
    # 1. Search existing expectations for this user
    active_expectations = list(
        db.scalars(
            select(Expectation).where(
                Expectation.user_id == user_id,
                Expectation.status.in_([ExpectationStatus.monitoring, ExpectationStatus.unknown]),
            )
        )
    )

    metric = getattr(extracted_exp, "metric", None)
    exp_type = getattr(extracted_exp, "type", "event")

    # Match by metric or evidence source
    for exp in active_expectations:
        if metric and exp.metric == metric:
            return exp
        if provider in (exp.evidence_sources or []):
            return exp

    # 2. Auto-create expectation if none exists
    type_enum = ExpectationType.event
    if exp_type == "numeric_comparison":
        type_enum = ExpectationType.numeric_comparison
    elif exp_type == "delivery":
        type_enum = ExpectationType.event

    claim = getattr(extracted_exp, "claim", f"Automatic tracking for {provider} event")
    sources = getattr(extracted_exp, "evidence_sources", [provider])

    new_create = ExpectationCreate(
        claim=claim,
        type=type_enum,
        metric=metric or "status",
        evidence_sources=sources,
        materiality_threshold=0.05,
    )
    return expectation_service.create_expectation(db, new_create, user_id)


def trigger_account_event(
    db: Session,
    user_id: UUID,
    provider: str,
    event_type: str,
    payload: dict[str, Any],
    mock_mode: bool | None = None,
) -> MonitoringEventResult:
    """
    Processes an external account event (Gmail, Outlook, Amazon, Calendar) end-to-end:
    1. Extracts expectation and normalized evidence using AI intelligence modules.
    2. Maps to or creates an expectation.
    3. Persists evidence to DB.
    4. Evaluates expectation deterministically.
    5. If MISMATCH (e.g. carrier delay, cancellation, reschedule), triggers Bedrock Investigator
       and enriches the proactive notification.
    """
    provider_lower = provider.strip().lower()
    extracted_evidence = []
    extracted_exp = None
    summary = ""

    # 1. Extract context based on provider
    if provider_lower in ("gmail", "google"):
        ctx = GmailContextPayload.model_validate(payload)
        res = extract_from_gmail_context(ctx)
        extracted_exp = res.expectation
        extracted_evidence = res.extracted_evidence
        summary = res.summary

    elif provider_lower in ("outlook", "microsoft"):
        ctx = OutlookContextPayload.model_validate(payload)
        res = extract_from_outlook_context(ctx)
        extracted_exp = res.expectation
        extracted_evidence = res.extracted_evidence
        summary = res.summary

    elif provider_lower in ("amazon", "delivery"):
        ctx = AmazonDeliveryPayload.model_validate(payload)
        res = extract_from_amazon_context(ctx)
        extracted_exp = res.expectation
        extracted_evidence = res.extracted_evidence
        summary = res.summary

    else:
        # Generic payload fallback
        summary = f"Generic event received from {provider}"

    # 2. Find or auto-create expectation
    expectation = _find_or_create_expectation_for_event(
        db=db,
        user_id=user_id,
        provider=provider_lower,
        extracted_exp=extracted_exp,
    )

    # 3. Persist normalized evidence records
    now_utc = datetime.now(timezone.utc)
    created_count = 0

    for ev in extracted_evidence:
        # Value must be a dictionary according to EvidenceCreate schema
        val_dict = ev.value if isinstance(ev.value, dict) else {"observed": ev.value}
        ev_create = EvidenceCreate(
            source=ev.source or provider_lower,
            metric=ev.metric or expectation.metric or "status",
            value=val_dict,
            unit=ev.unit,
            observed_at=now_utc,
            confidence=ev.confidence,
            raw_data={"provider": provider_lower, "event_type": event_type},
        )
        evidence_repository.create_evidence(db, expectation.id, ev_create)
        created_count += 1

    db.commit()

    # 4. Deterministic Evaluation
    evaluation = evaluation_service.evaluate_expectation(db, expectation.id, user_id)
    eval_result_str = evaluation.result.value if hasattr(evaluation.result, "value") else str(evaluation.result)
    is_mismatch = eval_result_str == "MISMATCH"

    investigation_res = None
    notification_id = None

    # 5. Proactive Investigation on Mismatch
    if is_mismatch:
        try:
            investigation_res = investigator_service.investigate_expectation_mismatch(
                db=db,
                expectation_id=expectation.id,
                user_id=user_id,
                mock_mode=mock_mode,
            )

            # Find and enrich the generated in-app notification
            notification = db.scalar(
                select(Notification).where(
                    Notification.expectation_id == expectation.id,
                    Notification.user_id == user_id,
                ).order_by(Notification.created_at.desc())
            )

            if notification:
                notification_id = notification.id
                notification.message = f"Mismatch Detected: {investigation_res.explanation}"
                meta = dict(notification.notification_metadata or {})
                meta["key_factors"] = investigation_res.key_factors
                meta["confidence"] = investigation_res.confidence
                meta["provider"] = provider_lower
                meta["evidence_summary"] = summary
                notification.notification_metadata = meta
                db.commit()

        except Exception as inv_err:
            logger.warning("Investigation on mismatch failed: %s", inv_err)

    return MonitoringEventResult(
        expectation_id=expectation.id,
        provider=provider_lower,
        event_type=event_type,
        evaluation_result=eval_result_str,
        mismatch_detected=is_mismatch,
        evidence_created=created_count,
        summary=summary,
        investigation=investigation_res,
        notification_id=notification_id,
    )


def run_continuous_monitoring_sweep(
    db: Session,
    user_id: UUID,
    mock_mode: bool | None = None,
) -> dict[str, Any]:
    """
    Performs a continuous monitoring sweep across all active user expectations:
    - Re-evaluates each monitoring expectation against latest evidence.
    - Flags contradictions, delays, and mismatches.
    - Generates Bedrock 'Why?' explanations and updates notifications proactively.
    """
    active_expectations = list(
        db.scalars(
            select(Expectation).where(
                Expectation.user_id == user_id,
                Expectation.status == ExpectationStatus.monitoring,
            )
        )
    )

    total = len(active_expectations)
    evaluated = 0
    mismatches = 0
    matches = 0
    unknowns = 0

    for exp in active_expectations:
        try:
            eval_res = evaluation_service.evaluate_expectation(db, exp.id, user_id)
            res_val = eval_res.result.value if hasattr(eval_res.result, "value") else str(eval_res.result)
            evaluated += 1

            if res_val == "MISMATCH":
                mismatches += 1
                try:
                    investigator_service.investigate_expectation_mismatch(
                        db=db,
                        expectation_id=exp.id,
                        user_id=user_id,
                        mock_mode=mock_mode,
                    )
                except Exception:
                    pass
            elif res_val == "MATCH":
                matches += 1
            else:
                unknowns += 1
        except Exception as e:
            logger.warning("Error evaluating expectation %s: %s", exp.id, e)

    return {
        "status": "completed",
        "total_active": total,
        "evaluated": evaluated,
        "matches": matches,
        "mismatches": mismatches,
        "unknowns": unknowns,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# =====================================================================
# Scheduled MonitoringJob CRUD & Scheduling (from feature branch)
# =====================================================================
from uuid import uuid4
from app.core.exceptions import InvalidExpectationError, ResourceNotFoundError
from app.db.models.operations import MonitoringJob
from app.db.models.integration import IntegrationConnection, IntegrationCredential
from app.repositories import operations
from app.schemas.monitoring import MonitoringSchedule
from app.services.expectation_service import get_expectation


def get(db: Session, expectation_id: UUID, user_id: UUID) -> MonitoringJob:
    """Retrieve the latest active or configured monitoring job for an expectation."""
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
    """Configure or update the monitoring schedule on an expectation."""
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

