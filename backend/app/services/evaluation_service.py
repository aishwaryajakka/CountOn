"""Deterministic evaluation orchestration with one atomic persistence commit."""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import observability
from app.core.exceptions import EvaluationNotFoundError
from app.db.models import Evaluation, Expectation, ExpectationStatus, ExpectationType
from app.evaluators import boolean, numeric, temporal
from app.evaluators.base import EvaluationOutput, EvaluationResult
from app.repositories import evaluation as repository
from app.repositories import evidence as evidence_repository
from app.repositories import expectation as expectation_repository
from app.repositories import operations
from app.services import notification_service
from app.services.expectation_service import get_expectation

logger = logging.getLogger(__name__)


def evaluate_expectation(db: Session, expectation_id: UUID, user_id: UUID, *,
                         idempotency_key: str | None = None, commit: bool = True,
                         monitoring_at: datetime | None = None, max_evidence_age_seconds: int = 86400,
                         window_start: datetime | None = None,
                         provider_identity: dict | None = None) -> Evaluation:
    expectation = get_expectation(db, expectation_id, user_id)
    if idempotency_key:
        db.scalar(select(Expectation).where(Expectation.id == expectation_id,
                                           Expectation.user_id == user_id).with_for_update())
        existing = db.scalar(select(Evaluation).where(Evaluation.expectation_id == expectation_id,
                                                     Evaluation.idempotency_key == idempotency_key))
        if existing is not None:
            return existing
    evidence = [] if monitoring_at else evidence_repository.latest_relevant_evidence(db, expectation_id, expectation.metric)
    evaluator = {
        ExpectationType.numeric_comparison: numeric.evaluate,
        ExpectationType.boolean: boolean.evaluate,
        ExpectationType.temporal: temporal.evaluate,
        ExpectationType.event: temporal.evaluate,
    }.get(expectation.type)
    output = evaluator(expectation, evidence) if evaluator else EvaluationOutput(
        result=EvaluationResult.UNKNOWN, confidence=0.0,
        reasoning={"reason": "unsupported_expectation_type"},
    )
    dedupe_key = None
    if monitoring_at:
        from app.monitoring.evidence import evaluate
        output, dedupe_key = evaluate(db, expectation, now=monitoring_at,
            max_age=max_evidence_age_seconds, window_start=window_start, provider_identity=provider_identity)
    status = expectation.status
    # Keep terminal statuses, while still recording a new evaluation in history.
    if status not in (ExpectationStatus.resolved, ExpectationStatus.cancelled):
        if output.result == EvaluationResult.MATCH:
            status = ExpectationStatus.fulfilled
        elif output.result == EvaluationResult.MISMATCH:
            status = ExpectationStatus.contradicted
        # UNKNOWN preserves the existing status, including monitoring.
    try:
        persisted = repository.create_evaluation(db, expectation_id, output)
        persisted.idempotency_key = idempotency_key
        db.flush()
        if status != expectation.status:
            expectation_repository.update_expectation(db, expectation, {"status": status})
        operations.audit(db, expectation, "expectation.evaluated", persisted.id)
        notification = notification_service.for_evaluation(db, expectation, persisted, dedupe_key=dedupe_key)
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
        raise
    if commit:
        observability.record("evaluation_results", output.result.value)
        if notification is not None:
            observability.record("notifications_created")
    db.refresh(persisted)
    if commit:
        logger.info("Evaluation completed id=%s expectation_id=%s result=%s", persisted.id, expectation_id, output.result.value)
    return persisted


def list_evaluations(db: Session, expectation_id: UUID, user_id: UUID, limit: int = 100, offset: int = 0) -> list[Evaluation]:
    get_expectation(db, expectation_id, user_id)
    return repository.list_evaluations_for_expectation(db, expectation_id, limit, offset)


def get_latest_evaluation(db: Session, expectation_id: UUID, user_id: UUID) -> Evaluation:
    get_expectation(db, expectation_id, user_id)
    evaluation = repository.get_latest_evaluation(db, expectation_id)
    if evaluation is None:
        raise EvaluationNotFoundError(expectation_id)
    return evaluation
